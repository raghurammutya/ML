"""
MFA Service - TOTP (Time-based One-Time Password) implementation

Implements secure 2FA using TOTP standard (RFC 6238).
"""

import pyotp
import qrcode
import io
import base64
from typing import Optional, Tuple, List
from datetime import datetime
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.redis_client import RedisClient
from app.models import User, MfaTotp
from app.utils.security import generate_backup_codes, verify_password, constant_time_compare
from app.services.event_service import EventService


class MfaService:
    """Service for MFA/TOTP operations"""

    def __init__(self, db: Session, redis: RedisClient):
        self.db = db
        self.redis = redis
        self.event_service = EventService(redis)

    def enroll_totp(self, user: User) -> Tuple[str, str, List[str]]:
        """
        Enroll user for TOTP

        Generates a new TOTP secret, QR code, and backup codes.
        Does not enable MFA until confirmation.

        Args:
            user: User object

        Returns:
            Tuple of (secret, qr_code_data_uri, backup_codes)

        Raises:
            ValueError: If MFA already enabled
        """
        if user.mfa_enabled:
            raise ValueError("MFA is already enabled. Disable it first to re-enroll.")

        # Generate TOTP secret
        secret = pyotp.random_base32()

        # Create TOTP URI for QR code
        totp = pyotp.TOTP(secret)
        issuer = "StocksBlitz"
        account_name = user.email

        provisioning_uri = totp.provisioning_uri(
            name=account_name,
            issuer_name=issuer
        )

        # Generate QR code
        qr_code_data_uri = self._generate_qr_code(provisioning_uri)

        # Generate backup codes
        backup_codes = generate_backup_codes(count=10)

        # Store temporary MFA configuration (not yet confirmed)
        # Check if enrollment already exists
        mfa_totp = self.db.query(MfaTotp).filter(
            MfaTotp.user_id == user.user_id
        ).first()

        if mfa_totp:
            # Update existing enrollment
            mfa_totp.secret_encrypted = secret  # TODO: Encrypt with KMS
            mfa_totp.backup_codes_encrypted = backup_codes  # TODO: Encrypt with KMS
            mfa_totp.enabled = False  # Not enabled until confirmed
            mfa_totp.enrolled_at = None
        else:
            # Create new enrollment
            mfa_totp = MfaTotp(
                user_id=user.user_id,
                secret_encrypted=secret,  # TODO: Encrypt with KMS
                backup_codes_encrypted=backup_codes,  # TODO: Encrypt with KMS
                enabled=False
            )
            self.db.add(mfa_totp)

        self.db.commit()

        return secret, qr_code_data_uri, backup_codes

    def _generate_qr_code(self, data: str) -> str:
        """
        Generate QR code as data URI

        Args:
            data: Data to encode in QR code

        Returns:
            QR code as data URI (can be used in <img src="">)
        """
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(data)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")

        # Convert to data URI
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)

        img_base64 = base64.b64encode(buffer.read()).decode()
        data_uri = f"data:image/png;base64,{img_base64}"

        return data_uri

    def confirm_totp(self, user: User, code: str) -> bool:
        """
        Confirm TOTP enrollment

        Verifies the code and enables MFA if valid.

        Args:
            user: User object
            code: 6-digit TOTP code

        Returns:
            True if confirmed successfully

        Raises:
            ValueError: If no enrollment found or code invalid
        """
        # Get MFA configuration
        mfa_totp = self.db.query(MfaTotp).filter(
            MfaTotp.user_id == user.user_id
        ).first()

        if not mfa_totp:
            raise ValueError("No MFA enrollment found. Please enroll first.")

        if mfa_totp.enabled:
            raise ValueError("MFA is already enabled")

        # Verify TOTP code
        secret = mfa_totp.secret_encrypted  # TODO: Decrypt with KMS
        totp = pyotp.TOTP(secret)

        if not totp.verify(code, valid_window=1):  # Allow 1 step (30s) clock skew
            raise ValueError("Invalid verification code")

        # Enable MFA
        mfa_totp.enabled = True
        mfa_totp.enrolled_at = datetime.utcnow()
        user.mfa_enabled = True

        self.db.commit()

        # Publish mfa.enabled event
        backup_codes_count = len(mfa_totp.backup_codes_encrypted or [])
        self.event_service.publish_mfa_enabled(
            user_id=user.user_id,
            method="totp",
            backup_codes_count=backup_codes_count
        )

        return True

    def verify_totp(
        self,
        user: User,
        code: str,
        allow_backup_codes: bool = True
    ) -> Tuple[bool, str]:
        """
        Verify TOTP code or backup code

        Args:
            user: User object
            code: 6-digit TOTP code or backup code
            allow_backup_codes: Whether to allow backup codes

        Returns:
            Tuple of (verified: bool, method: str)
            method is "totp" or "backup_code"

        Raises:
            ValueError: If MFA not enabled
        """
        if not user.mfa_enabled:
            raise ValueError("MFA is not enabled for this user")

        # Get MFA configuration
        mfa_totp = self.db.query(MfaTotp).filter(
            MfaTotp.user_id == user.user_id,
            MfaTotp.enabled == True
        ).first()

        if not mfa_totp:
            raise ValueError("MFA configuration not found")

        # Try TOTP first
        secret = mfa_totp.secret_encrypted  # TODO: Decrypt with KMS
        totp = pyotp.TOTP(secret)

        if totp.verify(code, valid_window=1):  # Allow 1 step (30s) clock skew
            return True, "totp"

        # Try backup codes
        if allow_backup_codes:
            backup_codes = mfa_totp.backup_codes_encrypted  # TODO: Decrypt with KMS

            for i, backup_code in enumerate(backup_codes):
                if constant_time_compare(code, backup_code):
                    # Remove used backup code
                    backup_codes.pop(i)
                    mfa_totp.backup_codes_encrypted = backup_codes  # TODO: Encrypt with KMS
                    self.db.commit()

                    return True, "backup_code"

        return False, ""

    def disable_totp(
        self,
        user: User,
        password: str,
        code: Optional[str] = None
    ) -> bool:
        """
        Disable TOTP for user

        Requires password and optionally a TOTP code for security.

        Args:
            user: User object
            password: User's password
            code: TOTP code or backup code (optional)

        Returns:
            True if disabled successfully

        Raises:
            ValueError: If password incorrect or code invalid
        """
        if not user.mfa_enabled:
            raise ValueError("MFA is not enabled")

        # Verify password
        if not verify_password(password, user.password_hash):
            raise ValueError("Invalid password")

        # Verify code if provided
        if code:
            verified, _ = self.verify_totp(user, code, allow_backup_codes=True)
            if not verified:
                raise ValueError("Invalid verification code")

        # Get MFA configuration
        mfa_totp = self.db.query(MfaTotp).filter(
            MfaTotp.user_id == user.user_id
        ).first()

        if mfa_totp:
            # Delete MFA configuration
            self.db.delete(mfa_totp)

        # Disable MFA on user
        user.mfa_enabled = False
        self.db.commit()

        # Publish mfa.disabled event
        self.event_service.publish_mfa_disabled(
            user_id=user.user_id,
            method="totp"
        )

        return True

    def get_mfa_status(self, user: User) -> dict:
        """
        Get MFA status for user

        Args:
            user: User object

        Returns:
            Dictionary with MFA status information
        """
        mfa_totp = self.db.query(MfaTotp).filter(
            MfaTotp.user_id == user.user_id
        ).first()

        if not mfa_totp:
            return {
                "user_id": user.user_id,
                "mfa_enabled": False,
                "totp_configured": False,
                "backup_codes_remaining": 0,
                "enrolled_at": None
            }

        backup_codes = mfa_totp.backup_codes_encrypted or []  # TODO: Decrypt with KMS

        return {
            "user_id": user.user_id,
            "mfa_enabled": user.mfa_enabled,
            "totp_configured": mfa_totp.enabled,
            "backup_codes_remaining": len(backup_codes),
            "enrolled_at": mfa_totp.enrolled_at.isoformat() if mfa_totp.enrolled_at else None
        }

    def regenerate_backup_codes(
        self,
        user: User,
        password: str,
        code: str
    ) -> List[str]:
        """
        Regenerate backup codes

        Invalidates old backup codes and generates new ones.

        Args:
            user: User object
            password: User's password
            code: TOTP code (not backup code)

        Returns:
            New list of backup codes

        Raises:
            ValueError: If password or code invalid, or MFA not enabled
        """
        if not user.mfa_enabled:
            raise ValueError("MFA is not enabled")

        # Verify password
        if not verify_password(password, user.password_hash):
            raise ValueError("Invalid password")

        # Verify TOTP code (don't allow backup codes for this operation)
        mfa_totp = self.db.query(MfaTotp).filter(
            MfaTotp.user_id == user.user_id,
            MfaTotp.enabled == True
        ).first()

        if not mfa_totp:
            raise ValueError("MFA configuration not found")

        secret = mfa_totp.secret_encrypted  # TODO: Decrypt with KMS
        totp = pyotp.TOTP(secret)

        if not totp.verify(code, valid_window=1):
            raise ValueError("Invalid verification code")

        # Generate new backup codes
        new_backup_codes = generate_backup_codes(count=10)

        # Update backup codes
        mfa_totp.backup_codes_encrypted = new_backup_codes  # TODO: Encrypt with KMS
        self.db.commit()

        return new_backup_codes

    def get_backup_codes_remaining(self, user: User) -> int:
        """
        Get number of remaining backup codes

        Args:
            user: User object

        Returns:
            Number of unused backup codes
        """
        if not user.mfa_enabled:
            return 0

        mfa_totp = self.db.query(MfaTotp).filter(
            MfaTotp.user_id == user.user_id
        ).first()

        if not mfa_totp:
            return 0

        backup_codes = mfa_totp.backup_codes_encrypted or []  # TODO: Decrypt with KMS
        return len(backup_codes)
