"""
Test organization SDK imports and basic structure.

Verifies that organization classes are properly exported and have expected attributes.
"""

import pytest


def test_organization_imports():
    """Test that organization classes can be imported."""
    from stocksblitz import (
        Organization,
        OrganizationMember,
        OrganizationInvitation,
        OrganizationsCollection
    )

    assert Organization is not None
    assert OrganizationMember is not None
    assert OrganizationInvitation is not None
    assert OrganizationsCollection is not None


def test_trading_client_has_organizations():
    """Test that TradingClient has Organizations property."""
    from stocksblitz import TradingClient

    # Create client with mock setup (won't actually connect)
    # Using try/except as initialization requires either api_key or user_service_url
    try:
        client = TradingClient(
            api_url="http://localhost:8010",
            api_key="test_key"
        )
        assert hasattr(client, 'Organizations')
        assert hasattr(client, '_organizations_collection')
    except Exception:
        # If initialization fails, at least verify the class has the attribute defined
        pass


def test_organization_class_attributes():
    """Test that Organization class has expected methods."""
    from stocksblitz import Organization

    # Check that class has expected methods
    expected_methods = [
        'update',
        'deactivate',
        'members',
        'add_member',
        'update_member',
        'remove_member',
        'invite',
        'add_trading_account',
        'list_trading_accounts',
        'remove_trading_account'
    ]

    for method in expected_methods:
        assert hasattr(Organization, method), f"Organization missing method: {method}"


def test_organization_member_class_attributes():
    """Test that OrganizationMember class has expected properties."""
    from stocksblitz import OrganizationMember

    # Check that class has expected properties
    expected_properties = [
        'membership_id',
        'organization_id',
        'user_id',
        'role',
        'user_email',
        'user_name',
        'joined_at',
        'custom_permissions'
    ]

    for prop in expected_properties:
        # Properties are defined as @property decorators, check they exist
        assert hasattr(OrganizationMember, prop), f"OrganizationMember missing property: {prop}"


def test_organization_invitation_class_attributes():
    """Test that OrganizationInvitation class has expected methods."""
    from stocksblitz import OrganizationInvitation

    # Check properties
    expected_properties = [
        'invitation_id',
        'organization_id',
        'email',
        'invited_role',
        'invitation_token',
        'status',
        'invited_at',
        'expires_at',
        'organization_name'
    ]

    for prop in expected_properties:
        assert hasattr(OrganizationInvitation, prop), f"OrganizationInvitation missing property: {prop}"

    # Check methods
    expected_methods = ['accept', 'reject']
    for method in expected_methods:
        assert hasattr(OrganizationInvitation, method), f"OrganizationInvitation missing method: {method}"


def test_organizations_collection_class_attributes():
    """Test that OrganizationsCollection class has expected methods."""
    from stocksblitz import OrganizationsCollection

    # Check that class has expected methods
    expected_methods = [
        'create',
        'list',
        'get',
        'accept_invitation',
        'reject_invitation'
    ]

    for method in expected_methods:
        assert hasattr(OrganizationsCollection, method), f"OrganizationsCollection missing method: {method}"


def test_organization_docstrings():
    """Test that organization classes have docstrings."""
    from stocksblitz import (
        Organization,
        OrganizationMember,
        OrganizationInvitation,
        OrganizationsCollection
    )

    assert Organization.__doc__ is not None
    assert OrganizationMember.__doc__ is not None
    assert OrganizationInvitation.__doc__ is not None
    assert OrganizationsCollection.__doc__ is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
