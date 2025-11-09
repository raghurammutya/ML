"""
Trading Account endpoints

Manages broker account linking and shared access.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Header, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from app.core.database import get_db
from app.core.redis_client import get_redis, RedisClient
from app.api.dependencies import get_current_active_user, get_current_user
from app.models import User, TradingAccountStatus
from app.services.trading_account_service import TradingAccountService
from app.schemas import trading_account as schemas
from app.schemas.trading_account import (
    LinkTradingAccountRequest,
    LinkTradingAccountResponse,
    GetTradingAccountsResponse,
    TradingAccountSummary,
    RotateCredentialsRequest,
    RotateCredentialsResponse,
    GrantMembershipRequest,
    GrantMembershipResponse,
    RevokeMembershipResponse,
    GetMembershipsResponse,
    MembershipInfo,
    UnlinkTradingAccountResponse,
    CheckTradingAccountPermissionRequest,
    CheckTradingAccountPermissionResponse,
    GetCredentialsRequest,
    GetCredentialsResponse
)

router = APIRouter()


def get_trading_account_service(
    db: Session = Depends(get_db),
    redis: RedisClient = Depends(get_redis)
) -> TradingAccountService:
    """Get trading account service instance"""
    return TradingAccountService(db, redis)


@router.post("/link", response_model=LinkTradingAccountResponse, status_code=status.HTTP_201_CREATED)
async def link_trading_account(
    request_data: LinkTradingAccountRequest,
    current_user: User = Depends(get_current_active_user),
    service: TradingAccountService = Depends(get_trading_account_service)
):
    """
    Link a broker trading account

    Links a broker account (Kite, Upstox, etc.) to your user account.
    You become the owner with full access.

    **Request Body:**
    - broker: Broker type (kite, upstox, angel, finvasia)
    - broker_user_id: Broker's client ID/user ID
    - api_key: API key from broker
    - api_secret: API secret from broker
    - password: Broker login password
    - totp_seed: TOTP secret (Base32)
    - access_token: Access token (optional, if already obtained)
    - account_name: Friendly name for account (optional)

    **Example:**
    ```json
    {
      "broker": "kite",
      "broker_user_id": "AB1234",
      "api_key": "your_api_key",
      "api_secret": "your_api_secret",
      "account_name": "My Kite Account"
    }
    ```

    **Security:**
    - Credentials are encrypted with KMS before storage
    - Only you can access your credentials
    - You can share read-only or trading access via memberships

    **Returns:**
    - trading_account_id: Unique account ID
    - status: Account status (active)

    **Authentication:**
    - Requires valid access token
    """
    try:
        account = service.link_trading_account(
            user_id=current_user.user_id,
            broker=request_data.broker.value,
            broker_user_id=request_data.broker_user_id,
            api_key=request_data.api_key,
            api_secret=request_data.api_secret,
            password=request_data.password,
            totp_seed=request_data.totp_seed,
            access_token=request_data.access_token,
            account_name=request_data.account_name
        )

        return LinkTradingAccountResponse(
            trading_account_id=account.trading_account_id,
            user_id=account.user_id,
            broker=account.broker,
            broker_user_id=account.broker_user_id,
            account_name=account.account_name,
            status=account.status.value
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("", response_model=GetTradingAccountsResponse)
async def get_trading_accounts(
    current_user: User = Depends(get_current_active_user),
    service: TradingAccountService = Depends(get_trading_account_service)
):
    """
    Get your trading accounts

    Returns all trading accounts you have access to:
    - Accounts you own (full access)
    - Accounts shared with you (limited by permissions)

    **Returns:**
    - owned_accounts: Accounts you own
    - shared_accounts: Accounts shared with you via memberships
    - total_accounts: Total count

    **Example Response:**
    ```json
    {
      "user_id": 123,
      "owned_accounts": [
        {
          "trading_account_id": 1,
          "broker": "kite",
          "broker_user_id": "AB1234",
          "account_name": "My Kite Account",
          "status": "active",
          "is_owner": true,
          "permissions": ["view", "trade", "manage"],
          "linked_at": "2025-11-01T10:00:00Z",
          "last_used_at": "2025-11-03T15:30:00Z"
        }
      ],
      "shared_accounts": [
        {
          "trading_account_id": 2,
          "broker": "upstox",
          "broker_user_id": "CD5678",
          "account_name": "Team Account",
          "status": "active",
          "is_owner": false,
          "permissions": ["view", "trade"],
          "linked_at": "2025-10-15T08:00:00Z",
          "last_used_at": null
        }
      ],
      "total_accounts": 2
    }
    ```

    **Authentication:**
    - Requires valid access token
    """
    owned_accounts, shared_accounts = service.get_user_trading_accounts(current_user.user_id)

    owned_summaries = [
        TradingAccountSummary(
            trading_account_id=acc.trading_account_id,
            broker=acc.broker,
            broker_user_id=acc.broker_user_id,
            account_name=acc.account_name,
            status=acc.status.value,
            is_owner=True,
            permissions=["view", "trade", "manage"],
            linked_at=acc.created_at.isoformat(),
            last_used_at=acc.last_used_at.isoformat() if acc.last_used_at else None
        )
        for acc in owned_accounts
    ]

    shared_summaries = [
        TradingAccountSummary(
            trading_account_id=acc.trading_account_id,
            broker=acc.broker,
            broker_user_id=acc.broker_user_id,
            account_name=acc.account_name,
            status=acc.status.value,
            is_owner=False,
            permissions=membership.permissions or [],
            linked_at=acc.created_at.isoformat(),
            last_used_at=acc.last_used_at.isoformat() if acc.last_used_at else None
        )
        for acc, membership in shared_accounts
    ]

    return GetTradingAccountsResponse(
        user_id=current_user.user_id,
        owned_accounts=owned_summaries,
        shared_accounts=shared_summaries,
        total_accounts=len(owned_summaries) + len(shared_summaries)
    )


@router.post("/{trading_account_id}/rotate-credentials", response_model=RotateCredentialsResponse)
async def rotate_credentials(
    trading_account_id: int,
    request_data: RotateCredentialsRequest,
    current_user: User = Depends(get_current_active_user),
    service: TradingAccountService = Depends(get_trading_account_service)
):
    """
    Rotate API credentials

    Update API key, secret, or access token for a trading account.
    Only account owner can rotate credentials.

    **Use Cases:**
    - API key expired
    - Access token needs refresh
    - Security breach - regenerate credentials

    **Request Body:**
    - api_key: New API key (optional)
    - api_secret: New API secret (optional)
    - access_token: New access token (optional)

    **Example:**
    ```json
    {
      "access_token": "new_access_token_here"
    }
    ```

    **Returns:**
    - trading_account_id: Account ID
    - status: Updated status
    - message: Success message

    **Errors:**
    - 400: Account not found or you're not the owner
    - 401: Unauthorized

    **Authentication:**
    - Requires valid access token
    - Must be account owner
    """
    try:
        account = service.rotate_credentials(
            trading_account_id=trading_account_id,
            user_id=current_user.user_id,
            api_key=request_data.api_key,
            api_secret=request_data.api_secret,
            access_token=request_data.access_token,
            password=request_data.password,
            totp_seed=request_data.totp_seed
        )

        return RotateCredentialsResponse(
            trading_account_id=account.trading_account_id,
            status=account.status.value
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.delete("/{trading_account_id}", response_model=UnlinkTradingAccountResponse)
async def unlink_trading_account(
    trading_account_id: int,
    current_user: User = Depends(get_current_active_user),
    service: TradingAccountService = Depends(get_trading_account_service)
):
    """
    Unlink trading account

    Permanently removes a trading account.
    Only account owner can unlink.
    All memberships (shared access) are automatically revoked.

    **Warning:** This action is permanent and cannot be undone!

    **Returns:**
    - trading_account_id: Account ID
    - message: Success message
    - memberships_revoked: Number of memberships that were revoked

    **Example Response:**
    ```json
    {
      "trading_account_id": 123,
      "message": "Trading account unlinked successfully",
      "memberships_revoked": 3
    }
    ```

    **Errors:**
    - 400: Account not found or you're not the owner
    - 401: Unauthorized

    **Authentication:**
    - Requires valid access token
    - Must be account owner
    """
    try:
        memberships_revoked = service.unlink_trading_account(
            trading_account_id=trading_account_id,
            user_id=current_user.user_id
        )

        return UnlinkTradingAccountResponse(
            trading_account_id=trading_account_id,
            memberships_revoked=memberships_revoked
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/{trading_account_id}/memberships", response_model=GrantMembershipResponse)
async def grant_membership(
    trading_account_id: int,
    request_data: GrantMembershipRequest,
    current_user: User = Depends(get_current_active_user),
    service: TradingAccountService = Depends(get_trading_account_service)
):
    """
    Grant shared access to trading account

    Share your trading account with another user.
    Only account owner can grant memberships.

    **Permissions:**
    - `view`: Read-only access (view positions, orders)
    - `trade`: Can place orders
    - `manage`: Can modify account settings (not unlink)

    **Request Body:**
    - user_email: Email of user to grant access to
    - permissions: List of permissions ["view"], ["view", "trade"], or ["view", "trade", "manage"]
    - note: Optional note about why access was granted

    **Example:**
    ```json
    {
      "user_email": "teammate@example.com",
      "permissions": ["view", "trade"],
      "note": "Team member for algorithmic trading"
    }
    ```

    **Returns:**
    - membership_id: Unique membership ID
    - user_id: User ID of member
    - permissions: Granted permissions

    **Errors:**
    - 400: Account not found, you're not owner, user not found, or already has access
    - 401: Unauthorized

    **Authentication:**
    - Requires valid access token
    - Must be account owner
    """
    try:
        membership = service.grant_membership(
            trading_account_id=trading_account_id,
            owner_id=current_user.user_id,
            member_email=request_data.user_email,
            permissions=[p.value for p in request_data.permissions],
            note=request_data.note
        )

        return GrantMembershipResponse(
            membership_id=membership.membership_id,
            trading_account_id=membership.trading_account_id,
            user_id=membership.user_id,
            user_email=request_data.user_email,
            permissions=membership.permissions,
            granted_by=current_user.user_id
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.delete("/{trading_account_id}/memberships/{membership_id}", response_model=RevokeMembershipResponse)
async def revoke_membership(
    trading_account_id: int,
    membership_id: int,
    current_user: User = Depends(get_current_active_user),
    service: TradingAccountService = Depends(get_trading_account_service)
):
    """
    Revoke shared access

    Remove a user's access to your trading account.
    Only account owner can revoke memberships.

    **Returns:**
    - membership_id: Membership ID
    - trading_account_id: Account ID
    - user_id: User whose access was revoked
    - revoked_by: Your user ID

    **Example Response:**
    ```json
    {
      "membership_id": 456,
      "trading_account_id": 123,
      "user_id": 789,
      "revoked_by": 123,
      "message": "Membership revoked successfully"
    }
    ```

    **Errors:**
    - 400: Membership not found or you're not the owner
    - 401: Unauthorized

    **Authentication:**
    - Requires valid access token
    - Must be account owner
    """
    try:
        membership = service.revoke_membership(
            trading_account_id=trading_account_id,
            membership_id=membership_id,
            revoker_id=current_user.user_id
        )

        return RevokeMembershipResponse(
            membership_id=membership.membership_id,
            trading_account_id=trading_account_id,
            user_id=membership.user_id,
            revoked_by=current_user.user_id
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/{trading_account_id}/memberships", response_model=GetMembershipsResponse)
async def get_memberships(
    trading_account_id: int,
    current_user: User = Depends(get_current_active_user),
    service: TradingAccountService = Depends(get_trading_account_service)
):
    """
    List memberships for trading account

    View all users who have shared access to your account.
    Only account owner can view memberships.

    **Returns:**
    - trading_account_id: Account ID
    - owner_id: Your user ID
    - memberships: List of members with permissions
    - total_members: Count of members

    **Example Response:**
    ```json
    {
      "trading_account_id": 123,
      "owner_id": 1,
      "memberships": [
        {
          "membership_id": 456,
          "trading_account_id": 123,
          "user_id": 789,
          "user_email": "teammate@example.com",
          "user_name": "John Teammate",
          "permissions": ["view", "trade"],
          "granted_by": 1,
          "granted_at": "2025-11-01T10:00:00Z",
          "note": "Team member for algo trading"
        }
      ],
      "total_members": 1
    }
    ```

    **Errors:**
    - 400: Account not found or you're not the owner
    - 401: Unauthorized

    **Authentication:**
    - Requires valid access token
    - Must be account owner
    """
    try:
        memberships = service.get_memberships(
            trading_account_id=trading_account_id,
            owner_id=current_user.user_id
        )

        membership_infos = [
            MembershipInfo(
                membership_id=m.membership_id,
                trading_account_id=m.trading_account_id,
                user_id=m.user_id,
                user_email=m.user.email,
                user_name=m.user.name,
                permissions=m.permissions or [],
                granted_by=m.granted_by,
                granted_at=m.granted_at.isoformat(),
                note=m.note
            )
            for m in memberships
        ]

        return GetMembershipsResponse(
            trading_account_id=trading_account_id,
            owner_id=current_user.user_id,
            memberships=membership_infos,
            total_members=len(membership_infos)
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/{trading_account_id}/permissions/check", response_model=CheckTradingAccountPermissionResponse)
async def check_permission(
    trading_account_id: int,
    request_data: CheckTradingAccountPermissionRequest,
    current_user: User = Depends(get_current_active_user),
    service: TradingAccountService = Depends(get_trading_account_service)
):
    """
    Check your permissions on trading account

    Verify what access you have to a trading account.
    Useful for UI to show/hide features based on permissions.

    **Request Body:**
    - required_permissions: Permissions to check (optional)

    **Example:**
    ```json
    {
      "required_permissions": ["trade"]
    }
    ```

    **Returns:**
    - has_access: Whether you have access at all
    - is_owner: Whether you own the account
    - permissions: Your actual permissions
    - reason: Reason if access denied

    **Example Response:**
    ```json
    {
      "trading_account_id": 123,
      "user_id": 789,
      "has_access": true,
      "is_owner": false,
      "permissions": ["view", "trade"],
      "reason": null
    }
    ```

    **Authentication:**
    - Requires valid access token
    """
    has_access, is_owner, permissions = service.check_access(
        trading_account_id=trading_account_id,
        user_id=current_user.user_id,
        required_permissions=request_data.required_permissions
    )

    reason = None
    if not has_access:
        if not permissions:
            reason = "No access to this trading account"
        else:
            reason = f"Missing required permissions: {request_data.required_permissions}"

    return CheckTradingAccountPermissionResponse(
        trading_account_id=trading_account_id,
        user_id=current_user.user_id,
        has_access=has_access,
        is_owner=is_owner,
        permissions=permissions,
        reason=reason
    )


# Internal endpoint (service-to-service only)

@router.post("/internal/{trading_account_id}/credentials", response_model=GetCredentialsResponse)
async def get_credentials_internal(
    trading_account_id: int,
    request_data: GetCredentialsRequest,
    x_service_token: Optional[str] = Header(None),
    service: TradingAccountService = Depends(get_trading_account_service)
):
    """
    Get decrypted credentials (INTERNAL ONLY)

    Returns decrypted API keys and secrets for a trading account.

    **SECURITY WARNING:**
    - This endpoint should ONLY be accessible to internal services
    - Use service-to-service authentication (X-Service-Token header)
    - Never expose this endpoint to public API
    - All access is logged for audit

    **Request Body:**
    - requesting_service: Name of service requesting credentials

    **Returns:**
    - Decrypted API key, secret, and access token
    - Status and broker information

    **TODO:**
    - Implement service-to-service authentication
    - Restrict to internal network only
    - Add rate limiting
    """
    # TODO: Verify service-to-service authentication
    # if not x_service_token or x_service_token != settings.SERVICE_AUTH_TOKEN:
    #     raise HTTPException(
    #         status_code=status.HTTP_401_UNAUTHORIZED,
    #         detail="Invalid service token"
    #     )

    try:
        credentials = service.get_decrypted_credentials(
            trading_account_id=trading_account_id,
            requesting_service=request_data.requesting_service
        )

        return GetCredentialsResponse(**credentials)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.get("/internal", response_model=List[GetCredentialsResponse])
async def list_credentials_internal(
    requesting_service: str = Query(..., description="Service requesting credentials"),
    status_filter: Optional[str] = Query("ACTIVE", description="Filter by trading account status"),
    x_service_token: Optional[str] = Header(None),
    service: TradingAccountService = Depends(get_trading_account_service)
):
    """
    List decrypted credentials for all trading accounts (INTERNAL ONLY).
    """
    # TODO: enforce service token verification as above
    status_enum: Optional[TradingAccountStatus] = None
    if status_filter:
        try:
            status_enum = TradingAccountStatus(status_filter.upper())
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status filter '{status_filter}'"
            )

    try:
        credentials = service.get_all_credentials(
            requesting_service=requesting_service,
            status_filter=status_enum
        )
        return credentials
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


# ============================================================================
# Subscription Tier Management Endpoints
# ============================================================================
# Subscription Tier Management
# Note: Subscription tier detection removed as it required direct KiteConnect
# access which violates service architecture. Tier should be set manually via
# PUT /subscription-tier endpoint or delegated to ticker_service if needed.
# ============================================================================

@router.put(
    "/{trading_account_id}/subscription-tier",
    response_model=schemas.UpdateSubscriptionTierResponse,
    summary="Manually update subscription tier",
    tags=["Trading Accounts", "Subscription Tier"]
)
async def update_subscription_tier(
    trading_account_id: int,
    request: schemas.UpdateSubscriptionTierRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    redis: RedisClient = Depends(get_redis)
):
    """
    Manually override subscription tier (for testing or correction).

    **Owner only** - Only account owner can update tier.

    **Use cases:**
    - Testing with mock tier for development
    - Correcting misdetected tier
    - Setting tier when detection fails

    **Parameters:**
    - **trading_account_id**: Trading account to update
    - **subscription_tier**: Tier to set (unknown/personal/connect/startup)

    **Returns:**
    - Updated subscription tier
    - Market data availability
    - Success message
    """
    service = TradingAccountService(db, redis)

    # Verify user is owner
    account = db.query(TradingAccount).filter(
        TradingAccount.trading_account_id == trading_account_id
    ).first()

    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trading account {trading_account_id} not found"
        )

    if account.user_id != current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only account owner can update subscription tier"
        )

    try:
        result = await service.update_subscription_tier(
            trading_account_id,
            request.subscription_tier.value
        )
        return schemas.UpdateSubscriptionTierResponse(**result)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update subscription tier: {str(e)}"
        )


# GET /subscription-tier endpoint removed - tier is now manually set only
