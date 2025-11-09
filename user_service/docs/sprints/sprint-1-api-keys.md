# Sprint 1: API Key Authentication System

**Priority:** HIGHEST
**Duration:** 1 week
**Branch:** `feature/sprint-1-api-keys`

---

## Context

The Python SDK (`/mnt/stocksblitz-data/Quantagro/tradingview-viz/python-sdk`) supports API key authentication via `TradingClient(api_key="sb_...")`, but the backend user_service does NOT implement API key authentication. This sprint adds complete API key management and authentication to enable SDK users to authenticate without username/password.

**Current SDK Implementation:**
- Location: `python-sdk/stocksblitz/client.py:48-91`
- Example: `python-sdk/examples/api_key_auth_example.py`
- Expected format: `sb_{8_char_prefix}_{40_char_secret}`

**User Service Location:** `/mnt/stocksblitz-data/Quantagro/tradingview-viz/user_service`

---

## Objectives

1. Add database schema for API keys
2. Implement API key CRUD endpoints
3. Add API key authentication middleware
4. Implement scope-based authorization
5. Add rate limiting per API key
6. Create comprehensive tests
7. Update documentation

---

## Task 1: Database Schema

### Requirements:

Create Alembic migration: `alembic/versions/YYYYMMDD_HHMM_005_add_api_keys.py`

**Tables to create:**

1. **api_keys** table:
```sql
CREATE TABLE api_keys (
    api_key_id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    key_prefix VARCHAR(20) NOT NULL UNIQUE,  -- 'sb_30d4d5ea'
    key_hash VARCHAR(255) NOT NULL,  -- SHA-256 hash of full key
    name VARCHAR(255) NOT NULL,  -- User-friendly name
    description TEXT,
    scopes JSONB NOT NULL DEFAULT '["read"]',  -- ['read', 'trade', 'admin']
    ip_whitelist JSONB,  -- ['1.2.3.4', '5.6.7.8'] or null (allow all)
    rate_limit_tier VARCHAR(50) DEFAULT 'standard',  -- 'free', 'standard', 'premium', 'unlimited'
    last_used_at TIMESTAMP,
    last_used_ip VARCHAR(45),
    usage_count BIGINT DEFAULT 0,
    expires_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    revoked_at TIMESTAMP,
    revoked_by BIGINT REFERENCES users(user_id),
    revoked_reason TEXT
);

CREATE INDEX idx_api_keys_user_id ON api_keys(user_id);
CREATE INDEX idx_api_keys_key_prefix ON api_keys(key_prefix) WHERE revoked_at IS NULL;
CREATE INDEX idx_api_keys_expires_at ON api_keys(expires_at) WHERE revoked_at IS NULL;
```

2. **api_key_usage** table (optional, for analytics):
```sql
CREATE TABLE api_key_usage_logs (
    log_id BIGSERIAL PRIMARY KEY,
    api_key_id BIGINT NOT NULL REFERENCES api_keys(api_key_id) ON DELETE CASCADE,
    endpoint VARCHAR(255) NOT NULL,
    method VARCHAR(10) NOT NULL,
    status_code INTEGER NOT NULL,
    response_time_ms INTEGER,
    ip_address VARCHAR(45),
    user_agent TEXT,
    error_message TEXT,
    timestamp TIMESTAMP DEFAULT NOW()
);

-- Convert to TimescaleDB hypertable for better performance
SELECT create_hypertable('api_key_usage_logs', 'timestamp');

CREATE INDEX idx_api_key_usage_api_key_id ON api_key_usage_logs(api_key_id, timestamp DESC);
CREATE INDEX idx_api_key_usage_timestamp ON api_key_usage_logs(timestamp DESC);
```

**Model to create:**

File: `app/models/api_key.py`

```python
"""
API Key model for SDK authentication
"""

from datetime import datetime
import enum
from sqlalchemy import Column, BigInteger, String, DateTime, ForeignKey, Text, Integer, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.core.database import Base


class RateLimitTier(str, enum.Enum):
    """Rate limit tier for API keys"""
    FREE = "free"           # 100 requests/hour
    STANDARD = "standard"   # 1000 requests/hour
    PREMIUM = "premium"     # 10000 requests/hour
    UNLIMITED = "unlimited" # No limit


class ApiKey(Base):
    """API Key model for authentication"""
    __tablename__ = "api_keys"
    __table_args__ = (
        Index('idx_api_keys_user_id', 'user_id'),
        Index('idx_api_keys_key_prefix', 'key_prefix', postgresql_where=sa.text('revoked_at IS NULL')),
        Index('idx_api_keys_expires_at', 'expires_at', postgresql_where=sa.text('revoked_at IS NULL')),
    )

    api_key_id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    key_prefix = Column(String(20), nullable=False, unique=True)
    key_hash = Column(String(255), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    scopes = Column(JSONB, nullable=False, default=["read"])
    ip_whitelist = Column(JSONB, nullable=True)
    rate_limit_tier = Column(Enum(RateLimitTier), default=RateLimitTier.STANDARD, nullable=False)
    last_used_at = Column(DateTime, nullable=True)
    last_used_ip = Column(String(45), nullable=True)
    usage_count = Column(BigInteger, default=0, nullable=False)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    revoked_at = Column(DateTime, nullable=True)
    revoked_by = Column(BigInteger, ForeignKey("users.user_id"), nullable=True)
    revoked_reason = Column(Text, nullable=True)

    # Relationships
    user = relationship("User", foreign_keys=[user_id], back_populates="api_keys")
    revoker = relationship("User", foreign_keys=[revoked_by])

    def __repr__(self):
        return f"<ApiKey(id={self.api_key_id}, prefix='{self.key_prefix}', user_id={self.user_id})>"


class ApiKeyUsageLog(Base):
    """API Key usage log for analytics"""
    __tablename__ = "api_key_usage_logs"
    __table_args__ = (
        Index('idx_api_key_usage_api_key_id', 'api_key_id', 'timestamp'),
        Index('idx_api_key_usage_timestamp', 'timestamp'),
    )

    log_id = Column(BigInteger, primary_key=True, autoincrement=True)
    api_key_id = Column(BigInteger, ForeignKey("api_keys.api_key_id", ondelete="CASCADE"), nullable=False)
    endpoint = Column(String(255), nullable=False)
    method = Column(String(10), nullable=False)
    status_code = Column(Integer, nullable=False)
    response_time_ms = Column(Integer, nullable=True)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    api_key = relationship("ApiKey")

    def __repr__(self):
        return f"<ApiKeyUsageLog(id={self.log_id}, api_key_id={self.api_key_id}, endpoint='{self.endpoint}')>"
```

