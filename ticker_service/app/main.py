from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from loguru import logger

from .config import get_settings
from .redis_client import redis_publisher

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        logger.info("Starting %s", settings.app_name)
        await redis_publisher.connect()
        yield
    finally:
        await redis_publisher.close()
        logger.info("Shutdown complete")


app = FastAPI(title="Ticker Service", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "environment": settings.environment}
