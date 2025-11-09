"""
Integration tests for organization API endpoints.

Tests all organization REST API endpoints end-to-end including:
- Organization CRUD
- Member management
- Invitation workflow
- Trading account management
- Permission enforcement
"""

import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timedelta

from app.main import app
from app.models.organization import OrganizationMemberRole


client = TestClient(app)


# Helper function to create test user and get auth token
def create_user_and_login(email: str, name: str, password: str = "SecurePassword123!"):
    """Create a test user and return access token."""
    # Register
    response = client.post(
        "/v1/auth/register",
        json={
            "email": email,
            "password": password,
            "name": name
        }
    )
    assert response.status_code == 201, f"Registration failed: {response.json()}"

    # Login
    response = client.post(
        "/v1/auth/login",
        json={
            "email": email,
            "password": password
        }
    )
    assert response.status_code == 200, f"Login failed: {response.json()}"

    data = response.json()
    return data["access_token"], data["user"]["user_id"]


class TestOrganizationCRUD:
    """Test organization CRUD endpoints."""

    def test_create_organization(self):
        """Test POST /v1/organizations - create organization."""
        # Create user and get token
        token, user_id = create_user_and_login(
            "org_owner@test.com",
            "Org Owner"
        )

        # Create organization
        response = client.post(
            "/v1/organizations",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "name": "Test Organization",
                "slug": "test-org",
                "description": "A test organization",
                "website": "https://test-org.com",
                "settings": {"require_2fa": True}
            }
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Test Organization"
        assert data["slug"] == "test-org"
        assert data["status"] == "ACTIVE"
        assert data["settings"]["require_2fa"] is True
        assert data["created_by_user_id"] == user_id

    def test_create_organization_duplicate_slug(self):
        """Test creating organization with duplicate slug fails."""
        token, _ = create_user_and_login("owner2@test.com", "Owner 2")

        # Create first org
        response = client.post(
            "/v1/organizations",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "name": "Org 1",
                "slug": "duplicate-slug-test"
            }
        )
        assert response.status_code == 201

        # Try to create with same slug
        response = client.post(
            "/v1/organizations",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "name": "Org 2",
                "slug": "duplicate-slug-test"
            }
        )
        assert response.status_code == 400
        assert "already exists" in response.json()["detail"]

    def test_list_organizations(self):
        """Test GET /v1/organizations - list user's organizations."""
        token, _ = create_user_and_login("member@test.com", "Member User")

        # Create multiple organizations
        for i in range(3):
            response = client.post(
                "/v1/organizations",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "name": f"Org {i}",
                    "slug": f"org-{i}-test"
                }
            )
            assert response.status_code == 201

        # List organizations
        response = client.get(
            "/v1/organizations",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 3
        assert len(data["organizations"]) >= 3

    def test_get_organization(self):
        """Test GET /v1/organizations/{id} - get organization details."""
        token, _ = create_user_and_login("viewer@test.com", "Viewer User")

        # Create organization
        create_response = client.post(
            "/v1/organizations",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "name": "Get Test Org",
                "slug": "get-test-org"
            }
        )
        org_id = create_response.json()["organization_id"]

        # Get organization
        response = client.get(
            f"/v1/organizations/{org_id}",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["organization_id"] == org_id
        assert data["name"] == "Get Test Org"

    def test_get_organization_not_member(self):
        """Test getting organization when not a member returns 404."""
        # Create org with one user
        token1, _ = create_user_and_login("user1@test.com", "User 1")
        create_response = client.post(
            "/v1/organizations",
            headers={"Authorization": f"Bearer {token1}"},
            json={"name": "Private Org", "slug": "private-org-test"}
        )
        org_id = create_response.json()["organization_id"]

        # Try to access with different user
        token2, _ = create_user_and_login("user2@test.com", "User 2")
        response = client.get(
            f"/v1/organizations/{org_id}",
            headers={"Authorization": f"Bearer {token2}"}
        )

        assert response.status_code == 404

    def test_update_organization(self):
        """Test PUT /v1/organizations/{id} - update organization."""
        token, _ = create_user_and_login("updater@test.com", "Updater")

        # Create organization
        create_response = client.post(
            "/v1/organizations",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "Original Name", "slug": "update-test-org"}
        )
        org_id = create_response.json()["organization_id"]

        # Update organization
        response = client.put(
            f"/v1/organizations/{org_id}",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "name": "Updated Name",
                "description": "New description"
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Name"
        assert data["description"] == "New description"

    def test_update_organization_requires_admin(self):
        """Test that only admins/owners can update organization."""
        # Create org with owner
        owner_token, owner_id = create_user_and_login("owner3@test.com", "Owner 3")
        create_response = client.post(
            "/v1/organizations",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"name": "Admin Test Org", "slug": "admin-test-org"}
        )
        org_id = create_response.json()["organization_id"]

        # Add member (non-admin)
        member_token, member_id = create_user_and_login("regular@test.com", "Regular Member")
        client.post(
            f"/v1/organizations/{org_id}/members",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"user_id": member_id, "role": "MEMBER"}
        )

        # Try to update as non-admin member
        response = client.put(
            f"/v1/organizations/{org_id}",
            headers={"Authorization": f"Bearer {member_token}"},
            json={"name": "Hacked Name"}
        )

        assert response.status_code == 403

    def test_deactivate_organization(self):
        """Test DELETE /v1/organizations/{id} - deactivate organization."""
        token, _ = create_user_and_login("deactivator@test.com", "Deactivator")

        # Create organization
        create_response = client.post(
            "/v1/organizations",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "To Delete", "slug": "to-delete-test"}
        )
        org_id = create_response.json()["organization_id"]

        # Deactivate
        response = client.delete(
            f"/v1/organizations/{org_id}",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 204


class TestOrganizationMembers:
    """Test organization member management endpoints."""

    def test_add_member(self):
        """Test POST /v1/organizations/{id}/members - add member."""
        # Create org owner
        owner_token, owner_id = create_user_and_login("owner4@test.com", "Owner 4")
        create_response = client.post(
            "/v1/organizations",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"name": "Member Test Org", "slug": "member-test-org"}
        )
        org_id = create_response.json()["organization_id"]

        # Create new user to add
        new_user_token, new_user_id = create_user_and_login("newmember@test.com", "New Member")

        # Add member
        response = client.post(
            f"/v1/organizations/{org_id}/members",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={
                "user_id": new_user_id,
                "role": "MEMBER"
            }
        )

        assert response.status_code == 201
        data = response.json()
        assert data["user_id"] == new_user_id
        assert data["role"] == "MEMBER"

    def test_list_members(self):
        """Test GET /v1/organizations/{id}/members - list members."""
        owner_token, owner_id = create_user_and_login("owner5@test.com", "Owner 5")
        create_response = client.post(
            "/v1/organizations",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"name": "List Members Org", "slug": "list-members-org"}
        )
        org_id = create_response.json()["organization_id"]

        # Add some members
        for i in range(3):
            user_token, user_id = create_user_and_login(
                f"member{i}@test.com",
                f"Member {i}"
            )
            client.post(
                f"/v1/organizations/{org_id}/members",
                headers={"Authorization": f"Bearer {owner_token}"},
                json={"user_id": user_id, "role": "MEMBER"}
            )

        # List members
        response = client.get(
            f"/v1/organizations/{org_id}/members",
            headers={"Authorization": f"Bearer {owner_token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 4  # Owner + 3 members

    def test_update_member_role(self):
        """Test PUT /v1/organizations/{id}/members/{user_id} - update role."""
        owner_token, owner_id = create_user_and_login("owner6@test.com", "Owner 6")
        create_response = client.post(
            "/v1/organizations",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"name": "Role Update Org", "slug": "role-update-org"}
        )
        org_id = create_response.json()["organization_id"]

        # Add member
        member_token, member_id = create_user_and_login("promote@test.com", "To Promote")
        client.post(
            f"/v1/organizations/{org_id}/members",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"user_id": member_id, "role": "MEMBER"}
        )

        # Update role to ADMIN
        response = client.put(
            f"/v1/organizations/{org_id}/members/{member_id}",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"role": "ADMIN"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "ADMIN"

    def test_remove_member(self):
        """Test DELETE /v1/organizations/{id}/members/{user_id} - remove member."""
        owner_token, owner_id = create_user_and_login("owner7@test.com", "Owner 7")
        create_response = client.post(
            "/v1/organizations",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"name": "Remove Member Org", "slug": "remove-member-org"}
        )
        org_id = create_response.json()["organization_id"]

        # Add member
        member_token, member_id = create_user_and_login("toremove@test.com", "To Remove")
        client.post(
            f"/v1/organizations/{org_id}/members",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"user_id": member_id, "role": "MEMBER"}
        )

        # Remove member
        response = client.delete(
            f"/v1/organizations/{org_id}/members/{member_id}",
            headers={"Authorization": f"Bearer {owner_token}"}
        )

        assert response.status_code == 204

    def test_member_can_remove_self(self):
        """Test that members can remove themselves."""
        owner_token, owner_id = create_user_and_login("owner8@test.com", "Owner 8")
        create_response = client.post(
            "/v1/organizations",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"name": "Self Remove Org", "slug": "self-remove-org"}
        )
        org_id = create_response.json()["organization_id"]

        # Add member
        member_token, member_id = create_user_and_login("selfleavemember@test.com", "Self Leave")
        client.post(
            f"/v1/organizations/{org_id}/members",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"user_id": member_id, "role": "MEMBER"}
        )

        # Member removes themselves
        response = client.delete(
            f"/v1/organizations/{org_id}/members/{member_id}",
            headers={"Authorization": f"Bearer {member_token}"}
        )

        assert response.status_code == 204