**Update:** `app/models/__init__.py` - Add ApiKey, ApiKeyUsageLog, RateLimitTier to exports

**Update:** `app/models/user.py` - Add relationship:
```python
api_keys = relationship("ApiKey", foreign_keys="ApiKey.user_id", back_populates="user", cascade="all, delete-orphan")
```

---

## Task 2: API Key Service

File: `app/services/api_key_service.py`

```python
"""
API Key Service - API key generation and management
"""

import secrets
import hashlib
from datetime import datetime, timedelta
from typing import Optional, List, Tuple
from sqlalchemy.orm import Session

from app.core.redis_client import RedisClient
from app.models import ApiKey, User, RateLimitTier
from app.services.event_service import EventService


class ApiKeyService:
    """Service for API key management"""

    def __init__(self, db: Session, redis: RedisClient):
        self.db = db
        self.redis = redis
        self.event_service = EventService(redis)

    def generate_api_key(
        self,
        user_id: int,
        name: str,
        scopes: List[str],
        description: Optional[str] = None,
        ip_whitelist: Optional[List[str]] = None,
        rate_limit_tier: RateLimitTier = RateLimitTier.STANDARD,
        expires_in_days: Optional[int] = None
    ) -> Tuple[ApiKey, str]:
        """
        Generate a new API key for a user.

        Args:
            user_id: User ID
            name: User-friendly name for the key
            scopes: List of scopes (e.g., ['read', 'trade'])
            description: Optional description
            ip_whitelist: Optional list of allowed IPs
            rate_limit_tier: Rate limit tier
            expires_in_days: Optional expiration in days

        Returns:
            Tuple of (ApiKey record, full_key_string)
            WARNING: full_key_string is returned ONLY ONCE and cannot be retrieved later
        """
        # Generate key components
        prefix = self._generate_key_prefix()
        secret = self._generate_key_secret()
        full_key = f"sb_{prefix}_{secret}"

        # Hash the secret for storage
        key_hash = self._hash_secret(secret)

        # Calculate expiration
        expires_at = None
        if expires_in_days:
            expires_at = datetime.utcnow() + timedelta(days=expires_in_days)

        # Create API key record
        api_key = ApiKey(
            user_id=user_id,
            key_prefix=f"sb_{prefix}",
            key_hash=key_hash,
            name=name,
            description=description,
            scopes=scopes,
            ip_whitelist=ip_whitelist,
            rate_limit_tier=rate_limit_tier,
            expires_at=expires_at
        )

        self.db.add(api_key)
        self.db.commit()
        self.db.refresh(api_key)

        # Publish event
        self.event_service.publish_event(
            "api_key.created",
            {
                "api_key_id": api_key.api_key_id,
                "user_id": user_id,
                "key_prefix": api_key.key_prefix,
                "scopes": scopes,
                "expires_at": expires_at.isoformat() if expires_at else None
            }
        )

        return api_key, full_key

    def verify_api_key(
        self,
        key_prefix: str,
        secret: str,
        ip_address: Optional[str] = None
    ) -> Optional[ApiKey]:
        """
        Verify an API key and return the ApiKey record if valid.

        Args:
            key_prefix: Key prefix (e.g., 'sb_30d4d5ea')
            secret: Secret part of the key
            ip_address: Client IP address for whitelist check

        Returns:
            ApiKey record if valid, None otherwise
        """
        # Find API key by prefix
        api_key = self.db.query(ApiKey).filter(
            ApiKey.key_prefix == key_prefix,
            ApiKey.revoked_at.is_(None)
        ).first()

        if not api_key:
            return None

        # Check expiration
        if api_key.expires_at and api_key.expires_at < datetime.utcnow():
            return None

        # Verify secret hash
        secret_hash = self._hash_secret(secret)
        if secret_hash != api_key.key_hash:
            return None

        # Check IP whitelist
        if api_key.ip_whitelist and ip_address:
            if ip_address not in api_key.ip_whitelist:
                return None

        # Update last used
        api_key.last_used_at = datetime.utcnow()
        api_key.last_used_ip = ip_address
        api_key.usage_count += 1
        self.db.commit()

        return api_key

    def list_user_api_keys(self, user_id: int, include_revoked: bool = False) -> List[ApiKey]:
        """List all API keys for a user"""
        query = self.db.query(ApiKey).filter(ApiKey.user_id == user_id)

        if not include_revoked:
            query = query.filter(ApiKey.revoked_at.is_(None))

        return query.order_by(ApiKey.created_at.desc()).all()

    def revoke_api_key(
        self,
        api_key_id: int,
        revoked_by_user_id: int,
        reason: Optional[str] = None
    ) -> bool:
        """Revoke an API key"""
        api_key = self.db.query(ApiKey).filter(ApiKey.api_key_id == api_key_id).first()

        if not api_key or api_key.revoked_at:
            return False

        api_key.revoked_at = datetime.utcnow()
        api_key.revoked_by = revoked_by_user_id
        api_key.revoked_reason = reason

        self.db.commit()

        # Publish event
        self.event_service.publish_event(
            "api_key.revoked",
            {
                "api_key_id": api_key_id,
                "user_id": api_key.user_id,
                "revoked_by": revoked_by_user_id,
                "reason": reason
            }
        )

        return True

    def update_api_key(
        self,
        api_key_id: int,
        name: Optional[str] = None,
        description: Optional[str] = None,
        scopes: Optional[List[str]] = None,
        ip_whitelist: Optional[List[str]] = None,
        rate_limit_tier: Optional[RateLimitTier] = None
    ) -> Optional[ApiKey]:
        """Update an API key"""
        api_key = self.db.query(ApiKey).filter(ApiKey.api_key_id == api_key_id).first()

        if not api_key or api_key.revoked_at:
            return None

        if name is not None:
            api_key.name = name
        if description is not None:
            api_key.description = description
        if scopes is not None:
            api_key.scopes = scopes
        if ip_whitelist is not None:
            api_key.ip_whitelist = ip_whitelist
        if rate_limit_tier is not None:
            api_key.rate_limit_tier = rate_limit_tier

        self.db.commit()
        self.db.refresh(api_key)

        return api_key

    def rotate_api_key(
        self,
        api_key_id: int,
        user_id: int
    ) -> Tuple[Optional[ApiKey], Optional[str]]:
        """
        Rotate an API key (revoke old, create new with same settings).

        Args:
            api_key_id: API key ID to rotate
            user_id: User ID (for verification)

        Returns:
            Tuple of (new_ApiKey, new_full_key) or (None, None) if failed
        """
        old_key = self.db.query(ApiKey).filter(
            ApiKey.api_key_id == api_key_id,
            ApiKey.user_id == user_id
        ).first()

        if not old_key or old_key.revoked_at:
            return None, None

        # Create new key with same settings
        new_key, full_key = self.generate_api_key(
            user_id=user_id,
            name=f"{old_key.name} (rotated)",
            scopes=old_key.scopes,
            description=old_key.description,
            ip_whitelist=old_key.ip_whitelist,
            rate_limit_tier=old_key.rate_limit_tier,
            expires_in_days=None  # Don't copy expiration
        )

        # Revoke old key
        self.revoke_api_key(api_key_id, user_id, "Key rotated")

        return new_key, full_key

    @staticmethod
    def _generate_key_prefix() -> str:
        """Generate 8-character prefix (hex)"""
        return secrets.token_hex(4)  # 4 bytes = 8 hex chars

    @staticmethod
    def _generate_key_secret() -> str:
        """Generate 40-character secret (hex)"""
        return secrets.token_hex(20)  # 20 bytes = 40 hex chars

    @staticmethod
    def _hash_secret(secret: str) -> str:
        """Hash secret with SHA-256"""
        return hashlib.sha256(secret.encode()).hexdigest()
```

