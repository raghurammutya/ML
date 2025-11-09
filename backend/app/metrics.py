"""
Prometheus metrics for backend service

Provides comprehensive metrics for monitoring:
- HTTP API requests (latency, status codes, endpoints)
- Database operations (queries, connections, pool health)
- Cache operations (hit rate, Redis operations)
- WebSocket connections and messages
- Smart order validation and execution
- Strategy calculations and M2M updates
- Circuit breaker state for external services
- Business metrics (user activity, trading operations)
"""
from prometheus_client import Counter, Gauge, Histogram, Info, Summary

# Application info
app_info = Info('backend_service', 'Backend service application info')
app_info.info({'version': '1.0.0', 'component': 'backend_api'})

# ============================================================================
# HTTP API METRICS
# ============================================================================

http_requests_total = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status']
)

http_request_duration_seconds = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration in seconds',
    ['method', 'endpoint'],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

http_request_size_bytes = Histogram(
    'http_request_size_bytes',
    'HTTP request size in bytes',
    ['method', 'endpoint'],
    buckets=[100, 1000, 10000, 100000, 1000000]
)

http_response_size_bytes = Histogram(
    'http_response_size_bytes',
    'HTTP response size in bytes',
    ['method', 'endpoint'],
    buckets=[100, 1000, 10000, 100000, 1000000, 10000000]
)

http_active_requests = Gauge(
    'http_active_requests',
    'Number of active HTTP requests',
    ['endpoint']
)

# ============================================================================
# DATABASE METRICS
# ============================================================================

database_queries_total = Counter(
    'database_queries_total',
    'Total database queries executed',
    ['query_type', 'status']  # query_type: select, insert, update, delete, procedure
)

database_query_duration_seconds = Histogram(
    'database_query_duration_seconds',
    'Database query execution duration in seconds',
    ['query_type'],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0]
)

database_pool_connections = Gauge(
    'database_pool_connections',
    'Number of database pool connections by state',
    ['state']  # state: active, idle, total
)

database_pool_acquire_duration_seconds = Histogram(
    'database_pool_acquire_duration_seconds',
    'Time to acquire connection from pool',
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0]
)

database_pool_acquire_timeouts_total = Counter(
    'database_pool_acquire_timeouts_total',
    'Total connection pool acquire timeouts'
)

database_transaction_duration_seconds = Histogram(
    'database_transaction_duration_seconds',
    'Database transaction duration in seconds',
    ['operation'],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

database_errors_total = Counter(
    'database_errors_total',
    'Total database errors',
    ['error_type']  # connection_error, query_error, timeout, deadlock
)

# ============================================================================
# CACHE METRICS (Redis + Memory)
# ============================================================================

cache_operations_total = Counter(
    'cache_operations_total',
    'Total cache operations',
    ['operation', 'cache_layer', 'status']  # operation: get/set/delete, cache_layer: l1_memory/l2_redis
)

cache_hit_rate = Gauge(
    'cache_hit_rate',
    'Cache hit rate percentage',
    ['cache_layer']
)

cache_operation_duration_seconds = Histogram(
    'cache_operation_duration_seconds',
    'Cache operation duration in seconds',
    ['operation', 'cache_layer'],
    buckets=[0.0001, 0.0005, 0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25]
)

cache_memory_usage_bytes = Gauge(
    'cache_memory_usage_bytes',
    'Memory cache usage in bytes'
)

cache_entries_total = Gauge(
    'cache_entries_total',
    'Total number of cache entries',
    ['cache_layer']
)

redis_connection_errors_total = Counter(
    'redis_connection_errors_total',
    'Total Redis connection errors'
)

redis_command_duration_seconds = Histogram(
    'redis_command_duration_seconds',
    'Redis command duration in seconds',
    ['command'],
    buckets=[0.0001, 0.0005, 0.001, 0.005, 0.01, 0.025, 0.05, 0.1]
)

# ============================================================================
# WEBSOCKET METRICS
# ============================================================================

websocket_connections_active = Gauge(
    'websocket_connections_active',
    'Number of active WebSocket connections',
    ['endpoint']  # /ws/fo/stream, /ws/indicators, etc.
)

websocket_messages_sent_total = Counter(
    'websocket_messages_sent_total',
    'Total WebSocket messages sent to clients',
    ['endpoint', 'message_type']
)

websocket_messages_received_total = Counter(
    'websocket_messages_received_total',
    'Total WebSocket messages received from clients',
    ['endpoint', 'message_type']
)

websocket_connection_duration_seconds = Histogram(
    'websocket_connection_duration_seconds',
    'WebSocket connection duration in seconds',
    ['endpoint'],
    buckets=[1, 5, 10, 30, 60, 300, 600, 1800, 3600, 7200]  # 1s to 2h
)

websocket_errors_total = Counter(
    'websocket_errors_total',
    'Total WebSocket errors',
    ['endpoint', 'error_type']
)

websocket_subscriptions_active = Gauge(
    'websocket_subscriptions_active',
    'Number of active subscriptions per session',
    ['endpoint', 'subscription_type']  # instruments, indicators, strategies
)

# ============================================================================
# SMART ORDER METRICS
# ============================================================================

smart_order_validations_total = Counter(
    'smart_order_validations_total',
    'Total smart order validations',
    ['status']  # passed, rejected
)

smart_order_validation_duration_seconds = Histogram(
    'smart_order_validation_duration_seconds',
    'Smart order validation duration in seconds',
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0]
)

