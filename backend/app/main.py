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
from app.routes import marks_asyncpg, labels, indicators, fo, nifty_monitor, label_stream

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
        fo.set_realtime_hub(real_time_hub)
        labels.set_realtime_hub(labels_hub)
        label_stream.set_realtime_hub(labels_hub)

        # Routes
        udf_handler = UDFHandler(data_manager)        # uses DB manager (not cache)
        app.include_router(udf_handler.get_router())
        app.include_router(marks_asyncpg.router)      # asyncpg-backed /marks route
        app.include_router(labels.router)             # labels CRUD endpoints
        app.include_router(label_stream.router)       # labels WebSocket stream
        
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

        if settings.fo_stream_enabled:
            fo_stream_consumer = FOStreamConsumer(redis_client, data_manager, settings, real_time_hub)
            background_tasks.append(asyncio.create_task(fo_stream_consumer.run()))
            logger.info("FO stream consumer started")
        if nifty_monitor_stream:
            background_tasks.append(asyncio.create_task(nifty_monitor_stream.run()))
            logger.info("Nifty monitor stream consumer started")
        if backfill_manager and settings.backfill_enabled:
            background_tasks.append(asyncio.create_task(backfill_manager.run()))
            logger.info("Backfill manager loop started")

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
        if data_manager:
            await data_manager.close()
        if redis_client:
            await redis_client.close()
        if ticker_client:
            await ticker_client.close()

        logger.info("Shutdown complete")


# -------- app --------
app = FastAPI(
    title=settings.api_title,
    version=settings.api_version,
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.cors_credentials,
    allow_methods=settings.cors_methods,
    allow_headers=settings.cors_headers,
)


# -------- middleware --------
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start = time.time()
    resp = await call_next(request)
    dur = time.time() - start

    track_request_metrics(request.method, request.url.path, resp.status_code, dur)
    resp.headers["X-Process-Time"] = str(dur)
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
