"""
Tick processing service.

Handles transformation, validation, and enrichment of market tick data.
Extracted from generator.py to improve modularity and testability.
"""
from __future__ import annotations

import time
from typing import Dict, List, Any, Optional
from datetime import datetime

from loguru import logger

from ..schema import Instrument, OptionSnapshot, DepthLevel, MarketDepth
from ..greeks_calculator import GreeksCalculator
from ..utils.symbol_utils import normalize_symbol
from ..metrics import (
    record_tick_processing,
    record_greeks_calculation,
    record_processing_error,
    market_depth_updates_total,
    update_underlying_price,
)


class TickProcessor:
    """
    Processes and enriches incoming market tick data.

    Responsibilities:
    - Validate and transform raw tick data
    - Route ticks to appropriate channels (underlying vs options)
    - Calculate Greeks for option ticks
    - Extract and normalize market depth data
    - Publish processed data to appropriate channels
    """

    def __init__(
        self,
        greeks_calculator: GreeksCalculator,
        market_tz,
        batcher: Optional[Any] = None,  # TickBatcher, Optional to avoid circular import
        validator: Optional[Any] = None,  # TickValidator, Optional to avoid circular import
    ):
        """
        Initialize tick processor.

        Args:
            greeks_calculator: Calculator for option Greeks
            market_tz: Market timezone for date calculations
            batcher: Optional TickBatcher for batched publishing
            validator: Optional TickValidator for validation
        """
        self._greeks_calculator = greeks_calculator
        self._market_tz = market_tz
        self._batcher = batcher
        self._validator = validator
        self._last_underlying_price: Optional[float] = None
        self._last_tick_at: Dict[str, float] = {}

    def get_last_underlying_price(self) -> Optional[float]:
        """Get the last known underlying price"""
        return self._last_underlying_price

    def get_last_tick_time(self, account_id: str) -> Optional[float]:
        """Get the last tick timestamp for an account"""
        return self._last_tick_at.get(account_id)

    async def process_ticks(
        self,
        account_id: str,
        lookup: Dict[int, Instrument],
        ticks: List[Dict[str, Any]],
        today_market: datetime.date,
    ) -> None:
        """
        Process a batch of tick data.

        Args:
            account_id: Account ID that received these ticks
            lookup: Mapping of instrument tokens to instruments
            ticks: List of raw tick data from WebSocket
            today_market: Current market date for expiry checking
        """
        if ticks:
            self._last_tick_at[account_id] = time.time()

        for tick in ticks:
            start_time = time.perf_counter()
            success = False

            try:
                instrument = lookup.get(tick.get("instrument_token"))
                if not instrument:
                    continue

                # Note: KiteConnect doesn't send ticks for expired contracts,
                # so no need for expiry check

                # Route based on instrument type
                if instrument.segment == "INDICES":
                    await self._process_underlying_tick(tick, instrument)
                    tick_type = "underlying"
                else:
                    await self._process_option_tick(tick, instrument)
                    tick_type = "option"

                success = True

            except Exception as e:
                logger.error(f"Error processing tick: {e}")
                record_processing_error("tick_processing")
                tick_type = "unknown"

            finally:
                # Record metrics
                if success:
                    latency = time.perf_counter() - start_time
                    record_tick_processing(tick_type, latency, success=True)

    async def _process_underlying_tick(
        self,
        tick: Dict[str, Any],
        instrument: Instrument,
    ) -> None:
        """
        Process underlying/index tick data.

        Args:
            tick: Raw tick data
            instrument: Instrument metadata
        """
        # Validate tick if validator is enabled
        if self._validator:
            if not self._validator.validate_underlying_tick(tick):
                logger.debug(f"Skipping invalid underlying tick for {instrument.tradingsymbol}")
                return

        last_price = float(tick.get("last_price") or 0.0)

        # Normalize symbol to canonical form (NIFTY 50 -> NIFTY)
        canonical_symbol = normalize_symbol(instrument.tradingsymbol)

        bar = {
            "symbol": canonical_symbol,
            "instrument_token": instrument.instrument_token,
            "last_price": last_price,
            "volume": int(tick.get("volume_traded_today") or tick.get("volume") or 0),
            "timestamp": int(tick.get("timestamp", int(time.time()))),
            "ohlc": tick.get("ohlc", {}),
        }

        # Track underlying price for Greeks calculation
        self._last_underlying_price = last_price
        logger.info(f"GREEKS TEST: Underlying {canonical_symbol} price updated to {last_price}")

        # Update metrics
        update_underlying_price(canonical_symbol, last_price)

        # Publish via batcher if available, otherwise publish directly
        if self._batcher:
            await self._batcher.add_underlying(bar)
        else:
            # Fallback to direct publishing
            from ..publisher import publish_underlying_bar
            await publish_underlying_bar(bar)

    async def _process_option_tick(
        self,
        tick: Dict[str, Any],
        instrument: Instrument,
    ) -> None:
        """
        Process option tick data with Greeks calculation.

        Args:
            tick: Raw tick data
            instrument: Instrument metadata
        """
        # Validate tick if validator is enabled
        if self._validator:
            if not self._validator.validate_option_tick(tick):
                logger.debug(f"Skipping invalid option tick for {instrument.tradingsymbol}")
                return

        market_price = float(tick.get("last_price") or 0.0)

        # Calculate Greeks
        greeks_data = await self._calculate_greeks(
            market_price=market_price,
            instrument=instrument,
        )

        # Extract market depth
        market_depth = self._extract_market_depth(tick, instrument)

        # Normalize the underlying symbol (e.g., NIFTY 50 -> NIFTY)
        canonical_symbol = normalize_symbol(instrument.symbol)

        # Create a normalized instrument with canonical underlying symbol
        normalized_instrument = Instrument(
            symbol=canonical_symbol,  # Normalized underlying (NIFTY)
            instrument_token=instrument.instrument_token,
            tradingsymbol=instrument.tradingsymbol,  # Keep full option name as-is
            segment=instrument.segment,
            exchange=instrument.exchange,
            strike=instrument.strike,
            expiry=instrument.expiry,
            instrument_type=instrument.instrument_type,
            lot_size=instrument.lot_size,
            tick_size=instrument.tick_size,
        )

        # Create option snapshot
        snapshot = OptionSnapshot(
            instrument=normalized_instrument,
            last_price=market_price,
            volume=int(tick.get("volume_traded_today") or tick.get("volume") or 0),
            oi=int(tick.get("oi") or tick.get("open_interest") or 0),
            iv=greeks_data["iv"],
            delta=greeks_data["delta"],
            gamma=greeks_data["gamma"],
            theta=greeks_data["theta"],
            vega=greeks_data["vega"],
            timestamp=int(tick.get("timestamp", int(time.time()))),
            depth=market_depth,
            total_buy_quantity=int(tick.get("total_buy_quantity", 0)),
            total_sell_quantity=int(tick.get("total_sell_quantity", 0)),
        )

        # Publish via batcher if available, otherwise publish directly
        if self._batcher:
            await self._batcher.add_option(snapshot)
        else:
            # Fallback to direct publishing
            from ..publisher import publish_option_snapshot
            await publish_option_snapshot(snapshot)

    async def _calculate_greeks(
        self,
        market_price: float,
        instrument: Instrument,
    ) -> Dict[str, float]:
        """
        Calculate Greeks for an option.

        Args:
            market_price: Current market price of the option
            instrument: Option instrument metadata

        Returns:
            Dictionary with iv, delta, gamma, theta, vega
        """
        # Initialize to zero
        result = {
            "iv": 0.0,
            "delta": 0.0,
            "gamma": 0.0,
            "theta": 0.0,
            "vega": 0.0,
        }

        # Only calculate Greeks if we have valid data
        if (market_price > 0 and
            self._last_underlying_price and
            self._last_underlying_price > 0 and
            instrument.strike and
            instrument.expiry and
            instrument.instrument_type in ('CE', 'PE')):

            try:
                # Calculate IV and Greeks with metrics
                greeks_start = time.perf_counter()

                iv, greeks = self._greeks_calculator.calculate_option_greeks(
                    market_price=market_price,
                    spot_price=self._last_underlying_price,
                    strike_price=instrument.strike,
                    expiry_date=instrument.expiry,
                    option_type=instrument.instrument_type,
                )

                greeks_latency = time.perf_counter() - greeks_start
                record_greeks_calculation(greeks_latency, success=True)

                result["iv"] = iv
                result["delta"] = greeks.get("delta", 0.0)
                result["gamma"] = greeks.get("gamma", 0.0)
                result["theta"] = greeks.get("theta", 0.0)
                result["vega"] = greeks.get("vega", 0.0)

                logger.info(
                    f"GREEKS TEST: Calculated for {instrument.tradingsymbol} | "
                    f"price={market_price:.2f} spot={self._last_underlying_price:.2f} | "
                    f"IV={iv:.4f} delta={result['delta']:.4f}"
                )
            except Exception as e:
                record_greeks_calculation(0.0, success=False)
                record_processing_error("greeks_calculation")
                logger.debug(
                    "Failed to calculate Greeks for %s (strike=%s, spot=%s, price=%s): %s",
                    instrument.tradingsymbol,
                    instrument.strike,
                    self._last_underlying_price,
                    market_price,
                    e,
                )

        return result

    def _extract_market_depth(
        self,
        tick: Dict[str, Any],
        instrument: Instrument,
    ) -> Optional[MarketDepth]:
        """
        Extract and normalize market depth data from tick.

        Args:
            tick: Raw tick data containing depth information
            instrument: Instrument metadata (for logging)

        Returns:
            MarketDepth object or None if no depth data available
        """
        depth_data = tick.get("depth")
        if not depth_data:
            return None

        try:
            # Extract buy (bid) levels
            buy_levels = []
            for level in depth_data.get("buy", []):
                buy_levels.append(DepthLevel(
                    quantity=int(level.get("quantity", 0)),
                    price=float(level.get("price", 0.0)) / 100.0,  # Convert paise to rupees
                    orders=int(level.get("orders", 0))
                ))

            # Extract sell (ask) levels
            sell_levels = []
            for level in depth_data.get("sell", []):
                sell_levels.append(DepthLevel(
                    quantity=int(level.get("quantity", 0)),
                    price=float(level.get("price", 0.0)) / 100.0,  # Convert paise to rupees
                    orders=int(level.get("orders", 0))
                ))

            if buy_levels or sell_levels:
                market_depth_updates_total.labels(instrument_type="option").inc()
                return MarketDepth(buy=buy_levels, sell=sell_levels)

        except Exception as e:
            record_processing_error("market_depth_parsing")
            logger.debug(f"Failed to parse market depth for {instrument.tradingsymbol}: {e}")

        return None

    def reset_state(self) -> None:
        """Reset processor state"""
        self._last_underlying_price = None
        self._last_tick_at.clear()

    def get_stats(self) -> Dict[str, Any]:
        """Get processor statistics"""
        return {
            "last_underlying_price": self._last_underlying_price,
            "accounts_tracked": len(self._last_tick_at),
            "last_tick_times": dict(self._last_tick_at),
        }
