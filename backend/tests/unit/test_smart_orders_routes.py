"""
Unit tests for Smart Order Management API route functions.

Tests the business logic of API endpoints without requiring full app setup.
"""

import pytest
from datetime import date
from unittest.mock import Mock, AsyncMock, patch

from app.routes.smart_orders import (
    ValidateOrderRequest,
    CalculateMarginRequest,
    CalculateCostRequest,
    PlaceSmartOrderRequest,
    validate_order,
    calculate_margin,
    calculate_cost,
    place_smart_order
)


@pytest.fixture
def mock_depth_data():
    """Mock market depth data with realistic values."""
    return {
        "buy": [
            {"price": 149.50, "quantity": 50, "orders": 5},
            {"price": 149.25, "quantity": 100, "orders": 8},
            {"price": 149.00, "quantity": 150, "orders": 12},
        ],
        "sell": [
            {"price": 150.00, "quantity": 50, "orders": 5},
            {"price": 150.25, "quantity": 100, "orders": 8},
            {"price": 150.50, "quantity": 150, "orders": 12},
        ]
    }


class TestValidateOrderRouteLogic:
    """Test validate_order endpoint logic."""

    @pytest.mark.asyncio
    async def test_validate_order_request_model(self, mock_depth_data):
        """Test ValidateOrderRequest model validation."""
        request = ValidateOrderRequest(
            depth_data=mock_depth_data,
            quantity=10,
            side="BUY",
            last_price=150.00,
            max_order_spread_pct=0.5,
            max_market_impact_bps=50
        )

        assert request.side == "BUY"
        assert request.quantity == 10
        assert request.max_order_spread_pct == 0.5

    @pytest.mark.asyncio
    async def test_validate_order_with_tight_spread(self, mock_depth_data):
        """Test order validation returns proper structure with tight spread."""
        request = ValidateOrderRequest(
            depth_data=mock_depth_data,
            quantity=10,
            side="BUY",
            last_price=150.00
        )

        result = await validate_order(request)

        # Check response structure
        assert hasattr(result, 'can_execute')
        assert hasattr(result, 'requires_user_approval')
        assert hasattr(result, 'recommended_order_type')
        assert hasattr(result, 'warnings')
        assert hasattr(result, 'spread_analysis')
        assert hasattr(result, 'impact_analysis')

        # Check types
        assert isinstance(result.can_execute, bool)
        assert isinstance(result.warnings, list)
        assert isinstance(result.spread_analysis, dict)
        assert isinstance(result.impact_analysis, dict)

    @pytest.mark.asyncio
    async def test_validate_order_invalid_side_raises_error(self, mock_depth_data):
        """Test that invalid side raises validation error."""
        with pytest.raises(Exception):  # Pydantic validation error
            ValidateOrderRequest(
                depth_data=mock_depth_data,
                quantity=10,
                side="INVALID",
                last_price=150.00
            )


class TestCalculateMarginRouteLogic:
    """Test calculate_margin endpoint logic."""

    @pytest.mark.asyncio
    async def test_calculate_margin_request_model(self):
        """Test CalculateMarginRequest model validation."""
        request = CalculateMarginRequest(
            tradingsymbol="NIFTY24NOV24000CE",
            exchange="NFO",
            transaction_type="BUY",
            quantity=50,
            price=150.0,
            underlying_price=23950.0,
            vix=15.5
        )

        assert request.tradingsymbol == "NIFTY24NOV24000CE"
        assert request.transaction_type == "BUY"
        assert request.vix == 15.5

    @pytest.mark.asyncio
    @patch('app.services.margin_calculator.MarginCalculator.fetch_margin_from_ticker_service')
    @patch('app.services.margin_calculator.MarginCalculator.calculate_margin')
    async def test_calculate_margin_response_structure(
        self, mock_calc_margin, mock_fetch_margin
    ):
        """Test calculate_margin returns proper response structure."""
        # Mock ticker service response
        mock_fetch_margin.return_value = {
            "total": 30000.0,
            "span": 15000.0
        }

        # Mock calculator response
        from app.services.margin_calculator import MarginBreakdown
        mock_calc_margin.return_value = MarginBreakdown(
            span_margin=15000.0,
            exposure_margin=7500.0,
            premium_margin=7500.0,
            additional_margin=0.0,
            total_margin=30000.0,
            vix_multiplier=1.2,
            expiry_multiplier=1.0,
            price_movement_multiplier=1.0,
            regulatory_multiplier=1.0,
            vix=15.5,
            days_to_expiry=7,
            is_expiry_week=True,
            is_expiry_day=False,
            underlying_price=23950.0,
            strike_price=24000.0
        )

        request = CalculateMarginRequest(
            tradingsymbol="NIFTY24NOV24000CE",
            exchange="NFO",
            transaction_type="BUY",
            quantity=50,
            price=150.0,
            underlying_price=23950.0,
            vix=15.5
        )

        result = await calculate_margin(request)

        # Check response structure
        assert hasattr(result, 'span_margin')
        assert hasattr(result, 'total_margin')
        assert hasattr(result, 'vix_multiplier')
        assert hasattr(result, 'days_to_expiry')

        # Check values
        assert result.total_margin == 30000.0
        assert result.vix_multiplier == 1.2

    @pytest.mark.asyncio
    async def test_calculate_margin_invalid_transaction_type_raises_error(self):
        """Test that invalid transaction type raises validation error."""
        with pytest.raises(Exception):  # Pydantic validation error
            CalculateMarginRequest(
                tradingsymbol="NIFTY24NOV24000CE",
                exchange="NFO",
                transaction_type="INVALID",
                quantity=50,
                price=150.0,
                underlying_price=23950.0
            )


