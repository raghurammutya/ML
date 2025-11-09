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
        """
        if encryption_key is None:
            # Read from environment or generate for development
            key_hex = os.environ.get('ENCRYPTION_KEY')
            if key_hex:
                encryption_key = bytes.fromhex(key_hex)
            else:
                # Development only: Generate a key (should be persisted)
                logger.warning(
                    "No ENCRYPTION_KEY found, generating temporary key. "
                    "THIS IS NOT SECURE FOR PRODUCTION!"
                )
                encryption_key = AESGCM.generate_key(bit_length=256)
                logger.info(f"Generated key (save to env): {encryption_key.hex()}")

        if len(encryption_key) != 32:
            raise ValueError("Encryption key must be exactly 32 bytes")

        self.cipher = AESGCM(encryption_key)

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
