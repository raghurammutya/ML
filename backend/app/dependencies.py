# app/dependencies.py
"""Common dependency functions for FastAPI routes."""

from typing import Optional, Dict
from fastapi import WebSocket, HTTPException, status
from jose import jwt, JWTError
from .cache import CacheManager
from .config import get_settings
import logging

logger = logging.getLogger(__name__)
settings = get_settings()

# This will be set by main.py during startup
_cache_manager: Optional[CacheManager] = None

def set_cache_manager(cache_manager: CacheManager):
    """Set the global cache manager instance."""
    global _cache_manager
    _cache_manager = cache_manager

def get_cache_manager() -> CacheManager:
    """Dependency to get CacheManager instance."""
    if _cache_manager is None:
        raise RuntimeError("Cache manager not initialized")
    return _cache_manager


async def verify_websocket_token(websocket: WebSocket) -> Dict:
    """
    Verify JWT token from WebSocket query parameters.

    Args:
        websocket: FastAPI WebSocket connection

    Returns:
        dict: Decoded token payload with user_id, account_id

    Raises:
        WebSocketException: If token is invalid or missing
    """
    # Extract token from query parameter: ws://localhost:8081/ws/fo/stream?token=eyJ...
    token = websocket.query_params.get("token")

    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Missing authentication token")
        raise HTTPException(status_code=401, detail="Missing authentication token")

    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm]
        )

        user_id = payload.get("user_id")
        account_id = payload.get("account_id")

        if not user_id:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid token payload")
            raise HTTPException(status_code=401, detail="Invalid token payload")

        logger.info(f"WebSocket authenticated: user_id={user_id}, account_id={account_id}")
        return payload

    except JWTError as e:
        logger.warning(f"WebSocket JWT validation failed: {e}")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid authentication token")
        raise HTTPException(status_code=401, detail="Invalid authentication token")