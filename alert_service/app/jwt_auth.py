"""
JWT Authentication for Alert Service

Validates JWT tokens from User Service for alert management.
"""

import httpx
import jwt
import time
import logging
from typing import Optional, Dict, Any
from functools import lru_cache
from fastapi import HTTPException, Security, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

logger = logging.getLogger(__name__)
security = HTTPBearer()

# User Service URL (from environment or default)
USER_SERVICE_URL = "http://localhost:8001"


class JWTAuthError(HTTPException):
    """Custom exception for JWT authentication errors"""
    def __init__(self, detail: str):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"}
        )


# Cache JWKS for 1 hour
@lru_cache(maxsize=1)
def get_jwks(timestamp: int) -> Dict[str, Any]:
    """
    Fetch JWKS from user_service (cached per hour)

    Args:
        timestamp: Current hour timestamp (for cache invalidation)

    Returns:
        JWKS dictionary

    Raises:
        JWTAuthError: If JWKS fetch fails
    """
    try:
        response = httpx.get(
            f"{USER_SERVICE_URL}/v1/auth/.well-known/jwks.json",
            timeout=5.0
        )
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError as e:
        logger.error(f"Failed to fetch JWKS: {e}")
        raise JWTAuthError("Failed to fetch JWT verification keys")


def extract_public_key_from_jwks(jwks: Dict[str, Any], kid: str) -> str:
    """
    Extract RSA public key from JWKS for the given key ID

    Args:
        jwks: JWKS dictionary
        kid: Key ID from JWT header

    Returns:
        PEM-formatted public key

    Raises:
        JWTAuthError: If key not found
    """
    for key in jwks.get("keys", []):
        if key.get("kid") == kid:
            try:
                from cryptography.hazmat.primitives import serialization
                from cryptography.hazmat.primitives.asymmetric import rsa
                from cryptography.hazmat.backends import default_backend
                import base64

                # Extract modulus and exponent
                n = int.from_bytes(
                    base64.urlsafe_b64decode(key["n"] + "=="),
                    byteorder="big"
                )
                e = int.from_bytes(
                    base64.urlsafe_b64decode(key["e"] + "=="),
                    byteorder="big"
                )

                # Create RSA public key
                public_numbers = rsa.RSAPublicNumbers(e, n)
                public_key = public_numbers.public_key(default_backend())

                # Convert to PEM
                pem = public_key.public_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PublicFormat.SubjectPublicKeyInfo
                )

                return pem.decode()
            except Exception as e:
                logger.error(f"Failed to convert JWK to PEM: {e}")
                raise JWTAuthError("Failed to process JWT key")

    raise JWTAuthError(f"Key ID '{kid}' not found in JWKS")


async def verify_jwt_token(
    credentials: HTTPAuthorizationCredentials = Security(security)
) -> Dict[str, Any]:
    """
    Verify JWT token from User Service

    Args:
        credentials: HTTP Bearer credentials

    Returns:
        Token payload with user_id, email, roles, etc.

    Raises:
        JWTAuthError: If token is invalid or expired
    """
    if not credentials:
        raise JWTAuthError("Missing authentication token")

    token = credentials.credentials

    try:
        # Decode JWT header to get key ID
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")

        if not kid:
            raise JWTAuthError("Missing key ID in token header")

        # Get JWKS (cached per hour)
        timestamp = int(time.time() / 3600)
        jwks = get_jwks(timestamp)

        # Extract public key for verification
        public_key = extract_public_key_from_jwks(jwks, kid)

        # Verify and decode token
        payload = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            audience="trading_platform",
            issuer="user_service"
        )

        logger.info(f"JWT validated for user {payload.get('sub')}")
        return payload

    except jwt.ExpiredSignatureError:
        logger.warning("Expired JWT token")
        raise JWTAuthError("Token expired")
    except jwt.InvalidAudienceError:
        logger.warning("Invalid JWT audience")
        raise JWTAuthError("Invalid token audience")
    except jwt.InvalidIssuerError:
        logger.warning("Invalid JWT issuer")
        raise JWTAuthError("Invalid token issuer")
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid JWT token: {e}")
        raise JWTAuthError(f"Invalid token: {str(e)}")
    except Exception as e:
        logger.error(f"JWT verification error: {e}", exc_info=True)
        raise JWTAuthError("Token verification failed")


async def get_current_user(
    token_payload: Dict[str, Any] = Depends(verify_jwt_token)
) -> Dict[str, Any]:
    """
    Get current user from verified JWT token

    Args:
        token_payload: Verified JWT payload

    Returns:
        User dictionary with:
        - user_id: User ID (from 'sub' claim)
        - email: User email
        - name: User name
        - roles: List of user roles
        - session_id: Session ID
        - permissions: List of permissions
    """
    return {
        "user_id": token_payload.get("sub"),
        "email": token_payload.get("email"),
        "name": token_payload.get("name"),
        "roles": token_payload.get("roles", []),
        "session_id": token_payload.get("session_id"),
        "permissions": token_payload.get("permissions", [])
    }


