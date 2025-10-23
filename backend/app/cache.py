import asyncio
import json
import logging
from typing import Any, Optional, Dict, Tuple
from datetime import datetime, timedelta
import redis.asyncio as redis
from functools import wraps
import hashlib

logger = logging.getLogger(__name__)

class CacheManager:
    def __init__(self, redis_client: redis.Redis):
        from .config import get_settings
        self.settings = get_settings()
        self.redis = redis_client
        self.memory_cache: Dict[str, Tuple[Any, float]] = {}
        self.stats = {
            "l1_hits": 0,
            "l2_hits": 0,
            "l3_hits": 0,
            "total_misses": 0
        }
        
    def get_cache_key(self, prefix: str, **kwargs) -> str:
        """Generate a consistent cache key from parameters"""
        key_parts = [prefix]
        for k, v in sorted(kwargs.items()):
            if v is not None:
                key_parts.append(f"{k}:{v}")
        return ":".join(key_parts)
    
    def get_hash_key(self, data: str) -> str:
        """Generate a hash key for large data"""
        return hashlib.md5(data.encode()).hexdigest()
    
    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache (L1 -> L2 -> None)"""
        # L1: Memory cache
        if key in self.memory_cache:
            value, expiry = self.memory_cache[key]
            if expiry > datetime.now().timestamp():
                self.stats["l1_hits"] += 1
                return value
            else:
                del self.memory_cache[key]
        
        # L2: Redis cache
        try:
            value = await self.redis.get(key)
            if value:
                self.stats["l2_hits"] += 1
                parsed_value = json.loads(value)
                # Promote to L1 cache
                self._set_memory_cache(key, parsed_value, 60)  # 1 minute in memory
                return parsed_value
        except Exception as e:
            logger.error(f"Redis get error: {e}")
        
        self.stats["total_misses"] += 1
        return None
    
    async def set(self, key: str, value: Any, ttl: int):
        """Set value in both cache layers"""
        # L1: Memory cache
        self._set_memory_cache(key, value, min(ttl, 300))  # Max 5 min in memory
        
        # L2: Redis cache
        try:
            await self.redis.setex(
                key,
                ttl,
                json.dumps(value, default=str)
            )
        except Exception as e:
            logger.error(f"Redis set error: {e}")
    
    def _set_memory_cache(self, key: str, value: Any, ttl: int):
        """Set value in memory cache with size limit"""
        # Implement LRU eviction if cache is too large
        max_size = self.settings.max_memory_cache_size
        if len(self.memory_cache) >= max_size:
            # Remove oldest entries
            sorted_keys = sorted(
                self.memory_cache.items(),
                key=lambda x: x[1][1]  # Sort by expiry time
            )
            for k, _ in sorted_keys[:len(sorted_keys)//4]:  # Remove 25%
                del self.memory_cache[k]
        
        expiry = datetime.now().timestamp() + ttl
        self.memory_cache[key] = (value, expiry)
    
    async def delete(self, pattern: str):
        """Delete keys matching pattern"""
        try:
            # Clear from memory cache
            keys_to_delete = [k for k in self.memory_cache if k.startswith(pattern)]
            for key in keys_to_delete:
                del self.memory_cache[key]
            
            # Clear from Redis
            async for key in self.redis.scan_iter(match=f"{pattern}*"):
                await self.redis.delete(key)
        except Exception as e:
            logger.error(f"Cache delete error: {e}")
    
    async def clear_expired(self):
        """Clear expired entries from memory cache"""
        current_time = datetime.now().timestamp()
        expired_keys = [
            k for k, (_, expiry) in self.memory_cache.items()
            if expiry <= current_time
        ]
        for key in expired_keys:
            del self.memory_cache[key]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        total_requests = sum(self.stats.values())
        hit_rate = 0.0
        if total_requests > 0:
            hits = self.stats["l1_hits"] + self.stats["l2_hits"]
            hit_rate = (hits / total_requests) * 100
        
        return {
            **self.stats,
            "hit_rate": round(hit_rate, 2),
            "memory_cache_size": len(self.memory_cache),
            "total_requests": total_requests
        }
    
    async def warmup(self, warmup_func, *args, **kwargs):
        """Warmup cache with preloaded data"""
        try:
            await warmup_func(*args, **kwargs)
            logger.info("Cache warmup completed")
        except Exception as e:
            logger.error(f"Cache warmup failed: {e}")

def cache_result(ttl: int):
    """Decorator for caching function results"""
    def decorator(func):
        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            # Generate cache key
            cache_key = self.cache_manager.get_cache_key(
                func.__name__,
                **{f"arg{i}": arg for i, arg in enumerate(args)},
                **kwargs
            )
            
            # Try to get from cache
            cached = await self.cache_manager.get(cache_key)
            if cached is not None:
                return cached
            
            # Call function and cache result
            result = await func(self, *args, **kwargs)
            if result is not None:
                await self.cache_manager.set(cache_key, result, ttl)
            
            return result
        return wrapper
    return decorator

# Background task for cache maintenance
async def cache_maintenance_task(cache_manager: CacheManager, interval: int = 60):
    """Periodic cache maintenance"""
    while True:
        try:
            await asyncio.sleep(interval)
            await cache_manager.clear_expired()
            stats = cache_manager.get_stats()
            logger.info(f"Cache stats: {stats}")
        except Exception as e:
            logger.error(f"Cache maintenance error: {e}")