class TestCalculateCostRouteLogic:
    """Test calculate_cost endpoint logic."""

    @pytest.mark.asyncio
    async def test_calculate_cost_request_model(self):
        """Test CalculateCostRequest model validation."""
        request = CalculateCostRequest(
            order_value=75000,
            quantity=10,
            price=150,
            side="BUY",
            segment="NFO-OPT"
        )

        assert request.order_value == 75000
        assert request.side == "BUY"
        assert request.segment == "NFO-OPT"

    @pytest.mark.asyncio
    async def test_calculate_cost_options_buy(self):
        """Test cost calculation for options buying."""
        request = CalculateCostRequest(
            order_value=75000,
            quantity=10,
            price=150,
            side="BUY",
            segment="NFO-OPT"
        )

        result = await calculate_cost(request)

        # Check response structure
        assert hasattr(result, 'brokerage')
        assert hasattr(result, 'stt')
        assert hasattr(result, 'gst')
        assert hasattr(result, 'total_charges')
        assert hasattr(result, 'net_cost')

        # Check values
        assert result.brokerage == 20.0  # Flat ₹20 for options
        assert result.stt == 0.0  # No STT on buy
        assert result.gst > 0
        assert result.total_charges > 0
        assert result.net_cost > result.order_value  # BUY adds charges

    @pytest.mark.asyncio
    async def test_calculate_cost_options_sell(self):
        """Test cost calculation for options selling."""
        request = CalculateCostRequest(
            order_value=75000,
            quantity=10,
            price=150,
            side="SELL",
            segment="NFO-OPT"
        )

        result = await calculate_cost(request)

        assert result.brokerage == 20.0
        assert result.stt > 0  # STT on sell side
        assert result.stamp_duty == 0.0  # No stamp duty on sell
        assert result.net_cost < result.order_value  # SELL subtracts charges

    @pytest.mark.asyncio
    async def test_calculate_cost_futures(self):
        """Test cost calculation for futures."""
        request = CalculateCostRequest(
            order_value=120000,
            quantity=5,
            price=24000,
            side="BUY",
            segment="NFO-FUT"
        )

        result = await calculate_cost(request)

        # Futures brokerage: 0.03% capped at ₹20
        assert result.brokerage <= 20.0
        assert result.total_charges > 0

    @pytest.mark.asyncio
    async def test_calculate_cost_invalid_segment_raises_error(self):
        """Test that invalid segment raises validation error."""
        with pytest.raises(Exception):  # Pydantic validation error
            CalculateCostRequest(
                order_value=75000,
                quantity=10,
                price=150,
                side="BUY",
                segment="INVALID"
            )


