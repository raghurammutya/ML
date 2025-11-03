"""
Password Reset schemas

Secure password reset flow with email verification.
"""

from pydantic import BaseModel, Field, validator, EmailStr


class PasswordResetRequestRequest(BaseModel):
    """
    Request password reset

    Sends password reset email with secure token.
    """
    email: EmailStr = Field(
        ...,
        description="Email address of account to reset"
    )


class PasswordResetRequestResponse(BaseModel):
    """Password reset request response"""
    email: str
    message: str = "If this email exists, a password reset link has been sent"
    expires_in_minutes: int = Field(
        default=30,
        description="Token expiry time in minutes"
    )


class PasswordResetRequest(BaseModel):
    """
    Complete password reset with token

    Uses token from email to reset password.
    """
    token: str = Field(
        ...,
        min_length=32,
        max_length=255,
        description="Reset token from email"
    )
    new_password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="New password"
    )

    @validator('token')
    def trim_token(cls, v):
        return v.strip()


class PasswordResetResponse(BaseModel):
    """Password reset completion response"""
    user_id: int
    message: str = "Password reset successfully"