async def get_current_user_id(
    user: Dict[str, Any] = Depends(get_current_user)
) -> str:
    """
    Get current user ID from JWT token

    Convenience function for endpoints that only need user_id.
    Replaces the hardcoded "test_user" in routes/alerts.py

    Args:
        user: User dict from get_current_user

    Returns:
        User ID string

    Example:
        @router.post("/alerts")
        async def create_alert(
            alert: AlertCreate,
            user_id: str = Depends(get_current_user_id)
        ):
            # user_id is now from JWT token
            ...
    """
    return user["user_id"]


async def require_permission(permission: str):
    """
    Dependency factory to require specific permission

    Usage:
        @router.delete("/alerts/{alert_id}")
        async def delete_alert(
            alert_id: str,
            user = Depends(require_permission("alert:delete"))
        ):
            ...

    Args:
        permission: Required permission string

    Returns:
        Dependency function that checks permission
    """
    async def check_permission(user: Dict[str, Any] = Depends(get_current_user)):
        user_permissions = user.get("permissions", [])

        if permission not in user_permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {permission}"
            )

        return user

    return check_permission


async def require_role(role: str):
    """
    Dependency factory to require specific role

    Usage:
        @router.get("/admin/alerts")
        async def admin_list_alerts(
            user = Depends(require_role("admin"))
        ):
            ...

    Args:
        role: Required role string

    Returns:
        Dependency function that checks role
    """
    async def check_role(user: Dict[str, Any] = Depends(get_current_user)):
        user_roles = user.get("roles", [])

        if role not in user_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role required: {role}"
            )

        return user

    return check_role


# Optional JWT - for endpoints that work with or without auth
async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(lambda: None)
) -> Optional[Dict[str, Any]]:
    """
    Get user from JWT token if provided, otherwise return None

    Useful for endpoints that enhance behavior when authenticated
    but don't require authentication.

    Args:
        credentials: Optional HTTP Bearer credentials

    Returns:
        User dict if authenticated, None otherwise
    """
    if not credentials:
        return None

    try:
        # Manually extract Bearer token from Authorization header
        # This avoids the Security() auto_error issue
        payload = await verify_jwt_token(credentials)
        return await get_current_user(payload)
    except (JWTAuthError, HTTPException):
        # If token is invalid, just return None (don't raise error)
        return None


# Alternative: Verify token by calling user_service API
async def verify_token_via_api(token: str) -> Dict[str, Any]:
    """
    Verify JWT token by calling user_service /users/me endpoint

    This is an alternative to JWKS validation that doesn't require
    cryptography dependencies. However, it's slower due to the API call.

    Args:
        token: JWT token string

    Returns:
        User info from user_service

    Raises:
        JWTAuthError: If token is invalid
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{USER_SERVICE_URL}/v1/users/me",
                headers={"Authorization": f"Bearer {token}"},
                timeout=5.0
            )

            if response.status_code == 200:
                user_data = response.json()
                logger.info(f"Token verified via API for user {user_data.get('user_id')}")
                return user_data
            else:
                raise JWTAuthError("Invalid token")

    except httpx.HTTPError as e:
        logger.error(f"Token verification via API failed: {e}")
        raise JWTAuthError("Token verification failed")


async def get_current_user_via_api(
    credentials: HTTPAuthorizationCredentials = Security(security)
) -> Dict[str, Any]:
    """
    Get current user by calling user_service API

    Alternative to JWKS-based verification.
    Simpler but slower (requires API call).

    Args:
        credentials: HTTP Bearer credentials

    Returns:
        User dictionary

    Raises:
        JWTAuthError: If token is invalid
    """
    if not credentials:
        raise JWTAuthError("Missing authentication token")

    user_data = await verify_token_via_api(credentials.credentials)

    return {
        "user_id": str(user_data.get("user_id")),
        "email": user_data.get("email"),
        "name": user_data.get("name"),
        "roles": user_data.get("roles", []),
        "permissions": user_data.get("permissions", [])
    }


# Usage example for migration:
"""
MIGRATION PATH for alert_service/app/routes/alerts.py:

# OLD (hardcoded user):
async def get_current_user_id(request: Request) -> str:
    return "test_user"

# NEW (JWT auth):
from ..jwt_auth import get_current_user_id  # Import from jwt_auth module

# Then endpoints automatically get real user_id:
@router.post("", response_model=Alert)
async def create_alert(
    alert_data: AlertCreate,
    user_id: str = Depends(get_current_user_id),  # Now returns JWT user_id
    service: AlertService = Depends(get_alert_service),
):
    alert = await service.create_alert(user_id, alert_data)
    return alert
"""
