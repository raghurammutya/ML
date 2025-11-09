"""
User profile endpoints
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.redis_client import get_redis, RedisClient
from app.api.dependencies import get_current_user, get_current_active_user
from app.models import User
from app.services.user_service import UserService
from app.schemas.user import (
    UserProfileResponse,
    UserPublicProfile,
    UpdateUserProfileRequest,
    UpdateUserProfileResponse,
    UserPreferencesResponse,
    UpdatePreferencesRequest,
    UpdatePreferencesResponse,
    DeactivateUserRequest,
    DeactivateUserResponse,
    UserSearchRequest,
    UserSearchResponse,
    UserListItem,
    UserStatistics,
    AssignRoleRequest,
    RevokeRoleRequest,
    RoleChangeResponse
)


router = APIRouter()


def get_user_service(
    db: Session = Depends(get_db),
    redis: RedisClient = Depends(get_redis)
) -> UserService:
    """
    Get user service instance

    Args:
        db: Database session
        redis: Redis client

    Returns:
        UserService instance
    """
    return UserService(db, redis)


@router.get("/me", response_model=UserProfileResponse)
async def get_current_user_profile(
    current_user: User = Depends(get_current_active_user),
    user_service: UserService = Depends(get_user_service)
):
    """
    Get current user's profile

    Returns full profile information for the authenticated user.

    **Returns:**
    - user_id: User ID
    - email: Email address
    - name: Full name
    - phone: Phone number (optional)
    - timezone: User timezone
    - locale: User locale
    - status: Account status
    - mfa_enabled: Whether MFA is enabled
    - oauth_provider: OAuth provider if used
    - roles: List of assigned roles
    - created_at: Account creation timestamp
    - last_login_at: Last login timestamp

    **Authentication:**
    - Requires valid access token
    - User must be in active status

    **Example Response:**
    ```json
    {
      "user_id": 123,
      "email": "user@example.com",
      "name": "John Doe",
      "phone": "+1234567890",
      "timezone": "America/New_York",
      "locale": "en-US",
      "status": "active",
      "mfa_enabled": true,
      "oauth_provider": null,
      "roles": ["user", "trader"],
      "created_at": "2025-11-01T10:00:00Z",
      "last_login_at": "2025-11-03T15:30:00Z"
    }
    ```
    """
    # Extract roles
    roles = [ur.role.name for ur in current_user.roles]

    return UserProfileResponse(
        user_id=current_user.user_id,
        email=current_user.email,
        name=current_user.name,
        phone=current_user.phone,
        timezone=current_user.timezone,
        locale=current_user.locale,
        status=current_user.status.value,
        mfa_enabled=current_user.mfa_enabled,
        oauth_provider=current_user.oauth_provider,
        roles=roles,
        created_at=current_user.created_at.isoformat(),
        last_login_at=current_user.last_login_at.isoformat() if current_user.last_login_at else None
    )


@router.patch("/me", response_model=UpdateUserProfileResponse)
async def update_current_user_profile(
    request_data: UpdateUserProfileRequest,
    current_user: User = Depends(get_current_active_user),
    user_service: UserService = Depends(get_user_service)
):
    """
    Update current user's profile

    Allows updating basic profile information. Only provided fields will be updated.

    **Request Body:**
    - name: Full name (optional)
    - phone: Phone number (optional)
    - timezone: Timezone (optional, e.g., "America/New_York", "UTC")
    - locale: Locale (optional, e.g., "en-US", "hi-IN")

    **Returns:**
    - user_id: User ID
    - message: Success message
    - updated_fields: List of fields that were updated

    **Authentication:**
    - Requires valid access token
    - User must be in active status

    **Example Request:**
    ```json
    {
      "name": "John Smith",
      "timezone": "America/Los_Angeles"
    }
    ```

    **Example Response:**
    ```json
    {
      "user_id": 123,
      "message": "Profile updated successfully",
      "updated_fields": ["name", "timezone"]
    }
    ```

    **Notes:**
    - Email changes are not supported via this endpoint (requires verification)
    - Password changes should use password reset flow
    """
    try:
        user, updated_fields = user_service.update_user_profile(
            user_id=current_user.user_id,
            name=request_data.name,
            phone=request_data.phone,
            timezone=request_data.timezone,
            locale=request_data.locale
        )

        return UpdateUserProfileResponse(
            user_id=user.user_id,
            message="Profile updated successfully",
            updated_fields=updated_fields
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/{user_id}", response_model=UserPublicProfile)
async def get_user_by_id(
    user_id: int,
    current_user: User = Depends(get_current_active_user),
    user_service: UserService = Depends(get_user_service)
):
    """
    Get user profile by ID

    Returns limited public profile information.
    Admin users can see more details.

    **Path Parameters:**
    - user_id: User ID to fetch

    **Returns:**
    - user_id: User ID
    - name: Full name
    - status: Account status
    - created_at: Account creation timestamp

    **Authentication:**
    - Requires valid access token
    - Only returns public information
    - Admin role required for full details (future enhancement)

    **Example Response:**
    ```json
    {
      "user_id": 456,
      "name": "Jane Doe",
      "status": "active",
      "created_at": "2025-10-15T08:00:00Z"
    }
    ```
    """
    user = user_service.get_user_profile(user_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} not found"
        )

    return UserPublicProfile(
        user_id=user.user_id,
        name=user.name,
        status=user.status.value,
        created_at=user.created_at.isoformat()
    )


@router.get("/me/preferences", response_model=UserPreferencesResponse)
async def get_user_preferences(
    current_user: User = Depends(get_current_active_user),
    user_service: UserService = Depends(get_user_service)
):
    """
    Get current user's preferences

    Returns user-specific preferences and settings.

    **Returns:**
    - user_id: User ID
    - default_trading_account_id: Default trading account (optional)
    - preferences: Flexible JSON object with user preferences

    **Authentication:**
    - Requires valid access token

    **Example Response:**
    ```json
    {
      "user_id": 123,
      "default_trading_account_id": 456,
      "preferences": {
        "theme": "dark",
        "notifications": {
          "email": true,
          "push": false
        },
        "trading": {
          "default_order_type": "LIMIT",
          "confirmation_required": true
        },
        "watchlists": [
          {"name": "Tech Stocks", "symbols": ["AAPL", "GOOGL", "MSFT"]},
          {"name": "Banking", "symbols": ["HDFC", "ICICI", "SBI"]}
        ]
      }
    }
    ```

    **Common Preferences:**
    - theme: "light" | "dark"
    - notifications: Email, push notification settings
    - trading: Default order types, confirmation preferences
    - watchlists: Custom watchlists
    - dashboard: Layout and widget preferences
    """
    preferences = user_service.get_user_preferences(current_user.user_id)

    return UserPreferencesResponse(
        user_id=preferences.user_id,
        default_trading_account_id=preferences.default_trading_account_id,
        preferences=preferences.preferences or {}
    )


@router.put("/me/preferences", response_model=UpdatePreferencesResponse)
async def update_user_preferences(
    request_data: UpdatePreferencesRequest,
    current_user: User = Depends(get_current_active_user),
    user_service: UserService = Depends(get_user_service)
):
    """
    Update current user's preferences

    Performs partial update - only provided fields are updated.
    Preferences object is deep-merged with existing preferences.

    **Request Body:**
    - default_trading_account_id: Set default trading account (optional)
    - preferences: Preferences to update (optional, merged with existing)

    **Returns:**
    - user_id: User ID
    - message: Success message
    - preferences: Updated full preferences object

    **Authentication:**
    - Requires valid access token

    **Example Request (Set Default Account):**
    ```json
    {
      "default_trading_account_id": 456
    }
    ```

    **Example Request (Update Preferences):**
    ```json
    {
      "preferences": {
        "theme": "dark",
        "notifications": {
          "email": true
        }
      }
    }
    ```

    **Merging Behavior:**
    - Nested objects are deep-merged
    - Arrays are replaced (not merged)
    - Null values remove the key

    **Example:**
    ```
    Current:  {"theme": "light", "trading": {"confirmation": true}}
    Update:   {"theme": "dark", "trading": {"default_order": "LIMIT"}}
    Result:   {"theme": "dark", "trading": {"confirmation": true, "default_order": "LIMIT"}}
    ```
    """
    try:
        preferences = user_service.update_user_preferences(
            user_id=current_user.user_id,
            default_trading_account_id=request_data.default_trading_account_id,
            preferences=request_data.preferences
        )

        return UpdatePreferencesResponse(
            user_id=preferences.user_id,
            message="Preferences updated successfully",
            preferences=preferences.preferences or {}
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/{user_id}/deactivate", response_model=DeactivateUserResponse)
async def deactivate_user(
    user_id: int,
    request_data: DeactivateUserRequest,
    current_user: User = Depends(get_current_active_user),
    user_service: UserService = Depends(get_user_service)
):
    """
    Deactivate user account (Admin only)

    Deactivates a user account and optionally revokes all active sessions.

    **Path Parameters:**
    - user_id: User ID to deactivate

    **Request Body:**
    - reason: Reason for deactivation (required for audit trail)
    - revoke_sessions: Whether to revoke all sessions (default: true)

    **Returns:**
    - user_id: User ID
    - previous_status: Status before deactivation
    - new_status: New status (deactivated)
    - sessions_revoked: Number of sessions revoked
    - message: Success message

    **Authentication:**
    - Requires valid access token
    - Requires admin role

    **Example Request:**
    ```json
    {
      "reason": "User requested account deletion",
      "revoke_sessions": true
    }
    ```

    **Example Response:**
    ```json
    {
      "user_id": 789,
      "previous_status": "active",
      "new_status": "deactivated",
      "sessions_revoked": 3,
      "message": "User deactivated successfully"
    }
    ```

    **Notes:**
    - Deactivated users cannot login
    - All active sessions are invalidated
    - Action is logged in audit trail
    - TODO: Requires admin role check (implement authorization)
    """
    # TODO: Check if current_user has admin role
    # For now, any authenticated user can deactivate (fix this!)

    try:
        user, sessions_revoked = user_service.deactivate_user(
            user_id=user_id,
            reason=request_data.reason,
            revoke_sessions=request_data.revoke_sessions,
            admin_id=current_user.user_id
        )

        return DeactivateUserResponse(
            user_id=user.user_id,
            previous_status="active",  # TODO: Get actual previous status
            new_status=user.status.value,
            sessions_revoked=sessions_revoked,
            message="User deactivated successfully"
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


# Admin endpoints (future: should check admin role)

@router.post("/search", response_model=UserSearchResponse)
async def search_users(
    request_data: UserSearchRequest,
    current_user: User = Depends(get_current_active_user),
    user_service: UserService = Depends(get_user_service)
):
    """
    Search users (Admin only)

    Search and filter users with pagination.

    **Request Body:**
    - query: Search query for email/name (optional)
    - status: Filter by status (optional)
    - role: Filter by role (optional)
    - page: Page number (default: 1)
    - page_size: Items per page (default: 50, max: 100)

    **Returns:**
    - users: List of matching users
    - total: Total count of matches
    - page: Current page
    - page_size: Items per page

    **Authentication:**
    - Requires valid access token
    - TODO: Requires admin role

    **Example Request:**
    ```json
    {
      "query": "john",
      "status": "active",
      "page": 1,
      "page_size": 20
    }
    ```
    """
    # TODO: Check admin role

    try:
        users, total = user_service.search_users(
            query=request_data.query,
            status=request_data.status,
            role=request_data.role,
            page=request_data.page,
            page_size=request_data.page_size
        )

        user_items = [
            UserListItem(
                user_id=u.user_id,
                email=u.email,
                name=u.name,
                status=u.status.value,
                roles=[ur.role.name for ur in u.roles],
                mfa_enabled=u.mfa_enabled,
                created_at=u.created_at.isoformat(),
                last_login_at=u.last_login_at.isoformat() if u.last_login_at else None
            )
            for u in users
        ]

        return UserSearchResponse(
            users=user_items,
            total=total,
            page=request_data.page,
            page_size=request_data.page_size
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {str(e)}"
        )


@router.get("/statistics", response_model=UserStatistics)
async def get_user_statistics(
    current_user: User = Depends(get_current_active_user),
    user_service: UserService = Depends(get_user_service)
):
    """
    Get user statistics (Admin only)

    Returns various user statistics for admin dashboard.

    **Returns:**
    - total_users: Total number of users
    - active_users: Active users count
    - pending_verification: Pending verification count
    - suspended_users: Suspended users count
    - deactivated_users: Deactivated users count
    - users_with_mfa: Users with MFA enabled
    - users_with_trading_accounts: Users with linked trading accounts
    - new_users_last_7_days: New registrations in last 7 days
    - new_users_last_30_days: New registrations in last 30 days

    **Authentication:**
    - Requires valid access token
    - TODO: Requires admin role

    **Example Response:**
    ```json
    {
      "total_users": 1250,
      "active_users": 980,
      "pending_verification": 45,
      "suspended_users": 12,
      "deactivated_users": 213,
      "users_with_mfa": 456,
      "users_with_trading_accounts": 234,
      "new_users_last_7_days": 23,
      "new_users_last_30_days": 87
    }
    ```
    """
    # TODO: Check admin role

    stats = user_service.get_user_statistics()
    return UserStatistics(**stats)


@router.post("/{user_id}/roles", response_model=RoleChangeResponse)
async def assign_role_to_user(
    user_id: int,
    request_data: AssignRoleRequest,
    current_user: User = Depends(get_current_active_user),
    user_service: UserService = Depends(get_user_service)
):
    """
    Assign role to user (Admin only)

    **Path Parameters:**
    - user_id: User ID

    **Request Body:**
    - role_name: Role to assign (user, admin, compliance)

    **Authentication:**
    - Requires valid access token
    - TODO: Requires admin role
    """
    # TODO: Check admin role

    try:
        user = user_service.assign_role(
            user_id=user_id,
            role_name=request_data.role_name,
            granted_by=current_user.user_id
        )

        roles = [ur.role.name for ur in user.roles]

        return RoleChangeResponse(
            user_id=user.user_id,
            role_name=request_data.role_name,
            action="assigned",
            message=f"Role '{request_data.role_name}' assigned successfully",
            current_roles=roles
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.delete("/{user_id}/roles/{role_name}", response_model=RoleChangeResponse)
async def revoke_role_from_user(
    user_id: int,
    role_name: str,
    current_user: User = Depends(get_current_active_user),
    user_service: UserService = Depends(get_user_service)
):
    """
    Revoke role from user (Admin only)

    **Path Parameters:**
    - user_id: User ID
    - role_name: Role to revoke

    **Authentication:**
    - Requires valid access token
    - TODO: Requires admin role
    """
    # TODO: Check admin role

    try:
        user = user_service.revoke_role(
            user_id=user_id,
            role_name=role_name,
            revoked_by=current_user.user_id
        )

        roles = [ur.role.name for ur in user.roles]

        return RoleChangeResponse(
            user_id=user.user_id,
            role_name=role_name,
            action="revoked",
            message=f"Role '{role_name}' revoked successfully",
            current_roles=roles
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/me/accounts")
async def list_accessible_accounts(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    List all trading accounts accessible to the current user

    Returns both owned accounts and accounts shared via memberships.
    This endpoint is optimized for SDK consumption.

    **Returns:**
    - user_id: Current user's ID
    - accounts: List of accessible trading accounts
    - primary_account_id: ID of primary account (if set)
    - total_count: Total number of accessible accounts

    **Authentication:**
    - Requires valid access token or API key

    **Example Response:**
    ```json
    {
      "user_id": 123,
      "accounts": [
        {
          "account_id": "XJ4540",
          "trading_account_id": 1,
          "broker": "kite",
          "nickname": "My Personal Account",
          "is_primary": true,
          "is_owner": true,
          "permissions": ["view", "trade", "manage"],
          "membership_type": "owner",
          "status": "active",
          "subscription_tier": "connect",
          "market_data_available": true
        }
      ],
      "primary_account_id": "XJ4540",
      "total_count": 1
    }
    ```
    """
    from app.models import TradingAccount, TradingAccountMembership
    from app.schemas.trading_account import ListAccessibleAccountsResponse, AccessibleAccountInfo

    accounts_list = []
    primary_account_id = None

    # Get owned accounts
    owned_accounts = db.query(TradingAccount).filter(
        TradingAccount.owner_id == current_user.user_id
    ).all()

    for account in owned_accounts:
        account_info = AccessibleAccountInfo(
            account_id=account.broker_user_id,
            trading_account_id=account.trading_account_id,
            broker=account.broker.value,
            nickname=account.account_name or account.nickname,
            is_primary=(account.is_primary if hasattr(account, 'is_primary') else False),
            is_owner=True,
            permissions=["view", "trade", "manage"],
            membership_type="owner",
            status=account.status.value,
            subscription_tier=account.subscription_tier.value if account.subscription_tier else "unknown",
            market_data_available=account.market_data_available or False
        )
        accounts_list.append(account_info)

        if account_info.is_primary:
            primary_account_id = account_info.account_id

    # Get shared accounts
    memberships = db.query(TradingAccountMembership).filter(
        TradingAccountMembership.user_id == current_user.user_id,
        TradingAccountMembership.status == "active"
    ).all()

    for membership in memberships:
        account = membership.trading_account
        account_info = AccessibleAccountInfo(
            account_id=account.broker_user_id,
            trading_account_id=account.trading_account_id,
            broker=account.broker.value,
            nickname=account.account_name or account.nickname,
            is_primary=False,
            is_owner=False,
            permissions=membership.permissions or [],
            membership_type="member",
            status=account.status.value,
            subscription_tier=account.subscription_tier.value if account.subscription_tier else "unknown",
            market_data_available=account.market_data_available or False
        )
        accounts_list.append(account_info)

    # Default to first owned account if no primary set
    if not primary_account_id and accounts_list:
        for acc in accounts_list:
            if acc.is_owner:
                primary_account_id = acc.account_id
                break

    return ListAccessibleAccountsResponse(
        user_id=current_user.user_id,
        accounts=accounts_list,
        primary_account_id=primary_account_id,
        total_count=len(accounts_list)
    )
