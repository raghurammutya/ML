"""
API Contract Tests (Simplified)

Tests verify API contract principles without requiring full app startup.
These are schema and validation tests.
"""
import pytest
from decimal import Decimal
from datetime import datetime, date
from pydantic import ValidationError

# Test Pydantic models
from app.models.statement import (
    StatementUploadCreate,
    StatementQueryParams,
    StatementTransaction,
    FundsCategorySummary
)

pytestmark = pytest.mark.integration


class TestStatementModels:
    """Test Statement API models validate correctly."""

    def test_statement_upload_create_valid(self):
        """Test valid StatementUploadCreate."""
        data = StatementUploadCreate(
            account_id="account_123",
            uploaded_by="user_456"
        )
        assert data.account_id == "account_123"
        assert data.uploaded_by == "user_456"

    def test_statement_upload_requires_account_id(self):
        """Test StatementUploadCreate requires account_id."""
        with pytest.raises(ValidationError):
            StatementUploadCreate(uploaded_by="user_456")

    def test_statement_query_params_validation(self):
        """Test StatementQueryParams validates dates."""
        # Valid dates
        params = StatementQueryParams(
            account_id="account_123",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 12, 31)
        )
        assert params.start_date < params.end_date

    def test_statement_query_end_before_start_fails(self):
        """Test end_date before start_date raises error."""
        with pytest.raises(ValidationError):
            StatementQueryParams(
                account_id="account_123",
                start_date=date(2025, 12, 31),
                end_date=date(2025, 1, 1)
            )

    def test_statement_query_limit_validation(self):
        """Test limit parameter validation."""
        # Valid limit
        params = StatementQueryParams(
            account_id="account_123",
            limit=50
        )
        assert params.limit == 50

    def test_statement_query_negative_limit_fails(self):
        """Test negative limit raises error."""
        with pytest.raises(ValidationError):
            StatementQueryParams(
                account_id="account_123",
                limit=-10
            )

    def test_statement_query_excessive_limit_fails(self):
        """Test excessive limit raises error."""
        with pytest.raises(ValidationError):
            StatementQueryParams(
                account_id="account_123",
                limit=100000
            )

    def test_statement_query_negative_offset_fails(self):
        """Test negative offset raises error."""
        with pytest.raises(ValidationError):
            StatementQueryParams(
                account_id="account_123",
                offset=-10
            )

    def test_statement_transaction_decimal_precision(self):
        """Test transaction uses Decimal for financial values."""
        txn = StatementTransaction(
            transaction_date=datetime.now(),
            description="Test transaction",
            debit=Decimal("100.50"),
            credit=Decimal("0.00"),
            category="equity_intraday"
        )
        assert isinstance(txn.debit, Decimal)
        assert isinstance(txn.credit, Decimal)

    def test_funds_category_summary_decimals(self):
        """Test FundsCategorySummary uses Decimals."""
        summary = FundsCategorySummary(
            account_id="account_123",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 12, 31),
            equity_intraday=Decimal("5000.00"),
            fno_premium_paid=Decimal("2000.00"),
            calculated_at=datetime.now()
        )
        assert isinstance(summary.equity_intraday, Decimal)
        assert isinstance(summary.fno_premium_paid, Decimal)


class TestSmartOrderModels:
    """Test Smart Order models if they exist."""

    def test_decimal_precision_in_models(self):
        """Test models use Decimal for precision."""
        # Import cost breakdown if available
        try:
            from app.services.cost_breakdown_calculator import CostBreakdown, calculate_cost_breakdown

            result = calculate_cost_breakdown(
                order_value=Decimal("10000.00"),
                transaction_type="BUY",
                segment="equity",
                product="CNC"
            )

            assert isinstance(result.order_value, Decimal)
            assert isinstance(result.total_charges, Decimal)
            assert isinstance(result.net_cost, Decimal)
        except ImportError:
            pytest.skip("CostBreakdown not available")


class TestEnumValidation:
    """Test enum field validation."""

    def test_statement_category_enum(self):
        """Test category field accepts valid values."""
        valid_categories = [
            "equity_intraday",
            "equity_delivery_acquisition",
            "fno_premium_paid",
            "funds_transfer_in"
        ]

        for category in valid_categories:
            txn = StatementTransaction(
                transaction_date=datetime.now(),
                description="Test",
                category=category
            )
            assert txn.category == category


class TestJSONSerialization:
    """Test model JSON serialization."""

    def test_statement_transaction_to_json(self):
        """Test StatementTransaction serializes to JSON."""
        txn = StatementTransaction(
            transaction_date=datetime.now(),
            description="Test transaction",
            debit=Decimal("100.50"),
            credit=Decimal("0.00"),
            category="equity_intraday"
        )

        json_data = txn.model_dump()
        assert isinstance(json_data, dict)
        assert "transaction_date" in json_data
        assert "debit" in json_data

    def test_decimal_serialization(self):
        """Test Decimals serialize correctly."""
        summary = FundsCategorySummary(
            account_id="account_123",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 12, 31),
            equity_intraday=Decimal("5000.00"),
            calculated_at=datetime.now()
        )

        json_data = summary.model_dump()
        # Decimals should be converted to float for JSON
        assert isinstance(json_data["equity_intraday"], (Decimal, float, int))

    def test_datetime_serialization(self):
        """Test datetime fields serialize."""
        txn = StatementTransaction(
            transaction_date=datetime.now(),
            description="Test",
            category="other"
        )

        json_data = txn.model_dump()
        assert "transaction_date" in json_data


class TestOptionalFields:
    """Test optional field handling."""

    def test_optional_fields_can_be_none(self):
        """Test optional fields accept None."""
        txn = StatementTransaction(
            transaction_date=datetime.now(),
            description="Test",
            category="other",
            balance=None,
            tradingsymbol=None
        )
        assert txn.balance is None
        assert txn.tradingsymbol is None

    def test_optional_uploaded_by(self):
        """Test uploaded_by is optional."""
        upload = StatementUploadCreate(
            account_id="account_123"
        )
        assert upload.uploaded_by is None


class TestDefaultValues:
    """Test model default values."""

    def test_transaction_default_debit_credit(self):
        """Test debit/credit default to zero."""
        txn = StatementTransaction(
            transaction_date=datetime.now(),
            description="Test",
            category="other"
        )
        assert txn.debit == Decimal('0')
        assert txn.credit == Decimal('0')

    def test_query_params_defaults(self):
        """Test QueryParams have sensible defaults."""
        params = StatementQueryParams(
            account_id="account_123"
        )
        assert params.limit == 100
        assert params.offset == 0
        assert params.margin_blocked_only is False


class TestFieldValidation:
    """Test field-level validation."""

    def test_account_id_required(self):
        """Test account_id is required."""
        with pytest.raises(ValidationError):
            StatementQueryParams(limit=10)

    def test_string_length_validation(self):
        """Test string fields validate length."""
        # This should work
        upload = StatementUploadCreate(
            account_id="a" * 100  # 100 chars should be fine
        )
        assert len(upload.account_id) == 100

    def test_date_types_enforced(self):
        """Test date fields enforce date type."""
        # Valid date
        summary = FundsCategorySummary(
            account_id="test",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 12, 31),
            calculated_at=datetime.now()
        )
        assert isinstance(summary.start_date, date)
        assert isinstance(summary.calculated_at, datetime)
