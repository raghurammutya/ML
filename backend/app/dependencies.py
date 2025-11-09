# app/dependencies.py
"""Common dependency functions for FastAPI routes."""

from typing import Optional
from .cache import CacheManager

# This will be set by main.py during startup
_cache_manager: Optional[CacheManager] = None

def set_cache_manager(cache_manager: CacheManager):
    """Set the global cache manager instance."""
    global _cache_manager
    _cache_manager = cache_manager

def get_cache_manager() -> CacheManager:
    """Dependency to get CacheManager instance."""
    if _cache_manager is None:
        raise RuntimeError("Cache manager not initialized")
    return _cache_manager