---

## Task 3: Authentication Middleware

File: `app/api/dependencies.py` - Add new functions:

```python
from typing import Optional
from fastapi import Header, HTTPException, status
from app.models import ApiKey
from app.services.api_key_service import ApiKeyService

async def get_api_key_service(
    db: Session = Depends(get_db),
    redis: RedisClient = Depends(get_redis)
) -> ApiKeyService:
    """Get API key service"""
    return ApiKeyService(db, redis)

async def get_current_user_from_api_key(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
    client_ip: str = Depends(get_client_ip)
) -> User:
    """
    Authenticate user via API key.

    Supports two header formats:
    - X-API-Key: sb_30d4d5ea_bbb52c64...
    - Authorization: Bearer sb_30d4d5ea_bbb52c64...
    """
    # Extract API key from headers
    api_key_string = None

    if x_api_key:
        api_key_string = x_api_key
    elif authorization and authorization.startswith("Bearer sb_"):
        api_key_string = authorization.replace("Bearer ", "")

    if not api_key_string:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required. Provide via X-API-Key header or Authorization: Bearer header"
        )

    # Parse key (format: sb_{prefix}_{secret})
    if not api_key_string.startswith("sb_"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key format"
        )

    parts = api_key_string.split("_")
    if len(parts) != 3:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key format"
        )

    key_prefix = f"sb_{parts[1]}"
    secret = parts[2]

    # Verify API key
    api_key_service = ApiKeyService(db, redis)
    api_key = api_key_service.verify_api_key(key_prefix, secret, client_ip)

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired API key"
        )

    # Check rate limit
    rate_limits = {
        RateLimitTier.FREE: (100, 3600),       # 100/hour
        RateLimitTier.STANDARD: (1000, 3600),  # 1000/hour
        RateLimitTier.PREMIUM: (10000, 3600),  # 10000/hour
        RateLimitTier.UNLIMITED: None
    }

    if api_key.rate_limit_tier != RateLimitTier.UNLIMITED:
        limit, window = rate_limits[api_key.rate_limit_tier]
        rate_limit_key = f"ratelimit:apikey:{api_key.api_key_id}"
        allowed, remaining = redis.check_rate_limit(rate_limit_key, limit, window)

        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded for API key. Tier: {api_key.rate_limit_tier.value}",
                headers={"Retry-After": str(window)}
            )

    # Return user
    return api_key.user

async def get_current_user_flexible(
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    db: Session = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
    client_ip: str = Depends(get_client_ip)
) -> User:
    """
    Authenticate user via JWT OR API key.

    Priority:
    1. Try JWT (Authorization: Bearer eyJ...)
    2. Try API key (X-API-Key or Authorization: Bearer sb_...)
    """
    # Try JWT first
    if authorization and not authorization.startswith("Bearer sb_"):
        try:
            return await get_current_user(
                authorization=authorization,
                db=db,
                redis=redis
            )
        except HTTPException:
            pass

    # Try API key
    return await get_current_user_from_api_key(
        x_api_key=x_api_key,
        authorization=authorization,
        db=db,
        redis=redis,
        client_ip=client_ip
    )

def require_scope(required_scope: str):
    """
    Dependency to require specific API key scope.

    Usage:
        @router.post("/orders")
        async def place_order(
            current_user: User = Depends(require_scope("trade"))
        ):
            ...
    """
    async def dependency(
        request: Request,
        db: Session = Depends(get_db),
        redis: RedisClient = Depends(get_redis),
        client_ip: str = Depends(get_client_ip)
    ) -> User:
        # Check if API key was used
        x_api_key = request.headers.get("X-API-Key")
        authorization = request.headers.get("Authorization", "")

        is_api_key = x_api_key or authorization.startswith("Bearer sb_")

        if not is_api_key:
            # Not API key, just authenticate normally
            return await get_current_user_flexible(
                authorization=authorization,
                x_api_key=x_api_key,
                db=db,
                redis=redis,
                client_ip=client_ip
            )

        # API key authentication - check scope
        user = await get_current_user_from_api_key(
            x_api_key=x_api_key,
            authorization=authorization,
            db=db,
            redis=redis,
            client_ip=client_ip
        )

        # Get API key from request state (set by get_current_user_from_api_key)
        # For now, re-verify to get scopes
        if authorization and authorization.startswith("Bearer sb_"):
            api_key_string = authorization.replace("Bearer ", "")
        else:
            api_key_string = x_api_key

        parts = api_key_string.split("_")
        key_prefix = f"sb_{parts[1]}"
        secret = parts[2]

        api_key_service = ApiKeyService(db, redis)
        api_key = api_key_service.verify_api_key(key_prefix, secret, client_ip)

        if required_scope not in api_key.scopes and "*" not in api_key.scopes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"API key missing required scope: {required_scope}"
            )

        return user

    return dependency
```

