"""
Trading Accounts API Routes - Sprint 4
Endpoints for managing trading accounts, positions, orders, holdings, and funds.
"""

from fastapi import APIRouter, Depends, Query, HTTPException, Body
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, validator
import logging

from ..services.account_service import AccountService
from ..database import DataManager
from ..config import get_settings
from .indicators import get_data_manager


settings = get_settings()


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/accounts", tags=["accounts"])


# ============================================================================
# Dependency: AccountService
# ============================================================================

_account_service: Optional[AccountService] = None


async def get_account_service(dm: DataManager = Depends(get_data_manager)) -> AccountService:
    """Get or create AccountService instance."""
    global _account_service
    if _account_service is None:
        ticker_url = settings.ticker_service_url
        _account_service = AccountService(dm, ticker_url)
        logger.info(f"AccountService initialized with ticker_url={ticker_url}")
    return _account_service


async def cleanup_account_service():
    """Cleanup AccountService resources on shutdown."""
    global _account_service
    if _account_service is not None:
        await _account_service.close()
        logger.info("AccountService HTTP client closed")
        _account_service = None


# ============================================================================
# Request/Response Models
# ============================================================================

class OrderRequest(BaseModel):
    """Request model for placing an order with validation."""
    tradingsymbol: str = Field(..., min_length=1, max_length=50, description="Trading symbol")
    exchange: str = Field(..., description="Exchange (NSE, NFO, etc.)")
    transaction_type: str = Field(..., description="BUY or SELL")
    quantity: int = Field(..., gt=0, le=10000, description="Order quantity (max 10,000)")
    order_type: str = Field(default="MARKET", description="MARKET, LIMIT, SL, SL-M")
    product: str = Field(default="MIS", description="MIS, NRML, CNC")
    price: Optional[float] = Field(None, gt=0, le=1000000, description="Limit price (for LIMIT/SL orders)")
    trigger_price: Optional[float] = Field(None, gt=0, le=1000000, description="Trigger price (for SL/SL-M orders)")
    validity: Optional[str] = Field("DAY", description="Order validity (DAY, IOC)")
    disclosed_quantity: Optional[int] = Field(None, gt=0, le=10000, description="Disclosed quantity for iceberg orders")
    tag: Optional[str] = Field(None, max_length=20, description="Order tag for tracking")

    @validator('exchange')
    def validate_exchange(cls, v):
        """Validate exchange is one of the allowed values."""
        allowed_exchanges = {'NSE', 'NFO', 'BSE', 'BFO', 'MCX'}
        if v.upper() not in allowed_exchanges:
            raise ValueError(f'Exchange must be one of: {", ".join(allowed_exchanges)}')
        return v.upper()

    @validator('transaction_type')
    def validate_transaction_type(cls, v):
        """Validate transaction type is BUY or SELL."""
        if v.upper() not in {'BUY', 'SELL'}:
            raise ValueError('Transaction type must be BUY or SELL')
        return v.upper()

    @validator('order_type')
    def validate_order_type(cls, v):
        """Validate order type is one of the allowed values."""
        allowed_types = {'MARKET', 'LIMIT', 'SL', 'SL-M'}
        if v.upper() not in allowed_types:
            raise ValueError(f'Order type must be one of: {", ".join(allowed_types)}')
        return v.upper()

    @validator('product')
    def validate_product(cls, v):
        """Validate product type is one of the allowed values."""
        allowed_products = {'MIS', 'NRML', 'CNC'}
        if v.upper() not in allowed_products:
            raise ValueError(f'Product must be one of: {", ".join(allowed_products)}')
        return v.upper()

    @validator('validity')
    def validate_validity(cls, v):
        """Validate order validity."""
        if v and v.upper() not in {'DAY', 'IOC'}:
            raise ValueError('Validity must be DAY or IOC')
        return v.upper() if v else 'DAY'

    @validator('price')
    def validate_price_for_order_type(cls, v, values):
        """Validate price is provided for LIMIT and SL orders."""
        order_type = values.get('order_type', '').upper()
        if order_type in {'LIMIT', 'SL'} and v is None:
            raise ValueError(f'Price is required for {order_type} orders')
        return v

    @validator('trigger_price')
    def validate_trigger_price_for_order_type(cls, v, values):
        """Validate trigger price is provided for SL and SL-M orders."""
        order_type = values.get('order_type', '').upper()
        if order_type in {'SL', 'SL-M'} and v is None:
            raise ValueError(f'Trigger price is required for {order_type} orders')
        return v


class SyncRequest(BaseModel):
    """Request model for syncing account data."""
    force: bool = Field(default=False, description="Force sync even if recently synced")