smart_order_rejection_reasons_total = Counter(
    'smart_order_rejection_reasons_total',
    'Smart order rejections by reason',
    ['reason']  # high_impact, wide_spread, low_liquidity, margin_insufficient
)

margin_calculations_total = Counter(
    'margin_calculations_total',
    'Total margin calculations',
    ['status']  # success, error, fallback
)

margin_calculation_duration_seconds = Histogram(
    'margin_calculation_duration_seconds',
    'Margin calculation duration in seconds',
    ['method'],  # ticker_service, fallback
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

cost_breakdown_calculations_total = Counter(
    'cost_breakdown_calculations_total',
    'Total cost breakdown calculations',
    ['transaction_type']  # options_buy, options_sell, futures, equity
)

market_impact_assessments_total = Counter(
    'market_impact_assessments_total',
    'Total market impact assessments',
    ['impact_level']  # low, medium, high
)

# ============================================================================
# STRATEGY METRICS
# ============================================================================

strategies_total = Gauge(
    'strategies_total',
    'Total number of active strategies',
    ['account_id']
)

strategy_operations_total = Counter(
    'strategy_operations_total',
    'Total strategy operations',
    ['operation', 'status']  # operation: create, update, delete, add_instrument
)

strategy_m2m_calculations_total = Counter(
    'strategy_m2m_calculations_total',
    'Total strategy M2M calculations',
    ['status']  # success, error
)

strategy_m2m_calculation_duration_seconds = Histogram(
    'strategy_m2m_calculation_duration_seconds',
    'Strategy M2M calculation duration in seconds',
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0]
)

strategy_instruments_total = Gauge(
    'strategy_instruments_total',
    'Total instruments across all strategies',
    ['account_id']
)

strategy_pnl_total = Gauge(
    'strategy_pnl_total',
    'Total P&L across all strategies in rupees',
    ['account_id']
)

# ============================================================================
# F&O ANALYTICS METRICS
# ============================================================================

fo_queries_total = Counter(
    'fo_queries_total',
    'Total F&O analytics queries',
    ['query_type', 'status']  # strike_distribution, oi_analysis, moneyness_series
)

fo_query_duration_seconds = Histogram(
    'fo_query_duration_seconds',
    'F&O analytics query duration in seconds',
    ['query_type'],
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0]
)

fo_instruments_cached = Gauge(
    'fo_instruments_cached',
    'Number of F&O instruments in cache'
)

fo_greeks_calculations_total = Counter(
    'fo_greeks_calculations_total',
    'Total Greeks calculations',
    ['status']  # success, error
)

# ============================================================================
# TICKER SERVICE CLIENT METRICS (Circuit Breaker)
# ============================================================================

ticker_service_requests_total = Counter(
    'ticker_service_requests_total',
    'Total requests to ticker service',
    ['operation', 'status']  # operation: subscribe, unsubscribe, health, history
)

