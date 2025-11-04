"""
JWT Authentication Middleware for Backend Service

Validates JWT tokens from User Service and provides user identity.
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

# User Service URL (from environment)
import os
USER_SERVICE_URL = os.getenv("USER_SERVICE_URL", "http://localhost:8001")


class JWTAuthError(HTTPException):
    """Custom exception for JWT authentication errors"""
    def __init__(self, detail: str):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )


# Cache JWKS for 1 hour (timestamp-based cache key)
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
    # Find the key with matching kid
    for key in jwks.get("keys", []):
        if key.get("kid") == kid:
            # Convert JWK to PEM format
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
        - roles: List of user roles
        - session_id: Session ID
        - permissions: List of permissions (if present)
    """
    return {
        "user_id": token_payload.get("sub"),
        "email": token_payload.get("email"),
        "name": token_payload.get("name"),
        "roles": token_payload.get("roles", []),
        "session_id": token_payload.get("session_id"),
        "permissions": token_payload.get("permissions", []),
        "token_type": "jwt"
    }


async def require_permission(permission: str):
    """
    Dependency factory to require specific permission

    Usage:
        @router.get("/admin")
        async def admin_endpoint(user = Depends(require_permission("admin:access"))):
            return {"message": "Admin access granted"}

    Args:
        permission: Required permission string

    Returns:
        Dependency function that checks permission
    """
    async def check_permission(user: Dict[str, Any] = Depends(get_current_user)):
        # Check if user has required permission
        user_permissions = user.get("permissions", [])

        if permission not in user_permissions:
            # Also check via user_service API
            try:
                # Get original token from request context (stored during verification)
                # For now, just check local permissions
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Permission denied: {permission}"
                )
            except Exception as e:
                logger.error(f"Permission check failed: {e}")
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Permission check failed"
                )

        return user

    return check_permission


async def require_role(role: str):
    """
    Dependency factory to require specific role

    Usage:
        @router.get("/admin")
        async def admin_endpoint(user = Depends(require_role("admin"))):
            return {"message": "Admin access granted"}

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
        payload = await verify_jwt_token(credentials)
        return await get_current_user(payload)
    except (JWTAuthError, HTTPException):
        # If token is invalid, just return None (don't raise error)
        return None


async def verify_jwt_token_string(token: str) -> Dict[str, Any]:
    """
    Verify JWT token from string (for WebSocket authentication).

    Args:
        token: JWT token string

    Returns:
        Token payload with user_id, email, roles, etc.

    Raises:
        JWTAuthError: If token is invalid or expired
    """
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
        return {
            "user_id": payload.get("sub"),
            "email": payload.get("email"),
            "name": payload.get("name"),
            "roles": payload.get("roles", []),
            "session_id": payload.get("session_id"),
            "permissions": payload.get("permissions", []),
            "token_type": "jwt"
        }

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
