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

    def get_api_key(self, api_key_id: int, user_id: int) -> Optional[ApiKey]:
        """Get a specific API key (must belong to user)"""
        return self.db.query(ApiKey).filter(
            ApiKey.api_key_id == api_key_id,
            ApiKey.user_id == user_id
        ).first()

    def revoke_api_key(
        self,
        api_key_id: int,
        revoked_by_user_id: int,
        reason: Optional[str] = None
    ) -> bool:
        """Revoke an API key"""
        api_key = self.db.query(ApiKey).filter(
            ApiKey.api_key_id == api_key_id
        ).first()

        if not api_key or api_key.revoked_at:
            return False

        # Verify user owns this key (security check)
        if api_key.user_id != revoked_by_user_id:
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
        user_id: int,
        name: Optional[str] = None,
        description: Optional[str] = None,
        scopes: Optional[List[str]] = None,
        ip_whitelist: Optional[List[str]] = None,
        rate_limit_tier: Optional[RateLimitTier] = None
    ) -> Optional[ApiKey]:
        """Update an API key"""
        api_key = self.db.query(ApiKey).filter(
            ApiKey.api_key_id == api_key_id,
            ApiKey.user_id == user_id
        ).first()

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
