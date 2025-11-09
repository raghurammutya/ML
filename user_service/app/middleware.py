"""
Custom middleware for user_service

Includes:
- Request ID tracking for request tracing
- HTTP metrics collection for Prometheus monitoring
"""
import time
import uuid
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app import metrics


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Middleware to track requests with unique IDs.

    Adds X-Request-ID header to all requests and responses.
    If client provides X-Request-ID, uses that, otherwise generates new UUID.

    Usage:
        app.add_middleware(RequestIDMiddleware)

    Benefits:
        - Trace requests across microservices
        - Correlate logs for debugging
        - Track request flow in distributed systems
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Get or generate request ID
        request_id = request.headers.get("X-Request-ID")
        if not request_id:
            request_id = str(uuid.uuid4())

        # Store in request state for access in route handlers
        request.state.request_id = request_id

        # Process request
        response = await call_next(request)

        # Add request ID to response headers
        response.headers["X-Request-ID"] = request_id

        return response


class HTTPMetricsMiddleware(BaseHTTPMiddleware):
    """
    Middleware to collect HTTP metrics for Prometheus.

    Tracks:
    - Total requests by method, endpoint, and status
    - Request duration by method and endpoint
    - Requests in progress by method and endpoint

    Usage:
        app.add_middleware(HTTPMetricsMiddleware)
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Extract method and path
        method = request.method
        path = request.url.path

        # Normalize path to avoid high cardinality
        # Replace IDs and other dynamic segments
        normalized_path = self._normalize_path(path)

        # Track in-progress requests
        metrics.http_requests_in_progress.labels(
            method=method,
            endpoint=normalized_path
        ).inc()

        # Track request duration
        start_time = time.time()

        try:
            # Process request
            response = await call_next(request)

            # Record metrics
            duration = time.time() - start_time
            status = response.status_code

            metrics.http_requests_total.labels(
                method=method,
                endpoint=normalized_path,
                status=status
            ).inc()

            metrics.http_request_duration_seconds.labels(
                method=method,
                endpoint=normalized_path
            ).observe(duration)

            return response

        finally:
            # Decrement in-progress counter
            metrics.http_requests_in_progress.labels(
                method=method,
                endpoint=normalized_path
            ).dec()

    def _normalize_path(self, path: str) -> str:
        """
        Normalize path to avoid high cardinality in metrics.

        Replaces dynamic segments (IDs, UUIDs, tokens) with placeholders.
        """
        # Skip normalization for static paths
        if path in ["/", "/health", "/metrics", "/docs", "/openapi.json", "/redoc"]:
            return path

        parts = path.split("/")
        normalized_parts = []

        for part in parts:
            if not part:
                continue

            # Replace numeric IDs
            if part.isdigit():
                normalized_parts.append("{id}")
            # Replace UUIDs
            elif len(part) == 36 and part.count("-") == 4:
                normalized_parts.append("{uuid}")
            # Replace tokens (long alphanumeric strings)
            elif len(part) > 32 and part.isalnum():
                normalized_parts.append("{token}")
            else:
                normalized_parts.append(part)

        return "/" + "/".join(normalized_parts)
