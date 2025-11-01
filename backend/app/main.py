# app/main.py
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Optional
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
import redis.asyncio as redis
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from .config import get_settings
from .database import DataManager, data_refresh_task, create_pool
from .cache import CacheManager, cache_maintenance_task
from .udf_handlers import UDFHandler
from .monitoring import (
    health_monitor, metrics_update_task,
    track_request_metrics, update_db_pool_metrics
)
from .models import HealthResponse, CacheStats
from .fo_stream import FOStreamConsumer
from .backfill import BackfillManager
from .realtime import RealTimeHub
from .ticker_client import TickerServiceClient
from .nifty_monitor_service import NiftyMonitorStream, NiftySubscriptionManager
from .order_stream import OrderStreamManager
from app.routes import marks_asyncpg, labels, indicators, fo, nifty_monitor, label_stream, historical, replay, accounts, order_ws, api_keys, indicators_api, indicator_ws
from app.routes import calendar_simple as calendar
from app.routes import admin_calendar

# -------- logging --------
logging.basicConfig(
    level=logging.INFO,
    format='{"time": "%(asctime)s", "level": "%(levelname)s", "logger": "%(name)s", "message": "%(message)s"}'
)
logger = logging.getLogger(__name__)

# -------- globals --------
settings = get_settings()
data_manager: Optional[DataManager] = None
cache_manager: Optional[CacheManager] = None
redis_client: Optional[redis.Redis] = None
fo_stream_consumer: Optional[FOStreamConsumer] = None
real_time_hub: Optional[RealTimeHub] = None
ticker_client: Optional[TickerServiceClient] = None
nifty_subscription_manager: Optional[NiftySubscriptionManager] = None
nifty_monitor_stream: Optional[NiftyMonitorStream] = None
monitor_hub: Optional[RealTimeHub] = None
labels_hub: Optional[RealTimeHub] = None
backfill_manager: Optional[BackfillManager] = None
order_hub: Optional[RealTimeHub] = None
order_stream_manager: Optional[OrderStreamManager] = None
snapshot_service = None  # Account snapshot service
indicator_streaming_task = None  # Indicator streaming background task

background_tasks = []  # supervised background tasks


# -------- task supervisor --------
async def task_supervisor():
    """
    Supervise background tasks and restart them if they fail.
    """
    global data_manager, cache_manager

    # If you have a separate health_check_task, import and add it here.
    task_configs = [
        {"name": "cache_maintenance", "func": cache_maintenance_task, "args": [cache_manager]},
        {"name": "data_refresh", "func": data_refresh_task, "args": [data_manager]},
        {"name": "metrics_update", "func": metrics_update_task, "args": []},
        # {"name": "health_check", "func": health_check_task, "args": []},  # only if defined
    ]

    running = {}

    while True:
        try:
            # restart tasks if needed
            for cfg in task_configs:
                name = cfg["name"]
                if name in running:
                    t = running[name]
                    if t.done():
                        try:
                            await t
                        except Exception as e:
                            logger.error(f"Task {name} failed: {e}", exc_info=True)
                        del running[name]

                if name not in running:
                    logger.info(f"Starting task: {name}")
                    running[name] = asyncio.create_task(cfg["func"](*cfg["args"]))

            await asyncio.sleep(30)

        except Exception as e:
            logger.error(f"Task supervisor error: {e}", exc_info=True)
            await asyncio.sleep(30)


