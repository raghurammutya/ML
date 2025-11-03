"""
JWT Token Service - Token generation, validation, and management
"""

import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from jose import jwt, JWTError
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend

from app.core.config import settings
from app.core.database import SessionLocal
from app.models import JwtSigningKey, User


class JWTService:
    """Service for JWT token operations"""

    def __init__(self):
        self.algorithm = settings.JWT_ALGORITHM
        self.issuer = settings.JWT_ISSUER
        self.audience = settings.JWT_AUDIENCE
        self.access_token_ttl = timedelta(minutes=settings.JWT_ACCESS_TOKEN_TTL_MINUTES)
        self.refresh_token_ttl = timedelta(days=settings.JWT_REFRESH_TOKEN_TTL_DAYS)
        self._private_key: Optional[str] = None
        self._public_key: Optional[str] = None
        self._key_id: Optional[str] = None

    def _load_signing_key(self) -> None:
        """Load the active signing key from database"""
        if self._private_key is not None:
            return  # Already loaded

        db = SessionLocal()
        try:
            # Get active signing key
            key_record = db.query(JwtSigningKey).filter(
                JwtSigningKey.active == True
            ).first()

            if not key_record:
                raise ValueError("No active JWT signing key found. Please generate a key first.")

            self._key_id = key_record.key_id
            self._public_key = key_record.public_key

            # TODO: Decrypt private key using KMS
            # For now, assuming it's stored in plain text (development only)
            self._private_key = key_record.private_key_encrypted

        finally:
            db.close()

    def generate_access_token(
        self,
        user_id: int,
        session_id: str,
        roles: list[str],
        trading_account_ids: list[int],
        mfa_verified: bool = False,
        additional_claims: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Generate an access token

        Args:
            user_id: User ID
            session_id: Session ID
            roles: List of user roles
            trading_account_ids: List of accessible trading account IDs
            mfa_verified: Whether MFA was used
            additional_claims: Optional additional claims

        Returns:
            JWT access token
        """
        self._load_signing_key()

        now = datetime.utcnow()
        expires_at = now + self.access_token_ttl

        claims = {
            "iss": self.issuer,
            "sub": f"user:{user_id}",
            "aud": [self.audience],
            "exp": int(expires_at.timestamp()),
            "iat": int(now.timestamp()),
            "sid": session_id,
            "scp": ["read", "trade"],  # Default scopes
            "roles": roles,
            "acct_ids": trading_account_ids,
            "mfa": mfa_verified,
            "ver": 1  # Token version
        }

        if additional_claims:
            claims.update(additional_claims)

        return jwt.encode(
            claims,
            self._private_key,
            algorithm=self.algorithm,
            headers={"kid": self._key_id}
        )

    def generate_refresh_token(
        self,
        user_id: int,
        session_id: str,
        jti: Optional[str] = None
    ) -> tuple[str, str]:
        """
        Generate a refresh token

        Args:
            user_id: User ID
            session_id: Session ID
            jti: Optional JWT ID (generated if not provided)

        Returns:
            Tuple of (refresh_token, jti)
        """
        self._load_signing_key()

        if jti is None:
            jti = str(uuid.uuid4())

        now = datetime.utcnow()
        expires_at = now + self.refresh_token_ttl

        claims = {
            "jti": jti,
            "sub": f"user:{user_id}",
            "sid": session_id,
            "exp": int(expires_at.timestamp()),
            "iat": int(now.timestamp()),
            "typ": "refresh"
        }

        token = jwt.encode(
            claims,
            self._private_key,
            algorithm=self.algorithm,
            headers={"kid": self._key_id}
        )

        return token, jti

    def generate_service_token(
        self,
        client_id: str,
        scopes: list[str]
    ) -> str:
        """
        Generate a service-to-service token (OAuth2 client credentials)

        Args:
            client_id: OAuth client ID
            scopes: List of scopes

        Returns:
            JWT service token
        """
        self._load_signing_key()

        now = datetime.utcnow()
        expires_at = now + timedelta(hours=1)  # Service tokens expire in 1 hour

        claims = {
            "iss": self.issuer,
            "sub": f"service:{client_id}",
            "aud": [self.issuer],  # Service tokens are for user_service itself
            "exp": int(expires_at.timestamp()),
            "iat": int(now.timestamp()),
            "scp": scopes,
            "ver": 1
        }

        return jwt.encode(
            claims,
            self._private_key,
            algorithm=self.algorithm,
            headers={"kid": self._key_id}
        )

    def validate_token(self, token: str, token_type: str = "access") -> Dict[str, Any]:
        """
        Validate and decode a JWT token

        Args:
            token: JWT token to validate
            token_type: Type of token ('access' or 'refresh')

        Returns:
            Decoded token claims

        Raises:
            JWTError: If token is invalid
        """
        self._load_signing_key()

        try:
            # Decode and validate
            payload = jwt.decode(
                token,
                self._public_key,
                algorithms=[self.algorithm],
                issuer=self.issuer,
                audience=self.audience if token_type == "access" else None
            )

            # Additional validation for refresh tokens
            if token_type == "refresh":
                if payload.get("typ") != "refresh":
                    raise JWTError("Invalid token type")

            return payload

        except JWTError as e:
            raise JWTError(f"Token validation failed: {str(e)}")

    def decode_token_unverified(self, token: str) -> Dict[str, Any]:
        """
        Decode token without verification (for introspection)

        Args:
            token: JWT token

        Returns:
            Decoded claims (unverified)
        """
        return jwt.get_unverified_claims(token)

    def get_jwks(self) -> Dict[str, Any]:
        """
        Get JSON Web Key Set (JWKS) for public key distribution

        Returns:
            JWKS dictionary
        """
        db = SessionLocal()
        try:
            # Get all active keys (usually just one, but support multiple for rotation)
            keys = db.query(JwtSigningKey).filter(
                JwtSigningKey.active == True
            ).all()

            jwks_keys = []
            for key_record in keys:
                # Parse public key
                public_key = serialization.load_pem_public_key(
                    key_record.public_key.encode(),
                    backend=default_backend()
                )

                # Extract RSA numbers
                public_numbers = public_key.public_numbers()

                # Convert to base64url encoding
                import base64
                n = base64.urlsafe_b64encode(
                    public_numbers.n.to_bytes(
                        (public_numbers.n.bit_length() + 7) // 8, 'big'
                    )
                ).decode('utf-8').rstrip('=')

                e = base64.urlsafe_b64encode(
                    public_numbers.e.to_bytes(
                        (public_numbers.e.bit_length() + 7) // 8, 'big'
                    )
                ).decode('utf-8').rstrip('=')

                jwks_keys.append({
                    "kty": "RSA",
                    "use": "sig",
                    "kid": key_record.key_id,
                    "alg": key_record.algorithm,
                    "n": n,
                    "e": e
                })

            return {"keys": jwks_keys}

        finally:
            db.close()

    def extract_user_id(self, token: str) -> Optional[int]:
        """
        Extract user ID from token without full validation

        Args:
            token: JWT token

        Returns:
            User ID or None if not found
        """
        try:
            claims = self.decode_token_unverified(token)
            sub = claims.get("sub", "")
            if sub.startswith("user:"):
                return int(sub.split(":", 1)[1])
        except Exception:
            pass
        return None


# Global JWT service instance
jwt_service = JWTService()
