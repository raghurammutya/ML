"""
Custom middleware for ticker service

Includes:
- Request ID tracking for request tracing
"""
import uuid
from typing import Callable

from fastapi import Request, Response
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware


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

        # Add to logger context
        with logger.contextualize(request_id=request_id):
            # Log incoming request
            logger.info(
                f"Request started: {request.method} {request.url.path}",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "client": request.client.host if request.client else None,
                }
            )

            # Process request
            try:
                response = await call_next(request)

                # Add request ID to response headers
                response.headers["X-Request-ID"] = request_id

                # Log response
                logger.info(
                    f"Request completed: {request.method} {request.url.path} - {response.status_code}",
                    extra={
                        "request_id": request_id,
                        "method": request.method,
                        "path": request.url.path,
                        "status_code": response.status_code,
                    }
                )

                return response

            except Exception as exc:
                # Log error with request ID
                logger.exception(
                    f"Request failed: {request.method} {request.url.path}",
                    extra={
                        "request_id": request_id,
                        "method": request.method,
                        "path": request.url.path,
                        "error": str(exc),
                    }
                )
                raise
