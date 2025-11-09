"""
Organization support for multi-tenant team collaboration.

Provides classes for:
- Organization: Team/firm entity with members and shared trading accounts
- OrganizationMember: Member with role-based access control
- OrganizationInvitation: Email-based invitation workflow
"""

from typing import Optional, List, Dict, Any
from datetime import datetime


class OrganizationMember:
    """
    Organization member with role-based permissions.

    Roles (hierarchical):
    - OWNER: Full control, can delete org
    - ADMIN: Manage members, settings (cannot delete org)
    - MEMBER: Regular access to org resources
    - VIEWER: Read-only access
    """

    def __init__(self, data: Dict[str, Any], api_client):
        """Initialize organization member from API data."""
        self._data = data
        self._api = api_client

    @property
    def membership_id(self) -> int:
        """Membership ID."""
        return self._data['membership_id']

    @property
    def organization_id(self) -> int:
        """Organization ID."""
        return self._data['organization_id']

    @property
    def user_id(self) -> int:
        """User ID."""
        return self._data['user_id']

    @property
    def role(self) -> str:
        """Member role (OWNER, ADMIN, MEMBER, VIEWER)."""
        return self._data['role']

    @property
    def user_email(self) -> Optional[str]:
        """Member email address."""
        return self._data.get('user_email')

    @property
    def user_name(self) -> Optional[str]:
        """Member name."""
        return self._data.get('user_name')

    @property
    def joined_at(self) -> datetime:
        """When member joined organization."""
        return datetime.fromisoformat(self._data['joined_at'].replace('Z', '+00:00'))

    @property
    def custom_permissions(self) -> Optional[Dict[str, Any]]:
        """Custom permissions for this member."""
        return self._data.get('custom_permissions')

    def __repr__(self) -> str:
        return f"<OrganizationMember user_id={self.user_id} role={self.role}>"


class OrganizationInvitation:
    """
    Organization invitation for adding new members via email.

    Invitations expire after 7 days by default and can be accepted or rejected.
    """

    def __init__(self, data: Dict[str, Any], api_client):
        """Initialize invitation from API data."""
        self._data = data
        self._api = api_client

    @property
    def invitation_id(self) -> int:
        """Invitation ID."""
        return self._data['invitation_id']

    @property
    def organization_id(self) -> int:
        """Organization ID."""
        return self._data['organization_id']

    @property
    def email(self) -> str:
        """Invitee email address."""
        return self._data['email']

    @property
    def invited_role(self) -> str:
        """Role to be assigned when accepted."""
        return self._data['invited_role']

    @property
    def invitation_token(self) -> str:
        """Secure invitation token."""
        return self._data['invitation_token']

    @property
    def status(self) -> str:
        """Invitation status (PENDING, ACCEPTED, REJECTED, EXPIRED)."""
        return self._data['status']

    @property
    def invited_at(self) -> datetime:
        """When invitation was created."""
        return datetime.fromisoformat(self._data['invited_at'].replace('Z', '+00:00'))

    @property
    def expires_at(self) -> datetime:
        """When invitation expires."""
        return datetime.fromisoformat(self._data['expires_at'].replace('Z', '+00:00'))

    @property
    def organization_name(self) -> Optional[str]:
        """Organization name."""
        return self._data.get('organization_name')

    def accept(self) -> OrganizationMember:
        """
        Accept this invitation and join the organization.

        Returns:
            OrganizationMember: The created membership

        Raises:
            ValueError: If invitation is expired or already processed
        """
        response = self._api.post(
            "/v1/organizations/invitations/accept",
            json={"invitation_token": self.invitation_token}
        )
        return OrganizationMember(response, self._api)

    def reject(self) -> None:
        """
        Reject this invitation.

        Raises:
            ValueError: If invitation is already processed
        """
        self._api.post(
            f"/v1/organizations/invitations/{self.invitation_token}/reject"
        )

    def __repr__(self) -> str:
        return f"<OrganizationInvitation email={self.email} role={self.invited_role} status={self.status}>"


