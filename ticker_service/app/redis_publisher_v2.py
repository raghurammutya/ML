"""
Resilient Redis Publisher with Backpressure Management

Features:
- Circuit breaker pattern
- Publish timeouts
- Buffered publishing with batching
- Load shedding
- Adaptive sampling
"""
from __future__ import annotations

import asyncio
import threading
import time
from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Deque, Optional

from loguru import logger
import redis.asyncio as redis
from redis.exceptions import ConnectionError as RedisConnectionError, TimeoutError as RedisTimeoutError

from .config import get_settings
from .backpressure_monitor import get_backpressure_monitor


class CircuitState(Enum):
    """Circuit breaker states"""
    CLOSED = "closed"  # Normal operation
    OPEN = "open"      # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if recovered


@dataclass
class CircuitBreaker:
    """Thread-safe circuit breaker for Redis connection"""
    failure_threshold: int = 5
    recovery_timeout: float = 30.0
    success_threshold: int = 2

    def __post_init__(self):
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[float] = None
        self._lock = threading.Lock()  # Protect state transitions

    def record_success(self):
        """Record successful operation (thread-safe)"""
        with self._lock:
            self.failure_count = 0

            if self.state == CircuitState.HALF_OPEN:
                self.success_count += 1
                if self.success_count >= self.success_threshold:
                    logger.info("Circuit breaker recovered - closing circuit")
                    self.state = CircuitState.CLOSED
                    self.success_count = 0

    def record_failure(self):
        """Record failed operation (thread-safe)"""
        with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.time()
            self.success_count = 0

            if self.failure_count >= self.failure_threshold:
                if self.state != CircuitState.OPEN:
                    logger.error(
                        f"Circuit breaker threshold reached ({self.failure_count} failures) - opening circuit"
                    )
                self.state = CircuitState.OPEN

    def can_attempt(self) -> bool:
        """Check if operation should be attempted (thread-safe)"""
        with self._lock:
            if self.state == CircuitState.CLOSED:
                return True

            if self.state == CircuitState.OPEN:
                # Check if recovery timeout has passed
                if self.last_failure_time and (time.time() - self.last_failure_time) >= self.recovery_timeout:
                    logger.info("Circuit breaker recovery timeout passed - entering half-open state")
                    self.state = CircuitState.HALF_OPEN
                    return True
                return False

            # HALF_OPEN state
            return True

    def get_state(self) -> CircuitState:
        """Get current circuit state (thread-safe)"""
        with self._lock:
            return self.state


