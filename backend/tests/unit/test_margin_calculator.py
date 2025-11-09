"""
Tests for Margin Calculator

Verify dynamic margin calculations with VIX, expiry, and price movement factors.
"""

import pytest
from datetime import date, timedelta

from app.services.margin_calculator import (
    MarginCalculator,
    calculate_margin
)


class TestMarginCalculator:
    """Test margin calculation functionality."""

    def test_basic_futures_margin(self):
        """Test basic futures margin calculation."""
        calculator = MarginCalculator()
        result = calculator.calculate_margin(
            instrument_token=256265,
            quantity=1,
            side="BUY",
            segment="NFO-FUT",
            underlying_price=24000,
            symbol="NIFTY",
            vix=15.0,
            expiry_date=date.today() + timedelta(days=15)
        )

        # Should have SPAN + exposure margin
        assert result.span_margin > 0
        assert result.exposure_margin > 0
        assert result.premium_margin == 0  # No premium for futures
        assert result.total_margin > 0
        assert result.total_margin == result.span_margin + result.exposure_margin + result.additional_margin

    def test_option_buy_margin(self):
        """Test option buying margin (no premium margin required)."""
        calculator = MarginCalculator()
        result = calculator.calculate_margin(
            instrument_token=256265,
            quantity=2,
            side="BUY",
            segment="NFO-OPT",
            underlying_price=24000,
            symbol="NIFTY",
            strike_price=24000,
            option_type="CE",
            vix=15.0,
            expiry_date=date.today() + timedelta(days=15)
        )

        # Option buying: SPAN + exposure, no premium margin
        assert result.span_margin > 0
        assert result.exposure_margin > 0
        assert result.premium_margin == 0
        assert result.total_margin > 0

    def test_option_sell_margin_with_premium(self):
        """Test option selling margin (includes premium margin)."""
        calculator = MarginCalculator()
        result = calculator.calculate_margin(
            instrument_token=256265,
            quantity=2,
            side="SELL",
            segment="NFO-OPT",
            underlying_price=24000,
            symbol="NIFTY",
            strike_price=24000,
            option_type="CE",
            premium=150.0,
            vix=15.0,
            expiry_date=date.today() + timedelta(days=15)
        )

        # Option selling: SPAN + exposure + premium
        assert result.span_margin > 0
        assert result.exposure_margin > 0
        assert result.premium_margin > 0  # Should have premium margin
        assert result.total_margin > 0

    def test_low_vix_multiplier(self):
        """Test low VIX results in 1.0x multiplier."""
        calculator = MarginCalculator()
        result = calculator.calculate_margin(
            instrument_token=256265,
            quantity=1,
            side="BUY",
            segment="NFO-FUT",
            underlying_price=24000,
            symbol="NIFTY",
            vix=12.0,  # Low VIX
            expiry_date=date.today() + timedelta(days=15)
        )

        assert result.vix_multiplier == 1.0
        assert result.vix == 12.0

    def test_high_vix_multiplier(self):
        """Test high VIX results in higher multiplier."""
        calculator = MarginCalculator()
        result = calculator.calculate_margin(
            instrument_token=256265,
            quantity=1,
            side="BUY",
            segment="NFO-FUT",
            underlying_price=24000,
            symbol="NIFTY",
            vix=28.0,  # High VIX
            expiry_date=date.today() + timedelta(days=15)
        )

        assert result.vix_multiplier > 1.5
        assert result.vix == 28.0

    def test_extreme_vix_multiplier(self):
        """Test extreme VIX caps at 2.0x."""
        calculator = MarginCalculator()
        result = calculator.calculate_margin(
            instrument_token=256265,
            quantity=1,
            side="BUY",
            segment="NFO-FUT",
            underlying_price=24000,
            symbol="NIFTY",
            vix=35.0,  # Extreme VIX
            expiry_date=date.today() + timedelta(days=15)
        )

        assert result.vix_multiplier <= 2.0
        assert result.vix == 35.0

    def test_expiry_day_multiplier(self):
        """Test expiry day results in 3.5x multiplier."""
        calculator = MarginCalculator()
        result = calculator.calculate_margin(
            instrument_token=256265,
            quantity=1,
            side="BUY",
            segment="NFO-FUT",
            underlying_price=24000,
            symbol="NIFTY",
            vix=15.0,
            expiry_date=date.today()  # Expiry today
        )

        assert result.expiry_multiplier == 3.5
        assert result.is_expiry_day
        assert result.days_to_expiry == 0
        # Should also have additional margin on expiry day
        assert result.additional_margin > 0

    def test_expiry_week_multiplier(self):
        """Test expiry week results in elevated multiplier."""
        calculator = MarginCalculator()
        result = calculator.calculate_margin(
            instrument_token=256265,
            quantity=1,
            side="BUY",
            segment="NFO-FUT",
            underlying_price=24000,
            symbol="NIFTY",
            vix=15.0,
            expiry_date=date.today() + timedelta(days=5)
        )

        assert result.expiry_multiplier > 1.0
        assert result.is_expiry_week
        assert result.days_to_expiry == 5

    def test_normal_expiry_multiplier(self):
        """Test normal expiry (> 7 days) results in 1.0x multiplier."""
        calculator = MarginCalculator()
        result = calculator.calculate_margin(
            instrument_token=256265,
            quantity=1,
            side="BUY",
            segment="NFO-FUT",
            underlying_price=24000,
            symbol="NIFTY",
            vix=15.0,
            expiry_date=date.today() + timedelta(days=15)
        )

        assert result.expiry_multiplier == 1.0
        assert not result.is_expiry_week
        assert not result.is_expiry_day

    def test_atm_option_multiplier(self):
        """Test ATM option results in 1.0x price movement multiplier."""
        calculator = MarginCalculator()
        result = calculator.calculate_margin(
            instrument_token=256265,
            quantity=1,
            side="BUY",
            segment="NFO-OPT",
            underlying_price=24000,
            symbol="NIFTY",
            strike_price=24000,  # ATM
            option_type="CE",
            vix=15.0,
            expiry_date=date.today() + timedelta(days=15)
        )

        assert result.price_movement_multiplier == 1.0

    def test_otm_option_multiplier(self):
        """Test OTM option results in higher multiplier."""
        calculator = MarginCalculator()
        result = calculator.calculate_margin(
            instrument_token=256265,
            quantity=1,
            side="BUY",
            segment="NFO-OPT",
            underlying_price=24000,
            symbol="NIFTY",
            strike_price=24500,  # OTM call
            option_type="CE",
            vix=15.0,
            expiry_date=date.today() + timedelta(days=15)
        )

        assert result.price_movement_multiplier > 1.0

    def test_deep_otm_option_multiplier(self):
        """Test deep OTM option results in even higher multiplier."""
        calculator = MarginCalculator()
        result = calculator.calculate_margin(
            instrument_token=256265,
            quantity=1,
            side="BUY",
            segment="NFO-OPT",
            underlying_price=24000,
            symbol="NIFTY",
            strike_price=26000,  # Deep OTM call
            option_type="CE",
            vix=15.0,
            expiry_date=date.today() + timedelta(days=15)
        )

        assert result.price_movement_multiplier >= 1.4

    def test_combined_multipliers_high_risk(self):
        """Test combined effect of multiple high-risk factors."""
        calculator = MarginCalculator()
        result = calculator.calculate_margin(
            instrument_token=256265,
            quantity=1,
            side="SELL",
            segment="NFO-OPT",
            underlying_price=24000,
            symbol="NIFTY",
            strike_price=26000,  # Deep OTM
            option_type="CE",
            premium=20.0,
            vix=30.0,  # High VIX
            expiry_date=date.today()  # Expiry day
        )

        # All multipliers should be elevated
        assert result.vix_multiplier >= 1.7
        assert result.expiry_multiplier == 3.5
        assert result.price_movement_multiplier >= 1.4
        # Total margin should be significantly higher than base
        # (SPAN is already multiplied, so total > SPAN + exposure)
        assert result.total_margin > result.span_margin + result.exposure_margin

    def test_multiple_lots_scales_margin(self):
        """Test that margin scales with number of lots."""
        calculator = MarginCalculator()

        # 1 lot
        result_1_lot = calculator.calculate_margin(
            instrument_token=256265,
            quantity=1,
            side="BUY",
            segment="NFO-FUT",
            underlying_price=24000,
            symbol="NIFTY",
            vix=15.0,
            expiry_date=date.today() + timedelta(days=15)
        )

        # 5 lots
        result_5_lots = calculator.calculate_margin(
            instrument_token=256265,
            quantity=5,
            side="BUY",
            segment="NFO-FUT",
            underlying_price=24000,
            symbol="NIFTY",
            vix=15.0,
            expiry_date=date.today() + timedelta(days=15)
        )

        # Margin should scale linearly with quantity
        assert abs(result_5_lots.total_margin - result_1_lot.total_margin * 5) < 1.0

    def test_banknifty_higher_regulatory_multiplier(self):
        """Test that BANKNIFTY gets higher regulatory multiplier."""
        calculator = MarginCalculator()

        # NIFTY
        nifty_result = calculator.calculate_margin(
            instrument_token=256265,
            quantity=1,
            side="BUY",
            segment="NFO-FUT",
            underlying_price=24000,
            symbol="NIFTY",
            vix=15.0,
            expiry_date=date.today() + timedelta(days=15)
        )

        # BANKNIFTY
        banknifty_result = calculator.calculate_margin(
            instrument_token=260105,
            quantity=1,
            side="BUY",
            segment="NFO-FUT",
            underlying_price=50000,
            symbol="BANKNIFTY",
            vix=15.0,
            expiry_date=date.today() + timedelta(days=15),
            lot_size=25
        )

        # BANKNIFTY should have higher regulatory multiplier
        assert banknifty_result.regulatory_multiplier >= nifty_result.regulatory_multiplier

    def test_to_dict_serialization(self):
        """Test that result can be serialized to dict."""
        calculator = MarginCalculator()
        result = calculator.calculate_margin(
            instrument_token=256265,
            quantity=1,
            side="BUY",
            segment="NFO-FUT",
            underlying_price=24000,
            symbol="NIFTY",
            vix=15.0,
            expiry_date=date.today() + timedelta(days=15)
        )

        result_dict = result.to_dict()

        assert isinstance(result_dict, dict)
        assert "span_margin" in result_dict
        assert "exposure_margin" in result_dict
        assert "total_margin" in result_dict
        assert "vix_multiplier" in result_dict
        assert "expiry_multiplier" in result_dict
        assert "days_to_expiry" in result_dict

    def test_convenience_function(self):
        """Test convenience function for quick calculation."""
        result_dict = calculate_margin(
            quantity=1,
            underlying_price=24000,
            side="BUY",
            segment="NFO-OPT",
            symbol="NIFTY",
            strike_price=24000,
            option_type="CE",
            vix=15.0,
            expiry_date=date.today() + timedelta(days=15)
        )

        assert isinstance(result_dict, dict)
        assert "total_margin" in result_dict
        assert result_dict["total_margin"] > 0

    def test_default_expiry_calculation(self):
        """Test that default expiry is calculated if not provided."""
        calculator = MarginCalculator()
        result = calculator.calculate_margin(
            instrument_token=256265,
            quantity=1,
            side="BUY",
            segment="NFO-FUT",
            underlying_price=24000,
            symbol="NIFTY",
            vix=15.0,
            expiry_date=None  # Should calculate default
        )

        # Should have calculated some days to expiry
        assert result.days_to_expiry >= 0

    def test_zero_quantity(self):
        """Test handling of zero quantity."""
        calculator = MarginCalculator()
        result = calculator.calculate_margin(
            instrument_token=256265,
            quantity=0,
            side="BUY",
            segment="NFO-FUT",
            underlying_price=24000,
            symbol="NIFTY",
            vix=15.0,
            expiry_date=date.today() + timedelta(days=15)
        )

        # Should have zero margin
        assert result.total_margin == 0.0
