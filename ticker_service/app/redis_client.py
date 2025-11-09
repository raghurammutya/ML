from __future__ import annotations

import asyncio
from typing import Optional

from loguru import logger
from prometheus_client import Counter, Gauge

import redis.asyncio as redis
from redis.exceptions import ConnectionError as RedisConnectionError, TimeoutError as RedisTimeoutError

from .config import get_settings
from .utils.circuit_breaker import CircuitBreaker, CircuitState

# Prometheus metrics
redis_publish_total = Counter("redis_publish_total", "Total Redis publish attempts")
redis_publish_failures = Counter("redis_publish_failures", "Total Redis publish failures")
redis_circuit_open_drops = Counter("redis_circuit_open_drops", "Messages dropped when circuit open")
redis_circuit_state = Gauge("redis_circuit_state", "Circuit breaker state (0=closed, 1=open, 2=half_open)")


class RedisPublisher:
    def __init__(self) -> None:
        self._settings = get_settings()
        self._client: Optional[redis.Redis] = None
        # ARCH-P0-002 FIX: Add connection pool for better performance under load
        self._pool: Optional[redis.ConnectionPool] = None
        self._lock = asyncio.Lock()

        # Circuit breaker for fault tolerance
        self._circuit_breaker = CircuitBreaker(
            failure_threshold=10,
            recovery_timeout_seconds=60.0,
            half_open_max_attempts=3,
            name="redis_publisher",
        )

    async def connect(self) -> None:
        if self._client:
            return
        async with self._lock:
            if self._client:
                return

            # ARCH-P0-002 FIX: Create connection pool instead of single connection
            # Pool configuration optimized for high-throughput publish workload
            # - max_connections: 50 (allows concurrent publishes without blocking)
            # - socket_timeout: 5s (prevents hanging on slow network)
            # - socket_keepalive: True (prevents idle connection drops)
            self._pool = redis.ConnectionPool.from_url(
                self._settings.redis_url,
                decode_responses=True,
                max_connections=50,  # Support up to 50 concurrent operations
                socket_timeout=5.0,  # 5 second timeout for socket operations
                socket_keepalive=True,  # Keep connections alive
                socket_keepalive_options={},  # Use OS defaults
                retry_on_timeout=True,  # Retry on timeout
            )

            # Create client from pool
            client = redis.Redis(connection_pool=self._pool)

            try:
                await client.ping()
            except Exception as exc:  # pragma: no cover - depends on runtime redis state
                await client.close()
                if self._pool:
                    await self._pool.disconnect()
                    self._pool = None
                logger.error("Redis ping failed during connect: %s", exc)
                raise
            self._client = client
            logger.info(
                f"Connected to Redis at {self._settings.redis_url} "
                f"(pool: max_connections=50, timeout=5s)"
            )

    async def close(self) -> None:
        async with self._lock:
            if self._client:
                await self._client.close()
                self._client = None

            # ARCH-P0-002 FIX: Also close connection pool
            if self._pool:
                await self._pool.disconnect()
                self._pool = None

            logger.info("Redis connection and pool closed")

    async def publish(self, channel: str, message: str) -> None:
        redis_publish_total.inc()

        # Update circuit state metric
        state = self._circuit_breaker.get_state()
        redis_circuit_state.set(
            0 if state == CircuitState.CLOSED else 1 if state == CircuitState.OPEN else 2
        )

        # Check circuit state
        if not await self._circuit_breaker.can_execute():
            # Circuit OPEN - drop message gracefully
            redis_circuit_open_drops.inc()
            logger.warning(
                f"Redis circuit breaker OPEN, dropping message | channel={channel} size={len(message)}"
            )
            return  # DON'T block streaming!

        if not self._client:
            await self.connect()
        if not self._client:
            logger.error("Redis client not initialized, dropping message")
            redis_publish_failures.inc()
            await self._circuit_breaker.record_failure()
            return  # Drop, don't raise

        # Attempt publish with retries
        for attempt in (1, 2):
            try:
                await self._client.publish(channel, message)
                await self._circuit_breaker.record_success()
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
                if attempt == 2:
                    # Final failure - record in circuit breaker
                    redis_publish_failures.inc()
                    await self._circuit_breaker.record_failure(exc)
                    logger.error(
                        f"Redis publish failed after retries, circuit may open | "
                        f"channel={channel} error={exc}"
                    )
                    return  # Drop, don't raise

    async def _reset(self) -> None:
        async with self._lock:
            if self._client:
                try:
                    await self._client.close()
                except Exception:  # pragma: no cover - defensive
                    logger.exception("Failed to close Redis client during reset")
            self._client = None

            # ARCH-P0-002 FIX: Also reset connection pool
            if self._pool:
                try:
                    await self._pool.disconnect()
                except Exception:  # pragma: no cover - defensive
                    logger.exception("Failed to disconnect Redis pool during reset")
            self._pool = None

        await self.connect()


redis_publisher = RedisPublisher()
