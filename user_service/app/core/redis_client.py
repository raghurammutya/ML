"""
Redis connection and session management
"""

import json
from typing import Any, Optional
from redis import Redis, ConnectionPool
from app.core.config import settings


class RedisClient:
    """Redis client wrapper for session and cache management"""

    def __init__(self):
        self.pool = ConnectionPool.from_url(
            str(settings.REDIS_URL),
            max_connections=settings.REDIS_POOL_SIZE,
            decode_responses=True
        )
        self.client = Redis(connection_pool=self.pool)

    def get(self, key: str) -> Optional[str]:
        """Get value by key"""
        return self.client.get(key)

    def set(self, key: str, value: str, ttl: Optional[int] = None) -> bool:
        """Set value with optional TTL (seconds)"""
        return self.client.set(key, value, ex=ttl)

    def delete(self, key: str) -> int:
        """Delete key"""
        return self.client.delete(key)

    def exists(self, key: str) -> bool:
        """Check if key exists"""
        return self.client.exists(key) > 0

    def hget(self, name: str, key: str) -> Optional[str]:
        """Get hash field value"""
        return self.client.hget(name, key)

    def hgetall(self, name: str) -> dict:
        """Get all hash fields"""
        return self.client.hgetall(name)

    def hset(self, name: str, key: str, value: str) -> int:
        """Set hash field"""
        return self.client.hset(name, key, value)

    def hmset(self, name: str, mapping: dict) -> bool:
        """Set multiple hash fields"""
        return self.client.hset(name, mapping=mapping)

    def expire(self, key: str, ttl: int) -> bool:
        """Set TTL on existing key"""
        return self.client.expire(key, ttl)

    def ttl(self, key: str) -> int:
        """Get remaining TTL"""
        return self.client.ttl(key)

    def incr(self, key: str) -> int:
        """Increment counter"""
        return self.client.incr(key)

    def publish(self, channel: str, message: str) -> int:
        """Publish message to channel"""
        return self.client.publish(channel, message)

    def publish_json(self, channel: str, data: dict) -> int:
        """Publish JSON message to channel"""
        message = json.dumps(data)
        return self.publish(channel, message)

    # Session management helpers
    def get_session(self, session_id: str) -> Optional[dict]:
        """Get session data"""
        session_data = self.hgetall(f"session:{session_id}")
        return session_data if session_data else None

    def set_session(self, session_id: str, session_data: dict, ttl: int) -> bool:
        """Set session data with TTL"""
        key = f"session:{session_id}"
        self.hmset(key, session_data)
        return self.expire(key, ttl)

    def delete_session(self, session_id: str) -> int:
        """Delete session"""
        return self.delete(f"session:{session_id}")

    # Refresh token family management
    def get_refresh_token(self, jti: str) -> Optional[dict]:
        """Get refresh token family data"""
        token_data = self.hgetall(f"refresh_family:{jti}")
        return token_data if token_data else None

    def set_refresh_token(self, jti: str, token_data: dict, ttl: int) -> bool:
        """Set refresh token family data with TTL"""
        key = f"refresh_family:{jti}"
        self.hmset(key, token_data)
        return self.expire(key, ttl)

    def mark_refresh_token_rotated(self, old_jti: str, new_jti: str) -> bool:
        """Mark refresh token as rotated"""
        return self.hset(f"refresh_family:{old_jti}", "rotated_to", new_jti)

    def delete_refresh_token(self, jti: str) -> int:
        """Delete refresh token family"""
        return self.delete(f"refresh_family:{jti}")

    # Authorization cache
    def get_authz_decision(self, user_id: int, resource: str, action: str) -> Optional[str]:
        """Get cached authorization decision"""
        key = f"authz_decision:{user_id}:{resource}:{action}"
        return self.get(key)

    def set_authz_decision(self, user_id: int, resource: str, action: str, decision: str, ttl: int = 60) -> bool:
        """Cache authorization decision"""
        key = f"authz_decision:{user_id}:{resource}:{action}"
        return self.set(key, decision, ttl=ttl)

    def invalidate_authz_cache(self, user_id: int) -> int:
        """Invalidate all authorization decisions for user"""
        pattern = f"authz_decision:{user_id}:*"
        keys = self.client.keys(pattern)
        if keys:
            return self.client.delete(*keys)
        return 0

    # Rate limiting
    def check_rate_limit(self, key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
        """
        Check rate limit using sliding window
        Returns (allowed, remaining)
        """
        current = self.get(key)
        if current is None:
            self.set(key, "1", ttl=window_seconds)
            return True, limit - 1

        count = int(current)
        if count >= limit:
            return False, 0

        self.incr(key)
        return True, limit - count - 1

    def close(self):
        """Close Redis connection"""
        self.client.close()
        self.pool.disconnect()


# Global Redis client instance
redis_client = RedisClient()


def get_redis() -> RedisClient:
    """Dependency function to get Redis client"""
    return redis_client
