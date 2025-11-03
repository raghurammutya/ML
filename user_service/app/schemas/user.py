"""
Pydantic schemas for user profile endpoints
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, EmailStr, Field, validator
from datetime import datetime


# User profile schemas

class UserProfileResponse(BaseModel):
    """
    User profile response

    Contains full user information for authenticated user.
    """
    user_id: int
    email: str
    name: str
    phone: Optional[str] = None
    timezone: str
    locale: str
    status: str
    mfa_enabled: bool
    oauth_provider: Optional[str] = None
    roles: List[str] = Field(default_factory=list, description="User roles")
    created_at: str
    last_login_at: Optional[str] = None

    class Config:
        from_attributes = True


class UserPublicProfile(BaseModel):
    """
    Public user profile

    Limited information shown to other users or admins.
    Does not include sensitive data like email, phone, or roles.
    """
    user_id: int
    name: str
    status: str
    created_at: str

    class Config:
        from_attributes = True


class UpdateUserProfileRequest(BaseModel):
    """
    Update user profile request

    Allows updating basic profile information.
    Email changes require verification (not implemented yet).
    """
    name: Optional[str] = Field(None, min_length=1, max_length=255, description="User's full name")
    phone: Optional[str] = Field(None, max_length=20, description="Phone number")
    timezone: Optional[str] = Field(None, max_length=50, description="User timezone (e.g., 'UTC', 'America/New_York')")
    locale: Optional[str] = Field(None, max_length=10, description="User locale (e.g., 'en-US', 'hi-IN')")

    @validator('name')
    def name_not_empty(cls, v):
        if v is not None and v.strip() == "":
            raise ValueError('Name cannot be empty')
        return v


class UpdateUserProfileResponse(BaseModel):
    """Update user profile response"""
    user_id: int
    message: str = "Profile updated successfully"
    updated_fields: List[str] = Field(description="List of fields that were updated")


# User preferences schemas

class UserPreferencesResponse(BaseModel):
    """
    User preferences response

    Returns user-specific preferences and settings.
    """
    user_id: int
    default_trading_account_id: Optional[int] = Field(
        None,
        description="Default trading account for quick access"
    )
    preferences: Dict[str, Any] = Field(
        default_factory=dict,
        description="User preferences as flexible JSON object"
    )

    class Config:
        from_attributes = True


class UpdatePreferencesRequest(BaseModel):
    """
    Update user preferences request

    Supports partial updates - only provided fields will be updated.
    """
    default_trading_account_id: Optional[int] = Field(
        None,
        description="Set default trading account"
    )
    preferences: Optional[Dict[str, Any]] = Field(
        None,
        description="User preferences to update (merged with existing)"
    )


class UpdatePreferencesResponse(BaseModel):
    """Update preferences response"""
    user_id: int
    message: str = "Preferences updated successfully"
    preferences: Dict[str, Any] = Field(description="Updated preferences")


# User deactivation schemas

class DeactivateUserRequest(BaseModel):
    """
    Deactivate user request

    Admin-only endpoint to deactivate user accounts.
    """
    reason: str = Field(
        ...,
        min_length=10,
        max_length=500,
        description="Reason for deactivation (required for audit trail)"
    )
    revoke_sessions: bool = Field(
        default=True,
        description="Whether to revoke all active sessions immediately"
    )


class DeactivateUserResponse(BaseModel):
    """Deactivate user response"""
    user_id: int
    previous_status: str
    new_status: str
    sessions_revoked: int
    message: str


# User search and listing (admin)

class UserSearchRequest(BaseModel):
    """User search request"""
    query: Optional[str] = Field(
        None,
        min_length=1,
        max_length=255,
        description="Search query (email, name)"
    )
    status: Optional[str] = Field(
        None,
        description="Filter by status (active, suspended, deactivated, pending_verification)"
    )
    role: Optional[str] = Field(
        None,
        description="Filter by role (user, admin, compliance)"
    )
    page: int = Field(default=1, ge=1, description="Page number")
    page_size: int = Field(default=50, ge=1, le=100, description="Items per page")


class UserListItem(BaseModel):
    """User list item for search results"""
    user_id: int
    email: str
    name: str
    status: str
    roles: List[str]
    mfa_enabled: bool
    created_at: str
    last_login_at: Optional[str] = None

    class Config:
        from_attributes = True


class UserSearchResponse(BaseModel):
    """User search response"""
    users: List[UserListItem]
    total: int
    page: int
    page_size: int


# Statistics schemas (for admin dashboard)

class UserStatistics(BaseModel):
    """User statistics for admin dashboard"""
    total_users: int
    active_users: int
    pending_verification: int
    suspended_users: int
    deactivated_users: int
    users_with_mfa: int
    users_with_trading_accounts: int
    new_users_last_7_days: int
    new_users_last_30_days: int


# Role management schemas

class AssignRoleRequest(BaseModel):
    """Assign role to user request"""
    role_name: str = Field(
        ...,
        description="Role to assign (user, admin, compliance)"
    )
    granted_by: Optional[int] = Field(
        None,
        description="User ID who granted the role (auto-populated)"
    )


class RevokeRoleRequest(BaseModel):
    """Revoke role from user request"""
    role_name: str = Field(
        ...,
        description="Role to revoke"
    )


class RoleChangeResponse(BaseModel):
    """Role change response"""
    user_id: int
    role_name: str
    action: str  # "assigned" or "revoked"
    message: str
    current_roles: List[str]


# Email verification schemas (for future implementation)

class RequestEmailVerificationResponse(BaseModel):
    """Request email verification response"""
    message: str = "Verification email sent (if account exists)"
    email_sent: bool


class VerifyEmailRequest(BaseModel):
    """Verify email request"""
    token: str = Field(
        ...,
        min_length=32,
        max_length=255,
        description="Email verification token from email"
    )


class VerifyEmailResponse(BaseModel):
    """Verify email response"""
    user_id: int
    email: str
    previous_status: str
    new_status: str
    message: str = "Email verified successfully"
