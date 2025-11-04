"""
OAuth Client model for service-to-service authentication
"""

from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, Text, BigInteger, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.core.database import Base


class OAuthClient(Base):
    """OAuth Client model for service accounts"""
    __tablename__ = "oauth_clients"

    client_id = Column(String(100), primary_key=True)
    client_secret_hash = Column(String(255), nullable=False)  # bcrypt
    name = Column(String(255), nullable=False)  # 'ticker_service', 'alert_service'
    scopes = Column(JSONB, nullable=False, default=['authz:check'])
    enabled = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_used_at = Column(DateTime, nullable=True)

    def __repr__(self):
        return f"<OAuthClient(client_id='{self.client_id}', name='{self.name}')>"


class JwtSigningKey(Base):
    """JWT Signing Key model"""
    __tablename__ = "jwt_signing_keys"

    key_id = Column(String(50), primary_key=True)  # 'key_2025_11_03'
    public_key = Column(Text, nullable=False)  # PEM format
    private_key_encrypted = Column(Text, nullable=False)  # Encrypted with KMS
    algorithm = Column(String(10), default="RS256", nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    rotated_at = Column(DateTime, nullable=True)

    def __repr__(self):
        return f"<JwtSigningKey(key_id='{self.key_id}', active={self.active})>"


class AuthProvider(Base):
    """Auth Provider model - links users to OAuth providers"""
    __tablename__ = "auth_providers"

    provider_id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    provider = Column(String(50), nullable=False)  # 'google', 'github', etc.
    provider_user_id = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False)
    email_verified = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User", back_populates="auth_providers")

    def __repr__(self):
        return f"<AuthProvider(provider='{self.provider}', user_id={self.user_id})>"