---

## Task 4: API Endpoints

File: `app/api/v1/endpoints/api_keys.py` (NEW)

```python
"""
API Key management endpoints
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.redis_client import get_redis, RedisClient
from app.api.dependencies import get_current_user, get_api_key_service
from app.models import User, RateLimitTier
from app.services.api_key_service import ApiKeyService
from app.schemas.api_key import (
    ApiKeyCreateRequest,
    ApiKeyCreateResponse,
    ApiKeyResponse,
    ApiKeyListResponse,
    ApiKeyUpdateRequest,
    ApiKeyRotateResponse
)


router = APIRouter()


@router.post("", response_model=ApiKeyCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    request_data: ApiKeyCreateRequest,
    current_user: User = Depends(get_current_user),
    api_key_service: ApiKeyService = Depends(get_api_key_service)
):
    """
    Create a new API key.

    **WARNING:** The full API key is returned ONLY ONCE and cannot be retrieved later.
    Store it securely.

    **Request Body:**
    - name: User-friendly name (e.g., "Production Bot")
    - scopes: List of scopes (e.g., ["read", "trade"])
    - description: Optional description
    - ip_whitelist: Optional list of allowed IPs
    - rate_limit_tier: Rate limit tier (free, standard, premium, unlimited)
    - expires_in_days: Optional expiration in days

    **Returns:**
    - api_key_id: Created API key ID
    - api_key: Full API key string (save this!)
    - key_prefix: Key prefix for identification
    - name, scopes, expires_at, etc.

    **Scopes:**
    - read: Read-only access
    - trade: Place and cancel orders
    - admin: Full access
    - account:manage: Manage trading accounts
    """
    try:
        api_key, full_key = api_key_service.generate_api_key(
            user_id=current_user.user_id,
            name=request_data.name,
            scopes=request_data.scopes,
            description=request_data.description,
            ip_whitelist=request_data.ip_whitelist,
            rate_limit_tier=request_data.rate_limit_tier or RateLimitTier.STANDARD,
            expires_in_days=request_data.expires_in_days
        )

        return ApiKeyCreateResponse(
            api_key_id=api_key.api_key_id,
            api_key=full_key,
            key_prefix=api_key.key_prefix,
            name=api_key.name,
            description=api_key.description,
            scopes=api_key.scopes,
            ip_whitelist=api_key.ip_whitelist,
            rate_limit_tier=api_key.rate_limit_tier.value,
            expires_at=api_key.expires_at,
            created_at=api_key.created_at
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create API key: {str(e)}"
        )


@router.get("", response_model=ApiKeyListResponse)
async def list_api_keys(
    include_revoked: bool = False,
    current_user: User = Depends(get_current_user),
    api_key_service: ApiKeyService = Depends(get_api_key_service)
):
    """
    List all API keys for the current user.

    **Query Parameters:**
    - include_revoked: Include revoked keys (default: false)

    **Returns:**
    - List of API keys (without secrets)
    """
    api_keys = api_key_service.list_user_api_keys(
        current_user.user_id,
        include_revoked=include_revoked
    )

    return ApiKeyListResponse(
        api_keys=[
            ApiKeyResponse(
                api_key_id=key.api_key_id,
                key_prefix=key.key_prefix,
                name=key.name,
                description=key.description,
                scopes=key.scopes,
                ip_whitelist=key.ip_whitelist,
                rate_limit_tier=key.rate_limit_tier.value,
                last_used_at=key.last_used_at,
                last_used_ip=key.last_used_ip,
                usage_count=key.usage_count,
                expires_at=key.expires_at,
                created_at=key.created_at,
                revoked_at=key.revoked_at,
                revoked_reason=key.revoked_reason
            )
            for key in api_keys
        ]
    )


@router.delete("/{api_key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(
    api_key_id: int,
    reason: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    api_key_service: ApiKeyService = Depends(get_api_key_service)
):
    """
    Revoke an API key.

    **Path Parameters:**
    - api_key_id: API key ID to revoke

    **Query Parameters:**
    - reason: Optional reason for revocation

    **Returns:**
    - 204 No Content on success
    - 404 if API key not found
    """
    success = api_key_service.revoke_api_key(
        api_key_id=api_key_id,
        revoked_by_user_id=current_user.user_id,
        reason=reason
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found or already revoked"
        )


@router.put("/{api_key_id}", response_model=ApiKeyResponse)
async def update_api_key(
    api_key_id: int,
    request_data: ApiKeyUpdateRequest,
    current_user: User = Depends(get_current_user),
    api_key_service: ApiKeyService = Depends(get_api_key_service)
):
    """
    Update an API key.

    **Path Parameters:**
    - api_key_id: API key ID to update

    **Request Body:**
    - name: New name (optional)
    - description: New description (optional)
    - scopes: New scopes (optional)
    - ip_whitelist: New IP whitelist (optional)
    - rate_limit_tier: New rate limit tier (optional)

    **Returns:**
    - Updated API key
    """
    api_key = api_key_service.update_api_key(
        api_key_id=api_key_id,
        name=request_data.name,
        description=request_data.description,
        scopes=request_data.scopes,
        ip_whitelist=request_data.ip_whitelist,
        rate_limit_tier=request_data.rate_limit_tier
    )

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found or revoked"
        )

    return ApiKeyResponse(
        api_key_id=api_key.api_key_id,
        key_prefix=api_key.key_prefix,
        name=api_key.name,
        description=api_key.description,
        scopes=api_key.scopes,
        ip_whitelist=api_key.ip_whitelist,
        rate_limit_tier=api_key.rate_limit_tier.value,
        last_used_at=api_key.last_used_at,
        last_used_ip=api_key.last_used_ip,
        usage_count=api_key.usage_count,
        expires_at=api_key.expires_at,
        created_at=api_key.created_at,
        revoked_at=api_key.revoked_at,
        revoked_reason=api_key.revoked_reason
    )


@router.post("/{api_key_id}/rotate", response_model=ApiKeyRotateResponse)
async def rotate_api_key(
    api_key_id: int,
    current_user: User = Depends(get_current_user),
    api_key_service: ApiKeyService = Depends(get_api_key_service)
):
    """
    Rotate an API key (revoke old, create new with same settings).

    **WARNING:** The new API key is returned ONLY ONCE. Store it securely.
    The old key is immediately revoked.

    **Path Parameters:**
    - api_key_id: API key ID to rotate

    **Returns:**
    - new_api_key_id: New API key ID
    - api_key: New full API key string
    - old_api_key_id: Old API key ID (now revoked)
    """
    new_key, full_key = api_key_service.rotate_api_key(
        api_key_id=api_key_id,
        user_id=current_user.user_id
    )

    if not new_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found or already revoked"
        )

    return ApiKeyRotateResponse(
        new_api_key_id=new_key.api_key_id,
        api_key=full_key,
        key_prefix=new_key.key_prefix,
        name=new_key.name,
        scopes=new_key.scopes,
        old_api_key_id=api_key_id
    )
```

