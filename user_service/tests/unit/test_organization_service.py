"""
Unit tests for OrganizationService.
"""

import pytest
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from app.services.organization_service import OrganizationService
from app.models.organization import (
    Organization,
    OrganizationStatus,
    OrganizationMember,
    OrganizationMemberRole,
    OrganizationTradingAccount,
    OrganizationInvitation
)
from app.models.user import User, UserStatus
from app.models.trading_account import TradingAccount, TradingAccountStatus


@pytest.fixture
def test_users(db_session: Session):
    """Create test users."""
    users = []
    for i in range(3):
        user = User(
            email=f"user{i}@test.com",
            password_hash="hashed_password",
            name=f"Test User {i}",
            status=UserStatus.ACTIVE
        )
        db_session.add(user)
        users.append(user)

    db_session.commit()
    for user in users:
        db_session.refresh(user)

    return users


@pytest.fixture
def test_trading_account(db_session: Session, test_users):
    """Create test trading account."""
    # Don't set subscription_tier - let the database server_default handle it
    account = TradingAccount(
        user_id=test_users[0].user_id,
        broker="zerodha",
        nickname="Test Account",
        status=TradingAccountStatus.ACTIVE,
        credential_vault_ref="vault_ref",
        data_key_wrapped="wrapped_key"
        # subscription_tier defaults to 'unknown' via server_default in migration
    )
    db_session.add(account)
    db_session.commit()
    db_session.refresh(account)
    return account


class TestOrganizationCRUD:
    """Test organization CRUD operations."""

    def test_create_organization(self, db_session: Session, test_users):
        """Test creating an organization."""
        service = OrganizationService(db_session)

        org = service.create_organization(
            name="Test Org",
            slug="test-org",
            created_by_user_id=test_users[0].user_id,
            description="Test organization",
            settings={"require_2fa": True}
        )

        assert org.organization_id is not None
        assert org.name == "Test Org"
        assert org.slug == "test-org"
        assert org.description == "Test organization"
        assert org.status == OrganizationStatus.ACTIVE
        assert org.settings == {"require_2fa": True}

        # Verify creator is added as OWNER
        member = service.get_member(org.organization_id, test_users[0].user_id)
        assert member is not None
        assert member.role == OrganizationMemberRole.OWNER
        assert member.accepted_at is not None

    def test_create_organization_duplicate_slug(self, db_session: Session, test_users):
        """Test creating organization with duplicate slug fails."""
        service = OrganizationService(db_session)

        # Create first org
        service.create_organization(
            name="Org 1",
            slug="duplicate-slug",
            created_by_user_id=test_users[0].user_id
        )

        # Try to create with same slug
        with pytest.raises(ValueError, match="already exists"):
            service.create_organization(
                name="Org 2",
                slug="duplicate-slug",
                created_by_user_id=test_users[1].user_id
            )

    def test_get_organization(self, db_session: Session, test_users):
        """Test getting organization by ID."""
        service = OrganizationService(db_session)

        created = service.create_organization(
            name="Get Test Org",
            slug="get-test-org",
            created_by_user_id=test_users[0].user_id
        )

        fetched = service.get_organization(created.organization_id)

        assert fetched is not None
        assert fetched.organization_id == created.organization_id
        assert fetched.name == "Get Test Org"

    def test_get_organization_by_slug(self, db_session: Session, test_users):
        """Test getting organization by slug."""
        service = OrganizationService(db_session)

        created = service.create_organization(
            name="Slug Test Org",
            slug="slug-test-org",
            created_by_user_id=test_users[0].user_id
        )

        fetched = service.get_organization_by_slug("slug-test-org")

        assert fetched is not None
        assert fetched.organization_id == created.organization_id
        assert fetched.slug == "slug-test-org"

    def test_list_organizations(self, db_session: Session, test_users):
        """Test listing organizations."""
        service = OrganizationService(db_session)

        # Create multiple orgs
        for i in range(3):
            service.create_organization(
                name=f"List Test Org {i}",
                slug=f"list-test-org-{i}",
                created_by_user_id=test_users[0].user_id
            )

        orgs = service.list_organizations(user_id=test_users[0].user_id)

        assert len(orgs) == 3

    def test_update_organization(self, db_session: Session, test_users):
        """Test updating organization."""
        service = OrganizationService(db_session)

        org = service.create_organization(
            name="Original Name",
            slug="update-test",
            created_by_user_id=test_users[0].user_id
        )

        updated = service.update_organization(
            organization_id=org.organization_id,
            name="Updated Name",
            description="New description"
        )

        assert updated.name == "Updated Name"
        assert updated.description == "New description"
        assert updated.slug == "update-test"  # Unchanged

    def test_deactivate_organization(self, db_session: Session, test_users):
        """Test deactivating organization."""
        service = OrganizationService(db_session)

        org = service.create_organization(
            name="Deactivate Test",
            slug="deactivate-test",
            created_by_user_id=test_users[0].user_id
        )

        success = service.deactivate_organization(org.organization_id)

        assert success is True

        # Verify status changed
        fetched = service.get_organization(org.organization_id)
        assert fetched.status == OrganizationStatus.DEACTIVATED
        assert fetched.deactivated_at is not None


