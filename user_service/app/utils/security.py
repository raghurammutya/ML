"""
Security utilities for password hashing, validation, and token generation
"""

import secrets
import string
import re
from typing import Optional
from passlib.context import CryptContext
import zxcvbn

from app.core.config import settings


# Password hashing context using bcrypt
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=settings.PASSWORD_BCRYPT_COST
)


def hash_password(password: str) -> str:
    """
    Hash a password using bcrypt

    Args:
        password: Plain text password

    Returns:
        Hashed password
    """
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a password against a hash

    Args:
        plain_password: Plain text password to verify
        hashed_password: Hashed password to check against

    Returns:
        True if password matches, False otherwise
    """
    print(f"[DEBUG] verify_password called:", flush=True)
    print(f"  plain_password type: {type(plain_password)}, len: {len(plain_password) if plain_password else 0}", flush=True)
    print(f"  hashed_password type: {type(hashed_password)}, len: {len(hashed_password) if hashed_password else 0}", flush=True)
    print(f"  plain_password value: '{plain_password}'", flush=True)
    print(f"  hashed_password value: '{hashed_password[:20]}...'", flush=True)
    result = pwd_context.verify(plain_password, hashed_password)
    print(f"  result: {result}", flush=True)
    return result


def validate_password_strength(password: str, user_inputs: Optional[list] = None) -> dict:
    """
    Validate password strength using multiple criteria

    Args:
        password: Password to validate
        user_inputs: Optional list of user-specific strings (email, name) to check against

    Returns:
        dict with 'valid' (bool) and 'errors' (list) keys
    """
    errors = []

    # Length check
    if len(password) < settings.PASSWORD_MIN_LENGTH:
        errors.append(f"Password must be at least {settings.PASSWORD_MIN_LENGTH} characters long")

    # Complexity checks
    if not re.search(r'[A-Z]', password):
        errors.append("Password must contain at least one uppercase letter")

    if not re.search(r'[a-z]', password):
        errors.append("Password must contain at least one lowercase letter")

    if not re.search(r'\d', password):
        errors.append("Password must contain at least one digit")

    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        errors.append("Password must contain at least one special character")

    # Use zxcvbn for additional entropy checking
    result = zxcvbn.zxcvbn(password, user_inputs=user_inputs or [])

    if result['score'] < 2:  # Score 0-4, we require at least 2
        errors.append(f"Password is too weak. {result['feedback']['warning']}")
        if result['feedback']['suggestions']:
            errors.extend(result['feedback']['suggestions'])

    return {
        'valid': len(errors) == 0,
        'errors': errors,
        'strength_score': result['score']  # 0-4
    }


def generate_random_token(length: int = 32) -> str:
    """
    Generate a cryptographically secure random token

    Args:
        length: Length of the token

    Returns:
        Random token string
    """
    return secrets.token_urlsafe(length)


def generate_device_fingerprint(user_agent: str, ip: str) -> str:
    """
    Generate a device fingerprint from user agent and IP

    Args:
        user_agent: User agent string
        ip: IP address

    Returns:
        Device fingerprint hash
    """
    import hashlib
    data = f"{user_agent}:{ip}".encode()
    return hashlib.sha256(data).hexdigest()[:32]


def generate_backup_codes(count: int = 10, length: int = 8) -> list[str]:
    """
    Generate backup codes for MFA

    Args:
        count: Number of backup codes to generate
        length: Length of each backup code

    Returns:
        List of backup codes
    """
    codes = []
    for _ in range(count):
        # Generate alphanumeric codes (easier to type)
        code = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(length))
        # Format as XXXX-XXXX for readability
        formatted = f"{code[:4]}-{code[4:]}" if length == 8 else code
        codes.append(formatted)
    return codes


def mask_email(email: str) -> str:
    """
    Mask email address for logging

    Args:
        email: Email address to mask

    Returns:
        Masked email (e.g., u***r@example.com)
    """
    if '@' not in email:
        return email

    local, domain = email.split('@', 1)
    if len(local) <= 2:
        masked_local = '*' * len(local)
    else:
        masked_local = f"{local[0]}***{local[-1]}"

    return f"{masked_local}@{domain}"


def mask_ip(ip: str) -> str:
    """
    Mask IP address for logging (last octet)

    Args:
        ip: IP address to mask

    Returns:
        Masked IP (e.g., 203.0.113.xxx)
    """
    parts = ip.split('.')
    if len(parts) == 4:  # IPv4
        parts[-1] = 'xxx'
        return '.'.join(parts)
    else:  # IPv6 or other format
        return ip[:20] + '...'


def constant_time_compare(a: str, b: str) -> bool:
    """
    Constant-time string comparison to prevent timing attacks

    Args:
        a: First string
        b: Second string

    Returns:
        True if strings are equal, False otherwise
    """
    return secrets.compare_digest(a.encode(), b.encode())
