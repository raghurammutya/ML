"""
Pydantic schemas for organization endpoints.
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator

from app.models.organization import OrganizationStatus, OrganizationMemberRole


# ==================== Organization Schemas ====================

class OrganizationBase(BaseModel):
    """Base organization schema."""
    name: str = Field(..., min_length=1, max_length=255, description="Organization name")
    slug: str = Field(..., min_length=1, max_length=100, pattern="^[a-z0-9-]+$", description="URL-safe slug")
    description: Optional[str] = Field(None, description="Organization description")
    logo_url: Optional[str] = Field(None, max_length=500, description="Logo URL")
    website: Optional[str] = Field(None, max_length=500, description="Website URL")


class OrganizationCreate(OrganizationBase):
    """Schema for creating an organization."""
    settings: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Custom settings")


class OrganizationUpdate(BaseModel):
    """Schema for updating an organization."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    logo_url: Optional[str] = Field(None, max_length=500)
    website: Optional[str] = Field(None, max_length=500)
    settings: Optional[Dict[str, Any]] = None


class OrganizationResponse(OrganizationBase):
    """Schema for organization response."""
    organization_id: int
    status: OrganizationStatus
    settings: Dict[str, Any]
    created_by_user_id: int
    created_at: datetime
    updated_at: datetime
    deactivated_at: Optional[datetime] = None

    # Additional computed fields
    member_count: Optional[int] = None
    trading_account_count: Optional[int] = None

    class Config:
        from_attributes = True


# ==================== Member Schemas ====================

class OrganizationMemberBase(BaseModel):
    """Base member schema."""
    user_id: int
    role: OrganizationMemberRole
    custom_permissions: Optional[Dict[str, Any]] = None


class OrganizationMemberAdd(BaseModel):
    """Schema for adding a member."""
    user_id: int
    role: OrganizationMemberRole = OrganizationMemberRole.MEMBER
    custom_permissions: Optional[Dict[str, Any]] = None


class OrganizationMemberUpdate(BaseModel):
    """Schema for updating a member."""
    role: Optional[OrganizationMemberRole] = None
    custom_permissions: Optional[Dict[str, Any]] = None


class OrganizationMemberResponse(BaseModel):
    """Schema for member response."""
    membership_id: int
    organization_id: int
    user_id: int
    role: OrganizationMemberRole
    custom_permissions: Optional[Dict[str, Any]] = None
    invited_by: Optional[int] = None
    invited_at: Optional[datetime] = None
    accepted_at: Optional[datetime] = None
    joined_at: datetime
    removed_at: Optional[datetime] = None

    # User details (if joined)
    user_email: Optional[str] = None
    user_name: Optional[str] = None

    class Config:
        from_attributes = True


# ==================== Invitation Schemas ====================

class OrganizationInvitationCreate(BaseModel):
    """Schema for creating an invitation."""
    email: str = Field(..., description="Invitee email address")
    invited_role: OrganizationMemberRole = OrganizationMemberRole.MEMBER
    custom_permissions: Optional[Dict[str, Any]] = None
    expires_in_days: int = Field(default=7, ge=1, le=30, description="Days until expiry")

    @field_validator('email')
    @classmethod
    def validate_email(cls, v):
        """Validate email format."""
        if '@' not in v:
            raise ValueError('Invalid email address')
        return v.lower()


class OrganizationInvitationResponse(BaseModel):
    """Schema for invitation response."""
    invitation_id: int
    organization_id: int
    email: str
    invited_role: OrganizationMemberRole
    custom_permissions: Optional[Dict[str, Any]] = None
    invitation_token: str
    invited_by: int
    invited_at: datetime
    expires_at: datetime
    status: str
    accepted_at: Optional[datetime] = None
    accepted_by_user_id: Optional[int] = None
    rejected_at: Optional[datetime] = None

    # Organization details
    organization_name: Optional[str] = None
    organization_slug: Optional[str] = None

    class Config:
        from_attributes = True


class InvitationAccept(BaseModel):
    """Schema for accepting an invitation."""
    invitation_token: str = Field(..., description="Invitation token from email")


# ==================== Trading Account Schemas ====================

class OrganizationTradingAccountAdd(BaseModel):
    """Schema for adding a trading account to organization."""
    trading_account_id: int
    default_permissions: List[str] = Field(default=['read'], description="Default permissions")

    @field_validator('default_permissions')
    @classmethod
    def validate_permissions(cls, v):
        """Validate permissions."""
        valid_permissions = {'read', 'trade', 'admin'}
        for perm in v:
            if perm not in valid_permissions:
                raise ValueError(f"Invalid permission: {perm}. Must be one of {valid_permissions}")
        return v


class OrganizationTradingAccountResponse(BaseModel):
    """Schema for organization trading account response."""
    id: int
    organization_id: int
    trading_account_id: int
    default_permissions: List[str]
    added_by: int
    added_at: datetime
    removed_at: Optional[datetime] = None

    # Trading account details (if joined)
    account_broker: Optional[str] = None
    account_nickname: Optional[str] = None
    account_status: Optional[str] = None

    class Config:
        from_attributes = True


# ==================== List Responses ====================

class OrganizationListResponse(BaseModel):
    """Schema for organization list response."""
    organizations: List[OrganizationResponse]
    total: int
    limit: int
    offset: int


class OrganizationMemberListResponse(BaseModel):
    """Schema for member list response."""
    members: List[OrganizationMemberResponse]
    total: int


class OrganizationTradingAccountListResponse(BaseModel):
    """Schema for trading account list response."""
    trading_accounts: List[OrganizationTradingAccountResponse]
    total: int


class OrganizationInvitationListResponse(BaseModel):
    """Schema for invitation list response."""
    invitations: List[OrganizationInvitationResponse]
    total: int