class TestOrganizationMembers:
    """Test organization member management."""

    def test_add_member(self, db_session: Session, test_users):
        """Test adding a member to organization."""
        service = OrganizationService(db_session)

        org = service.create_organization(
            name="Member Test Org",
            slug="member-test-org",
            created_by_user_id=test_users[0].user_id
        )

        member = service.add_member(
            organization_id=org.organization_id,
            user_id=test_users[1].user_id,
            role=OrganizationMemberRole.MEMBER,
            invited_by=test_users[0].user_id
        )

        assert member.user_id == test_users[1].user_id
        assert member.role == OrganizationMemberRole.MEMBER
        assert member.invited_by == test_users[0].user_id
        assert member.accepted_at is not None

    def test_add_member_duplicate(self, db_session: Session, test_users):
        """Test adding duplicate member fails."""
        service = OrganizationService(db_session)

        org = service.create_organization(
            name="Duplicate Member Test",
            slug="duplicate-member-test",
            created_by_user_id=test_users[0].user_id
        )

        service.add_member(
            organization_id=org.organization_id,
            user_id=test_users[1].user_id,
            role=OrganizationMemberRole.MEMBER
        )

        # Try to add again
        with pytest.raises(ValueError, match="already a member"):
            service.add_member(
                organization_id=org.organization_id,
                user_id=test_users[1].user_id,
                role=OrganizationMemberRole.ADMIN
            )

    def test_list_members(self, db_session: Session, test_users):
        """Test listing organization members."""
        service = OrganizationService(db_session)

        org = service.create_organization(
            name="List Members Test",
            slug="list-members-test",
            created_by_user_id=test_users[0].user_id
        )

        # Add members
        for user in test_users[1:]:
            service.add_member(
                organization_id=org.organization_id,
                user_id=user.user_id,
                role=OrganizationMemberRole.MEMBER
            )

        members = service.list_members(org.organization_id)

        # 1 owner + 2 members = 3 total
        assert len(members) == 3

    def test_update_member_role(self, db_session: Session, test_users):
        """Test updating member role."""
        service = OrganizationService(db_session)

        org = service.create_organization(
            name="Update Member Test",
            slug="update-member-test",
            created_by_user_id=test_users[0].user_id
        )

        service.add_member(
            organization_id=org.organization_id,
            user_id=test_users[1].user_id,
            role=OrganizationMemberRole.MEMBER
        )

        updated = service.update_member_role(
            organization_id=org.organization_id,
            user_id=test_users[1].user_id,
            new_role=OrganizationMemberRole.ADMIN
        )

        assert updated.role == OrganizationMemberRole.ADMIN

    def test_remove_member(self, db_session: Session, test_users):
        """Test removing a member."""
        service = OrganizationService(db_session)

        org = service.create_organization(
            name="Remove Member Test",
            slug="remove-member-test",
            created_by_user_id=test_users[0].user_id
        )

        service.add_member(
            organization_id=org.organization_id,
            user_id=test_users[1].user_id,
            role=OrganizationMemberRole.MEMBER
        )

        success = service.remove_member(org.organization_id, test_users[1].user_id)

        assert success is True

        # Verify member is soft-deleted
        member = db_session.query(OrganizationMember).filter(
            OrganizationMember.organization_id == org.organization_id,
            OrganizationMember.user_id == test_users[1].user_id
        ).first()

        assert member.removed_at is not None

    def test_remove_last_owner_fails(self, db_session: Session, test_users):
        """Test that removing the last owner fails."""
        service = OrganizationService(db_session)

        org = service.create_organization(
            name="Last Owner Test",
            slug="last-owner-test",
            created_by_user_id=test_users[0].user_id
        )

        # Try to remove the only owner
        with pytest.raises(ValueError, match="last owner"):
            service.remove_member(org.organization_id, test_users[0].user_id)


