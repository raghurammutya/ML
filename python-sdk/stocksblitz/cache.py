"""
Caching layer for API responses.
"""

import time
from typing import Any, Optional, Dict
from threading import Lock
from .exceptions import CacheError


class SimpleCache:
    """
    Simple in-memory cache with TTL support.

    For production, this can be replaced with Redis.
    """

    def __init__(self, default_ttl: int = 60):
        """
        Initialize cache.

        Args:
            default_ttl: Default time-to-live in seconds
        """
        self._cache: Dict[str, tuple] = {}  # key -> (value, expiry_time)
        self._lock = Lock()
        self.default_ttl = default_ttl

    def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found/expired
        """
        with self._lock:
            if key not in self._cache:
                return None

            value, expiry = self._cache[key]

            # Check expiry
            if expiry and time.time() > expiry:
                del self._cache[key]
                return None

            return value

    def set(self, key: str, value: Any, ttl: Optional[int] = None):
        """
        Set value in cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time-to-live in seconds (None for no expiry)
        """
        if ttl is None:
            ttl = self.default_ttl

        expiry = time.time() + ttl if ttl else None

        with self._lock:
            self._cache[key] = (value, expiry)

    def delete(self, key: str):
        """Delete key from cache."""
        with self._lock:
            if key in self._cache:
                del self._cache[key]

    def clear(self):
        """Clear entire cache."""
        with self._lock:
            self._cache.clear()

    def has(self, key: str) -> bool:
        """Check if key exists and is not expired."""
        return self.get(key) is not None


def cache_key(*parts) -> str:
    """
    Generate cache key from parts.

    Args:
        *parts: Key components

    Returns:
        Cache key string

    Example:
        >>> cache_key("instrument", "NIFTY50", "5min", "rsi", 14)
        'instrument:NIFTY50:5min:rsi:14'
    """
    return ":".join(str(p) for p in parts)
