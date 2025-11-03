"""
OAuth schemas

Google OAuth 2.0 authentication flow.
"""

from typing import Optional
from pydantic import BaseModel, Field, HttpUrl


class OAuthInitiateRequest(BaseModel):
    """
    Initiate OAuth flow

    Returns authorization URL for user to visit.
    """
    provider: str = Field(
        default="google",
        description="OAuth provider (currently only 'google' supported)"
    )
    redirect_uri: Optional[str] = Field(
        default=None,
        description="Custom redirect URI (must be pre-registered)"
    )


class OAuthInitiateResponse(BaseModel):
    """OAuth initiation response"""
    authorization_url: str = Field(
        ...,
        description="URL to redirect user to for OAuth consent"
    )
    state: str = Field(
        ...,
        description="CSRF protection state token (verify on callback)"
    )
    provider: str = Field(
        default="google",
        description="OAuth provider"
    )


class OAuthCallbackRequest(BaseModel):
    """
    OAuth callback request

    Receives authorization code from OAuth provider.
    """
    code: str = Field(
        ...,
        min_length=10,
        max_length=1024,
        description="Authorization code from OAuth provider"
    )
    state: str = Field(
        ...,
        min_length=10,
        max_length=128,
        description="CSRF protection state token (must match initiate)"
    )
    persist_session: bool = Field(
        default=True,
        description="Whether to create long-lived session (default: true)"
    )


class OAuthCallbackResponse(BaseModel):
    """
    OAuth callback response

    Returns JWT tokens and user info after successful OAuth login.
    """
    access_token: str = Field(
        ...,
        description="JWT access token (15 min)"
    )
    refresh_token: Optional[str] = Field(
        default=None,
        description="Refresh token (only if persist_session=true, set in HTTP-only cookie)"
    )
    token_type: str = Field(
        default="Bearer",
        description="Token type"
    )
    expires_in: int = Field(
        ...,
        description="Token expiration in seconds"
    )
    user: dict = Field(
        ...,
        description="User information"
    )
    is_new_user: bool = Field(
        default=False,
        description="Whether this is a newly created user account"
    )


class OAuthUserInfo(BaseModel):
    """
    User information from OAuth provider

    Internal schema for processing OAuth user data.
    """
    email: str
    name: str
    given_name: Optional[str] = None
    family_name: Optional[str] = None
    picture: Optional[str] = None
    email_verified: bool = False
    provider_user_id: str
    provider: str = "google"
