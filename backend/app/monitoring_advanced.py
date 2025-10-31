"""
Advanced monitoring for backpressure, memory leaks, and architectural issues.

This module provides comprehensive monitoring capabilities:
1. Backpressure detection (DB pool, Redis, async task queues)
2. Memory leak detection (RSS growth, GC stats, object tracking)
3. Architectural health (circuit breakers, dependency health)
4. Performance anomaly detection
"""

import asyncio
import gc
import logging
import os
import sys
import time
import tracemalloc
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import psutil
from prometheus_client import Counter, Gauge, Histogram, Info

logger = logging.getLogger(__name__)

# ============================================================================
# PROMETHEUS METRICS
# ============================================================================

# Backpressure Metrics
backpressure_db_queue_size = Gauge(
    'backpressure_db_queue_size',
    'Number of waiting database connection requests'
)

backpressure_redis_queue_size = Gauge(
    'backpressure_redis_queue_size',
    'Number of waiting Redis connection requests'
)

backpressure_async_tasks = Gauge(
    'backpressure_async_tasks_pending',
    'Number of pending async tasks',
    ['task_type']
)

backpressure_event_loop_lag = Gauge(
    'backpressure_event_loop_lag_seconds',
    'Event loop lag in seconds'
)

# Memory Leak Metrics
memory_rss_bytes = Gauge(
    'memory_rss_bytes',
    'Resident Set Size memory in bytes'
)

memory_vms_bytes = Gauge(
    'memory_vms_bytes',
    'Virtual Memory Size in bytes'
)

memory_objects_count = Gauge(
    'memory_objects_count',
    'Number of Python objects in memory',
    ['type']
)

memory_gc_collections = Counter(
    'memory_gc_collections_total',
    'Total garbage collection cycles',
    ['generation']
)

memory_gc_collected = Counter(
    'memory_gc_collected_total',
    'Total objects collected by GC',
    ['generation']
)

memory_growth_rate = Gauge(
    'memory_growth_rate_bytes_per_second',
    'Memory growth rate in bytes per second'
)

# Architectural Health Metrics
circuit_breaker_state = Gauge(
    'circuit_breaker_state',
    'Circuit breaker state (0=closed, 1=open, 2=half_open)',
    ['service']
)

dependency_health = Gauge(
    'dependency_health_status',
    'Dependency health status (0=down, 1=degraded, 2=healthy)',
    ['dependency']
)

slow_query_count = Counter(
    'slow_query_count_total',
    'Number of slow queries detected',
    ['query_type']
)

query_timeout_count = Counter(
    'query_timeout_count_total',
    'Number of query timeouts',
    ['query_type']
)

websocket_connections = Gauge(
    'websocket_connections_active',
    'Number of active WebSocket connections',
    ['endpoint']
)

