"""
Microservices Health Monitoring Metrics

Tracks health and performance metrics for all microservices in the system.
Each service reports:
- Health status (Green/Amber/Red)
- Uptime
- Request rate
- Error rate
- Resource usage (CPU, memory)
- Dependencies status
"""
from prometheus_client import Gauge, Counter, Histogram, Info
import time

# ============================================================================
# SERVICE HEALTH STATUS
# ============================================================================

service_health_status = Gauge(
    'service_health_status',
    'Service health status (2=healthy/green, 1=degraded/amber, 0=unhealthy/red)',
    ['service_name', 'instance']
)

service_health_status_change_timestamp = Gauge(
    'service_health_status_change_timestamp',
    'Unix timestamp when service health status last changed',
    ['service_name', 'instance']
)

service_info = Info(
    'service_info',
    'Service information (version, environment, etc.)',
)

# ============================================================================
# SERVICE UPTIME & AVAILABILITY
# ============================================================================

service_start_time = Gauge(
    'service_start_time_seconds',
    'Unix timestamp when service started',
    ['service_name', 'instance']
)

service_uptime_seconds = Gauge(
    'service_uptime_seconds',
    'Service uptime in seconds',
    ['service_name', 'instance']
)

service_restarts_total = Counter(
    'service_restarts_total',
    'Total number of service restarts',
    ['service_name', 'instance']
)

# ============================================================================
# SERVICE PERFORMANCE
# ============================================================================

service_requests_total = Counter(
    'service_requests_total',
    'Total requests handled by service',
    ['service_name', 'instance', 'method', 'endpoint']
)

service_requests_duration_seconds = Histogram(
    'service_requests_duration_seconds',
    'Request duration in seconds',
    ['service_name', 'instance', 'method', 'endpoint'],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

service_errors_total = Counter(
    'service_errors_total',
    'Total errors by service',
    ['service_name', 'instance', 'error_type']
)

service_error_rate = Gauge(
    'service_error_rate',
    'Service error rate (errors/sec)',
    ['service_name', 'instance']
)

# ============================================================================
# RESOURCE USAGE
# ============================================================================

service_cpu_usage_percent = Gauge(
    'service_cpu_usage_percent',
    'CPU usage percentage (0-100)',
    ['service_name', 'instance']
)

service_memory_usage_bytes = Gauge(
    'service_memory_usage_bytes',
    'Memory usage in bytes',
    ['service_name', 'instance']
)

service_memory_usage_percent = Gauge(
    'service_memory_usage_percent',
    'Memory usage percentage (0-100)',
    ['service_name', 'instance']
)

service_disk_usage_bytes = Gauge(
    'service_disk_usage_bytes',
    'Disk usage in bytes',
    ['service_name', 'instance']
)

service_network_received_bytes_total = Counter(
    'service_network_received_bytes_total',
    'Total bytes received over network',
    ['service_name', 'instance']
)

service_network_sent_bytes_total = Counter(
    'service_network_sent_bytes_total',
    'Total bytes sent over network',
    ['service_name', 'instance']
)

# ============================================================================
# DEPENDENCIES HEALTH
# ============================================================================

service_dependency_health = Gauge(
    'service_dependency_health',
    'Dependency health status (1=healthy, 0=unhealthy)',
    ['service_name', 'instance', 'dependency_name', 'dependency_type']
)

service_dependency_latency_seconds = Histogram(
    'service_dependency_latency_seconds',
    'Latency to dependency in seconds',
    ['service_name', 'instance', 'dependency_name', 'dependency_type'],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0]
)

# ============================================================================
# SERVICE-SPECIFIC METRICS
# ============================================================================

service_active_connections = Gauge(
    'service_active_connections',
    'Number of active connections',
    ['service_name', 'instance', 'connection_type']
)

service_queue_depth = Gauge(
    'service_queue_depth',
    'Number of items in queue',
    ['service_name', 'instance', 'queue_name']
)

service_cache_hit_rate = Gauge(
    'service_cache_hit_rate',
    'Cache hit rate (0-100%)',
    ['service_name', 'instance', 'cache_name']
)

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def update_service_health(
    service_name: str,
    instance: str,
    status: int,
    timestamp: float = None
):
    """
    Update service health status

    Args:
        service_name: Name of the service (e.g., 'ticker_service', 'user_service')
        instance: Service instance identifier (e.g., 'main', 'worker-1')
        status: Health status (2=green/healthy, 1=amber/degraded, 0=red/unhealthy)
        timestamp: Unix timestamp of status change (default: now)
    """
    if timestamp is None:
        timestamp = time.time()

    service_health_status.labels(
        service_name=service_name,
        instance=instance
    ).set(status)

    service_health_status_change_timestamp.labels(
        service_name=service_name,
        instance=instance
    ).set(timestamp)


