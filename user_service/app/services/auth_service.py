"""
Authentication Service - Login, registration, session management
"""

import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.redis_client import RedisClient
from app.models import User, UserStatus, Role, UserRole, UserPreference, AuthEvent
from app.utils.security import (
    hash_password,
    verify_password,
    validate_password_strength,
    generate_device_fingerprint
)
from app.services.jwt_service import jwt_service
from app.services.event_service import EventService


class AuthService:
    """Service for authentication operations"""

    def __init__(self, db: Session, redis: RedisClient):
        self.db = db
        self.redis = redis
        self.event_service = EventService(redis)

    def register_user(
        self,
        email: str,
        password: str,
        name: str,
        phone: Optional[str] = None,
        timezone: str = "UTC",
        locale: str = "en-US"
    ) -> Tuple[User, Dict[str, Any]]:
        """
        Register a new user

        Args:
            email: User email
            password: Plain text password
            name: User's full name
            phone: Optional phone number
            timezone: User timezone
            locale: User locale

        Returns:
            Tuple of (User, validation_result)

        Raises:
            ValueError: If validation fails
        """
        # Check if email already exists
        existing_user = self.db.query(User).filter(User.email == email).first()
        if existing_user:
            raise ValueError("Email already registered")

        # Validate password strength
        password_validation = validate_password_strength(password, [email, name])
        if not password_validation['valid']:
            raise ValueError(f"Password validation failed: {', '.join(password_validation['errors'])}")

        # Hash password
        password_hash = hash_password(password)

        # Create user
        user = User(
            email=email,
            password_hash=password_hash,
            name=name,
            phone=phone,
            timezone=timezone,
            locale=locale,
            status=UserStatus.PENDING_VERIFICATION
        )

        self.db.add(user)
        self.db.flush()  # Get user_id

        # Assign default 'user' role
        user_role_record = self.db.query(Role).filter(Role.name == "user").first()
        if user_role_record:
            user_role = UserRole(
                user_id=user.user_id,
                role_id=user_role_record.role_id
            )
            self.db.add(user_role)

        # Create default preferences
        preferences = UserPreference(
            user_id=user.user_id,
            preferences={}
        )
        self.db.add(preferences)

        self.db.commit()
        self.db.refresh(user)

        # Log registration event
        self._log_auth_event(
            user_id=user.user_id,
            event_type="user.registered",
            metadata={"email": email, "name": name}
        )

        # Publish user.registered event
        roles = [ur.role.name for ur in user.roles] if user.roles else ["user"]
        self.event_service.publish_user_registered(
            user_id=user.user_id,
            email=user.email,
            name=user.name,
            status=user.status.value,
            roles=roles
        )

        return user, password_validation

    def login(
        self,
        email: str,
        password: str,
        device_fingerprint: Optional[str] = None,
        ip: Optional[str] = None,
        persist_session: bool = False
    ) -> Optional[Dict[str, Any]]:
        """
        Authenticate user with email/password

        Args:
            email: User email
            password: Plain text password
            device_fingerprint: Device fingerprint
            ip: User IP address
            persist_session: Whether to create long-lived session

        Returns:
            Dict with user, tokens, and session info, or None if authentication fails
        """
        # Check rate limit
        rate_limit_key = f"ratelimit:login:{email}"
        allowed, remaining = self.redis.check_rate_limit(
            rate_limit_key,
            settings.RATELIMIT_LOGIN_ATTEMPTS,
            settings.RATELIMIT_LOGIN_WINDOW_MINUTES * 60
        )

        if not allowed:
            self._log_auth_event(
                user_id=None,
                event_type="login.rate_limited",
                ip=ip,
                metadata={"email": email}
            )
            raise ValueError("Rate limit exceeded. Please try again later.")

        # Find user
        user = self.db.query(User).filter(User.email == email).first()

        if not user or not user.password_hash:
            # Log failed attempt
            self._log_auth_event(
                user_id=None,
                event_type="login.failed",
                ip=ip,
                metadata={"email": email, "reason": "invalid_credentials"}
            )
            return None

        # Verify password
        if not verify_password(password, user.password_hash):
            self._log_auth_event(
                user_id=user.user_id,
                event_type="login.failed",
                ip=ip,
                metadata={"reason": "invalid_password"}
            )
            return None

        # Check user status
        if user.status == UserStatus.DEACTIVATED:
            raise ValueError("Account has been deactivated")
        elif user.status == UserStatus.SUSPENDED:
            raise ValueError("Account is suspended")

        # Check if MFA is enabled
        if user.mfa_enabled:
            # Create temporary session for MFA verification
            temp_session_token = str(uuid.uuid4())
            self.redis.set(
                f"mfa_pending:{temp_session_token}",
                str(user.user_id),
                ttl=600  # 10 minutes
            )

            return {
                "status": "mfa_required",
                "session_token": temp_session_token,
                "methods": ["totp"]
            }

        # Create full session
        return self._create_session(user, device_fingerprint, ip, persist_session)

    def verify_mfa_and_login(
        self,
        session_token: str,
        totp_code: str,
        device_fingerprint: Optional[str] = None,
        ip: Optional[str] = None,
        persist_session: bool = False
    ) -> Optional[Dict[str, Any]]:
        """
        Verify MFA code and complete login

        Args:
            session_token: Temporary session token from login
            totp_code: TOTP code
            device_fingerprint: Device fingerprint
            ip: User IP address
            persist_session: Whether to create long-lived session

        Returns:
            Dict with user, tokens, and session info
        """
        # Get pending user_id
        user_id_str = self.redis.get(f"mfa_pending:{session_token}")
        if not user_id_str:
            raise ValueError("Invalid or expired session token")

        user_id = int(user_id_str)
        user = self.db.query(User).filter(User.user_id == user_id).first()

        if not user:
            raise ValueError("User not found")

        # Verify TOTP code using MFA service
        from app.services.mfa_service import MfaService
        mfa_service = MfaService(self.db, self.redis)

        try:
            verified, method = mfa_service.verify_totp(user, totp_code, allow_backup_codes=True)
            if not verified:
                self._log_auth_event(
                    user_id=user.user_id,
                    event_type="mfa.failed",
                    ip=ip,
                    metadata={"reason": "invalid_code"}
                )
                raise ValueError("Invalid MFA code")
        except ValueError as e:
            self._log_auth_event(
                user_id=user.user_id,
                event_type="mfa.failed",
                ip=ip,
                metadata={"reason": str(e)}
            )
            raise

        # Delete temporary session
        self.redis.delete(f"mfa_pending:{session_token}")

        # Create full session with MFA verified
        return self._create_session(user, device_fingerprint, ip, persist_session, mfa_verified=True)

    def _create_session(
        self,
        user: User,
        device_fingerprint: Optional[str],
        ip: Optional[str],
        persist_session: bool,
        mfa_verified: bool = False
    ) -> Dict[str, Any]:
        """Create user session and generate tokens"""
        # Generate session ID
        session_id = f"sid_{uuid.uuid4().hex}"

        # Get user roles
        roles = [ur.role.name for ur in user.roles]

        # Get trading account IDs
        trading_account_ids = [ta.trading_account_id for ta in user.trading_accounts if ta.status == "active"]

        # Store session in Redis
        session_ttl = (
            settings.REDIS_SESSION_TTL_DAYS * 86400
            if persist_session
            else settings.REDIS_SESSION_INACTIVITY_DAYS * 86400
        )

        session_data = {
            "user_id": str(user.user_id),
            "device_fingerprint": device_fingerprint or "",
            "ip": ip or "",
            "created_at": datetime.utcnow().isoformat(),
            "last_active_at": datetime.utcnow().isoformat(),
            "mfa_verified": str(mfa_verified)
        }

        self.redis.set_session(session_id, session_data, session_ttl)

        # Generate access token
        access_token = jwt_service.generate_access_token(
            user_id=user.user_id,
            session_id=session_id,
            roles=roles,
            trading_account_ids=trading_account_ids,
            mfa_verified=mfa_verified
        )

        # Generate refresh token (if persist_session)
        refresh_token = None
        refresh_jti = None
        if persist_session:
            refresh_token, refresh_jti = jwt_service.generate_refresh_token(
                user_id=user.user_id,
                session_id=session_id
            )

            # Store refresh token family
            refresh_ttl = settings.JWT_REFRESH_TOKEN_TTL_DAYS * 86400
            refresh_data = {
                "user_id": str(user.user_id),
                "sid": session_id,
                "parent_jti": "",
                "rotated_to": "",
                "issued_at": datetime.utcnow().isoformat()
            }
            self.redis.set_refresh_token(refresh_jti, refresh_data, refresh_ttl)

        # Update user last login
        user.last_login_at = datetime.utcnow()
        if user.status == UserStatus.PENDING_VERIFICATION:
            user.status = UserStatus.ACTIVE  # Auto-activate on first login

        self.db.commit()

        # Log successful login
        self._log_auth_event(
            user_id=user.user_id,
            event_type="login.success",
            session_id=session_id,
            ip=ip,
            device_fingerprint=device_fingerprint,
            metadata={"mfa_verified": mfa_verified}
        )

        # Publish login.success event
        self.event_service.publish_login_success(
            user_id=user.user_id,
            session_id=session_id,
            mfa_verified=mfa_verified,
            device_fingerprint=device_fingerprint,
            ip=ip
        )

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "Bearer",
            "expires_in": settings.JWT_ACCESS_TOKEN_TTL_MINUTES * 60,
            "user": {
                "user_id": user.user_id,
                "email": user.email,
                "name": user.name,
                "roles": roles,
                "mfa_enabled": user.mfa_enabled
            },
            "session_id": session_id
        }

    def refresh_access_token(self, refresh_token: str) -> Dict[str, Any]:
        """
        Refresh access token using refresh token

        Args:
            refresh_token: Refresh token JWT

        Returns:
            Dict with new access token and rotated refresh token
        """
        # Validate refresh token
        try:
            payload = jwt_service.validate_token(refresh_token, token_type="refresh")
        except Exception as e:
            raise ValueError(f"Invalid refresh token: {str(e)}")

        jti = payload.get("jti")
        user_id_str = payload["sub"].split(":")[1]
        user_id = int(user_id_str)
        session_id = payload.get("sid")

        # Check if token family exists and hasn't been rotated
        token_data = self.redis.get_refresh_token(jti)
        if not token_data:
            raise ValueError("Refresh token not found or expired")

        # Reuse detection
        if token_data.get("rotated_to"):
            # This token was already used! Security violation
            self._log_auth_event(
                user_id=user_id,
                event_type="refresh.reuse_detected",
                session_id=session_id,
                metadata={"jti": jti},
                risk_score="high"
            )

            # Revoke entire session
            self.redis.delete_session(session_id)
            self.redis.delete_refresh_token(jti)

            raise ValueError("Refresh token reuse detected. Session revoked for security.")

        # Get user
        user = self.db.query(User).filter(User.user_id == user_id).first()
        if not user:
            raise ValueError("User not found")

        # Get user roles and trading accounts
        roles = [ur.role.name for ur in user.roles]
        trading_account_ids = [ta.trading_account_id for ta in user.trading_accounts if ta.status == "active"]

        # Generate new access token
        access_token = jwt_service.generate_access_token(
            user_id=user.user_id,
            session_id=session_id,
            roles=roles,
            trading_account_ids=trading_account_ids,
            mfa_verified=token_data.get("mfa_verified") == "True"
        )

        # Rotate refresh token
        new_refresh_token, new_jti = jwt_service.generate_refresh_token(
            user_id=user.user_id,
            session_id=session_id
        )

        # Mark old token as rotated
        self.redis.mark_refresh_token_rotated(jti, new_jti)

        # Store new refresh token family
        refresh_ttl = settings.JWT_REFRESH_TOKEN_TTL_DAYS * 86400
        new_refresh_data = {
            "user_id": str(user.user_id),
            "sid": session_id,
            "parent_jti": jti,
            "rotated_to": "",
            "issued_at": datetime.utcnow().isoformat()
        }
        self.redis.set_refresh_token(new_jti, new_refresh_data, refresh_ttl)

        # Update session last_active
        session_data = self.redis.get_session(session_id)
        if session_data:
            session_data["last_active_at"] = datetime.utcnow().isoformat()
            session_ttl = self.redis.ttl(f"session:{session_id}")
            self.redis.set_session(session_id, session_data, session_ttl)

        # Log refresh
        self._log_auth_event(
            user_id=user.user_id,
            event_type="token.refreshed",
            session_id=session_id,
            metadata={"old_jti": jti, "new_jti": new_jti}
        )

        return {
            "access_token": access_token,
            "refresh_token": new_refresh_token,
            "token_type": "Bearer",
            "expires_in": settings.JWT_ACCESS_TOKEN_TTL_MINUTES * 60
        }

    def logout(self, session_id: str, user_id: int, all_devices: bool = False) -> int:
        """
        Logout user and invalidate session(s)

        Args:
            session_id: Current session ID
            user_id: User ID
            all_devices: Whether to logout from all devices

        Returns:
            Number of sessions revoked
        """
        sessions_revoked = 0

        if all_devices:
            # TODO: Implement pattern matching to find all sessions for user
            # For now, just revoke current session
            pass

        # Revoke current session
        self.redis.delete_session(session_id)
        sessions_revoked += 1

        # Log logout
        self._log_auth_event(
            user_id=user_id,
            event_type="logout",
            session_id=session_id,
            metadata={"all_devices": all_devices}
        )

        # Publish session.revoked event
        self.event_service.publish_session_revoked(
            user_id=user_id,
            session_id=session_id,
            reason="logout"
        )

        return sessions_revoked

    def _log_auth_event(
        self,
        event_type: str,
        user_id: Optional[int] = None,
        session_id: Optional[str] = None,
        ip: Optional[str] = None,
        device_fingerprint: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        risk_score: Optional[str] = None
    ) -> None:
        """Log authentication event to database"""
        event = AuthEvent(
            user_id=user_id,
            event_type=event_type,
            ip=ip,
            session_id=session_id,
            device_fingerprint=device_fingerprint,
            metadata=metadata or {},
            risk_score=risk_score
        )

        self.db.add(event)
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
