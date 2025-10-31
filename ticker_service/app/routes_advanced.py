"""
Advanced Order Features API Routes

WebSocket streaming, webhooks, batch orders
"""
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks, Depends, Query, Request
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


# ============================================================================
# Mock Data Control
# ============================================================================

@router.post("/mock-data/enable", dependencies=[Depends(verify_api_key)])
async def enable_mock_data():
    """
    Enable mock data generation outside market hours.

    When enabled, the ticker service will generate simulated market data
    when markets are closed (outside of market_open_time to market_close_time).

    This is useful for:
    - Testing and development outside market hours
    - Demo environments
    - Continuous data flow for UI testing

    Returns:
        {
            "success": true,
            "mock_data_enabled": true,
            "message": "Mock data generation enabled"
        }
    """
    from .config import get_settings

    settings = get_settings()
    settings.enable_mock_data = True

    logger.info("Mock data generation enabled via API")

    return {
        "success": True,
        "mock_data_enabled": True,
        "message": "Mock data generation enabled. Simulated data will be published outside market hours."
    }


@router.post("/mock-data/disable", dependencies=[Depends(verify_api_key)])
async def disable_mock_data():
    """
    Disable mock data generation outside market hours.

    When disabled, the ticker service will NOT generate any data outside market hours.
    Only real market data during trading hours will be published.

    Use this in production to ensure only real market data is used.

    Returns:
        {
            "success": true,
            "mock_data_enabled": false,
            "message": "Mock data generation disabled"
        }
    """
    from .config import get_settings

    settings = get_settings()
    settings.enable_mock_data = False

    logger.info("Mock data generation disabled via API")

    return {
        "success": True,
        "mock_data_enabled": False,
        "message": "Mock data generation disabled. No data will be published outside market hours."
    }


@router.get("/mock-data/status")
async def get_mock_data_status():
    """
    Get current mock data generation status.

    Returns the current state of mock data generation and market hours information.

    Returns:
        {
            "mock_data_enabled": true,
            "market_hours": {
                "open": "09:15",
                "close": "15:30",
                "timezone": "Asia/Kolkata"
            },
            "is_market_hours": false
        }
    """
    from .config import get_settings
    from .generator import ticker_loop

    settings = get_settings()

    # Get current market hours status
    is_market_hours = ticker_loop._is_market_hours() if hasattr(ticker_loop, '_is_market_hours') else None

    return {
        "mock_data_enabled": settings.enable_mock_data,
        "market_hours": {
            "open": settings.market_open_time.strftime("%H:%M"),
            "close": settings.market_close_time.strftime("%H:%M"),
            "timezone": settings.market_timezone
        },
        "is_market_hours": is_market_hours,
        "mock_config": {
            "price_variation_bps": settings.mock_price_variation_bps,
            "volume_variation": settings.mock_volume_variation,
            "history_minutes": settings.mock_history_minutes
        }
    }


# ============================================================================
# Backpressure Monitoring & Control
# ============================================================================

@router.get("/backpressure/status")
async def get_backpressure_status():
    """
    Get current backpressure status and metrics.

    Returns:
        {
            "backpressure_level": "healthy" | "warning" | "critical" | "overload",
            "health_status": "healthy" | "degraded",
            "ingestion_rate": "1234.5 ticks/sec",
            "publish_rate": "1234.5 ticks/sec",
            "rate_ratio": "100.00%",
            "avg_latency": "1.23 ms",
            "p99_latency": "5.67 ms",
            "pending_publishes": 123,
            "dropped_messages": 0,
            "redis_errors": 0,
            "memory_usage": "512.3 MB",
            "cpu_usage": "45.6%",
            "timestamp": "2025-10-31T..."
        }
    """
    from .backpressure_monitor import get_backpressure_monitor

    monitor = get_backpressure_monitor()
    return monitor.get_status_summary()


