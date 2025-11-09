"""
Execution Decision Engine

Central engine for order execution decisions that integrates:
- Spread analysis (SpreadAnalyzer)
- Market impact calculation (MarketImpactCalculator)
- SDK exceptions (WideSpreadException, HighMarketImpactException, etc.)

Makes final execution decisions and raises appropriate exceptions.

Usage:
    engine = ExecutionDecisionEngine()

    try:
        decision = engine.evaluate_order(
            depth_data=tick['depth'],
            quantity=500,
            side='BUY',
            last_price=tick['last_price'],
            strategy_settings=settings
        )
        # Proceed with order execution
    except WideSpreadException as e:
        # Handle wide spread
        print(f"Wide spread: {e.spread_pct}%, use limit: {e.recommended_limit_price}")
    except HighMarketImpactException as e:
        # Handle high impact
        print(f"High impact: {e.impact_bps} bps, recommended: {e.recommended_action}")
"""

from __future__ import annotations

import logging
from typing import Dict, Optional, List
from dataclasses import dataclass
from decimal import Decimal

from .spread_analyzer import SpreadAnalyzer, SpreadAnalysisResult, StrategySettings
from .market_impact_calculator import MarketImpactCalculator, MarketImpactResult
from ..sdk.exceptions import (
    WideSpreadException,
    HighMarketImpactException,
    InsufficientLiquidityException
)

logger = logging.getLogger(__name__)


@dataclass
class ExecutionDecision:
    """
    Final execution decision with all analysis.

    Attributes:
        can_execute: Whether order can be executed
        requires_user_approval: Whether user approval is needed
        recommended_order_type: MARKET, LIMIT, ICEBERG, TWAP
        recommended_limit_price: Suggested limit price (if applicable)
        spread_analysis: Complete spread analysis
        impact_analysis: Complete market impact analysis
        warnings: Consolidated list of warnings
        action_summary: Human-readable action summary
    """
    can_execute: bool
    requires_user_approval: bool
    recommended_order_type: str
    recommended_limit_price: Optional[Decimal]
    spread_analysis: SpreadAnalysisResult
    impact_analysis: MarketImpactResult
    warnings: List[str]
    action_summary: str

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "can_execute": self.can_execute,
            "requires_user_approval": self.requires_user_approval,
            "recommended_order_type": self.recommended_order_type,
            "recommended_limit_price": float(self.recommended_limit_price) if self.recommended_limit_price else None,
            "spread_analysis": self.spread_analysis.to_dict(),
            "impact_analysis": self.impact_analysis.to_dict(),
            "warnings": self.warnings,
            "action_summary": self.action_summary
        }


