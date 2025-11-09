"""
Smart Order Management API Endpoints

Provides REST API for:
- Order validation with spread/impact analysis
- Margin calculation with dynamic multipliers
- Cost breakdown calculation
- Smart order placement with pre-checks

All endpoints integrate with ticker_service for real-time data.
"""

from typing import Dict, List, Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from datetime import date

from ..services.spread_analyzer import SpreadAnalyzer, StrategySettings as SpreadSettings
from ..services.market_impact_calculator import MarketImpactCalculator
from ..services.execution_decision_engine import ExecutionDecisionEngine
from ..services.margin_calculator import MarginCalculator
from ..services.cost_breakdown_calculator import CostBreakdownCalculator
from ..sdk.exceptions import (
    WideSpreadException,
    HighMarketImpactException,
    InsufficientLiquidityException
)

import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/smart-orders", tags=["smart-orders"])


# ============================================================================
# Request/Response Models
# ============================================================================

class ValidateOrderRequest(BaseModel):
    """Request model for order validation."""
    depth_data: Dict
    quantity: int
    side: str = Field(..., pattern="^(BUY|SELL)$")
    last_price: float
    instrument_token: Optional[int] = None

    # Strategy settings (optional, uses defaults if not provided)
    max_order_spread_pct: float = Field(default=0.5, ge=0, le=10)
    min_liquidity_score: int = Field(default=50, ge=0, le=100)
    require_user_approval_high_impact: bool = True
    max_market_impact_bps: int = Field(default=50, ge=0)


class ValidateOrderResponse(BaseModel):
    """Response model for order validation."""
    can_execute: bool
    requires_user_approval: bool
    recommended_order_type: str
    recommended_limit_price: Optional[float]
    warnings: List[str]
    action_summary: str

    # Detailed analysis
    spread_analysis: Dict
    impact_analysis: Dict


class CalculateMarginRequest(BaseModel):
    """Request model for margin calculation."""
    # For ticker_service API call
    tradingsymbol: str
    exchange: str
    transaction_type: str = Field(..., pattern="^(BUY|SELL)$")
    quantity: int
    price: float
    order_type: str = "MARKET"
    product: str = "MIS"
    account_id: str = "primary"

    # For dynamic multipliers
    symbol: str = "NIFTY"
    underlying_price: float
    strike_price: Optional[float] = None
    option_type: Optional[str] = Field(None, pattern="^(CE|PE)$")
    vix: Optional[float] = None
    expiry_date: Optional[date] = None


class CalculateMarginResponse(BaseModel):
    """Response model for margin calculation."""
    # From Kite API (via ticker_service)
    kite_margin: Optional[Dict] = None

    # Enhanced with dynamic multipliers
    span_margin: float
    exposure_margin: float
    premium_margin: float
    additional_margin: float
    total_margin: float

    # Multipliers applied
    vix_multiplier: float
    expiry_multiplier: float
    price_movement_multiplier: float
    regulatory_multiplier: float

    # Metadata
    vix: float
    days_to_expiry: int
    is_expiry_week: bool
    is_expiry_day: bool


class CalculateCostRequest(BaseModel):
    """Request model for cost calculation."""
    order_value: float
    quantity: int
    price: float
    side: str = Field(..., pattern="^(BUY|SELL)$")
    segment: str = Field(..., pattern="^(NFO-OPT|NFO-FUT|EQUITY-INTRADAY|EQUITY-DELIVERY)$")


class CalculateCostResponse(BaseModel):
    """Response model for cost calculation."""
    order_value: float
    brokerage: float
    stt: float
    exchange_charges: float
    gst: float
    sebi_charges: float
    stamp_duty: float
    total_charges: float
    net_cost: float


class PlaceSmartOrderRequest(BaseModel):
    """Request model for smart order placement."""
    # Order details
    tradingsymbol: str
    exchange: str
    transaction_type: str = Field(..., pattern="^(BUY|SELL)$")
    quantity: int
    price: float
    order_type: str = "MARKET"
    product: str = "MIS"
    variety: str = "regular"
    account_id: str = "primary"

    # For validation
    depth_data: Dict
    last_price: float
    instrument_token: Optional[int] = None

    # For cost/margin calculation
    segment: str = "NFO-OPT"
    symbol: str = "NIFTY"
    underlying_price: float
    strike_price: Optional[float] = None
    option_type: Optional[str] = None
    vix: Optional[float] = None
    expiry_date: Optional[date] = None

    # Settings
    max_order_spread_pct: float = 0.5
    max_market_impact_bps: int = 50
    skip_validation: bool = False  # Allow user to override


class PlaceSmartOrderResponse(BaseModel):
    """Response model for smart order placement."""
    order_placed: bool
    order_id: Optional[str] = None

    # Pre-execution analysis
    validation: ValidateOrderResponse
    margin: Optional[CalculateMarginResponse] = None
    cost: CalculateCostResponse

    # Errors/warnings
    error: Optional[str] = None
    warnings: List[str]


