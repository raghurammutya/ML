#!/usr/bin/env python3
"""
Generate RSA key pair for JWT signing and store in database
"""

import sys
import os
from datetime import datetime
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.core.database import SessionLocal
from app.models import JwtSigningKey


def generate_rsa_keypair(key_size: int = 4096):
    """Generate RSA key pair"""
    print(f"Generating RSA-{key_size} key pair...")

    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=key_size,
        backend=default_backend()
    )

    # Serialize private key
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()  # TODO: Encrypt with KMS in production
    ).decode('utf-8')

    # Serialize public key
    public_key = private_key.public_key()
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode('utf-8')

    return private_pem, public_pem


def store_key(key_id: str, private_pem: str, public_pem: str):
    """Store key in database"""
    db = SessionLocal()
    try:
        # Deactivate all existing keys
        db.query(JwtSigningKey).update({"active": False})

        # Create new key
        new_key = JwtSigningKey(
            key_id=key_id,
            public_key=public_pem,
            private_key_encrypted=private_pem,  # TODO: Encrypt with KMS
            algorithm="RS256",
            active=True
        )

        db.add(new_key)
        db.commit()

        print(f"✓ Key '{key_id}' stored and activated")
        print(f"  Algorithm: RS256")
        print(f"  Created: {datetime.utcnow().isoformat()}")

    except Exception as e:
        db.rollback()
        print(f"✗ Error storing key: {e}")
        raise
    finally:
        db.close()


def main():
    """Main function"""
    # Generate key ID from current date
    key_id = f"key_{datetime.utcnow().strftime('%Y_%m_%d_%H%M')}"

    print("=" * 60)
    print("JWT Signing Key Generator")
    print("=" * 60)
    print()

    # Generate keypair
    private_pem, public_pem = generate_rsa_keypair(key_size=4096)

    # Store in database
    store_key(key_id, private_pem, public_pem)

    print()
    print("=" * 60)
    print("Key generation complete!")
    print("=" * 60)
    print()
    print(f"Key ID: {key_id}")
    print()
    print("Next steps:")
    print("1. Update JWT_SIGNING_KEY_ID in .env to:", key_id)
    print("2. Restart user_service")
    print("3. Verify JWKS endpoint: GET /v1/.well-known/jwks.json")
    print()
    print("NOTE: In production, encrypt the private key with KMS before storing")
    print()


if __name__ == "__main__":
    main()
