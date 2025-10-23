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
from app.routes import marks_asyncpg, labels

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
    global data_manager, cache_manager, redis_client

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

        # Routes
        udf_handler = UDFHandler(data_manager)        # uses DB manager (not cache)
        app.include_router(udf_handler.get_router())
        app.include_router(marks_asyncpg.router)      # asyncpg-backed /marks route
        app.include_router(labels.router)             # labels CRUD endpoints
        logger.info("UDF routes included successfully")

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

        if data_manager:
            await data_manager.close()
        if redis_client:
            await redis_client.close()

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
