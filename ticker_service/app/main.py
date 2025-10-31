from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import List, Optional

import re

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from .config import get_settings
from .generator import ticker_loop
from .instrument_registry import instrument_registry
from .order_executor import get_executor, init_executor
from .redis_client import redis_publisher
from .routes_account import router as account_router
from .routes_gtt import router as gtt_router
from .routes_mf import router as mf_router
from .routes_orders import router as orders_router
from .routes_portfolio import router as portfolio_router
from .subscription_store import SubscriptionRecord, subscription_store

settings = get_settings()

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


# Configure loguru with PII filter
logger.remove()  # Remove default handler
logger.add(
    sink=lambda msg: print(msg, end=""),
    format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    filter=sanitize_pii,
    colorize=True
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio

    logger.info("Starting %s", settings.app_name)
    await redis_publisher.connect()
    await ticker_loop.start()

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

    try:
        yield
    finally:
        # Stop order executor
        await executor.stop_worker()
        try:
            await asyncio.wait_for(executor_task, timeout=10.0)
        except asyncio.TimeoutError:
            logger.warning("OrderExecutor worker did not stop within timeout")
            executor_task.cancel()
        logger.info("OrderExecutor worker stopped")

        await ticker_loop.stop()
        await redis_publisher.close()
        await instrument_registry.close()
        logger.info("Shutdown complete")


app = FastAPI(title="Ticker Service", lifespan=lifespan)

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
        # Check if instruments cache is populated
        registry_ok = hasattr(instrument_registry, '_instruments') and instrument_registry._instruments is not None
        health_status["dependencies"]["instrument_registry"] = "ok" if registry_ok else "not_loaded"
        if not registry_ok:
            health_status["status"] = "degraded"
    except Exception as exc:
        logger.error(f"Instrument registry health check failed: {exc}")
        health_status["dependencies"]["instrument_registry"] = f"error: {str(exc)}"
        health_status["status"] = "degraded"

    return health_status


@app.post("/admin/instrument-refresh")
async def instrument_refresh(force: bool = False) -> dict[str, object]:
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
async def create_subscription(payload: SubscriptionRequest) -> SubscriptionResponse:
    requested_mode = (payload.requested_mode or "FULL").upper()
    if requested_mode not in {"FULL", "QUOTE", "LTP"}:
        raise HTTPException(status_code=400, detail="requested_mode must be one of FULL, QUOTE, LTP")

    metadata = await instrument_registry.fetch_metadata(payload.instrument_token)
    if not metadata or not metadata.is_active:
        raise HTTPException(status_code=404, detail="Instrument token not found or inactive in registry")

    tradingsymbol = metadata.tradingsymbol or metadata.name
    if not tradingsymbol:
        raise HTTPException(status_code=400, detail="Instrument metadata missing tradingsymbol/name")

    account_id = payload.account_id
    if account_id:
        accounts = ticker_loop.list_accounts()
        if account_id not in accounts:
            raise HTTPException(status_code=400, detail=f"Account '{account_id}' is not configured")

    await subscription_store.upsert(
        instrument_token=payload.instrument_token,
        tradingsymbol=tradingsymbol,
        segment=metadata.segment or "",
        requested_mode=requested_mode,
        account_id=account_id,
        status="active",
    )
    record = await subscription_store.get(payload.instrument_token)
    if not record:
        raise HTTPException(status_code=500, detail="Failed to persist subscription")

    try:
        await ticker_loop.reload_subscriptions()
    except Exception as exc:
        logger.exception("Subscription reload failed after create: %s", exc)
        raise HTTPException(status_code=502, detail=f"Failed to activate subscription: {exc}") from exc
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

    for candle in candles:
        ts = candle.get("date")
        if isinstance(ts, datetime):
            candle["date"] = ts.isoformat()

    return {
        "instrument_token": instrument_token,
        "tradingsymbol": metadata.tradingsymbol or metadata.name,
        "segment": metadata.segment,
        "interval": interval,
        "from_ts": from_ts,
        "to_ts": to_ts,
        "candles": candles,
    }


@app.delete("/subscriptions/{instrument_token}", response_model=SubscriptionResponse)
async def delete_subscription(instrument_token: int) -> SubscriptionResponse:
    record = await subscription_store.get(instrument_token)
    if not record:
        raise HTTPException(status_code=404, detail="Subscription not found")
    changed = await subscription_store.deactivate(instrument_token)
    if not changed:
        raise HTTPException(status_code=404, detail="Subscription not found or already inactive")
    record = await subscription_store.get(instrument_token)
    if not record:
        raise HTTPException(status_code=500, detail="Failed to fetch updated subscription")
    try:
        await ticker_loop.reload_subscriptions()
    except Exception as exc:
        logger.exception("Subscription reload failed after delete: %s", exc)
        raise HTTPException(status_code=502, detail=f"Failed to apply subscription removal: {exc}") from exc
    return _record_to_response(record)
