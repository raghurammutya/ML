from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Iterable

from zoneinfo import ZoneInfo

from loguru import logger

from .accounts import SessionOrchestrator
from .config import get_settings
from .instrument_registry import instrument_registry
from .subscription_store import SubscriptionRecord, subscription_store
from .kite.client import KiteClient
from .publisher import publish_option_snapshot, publish_underlying_bar
from .schema import Instrument, OptionSnapshot

settings = get_settings()


@dataclass
class SubscriptionPlanItem:
    record: SubscriptionRecord
    instrument: Instrument


@dataclass
class MockOptionState:
    instrument: Instrument
    base_price: float
    last_price: float
    base_volume: int
    base_oi: int
    iv: float
    delta: float
    gamma: float
    theta: float
    vega: float


@dataclass
class MockUnderlyingState:
    symbol: str
    base_open: float
    base_high: float
    base_low: float
    base_close: float
    base_volume: int
    last_close: float


def _to_iso(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


class MultiAccountTickerLoop:
    """
    Supervises the option streaming flow across every configured Kite account.
    """

    def __init__(self, orchestrator: SessionOrchestrator | None = None) -> None:
        self._orchestrator = orchestrator
        self._running = False
        self._stop_event: asyncio.Event = asyncio.Event()
        self._underlying_task: asyncio.Task | None = None
        self._account_tasks: Dict[str, asyncio.Task] = {}
        self._assignments: Dict[str, List[Instrument]] = {}
        self._last_tick_at: Dict[str, float] = {}
        self._started_at: float | None = None
        self._registry_refresh_task: asyncio.Task | None = None
        self._reconcile_lock = asyncio.Lock()
        try:
            self._market_tz = ZoneInfo(settings.market_timezone)
        except Exception:
            logger.warning("Invalid timezone %s; falling back to UTC", settings.market_timezone)
            self._market_tz = timezone.utc
        self._mock_option_state: Dict[int, MockOptionState] = {}
        self._mock_underlying_state: MockUnderlyingState | None = None
        self._mock_seed_lock = asyncio.Lock()
        self._historical_bootstrap_done: Dict[str, bool] = {}
        self._last_market_state: Optional[bool] = None

    async def start(self) -> None:
        if self._running:
            return

        if self._orchestrator is None:
            self._orchestrator = SessionOrchestrator()

        logger.debug("Starting ticker loop")
        self._stop_event = asyncio.Event()

        # Step 1: Refresh instrument registry before anything else
        try:
            kite = self._orchestrator.get_default_session()
            result = await self.refresh_instruments(force=True, kite_session=kite)

            logger.info("Instrument registry forced refresh at startup: %s", result)
        except Exception as exc:
            logger.exception("Startup instrument refresh failed")

        # Step 2: Initialize subscription store and load plan
        await subscription_store.initialise()
        plan_items = await self._load_subscription_plan()
        if not plan_items:
            self._assignments = {}
            self._running = False
            self._started_at = None
            logger.info("No active subscriptions; ticker loop idle.")
            return

        # Step 3: Validate available accounts
        available_accounts = await self._available_accounts()
        if not available_accounts:
            raise RuntimeError("No Kite accounts authenticated successfully; unable to start streaming.")

        # Step 4: Build assignments
        assignments = await self._build_assignments(plan_items, available_accounts)
        if not assignments:
            self._assignments = {}
            self._running = False
            self._started_at = None
            logger.warning("Active subscriptions present but no assignments could be made.")
            return

        # Step 5: Launch streaming tasks
        self._assignments = assignments
        self._running = True
        self._started_at = time.time()
        self._underlying_task = asyncio.create_task(self._stream_underlying())
        self._historical_bootstrap_done = {}

        for account_id, acc_instruments in assignments.items():
            task = asyncio.create_task(self._stream_account(account_id, acc_instruments))
            logger.debug("Streaming task created for %s instruments=%d", account_id, len(acc_instruments))
            self._account_tasks[account_id] = task

        # Step 6: Start periodic registry refresh
        self._start_periodic_registry_refresh()

        logger.info(
            "Ticker loop live | accounts=%s",
            ", ".join(f"{account}:{len(items)} instruments" for account, items in assignments.items()),
        )
    
    async def stop(self) -> None:
        if not self._running:
            return
        self._stop_event.set()
        await asyncio.gather(*self._account_tasks.values(), return_exceptions=True)
        if self._underlying_task:
            await self._underlying_task
        if self._registry_refresh_task:
            self._registry_refresh_task.cancel()
            try:
                await self._registry_refresh_task
            except asyncio.CancelledError:  # pragma: no cover - cooperative cancel
                pass
            self._registry_refresh_task = None
        self._account_tasks.clear()
        self._underlying_task = None
        self._running = False
        self._assignments = {}
        self._last_tick_at = {}
        self._started_at = None
        self._historical_bootstrap_done = {}
        self._reset_mock_state()
        logger.info("Ticker loop stopped")

    async def reload_subscriptions(self) -> None:
        async with self._reconcile_lock:
            if self._running:
                await self.stop()
            await self.start()

    async def fetch_history(
        self,
        instrument_token: int,
        from_ts: int,
        to_ts: int,
        interval: str,
        account_id: Optional[str] = None,
        continuous: bool = False,
        oi: bool = False,
    ) -> List[Dict[str, Any]]:
        from .kite_failover import borrow_with_failover

        orchestrator = self._orchestrator or SessionOrchestrator()
        if self._orchestrator is None:
            self._orchestrator = orchestrator

        # Use failover mechanism to automatically try next account on API limits
        async with borrow_with_failover(
            orchestrator,
            operation=f"history_fetch[{instrument_token}]",
            preferred_account=account_id
        ) as client:
            return await client.fetch_historical(
                instrument_token=instrument_token,
                from_ts=from_ts,
                to_ts=to_ts,
                interval=interval,
                continuous=continuous,
                oi=oi,
            )

    async def refresh_instruments(self, force: bool = False, kite_session: KiteClient | None = None) -> Dict[str, Any]:
        await instrument_registry.initialise()

        if not force and not instrument_registry.is_stale():
            await instrument_registry.ensure_cache_loaded()
            return {
                "refreshed": False,
                "reason": "Instrument registry already fresh for current trading day.",
                "last_refreshed_at": _to_iso(instrument_registry.last_refresh_at()),
            }

        # Use injected session if provided
        if kite_session:
            logger.debug("Using injected Kite session for instrument refresh")
            await instrument_registry.refresh_with_client(kite_session)
            return {
                "refreshed": True,
                "last_refreshed_at": _to_iso(instrument_registry.last_refresh_at()),
                "account_used": "injected",
            }

        # Otherwise use orchestrator's default session
        orchestrator = self._orchestrator or SessionOrchestrator()
        if self._orchestrator is None:
            self._orchestrator = orchestrator

        primary_account = orchestrator.primary_account_id()
        if not primary_account:
            raise RuntimeError("No Kite accounts available for instrument refresh.")

        async with orchestrator.borrow(primary_account) as client:
            await instrument_registry.refresh_with_client(client)

        return {
            "refreshed": True,
            "last_refreshed_at": _to_iso(instrument_registry.last_refresh_at()),
            "account_used": primary_account,
        }
    def _start_periodic_registry_refresh(self) -> None:
        if self._registry_refresh_task and not self._registry_refresh_task.done():
            return
        interval = max(300, settings.instrument_refresh_check_seconds)
        self._registry_refresh_task = asyncio.create_task(self._registry_refresh_loop(interval))

    def _now_market(self) -> datetime:
        return datetime.now(self._market_tz)

    def _is_market_hours(self) -> bool:
        now = self._now_market()
        start = datetime.combine(now.date(), settings.market_open_time, tzinfo=self._market_tz)
        end = datetime.combine(now.date(), settings.market_close_time, tzinfo=self._market_tz)
        if end <= start:
            end += timedelta(days=1)
        active = start <= now <= end
        if active != self._last_market_state:
            logger.info("Market hours %s", "active" if active else "inactive")
            self._last_market_state = active
        return active

    def _reset_mock_state(self) -> None:
        self._mock_option_state.clear()
        self._mock_underlying_state = None

    async def _ensure_mock_underlying_seed(self, client: KiteClient) -> None:
        if self._mock_underlying_state is not None:
            return
        try:
            quote = await client.get_quote([settings.nifty_quote_symbol])
        except Exception as exc:
            logger.error("Failed to seed mock underlying quote: %s", exc)
            return

        payload = quote.get(settings.nifty_quote_symbol)
        if not payload:
            logger.warning("Mock underlying seed missing quote for %s", settings.nifty_quote_symbol)
            return

        ohlc = payload.get("ohlc") or {}
        last_price = float(payload.get("last_price") or ohlc.get("close") or 0.0)
        if not last_price:
            logger.warning("Mock underlying seed missing price data for %s", settings.nifty_quote_symbol)
            return

        base_open = float(ohlc.get("open") or last_price)
        base_high = float(ohlc.get("high") or last_price)
        base_low = float(ohlc.get("low") or last_price)
        base_close = float(ohlc.get("close") or last_price)
        volume = int(payload.get("volume") or 0)
        if not volume:
            volume = 1000

        self._mock_underlying_state = MockUnderlyingState(
            symbol=settings.fo_underlying or settings.nifty_symbol or "NIFTY",
            base_open=base_open,
            base_high=base_high,
            base_low=base_low,
            base_close=base_close,
            base_volume=volume,
            last_close=base_close,
        )
        logger.info("Seeded mock underlying state | symbol=%s close=%.2f volume=%d",
                    self._mock_underlying_state.symbol,
                    self._mock_underlying_state.last_close,
                    self._mock_underlying_state.base_volume)

    def _generate_mock_underlying_bar(self) -> Dict[str, Any]:
        state = self._mock_underlying_state
        if state is None:
            return {}

        variance = settings.mock_price_variation_bps / 10_000.0
        drift = random.uniform(-variance, variance)
        new_close = max(0.01, state.last_close * (1 + drift))
        open_price = state.last_close

        high = max(open_price, new_close, state.base_high, new_close * (1 + variance))
        low = min(open_price, new_close, state.base_low, new_close * (1 - variance))

        volume_variance = max(int(state.base_volume * settings.mock_volume_variation), 50)
        volume = max(0, state.base_volume + random.randint(-volume_variance, volume_variance))

        state.last_close = new_close
        state.base_close = (state.base_close * 0.9) + (new_close * 0.1)
        state.base_volume = max(100, int((state.base_volume * 0.8) + (volume * 0.2)))

        return {
            "symbol": state.symbol,
            "open": round(open_price, 2),
            "high": round(high, 2),
            "low": round(low, 2),
            "close": round(new_close, 2),
            "volume": volume,
            "ts": int(time.time()),
            "is_mock": True,
        }

    async def _ensure_mock_option_seed(self, client: KiteClient, instruments: Iterable[Instrument]) -> None:
        missing = [inst for inst in instruments if inst.instrument_token not in self._mock_option_state]
        if not missing:
            return

        now = int(time.time())
        from_ts = now - settings.mock_history_minutes * 60
        async with self._mock_seed_lock:
            for instrument in missing:
                if instrument.instrument_token in self._mock_option_state:
                    continue
                state = await self._seed_option_state(client, instrument, from_ts, now)
                if state:
                    self._mock_option_state[instrument.instrument_token] = state

    async def _seed_option_state(
        self,
        client: KiteClient,
        instrument: Instrument,
        from_ts: int,
        to_ts: int,
    ) -> Optional[MockOptionState]:
        try:
            candles = await client.fetch_historical(
                instrument_token=instrument.instrument_token,
                from_ts=from_ts,
                to_ts=to_ts,
                interval="minute",
                oi=True,
            )
        except Exception as exc:
            logger.debug("Historical seed fetch failed for %s (%s): %s", instrument.tradingsymbol, instrument.instrument_token, exc)
            candles = []

        last_price = 0.0
        volume = 0
        oi = 0
        if candles:
            last = candles[-1]
            last_price = float(last.get("close") or 0.0)
            volume = int(last.get("volume") or 0)
            oi = int(last.get("oi") or 0)

        tradingsymbol = instrument.tradingsymbol or instrument.symbol
        if last_price <= 0 and tradingsymbol:
            candidates = [tradingsymbol]
            if ":" not in tradingsymbol:
                candidates.append(f"NFO:{tradingsymbol}")
            for candidate in candidates:
                try:
                    last_price = await client.get_last_price(candidate)
                    if last_price:
                        break
                except Exception:
                    continue

        if last_price <= 0:
            logger.warning(
                "Unable to seed mock state for token={} ({}): no price data",
                instrument.instrument_token,
                tradingsymbol or "unknown",
            )
            return None

        return MockOptionState(
            instrument=instrument,
            base_price=last_price,
            last_price=last_price,
            base_volume=volume or 1,
            base_oi=oi,
            iv=0.0,
            delta=0.0,
            gamma=0.0,
            theta=0.0,
            vega=0.0,
        )

    def _generate_mock_option_snapshot(self, instrument: Instrument) -> Optional[OptionSnapshot]:
        state = self._mock_option_state.get(instrument.instrument_token)
        if not state:
            return None

        variance = settings.mock_price_variation_bps / 10_000.0
        price_drift = random.uniform(-variance, variance)
        new_price = max(0.05, state.last_price * (1 + price_drift))
        state.last_price = new_price
        state.base_price = (state.base_price * 0.85) + (new_price * 0.15)

        volume = self._jitter_int(state.base_volume, settings.mock_volume_variation, minimum=0)
        oi = self._jitter_int(state.base_oi, settings.mock_volume_variation, minimum=0)
        state.base_volume = max(1, int((state.base_volume * 0.7) + (volume * 0.3)))
        state.base_oi = max(0, int((state.base_oi * 0.7) + (oi * 0.3)))

        return OptionSnapshot(
            instrument=instrument,
            last_price=round(new_price, 2),
            volume=volume,
            oi=oi,
            iv=state.iv,
            delta=state.delta,
            gamma=state.gamma,
            theta=state.theta,
            vega=state.vega,
            timestamp=int(time.time()),
            is_mock=True,
        )

    @staticmethod
    def _jitter_int(base: int, proportion: float, minimum: int = 0) -> int:
        base = max(base, minimum)
        jitter = max(int(base * proportion), 5 if base == 0 else 1)
        low = base - jitter
        high = base + jitter
        return max(minimum, random.randint(low, high))

    async def _registry_refresh_loop(self, interval: int) -> None:
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=interval)
                continue
            except asyncio.TimeoutError:
                pass
            try:
                result = await self.refresh_instruments(force=False)
                if result.get("refreshed"):
                    logger.info(
                        "Instrument registry refreshed in background via %s",
                        result.get("account_used"),
                    )
            except Exception as exc:  # pragma: no cover - network dependent
                logger.exception("Instrument registry background refresh failed: %s", exc)
                await asyncio.sleep(60)

    async def _load_subscription_plan(self) -> List[SubscriptionPlanItem]:
        await instrument_registry.initialise()

        active_records = await subscription_store.list_active()
        if not active_records:
            return []

        plan: List[SubscriptionPlanItem] = []
        stale: List[int] = []

        for record in active_records:
            metadata = await instrument_registry.fetch_metadata(record.instrument_token)
            if not metadata or not metadata.is_active:
                stale.append(record.instrument_token)
                continue
            plan.append(
                SubscriptionPlanItem(
                    record=record,
                    instrument=metadata.to_instrument(),
                )
            )

        for token in stale:
            try:
                await subscription_store.deactivate(token)
                logger.info("Deactivated subscription %s – instrument missing or inactive.", token)
            except Exception as exc:
                logger.exception("Failed to deactivate stale subscription %s: %s", token, exc)

        return plan

    async def _available_accounts(self) -> List[str]:
        orchestrator = self._orchestrator or SessionOrchestrator()
        if self._orchestrator is None:
            self._orchestrator = orchestrator

        available: List[str] = []
        unavailable: List[str] = []

        for account_id in orchestrator.list_accounts():
            try:
                async with orchestrator.borrow(account_id) as client:
                    await client.ensure_session()
            except Exception as exc:
                unavailable.append(account_id)
                logger.error("Account %s unavailable during subscription load: %s", account_id, exc)
            else:
                available.append(account_id)

        if unavailable:
            logger.warning("Accounts skipped due to authentication failure: %s", ", ".join(unavailable))
        return available

    async def _build_assignments(
        self, plan_items: List[SubscriptionPlanItem], accounts: List[str]
    ) -> Dict[str, List[Instrument]]:
        if not accounts:
            return {}

        assignments: Dict[str, List[Instrument]] = {account_id: [] for account_id in accounts}
        rr_index = 0
        account_count = len(accounts)

        for item in plan_items:
            target_account = item.record.account_id if item.record.account_id in assignments else None
            if target_account is None:
                target_account = accounts[rr_index % account_count]
                rr_index += 1

            assignments[target_account].append(item.instrument)
            try:
                await subscription_store.update_account(item.record.instrument_token, target_account)
            except Exception as exc:
                logger.exception(
                    "Failed to persist account assignment for token %s -> %s: %s",
                    item.record.instrument_token,
                    target_account,
                    exc,
                )

        return {account: instruments for account, instruments in assignments.items() if instruments}

    async def _stream_underlying(self) -> None:
        try:
            last_mode = None
            while not self._stop_event.is_set():
                is_market_hours = self._is_market_hours()
                if is_market_hours:
                    current_mode = "LIVE"
                elif self._settings.enable_mock_data:
                    current_mode = "MOCK"
                else:
                    current_mode = "DISABLED"

                # Log mode transitions
                if current_mode != last_mode:
                    logger.info("Underlying stream switching to %s mode", current_mode)
                    last_mode = current_mode

                if is_market_hours:
                    await self._emit_live_underlying()
                elif self._settings.enable_mock_data:
                    await self._emit_mock_underlying()
                else:
                    # Mock data disabled, just wait
                    pass

                try:
                    await asyncio.wait_for(self._stop_event.wait(), settings.stream_interval_seconds)
                except asyncio.TimeoutError:
                    continue
        except asyncio.CancelledError:
            pass

    async def _emit_live_underlying(self) -> None:
        ts = int(time.time())
        try:
            async with self._orchestrator.borrow() as client:
                quote = await client.get_quote([settings.nifty_quote_symbol])
        except Exception as exc:
            logger.error("Failed to fetch live underlying quote: %s", exc)
            return

        nifty = quote.get(settings.nifty_quote_symbol)
        if not nifty:
            logger.warning("Underlying quote missing for %s", settings.nifty_quote_symbol)
            return

        ohlc = nifty.get("ohlc") or {}
        payload = {
            "symbol": settings.fo_underlying or settings.nifty_symbol or "NIFTY",
            "open": ohlc.get("open", nifty.get("last_price")),
            "high": ohlc.get("high", nifty.get("last_price")),
            "low": ohlc.get("low", nifty.get("last_price")),
            "close": nifty.get("last_price"),
            "volume": nifty.get("volume", 0),
            "ts": ts,
        }
        await publish_underlying_bar(payload)

    async def _emit_mock_underlying(self) -> None:
        if self._mock_underlying_state is None:
            try:
                async with self._orchestrator.borrow() as client:
                    await self._ensure_mock_underlying_seed(client)
            except Exception as exc:
                logger.error("Failed to seed mock underlying: %s", exc)
                return

        bar = self._generate_mock_underlying_bar()
        if not bar:
            logger.debug("Mock underlying bar skipped; state not ready")
            return
        await publish_underlying_bar(bar)
    async def _stream_account(self, account_id: str, instruments: List[Instrument]) -> None:
        tokens = [instrument.instrument_token for instrument in instruments]
        token_map = {instrument.instrument_token: instrument for instrument in instruments}

        async with self._orchestrator.borrow(account_id) as client:
            await client.ensure_session()
            while not self._stop_event.is_set():
                is_market_hours = self._is_market_hours()
                if is_market_hours:
                    logger.debug("Account %s switching to LIVE stream mode", account_id)
                    await self._run_live_stream(client, account_id, instruments, tokens, token_map)
                    logger.debug("Account %s exited LIVE stream mode", account_id)
                elif self._settings.enable_mock_data:
                    logger.debug("Account %s switching to MOCK stream mode", account_id)
                    await self._run_mock_stream(client, account_id, instruments)
                    logger.debug("Account %s exited MOCK stream mode", account_id)
                else:
                    logger.debug("Account %s: Mock data disabled, waiting for market hours", account_id)
                    await asyncio.sleep(30)  # Wait 30 seconds before checking again

                # Small delay to prevent tight loop during mode transitions
                await asyncio.sleep(0.5)

    async def _run_live_stream(
        self,
        client: KiteClient,
        account_id: str,
        instruments: List[Instrument],
        tokens: List[int],
        token_map: Dict[int, Instrument],
    ) -> None:
        if not tokens:
            await asyncio.sleep(settings.stream_interval_seconds)
            return

        # Reset mock state when entering live mode
        self._reset_mock_state()
        logger.info("Account %s: Starting LIVE data stream (market hours active)", account_id)

        async def on_ticks(_account: str, ticks: List[Dict[str, Any]]) -> None:
            # Only process ticks if still in market hours
            if not self._is_market_hours():
                logger.debug("Ignoring ticks - market hours ended")
                return
            logger.debug("Received %d ticks from %s", len(ticks), _account)
            await self._handle_ticks(account_id, token_map, ticks)

        async def on_error(_account: str, exc: Exception) -> None:
            logger.error("Ticker error [%s]: %s", _account, exc)

        await client.subscribe_tokens(tokens, on_ticks=on_ticks, on_error=on_error)
        if not self._historical_bootstrap_done.get(account_id):
            await self._emit_historical_bootstrap(client, instruments)
            self._historical_bootstrap_done[account_id] = True

        try:
            while self._is_market_hours() and not self._stop_event.is_set():
                await asyncio.sleep(min(settings.stream_interval_seconds, 1.0))
        finally:
            logger.info("Account %s: Stopping LIVE data stream (market hours ended)", account_id)
            try:
                await client.unsubscribe_tokens(tokens)
            except Exception as exc:
                logger.exception("Unsubscribe failed for account %s: %s", account_id, exc)
            try:
                await client.stop_stream()
            except Exception as exc:
                logger.exception("Stop stream failed for account %s: %s", account_id, exc)

            # Ensure a clean transition - wait for any pending callbacks to complete
            await asyncio.sleep(0.5)

    async def _run_mock_stream(
        self,
        client: KiteClient,
        account_id: str,
        instruments: List[Instrument],
    ) -> None:
        if not instruments:
            await asyncio.sleep(settings.stream_interval_seconds)
            return

        logger.info("Account %s: Starting MOCK data stream (outside market hours)", account_id)
        await self._ensure_mock_option_seed(client, instruments)

        try:
            while not self._is_market_hours() and not self._stop_event.is_set():
                await self._ensure_mock_option_seed(client, instruments)
                emitted = 0
                for instrument in instruments:
                    # Double-check market hours before each emission
                    if self._is_market_hours():
                        logger.debug("Market hours started during mock emission - stopping")
                        break
                    snapshot = self._generate_mock_option_snapshot(instrument)
                    if snapshot:
                        await publish_option_snapshot(snapshot)
                        emitted += 1
                if emitted:
                    logger.debug("Published %d mock option snapshots for account %s", emitted, account_id)
                try:
                    await asyncio.wait_for(self._stop_event.wait(), settings.stream_interval_seconds)
                except asyncio.TimeoutError:
                    continue
        finally:
            logger.info("Account %s: Stopping MOCK data stream (market hours started)", account_id)

    async def _handle_ticks(self, account_id: str, lookup: Dict[int, Instrument], ticks: List[Dict[str, Any]]) -> None:
        if ticks:
            self._last_tick_at[account_id] = time.time()
        for tick in ticks:
            instrument = lookup.get(tick.get("instrument_token"))
            if not instrument:
                continue
            snapshot = OptionSnapshot(
                instrument=instrument,
                last_price=float(tick.get("last_price") or 0.0),
                volume=int(tick.get("volume_traded_today") or tick.get("volume") or 0),
                oi=int(tick.get("oi") or tick.get("open_interest") or 0),
                iv=float(tick.get("implied_volatility") or 0.0),
                delta=float(tick.get("delta") or 0.0),
                gamma=float(tick.get("gamma") or 0.0),
                theta=float(tick.get("theta") or 0.0),
                vega=float(tick.get("vega") or 0.0),
                timestamp=int(tick.get("timestamp", int(time.time()))),
            )
            await publish_option_snapshot(snapshot)

    def runtime_state(self) -> Dict[str, Any]:
        orchestrator_stats = self._orchestrator.stats() if self._orchestrator else []
        accounts_state = []
        for account_id, instruments in self._assignments.items():
            accounts_state.append(
                {
                    "account_id": account_id,
                    "instrument_count": len(instruments),
                    "last_tick_at": self._last_tick_at.get(account_id),
                }
            )
        return {
            "running": self._running,
            "started_at": self._started_at,
            "active_subscriptions": sum(len(v) for v in self._assignments.values()),
            "accounts": accounts_state,
            "orchestrator": orchestrator_stats,
        }

    def list_accounts(self) -> List[str]:
        orchestrator = self._orchestrator or SessionOrchestrator()
        if self._orchestrator is None:
            self._orchestrator = orchestrator
        return orchestrator.list_accounts()

    def borrow_client(self, account_id: Optional[str] = None):
        """
        Borrow a Kite client for the specified account.
        Returns an async context manager (AccountLease).
        """
        orchestrator = self._orchestrator or SessionOrchestrator()
        if self._orchestrator is None:
            self._orchestrator = orchestrator
        return orchestrator.borrow(account_id)

    async def _emit_historical_bootstrap(self, client: KiteClient, instruments: List[Instrument]) -> None:
        if settings.historical_days <= 0:
            return
        now = int(time.time())
        from_ts = now - settings.historical_days * 86400
        sample = instruments[: settings.historical_bootstrap_batch]
        for instrument in sample:
            try:
                await client.fetch_historical(
                    instrument_token=instrument.instrument_token,
                    from_ts=from_ts,
                    to_ts=now,
                    interval="minute",
                )
            except Exception as exc:
                logger.error("Historical fetch failed [%s token=%s]: %s", client.account_id, instrument.instrument_token, exc)
        logger.info(
            "Historical bootstrap complete | account=%s instruments=%d days=%d",
            client.account_id,
            len(sample),
            settings.historical_days,
        )
        if not sample:
            logger.debug("Historical bootstrap skipped (no instruments sampled)")


ticker_loop = MultiAccountTickerLoop()
