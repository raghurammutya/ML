"""
Kite Connect API Rate Limiter

Implements rate limiting based on official Kite Connect API limits:
https://kite.trade/docs/connect/v3/exceptions/#api-rate-limit

Per-Second Limits:
- Quote endpoint: 1 req/sec
- Historical data: 3 req/sec
- Order placement: 10 req/sec
- Other endpoints: 10 req/sec

Per-Minute Limits:
- Order placement: 200 req/min

Daily Limits:
- Total orders: 3000 orders/day
"""
from __future__ import annotations

import asyncio
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, time as dtime, timedelta
from enum import Enum
from typing import Deque, Dict, Optional

import pytz
from loguru import logger


class KiteEndpoint(Enum):
    """Kite API endpoint categories with their rate limits"""
    QUOTE = "quote"  # 1 req/sec
    HISTORICAL = "historical"  # 3 req/sec
    ORDER_PLACE = "order_place"  # 10 req/sec, 200 req/min
    ORDER_MODIFY = "order_modify"  # 10 req/sec
    ORDER_CANCEL = "order_cancel"  # 10 req/sec
    DEFAULT = "default"  # 10 req/sec


@dataclass
class RateLimitConfig:
    """Rate limit configuration for an endpoint"""
    requests_per_second: int
    requests_per_minute: Optional[int] = None
    requests_per_day: Optional[int] = None


# Official Kite API rate limits
KITE_RATE_LIMITS: Dict[KiteEndpoint, RateLimitConfig] = {
    KiteEndpoint.QUOTE: RateLimitConfig(
        requests_per_second=1
    ),
    KiteEndpoint.HISTORICAL: RateLimitConfig(
        requests_per_second=3
    ),
    KiteEndpoint.ORDER_PLACE: RateLimitConfig(
        requests_per_second=10,
        requests_per_minute=200,
        requests_per_day=3000
    ),
    KiteEndpoint.ORDER_MODIFY: RateLimitConfig(
        requests_per_second=10
    ),
    KiteEndpoint.ORDER_CANCEL: RateLimitConfig(
        requests_per_second=10
    ),
    KiteEndpoint.DEFAULT: RateLimitConfig(
        requests_per_second=10
    ),
}


class TokenBucket:
    """Token bucket algorithm for rate limiting"""

    def __init__(self, rate: int, capacity: Optional[int] = None):
        """
        Initialize token bucket.

        Args:
            rate: Tokens added per second
            capacity: Maximum tokens (defaults to rate)
        """
        self.rate = rate
        self.capacity = capacity or rate
        self.tokens = float(self.capacity)
        self.last_update = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, tokens: int = 1) -> bool:
        """
        Try to acquire tokens from bucket.

        Args:
            tokens: Number of tokens to acquire

        Returns:
            True if tokens acquired, False otherwise
        """
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_update

            # Add tokens based on elapsed time
            self.tokens = min(
                self.capacity,
                self.tokens + elapsed * self.rate
            )
            self.last_update = now

            # Check if we have enough tokens
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True

            return False

    async def wait_for_token(self, tokens: int = 1, timeout: Optional[float] = None) -> bool:
        """
        Wait until tokens are available.

        Args:
            tokens: Number of tokens to acquire
            timeout: Maximum wait time in seconds

        Returns:
            True if tokens acquired, False if timeout
        """
        start_time = time.monotonic()

        while True:
            if await self.acquire(tokens):
                return True

            # Check timeout
            if timeout and (time.monotonic() - start_time) >= timeout:
                return False

            # Calculate wait time
            async with self._lock:
                tokens_needed = tokens - self.tokens
                wait_time = tokens_needed / self.rate
                wait_time = min(wait_time, 1.0)  # Max 1 second wait

            await asyncio.sleep(wait_time)


class SlidingWindow:
    """Sliding window for per-minute and per-day limits"""

    def __init__(self, window_seconds: int, max_requests: int):
        """
        Initialize sliding window.

        Args:
            window_seconds: Window size in seconds
            max_requests: Maximum requests in window
        """
        self.window_seconds = window_seconds
        self.max_requests = max_requests
        self.requests: Deque[float] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self) -> bool:
        """
        Try to acquire a request slot.

        Returns:
            True if request allowed, False otherwise
        """
        async with self._lock:
            now = time.monotonic()
            cutoff = now - self.window_seconds

            # Remove expired requests
            while self.requests and self.requests[0] < cutoff:
                self.requests.popleft()

            # Check if we can add another request
            if len(self.requests) < self.max_requests:
                self.requests.append(now)
                return True

            return False

    async def wait_for_slot(self, timeout: Optional[float] = None) -> bool:
        """
        Wait until a request slot is available.

        Args:
            timeout: Maximum wait time in seconds

        Returns:
            True if slot acquired, False if timeout
        """
        start_time = time.monotonic()

        while True:
            if await self.acquire():
                return True

            # Check timeout
            if timeout and (time.monotonic() - start_time) >= timeout:
                return False

            # Calculate wait time (when oldest request expires)
            async with self._lock:
                if self.requests:
                    oldest = self.requests[0]
                    now = time.monotonic()
                    wait_time = (oldest + self.window_seconds) - now
                    wait_time = max(0.1, min(wait_time, 1.0))
                else:
                    wait_time = 0.1

            await asyncio.sleep(wait_time)

    def get_current_count(self) -> int:
        """Get current number of requests in window"""
        now = time.monotonic()
        cutoff = now - self.window_seconds
        return sum(1 for req_time in self.requests if req_time >= cutoff)


