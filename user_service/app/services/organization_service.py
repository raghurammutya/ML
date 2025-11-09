"""
Organization Service - Business logic for organizations.

Handles:
- Organization creation and management
- Member management (invite, add, remove)
- Permission checks
- Trading account associations
"""

import secrets
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from app.models.organization import (
    Organization,
    OrganizationStatus,
    OrganizationMember,
    OrganizationMemberRole,
    OrganizationTradingAccount,
    OrganizationInvitation
)
from app.models.user import User
from app.models.trading_account import TradingAccount


class OrganizationService:
    """Service for organization operations."""

    def __init__(self, db: Session):
        self.db = db

    # ==================== Organization CRUD ====================

    def create_organization(
        self,
        name: str,
        slug: str,
        created_by_user_id: int,
        description: Optional[str] = None,
        logo_url: Optional[str] = None,
        website: Optional[str] = None,
        settings: Optional[Dict[str, Any]] = None
    ) -> Organization:
        """
        Create a new organization.

        The creator automatically becomes the OWNER.

        Args:
            name: Organization display name
            slug: URL-safe identifier (must be unique)
            created_by_user_id: User ID of creator
            description: Optional description
            logo_url: Optional logo URL
            website: Optional website URL
            settings: Optional custom settings

        Returns:
            Created Organization object

        Raises:
            ValueError: If slug already exists
        """
        # Check if slug already exists
        existing = self.db.query(Organization).filter(
            Organization.slug == slug
        ).first()

        if existing:
            raise ValueError(f"Organization with slug '{slug}' already exists")

        # Create organization
        org = Organization(
            name=name,
            slug=slug,
            description=description,
            logo_url=logo_url,
            website=website,
            status=OrganizationStatus.ACTIVE,
            settings=settings or {},
            created_by_user_id=created_by_user_id
        )

        self.db.add(org)
        self.db.flush()  # Get org.organization_id

        # Add creator as OWNER
        owner_member = OrganizationMember(
            organization_id=org.organization_id,
            user_id=created_by_user_id,
            role=OrganizationMemberRole.OWNER,
            accepted_at=datetime.utcnow()  # Auto-accepted
        )

        self.db.add(owner_member)
        self.db.commit()
        self.db.refresh(org)

        return org

    def get_organization(self, organization_id: int) -> Optional[Organization]:
        """Get organization by ID."""
        return self.db.query(Organization).filter(
            Organization.organization_id == organization_id
        ).first()

    def get_organization_by_slug(self, slug: str) -> Optional[Organization]:
        """Get organization by slug."""
        return self.db.query(Organization).filter(
            Organization.slug == slug
        ).first()

    def list_organizations(
        self,
        user_id: Optional[int] = None,
        status: Optional[OrganizationStatus] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Organization]:
        """
        List organizations.

        Args:
            user_id: Filter by organizations the user is a member of
            status: Filter by status
            limit: Maximum number of results
            offset: Pagination offset

        Returns:
            List of organizations
        """
        query = self.db.query(Organization)

        # Filter by user membership
        if user_id is not None:
            query = query.join(OrganizationMember).filter(
                OrganizationMember.user_id == user_id,
                OrganizationMember.removed_at.is_(None)
            )

        # Filter by status
        if status is not None:
            query = query.filter(Organization.status == status)

        return query.order_by(Organization.created_at.desc()).limit(limit).offset(offset).all()

    def update_organization(
        self,
        organization_id: int,
        name: Optional[str] = None,
        description: Optional[str] = None,
        logo_url: Optional[str] = None,
        website: Optional[str] = None,
        settings: Optional[Dict[str, Any]] = None
    ) -> Optional[Organization]:
        """
        Update organization details.

        Args:
            organization_id: Organization ID
            name: New name (optional)
            description: New description (optional)
            logo_url: New logo URL (optional)
            website: New website URL (optional)
            settings: New settings (optional)

        Returns:
            Updated Organization or None if not found
        """
        org = self.get_organization(organization_id)
        if not org:
            return None

        if name is not None:
            org.name = name
        if description is not None:
            org.description = description
        if logo_url is not None:
            org.logo_url = logo_url
        if website is not None:
            org.website = website
        if settings is not None:
            org.settings = settings

        org.updated_at = datetime.utcnow()

        self.db.commit()
        self.db.refresh(org)

        return org

    def deactivate_organization(self, organization_id: int) -> bool:
        """
        Deactivate an organization.

        Args:
            organization_id: Organization ID

        Returns:
            True if deactivated, False if not found
        """
        org = self.get_organization(organization_id)
        if not org:
            return False

        org.status = OrganizationStatus.DEACTIVATED
        org.deactivated_at = datetime.utcnow()

        self.db.commit()

        return True

    # ==================== Member Management ====================

    def add_member(
        self,
        organization_id: int,
        user_id: int,
        role: OrganizationMemberRole,
        invited_by: Optional[int] = None,
        custom_permissions: Optional[Dict[str, Any]] = None
    ) -> OrganizationMember:
        """
        Add a member to an organization.

        Args:
            organization_id: Organization ID
            user_id: User ID to add
            role: Member role
            invited_by: User ID who invited (optional)
            custom_permissions: Custom permissions (optional)

        Returns:
            Created OrganizationMember

        Raises:
            ValueError: If user is already a member
        """
        # Check if already a member
        existing = self.db.query(OrganizationMember).filter(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.user_id == user_id,
            OrganizationMember.removed_at.is_(None)
        ).first()

        if existing:
            raise ValueError("User is already a member of this organization")

        member = OrganizationMember(
            organization_id=organization_id,
            user_id=user_id,
            role=role,
            custom_permissions=custom_permissions,
            invited_by=invited_by,
            accepted_at=datetime.utcnow()
        )

        self.db.add(member)
        self.db.commit()
        self.db.refresh(member)

        return member

    def get_member(
        self,
        organization_id: int,
        user_id: int
    ) -> Optional[OrganizationMember]:
        """Get member details."""
        return self.db.query(OrganizationMember).filter(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.user_id == user_id,
            OrganizationMember.removed_at.is_(None)
        ).first()

    def list_members(
        self,
        organization_id: int,
        role: Optional[OrganizationMemberRole] = None
    ) -> List[OrganizationMember]:
        """
        List organization members.

        Args:
            organization_id: Organization ID
            role: Filter by role (optional)

        Returns:
            List of members
        """
        query = self.db.query(OrganizationMember).filter(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.removed_at.is_(None)
        )

        if role is not None:
            query = query.filter(OrganizationMember.role == role)

        return query.all()

    def update_member_role(
        self,
        organization_id: int,
        user_id: int,
        new_role: OrganizationMemberRole,
        custom_permissions: Optional[Dict[str, Any]] = None
    ) -> Optional[OrganizationMember]:
        """
        Update a member's role and permissions.

        Args:
            organization_id: Organization ID
            user_id: User ID
            new_role: New role
            custom_permissions: New custom permissions (optional)

        Returns:
            Updated OrganizationMember or None if not found
        """
        member = self.get_member(organization_id, user_id)
        if not member:
            return None

        member.role = new_role
        if custom_permissions is not None:
            member.custom_permissions = custom_permissions

        self.db.commit()
        self.db.refresh(member)

        return member

    def remove_member(
        self,
        organization_id: int,
        user_id: int
    ) -> bool:
        """
        Remove a member from an organization (soft delete).

        Args:
            organization_id: Organization ID
            user_id: User ID to remove

        Returns:
            True if removed, False if not found

        Raises:
            ValueError: If trying to remove the last OWNER
        """
        member = self.get_member(organization_id, user_id)
        if not member:
            return False

        # Prevent removing the last owner
        if member.role == OrganizationMemberRole.OWNER:
            owner_count = self.db.query(OrganizationMember).filter(
                OrganizationMember.organization_id == organization_id,
                OrganizationMember.role == OrganizationMemberRole.OWNER,
                OrganizationMember.removed_at.is_(None)
            ).count()

            if owner_count <= 1:
                raise ValueError("Cannot remove the last owner of an organization")

        member.removed_at = datetime.utcnow()

        self.db.commit()

        return True

    # ==================== Invitations ====================

    def create_invitation(
        self,
        organization_id: int,
        email: str,
        invited_role: OrganizationMemberRole,
        invited_by: int,
        expires_in_days: int = 7,
        custom_permissions: Optional[Dict[str, Any]] = None
    ) -> OrganizationInvitation:
        """
        Create an organization invitation.

        Args:
            organization_id: Organization ID
            email: Invitee email
            invited_role: Role to assign when accepted
            invited_by: User ID who is inviting
            expires_in_days: Days until invitation expires
            custom_permissions: Custom permissions (optional)

        Returns:
            Created OrganizationInvitation
        """
        # Generate secure token
        invitation_token = secrets.token_urlsafe(32)

        invitation = OrganizationInvitation(
            organization_id=organization_id,
            email=email,
            invited_role=invited_role,
            custom_permissions=custom_permissions,
            invitation_token=invitation_token,
            invited_by=invited_by,
            expires_at=datetime.utcnow() + timedelta(days=expires_in_days),
            status="pending"
        )

        self.db.add(invitation)
        self.db.commit()
        self.db.refresh(invitation)

        return invitation

    def get_invitation(self, invitation_token: str) -> Optional[OrganizationInvitation]:
        """Get invitation by token."""
        return self.db.query(OrganizationInvitation).filter(
            OrganizationInvitation.invitation_token == invitation_token
        ).first()

    def accept_invitation(
        self,
        invitation_token: str,
        user_id: int
    ) -> OrganizationMember:
        """
        Accept an organization invitation.

        Args:
            invitation_token: Invitation token
            user_id: User ID accepting the invitation

        Returns:
            Created OrganizationMember

        Raises:
            ValueError: If invitation is invalid, expired, or already used
        """
        invitation = self.get_invitation(invitation_token)

        if not invitation:
            raise ValueError("Invitation not found")

        if invitation.status != "pending":
            raise ValueError(f"Invitation already {invitation.status}")

        if invitation.expires_at < datetime.utcnow():
            invitation.status = "expired"
            self.db.commit()
            raise ValueError("Invitation has expired")

        # Verify email matches user's email
        user = self.db.query(User).filter(User.user_id == user_id).first()
        if not user or user.email != invitation.email:
            raise ValueError("Invitation email does not match user email")

        # Add member
        member = self.add_member(
            organization_id=invitation.organization_id,
            user_id=user_id,
            role=invitation.invited_role,
            invited_by=invitation.invited_by,
            custom_permissions=invitation.custom_permissions
        )

        # Mark invitation as accepted
        invitation.status = "accepted"
        invitation.accepted_at = datetime.utcnow()
        invitation.accepted_by_user_id = user_id

        self.db.commit()

        return member

    def reject_invitation(self, invitation_token: str) -> bool:
        """
        Reject an organization invitation.

        Args:
            invitation_token: Invitation token

        Returns:
            True if rejected, False if not found
        """
        invitation = self.get_invitation(invitation_token)

        if not invitation or invitation.status != "pending":
            return False

        invitation.status = "rejected"
        invitation.rejected_at = datetime.utcnow()

        self.db.commit()

        return True

    # ==================== Trading Account Management ====================

    def add_trading_account(
        self,
        organization_id: int,
        trading_account_id: int,
        added_by: int,
        default_permissions: Optional[List[str]] = None
    ) -> OrganizationTradingAccount:
        """
        Add a trading account to an organization.

        Args:
            organization_id: Organization ID
            trading_account_id: Trading account ID
            added_by: User ID adding the account
            default_permissions: Default permissions for members

        Returns:
            Created OrganizationTradingAccount

        Raises:
            ValueError: If account already added to organization
        """
        # Check if already added
        existing = self.db.query(OrganizationTradingAccount).filter(
            OrganizationTradingAccount.organization_id == organization_id,
            OrganizationTradingAccount.trading_account_id == trading_account_id,
            OrganizationTradingAccount.removed_at.is_(None)
        ).first()

        if existing:
            raise ValueError("Trading account already added to organization")

        org_account = OrganizationTradingAccount(
            organization_id=organization_id,
            trading_account_id=trading_account_id,
            added_by=added_by,
            default_permissions=default_permissions or ['read']
        )

        self.db.add(org_account)
        self.db.commit()
        self.db.refresh(org_account)

        return org_account

    def list_trading_accounts(
        self,
        organization_id: int
    ) -> List[OrganizationTradingAccount]:
        """
        List all trading accounts for an organization.

        Args:
            organization_id: Organization ID

        Returns:
            List of OrganizationTradingAccount
        """
        return self.db.query(OrganizationTradingAccount).filter(
            OrganizationTradingAccount.organization_id == organization_id,
            OrganizationTradingAccount.removed_at.is_(None)
        ).all()

    def remove_trading_account(
        self,
        organization_id: int,
        trading_account_id: int
    ) -> bool:
        """
        Remove a trading account from organization (soft delete).

        Args:
            organization_id: Organization ID
            trading_account_id: Trading account ID

        Returns:
            True if removed, False if not found
        """
        org_account = self.db.query(OrganizationTradingAccount).filter(
            OrganizationTradingAccount.organization_id == organization_id,
            OrganizationTradingAccount.trading_account_id == trading_account_id,
            OrganizationTradingAccount.removed_at.is_(None)
        ).first()

        if not org_account:
            return False

        org_account.removed_at = datetime.utcnow()

        self.db.commit()

        return True

    # ==================== Permission Checks ====================

    def check_permission(
        self,
        organization_id: int,
        user_id: int,
        required_role: Optional[OrganizationMemberRole] = None,
        required_permission: Optional[str] = None
    ) -> bool:
        """
        Check if user has permission in organization.

        Args:
            organization_id: Organization ID
            user_id: User ID
            required_role: Minimum required role (optional)
            required_permission: Required custom permission (optional)

        Returns:
            True if user has permission, False otherwise
        """
        member = self.get_member(organization_id, user_id)

        if not member:
            return False

        # Role hierarchy: OWNER > ADMIN > MEMBER > VIEWER
        role_hierarchy = {
            OrganizationMemberRole.OWNER: 4,
            OrganizationMemberRole.ADMIN: 3,
            OrganizationMemberRole.MEMBER: 2,
            OrganizationMemberRole.VIEWER: 1
        }

        # Check role
        if required_role:
            if role_hierarchy.get(member.role, 0) < role_hierarchy.get(required_role, 0):
                return False

        # Check custom permission
        if required_permission:
            if not member.custom_permissions:
                return False
            if not member.custom_permissions.get(required_permission, False):
                return False

        return True

    def is_owner(self, organization_id: int, user_id: int) -> bool:
        """Check if user is an owner of the organization."""
        return self.check_permission(
            organization_id,
            user_id,
            required_role=OrganizationMemberRole.OWNER
        )

    def is_admin_or_above(self, organization_id: int, user_id: int) -> bool:
        """Check if user is an admin or owner."""
        return self.check_permission(
            organization_id,
            user_id,
            required_role=OrganizationMemberRole.ADMIN
        )