class ResilientRedisPublisher:
    """
    Redis publisher with backpressure management.

    Features:
    - Circuit breaker for fault tolerance
    - Publish timeouts to prevent hanging
    - Buffered publishing with batching
    - Load shedding when overwhelmed
    - Adaptive sampling based on backpressure
    """

    def __init__(
        self,
        publish_timeout: float = 1.0,
        buffer_size: int = 10000,
        batch_size: int = 100,
        batch_interval: float = 0.1,
        enable_sampling: bool = True,
        enable_load_shedding: bool = True
    ):
        self._settings = get_settings()
        self._client: Optional[redis.Redis] = None
        self._lock = asyncio.Lock()

        # Configuration
        self.publish_timeout = publish_timeout
        self.buffer_size = buffer_size
        self.batch_size = batch_size
        self.batch_interval = batch_interval
        self.enable_sampling = enable_sampling
        self.enable_load_shedding = enable_load_shedding

        # Circuit breaker
        self.circuit_breaker = CircuitBreaker()

        # Backpressure monitor
        self.monitor = get_backpressure_monitor()

        # Buffering
        self._buffer: Deque[tuple[str, str]] = deque(maxlen=buffer_size)
        self._buffer_task: Optional[asyncio.Task] = None
        self._stop_buffer = asyncio.Event()

        # Statistics
        self._total_published = 0
        self._total_dropped = 0
        self._total_sampled_out = 0

    async def connect(self) -> None:
        """Connect to Redis"""
        if self._client:
            return

        async with self._lock:
            if self._client:
                return

            client = redis.from_url(
                self._settings.redis_url,
                decode_responses=True,
                socket_timeout=self.publish_timeout,
                socket_connect_timeout=5.0
            )

            try:
                await client.ping()
            except Exception as exc:
                await client.close()
                logger.error("Redis ping failed during connect: %s", exc)
                raise

            self._client = client
            logger.info(f"Connected to Redis at {self._settings.redis_url}")

            # Start buffer worker
            self._buffer_task = asyncio.create_task(self._buffer_worker())

    async def close(self) -> None:
        """Close Redis connection"""
        # Stop buffer worker
        if self._buffer_task:
            self._stop_buffer.set()
            try:
                await asyncio.wait_for(self._buffer_task, timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("Buffer worker did not stop gracefully")
                self._buffer_task.cancel()

        async with self._lock:
            if self._client:
                await self._client.close()
                self._client = None
                logger.info("Redis connection closed")

    async def publish(self, channel: str, message: str, bypass_buffer: bool = False) -> bool:
        """
        Publish message to Redis channel.

        Args:
            channel: Redis channel name
            message: Message to publish
            bypass_buffer: If True, publish immediately without buffering

        Returns:
            True if published successfully, False if dropped/failed
        """
        if not self._client:
            await self.connect()

        # Record tick received
        self.monitor.record_tick_received()

        # Check circuit breaker
        if not self.circuit_breaker.can_attempt():
            logger.debug(f"Circuit breaker open - dropping message to {channel}")
            self.monitor.record_tick_dropped()
            self._total_dropped += 1
            return False

        # Check load shedding
        if self.enable_load_shedding and self.monitor.should_drop_message():
            logger.debug(f"Load shedding active - dropping message to {channel}")
            self.monitor.record_tick_dropped()
            self._total_dropped += 1
            return False

        # Apply adaptive sampling
        if self.enable_sampling:
            sampling_rate = self.monitor.should_apply_sampling()
            if sampling_rate is not None:
                import random
                if random.random() > sampling_rate:
                    self._total_sampled_out += 1
                    return False  # Sampled out

        # Immediate publish (bypass buffer)
        if bypass_buffer:
            return await self._publish_immediate(channel, message)

        # Buffered publish
        try:
            self._buffer.append((channel, message))
            self.monitor.update_pending_count(len(self._buffer))
            return True
        except IndexError:
            # Buffer full (deque maxlen exceeded)
            logger.warning(f"Buffer full ({self.buffer_size}) - dropping message")
            self.monitor.record_tick_dropped()
            self._total_dropped += 1
            return False

    async def _publish_immediate(self, channel: str, message: str) -> bool:
        """Publish message immediately without buffering"""
        start_time = time.time()

        try:
            await asyncio.wait_for(
                self._client.publish(channel, message),
                timeout=self.publish_timeout
            )

            # Success
            latency = time.time() - start_time
            self.monitor.record_tick_published(latency)
            self.circuit_breaker.record_success()
            self._total_published += 1

            logger.debug(f"Published to {channel} (latency={latency*1000:.2f}ms)")
            return True

        except asyncio.TimeoutError:
            logger.warning(f"Redis publish timeout after {self.publish_timeout}s on channel {channel}")
            self.monitor.record_redis_error()
            self.circuit_breaker.record_failure()
            return False

        except (RedisConnectionError, RedisTimeoutError) as exc:
            logger.warning(f"Redis publish failed on channel {channel}: {exc}")
            self.monitor.record_redis_error()
            self.circuit_breaker.record_failure()
            await self._reset()
            return False

        except Exception as exc:
            logger.exception(f"Unexpected error publishing to {channel}: {exc}")
            self.monitor.record_redis_error()
            self.circuit_breaker.record_failure()
            return False

    async def _buffer_worker(self):
        """Background worker that flushes buffer in batches"""
        logger.info(
            f"Buffer worker started (batch_size={self.batch_size}, interval={self.batch_interval}s)"
        )

        while not self._stop_buffer.is_set():
            try:
                # Wait for batch interval or stop signal
                try:
                    await asyncio.wait_for(
                        self._stop_buffer.wait(),
                        timeout=self.batch_interval
                    )
                    # Stop signal received
                    break
                except asyncio.TimeoutError:
                    # Timeout - time to flush batch
                    pass

                # Flush batch
                await self._flush_batch()

            except Exception as exc:
                logger.exception(f"Buffer worker error: {exc}")
                await asyncio.sleep(1.0)

        # Final flush on shutdown
        logger.info("Buffer worker stopping - flushing remaining messages")
        await self._flush_batch()
        logger.info("Buffer worker stopped")

    async def _flush_batch(self):
        """Flush a batch of messages from buffer"""
        if not self._buffer:
            return

        # Extract batch
        batch = []
        for _ in range(min(self.batch_size, len(self._buffer))):
            if self._buffer:
                batch.append(self._buffer.popleft())

        if not batch:
            return

        # Update pending count
        self.monitor.update_pending_count(len(self._buffer))

        # Publish batch
        logger.debug(f"Flushing batch of {len(batch)} messages")

        # Use pipeline for efficiency
        if self._client:
            pipe = self._client.pipeline()
            for channel, message in batch:
                pipe.publish(channel, message)

            start_time = time.time()
            try:
                await asyncio.wait_for(pipe.execute(), timeout=self.publish_timeout * len(batch))

                # Success
                latency = (time.time() - start_time) / len(batch)  # Average latency per message
                for _ in batch:
                    self.monitor.record_tick_published(latency)
                    self._total_published += 1

                self.circuit_breaker.record_success()
                logger.debug(f"Batch published successfully (avg_latency={latency*1000:.2f}ms)")

            except asyncio.TimeoutError:
                logger.warning(f"Batch publish timeout - dropping {len(batch)} messages")
                for _ in batch:
                    self.monitor.record_tick_dropped()
                    self._total_dropped += 1
                self.circuit_breaker.record_failure()

            except Exception as exc:
                logger.error(f"Batch publish failed: {exc} - dropping {len(batch)} messages")
                for _ in batch:
                    self.monitor.record_tick_dropped()
                    self._total_dropped += 1
                self.circuit_breaker.record_failure()
                await self._reset()

    async def _reset(self) -> None:
        """Reset Redis connection"""
        async with self._lock:
            if self._client:
                try:
                    await self._client.close()
                except Exception:
                    logger.exception("Failed to close Redis client during reset")
            self._client = None
        await self.connect()

    def get_stats(self) -> dict:
        """Get publisher statistics"""
        return {
            "total_published": self._total_published,
            "total_dropped": self._total_dropped,
            "total_sampled_out": self._total_sampled_out,
            "buffer_size": len(self._buffer),
            "buffer_capacity": self.buffer_size,
            "circuit_breaker_state": self.circuit_breaker.get_state().value,
            "circuit_breaker_failures": self.circuit_breaker.failure_count,
            "backpressure_metrics": self.monitor.get_status_summary()
        }


# Global resilient publisher instance
_resilient_publisher: Optional[ResilientRedisPublisher] = None


def get_resilient_publisher() -> ResilientRedisPublisher:
    """Get global resilient publisher instance"""
    global _resilient_publisher
    if _resilient_publisher is None:
        _resilient_publisher = ResilientRedisPublisher()
    return _resilient_publisher