@router.get("/backpressure/metrics")
async def get_backpressure_metrics():
    """
    Get detailed backpressure metrics.

    Returns full BackpressureMetrics object with all measurements.
    """
    from .backpressure_monitor import get_backpressure_monitor

    monitor = get_backpressure_monitor()
    metrics = monitor.get_metrics()

    return {
        "ticks_received_per_sec": metrics.ticks_received_per_sec,
        "ticks_published_per_sec": metrics.ticks_published_per_sec,
        "avg_publish_latency_ms": metrics.avg_publish_latency_ms,
        "p95_publish_latency_ms": metrics.p95_publish_latency_ms,
        "p99_publish_latency_ms": metrics.p99_publish_latency_ms,
        "pending_publishes": metrics.pending_publishes,
        "dropped_messages": metrics.dropped_messages,
        "redis_publish_errors": metrics.redis_publish_errors,
        "redis_connection_errors": metrics.redis_connection_errors,
        "memory_usage_mb": metrics.memory_usage_mb,
        "cpu_usage_percent": metrics.cpu_usage_percent,
        "backpressure_level": metrics.backpressure_level.value,
        "ingestion_rate_ratio": metrics.ingestion_rate_ratio,
        "timestamp": metrics.timestamp.isoformat()
    }


@router.get("/backpressure/circuit-breaker")
async def get_circuit_breaker_status():
    """
    Get Redis circuit breaker status.

    Returns:
        {
            "state": "closed" | "open" | "half_open",
            "failure_count": 0,
            "last_failure_time": "2025-10-31T..." | null
        }
    """
    from .redis_publisher_v2 import get_resilient_publisher

    try:
        publisher = get_resilient_publisher()
        cb = publisher.circuit_breaker

        return {
            "state": cb.state.value,
            "failure_count": cb.failure_count,
            "success_count": cb.success_count,
            "last_failure_time": cb.last_failure_time
        }
    except Exception:
        # V2 publisher not initialized - return N/A
        return {
            "state": "unknown",
            "message": "Resilient publisher not initialized"
        }


@router.get("/backpressure/publisher-stats")
async def get_publisher_stats():
    """
    Get Redis publisher statistics.

    Returns:
        {
            "total_published": 12345,
            "total_dropped": 0,
            "total_sampled_out": 123,
            "buffer_size": 45,
            "buffer_capacity": 10000,
            "circuit_breaker_state": "closed",
            "circuit_breaker_failures": 0,
            "backpressure_metrics": { ... }
        }
    """
    from .redis_publisher_v2 import get_resilient_publisher

    try:
        publisher = get_resilient_publisher()
        return publisher.get_stats()
    except Exception as e:
        return {
            "error": "Resilient publisher not initialized",
            "message": str(e)
        }


