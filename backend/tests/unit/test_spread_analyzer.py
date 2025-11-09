"""
Tests for Spread Analyzer

Verify spread categorization, execution recommendations, and warning generation.
"""

import pytest
from decimal import Decimal

from app.services.spread_analyzer import (
    SpreadAnalyzer,
    SpreadCategory,
    ExecutionAction,
    StrategySettings,
    analyze_spread
)


class TestSpreadAnalyzer:
    """Test spread analysis functionality."""

    @pytest.fixture
    def tight_spread_depth(self):
        """Market depth with tight spread (< 0.2%)."""
        return {
            "buy": [
                {"price": 100.00, "quantity": 500, "orders": 10},
                {"price": 99.90, "quantity": 300, "orders": 8},
                {"price": 99.80, "quantity": 200, "orders": 5},
                {"price": 99.70, "quantity": 150, "orders": 4},
                {"price": 99.60, "quantity": 100, "orders": 3},
            ],
            "sell": [
                {"price": 100.10, "quantity": 450, "orders": 9},
                {"price": 100.20, "quantity": 280, "orders": 7},
                {"price": 100.30, "quantity": 190, "orders": 6},
                {"price": 100.40, "quantity": 140, "orders": 4},
                {"price": 100.50, "quantity": 90, "orders": 2},
            ]
        }

    @pytest.fixture
    def normal_spread_depth(self):
        """Market depth with normal spread (0.2% - 0.5%)."""
        return {
            "buy": [
                {"price": 100.00, "quantity": 300, "orders": 8},
                {"price": 99.80, "quantity": 200, "orders": 6},
                {"price": 99.60, "quantity": 150, "orders": 4},
                {"price": 99.40, "quantity": 100, "orders": 3},
                {"price": 99.20, "quantity": 80, "orders": 2},
            ],
            "sell": [
                {"price": 100.40, "quantity": 280, "orders": 7},
                {"price": 100.60, "quantity": 180, "orders": 5},
                {"price": 100.80, "quantity": 130, "orders": 4},
                {"price": 101.00, "quantity": 90, "orders": 3},
                {"price": 101.20, "quantity": 70, "orders": 2},
            ]
        }

    @pytest.fixture
    def wide_spread_depth(self):
        """Market depth with wide spread (0.5% - 1.0%) but reasonable liquidity."""
        return {
            "buy": [
                {"price": 100.00, "quantity": 400, "orders": 15},
                {"price": 99.50, "quantity": 300, "orders": 12},
                {"price": 99.00, "quantity": 250, "orders": 10},
                {"price": 98.50, "quantity": 200, "orders": 8},
                {"price": 98.00, "quantity": 150, "orders": 6},
            ],
            "sell": [
                {"price": 100.80, "quantity": 380, "orders": 14},
                {"price": 101.30, "quantity": 280, "orders": 11},
                {"price": 101.80, "quantity": 230, "orders": 9},
                {"price": 102.30, "quantity": 180, "orders": 7},
                {"price": 102.80, "quantity": 130, "orders": 5},
            ]
        }

    @pytest.fixture
    def very_wide_spread_depth(self):
        """Market depth with very wide spread (> 1.0%)."""
        return {
            "buy": [
                {"price": 100.00, "quantity": 80, "orders": 3},
                {"price": 99.00, "quantity": 60, "orders": 2},
                {"price": 98.00, "quantity": 50, "orders": 2},
                {"price": 97.00, "quantity": 40, "orders": 1},
                {"price": 96.00, "quantity": 30, "orders": 1},
            ],
            "sell": [
                {"price": 101.50, "quantity": 75, "orders": 2},
                {"price": 102.50, "quantity": 55, "orders": 2},
                {"price": 103.50, "quantity": 45, "orders": 1},
                {"price": 104.50, "quantity": 35, "orders": 1},
                {"price": 105.50, "quantity": 25, "orders": 1},
            ]
        }

    def test_tight_spread_categorization(self, tight_spread_depth):
        """Test that tight spreads are categorized correctly."""
        analyzer = SpreadAnalyzer()
        result = analyzer.analyze_spread(
            depth_data=tight_spread_depth,
            last_price=100.05,
            quantity=100,
            side="BUY"
        )

        assert result.spread_category == SpreadCategory.TIGHT
        assert result.spread_pct < 0.2
        assert not result.should_reject
        assert result.recommended_action == ExecutionAction.PROCEED

    def test_normal_spread_categorization(self, normal_spread_depth):
        """Test that normal spreads are categorized correctly."""
        analyzer = SpreadAnalyzer()
        result = analyzer.analyze_spread(
            depth_data=normal_spread_depth,
            last_price=100.20,
            quantity=100,
            side="BUY"
        )

        assert result.spread_category == SpreadCategory.NORMAL
        assert 0.2 <= result.spread_pct < 0.5
        assert not result.should_reject

    def test_wide_spread_categorization(self, wide_spread_depth):
        """Test that wide spreads are categorized correctly."""
        analyzer = SpreadAnalyzer()
        result = analyzer.analyze_spread(
            depth_data=wide_spread_depth,
            last_price=100.40,
            quantity=100,
            side="BUY"
        )

        assert result.spread_category == SpreadCategory.WIDE
        assert 0.5 <= result.spread_pct < 1.0
        assert result.should_alert
        assert result.recommended_action in (ExecutionAction.ALERT_USER, ExecutionAction.USE_LIMIT_ORDER)

    def test_very_wide_spread_categorization(self, very_wide_spread_depth):
        """Test that very wide spreads are categorized correctly."""
        analyzer = SpreadAnalyzer()
        result = analyzer.analyze_spread(
            depth_data=very_wide_spread_depth,
            last_price=100.75,
            quantity=100,
            side="BUY"
        )

        assert result.spread_category == SpreadCategory.VERY_WIDE
        assert result.spread_pct >= 1.0
        assert result.should_alert
        assert result.should_reject
        assert result.recommended_action == ExecutionAction.REJECT

    def test_strategy_settings_override(self, normal_spread_depth):
        """Test that strategy settings override defaults."""
        analyzer = SpreadAnalyzer()

        # Strict settings (reject normal spreads)
        strict_settings = StrategySettings(
            max_order_spread_pct=0.2,
            min_liquidity_score=80,
            require_user_approval_high_impact=True
        )

        result = analyzer.analyze_spread(
            depth_data=normal_spread_depth,
            last_price=100.20,
            quantity=100,
            side="BUY",
            strategy_settings=strict_settings
        )

        # Normal spread (0.4%) should trigger alert with strict settings (0.2% max)
        assert result.should_alert

    def test_limit_price_recommendation_buy(self, tight_spread_depth):
        """Test limit price calculation for BUY orders."""
        analyzer = SpreadAnalyzer()
        result = analyzer.analyze_spread(
            depth_data=tight_spread_depth,
            last_price=100.05,
            quantity=100,
            side="BUY"
        )

        # For tight spreads on BUY, should recommend near best ask
        assert result.recommended_limit_price is not None
        assert result.recommended_limit_price >= Decimal("100.00")
        assert result.recommended_limit_price <= Decimal("100.10")

    def test_limit_price_recommendation_sell(self, tight_spread_depth):
        """Test limit price calculation for SELL orders."""
        analyzer = SpreadAnalyzer()
        result = analyzer.analyze_spread(
            depth_data=tight_spread_depth,
            last_price=100.05,
            quantity=100,
            side="SELL"
        )

        # For tight spreads on SELL, should recommend near best bid
        assert result.recommended_limit_price is not None
        assert result.recommended_limit_price >= Decimal("100.00")
        assert result.recommended_limit_price <= Decimal("100.10")

    def test_warning_generation_wide_spread(self, wide_spread_depth):
        """Test that warnings are generated for wide spreads."""
        analyzer = SpreadAnalyzer()
        result = analyzer.analyze_spread(
            depth_data=wide_spread_depth,
            last_price=100.40,
            quantity=100,
            side="BUY"
        )

        assert len(result.warnings) > 0
        # Should have warning about wide spread
        assert any("Wide spread" in w for w in result.warnings)

    def test_warning_generation_low_liquidity(self, very_wide_spread_depth):
        """Test that warnings are generated for low liquidity."""
        analyzer = SpreadAnalyzer()
        result = analyzer.analyze_spread(
            depth_data=very_wide_spread_depth,
            last_price=100.75,
            quantity=100,
            side="BUY",
            strategy_settings=StrategySettings(min_liquidity_score=50)
        )

        assert len(result.warnings) > 0
        # Should have warning about low liquidity
        assert any("liquidity" in w.lower() for w in result.warnings)

    def test_market_depth_analysis_included(self, tight_spread_depth):
        """Test that full market depth analysis is included in result."""
        analyzer = SpreadAnalyzer()
        result = analyzer.analyze_spread(
            depth_data=tight_spread_depth,
            last_price=100.05,
            quantity=100,
            side="BUY"
        )

        # Market depth analysis should be populated
        assert result.market_depth_analysis is not None
        assert result.market_depth_analysis.spread is not None
        assert result.market_depth_analysis.depth is not None
        assert result.market_depth_analysis.liquidity is not None
        assert result.market_depth_analysis.imbalance is not None

    def test_to_dict_serialization(self, tight_spread_depth):
        """Test that result can be serialized to dict."""
        analyzer = SpreadAnalyzer()
        result = analyzer.analyze_spread(
            depth_data=tight_spread_depth,
            last_price=100.05,
            quantity=100,
            side="BUY"
        )

        result_dict = result.to_dict()

        assert isinstance(result_dict, dict)
        assert "spread_pct" in result_dict
        assert "spread_category" in result_dict
        assert "recommended_action" in result_dict
        assert "warnings" in result_dict
        assert "market_depth_analysis" in result_dict

    def test_convenience_function(self, tight_spread_depth):
        """Test convenience function for quick analysis."""
        result_dict = analyze_spread(
            depth_data=tight_spread_depth,
            last_price=100.05,
            quantity=100,
            side="BUY",
            max_spread_pct=0.5,
            min_liquidity_score=50
        )

        assert isinstance(result_dict, dict)
        assert "spread_pct" in result_dict
        assert "recommended_action" in result_dict

    def test_empty_depth_data(self):
        """Test handling of empty depth data."""
        analyzer = SpreadAnalyzer()
        result = analyzer.analyze_spread(
            depth_data={"buy": [], "sell": []},
            last_price=100.00,
            quantity=100,
            side="BUY"
        )

        # Should return ILLIQUID tier
        assert result.market_depth_analysis.liquidity.liquidity_tier == "ILLIQUID"
        assert result.should_reject

    def test_require_user_approval_setting(self, wide_spread_depth):
        """Test require_user_approval_high_impact setting."""
        analyzer = SpreadAnalyzer()

        # With approval required
        settings_with_approval = StrategySettings(
            require_user_approval_high_impact=True
        )
        result1 = analyzer.analyze_spread(
            depth_data=wide_spread_depth,
            last_price=100.40,
            quantity=100,
            side="BUY",
            strategy_settings=settings_with_approval
        )

        # Should alert user for wide spread
        assert result1.recommended_action == ExecutionAction.ALERT_USER

        # Without approval required
        settings_without_approval = StrategySettings(
            require_user_approval_high_impact=False
        )
        result2 = analyzer.analyze_spread(
            depth_data=wide_spread_depth,
            last_price=100.40,
            quantity=100,
            side="BUY",
            strategy_settings=settings_without_approval
        )

        # Should use limit order for wide spread
        assert result2.recommended_action == ExecutionAction.USE_LIMIT_ORDER

    def test_instrument_token_logging(self, tight_spread_depth):
        """Test that instrument_token is passed for logging."""
        analyzer = SpreadAnalyzer()

        # Should not raise error with instrument_token
        result = analyzer.analyze_spread(
            depth_data=tight_spread_depth,
            last_price=100.05,
            quantity=100,
            side="BUY",
            instrument_token=256265
        )

        assert result is not None
        assert result.spread_category == SpreadCategory.TIGHT
