"""
Custom middleware for ticker service

Includes:
- Request ID tracking for request tracing
- HTTPS enforcement for production (SEC-HIGH-002)
"""
import uuid
from typing import Callable

from fastapi import Request, Response
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import RedirectResponse


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


class HTTPSRedirectMiddleware(BaseHTTPMiddleware):
    """
    SEC-HIGH-002 FIX: Enforce HTTPS in production to prevent man-in-the-middle attacks.

    Security Benefits:
    - Prevents credential theft over unencrypted HTTP
    - Protects JWT tokens from interception
    - Mitigates session hijacking attacks
    - Compliance with CWE-319 (Cleartext Transmission of Sensitive Information)

    Behavior:
    - Production/Staging: Redirects HTTP to HTTPS (permanent 301)
    - Development: Allows HTTP for localhost testing
    - Health checks: Always allowed (for load balancers)

    References:
        - CWE-319: Cleartext Transmission of Sensitive Information
        - OWASP A02:2021 – Cryptographic Failures
    """

    def __init__(self, app, environment: str = "development"):
        super().__init__(app)
        self.environment = environment
        self.enforce_https = environment in ("production", "staging")

        if self.enforce_https:
            logger.info("HTTPS enforcement enabled for production/staging")
        else:
            logger.info("HTTPS enforcement disabled for development")

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip HTTPS check for health endpoints (load balancer probes)
        if request.url.path in ["/health", "/metrics"]:
            return await call_next(request)

        # Enforce HTTPS in production
        if self.enforce_https:
            # Check if request is over HTTP
            scheme = request.url.scheme
            forwarded_proto = request.headers.get("X-Forwarded-Proto")

            # Trust X-Forwarded-Proto header from reverse proxy (nginx, load balancer)
            is_https = forwarded_proto == "https" if forwarded_proto else scheme == "https"

            if not is_https:
                # Build HTTPS URL
                https_url = request.url.replace(scheme="https")

                logger.warning(
                    f"SEC-HIGH-002: Redirecting HTTP request to HTTPS: {request.url} -> {https_url}",
                    extra={
                        "original_scheme": scheme,
                        "forwarded_proto": forwarded_proto,
                        "path": request.url.path
                    }
                )

                # Permanent redirect (301) to HTTPS
                return RedirectResponse(url=str(https_url), status_code=301)

        return await call_next(request)
