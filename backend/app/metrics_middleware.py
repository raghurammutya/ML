"""
Metrics Middleware for Backend Service

Integrates comprehensive Prometheus metrics collection into FastAPI application.
Tracks HTTP requests, database operations, cache hits, WebSocket connections, and more.
"""
import time
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from typing import Callable

from app import metrics

logger = logging.getLogger(__name__)


class MetricsMiddleware(BaseHTTPMiddleware):
    """
    Middleware to collect metrics for all HTTP requests.

    Tracks:
    - Request count by method, endpoint, and status
    - Request duration by method and endpoint
    - Request/response sizes
    - Active requests gauge
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Extract endpoint path (normalize to avoid cardinality explosion)
        endpoint = self._normalize_endpoint(request.url.path)
        method = request.method

        # Track active requests
        metrics.http_active_requests.labels(endpoint=endpoint).inc()

        # Track request size
        content_length = request.headers.get('content-length')
        if content_length:
            try:
                metrics.http_request_size_bytes.labels(
                    method=method,
                    endpoint=endpoint
                ).observe(int(content_length))
            except ValueError:
                pass

        # Start timer
        start_time = time.time()

        try:
            # Process request
            response = await call_next(request)

            # Calculate duration
            duration = time.time() - start_time

            # Track metrics
            status_code = response.status_code
            metrics.http_requests_total.labels(
                method=method,
                endpoint=endpoint,
                status=str(status_code)
            ).inc()

            metrics.http_request_duration_seconds.labels(
                method=method,
                endpoint=endpoint
            ).observe(duration)

            # Track response size if available
            if hasattr(response, 'body') and response.body:
                metrics.http_response_size_bytes.labels(
                    method=method,
                    endpoint=endpoint
                ).observe(len(response.body))

            return response

        except Exception as e:
            # Track error
            duration = time.time() - start_time
            metrics.http_requests_total.labels(
                method=method,
                endpoint=endpoint,
                status="500"
            ).inc()

            metrics.http_request_duration_seconds.labels(
                method=method,
                endpoint=endpoint
            ).observe(duration)

            metrics.application_errors_total.labels(
                error_type=type(e).__name__,
                severity="error"
            ).inc()

            logger.error(f"Request error: {endpoint} - {e}")
            raise

        finally:
            # Decrement active requests
            metrics.http_active_requests.labels(endpoint=endpoint).dec()

    @staticmethod
    def _normalize_endpoint(path: str) -> str:
        """
        Normalize endpoint path to avoid metric cardinality explosion.

        Examples:
        - /strategies/123 -> /strategies/{id}
        - /fo/instruments/256265 -> /fo/instruments/{token}
        - /users/abc123/orders -> /users/{id}/orders
        """
        parts = path.split('/')
        normalized = []

        for i, part in enumerate(parts):
            # Skip empty parts
            if not part:
                continue

            # Replace numeric IDs
            if part.isdigit():
                if i > 0:
                    prev = parts[i-1]
                    if prev in ['strategies', 'accounts', 'users', 'instruments']:
                        normalized.append('{id}')
                    elif prev in ['tokens', 'symbols']:
                        normalized.append('{token}')
                    else:
                        normalized.append('{id}')
                else:
                    normalized.append('{id}')
            # Replace UUIDs
            elif len(part) == 36 and part.count('-') == 4:
                normalized.append('{uuid}')
            # Replace alphanumeric IDs (mixed letters and numbers, >8 chars)
            elif len(part) > 8 and any(c.isdigit() for c in part) and any(c.isalpha() for c in part):
                normalized.append('{id}')
            else:
                normalized.append(part)

        return '/' + '/'.join(normalized) if normalized else '/'


def track_database_query(query_type: str, duration: float, success: bool = True):
    """
    Track database query metrics.

    Args:
        query_type: Type of query (select, insert, update, delete, procedure)
        duration: Query duration in seconds
        success: Whether query succeeded
    """
    status = "success" if success else "error"
    metrics.database_queries_total.labels(
        query_type=query_type,
        status=status
    ).inc()

    metrics.database_query_duration_seconds.labels(
        query_type=query_type
    ).observe(duration)


def track_cache_operation(operation: str, cache_layer: str, duration: float, hit: bool = None):
    """
    Track cache operation metrics.

    Args:
        operation: Operation type (get, set, delete)
        cache_layer: Cache layer (l1_memory, l2_redis)
        duration: Operation duration in seconds
        hit: For 'get' operations, whether it was a hit or miss
    """
    if operation == 'get' and hit is not None:
        status = "hit" if hit else "miss"
    else:
        status = "success"

    metrics.cache_operations_total.labels(
        operation=operation,
        cache_layer=cache_layer,
        status=status
    ).inc()

    metrics.cache_operation_duration_seconds.labels(
        operation=operation,
        cache_layer=cache_layer
    ).observe(duration)


def update_cache_stats(l1_entries: int, l2_entries: int, l1_hit_rate: float, l2_hit_rate: float, memory_bytes: int):
    """
    Update cache statistics gauges.

    Args:
        l1_entries: Number of entries in L1 (memory) cache
        l2_entries: Number of entries in L2 (Redis) cache
        l1_hit_rate: L1 cache hit rate percentage (0-100)
        l2_hit_rate: L2 cache hit rate percentage (0-100)
        memory_bytes: Memory usage in bytes
    """
    metrics.cache_entries_total.labels(cache_layer="l1_memory").set(l1_entries)
    metrics.cache_entries_total.labels(cache_layer="l2_redis").set(l2_entries)
    metrics.cache_hit_rate.labels(cache_layer="l1_memory").set(l1_hit_rate)
    metrics.cache_hit_rate.labels(cache_layer="l2_redis").set(l2_hit_rate)
    metrics.cache_memory_usage_bytes.set(memory_bytes)


def track_websocket_connection(endpoint: str, connected: bool):
    """
    Track WebSocket connection state.

    Args:
        endpoint: WebSocket endpoint path
        connected: True if connecting, False if disconnecting
    """
    if connected:
        metrics.websocket_connections_active.labels(endpoint=endpoint).inc()
    else:
        metrics.websocket_connections_active.labels(endpoint=endpoint).dec()


def track_websocket_message(endpoint: str, message_type: str, sent: bool = True):
    """
    Track WebSocket messages.

    Args:
        endpoint: WebSocket endpoint path
        message_type: Type of message (tick, quote, order, etc.)
        sent: True if sent, False if received
    """
    if sent:
        metrics.websocket_messages_sent_total.labels(
            endpoint=endpoint,
            message_type=message_type
        ).inc()
    else:
        metrics.websocket_messages_received_total.labels(
            endpoint=endpoint,
            message_type=message_type
        ).inc()


def track_smart_order_validation(passed: bool, duration: float, rejection_reason: str = None):
    """
    Track smart order validation metrics.

    Args:
        passed: Whether validation passed
        duration: Validation duration in seconds
        rejection_reason: Reason for rejection if failed
    """
    status = "passed" if passed else "rejected"
    metrics.smart_order_validations_total.labels(status=status).inc()
    metrics.smart_order_validation_duration_seconds.observe(duration)

    if not passed and rejection_reason:
        metrics.smart_order_rejection_reasons_total.labels(reason=rejection_reason).inc()


def track_margin_calculation(duration: float, method: str, success: bool, fallback: bool = False):
    """
    Track margin calculation metrics.

    Args:
        duration: Calculation duration in seconds
        method: Method used (ticker_service, fallback)
        success: Whether calculation succeeded
        fallback: Whether fallback method was used
    """
    if success:
        status = "fallback" if fallback else "success"
    else:
        status = "error"

    metrics.margin_calculations_total.labels(status=status).inc()
    metrics.margin_calculation_duration_seconds.labels(method=method).observe(duration)


def track_strategy_operation(operation: str, success: bool):
    """
    Track strategy CRUD operations.

    Args:
        operation: Operation type (create, update, delete, add_instrument)
        success: Whether operation succeeded
    """
    status = "success" if success else "error"
    metrics.strategy_operations_total.labels(
        operation=operation,
        status=status
    ).inc()


def track_authentication(success: bool):
    """
    Track authentication attempts.

    Args:
        success: Whether authentication succeeded
    """
    status = "success" if success else "failed"
    metrics.auth_attempts_total.labels(status=status).inc()


def track_jwt_validation(valid: bool, expired: bool = False):
    """
    Track JWT validation.

    Args:
        valid: Whether JWT is valid
        expired: Whether JWT is expired (only if not valid)
    """
    if valid:
        status = "valid"
    elif expired:
        status = "expired"
    else:
        status = "invalid"

    metrics.jwt_validations_total.labels(status=status).inc()


def update_business_metrics(active_users_5m: int, active_users_15m: int, active_users_1h: int, daily_active: int):
    """
    Update business metrics.

    Args:
        active_users_5m: Active users in last 5 minutes
        active_users_15m: Active users in last 15 minutes
        active_users_1h: Active users in last 1 hour
        daily_active: Daily active users
    """
    metrics.active_users.labels(time_window="5m").set(active_users_5m)
    metrics.active_users.labels(time_window="15m").set(active_users_15m)
    metrics.active_users.labels(time_window="1h").set(active_users_1h)
    metrics.daily_active_users.set(daily_active)
