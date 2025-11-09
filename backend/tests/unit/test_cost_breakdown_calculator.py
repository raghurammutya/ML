"""
Tests for Cost Breakdown Calculator

Verify brokerage, STT, GST, SEBI charges, and stamp duty calculations.
"""

import pytest

from app.services.cost_breakdown_calculator import (
    CostBreakdownCalculator,
    calculate_trade_cost
)


class TestCostBreakdownCalculator:
    """Test cost breakdown calculation functionality."""

    def test_options_buy_cost(self):
        """Test cost breakdown for options buying."""
        calculator = CostBreakdownCalculator()
        result = calculator.calculate_cost(
            order_value=75000,  # ₹150 * 50 lots * 10 quantity
            quantity=10,
            price=150,
            side="BUY",
            segment="NFO-OPT"
        )

        # Options: ₹20 flat brokerage
        assert result.brokerage == 20.0
        # No STT on buy side
        assert result.stt == 0.0
        # Should have exchange charges
        assert result.exchange_charges > 0
        # GST on brokerage + exchange
        assert result.gst > 0
        # Stamp duty on buy side
        assert result.stamp_duty > 0
        # Total charges
        assert result.total_charges > 20.0
        # Net cost = order_value + charges (BUY)
        assert result.net_cost > result.order_value

    def test_options_sell_cost(self):
        """Test cost breakdown for options selling."""
        calculator = CostBreakdownCalculator()
        result = calculator.calculate_cost(
            order_value=75000,
            quantity=10,
            price=150,
            side="SELL",
            segment="NFO-OPT"
        )

        # Options: ₹20 flat brokerage
        assert result.brokerage == 20.0
        # STT 0.05% on sell side
        assert result.stt > 0
        assert abs(result.stt - (75000 * 0.05 / 100)) < 0.01
        # No stamp duty on sell side
        assert result.stamp_duty == 0.0
        # Net cost = order_value - charges (SELL)
        assert result.net_cost < result.order_value

    def test_futures_buy_cost(self):
        """Test cost breakdown for futures buying."""
        calculator = CostBreakdownCalculator()
        result = calculator.calculate_cost(
            order_value=120000,
            quantity=5,
            price=24000,
            side="BUY",
            segment="NFO-FUT"
        )

        # Futures: 0.03% of turnover, capped at ₹20
        expected_brokerage = min(120000 * 0.03 / 100, 20.0)
        assert abs(result.brokerage - expected_brokerage) < 0.01
        # No STT on buy side
        assert result.stt == 0.0
        # Stamp duty on buy side
        assert result.stamp_duty > 0
        # Total charges
        assert result.total_charges > 0

    def test_futures_sell_cost(self):
        """Test cost breakdown for futures selling."""
        calculator = CostBreakdownCalculator()
        result = calculator.calculate_cost(
            order_value=120000,
            quantity=5,
            price=24000,
            side="SELL",
            segment="NFO-FUT"
        )

        # STT 0.0125% on sell side
        assert result.stt > 0
        assert abs(result.stt - (120000 * 0.0125 / 100)) < 0.01
        # No stamp duty on sell side
        assert result.stamp_duty == 0.0

    def test_equity_delivery_buy_cost(self):
        """Test cost breakdown for equity delivery buying."""
        calculator = CostBreakdownCalculator()
        result = calculator.calculate_cost(
            order_value=100000,
            quantity=100,
            price=1000,
            side="BUY",
            segment="EQUITY-DELIVERY"
        )

        # Equity delivery: ₹0 brokerage
        assert result.brokerage == 0.0
        # STT 0.1% on both sides
        assert result.stt > 0
        assert abs(result.stt - (100000 * 0.1 / 100)) < 0.01
        # Stamp duty 0.015% on buy side
        assert result.stamp_duty > 0
        assert abs(result.stamp_duty - (100000 * 0.015 / 100)) < 0.01

    def test_equity_delivery_sell_cost(self):
        """Test cost breakdown for equity delivery selling."""
        calculator = CostBreakdownCalculator()
        result = calculator.calculate_cost(
            order_value=100000,
            quantity=100,
            price=1000,
            side="SELL",
            segment="EQUITY-DELIVERY"
        )

        # Equity delivery: ₹0 brokerage
        assert result.brokerage == 0.0
        # STT 0.1% on both sides
        assert result.stt > 0
        # No stamp duty on sell side
        assert result.stamp_duty == 0.0

    def test_equity_intraday_cost(self):
        """Test cost breakdown for equity intraday."""
        calculator = CostBreakdownCalculator()
        result = calculator.calculate_cost(
            order_value=100000,
            quantity=100,
            price=1000,
            side="BUY",
            segment="EQUITY-INTRADAY"
        )

        # Intraday: 0.03% capped at ₹20
        expected_brokerage = min(100000 * 0.03 / 100, 20.0)
        assert abs(result.brokerage - expected_brokerage) < 0.01
        # Stamp duty 0.002% on buy side
        assert result.stamp_duty > 0

    def test_gst_calculation(self):
        """Test GST is calculated correctly as 18% of brokerage + exchange."""
        calculator = CostBreakdownCalculator()
        result = calculator.calculate_cost(
            order_value=75000,
            quantity=10,
            price=150,
            side="BUY",
            segment="NFO-OPT"
        )

        # GST should be 18% of (brokerage + exchange_charges)
        expected_gst = (result.brokerage + result.exchange_charges) * 0.18
        assert abs(result.gst - expected_gst) < 0.01

    def test_sebi_charges_calculation(self):
        """Test SEBI charges are ₹10 per crore."""
        calculator = CostBreakdownCalculator()
        result = calculator.calculate_cost(
            order_value=10000000,  # 1 crore
            quantity=100,
            price=100000,
            side="BUY",
            segment="NFO-FUT"
        )

        # SEBI charges: ₹10 per crore
        assert abs(result.sebi_charges - 10.0) < 0.01

    def test_total_charges_sum(self):
        """Test that total_charges is sum of all components."""
        calculator = CostBreakdownCalculator()
        result = calculator.calculate_cost(
            order_value=75000,
            quantity=10,
            price=150,
            side="BUY",
            segment="NFO-OPT"
        )

        # Total should be sum of all components
        expected_total = (
            result.brokerage +
            result.stt +
            result.exchange_charges +
            result.gst +
            result.sebi_charges +
            result.stamp_duty
        )
        assert abs(result.total_charges - expected_total) < 0.01

    def test_net_cost_buy(self):
        """Test net cost calculation for BUY orders."""
        calculator = CostBreakdownCalculator()
        result = calculator.calculate_cost(
            order_value=75000,
            quantity=10,
            price=150,
            side="BUY",
            segment="NFO-OPT"
        )

        # Net cost = order_value + total_charges
        expected_net = result.order_value + result.total_charges
        assert abs(result.net_cost - expected_net) < 0.01

    def test_net_cost_sell(self):
        """Test net cost calculation for SELL orders."""
        calculator = CostBreakdownCalculator()
        result = calculator.calculate_cost(
            order_value=75000,
            quantity=10,
            price=150,
            side="SELL",
            segment="NFO-OPT"
        )

        # Net cost = order_value - total_charges
        expected_net = result.order_value - result.total_charges
        assert abs(result.net_cost - expected_net) < 0.01

    def test_to_dict_serialization(self):
        """Test that result can be serialized to dict."""
        calculator = CostBreakdownCalculator()
        result = calculator.calculate_cost(
            order_value=75000,
            quantity=10,
            price=150,
            side="BUY",
            segment="NFO-OPT"
        )

        result_dict = result.to_dict()

        assert isinstance(result_dict, dict)
        assert "brokerage" in result_dict
        assert "stt" in result_dict
        assert "gst" in result_dict
        assert "total_charges" in result_dict
        assert "net_cost" in result_dict

    def test_convenience_function(self):
        """Test convenience function for quick calculation."""
        result_dict = calculate_trade_cost(
            order_value=75000,
            quantity=10,
            price=150,
            side="BUY",
            segment="NFO-OPT"
        )

        assert isinstance(result_dict, dict)
        assert "total_charges" in result_dict
        assert result_dict["total_charges"] > 0

    def test_zero_order_value(self):
        """Test handling of zero order value."""
        calculator = CostBreakdownCalculator()
        result = calculator.calculate_cost(
            order_value=0,
            quantity=0,
            price=0,
            side="BUY",
            segment="NFO-OPT"
        )

        # Should still have flat brokerage for options
        assert result.brokerage == 20.0
        # But other charges should be zero
        assert result.stt == 0.0

    def test_large_order_brokerage_cap(self):
        """Test that futures brokerage is capped at ₹20."""
        calculator = CostBreakdownCalculator()
        result = calculator.calculate_cost(
            order_value=10000000,  # Very large order
            quantity=100,
            price=100000,
            side="BUY",
            segment="NFO-FUT"
        )

        # Should be capped at ₹20
        assert result.brokerage == 20.0

    def test_broker_attribute(self):
        """Test that broker attribute is set correctly."""
        calculator = CostBreakdownCalculator()
        result = calculator.calculate_cost(
            order_value=75000,
            quantity=10,
            price=150,
            side="BUY",
            segment="NFO-OPT",
            broker="zerodha"
        )

        assert result.broker == "zerodha"
