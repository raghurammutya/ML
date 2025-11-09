"""
API Key Authentication Module

Provides FastAPI dependency for securing endpoints with API key authentication.
"""
import secrets
from typing import Optional

from fastapi import Header, HTTPException, status
from loguru import logger

from .config import get_settings


async def verify_api_key(x_api_key: Optional[str] = Header(None, alias="X-API-Key")) -> str:
    """
    FastAPI dependency to verify API key authentication.

    Usage:
        @router.get("/protected-endpoint")
        async def protected(api_key: str = Depends(verify_api_key)):
            # Endpoint logic here
            pass

    Args:
        x_api_key: API key from X-API-Key header

    Returns:
        The validated API key

    Raises:
        HTTPException: 401 if API key is missing or invalid
    """
    settings = get_settings()

    # Check if API key authentication is enabled
    if not settings.api_key_enabled:
        # Authentication disabled - allow access
        return "auth_disabled"

    # API key required but not provided
    if not x_api_key:
        logger.warning("API request rejected: Missing X-API-Key header")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key. Provide X-API-Key header.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    # Validate API key using constant-time comparison to prevent timing attacks
    # SEC-CRITICAL-001 FIX: Use secrets.compare_digest() instead of direct string comparison
    # This prevents attackers from using timing analysis to iteratively discover the API key
    if not secrets.compare_digest(x_api_key, settings.api_key):
        logger.warning("API request rejected: Invalid API key provided")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    # Valid API key
    return x_api_key
