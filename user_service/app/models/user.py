"""
User model
"""

from datetime import datetime
from sqlalchemy import Column, BigInteger, String, Boolean, DateTime, Enum
from sqlalchemy.orm import relationship
import enum

from app.core.database import Base


class UserStatus(str, enum.Enum):
    """User account status"""
    PENDING_VERIFICATION = "pending_verification"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DEACTIVATED = "deactivated"


class User(Base):
    """User model - central identity"""
    __tablename__ = "users"

    user_id = Column(BigInteger, primary_key=True, index=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    email_verified = Column(Boolean, default=False, nullable=False)
    password_hash = Column(String(255), nullable=True)  # NULL for OAuth-only users
    name = Column(String(255), nullable=False)
    phone = Column(String(20), nullable=True)
    phone_verified = Column(Boolean, default=False, nullable=False)
    timezone = Column(String(50), default="UTC", nullable=False)
    locale = Column(String(10), default="en-US", nullable=False)
    status = Column(Enum(UserStatus), default=UserStatus.PENDING_VERIFICATION, nullable=False, index=True)
    mfa_enabled = Column(Boolean, default=False, nullable=False)
    oauth_provider = Column(String(50), nullable=True)  # 'google', 'github', NULL
    oauth_subject = Column(String(255), nullable=True)  # External provider user ID
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    deactivated_at = Column(DateTime, nullable=True)
    last_login_at = Column(DateTime, nullable=True)

    # Relationships
    roles = relationship("UserRole", foreign_keys="UserRole.user_id", back_populates="user", cascade="all, delete-orphan")
    preferences = relationship("UserPreference", back_populates="user", uselist=False, cascade="all, delete-orphan")
    trading_accounts = relationship("TradingAccount", back_populates="owner", cascade="all, delete-orphan")
    account_memberships = relationship("TradingAccountMembership", foreign_keys="TradingAccountMembership.member_user_id", back_populates="member", cascade="all, delete-orphan")
    mfa_totp = relationship("MfaTotp", back_populates="user", uselist=False, cascade="all, delete-orphan")
    auth_providers = relationship("AuthProvider", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User(user_id={self.user_id}, email='{self.email}', status='{self.status}')>"
