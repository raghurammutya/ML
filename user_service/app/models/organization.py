"""
Organization models for multi-tenant support.

Organizations allow groups of users to:
- Share trading accounts
- Manage team permissions
- Collaborate on strategies
- Track team performance
"""

from datetime import datetime
import enum
from sqlalchemy import Column, BigInteger, String, DateTime, ForeignKey, Text, Enum, UniqueConstraint, Index, Boolean
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.core.database import Base


class OrganizationStatus(str, enum.Enum):
    """Organization account status"""
    PENDING = "pending"  # Awaiting initial setup
    ACTIVE = "active"  # Fully operational
    SUSPENDED = "suspended"  # Temporarily disabled (payment issues, policy violation)
    DEACTIVATED = "deactivated"  # Permanently closed


class OrganizationMemberRole(str, enum.Enum):
    """Role of member within organization"""
    OWNER = "owner"  # Full control, can delete org
    ADMIN = "admin"  # Can manage members and settings
    MEMBER = "member"  # Can access shared accounts based on permissions
    VIEWER = "viewer"  # Read-only access


class Organization(Base):
    """
    Organization model - represents a team/company.

    Organizations provide:
    - Shared trading account management
    - Team collaboration features
    - Centralized billing
    - Role-based access control
    """
    __tablename__ = "organizations"
    __table_args__ = (
        Index('idx_organizations_slug', 'slug'),
        Index('idx_organizations_status', 'status'),
        Index('idx_organizations_created_by', 'created_by_user_id'),
    )

    organization_id = Column(BigInteger, primary_key=True, index=True, autoincrement=True)

    # Organization Identity
    name = Column(String(255), nullable=False)  # Display name
    slug = Column(String(100), unique=True, nullable=False, index=True)  # URL-safe identifier
    description = Column(Text, nullable=True)
    logo_url = Column(String(500), nullable=True)
    website = Column(String(500), nullable=True)

    # Status
    status = Column(Enum(OrganizationStatus), default=OrganizationStatus.PENDING, nullable=False)

    # Settings
    settings = Column(JSONB, nullable=False, default={})  # Custom organization settings
    # Example settings:
    # {
    #   "require_2fa": true,
    #   "allowed_brokers": ["zerodha", "kite"],
    #   "max_members": 10,
    #   "trading_hours": {"start": "09:15", "end": "15:30"}
    # }

    # Metadata
    created_by_user_id = Column(BigInteger, ForeignKey("users.user_id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    deactivated_at = Column(DateTime, nullable=True)

    # Relationships
    created_by = relationship("User", foreign_keys=[created_by_user_id])
    members = relationship("OrganizationMember", back_populates="organization", cascade="all, delete-orphan")
    trading_accounts = relationship("OrganizationTradingAccount", back_populates="organization", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Organization(id={self.organization_id}, name='{self.name}', slug='{self.slug}')>"


class OrganizationMember(Base):
    """
    Organization membership - links users to organizations with roles.

    Supports:
    - Multiple users per organization
    - Multiple organizations per user
    - Role-based permissions
    - Invitation workflow
    """
    __tablename__ = "organization_members"
    __table_args__ = (
        UniqueConstraint('organization_id', 'user_id', name='uq_org_user'),
        Index('idx_org_members_org', 'organization_id'),
        Index('idx_org_members_user', 'user_id'),
        Index('idx_org_members_role', 'role'),
    )

    membership_id = Column(BigInteger, primary_key=True, index=True, autoincrement=True)
    organization_id = Column(BigInteger, ForeignKey("organizations.organization_id", ondelete="CASCADE"), nullable=False)
    user_id = Column(BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)

    # Role and Permissions
    role = Column(Enum(OrganizationMemberRole), nullable=False)
    custom_permissions = Column(JSONB, nullable=True)  # Optional custom permissions beyond role
    # Example:
    # {
    #   "can_create_accounts": true,
    #   "can_delete_accounts": false,
    #   "can_invite_members": true,
    #   "accessible_account_ids": [1, 2, 3]  # Restrict to specific accounts
    # }

    # Invitation tracking
    invited_by = Column(BigInteger, ForeignKey("users.user_id"), nullable=True)
    invited_at = Column(DateTime, nullable=True)
    accepted_at = Column(DateTime, nullable=True)  # NULL if invitation pending

    # Metadata
    joined_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    removed_at = Column(DateTime, nullable=True)  # Soft delete

    # Relationships
    organization = relationship("Organization", back_populates="members")
    user = relationship("User", foreign_keys=[user_id])
    invited_by_user = relationship("User", foreign_keys=[invited_by])

    def __repr__(self):
        return f"<OrganizationMember(org={self.organization_id}, user={self.user_id}, role='{self.role}')>"


class OrganizationTradingAccount(Base):
    """
    Link between organizations and trading accounts.

    Allows:
    - Organizations to own/manage trading accounts
    - Organization-wide account sharing
    - Centralized account management
    """
    __tablename__ = "organization_trading_accounts"
    __table_args__ = (
        UniqueConstraint('organization_id', 'trading_account_id', name='uq_org_trading_account'),
        Index('idx_org_accounts_org', 'organization_id'),
        Index('idx_org_accounts_account', 'trading_account_id'),
    )

    id = Column(BigInteger, primary_key=True, index=True, autoincrement=True)
    organization_id = Column(BigInteger, ForeignKey("organizations.organization_id", ondelete="CASCADE"), nullable=False)
    trading_account_id = Column(BigInteger, ForeignKey("trading_accounts.trading_account_id", ondelete="CASCADE"), nullable=False)

    # Account-level permissions for organization members
    default_permissions = Column(JSONB, nullable=False, default=['read'])
    # Example: ['read', 'trade', 'admin']
    # - read: View positions, orders
    # - trade: Place/cancel orders
    # - admin: Modify account settings

    # Metadata
    added_by = Column(BigInteger, ForeignKey("users.user_id"), nullable=False)
    added_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    removed_at = Column(DateTime, nullable=True)  # Soft delete

    # Relationships
    organization = relationship("Organization", back_populates="trading_accounts")
    trading_account = relationship("TradingAccount")
    added_by_user = relationship("User", foreign_keys=[added_by])

    def __repr__(self):
        return f"<OrgTradingAccount(org={self.organization_id}, account={self.trading_account_id})>"


class OrganizationInvitation(Base):
    """
    Pending organization invitations.

    Tracks invitation lifecycle:
    - Invitation sent via email
    - Acceptance/rejection
    - Expiry
    """
    __tablename__ = "organization_invitations"
    __table_args__ = (
        Index('idx_org_invitations_org', 'organization_id'),
        Index('idx_org_invitations_email', 'email'),
        Index('idx_org_invitations_token', 'invitation_token'),
        Index('idx_org_invitations_status', 'status'),
    )

    invitation_id = Column(BigInteger, primary_key=True, index=True, autoincrement=True)
    organization_id = Column(BigInteger, ForeignKey("organizations.organization_id", ondelete="CASCADE"), nullable=False)

    # Invitee information
    email = Column(String(255), nullable=False, index=True)
    invited_role = Column(Enum(OrganizationMemberRole), nullable=False)
    custom_permissions = Column(JSONB, nullable=True)

    # Invitation tracking
    invitation_token = Column(String(255), unique=True, nullable=False, index=True)  # Secure random token
    invited_by = Column(BigInteger, ForeignKey("users.user_id"), nullable=False)
    invited_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)  # Typically 7 days

    # Status
    status = Column(String(50), default="pending", nullable=False)  # pending, accepted, rejected, expired
    accepted_at = Column(DateTime, nullable=True)
    accepted_by_user_id = Column(BigInteger, ForeignKey("users.user_id"), nullable=True)
    rejected_at = Column(DateTime, nullable=True)

    # Relationships
    organization = relationship("Organization")
    invited_by_user = relationship("User", foreign_keys=[invited_by])
    accepted_by_user = relationship("User", foreign_keys=[accepted_by_user_id])

    def __repr__(self):
        return f"<OrgInvitation(org={self.organization_id}, email='{self.email}', status='{self.status}')>"
