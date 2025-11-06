"""
Auto-rebalancing service for option strike subscriptions.

Monitors underlying price and dynamically adjusts option strike subscriptions
to maintain ATM ± configured moneyness levels.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Set

from loguru import logger

from .config import get_settings
from .instrument_registry import instrument_registry
from .subscription_store import subscription_store


class StrikeRebalancer:
    """
    Automatically rebalances option strike subscriptions based on underlying price movements.

    Maintains a subscription range of ATM ± (otm_levels * strike_step) for configured expiries.
    """

    def __init__(self):
        self._settings = get_settings()
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._last_rebalance: Dict[str, datetime] = {}
        self._last_atm: Dict[str, float] = {}

        # Rebalancing configuration
        self._check_interval = 60  # Check every 60 seconds
        self._atm_movement_threshold = 100  # Rebalance if ATM moved by 100 points (2 strikes)
        self._min_rebalance_interval = 300  # Min 5 minutes between rebalances for same underlying

    async def start(self):
        """Start the rebalancing task."""
        if self._running:
            logger.warning("StrikeRebalancer already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._run())
        logger.info(
            "StrikeRebalancer started | interval=%ds threshold=%d",
            self._check_interval,
            self._atm_movement_threshold,
        )

    async def stop(self):
        """Stop the rebalancing task."""
        if not self._running:
            return

        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("StrikeRebalancer stopped")

    async def _run(self):
        """Main rebalancing loop."""
        # Wait for services to initialize
        await asyncio.sleep(10)

        while self._running:
            try:
                await self._rebalance_all()
            except Exception as exc:
                logger.error(f"Rebalancing error: {exc}", exc_info=True)

            await asyncio.sleep(self._check_interval)

    async def _rebalance_all(self):
        """Check and rebalance all configured underlyings."""
        # Get configured underlyings from settings (currently hardcoded to NIFTY/NIFTY50)
        underlyings = ["NIFTY50", "NIFTY"]

        for underlying in underlyings:
            try:
                await self._rebalance_underlying(underlying)
            except Exception as exc:
                logger.error(f"Failed to rebalance {underlying}: {exc}")

    async def _rebalance_underlying(self, underlying: str):
        """Rebalance option strikes for a single underlying."""
        # Check if enough time has passed since last rebalance
        last_time = self._last_rebalance.get(underlying)
        if last_time:
            elapsed = (datetime.now() - last_time).total_seconds()
            if elapsed < self._min_rebalance_interval:
                return

        # Get current LTP for underlying
        ltp = await self._get_underlying_ltp(underlying)
        if not ltp:
            logger.debug(f"No LTP available for {underlying}, skipping rebalance")
            return

        # Calculate ATM strike
        strike_step = self._settings.option_strike_step
        atm = round(ltp / strike_step) * strike_step

        # Check if ATM has moved enough to warrant rebalancing
        last_atm = self._last_atm.get(underlying)
        if last_atm:
            movement = abs(atm - last_atm)
            if movement < self._atm_movement_threshold:
                return

        logger.info(
            f"Rebalancing {underlying} | ltp={ltp:.2f} atm={atm:.0f} last_atm={last_atm or 'N/A'}"
        )

        # Get upcoming expiries
        expiries = await self._get_upcoming_expiries(underlying)
        if not expiries:
            logger.warning(f"No expiries found for {underlying}")
            return

        # Calculate required strike range
        otm_levels = self._settings.otm_levels
        strike_range = otm_levels * strike_step
        min_strike = atm - strike_range
        max_strike = atm + strike_range

        logger.info(
            f"Target strike range for {underlying}: {min_strike:.0f} to {max_strike:.0f}"
        )

        # Get currently subscribed strikes
        current_subscriptions = await self._get_current_subscriptions(underlying, expiries)

        # Find missing strikes
        missing_instruments = await self._find_missing_strikes(
            underlying, expiries, min_strike, max_strike, current_subscriptions
        )

        if missing_instruments:
            logger.info(f"Found {len(missing_instruments)} missing strikes for {underlying}")
            await self._subscribe_instruments(missing_instruments)
        else:
            logger.debug(f"No missing strikes for {underlying}")

        # Update tracking
        self._last_rebalance[underlying] = datetime.now()
        self._last_atm[underlying] = atm

    async def _get_underlying_ltp(self, symbol: str) -> Optional[float]:
        """Get current LTP for underlying from instrument registry cache or tick data."""
        # Try to get from instrument registry first
        await instrument_registry.initialise()

        # Look for the underlying instrument
        for instrument in instrument_registry._cache.values():
            if (
                instrument.tradingsymbol in [symbol, f"NSE:{symbol}"]
                or instrument.name == symbol
            ):
                # Check if we have recent tick data (this would need to be stored somewhere)
                # For now, return None to trigger subscription based on database query
                pass

        # Fallback: query database for recent price
        try:
            from psycopg_pool import AsyncConnectionPool

            conninfo = self._build_db_conninfo()
            async with AsyncConnectionPool(conninfo, min_size=1, max_size=2, timeout=5) as pool:
                async with pool.connection() as conn:
                    async with conn.cursor() as cur:
                        await cur.execute(
                            """
                            SELECT close
                            FROM minute_bars
                            WHERE symbol = ANY(%s)
                              AND resolution = 1
                            ORDER BY time DESC
                            LIMIT 1
                            """,
                            ([symbol.lower(), symbol.upper(), "nifty50", "nifty"],),
                        )
                        row = await cur.fetchone()
                        if row and row[0]:
                            return float(row[0])
        except Exception as exc:
            logger.error(f"Failed to get LTP for {symbol}: {exc}")

        return None

    async def _get_upcoming_expiries(self, underlying: str) -> List[date]:
        """Get upcoming N expiries for underlying."""
        await instrument_registry.initialise()

        expiry_window = self._settings.option_expiry_window
        expiries: Set[date] = set()

        # Normalize underlying name variations (NIFTY50 -> NIFTY, NIFTY -> NIFTY)
        underlying_variants = {
            underlying.upper(),
            underlying.replace("50", "").upper(),
            underlying.replace("NIFTY50", "NIFTY").upper(),
        }

        today = date.today()
        for instrument in instrument_registry._cache.values():
            if (
                instrument.segment == "NFO-OPT"
                and instrument.name
                and instrument.name.upper() in underlying_variants
                and instrument.expiry
            ):
                # Handle both date objects and strings
                expiry_date = instrument.expiry
                if isinstance(expiry_date, str):
                    try:
                        from datetime import datetime
                        expiry_date = datetime.strptime(expiry_date, "%Y-%m-%d").date()
                    except:
                        continue

                if expiry_date >= today:
                    expiries.add(expiry_date)

        logger.debug(
            f"Found {len(expiries)} expiries for {underlying}: {sorted(list(expiries))[:expiry_window]}"
        )

        return sorted(list(expiries))[:expiry_window]

    async def _get_current_subscriptions(
        self, underlying: str, expiries: List[date]
    ) -> Set[str]:
        """Get currently subscribed instrument tokens for underlying and expiries."""
        subscriptions = await subscription_store.list_active()

        # Build set of subscribed tradingsymbols
        subscribed: Set[str] = set()
        for sub in subscriptions:
            # Match NIFTY options for given expiries
            if underlying.upper() in sub.tradingsymbol and sub.segment == "NFO-OPT":
                subscribed.add(sub.tradingsymbol)

        return subscribed

    async def _find_missing_strikes(
        self,
        underlying: str,
        expiries: List[date],
        min_strike: float,
        max_strike: float,
        current_subscriptions: Set[str],
    ) -> List[Dict]:
        """Find instruments that should be subscribed but aren't."""
        await instrument_registry.initialise()

        strike_step = self._settings.option_strike_step
        missing: List[Dict] = []

        for expiry in expiries:
            # Generate expected strikes
            strike = min_strike
            while strike <= max_strike:
                # Find CE and PE instruments for this strike and expiry
                for option_type in ["CE", "PE"]:
                    instrument = await self._find_instrument(
                        underlying, expiry, strike, option_type
                    )

                    if instrument and instrument.tradingsymbol not in current_subscriptions:
                        missing.append({
                            "instrument_token": instrument.instrument_token,
                            "tradingsymbol": instrument.tradingsymbol,
                            "segment": instrument.segment,
                            "expiry": str(expiry),
                            "strike": strike,
                            "option_type": option_type,
                        })

                strike += strike_step

        return missing

    async def _find_instrument(
        self, underlying: str, expiry: date, strike: float, option_type: str
    ):
        """Find a specific option instrument."""
        await instrument_registry.initialise()

        # Normalize underlying name variations
        underlying_variants = {
            underlying.upper(),
            underlying.replace("50", "").upper(),
            underlying.replace("NIFTY50", "NIFTY").upper(),
        }

        for instrument in instrument_registry._cache.values():
            if (
                instrument.segment == "NFO-OPT"
                and instrument.name
                and instrument.name.upper() in underlying_variants
                and instrument.expiry == expiry
                and instrument.strike == strike
                and instrument.instrument_type == option_type
            ):
                return instrument

        return None

    async def _subscribe_instruments(self, instruments: List[Dict]):
        """Subscribe to a list of instruments."""
        if not instruments:
            return

        # Add all instruments to subscription store in batch
        for inst in instruments:
            try:
                await subscription_store.upsert(
                    instrument_token=inst["instrument_token"],
                    tradingsymbol=inst["tradingsymbol"],
                    segment=inst["segment"],
                    requested_mode="FULL",
                    account_id="primary",
                    status="active",
                )
                logger.info(
                    f"Queued subscription: {inst['tradingsymbol']} (strike={inst['strike']} expiry={inst['expiry']})"
                )
            except Exception as exc:
                logger.error(
                    f"Failed to queue subscription for {inst['tradingsymbol']}: {exc}"
                )

        # Reload all subscriptions once to activate the new ones
        try:
            from .ticker_loop import ticker_loop
            await ticker_loop.reload_subscriptions()
            logger.info(f"Successfully activated {len(instruments)} new option subscriptions")
        except Exception as exc:
            logger.error(f"Failed to reload subscriptions: {exc}")

    def _build_db_conninfo(self) -> str:
        """Build database connection string for querying underlying prices."""
        parts = [
            f"host={self._settings.instrument_db_host}",
            f"port={self._settings.instrument_db_port}",
            f"dbname={self._settings.instrument_db_name}",
            f"user={self._settings.instrument_db_user}",
        ]
        if self._settings.instrument_db_password:
            parts.append(f"password={self._settings.instrument_db_password}")
        return " ".join(parts)


# Global instance
strike_rebalancer = StrikeRebalancer()