class KiteRateLimiter:
    """
    Rate limiter for Kite Connect API.

    Enforces per-second, per-minute, and per-day rate limits
    according to official Kite documentation.
    """

    def __init__(self):
        # Per-second limits (token buckets)
        self.per_second_limiters: Dict[KiteEndpoint, TokenBucket] = {}
        for endpoint, config in KITE_RATE_LIMITS.items():
            self.per_second_limiters[endpoint] = TokenBucket(
                rate=config.requests_per_second
            )

        # Per-minute limits (sliding windows)
        self.per_minute_limiters: Dict[KiteEndpoint, SlidingWindow] = {}
        for endpoint, config in KITE_RATE_LIMITS.items():
            if config.requests_per_minute:
                self.per_minute_limiters[endpoint] = SlidingWindow(
                    window_seconds=60,
                    max_requests=config.requests_per_minute
                )

        # Per-day limits (sliding windows)
        self.per_day_limiters: Dict[KiteEndpoint, SlidingWindow] = {}
        for endpoint, config in KITE_RATE_LIMITS.items():
            if config.requests_per_day:
                self.per_day_limiters[endpoint] = SlidingWindow(
                    window_seconds=86400,  # 24 hours
                    max_requests=config.requests_per_day
                )

        # Statistics (protected by lock for thread safety)
        self._stats_lock = threading.Lock()
        self.total_requests = 0
        self.total_wait_time = 0.0
        self.rate_limited_count = 0

        # Daily reset scheduler
        self._reset_task: Optional[asyncio.Task] = None
        self._market_timezone = pytz.timezone('Asia/Kolkata')

    async def acquire(
        self,
        endpoint: KiteEndpoint,
        wait: bool = True,
        timeout: Optional[float] = 30.0
    ) -> bool:
        """
        Acquire rate limit permission for API call.

        Args:
            endpoint: The Kite API endpoint being called
            wait: If True, wait for rate limit. If False, return immediately
            timeout: Maximum wait time in seconds (default 30s)

        Returns:
            True if request allowed, False if rate limited and wait=False
        """
        start_time = time.monotonic()

        # Increment request counter (thread-safe)
        with self._stats_lock:
            self.total_requests += 1

        # Check per-second limit
        per_second = self.per_second_limiters.get(endpoint)
        if per_second:
            if wait:
                success = await per_second.wait_for_token(timeout=timeout)
                if not success:
                    logger.warning(
                        f"Rate limit timeout for {endpoint.value}: per-second limit "
                        f"({KITE_RATE_LIMITS[endpoint].requests_per_second} req/sec)"
                    )
                    with self._stats_lock:
                        self.rate_limited_count += 1
                    return False
            else:
                if not await per_second.acquire():
                    logger.debug(f"Rate limited: {endpoint.value} (per-second)")
                    with self._stats_lock:
                        self.rate_limited_count += 1
                    return False

        # Check per-minute limit
        per_minute = self.per_minute_limiters.get(endpoint)
        if per_minute:
            if timeout:
                remaining_timeout = timeout - (time.monotonic() - start_time)
                # Check if we've already exceeded timeout
                if remaining_timeout <= 0:
                    logger.warning(
                        f"Rate limit timeout exhausted for {endpoint.value} before per-minute check"
                    )
                    with self._stats_lock:
                        self.rate_limited_count += 1
                    return False
            else:
                remaining_timeout = None

            if wait:
                success = await per_minute.wait_for_slot(timeout=remaining_timeout)
                if not success:
                    logger.warning(
                        f"Rate limit timeout for {endpoint.value}: per-minute limit "
                        f"({KITE_RATE_LIMITS[endpoint].requests_per_minute} req/min)"
                    )
                    with self._stats_lock:
                        self.rate_limited_count += 1
                    return False
            else:
                if not await per_minute.acquire():
                    logger.debug(f"Rate limited: {endpoint.value} (per-minute)")
                    with self._stats_lock:
                        self.rate_limited_count += 1
                    return False

        # Check per-day limit
        per_day = self.per_day_limiters.get(endpoint)
        if per_day:
            if timeout:
                remaining_timeout = timeout - (time.monotonic() - start_time)
                # Check if we've already exceeded timeout
                if remaining_timeout <= 0:
                    logger.error(
                        f"Rate limit timeout exhausted for {endpoint.value} before daily check"
                    )
                    with self._stats_lock:
                        self.rate_limited_count += 1
                    return False
            else:
                remaining_timeout = None

            if wait:
                success = await per_day.wait_for_slot(timeout=remaining_timeout)
                if not success:
                    logger.error(
                        f"Rate limit timeout for {endpoint.value}: daily limit "
                        f"({KITE_RATE_LIMITS[endpoint].requests_per_day} req/day) reached!"
                    )
                    with self._stats_lock:
                        self.rate_limited_count += 1
                    return False
            else:
                if not await per_day.acquire():
                    logger.error(f"Daily rate limit reached for {endpoint.value}!")
                    with self._stats_lock:
                        self.rate_limited_count += 1
                    return False

        # Track wait time (thread-safe)
        elapsed = time.monotonic() - start_time
        if elapsed > 0.001:  # Only track significant waits
            with self._stats_lock:
                self.total_wait_time += elapsed
            logger.debug(f"Rate limit wait: {endpoint.value} ({elapsed:.3f}s)")

        return True

    def get_stats(self) -> dict:
        """Get rate limiter statistics (thread-safe)"""
        # Read statistics with lock to ensure consistency
        with self._stats_lock:
            total_requests = self.total_requests
            total_wait_time = self.total_wait_time
            rate_limited_count = self.rate_limited_count

        stats = {
            "total_requests": total_requests,
            "total_wait_time_seconds": round(total_wait_time, 2),
            "rate_limited_count": rate_limited_count,
            "avg_wait_time_ms": round((total_wait_time / total_requests * 1000), 2)
            if total_requests > 0
            else 0,
            "endpoints": {}
        }

        # Per-endpoint stats
        for endpoint in KiteEndpoint:
            endpoint_stats = {}

            # Per-minute counts
            if endpoint in self.per_minute_limiters:
                limiter = self.per_minute_limiters[endpoint]
                endpoint_stats["requests_last_minute"] = limiter.get_current_count()
                endpoint_stats["minute_limit"] = limiter.max_requests

            # Per-day counts
            if endpoint in self.per_day_limiters:
                limiter = self.per_day_limiters[endpoint]
                endpoint_stats["requests_today"] = limiter.get_current_count()
                endpoint_stats["daily_limit"] = limiter.max_requests

            if endpoint_stats:
                stats["endpoints"][endpoint.value] = endpoint_stats

        return stats

    def start_daily_reset_scheduler(self, loop: asyncio.AbstractEventLoop):
        """
        Start background task to reset daily limits at market close (15:30 IST).

        Args:
            loop: Event loop to run the scheduler task
        """
        if self._reset_task is None:
            self._reset_task = loop.create_task(self._daily_reset_loop())
            logger.info("Daily rate limit reset scheduler started (resets at 15:30 IST)")

    async def _daily_reset_loop(self):
        """Background task that resets daily limits at 15:30 IST every day"""
        while True:
            try:
                # Calculate time until next market close (15:30 IST)
                now = datetime.now(self._market_timezone)
                market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)

                # If we're past market close today, schedule for tomorrow
                if now >= market_close:
                    market_close = market_close + timedelta(days=1)

                # Wait until market close
                wait_seconds = (market_close - now).total_seconds()
                logger.info(
                    "Next daily rate limit reset scheduled for %s (in %.1f hours)",
                    market_close.strftime("%Y-%m-%d %H:%M:%S %Z"),
                    wait_seconds / 3600
                )

                await asyncio.sleep(wait_seconds)

                # Reset daily limits
                self.reset_daily_stats()
                logger.info("Daily rate limits reset at market close (15:30 IST)")

            except asyncio.CancelledError:
                logger.info("Daily rate limit reset scheduler cancelled")
                break
            except Exception as e:
                logger.exception("Error in daily reset scheduler: %s", e)
                # Wait 1 hour before retrying on error
                await asyncio.sleep(3600)

    def stop_daily_reset_scheduler(self):
        """Stop the daily reset scheduler"""
        if self._reset_task:
            self._reset_task.cancel()
            self._reset_task = None
            logger.info("Daily rate limit reset scheduler stopped")

    def reset_daily_stats(self):
        """Reset daily statistics (called at market close by scheduler)"""
        logger.info("Resetting daily rate limit statistics")
        for limiter in self.per_day_limiters.values():
            limiter.requests.clear()


# Global rate limiter instance
_kite_rate_limiter: Optional[KiteRateLimiter] = None


def get_rate_limiter() -> KiteRateLimiter:
    """Get global Kite rate limiter instance"""
    global _kite_rate_limiter
    if _kite_rate_limiter is None:
        _kite_rate_limiter = KiteRateLimiter()
    return _kite_rate_limiter
