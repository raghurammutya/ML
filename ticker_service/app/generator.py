from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from zoneinfo import ZoneInfo

from loguru import logger

from .accounts import SessionOrchestrator
from .config import get_settings
from .instrument_registry import instrument_registry
from .subscription_store import subscription_store
from .kite.client import KiteClient
from .publisher import publish_option_snapshot, publish_underlying_bar
from .schema import Instrument, OptionSnapshot, DepthLevel, MarketDepth
from .greeks_calculator import GreeksCalculator
from .utils.symbol_utils import normalize_symbol
from .services.mock_generator import MockDataGenerator
from .services.subscription_reconciler import SubscriptionReconciler
from .services.historical_bootstrapper import HistoricalBootstrapper
from .services.tick_processor import TickProcessor
from .services.tick_batcher import TickBatcher  # NEW: Phase 4 batching
from .services.tick_validator import TickValidator  # NEW: Phase 4 validation

settings = get_settings()


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

    def __init__(
        self,
        orchestrator: SessionOrchestrator | None = None,
        task_monitor: Optional[Any] = None,  # TaskMonitor for exception handling
        mock_generator: Optional[MockDataGenerator] = None,  # NEW: Injected mock data generator
        tick_processor: Optional[TickProcessor] = None,  # NEW: Injected tick processor
    ) -> None:
        self._orchestrator = orchestrator
        self._task_monitor = task_monitor
        self._settings = get_settings()
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

        self._cleanup_task: asyncio.Task | None = None
        self._last_market_state: Optional[bool] = None
        self._last_underlying_price: float | None = None

        # Initialize Greeks calculator
        self._greeks_calculator = GreeksCalculator(
            interest_rate=self._settings.option_greeks_interest_rate,
            dividend_yield=self._settings.option_greeks_dividend_yield,
            expiry_time_hour=self._settings.option_expiry_time_hour,
            expiry_time_minute=self._settings.option_expiry_time_minute,
            market_timezone=self._settings.market_timezone,
        )

        # NEW: Initialize mock data generator (injected or created)
        self._mock_generator = mock_generator or MockDataGenerator(
            greeks_calculator=self._greeks_calculator,
            market_tz=self._market_tz,
            max_size=settings.mock_state_max_size,
        )

        # NEW: Initialize subscription reconciler
        self._reconciler = SubscriptionReconciler(market_tz=self._market_tz)

        # NEW: Initialize historical bootstrapper
        self._bootstrapper = HistoricalBootstrapper()

        # NEW: Initialize tick batcher (Phase 4)
        self._tick_batcher = TickBatcher(
            window_ms=self._settings.tick_batch_window_ms,
            max_batch_size=self._settings.tick_batch_max_size,
            enabled=self._settings.tick_batch_enabled,
        )

        # NEW: Initialize tick validator (Phase 4)
        self._tick_validator = TickValidator(
            strict_mode=self._settings.tick_validation_strict,
            enabled=self._settings.tick_validation_enabled,
        )

        # NEW: Initialize tick processor (injected or created)
        self._tick_processor = tick_processor or TickProcessor(
            greeks_calculator=self._greeks_calculator,
            market_tz=self._market_tz,
            batcher=self._tick_batcher,
            validator=self._tick_validator,
        )

    async def start(self) -> None:
        if self._running:
            return

        if self._orchestrator is None:
            self._orchestrator = SessionOrchestrator()

        logger.debug("Starting ticker loop")
        self._stop_event = asyncio.Event()

        # Step 1: Refresh instrument registry before anything else (skip if no accounts in mock mode)
        try:
            kite = self._orchestrator.get_default_session()
            if kite:
                result = await self.refresh_instruments(force=True, kite_session=kite)
                logger.info("Instrument registry forced refresh at startup: %s", result)
            else:
                logger.warning("Skipping instrument refresh (no Kite accounts, running in mock mode)")
        except Exception as exc:
            logger.exception("Startup instrument refresh failed")

        # Step 2: Initialize subscription store and load plan
        await subscription_store.initialise()
        plan_items = await self._reconciler.load_subscription_plan()
        if not plan_items:
            self._assignments = {}
            self._running = False
            self._started_at = None
            logger.info("No active subscriptions; ticker loop idle.")
            return

        # Step 3: Validate available accounts
        available_accounts = await self._available_accounts()
        if not available_accounts:
            if settings.enable_mock_data:
                self._assignments = {}
                self._running = False
                self._started_at = None
                logger.warning("No Kite accounts available; ticker loop idle (mock mode enabled).")
                return
            raise RuntimeError("No Kite accounts authenticated successfully; unable to start streaming.")

        # Step 4: Build assignments
        assignments = await self._reconciler.build_assignments(plan_items, available_accounts)
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

        # ARCH-P0-003 FIX: Make TaskMonitor mandatory to prevent silent failures
        # Background tasks MUST be monitored to catch and log exceptions
        if not self._task_monitor:
            raise RuntimeError(
                "TaskMonitor is required for MultiAccountTickerLoop. "
                "Background tasks cannot run unmonitored as failures would be silent. "
                "Initialize with task_monitor=TaskMonitor() to enable exception tracking."
            )

        # Create underlying task with monitoring
        self._underlying_task = self._task_monitor.create_monitored_task(
            self._stream_underlying(),
            task_name="stream_underlying",
            on_error=self._on_underlying_stream_error,
        )

        self._historical_bootstrap_done = {}

        for account_id, acc_instruments in assignments.items():
            # ARCH-P0-003 FIX: All background tasks must be monitored (no fallback)
            task = self._task_monitor.create_monitored_task(
                self._stream_account(account_id, acc_instruments),
                task_name=f"stream_account_{account_id}",
                on_error=lambda exc, aid=account_id: self._on_account_stream_error(aid, exc),
            )
            logger.debug("Streaming task created for %s instruments=%d", account_id, len(acc_instruments))
            self._account_tasks[account_id] = task

        # Step 6: Start periodic registry refresh
        self._start_periodic_registry_refresh()

        # NEW: Initialize and start subscription reloader
        self._reconciler.initialize_reloader(self._perform_reload)
        await self._reconciler.start_reloader()

        # NEW: Start tick batcher (Phase 4)
        await self._tick_batcher.start()
        logger.info("Tick batcher started")

        # ARCH-P0-003 FIX: All background tasks must be monitored (no fallback)
        self._cleanup_task = self._task_monitor.create_monitored_task(
            self._mock_state_cleanup_loop(),
            task_name="mock_state_cleanup"
        )
        logger.info("Mock state cleanup task started with monitoring")

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

        # NEW: Stop subscription reloader
        await self._reconciler.stop_reloader()

        # NEW: Stop tick batcher (Phase 4) - flushes remaining batches
        await self._tick_batcher.stop()
        logger.info("Tick batcher stopped")

        # NEW: Stop cleanup task
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
            logger.info("Mock state cleanup task stopped")

        self._account_tasks.clear()
        self._underlying_task = None
        self._running = False
        self._assignments = {}
        self._last_tick_at = {}
        self._started_at = None
        await self._mock_generator.reset_state()  # NEW: Delegate to service
        self._bootstrapper.reset_bootstrap_state()  # NEW: Delegate to service
        logger.info("Ticker loop stopped")

    async def _on_underlying_stream_error(self, exc: Exception) -> None:
        """Callback when underlying stream task fails"""
        logger.critical(
            f"Underlying stream failed critically: {exc}",
            exc_info=True,
            extra={"component": "ticker_loop", "stream": "underlying"}
        )
        # Optional: Attempt restart
        # await asyncio.sleep(5.0)
        # await self.start()

    async def _on_account_stream_error(self, account_id: str, exc: Exception) -> None:
        """Callback when account stream task fails"""
        logger.critical(
            f"Account stream for {account_id} failed critically: {exc}",
            exc_info=True,
            extra={"component": "ticker_loop", "account_id": account_id}
        )
        # Remove failed task from tracking
        if account_id in self._account_tasks:
            del self._account_tasks[account_id]
        # Optional: Attempt to restart just this account
        # await asyncio.sleep(5.0)
        # if account_id in self._assignments:
        #     task = self._task_monitor.create_monitored_task(
        #         self._stream_account(account_id, self._assignments[account_id]),
        #         task_name=f"stream_account_{account_id}",
        #         on_error=lambda exc: self._on_account_stream_error(account_id, exc),
        #     )
        #     self._account_tasks[account_id] = task

    async def _perform_reload(self) -> None:
        """
        Internal method: Perform actual subscription reload.

        Called by SubscriptionReloader, not directly.
        This method stops and restarts the ticker loop to apply new subscriptions.
        """
        async with self._reconcile_lock:
            if self._running:
                await self.stop()
            await self.start()

    async def reload_subscriptions(self) -> None:
        """
        Public API: Reload subscriptions immediately (blocking).

        For most use cases, prefer reload_subscriptions_async() which is non-blocking.
        """
        # Directly call the implementation (bypass reloader for blocking API)
        await self._reconciler.reload_subscriptions_blocking()

    def reload_subscriptions_async(self) -> None:
        """
        Trigger subscription reload in the background without blocking (non-blocking, coalesced).

        Returns immediately while the reload happens asynchronously.
        Multiple rapid calls will be coalesced into a single reload.

        Use this for API endpoints to avoid blocking HTTP responses.
        """
        # Trigger reload via reconciler (which uses SubscriptionReloader for rate limiting)
        self._reconciler.trigger_reload()

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

        # Use lock-free client access for API calls to avoid blocking on WebSocket locks
        # Historical data fetches are thread-safe HTTP requests and don't need exclusive access
        client = orchestrator.get_client_for_api_call(preferred_account=account_id)
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

    async def _ensure_mock_underlying_seed(self, client: KiteClient) -> None:
        """Delegate to mock generator service"""
        await self._mock_generator.ensure_underlying_seeded(client)

    async def _generate_mock_underlying_bar(self) -> Dict[str, Any]:
        """Delegate to mock generator service"""
        return await self._mock_generator.generate_underlying_bar()

    async def _ensure_mock_option_seed(self, client: KiteClient, instruments: Iterable[Instrument]) -> None:
        """Delegate to mock generator service"""
        await self._mock_generator.ensure_options_seeded(client, instruments, self._last_underlying_price)

    async def _generate_mock_option_snapshot(self, instrument: Instrument) -> Optional[OptionSnapshot]:
        """Delegate to mock generator service"""
        return await self._mock_generator.generate_option_snapshot(instrument)

    async def _reset_mock_state(self) -> None:
        """Reset mock state when transitioning to live mode"""
        try:
            await self._mock_generator.cleanup_expired()
            logger.debug("Mock state reset for live mode transition")
        except Exception as exc:
            logger.warning(f"Failed to reset mock state: {exc}")

    async def _mock_state_cleanup_loop(self) -> None:
        """
        Background task: Cleanup expired mock state aggressively.

        ARCH-P0-005 FIX: Changed from 5 minutes to 1 minute intervals
        This prevents accumulation of expired options (500 KB stale data issue).
        More frequent cleanup keeps memory usage stable during extended mock mode operation.
        """
        logger.info("Mock state cleanup loop started (1-minute intervals)")

        while self._running:
            try:
                # ARCH-P0-005 FIX: Aggressive 1-minute cleanup interval (was 5 minutes)
                # This prevents stale data buildup during extended mock mode
                await asyncio.sleep(60)  # 1 minute

                if not self._running:
                    break

                # Cleanup expired options
                await self._mock_generator.cleanup_expired()

            except asyncio.CancelledError:
                logger.info("Mock state cleanup loop cancelled")
                break
            except Exception as exc:
                logger.exception(f"Mock state cleanup loop error: {exc}")
                await asyncio.sleep(60)  # Wait 1 minute on error before retrying

        logger.info("Mock state cleanup loop stopped")

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
        if self._mock_generator.get_underlying_snapshot() is None:
            try:
                async with self._orchestrator.borrow() as client:
                    await self._ensure_mock_underlying_seed(client)
            except Exception as exc:
                logger.error("Failed to seed mock underlying: %s", exc)
                return

        bar = await self._generate_mock_underlying_bar()
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
        await self._reset_mock_state()
        logger.info("Account %s: Starting LIVE data stream (market hours active)", account_id)

        async def on_ticks(_account: str, ticks: List[Dict[str, Any]]) -> None:
            logger.info(f"DEBUG GENERATOR: on_ticks callback fired! account={_account}, ticks={len(ticks)}")
            # Only process ticks if still in market hours
            if not self._is_market_hours():
                logger.warning(f"DEBUG GENERATOR: Ignoring ticks - market hours ended")
                return
            logger.info(f"DEBUG GENERATOR: Processing {len(ticks)} ticks from {_account}")
            await self._handle_ticks(account_id, token_map, ticks)
            logger.info(f"DEBUG GENERATOR: Finished handling ticks")

        async def on_error(_account: str, exc: Exception) -> None:
            logger.error("Ticker error [%s]: %s", _account, exc)

        await client.subscribe_tokens(tokens, on_ticks=on_ticks, on_error=on_error)
        if not self._bootstrapper.is_bootstrap_done(account_id):
            await self._bootstrapper.backfill_missing_history(account_id, instruments, client)

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

        # Get current date for expiry filtering
        today_market = self._now_market().date()

        # Filter out expired instruments
        active_instruments = [
            inst for inst in instruments
            if not inst.expiry or inst.expiry >= today_market
        ]

        if len(active_instruments) < len(instruments):
            logger.info(
                "Filtered out %d expired contracts from mock stream for account %s",
                len(instruments) - len(active_instruments),
                account_id
            )

        try:
            while not self._is_market_hours() and not self._stop_event.is_set():
                await self._ensure_mock_option_seed(client, active_instruments)
                emitted = 0
                for instrument in active_instruments:
                    # Double-check market hours before each emission
                    if self._is_market_hours():
                        logger.debug("Market hours started during mock emission - stopping")
                        break
                    snapshot = await self._generate_mock_option_snapshot(instrument)
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
        """
        Handle incoming tick data by delegating to TickProcessor.

        Args:
            account_id: Account ID that received these ticks
            lookup: Mapping of instrument tokens to instruments
            ticks: List of raw tick data from WebSocket
        """
        # Update last tick time
        if ticks:
            self._last_tick_at[account_id] = time.time()

        # Get current date for expiry checking
        today_market = self._now_market().date()

        # Delegate to tick processor
        await self._tick_processor.process_ticks(
            account_id=account_id,
            lookup=lookup,
            ticks=ticks,
            today_market=today_market,
        )

        # Sync underlying price from processor to generator (for backward compatibility)
        self._last_underlying_price = self._tick_processor.get_last_underlying_price()

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

ticker_loop = MultiAccountTickerLoop()
