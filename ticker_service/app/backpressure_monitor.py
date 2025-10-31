"""
Backpressure Detection and Monitoring

Tracks system health metrics and detects backpressure buildup.
"""
from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Deque, Dict, Optional

from loguru import logger
from prometheus_client import Counter, Gauge, Histogram


class BackpressureLevel(Enum):
    """Backpressure severity levels"""
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    OVERLOAD = "overload"


@dataclass
class BackpressureMetrics:
    """Real-time backpressure metrics"""

    # Ingestion metrics
    ticks_received_per_sec: float = 0.0
    ticks_published_per_sec: float = 0.0

    # Processing lag metrics
    avg_publish_latency_ms: float = 0.0
    p95_publish_latency_ms: float = 0.0
    p99_publish_latency_ms: float = 0.0

    # Queue metrics
    pending_publishes: int = 0
    dropped_messages: int = 0

    # Redis metrics
    redis_publish_errors: int = 0
    redis_connection_errors: int = 0

    # System metrics
    memory_usage_mb: float = 0.0
    cpu_usage_percent: float = 0.0

    # Computed health metrics
    backpressure_level: BackpressureLevel = BackpressureLevel.HEALTHY
    ingestion_rate_ratio: float = 1.0  # published / received

    # Timestamp
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class BackpressureMonitor:
    """
    Monitor system health and detect backpressure buildup.

    Tracks:
    - Ingestion vs publish rates
    - Publish latencies
    - Queue depths
    - Error rates
    - System resources
    """

    def __init__(
        self,
        window_seconds: int = 60,
        warning_threshold: float = 0.8,
        critical_threshold: float = 0.95,
        overload_threshold: float = 0.99
    ):
        self.window_seconds = window_seconds
        self.warning_threshold = warning_threshold
        self.critical_threshold = critical_threshold
        self.overload_threshold = overload_threshold

        # Sliding windows for rate calculation
        self._tick_ingestion_times: Deque[float] = deque(maxlen=10000)
        self._tick_publish_times: Deque[float] = deque(maxlen=10000)
        self._publish_latencies: Deque[float] = deque(maxlen=1000)

        # Counters
        self._ticks_received = 0
        self._ticks_published = 0
        self._ticks_dropped = 0
        self._redis_errors = 0

        # Current state
        self._current_level = BackpressureLevel.HEALTHY
        self._pending_publishes = 0

        # Prometheus metrics
        self._setup_prometheus_metrics()

    def _setup_prometheus_metrics(self):
        """Initialize Prometheus metrics"""
        self.prom_ticks_received = Counter(
            'ticker_ticks_received_total',
            'Total number of ticks received from upstream'
        )
        self.prom_ticks_published = Counter(
            'ticker_ticks_published_total',
            'Total number of ticks published to Redis'
        )
        self.prom_ticks_dropped = Counter(
            'ticker_ticks_dropped_total',
            'Total number of ticks dropped due to backpressure'
        )
        self.prom_publish_latency = Histogram(
            'ticker_publish_latency_seconds',
            'Time taken to publish message to Redis',
            buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0]
        )
        self.prom_pending_publishes = Gauge(
            'ticker_pending_publishes',
            'Number of messages waiting to be published'
        )
        self.prom_backpressure_level = Gauge(
            'ticker_backpressure_level',
            'Current backpressure level (0=healthy, 1=warning, 2=critical, 3=overload)'
        )
        self.prom_ingestion_rate = Gauge(
            'ticker_ingestion_rate_per_sec',
            'Number of ticks received per second'
        )
        self.prom_publish_rate = Gauge(
            'ticker_publish_rate_per_sec',
            'Number of ticks published per second'
        )

    def record_tick_received(self):
        """Record a tick received from upstream"""
        now = time.time()
        self._tick_ingestion_times.append(now)
        self._ticks_received += 1
        self.prom_ticks_received.inc()

    def record_tick_published(self, latency_seconds: float):
        """Record a tick published to Redis"""
        now = time.time()
        self._tick_publish_times.append(now)
        self._publish_latencies.append(latency_seconds * 1000)  # Convert to ms
        self._ticks_published += 1

        self.prom_ticks_published.inc()
        self.prom_publish_latency.observe(latency_seconds)

    def record_tick_dropped(self):
        """Record a tick dropped due to backpressure"""
        self._ticks_dropped += 1
        self.prom_ticks_dropped.inc()

    def record_redis_error(self):
        """Record a Redis publish error"""
        self._redis_errors += 1

    def update_pending_count(self, count: int):
        """Update the count of pending publishes"""
        self._pending_publishes = count
        self.prom_pending_publishes.set(count)

    def get_metrics(self) -> BackpressureMetrics:
        """Get current backpressure metrics"""
        now = time.time()
        window_start = now - self.window_seconds

        # Calculate ingestion rate
        recent_ingestions = [t for t in self._tick_ingestion_times if t >= window_start]
        ingestion_rate = len(recent_ingestions) / self.window_seconds if recent_ingestions else 0.0

        # Calculate publish rate
        recent_publishes = [t for t in self._tick_publish_times if t >= window_start]
        publish_rate = len(recent_publishes) / self.window_seconds if recent_publishes else 0.0

        # Calculate publish latencies
        recent_latencies = list(self._publish_latencies)
        avg_latency = sum(recent_latencies) / len(recent_latencies) if recent_latencies else 0.0

        p95_latency = 0.0
        p99_latency = 0.0
        if recent_latencies:
            sorted_latencies = sorted(recent_latencies)
            p95_idx = int(len(sorted_latencies) * 0.95)
            p99_idx = int(len(sorted_latencies) * 0.99)
            p95_latency = sorted_latencies[min(p95_idx, len(sorted_latencies) - 1)]
            p99_latency = sorted_latencies[min(p99_idx, len(sorted_latencies) - 1)]

        # Calculate ingestion rate ratio
        rate_ratio = publish_rate / ingestion_rate if ingestion_rate > 0 else 1.0

        # Determine backpressure level
        level = self._compute_backpressure_level(rate_ratio, avg_latency, self._pending_publishes)

        # Update Prometheus gauges
        self.prom_ingestion_rate.set(ingestion_rate)
        self.prom_publish_rate.set(publish_rate)
        self.prom_backpressure_level.set(self._level_to_numeric(level))

        # Get system metrics
        memory_mb, cpu_percent = self._get_system_metrics()

        metrics = BackpressureMetrics(
            ticks_received_per_sec=ingestion_rate,
            ticks_published_per_sec=publish_rate,
            avg_publish_latency_ms=avg_latency,
            p95_publish_latency_ms=p95_latency,
            p99_publish_latency_ms=p99_latency,
            pending_publishes=self._pending_publishes,
            dropped_messages=self._ticks_dropped,
            redis_publish_errors=self._redis_errors,
            memory_usage_mb=memory_mb,
            cpu_usage_percent=cpu_percent,
            backpressure_level=level,
            ingestion_rate_ratio=rate_ratio
        )

        # Log if level changed
        if level != self._current_level:
            logger.warning(
                f"Backpressure level changed: {self._current_level.value} -> {level.value} "
                f"(rate_ratio={rate_ratio:.2f}, latency={avg_latency:.2f}ms, pending={self._pending_publishes})"
            )
            self._current_level = level

        return metrics

    def _compute_backpressure_level(
        self,
        rate_ratio: float,
        avg_latency_ms: float,
        pending_count: int
    ) -> BackpressureLevel:
        """
        Compute backpressure level based on metrics.

        Healthy: rate_ratio >= 0.95, latency < 10ms, pending < 100
        Warning: rate_ratio >= 0.80, latency < 50ms, pending < 500
        Critical: rate_ratio >= 0.50, latency < 200ms, pending < 2000
        Overload: anything worse
        """
        # Check for overload conditions
        if rate_ratio < 0.5 or avg_latency_ms > 200 or pending_count > 2000:
            return BackpressureLevel.OVERLOAD

        # Check for critical conditions
        if rate_ratio < 0.8 or avg_latency_ms > 50 or pending_count > 500:
            return BackpressureLevel.CRITICAL

        # Check for warning conditions
        if rate_ratio < 0.95 or avg_latency_ms > 10 or pending_count > 100:
            return BackpressureLevel.WARNING

        return BackpressureLevel.HEALTHY

    def _level_to_numeric(self, level: BackpressureLevel) -> int:
        """Convert level to numeric for Prometheus"""
        mapping = {
            BackpressureLevel.HEALTHY: 0,
            BackpressureLevel.WARNING: 1,
            BackpressureLevel.CRITICAL: 2,
            BackpressureLevel.OVERLOAD: 3
        }
        return mapping[level]

    def _get_system_metrics(self) -> tuple[float, float]:
        """Get system resource usage"""
        try:
            import psutil
            process = psutil.Process()
            memory_mb = process.memory_info().rss / 1024 / 1024
            cpu_percent = process.cpu_percent(interval=0.1)
            return memory_mb, cpu_percent
        except ImportError:
            return 0.0, 0.0

    def should_drop_message(self) -> bool:
        """
        Determine if incoming message should be dropped.

        Returns True if system is overloaded and message should be dropped.
        """
        metrics = self.get_metrics()

        # Drop messages in overload state
        if metrics.backpressure_level == BackpressureLevel.OVERLOAD:
            return True

        # Drop messages in critical state if pending queue is large
        if metrics.backpressure_level == BackpressureLevel.CRITICAL and metrics.pending_publishes > 1000:
            return True

        return False

    def should_apply_sampling(self) -> Optional[float]:
        """
        Determine if adaptive sampling should be applied.

        Returns sampling rate (0.0 to 1.0) or None if no sampling needed.
        """
        metrics = self.get_metrics()

        # Apply aggressive sampling in overload
        if metrics.backpressure_level == BackpressureLevel.OVERLOAD:
            return 0.2  # Keep only 20% of messages

        # Apply moderate sampling in critical
        if metrics.backpressure_level == BackpressureLevel.CRITICAL:
            return 0.5  # Keep 50% of messages

        # Apply light sampling in warning
        if metrics.backpressure_level == BackpressureLevel.WARNING:
            return 0.8  # Keep 80% of messages

        return None  # No sampling needed

    def get_status_summary(self) -> Dict:
        """Get human-readable status summary"""
        metrics = self.get_metrics()

        return {
            "backpressure_level": metrics.backpressure_level.value,
            "health_status": "healthy" if metrics.backpressure_level == BackpressureLevel.HEALTHY else "degraded",
            "ingestion_rate": f"{metrics.ticks_received_per_sec:.1f} ticks/sec",
            "publish_rate": f"{metrics.ticks_published_per_sec:.1f} ticks/sec",
            "rate_ratio": f"{metrics.ingestion_rate_ratio:.2%}",
            "avg_latency": f"{metrics.avg_publish_latency_ms:.2f} ms",
            "p99_latency": f"{metrics.p99_publish_latency_ms:.2f} ms",
            "pending_publishes": metrics.pending_publishes,
            "dropped_messages": metrics.dropped_messages,
            "redis_errors": metrics.redis_publish_errors,
            "memory_usage": f"{metrics.memory_usage_mb:.1f} MB",
            "cpu_usage": f"{metrics.cpu_usage_percent:.1f}%",
            "timestamp": metrics.timestamp.isoformat()
        }


# Global monitor instance
_backpressure_monitor: Optional[BackpressureMonitor] = None


def get_backpressure_monitor() -> BackpressureMonitor:
    """Get global backpressure monitor instance"""
    global _backpressure_monitor
    if _backpressure_monitor is None:
        _backpressure_monitor = BackpressureMonitor()
    return _backpressure_monitor