**Update:** `app/api/v1/__init__.py` - Add API key router

---

## Task 5: Schemas

File: `app/schemas/api_key.py` (NEW)

```python
"""
API Key schemas
"""

from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field, validator

from app.models import RateLimitTier


class ApiKeyCreateRequest(BaseModel):
    """API key creation request"""
    name: str = Field(..., min_length=1, max_length=255, description="User-friendly name")
    scopes: List[str] = Field(..., min_items=1, description="List of scopes")
    description: Optional[str] = Field(None, description="Optional description")
    ip_whitelist: Optional[List[str]] = Field(None, description="Optional IP whitelist")
    rate_limit_tier: Optional[RateLimitTier] = Field(RateLimitTier.STANDARD, description="Rate limit tier")
    expires_in_days: Optional[int] = Field(None, ge=1, le=3650, description="Expiration in days (max 10 years)")

    @validator('scopes')
    def validate_scopes(cls, v):
        valid_scopes = ['read', 'trade', 'admin', 'account:manage', 'strategy:execute', '*']
        for scope in v:
            if scope not in valid_scopes:
                raise ValueError(f"Invalid scope: {scope}. Valid scopes: {', '.join(valid_scopes)}")
        return v


class ApiKeyCreateResponse(BaseModel):
    """API key creation response"""
    api_key_id: int
    api_key: str = Field(..., description="Full API key (save this, won't be shown again!)")
    key_prefix: str
    name: str
    description: Optional[str]
    scopes: List[str]
    ip_whitelist: Optional[List[str]]
    rate_limit_tier: str
    expires_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


class ApiKeyResponse(BaseModel):
    """API key response (without secret)"""
    api_key_id: int
    key_prefix: str
    name: str
    description: Optional[str]
    scopes: List[str]
    ip_whitelist: Optional[List[str]]
    rate_limit_tier: str
    last_used_at: Optional[datetime]
    last_used_ip: Optional[str]
    usage_count: int
    expires_at: Optional[datetime]
    created_at: datetime
    revoked_at: Optional[datetime]
    revoked_reason: Optional[str]

    class Config:
        from_attributes = True


class ApiKeyListResponse(BaseModel):
    """API key list response"""
    api_keys: List[ApiKeyResponse]


class ApiKeyUpdateRequest(BaseModel):
    """API key update request"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    scopes: Optional[List[str]] = None
    ip_whitelist: Optional[List[str]] = None
    rate_limit_tier: Optional[RateLimitTier] = None

    @validator('scopes')
    def validate_scopes(cls, v):
        if v is None:
            return v
        valid_scopes = ['read', 'trade', 'admin', 'account:manage', 'strategy:execute', '*']
        for scope in v:
            if scope not in valid_scopes:
                raise ValueError(f"Invalid scope: {scope}")
        return v


class ApiKeyRotateResponse(BaseModel):
    """API key rotation response"""
    new_api_key_id: int
    api_key: str = Field(..., description="New full API key (save this!)")
    key_prefix: str
    name: str
    scopes: List[str]
    old_api_key_id: int

    class Config:
        from_attributes = True
```

