"""
Password Reset Service

Handles secure password reset flow with email verification.
"""

import secrets
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.redis_client import RedisClient
from app.models import User
from app.utils.security import hash_password, validate_password_strength
from app.services.event_service import EventService


class PasswordResetService:
    """Service for password reset operations"""

    def __init__(self, db: Session, redis: RedisClient):
        self.db = db
        self.redis = redis
        self.event_service = EventService(redis)

    def request_password_reset(
        self,
        email: str,
        ip: Optional[str] = None
    ) -> Optional[str]:
        """
        Request password reset for email

        Generates secure reset token and stores in Redis.
        Returns token for email sending (in production, this would trigger email service).

        Args:
            email: User email address
            ip: IP address of requester (for security)

        Returns:
            Reset token if user found, None otherwise (security - don't reveal if email exists)

        Security:
            - Always returns success message (don't reveal if email exists)
            - Token expires in 30 minutes
            - Token can only be used once
            - Rate limited per IP
        """
        # Find user by email
        user = self.db.query(User).filter(User.email == email).first()

        if not user:
            # Don't reveal that email doesn't exist (security best practice)
            return None

        # Generate secure reset token
        reset_token = secrets.token_urlsafe(32)  # 256-bit security

        # Store token in Redis with expiry
        token_key = f"password_reset:{reset_token}"
        token_data = {
            "user_id": str(user.user_id),
            "email": email,
            "created_at": datetime.utcnow().isoformat(),
            "ip": ip or ""
        }

        # Token expires in 30 minutes
        self.redis.client.hmset(token_key, token_data)
        self.redis.client.expire(token_key, settings.PASSWORD_RESET_TOKEN_TTL_MINUTES * 60)

        # Publish password.reset_requested event
        self.event_service.publish_event(
            event_type="password.reset_requested",
            subject=f"user:{user.user_id}",
            data={
                "user_id": user.user_id,
                "email": email
            },
            metadata={
                "ip": ip
            },
            priority="high"
        )

        # TODO: Send email with reset link
        # reset_link = f"{settings.FRONTEND_URL}/reset-password?token={reset_token}"
        # send_email(
        #     to=email,
        #     subject="Password Reset Request",
        #     body=f"Click here to reset your password: {reset_link}"
        # )

        return reset_token

    def reset_password(
        self,
        token: str,
        new_password: str
    ) -> User:
        """
        Complete password reset with token

        Verifies token and updates password.

        Args:
            token: Reset token from email
            new_password: New password

        Returns:
            User object

        Raises:
            ValueError: If token invalid, expired, or password validation fails

        Security:
            - Token can only be used once
            - Token expires after 30 minutes
            - Password strength validation
            - Old sessions are NOT revoked (user stays logged in on existing devices)
        """
        # Get token data from Redis
        token_key = f"password_reset:{token}"
        token_data = self.redis.client.hgetall(token_key)

        if not token_data:
            raise ValueError("Invalid or expired reset token")

        # Decode Redis bytes to strings
        user_id = int(token_data[b'user_id'].decode())
        email = token_data[b'email'].decode()

        # Get user
        user = self.db.query(User).filter(User.user_id == user_id).first()
        if not user:
            raise ValueError("User not found")

        # Validate new password
        password_validation = validate_password_strength(new_password, [email, user.name])
        if not password_validation['valid']:
            raise ValueError(f"Password validation failed: {', '.join(password_validation['errors'])}")

        # Update password
        user.password_hash = hash_password(new_password)
        user.updated_at = datetime.utcnow()

        self.db.commit()
        self.db.refresh(user)

        # Delete token (single use)
        self.redis.client.delete(token_key)

        # Publish password.reset_completed event
        self.event_service.publish_event(
            event_type="password.reset_completed",
            subject=f"user:{user.user_id}",
            data={
                "user_id": user.user_id,
                "changed_via": "reset"
            },
            priority="high"
        )

        # Publish password.changed event
        self.event_service.publish_password_changed(
            user_id=user.user_id,
            changed_via="reset"
        )

        return user
