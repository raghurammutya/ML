"""
Trading Account models
"""

from datetime import datetime
import enum
from sqlalchemy import Column, BigInteger, String, DateTime, ForeignKey, Text, Enum, UniqueConstraint, Index, Boolean
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.core.database import Base


class TradingAccountStatus(str, enum.Enum):
    """Trading account status"""
    PENDING_VERIFICATION = "pending_verification"
    ACTIVE = "active"
    CREDENTIALS_EXPIRED = "credentials_expired"
    DEACTIVATED = "deactivated"


class SubscriptionTier(str, enum.Enum):
    """KiteConnect subscription tier"""
    UNKNOWN = "unknown"  # Not yet detected
    PERSONAL = "personal"  # Free tier - trading only, no market data
    CONNECT = "connect"  # Paid tier (Rs. 500/month) - trading + market data
    STARTUP = "startup"  # Startup program - free with full features


class TradingAccount(Base):
    """Trading Account model - links users to broker accounts"""
    __tablename__ = "trading_accounts"
    __table_args__ = (
        # Unique constraint: one broker user ID per broker (when active)
        # Note: Partial unique index removed to avoid SQLAlchemy compilation issues
        # Can be added manually via migration if needed: CREATE UNIQUE INDEX ... WHERE status='active'
        Index('idx_trading_accounts_user_id', 'user_id'),
        Index('idx_trading_accounts_status', 'status'),
    )

    trading_account_id = Column(BigInteger, primary_key=True, index=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    broker = Column(String(50), nullable=False)  # 'kite', 'zerodha', etc.
    broker_user_id = Column(String(100), nullable=True)
    nickname = Column(String(255), nullable=False)
    account_name = Column(String(255), nullable=True)
    status = Column(Enum(TradingAccountStatus), default=TradingAccountStatus.PENDING_VERIFICATION, nullable=False)
    broker_profile_snapshot = Column(JSONB, nullable=True)  # {name, email, broker_user_id}
    credential_vault_ref = Column(String(255), nullable=False)  # Reference to KMS/Vault
    data_key_wrapped = Column(Text, nullable=False)  # Encrypted data key (envelope encryption)
    api_key_encrypted = Column(Text, nullable=True)
    api_secret_encrypted = Column(Text, nullable=True)
    access_token_encrypted = Column(Text, nullable=True)
    password_encrypted = Column(Text, nullable=True)
    totp_secret_encrypted = Column(Text, nullable=True)
    linked_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_synced_at = Column(DateTime, nullable=True)

    # Subscription tier tracking (KiteConnect API tiers)
    subscription_tier = Column(Enum(SubscriptionTier, name='subscriptiontier', create_constraint=False, values_callable=lambda x: [e.value for e in x]), default=SubscriptionTier.UNKNOWN, nullable=False)
    subscription_tier_last_checked = Column(DateTime, nullable=True)
    market_data_available = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    owner = relationship("User", back_populates="trading_accounts")
    memberships = relationship("TradingAccountMembership", back_populates="trading_account", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<TradingAccount(id={self.trading_account_id}, broker='{self.broker}', user_id={self.user_id})>"


class TradingAccountMembership(Base):
    """Trading Account Membership - shared account access"""
    __tablename__ = "trading_account_memberships"
    __table_args__ = (
        UniqueConstraint('trading_account_id', 'member_user_id', name='uq_account_member'),
        Index('idx_memberships_account', 'trading_account_id'),
        Index('idx_memberships_member', 'member_user_id'),
    )

    membership_id = Column(BigInteger, primary_key=True, index=True, autoincrement=True)
    trading_account_id = Column(BigInteger, ForeignKey("trading_accounts.trading_account_id", ondelete="CASCADE"), nullable=False)
    member_user_id = Column(BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    permissions = Column(JSONB, nullable=False, default=['read'])  # ['read', 'trade']
    granted_by = Column(BigInteger, ForeignKey("users.user_id"), nullable=False)
    granted_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    revoked_at = Column(DateTime, nullable=True)

    # Relationships
    trading_account = relationship("TradingAccount", back_populates="memberships")
    member = relationship("User", foreign_keys=[member_user_id], back_populates="account_memberships")
    granted_by_user = relationship("User", foreign_keys=[granted_by])

    def __repr__(self):
        return f"<Membership(id={self.membership_id}, account={self.trading_account_id}, member={self.member_user_id})>"
