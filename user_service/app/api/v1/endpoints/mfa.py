"""
MFA (Multi-Factor Authentication) endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.redis_client import get_redis, RedisClient
from app.api.dependencies import get_current_active_user
from app.models import User
from app.services.mfa_service import MfaService
from app.schemas.mfa import (
    MfaEnrollRequest,
    MfaEnrollResponse,
    MfaConfirmRequest,
    MfaConfirmResponse,
    MfaDisableRequest,
    MfaDisableResponse,
    MfaStatusResponse,
    BackupCodesRegenerateRequest,
    BackupCodesRegenerateResponse
)


router = APIRouter()


def get_mfa_service(
    db: Session = Depends(get_db),
    redis: RedisClient = Depends(get_redis)
) -> MfaService:
    """
    Get MFA service instance

    Args:
        db: Database session
        redis: Redis client

    Returns:
        MfaService instance
    """
    return MfaService(db, redis)


@router.post("/totp/enroll", response_model=MfaEnrollResponse)
async def enroll_totp(
    current_user: User = Depends(get_current_active_user),
    mfa_service: MfaService = Depends(get_mfa_service)
):
    """
    Enroll in TOTP (Time-based One-Time Password) MFA

    Generates a TOTP secret and QR code for enrollment.
    Scan the QR code with an authenticator app (Google Authenticator, Authy, Microsoft Authenticator, etc.).

    **Returns:**
    - secret: Base32-encoded TOTP secret (for manual entry)
    - qr_code_data_uri: QR code as data URI (embed in <img> tag)
    - backup_codes: 10 one-time backup codes
    - issuer: Issuer name ("StocksBlitz")
    - account_name: Account name (your email)
    - message: Instructions

    **Authentication:**
    - Requires valid access token
    - User must be in active status

    **Process:**
    1. Call this endpoint to get QR code
    2. Scan QR code with authenticator app
    3. App will show 6-digit code that changes every 30 seconds
    4. Call `/mfa/totp/confirm` with the code to activate MFA

    **Backup Codes:**
    - 10 one-time backup codes are provided
    - Store them securely (print or save in password manager)
    - Each code can only be used once
    - Use them if you lose access to your authenticator app

    **Example Response:**
    ```json
    {
      "secret": "JBSWY3DPEHPK3PXP",
      "qr_code_data_uri": "data:image/png;base64,iVBORw0KGgoAAAANS...",
      "backup_codes": [
        "12345678",
        "87654321",
        ...
      ],
      "issuer": "StocksBlitz",
      "account_name": "user@example.com",
      "message": "Scan QR code with authenticator app..."
    }
    ```

    **Errors:**
    - 400: MFA already enabled (disable it first to re-enroll)
    """
    try:
        secret, qr_code_data_uri, backup_codes = mfa_service.enroll_totp(current_user)

        return MfaEnrollResponse(
            secret=secret,
            qr_code_data_uri=qr_code_data_uri,
            backup_codes=backup_codes,
            issuer="StocksBlitz",
            account_name=current_user.email,
            message="Scan QR code with authenticator app (Google Authenticator, Authy, etc.)"
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/totp/confirm", response_model=MfaConfirmResponse)
async def confirm_totp(
    request_data: MfaConfirmRequest,
    current_user: User = Depends(get_current_active_user),
    mfa_service: MfaService = Depends(get_mfa_service)
):
    """
    Confirm TOTP enrollment and activate MFA

    Verifies the 6-digit code from your authenticator app and enables MFA.

    **Request Body:**
    - code: 6-digit TOTP code from authenticator app

    **Returns:**
    - user_id: User ID
    - mfa_enabled: true
    - message: Success message
    - backup_codes_remaining: Number of unused backup codes

    **Authentication:**
    - Requires valid access token
    - User must have called `/mfa/totp/enroll` first

    **Example Request:**
    ```json
    {
      "code": "123456"
    }
    ```

    **Example Response:**
    ```json
    {
      "user_id": 123,
      "mfa_enabled": true,
      "message": "MFA enabled successfully",
      "backup_codes_remaining": 10
    }
    ```

    **After Activation:**
    - Next login will require MFA code
    - You'll see 2-step authentication prompt after entering password
    - Can use TOTP code or backup code for verification

    **Errors:**
    - 400: Invalid code, no enrollment found, or MFA already enabled
    """
    try:
        mfa_service.confirm_totp(current_user, request_data.code)
        backup_codes_remaining = mfa_service.get_backup_codes_remaining(current_user)

        return MfaConfirmResponse(
            user_id=current_user.user_id,
            mfa_enabled=True,
            message="MFA enabled successfully",
            backup_codes_remaining=backup_codes_remaining
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.delete("/totp", response_model=MfaDisableResponse)
async def disable_totp(
    request_data: MfaDisableRequest,
    current_user: User = Depends(get_current_active_user),
    mfa_service: MfaService = Depends(get_mfa_service)
):
    """
    Disable TOTP MFA

    Disables MFA for your account. Requires password and optionally a TOTP code for security.

    **Request Body:**
    - password: Your password (required for security)
    - code: 6-digit TOTP code or backup code (optional but recommended)

    **Returns:**
    - user_id: User ID
    - mfa_enabled: false
    - message: Success message

    **Authentication:**
    - Requires valid access token
    - MFA must be currently enabled

    **Example Request:**
    ```json
    {
      "password": "your_password",
      "code": "123456"
    }
    ```

    **Example Response:**
    ```json
    {
      "user_id": 123,
      "mfa_enabled": false,
      "message": "MFA disabled successfully"
    }
    ```

    **After Disabling:**
    - Future logins will not require MFA code
    - You can re-enroll at any time by calling `/mfa/totp/enroll`
    - Backup codes are invalidated

    **Errors:**
    - 400: Invalid password, invalid code, or MFA not enabled
    """
    try:
        mfa_service.disable_totp(
            user=current_user,
            password=request_data.password,
            code=request_data.code
        )

        return MfaDisableResponse(
            user_id=current_user.user_id,
            mfa_enabled=False,
            message="MFA disabled successfully"
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/status", response_model=MfaStatusResponse)
async def get_mfa_status(
    current_user: User = Depends(get_current_active_user),
    mfa_service: MfaService = Depends(get_mfa_service)
):
    """
    Get MFA status

    Returns current MFA configuration status for your account.

    **Returns:**
    - user_id: User ID
    - mfa_enabled: Whether MFA is currently enabled
    - totp_configured: Whether TOTP is configured
    - backup_codes_remaining: Number of unused backup codes
    - enrolled_at: When MFA was first enabled (ISO timestamp)

    **Authentication:**
    - Requires valid access token

    **Example Response:**
    ```json
    {
      "user_id": 123,
      "mfa_enabled": true,
      "totp_configured": true,
      "backup_codes_remaining": 8,
      "enrolled_at": "2025-11-01T10:00:00Z"
    }
    ```

    **Interpretation:**
    - mfa_enabled: false → MFA not set up
    - mfa_enabled: true, backup_codes_remaining: 0 → Low on backup codes, regenerate them
    """
    status_dict = mfa_service.get_mfa_status(current_user)
    return MfaStatusResponse(**status_dict)


@router.post("/backup-codes/regenerate", response_model=BackupCodesRegenerateResponse)
async def regenerate_backup_codes(
    request_data: BackupCodesRegenerateRequest,
    current_user: User = Depends(get_current_active_user),
    mfa_service: MfaService = Depends(get_mfa_service)
):
    """
    Regenerate backup codes

    Generates a new set of 10 backup codes. Previous codes are invalidated.

    **Request Body:**
    - password: Your password (required for security)
    - code: 6-digit TOTP code (backup codes NOT allowed for this operation)

    **Returns:**
    - user_id: User ID
    - backup_codes: New list of 10 backup codes
    - message: Success message
    - warning: Warning about previous codes being invalidated

    **Authentication:**
    - Requires valid access token
    - MFA must be enabled

    **Example Request:**
    ```json
    {
      "password": "your_password",
      "code": "123456"
    }
    ```

    **Example Response:**
    ```json
    {
      "user_id": 123,
      "backup_codes": [
        "12345678",
        "87654321",
        "11223344",
        ...
      ],
      "message": "Backup codes regenerated successfully",
      "warning": "Store these codes securely. Previous backup codes are now invalid."
    }
    ```

    **Important:**
    - Store new codes securely (print or save in password manager)
    - Previous backup codes are immediately invalidated
    - Each code can only be used once

    **When to Regenerate:**
    - Running low on backup codes
    - Suspect backup codes have been compromised
    - Lost access to stored backup codes

    **Errors:**
    - 400: Invalid password, invalid code, or MFA not enabled
    - 400: Cannot use backup code for this operation (must use TOTP code)
    """
    try:
        new_backup_codes = mfa_service.regenerate_backup_codes(
            user=current_user,
            password=request_data.password,
            code=request_data.code
        )

        return BackupCodesRegenerateResponse(
            user_id=current_user.user_id,
            backup_codes=new_backup_codes,
            message="Backup codes regenerated successfully",
            warning="Store these codes securely. Previous backup codes are now invalid."
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
