# tests/unit/test_decimal_precision.py
"""
Unit tests for decimal precision in financial calculations.
Ensures no float precision loss in money calculations.
"""
import pytest
from decimal import Decimal


class TestDecimalPrecision:
    """Test financial calculations use Decimal, not float."""

    def test_decimal_addition_precision(self):
        """Test Decimal addition maintains precision."""
        price1 = Decimal("100.05")
        price2 = Decimal("50.10")

        total = price1 + price2

        assert total == Decimal("150.15")
        assert isinstance(total, Decimal)

    def test_decimal_multiplication_precision(self):
        """Test Decimal multiplication for P&L calculation."""
        entry_price = Decimal("100.05")
        quantity = 75

        total_value = entry_price * quantity

        # 100.05 × 75 = 7503.75 (exact)
        assert total_value == Decimal("7503.75")
        assert isinstance(total_value, Decimal)

    def test_float_precision_loss_demonstration(self):
        """Demonstrate float precision loss (negative test)."""
        # Using float arithmetic (BAD)
        price_float = 0.1 + 0.2

        # Float result is imprecise
        assert price_float != 0.3  # Classic float precision issue
        assert abs(price_float - 0.3) < 0.0000001  # Close, but not exact

    def test_decimal_maintains_exact_precision(self):
        """Test Decimal maintains exact precision."""
        # Using Decimal (GOOD)
        price_decimal = Decimal("0.1") + Decimal("0.2")

        # Decimal is exact
        assert price_decimal == Decimal("0.3")

    def test_decimal_division_precision(self):
        """Test Decimal division maintains precision."""
        total_value = Decimal("1000.00")
        quantity = 3

        per_unit = total_value / quantity

        # 1000 / 3 = 333.3333... (repeating decimal)
        # Decimal maintains precision up to 28 decimal places
        assert str(per_unit).startswith("333.3333")
        assert isinstance(per_unit, Decimal)

    def test_decimal_rounding_to_currency(self):
        """Test Decimal rounding for currency (2 decimal places)."""
        pnl = Decimal("378.7567")

        rounded = pnl.quantize(Decimal("0.01"))

        assert rounded == Decimal("378.76")  # Rounded up

    def test_decimal_aggregation_precision(self):
        """Test Decimal precision in multi-instrument aggregation."""
        positions = [
            Decimal("123.45"),
            Decimal("67.89"),
            Decimal("0.01")
        ]

        total = sum(positions)

        # 123.45 + 67.89 + 0.01 = 191.35 (exact)
        assert total == Decimal("191.35")

    def test_decimal_negative_values(self):
        """Test Decimal with negative P&L values."""
        profit = Decimal("500.00")
        loss = Decimal("-350.75")

        net_pnl = profit + loss

        assert net_pnl == Decimal("149.25")
        assert isinstance(net_pnl, Decimal)

    def test_decimal_from_string_conversion(self):
        """Test that string conversion to Decimal is safe."""
        price_str = "123.456789"

        price_decimal = Decimal(price_str)

        assert price_decimal == Decimal("123.456789")
        # Full precision maintained
        assert str(price_decimal) == "123.456789"

    def test_decimal_comparison_precision(self):
        """Test Decimal comparison is exact."""
        price1 = Decimal("100.00")
        price2 = Decimal("100.0000")

        # Decimals compare by value, not representation
        assert price1 == price2
