from __future__ import annotations

import asyncio
from typing import Optional

from loguru import logger

import redis.asyncio as redis
from redis.exceptions import ConnectionError as RedisConnectionError, TimeoutError as RedisTimeoutError

from .config import get_settings


class RedisPublisher:
    def __init__(self) -> None:
        self._settings = get_settings()
        self._client: Optional[redis.Redis] = None
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        if self._client:
            return
        async with self._lock:
            if self._client:
                return
            client = redis.from_url(self._settings.redis_url, decode_responses=True)
            try:
                await client.ping()
            except Exception as exc:  # pragma: no cover - depends on runtime redis state
                await client.close()
                logger.error("Redis ping failed during connect: %s", exc)
                raise
            self._client = client
            logger.info(f"Connected to Redis at {self._settings.redis_url}")

    async def close(self) -> None:
        async with self._lock:
            if self._client:
                await self._client.close()
                self._client = None
                logger.info("Redis connection closed")

    async def publish(self, channel: str, message: str) -> None:
        if not self._client:
            await self.connect()
        if not self._client:
            raise RuntimeError("Redis client not initialized")

        for attempt in (1, 2):
            try:
                await self._client.publish(channel, message)
                logger.debug(f"Published message to Redis channel={channel} size={len(message)}")
                return
            except (RedisConnectionError, RedisTimeoutError) as exc:
                logger.warning(
                    "Redis publish failed (attempt %d) on channel %s: %s",
                    attempt,
                    channel,
                    exc,
                )
                await self._reset()
        raise RuntimeError(f"Failed to publish message to {channel} after retries")

    async def _reset(self) -> None:
        async with self._lock:
            if self._client:
                try:
                    await self._client.close()
                except Exception:  # pragma: no cover - defensive
                    logger.exception("Failed to close Redis client during reset")
            self._client = None
        await self.connect()


redis_publisher = RedisPublisher()
