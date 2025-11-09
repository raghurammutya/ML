"""
Organization API endpoints.

Provides:
- Organization CRUD
- Member management
- Invitation system
- Trading account management
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.dependencies import get_current_user
from app.models.user import User
from app.models.organization import OrganizationMemberRole
from app.services.organization_service import OrganizationService
from app.schemas.organization import (
    OrganizationCreate,
    OrganizationUpdate,
    OrganizationResponse,
    OrganizationListResponse,
    OrganizationMemberAdd,
    OrganizationMemberUpdate,
    OrganizationMemberResponse,
    OrganizationMemberListResponse,
    OrganizationInvitationCreate,
    OrganizationInvitationResponse,
    OrganizationInvitationListResponse,
    InvitationAccept,
    OrganizationTradingAccountAdd,
    OrganizationTradingAccountResponse,
    OrganizationTradingAccountListResponse
)


router = APIRouter(prefix="/organizations", tags=["organizations"])


def get_org_service(db: Session = Depends(get_db)) -> OrganizationService:
    """Dependency to get organization service."""
    return OrganizationService(db)


# ==================== Organization Endpoints ====================

@router.post("", response_model=OrganizationResponse, status_code=status.HTTP_201_CREATED)
def create_organization(
    org_data: OrganizationCreate,
    current_user: User = Depends(get_current_user),
    org_service: OrganizationService = Depends(get_org_service)
):
    """
    Create a new organization.

    The current user becomes the owner of the organization.
    """
    try:
        org = org_service.create_organization(
            name=org_data.name,
            slug=org_data.slug,
            created_by_user_id=current_user.user_id,
            description=org_data.description,
            logo_url=org_data.logo_url,
            website=org_data.website,
            settings=org_data.settings
        )

        return org

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("", response_model=OrganizationListResponse)
def list_organizations(
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    org_service: OrganizationService = Depends(get_org_service)
):
    """
    List organizations the current user is a member of.
    """
    organizations = org_service.list_organizations(
        user_id=current_user.user_id,
        limit=limit,
        offset=offset
    )

    return {
        "organizations": organizations,
        "total": len(organizations),
        "limit": limit,
        "offset": offset
    }


@router.get("/{organization_id}", response_model=OrganizationResponse)
def get_organization(
    organization_id: int,
    current_user: User = Depends(get_current_user),
    org_service: OrganizationService = Depends(get_org_service)
):
    """
    Get organization details.

    User must be a member of the organization.
    """
    # Check membership
    member = org_service.get_member(organization_id, current_user.user_id)
    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found or you are not a member"
        )

    org = org_service.get_organization(organization_id)
    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found"
        )

    return org


@router.put("/{organization_id}", response_model=OrganizationResponse)
def update_organization(
    organization_id: int,
    org_data: OrganizationUpdate,
    current_user: User = Depends(get_current_user),
    org_service: OrganizationService = Depends(get_org_service)
):
    """
    Update organization details.

    Requires ADMIN or OWNER role.
    """
    # Check permission
    if not org_service.is_admin_or_above(organization_id, current_user.user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to update this organization"
        )

    org = org_service.update_organization(
        organization_id=organization_id,
        name=org_data.name,
        description=org_data.description,
        logo_url=org_data.logo_url,
        website=org_data.website,
        settings=org_data.settings
    )

    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found"
        )

    return org


@router.delete("/{organization_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_organization(
    organization_id: int,
    current_user: User = Depends(get_current_user),
    org_service: OrganizationService = Depends(get_org_service)
):
    """
    Deactivate an organization.

    Requires OWNER role.
    """
    # Check permission
    if not org_service.is_owner(organization_id, current_user.user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only organization owners can deactivate the organization"
        )

    success = org_service.deactivate_organization(organization_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found"
        )


# ==================== Member Endpoints ====================

@router.get("/{organization_id}/members", response_model=OrganizationMemberListResponse)
def list_members(
    organization_id: int,
    current_user: User = Depends(get_current_user),
    org_service: OrganizationService = Depends(get_org_service)
):
    """
    List organization members.

    User must be a member of the organization.
    """
    # Check membership
    member = org_service.get_member(organization_id, current_user.user_id)
    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found or you are not a member"
        )

    members = org_service.list_members(organization_id)

    return {
        "members": members,
        "total": len(members)
    }


@router.post("/{organization_id}/members", response_model=OrganizationMemberResponse, status_code=status.HTTP_201_CREATED)
def add_member(
    organization_id: int,
    member_data: OrganizationMemberAdd,
    current_user: User = Depends(get_current_user),
    org_service: OrganizationService = Depends(get_org_service)
):
    """
    Add a member to the organization.

    Requires ADMIN or OWNER role.
    """
    # Check permission
    if not org_service.is_admin_or_above(organization_id, current_user.user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to add members"
        )

    try:
        member = org_service.add_member(
            organization_id=organization_id,
            user_id=member_data.user_id,
            role=member_data.role,
            invited_by=current_user.user_id,
            custom_permissions=member_data.custom_permissions
        )

        return member

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.put("/{organization_id}/members/{user_id}", response_model=OrganizationMemberResponse)
def update_member(
    organization_id: int,
    user_id: int,
    member_data: OrganizationMemberUpdate,
    current_user: User = Depends(get_current_user),
    org_service: OrganizationService = Depends(get_org_service)
):
    """
    Update a member's role and permissions.

    Requires ADMIN or OWNER role.
    """
    # Check permission
    if not org_service.is_admin_or_above(organization_id, current_user.user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to update members"
        )

    member = org_service.update_member_role(
        organization_id=organization_id,
        user_id=user_id,
        new_role=member_data.role,
        custom_permissions=member_data.custom_permissions
    )

    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member not found"
        )

    return member


@router.delete("/{organization_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(
    organization_id: int,
    user_id: int,
    current_user: User = Depends(get_current_user),
    org_service: OrganizationService = Depends(get_org_service)
):
    """
    Remove a member from the organization.

    Requires ADMIN or OWNER role.
    Members can also remove themselves.
    """
    # Check permission
    is_self = user_id == current_user.user_id
    is_admin = org_service.is_admin_or_above(organization_id, current_user.user_id)

    if not (is_self or is_admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to remove this member"
        )

    try:
        success = org_service.remove_member(organization_id, user_id)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Member not found"
            )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


# ==================== Invitation Endpoints ====================

@router.post("/{organization_id}/invitations", response_model=OrganizationInvitationResponse, status_code=status.HTTP_201_CREATED)
def create_invitation(
    organization_id: int,
    invitation_data: OrganizationInvitationCreate,
    current_user: User = Depends(get_current_user),
    org_service: OrganizationService = Depends(get_org_service)
):
    """
    Create an organization invitation.

    Requires ADMIN or OWNER role.
    """
    # Check permission
    if not org_service.is_admin_or_above(organization_id, current_user.user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to invite members"
        )

    invitation = org_service.create_invitation(
        organization_id=organization_id,
        email=invitation_data.email,
        invited_role=invitation_data.invited_role,
        invited_by=current_user.user_id,
        expires_in_days=invitation_data.expires_in_days,
        custom_permissions=invitation_data.custom_permissions
    )

    return invitation


@router.post("/invitations/accept", response_model=OrganizationMemberResponse)
def accept_invitation(
    invitation_data: InvitationAccept,
    current_user: User = Depends(get_current_user),
    org_service: OrganizationService = Depends(get_org_service)
):
    """
    Accept an organization invitation.

    The invitation token is typically sent via email.
    """
    try:
        member = org_service.accept_invitation(
            invitation_token=invitation_data.invitation_token,
            user_id=current_user.user_id
        )

        return member

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/invitations/{invitation_token}/reject", status_code=status.HTTP_204_NO_CONTENT)
def reject_invitation(
    invitation_token: str,
    current_user: User = Depends(get_current_user),
    org_service: OrganizationService = Depends(get_org_service)
):
    """
    Reject an organization invitation.
    """
    success = org_service.reject_invitation(invitation_token)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found or already processed"
        )


# ==================== Trading Account Endpoints ====================

@router.post("/{organization_id}/trading-accounts", response_model=OrganizationTradingAccountResponse, status_code=status.HTTP_201_CREATED)
def add_trading_account(
    organization_id: int,
    account_data: OrganizationTradingAccountAdd,
    current_user: User = Depends(get_current_user),
    org_service: OrganizationService = Depends(get_org_service)
):
    """
    Add a trading account to the organization.

    Requires ADMIN or OWNER role.
    """
    # Check permission
    if not org_service.is_admin_or_above(organization_id, current_user.user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to add trading accounts"
        )

    try:
        org_account = org_service.add_trading_account(
            organization_id=organization_id,
            trading_account_id=account_data.trading_account_id,
            added_by=current_user.user_id,
            default_permissions=account_data.default_permissions
        )

        return org_account

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/{organization_id}/trading-accounts", response_model=OrganizationTradingAccountListResponse)
def list_trading_accounts(
    organization_id: int,
    current_user: User = Depends(get_current_user),
    org_service: OrganizationService = Depends(get_org_service)
):
    """
    List trading accounts for the organization.

    User must be a member of the organization.
    """
    # Check membership
    member = org_service.get_member(organization_id, current_user.user_id)
    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found or you are not a member"
        )

    accounts = org_service.list_trading_accounts(organization_id)

    return {
        "trading_accounts": accounts,
        "total": len(accounts)
    }


@router.delete("/{organization_id}/trading-accounts/{trading_account_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_trading_account(
    organization_id: int,
    trading_account_id: int,
    current_user: User = Depends(get_current_user),
    org_service: OrganizationService = Depends(get_org_service)
):
    """
    Remove a trading account from the organization.

    Requires ADMIN or OWNER role.
    """
    # Check permission
    if not org_service.is_admin_or_above(organization_id, current_user.user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to remove trading accounts"
        )

    success = org_service.remove_trading_account(organization_id, trading_account_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trading account not found in organization"
        )
