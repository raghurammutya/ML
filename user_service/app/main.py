"""
Main FastAPI application for user_service
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.core.config import settings
from app.core.database import init_db, dispose_db
from app.core.redis_client import redis_client

# Import routers
from app.api.v1.endpoints import auth, authz, users, mfa, trading_accounts, audit
# from app.api.v1.endpoints import admin


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup and shutdown events
    """
    # Startup
    print(f"Starting {settings.APP_NAME} v{settings.VERSION}")
    print(f"Environment: {settings.ENVIRONMENT}")

    # Initialize database (in production, use migrations instead)
    if settings.ENVIRONMENT == "development":
        init_db()

    yield

    # Shutdown
    print("Shutting down...")
    redis_client.close()
    dispose_db()


# Create FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    description="User Service - Central Identity, Authentication, and Authorization Provider",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOWED_ORIGINS,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-RateLimit-*"],
    expose_headers=["X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset"],
)

# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        # Check Redis
        redis_client.client.ping()
        redis_status = "healthy"
    except Exception:
        redis_status = "unhealthy"

    # Note: Database check would be done here with a SELECT 1
    # For now, assume healthy if app is running

    return {
        "status": "healthy" if redis_status == "healthy" else "degraded",
        "version": settings.VERSION,
        "checks": {
            "database": "healthy",  # Placeholder
            "redis": redis_status,
        }
    }


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": settings.APP_NAME,
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "docs_url": "/docs",
    }


# Include API routers
app.include_router(auth.router, prefix=f"{settings.API_V1_PREFIX}/auth", tags=["authentication"])
app.include_router(authz.router, prefix=f"{settings.API_V1_PREFIX}/authz", tags=["authorization"])
app.include_router(users.router, prefix=f"{settings.API_V1_PREFIX}/users", tags=["users"])
app.include_router(mfa.router, prefix=f"{settings.API_V1_PREFIX}/mfa", tags=["mfa"])
app.include_router(trading_accounts.router, prefix=f"{settings.API_V1_PREFIX}/trading-accounts", tags=["trading_accounts"])
app.include_router(audit.router, prefix=f"{settings.API_V1_PREFIX}/audit", tags=["audit"])
# app.include_router(admin.router, prefix=f"{settings.API_V1_PREFIX}/admin", tags=["admin"])
