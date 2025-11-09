"""
Tests for Market Impact Calculator

Verify impact calculation, level consumption, and execution strategy recommendations.
"""

import pytest

from app.services.market_impact_calculator import (
    MarketImpactCalculator,
    ImpactLevel,
    ExecutionStrategy,
    calculate_market_impact
)


class TestMarketImpactCalculator:
    """Test market impact calculation functionality."""

    @pytest.fixture
    def deep_liquid_depth(self):
        """Deep, liquid market depth."""
        return {
            "buy": [
                {"price": 100.00, "quantity": 1000, "orders": 20},
                {"price": 99.90, "quantity": 800, "orders": 18},
                {"price": 99.80, "quantity": 600, "orders": 15},
                {"price": 99.70, "quantity": 500, "orders": 12},
                {"price": 99.60, "quantity": 400, "orders": 10},
            ],
            "sell": [
                {"price": 100.10, "quantity": 950, "orders": 19},
                {"price": 100.20, "quantity": 750, "orders": 17},
                {"price": 100.30, "quantity": 550, "orders": 14},
                {"price": 100.40, "quantity": 450, "orders": 11},
                {"price": 100.50, "quantity": 350, "orders": 9},
            ]
        }

    @pytest.fixture
    def moderate_depth(self):
        """Moderate liquidity depth."""
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
    def shallow_depth(self):
        """Shallow, illiquid market depth."""
        return {
            "buy": [
                {"price": 100.00, "quantity": 50, "orders": 3},
                {"price": 99.50, "quantity": 40, "orders": 2},
                {"price": 99.00, "quantity": 30, "orders": 2},
                {"price": 98.50, "quantity": 20, "orders": 1},
                {"price": 98.00, "quantity": 10, "orders": 1},
            ],
            "sell": [
                {"price": 101.00, "quantity": 45, "orders": 3},
                {"price": 101.50, "quantity": 35, "orders": 2},
                {"price": 102.00, "quantity": 25, "orders": 1},
                {"price": 102.50, "quantity": 15, "orders": 1},
                {"price": 103.00, "quantity": 10, "orders": 1},
            ]
        }

    def test_low_impact_small_order(self, deep_liquid_depth):
        """Test low impact for small order in liquid market."""
        calculator = MarketImpactCalculator()
        result = calculator.calculate_impact(
            depth_data=deep_liquid_depth,
            quantity=100,
            side="BUY",
            last_price=100.05
        )

        # Should have low impact (fills within first level)
        assert result.impact_level == ImpactLevel.LOW
        assert result.impact_bps < 10
        assert result.can_fill_completely
        assert result.levels_consumed == 1
        assert result.recommended_strategy == ExecutionStrategy.MARKET_ORDER

    def test_moderate_impact_medium_order(self, moderate_depth):
        """Test moderate impact for medium-sized order."""
        calculator = MarketImpactCalculator()
        result = calculator.calculate_impact(
            depth_data=moderate_depth,
            quantity=400,
            side="BUY",
            last_price=100.20
        )

        # Should have moderate impact (consumes 2-3 levels)
        assert result.impact_level in (ImpactLevel.MODERATE, ImpactLevel.HIGH)
        assert result.can_fill_completely
        assert result.levels_consumed >= 2
        assert result.recommended_strategy in (
            ExecutionStrategy.LIMIT_ORDER,
            ExecutionStrategy.SPLIT_ORDER
        )

    def test_high_impact_large_order(self, moderate_depth):
        """Test high impact for large order."""
        calculator = MarketImpactCalculator()
        result = calculator.calculate_impact(
            depth_data=moderate_depth,
            quantity=800,
            side="BUY",
            last_price=100.20
        )

        # Should have high impact (consumes many levels)
        assert result.impact_level in (ImpactLevel.HIGH, ImpactLevel.VERY_HIGH)
        assert result.levels_consumed >= 3
        assert len(result.warnings) > 0

    def test_very_high_impact_shallow_market(self, shallow_depth):
        """Test very high impact in shallow market."""
        calculator = MarketImpactCalculator()
        result = calculator.calculate_impact(
            depth_data=shallow_depth,
            quantity=100,
            side="BUY",
            last_price=100.50
        )

        # Should have very high impact
        assert result.impact_level in (ImpactLevel.HIGH, ImpactLevel.VERY_HIGH)
        assert result.impact_bps >= 30
        assert result.recommended_strategy in (
            ExecutionStrategy.SPLIT_ORDER,
            ExecutionStrategy.TWAP,
            ExecutionStrategy.REDUCE_QUANTITY
        )

    def test_buy_side_consumes_sell_levels(self, deep_liquid_depth):
        """Test that BUY orders consume sell side depth."""
        calculator = MarketImpactCalculator()
        result = calculator.calculate_impact(
            depth_data=deep_liquid_depth,
            quantity=500,
            side="BUY",
            last_price=100.05
        )

        # Fill price should be >= best ask (100.10)
        assert result.estimated_fill_price >= 100.10
        # Mid price should be around 100.05
        assert 100.00 <= result.mid_price <= 100.10
        # Slippage should be positive (paying more than mid)
        assert result.slippage_abs > 0

    def test_sell_side_consumes_buy_levels(self, deep_liquid_depth):
        """Test that SELL orders consume buy side depth."""
        calculator = MarketImpactCalculator()
        result = calculator.calculate_impact(
            depth_data=deep_liquid_depth,
            quantity=500,
            side="SELL",
            last_price=100.05
        )

        # Fill price should be <= best bid (100.00)
        assert result.estimated_fill_price <= 100.00
        # Mid price should be around 100.05
        assert 100.00 <= result.mid_price <= 100.10
        # Slippage should be positive (receiving less than mid)
        assert result.slippage_abs > 0

    def test_insufficient_depth_warning(self, shallow_depth):
        """Test warning when depth is insufficient."""
        calculator = MarketImpactCalculator()
        result = calculator.calculate_impact(
            depth_data=shallow_depth,
            quantity=200,
            side="BUY",
            last_price=100.50
        )

        # Should not be able to fill completely
        assert not result.can_fill_completely
        assert result.unfilled_quantity > 0
        # Should have warning about insufficient depth
        assert any("Insufficient depth" in w for w in result.warnings)
        # Should recommend reducing quantity
        assert result.recommended_strategy == ExecutionStrategy.REDUCE_QUANTITY

    def test_many_levels_consumed_warning(self, moderate_depth):
        """Test warning when many levels are consumed."""
        calculator = MarketImpactCalculator()
        result = calculator.calculate_impact(
            depth_data=moderate_depth,
            quantity=700,
            side="BUY",
            last_price=100.20
        )

        # Should consume 3+ levels
        assert result.levels_consumed >= 3
        # Should have warning about levels consumed
        assert any("levels" in w.lower() for w in result.warnings)

    def test_impact_cost_calculation(self, deep_liquid_depth):
        """Test that impact cost is calculated correctly."""
        calculator = MarketImpactCalculator()
        result = calculator.calculate_impact(
            depth_data=deep_liquid_depth,
            quantity=500,
            side="BUY",
            last_price=100.05
        )

        # Impact cost should be slippage * quantity
        expected_cost = result.slippage_abs * result.quantity
        assert abs(result.impact_cost - expected_cost) < 0.01

    def test_impact_bps_calculation(self, deep_liquid_depth):
        """Test basis points calculation."""
        calculator = MarketImpactCalculator()
        result = calculator.calculate_impact(
            depth_data=deep_liquid_depth,
            quantity=500,
            side="BUY",
            last_price=100.05
        )

        # BPS should be (slippage / mid_price) * 10000
        expected_bps = int((result.slippage_abs / result.mid_price) * 10000)
        assert abs(result.impact_bps - expected_bps) <= 1  # Allow 1 bps rounding

    def test_empty_depth_data(self):
        """Test handling of empty depth data."""
        calculator = MarketImpactCalculator()
        result = calculator.calculate_impact(
            depth_data={"buy": [], "sell": []},
            quantity=100,
            side="BUY",
            last_price=100.00
        )

        # Should return empty result with warnings
        assert not result.can_fill_completely
        assert result.unfilled_quantity == 100
        assert result.impact_level == ImpactLevel.VERY_HIGH
        assert len(result.warnings) > 0

    def test_to_dict_serialization(self, deep_liquid_depth):
        """Test that result can be serialized to dict."""
        calculator = MarketImpactCalculator()
        result = calculator.calculate_impact(
            depth_data=deep_liquid_depth,
            quantity=100,
            side="BUY",
            last_price=100.05
        )

        result_dict = result.to_dict()

        assert isinstance(result_dict, dict)
        assert "quantity" in result_dict
        assert "estimated_fill_price" in result_dict
        assert "impact_bps" in result_dict
        assert "impact_level" in result_dict
        assert "recommended_strategy" in result_dict
        assert "warnings" in result_dict

    def test_convenience_function(self, deep_liquid_depth):
        """Test convenience function for quick calculation."""
        result_dict = calculate_market_impact(
            depth_data=deep_liquid_depth,
            quantity=100,
            side="BUY",
            last_price=100.05
        )

        assert isinstance(result_dict, dict)
        assert "impact_bps" in result_dict
        assert "recommended_strategy" in result_dict

    def test_single_level_fill(self, deep_liquid_depth):
        """Test order that fills within first level."""
        calculator = MarketImpactCalculator()
        result = calculator.calculate_impact(
            depth_data=deep_liquid_depth,
            quantity=50,
            side="BUY",
            last_price=100.05
        )

        # Should fill completely within first level
        assert result.levels_consumed == 1
        assert result.can_fill_completely
        assert result.unfilled_quantity == 0

    def test_multi_level_fill(self, moderate_depth):
        """Test order that requires multiple levels."""
        calculator = MarketImpactCalculator()
        result = calculator.calculate_impact(
            depth_data=moderate_depth,
            quantity=500,
            side="BUY",
            last_price=100.20
        )

        # Should consume multiple levels
        assert result.levels_consumed > 1
        assert result.levels_consumed <= 5

    def test_instrument_token_logging(self, deep_liquid_depth):
        """Test that instrument_token is passed for logging."""
        calculator = MarketImpactCalculator()

        # Should not raise error with instrument_token
        result = calculator.calculate_impact(
            depth_data=deep_liquid_depth,
            quantity=100,
            side="BUY",
            last_price=100.05,
            instrument_token=256265
        )

        assert result is not None
        assert result.can_fill_completely

    def test_slippage_percentage_calculation(self, deep_liquid_depth):
        """Test slippage percentage is calculated correctly."""
        calculator = MarketImpactCalculator()
        result = calculator.calculate_impact(
            depth_data=deep_liquid_depth,
            quantity=500,
            side="BUY",
            last_price=100.05
        )

        # Slippage % should be (slippage_abs / mid_price) * 100
        expected_pct = (result.slippage_abs / result.mid_price) * 100
        assert abs(result.slippage_pct - expected_pct) < 0.01

    def test_zero_quantity(self, deep_liquid_depth):
        """Test handling of zero quantity order."""
        calculator = MarketImpactCalculator()
        result = calculator.calculate_impact(
            depth_data=deep_liquid_depth,
            quantity=0,
            side="BUY",
            last_price=100.05
        )

        # Should handle gracefully
        assert result.quantity == 0
        assert result.impact_cost == 0.0
        assert result.levels_consumed == 0
