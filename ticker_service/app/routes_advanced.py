"""
Advanced Order Features API Routes

WebSocket streaming, webhooks, batch orders
"""
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks, Depends, Query
from pydantic import BaseModel, Field, HttpUrl

from .batch_orders import BatchOrderRequest, batch_executor
from .webhooks import WebhookSubscription, webhook_manager
from .websocket_orders import order_stream_manager
from .order_executor import get_executor
from .auth import verify_api_key
from .config import get_settings
from loguru import logger

router = APIRouter(prefix="/advanced", tags=["advanced"])


# ============================================================================
# WebSocket Order Streaming
# ============================================================================

async def _verify_websocket_auth(api_key: str) -> bool:
    """Verify WebSocket API key"""
    settings = get_settings()

    if not settings.api_key_enabled:
        return True  # Auth disabled

    if not api_key:
        return False

    return api_key == settings.api_key


@router.websocket("/ws/orders/{account_id}")
async def websocket_orders(websocket: WebSocket, account_id: str, api_key: str = Query(None)):
    """
    WebSocket endpoint for real-time order updates.

    Connect to receive live updates when orders change status.

    Example (JavaScript):
        const ws = new WebSocket('ws://localhost:8080/advanced/ws/orders/primary?api_key=YOUR_KEY');
        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            console.log('Order update:', data);
        };
    """
    # Verify authentication before accepting connection
    if not await _verify_websocket_auth(api_key):
        await websocket.close(code=1008, reason="Unauthorized")
        logger.warning(f"WebSocket connection rejected for account {account_id}: Invalid API key")
        return

    await order_stream_manager.connect(websocket, account_id)

    try:
        while True:
            # Keep connection alive, client sends ping/pong
            data = await websocket.receive_text()

            if data == "ping":
                order_stream_manager.update_ping(websocket)  # Update heartbeat timestamp
                await websocket.send_text("pong")

    except WebSocketDisconnect:
        await order_stream_manager.disconnect(websocket, account_id)


# ============================================================================
# Webhook Notifications
# ============================================================================

class WebhookCreateRequest(BaseModel):
    url: HttpUrl
    account_id: str
    events: List[str] = Field(
        default=["order_placed", "order_completed", "order_failed"],
        description="Events to subscribe to"
    )
    secret: Optional[str] = Field(None, description="Secret for HMAC verification")


class WebhookResponse(BaseModel):
    webhook_id: str
    url: str
    account_id: str
    events: List[str]
    active: bool
    created_at: datetime


@router.post("/webhooks", response_model=WebhookResponse, status_code=201, dependencies=[Depends(verify_api_key)])
async def create_webhook(payload: WebhookCreateRequest):
    """
    Register a webhook for order notifications.

    Webhook will receive HTTP POST requests when events occur:
        POST <your_url>
        Content-Type: application/json
        X-Webhook-Secret: <your_secret>

        {
            "event": "order_completed",
            "account_id": "primary",
            "data": { ... },
            "timestamp": "2025-10-31T..."
        }
    """
    import uuid
    import httpx
    from urllib.parse import urlparse

    # Validate URL is not internal (SSRF protection)
    parsed = urlparse(str(payload.url))

    # Block localhost and private IPs
    blocked_hosts = ['localhost', '127.0.0.1', '0.0.0.0']
    if parsed.hostname in blocked_hosts or (parsed.hostname and parsed.hostname.startswith('192.168.')):
        raise HTTPException(status_code=400, detail="Internal URLs are not allowed for webhooks")

    # Block private IP ranges
    if parsed.hostname and (
        parsed.hostname.startswith('10.') or
        parsed.hostname.startswith('172.16.') or
        parsed.hostname.startswith('172.17.') or
        parsed.hostname.startswith('172.18.') or
        parsed.hostname.startswith('172.19.') or
        parsed.hostname.startswith('172.20.') or
        parsed.hostname.startswith('172.21.') or
        parsed.hostname.startswith('172.22.') or
        parsed.hostname.startswith('172.23.') or
        parsed.hostname.startswith('172.24.') or
        parsed.hostname.startswith('172.25.') or
        parsed.hostname.startswith('172.26.') or
        parsed.hostname.startswith('172.27.') or
        parsed.hostname.startswith('172.28.') or
        parsed.hostname.startswith('172.29.') or
        parsed.hostname.startswith('172.30.') or
        parsed.hostname.startswith('172.31.')
    ):
        raise HTTPException(status_code=400, detail="Private network URLs are not allowed for webhooks")

    # Validate webhook endpoint is accessible (test connection)
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.head(str(payload.url))
            # Accept any response (including 404) as long as connection succeeds
    except httpx.ConnectError:
        raise HTTPException(status_code=400, detail=f"Webhook URL is not accessible: Connection failed")
    except httpx.TimeoutException:
        raise HTTPException(status_code=400, detail=f"Webhook URL is not accessible: Connection timeout")
    except Exception as e:
        logger.warning(f"Webhook URL validation encountered error (accepting anyway): {e}")
        # Don't fail on other errors (like SSL, redirects, etc.)

    # Validate events
    valid_events = {"order_placed", "order_completed", "order_failed", "order_cancelled", "order_rejected"}
    invalid_events = set(payload.events) - valid_events
    if invalid_events:
        raise HTTPException(status_code=400, detail=f"Invalid events: {invalid_events}. Valid events: {valid_events}")

    # Count existing webhooks for account (limit to 10 per account)
    existing_webhooks = webhook_manager.list_subscriptions(payload.account_id)
    if len(existing_webhooks) >= 10:
        raise HTTPException(status_code=400, detail=f"Maximum webhook limit (10) reached for account '{payload.account_id}'")

    subscription = WebhookSubscription(
        webhook_id=str(uuid.uuid4()),
        url=str(payload.url),
        account_id=payload.account_id,
        events=payload.events,
        secret=payload.secret
    )

    webhook_manager.register(subscription)

    return WebhookResponse(
        webhook_id=subscription.webhook_id,
        url=subscription.url,
        account_id=subscription.account_id,
        events=subscription.events,
        active=subscription.active,
        created_at=subscription.created_at
    )


