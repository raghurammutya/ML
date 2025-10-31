"""
API Key Authentication and Authorization Module

Provides secure API key authentication for algo trading endpoints.
"""

import hashlib
import secrets
import logging
import json
from typing import Optional, Dict, Any, List
from datetime import datetime
from fastapi import HTTPException, Security, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.status import HTTP_401_UNAUTHORIZED, HTTP_403_FORBIDDEN
import asyncpg

logger = logging.getLogger(__name__)

# Security scheme for API key authentication
security = HTTPBearer(auto_error=False)


class APIKey:
    """API Key model."""

    def __init__(self, data: Dict[str, Any]):
        self.key_id = data["key_id"]
        self.user_id = data["user_id"]
        self.strategy_id = data.get("strategy_id")
        self.name = data["name"]
        self.permissions = data.get("permissions", {})
        self.rate_limit_orders_per_sec = data.get("rate_limit_orders_per_sec", 10)
        self.rate_limit_requests_per_min = data.get("rate_limit_requests_per_min", 200)
        self.ip_whitelist = data.get("ip_whitelist", [])
        self.allowed_accounts = data.get("allowed_accounts", [])
        self.is_active = data.get("is_active", True)
        self.expires_at = data.get("expires_at")

    def has_permission(self, permission: str) -> bool:
        """Check if API key has a specific permission."""
        return self.permissions.get(permission, False)

    def can_access_account(self, account_id: str) -> bool:
        """Check if API key can access a specific account."""
        if not self.allowed_accounts:  # Empty list = allow all
            return True
        return account_id in self.allowed_accounts

    def is_ip_allowed(self, ip_address: str) -> bool:
        """Check if request IP is whitelisted."""
        if not self.ip_whitelist:  # Empty list = allow all
            return True
        return ip_address in self.ip_whitelist

    def is_expired(self) -> bool:
        """Check if API key is expired."""
        if not self.expires_at:
            return False
        return datetime.now() > self.expires_at