---

## Task 6: Testing

### Unit Tests

File: `tests/unit/test_api_key_service.py` (NEW)

```python
"""
Unit tests for API Key Service
"""

import pytest
from datetime import datetime, timedelta
from app.services.api_key_service import ApiKeyService
from app.models import RateLimitTier


class TestApiKeyService:

    def test_generate_api_key(self, db, redis, test_user):
        """Test API key generation"""
        service = ApiKeyService(db, redis)

        api_key, full_key = service.generate_api_key(
            user_id=test_user.user_id,
            name="Test Key",
            scopes=["read", "trade"]
        )

        assert api_key.api_key_id is not None
        assert api_key.user_id == test_user.user_id
        assert api_key.name == "Test Key"
        assert api_key.scopes == ["read", "trade"]
        assert full_key.startswith("sb_")
        assert len(full_key.split("_")) == 3

    def test_verify_api_key_valid(self, db, redis, test_user):
        """Test API key verification with valid key"""
        service = ApiKeyService(db, redis)

        # Create key
        api_key, full_key = service.generate_api_key(
            user_id=test_user.user_id,
            name="Test Key",
            scopes=["read"]
        )

        # Parse key
        parts = full_key.split("_")
        key_prefix = f"sb_{parts[1]}"
        secret = parts[2]

        # Verify
        verified_key = service.verify_api_key(key_prefix, secret)
        assert verified_key is not None
        assert verified_key.api_key_id == api_key.api_key_id

    def test_verify_api_key_invalid_secret(self, db, redis, test_user):
        """Test API key verification with invalid secret"""
        service = ApiKeyService(db, redis)

        # Create key
        api_key, full_key = service.generate_api_key(
            user_id=test_user.user_id,
            name="Test Key",
            scopes=["read"]
        )

        # Parse key
        parts = full_key.split("_")
        key_prefix = f"sb_{parts[1]}"

        # Verify with wrong secret
        verified_key = service.verify_api_key(key_prefix, "wrong_secret")
        assert verified_key is None

    def test_verify_api_key_expired(self, db, redis, test_user):
        """Test API key verification with expired key"""
        service = ApiKeyService(db, redis)

        # Create key that expires in 1 day
        api_key, full_key = service.generate_api_key(
            user_id=test_user.user_id,
            name="Test Key",
            scopes=["read"],
            expires_in_days=1
        )

        # Manually expire the key
        api_key.expires_at = datetime.utcnow() - timedelta(days=1)
        db.commit()

        # Parse key
        parts = full_key.split("_")
        key_prefix = f"sb_{parts[1]}"
        secret = parts[2]

        # Verify
        verified_key = service.verify_api_key(key_prefix, secret)
        assert verified_key is None

    def test_verify_api_key_ip_whitelist_allowed(self, db, redis, test_user):
        """Test API key verification with IP whitelist (allowed IP)"""
        service = ApiKeyService(db, redis)

        # Create key with IP whitelist
        api_key, full_key = service.generate_api_key(
            user_id=test_user.user_id,
            name="Test Key",
            scopes=["read"],
            ip_whitelist=["1.2.3.4", "5.6.7.8"]
        )

        # Parse key
        parts = full_key.split("_")
        key_prefix = f"sb_{parts[1]}"
        secret = parts[2]

        # Verify with allowed IP
        verified_key = service.verify_api_key(key_prefix, secret, "1.2.3.4")
        assert verified_key is not None

    def test_verify_api_key_ip_whitelist_denied(self, db, redis, test_user):
        """Test API key verification with IP whitelist (denied IP)"""
        service = ApiKeyService(db, redis)

        # Create key with IP whitelist
        api_key, full_key = service.generate_api_key(
            user_id=test_user.user_id,
            name="Test Key",
            scopes=["read"],
            ip_whitelist=["1.2.3.4"]
        )

        # Parse key
        parts = full_key.split("_")
        key_prefix = f"sb_{parts[1]}"
        secret = parts[2]

        # Verify with denied IP
        verified_key = service.verify_api_key(key_prefix, secret, "9.9.9.9")
        assert verified_key is None

    def test_revoke_api_key(self, db, redis, test_user):
        """Test API key revocation"""
        service = ApiKeyService(db, redis)

        # Create key
        api_key, full_key = service.generate_api_key(
            user_id=test_user.user_id,
            name="Test Key",
            scopes=["read"]
        )

        # Revoke
        success = service.revoke_api_key(
            api_key.api_key_id,
            test_user.user_id,
            "Testing revocation"
        )
        assert success is True

        # Verify revoked key cannot be used
        parts = full_key.split("_")
        key_prefix = f"sb_{parts[1]}"
        secret = parts[2]
        verified_key = service.verify_api_key(key_prefix, secret)
        assert verified_key is None

    def test_rotate_api_key(self, db, redis, test_user):
        """Test API key rotation"""
        service = ApiKeyService(db, redis)

        # Create key
        old_key, old_full_key = service.generate_api_key(
            user_id=test_user.user_id,
            name="Test Key",
            scopes=["read", "trade"]
        )

        # Rotate
        new_key, new_full_key = service.rotate_api_key(
            old_key.api_key_id,
            test_user.user_id
        )

        assert new_key is not None
        assert new_full_key != old_full_key
        assert new_key.scopes == old_key.scopes

        # Old key should be revoked
        db.refresh(old_key)
        assert old_key.revoked_at is not None
```

