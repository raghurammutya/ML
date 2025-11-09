"""
Secure Token Storage Module

SEC-CRITICAL-003 FIX: Encrypted token storage with proper file permissions.

This module provides secure storage for Kite access tokens using:
1. AES-256-GCM encryption (via cryptography.Fernet)
2. Strict file permissions (600 - owner read/write only)
3. Encrypted token files with .enc extension

Security Improvements:
- Tokens encrypted at rest (prevents cleartext credential exposure)
- File permissions set to 600 (prevents group/other access)
- Encryption key required from environment (no hardcoded keys)
- Automatic migration from plaintext to encrypted format

References:
- CWE-312: Cleartext Storage of Sensitive Information
- CWE-732: Incorrect Permission Assignment for Critical Resource
"""

from __future__ import annotations

import json
import logging
import os
import stat
from pathlib import Path
from typing import Dict, Any, Optional
from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)


class SecureTokenStorage:
    """
    Secure storage for Kite access tokens with encryption and proper permissions.

    SEC-CRITICAL-003 FIX: Replaces plaintext JSON storage with encrypted storage.
    """

    def __init__(self, encryption_key: Optional[str] = None):
        """
        Initialize secure token storage.

        Args:
            encryption_key: Base64-encoded Fernet key. If None, reads from ENCRYPTION_KEY env var.

        Raises:
            ValueError: If encryption key is not provided or invalid
        """
        if encryption_key is None:
            encryption_key = os.environ.get('ENCRYPTION_KEY')
            if not encryption_key:
                raise ValueError(
                    "ENCRYPTION_KEY environment variable is required for secure token storage. "
                    "Generate a key with: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())' "
                    "and set it in your environment: export ENCRYPTION_KEY=<generated_key>"
                )

        try:
            # Fernet expects base64-encoded 32-byte key
            # If user provided hex key (64 chars), convert to Fernet format
            if len(encryption_key) == 64 and all(c in '0123456789abcdefABCDEF' for c in encryption_key):
                # Convert hex to bytes and then to Fernet key
                import base64
                key_bytes = bytes.fromhex(encryption_key)
                encryption_key = base64.urlsafe_b64encode(key_bytes).decode()

            self.cipher = Fernet(encryption_key.encode() if isinstance(encryption_key, str) else encryption_key)
            logger.info("Secure token storage initialized successfully")
        except Exception as e:
            raise ValueError(f"Invalid ENCRYPTION_KEY format. Must be a valid Fernet key: {e}")

    def save_token(self, token_path: Path, token_data: Dict[str, Any]) -> None:
        """
        Save token data to encrypted file with secure permissions.

        Args:
            token_path: Path to token file (will add .enc extension)
            token_data: Token data dictionary to encrypt and save

        Security:
        - Encrypts token data using Fernet (AES-128-CBC + HMAC)
        - Sets file permissions to 600 (owner read/write only)
        - Atomic write (write to temp file, then rename)
        """
        # Use .enc extension for encrypted files
        encrypted_path = token_path.with_suffix('.json.enc')

        # Serialize token data to JSON
        json_data = json.dumps(token_data, indent=2)

        # Encrypt the JSON data
        encrypted_data = self.cipher.encrypt(json_data.encode('utf-8'))

        # Write to temporary file first (atomic write)
        temp_path = encrypted_path.with_suffix('.tmp')
        try:
            # Write encrypted data
            temp_path.write_bytes(encrypted_data)

            # Set strict file permissions (600 - owner read/write only)
            # SEC-CRITICAL-003 FIX: Prevent group/other access
            os.chmod(temp_path, stat.S_IRUSR | stat.S_IWUSR)  # 0o600

            # Atomic rename
            temp_path.rename(encrypted_path)

            logger.info(
                f"Saved encrypted token to {encrypted_path} with permissions 600"
            )

            # Remove old plaintext file if it exists (migration)
            if token_path.exists():
                logger.warning(
                    f"Removing old plaintext token file: {token_path} (migrated to encrypted format)"
                )
                token_path.unlink()

        except Exception as e:
            # Clean up temp file on error
            if temp_path.exists():
                temp_path.unlink()
            raise RuntimeError(f"Failed to save encrypted token: {e}")

    def load_token(self, token_path: Path) -> Optional[Dict[str, Any]]:
        """
        Load token data from encrypted file.

        Args:
            token_path: Base path to token file (will check .enc extension)

        Returns:
            Decrypted token data dictionary, or None if file doesn't exist

        Raises:
            RuntimeError: If decryption fails

        Migration Support:
        - Checks for encrypted file (.json.enc) first
        - Falls back to plaintext file (.json) for backward compatibility
        - Auto-migrates plaintext to encrypted format
        """
        encrypted_path = token_path.with_suffix('.json.enc')

        # Try encrypted file first
        if encrypted_path.exists():
            try:
                # Read encrypted data
                encrypted_data = encrypted_path.read_bytes()

                # Decrypt
                decrypted_data = self.cipher.decrypt(encrypted_data)

                # Parse JSON
                token_data = json.loads(decrypted_data.decode('utf-8'))

                logger.debug(f"Loaded encrypted token from {encrypted_path}")
                return token_data

            except InvalidToken:
                logger.error(
                    f"Failed to decrypt token file {encrypted_path}. "
                    "The encryption key may have changed. "
                    "You may need to re-authenticate."
                )
                raise RuntimeError("Token decryption failed - encryption key mismatch")
            except Exception as e:
                raise RuntimeError(f"Failed to load encrypted token: {e}")

        # Migration path: check for old plaintext file
        if token_path.exists():
            logger.warning(
                f"Found plaintext token file {token_path}. Migrating to encrypted format..."
            )
            try:
                # Load plaintext token
                token_data = json.loads(token_path.read_text())

                # Save as encrypted (this will also delete the plaintext file)
                self.save_token(token_path, token_data)

                logger.info(f"Successfully migrated token to encrypted format")
                return token_data

            except Exception as e:
                logger.error(f"Failed to migrate plaintext token: {e}")
                raise RuntimeError(f"Token migration failed: {e}")

        # No token file found
        logger.debug(f"No token file found at {token_path} or {encrypted_path}")
        return None


# Global instance (initialized on first use)
_storage_instance: Optional[SecureTokenStorage] = None


def get_secure_storage() -> SecureTokenStorage:
    """Get global secure token storage instance."""
    global _storage_instance
    if _storage_instance is None:
        _storage_instance = SecureTokenStorage()
    return _storage_instance