class BatchOrderRequest(BaseModel):
    """Request model for placing multiple orders atomically."""
    orders: List[OrderRequest] = Field(..., min_items=1, max_items=10, description="List of orders to place")
    rollback_on_failure: bool = Field(default=True, description="Cancel all orders if any fails")

    @validator('orders')
    def validate_orders_count(cls, v):
        """Validate order count is within limits."""
        if len(v) > 10:
            raise ValueError('Maximum 10 orders per batch')
        if len(v) == 0:
            raise ValueError('At least 1 order required')
        return v


# ============================================================================
# Trading Accounts Endpoints
# ============================================================================

@router.get("")
async def list_accounts(
    user_id: Optional[str] = Query(None, description="Filter by user_id"),
    service: AccountService = Depends(get_account_service)
) -> Dict[str, Any]:
    """
    List all trading accounts with aggregated metrics.

    Returns accounts with:
    - Account info (id, name, broker, status)
    - Aggregated P&L
    - Position count
    - Available margin
    """
    try:
        accounts = await service.list_accounts(user_id)
        return {
            "status": "success",
            "count": len(accounts),
            "accounts": accounts
        }
    except Exception as e:
        logger.error(f"Error listing accounts: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{account_id}")
async def get_account(
    account_id: str,
    service: AccountService = Depends(get_account_service)
) -> Dict[str, Any]:
    """
    Get details for a specific trading account.

    Args:
        account_id: Account identifier (user_id)

    Returns:
        Account details with metrics
    """
    try:
        account = await service.get_account(account_id)
        if not account:
            raise HTTPException(status_code=404, detail=f"Account {account_id} not found")

        return {
            "status": "success",
            "account": account
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting account {account_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{account_id}/sync")
async def sync_account(
    account_id: str,
    request: SyncRequest = Body(default=SyncRequest()),
    service: AccountService = Depends(get_account_service)
) -> Dict[str, Any]:
    """
    Sync account data from ticker_service.

    Fetches and caches:
    - Positions
    - Holdings
    - Orders
    - Funds/Margins

    Args:
        account_id: Account identifier (user_id)
        request: Sync options

    Returns:
        Sync status with counts
    """
    try:
        result = await service.sync_account(account_id)
        return {
            "status": "success" if result.get("success") else "error",
            **result
        }
    except Exception as e:
        logger.error(f"Error syncing account {account_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Positions Endpoints
# ============================================================================

@router.get("/{account_id}/positions")
async def get_positions(
    account_id: str,
    fresh: bool = Query(False, description="Fetch fresh data from ticker_service"),
    service: AccountService = Depends(get_account_service)
) -> Dict[str, Any]:
    """
    Get positions for an account.

    Args:
        account_id: Account identifier
        fresh: If true, fetches fresh data from ticker_service

    Returns:
        List of positions with P&L
    """
    try:
        positions = await service.get_positions(account_id, fresh=fresh)

        # Calculate totals
        total_pnl = sum(p.get("pnl", 0) for p in positions)
        day_pnl = sum(p.get("day_pnl", 0) for p in positions)

        return {
            "status": "success",
            "account_id": account_id,
            "count": len(positions),
            "total_pnl": total_pnl,
            "day_pnl": day_pnl,
            "positions": positions
        }
    except Exception as e:
        logger.error(f"Error getting positions for {account_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Orders Endpoints
# ============================================================================

@router.get("/{account_id}/orders")
async def get_orders(
    account_id: str,
    status: Optional[str] = Query(None, description="Filter by status (OPEN, COMPLETE, etc.)"),
    limit: int = Query(100, ge=1, le=1000, description="Max orders to return"),
    service: AccountService = Depends(get_account_service)
) -> Dict[str, Any]:
    """
    Get orders for an account.

    Args:
        account_id: Account identifier
        status: Optional status filter
        limit: Max orders to return

    Returns:
        List of orders
    """
    try:
        orders = await service.get_orders(account_id, status=status, limit=limit)
        return {
            "status": "success",
            "account_id": account_id,
            "count": len(orders),
            "orders": orders
        }
    except Exception as e:
        logger.error(f"Error getting orders for {account_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{account_id}/orders")
async def place_order(
    account_id: str,
    order: OrderRequest,
    service: AccountService = Depends(get_account_service)
) -> Dict[str, Any]:
    """
    Place a new order.

    Args:
        account_id: Account identifier (user_id)
        order: Order parameters

    Returns:
        Order result with order_id
    """
    try:
        result = await service.place_order(
            account_id=account_id,
            tradingsymbol=order.tradingsymbol,
            exchange=order.exchange,
            transaction_type=order.transaction_type,
            quantity=order.quantity,
            order_type=order.order_type,
            product=order.product,
            price=order.price,
            trigger_price=order.trigger_price,
            validity=order.validity,
            disclosed_quantity=order.disclosed_quantity,
            tag=order.tag
        )

        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "Order placement failed"))

        return {
            "status": "success",
            "account_id": account_id,
            **result
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error placing order for {account_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{account_id}/batch-orders")
async def place_batch_orders(
    account_id: str,
    batch_request: BatchOrderRequest,
    service: AccountService = Depends(get_account_service)
) -> Dict[str, Any]:
    """
    Place multiple orders atomically (all-or-nothing execution).

    This endpoint allows placing multiple orders simultaneously with automatic
    rollback if any order fails. Ideal for multi-leg strategies like:
    - Option spreads (bull call spread, bear put spread)
    - Iron condors (4-leg position)
    - Straddles/Strangles (buy call + put)
    - Portfolio rebalancing

    Args:
        account_id: Account identifier (user_id)
        batch_request: Batch order specification with rollback flag

    Returns:
        Batch execution result with order IDs and status

    Example Request:
        {
            "orders": [
                {
                    "tradingsymbol": "NIFTY25NOVFUT",
                    "exchange": "NFO",
                    "transaction_type": "BUY",
                    "quantity": 50,
                    "order_type": "MARKET",
                    "product": "NRML"
                },
                {
                    "tradingsymbol": "BANKNIFTY25NOVFUT",
                    "exchange": "NFO",
                    "transaction_type": "SELL",
                    "quantity": 25,
                    "order_type": "LIMIT",
                    "product": "NRML",
                    "price": 45500.0
                }
            ],
            "rollback_on_failure": true
        }

    Example Response:
        {
            "status": "success",
            "batch_id": "550e8400-e29b-41d4-a716-446655440000",
            "total_orders": 2,
            "succeeded": 2,
            "failed": 0,
            "order_ids": ["230405000123456", "230405000123457"]
        }
    """
    try:
        # Convert OrderRequest models to dicts
        orders_data = []
        for order in batch_request.orders:
            order_dict = {
                "tradingsymbol": order.tradingsymbol,
                "exchange": order.exchange,
                "transaction_type": order.transaction_type,
                "quantity": order.quantity,
                "order_type": order.order_type,
                "product": order.product,
            }
            if order.price is not None:
                order_dict["price"] = order.price
            if order.trigger_price is not None:
                order_dict["trigger_price"] = order.trigger_price
            if order.validity:
                order_dict["validity"] = order.validity
            if order.disclosed_quantity is not None:
                order_dict["disclosed_quantity"] = order.disclosed_quantity
            if order.tag:
                order_dict["tag"] = order.tag

            orders_data.append(order_dict)

        # Place batch orders via service
        result = await service.place_batch_orders(
            account_id=account_id,
            orders=orders_data,
            rollback_on_failure=batch_request.rollback_on_failure
        )

        if not result.get("success"):
            raise HTTPException(
                status_code=400,
                detail=result.get("error", "Batch order placement failed")
            )

        return {
            "status": "success",
            "account_id": account_id,
            **result
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error placing batch orders for {account_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Holdings Endpoints
# ============================================================================

@router.get("/{account_id}/holdings")
async def get_holdings(
    account_id: str,
    service: AccountService = Depends(get_account_service)
) -> Dict[str, Any]:
    """
    Get holdings (delivery positions) for an account.

    Args:
        account_id: Account identifier

    Returns:
        List of holdings with P&L
    """
    try:
        holdings = await service.get_holdings(account_id)

        # Calculate totals
        total_pnl = sum(h.get("pnl", 0) for h in holdings)
        total_value = sum(h.get("last_price", 0) * h.get("quantity", 0) for h in holdings)

        return {
            "status": "success",
            "account_id": account_id,
            "count": len(holdings),
            "total_pnl": total_pnl,
            "total_value": total_value,
            "holdings": holdings
        }
    except Exception as e:
        logger.error(f"Error getting holdings for {account_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Funds/Margins Endpoints
# ============================================================================

@router.get("/{account_id}/funds")
async def get_funds(
    account_id: str,
    segment: str = Query("equity", description="Segment: equity or commodity"),
    service: AccountService = Depends(get_account_service)
) -> Dict[str, Any]:
    """
    Get funds/margins for an account.

    Args:
        account_id: Account identifier
        segment: equity or commodity

    Returns:
        Funds information
    """
    try:
        funds = await service.get_funds(account_id, segment=segment)
        if not funds:
            raise HTTPException(status_code=404, detail=f"Funds not found for account {account_id}")

        return {
            "status": "success",
            "account_id": account_id,
            "funds": funds
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting funds for {account_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Health Check
# ============================================================================

@router.get("/health/status")
async def health_check() -> Dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok", "service": "accounts"}