@router.get("/webhooks", response_model=List[WebhookResponse], dependencies=[Depends(verify_api_key)])
async def list_webhooks(account_id: Optional[str] = None):
    """List registered webhooks"""
    subscriptions = webhook_manager.list_subscriptions(account_id)

    return [
        WebhookResponse(
            webhook_id=sub.webhook_id,
            url=sub.url,
            account_id=sub.account_id,
            events=sub.events,
            active=sub.active,
            created_at=sub.created_at
        )
        for sub in subscriptions
    ]


@router.delete("/webhooks/{webhook_id}", dependencies=[Depends(verify_api_key)])
async def delete_webhook(webhook_id: str):
    """Unregister a webhook"""
    success = webhook_manager.unregister(webhook_id)

    if not success:
        raise HTTPException(status_code=404, detail="Webhook not found")

    return {"success": True, "webhook_id": webhook_id}


# ============================================================================
# Batch Order Execution
# ============================================================================

class BatchOrdersRequest(BaseModel):
    orders: List[BatchOrderRequest]
    account_id: str = "primary"
    rollback_on_failure: bool = Field(
        default=True,
        description="Cancel all orders if any fails"
    )


class BatchOrdersResponse(BaseModel):
    batch_id: str
    success: bool
    total_orders: int
    succeeded: int
    failed: int
    created_at: datetime
    completed_at: Optional[datetime]
    error: Optional[str]


@router.post("/batch-orders", response_model=BatchOrdersResponse, status_code=201, dependencies=[Depends(verify_api_key)])
async def execute_batch_orders(payload: BatchOrdersRequest):
    """
    Execute multiple orders atomically.

    If rollback_on_failure=true, all successfully placed orders
    will be cancelled if any order fails.

    Example:
        POST /advanced/batch-orders
        {
            "orders": [
                {
                    "exchange": "NFO",
                    "tradingsymbol": "NIFTY25NOVFUT",
                    "transaction_type": "BUY",
                    "quantity": 50,
                    "product": "NRML",
                    "order_type": "MARKET"
                },
                {
                    "exchange": "NFO",
                    "tradingsymbol": "BANKNIFTY25NOVFUT",
                    "transaction_type": "BUY",
                    "quantity": 25,
                    "product": "NRML",
                    "order_type": "MARKET"
                }
            ],
            "account_id": "primary",
            "rollback_on_failure": true
        }
    """
    # Validate batch size
    if len(payload.orders) == 0:
        raise HTTPException(status_code=400, detail="Batch must contain at least one order")

    if len(payload.orders) > 20:
        raise HTTPException(status_code=400, detail=f"Batch size {len(payload.orders)} exceeds maximum of 20 orders")

    # Validate each order
    for idx, order in enumerate(payload.orders):
        if order.quantity <= 0:
            raise HTTPException(status_code=400, detail=f"Order {idx}: Quantity must be positive")

        if order.transaction_type not in ("BUY", "SELL"):
            raise HTTPException(status_code=400, detail=f"Order {idx}: transaction_type must be BUY or SELL")

        if order.order_type not in ("MARKET", "LIMIT", "SL", "SL-M"):
            raise HTTPException(status_code=400, detail=f"Order {idx}: Invalid order_type '{order.order_type}'")

        if order.order_type == "LIMIT" and not order.price:
            raise HTTPException(status_code=400, detail=f"Order {idx}: LIMIT orders require a price")

        if order.order_type in ("SL", "SL-M") and not order.trigger_price:
            raise HTTPException(status_code=400, detail=f"Order {idx}: Stop-loss orders require a trigger_price")

    # Validate account exists (import ticker_loop from generator module)
    from .generator import ticker_loop
    accounts = ticker_loop.list_accounts()
    if payload.account_id not in accounts:
        raise HTTPException(status_code=400, detail=f"Account '{payload.account_id}' not found")

    executor = get_executor()

    try:
        result = await batch_executor.execute_batch(
            orders=payload.orders,
            account_id=payload.account_id,
            executor=executor,
            rollback_on_failure=payload.rollback_on_failure
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return BatchOrdersResponse(
        batch_id=result.batch_id,
        success=result.success,
        total_orders=result.total_orders,
        succeeded=result.succeeded,
        failed=result.failed,
        created_at=result.created_at,
        completed_at=result.completed_at,
        error=result.error
    )


# ============================================================================
# WebSocket Connection Status
# ============================================================================

@router.get("/ws/stats")
async def websocket_stats():
    """Get WebSocket connection statistics"""
    return {
        "total_connections": order_stream_manager.get_connection_count()
    }