# ============================================================================
# API Endpoints
# ============================================================================

@router.post("/validate", response_model=ValidateOrderResponse)
async def validate_order(request: ValidateOrderRequest) -> ValidateOrderResponse:
    """
    Validate order execution conditions using spread and market impact analysis.

    Returns execution decision with warnings, recommendations, and detailed analysis.
    Does NOT place the order - only validates if it should be placed.

    Example:
        POST /smart-orders/validate
        {
            "depth_data": {"buy": [...], "sell": [...]},
            "quantity": 50,
            "side": "BUY",
            "last_price": 150.25,
            "max_order_spread_pct": 0.5,
            "max_market_impact_bps": 50
        }
    """
    try:
        # Create settings
        settings = SpreadSettings(
            max_order_spread_pct=request.max_order_spread_pct,
            min_liquidity_score=request.min_liquidity_score,
            require_user_approval_high_impact=request.require_user_approval_high_impact,
            max_market_impact_bps=request.max_market_impact_bps
        )

        # Run execution decision engine
        engine = ExecutionDecisionEngine()
        decision = engine.evaluate_order(
            depth_data=request.depth_data,
            quantity=request.quantity,
            side=request.side,
            last_price=request.last_price,
            strategy_settings=settings,
            instrument_token=request.instrument_token,
            raise_exceptions=False  # Return decision object instead of raising
        )

        return ValidateOrderResponse(
            can_execute=decision.can_execute,
            requires_user_approval=decision.requires_user_approval,
            recommended_order_type=decision.recommended_order_type,
            recommended_limit_price=float(decision.recommended_limit_price) if decision.recommended_limit_price else None,
            warnings=decision.warnings,
            action_summary=decision.action_summary,
            spread_analysis=decision.spread_analysis.to_dict(),
            impact_analysis=decision.impact_analysis.to_dict()
        )

    except Exception as e:
        logger.exception("Error validating order")
        raise HTTPException(status_code=500, detail=f"Validation failed: {str(e)}")


@router.post("/calculate-margin", response_model=CalculateMarginResponse)
async def calculate_margin(request: CalculateMarginRequest) -> CalculateMarginResponse:
    """
    Calculate margin requirement with real-time data from Kite API and dynamic multipliers.

    Fetches actual margin from ticker_service (Kite API), then applies dynamic adjustments
    based on VIX, expiry proximity, and price movement.

    Example:
        POST /smart-orders/calculate-margin
        {
            "tradingsymbol": "NIFTY24NOV24000CE",
            "exchange": "NFO",
            "transaction_type": "BUY",
            "quantity": 50,
            "price": 150.0,
            "symbol": "NIFTY",
            "underlying_price": 23950,
            "vix": 15.5
        }
    """
    try:
        calculator = MarginCalculator(ticker_service_url="http://localhost:8080")

        # Fetch real-time margin from ticker_service
        kite_margin = await calculator.fetch_margin_from_ticker_service(
            tradingsymbol=request.tradingsymbol,
            exchange=request.exchange,
            transaction_type=request.transaction_type,
            quantity=request.quantity,
            price=request.price,
            order_type=request.order_type,
            product=request.product,
            account_id=request.account_id
        )

        # Calculate with dynamic multipliers (fallback if Kite unavailable)
        segment = "NFO-OPT" if "CE" in request.tradingsymbol or "PE" in request.tradingsymbol else "NFO-FUT"

        enhanced_margin = calculator.calculate_margin(
            instrument_token=0,  # Not needed for fallback calc
            quantity=request.quantity,
            side=request.transaction_type,
            segment=segment,
            underlying_price=request.underlying_price,
            symbol=request.symbol,
            strike_price=request.strike_price,
            option_type=request.option_type,
            vix=request.vix,
            expiry_date=request.expiry_date
        )

        return CalculateMarginResponse(
            kite_margin=kite_margin,
            span_margin=enhanced_margin.span_margin,
            exposure_margin=enhanced_margin.exposure_margin,
            premium_margin=enhanced_margin.premium_margin,
            additional_margin=enhanced_margin.additional_margin,
            total_margin=enhanced_margin.total_margin,
            vix_multiplier=enhanced_margin.vix_multiplier,
            expiry_multiplier=enhanced_margin.expiry_multiplier,
            price_movement_multiplier=enhanced_margin.price_movement_multiplier,
            regulatory_multiplier=enhanced_margin.regulatory_multiplier,
            vix=enhanced_margin.vix,
            days_to_expiry=enhanced_margin.days_to_expiry,
            is_expiry_week=enhanced_margin.is_expiry_week,
            is_expiry_day=enhanced_margin.is_expiry_day
        )

    except Exception as e:
        logger.exception("Error calculating margin")
        raise HTTPException(status_code=500, detail=f"Margin calculation failed: {str(e)}")


