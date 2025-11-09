"""
Organization feature demonstration.

Shows how to use the SDK's organization support for team collaboration.

Requirements:
- user_service running with organizations feature
- Two test users for demonstrating invitations
"""

from stocksblitz import TradingClient

# Configuration
USER_SERVICE_URL = "http://localhost:8011"
API_URL = "http://localhost:8010"  # Backend API


def demo_create_organization(client: TradingClient):
    """Demonstrate creating an organization."""
    print("\n=== Creating Organization ===")

    org = client.Organizations.create(
        name="Demo Trading Firm",
        slug="demo-trading-firm",
        description="A quantitative trading firm for demonstration",
        website="https://demo-firm.example.com",
        settings={
            "require_2fa": True,
            "max_members": 50
        }
    )

    print(f"✓ Created organization: {org.name}")
    print(f"  ID: {org.organization_id}")
    print(f"  Slug: {org.slug}")
    print(f"  Status: {org.status}")
    print(f"  Created at: {org.created_at}")

    return org


def demo_list_organizations(client: TradingClient):
    """Demonstrate listing organizations."""
    print("\n=== Listing Organizations ===")

    orgs = client.Organizations.list()

    print(f"Found {len(orgs)} organization(s):")
    for org in orgs:
        print(f"  - {org.name} ({org.slug})")
        print(f"    Status: {org.status}")
        print(f"    Members: {len(org.members())}")


def demo_member_management(org):
    """Demonstrate member management."""
    print("\n=== Managing Members ===")

    # List current members
    members = org.members()
    print(f"Current members: {len(members)}")
    for member in members:
        print(f"  - {member.user_email or f'User {member.user_id}'}: {member.role}")
        print(f"    Joined: {member.joined_at}")

    # Note: Adding members requires knowing user IDs
    # In real usage, you'd get this from user lookup or invitation acceptance
    print("\n✓ Member management operations demonstrated")


def demo_invitations(org):
    """Demonstrate invitation workflow."""
    print("\n=== Creating Invitations ===")

    # Create invitation for a colleague
    invitation = org.invite(
        email="colleague@example.com",
        role="MEMBER",
        expires_in_days=7
    )

    print(f"✓ Created invitation for {invitation.email}")
    print(f"  Role: {invitation.invited_role}")
    print(f"  Token: {invitation.invitation_token}")
    print(f"  Status: {invitation.status}")
    print(f"  Expires at: {invitation.expires_at}")

    print("\n📧 In practice, you would:")
    print("  1. Email the invitation token to the invitee")
    print("  2. They create an account (if needed)")
    print("  3. They call: client.Organizations.accept_invitation(token)")

    return invitation


def demo_accept_invitation(invitation_token: str):
    """
    Demonstrate accepting an invitation (run as invitee).

    This would typically be run by a different user.
    """
    print("\n=== Accepting Invitation (as invitee) ===")

    # The invitee would create their own client
    invitee_client = TradingClient.from_credentials(
        api_url=API_URL,
        user_service_url=USER_SERVICE_URL,
        username="colleague@example.com",
        password="their_password"
    )

    # Accept the invitation
    member = invitee_client.Organizations.accept_invitation(invitation_token)

    print(f"✓ Accepted invitation!")
    print(f"  Organization ID: {member.organization_id}")
    print(f"  Role: {member.role}")
    print(f"  Joined at: {member.joined_at}")


def demo_update_organization(org):
    """Demonstrate updating organization details."""
    print("\n=== Updating Organization ===")

    org.update(
        description="Updated: A quantitative trading firm",
        settings={
            "require_2fa": True,
            "max_members": 100,
            "allow_api_access": True
        }
    )

    print(f"✓ Updated organization: {org.name}")
    print(f"  New description: {org.description}")
    print(f"  Settings: {org.settings}")


def demo_update_member_role(org, user_id: int):
    """Demonstrate updating member role."""
    print("\n=== Updating Member Role ===")

    # Promote member to admin
    member = org.update_member(
        user_id=user_id,
        role="ADMIN"
    )

    print(f"✓ Updated member role")
    print(f"  User ID: {member.user_id}")
    print(f"  New role: {member.role}")


def demo_trading_accounts(org):
    """Demonstrate managing shared trading accounts."""
    print("\n=== Managing Shared Trading Accounts ===")

    print("Note: This requires an existing trading account ID")
    print("In practice, you would:")
    print("  1. Get trading account ID from client.Accounts")
    print("  2. Add it to organization: org.add_trading_account(account_id)")
    print("  3. All members get access based on default permissions")

    # Example (commented out as it needs real account ID):
    # org.add_trading_account(
    #     trading_account_id=123,
    #     default_permissions=["read", "trade"]
    # )

    # List accounts (will be empty in demo)
    accounts = org.list_trading_accounts()
    print(f"\nOrganization has {len(accounts)} shared trading account(s)")


def demo_access_by_id(client: TradingClient, org_id: int):
    """Demonstrate accessing organization by ID."""
    print(f"\n=== Accessing Organization by ID ===")

    # Dictionary-style access
    org = client.Organizations[org_id]

    print(f"✓ Accessed organization: {org.name}")
    print(f"  ID: {org.organization_id}")
    print(f"  Status: {org.status}")


def demo_remove_member(org, user_id: int):
    """Demonstrate removing a member."""
    print("\n=== Removing Member ===")

    org.remove_member(user_id)
    print(f"✓ Removed user {user_id} from organization")


def demo_deactivate_organization(org):
    """Demonstrate deactivating an organization."""
    print("\n=== Deactivating Organization ===")

    print(f"⚠️  About to deactivate: {org.name}")
    print("    (Requires OWNER role)")

    # Uncomment to actually deactivate:
    # org.deactivate()
    # print("✓ Organization deactivated")

    print("✓ Deactivation demonstrated (not executed)")


def main():
    """Run organization demonstration."""
    print("=" * 60)
    print("Organization Feature Demonstration")
    print("=" * 60)

    # Authenticate as organization owner
    print("\nAuthenticating as organization owner...")
    client = TradingClient.from_credentials(
        api_url=API_URL,
        user_service_url=USER_SERVICE_URL,
        username="org_owner@example.com",
        password="secure_password123"
    )
    print("✓ Authenticated successfully")

    try:
        # Create organization
        org = demo_create_organization(client)

        # List organizations
        demo_list_organizations(client)

        # Access by ID
        demo_access_by_id(client, org.organization_id)

        # Manage members
        demo_member_management(org)

        # Create invitation
        invitation = demo_invitations(org)

        # Update organization
        demo_update_organization(org)

        # Manage trading accounts
        demo_trading_accounts(org)

        # Demo invitation acceptance (commented out - needs second user)
        # demo_accept_invitation(invitation.invitation_token)

        # Demo role update (commented out - needs member user ID)
        # demo_update_member_role(org, member_user_id=2)

        # Demo member removal (commented out)
        # demo_remove_member(org, user_id=2)

        # Demo deactivation (commented out)
        # demo_deactivate_organization(org)

        print("\n" + "=" * 60)
        print("✓ Demonstration completed successfully!")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