class TestPlaceSmartOrderRouteLogic:
    """Test place_smart_order endpoint logic."""

    @pytest.mark.asyncio
    async def test_place_smart_order_request_model(self, mock_depth_data):
        """Test PlaceSmartOrderRequest model validation."""
        request = PlaceSmartOrderRequest(
            tradingsymbol="NIFTY24NOV24000CE",
            exchange="NFO",
            transaction_type="BUY",
            quantity=10,
            price=150.0,
            depth_data=mock_depth_data,
            last_price=150.25,
            underlying_price=23950,
            segment="NFO-OPT"
        )

        assert request.tradingsymbol == "NIFTY24NOV24000CE"
        assert request.transaction_type == "BUY"
        assert request.skip_validation is False

    @pytest.mark.asyncio
    @patch('app.services.margin_calculator.MarginCalculator.fetch_margin_from_ticker_service')
    @patch('app.services.margin_calculator.MarginCalculator.calculate_margin')
    async def test_place_smart_order_response_structure(
        self, mock_calc_margin, mock_fetch_margin, mock_depth_data
    ):
        """Test place_smart_order returns proper response structure."""
        # Mock margin calculator
        from app.services.margin_calculator import MarginBreakdown
        mock_fetch_margin.return_value = {"total": 30000.0}
        mock_calc_margin.return_value = MarginBreakdown(
            span_margin=15000.0,
            exposure_margin=7500.0,
            premium_margin=7500.0,
            additional_margin=0.0,
            total_margin=30000.0,
            vix_multiplier=1.0,
            expiry_multiplier=1.0,
            price_movement_multiplier=1.0,
            regulatory_multiplier=1.0,
            vix=15.5,
            days_to_expiry=7,
            is_expiry_week=True,
            is_expiry_day=False,
            underlying_price=23950.0,
            strike_price=24000.0
        )

        request = PlaceSmartOrderRequest(
            tradingsymbol="NIFTY24NOV24000CE",
            exchange="NFO",
            transaction_type="BUY",
            quantity=10,
            price=150.0,
            depth_data=mock_depth_data,
            last_price=150.25,
            underlying_price=23950,
            segment="NFO-OPT"
        )

        result = await place_smart_order(request)

        # Check response structure
        assert hasattr(result, 'order_placed')
        assert hasattr(result, 'validation')
        assert hasattr(result, 'margin')
        assert hasattr(result, 'cost')
        assert hasattr(result, 'warnings')

        # Check types
        assert isinstance(result.order_placed, bool)
        assert isinstance(result.warnings, list)

    @pytest.mark.asyncio
    @patch('app.services.margin_calculator.MarginCalculator.fetch_margin_from_ticker_service')
    @patch('app.services.margin_calculator.MarginCalculator.calculate_margin')
    async def test_place_smart_order_with_skip_validation(
        self, mock_calc_margin, mock_fetch_margin, mock_depth_data
    ):
        """Test place_smart_order with skip_validation flag."""
        # Mock margin calculator
        from app.services.margin_calculator import MarginBreakdown
        mock_fetch_margin.return_value = {"total": 30000.0}
        mock_calc_margin.return_value = MarginBreakdown(
            span_margin=15000.0,
            exposure_margin=7500.0,
            premium_margin=7500.0,
            additional_margin=0.0,
            total_margin=30000.0,
            vix_multiplier=1.0,
            expiry_multiplier=1.0,
            price_movement_multiplier=1.0,
            regulatory_multiplier=1.0,
            vix=15.5,
            days_to_expiry=7,
            is_expiry_week=True,
            is_expiry_day=False,
            underlying_price=23950.0,
            strike_price=24000.0
        )

        request = PlaceSmartOrderRequest(
            tradingsymbol="NIFTY24NOV24000CE",
            exchange="NFO",
            transaction_type="BUY",
            quantity=10,
            price=150.0,
            depth_data=mock_depth_data,
            last_price=150.25,
            underlying_price=23950,
            segment="NFO-OPT",
            skip_validation=True
        )

        result = await place_smart_order(request)

        # Should still provide analysis
        assert result.validation is not None
        assert result.cost is not None


class TestRequestResponseModels:
    """Test Pydantic model validation."""

    def test_validate_order_request_defaults(self, mock_depth_data):
        """Test ValidateOrderRequest applies correct defaults."""
        request = ValidateOrderRequest(
            depth_data=mock_depth_data,
            quantity=10,
            side="BUY",
            last_price=150.00
        )

        # Check defaults
        assert request.max_order_spread_pct == 0.5
        assert request.min_liquidity_score == 50
        assert request.require_user_approval_high_impact is True
        assert request.max_market_impact_bps == 50

    def test_calculate_margin_request_defaults(self):
        """Test CalculateMarginRequest applies correct defaults."""
        request = CalculateMarginRequest(
            tradingsymbol="NIFTY24NOV24000CE",
            exchange="NFO",
            transaction_type="BUY",
            quantity=50,
            price=150.0,
            underlying_price=23950.0
        )

        # Check defaults
        assert request.order_type == "MARKET"
        assert request.product == "MIS"
        assert request.account_id == "primary"
        assert request.symbol == "NIFTY"

    def test_place_smart_order_request_defaults(self, mock_depth_data):
        """Test PlaceSmartOrderRequest applies correct defaults."""
        request = PlaceSmartOrderRequest(
            tradingsymbol="NIFTY24NOV24000CE",
            exchange="NFO",
            transaction_type="BUY",
            quantity=10,
            price=150.0,
            depth_data=mock_depth_data,
            last_price=150.25,
            underlying_price=23950
        )

        # Check defaults
        assert request.order_type == "MARKET"
        assert request.product == "MIS"
        assert request.segment == "NFO-OPT"
        assert request.skip_validation is False
