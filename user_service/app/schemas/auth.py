"""
Pydantic schemas for authentication endpoints
"""

from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field, validator


# Request schemas

class RegisterRequest(BaseModel):
    """User registration request"""
    email: EmailStr
    password: str = Field(..., min_length=12)
    name: str = Field(..., min_length=1, max_length=255)
    phone: Optional[str] = Field(None, max_length=20)
    timezone: str = Field(default="UTC", max_length=50)
    locale: str = Field(default="en-US", max_length=10)


class LoginRequest(BaseModel):
    """User login request"""
    email: EmailStr
    password: str
    persist_session: bool = Field(default=False)
    device_fingerprint: Optional[str] = Field(None, max_length=255)


class MfaVerifyRequest(BaseModel):
    """MFA verification request"""
    session_token: str
    code: str = Field(..., min_length=6, max_length=6)

    @validator('code')
    def code_must_be_numeric(cls, v):
        if not v.isdigit():
            raise ValueError('Code must be numeric')
        return v


class LogoutRequest(BaseModel):
    """Logout request"""
    all_devices: bool = Field(default=False)


class PasswordResetRequest(BaseModel):
    """Password reset request"""
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    """Password reset confirmation"""
    token: str
    new_password: str = Field(..., min_length=12)


# Response schemas

class UserResponse(BaseModel):
    """User information in response"""
    user_id: int
    email: str
    name: str
    roles: List[str]
    mfa_enabled: bool

    class Config:
        from_attributes = True


class LoginResponse(BaseModel):
    """Login response with tokens"""
    access_token: str
    token_type: str = "Bearer"
    expires_in: int
    user: UserResponse
    refresh_token: Optional[str] = None


class MfaRequiredResponse(BaseModel):
    """MFA required response"""
    status: str = "mfa_required"
    session_token: str
    methods: List[str]
    message: str = "MFA verification required"


class TokenRefreshResponse(BaseModel):
    """Token refresh response"""
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int


class RegisterResponse(BaseModel):
    """Registration response"""
    user_id: int
    email: str
    status: str
    verification_email_sent: bool
    created_at: str

    class Config:
        from_attributes = True


class LogoutResponse(BaseModel):
    """Logout response"""
    message: str
    sessions_revoked: int


class SessionInfo(BaseModel):
    """Session information"""
    session_id: str
    device_fingerprint: str
    ip: str
    country: Optional[str] = None
    created_at: str
    last_active_at: str
    current: bool


class SessionsResponse(BaseModel):
    """List of user sessions"""
    sessions: List[SessionInfo]
    total: int


class PasswordResetResponse(BaseModel):
    """Password reset request response"""
    message: str = "If this email is registered, you will receive a password reset link."


class PasswordResetConfirmResponse(BaseModel):
    """Password reset confirmation response"""
    message: str = "Password reset successfully"
    sessions_revoked: int