# -------- lifespan --------
@asynccontextmanager
async def lifespan(app: FastAPI):
    global data_manager
    global cache_manager
    global redis_client
    global fo_stream_consumer
    global real_time_hub
    global ticker_client
    global nifty_subscription_manager
    global nifty_monitor_stream
    global monitor_hub
    global backfill_manager
    global order_hub
    global order_stream_manager
    global snapshot_service
    global indicator_streaming_task

    try:
        logger.info("Starting TradingView ML Visualization API")

        # Redis
        redis_client = redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_timeout=settings.redis_socket_timeout,
            socket_connect_timeout=settings.redis_socket_connect_timeout,
        )
        await redis_client.ping()
        logger.info("Redis connection established")
        health_monitor.update_redis_health(True)

        # Cache
        cache_manager = CacheManager(redis_client)

        # --- DB POOL + DATA MANAGER (FIX) ---
        # Create a real asyncpg pool and pass it to DataManager
        pool = await create_pool()
        data_manager = DataManager(pool)
        await data_manager.initialize()
        health_monitor.update_db_health(True)

        # Real-time hubs shared between routes and background consumers
        real_time_hub = RealTimeHub()
        monitor_hub = RealTimeHub()
        labels_hub = RealTimeHub()
        order_hub = RealTimeHub()  # New: for order updates
        fo.set_realtime_hub(real_time_hub)
        labels.set_realtime_hub(labels_hub)
        label_stream.set_realtime_hub(labels_hub)
        order_ws.set_order_hub(order_hub)  # New: set order hub for WebSocket routes

        # Routes
        udf_handler = UDFHandler(data_manager)        # uses DB manager (not cache)
        app.include_router(udf_handler.get_router())
        app.include_router(marks_asyncpg.router)      # asyncpg-backed /marks route
        app.include_router(labels.router)             # labels CRUD endpoints
        app.include_router(label_stream.router)       # labels WebSocket stream
        app.include_router(historical.router)         # historical series endpoint
        
        # Set data manager for indicators and include router
        try:
            indicators.set_data_manager(data_manager)
            app.include_router(indicators.router)         # technical indicators endpoints
            logger.info("Indicators router included successfully")
        except Exception as e:
            logger.error(f"Failed to include indicators router: {e}")
        logger.info("UDF routes included successfully")
        app.include_router(fo.router)

        ticker_client = TickerServiceClient(
            settings.ticker_service_url,
            timeout=settings.ticker_service_timeout,
        )
        nifty_subscription_manager = NiftySubscriptionManager(ticker_client, settings)
        backfill_manager = BackfillManager(data_manager, ticker_client)
        nifty_monitor.set_data_manager(data_manager)
        nifty_monitor.set_subscription_manager(nifty_subscription_manager)

        if settings.monitor_stream_enabled:
            nifty_monitor_stream = NiftyMonitorStream(redis_client, settings, monitor_hub)
            nifty_monitor.set_monitor_stream(nifty_monitor_stream)
            nifty_monitor.set_realtime_hub(monitor_hub)
        else:
            nifty_monitor_stream = None
            logger.info("Nifty monitor stream disabled via configuration")

        app.include_router(nifty_monitor.router)
        app.include_router(replay.router)

        # Store DB pool for API key authentication
        app.state.db_pool = data_manager.pool

        app.include_router(accounts.router)
        app.include_router(api_keys.router)  # API key management endpoints
        app.include_router(order_ws.router)  # New: WebSocket routes for order updates
        app.include_router(indicators_api.router)  # Phase 2: Dynamic technical indicators API
        app.include_router(indicator_ws.router)  # Phase 2D: Indicator WebSocket streaming
        calendar.set_data_manager(data_manager)  # Set data manager for calendar
        app.include_router(calendar.router)  # Calendar service: market holidays and trading hours
        admin_calendar.set_data_manager(data_manager)  # Set data manager for admin calendar
        app.include_router(admin_calendar.router)  # Admin API: holiday management
        logger.info("Indicator API and WebSocket routes included")

        if settings.fo_stream_enabled:
            print(f"[MAIN] Creating FOStreamConsumer, fo_stream_enabled={settings.fo_stream_enabled}", flush=True)
            fo_stream_consumer = FOStreamConsumer(redis_client, data_manager, settings, real_time_hub)
            print(f"[MAIN] FOStreamConsumer created: {fo_stream_consumer}", flush=True)
            task = asyncio.create_task(fo_stream_consumer.run())
            print(f"[MAIN] Task created: {task}", flush=True)
            background_tasks.append(task)
            print(f"[MAIN] Task appended to background_tasks, len={len(background_tasks)}", flush=True)
            logger.info("FO stream consumer started")
        if nifty_monitor_stream:
            background_tasks.append(asyncio.create_task(nifty_monitor_stream.run()))
            logger.info("Nifty monitor stream consumer started")
        if backfill_manager and settings.backfill_enabled:
            background_tasks.append(asyncio.create_task(backfill_manager.run()))
            logger.info("Backfill manager loop started")

        # Subscription event listener (triggers immediate backfill on new subscriptions)
        print(f"[MAIN] Checking subscription_events_enabled={settings.subscription_events_enabled}", flush=True)
        if settings.subscription_events_enabled:
            print("[MAIN] Creating SubscriptionEventListener", flush=True)
            from app.services.subscription_event_listener import SubscriptionEventListener
            subscription_event_listener = SubscriptionEventListener(
                redis_client=redis_client,
                backfill_manager=backfill_manager if settings.backfill_immediate_on_subscribe else None
            )
            print("[MAIN] Starting subscription event listener...", flush=True)
            await subscription_event_listener.start()
            print("[MAIN] Subscription event listener started!", flush=True)
            logger.info("Subscription event listener started")

        # Order stream manager (Phase 4A: WebSocket order streaming)
        order_stream_manager = OrderStreamManager(settings.ticker_service_url, order_hub)
        await order_stream_manager.start()
        logger.info("Order stream manager started")

        # Account snapshot service (Historical positions/holdings/funds)
        from app.services.snapshot_service import AccountSnapshotService
        from app.services.account_service import AccountService

        # Get or create AccountService instance
        account_service = AccountService(data_manager, settings.ticker_service_url)
        snapshot_service = AccountSnapshotService(data_manager, account_service)

        # Start with 5-minute snapshot interval (configurable)
        snapshot_interval_seconds = getattr(settings, 'snapshot_interval_seconds', 300)
        await snapshot_service.start(interval_seconds=snapshot_interval_seconds)
        logger.info(f"Account snapshot service started (interval: {snapshot_interval_seconds}s)")

        # Indicator streaming service (Phase 2D: Real-time indicator updates)
        from app.routes.indicator_ws import stream_indicator_updates_task
        indicator_streaming_task = asyncio.create_task(
            stream_indicator_updates_task(redis_client, data_manager)
        )
        background_tasks.append(indicator_streaming_task)
        logger.info("Indicator streaming task started")

        # Supervise background tasks
        background_tasks.append(asyncio.create_task(task_supervisor()))
        logger.info("All systems initialized successfully")

        yield

    except Exception as e:
        logger.error(f"Startup failed: {e}")
        raise
    finally:
        logger.info("Shutting down...")
        for t in background_tasks:
            t.cancel()
        await asyncio.gather(*background_tasks, return_exceptions=True)

        if fo_stream_consumer:
            await fo_stream_consumer.shutdown()
        if backfill_manager:
            await backfill_manager.shutdown()
        if order_stream_manager:
            await order_stream_manager.stop()
        if snapshot_service:
            await snapshot_service.stop()
            logger.info("Snapshot service stopped")
        if data_manager:
            await data_manager.close()
        if redis_client:
            await redis_client.close()
        if ticker_client:
            await ticker_client.close()

        # Cleanup AccountService HTTP client
        await accounts.cleanup_account_service()

        logger.info("Shutdown complete")


