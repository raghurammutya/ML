"""
Pydantic schemas for MFA (Multi-Factor Authentication) endpoints
"""

from typing import Optional, List
from pydantic import BaseModel, Field, validator


# MFA enrollment schemas

class MfaEnrollRequest(BaseModel):
    """
    MFA enrollment request

    Initiates TOTP enrollment for the user.
    """
    pass  # No parameters needed, uses current user from token


class MfaEnrollResponse(BaseModel):
    """
    MFA enrollment response

    Contains the TOTP secret and QR code for enrollment.
    """
    secret: str = Field(
        ...,
        description="Base32-encoded TOTP secret (display to user for manual entry)"
    )
    qr_code_data_uri: str = Field(
        ...,
        description="QR code as data URI (can be embedded in <img> tag)"
    )
    backup_codes: List[str] = Field(
        ...,
        description="One-time backup codes (10 codes)"
    )
    issuer: str = Field(
        default="StocksBlitz",
        description="Issuer name shown in authenticator app"
    )
    account_name: str = Field(
        ...,
        description="Account name (user's email)"
    )
    message: str = Field(
        default="Scan QR code with authenticator app (Google Authenticator, Authy, etc.)"
    )


class MfaConfirmRequest(BaseModel):
    """
    MFA confirmation request

    Confirms TOTP enrollment by verifying a code.
    """
    code: str = Field(
        ...,
        min_length=6,
        max_length=6,
        description="6-digit TOTP code from authenticator app"
    )

    @validator('code')
    def code_must_be_numeric(cls, v):
        if not v.isdigit():
            raise ValueError('Code must be numeric')
        return v


class MfaConfirmResponse(BaseModel):
    """MFA confirmation response"""
    user_id: int
    mfa_enabled: bool = True
    message: str = "MFA enabled successfully"
    backup_codes_remaining: int = Field(
        ...,
        description="Number of unused backup codes"
    )


class MfaDisableRequest(BaseModel):
    """
    MFA disable request

    Disables TOTP for the user.
    """
    password: str = Field(
        ...,
        description="User's password (required for security)"
    )
    code: Optional[str] = Field(
        None,
        min_length=6,
        max_length=6,
        description="6-digit TOTP code or backup code"
    )

    @validator('code')
    def code_must_be_numeric_or_none(cls, v):
        if v is not None and not v.isdigit():
            raise ValueError('Code must be numeric')
        return v


class MfaDisableResponse(BaseModel):
    """MFA disable response"""
    user_id: int
    mfa_enabled: bool = False
    message: str = "MFA disabled successfully"


# MFA status schemas

class MfaStatusResponse(BaseModel):
    """
    MFA status response

    Returns current MFA configuration status.
    """
    user_id: int
    mfa_enabled: bool
    totp_configured: bool
    backup_codes_remaining: int
    enrolled_at: Optional[str] = Field(
        None,
        description="When MFA was first enabled"
    )


# Backup code schemas

class BackupCodesRegenerateRequest(BaseModel):
    """
    Backup codes regeneration request

    Generates new set of backup codes (invalidates old ones).
    """
    password: str = Field(
        ...,
        description="User's password (required for security)"
    )
    code: str = Field(
        ...,
        min_length=6,
        max_length=6,
        description="6-digit TOTP code"
    )

    @validator('code')
    def code_must_be_numeric(cls, v):
        if not v.isdigit():
            raise ValueError('Code must be numeric')
        return v


class BackupCodesRegenerateResponse(BaseModel):
    """Backup codes regeneration response"""
    user_id: int
    backup_codes: List[str] = Field(
        ...,
        description="New one-time backup codes (10 codes)"
    )
    message: str = "Backup codes regenerated successfully"
    warning: str = "Store these codes securely. Previous backup codes are now invalid."


# MFA verification schemas (used in login flow)

class MfaVerifyResponse(BaseModel):
    """
    MFA verification response

    Extended response after successful MFA verification.
    """
    verified: bool
    method_used: str = Field(
        ...,
        description="Method used: 'totp' or 'backup_code'"
    )
    backup_code_used: bool = Field(
        default=False,
        description="Whether a backup code was used"
    )
    backup_codes_remaining: Optional[int] = Field(
        None,
        description="Remaining backup codes (if backup code was used)"
    )
