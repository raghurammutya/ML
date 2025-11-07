from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import List, Optional

import re

from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.responses import JSONResponse, PlainTextResponse
from loguru import logger
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from .config import get_settings
from .middleware import RequestIDMiddleware
from .generator import ticker_loop
from .instrument_registry import instrument_registry
from .order_executor import get_executor, init_executor
from .redis_client import redis_publisher
from .routes_account import router as account_router
from .routes_gtt import router as gtt_router
from .routes_mf import router as mf_router
from .routes_orders import router as orders_router
from .routes_portfolio import router as portfolio_router
from .routes_trading_accounts import router as trading_accounts_router
from .subscription_store import SubscriptionRecord, subscription_store
from .account_store import initialize_account_store, get_account_store
from .jwt_auth import get_current_user, get_optional_user
from .historical_greeks import HistoricalGreeksEnricher
from .utils.symbol_utils import normalize_symbol

settings = get_settings()

# Global instance for historical Greeks enricher (initialized at startup)
historical_greeks_enricher: Optional[HistoricalGreeksEnricher] = None

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])


# PII Sanitization Filter for Logs
def sanitize_pii(record: dict) -> bool:
    """
    Sanitize personally identifiable information from log messages.
    Redacts: email addresses, phone numbers, and common PII patterns.
    """
    if "message" in record:
        message = record["message"]
        # Redact email addresses
        message = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '[EMAIL_REDACTED]', message)
        # Redact phone numbers (Indian format: 10 digits)
        message = re.sub(r'\b\d{10}\b', '[PHONE_REDACTED]', message)
        # Redact potential API keys/tokens (long hex strings)
        message = re.sub(r'\b[a-fA-F0-9]{32,}\b', '[TOKEN_REDACTED]', message)
        record["message"] = message
    return True


# Configure loguru with PII filter and log rotation
logger.remove()  # Remove default handler

# Console handler (for Docker logs)
logger.add(
    sink=lambda msg: print(msg, end=""),
    format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    filter=sanitize_pii,
    colorize=True,
    level="INFO"
)

# File handler with rotation (for persistent logs)
import os
log_dir = os.getenv("LOG_DIR", "logs")
os.makedirs(log_dir, exist_ok=True)