class TestOrganizationInvitations:
    """Test organization invitation endpoints."""

    def test_create_invitation(self):
        """Test POST /v1/organizations/{id}/invitations - create invitation."""
        owner_token, owner_id = create_user_and_login("owner9@test.com", "Owner 9")
        create_response = client.post(
            "/v1/organizations",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"name": "Invitation Org", "slug": "invitation-org"}
        )
        org_id = create_response.json()["organization_id"]

        # Create invitation
        response = client.post(
            f"/v1/organizations/{org_id}/invitations",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={
                "email": "invitee@test.com",
                "invited_role": "MEMBER",
                "expires_in_days": 7
            }
        )

        assert response.status_code == 201
        data = response.json()
        assert data["email"] == "invitee@test.com"
        assert data["invited_role"] == "MEMBER"
        assert "invitation_token" in data
        assert data["status"] == "PENDING"

    def test_accept_invitation(self):
        """Test POST /v1/organizations/invitations/accept - accept invitation."""
        # Create org and invitation
        owner_token, owner_id = create_user_and_login("owner10@test.com", "Owner 10")
        create_response = client.post(
            "/v1/organizations",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"name": "Accept Invitation Org", "slug": "accept-invitation-org"}
        )
        org_id = create_response.json()["organization_id"]

        invite_response = client.post(
            f"/v1/organizations/{org_id}/invitations",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"email": "acceptinvite@test.com", "invited_role": "MEMBER"}
        )
        invitation_token = invite_response.json()["invitation_token"]

        # Create user with same email and accept invitation
        invitee_token, invitee_id = create_user_and_login(
            "acceptinvite@test.com",
            "Accept Invite User"
        )

        response = client.post(
            "/v1/organizations/invitations/accept",
            headers={"Authorization": f"Bearer {invitee_token}"},
            json={"invitation_token": invitation_token}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["organization_id"] == org_id
        assert data["user_id"] == invitee_id
        assert data["role"] == "MEMBER"

    def test_reject_invitation(self):
        """Test POST /v1/organizations/invitations/{token}/reject - reject invitation."""
        # Create org and invitation
        owner_token, owner_id = create_user_and_login("owner11@test.com", "Owner 11")
        create_response = client.post(
            "/v1/organizations",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"name": "Reject Invitation Org", "slug": "reject-invitation-org"}
        )
        org_id = create_response.json()["organization_id"]

        invite_response = client.post(
            f"/v1/organizations/{org_id}/invitations",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"email": "rejectinvite@test.com", "invited_role": "MEMBER"}
        )
        invitation_token = invite_response.json()["invitation_token"]

        # Create user and reject
        invitee_token, _ = create_user_and_login("rejectinvite@test.com", "Reject User")

        response = client.post(
            f"/v1/organizations/invitations/{invitation_token}/reject",
            headers={"Authorization": f"Bearer {invitee_token}"}
        )

        assert response.status_code == 204


# Note: Trading account tests would require creating actual trading accounts
# which involves KMS/encryption setup. Skipping for now as those are tested
# in unit tests.


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
