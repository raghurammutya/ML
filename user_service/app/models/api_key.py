"""
API Key model for SDK authentication
"""

from datetime import datetime
import enum
from sqlalchemy import Column, BigInteger, String, DateTime, ForeignKey, Text, Integer, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
import sqlalchemy as sa

from app.core.database import Base


class RateLimitTier(str, enum.Enum):
    """Rate limit tier for API keys"""
    FREE = "free"           # 100 requests/hour
    STANDARD = "standard"   # 1000 requests/hour
    PREMIUM = "premium"     # 10000 requests/hour
    UNLIMITED = "unlimited" # No limit


class ApiKey(Base):
    """API Key model for authentication"""
    __tablename__ = "api_keys"
    __table_args__ = (
        Index('idx_api_keys_user_id', 'user_id'),
        Index('idx_api_keys_key_prefix_active', 'key_prefix', postgresql_where=sa.text('revoked_at IS NULL')),
        Index('idx_api_keys_expires_at', 'expires_at', postgresql_where=sa.text('revoked_at IS NULL AND expires_at IS NOT NULL')),
    )

    api_key_id = Column(BigInteger, primary_key=True, autoincrement=True, index=True)
    user_id = Column(BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    key_prefix = Column(String(20), nullable=False, unique=True)
    key_hash = Column(String(255), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    scopes = Column(JSONB, nullable=False, default=["read"])
    ip_whitelist = Column(JSONB, nullable=True)
    rate_limit_tier = Column(sa.Enum(RateLimitTier), default=RateLimitTier.STANDARD, nullable=False)
    last_used_at = Column(DateTime, nullable=True)
    last_used_ip = Column(String(45), nullable=True)
    usage_count = Column(BigInteger, default=0, nullable=False)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    revoked_at = Column(DateTime, nullable=True)
    revoked_by = Column(BigInteger, ForeignKey("users.user_id"), nullable=True)
    revoked_reason = Column(Text, nullable=True)

    # Relationships
    user = relationship("User", foreign_keys=[user_id], back_populates="api_keys")
    revoker = relationship("User", foreign_keys=[revoked_by])

    def __repr__(self):
        return f"<ApiKey(id={self.api_key_id}, prefix='{self.key_prefix}', user_id={self.user_id})>"


class ApiKeyUsageLog(Base):
    """API Key usage log for analytics"""
    __tablename__ = "api_key_usage_logs"
    __table_args__ = (
        Index('idx_api_key_usage_api_key_id', 'api_key_id', 'timestamp'),
        Index('idx_api_key_usage_timestamp', 'timestamp'),
    )

    log_id = Column(BigInteger, primary_key=True, autoincrement=True, index=True)
    api_key_id = Column(BigInteger, ForeignKey("api_keys.api_key_id", ondelete="CASCADE"), nullable=False)
    endpoint = Column(String(255), nullable=False)
    method = Column(String(10), nullable=False)
    status_code = Column(Integer, nullable=False)
    response_time_ms = Column(Integer, nullable=True)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    api_key = relationship("ApiKey")

    def __repr__(self):
        return f"<ApiKeyUsageLog(id={self.log_id}, api_key_id={self.api_key_id}, endpoint='{self.endpoint}')>"
