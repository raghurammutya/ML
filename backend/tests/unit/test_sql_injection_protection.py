# tests/unit/test_sql_injection_protection.py
"""
Unit tests for SQL injection protection mechanisms.
Tests the validate_sort_params function for security.
"""
import pytest
from fastapi import HTTPException
from app.database import validate_sort_params, ALLOWED_STRATEGY_SORT_COLUMNS


class TestSQLInjectionProtection:
    """Test SQL injection protection via whitelisting."""

    def test_valid_sort_params(self):
        """Test that valid sort parameters are accepted."""
        sort_by, order = validate_sort_params(
            "created_at",
            "DESC",
            ALLOWED_STRATEGY_SORT_COLUMNS
        )

        assert sort_by == "created_at"
        assert order == "DESC"

    def test_valid_sort_params_asc(self):
        """Test that ASC order is accepted."""
        sort_by, order = validate_sort_params(
            "name",
            "ASC",
            ALLOWED_STRATEGY_SORT_COLUMNS
        )

        assert sort_by == "name"
        assert order == "ASC"

    def test_invalid_column_rejected(self):
        """Test that SQL injection attempt via column name is rejected."""
        with pytest.raises(HTTPException) as exc_info:
            validate_sort_params(
                "id; DROP TABLE strategies; --",
                "DESC",
                ALLOWED_STRATEGY_SORT_COLUMNS
            )

        assert exc_info.value.status_code == 400
        assert "Invalid sort_by parameter" in exc_info.value.detail

    def test_invalid_order_rejected(self):
        """Test that SQL injection attempt via order is rejected."""
        with pytest.raises(HTTPException) as exc_info:
            validate_sort_params(
                "created_at",
                "DESC; DROP TABLE strategies; --",
                ALLOWED_STRATEGY_SORT_COLUMNS
            )

        assert exc_info.value.status_code == 400
        assert "Invalid order parameter" in exc_info.value.detail

    def test_case_insensitive_order(self):
        """Test that order is case-insensitive."""
        sort_by, order = validate_sort_params(
            "name",
            "asc",
            ALLOWED_STRATEGY_SORT_COLUMNS
        )

        assert order == "ASC"

    def test_empty_column_rejected(self):
        """Test that empty column name is rejected."""
        with pytest.raises(HTTPException) as exc_info:
            validate_sort_params(
                "",
                "DESC",
                ALLOWED_STRATEGY_SORT_COLUMNS
            )

        assert exc_info.value.status_code == 400

    def test_all_allowed_columns(self):
        """Test that all whitelisted columns work."""
        for column in ALLOWED_STRATEGY_SORT_COLUMNS:
            sort_by, order = validate_sort_params(
                column,
                "DESC",
                ALLOWED_STRATEGY_SORT_COLUMNS
            )
            assert sort_by == column
            assert order == "DESC"
