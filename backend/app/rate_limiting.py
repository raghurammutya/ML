"""
Rate limiting middleware with support for IP-based and user-based limits.

Features:
1. IP-based rate limiting (current - no user service)
2. User-based rate limiting (future - when user service ready)
3. Tiered rate limits (free, premium, enterprise)
4. Endpoint-specific limits
5. Token bucket algorithm for burst handling
6. Redis-based distributed rate limiting
"""

import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Dict, Optional, Tuple

import redis.asyncio as redis
from fastapi import HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from prometheus_client import Counter, Histogram
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

# ============================================================================
# PROMETHEUS METRICS
# ============================================================================

rate_limit_hits = Counter(
    'rate_limit_hits_total',
    'Number of rate limit hits',
    ['identifier_type', 'tier', 'endpoint']
)

rate_limit_blocks = Counter(
    'rate_limit_blocks_total',
    'Number of rate limit blocks',
    ['identifier_type', 'tier', 'endpoint']
)

rate_limit_remaining = Histogram(
    'rate_limit_remaining_requests',
    'Remaining requests before rate limit',
    ['identifier_type', 'tier']
)


# ============================================================================
# RATE LIMIT TIERS
# ============================================================================

class RateLimitTier(Enum):
    """Rate limit tiers."""
    FREE = "free"
    PREMIUM = "premium"
    ENTERPRISE = "enterprise"
    INTERNAL = "internal"


@dataclass
class RateLimitConfig:
    """Rate limit configuration."""
    requests_per_second: int
    requests_per_minute: int
    requests_per_hour: int
    burst_size: int  # Maximum burst allowed

    # Endpoint-specific overrides
    endpoint_limits: Dict[str, Dict[str, int]] = None

    def get_limit_for_endpoint(self, endpoint: str, period: str) -> int:
        """Get rate limit for specific endpoint and period."""
        if self.endpoint_limits and endpoint in self.endpoint_limits:
            return self.endpoint_limits[endpoint].get(
                period,
                getattr(self, f"requests_per_{period}")
            )
        return getattr(self, f"requests_per_{period}")


# Default tier configurations
TIER_CONFIGS = {
    RateLimitTier.FREE: RateLimitConfig(
        requests_per_second=5,
        requests_per_minute=100,
        requests_per_hour=1000,
        burst_size=10,
        endpoint_limits={
            "/fo/moneyness-series": {"second": 2, "minute": 30, "hour": 300},
            "/fo/strike-distribution": {"second": 2, "minute": 30, "hour": 300},
            "/history": {"second": 5, "minute": 100, "hour": 1000},
        }
    ),
    RateLimitTier.PREMIUM: RateLimitConfig(
        requests_per_second=20,
        requests_per_minute=500,
        requests_per_hour=10000,
        burst_size=50,
    ),
    RateLimitTier.ENTERPRISE: RateLimitConfig(
        requests_per_second=100,
        requests_per_minute=3000,
        requests_per_hour=50000,
        burst_size=200,
    ),
    RateLimitTier.INTERNAL: RateLimitConfig(
        requests_per_second=1000,
        requests_per_minute=30000,
        requests_per_hour=500000,
        burst_size=2000,
    ),
}


# ============================================================================
# TOKEN BUCKET RATE LIMITER
# ============================================================================

class TokenBucket:
    """Token bucket algorithm for rate limiting with burst support."""

    def __init__(
        self,
        rate: float,  # tokens per second
        capacity: int,  # bucket capacity
    ):
        self.rate = rate
        self.capacity = capacity
        self.tokens = capacity
        self.last_update = time.time()

    def _refill(self):
        """Refill tokens based on time elapsed."""
        now = time.time()
        elapsed = now - self.last_update
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        self.last_update = now

    def consume(self, tokens: int = 1) -> Tuple[bool, float]:
        """
        Try to consume tokens.

        Returns:
            (allowed, retry_after_seconds)
        """
        self._refill()

        if self.tokens >= tokens:
            self.tokens -= tokens
            return True, 0.0

        # Calculate retry after
        tokens_needed = tokens - self.tokens
        retry_after = tokens_needed / self.rate
        return False, retry_after

    def get_remaining(self) -> int:
        """Get remaining tokens."""
        self._refill()
        return int(self.tokens)


# ============================================================================
# REDIS-BASED DISTRIBUTED RATE LIMITER
# ============================================================================

