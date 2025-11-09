"""
JWT Authentication for Ticker Service

Validates JWT tokens from User Service for WebSocket and REST API authentication.
"""

import httpx
import jwt
import time
import logging
import ipaddress
from typing import Optional, Dict, Any
from functools import lru_cache
from urllib.parse import urlparse
from fastapi import HTTPException, Security, Depends, status, WebSocket
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from .config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()
security = HTTPBearer()

# User Service URL
USER_SERVICE_URL = getattr(settings, 'user_service_url', 'http://localhost:8001')


class JWTAuthError(Exception):
    """Custom exception for JWT authentication errors"""
    def __init__(self, detail: str):
        self.detail = detail
        super().__init__(detail)


def validate_jwks_url(url: str) -> None:
    """
    Validate JWKS URL to prevent SSRF attacks.

    SEC-CRITICAL-002 FIX: Comprehensive SSRF protection for JWKS URL fetching.

    Protections:
    1. HTTPS-only (prevents downgrade attacks)
    2. Domain whitelist (only allowed user service domains)
    3. Private IP blocking (prevents AWS metadata, internal services access)

    Args:
        url: JWKS URL to validate

    Raises:
        JWTAuthError: If URL validation fails

    References:
        - CWE-918: Server-Side Request Forgery (SSRF)
        - OWASP SSRF Prevention Cheat Sheet
    """
    try:
        parsed = urlparse(url)
    except Exception as e:
        raise JWTAuthError(f"Invalid JWKS URL format: {e}")

    # 1. HTTPS-only enforcement
    if parsed.scheme != 'https':
        raise JWTAuthError(
            f"JWKS URL must use HTTPS protocol, got '{parsed.scheme}://'. "
            "HTTP is not allowed for security reasons."
        )

    # 2. Domain whitelist validation
    # Extract allowed domains from USER_SERVICE_URL
    allowed_domains = []
    if USER_SERVICE_URL:
        try:
            user_service_parsed = urlparse(USER_SERVICE_URL)
            if user_service_parsed.hostname:
                allowed_domains.append(user_service_parsed.hostname)
        except Exception:
            pass

    # Add localhost for development (only if USER_SERVICE_URL contains localhost)
    if any('localhost' in domain or '127.0.0.1' in domain for domain in allowed_domains):
        allowed_domains.extend(['localhost', '127.0.0.1'])

    hostname = parsed.hostname
    if not hostname:
        raise JWTAuthError("JWKS URL must contain a valid hostname")

    # Validate against whitelist
    if allowed_domains and hostname not in allowed_domains:
        raise JWTAuthError(
            f"JWKS URL domain '{hostname}' is not in the allowed whitelist: {allowed_domains}. "
            "Configure USER_SERVICE_URL to set the allowed domain."
        )

    # 3. Private IP address blocking (prevent AWS metadata, internal services)
    try:
        ip = ipaddress.ip_address(hostname)

        # Block all private IP ranges
        if ip.is_private:
            raise JWTAuthError(
                f"JWKS URL cannot target private IP address: {hostname}. "
                "Private IPs (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16) are blocked."
            )

        # Block loopback (unless explicitly allowed via localhost)
        if ip.is_loopback and hostname not in ['localhost', '127.0.0.1']:
            raise JWTAuthError(f"JWKS URL cannot target loopback address: {hostname}")

        # Block link-local (AWS metadata service at 169.254.169.254)
        if ip.is_link_local:
            raise JWTAuthError(
                f"JWKS URL cannot target link-local address: {hostname}. "
                "This blocks access to cloud metadata services (169.254.169.254)."
            )

        # Block multicast and reserved
        if ip.is_multicast or ip.is_reserved:
            raise JWTAuthError(f"JWKS URL cannot target multicast/reserved address: {hostname}")

    except ValueError:
        # hostname is a domain name, not an IP - this is preferred
        # Additional DNS rebinding protection could be added here
        pass

    logger.info(f"JWKS URL validation passed for: {url}")


# Cache JWKS for 1 hour (timestamp-based cache key)
@lru_cache(maxsize=1)
def get_jwks(timestamp: int) -> Dict[str, Any]:
    """
    Fetch JWKS from user_service (cached per hour)

    SEC-CRITICAL-002 FIX: Added comprehensive SSRF protection before fetching JWKS.

    Args:
        timestamp: Current hour timestamp (for cache invalidation)

    Returns:
        JWKS dictionary

    Raises:
        JWTAuthError: If JWKS fetch fails or URL validation fails
    """
    # Construct JWKS URL
    jwks_url = f"{USER_SERVICE_URL}/v1/auth/.well-known/jwks.json"

    # SEC-CRITICAL-002 FIX: Validate URL before fetching to prevent SSRF attacks
    validate_jwks_url(jwks_url)

    try:
        # Fetch JWKS with timeout (prevents hanging on slow/malicious endpoints)
        response = httpx.get(
            jwks_url,
            timeout=5.0,
            follow_redirects=False  # Additional protection: don't follow redirects
        )
        response.raise_for_status()
        logger.info("JWKS fetched successfully from user_service")
        return response.json()
    except httpx.HTTPError as e:
        logger.error(f"Failed to fetch JWKS from {jwks_url}: {e}")
        raise JWTAuthError("Failed to fetch JWT verification keys")
    except Exception as e:
        logger.error(f"Unexpected error fetching JWKS: {e}", exc_info=True)
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


