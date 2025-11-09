"""
Market Impact Calculator

Calculates the cost of executing an order based on market depth,
estimating price slippage, basis points impact, and levels consumed.

Integrates with MarketDepthAnalyzer to provide detailed impact analysis.

Usage:
    calculator = MarketImpactCalculator()
    impact = calculator.calculate_impact(
        depth_data=tick['depth'],
        quantity=500,
        side='BUY',
        last_price=tick['last_price']
    )

    if impact.impact_bps > 50:
        print(f"High impact: {impact.impact_bps} bps, cost: ₹{impact.impact_cost}")
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from .market_depth_analyzer import MarketDepthAnalyzer, DepthLevel

logger = logging.getLogger(__name__)


class ImpactLevel(str, Enum):
    """Market impact severity levels."""
    LOW = "LOW"           # < 10 bps
    MODERATE = "MODERATE"  # 10-30 bps
    HIGH = "HIGH"          # 30-50 bps
    VERY_HIGH = "VERY_HIGH"  # > 50 bps


class ExecutionStrategy(str, Enum):
    """Recommended execution strategies based on impact."""
    MARKET_ORDER = "MARKET_ORDER"        # Low impact, execute immediately
    LIMIT_ORDER = "LIMIT_ORDER"          # Moderate impact, use limit
    SPLIT_ORDER = "SPLIT_ORDER"          # High impact, split into smaller pieces
    TWAP = "TWAP"                        # Very high impact, time-weighted average price
    REDUCE_QUANTITY = "REDUCE_QUANTITY"  # Excessive impact, reduce order size


@dataclass
class MarketImpactResult:
    """
    Result of market impact calculation.

    Attributes:
        quantity: Order quantity
        side: Order side (BUY/SELL)
        estimated_fill_price: Average execution price
        mid_price: Market mid-price
        slippage_abs: Absolute slippage (fill_price - mid_price)
        slippage_pct: Slippage as percentage of mid-price
        impact_bps: Market impact in basis points
        impact_cost: Absolute cost in rupees
        levels_consumed: Number of price levels needed
        can_fill_completely: Whether order can be filled
        unfilled_quantity: Quantity that cannot be filled
        impact_level: LOW/MODERATE/HIGH/VERY_HIGH
        recommended_strategy: Execution strategy recommendation
        warnings: List of warning messages
    """
    quantity: int
    side: str
    estimated_fill_price: float
    mid_price: float
    slippage_abs: float
    slippage_pct: float
    impact_bps: int
    impact_cost: float
    levels_consumed: int
    can_fill_completely: bool
    unfilled_quantity: int
    impact_level: ImpactLevel
    recommended_strategy: ExecutionStrategy
    warnings: List[str]

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "quantity": self.quantity,
            "side": self.side,
            "estimated_fill_price": round(self.estimated_fill_price, 2),
            "mid_price": round(self.mid_price, 2),
            "slippage_abs": round(self.slippage_abs, 4),
            "slippage_pct": round(self.slippage_pct, 4),
            "impact_bps": self.impact_bps,
            "impact_cost": round(self.impact_cost, 2),
            "levels_consumed": self.levels_consumed,
            "can_fill_completely": self.can_fill_completely,
            "unfilled_quantity": self.unfilled_quantity,
            "impact_level": self.impact_level.value,
            "recommended_strategy": self.recommended_strategy.value,
            "warnings": self.warnings
        }


class MarketImpactCalculator:
    """
    Calculates market impact for order execution.

    Impact thresholds (basis points):
    - LOW: < 10 bps (negligible impact)
    - MODERATE: 10-30 bps (acceptable for most orders)
    - HIGH: 30-50 bps (consider splitting or using TWAP)
    - VERY_HIGH: > 50 bps (reduce size or wait for better liquidity)
    """

    # Impact thresholds in basis points
    LOW_THRESHOLD = 10
    MODERATE_THRESHOLD = 30
    HIGH_THRESHOLD = 50

    def __init__(self, market_depth_analyzer: Optional[MarketDepthAnalyzer] = None):
        """
        Initialize market impact calculator.

        Args:
            market_depth_analyzer: Optional existing analyzer
        """
        self.depth_analyzer = market_depth_analyzer or MarketDepthAnalyzer(
            include_advanced=True
        )

    def calculate_impact(
        self,
        depth_data: Dict,
        quantity: int,
        side: str,  # 'BUY' or 'SELL'
        last_price: float,
        instrument_token: Optional[int] = None
    ) -> MarketImpactResult:
        """
        Calculate market impact for an order.

        Args:
            depth_data: Market depth dict with 'buy' and 'sell' arrays
            quantity: Order quantity (number of lots/shares)
            side: Order side ('BUY' or 'SELL')
            last_price: Last traded price
            instrument_token: Optional instrument identifier for logging

        Returns:
            MarketImpactResult with detailed impact analysis
        """
        # Parse depth levels
        buy_levels = self.depth_analyzer._parse_depth_levels(depth_data.get("buy", []))
        sell_levels = self.depth_analyzer._parse_depth_levels(depth_data.get("sell", []))

        if not buy_levels or not sell_levels:
            logger.warning(
                f"Empty depth data for instrument {instrument_token}, "
                f"cannot calculate market impact"
            )
            return self._empty_impact_result(quantity, side, last_price)

        # Calculate mid-price
        mid_price = (buy_levels[0].price + sell_levels[0].price) / 2.0

        # Determine which side we're consuming
        levels_to_consume = sell_levels if side.upper() == "BUY" else buy_levels

        # Calculate fill price and levels consumed
        fill_price, levels_consumed, unfilled = self._calculate_fill_price(
            levels=levels_to_consume,
            quantity=quantity
        )

        # Calculate slippage
        slippage_abs = abs(fill_price - mid_price)
        slippage_pct = (slippage_abs / mid_price * 100.0) if mid_price > 0 else 0.0

        # Calculate impact in basis points
        impact_bps = int((slippage_abs / mid_price) * 10000) if mid_price > 0 else 0

        # Calculate absolute impact cost
        impact_cost = slippage_abs * quantity

        # Determine if can fill completely
        can_fill = (unfilled == 0)

        # Categorize impact level
        impact_level = self._categorize_impact(impact_bps)

        # Determine recommended strategy
        recommended_strategy = self._determine_strategy(
            impact_level=impact_level,
            can_fill=can_fill,
            quantity=quantity,
            levels_consumed=levels_consumed
        )

        # Generate warnings
        warnings = self._generate_warnings(
            impact_bps=impact_bps,
            impact_cost=impact_cost,
            can_fill=can_fill,
            unfilled=unfilled,
            levels_consumed=levels_consumed,
            total_levels=len(levels_to_consume)
        )

        return MarketImpactResult(
            quantity=quantity,
            side=side,
            estimated_fill_price=fill_price,
            mid_price=mid_price,
            slippage_abs=slippage_abs,
            slippage_pct=slippage_pct,
            impact_bps=impact_bps,
            impact_cost=impact_cost,
            levels_consumed=levels_consumed,
            can_fill_completely=can_fill,
            unfilled_quantity=unfilled,
            impact_level=impact_level,
            recommended_strategy=recommended_strategy,
            warnings=warnings
        )

    def _calculate_fill_price(
        self,
        levels: List[DepthLevel],
        quantity: int
    ) -> Tuple[float, int, int]:
        """
        Calculate average fill price by walking through depth levels.

        Args:
            levels: List of depth levels (sell side for BUY, buy side for SELL)
            quantity: Order quantity

        Returns:
            Tuple of (fill_price, levels_consumed, unfilled_quantity)
        """
        remaining = quantity
        total_cost = 0.0
        levels_consumed = 0

        for level in levels:
            if remaining <= 0:
                break

            # Consume this level
            qty_at_level = min(remaining, level.quantity)
            total_cost += qty_at_level * level.price
            remaining -= qty_at_level
            levels_consumed += 1

        # Calculate unfilled quantity
        unfilled = max(0, remaining)

        # If we couldn't fill completely, use last level price for unfilled
        if unfilled > 0 and levels:
            total_cost += unfilled * levels[-1].price

        # Calculate average fill price
        fill_price = total_cost / quantity if quantity > 0 else 0.0

        return fill_price, levels_consumed, unfilled

    def _categorize_impact(self, impact_bps: int) -> ImpactLevel:
        """Categorize impact based on basis points."""
        if impact_bps < self.LOW_THRESHOLD:
            return ImpactLevel.LOW
        elif impact_bps < self.MODERATE_THRESHOLD:
            return ImpactLevel.MODERATE
        elif impact_bps < self.HIGH_THRESHOLD:
            return ImpactLevel.HIGH
        else:
            return ImpactLevel.VERY_HIGH

    def _determine_strategy(
        self,
        impact_level: ImpactLevel,
        can_fill: bool,
        quantity: int,
        levels_consumed: int
    ) -> ExecutionStrategy:
        """Determine recommended execution strategy."""
        # Cannot fill completely - reduce quantity
        if not can_fill:
            return ExecutionStrategy.REDUCE_QUANTITY

        # Very high impact - use TWAP
        if impact_level == ImpactLevel.VERY_HIGH:
            return ExecutionStrategy.TWAP

        # High impact - split order
        if impact_level == ImpactLevel.HIGH:
            return ExecutionStrategy.SPLIT_ORDER

        # Moderate impact - use limit order
        if impact_level == ImpactLevel.MODERATE:
            return ExecutionStrategy.LIMIT_ORDER

        # Low impact - proceed with market order
        return ExecutionStrategy.MARKET_ORDER

    def _generate_warnings(
        self,
        impact_bps: int,
        impact_cost: float,
        can_fill: bool,
        unfilled: int,
        levels_consumed: int,
        total_levels: int
    ) -> List[str]:
        """Generate warning messages based on impact analysis."""
        warnings = []

        # High impact warning
        if impact_bps >= self.HIGH_THRESHOLD:
            warnings.append(
                f"High market impact: {impact_bps} bps (threshold: {self.HIGH_THRESHOLD}). "
                f"Estimated cost: ₹{impact_cost:.2f}"
            )

        # Cannot fill warning
        if not can_fill:
            warnings.append(
                f"Insufficient depth: {unfilled} lots cannot be filled. "
                f"Consider reducing order size or splitting into multiple orders."
            )

        # Many levels consumed warning
        if levels_consumed >= 3:
            warnings.append(
                f"Order consumes {levels_consumed} price levels ({levels_consumed}/{total_levels} available). "
                f"Consider using limit order or TWAP strategy."
            )

        # Moderate impact advisory
        if self.MODERATE_THRESHOLD <= impact_bps < self.HIGH_THRESHOLD:
            warnings.append(
                f"Moderate market impact: {impact_bps} bps. "
                f"Consider using limit order to reduce costs."
            )

        return warnings

    def _empty_impact_result(
        self,
        quantity: int,
        side: str,
        last_price: float
    ) -> MarketImpactResult:
        """Return empty/default result when depth data is missing."""
        return MarketImpactResult(
            quantity=quantity,
            side=side,
            estimated_fill_price=last_price,
            mid_price=last_price,
            slippage_abs=0.0,
            slippage_pct=0.0,
            impact_bps=0,
            impact_cost=0.0,
            levels_consumed=0,
            can_fill_completely=False,
            unfilled_quantity=quantity,
            impact_level=ImpactLevel.VERY_HIGH,
            recommended_strategy=ExecutionStrategy.REDUCE_QUANTITY,
            warnings=["No market depth data available - cannot calculate impact"]
        )


# Convenience function for quick impact calculation
def calculate_market_impact(
    depth_data: Dict,
    quantity: int,
    side: str,
    last_price: float
) -> Dict:
    """
    Quick market impact calculation function.

    Args:
        depth_data: Market depth dict
        quantity: Order quantity
        side: 'BUY' or 'SELL'
        last_price: Last traded price

    Returns:
        Dictionary with impact analysis
    """
    calculator = MarketImpactCalculator()
    result = calculator.calculate_impact(
        depth_data=depth_data,
        quantity=quantity,
        side=side,
        last_price=last_price
    )
    return result.to_dict()