class RedisRateLimiter:
    """Redis-based distributed rate limiter."""

    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client

    async def check_rate_limit(
        self,
        identifier: str,
        config: RateLimitConfig,
        endpoint: str = ""
    ) -> Tuple[bool, Dict[str, any]]:
        """
        Check if request is within rate limit.

        Returns:
            (allowed, metadata)
            metadata includes: remaining, reset_time, retry_after
        """
        now = time.time()
        periods = {
            "second": (1, config.get_limit_for_endpoint(endpoint, "second")),
            "minute": (60, config.get_limit_for_endpoint(endpoint, "minute")),
            "hour": (3600, config.get_limit_for_endpoint(endpoint, "hour")),
        }

        for period_name, (window, limit) in periods.items():
            key = f"rate_limit:{identifier}:{period_name}:{int(now / window)}"

            try:
                # Increment counter
                count = await self.redis.incr(key)

                # Set expiry on first request
                if count == 1:
                    await self.redis.expire(key, int(window * 2))  # 2x window for safety

                if count > limit:
                    # Rate limit exceeded
                    ttl = await self.redis.ttl(key)
                    reset_time = now + ttl

                    return False, {
                        "remaining": 0,
                        "limit": limit,
                        "reset": int(reset_time),
                        "retry_after": ttl,
                        "period": period_name
                    }

            except Exception as e:
                logger.error(f"Redis rate limit check failed: {e}")
                # Fail open - allow request if Redis is down
                return True, {
                    "remaining": limit,
                    "limit": limit,
                    "reset": int(now + window),
                    "retry_after": 0,
                    "period": period_name
                }

        # All periods passed
        remaining = limit - count
        return True, {
            "remaining": remaining,
            "limit": limit,
            "reset": int(now + 60),  # Use minute window for reset
            "retry_after": 0,
            "period": "minute"
        }


# ============================================================================
# RATE LIMITER IDENTIFIER STRATEGIES
# ============================================================================

class IdentifierStrategy:
    """Base class for identifier strategies."""

    async def get_identifier(self, request: Request) -> str:
        """Get unique identifier for rate limiting."""
        raise NotImplementedError

    def get_type(self) -> str:
        """Get identifier type name."""
        raise NotImplementedError


class IPBasedIdentifier(IdentifierStrategy):
    """IP-based identifier (current)."""

    async def get_identifier(self, request: Request) -> str:
        # Get real IP from X-Forwarded-For or X-Real-IP headers
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            ip = forwarded.split(",")[0].strip()
        else:
            ip = request.headers.get("X-Real-IP") or request.client.host

        # Hash IP for privacy
        return hashlib.sha256(ip.encode()).hexdigest()[:16]

    def get_type(self) -> str:
        return "ip"


class UserBasedIdentifier(IdentifierStrategy):
    """User-based identifier (future - requires user service)."""

    async def get_identifier(self, request: Request) -> str:
        # TODO: Extract user_id from JWT token or session
        # This will be implemented when user service is ready

        # For now, check if there's an Authorization header
        auth_header = request.headers.get("Authorization")
        if auth_header:
            # Extract user_id from JWT (simplified)
            # In production, properly decode and validate JWT
            token = auth_header.replace("Bearer ", "")
            return f"user:{token[:16]}"  # Placeholder

        # Fallback to IP-based
        return await IPBasedIdentifier().get_identifier(request)

    def get_type(self) -> str:
        return "user"


class APIKeyBasedIdentifier(IdentifierStrategy):
    """API key-based identifier."""

    async def get_identifier(self, request: Request) -> str:
        # Check for API key in headers
        api_key = request.headers.get("X-API-Key")
        if api_key:
            # Hash for privacy
            return hashlib.sha256(api_key.encode()).hexdigest()[:16]

        # Fallback to IP-based
        return await IPBasedIdentifier().get_identifier(request)

    def get_type(self) -> str:
        return "api_key"


# ============================================================================
# TIER RESOLVER
# ============================================================================

class TierResolver:
    """Resolves rate limit tier for a request."""

    def __init__(self, user_service_available: bool = False):
        self.user_service_available = user_service_available

    async def get_tier(self, request: Request) -> RateLimitTier:
        """Get rate limit tier for request."""

        # Check for internal service token
        if request.headers.get("X-Internal-Service") == "true":
            return RateLimitTier.INTERNAL

        # TODO: When user service is ready, fetch user's subscription tier
        # if self.user_service_available:
        #     user_id = await extract_user_id(request)
        #     tier = await user_service.get_user_tier(user_id)
        #     return tier

        # Check for API key tier (if you have api_keys table)
        api_key = request.headers.get("X-API-Key")
        if api_key:
            # TODO: Look up API key tier in database
            # For now, default to FREE
            pass

        # Default to FREE tier
        return RateLimitTier.FREE


# ============================================================================
# RATE LIMITING MIDDLEWARE
# ============================================================================

class RateLimitMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware for rate limiting."""

    def __init__(
        self,
        app,
        redis_client: redis.Redis,
        identifier_strategy: IdentifierStrategy = None,
        tier_resolver: TierResolver = None,
        exempt_endpoints: list = None,
    ):
        super().__init__(app)
        self.rate_limiter = RedisRateLimiter(redis_client)
        self.identifier_strategy = identifier_strategy or IPBasedIdentifier()
        self.tier_resolver = tier_resolver or TierResolver()
        self.exempt_endpoints = exempt_endpoints or [
            "/health",
            "/metrics",
            "/docs",
            "/openapi.json"
        ]

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with rate limiting."""

        # Skip rate limiting for exempt endpoints
        if request.url.path in self.exempt_endpoints:
            return await call_next(request)

        try:
            # Get identifier and tier
            identifier = await self.identifier_strategy.get_identifier(request)
            tier = await self.tier_resolver.get_tier(request)
            config = TIER_CONFIGS[tier]

            # Check rate limit
            allowed, metadata = await self.rate_limiter.check_rate_limit(
                identifier=identifier,
                config=config,
                endpoint=request.url.path
            )

            # Update metrics
            rate_limit_hits.labels(
                identifier_type=self.identifier_strategy.get_type(),
                tier=tier.value,
                endpoint=request.url.path
            ).inc()

            if not allowed:
                # Rate limit exceeded
                rate_limit_blocks.labels(
                    identifier_type=self.identifier_strategy.get_type(),
                    tier=tier.value,
                    endpoint=request.url.path
                ).inc()

                logger.warning(
                    f"Rate limit exceeded for {identifier}",
                    extra={
                        "identifier": identifier,
                        "tier": tier.value,
                        "endpoint": request.url.path,
                        "metadata": metadata
                    }
                )

                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={
                        "error": "Rate limit exceeded",
                        "retry_after": metadata["retry_after"],
                        "limit": metadata["limit"],
                        "period": metadata["period"]
                    },
                    headers={
                        "X-RateLimit-Limit": str(metadata["limit"]),
                        "X-RateLimit-Remaining": "0",
                        "X-RateLimit-Reset": str(metadata["reset"]),
                        "Retry-After": str(int(metadata["retry_after"]))
                    }
                )

            # Request allowed - add rate limit headers
            response = await call_next(request)
            response.headers["X-RateLimit-Limit"] = str(metadata["limit"])
            response.headers["X-RateLimit-Remaining"] = str(metadata["remaining"])
            response.headers["X-RateLimit-Reset"] = str(metadata["reset"])

            # Update remaining requests metric
            rate_limit_remaining.labels(
                identifier_type=self.identifier_strategy.get_type(),
                tier=tier.value
            ).observe(metadata["remaining"])

            return response

        except Exception as e:
            logger.error(f"Rate limiting middleware error: {e}")
            # Fail open - allow request if rate limiting fails
            return await call_next(request)


# ============================================================================
# USAGE TRACKING (for future user service integration)
# ============================================================================

class UsageTracker:
    """Track API usage per user for billing/analytics."""

    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client

    async def track_request(
        self,
        user_id: str,
        endpoint: str,
        tokens_used: int = 1,
        cost: float = 0.0
    ):
        """Track API request for user."""
        today = time.strftime("%Y-%m-%d")

        # Increment daily usage
        await self.redis.hincrby(
            f"usage:{user_id}:{today}",
            "requests",
            tokens_used
        )

        # Track cost (for billing)
        if cost > 0:
            await self.redis.hincrbyfloat(
                f"usage:{user_id}:{today}",
                "cost",
                cost
            )

        # Set expiry (keep usage data for 90 days)
        await self.redis.expire(f"usage:{user_id}:{today}", 90 * 24 * 3600)

    async def get_usage(self, user_id: str, date: str = None) -> Dict:
        """Get usage statistics for user."""
        if date is None:
            date = time.strftime("%Y-%m-%d")

        usage = await self.redis.hgetall(f"usage:{user_id}:{date}")
        return {
            "date": date,
            "requests": int(usage.get(b"requests", 0)),
            "cost": float(usage.get(b"cost", 0.0))
        }


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

async def get_client_identifier(request: Request) -> str:
    """Get client identifier (IP or user_id)."""
    # Try user-based first (when user service ready)
    auth_header = request.headers.get("Authorization")
    if auth_header:
        # TODO: Extract and validate user_id from JWT
        pass

    # Fallback to IP-based
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        ip = forwarded.split(",")[0].strip()
    else:
        ip = request.headers.get("X-Real-IP") or request.client.host

    return hashlib.sha256(ip.encode()).hexdigest()[:16]


def create_rate_limit_middleware(
    redis_client: redis.Redis,
    use_user_based: bool = False
) -> RateLimitMiddleware:
    """
    Factory function to create rate limit middleware.

    Args:
        redis_client: Redis client for distributed rate limiting
        use_user_based: Use user-based identifier (requires user service)

    Returns:
        Configured RateLimitMiddleware
    """
    identifier_strategy = (
        UserBasedIdentifier() if use_user_based
        else IPBasedIdentifier()
    )

    tier_resolver = TierResolver(user_service_available=use_user_based)

    return lambda app: RateLimitMiddleware(
        app=app,
        redis_client=redis_client,
        identifier_strategy=identifier_strategy,
        tier_resolver=tier_resolver
    )
