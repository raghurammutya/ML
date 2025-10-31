"""
Custom middleware for the application.
Includes correlation ID tracking, request logging, and error handling.
"""

import time
import uuid
import logging
from typing import Callable
from contextvars import ContextVar
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)

# Context variable to store correlation ID for the current request
correlation_id_ctx: ContextVar[str] = ContextVar('correlation_id', default='')


def get_correlation_id() -> str:
    """Get the correlation ID for the current request."""
    return correlation_id_ctx.get()


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """
    Middleware to add correlation ID to each request for distributed tracing.

    The correlation ID can be:
    1. Provided by the client via X-Correlation-ID header
    2. Auto-generated if not provided

    The correlation ID is:
    - Added to response headers
    - Available in logs via get_correlation_id()
    - Stored in context variable for access anywhere in request lifecycle
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Get or generate correlation ID
        correlation_id = request.headers.get('X-Correlation-ID') or str(uuid.uuid4())

        # Store in context variable
        correlation_id_ctx.set(correlation_id)

        # Add to request state for easy access
        request.state.correlation_id = correlation_id

        # Process request
        response = await call_next(request)

        # Add correlation ID to response headers
        response.headers['X-Correlation-ID'] = correlation_id

        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware to log all incoming requests and responses with timing information.
    Includes correlation ID for request tracing.
    """

    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.logger = logging.getLogger("app.requests")

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Start timing
        start_time = time.time()

        # Get correlation ID
        correlation_id = getattr(request.state, 'correlation_id', 'unknown')

        # Log incoming request
        self.logger.info(
            f"Request started",
            extra={
                "correlation_id": correlation_id,
                "method": request.method,
                "path": request.url.path,
                "query": str(request.url.query),
                "client_ip": request.client.host if request.client else "unknown",
                "user_agent": request.headers.get("user-agent", "unknown"),
            }
        )

        # Process request
        try:
            response = await call_next(request)
        except Exception as e:
            # Calculate duration
            duration = time.time() - start_time

            # Log error
            self.logger.error(
                f"Request failed",
                extra={
                    "correlation_id": correlation_id,
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": round(duration * 1000, 2),
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
                exc_info=True
            )
            raise

        # Calculate duration
        duration = time.time() - start_time

        # Log successful response
        log_level = logging.WARNING if response.status_code >= 400 else logging.INFO
        self.logger.log(
            log_level,
            f"Request completed",
            extra={
                "correlation_id": correlation_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round(duration * 1000, 2),
            }
        )

        # Add timing header
        response.headers['X-Process-Time'] = f"{duration:.4f}"

        return response


class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    """
    Middleware to catch and standardize error responses.
    Ensures all errors are properly logged with correlation ID.
    """

    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.logger = logging.getLogger("app.errors")

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        try:
            return await call_next(request)
        except Exception as e:
            # Get correlation ID
            correlation_id = getattr(request.state, 'correlation_id', 'unknown')

            # Log error with full context
            self.logger.error(
                f"Unhandled exception",
                extra={
                    "correlation_id": correlation_id,
                    "method": request.method,
                    "path": request.url.path,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
                exc_info=True
            )

            # Re-raise to let FastAPI's exception handlers deal with it
            raise
