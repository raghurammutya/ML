"""
OAuth Service

Handles OAuth 2.0 authentication flow with external providers (Google).
"""

import secrets
import httpx
from typing import Optional, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session
from urllib.parse import urlencode

from app.core.config import settings
from app.core.redis_client import RedisClient
from app.models import User, UserStatus, AuthProvider
from app.services.jwt_service import jwt_service
from app.services.event_service import EventService
from app.schemas.oauth import OAuthUserInfo


class OAuthService:
    """Service for OAuth authentication"""

    # Google OAuth endpoints
    GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
    GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

    def __init__(self, db: Session, redis: RedisClient):
        self.db = db
        self.redis = redis
        self.event_service = EventService(redis)

    def initiate_oauth_flow(
        self,
        provider: str = "google",
        redirect_uri: Optional[str] = None
    ) -> Dict[str, str]:
        """
        Initiate OAuth flow

        Generates authorization URL with state token for CSRF protection.

        Args:
            provider: OAuth provider (currently only 'google')
            redirect_uri: Custom redirect URI (must be pre-registered)

        Returns:
            Dictionary with authorization_url and state

        Raises:
            ValueError: If provider not supported or not configured
        """
        if provider != "google":
            raise ValueError(f"OAuth provider '{provider}' not supported")

        if not settings.FEATURE_GOOGLE_OAUTH:
            raise ValueError("Google OAuth is not enabled")

        if not settings.GOOGLE_OAUTH_CLIENT_ID or not settings.GOOGLE_OAUTH_CLIENT_SECRET:
            raise ValueError("Google OAuth is not configured")

        # Generate CSRF protection state token
        state = secrets.token_urlsafe(32)

        # Store state in Redis with 10 minute expiry
        state_key = f"oauth:state:{state}"
        self.redis.client.setex(
            state_key,
            600,  # 10 minutes
            provider
        )

        # Use configured redirect URI if not provided
        redirect_uri = redirect_uri or settings.GOOGLE_OAUTH_REDIRECT_URI

        # Build authorization URL
        params = {
            "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "access_type": "offline",
            "prompt": "consent"
        }

        authorization_url = f"{self.GOOGLE_AUTH_URL}?{urlencode(params)}"

        return {
            "authorization_url": authorization_url,
            "state": state,
            "provider": provider
        }

    def handle_oauth_callback(
        self,
        code: str,
        state: str,
        device_fingerprint: str,
        ip: str,
        persist_session: bool = True
    ) -> Dict[str, Any]:
        """
        Handle OAuth callback

        Validates state, exchanges code for tokens, fetches user info,
        creates/updates user, and generates JWT tokens.

        Args:
            code: Authorization code from OAuth provider
            state: CSRF protection state token
            device_fingerprint: Device fingerprint
            ip: Client IP address
            persist_session: Whether to create long-lived session

        Returns:
            Dictionary with access_token, refresh_token, user info

        Raises:
            ValueError: If state invalid, code exchange fails, or user creation fails
        """
        # Validate state (CSRF protection)
        state_key = f"oauth:state:{state}"
        stored_provider = self.redis.client.get(state_key)

        if not stored_provider:
            raise ValueError("Invalid or expired OAuth state token")

        provider = stored_provider.decode() if isinstance(stored_provider, bytes) else stored_provider

        # Delete state (single use)
        self.redis.client.delete(state_key)

        if provider != "google":
            raise ValueError(f"Unsupported OAuth provider: {provider}")

        # Exchange code for access token
        user_info = self._exchange_code_for_user_info(code)

        # Create or update user
        user, is_new_user = self._get_or_create_oauth_user(user_info)

        # Generate session and tokens
        session_id = secrets.token_urlsafe(32)
        access_token = jwt_service.generate_access_token(
            user_id=user.user_id,
            session_id=session_id,
            email=user.email,
            roles=[role.role_name for role in user.roles]
        )

        refresh_token = None
        if persist_session:
            refresh_token = jwt_service.generate_refresh_token(
                user_id=user.user_id,
                session_id=session_id
            )

            # Store session in Redis
            session_data = {
                "user_id": str(user.user_id),
                "session_id": session_id,
                "device_fingerprint": device_fingerprint,
                "ip": ip,
                "created_at": datetime.utcnow().isoformat(),
                "last_active_at": datetime.utcnow().isoformat(),
                "auth_method": f"oauth_{provider}"
            }

            session_key = f"session:{session_id}"
            self.redis.client.hmset(session_key, session_data)
            self.redis.client.expire(session_key, settings.REDIS_SESSION_TTL_DAYS * 86400)

            # Store refresh token with session mapping
            refresh_token_key = f"refresh_token:{refresh_token}"
            self.redis.client.setex(
                refresh_token_key,
                settings.JWT_REFRESH_TOKEN_TTL_DAYS * 86400,
                session_id
            )

        # Publish login event
        self.event_service.publish_user_login(
            user_id=user.user_id,
            session_id=session_id,
            auth_method=f"oauth_{provider}",
            ip=ip,
            device_fingerprint=device_fingerprint
        )

        if is_new_user:
            # Publish user registered event
            self.event_service.publish_event(
                event_type="user.registered",
                subject=f"user:{user.user_id}",
                data={
                    "user_id": user.user_id,
                    "email": user.email,
                    "auth_provider": provider,
                    "registration_method": f"oauth_{provider}"
                },
                priority="high"
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
                "status": user.status.value,
                "roles": [role.role_name for role in user.roles]
            },
            "is_new_user": is_new_user
        }

    def _exchange_code_for_user_info(self, code: str) -> OAuthUserInfo:
        """
        Exchange authorization code for access token and fetch user info

        Args:
            code: Authorization code

        Returns:
            OAuthUserInfo with user data from Google

        Raises:
            ValueError: If token exchange or user info fetch fails
        """
        try:
            # Exchange code for access token
            token_data = {
                "code": code,
                "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
                "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
                "redirect_uri": settings.GOOGLE_OAUTH_REDIRECT_URI,
                "grant_type": "authorization_code"
            }

            with httpx.Client() as client:
                # Get access token
                token_response = client.post(self.GOOGLE_TOKEN_URL, data=token_data)
                token_response.raise_for_status()
                tokens = token_response.json()

                access_token = tokens.get("access_token")
                if not access_token:
                    raise ValueError("No access token in response")

                # Fetch user info
                headers = {"Authorization": f"Bearer {access_token}"}
                userinfo_response = client.get(self.GOOGLE_USERINFO_URL, headers=headers)
                userinfo_response.raise_for_status()
                userinfo = userinfo_response.json()

            # Parse user info
            return OAuthUserInfo(
                email=userinfo.get("email"),
                name=userinfo.get("name"),
                given_name=userinfo.get("given_name"),
                family_name=userinfo.get("family_name"),
                picture=userinfo.get("picture"),
                email_verified=userinfo.get("email_verified", False),
                provider_user_id=userinfo.get("id"),
                provider="google"
            )

        except httpx.HTTPStatusError as e:
            raise ValueError(f"OAuth provider error: {e.response.text}")
        except Exception as e:
            raise ValueError(f"Failed to exchange OAuth code: {str(e)}")

    def _get_or_create_oauth_user(
        self,
        user_info: OAuthUserInfo
    ) -> tuple[User, bool]:
        """
        Get existing user or create new user from OAuth info

        Args:
            user_info: User info from OAuth provider

        Returns:
            Tuple of (User, is_new_user)

        Raises:
            ValueError: If user creation fails
        """
        # Check if user exists with this email
        user = self.db.query(User).filter(User.email == user_info.email).first()

        is_new_user = False

        if user:
            # Update existing user's OAuth info if needed
            # Check if this OAuth provider is already linked
            existing_provider = None
            for provider in user.auth_providers:
                if provider.provider == user_info.provider:
                    existing_provider = provider
                    break

            if existing_provider:
                # Update provider info
                existing_provider.provider_user_id = user_info.provider_user_id
                existing_provider.updated_at = datetime.utcnow()
            else:
                # Add new OAuth provider
                new_provider = AuthProvider(
                    user_id=user.user_id,
                    provider=user_info.provider,
                    provider_user_id=user_info.provider_user_id,
                    email=user_info.email,
                    email_verified=user_info.email_verified
                )
                self.db.add(new_provider)

            # Update user info if needed
            if user_info.picture and not user.profile_picture_url:
                user.profile_picture_url = user_info.picture

            user.updated_at = datetime.utcnow()

        else:
            # Create new user
            user = User(
                email=user_info.email,
                name=user_info.name,
                password_hash="",  # No password for OAuth users
                status=UserStatus.ACTIVE if user_info.email_verified else UserStatus.PENDING_VERIFICATION,
                email_verified=user_info.email_verified,
                profile_picture_url=user_info.picture,
                timezone="UTC",
                locale="en-US"
            )

            self.db.add(user)
            self.db.flush()  # Get user_id

            # Add OAuth provider
            auth_provider = AuthProvider(
                user_id=user.user_id,
                provider=user_info.provider,
                provider_user_id=user_info.provider_user_id,
                email=user_info.email,
                email_verified=user_info.email_verified
            )
            self.db.add(auth_provider)

            is_new_user = True

        self.db.commit()
        self.db.refresh(user)

        return user, is_new_user