### Integration Tests

File: `tests/integration/test_api_key_endpoints.py` (NEW)

```python
"""
Integration tests for API Key endpoints
"""

import pytest
from fastapi.testclient import TestClient


class TestApiKeyEndpoints:

    def test_create_api_key(self, client: TestClient, auth_headers):
        """Test POST /v1/api-keys"""
        response = client.post(
            "/v1/api-keys",
            headers=auth_headers,
            json={
                "name": "Test Key",
                "scopes": ["read", "trade"],
                "description": "For testing",
                "rate_limit_tier": "standard",
                "expires_in_days": 365
            }
        )

        assert response.status_code == 201
        data = response.json()
        assert "api_key" in data
        assert data["api_key"].startswith("sb_")
        assert data["name"] == "Test Key"
        assert data["scopes"] == ["read", "trade"]

    def test_list_api_keys(self, client: TestClient, auth_headers, test_api_key):
        """Test GET /v1/api-keys"""
        response = client.get("/v1/api-keys", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert "api_keys" in data
        assert len(data["api_keys"]) > 0

    def test_revoke_api_key(self, client: TestClient, auth_headers, test_api_key):
        """Test DELETE /v1/api-keys/{api_key_id}"""
        response = client.delete(
            f"/v1/api-keys/{test_api_key.api_key_id}",
            headers=auth_headers
        )

        assert response.status_code == 204

    def test_update_api_key(self, client: TestClient, auth_headers, test_api_key):
        """Test PUT /v1/api-keys/{api_key_id}"""
        response = client.put(
            f"/v1/api-keys/{test_api_key.api_key_id}",
            headers=auth_headers,
            json={
                "name": "Updated Name",
                "scopes": ["read"]
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Name"
        assert data["scopes"] == ["read"]

    def test_rotate_api_key(self, client: TestClient, auth_headers, test_api_key):
        """Test POST /v1/api-keys/{api_key_id}/rotate"""
        response = client.post(
            f"/v1/api-keys/{test_api_key.api_key_id}/rotate",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert "api_key" in data
        assert data["old_api_key_id"] == test_api_key.api_key_id

    def test_authenticate_with_api_key(self, client: TestClient, test_api_key_with_secret):
        """Test authentication with API key"""
        api_key, full_key = test_api_key_with_secret

        # Test with X-API-Key header
        response = client.get(
            "/v1/users/me",
            headers={"X-API-Key": full_key}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == api_key.user_id

    def test_authenticate_with_api_key_bearer(self, client: TestClient, test_api_key_with_secret):
        """Test authentication with API key in Bearer token"""
        api_key, full_key = test_api_key_with_secret

        # Test with Authorization: Bearer header
        response = client.get(
            "/v1/users/me",
            headers={"Authorization": f"Bearer {full_key}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == api_key.user_id

    def test_api_key_rate_limiting(self, client: TestClient, test_api_key_with_secret):
        """Test rate limiting for API keys"""
        api_key, full_key = test_api_key_with_secret

        # Make requests until rate limit hit
        # (This depends on rate_limit_tier)
        # For testing, use a low limit

        pass  # TODO: Implement based on rate limit tier
```

