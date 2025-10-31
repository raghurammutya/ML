"""
Pydantic models for Kite Connect API requests and responses
"""
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# ------------------------------------------------------------------ Order Management Models
class PlaceOrderRequest(BaseModel):
    exchange: str = Field(..., description="Exchange (NSE, BSE, NFO, etc.)")
    tradingsymbol: str = Field(..., description="Trading symbol")
    transaction_type: str = Field(..., description="Transaction type (BUY or SELL)")
    quantity: int = Field(..., description="Order quantity", gt=0)
    product: str = Field(..., description="Product type (CNC, NRML, MIS)")
    order_type: str = Field(..., description="Order type (LIMIT, MARKET, SL, SL-M)")
    variety: str = Field(default="regular", description="Order variety (regular, amo, co, iceberg)")
    price: Optional[float] = Field(None, description="Order price for LIMIT orders")
    trigger_price: Optional[float] = Field(None, description="Trigger price for SL orders")
    validity: str = Field(default="DAY", description="Order validity (DAY, IOC)")
    disclosed_quantity: Optional[int] = Field(None, description="Disclosed quantity for iceberg orders")
    squareoff: Optional[float] = Field(None, description="Square off value for CO orders")
    stoploss: Optional[float] = Field(None, description="Stoploss value for CO/BO orders")
    trailing_stoploss: Optional[float] = Field(None, description="Trailing stoploss for BO orders")
    tag: Optional[str] = Field(None, description="Custom tag for order")
    account_id: str = Field(default="primary", description="Account ID to use")


class ModifyOrderRequest(BaseModel):
    variety: str = Field(..., description="Order variety")
    order_id: str = Field(..., description="Order ID to modify")
    quantity: Optional[int] = Field(None, description="New quantity")
    price: Optional[float] = Field(None, description="New price")
    order_type: Optional[str] = Field(None, description="New order type")
    trigger_price: Optional[float] = Field(None, description="New trigger price")
    validity: Optional[str] = Field(None, description="New validity")
    disclosed_quantity: Optional[int] = Field(None, description="New disclosed quantity")
    parent_order_id: Optional[str] = Field(None, description="Parent order ID for CO/BO")
    account_id: str = Field(default="primary", description="Account ID to use")


class CancelOrderRequest(BaseModel):
    variety: str = Field(..., description="Order variety")
    order_id: str = Field(..., description="Order ID to cancel")
    parent_order_id: Optional[str] = Field(None, description="Parent order ID for CO/BO")
    account_id: str = Field(default="primary", description="Account ID to use")


class ExitOrderRequest(BaseModel):
    variety: str = Field(..., description="Order variety (co or bo)")
    order_id: str = Field(..., description="Order ID to exit")
    parent_order_id: Optional[str] = Field(None, description="Parent order ID")
    account_id: str = Field(default="primary", description="Account ID to use")


class OrderResponse(BaseModel):
    order_id: str
    task_id: Optional[str] = None  # For tracked orders


class OrderTaskResponse(BaseModel):
    task_id: str
    idempotency_key: str
    operation: str
    status: str
    attempts: int
    max_attempts: int
    created_at: datetime
    updated_at: datetime
    last_error: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    account_id: str


class OrderMarginRequest(BaseModel):
    exchange: str
    tradingsymbol: str
    transaction_type: str
    variety: str
    product: str
    order_type: str
    quantity: int
    price: Optional[float] = None
    trigger_price: Optional[float] = None


class BasketOrderMarginRequest(BaseModel):
    orders: List[OrderMarginRequest]
    consider_positions: bool = Field(default=True)
    account_id: str = Field(default="primary")


# ------------------------------------------------------------------ Portfolio Models
class ConvertPositionRequest(BaseModel):
    exchange: str
    tradingsymbol: str
    transaction_type: str
    position_type: str
    quantity: int
    old_product: str
    new_product: str
    account_id: str = Field(default="primary")


# ------------------------------------------------------------------ GTT Models
class GTTOrderDetails(BaseModel):
    exchange: str
    tradingsymbol: str
    transaction_type: str
    quantity: int
    order_type: str
    product: str
    price: Optional[float] = None


class PlaceGTTRequest(BaseModel):
    trigger_type: str = Field(..., description="GTT trigger type (single or two-leg)")
    tradingsymbol: str
    exchange: str
    trigger_values: List[float] = Field(..., description="Trigger price levels")
    last_price: float
    orders: List[GTTOrderDetails]
    account_id: str = Field(default="primary")


class ModifyGTTRequest(BaseModel):
    gtt_id: int
    trigger_type: str
    tradingsymbol: str
    exchange: str
    trigger_values: List[float]
    last_price: float
    orders: List[GTTOrderDetails]
    account_id: str = Field(default="primary")


class DeleteGTTRequest(BaseModel):
    gtt_id: int
    account_id: str = Field(default="primary")


class GTTTriggerRangeRequest(BaseModel):
    transaction_type: str
    exchange: str
    tradingsymbol: str
    account_id: str = Field(default="primary")


# ------------------------------------------------------------------ Mutual Funds Models
class PlaceMFOrderRequest(BaseModel):
    tradingsymbol: str
    transaction_type: str
    amount: Optional[float] = Field(None, description="Amount for purchase (mutual exclusive with quantity)")
    quantity: Optional[float] = Field(None, description="Quantity for redemption (mutual exclusive with amount)")
    tag: Optional[str] = None
    account_id: str = Field(default="primary")


class CancelMFOrderRequest(BaseModel):
    order_id: str
    account_id: str = Field(default="primary")


class PlaceMFSIPRequest(BaseModel):
    tradingsymbol: str
    amount: float
    frequency: str = Field(..., description="SIP frequency (weekly, monthly, quarterly)")
    initial_amount: Optional[float] = None
    installments: Optional[int] = None
    installment_day: Optional[int] = Field(None, description="Day of month for SIP installment")
    tag: Optional[str] = None
    account_id: str = Field(default="primary")


class ModifyMFSIPRequest(BaseModel):
    sip_id: str
    amount: Optional[float] = None
    frequency: Optional[str] = None
    installments: Optional[int] = None
    installment_day: Optional[int] = None
    status: Optional[str] = Field(None, description="active or paused")
    account_id: str = Field(default="primary")


class CancelMFSIPRequest(BaseModel):
    sip_id: str
    account_id: str = Field(default="primary")


# ------------------------------------------------------------------ Session Management Models
class InvalidateRefreshTokenRequest(BaseModel):
    refresh_token: str
    account_id: str = Field(default="primary")


class RenewAccessTokenRequest(BaseModel):
    refresh_token: str
    api_secret: str
    account_id: str = Field(default="primary")


# ------------------------------------------------------------------ Common Models
class AccountRequest(BaseModel):
    account_id: str = Field(default="primary")


class MarginSegmentRequest(BaseModel):
    segment: Optional[str] = Field(None, description="equity or commodity")
    account_id: str = Field(default="primary")
