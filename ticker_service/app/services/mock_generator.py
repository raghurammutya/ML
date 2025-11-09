"""
Mock data generator service for ticker loop.

Extracted from generator.py to improve modularity and maintainability.
Handles all mock data generation, seeding, and cleanup operations.
"""
from __future__ import annotations

import asyncio
import random
import time
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Iterable, TYPE_CHECKING

from loguru import logger

from ..config import get_settings
from ..schema import Instrument, OptionSnapshot, DepthLevel, MarketDepth
from ..greeks_calculator import GreeksCalculator

if TYPE_CHECKING:
    from ..kite.client import KiteClient

settings = get_settings()


@dataclass(frozen=True)
class MockOptionSnapshot:
    """Thread-safe immutable snapshot of mock option state"""
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
    timestamp: float


@dataclass
class _MockOptionBuilder:
    """Internal mutable builder for mock option state (use ONLY under lock)"""
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

    def build_snapshot(self) -> MockOptionSnapshot:
        """Create immutable snapshot from current builder state"""
        return MockOptionSnapshot(
            instrument=self.instrument,
            base_price=self.base_price,
            last_price=self.last_price,
            base_volume=self.base_volume,
            base_oi=self.base_oi,
            iv=self.iv,
            delta=self.delta,
            gamma=self.gamma,
            theta=self.theta,
            vega=self.vega,
            timestamp=time.time(),
        )


@dataclass(frozen=True)
class MockUnderlyingSnapshot:
    """Thread-safe immutable snapshot of mock underlying state"""
    symbol: str
    base_open: float
    base_high: float
    base_low: float
    base_close: float
    base_volume: int
    last_close: float
    timestamp: float


@dataclass
class _MockUnderlyingBuilder:
    """Internal mutable builder for mock underlying state (use ONLY under lock)"""
    symbol: str
    base_open: float
    base_high: float
    base_low: float
    base_close: float
    base_volume: int
    last_close: float

    def build_snapshot(self) -> MockUnderlyingSnapshot:
        """Create immutable snapshot from current builder state"""
        return MockUnderlyingSnapshot(
            symbol=self.symbol,
            base_open=self.base_open,
            base_high=self.base_high,
            base_low=self.base_low,
            base_close=self.base_close,
            base_volume=self.base_volume,
            last_close=self.last_close,
            timestamp=time.time(),
        )


