"""
Spread Analyzer

Analyzes bid-ask spreads and provides execution recommendations based on
spread width, liquidity, and configured thresholds.

Integrates with MarketDepthAnalyzer to provide actionable insights for order execution.

Usage:
    analyzer = SpreadAnalyzer()
    result = analyzer.analyze_spread(
        depth_data=tick['depth'],
        last_price=tick['last_price'],
        quantity=100,
        side='BUY',
        strategy_settings=settings
    )

    if result.should_alert:
        print(f"Wide spread detected: {result.spread_pct}%")
        print(f"Recommended action: {result.recommended_action}")
"""

from __future__ import annotations

import logging
from typing import Dict, Optional, List
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from .market_depth_analyzer import MarketDepthAnalyzer, MarketDepthAnalysis

logger = logging.getLogger(__name__)


class SpreadCategory(str, Enum):
    """Spread width categories."""
    TIGHT = "TIGHT"           # < 0.2%
    NORMAL = "NORMAL"         # 0.2% - 0.5%
    WIDE = "WIDE"             # 0.5% - 1.0%
    VERY_WIDE = "VERY_WIDE"   # > 1.0%


class ExecutionAction(str, Enum):
    """Recommended execution actions."""
    PROCEED = "PROCEED"                    # Execute immediately
    USE_LIMIT_ORDER = "USE_LIMIT_ORDER"    # Use limit order instead of market
    ALERT_USER = "ALERT_USER"              # Warn user before executing
    REJECT = "REJECT"                      # Reject the order


@dataclass
class SpreadAnalysisResult:
    """
    Result of spread analysis.

    Attributes:
        spread_pct: Spread as percentage
        spread_abs: Absolute spread value
        spread_category: TIGHT/NORMAL/WIDE/VERY_WIDE
        should_alert: Whether to alert user
        should_reject: Whether to reject order
        recommended_action: Suggested action (PROCEED, LIMIT, ALERT, REJECT)
        recommended_limit_price: Suggested limit price (if applicable)
        warnings: List of warning messages
        market_depth_analysis: Full market depth metrics
    """
    spread_pct: float
    spread_abs: float
    spread_category: SpreadCategory
    should_alert: bool
    should_reject: bool
    recommended_action: ExecutionAction
    recommended_limit_price: Optional[Decimal]
    warnings: List[str]
    market_depth_analysis: MarketDepthAnalysis

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "spread_pct": self.spread_pct,
            "spread_abs": self.spread_abs,
            "spread_category": self.spread_category.value,
            "should_alert": self.should_alert,
            "should_reject": self.should_reject,
            "recommended_action": self.recommended_action.value,
            "recommended_limit_price": float(self.recommended_limit_price) if self.recommended_limit_price else None,
            "warnings": self.warnings,
            "market_depth_analysis": self.market_depth_analysis.to_dict()
        }


@dataclass
class StrategySettings:
    """
    Strategy-specific settings for spread analysis.

    These typically come from the strategy_settings table.
    """
    max_order_spread_pct: float = 0.5
    min_liquidity_score: int = 50
    require_user_approval_high_impact: bool = True
    max_market_impact_bps: int = 50


