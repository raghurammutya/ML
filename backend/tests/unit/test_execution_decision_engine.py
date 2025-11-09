"""
Tests for Execution Decision Engine

Verify integration of spread analysis, market impact, and SDK exceptions.
"""

import pytest

from app.services.execution_decision_engine import (
    ExecutionDecisionEngine,
    StrategySettings,
    evaluate_order_execution
)
from app.sdk.exceptions import (
    WideSpreadException,
    HighMarketImpactException,
    InsufficientLiquidityException
)


class TestExecutionDecisionEngine:
    """Test execution decision engine functionality."""

    @pytest.fixture
    def excellent_depth(self):
        """Excellent market conditions - tight spread, deep liquidity."""
        return {
            "buy": [
                {"price": 100.00, "quantity": 1000, "orders": 25},
                {"price": 99.95, "quantity": 900, "orders": 22},
                {"price": 99.90, "quantity": 800, "orders": 20},
                {"price": 99.85, "quantity": 700, "orders": 18},
                {"price": 99.80, "quantity": 600, "orders": 15},
            ],
            "sell": [
                {"price": 100.05, "quantity": 980, "orders": 24},
                {"price": 100.10, "quantity": 880, "orders": 21},
                {"price": 100.15, "quantity": 780, "orders": 19},
                {"price": 100.20, "quantity": 680, "orders": 17},
                {"price": 100.25, "quantity": 580, "orders": 14},
            ]
        }

    @pytest.fixture
    def moderate_depth(self):
        """Moderate market conditions."""
        return {
            "buy": [
                {"price": 100.00, "quantity": 300, "orders": 10},
                {"price": 99.80, "quantity": 250, "orders": 8},
                {"price": 99.60, "quantity": 200, "orders": 6},
                {"price": 99.40, "quantity": 150, "orders": 5},
                {"price": 99.20, "quantity": 100, "orders": 3},
            ],
            "sell": [
                {"price": 100.40, "quantity": 280, "orders": 9},
                {"price": 100.60, "quantity": 230, "orders": 7},
                {"price": 100.80, "quantity": 180, "orders": 5},
                {"price": 101.00, "quantity": 130, "orders": 4},
                {"price": 101.20, "quantity": 80, "orders": 2},
            ]
        }

    @pytest.fixture
    def poor_depth(self):
        """Poor market conditions - wide spread, thin liquidity."""
        return {
            "buy": [
                {"price": 100.00, "quantity": 50, "orders": 3},
                {"price": 99.00, "quantity": 40, "orders": 2},
                {"price": 98.00, "quantity": 30, "orders": 2},
                {"price": 97.00, "quantity": 20, "orders": 1},
                {"price": 96.00, "quantity": 10, "orders": 1},
            ],
            "sell": [
                {"price": 102.00, "quantity": 45, "orders": 3},
                {"price": 103.00, "quantity": 35, "orders": 2},
                {"price": 104.00, "quantity": 25, "orders": 1},
                {"price": 105.00, "quantity": 15, "orders": 1},
                {"price": 106.00, "quantity": 10, "orders": 1},
            ]
        }

    def test_excellent_conditions_proceed(self, excellent_depth):
        """Test that excellent conditions allow immediate execution."""
        engine = ExecutionDecisionEngine()
        decision = engine.evaluate_order(
            depth_data=excellent_depth,
            quantity=100,
            side="BUY",
            last_price=100.025,
            raise_exceptions=False
        )

        assert decision.can_execute
        assert not decision.requires_user_approval
        assert decision.recommended_order_type in ("MARKET", "LIMIT")
        assert len(decision.warnings) == 0 or all("low" in w.lower() for w in decision.warnings)

    def test_wide_spread_exception_raised(self, moderate_depth):
        """Test that WideSpreadException is raised for wide spreads."""
        engine = ExecutionDecisionEngine()
        settings = StrategySettings(max_order_spread_pct=0.2)  # Very strict

        with pytest.raises(WideSpreadException) as exc_info:
            engine.evaluate_order(
                depth_data=moderate_depth,
                quantity=100,
                side="BUY",
                last_price=100.20,
                strategy_settings=settings,
                raise_exceptions=True
            )

        exc = exc_info.value
        assert exc.spread_pct > 0.2
        assert exc.threshold == 0.2
        assert exc.recommended_limit_price is not None

    def test_high_market_impact_exception_raised(self, moderate_depth):
        """Test that HighMarketImpactException is raised for high impact."""
        engine = ExecutionDecisionEngine()
        settings = StrategySettings(
            max_order_spread_pct=1.0,  # Allow wide spread
            max_market_impact_bps=10   # Very strict impact
        )

        with pytest.raises(HighMarketImpactException) as exc_info:
            engine.evaluate_order(
                depth_data=moderate_depth,
                quantity=800,
                side="BUY",
                last_price=100.20,
                strategy_settings=settings,
                raise_exceptions=True
            )

        exc = exc_info.value
        assert exc.impact_bps > 10
        assert exc.threshold_bps == 10
        assert exc.recommended_action in ("USE_LIMIT_ORDER", "SPLIT_ORDER", "USE_TWAP")

    def test_insufficient_liquidity_exception_raised(self, poor_depth):
        """Test that InsufficientLiquidityException is raised when cannot fill."""
        engine = ExecutionDecisionEngine()

        with pytest.raises(InsufficientLiquidityException) as exc_info:
            engine.evaluate_order(
                depth_data=poor_depth,
                quantity=200,
                side="BUY",
                last_price=101.00,
                raise_exceptions=True
            )

        exc = exc_info.value
        assert exc.requested_quantity == 200
        assert exc.available_quantity < 200
        assert exc.liquidity_tier in ("LOW", "ILLIQUID")

    def test_no_exceptions_when_disabled(self, poor_depth):
        """Test that exceptions are not raised when raise_exceptions=False."""
        engine = ExecutionDecisionEngine()

        # Should not raise exception, even with poor conditions
        decision = engine.evaluate_order(
            depth_data=poor_depth,
            quantity=200,
            side="BUY",
            last_price=101.00,
            raise_exceptions=False
        )

        # But should still indicate cannot execute
        assert not decision.can_execute

    def test_user_approval_required_for_wide_spread(self, moderate_depth):
        """Test that user approval is required for wide spreads."""
        engine = ExecutionDecisionEngine()
        settings = StrategySettings(
            max_order_spread_pct=0.3,
            require_user_approval_high_impact=True
        )

        decision = engine.evaluate_order(
            depth_data=moderate_depth,
            quantity=100,
            side="BUY",
            last_price=100.20,
            strategy_settings=settings,
            raise_exceptions=False
        )

        assert decision.requires_user_approval
        assert "ALERT" in decision.action_summary

    def test_limit_order_recommended_for_moderate_spread(self, moderate_depth):
        """Test that LIMIT order is recommended for moderate conditions."""
        engine = ExecutionDecisionEngine()
        settings = StrategySettings(
            max_order_spread_pct=0.5,  # Allow moderate spread
            require_user_approval_high_impact=False
        )

        decision = engine.evaluate_order(
            depth_data=moderate_depth,
            quantity=200,
            side="BUY",
            last_price=100.20,
            strategy_settings=settings,
            raise_exceptions=False
        )

        assert decision.can_execute
        assert decision.recommended_order_type == "LIMIT"
        assert decision.recommended_limit_price is not None

    def test_twap_recommended_for_very_high_impact(self, moderate_depth):
        """Test that TWAP is recommended for very high impact orders."""
        engine = ExecutionDecisionEngine()
        settings = StrategySettings(
            max_order_spread_pct=1.0,
            max_market_impact_bps=100,  # Allow high impact
            require_user_approval_high_impact=False
        )

        decision = engine.evaluate_order(
            depth_data=moderate_depth,
            quantity=900,
            side="BUY",
            last_price=100.20,
            strategy_settings=settings,
            raise_exceptions=False
        )

        assert decision.recommended_order_type in ("TWAP", "SPLIT_ORDER")

    def test_warnings_consolidated_from_both_analyzers(self, moderate_depth):
        """Test that warnings from both analyzers are consolidated."""
        engine = ExecutionDecisionEngine()
        settings = StrategySettings(
            max_order_spread_pct=0.6,
            max_market_impact_bps=60
        )

        decision = engine.evaluate_order(
            depth_data=moderate_depth,
            quantity=600,
            side="BUY",
            last_price=100.20,
            strategy_settings=settings,
            raise_exceptions=False
        )

        # Should have warnings from both spread and impact analysis
        assert len(decision.warnings) > 0

    def test_action_summary_for_reject(self, poor_depth):
        """Test action summary for rejected orders."""
        engine = ExecutionDecisionEngine()

        decision = engine.evaluate_order(
            depth_data=poor_depth,
            quantity=200,
            side="BUY",
            last_price=101.00,
            raise_exceptions=False
        )

        assert not decision.can_execute
        assert "REJECT" in decision.action_summary
        assert "liquidity" in decision.action_summary.lower()

    def test_action_summary_for_proceed_market(self, excellent_depth):
        """Test action summary for market order execution."""
        engine = ExecutionDecisionEngine()

        decision = engine.evaluate_order(
            depth_data=excellent_depth,
            quantity=100,
            side="BUY",
            last_price=100.025,
            raise_exceptions=False
        )

        if decision.recommended_order_type == "MARKET":
            assert "PROCEED" in decision.action_summary
            assert "market order" in decision.action_summary.lower()

    def test_to_dict_serialization(self, excellent_depth):
        """Test that decision can be serialized to dict."""
        engine = ExecutionDecisionEngine()
        decision = engine.evaluate_order(
            depth_data=excellent_depth,
            quantity=100,
            side="BUY",
            last_price=100.025,
            raise_exceptions=False
        )

        decision_dict = decision.to_dict()

        assert isinstance(decision_dict, dict)
        assert "can_execute" in decision_dict
        assert "requires_user_approval" in decision_dict
        assert "recommended_order_type" in decision_dict
        assert "spread_analysis" in decision_dict
        assert "impact_analysis" in decision_dict
        assert "warnings" in decision_dict
        assert "action_summary" in decision_dict

    def test_convenience_function(self, excellent_depth):
        """Test convenience function for quick evaluation."""
        result_dict = evaluate_order_execution(
            depth_data=excellent_depth,
            quantity=100,
            side="BUY",
            last_price=100.025,
            max_spread_pct=0.5,
            max_impact_bps=50,
            raise_exceptions=False
        )

        assert isinstance(result_dict, dict)
        assert "can_execute" in result_dict
        assert "action_summary" in result_dict

    def test_buy_and_sell_sides(self, excellent_depth):
        """Test that both BUY and SELL orders work correctly."""
        engine = ExecutionDecisionEngine()

        # BUY order
        buy_decision = engine.evaluate_order(
            depth_data=excellent_depth,
            quantity=100,
            side="BUY",
            last_price=100.025,
            raise_exceptions=False
        )
        assert buy_decision.can_execute

        # SELL order
        sell_decision = engine.evaluate_order(
            depth_data=excellent_depth,
            quantity=100,
            side="SELL",
            last_price=100.025,
            raise_exceptions=False
        )
        assert sell_decision.can_execute

    def test_instrument_token_passed_to_analyzers(self, excellent_depth):
        """Test that instrument_token is passed to underlying analyzers."""
        engine = ExecutionDecisionEngine()

        # Should not raise error with instrument_token
        decision = engine.evaluate_order(
            depth_data=excellent_depth,
            quantity=100,
            side="BUY",
            last_price=100.025,
            instrument_token=256265,
            raise_exceptions=False
        )

        assert decision is not None
        assert decision.can_execute

    def test_exception_priority_insufficient_liquidity_first(self, poor_depth):
        """Test that InsufficientLiquidityException has highest priority."""
        engine = ExecutionDecisionEngine()

        # Even with lenient settings, insufficient liquidity should raise first
        settings = StrategySettings(
            max_order_spread_pct=10.0,  # Very lenient
            max_market_impact_bps=1000  # Very lenient
        )

        with pytest.raises(InsufficientLiquidityException):
            engine.evaluate_order(
                depth_data=poor_depth,
                quantity=200,
                side="BUY",
                last_price=101.00,
                strategy_settings=settings,
                raise_exceptions=True
            )

    def test_empty_depth_data(self):
        """Test handling of empty depth data."""
        engine = ExecutionDecisionEngine()

        with pytest.raises(InsufficientLiquidityException):
            engine.evaluate_order(
                depth_data={"buy": [], "sell": []},
                quantity=100,
                side="BUY",
                last_price=100.00,
                raise_exceptions=True
            )