---

## Task 7: Documentation

Update: `README.md` - Add API key documentation section

Update: `app/main.py` - Add API key router to app

---

## Acceptance Criteria

- ✅ API keys can be generated via `POST /v1/api-keys`
- ✅ API keys can be listed via `GET /v1/api-keys`
- ✅ API keys can be revoked via `DELETE /v1/api-keys/{key_id}`
- ✅ API keys can be updated via `PUT /v1/api-keys/{key_id}`
- ✅ API keys can be rotated via `POST /v1/api-keys/{key_id}/rotate`
- ✅ SDK can authenticate with API keys via `X-API-Key` header
- ✅ SDK can authenticate with API keys via `Authorization: Bearer` header
- ✅ Scope enforcement works (e.g., "trade" scope required for trading)
- ✅ Rate limiting per API key works
- ✅ IP whitelisting works
- ✅ Expired keys are rejected
- ✅ Revoked keys are rejected
- ✅ All unit tests pass
- ✅ All integration tests pass
- ✅ SDK compatibility tested manually

---

## Git Workflow

```bash
# Create feature branch
git checkout -b feature/sprint-1-api-keys

# Commit after each task
git add .
git commit -m "feat(api-keys): add database schema and models"
git commit -m "feat(api-keys): add API key service"
git commit -m "feat(api-keys): add authentication middleware"
git commit -m "feat(api-keys): add API endpoints"
git commit -m "feat(api-keys): add schemas"
git commit -m "test(api-keys): add unit and integration tests"
git commit -m "docs(api-keys): update README with API key docs"

# Push to GitHub
git push origin feature/sprint-1-api-keys

# Create PR (optional)
# Or merge directly to main
```

---

## Testing Checklist

### Manual Testing

1. **Generate API key:**
   ```bash
   curl -X POST http://localhost:8001/v1/api-keys \
     -H "Authorization: Bearer <JWT_TOKEN>" \
     -H "Content-Type: application/json" \
     -d '{
       "name": "Test Key",
       "scopes": ["read", "trade"],
       "rate_limit_tier": "standard"
     }'
   ```

2. **Test authentication with API key:**
   ```bash
   curl http://localhost:8001/v1/users/me \
     -H "X-API-Key: sb_30d4d5ea_bbb52c64cc4eb2536fdd7b44861c93e4b30b50c6"
   ```

3. **Test SDK integration:**
   ```python
   from stocksblitz import TradingClient

   client = TradingClient(
       api_url="http://localhost:8081",
       api_key="sb_30d4d5ea_bbb52c64cc4eb2536fdd7b44861c93e4b30b50c6"
   )

   # Should work without login
   inst = client.Instrument("NIFTY50")
   print(inst['5m'].close)
   ```

4. **Test scope enforcement:**
   ```bash
   # Create key with only "read" scope
   # Try to place order → should fail with 403
   ```

5. **Test rate limiting:**
   ```bash
   # Create key with "free" tier (100/hour)
   # Make 101 requests → 101st should fail with 429
   ```

6. **Test IP whitelist:**
   ```bash
   # Create key with IP whitelist ["1.2.3.4"]
   # Request from different IP → should fail with 403
   ```

7. **Test expiration:**
   ```bash
   # Create key with expires_in_days=1
   # Manually set expires_at to past
   # Request → should fail with 401
   ```

8. **Test revocation:**
   ```bash
   # Create key → revoke → try to use → should fail with 401
   ```

9. **Test rotation:**
   ```bash
   # Create key → rotate → old key fails, new key works
   ```

### Automated Testing

```bash
# Run all tests
pytest tests/

# Run only API key tests
pytest tests/unit/test_api_key_service.py
pytest tests/integration/test_api_key_endpoints.py

# Run with coverage
pytest --cov=app/services/api_key_service --cov-report=html
```

---

## End of Sprint 1 Prompt
