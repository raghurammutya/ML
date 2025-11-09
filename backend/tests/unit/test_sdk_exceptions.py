"""
Tests for SDK exceptions

Verify that all exception classes work correctly with proper attributes.
"""

import pytest
from datetime import datetime, timedelta
from decimal import Decimal

from app.sdk.exceptions import (
    SDKException,
    WideSpreadException,
    HighMarketImpactException,
    InsufficientLiquidityException,
    MarginShortfallException,
    MarginIncreasedException,
    RiskLimitBreachException,
    GreeksRiskException,
    OrphanedOrdersDetectedException,
    DuplicateOrderException,
    PositionSizeExceedsRecommendationException,
)


class TestSDKExceptions:
    """Test SDK exception hierarchy."""

    def test_base_sdk_exception(self):
        """Test base SDKException."""
        exc = SDKException(
            message="Test error",
            code="TEST_ERROR",
            details={'key': 'value'}
        )

        assert exc.message == "Test error"
        assert exc.code == "TEST_ERROR"
        assert exc.details == {'key': 'value'}
        assert str(exc) == "Test error"

    def test_sdk_exception_to_dict(self):
        """Test exception serialization to dict."""
        exc = SDKException("Test error", code="TEST")

        result = exc.to_dict()

        assert result['error'] == 'SDKException'
        assert result['code'] == 'TEST'
        assert result['message'] == 'Test error'
        assert 'details' in result

    def test_wide_spread_exception(self):
        """Test WideSpreadException with all attributes."""
        exc = WideSpreadException(
            message="Spread too wide",
            spread_pct=0.8,
            spread_abs=4.0,
            threshold=0.5,
            recommended_action="USE_LIMIT_ORDER",
            recommended_limit_price=Decimal('150.25')
        )

        assert exc.spread_pct == 0.8
        assert exc.spread_abs == 4.0
        assert exc.threshold == 0.5
        assert exc.recommended_action == "USE_LIMIT_ORDER"
        assert exc.recommended_limit_price == Decimal('150.25')
        assert exc.code == "WIDE_SPREAD"
        assert exc.details['spread_pct'] == 0.8

    def test_high_market_impact_exception(self):
        """Test HighMarketImpactException."""
        exc = HighMarketImpactException(
            message="High market impact",
            impact_bps=75,
            impact_cost=450.0,
            threshold_bps=50,
            levels_consumed=6,
            recommended_action="USE_TWAP"
        )

        assert exc.impact_bps == 75
        assert exc.impact_cost == 450.0
        assert exc.threshold_bps == 50
        assert exc.levels_consumed == 6
        assert exc.recommended_action == "USE_TWAP"
        assert exc.code == "HIGH_MARKET_IMPACT"

    def test_insufficient_liquidity_exception(self):
        """Test InsufficientLiquidityException."""
        exc = InsufficientLiquidityException(
            message="Insufficient liquidity",
            requested_quantity=1000,
            available_quantity=250,
            liquidity_tier="LOW"
        )

        assert exc.requested_quantity == 1000
        assert exc.available_quantity == 250
        assert exc.liquidity_tier == "LOW"
        assert exc.code == "INSUFFICIENT_LIQUIDITY"

    def test_margin_shortfall_exception(self):
        """Test MarginShortfallException with deadline."""
        deadline = datetime.now() + timedelta(hours=1)
        exc = MarginShortfallException(
            message="Margin shortfall",
            required_margin=55000.0,
            available_margin=50000.0,
            shortfall=5000.0,
            deadline=deadline
        )

        assert exc.required_margin == 55000.0
        assert exc.available_margin == 50000.0
        assert exc.shortfall == 5000.0
        assert exc.deadline == deadline
        assert exc.code == "MARGIN_SHORTFALL"
        assert exc.details['deadline'] == deadline.isoformat()

    def test_margin_increased_exception(self):
        """Test MarginIncreasedException."""
        exc = MarginIncreasedException(
            message="Margin increased",
            old_margin=45000.0,
            new_margin=58500.0,
            change_pct=30.0,
            reason="VIX_INCREASE"
        )

        assert exc.old_margin == 45000.0
        assert exc.new_margin == 58500.0
        assert exc.change_pct == 30.0
        assert exc.reason == "VIX_INCREASE"
        assert exc.code == "MARGIN_INCREASED"

    def test_risk_limit_breach_exception(self):
        """Test RiskLimitBreachException."""
        exc = RiskLimitBreachException(
            message="Loss limit breached",
            limit_type="MAX_LOSS_PCT",
            current_value=12.5,
            limit_value=10.0,
            action_taken="STOP_NEW_ORDERS"
        )

        assert exc.limit_type == "MAX_LOSS_PCT"
        assert exc.current_value == 12.5
        assert exc.limit_value == 10.0
        assert exc.action_taken == "STOP_NEW_ORDERS"
        assert exc.code == "RISK_LIMIT_BREACH"

    def test_greeks_risk_exception(self):
        """Test GreeksRiskException with all Greeks."""
        exc = GreeksRiskException(
            message="High Greeks risk",
            delta_risk="HIGH",
            gamma_risk="MEDIUM",
            vega_risk="LOW",
            net_delta=0.45,
            net_gamma=0.035,
            net_vega=850.0,
            recommendations=["Add opposite delta position", "Reduce gamma exposure"]
        )

        assert exc.delta_risk == "HIGH"
        assert exc.gamma_risk == "MEDIUM"
        assert exc.vega_risk == "LOW"
        assert exc.net_delta == 0.45
        assert exc.net_gamma == 0.035
        assert exc.net_vega == 850.0
        assert len(exc.recommendations) == 2
        assert exc.code == "GREEKS_RISK"

    def test_orphaned_orders_detected_exception(self):
        """Test OrphanedOrdersDetectedException."""
        exc = OrphanedOrdersDetectedException(
            message="Orphaned orders found",
            orphaned_orders=[12345, 12346, 12347],
            reason="POSITION_CLOSED",
            auto_cleanup_enabled=True
        )

        assert len(exc.orphaned_orders) == 3
        assert exc.orphaned_orders[0] == 12345
        assert exc.reason == "POSITION_CLOSED"
        assert exc.auto_cleanup_enabled is True
        assert exc.code == "ORPHANED_ORDERS"

    def test_duplicate_order_exception(self):
        """Test DuplicateOrderException."""
        exc = DuplicateOrderException(
            message="Duplicate order",
            original_order_id=99999,
            reason="IDENTICAL_ORDER_WITHIN_5_SEC"
        )

        assert exc.original_order_id == 99999
        assert exc.reason == "IDENTICAL_ORDER_WITHIN_5_SEC"
        assert exc.code == "DUPLICATE_ORDER"

    def test_position_size_exceeds_recommendation_exception(self):
        """Test PositionSizeExceedsRecommendationException."""
        exc = PositionSizeExceedsRecommendationException(
            message="Position size too large",
            requested_quantity=500,
            recommended_quantity=200,
            liquidity_tier="LOW"
        )

        assert exc.requested_quantity == 500
        assert exc.recommended_quantity == 200
        assert exc.liquidity_tier == "LOW"
        assert exc.code == "POSITION_SIZE_EXCEEDS_REC"

    def test_exception_inheritance(self):
        """Test that exceptions inherit correctly."""
        assert issubclass(WideSpreadException, SDKException)
        assert issubclass(MarginShortfallException, SDKException)
        assert issubclass(RiskLimitBreachException, SDKException)

    def test_exception_can_be_raised_and_caught(self):
        """Test that exceptions can be raised and caught."""
        with pytest.raises(WideSpreadException) as exc_info:
            raise WideSpreadException(
                message="Test",
                spread_pct=1.0,
                spread_abs=5.0,
                threshold=0.5,
                recommended_action="CANCEL"
            )

        assert exc_info.value.spread_pct == 1.0
        assert exc_info.value.code == "WIDE_SPREAD"