def verify_jwt_token_sync(token: str) -> Dict[str, Any]:
    """
    Verify JWT token from User Service (synchronous)

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


async def verify_jwt_token(
    credentials: HTTPAuthorizationCredentials = Security(security)
) -> Dict[str, Any]:
    """
    Verify JWT token from User Service (async)

    Args:
        credentials: HTTP Bearer credentials

    Returns:
        Token payload

    Raises:
        HTTPException: 401 if token is invalid
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
            headers={"WWW-Authenticate": "Bearer"}
        )

    try:
        return verify_jwt_token_sync(credentials.credentials)
    except JWTAuthError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=e.detail,
            headers={"WWW-Authenticate": "Bearer"}
        )


async def get_current_user(
    token_payload: Dict[str, Any] = Depends(verify_jwt_token)
) -> Dict[str, Any]:
    """
    Get current user from verified JWT token

    Args:
        token_payload: Verified JWT payload

    Returns:
        User dictionary
    """
    return {
        "user_id": token_payload.get("sub"),
        "email": token_payload.get("email"),
        "name": token_payload.get("name"),
        "roles": token_payload.get("roles", []),
        "session_id": token_payload.get("session_id"),
        "permissions": token_payload.get("permissions", [])
    }


async def verify_ws_token(token: str) -> Dict[str, Any]:
    """
    Verify JWT token for WebSocket connection

    WebSockets can't use HTTPBearer, so we extract token from query params.

    Usage:
        @app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket, token: str):
            user = await verify_ws_token(token)
            await websocket.accept()
            # ... rest of logic

    Args:
        token: JWT token from query parameter

    Returns:
        Token payload with user info

    Raises:
        JWTAuthError: If token is invalid
    """
    try:
        return verify_jwt_token_sync(token)
    except JWTAuthError as e:
        logger.warning(f"WebSocket JWT verification failed: {e.detail}")
        raise


async def get_user_trading_accounts(user_id: str, access_token: str) -> list:
    """
    Fetch user's trading accounts from user_service

    Args:
        user_id: User ID
        access_token: JWT access token

    Returns:
        List of trading account dictionaries

    Raises:
        Exception: If fetch fails
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{USER_SERVICE_URL}/v1/trading-accounts",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=10.0
            )

            if response.status_code == 200:
                accounts = response.json()
                # Filter for active Kite accounts
                active_accounts = [
                    a for a in accounts
                    if a.get("broker") == "kite" and a.get("status") == "active"
                ]
                logger.info(f"Found {len(active_accounts)} active Kite accounts for user {user_id}")
                return active_accounts
            else:
                logger.error(f"Failed to fetch trading accounts: {response.status_code}")
                return []

    except Exception as e:
        logger.error(f"Error fetching trading accounts: {e}", exc_info=True)
        return []


async def get_account_credentials(account_id: str, service_token: str) -> Optional[Dict[str, str]]:
    """
    Get decrypted credentials for a trading account (service-to-service call)

    Args:
        account_id: Trading account ID
        service_token: Service-to-service authentication token

    Returns:
        Dictionary with decrypted credentials:
        - api_key: Kite API key
        - api_secret: Kite API secret
        - access_token: Kite access token (if available)

    Raises:
        Exception: If fetch fails
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{USER_SERVICE_URL}/v1/internal/trading-accounts/{account_id}/credentials",
                headers={"X-Service-Token": service_token},
                timeout=10.0
            )

            if response.status_code == 200:
                credentials = response.json()
                logger.info(f"Retrieved credentials for account {account_id}")
                return credentials
            else:
                logger.error(f"Failed to get account credentials: {response.status_code}")
                return None

    except Exception as e:
        logger.error(f"Error fetching account credentials: {e}", exc_info=True)
        return None


# Dual authentication support (API key + JWT)
async def get_user_from_either_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(lambda: None),
    api_key: Optional[str] = None  # Would come from existing auth.verify_api_key
) -> Dict[str, Any]:
    """
    Support both JWT and API key authentication during migration

    Args:
        credentials: Optional Bearer token
        api_key: Optional API key from X-API-Key header

    Returns:
        User dictionary

    Raises:
        HTTPException: 401 if authentication fails
    """
    # Try JWT first
    if credentials:
        try:
            payload = verify_jwt_token_sync(credentials.credentials)
            return {
                "user_id": payload.get("sub"),
                "email": payload.get("email"),
                "auth_method": "jwt",
                "token": credentials.credentials
            }
        except JWTAuthError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"JWT authentication failed: {e.detail}"
            )

    # Fall back to API key (if provided)
    if api_key:
        # API key validation would go here
        # For now, we'll accept it
        return {
            "user_id": "api_key_user",
            "auth_method": "api_key"
        }

    # No authentication provided
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required (Bearer token or API key)"
    )


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