class ExecutionDecisionEngine:
    """
    Central decision engine for order execution.

    Evaluates orders against spread and market impact thresholds,
    and raises appropriate SDK exceptions when limits are exceeded.
    """

    def __init__(
        self,
        spread_analyzer: Optional[SpreadAnalyzer] = None,
        impact_calculator: Optional[MarketImpactCalculator] = None
    ):
        """
        Initialize decision engine.

        Args:
            spread_analyzer: Optional existing analyzer
            impact_calculator: Optional existing calculator
        """
        self.spread_analyzer = spread_analyzer or SpreadAnalyzer()
        self.impact_calculator = impact_calculator or MarketImpactCalculator()

    def evaluate_order(
        self,
        depth_data: Dict,
        quantity: int,
        side: str,  # 'BUY' or 'SELL'
        last_price: float,
        strategy_settings: Optional[StrategySettings] = None,
        instrument_token: Optional[int] = None,
        raise_exceptions: bool = True
    ) -> ExecutionDecision:
        """
        Evaluate order and make execution decision.

        Args:
            depth_data: Market depth dict
            quantity: Order quantity
            side: 'BUY' or 'SELL'
            last_price: Last traded price
            strategy_settings: Optional strategy-specific settings
            instrument_token: Optional instrument identifier
            raise_exceptions: Whether to raise SDK exceptions (default: True)

        Returns:
            ExecutionDecision with recommendations

        Raises:
            WideSpreadException: If spread exceeds thresholds
            HighMarketImpactException: If market impact exceeds thresholds
            InsufficientLiquidityException: If insufficient depth
        """
        settings = strategy_settings or StrategySettings()

        # Run spread analysis
        spread_result = self.spread_analyzer.analyze_spread(
            depth_data=depth_data,
            last_price=last_price,
            quantity=quantity,
            side=side,
            strategy_settings=settings,
            instrument_token=instrument_token
        )

        # Run market impact analysis
        impact_result = self.impact_calculator.calculate_impact(
            depth_data=depth_data,
            quantity=quantity,
            side=side,
            last_price=last_price,
            instrument_token=instrument_token
        )

        # Check for critical failures and raise exceptions if enabled
        if raise_exceptions:
            self._check_and_raise_exceptions(
                spread_result=spread_result,
                impact_result=impact_result,
                settings=settings
            )

        # Make execution decision
        decision = self._make_decision(
            spread_result=spread_result,
            impact_result=impact_result,
            settings=settings
        )

        return decision

    def _check_and_raise_exceptions(
        self,
        spread_result: SpreadAnalysisResult,
        impact_result: MarketImpactResult,
        settings: StrategySettings
    ):
        """
        Check thresholds and raise appropriate SDK exceptions.

        Raises exceptions in priority order:
        1. InsufficientLiquidityException (cannot fill)
        2. HighMarketImpactException (excessive impact)
        3. WideSpreadException (wide spread)
        """
        # Priority 1: Insufficient liquidity (cannot fill)
        if not impact_result.can_fill_completely:
            raise InsufficientLiquidityException(
                message=f"Insufficient liquidity to fill order of {impact_result.quantity} lots. "
                        f"Only {impact_result.quantity - impact_result.unfilled_quantity} lots available.",
                requested_quantity=impact_result.quantity,
                available_quantity=impact_result.quantity - impact_result.unfilled_quantity,
                liquidity_tier=spread_result.market_depth_analysis.liquidity.liquidity_tier
            )

        # Priority 2: High market impact
        if impact_result.impact_bps > settings.max_market_impact_bps:
            # Determine recommended action based on impact level
            if impact_result.impact_bps > settings.max_market_impact_bps * 2:
                recommended_action = "USE_TWAP"
            elif impact_result.impact_bps > settings.max_market_impact_bps * 1.5:
                recommended_action = "SPLIT_ORDER"
            else:
                recommended_action = "USE_LIMIT_ORDER"

            raise HighMarketImpactException(
                message=f"Market impact {impact_result.impact_bps} bps exceeds threshold "
                        f"{settings.max_market_impact_bps} bps. Estimated cost: ₹{impact_result.impact_cost:.2f}",
                impact_bps=impact_result.impact_bps,
                impact_cost=impact_result.impact_cost,
                threshold_bps=settings.max_market_impact_bps,
                levels_consumed=impact_result.levels_consumed,
                recommended_action=recommended_action
            )

        # Priority 3: Wide spread
        if spread_result.spread_pct > settings.max_order_spread_pct:
            raise WideSpreadException(
                message=f"Bid-ask spread {spread_result.spread_pct:.2f}% exceeds threshold "
                        f"{settings.max_order_spread_pct:.2f}%. "
                        f"Potential slippage cost: ₹{spread_result.spread_abs * impact_result.quantity:.2f}",
                spread_pct=spread_result.spread_pct,
                spread_abs=spread_result.spread_abs,
                threshold=settings.max_order_spread_pct,
                recommended_action=spread_result.recommended_action.value,
                recommended_limit_price=spread_result.recommended_limit_price
            )

    def _make_decision(
        self,
        spread_result: SpreadAnalysisResult,
        impact_result: MarketImpactResult,
        settings: StrategySettings
    ) -> ExecutionDecision:
        """
        Make final execution decision based on spread and impact analysis.

        Decision logic:
        1. Cannot execute if: rejected by spread OR cannot fill
        2. Requires approval if: spread alert OR high impact + require_approval setting
        3. Order type: Use most conservative recommendation from spread/impact
        """
        # Determine if we can execute
        can_execute = not (
            spread_result.should_reject or
            not impact_result.can_fill_completely
        )

        # Determine if user approval is needed
        requires_approval = False
        if can_execute:
            requires_approval = (
                (spread_result.should_alert and settings.require_user_approval_high_impact) or
                (impact_result.impact_bps > settings.max_market_impact_bps and settings.require_user_approval_high_impact)
            )

        # Determine order type (use most conservative)
        recommended_order_type = self._determine_order_type(
            spread_action=spread_result.recommended_action.value,
            impact_strategy=impact_result.recommended_strategy.value
        )

        # Use spread analyzer's limit price (it's already optimized)
        recommended_limit_price = spread_result.recommended_limit_price

        # Consolidate warnings
        warnings = list(set(spread_result.warnings + impact_result.warnings))

        # Generate action summary
        action_summary = self._generate_action_summary(
            can_execute=can_execute,
            requires_approval=requires_approval,
            order_type=recommended_order_type,
            spread_result=spread_result,
            impact_result=impact_result
        )

        return ExecutionDecision(
            can_execute=can_execute,
            requires_user_approval=requires_approval,
            recommended_order_type=recommended_order_type,
            recommended_limit_price=recommended_limit_price,
            spread_analysis=spread_result,
            impact_analysis=impact_result,
            warnings=warnings,
            action_summary=action_summary
        )

    def _determine_order_type(self, spread_action: str, impact_strategy: str) -> str:
        """
        Determine order type from spread and impact recommendations.

        Uses most conservative recommendation.
        """
        # Map actions to order types
        action_priority = {
            "REJECT": 0,
            "REDUCE_QUANTITY": 1,
            "TWAP": 2,
            "SPLIT_ORDER": 3,
            "ALERT_USER": 4,
            "USE_LIMIT_ORDER": 5,
            "LIMIT_ORDER": 5,
            "PROCEED": 6,
            "MARKET_ORDER": 6
        }

        # Get priorities
        spread_priority = action_priority.get(spread_action, 5)
        impact_priority = action_priority.get(impact_strategy, 5)

        # Use lower priority (more conservative)
        if min(spread_priority, impact_priority) <= 2:
            return "TWAP"
        elif min(spread_priority, impact_priority) <= 3:
            return "SPLIT_ORDER"
        elif min(spread_priority, impact_priority) <= 5:
            return "LIMIT"
        else:
            return "MARKET"

    def _generate_action_summary(
        self,
        can_execute: bool,
        requires_approval: bool,
        order_type: str,
        spread_result: SpreadAnalysisResult,
        impact_result: MarketImpactResult
    ) -> str:
        """Generate human-readable action summary."""
        if not can_execute:
            if not impact_result.can_fill_completely:
                return (
                    f"REJECT: Insufficient liquidity. Only {impact_result.quantity - impact_result.unfilled_quantity} "
                    f"of {impact_result.quantity} lots available. Reduce order size or wait for better liquidity."
                )
            else:
                return (
                    f"REJECT: Spread {spread_result.spread_pct:.2f}% or impact {impact_result.impact_bps} bps "
                    f"exceeds safety thresholds. Review market conditions before proceeding."
                )

        if requires_approval:
            return (
                f"ALERT: User approval required. Spread: {spread_result.spread_pct:.2f}%, "
                f"Impact: {impact_result.impact_bps} bps, Estimated cost: ₹{impact_result.impact_cost:.2f}. "
                f"Recommended: Use {order_type} order at ₹{spread_result.recommended_limit_price}."
            )

        # Can execute without approval
        if order_type == "MARKET":
            return (
                f"PROCEED: Execute market order. Low spread ({spread_result.spread_pct:.2f}%), "
                f"low impact ({impact_result.impact_bps} bps). Expected fill: ₹{impact_result.estimated_fill_price:.2f}."
            )
        elif order_type == "LIMIT":
            return (
                f"PROCEED: Use limit order at ₹{spread_result.recommended_limit_price}. "
                f"Spread: {spread_result.spread_pct:.2f}%, Impact: {impact_result.impact_bps} bps."
            )
        elif order_type == "SPLIT_ORDER":
            return (
                f"PROCEED: Split order into smaller chunks. High impact ({impact_result.impact_bps} bps) "
                f"if executed as single order. Use limit orders for each chunk."
            )
        else:  # TWAP
            return (
                f"PROCEED: Use TWAP strategy over 15-30 minutes. Very high impact ({impact_result.impact_bps} bps) "
                f"if executed immediately. Estimated savings: ₹{impact_result.impact_cost * 0.3:.2f}."
            )


# Convenience function for quick evaluation
def evaluate_order_execution(
    depth_data: Dict,
    quantity: int,
    side: str,
    last_price: float,
    max_spread_pct: float = 0.5,
    max_impact_bps: int = 50,
    raise_exceptions: bool = False
) -> Dict:
    """
    Quick order evaluation function.

    Args:
        depth_data: Market depth dict
        quantity: Order quantity
        side: 'BUY' or 'SELL'
        last_price: Last traded price
        max_spread_pct: Maximum acceptable spread
        max_impact_bps: Maximum acceptable impact
        raise_exceptions: Whether to raise SDK exceptions

    Returns:
        Dictionary with execution decision
    """
    settings = StrategySettings(
        max_order_spread_pct=max_spread_pct,
        max_market_impact_bps=max_impact_bps
    )

    engine = ExecutionDecisionEngine()
    decision = engine.evaluate_order(
        depth_data=depth_data,
        quantity=quantity,
        side=side,
        last_price=last_price,
        strategy_settings=settings,
        raise_exceptions=raise_exceptions
    )

    return decision.to_dict()