class MockDataGenerator:
    """
    Generates realistic mock market data for testing and development.

    Features:
    - Thread-safe Builder + Snapshot pattern
    - LRU eviction to prevent memory leaks
    - Automatic cleanup of expired options
    - Realistic price movements and Greeks calculation
    """

    def __init__(
        self,
        greeks_calculator: GreeksCalculator,
        market_tz,
        max_size: int = 5000,
    ):
        self._greeks_calculator = greeks_calculator
        self._market_tz = market_tz
        self._max_size = max_size

        # Builder + Snapshot pattern for thread-safe mock state
        # Builders are mutable, protected by lock
        self._option_builders: OrderedDict[int, _MockOptionBuilder] = OrderedDict()
        self._underlying_builder: Optional[_MockUnderlyingBuilder] = None

        # Snapshots are immutable, safe to read without lock
        self._option_snapshots: OrderedDict[int, MockOptionSnapshot] = OrderedDict()
        self._underlying_snapshot: Optional[MockUnderlyingSnapshot] = None

        # Lock for thread-safe state updates
        self._lock = asyncio.Lock()

    def _now_market(self) -> datetime:
        """Get current time in market timezone"""
        return datetime.now(self._market_tz)

    async def reset_state(self) -> None:
        """Reset all mock state with thread-safe locking"""
        async with self._lock:
            self._option_builders.clear()
            self._option_snapshots.clear()
            self._underlying_builder = None
            self._underlying_snapshot = None

    # ======================
    # UNDERLYING METHODS
    # ======================

    async def ensure_underlying_seeded(self, client: KiteClient) -> None:
        """Ensure underlying (NIFTY) state is seeded from real data"""
        # Quick check WITHOUT lock (safe - snapshot is immutable)
        if self._underlying_snapshot is not None:
            return

        async with self._lock:
            # Double-check AFTER lock
            if self._underlying_snapshot is not None:
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

            # Create builder (mutable, under lock)
            self._underlying_builder = _MockUnderlyingBuilder(
                symbol=settings.fo_underlying or settings.nifty_symbol or "NIFTY",
                base_open=base_open,
                base_high=base_high,
                base_low=base_low,
                base_close=base_close,
                base_volume=volume,
                last_close=base_close,
            )

            # Create snapshot (immutable, for consumers)
            self._underlying_snapshot = self._underlying_builder.build_snapshot()

            logger.info("Seeded mock underlying state | symbol=%s close=%.2f volume=%d",
                        self._underlying_snapshot.symbol,
                        self._underlying_snapshot.last_close,
                        self._underlying_snapshot.base_volume)

    async def generate_underlying_bar(self) -> dict:
        """Generate mock underlying bar with thread-safe state access"""
        # Read snapshot (NO LOCK - immutable!)
        snapshot = self._underlying_snapshot
        if snapshot is None:
            return {}

        # Generate new values based on snapshot
        variance = settings.mock_price_variation_bps / 10_000.0
        drift = random.uniform(-variance, variance)
        new_close = max(0.01, snapshot.last_close * (1 + drift))
        open_price = snapshot.last_close

        high = max(open_price, new_close, snapshot.base_high, new_close * (1 + variance))
        low = min(open_price, new_close, snapshot.base_low, new_close * (1 - variance))

        volume_variance = max(int(snapshot.base_volume * settings.mock_volume_variation), 50)
        volume = max(0, snapshot.base_volume + random.randint(-volume_variance, volume_variance))

        # Update builder UNDER LOCK, create new snapshot
        async with self._lock:
            if self._underlying_builder:
                self._underlying_builder.last_close = new_close
                self._underlying_builder.base_close = (self._underlying_builder.base_close * 0.9) + (new_close * 0.1)
                self._underlying_builder.base_volume = max(100, int((self._underlying_builder.base_volume * 0.8) + (volume * 0.2)))

                # Create NEW snapshot
                self._underlying_snapshot = self._underlying_builder.build_snapshot()

        return {
            "symbol": snapshot.symbol,
            "open": round(open_price, 2),
            "high": round(high, 2),
            "low": round(low, 2),
            "close": round(new_close, 2),
            "volume": volume,
            "ts": int(time.time()),
            "is_mock": False,  # TEMP: Changed from True for testing
        }

    def get_underlying_snapshot(self) -> Optional[MockUnderlyingSnapshot]:
        """Get current underlying snapshot (lock-free read)"""
        return self._underlying_snapshot

    # ======================
    # OPTION METHODS
    # ======================

    async def ensure_options_seeded(
        self,
        client: KiteClient,
        instruments: Iterable[Instrument],
        last_underlying_price: Optional[float] = None,
    ) -> None:
        """Ensure option instruments are seeded with mock state"""
        missing = [inst for inst in instruments if inst.instrument_token not in self._option_snapshots]
        if not missing:
            return

        now = int(time.time())
        from_ts = now - settings.mock_history_minutes * 60

        async with self._lock:
            # STEP 1: Cleanup expired options FIRST
            await self._cleanup_expired_internal()

            # STEP 2: Re-check what's still missing after cleanup
            still_missing = [inst for inst in missing if inst.instrument_token not in self._option_snapshots]

            for instrument in still_missing:
                if instrument.instrument_token in self._option_snapshots:
                    continue

                # STEP 3: Enforce max size (LRU eviction) BEFORE adding new
                while len(self._option_snapshots) >= self._max_size:
                    # Evict oldest (first item in OrderedDict)
                    evicted_token, _ = self._option_snapshots.popitem(last=False)
                    self._option_builders.pop(evicted_token, None)
                    logger.debug(f"Evicted LRU mock state: token={evicted_token}")

                # STEP 4: Seed new instrument
                builder = await self._seed_option_state(client, instrument, from_ts, now, last_underlying_price)
                if builder:
                    # Add to END (most recently used)
                    self._option_builders[instrument.instrument_token] = builder
                    self._option_snapshots[instrument.instrument_token] = builder.build_snapshot()

    async def _seed_option_state(
        self,
        client: KiteClient,
        instrument: Instrument,
        from_ts: int,
        to_ts: int,
        last_underlying_price: Optional[float] = None,
    ) -> Optional[_MockOptionBuilder]:
        """Seed option state from historical data or theoretical calculation"""
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
            # Fallback: Calculate theoretical price for options when live data unavailable
            logger.info(
                "No live price data for {} - using theoretical fallback",
                tradingsymbol or instrument.instrument_token,
            )

            # Estimate NIFTY spot price
            estimated_spot = last_underlying_price if last_underlying_price else 24000.0
            if self._underlying_snapshot:
                estimated_spot = self._underlying_snapshot.last_close

            if instrument.strike and instrument.instrument_type in ['CE', 'PE']:
                strike = float(instrument.strike)

                if instrument.instrument_type == 'CE':
                    # Call option
                    intrinsic = max(0, estimated_spot - strike)
                    time_value = max(10, strike * 0.01)  # 1% time value minimum
                    last_price = intrinsic + time_value
                else:
                    # Put option
                    intrinsic = max(0, strike - estimated_spot)
                    time_value = max(10, strike * 0.01)
                    last_price = intrinsic + time_value

                # Add some randomness
                last_price *= random.uniform(0.9, 1.1)
                last_price = max(0.05, last_price)  # Minimum price

                # Estimate volume and OI based on strike distance
                distance = abs(strike - estimated_spot)
                if distance < 500:  # ATM/near ATM
                    volume = random.randint(5000, 20000)
                    oi = random.randint(50000, 200000)
                else:  # OTM
                    volume = random.randint(500, 5000)
                    oi = random.randint(5000, 50000)
            else:
                # For spot/futures, use estimated spot
                last_price = estimated_spot
                volume = random.randint(100000, 500000)
                oi = 0

            logger.debug(
                "Fallback seed: {} strike={} price={:.2f}",
                tradingsymbol,
                instrument.strike if instrument.strike else "N/A",
                last_price
            )

        # Calculate Greeks for options in mock mode
        iv = 0.0
        delta = 0.0
        gamma = 0.0
        theta = 0.0
        vega = 0.0

        if (last_price > 0 and
            instrument.strike and
            instrument.expiry and
            instrument.instrument_type in ('CE', 'PE')):

            # Get spot price
            spot_price = last_underlying_price
            if self._underlying_snapshot:
                spot_price = self._underlying_snapshot.last_close
            elif not spot_price:
                spot_price = 24000.0  # Fallback

            if spot_price and spot_price > 0:
                try:
                    iv, greeks = self._greeks_calculator.calculate_option_greeks(
                        market_price=last_price,
                        spot_price=spot_price,
                        strike_price=instrument.strike,
                        expiry_date=instrument.expiry,
                        option_type=instrument.instrument_type,
                    )
                    delta = greeks.get("delta", 0.0)
                    gamma = greeks.get("gamma", 0.0)
                    theta = greeks.get("theta", 0.0)
                    vega = greeks.get("vega", 0.0)
                    logger.info(
                        f"MOCK GREEKS: Calculated for {instrument.tradingsymbol} | "
                        f"price={last_price:.2f} spot={spot_price:.2f} | "
                        f"IV={iv:.4f} delta={delta:.4f}"
                    )
                except Exception as e:
                    logger.warning(f"Failed to calculate mock Greeks for {instrument.tradingsymbol}: {e}")

        return _MockOptionBuilder(
            instrument=instrument,
            base_price=last_price,
            last_price=last_price,
            base_volume=volume or 1,
            base_oi=oi,
            iv=iv,
            delta=delta,
            gamma=gamma,
            theta=theta,
            vega=vega,
        )

    async def generate_option_snapshot(self, instrument: Instrument) -> Optional[OptionSnapshot]:
        """Generate mock option snapshot with thread-safe state access"""
        # Read snapshot (NO LOCK - immutable!)
        snapshot = self._option_snapshots.get(instrument.instrument_token)
        if not snapshot:
            return None

        # Generate new values based on snapshot
        variance = settings.mock_price_variation_bps / 10_000.0
        price_drift = random.uniform(-variance, variance)
        new_price = max(0.05, snapshot.last_price * (1 + price_drift))

        volume = self._jitter_int(snapshot.base_volume, settings.mock_volume_variation, minimum=0)
        oi = self._jitter_int(snapshot.base_oi, settings.mock_volume_variation, minimum=0)

        # Update builder UNDER LOCK, create new snapshot
        async with self._lock:
            builder = self._option_builders.get(instrument.instrument_token)
            if builder:
                builder.last_price = new_price
                builder.base_price = (builder.base_price * 0.85) + (new_price * 0.15)
                builder.base_volume = max(1, int((builder.base_volume * 0.7) + (volume * 0.3)))
                builder.base_oi = max(0, int((builder.base_oi * 0.7) + (oi * 0.3)))

                # Create NEW snapshot
                self._option_snapshots[instrument.instrument_token] = builder.build_snapshot()

        # Generate mock market depth
        tick_size = instrument.tick_size or 0.05
        mock_depth = self._generate_market_depth(new_price, tick_size)

        # Calculate total buy/sell quantities
        total_buy_qty = sum(level.quantity for level in mock_depth.buy)
        total_sell_qty = sum(level.quantity for level in mock_depth.sell)

        return OptionSnapshot(
            instrument=instrument,
            last_price=round(new_price, 2),
            volume=volume,
            oi=oi,
            iv=snapshot.iv,
            delta=snapshot.delta,
            gamma=snapshot.gamma,
            theta=snapshot.theta,
            vega=snapshot.vega,
            timestamp=int(time.time()),
            is_mock=False,  # TEMP: Changed from True for testing
            depth=mock_depth,
            total_buy_quantity=total_buy_qty,
            total_sell_quantity=total_sell_qty,
        )

    @staticmethod
    def _generate_market_depth(last_price: float, tick_size: float = 0.05) -> MarketDepth:
        """
        Generate realistic mock market depth.

        Args:
            last_price: Current option price
            tick_size: Minimum price increment

        Returns:
            MarketDepth with 5 bid and 5 ask levels
        """
        # Generate 5 bid levels (descending prices)
        buy_levels = []
        for i in range(5):
            bid_price = last_price - (tick_size * (i + 1))
            if bid_price < tick_size:
                bid_price = tick_size
            quantity = random.randint(25, 200) * (5 - i)  # More quantity at better prices
            orders = random.randint(2, 8)
            buy_levels.append(DepthLevel(
                quantity=quantity,
                price=round(bid_price, 2),
                orders=orders
            ))

        # Generate 5 ask levels (ascending prices)
        sell_levels = []
        for i in range(5):
            ask_price = last_price + (tick_size * (i + 1))
            quantity = random.randint(25, 200) * (5 - i)  # More quantity at better prices
            orders = random.randint(2, 8)
            sell_levels.append(DepthLevel(
                quantity=quantity,
                price=round(ask_price, 2),
                orders=orders
            ))

        return MarketDepth(buy=buy_levels, sell=sell_levels)

    @staticmethod
    def _jitter_int(base: int, proportion: float, minimum: int = 0) -> int:
        """Add random jitter to an integer value"""
        base = max(base, minimum)
        jitter = max(int(base * proportion), 5 if base == 0 else 1)
        low = base - jitter
        high = base + jitter
        return max(minimum, random.randint(low, high))

    # ======================
    # CLEANUP METHODS
    # ======================

    async def cleanup_expired_internal(self) -> None:
        """
        Remove expired mock state entries (internal, assumes lock held).

        This is called during ensure_options_seeded with lock already held.
        """
        today = self._now_market().date()

        expired_tokens = []
        for token, snapshot in list(self._option_snapshots.items()):
            if snapshot.instrument.expiry:
                try:
                    # Parse expiry string to date
                    expiry_date = datetime.strptime(snapshot.instrument.expiry, "%Y-%m-%d").date()
                    if expiry_date < today:
                        expired_tokens.append(token)
                except (ValueError, TypeError):
                    # Invalid expiry format, skip
                    pass

        for token in expired_tokens:
            self._option_snapshots.pop(token, None)
            self._option_builders.pop(token, None)

        if expired_tokens:
            logger.info(
                f"Cleaned up {len(expired_tokens)} expired mock states, "
                f"remaining: {len(self._option_snapshots)}"
            )

    # Alias for internal use
    _cleanup_expired_internal = cleanup_expired_internal

    async def cleanup_expired(self) -> None:
        """
        Remove expired mock state entries (public, acquires lock).

        This is called from background cleanup task.
        """
        async with self._lock:
            await self._cleanup_expired_internal()

    def get_state_size(self) -> int:
        """Get current number of cached option states"""
        return len(self._option_snapshots)