@router.post("/calculate-cost", response_model=CalculateCostResponse)
async def calculate_cost(request: CalculateCostRequest) -> CalculateCostResponse:
    """
    Calculate complete cost breakdown including brokerage, taxes, and charges.

    Uses Zerodha fee structure:
    - Options: ₹20 flat
    - Futures: 0.03% capped at ₹20
    - STT, GST, SEBI charges, stamp duty

    Example:
        POST /smart-orders/calculate-cost
        {
            "order_value": 75000,
            "quantity": 50,
            "price": 150,
            "side": "BUY",
            "segment": "NFO-OPT"
        }
    """
    try:
        calculator = CostBreakdownCalculator()

        cost = calculator.calculate_cost(
            order_value=request.order_value,
            quantity=request.quantity,
            price=request.price,
            side=request.side,
            segment=request.segment
        )

        return CalculateCostResponse(
            order_value=cost.order_value,
            brokerage=cost.brokerage,
            stt=cost.stt,
            exchange_charges=cost.exchange_charges,
            gst=cost.gst,
            sebi_charges=cost.sebi_charges,
            stamp_duty=cost.stamp_duty,
            total_charges=cost.total_charges,
            net_cost=cost.net_cost
        )

    except Exception as e:
        logger.exception("Error calculating cost")
        raise HTTPException(status_code=500, detail=f"Cost calculation failed: {str(e)}")


@router.post("/place", response_model=PlaceSmartOrderResponse)
async def place_smart_order(request: PlaceSmartOrderRequest) -> PlaceSmartOrderResponse:
    """
    Place order with complete pre-execution validation and cost analysis.

    Steps:
    1. Validate execution conditions (spread, market impact)
    2. Calculate margin requirement
    3. Calculate cost breakdown
    4. Place order via ticker_service (if validation passes)

    Returns complete analysis even if order is rejected.

    Example:
        POST /smart-orders/place
        {
            "tradingsymbol": "NIFTY24NOV24000CE",
            "exchange": "NFO",
            "transaction_type": "BUY",
            "quantity": 50,
            "price": 150.0,
            "depth_data": {"buy": [...], "sell": [...]},
            "last_price": 150.25,
            "underlying_price": 23950,
            "segment": "NFO-OPT",
            "skip_validation": false
        }
    """
    warnings = []

    try:
        # Step 1: Validate order
        validation_request = ValidateOrderRequest(
            depth_data=request.depth_data,
            quantity=request.quantity,
            side=request.transaction_type,
            last_price=request.last_price,
            instrument_token=request.instrument_token,
            max_order_spread_pct=request.max_order_spread_pct,
            max_market_impact_bps=request.max_market_impact_bps
        )
        validation = await validate_order(validation_request)

        # Step 2: Calculate margin
        margin_request = CalculateMarginRequest(
            tradingsymbol=request.tradingsymbol,
            exchange=request.exchange,
            transaction_type=request.transaction_type,
            quantity=request.quantity,
            price=request.price,
            order_type=request.order_type,
            product=request.product,
            account_id=request.account_id,
            symbol=request.symbol,
            underlying_price=request.underlying_price,
            strike_price=request.strike_price,
            option_type=request.option_type,
            vix=request.vix,
            expiry_date=request.expiry_date
        )
        margin = await calculate_margin(margin_request)

        # Step 3: Calculate cost
        order_value = request.price * request.quantity * 50  # Assuming lot size 50
        cost_request = CalculateCostRequest(
            order_value=order_value,
            quantity=request.quantity,
            price=request.price,
            side=request.transaction_type,
            segment=request.segment
        )
        cost = await calculate_cost(cost_request)

        # Step 4: Check if we should place order
        should_place = (validation.can_execute and not validation.requires_user_approval) or request.skip_validation

        order_id = None
        error = None

        if should_place:
            # TODO: Call ticker_service to place order
            # For now, return success without actually placing
            # In production, would call: POST http://ticker-service:8080/orders/place
            warnings.append("Order placement not yet integrated with ticker_service - validation only")
            order_id = "SIMULATED_ORDER_ID"
        else:
            error = "Order rejected by validation - user approval required or cannot execute"

        # Combine warnings
        all_warnings = list(set(validation.warnings + warnings))

        return PlaceSmartOrderResponse(
            order_placed=should_place and order_id is not None,
            order_id=order_id,
            validation=validation,
            margin=margin,
            cost=cost,
            error=error,
            warnings=all_warnings
        )

    except Exception as e:
        logger.exception("Error placing smart order")
        raise HTTPException(status_code=500, detail=f"Order placement failed: {str(e)}")
