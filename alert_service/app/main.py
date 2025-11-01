"""
Alert Service - Main Application
FastAPI application for managing trading alerts and notifications
"""

import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from .config import get_settings
from .database import get_database_manager, close_database_manager
from .services import ConditionEvaluator, NotificationService
from .background import EvaluationWorker

# Configure logging
settings = get_settings()
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format='{"timestamp": "%(asctime)s", "level": "%(levelname)s", "module": "%(name)s", "message": "%(message)s"}',
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    Handles startup and shutdown events.
    """
    # Startup
    logger.info(f"Starting {settings.app_name} in {settings.environment} mode")

    try:
        # Initialize database
        db_manager = await get_database_manager()
        app.state.db_manager = db_manager
        logger.info("Database connection initialized")

        # Initialize services
        evaluator = ConditionEvaluator()
        notification_service = NotificationService(
            db_manager=db_manager,
            telegram_bot_token=settings.telegram_bot_token,
        )
        app.state.notification_service = notification_service
        logger.info("Services initialized")

        # Initialize and start evaluation worker
        evaluation_worker = None
        if settings.evaluation_worker_enabled:
            evaluation_worker = EvaluationWorker(
                db_manager=db_manager,
                notification_service=notification_service,
                evaluator=evaluator,
            )
            await evaluation_worker.start()
            app.state.evaluation_worker = evaluation_worker
            logger.info("Evaluation worker started")
        else:
            logger.info("Evaluation worker disabled")

        # TODO: Initialize Redis

        logger.info(f"{settings.app_name} started successfully on port {settings.port}")

        yield

    finally:
        # Shutdown
        logger.info(f"Shutting down {settings.app_name}")

        # Stop evaluation worker
        if hasattr(app.state, "evaluation_worker") and app.state.evaluation_worker:
            await app.state.evaluation_worker.stop()
            logger.info("Evaluation worker stopped")

        # Close database
        await close_database_manager()
        logger.info("Database connection closed")

        # TODO: Close Redis connection

        logger.info(f"{settings.app_name} shutdown complete")


# Create FastAPI application
app = FastAPI(
    title="StocksBlitz Alert Service",
    description="Real-time trading alerts and notifications",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: Configure from settings
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Health check endpoint
@app.get("/health")
async def health_check():
    """
    Health check endpoint.
    Returns service status and dependency health.
    """
    from datetime import datetime

    health_status = {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "service": settings.app_name,
        "version": "1.0.0",
        "environment": settings.environment,
    }

    # Check database
    try:
        if hasattr(app.state, "db_manager") and app.state.db_manager.pool:
            async with app.state.db_manager.pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            health_status["database"] = "healthy"
        else:
            health_status["database"] = "not initialized"
            health_status["status"] = "degraded"
    except Exception as e:
        health_status["database"] = f"unhealthy: {e}"
        health_status["status"] = "degraded"

    # TODO: Check Redis health
    # TODO: Check Telegram API health

    return health_status


# Metrics endpoint (Prometheus)
if settings.metrics_enabled:

    @app.get("/metrics")
    async def metrics():
        """Prometheus metrics endpoint."""
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint with service information."""
    return {
        "service": settings.app_name,
        "version": "1.0.0",
        "environment": settings.environment,
        "status": "running",
        "endpoints": {
            "health": "/health",
            "metrics": "/metrics" if settings.metrics_enabled else None,
            "docs": "/docs",
            "alerts": "/alerts",
        },
    }


# Exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "message": "Internal server error",
            "detail": str(exc) if settings.environment == "development" else None,
        },
    )


# Include alert routes
from .routes import alerts
app.include_router(alerts.router, prefix="/alerts", tags=["alerts"])

logger.info("FastAPI application initialized")
logger.info("Alert routes registered at /alerts")
