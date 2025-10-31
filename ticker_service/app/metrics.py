"""
Prometheus metrics for ticker service

Provides metrics for monitoring:
- HTTP requests (count, latency)
- Order execution (count, duration, status)
- Circuit breaker state
- Task queue depth
- WebSocket connections
"""
from prometheus_client import Counter, Gauge, Histogram, Info

# Application info
app_info = Info('ticker_service', 'Ticker service application info')
app_info.info({'version': '2.0.0', 'component': 'ticker_service'})

# HTTP metrics
http_requests_total = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status']
)

http_request_duration_seconds = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration in seconds',
    ['method', 'endpoint']
)

# Order execution metrics
order_requests_total = Counter(
    'order_requests_total',
    'Total order requests submitted',
    ['operation', 'account_id']
)

order_requests_completed = Counter(
    'order_requests_completed',
    'Total order requests completed',
    ['operation', 'status', 'account_id']
)

order_execution_duration_seconds = Histogram(
    'order_execution_duration_seconds',
    'Order execution duration in seconds',
    ['operation']
)

# Circuit breaker metrics
circuit_breaker_state = Gauge(
    'circuit_breaker_state',
    'Circuit breaker state (0=closed, 1=open, 2=half_open)',
    ['account_id']
)

circuit_breaker_failures_total = Counter(
    'circuit_breaker_failures_total',
    'Total circuit breaker failures',
    ['account_id']
)

# Task queue metrics
task_queue_depth = Gauge(
    'task_queue_depth',
    'Number of tasks in queue',
    ['status']
)

task_queue_depth_total = Gauge(
    'task_queue_depth_total',
    'Total tasks in executor'
)

# Subscription metrics
active_subscriptions = Gauge(
    'active_subscriptions_total',
    'Number of active subscriptions'
)

# WebSocket metrics
websocket_connections = Gauge(
    'websocket_connections_total',
    'Number of active WebSocket connections',
    ['connection_type']
)

websocket_messages_total = Counter(
    'websocket_messages_total',
    'Total WebSocket messages sent',
    ['message_type', 'channel']
)

# Instrument registry metrics
instrument_cache_size = Gauge(
    'instrument_cache_size',
    'Number of instruments in cache'
)

instrument_lookups_total = Counter(
    'instrument_lookups_total',
    'Total instrument lookups',
    ['result']  # hit or miss
)

# Kite API metrics
kite_api_calls_total = Counter(
    'kite_api_calls_total',
    'Total Kite API calls',
    ['method', 'status']
)

kite_api_errors_total = Counter(
    'kite_api_errors_total',
    'Total Kite API errors',
    ['method', 'error_type']
)

# Database metrics
database_queries_total = Counter(
    'database_queries_total',
    'Total database queries',
    ['query_type']
)

database_query_duration_seconds = Histogram(
    'database_query_duration_seconds',
    'Database query duration in seconds',
    ['query_type']
)

# Redis metrics
redis_operations_total = Counter(
    'redis_operations_total',
    'Total Redis operations',
    ['operation', 'status']
)

redis_publish_size_bytes = Histogram(
    'redis_publish_size_bytes',
    'Size of Redis published messages in bytes',
    ['channel']
)
