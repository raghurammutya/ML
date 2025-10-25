from __future__ import annotations

import asyncio
from typing import Optional

import redis.asyncio as redis

from .config import get_settings


class RedisPublisher:
    def __init__(self) -> None:
        self._settings = get_settings()
        self._client: Optional[redis.Redis] = None

    async def connect(self) -> None:
        if self._client:
            return
        self._client = redis.from_url(self._settings.redis_url, decode_responses=True)
        await self._client.ping()

    async def close(self) -> None:
        if self._client:
            await self._client.close()
            self._client = None

    async def publish(self, channel: str, message: str) -> None:
        if not self._client:
            raise RuntimeError("Redis client not initialized")
        await self._client.publish(channel, message)


redis_publisher = RedisPublisher()
