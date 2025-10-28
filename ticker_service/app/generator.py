from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

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

    async def start(self) -> None:
        if self._running:
            return
        if self._orchestrator is None:
            self._orchestrator = SessionOrchestrator()
        logger.debug("Starting ticker loop")

        self._stop_event = asyncio.Event()
        await subscription_store.initialise()
        plan_items = await self._load_subscription_plan()
        if not plan_items:
            self._assignments = {}
            self._running = False
            self._started_at = None
            logger.info("No active subscriptions; ticker loop idle.")
            return

        available_accounts = await self._available_accounts()
        if not available_accounts:
            raise RuntimeError("No Kite accounts authenticated successfully; unable to start streaming.")

        assignments = await self._build_assignments(plan_items, available_accounts)
        if not assignments:
            self._assignments = {}
            self._running = False
            self._started_at = None
            logger.warning("Active subscriptions present but no assignments could be made.")
            return

        self._assignments = assignments
        self._running = True
        self._started_at = time.time()
        self._underlying_task = asyncio.create_task(self._stream_underlying())

        for account_id, acc_instruments in assignments.items():
            task = asyncio.create_task(self._stream_account(account_id, acc_instruments))
            logger.debug("Streaming task created for %s instruments=%d", account_id, len(acc_instruments))
            self._account_tasks[account_id] = task

        self._start_registry_refresh_task()

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
        orchestrator = self._orchestrator or SessionOrchestrator()
        if self._orchestrator is None:
            self._orchestrator = orchestrator
        lease = orchestrator.borrow(account_id) if account_id else orchestrator.borrow()
        async with lease as client:
            return await client.fetch_historical(
                instrument_token=instrument_token,
                from_ts=from_ts,
                to_ts=to_ts,
                interval=interval,
                continuous=continuous,
                oi=oi,
            )

    async def refresh_instruments(self, force: bool = False) -> Dict[str, Any]:
        await instrument_registry.initialise()
        if not force and not instrument_registry.is_stale():
            await instrument_registry.ensure_cache_loaded()
            return {
                "refreshed": False,
                "reason": "Instrument registry already fresh for current trading day.",
                "last_refreshed_at": _to_iso(instrument_registry.last_refresh_at()),
            }

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

    def _start_registry_refresh_task(self) -> None:
        if self._registry_refresh_task and not self._registry_refresh_task.done():
            return
        interval = max(300, settings.instrument_refresh_check_seconds)
        self._registry_refresh_task = asyncio.create_task(self._registry_refresh_loop(interval))

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
            while not self._stop_event.is_set():
                ts = int(time.time())
                await publish_underlying_bar(
                    {
                        "symbol": settings.fo_underlying,
                        "open": random.uniform(24000, 25000),
                        "high": random.uniform(25000, 25500),
                        "low": random.uniform(23500, 24500),
                        "close": random.uniform(24000, 25000),
                        "volume": random.randint(100_000, 300_000),
                        "ts": ts,
                    }
                )
                try:
                    await asyncio.wait_for(self._stop_event.wait(), settings.stream_interval_seconds)
                except asyncio.TimeoutError:
                    continue
        except asyncio.CancelledError:  # pragma: no cover - cooperative cancel
            pass

    async def _stream_account(self, account_id: str, instruments: List[Instrument]) -> None:
        tokens = [instrument.instrument_token for instrument in instruments]
        token_map = {instrument.instrument_token: instrument for instrument in instruments}

        async with self._orchestrator.borrow(account_id) as client:
            await client.ensure_session()
            async def on_ticks(_account: str, ticks: List[Dict[str, Any]]) -> None:
                logger.debug("Received %d ticks from %s", len(ticks), _account)
                await self._handle_ticks(account_id, token_map, ticks)

            async def on_error(_account: str, exc: Exception) -> None:
                logger.error("Ticker error [%s]: %s", _account, exc)

            await client.subscribe_tokens(tokens, on_ticks=on_ticks, on_error=on_error)
            await self._emit_historical_bootstrap(client, instruments)

            try:
                await self._stop_event.wait()
            finally:
                logger.debug("Stopping stream for account %s", account_id)
                await client.unsubscribe_tokens(tokens)
                await client.stop_stream()

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
