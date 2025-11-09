"""
Integration tests for Smart Order Management API endpoints.

Tests all 4 endpoints:
- POST /smart-orders/validate
- POST /smart-orders/calculate-margin
- POST /smart-orders/calculate-cost
- POST /smart-orders/place
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch
from datetime import date


@pytest.fixture
def mock_depth_data():
    """Mock market depth data with realistic values."""
    return {
        "buy": [
            {"price": 149.50, "quantity": 50, "orders": 5},
            {"price": 149.25, "quantity": 100, "orders": 8},
            {"price": 149.00, "quantity": 150, "orders": 12},
            {"price": 148.75, "quantity": 200, "orders": 15},
            {"price": 148.50, "quantity": 250, "orders": 18}
        ],
        "sell": [
            {"price": 150.00, "quantity": 50, "orders": 5},
            {"price": 150.25, "quantity": 100, "orders": 8},
            {"price": 150.50, "quantity": 150, "orders": 12},
            {"price": 150.75, "quantity": 200, "orders": 15},
            {"price": 151.00, "quantity": 250, "orders": 18}
        ]
    }


class TestValidateOrderEndpoint:
    """Test POST /smart-orders/validate endpoint."""

    def test_validate_order_tight_spread(self, client: TestClient, mock_depth_data):
        """Test order validation with tight spread."""
        response = client.post("/smart-orders/validate", json={
            "depth_data": mock_depth_data,
            "quantity": 10,
            "side": "BUY",
            "last_price": 150.00,
            "max_order_spread_pct": 0.5,
            "max_market_impact_bps": 50
        })

        assert response.status_code == 200
        data = response.json()

        # Should allow execution with tight spread
        assert data["can_execute"] is True
        assert data["requires_user_approval"] is False
        assert data["recommended_order_type"] in ["MARKET", "LIMIT"]
        assert isinstance(data["warnings"], list)
        assert isinstance(data["spread_analysis"], dict)
        assert isinstance(data["impact_analysis"], dict)

    def test_validate_order_wide_spread(self, client: TestClient):
        """Test order validation with wide spread."""
        # Create wide spread depth
        wide_depth = {
            "buy": [{"price": 140.00, "quantity": 50, "orders": 5}],
            "sell": [{"price": 160.00, "quantity": 50, "orders": 5}]
        }

        response = client.post("/smart-orders/validate", json={
            "depth_data": wide_depth,
            "quantity": 10,
            "side": "BUY",
            "last_price": 150.00,
            "max_order_spread_pct": 0.5
        })

        assert response.status_code == 200
        data = response.json()

        # Should flag wide spread
        assert data["requires_user_approval"] is True or data["can_execute"] is False
        assert len(data["warnings"]) > 0
        assert "spread" in str(data["warnings"]).lower() or "spread" in data["action_summary"].lower()

    def test_validate_order_high_impact(self, client: TestClient):
        """Test order validation with high market impact."""
        # Low liquidity depth
        low_liquidity_depth = {
            "buy": [
                {"price": 149.50, "quantity": 5, "orders": 1},
                {"price": 149.00, "quantity": 10, "orders": 2}
            ],
            "sell": [
                {"price": 150.00, "quantity": 5, "orders": 1},
                {"price": 150.50, "quantity": 10, "orders": 2}
            ]
        }

        response = client.post("/smart-orders/validate", json={
            "depth_data": low_liquidity_depth,
            "quantity": 50,  # Large quantity vs available liquidity
            "side": "BUY",
            "last_price": 150.00,
            "max_market_impact_bps": 50
        })

        assert response.status_code == 200
        data = response.json()

        # Should flag high impact
        assert data["requires_user_approval"] is True or data["can_execute"] is False
        assert len(data["warnings"]) > 0

    def test_validate_order_invalid_side(self, client: TestClient, mock_depth_data):
        """Test validation with invalid side parameter."""
        response = client.post("/smart-orders/validate", json={
            "depth_data": mock_depth_data,
            "quantity": 10,
            "side": "INVALID",
            "last_price": 150.00
        })

        # Should return validation error
        assert response.status_code == 422


class TestCalculateMarginEndpoint:
    """Test POST /smart-orders/calculate-margin endpoint."""

    @patch('app.services.margin_calculator.MarginCalculator.fetch_margin_from_ticker_service')
    async def test_calculate_margin_with_ticker_service(
        self, mock_fetch, client: TestClient
    ):
        """Test margin calculation with ticker_service integration."""
        # Mock ticker_service response
        mock_fetch.return_value = {
            "type": "equity",
            "tradingsymbol": "NIFTY24NOV24000CE",
            "span": 15000.0,
            "exposure": 7500.0,
            "option_premium": 7500.0,
            "additional": 0.0,
            "total": 30000.0
        }

        response = client.post("/smart-orders/calculate-margin", json={
            "tradingsymbol": "NIFTY24NOV24000CE",
            "exchange": "NFO",
            "transaction_type": "BUY",
            "quantity": 50,
            "price": 150.0,
            "symbol": "NIFTY",
            "underlying_price": 23950,
            "vix": 15.5
        })

        assert response.status_code == 200
        data = response.json()

        # Should have all margin components
        assert "span_margin" in data
        assert "exposure_margin" in data
        assert "premium_margin" in data
        assert "total_margin" in data

        # Should have multipliers
        assert "vix_multiplier" in data
        assert "expiry_multiplier" in data
        assert "price_movement_multiplier" in data

        # Should have metadata
        assert "vix" in data
        assert "days_to_expiry" in data

    def test_calculate_margin_fallback(self, client: TestClient):
        """Test margin calculation with fallback when ticker_service unavailable."""
        response = client.post("/smart-orders/calculate-margin", json={
            "tradingsymbol": "NIFTY24DEC24000CE",
            "exchange": "NFO",
            "transaction_type": "BUY",
            "quantity": 50,
            "price": 150.0,
            "symbol": "NIFTY",
            "underlying_price": 24000,
            "strike_price": 24000.0,
            "option_type": "CE",
            "vix": 18.0,
            "expiry_date": "2024-12-26"
        })

        # Should still work with fallback calculation
        assert response.status_code == 200
        data = response.json()

        assert data["total_margin"] > 0
        assert data["span_margin"] > 0
        assert data["vix_multiplier"] >= 1.0

    def test_calculate_margin_invalid_transaction_type(self, client: TestClient):
        """Test margin calculation with invalid transaction type."""
        response = client.post("/smart-orders/calculate-margin", json={
            "tradingsymbol": "NIFTY24NOV24000CE",
            "exchange": "NFO",
            "transaction_type": "INVALID",
            "quantity": 50,
            "price": 150.0,
            "underlying_price": 23950
        })

        assert response.status_code == 422


class TestCalculateCostEndpoint:
    """Test POST /smart-orders/calculate-cost endpoint."""

    def test_calculate_cost_options_buy(self, client: TestClient):
        """Test cost calculation for options buying."""
        response = client.post("/smart-orders/calculate-cost", json={
            "order_value": 75000,
            "quantity": 10,
            "price": 150,
            "side": "BUY",
            "segment": "NFO-OPT"
        })

        assert response.status_code == 200
        data = response.json()

        # Should have all cost components
        assert data["brokerage"] == 20.0  # Flat ₹20 for options
        assert data["stt"] == 0.0  # No STT on buy
        assert data["gst"] > 0
        assert data["stamp_duty"] > 0
        assert data["total_charges"] > 0
        assert data["net_cost"] > data["order_value"]  # BUY adds charges

    def test_calculate_cost_options_sell(self, client: TestClient):
        """Test cost calculation for options selling."""
        response = client.post("/smart-orders/calculate-cost", json={
            "order_value": 75000,
            "quantity": 10,
            "price": 150,
            "side": "SELL",
            "segment": "NFO-OPT"
        })

        assert response.status_code == 200
        data = response.json()

        assert data["brokerage"] == 20.0
        assert data["stt"] > 0  # STT on sell side
        assert data["stamp_duty"] == 0.0  # No stamp duty on sell
        assert data["net_cost"] < data["order_value"]  # SELL subtracts charges

    def test_calculate_cost_futures(self, client: TestClient):
        """Test cost calculation for futures."""
        response = client.post("/smart-orders/calculate-cost", json={
            "order_value": 120000,
            "quantity": 5,
            "price": 24000,
            "side": "BUY",
            "segment": "NFO-FUT"
        })

        assert response.status_code == 200
        data = response.json()

        # Futures brokerage: 0.03% capped at ₹20
        assert data["brokerage"] <= 20.0
        assert data["total_charges"] > 0

    def test_calculate_cost_equity_delivery(self, client: TestClient):
        """Test cost calculation for equity delivery."""
        response = client.post("/smart-orders/calculate-cost", json={
            "order_value": 100000,
            "quantity": 100,
            "price": 1000,
            "side": "BUY",
            "segment": "EQUITY-DELIVERY"
        })

        assert response.status_code == 200
        data = response.json()

        # Equity delivery: ₹0 brokerage
        assert data["brokerage"] == 0.0
        assert data["stt"] > 0  # STT on both sides
        assert data["stamp_duty"] > 0


class TestPlaceSmartOrderEndpoint:
    """Test POST /smart-orders/place endpoint."""

    def test_place_smart_order_success(self, client: TestClient, mock_depth_data):
        """Test smart order placement with all validations passing."""
        response = client.post("/smart-orders/place", json={
            "tradingsymbol": "NIFTY24NOV24000CE",
            "exchange": "NFO",
            "transaction_type": "BUY",
            "quantity": 10,
            "price": 150.0,
            "depth_data": mock_depth_data,
            "last_price": 150.25,
            "underlying_price": 23950,
            "segment": "NFO-OPT",
            "symbol": "NIFTY",
            "vix": 15.5
        })

        assert response.status_code == 200
        data = response.json()

        # Should have all analysis components
        assert "validation" in data
        assert "margin" in data
        assert "cost" in data
        assert "warnings" in data

        # Check validation result
        assert isinstance(data["validation"], dict)
        assert "can_execute" in data["validation"]

        # Check margin result
        if data["margin"]:
            assert "total_margin" in data["margin"]

        # Check cost result
        assert "total_charges" in data["cost"]
        assert "net_cost" in data["cost"]

    def test_place_smart_order_skip_validation(self, client: TestClient, mock_depth_data):
        """Test smart order placement with validation skip."""
        response = client.post("/smart-orders/place", json={
            "tradingsymbol": "NIFTY24NOV24000CE",
            "exchange": "NFO",
            "transaction_type": "BUY",
            "quantity": 10,
            "price": 150.0,
            "depth_data": mock_depth_data,
            "last_price": 150.25,
            "underlying_price": 23950,
            "segment": "NFO-OPT",
            "skip_validation": True
        })

        assert response.status_code == 200
        data = response.json()

        # Should still provide analysis even with skip
        assert "validation" in data
        assert "cost" in data

    def test_place_smart_order_rejected_by_validation(self, client: TestClient):
        """Test smart order placement rejected by validation."""
        # Wide spread that should trigger rejection
        wide_depth = {
            "buy": [{"price": 140.00, "quantity": 50, "orders": 5}],
            "sell": [{"price": 160.00, "quantity": 50, "orders": 5}]
        }

        response = client.post("/smart-orders/place", json={
            "tradingsymbol": "NIFTY24NOV24000CE",
            "exchange": "NFO",
            "transaction_type": "BUY",
            "quantity": 10,
            "price": 150.0,
            "depth_data": wide_depth,
            "last_price": 150.0,
            "underlying_price": 23950,
            "segment": "NFO-OPT",
            "max_order_spread_pct": 0.5
        })

        assert response.status_code == 200
        data = response.json()

        # Should provide analysis but not place order
        assert "error" in data or data["order_placed"] is False
        assert "validation" in data


class TestAPIErrorHandling:
    """Test error handling across all endpoints."""

    def test_missing_required_fields(self, client: TestClient):
        """Test endpoints with missing required fields."""
        # Validate endpoint - missing depth_data
        response = client.post("/smart-orders/validate", json={
            "quantity": 10,
            "side": "BUY",
            "last_price": 150.00
        })
        assert response.status_code == 422

        # Margin endpoint - missing tradingsymbol
        response = client.post("/smart-orders/calculate-margin", json={
            "exchange": "NFO",
            "transaction_type": "BUY",
            "quantity": 50,
            "price": 150.0
        })
        assert response.status_code == 422

        # Cost endpoint - missing segment
        response = client.post("/smart-orders/calculate-cost", json={
            "order_value": 75000,
            "quantity": 10,
            "price": 150,
            "side": "BUY"
        })
        assert response.status_code == 422