# Performance Anomaly Metrics
response_time_p95 = Histogram(
    'response_time_p95_seconds',
    'Response time 95th percentile',
    ['endpoint'],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

error_rate = Counter(
    'error_rate_total',
    'Total error count',
    ['error_type', 'endpoint']
)

# System Info
system_info = Info('tradingview_system', 'System information')


# ============================================================================
# BACKPRESSURE DETECTOR
# ============================================================================

@dataclass
class BackpressureMetrics:
    """Tracks backpressure indicators."""
    db_pool_waiting: int = 0
    db_pool_size: int = 0
    redis_connections_waiting: int = 0
    async_tasks_pending: Dict[str, int] = field(default_factory=dict)
    event_loop_lag_ms: float = 0.0
    timestamp: float = field(default_factory=time.time)

    @property
    def has_backpressure(self) -> bool:
        """Check if system is experiencing backpressure."""
        return (
            self.db_pool_waiting > self.db_pool_size * 0.5 or  # DB pool > 50% waiting
            self.redis_connections_waiting > 10 or
            self.event_loop_lag_ms > 100 or  # > 100ms lag
            any(count > 100 for count in self.async_tasks_pending.values())
        )

    def get_severity(self) -> str:
        """Get backpressure severity level."""
        if not self.has_backpressure:
            return "normal"
        if self.event_loop_lag_ms > 500 or self.db_pool_waiting > self.db_pool_size:
            return "critical"
        if self.event_loop_lag_ms > 200 or self.db_pool_waiting > self.db_pool_size * 0.7:
            return "high"
        return "medium"


class BackpressureDetector:
    """Detects and monitors backpressure across the system."""

    def __init__(self, check_interval: int = 5):
        self.check_interval = check_interval
        self.metrics_history: deque = deque(maxlen=60)  # Keep 5 minutes of history
        self.alerts_sent: Dict[str, float] = {}  # Track alert cooldowns
        self.alert_cooldown = 300  # 5 minutes between same alerts

    async def measure_event_loop_lag(self) -> float:
        """Measure event loop lag in milliseconds."""
        start = time.perf_counter()
        await asyncio.sleep(0)
        actual = (time.perf_counter() - start) * 1000
        expected = 0
        return max(0, actual - expected)

    async def collect_metrics(self, db_pool=None, redis_client=None) -> BackpressureMetrics:
        """Collect current backpressure metrics."""
        metrics = BackpressureMetrics()

        # DB pool metrics
        if db_pool:
            try:
                metrics.db_pool_size = db_pool.get_size()
                metrics.db_pool_waiting = db_pool.get_size() - db_pool.get_idle_size()
                backpressure_db_queue_size.set(metrics.db_pool_waiting)
            except Exception as e:
                logger.warning(f"Failed to collect DB pool metrics: {e}")

        # Redis metrics
        if redis_client:
            try:
                # Note: Redis connection pooling varies by implementation
                # Adjust based on your redis client
                pass
            except Exception as e:
                logger.warning(f"Failed to collect Redis metrics: {e}")

        # Event loop lag
        metrics.event_loop_lag_ms = await self.measure_event_loop_lag()
        backpressure_event_loop_lag.set(metrics.event_loop_lag_ms / 1000)

        # Async tasks
        all_tasks = asyncio.all_tasks()
        metrics.async_tasks_pending["total"] = len(all_tasks)
        backpressure_async_tasks.labels(task_type="total").set(len(all_tasks))

        return metrics

    async def check_and_alert(self, metrics: BackpressureMetrics):
        """Check for backpressure and send alerts if needed."""
        if not metrics.has_backpressure:
            return

        severity = metrics.get_severity()
        alert_key = f"backpressure_{severity}"

        # Check cooldown
        last_alert = self.alerts_sent.get(alert_key, 0)
        if time.time() - last_alert < self.alert_cooldown:
            return

        # Log alert
        logger.warning(
            f"BACKPRESSURE DETECTED - Severity: {severity}",
            extra={
                "db_pool_waiting": metrics.db_pool_waiting,
                "db_pool_size": metrics.db_pool_size,
                "event_loop_lag_ms": metrics.event_loop_lag_ms,
                "async_tasks": metrics.async_tasks_pending
            }
        )

        self.alerts_sent[alert_key] = time.time()

    async def monitor_loop(self, db_pool=None, redis_client=None):
        """Main monitoring loop."""
        logger.info("Starting backpressure monitoring")
        while True:
            try:
                metrics = await self.collect_metrics(db_pool, redis_client)
                self.metrics_history.append(metrics)
                await self.check_and_alert(metrics)
                await asyncio.sleep(self.check_interval)
            except Exception as e:
                logger.error(f"Backpressure monitoring error: {e}")
                await asyncio.sleep(self.check_interval)


# ============================================================================
# MEMORY LEAK DETECTOR
# ============================================================================

@dataclass
class MemorySnapshot:
    """Snapshot of memory usage at a point in time."""
    timestamp: float
    rss_bytes: int
    vms_bytes: int
    available_mb: float
    percent: float
    gc_stats: Dict[int, Dict] = field(default_factory=dict)
    top_objects: List[Tuple[str, int]] = field(default_factory=list)


class MemoryLeakDetector:
    """Detects memory leaks and excessive memory growth."""

    def __init__(self, snapshot_interval: int = 60, enable_tracemalloc: bool = False):
        self.snapshot_interval = snapshot_interval
        self.snapshots: deque = deque(maxlen=60)  # Keep 1 hour of snapshots
        self.baseline_rss: Optional[int] = None
        self.enable_tracemalloc = enable_tracemalloc
        self.process = psutil.Process(os.getpid())

        if self.enable_tracemalloc:
            tracemalloc.start()
            logger.info("tracemalloc enabled for detailed memory tracking")

    def take_snapshot(self) -> MemorySnapshot:
        """Take a memory snapshot."""
        memory_info = self.process.memory_info()
        vm = psutil.virtual_memory()

        # GC statistics
        gc_stats = {}
        for gen in range(3):
            stats = gc.get_count()[gen]
            gc_stats[gen] = {
                "collections": gc.get_stats()[gen].get("collections", 0),
                "collected": gc.get_stats()[gen].get("collected", 0),
                "uncollectable": gc.get_stats()[gen].get("uncollectable", 0),
            }
            # Update Prometheus metrics
            memory_gc_collections.labels(generation=str(gen)).inc(
                gc_stats[gen]["collections"]
            )

        # Top objects by count
        top_objects = []
        if self.enable_tracemalloc:
            snapshot = tracemalloc.take_snapshot()
            top_stats = snapshot.statistics('lineno')[:10]
            top_objects = [(str(stat), stat.size) for stat in top_stats]

        # Update Prometheus metrics
        memory_rss_bytes.set(memory_info.rss)
        memory_vms_bytes.set(memory_info.vms)

        return MemorySnapshot(
            timestamp=time.time(),
            rss_bytes=memory_info.rss,
            vms_bytes=memory_info.vms,
            available_mb=vm.available / 1024 / 1024,
            percent=vm.percent,
            gc_stats=gc_stats,
            top_objects=top_objects
        )

    def calculate_growth_rate(self) -> float:
        """Calculate memory growth rate in bytes per second."""
        if len(self.snapshots) < 2:
            return 0.0

        oldest = self.snapshots[0]
        newest = self.snapshots[-1]

        time_delta = newest.timestamp - oldest.timestamp
        if time_delta == 0:
            return 0.0

        rss_delta = newest.rss_bytes - oldest.rss_bytes
        return rss_delta / time_delta

    def detect_leak(self) -> Optional[Dict]:
        """Detect potential memory leak."""
        if len(self.snapshots) < 10:
            return None

        growth_rate = self.calculate_growth_rate()
        memory_growth_rate.set(growth_rate)

        # Leak thresholds
        LEAK_THRESHOLD_BYTES_PER_SEC = 1024 * 1024  # 1 MB/sec sustained growth
        LEAK_THRESHOLD_PERCENT = 80  # 80% memory usage

        newest = self.snapshots[-1]

        is_growing = growth_rate > LEAK_THRESHOLD_BYTES_PER_SEC
        is_high_usage = newest.percent > LEAK_THRESHOLD_PERCENT

        if is_growing or is_high_usage:
            return {
                "growth_rate_mb_per_sec": growth_rate / 1024 / 1024,
                "current_rss_mb": newest.rss_bytes / 1024 / 1024,
                "memory_percent": newest.percent,
                "severity": "critical" if is_high_usage else "warning"
            }

        return None

    async def monitor_loop(self):
        """Main monitoring loop."""
        logger.info("Starting memory leak monitoring")
        while True:
            try:
                snapshot = self.take_snapshot()
                self.snapshots.append(snapshot)

                if self.baseline_rss is None:
                    self.baseline_rss = snapshot.rss_bytes

                leak_info = self.detect_leak()
                if leak_info:
                    logger.warning(
                        f"MEMORY LEAK DETECTED - {leak_info['severity'].upper()}",
                        extra=leak_info
                    )

                await asyncio.sleep(self.snapshot_interval)
            except Exception as e:
                logger.error(f"Memory leak monitoring error: {e}")
                await asyncio.sleep(self.snapshot_interval)


# ============================================================================
# ARCHITECTURAL HEALTH MONITOR
# ============================================================================

class CircuitBreaker:
    """Circuit breaker pattern implementation."""

    def __init__(self, failure_threshold: int = 5, timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.failure_count = 0
        self.last_failure_time = 0
        self.state = "closed"  # closed, open, half_open

    def call(self, func):
        """Execute function with circuit breaker protection."""
        if self.state == "open":
            if time.time() - self.last_failure_time > self.timeout:
                self.state = "half_open"
            else:
                raise Exception("Circuit breaker is OPEN")

        try:
            result = func()
            if self.state == "half_open":
                self.state = "closed"
                self.failure_count = 0
            return result
        except Exception as e:
            self.failure_count += 1
            self.last_failure_time = time.time()
            if self.failure_count >= self.failure_threshold:
                self.state = "open"
            raise e


class ArchitecturalHealthMonitor:
    """Monitor architectural health and dependencies."""

    def __init__(self, check_interval: int = 30):
        self.check_interval = check_interval
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
        self.dependency_status: Dict[str, str] = {}
        self.slow_queries: deque = deque(maxlen=100)

    def register_circuit_breaker(self, service: str, **kwargs):
        """Register a circuit breaker for a service."""
        self.circuit_breakers[service] = CircuitBreaker(**kwargs)

    async def check_dependency(self, name: str, check_func) -> bool:
        """Check if a dependency is healthy."""
        try:
            result = await check_func()
            self.dependency_status[name] = "healthy"
            dependency_health.labels(dependency=name).set(2)
            return True
        except Exception as e:
            logger.warning(f"Dependency check failed for {name}: {e}")
            self.dependency_status[name] = "unhealthy"
            dependency_health.labels(dependency=name).set(0)
            return False

    def record_slow_query(self, query_type: str, duration: float, query: str = ""):
        """Record a slow query."""
        SLOW_QUERY_THRESHOLD = 1.0  # 1 second
        if duration > SLOW_QUERY_THRESHOLD:
            self.slow_queries.append({
                "query_type": query_type,
                "duration": duration,
                "query": query[:200],  # Truncate
                "timestamp": time.time()
            })
            slow_query_count.labels(query_type=query_type).inc()
            logger.warning(
                f"Slow query detected: {query_type}",
                extra={"duration": duration, "query": query[:100]}
            )

    async def monitor_loop(self):
        """Main monitoring loop."""
        logger.info("Starting architectural health monitoring")
        while True:
            try:
                # Update circuit breaker states
                for service, cb in self.circuit_breakers.items():
                    state_value = {"closed": 0, "open": 1, "half_open": 2}[cb.state]
                    circuit_breaker_state.labels(service=service).set(state_value)

                await asyncio.sleep(self.check_interval)
            except Exception as e:
                logger.error(f"Architectural health monitoring error: {e}")
                await asyncio.sleep(self.check_interval)


# ============================================================================
# MAIN MONITORING ORCHESTRATOR
# ============================================================================

class MonitoringOrchestrator:
    """Orchestrates all monitoring components."""

    def __init__(self):
        self.backpressure_detector = BackpressureDetector()
        self.memory_leak_detector = MemoryLeakDetector()
        self.arch_health_monitor = ArchitecturalHealthMonitor()
        self.monitoring_tasks: List[asyncio.Task] = []

    async def start(self, db_pool=None, redis_client=None):
        """Start all monitoring tasks."""
        logger.info("Starting comprehensive monitoring system")

        # Set system info
        system_info.info({
            'python_version': sys.version,
            'platform': sys.platform,
            'hostname': os.uname().nodename,
            'pid': str(os.getpid())
        })

        # Start monitoring tasks
        self.monitoring_tasks = [
            asyncio.create_task(self.backpressure_detector.monitor_loop(db_pool, redis_client)),
            asyncio.create_task(self.memory_leak_detector.monitor_loop()),
            asyncio.create_task(self.arch_health_monitor.monitor_loop()),
        ]

        logger.info("All monitoring tasks started")

    async def stop(self):
        """Stop all monitoring tasks."""
        logger.info("Stopping monitoring system")
        for task in self.monitoring_tasks:
            task.cancel()
        await asyncio.gather(*self.monitoring_tasks, return_exceptions=True)

    def get_health_summary(self) -> Dict:
        """Get overall health summary."""
        backpressure_metrics = (
            self.backpressure_detector.metrics_history[-1]
            if self.backpressure_detector.metrics_history
            else None
        )

        memory_snapshot = (
            self.memory_leak_detector.snapshots[-1]
            if self.memory_leak_detector.snapshots
            else None
        )

        return {
            "backpressure": {
                "has_backpressure": backpressure_metrics.has_backpressure if backpressure_metrics else False,
                "severity": backpressure_metrics.get_severity() if backpressure_metrics else "unknown",
                "event_loop_lag_ms": backpressure_metrics.event_loop_lag_ms if backpressure_metrics else 0,
            },
            "memory": {
                "rss_mb": memory_snapshot.rss_bytes / 1024 / 1024 if memory_snapshot else 0,
                "percent": memory_snapshot.percent if memory_snapshot else 0,
                "growth_rate_mb_per_sec": self.memory_leak_detector.calculate_growth_rate() / 1024 / 1024,
            },
            "dependencies": self.arch_health_monitor.dependency_status,
            "circuit_breakers": {
                service: cb.state
                for service, cb in self.arch_health_monitor.circuit_breakers.items()
            }
        }


# Global monitoring orchestrator instance
monitoring_orchestrator = MonitoringOrchestrator()