class TestOrganizationInvitations:
    """Test organization invitation system."""

    def test_create_invitation(self, db_session: Session, test_users):
        """Test creating an invitation."""
        service = OrganizationService(db_session)

        org = service.create_organization(
            name="Invitation Test",
            slug="invitation-test",
            created_by_user_id=test_users[0].user_id
        )

        invitation = service.create_invitation(
            organization_id=org.organization_id,
            email="invite@test.com",
            invited_role=OrganizationMemberRole.MEMBER,
            invited_by=test_users[0].user_id,
            expires_in_days=7
        )

        assert invitation.email == "invite@test.com"
        assert invitation.invited_role == OrganizationMemberRole.MEMBER
        assert invitation.status == "pending"
        assert invitation.invitation_token is not None
        assert len(invitation.invitation_token) > 20  # Secure token

    def test_accept_invitation(self, db_session: Session, test_users):
        """Test accepting an invitation."""
        service = OrganizationService(db_session)

        org = service.create_organization(
            name="Accept Invitation Test",
            slug="accept-invitation-test",
            created_by_user_id=test_users[0].user_id
        )

        invitation = service.create_invitation(
            organization_id=org.organization_id,
            email=test_users[1].email,
            invited_role=OrganizationMemberRole.ADMIN,
            invited_by=test_users[0].user_id
        )

        member = service.accept_invitation(
            invitation_token=invitation.invitation_token,
            user_id=test_users[1].user_id
        )

        assert member.user_id == test_users[1].user_id
        assert member.role == OrganizationMemberRole.ADMIN

        # Verify invitation status updated
        db_session.refresh(invitation)
        assert invitation.status == "accepted"
        assert invitation.accepted_by_user_id == test_users[1].user_id

    def test_accept_expired_invitation_fails(self, db_session: Session, test_users):
        """Test accepting expired invitation fails."""
        service = OrganizationService(db_session)

        org = service.create_organization(
            name="Expired Invitation Test",
            slug="expired-invitation-test",
            created_by_user_id=test_users[0].user_id
        )

        invitation = service.create_invitation(
            organization_id=org.organization_id,
            email=test_users[1].email,
            invited_role=OrganizationMemberRole.MEMBER,
            invited_by=test_users[0].user_id,
            expires_in_days=7
        )

        # Manually expire the invitation
        invitation.expires_at = datetime.utcnow() - timedelta(days=1)
        db_session.commit()

        with pytest.raises(ValueError, match="expired"):
            service.accept_invitation(
                invitation_token=invitation.invitation_token,
                user_id=test_users[1].user_id
            )

    def test_reject_invitation(self, db_session: Session, test_users):
        """Test rejecting an invitation."""
        service = OrganizationService(db_session)

        org = service.create_organization(
            name="Reject Invitation Test",
            slug="reject-invitation-test",
            created_by_user_id=test_users[0].user_id
        )

        invitation = service.create_invitation(
            organization_id=org.organization_id,
            email="reject@test.com",
            invited_role=OrganizationMemberRole.MEMBER,
            invited_by=test_users[0].user_id
        )

        success = service.reject_invitation(invitation.invitation_token)

        assert success is True

        # Verify status
        db_session.refresh(invitation)
        assert invitation.status == "rejected"
        assert invitation.rejected_at is not None