class Organization:
    """
    Organization for team/firm collaboration.

    Provides:
    - Member management with role-based access control
    - Invitation workflow for adding new members
    - Shared trading accounts accessible to all members
    - Organization-level settings and permissions

    Example:
        >>> # Create organization
        >>> org = client.Organizations.create(
        ...     name="Trading Firm",
        ...     slug="trading-firm",
        ...     description="Quantitative trading firm"
        ... )
        >>>
        >>> # Invite member
        >>> invitation = org.invite("colleague@example.com", role="MEMBER")
        >>> print(f"Invitation token: {invitation.invitation_token}")
        >>>
        >>> # List members
        >>> for member in org.members():
        ...     print(f"{member.user_email}: {member.role}")
        >>>
        >>> # Add trading account
        >>> org.add_trading_account(account_id=123, permissions=["read", "trade"])
    """

    def __init__(self, data: Dict[str, Any], api_client):
        """Initialize organization from API data."""
        self._data = data
        self._api = api_client

    @property
    def organization_id(self) -> int:
        """Organization ID."""
        return self._data['organization_id']

    @property
    def name(self) -> str:
        """Organization name."""
        return self._data['name']

    @property
    def slug(self) -> str:
        """URL-safe organization identifier."""
        return self._data['slug']

    @property
    def description(self) -> Optional[str]:
        """Organization description."""
        return self._data.get('description')

    @property
    def status(self) -> str:
        """Organization status (PENDING, ACTIVE, SUSPENDED, DEACTIVATED)."""
        return self._data['status']

    @property
    def created_by_user_id(self) -> int:
        """User ID of organization creator."""
        return self._data['created_by_user_id']

    @property
    def created_at(self) -> datetime:
        """When organization was created."""
        return datetime.fromisoformat(self._data['created_at'].replace('Z', '+00:00'))

    @property
    def settings(self) -> Dict[str, Any]:
        """Organization settings (e.g., require_2fa)."""
        return self._data.get('settings', {})

    @property
    def logo_url(self) -> Optional[str]:
        """Organization logo URL."""
        return self._data.get('logo_url')

    @property
    def website(self) -> Optional[str]:
        """Organization website."""
        return self._data.get('website')

    def update(
        self,
        name: Optional[str] = None,
        description: Optional[str] = None,
        logo_url: Optional[str] = None,
        website: Optional[str] = None,
        settings: Optional[Dict[str, Any]] = None
    ) -> 'Organization':
        """
        Update organization details.

        Requires ADMIN or OWNER role.

        Args:
            name: New organization name
            description: New description
            logo_url: New logo URL
            website: New website URL
            settings: New settings dictionary

        Returns:
            Organization: Updated organization
        """
        update_data = {}
        if name is not None:
            update_data['name'] = name
        if description is not None:
            update_data['description'] = description
        if logo_url is not None:
            update_data['logo_url'] = logo_url
        if website is not None:
            update_data['website'] = website
        if settings is not None:
            update_data['settings'] = settings

        response = self._api.put(
            f"/v1/organizations/{self.organization_id}",
            json=update_data
        )
        self._data = response
        return self

    def deactivate(self) -> None:
        """
        Deactivate this organization.

        Requires OWNER role.
        """
        self._api.delete(f"/v1/organizations/{self.organization_id}")

    def members(self) -> List[OrganizationMember]:
        """
        List all organization members.

        Returns:
            List of OrganizationMember objects
        """
        response = self._api.get(f"/v1/organizations/{self.organization_id}/members")
        return [OrganizationMember(m, self._api) for m in response['members']]

    def add_member(
        self,
        user_id: int,
        role: str = "MEMBER",
        custom_permissions: Optional[Dict[str, Any]] = None
    ) -> OrganizationMember:
        """
        Add a member to the organization.

        Requires ADMIN or OWNER role.

        Args:
            user_id: User ID to add
            role: Role to assign (OWNER, ADMIN, MEMBER, VIEWER)
            custom_permissions: Optional custom permissions

        Returns:
            OrganizationMember: The created membership
        """
        response = self._api.post(
            f"/v1/organizations/{self.organization_id}/members",
            json={
                "user_id": user_id,
                "role": role,
                "custom_permissions": custom_permissions
            }
        )
        return OrganizationMember(response, self._api)

    def update_member(
        self,
        user_id: int,
        role: Optional[str] = None,
        custom_permissions: Optional[Dict[str, Any]] = None
    ) -> OrganizationMember:
        """
        Update a member's role and permissions.

        Requires ADMIN or OWNER role.

        Args:
            user_id: User ID to update
            role: New role
            custom_permissions: New custom permissions

        Returns:
            OrganizationMember: Updated membership
        """
        update_data = {}
        if role is not None:
            update_data['role'] = role
        if custom_permissions is not None:
            update_data['custom_permissions'] = custom_permissions

        response = self._api.put(
            f"/v1/organizations/{self.organization_id}/members/{user_id}",
            json=update_data
        )
        return OrganizationMember(response, self._api)

    def remove_member(self, user_id: int) -> None:
        """
        Remove a member from the organization.

        Requires ADMIN or OWNER role. Members can also remove themselves.

        Args:
            user_id: User ID to remove
        """
        self._api.delete(
            f"/v1/organizations/{self.organization_id}/members/{user_id}"
        )

    def invite(
        self,
        email: str,
        role: str = "MEMBER",
        expires_in_days: int = 7,
        custom_permissions: Optional[Dict[str, Any]] = None
    ) -> OrganizationInvitation:
        """
        Create an invitation to join the organization.

        Requires ADMIN or OWNER role.

        Args:
            email: Email address to invite
            role: Role to assign when accepted
            expires_in_days: Days until invitation expires (1-30)
            custom_permissions: Optional custom permissions

        Returns:
            OrganizationInvitation: The created invitation
        """
        response = self._api.post(
            f"/v1/organizations/{self.organization_id}/invitations",
            json={
                "email": email,
                "invited_role": role,
                "expires_in_days": expires_in_days,
                "custom_permissions": custom_permissions
            }
        )
        return OrganizationInvitation(response, self._api)

    def add_trading_account(
        self,
        trading_account_id: int,
        default_permissions: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Add a trading account to the organization.

        Requires ADMIN or OWNER role.

        Args:
            trading_account_id: Trading account ID to add
            default_permissions: Default permissions for members (e.g., ["read", "trade"])

        Returns:
            Dict with account details
        """
        response = self._api.post(
            f"/v1/organizations/{self.organization_id}/trading-accounts",
            json={
                "trading_account_id": trading_account_id,
                "default_permissions": default_permissions or ["read"]
            }
        )
        return response

    def list_trading_accounts(self) -> List[Dict[str, Any]]:
        """
        List trading accounts associated with this organization.

        Returns:
            List of trading account details
        """
        response = self._api.get(
            f"/v1/organizations/{self.organization_id}/trading-accounts"
        )
        return response['trading_accounts']

    def remove_trading_account(self, trading_account_id: int) -> None:
        """
        Remove a trading account from the organization.

        Requires ADMIN or OWNER role.

        Args:
            trading_account_id: Trading account ID to remove
        """
        self._api.delete(
            f"/v1/organizations/{self.organization_id}/trading-accounts/{trading_account_id}"
        )

    def __repr__(self) -> str:
        return f"<Organization id={self.organization_id} name={self.name} status={self.status}>"


class OrganizationsCollection:
    """
    Collection interface for managing organizations.

    Provides methods to:
    - Create new organizations
    - List user's organizations
    - Access organizations by ID
    - Accept/reject invitations

    Example:
        >>> # Create organization
        >>> org = client.Organizations.create(
        ...     name="My Trading Firm",
        ...     slug="my-trading-firm"
        ... )
        >>>
        >>> # List all organizations
        >>> for org in client.Organizations.list():
        ...     print(f"{org.name}: {len(org.members())} members")
        >>>
        >>> # Access specific organization
        >>> org = client.Organizations[123]
        >>> print(f"Organization: {org.name}")
        >>>
        >>> # Accept invitation
        >>> member = client.Organizations.accept_invitation(invitation_token)
    """

    def __init__(self, api_client):
        """Initialize organizations collection."""
        self._api = api_client

    def create(
        self,
        name: str,
        slug: str,
        description: Optional[str] = None,
        logo_url: Optional[str] = None,
        website: Optional[str] = None,
        settings: Optional[Dict[str, Any]] = None
    ) -> Organization:
        """
        Create a new organization.

        The current user becomes the owner of the organization.

        Args:
            name: Organization name
            slug: URL-safe slug (lowercase, alphanumeric, hyphens)
            description: Optional description
            logo_url: Optional logo URL
            website: Optional website URL
            settings: Optional settings dictionary

        Returns:
            Organization: The created organization
        """
        response = self._api.post(
            "/v1/organizations",
            json={
                "name": name,
                "slug": slug,
                "description": description,
                "logo_url": logo_url,
                "website": website,
                "settings": settings or {}
            }
        )
        return Organization(response, self._api)

    def list(self, limit: int = 50, offset: int = 0) -> List[Organization]:
        """
        List organizations the current user is a member of.

        Args:
            limit: Maximum number of organizations to return
            offset: Number of organizations to skip

        Returns:
            List of Organization objects
        """
        response = self._api.get(
            "/v1/organizations",
            params={"limit": limit, "offset": offset}
        )
        return [Organization(org, self._api) for org in response['organizations']]

    def get(self, organization_id: int) -> Organization:
        """
        Get organization by ID.

        User must be a member of the organization.

        Args:
            organization_id: Organization ID

        Returns:
            Organization object
        """
        response = self._api.get(f"/v1/organizations/{organization_id}")
        return Organization(response, self._api)

    def __getitem__(self, organization_id: int) -> Organization:
        """
        Access organization by ID using dictionary syntax.

        Example:
            >>> org = client.Organizations[123]
        """
        return self.get(organization_id)

    def accept_invitation(self, invitation_token: str) -> OrganizationMember:
        """
        Accept an organization invitation.

        Args:
            invitation_token: Invitation token from email

        Returns:
            OrganizationMember: The created membership
        """
        response = self._api.post(
            "/v1/organizations/invitations/accept",
            json={"invitation_token": invitation_token}
        )
        return OrganizationMember(response, self._api)

    def reject_invitation(self, invitation_token: str) -> None:
        """
        Reject an organization invitation.

        Args:
            invitation_token: Invitation token from email
        """
        self._api.post(f"/v1/organizations/invitations/{invitation_token}/reject")

    def __repr__(self) -> str:
        return "<OrganizationsCollection>"
