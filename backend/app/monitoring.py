from prometheus_client import Counter, Histogram, Gauge, generate_latest
import time
from functools import wraps
import logging
import asyncio

logger = logging.getLogger(__name__)

# Metrics
request_count = Counter(
    'tradingview_requests_total',
    'Total number of requests',
    ['method', 'endpoint', 'status']
)

request_duration = Histogram(
    'tradingview_request_duration_seconds',
    'Request duration in seconds',
    ['method', 'endpoint']
)

cache_hits = Counter(
    'tradingview_cache_hits_total',
    'Total cache hits',
    ['cache_type']
)

cache_misses = Counter(
    'tradingview_cache_misses_total',
    'Total cache misses',
    ['cache_type']
)

db_pool_size = Gauge(
    'tradingview_db_pool_connections',
    'Database pool connections',
    ['status']
)

active_connections = Gauge(
    'tradingview_active_connections',
    'Active connections'
)

memory_usage = Gauge(
    'tradingview_memory_usage_bytes',
    'Memory usage in bytes'
)

# Track metrics
def track_request_metrics(method: str, endpoint: str, status: int, duration: float):
    """Track request metrics"""
    request_count.labels(method=method, endpoint=endpoint, status=status).inc()
    request_duration.labels(method=method, endpoint=endpoint).observe(duration)

def track_cache_hit(cache_type: str):
    """Track cache hit"""
    cache_hits.labels(cache_type=cache_type).inc()

def track_cache_miss(cache_type: str):
    """Track cache miss"""
    cache_misses.labels(cache_type=cache_type).inc()

def update_db_pool_metrics(pool_stats: dict):
    """Update database pool metrics"""
    db_pool_size.labels(status='total').set(pool_stats.get('size', 0))
    db_pool_size.labels(status='idle').set(pool_stats.get('idle', 0))
    db_pool_size.labels(status='active').set(
        pool_stats.get('size', 0) - pool_stats.get('idle', 0)
    )

# Decorator for timing functions
def timed_operation(operation_name: str):
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                duration = time.time() - start_time
                logger.debug(f"{operation_name} completed in {duration:.3f}s")
                return result
            except Exception as e:
                duration = time.time() - start_time
                logger.error(f"{operation_name} failed after {duration:.3f}s: {e}")
                raise
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time
                logger.debug(f"{operation_name} completed in {duration:.3f}s")
                return result
            except Exception as e:
                duration = time.time() - start_time
                logger.error(f"{operation_name} failed after {duration:.3f}s: {e}")
                raise
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    return decorator

# Health check metrics
class HealthMonitor:
    def __init__(self):
        self.start_time = time.time()
        self.last_db_check = 0
        self.last_redis_check = 0
        self.db_healthy = True
        self.redis_healthy = True
    
    def get_uptime(self) -> float:
        """Get uptime in seconds"""
        return time.time() - self.start_time
    
    def update_db_health(self, is_healthy: bool):
        """Update database health status"""
        self.db_healthy = is_healthy
        self.last_db_check = time.time()
    
    def update_redis_health(self, is_healthy: bool):
        """Update Redis health status"""
        self.redis_healthy = is_healthy
        self.last_redis_check = time.time()
    
    def get_health_status(self) -> dict:
        """Get overall health status"""
        return {
            "status": "healthy" if self.db_healthy and self.redis_healthy else "unhealthy",
            "database": "healthy" if self.db_healthy else "unhealthy",
            "redis": "healthy" if self.redis_healthy else "unhealthy",
            "uptime": self.get_uptime(),
            "last_db_check": time.time() - self.last_db_check,
            "last_redis_check": time.time() - self.last_redis_check
        }

# Global health monitor instance
health_monitor = HealthMonitor()

# Memory monitoring
import psutil
import os

def update_memory_metrics():
    """Update memory usage metrics"""
    process = psutil.Process(os.getpid())
    memory_info = process.memory_info()
    memory_usage.set(memory_info.rss)  # Resident Set Size

# Background task for metrics update
async def metrics_update_task(interval: int = 30):
    """Periodic metrics update"""
    while True:
        try:
            update_memory_metrics()
            await asyncio.sleep(interval)
        except Exception as e:
            logger.error(f"Metrics update error: {e}")
            await asyncio.sleep(interval)