class TestOrganizationTradingAccounts:
    """Test organization trading account management."""

    def test_add_trading_account(self, db_session: Session, test_users, test_trading_account):
        """Test adding trading account to organization."""
        service = OrganizationService(db_session)

        org = service.create_organization(
            name="Trading Account Test",
            slug="trading-account-test",
            created_by_user_id=test_users[0].user_id
        )

        org_account = service.add_trading_account(
            organization_id=org.organization_id,
            trading_account_id=test_trading_account.trading_account_id,
            added_by=test_users[0].user_id,
            default_permissions=['read', 'trade']
        )

        assert org_account.trading_account_id == test_trading_account.trading_account_id
        assert org_account.default_permissions == ['read', 'trade']
        assert org_account.added_by == test_users[0].user_id

    def test_add_trading_account_duplicate_fails(self, db_session: Session, test_users, test_trading_account):
        """Test adding duplicate trading account fails."""
        service = OrganizationService(db_session)

        org = service.create_organization(
            name="Duplicate Account Test",
            slug="duplicate-account-test",
            created_by_user_id=test_users[0].user_id
        )

        service.add_trading_account(
            organization_id=org.organization_id,
            trading_account_id=test_trading_account.trading_account_id,
            added_by=test_users[0].user_id
        )

        # Try to add again
        with pytest.raises(ValueError, match="already added"):
            service.add_trading_account(
                organization_id=org.organization_id,
                trading_account_id=test_trading_account.trading_account_id,
                added_by=test_users[0].user_id
            )

    def test_list_trading_accounts(self, db_session: Session, test_users, test_trading_account):
        """Test listing organization trading accounts."""
        service = OrganizationService(db_session)

        org = service.create_organization(
            name="List Accounts Test",
            slug="list-accounts-test",
            created_by_user_id=test_users[0].user_id
        )

        service.add_trading_account(
            organization_id=org.organization_id,
            trading_account_id=test_trading_account.trading_account_id,
            added_by=test_users[0].user_id
        )

        accounts = service.list_trading_accounts(org.organization_id)

        assert len(accounts) == 1
        assert accounts[0].trading_account_id == test_trading_account.trading_account_id

    def test_remove_trading_account(self, db_session: Session, test_users, test_trading_account):
        """Test removing trading account from organization."""
        service = OrganizationService(db_session)

        org = service.create_organization(
            name="Remove Account Test",
            slug="remove-account-test",
            created_by_user_id=test_users[0].user_id
        )

        service.add_trading_account(
            organization_id=org.organization_id,
            trading_account_id=test_trading_account.trading_account_id,
            added_by=test_users[0].user_id
        )

        success = service.remove_trading_account(
            org.organization_id,
            test_trading_account.trading_account_id
        )

        assert success is True

        # Verify soft delete
        org_account = db_session.query(OrganizationTradingAccount).filter(
            OrganizationTradingAccount.organization_id == org.organization_id,
            OrganizationTradingAccount.trading_account_id == test_trading_account.trading_account_id
        ).first()

        assert org_account.removed_at is not None


class TestOrganizationPermissions:
    """Test organization permission checks."""

    def test_check_permission_owner(self, db_session: Session, test_users):
        """Test owner has all permissions."""
        service = OrganizationService(db_session)

        org = service.create_organization(
            name="Permission Test",
            slug="permission-test",
            created_by_user_id=test_users[0].user_id
        )

        # Owner should have permission
        has_perm = service.check_permission(
            org.organization_id,
            test_users[0].user_id,
            required_role=OrganizationMemberRole.OWNER
        )

        assert has_perm is True

    def test_check_permission_hierarchy(self, db_session: Session, test_users):
        """Test role hierarchy."""
        service = OrganizationService(db_session)

        org = service.create_organization(
            name="Hierarchy Test",
            slug="hierarchy-test",
            created_by_user_id=test_users[0].user_id
        )

        # Add member
        service.add_member(
            organization_id=org.organization_id,
            user_id=test_users[1].user_id,
            role=OrganizationMemberRole.MEMBER
        )

        # Member should NOT have admin permission
        has_perm = service.check_permission(
            org.organization_id,
            test_users[1].user_id,
            required_role=OrganizationMemberRole.ADMIN
        )

        assert has_perm is False

    def test_is_owner(self, db_session: Session, test_users):
        """Test is_owner helper."""
        service = OrganizationService(db_session)

        org = service.create_organization(
            name="Is Owner Test",
            slug="is-owner-test",
            created_by_user_id=test_users[0].user_id
        )

        assert service.is_owner(org.organization_id, test_users[0].user_id) is True
        assert service.is_owner(org.organization_id, test_users[1].user_id) is False

    def test_is_admin_or_above(self, db_session: Session, test_users):
        """Test is_admin_or_above helper."""
        service = OrganizationService(db_session)

        org = service.create_organization(
            name="Is Admin Test",
            slug="is-admin-test",
            created_by_user_id=test_users[0].user_id
        )

        # Add admin
        service.add_member(
            organization_id=org.organization_id,
            user_id=test_users[1].user_id,
            role=OrganizationMemberRole.ADMIN
        )

        # Add member
        service.add_member(
            organization_id=org.organization_id,
            user_id=test_users[2].user_id,
            role=OrganizationMemberRole.MEMBER
        )

        # Owner is admin or above
        assert service.is_admin_or_above(org.organization_id, test_users[0].user_id) is True

        # Admin is admin or above
        assert service.is_admin_or_above(org.organization_id, test_users[1].user_id) is True

        # Member is NOT admin or above
        assert service.is_admin_or_above(org.organization_id, test_users[2].user_id) is False