# -------- app --------
app = FastAPI(
    title=settings.api_title,
    version=settings.api_version,
    lifespan=lifespan,
)

# CORS - Configure allowed origins for security
# In production, ensure cors_origins in config.py contains only trusted domains
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.cors_credentials,
    allow_methods=settings.cors_methods,
    allow_headers=settings.cors_headers,
    max_age=600,  # Cache preflight requests for 10 minutes
)

# Custom middleware for correlation ID tracking and request logging
from .middleware import CorrelationIdMiddleware, RequestLoggingMiddleware, ErrorHandlingMiddleware

app.add_middleware(ErrorHandlingMiddleware)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(CorrelationIdMiddleware)


# -------- middleware --------
@app.middleware("http")
async def add_process_time_and_metrics(request: Request, call_next):
    """Add metrics tracking (keeps existing functionality)."""
    start = time.time()
    resp = await call_next(request)
    dur = time.time() - start

    track_request_metrics(request.method, request.url.path, resp.status_code, dur)
    # Note: X-Process-Time is now added by RequestLoggingMiddleware
    return resp


# -------- endpoints --------
@app.get("/health", response_model=HealthResponse)
async def health_check():
    try:
        # db pool stats
        if data_manager:
            pool_stats = await data_manager.get_pool_stats()
            update_db_pool_metrics(pool_stats)
            health_monitor.update_db_health(pool_stats.get("size", 0) > 0)

        # redis ping
        if redis_client:
            await redis_client.ping()
            health_monitor.update_redis_health(True)

        # cache stats
        cache_stats = CacheStats()
        if cache_manager:
            stats = cache_manager.get_stats()
            cache_stats = CacheStats(
                l1_hits=stats.get("l1_hits", 0),
                l2_hits=stats.get("l2_hits", 0),
                l3_hits=stats.get("l3_hits", 0),
                total_misses=stats.get("total_misses", 0),
                hit_rate=stats.get("hit_rate", 0.0),
                memory_cache_size=stats.get("memory_cache_size", 0),
                redis_keys=await redis_client.dbsize() if redis_client else 0,
            )

        s = health_monitor.get_health_status()
        return HealthResponse(
            status=s["status"],
            database=s["database"],
            redis=s["redis"],
            cache_stats=cache_stats,
            uptime=s["uptime"],
            version=settings.api_version,
        )
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return HealthResponse(
            status="unhealthy",
            database="unknown",
            redis="unknown",
            cache_stats=CacheStats(),
            uptime=0,
            version=settings.api_version,
        )


@app.get("/metrics")
async def get_metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
