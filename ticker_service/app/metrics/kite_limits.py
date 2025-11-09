"""
KiteConnect Rate Limit Monitoring Metrics

Tracks KiteConnect API usage against rate limits:
- WebSocket subscription capacity (3,000/connection, 3 connections max)
- Order rate limits (10/sec, 200/min, 2,000/day)
- General API rate limits (3 req/sec for most endpoints)
- Session/token status
"""
from prometheus_client import Gauge, Counter

# ============================================================================
# WEBSOCKET SUBSCRIPTION METRICS
# ============================================================================

kite_websocket_subscriptions_current = Gauge(
    'kite_websocket_subscriptions_current',
    'Current number of subscribed instruments per WebSocket connection',
    ['account_id', 'connection_id']
)

kite_websocket_subscriptions_limit = Gauge(
    'kite_websocket_subscriptions_limit',
    'Maximum subscriptions per WebSocket connection',
    ['account_id', 'connection_id']
)

kite_websocket_subscription_utilization_percent = Gauge(
    'kite_websocket_subscription_utilization_percent',
    'WebSocket subscription capacity utilization percentage (0-100)',
    ['account_id', 'connection_id']
)

kite_websocket_connections_active = Gauge(
    'kite_websocket_connections_active',
    'Number of active WebSocket connections',
    ['account_id']
)

kite_websocket_connections_limit = Gauge(
    'kite_websocket_connections_limit',
    'Maximum WebSocket connections per account',
    ['account_id']
)

kite_websocket_total_capacity_utilization_percent = Gauge(
    'kite_websocket_total_capacity_utilization_percent',
    'Total subscription capacity utilization across all connections',
    ['account_id']
)

# ============================================================================
# API RATE LIMIT METRICS
# ============================================================================

kite_api_rate_limit_remaining = Gauge(
    'kite_api_rate_limit_remaining',
    'Remaining API calls in current rate limit window',
    ['account_id', 'endpoint_category']
)

kite_api_rate_limit_exceeded_total = Counter(
    'kite_api_rate_limit_exceeded_total',
    'Number of times API rate limit was exceeded (429 errors)',
    ['account_id', 'endpoint_category']
)

kite_api_calls_per_second = Gauge(
    'kite_api_calls_per_second',
    'Current API call rate (calls/second)',
    ['account_id', 'endpoint_category']
)

# ============================================================================
# ORDER RATE LIMIT METRICS
# ============================================================================

kite_order_rate_current = Gauge(
    'kite_order_rate_current',
    'Current order operation rate (operations/second)',
    ['account_id', 'operation']  # operation: place, modify, cancel
)

kite_order_queue_depth = Gauge(
    'kite_order_queue_depth',
    'Number of orders queued due to rate limiting',
    ['account_id']
)

kite_daily_order_count = Gauge(
    'kite_daily_order_count',
    'Total orders placed today (resets at midnight IST)',
    ['account_id']
)

kite_daily_api_requests = Gauge(
    'kite_daily_api_requests',
    'Total API requests made today (resets at midnight IST)',
    ['account_id']
)

# ============================================================================
# SESSION/TOKEN METRICS
# ============================================================================

kite_access_token_expiry_seconds = Gauge(
    'kite_access_token_expiry_seconds',
    'Seconds until access token expires',
    ['account_id']
)

kite_session_active = Gauge(
    'kite_session_active',
    'KiteConnect session active status (1=active, 0=inactive)',
    ['account_id']
)

# ============================================================================
# TRADING ACCOUNT CONNECTION STATUS
# ============================================================================

trading_account_connection_status = Gauge(
    'trading_account_connection_status',
    'Trading account connection status (2=connected/green, 1=degraded/amber, 0=disconnected/red)',
    ['account_id', 'account_name']
)

trading_account_connection_status_change_timestamp = Gauge(
    'trading_account_connection_status_change_timestamp',
    'Unix timestamp when connection status last changed',
    ['account_id', 'account_name']
)

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def update_websocket_subscription_metrics(
    account_id: str,
    connection_id: str,
    current_subscriptions: int,
    subscription_limit: int = 3000
):
    """
    Update WebSocket subscription metrics for a connection

    Args:
        account_id: Account identifier
        connection_id: WebSocket connection identifier
        current_subscriptions: Current number of subscribed instruments
        subscription_limit: Max subscriptions per connection (default: 3000)
    """
    utilization = (current_subscriptions / subscription_limit) * 100 if subscription_limit > 0 else 0

    kite_websocket_subscriptions_current.labels(
        account_id=account_id,
        connection_id=connection_id
    ).set(current_subscriptions)

    kite_websocket_subscriptions_limit.labels(
        account_id=account_id,
        connection_id=connection_id
    ).set(subscription_limit)

    kite_websocket_subscription_utilization_percent.labels(
        account_id=account_id,
        connection_id=connection_id
    ).set(utilization)


def update_total_subscription_capacity(
    account_id: str,
    total_subscriptions: int,
    total_capacity: int = 9000
):
    """
    Update total subscription capacity across all connections

    Args:
        account_id: Account identifier
        total_subscriptions: Total subscriptions across all connections
        total_capacity: Total capacity (default: 9000 = 3 connections × 3000)
    """
    utilization = (total_subscriptions / total_capacity) * 100 if total_capacity > 0 else 0

    kite_websocket_total_capacity_utilization_percent.labels(
        account_id=account_id
    ).set(utilization)


def update_api_rate_limit(
    account_id: str,
    endpoint_category: str,
    remaining: int
):
    """
    Update API rate limit remaining calls

    Args:
        account_id: Account identifier
        endpoint_category: API category (orders, quotes, historical, portfolio)
        remaining: Remaining calls in current window
    """
    kite_api_rate_limit_remaining.labels(
        account_id=account_id,
        endpoint_category=endpoint_category
    ).set(remaining)


def record_rate_limit_exceeded(
    account_id: str,
    endpoint_category: str
):
    """
    Record a rate limit exceeded event

    Args:
        account_id: Account identifier
        endpoint_category: API category that hit rate limit
    """
    kite_api_rate_limit_exceeded_total.labels(
        account_id=account_id,
        endpoint_category=endpoint_category
    ).inc()


def update_session_metrics(
    account_id: str,
    token_expiry_seconds: int,
    is_active: bool
):
    """
    Update session/token metrics

    Args:
        account_id: Account identifier
        token_expiry_seconds: Seconds until token expires
        is_active: Whether session is active
    """
    kite_access_token_expiry_seconds.labels(account_id=account_id).set(token_expiry_seconds)
    kite_session_active.labels(account_id=account_id).set(1 if is_active else 0)


def update_trading_account_connection_status(
    account_id: str,
    account_name: str,
    status: int,
    timestamp: float
):
    """
    Update trading account connection status

    Args:
        account_id: Account identifier
        account_name: Human-readable account name
        status: Connection status (2=connected/green, 1=degraded/amber, 0=disconnected/red)
        timestamp: Unix timestamp when status changed
    """
    trading_account_connection_status.labels(
        account_id=account_id,
        account_name=account_name
    ).set(status)

    trading_account_connection_status_change_timestamp.labels(
        account_id=account_id,
        account_name=account_name
    ).set(timestamp)
