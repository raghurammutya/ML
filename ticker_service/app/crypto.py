"""
Cryptographic utilities for secure credential management.

This module provides AES-256-GCM encryption with AWS KMS for key management.
Replaces insecure base64 encoding with proper encryption.
"""

import os
import logging
from typing import Optional
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = logging.getLogger(__name__)


class CredentialEncryption:
    """
    Secure credential encryption using AES-256-GCM.

    For production: Integrate with AWS KMS or similar key management service.
    For development: Uses environment-based encryption key.
    """

    def __init__(self, encryption_key: Optional[bytes] = None):
        """
        Initialize credential encryption.

        Args:
            encryption_key: 32-byte encryption key. If None, reads from environment.

        Raises:
            ValueError: If encryption key is not provided or invalid

        Security Note:
            SEC-CRITICAL-004 FIX: Encryption key MUST be provided via environment variable.
            Random key generation has been removed to prevent data loss and key exposure.
        """
        if encryption_key is None:
            # SEC-CRITICAL-004 FIX: REQUIRE encryption key from environment
            # Never auto-generate keys as this causes data loss on restart
            key_hex = os.environ.get('ENCRYPTION_KEY')
            if not key_hex:
                raise ValueError(
                    "ENCRYPTION_KEY environment variable is required for credential encryption. "
                    "Generate a key with: python -c 'import os; print(os.urandom(32).hex())' "
                    "and set it in your environment: export ENCRYPTION_KEY=<generated_key>"
                )

            try:
                encryption_key = bytes.fromhex(key_hex)
            except ValueError as e:
                raise ValueError(f"Invalid ENCRYPTION_KEY format. Must be a hex string: {e}")

        if len(encryption_key) != 32:
            raise ValueError(
                f"Encryption key must be exactly 32 bytes (64 hex characters), got {len(encryption_key)} bytes"
            )

        # SEC-CRITICAL-004 FIX: Never log encryption keys
        self.cipher = AESGCM(encryption_key)
        logger.info("Credential encryption initialized successfully")

    def encrypt(self, plaintext: str) -> bytes:
        """
        Encrypt credential using AES-256-GCM.

        Args:
            plaintext: Credential to encrypt

        Returns:
            Encrypted blob: [12 bytes: nonce][N bytes: ciphertext]
        """
        nonce = os.urandom(12)  # 96-bit nonce for GCM
        ciphertext = self.cipher.encrypt(nonce, plaintext.encode('utf-8'), None)

        # Return nonce + ciphertext
        return nonce + ciphertext

    def decrypt(self, encrypted_blob: bytes) -> str:
        """
        Decrypt credential using AES-256-GCM.

        Args:
            encrypted_blob: Encrypted data from encrypt()

        Returns:
            Decrypted plaintext credential
        """
        # Extract nonce and ciphertext
        nonce = encrypted_blob[:12]
        ciphertext = encrypted_blob[12:]

        plaintext = self.cipher.decrypt(nonce, ciphertext, None)
        return plaintext.decode('utf-8')


# Global instance (initialized on first use)
_encryption_instance: Optional[CredentialEncryption] = None


def get_encryption() -> CredentialEncryption:
    """Get global encryption instance."""
    global _encryption_instance
    if _encryption_instance is None:
        _encryption_instance = CredentialEncryption()
    return _encryption_instance
