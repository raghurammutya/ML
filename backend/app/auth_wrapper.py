"""
Dual Authentication Wrapper for Backend Service

Supports both API keys (legacy) and JWT tokens (new) during migration period.
"""

import logging
from typing import Optional, Dict, Any
from fastapi import Depends, HTTPException, Header, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .auth import require_api_key, APIKey
from .jwt_auth import verify_jwt_token, JWTAuthError

logger = logging.getLogger(__name__)
security = HTTPBearer(auto_error=False)


async def get_user_from_either_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    api_key_header: Optional[str] = Header(None, alias="X-API-Key")
) -> Dict[str, Any]:
    """
    Accept either API key or JWT token for authentication

    During migration period, support both auth methods.
    Priority: JWT > API Key

    Args:
        credentials: Optional Bearer token
        api_key_header: Optional X-API-Key header

    Returns:
        User dictionary with:
        - user_id: User ID
        - auth_method: "jwt" or "api_key"
        - email: User email (JWT only)
        - name: User name (JWT only)
        - roles: User roles (JWT only)
        - api_key: API key object (api_key auth only)

    Raises:
        HTTPException: 401 if both auth methods fail or are missing
    """

    # Try JWT authentication first (preferred)
    if credentials:
        try:
            token_payload = await verify_jwt_token(credentials)

            return {
                "user_id": token_payload.get("sub"),
                "email": token_payload.get("email"),
                "name": token_payload.get("name"),
                "roles": token_payload.get("roles", []),
                "session_id": token_payload.get("session_id"),
                "permissions": token_payload.get("permissions", []),
                "auth_method": "jwt"
            }
        except JWTAuthError as e:
            # JWT provided but invalid - don't fall back to API key
            logger.warning(f"JWT authentication failed: {e.detail}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"JWT authentication failed: {e.detail}",
                headers={"WWW-Authenticate": "Bearer"}
            )

    # Try API key authentication (legacy)
    if api_key_header:
        try:
            # Import here to avoid circular dependency
            from .auth import APIKeyManager, get_api_key_manager

            # Validate API key
            key_manager = get_api_key_manager()
            api_key = await key_manager.validate_key(api_key_header)

            if not api_key or not api_key.is_active:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or inactive API key"
                )

            logger.info(f"API key authentication successful for user {api_key.user_id}")

            return {
                "user_id": api_key.user_id,
                "email": None,  # API keys don't have email
                "name": api_key.name,
                "roles": [],  # API keys don't have roles
                "permissions": [],
                "auth_method": "api_key",
                "api_key": api_key  # Include full API key object for permission checks
            }
        except Exception as e:
            logger.warning(f"API key authentication failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key",
                headers={"WWW-Authenticate": "ApiKey"}
            )

    # No authentication provided
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required. Provide either Bearer token or X-API-Key header.",
        headers={"WWW-Authenticate": "Bearer"}
    )


async def get_user_id_from_either_auth(
    user: Dict[str, Any] = Depends(get_user_from_either_auth)
) -> str:
    """
    Extract user ID from either auth method

    Convenience function for endpoints that only need user_id.

    Args:
        user: User dict from get_user_from_either_auth

    Returns:
        User ID string
    """
    return user["user_id"]


async def require_jwt_only(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> Dict[str, Any]:
    """
    Require JWT authentication only (no API key fallback)

    Use this for new endpoints that should only accept JWT.

    Args:
        credentials: Bearer token credentials

    Returns:
        User dictionary from JWT

    Raises:
        HTTPException: 401 if JWT missing or invalid
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="JWT token required",
            headers={"WWW-Authenticate": "Bearer"}
        )

    token_payload = await verify_jwt_token(credentials)

    return {
        "user_id": token_payload.get("sub"),
        "email": token_payload.get("email"),
        "name": token_payload.get("name"),
        "roles": token_payload.get("roles", []),
        "session_id": token_payload.get("session_id"),
        "permissions": token_payload.get("permissions", []),
        "auth_method": "jwt"
    }


def check_api_key_permission(user: Dict[str, Any], permission: str) -> bool:
    """
    Check if API key has specific permission

    Args:
        user: User dict from authentication
        permission: Permission to check

    Returns:
        True if permission granted, False otherwise
    """
    if user["auth_method"] != "api_key":
        return False

    api_key = user.get("api_key")
    if not api_key:
        return False

    # Map permission strings to API key flags
    permission_map = {
        "read": "can_read",
        "trade": "can_trade",
        "cancel": "can_cancel",
        "modify": "can_modify"
    }

    flag = permission_map.get(permission)
    if not flag:
        return False

    return getattr(api_key, flag, False)


async def require_trading_permission(
    user: Dict[str, Any] = Depends(get_user_from_either_auth)
) -> Dict[str, Any]:
    """
    Require permission to place trades

    Works with both JWT and API key authentication.

    Args:
        user: User from either auth method

    Returns:
        User dict if permission granted

    Raises:
        HTTPException: 403 if permission denied
    """
    if user["auth_method"] == "jwt":
        # Check JWT permissions
        if "trade:place" not in user.get("permissions", []):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Trading permission required"
            )
    elif user["auth_method"] == "api_key":
        # Check API key permissions
        if not check_api_key_permission(user, "trade"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="API key does not have trading permission"
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unknown authentication method"
        )

    return user


# Example migration path for endpoints
"""
MIGRATION GUIDE:

Phase 1 (Current): API Key only
    @router.get("/data")
    async def get_data(api_key: APIKey = Depends(require_api_key)):
        user_id = api_key.user_id
        ...

Phase 2 (Transition): Support both
    @router.get("/data")
    async def get_data(user: Dict = Depends(get_user_from_either_auth)):
        user_id = user["user_id"]
        ...

Phase 3 (Final): JWT only
    @router.get("/data")
    async def get_data(user: Dict = Depends(require_jwt_only)):
        user_id = user["user_id"]
        ...
"""