def record_service_start(
    service_name: str,
    instance: str,
    version: str = None,
    environment: str = None
):
    """
    Record service startup

    Args:
        service_name: Name of the service
        instance: Service instance identifier
        version: Service version
        environment: Environment (dev, staging, prod)
    """
    start_time = time.time()

    service_start_time.labels(
        service_name=service_name,
        instance=instance
    ).set(start_time)

    service_restarts_total.labels(
        service_name=service_name,
        instance=instance
    ).inc()

    # Set initial health to healthy
    update_service_health(service_name, instance, 2, start_time)

    # Update service info
    if version or environment:
        info_dict = {'service_name': service_name, 'instance': instance}
        if version:
            info_dict['version'] = version
        if environment:
            info_dict['environment'] = environment
        service_info.info(info_dict)


def update_service_uptime(service_name: str, instance: str):
    """
    Update service uptime (call periodically)

    Args:
        service_name: Name of the service
        instance: Service instance identifier
    """
    # Get start time
    start_time_metric = service_start_time.labels(
        service_name=service_name,
        instance=instance
    )

    try:
        start_time = start_time_metric._value.get()
        if start_time:
            uptime = time.time() - start_time
            service_uptime_seconds.labels(
                service_name=service_name,
                instance=instance
            ).set(uptime)
    except:
        pass


def update_dependency_health(
    service_name: str,
    instance: str,
    dependency_name: str,
    dependency_type: str,
    is_healthy: bool,
    latency: float = None
):
    """
    Update dependency health status

    Args:
        service_name: Name of the service
        instance: Service instance identifier
        dependency_name: Name of the dependency (e.g., 'postgres', 'redis')
        dependency_type: Type of dependency (e.g., 'database', 'cache', 'api')
        is_healthy: Whether dependency is healthy
        latency: Latency to dependency in seconds (optional)
    """
    service_dependency_health.labels(
        service_name=service_name,
        instance=instance,
        dependency_name=dependency_name,
        dependency_type=dependency_type
    ).set(1 if is_healthy else 0)

    if latency is not None:
        service_dependency_latency_seconds.labels(
            service_name=service_name,
            instance=instance,
            dependency_name=dependency_name,
            dependency_type=dependency_type
        ).observe(latency)


def calculate_service_health_status(
    dependencies_healthy: dict,
    error_rate: float = 0.0,
    cpu_usage: float = 0.0,
    memory_usage: float = 0.0
) -> int:
    """
    Calculate overall service health status based on various factors

    Args:
        dependencies_healthy: Dict of {dependency_name: is_healthy}
        error_rate: Current error rate (errors/sec)
        cpu_usage: CPU usage percentage
        memory_usage: Memory usage percentage

    Returns:
        int: 2 (green), 1 (amber), or 0 (red)
    """
    # Red (0) conditions - critical failures
    if dependencies_healthy:
        critical_deps = ['database', 'postgres', 'redis']
        for dep_name, is_healthy in dependencies_healthy.items():
            if any(critical in dep_name.lower() for critical in critical_deps):
                if not is_healthy:
                    return 0  # Red - critical dependency down

    if error_rate > 10:  # >10 errors/sec
        return 0  # Red - high error rate

    if cpu_usage > 95 or memory_usage > 95:
        return 0  # Red - resource exhaustion

    # Amber (1) conditions - degraded performance
    if dependencies_healthy:
        for is_healthy in dependencies_healthy.values():
            if not is_healthy:
                return 1  # Amber - non-critical dependency down

    if error_rate > 1:  # >1 error/sec
        return 1  # Amber - elevated error rate

    if cpu_usage > 80 or memory_usage > 80:
        return 1  # Amber - high resource usage

    # Green (2) - healthy
    return 2


# ============================================================================
# TICKER SERVICE SPECIFIC INITIALIZATION
# ============================================================================

def initialize_ticker_service_health(
    instance: str = "main",
    version: str = "2.0.0",
    environment: str = "production"
):
    """
    Initialize health metrics for ticker service

    Args:
        instance: Instance identifier
        version: Service version
        environment: Deployment environment
    """
    record_service_start(
        service_name="ticker_service",
        instance=instance,
        version=version,
        environment=environment
    )