logger.add(
    sink=os.path.join(log_dir, "ticker_service.log"),
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
    filter=sanitize_pii,
    rotation="100 MB",      # Rotate when file reaches 100MB
    retention="7 days",     # Keep logs for 7 days
    compression="zip",      # Compress rotated logs
    enqueue=True,           # Thread-safe logging
    level="DEBUG"           # Capture all levels in file
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio
    import os

    logger.info("Starting %s", settings.app_name)
    await redis_publisher.connect()

    # Initialize Account Store for dynamic account management
    try:
        # Build database connection string from settings
        db_conn_string = (
            f"postgresql://{settings.instrument_db_user}:{settings.instrument_db_password}"
            f"@{settings.instrument_db_host}:{settings.instrument_db_port}/{settings.instrument_db_name}"
        )
        encryption_key = os.getenv("ACCOUNT_ENCRYPTION_KEY")
        await initialize_account_store(db_conn_string, encryption_key)
        logger.info("Account store initialized")

        # Initialize Historical Greeks Enricher
        global historical_greeks_enricher
        account_store = get_account_store()
        historical_greeks_enricher = HistoricalGreeksEnricher(
            db_pool=account_store._pool,
            kite_fetch_fn=ticker_loop.fetch_history
        )
        logger.info("Historical Greeks enricher initialized")

    except Exception as exc:
        logger.warning(f"Failed to initialize account store: {exc}")
        logger.warning("Trading account management endpoints will not be available")

    await ticker_loop.start()

    # Start strike rebalancer for automatic option subscription management
    try:
        from .strike_rebalancer import strike_rebalancer
        await strike_rebalancer.start()
        logger.info("Strike rebalancer started")
    except Exception as exc:
        logger.warning(f"Failed to start strike rebalancer: {exc}")
        # Non-critical, continue startup

    # Initialize OrderExecutor with config values
    init_executor(
        max_tasks=settings.order_executor_max_tasks,
        worker_poll_interval=settings.order_executor_worker_poll_interval,
        worker_error_backoff=settings.order_executor_worker_error_backoff
    )

    # Start OrderExecutor worker with client factory
    executor = get_executor()
    executor_task = asyncio.create_task(executor.start_worker(ticker_loop.borrow_client))
    logger.info("OrderExecutor worker started with config: max_tasks=%d, poll_interval=%.1fs, error_backoff=%.1fs",
                settings.order_executor_max_tasks,
                settings.order_executor_worker_poll_interval,
                settings.order_executor_worker_error_backoff)

    # Start daily rate limit reset scheduler
    from .kite_rate_limiter import get_rate_limiter
    rate_limiter = get_rate_limiter()
    rate_limiter.start_daily_reset_scheduler(asyncio.get_running_loop())

    # Start WebSocket services (Redis listener)
    try:
        from .routes_websocket import start_websocket_services
        await start_websocket_services()
        logger.info("WebSocket services started")
    except Exception as e:
        logger.error(f"Failed to start WebSocket services: {e}")
        # Non-critical, continue startup

    try:
        yield
    finally:
        # Stop WebSocket services
        try:
            from .routes_websocket import stop_websocket_services
            await stop_websocket_services()
            logger.info("WebSocket services stopped")
        except Exception as e:
            logger.error(f"Error stopping WebSocket services: {e}")

        # Stop rate limiter scheduler
        rate_limiter.stop_daily_reset_scheduler()

        # Stop order executor
        await executor.stop_worker()
        try:
            await asyncio.wait_for(executor_task, timeout=10.0)
        except asyncio.TimeoutError:
            logger.warning("OrderExecutor worker did not stop within timeout")
            executor_task.cancel()
        logger.info("OrderExecutor worker stopped")

        # Stop strike rebalancer
        try:
            from .strike_rebalancer import strike_rebalancer
            await strike_rebalancer.stop()
            logger.info("Strike rebalancer stopped")
        except Exception as exc:
            logger.error(f"Error stopping strike rebalancer: {exc}")

        await ticker_loop.stop()
        await redis_publisher.close()
        await instrument_registry.close()

        # Close account store
        try:
            account_store = get_account_store()
            await account_store.close()
            logger.info("Account store closed")
        except RuntimeError:
            pass  # Account store was not initialized

        logger.info("Shutdown complete")


app = FastAPI(title="Ticker Service", lifespan=lifespan)

# Add middlewares
app.add_middleware(RequestIDMiddleware)

# Add rate limiter state and exception handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# Standardized error response handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Global exception handler that returns standardized error responses.

    Response format:
    {
        "error": {
            "type": "ErrorClassName",
            "message": "Error description",
            "timestamp": "2025-10-31T07:30:00.000Z"
        }
    }
    """
    # Handle HTTPException separately to preserve status codes
    if isinstance(exc, HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "type": "HTTPException",
                    "message": exc.detail,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            },
        )

    # Log unexpected errors
    logger.exception(f"Unhandled exception in {request.method} {request.url.path}")

    # Return generic 500 error
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "type": exc.__class__.__name__,
                "message": str(exc),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        },
    )

# Include all API routers
app.include_router(orders_router)
app.include_router(portfolio_router)
app.include_router(account_router)
app.include_router(gtt_router)
app.include_router(mf_router)

# Include advanced features router
from .routes_advanced import router as advanced_router
app.include_router(advanced_router)

# Include trading accounts management router
app.include_router(trading_accounts_router)

# Include WebSocket router for real-time tick streaming
from .routes_websocket import router as websocket_router
app.include_router(websocket_router)


class SubscriptionRequest(BaseModel):
    instrument_token: int = Field(ge=1)
    requested_mode: str = Field(default="FULL")
    account_id: Optional[str] = None


class SubscriptionResponse(BaseModel):
    instrument_token: int
    tradingsymbol: str
    segment: str
    status: str
    requested_mode: str
    account_id: Optional[str]
    created_at: datetime
    updated_at: datetime


def _record_to_response(record: SubscriptionRecord) -> SubscriptionResponse:
    return SubscriptionResponse(
        instrument_token=record.instrument_token,
        tradingsymbol=record.tradingsymbol,
        segment=record.segment,
        status=record.status,
        requested_mode=record.requested_mode,
        account_id=record.account_id,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _to_timestamp(dt: datetime) -> int:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return int(dt.timestamp())


@app.get("/metrics")
async def metrics() -> PlainTextResponse:
    """
    Prometheus metrics endpoint.

    Returns metrics in Prometheus exposition format.
    """
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/health")
@limiter.limit("60/minute")
async def health(request: Request) -> dict[str, object]:
    """
    Enhanced health check that verifies all critical dependencies.
    """
    health_status = {
        "status": "ok",
        "environment": settings.environment,
        "ticker": ticker_loop.runtime_state(),
        "dependencies": {}
    }

    # Check Redis connectivity
    try:
        import json
        test_message = json.dumps({"timestamp": datetime.now(timezone.utc).isoformat()})
        await redis_publisher.publish("health:check", test_message)
        health_status["dependencies"]["redis"] = "ok"
    except Exception as exc:
        logger.error(f"Redis health check failed: {exc}")
        health_status["dependencies"]["redis"] = f"error: {str(exc)}"
        health_status["status"] = "degraded"

    # Check database connectivity
    try:
        from .subscription_store import subscription_store
        _ = await subscription_store.list_active()
        health_status["dependencies"]["database"] = "ok"
    except Exception as exc:
        logger.error(f"Database health check failed: {exc}")
        health_status["dependencies"]["database"] = f"error: {str(exc)}"
        health_status["status"] = "degraded"

    # Check instrument registry
    try:
        # Check if registry is initialized and cache is populated
        registry_initialized = instrument_registry._initialised
        cache_loaded = len(instrument_registry._cache) > 0

        if registry_initialized and cache_loaded:
            health_status["dependencies"]["instrument_registry"] = {
                "status": "ok",
                "cached_instruments": len(instrument_registry._cache),
                "last_refresh": instrument_registry._last_refresh.isoformat() if instrument_registry._last_refresh else None
            }
        elif registry_initialized:
            health_status["dependencies"]["instrument_registry"] = {
                "status": "initialized_but_empty",
                "cached_instruments": 0
            }
            health_status["status"] = "degraded"
        else:
            health_status["dependencies"]["instrument_registry"] = "not_initialized"
            health_status["status"] = "degraded"
    except Exception as exc:
        logger.error(f"Instrument registry health check failed: {exc}")
        health_status["dependencies"]["instrument_registry"] = f"error: {str(exc)}"
        health_status["status"] = "degraded"

    return health_status


@app.get("/auth/test")
async def test_jwt_auth(current_user: dict = Depends(get_current_user)) -> dict[str, object]:
    """
    Test endpoint for JWT authentication.
    Requires valid JWT token from user_service.
    """
    return {
        "message": "JWT authentication successful",
        "user": current_user,
        "service": "ticker_service"
    }


@app.post("/admin/instrument-refresh")
@limiter.limit("5/hour")
async def instrument_refresh(request: Request, force: bool = False) -> dict[str, object]:
    try:
        result = await ticker_loop.refresh_instruments(force=force)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {
        "force": force,
        **result,
    }


@app.get("/subscriptions", response_model=List[SubscriptionResponse])
@limiter.limit("100/minute")
async def list_subscriptions(
    request: Request,
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
) -> List[SubscriptionResponse]:
    """
    List subscriptions with pagination support.

    Args:
        status: Filter by status ('active' or 'inactive')
        limit: Maximum number of records to return (default: 100, max: 1000)
        offset: Number of records to skip (default: 0)
    """
    if limit < 1 or limit > 1000:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 1000")
    if offset < 0:
        raise HTTPException(status_code=400, detail="offset must be non-negative")

    status_normalised = status.lower() if status else None
    if status_normalised not in (None, "active", "inactive"):
        raise HTTPException(status_code=400, detail="status must be 'active', 'inactive', or omitted")

    if status_normalised == "active":
        records = await subscription_store.list_active()
    else:
        records = await subscription_store.list_all()
        if status_normalised == "inactive":
            records = [record for record in records if record.status == "inactive"]

    # Apply pagination
    paginated_records = records[offset:offset + limit]
    return [_record_to_response(record) for record in paginated_records]


@app.post("/subscriptions", response_model=SubscriptionResponse, status_code=201)
@limiter.limit("30/minute")
async def create_subscription(request: Request, payload: SubscriptionRequest) -> SubscriptionResponse:
    requested_mode = (payload.requested_mode or "FULL").upper()
    if requested_mode not in {"FULL", "QUOTE", "LTP"}:
        raise HTTPException(status_code=400, detail="requested_mode must be one of FULL, QUOTE, LTP")

    metadata = await instrument_registry.fetch_metadata(payload.instrument_token)
    if not metadata or not metadata.is_active:
        raise HTTPException(status_code=404, detail="Instrument token not found or inactive in registry")

    tradingsymbol = metadata.tradingsymbol or metadata.name
    if not tradingsymbol:
        raise HTTPException(status_code=400, detail="Instrument metadata missing tradingsymbol/name")

    # Normalize the symbol for consistency across all brokers
    normalized_symbol = normalize_symbol(tradingsymbol)

    account_id = payload.account_id
    if account_id:
        accounts = ticker_loop.list_accounts()
        if account_id not in accounts:
            raise HTTPException(status_code=400, detail=f"Account '{account_id}' is not configured")

    await subscription_store.upsert(
        instrument_token=payload.instrument_token,
        tradingsymbol=normalized_symbol,  # Store normalized symbol
        segment=metadata.segment or "",
        requested_mode=requested_mode,
        account_id=account_id,
        status="active",
    )
    record = await subscription_store.get(payload.instrument_token)
    if not record:
        raise HTTPException(status_code=500, detail="Failed to persist subscription")

    # Trigger subscription reload in background (non-blocking)
    # The ticker loop will pick up the new subscription asynchronously
    ticker_loop.reload_subscriptions_async()
    logger.info(f"Subscription created for {payload.instrument_token}, reload triggered in background")

    return _record_to_response(record)


@app.get("/history")
async def history(
    instrument_token: int,
    from_ts: datetime,
    to_ts: datetime,
    interval: str = "minute",
    account_id: Optional[str] = None,
    continuous: bool = False,
    oi: bool = False,
) -> dict[str, object]:
    if to_ts <= from_ts:
        raise HTTPException(status_code=400, detail="'to_ts' must be greater than 'from_ts'")

    metadata = await instrument_registry.fetch_metadata(instrument_token)
    if not metadata:
        raise HTTPException(status_code=404, detail="Instrument token not found in registry")

    from_epoch = _to_timestamp(from_ts)
    to_epoch = _to_timestamp(to_ts)

    try:
        candles = await ticker_loop.fetch_history(
            instrument_token=instrument_token,
            from_ts=from_epoch,
            to_ts=to_epoch,
            interval=interval,
            account_id=account_id,
            continuous=continuous,
            oi=oi,
        )
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Historical fetch failed: {exc}") from exc

    # Enrich option candles with Greeks if requested
    if oi and historical_greeks_enricher and metadata.segment in ("NFO-OPT", "BFO-OPT", "MCX-OPT"):
        try:
            logger.info(f"Enriching {len(candles)} historical candles with Greeks for {metadata.tradingsymbol}")
            candles = await historical_greeks_enricher.enrich_option_candles(
                option_metadata=metadata,
                option_candles=candles,
                from_ts=from_epoch,
                to_ts=to_epoch,
                interval=interval
            )
        except Exception as exc:
            logger.error(f"Failed to enrich historical candles with Greeks: {exc}", exc_info=True)
            # Continue without Greeks enrichment

    for candle in candles:
        ts = candle.get("date")
        if isinstance(ts, datetime):
            candle["date"] = ts.isoformat()

    # Normalize the symbol for consistency across all brokers
    raw_symbol = metadata.tradingsymbol or metadata.name
    normalized_symbol = normalize_symbol(raw_symbol) if raw_symbol else raw_symbol

    return {
        "instrument_token": instrument_token,
        "symbol": normalized_symbol,  # Canonical symbol (e.g., NIFTY)
        "tradingsymbol": raw_symbol,  # Original tradingsymbol from Kite (e.g., NIFTY 50)
        "segment": metadata.segment,
        "interval": interval,
        "from_ts": from_ts,
        "to_ts": to_ts,
        "candles": candles,
    }


@app.delete("/subscriptions/{instrument_token}", response_model=SubscriptionResponse)
@limiter.limit("30/minute")
async def delete_subscription(request: Request, instrument_token: int) -> SubscriptionResponse:
    record = await subscription_store.get(instrument_token)
    if not record:
        raise HTTPException(status_code=404, detail="Subscription not found")
    changed = await subscription_store.deactivate(instrument_token)
    if not changed:
        raise HTTPException(status_code=404, detail="Subscription not found or already inactive")
    record = await subscription_store.get(instrument_token)
    if not record:
        raise HTTPException(status_code=500, detail="Failed to fetch updated subscription")

    # Trigger subscription reload in background (non-blocking)
    ticker_loop.reload_subscriptions_async()
    logger.info(f"Subscription deleted for {instrument_token}, reload triggered in background")

    return _record_to_response(record)
