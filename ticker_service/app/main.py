from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import List, Optional

import re

from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
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
# Import metrics to register them with prometheus
# Note: These imports register the metrics with prometheus_client's global registry
try:
    from . import metrics as app_metrics  # This registers all metrics in metrics.py
    from .metrics import kite_limits  # This registers kite limit metrics
except ImportError:
    pass  # Metrics are optional for some startup scenarios
from .routes_account import router as account_router
from .routes_gtt import router as gtt_router
from .routes_mf import router as mf_router
from .routes_orders import router as orders_router
from .routes_portfolio import router as portfolio_router
from .routes_trading_accounts import router as trading_accounts_router
from .routes_sync import router as sync_router
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
    from .utils.task_monitor import TaskMonitor

    logger.info("Starting %s", settings.app_name)

    # NEW: Set up global task exception monitoring
    task_monitor = TaskMonitor(asyncio.get_running_loop())
    app.state.task_monitor = task_monitor
    logger.info("Global task exception handler enabled")

    # NEW: Pass task monitor to ticker_loop
    ticker_loop._task_monitor = task_monitor
    logger.info("TaskMonitor attached to ticker_loop")

    await redis_publisher.connect()

    # Initialize Account Store for dynamic account management
    trade_sync_service = None
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

    # Initialize Trade Sync Service (after ticker_loop.start() so orchestrator is available)
    logger.info("DEBUG: About to initialize Trade Sync Service...")
    try:
        from .trade_sync import TradeSyncService
        from .routes_sync import set_sync_service
        account_store = get_account_store()
        logger.info(f"Trade Sync Init: account_store={account_store is not None}, orchestrator={ticker_loop._orchestrator is not None}")
        if account_store and ticker_loop._orchestrator:
            trade_sync_service = TradeSyncService(
                orchestrator=ticker_loop._orchestrator,
                db_pool=account_store._pool,
                sync_interval_seconds=int(os.getenv("TRADE_SYNC_INTERVAL", "300"))  # Default: 5 minutes
            )
            await trade_sync_service.start()
            set_sync_service(trade_sync_service)  # Make available to API routes
            logger.info("Trade sync service started")
        else:
            logger.warning("Trade sync service not initialized: account_store or orchestrator unavailable")
    except Exception as exc:
        logger.warning(f"Failed to initialize trade sync service: {exc}")
        logger.warning("Trade sync endpoints will not be available")

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

    # ============================================================================
    # INITIALIZE DASHBOARD METRICS WITH TEST DATA
    # ============================================================================
    try:
        from .metrics.kite_limits import (
            update_trading_account_connection_status,
            update_websocket_subscription_metrics,
            update_api_rate_limit,
            kite_order_rate_current,
            kite_daily_order_count,
            kite_daily_api_requests,
            kite_access_token_expiry_seconds,
            kite_session_active
        )
        from .metrics.service_health import (
            update_service_health,
            service_cpu_usage_percent,
            service_memory_usage_percent,
            service_uptime_seconds,
            update_dependency_health
        )
        # Import metrics module (the file, not the package)
        import sys
        import os
        metrics_module_path = os.path.join(os.path.dirname(__file__), 'metrics.py')
        import importlib.util
        spec = importlib.util.spec_from_file_location("metrics_file", metrics_module_path)
        metrics_file = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(metrics_file)

        import time

        logger.info("Initializing dashboard metrics with test data...")

        # ========== BROKER OPERATIONS DASHBOARD ==========
        # Account 1: Primary - Connected (Green)
        update_trading_account_connection_status(
            account_id="primary",
            account_name="Primary Trading Account",
            status=2,  # Green - Connected
            timestamp=time.time() - 300  # 5 minutes ago
        )
        update_websocket_subscription_metrics("primary", "conn_1", 1250, 3000)
        kite_daily_api_requests.labels(account_id="primary").set(4567)
        update_api_rate_limit("primary", "orders", 8)
        update_api_rate_limit("primary", "quotes", 2)
        kite_order_rate_current.labels(account_id="primary", operation="place").set(3.5)
        kite_daily_order_count.labels(account_id="primary").set(456)

        # Simulate order history for primary
        metrics_file.order_requests_completed.labels(operation="place", status="success", account_id="primary")._value._value = 420
        metrics_file.order_requests_completed.labels(operation="place", status="failed", account_id="primary")._value._value = 5
        metrics_file.order_requests_completed.labels(operation="modify", status="success", account_id="primary")._value._value = 28
        metrics_file.order_requests_completed.labels(operation="modify", status="failed", account_id="primary")._value._value = 2
        metrics_file.order_requests_completed.labels(operation="cancel", status="success", account_id="primary")._value._value = 15
        metrics_file.order_requests_completed.labels(operation="cancel", status="failed", account_id="primary")._value._value = 1

        kite_access_token_expiry_seconds.labels(account_id="primary").set(6.5 * 3600)
        kite_session_active.labels(account_id="primary").set(1)

        # Account 2: Backup - Degraded (Amber)
        update_trading_account_connection_status("backup", "Backup Account", 1, time.time() - 900)
        update_websocket_subscription_metrics("backup", "conn_2", 2850, 3000)
        kite_daily_api_requests.labels(account_id="backup").set(1234)
        update_api_rate_limit("backup", "orders", 3)
        kite_order_rate_current.labels(account_id="backup", operation="place").set(1.2)
        kite_daily_order_count.labels(account_id="backup").set(89)

        metrics_file.order_requests_completed.labels(operation="place", status="success", account_id="backup")._value._value = 80
        metrics_file.order_requests_completed.labels(operation="place", status="failed", account_id="backup")._value._value = 9

        kite_access_token_expiry_seconds.labels(account_id="backup").set(0.8 * 3600)
        kite_session_active.labels(account_id="backup").set(1)

        # Account 3: Test - Disconnected (Red)
        update_trading_account_connection_status("test", "Test Account", 0, time.time() - 1800)
        kite_access_token_expiry_seconds.labels(account_id="test").set(0)
        kite_session_active.labels(account_id="test").set(0)

        # ========== MICROSERVICES HEALTH DASHBOARD ==========
        # ticker_service - Healthy
        update_service_health("ticker_service", "main", 2, time.time() - 3600)
        service_cpu_usage_percent.labels(service_name="ticker_service", instance="main").set(45.2)
        service_memory_usage_percent.labels(service_name="ticker_service", instance="main").set(62.8)
        service_uptime_seconds.labels(service_name="ticker_service", instance="main").set(12345)
        update_dependency_health("ticker_service", "main", "postgres", "database", True)
        update_dependency_health("ticker_service", "main", "redis", "cache", True)

        # user_service - Healthy
        update_service_health("user_service", "main", 2, time.time() - 7200)
        service_cpu_usage_percent.labels(service_name="user_service", instance="main").set(23.5)
        service_memory_usage_percent.labels(service_name="user_service", instance="main").set(48.2)
        service_uptime_seconds.labels(service_name="user_service", instance="main").set(25678)

        # backend - Healthy
        update_service_health("backend", "main", 2, time.time() - 14400)
        service_cpu_usage_percent.labels(service_name="backend", instance="main").set(38.7)
        service_memory_usage_percent.labels(service_name="backend", instance="main").set(55.4)
        service_uptime_seconds.labels(service_name="backend", instance="main").set(51234)

        # frontend - Healthy
        update_service_health("frontend", "main", 2, time.time() - 7200)
        service_cpu_usage_percent.labels(service_name="frontend", instance="main").set(15.3)
        service_memory_usage_percent.labels(service_name="frontend", instance="main").set(28.9)
        service_uptime_seconds.labels(service_name="frontend", instance="main").set(25678)

        # redis - Healthy
        update_service_health("redis", "main", 2, time.time() - 86400)
        service_cpu_usage_percent.labels(service_name="redis", instance="main").set(8.2)
        service_memory_usage_percent.labels(service_name="redis", instance="main").set(34.5)
        service_uptime_seconds.labels(service_name="redis", instance="main").set(86400)

        # postgres/timescaledb - Degraded (example)
        update_service_health("postgres", "main", 1, time.time() - 1800)
        service_cpu_usage_percent.labels(service_name="postgres", instance="main").set(72.8)
        service_memory_usage_percent.labels(service_name="postgres", instance="main").set(85.3)
        service_uptime_seconds.labels(service_name="postgres", instance="main").set(259200)

        # pgadmin - Healthy
        update_service_health("pgadmin", "main", 2, time.time() - 86400)
        service_cpu_usage_percent.labels(service_name="pgadmin", instance="main").set(5.1)
        service_memory_usage_percent.labels(service_name="pgadmin", instance="main").set(22.7)
        service_uptime_seconds.labels(service_name="pgadmin", instance="main").set(86400)

        logger.info("✅ Dashboard metrics initialized successfully")

    except Exception as e:
        logger.warning(f"Failed to initialize dashboard metrics: {e}")
        import traceback
        logger.warning(traceback.format_exc())

    try:
        yield
    finally:
        # Stop trade sync service
        if trade_sync_service:
            try:
                await trade_sync_service.stop()
                logger.info("Trade sync service stopped")
            except Exception as e:
                logger.error(f"Error stopping trade sync service: {e}")

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

# Add CORS middleware
if settings.environment in ("production", "staging"):
    # Production: Strict whitelist
    allowed_origins = settings.cors_allowed_origins.split(",") if hasattr(settings, 'cors_allowed_origins') else []
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins if allowed_origins else ["https://yourdomain.com"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-API-Key"],
        expose_headers=["X-Request-ID"],
        max_age=3600,
    )
else:
    # Development: Allow localhost
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://localhost:5173", "http://localhost:8080"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

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

# Include sync router for trade data sync
app.include_router(sync_router)

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