class SpreadAnalyzer:
    """
    Analyzes bid-ask spreads and provides execution recommendations.

    Thresholds for spread categorization:
    - TIGHT: < 0.2% (excellent liquidity)
    - NORMAL: 0.2% - 0.5% (acceptable for most orders)
    - WIDE: 0.5% - 1.0% (caution advised)
    - VERY_WIDE: > 1.0% (high cost, user confirmation needed)
    """

    # Default spread thresholds (can be overridden per strategy)
    TIGHT_THRESHOLD = 0.2      # 0.2%
    NORMAL_THRESHOLD = 0.5     # 0.5%
    WIDE_THRESHOLD = 1.0       # 1.0%

    def __init__(self, market_depth_analyzer: Optional[MarketDepthAnalyzer] = None):
        """
        Initialize spread analyzer.

        Args:
            market_depth_analyzer: Optional existing analyzer, creates new one if not provided
        """
        self.depth_analyzer = market_depth_analyzer or MarketDepthAnalyzer(
            include_advanced=True,
            min_liquid_score=50.0,
            max_spread_pct=0.5
        )

    def analyze_spread(
        self,
        depth_data: Dict,
        last_price: float,
        quantity: int,
        side: str,  # 'BUY' or 'SELL'
        strategy_settings: Optional[StrategySettings] = None,
        instrument_token: Optional[int] = None
    ) -> SpreadAnalysisResult:
        """
        Analyze spread and provide execution recommendation.

        Args:
            depth_data: Market depth dict with 'buy' and 'sell' arrays
            last_price: Last traded price
            quantity: Order quantity
            side: Order side ('BUY' or 'SELL')
            strategy_settings: Optional strategy-specific settings
            instrument_token: Optional instrument identifier for logging

        Returns:
            SpreadAnalysisResult with recommendations
        """
        # Use default settings if not provided
        settings = strategy_settings or StrategySettings()

        # Run market depth analysis
        depth_analysis = self.depth_analyzer.analyze(
            depth_data=depth_data,
            last_price=last_price,
            instrument_token=instrument_token
        )

        # Extract spread metrics
        spread_pct = depth_analysis.spread.bid_ask_spread_pct
        spread_abs = depth_analysis.spread.bid_ask_spread_abs

        # Categorize spread
        spread_category = self._categorize_spread(spread_pct)

        # Determine if we should alert or reject
        should_alert = self._should_alert(spread_pct, depth_analysis, settings)
        should_reject = self._should_reject(spread_pct, depth_analysis, settings)

        # Generate warnings
        warnings = self._generate_warnings(spread_pct, spread_abs, depth_analysis, settings, quantity, side)

        # Determine recommended action
        recommended_action = self._determine_action(
            spread_category=spread_category,
            should_alert=should_alert,
            should_reject=should_reject,
            liquidity_score=depth_analysis.liquidity.liquidity_score,
            settings=settings
        )

        # Calculate recommended limit price
        recommended_limit_price = self._calculate_limit_price(
            side=side,
            spread_metrics=depth_analysis.spread,
            spread_category=spread_category
        )

        return SpreadAnalysisResult(
            spread_pct=spread_pct,
            spread_abs=spread_abs,
            spread_category=spread_category,
            should_alert=should_alert,
            should_reject=should_reject,
            recommended_action=recommended_action,
            recommended_limit_price=recommended_limit_price,
            warnings=warnings,
            market_depth_analysis=depth_analysis
        )

    def _categorize_spread(self, spread_pct: float) -> SpreadCategory:
        """Categorize spread based on percentage."""
        if spread_pct < self.TIGHT_THRESHOLD:
            return SpreadCategory.TIGHT
        elif spread_pct < self.NORMAL_THRESHOLD:
            return SpreadCategory.NORMAL
        elif spread_pct < self.WIDE_THRESHOLD:
            return SpreadCategory.WIDE
        else:
            return SpreadCategory.VERY_WIDE

    def _should_alert(
        self,
        spread_pct: float,
        depth_analysis: MarketDepthAnalysis,
        settings: StrategySettings
    ) -> bool:
        """Determine if we should alert the user."""
        # Alert if spread exceeds strategy threshold
        if spread_pct > settings.max_order_spread_pct:
            return True

        # Alert if liquidity is too low
        if depth_analysis.liquidity.liquidity_score < settings.min_liquidity_score:
            return True

        # Alert if spread is WIDE or VERY_WIDE
        spread_category = self._categorize_spread(spread_pct)
        if spread_category in (SpreadCategory.WIDE, SpreadCategory.VERY_WIDE):
            return True

        return False

    def _should_reject(
        self,
        spread_pct: float,
        depth_analysis: MarketDepthAnalysis,
        settings: StrategySettings
    ) -> bool:
        """Determine if we should reject the order outright."""
        # Reject if spread is extremely wide (> 2x strategy threshold)
        if spread_pct > settings.max_order_spread_pct * 2:
            return True

        # Reject if liquidity tier is ILLIQUID
        if depth_analysis.liquidity.liquidity_tier == "ILLIQUID":
            return True

        # Reject if spread is VERY_WIDE (> 1.0%) for safety
        if spread_pct > self.WIDE_THRESHOLD:
            return True

        return False

    def _generate_warnings(
        self,
        spread_pct: float,
        spread_abs: float,
        depth_analysis: MarketDepthAnalysis,
        settings: StrategySettings,
        quantity: int,
        side: str
    ) -> List[str]:
        """Generate warning messages based on analysis."""
        warnings = []

        # Wide spread warning
        if spread_pct > settings.max_order_spread_pct:
            potential_loss = spread_abs * quantity
            warnings.append(
                f"Wide spread detected: {spread_pct:.2f}% "
                f"(threshold: {settings.max_order_spread_pct:.2f}%). "
                f"Potential slippage cost: ₹{potential_loss:.2f}"
            )

        # Low liquidity warning
        if depth_analysis.liquidity.liquidity_score < settings.min_liquidity_score:
            warnings.append(
                f"Low liquidity: score {depth_analysis.liquidity.liquidity_score:.0f}/100 "
                f"(minimum: {settings.min_liquidity_score}). Tier: {depth_analysis.liquidity.liquidity_tier}"
            )

        # Market impact warning (if advanced metrics available)
        if depth_analysis.advanced:
            # Estimate market impact cost for this order
            impact_cost = (
                depth_analysis.advanced.market_impact_cost_100 * (quantity / 100)
                if quantity <= 500
                else depth_analysis.advanced.market_impact_cost_500 * (quantity / 500)
            )

            # Calculate impact in basis points
            mid_price = depth_analysis.spread.mid_price
            impact_bps = (impact_cost / mid_price) * 10000 if mid_price > 0 else 0

            if impact_bps > settings.max_market_impact_bps:
                warnings.append(
                    f"High market impact: {impact_bps:.0f} bps "
                    f"(threshold: {settings.max_market_impact_bps} bps). "
                    f"Estimated cost: ₹{impact_cost:.2f}"
                )

        # Imbalanced book warning
        if abs(depth_analysis.imbalance.depth_imbalance_pct) > 20:
            direction = "buy" if depth_analysis.imbalance.depth_imbalance_pct > 0 else "sell"
            warnings.append(
                f"Imbalanced order book: {abs(depth_analysis.imbalance.depth_imbalance_pct):.1f}% {direction} side. "
                f"Book pressure: {depth_analysis.imbalance.book_pressure:.2f}"
            )

        # Illiquidity flags
        flags = depth_analysis.liquidity.illiquidity_flags
        if flags.get("thin_depth"):
            warnings.append(
                f"Thin order book: total depth {depth_analysis.depth.total_bid_quantity + depth_analysis.depth.total_ask_quantity} lots"
            )

        if flags.get("low_best_depth"):
            warnings.append(
                f"Low depth at best price: bid {depth_analysis.depth.depth_at_best_bid} / "
                f"ask {depth_analysis.depth.depth_at_best_ask} lots"
            )

        return warnings

    def _determine_action(
        self,
        spread_category: SpreadCategory,
        should_alert: bool,
        should_reject: bool,
        liquidity_score: float,
        settings: StrategySettings
    ) -> ExecutionAction:
        """Determine recommended execution action."""
        # Reject if flagged
        if should_reject:
            return ExecutionAction.REJECT

        # Alert user for WIDE/VERY_WIDE spreads
        if spread_category in (SpreadCategory.WIDE, SpreadCategory.VERY_WIDE):
            if settings.require_user_approval_high_impact:
                return ExecutionAction.ALERT_USER
            else:
                return ExecutionAction.USE_LIMIT_ORDER

        # Use limit order for NORMAL spreads (safer than market)
        if spread_category == SpreadCategory.NORMAL:
            if should_alert:
                return ExecutionAction.USE_LIMIT_ORDER
            else:
                return ExecutionAction.PROCEED

        # TIGHT spreads - safe to proceed
        return ExecutionAction.PROCEED

    def _calculate_limit_price(
        self,
        side: str,
        spread_metrics,
        spread_category: SpreadCategory
    ) -> Optional[Decimal]:
        """
        Calculate recommended limit price.

        Strategy:
        - For BUY: Start at microprice or weighted_mid, adjust based on spread
        - For SELL: Start at microprice or weighted_mid, adjust based on spread
        - Tighter spreads = closer to best bid/ask
        - Wider spreads = closer to mid price for better fill probability
        """
        best_bid = spread_metrics.best_bid
        best_ask = spread_metrics.best_ask
        mid_price = spread_metrics.mid_price
        weighted_mid = spread_metrics.weighted_mid_price

        if side.upper() == "BUY":
            # For buying, we want to pay less
            if spread_category == SpreadCategory.TIGHT:
                # Tight spread - can be aggressive, use best ask
                price = best_ask
            elif spread_category == SpreadCategory.NORMAL:
                # Normal spread - use weighted mid (slightly better than mid)
                price = weighted_mid
            else:
                # Wide/Very wide - use mid price for better fill chance
                price = mid_price
        else:  # SELL
            # For selling, we want to receive more
            if spread_category == SpreadCategory.TIGHT:
                # Tight spread - can be aggressive, use best bid
                price = best_bid
            elif spread_category == SpreadCategory.NORMAL:
                # Normal spread - use weighted mid
                price = weighted_mid
            else:
                # Wide/Very wide - use mid price for better fill chance
                price = mid_price

        # Round to 2 decimal places for options/futures
        return Decimal(str(round(price, 2)))


# Convenience function for quick analysis
def analyze_spread(
    depth_data: Dict,
    last_price: float,
    quantity: int,
    side: str,
    max_spread_pct: float = 0.5,
    min_liquidity_score: int = 50
) -> Dict:
    """
    Quick spread analysis function.

    Args:
        depth_data: Market depth dict
        last_price: Last traded price
        quantity: Order quantity
        side: 'BUY' or 'SELL'
        max_spread_pct: Maximum acceptable spread percentage
        min_liquidity_score: Minimum acceptable liquidity score

    Returns:
        Dictionary with analysis results
    """
    settings = StrategySettings(
        max_order_spread_pct=max_spread_pct,
        min_liquidity_score=min_liquidity_score
    )

    analyzer = SpreadAnalyzer()
    result = analyzer.analyze_spread(
        depth_data=depth_data,
        last_price=last_price,
        quantity=quantity,
        side=side,
        strategy_settings=settings
    )

    return result.to_dict()
