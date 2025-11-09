"""
Futures Position Analysis & Rollover Metrics

Analyzes futures market data to identify:
- Position signals (long/short buildup/unwinding)
- Signal strength
- Rollover pressure
"""
from typing import Optional


class FuturesAnalyzer:
    """Analyzes futures position signals and rollover metrics."""

    @staticmethod
    def classify_position_signal(
        price_change_pct: float,
        oi_change_pct: float,
        threshold_pct: float = 0.1
    ) -> str:
        """
        Classify position signal based on price and OI changes.

        Logic:
        - Long Buildup: price ↑ + OI ↑ (bullish - new longs entering)
        - Short Buildup: price ↓ + OI ↑ (bearish - new shorts entering)
        - Long Unwinding: price ↓ + OI ↓ (bearish - longs exiting)
        - Short Unwinding: price ↑ + OI ↓ (bullish - shorts covering)

        Args:
            price_change_pct: Price change percentage
            oi_change_pct: Open interest change percentage
            threshold_pct: Minimum % change to consider significant (default 0.1%)

        Returns:
            Position signal: LONG_BUILDUP, SHORT_BUILDUP, LONG_UNWINDING,
                           SHORT_UNWINDING, or NEUTRAL
        """
        if abs(price_change_pct) < threshold_pct and abs(oi_change_pct) < threshold_pct:
            return "NEUTRAL"

        if price_change_pct > 0 and oi_change_pct > 0:
            return "LONG_BUILDUP"
        elif price_change_pct < 0 and oi_change_pct > 0:
            return "SHORT_BUILDUP"
        elif price_change_pct < 0 and oi_change_pct < 0:
            return "LONG_UNWINDING"
        elif price_change_pct > 0 and oi_change_pct < 0:
            return "SHORT_UNWINDING"
        else:
            return "NEUTRAL"

    @staticmethod
    def compute_signal_strength(
        price_change_pct: float,
        oi_change_pct: float
    ) -> float:
        """
        Compute signal strength as product of price and OI change magnitudes.

        Strong signals have both significant price AND OI movement.

        Args:
            price_change_pct: Absolute price change percentage
            oi_change_pct: Absolute OI change percentage

        Returns:
            Strength value (0-100+). Higher = stronger signal.
            Examples:
            - 2% price + 5% OI = 0.10 strength
            - 5% price + 10% OI = 0.50 strength
        """
        return abs(price_change_pct) * abs(oi_change_pct) / 100

    @staticmethod
    def compute_rollover_pressure(
        days_to_expiry: int,
        oi_pct: float,
        threshold_days: int = 5
    ) -> float:
        """
        Compute rollover pressure based on days to expiry and OI concentration.

        Rollover pressure increases exponentially as expiry approaches when
        significant OI is still concentrated in the expiring contract.

        Args:
            days_to_expiry: Days until contract expiry
            oi_pct: Percentage of total OI in this contract (0-100)
            threshold_days: Days before expiry to start computing pressure

        Returns:
            Rollover pressure (0-100). Higher = more urgent to roll.

        Example:
            - 7 days to expiry, 60% OI = 0 (beyond threshold)
            - 5 days to expiry, 60% OI = 0 (at threshold)
            - 3 days to expiry, 60% OI = 8.64 (moderate pressure)
            - 1 day to expiry, 60% OI = 38.4 (high pressure)
            - 0 days to expiry, 60% OI = 60 (maximum pressure)
        """
        if days_to_expiry > threshold_days:
            return 0.0

        # Pressure increases exponentially as expiry approaches
        # time_factor: 1.0 at expiry, 0.0 at threshold
        time_factor = (threshold_days - days_to_expiry) / threshold_days

        # Quadratic scaling: pressure = oi_pct * (time_factor^2)
        # This makes pressure escalate rapidly in final days
        return oi_pct * (time_factor ** 2)

    @staticmethod
    def get_bullish_bearish_indicator(position_signal: str) -> str:
        """
        Convert position signal to simple bullish/bearish/neutral indicator.

        Args:
            position_signal: One of LONG_BUILDUP, SHORT_BUILDUP, etc.

        Returns:
            BULLISH, BEARISH, or NEUTRAL
        """
        bullish_signals = ["LONG_BUILDUP", "SHORT_UNWINDING"]
        bearish_signals = ["SHORT_BUILDUP", "LONG_UNWINDING"]

        if position_signal in bullish_signals:
            return "BULLISH"
        elif position_signal in bearish_signals:
            return "BEARISH"
        else:
            return "NEUTRAL"