class APIKeyManager:
    """Manages API key authentication and authorization."""

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    @staticmethod
    def generate_api_key() -> str:
        """
        Generate a new API key.

        Format: sb_{prefix}_{secret}
        Example: sb_test1234_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6
        """
        prefix = secrets.token_hex(4)  # 8 characters
        secret = secrets.token_hex(20)  # 40 characters
        return f"sb_{prefix}_{secret}"

    @staticmethod
    def hash_api_key(api_key: str) -> str:
        """Hash API key using SHA-256."""
        return hashlib.sha256(api_key.encode()).hexdigest()

    @staticmethod
    def get_key_prefix(api_key: str) -> str:
        """Extract key prefix for identification (first 8 characters)."""
        return api_key[:8]

    async def create_api_key(
        self,
        user_id: str,
        name: str,
        description: Optional[str] = None,
        permissions: Optional[Dict[str, bool]] = None,
        strategy_id: Optional[str] = None,
        rate_limit_orders_per_sec: int = 10,
        rate_limit_requests_per_min: int = 200,
        ip_whitelist: Optional[List[str]] = None,
        allowed_accounts: Optional[List[str]] = None,
        expires_at: Optional[datetime] = None,
        created_by: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new API key.

        Returns:
            {
                "api_key": "sb_xxx_yyy...",  # ONLY returned once!
                "key_id": "uuid",
                "key_prefix": "sb_xxx_"
            }
        """
        # Generate API key
        api_key = self.generate_api_key()
        key_hash = self.hash_api_key(api_key)
        key_prefix = self.get_key_prefix(api_key)

        # Default permissions
        if permissions is None:
            permissions = {"can_read": True, "can_trade": False, "can_cancel": False}

        # Insert into database
        query = """
            INSERT INTO api_keys (
                key_hash, key_prefix, user_id, strategy_id, name, description,
                permissions, rate_limit_orders_per_sec, rate_limit_requests_per_min,
                ip_whitelist, allowed_accounts, expires_at, created_by, is_active
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, true
            )
            RETURNING key_id
        """

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                query,
                key_hash, key_prefix, user_id, strategy_id, name, description,
                json.dumps(permissions), rate_limit_orders_per_sec, rate_limit_requests_per_min,
                ip_whitelist or [], allowed_accounts or [], expires_at, created_by
            )

        logger.info(f"Created API key {key_prefix} for user {user_id}")

        return {
            "api_key": api_key,  # ONLY returned once! User must save this.
            "key_id": str(row["key_id"]),
            "key_prefix": key_prefix,
            "user_id": user_id,
            "name": name,
            "permissions": permissions,
            "expires_at": expires_at.isoformat() if expires_at else None
        }

    async def validate_api_key(self, api_key: str, ip_address: Optional[str] = None) -> Optional[APIKey]:
        """
        Validate API key and return APIKey object if valid.

        Args:
            api_key: Raw API key string
            ip_address: Client IP address for whitelist check

        Returns:
            APIKey object if valid, None otherwise
        """
        key_hash = self.hash_api_key(api_key)

        query = """
            SELECT *
            FROM api_keys
            WHERE key_hash = $1 AND is_active = true
        """

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, key_hash)

            if not row:
                logger.warning(f"Invalid API key attempt: {api_key[:16]}...")
                return None

            # Convert to APIKey object
            api_key_obj = APIKey(dict(row))

            # Check expiration
            if api_key_obj.is_expired():
                logger.warning(f"Expired API key attempt: {api_key_obj.key_id}")
                return None

            # Check IP whitelist
            if ip_address and not api_key_obj.is_ip_allowed(ip_address):
                logger.warning(f"IP {ip_address} not whitelisted for key {api_key_obj.key_id}")
                return None

            # Update last_used_at (must be done inside connection context)
            await self._update_last_used(api_key_obj.key_id, conn)

        logger.debug(f"Validated API key {api_key_obj.key_id} for user {api_key_obj.user_id}")
        return api_key_obj

    async def log_usage(
        self,
        key_id: str,
        endpoint: str,
        method: str,
        ip_address: Optional[str],
        user_agent: Optional[str],
        status_code: int,
        response_time_ms: float,
        error_message: Optional[str] = None
    ):
        """Log API key usage for audit trail."""
        query = """
            INSERT INTO api_key_usage (
                key_id, endpoint, method, ip_address, user_agent,
                status_code, response_time_ms, error_message
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        """

        async with self.pool.acquire() as conn:
            await conn.execute(
                query,
                key_id, endpoint, method, ip_address, user_agent,
                status_code, response_time_ms, error_message
            )

    async def revoke_api_key(
        self,
        key_id: str,
        revoked_by: Optional[str] = None,
        reason: Optional[str] = None
    ):
        """Revoke an API key (soft delete)."""
        query = """
            UPDATE api_keys
            SET is_active = false,
                revoked_at = NOW(),
                revoked_by = $2,
                revoke_reason = $3
            WHERE key_id = $1
        """

        async with self.pool.acquire() as conn:
            await conn.execute(query, key_id, revoked_by, reason)

        logger.info(f"Revoked API key {key_id} by {revoked_by}: {reason}")

    async def list_api_keys(self, user_id: str) -> List[Dict[str, Any]]:
        """List all API keys for a user."""
        query = """
            SELECT
                key_id, key_prefix, user_id, strategy_id, name, description,
                permissions, rate_limit_orders_per_sec, rate_limit_requests_per_min,
                ip_whitelist, allowed_accounts, created_at, expires_at,
                last_used_at, is_active, revoked_at, revoke_reason
            FROM api_keys
            WHERE user_id = $1
            ORDER BY created_at DESC
        """

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, user_id)

        return [dict(row) for row in rows]

    async def _update_last_used(self, key_id: str, conn: asyncpg.Connection):
        """Update last_used_at timestamp."""
        await conn.execute(
            "UPDATE api_keys SET last_used_at = NOW() WHERE key_id = $1",
            key_id
        )


# ============================================================================
# FastAPI Dependency for Authentication
# ============================================================================

async def get_api_key_manager(request: Request) -> APIKeyManager:
    """Get APIKeyManager instance from app state."""
    # Get database pool from app state
    pool = request.app.state.db_pool
    return APIKeyManager(pool)


async def require_api_key(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security)
) -> APIKey:
    """
    Require valid API key for endpoint access.

    Usage:
        @router.get("/protected")
        async def protected_endpoint(api_key: APIKey = Depends(require_api_key)):
            ...
    """
    if not credentials:
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="API key required. Provide Bearer token in Authorization header."
        )

    # Get client IP
    client_ip = request.client.host if request.client else None

    # Validate API key
    manager = await get_api_key_manager(request)
    api_key_obj = await manager.validate_api_key(credentials.credentials, client_ip)

    if not api_key_obj:
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired API key"
        )

    # Store in request state for logging
    request.state.api_key = api_key_obj

    return api_key_obj


async def require_permission(permission: str):
    """
    Require specific permission for endpoint access.

    Usage:
        @router.post("/orders")
        async def place_order(
            api_key: APIKey = Depends(require_api_key),
            _perm: None = Depends(require_permission("can_trade"))
        ):
            ...
    """
    async def _check_permission(api_key: APIKey = Security(require_api_key)):
        if not api_key.has_permission(permission):
            raise HTTPException(
                status_code=HTTP_403_FORBIDDEN,
                detail=f"Permission '{permission}' required"
            )
    return _check_permission


async def require_account_access(account_id: str, api_key: APIKey = Security(require_api_key)):
    """Check if API key can access specific account."""
    if not api_key.can_access_account(account_id):
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail=f"Access denied to account '{account_id}'"
        )


async def require_api_key_ws(api_key: str) -> Optional[APIKey]:
    """
    Validate API key for WebSocket connections.

    WebSockets pass API key as query parameter instead of Authorization header.

    Usage:
        @router.websocket("/stream")
        async def websocket_endpoint(
            websocket: WebSocket,
            api_key: str = Query(...)
        ):
            auth_result = await require_api_key_ws(api_key)
            if not auth_result:
                await websocket.close(code=1008, reason="Invalid API key")
                return
            ...

    Args:
        api_key: Raw API key string from query parameter

    Returns:
        APIKey object if valid, None otherwise
    """
    # Import here to avoid circular dependency
    from app.database import get_data_manager

    try:
        # Get database pool
        async for dm in get_data_manager():
            manager = APIKeyManager(dm.pool)
            api_key_obj = await manager.validate_api_key(api_key, ip_address=None)
            return api_key_obj
    except Exception as e:
        logger.error(f"WebSocket API key validation failed: {e}")
        return None