@router.post("/backpressure/reset-circuit-breaker", dependencies=[Depends(verify_api_key)])
async def reset_circuit_breaker(request: Request):
    """
    Manually reset the circuit breaker to CLOSED state.

    Use this to force-reopen a circuit after fixing underlying issues.

    Requires API key authentication.
    Rate limited to 5 requests per minute to prevent abuse.
    """
    from .redis_publisher_v2 import get_resilient_publisher, CircuitState

    # Apply rate limiting (5 requests per minute for this sensitive endpoint)
    limiter = request.app.state.limiter
    await limiter.limit("5/minute")(request)

    try:
        publisher = get_resilient_publisher()

        # Use thread-safe state mutation
        with publisher.circuit_breaker._lock:
            publisher.circuit_breaker.state = CircuitState.CLOSED
            publisher.circuit_breaker.failure_count = 0
            publisher.circuit_breaker.success_count = 0

        logger.info("Circuit breaker manually reset to CLOSED state")

        return {
            "success": True,
            "message": "Circuit breaker reset to CLOSED state",
            "new_state": "closed"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to reset circuit breaker: {e}")


# ============================================================================
# Kite API Rate Limiting
# ============================================================================

@router.get("/rate-limit/stats")
async def get_rate_limit_stats():
    """
    Get Kite API rate limiting statistics.

    Returns statistics for all rate-limited endpoints including:
    - Total requests made
    - Total wait time due to rate limiting
    - Current usage per endpoint (per-minute and per-day counters)
    - Average wait time per request

    Useful for monitoring API usage and identifying rate limit bottlenecks.
    """
    from .kite_rate_limiter import get_rate_limiter

    rate_limiter = get_rate_limiter()
    return rate_limiter.get_stats()


@router.get("/rate-limit/config")
async def get_rate_limit_config():
    """
    Get Kite API rate limit configuration.

    Returns the official Kite Connect API rate limits as documented at:
    https://kite.trade/docs/connect/v3/exceptions/#api-rate-limit

    Rate Limits:
    - Quote endpoint: 1 req/sec
    - Historical data: 3 req/sec
    - Order placement: 10 req/sec, 200 req/min, 3000 req/day
    - Order modifications: 10 req/sec
    - Order cancellations: 10 req/sec
    - Other endpoints: 10 req/sec
    """
    from .kite_rate_limiter import KITE_RATE_LIMITS

    return {
        "documentation_url": "https://kite.trade/docs/connect/v3/exceptions/#api-rate-limit",
        "limits": {
            endpoint.value: {
                "requests_per_second": config.requests_per_second,
                "requests_per_minute": config.requests_per_minute,
                "requests_per_day": config.requests_per_day
            }
            for endpoint, config in KITE_RATE_LIMITS.items()
        }
    }


# ============================================================================
# WebSocket Connection Pool Monitoring
# ============================================================================

@router.get("/websocket-pool/stats")
async def get_websocket_pool_stats():
    """
    Get WebSocket connection pool statistics for all accounts.

    Returns detailed information about WebSocket connections including:
    - Total number of active connections per account
    - Subscribed instruments count per connection
    - Connection capacity and utilization
    - Total connections created (lifetime counter)
    - Total subscriptions/unsubscriptions

    This is useful for monitoring WebSocket scaling behavior and ensuring
    the pool is properly distributing load across multiple connections.

    Note: Each WebSocket connection can handle up to 1000 instruments (configurable).
    The pool automatically creates additional connections when this limit is reached.
    """
    from .accounts import get_orchestrator

    orchestrator = get_orchestrator()
    all_stats = {}

    # Get stats from all accounts
    for account_id, session in orchestrator._sessions.items():
        try:
            pool_stats = session.client.get_pool_stats()
            if pool_stats and isinstance(pool_stats, dict):
                # Validate and sanitize stats to handle None values
                sanitized_stats = {
                    "account_id": pool_stats.get("account_id", account_id),
                    "total_connections": pool_stats.get("total_connections", 0),
                    "total_target_tokens": pool_stats.get("total_target_tokens", 0),
                    "total_subscribed_tokens": pool_stats.get("total_subscribed_tokens", 0),
                    "max_instruments_per_connection": pool_stats.get("max_instruments_per_connection", 1000),
                    "total_capacity": pool_stats.get("total_capacity", 0),
                    "connections": pool_stats.get("connections", []),
                    "statistics": pool_stats.get("statistics", {})
                }
                all_stats[account_id] = sanitized_stats
        except Exception as e:
            logger.warning(f"Failed to get pool stats for account {account_id}: {e}")
            # Include error info in stats
            all_stats[account_id] = {
                "error": "Failed to retrieve stats",
                "message": str(e)
            }

    return {
        "total_accounts": len(all_stats),
        "accounts": all_stats,
        "note": "Each connection can handle up to max_instruments_per_ws_connection instruments (default: 1000)"
    }


@router.get("/websocket-pool/stats/{account_id}")
async def get_websocket_pool_stats_for_account(account_id: str):
    """
    Get WebSocket connection pool statistics for a specific account.

    Returns detailed information about WebSocket connections for the specified account:
    - Number of active connections
    - Subscribed instruments per connection
    - Connection health status
    - Capacity utilization per connection
    - Statistics (total connections created, subscriptions, unsubscriptions)

    Args:
        account_id: The account ID to get statistics for

    Raises:
        404: If account not found or has no active WebSocket pool
    """
    from .accounts import get_orchestrator

    orchestrator = get_orchestrator()
    session = orchestrator._sessions.get(account_id)

    if not session:
        raise HTTPException(
            status_code=404,
            detail=f"Account '{account_id}' not found"
        )

    try:
        pool_stats = session.client.get_pool_stats()
        if not pool_stats or not isinstance(pool_stats, dict):
            raise HTTPException(
                status_code=404,
                detail=f"Account '{account_id}' has no active WebSocket pool"
            )

        # Validate and sanitize stats to handle None values
        sanitized_stats = {
            "account_id": pool_stats.get("account_id", account_id),
            "total_connections": pool_stats.get("total_connections", 0),
            "total_target_tokens": pool_stats.get("total_target_tokens", 0),
            "total_subscribed_tokens": pool_stats.get("total_subscribed_tokens", 0),
            "max_instruments_per_connection": pool_stats.get("max_instruments_per_connection", 1000),
            "total_capacity": pool_stats.get("total_capacity", 0),
            "connections": pool_stats.get("connections", []),
            "statistics": pool_stats.get("statistics", {})
        }

        return sanitized_stats

    except HTTPException:
        raise  # Re-raise HTTP exceptions
    except Exception as e:
        logger.exception(f"Failed to get pool stats for account {account_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve pool stats: {str(e)}"
        )