ticker_service_request_duration_seconds = Histogram(
    'ticker_service_request_duration_seconds',
    'Ticker service request duration in seconds',
    ['operation'],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

ticker_service_circuit_breaker_state = Gauge(
    'ticker_service_circuit_breaker_state',
    'Ticker service circuit breaker state (0=closed, 1=open, 2=half_open)'
)

ticker_service_circuit_breaker_failures_total = Counter(
    'ticker_service_circuit_breaker_failures_total',
    'Total ticker service circuit breaker failures'
)

ticker_service_errors_total = Counter(
    'ticker_service_errors_total',
    'Total ticker service errors',
    ['error_type']  # timeout, connection_error, circuit_open, http_error
)

# ============================================================================
# AUTHENTICATION & AUTHORIZATION METRICS
# ============================================================================

auth_attempts_total = Counter(
    'auth_attempts_total',
    'Total authentication attempts',
    ['status']  # success, failed
)

jwt_validations_total = Counter(
    'jwt_validations_total',
    'Total JWT validations',
    ['status']  # valid, expired, invalid
)

jwt_validation_duration_seconds = Histogram(
    'jwt_validation_duration_seconds',
    'JWT validation duration in seconds',
    buckets=[0.0001, 0.0005, 0.001, 0.005, 0.01, 0.025]
)

active_sessions = Gauge(
    'active_sessions',
    'Number of active user sessions'
)

api_key_validations_total = Counter(
    'api_key_validations_total',
    'Total API key validations',
    ['status']  # valid, invalid, expired
)

# ============================================================================
# STATEMENT PARSER METRICS
# ============================================================================

statement_uploads_total = Counter(
    'statement_uploads_total',
    'Total statement uploads',
    ['status', 'file_type']  # status: success/error, file_type: csv/excel
)

statement_parsing_duration_seconds = Histogram(
    'statement_parsing_duration_seconds',
    'Statement parsing duration in seconds',
    ['file_type'],
    buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0]
)

transactions_parsed_total = Counter(
    'transactions_parsed_total',
    'Total transactions parsed from statements',
    ['category']  # fno, equity, charges, dividend, etc.
)

statement_parsing_errors_total = Counter(
    'statement_parsing_errors_total',
    'Total statement parsing errors',
    ['error_type']  # invalid_format, missing_columns, date_error, decimal_error
)

# ============================================================================
# CALENDAR & MARKET DATA METRICS
# ============================================================================

calendar_requests_total = Counter(
    'calendar_requests_total',
    'Total calendar API requests',
    ['endpoint', 'status']  # holidays, corporate_actions, etc.
)

market_data_updates_total = Counter(
    'market_data_updates_total',
    'Total market data updates received',
    ['data_type']  # tick, ohlc, market_depth
)

indicator_calculations_total = Counter(
    'indicator_calculations_total',
    'Total indicator calculations',
    ['indicator_type', 'status']  # iv, delta, gamma, theta, vega, oi
)

indicator_cache_hit_rate = Gauge(
    'indicator_cache_hit_rate',
    'Indicator cache hit rate percentage',
    ['indicator_type']
)

# ============================================================================
# BACKGROUND WORKER METRICS
# ============================================================================

worker_tasks_total = Counter(
    'worker_tasks_total',
    'Total background worker tasks',
    ['worker_type', 'status']  # strategy_m2m, order_cleanup, housekeeping
)

worker_task_duration_seconds = Histogram(
    'worker_task_duration_seconds',
    'Background worker task duration in seconds',
    ['worker_type'],
    buckets=[0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0, 300.0]
)

worker_queue_depth = Gauge(
    'worker_queue_depth',
    'Background worker queue depth',
    ['worker_type']
)

# ============================================================================
# BUSINESS METRICS
# ============================================================================

active_users = Gauge(
    'active_users',
    'Number of active users in last N minutes',
    ['time_window']  # 5m, 15m, 1h
)

user_requests_per_second = Gauge(
    'user_requests_per_second',
    'User requests per second',
    ['account_id']
)

daily_active_users = Gauge(
    'daily_active_users',
    'Number of daily active users'
)

total_orders_placed_today = Counter(
    'total_orders_placed_today',
    'Total orders placed today'
)

total_strategies_created_today = Counter(
    'total_strategies_created_today',
    'Total strategies created today'
)

# ============================================================================
# ERROR TRACKING METRICS
# ============================================================================

application_errors_total = Counter(
    'application_errors_total',
    'Total application errors',
    ['error_type', 'severity']  # severity: warning, error, critical
)

unhandled_exceptions_total = Counter(
    'unhandled_exceptions_total',
    'Total unhandled exceptions',
    ['exception_type']
)

# ============================================================================
# RATE LIMITING METRICS
# ============================================================================

rate_limit_exceeded_total = Counter(
    'rate_limit_exceeded_total',
    'Total rate limit exceeded events',
    ['endpoint', 'user_id']
)

rate_limit_current_usage = Gauge(
    'rate_limit_current_usage',
    'Current rate limit usage percentage',
    ['endpoint', 'user_id']
)
