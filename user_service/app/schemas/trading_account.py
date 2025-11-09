"""
Pydantic schemas for Trading Account Management

Trading accounts represent broker accounts (Kite, Upstox, etc.) linked to users.
Users can share access to their accounts with other users via memberships.
"""

from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field, validator
from enum import Enum


class BrokerType(str, Enum):
    """Supported broker types"""
    KITE = "kite"
    UPSTOX = "upstox"
    ANGEL = "angel"
    FINVASIA = "finvasia"
    # Add more brokers as needed


class TradingAccountStatus(str, Enum):
    """Trading account status"""
    ACTIVE = "active"
    SUSPENDED = "suspended"
    EXPIRED = "expired"  # API token expired
    ERROR = "error"  # Connection error


class MembershipPermission(str, Enum):
    """Membership permissions for shared accounts"""
    VIEW = "view"  # Read-only access
    TRADE = "trade"  # Can place orders
    MANAGE = "manage"  # Can modify settings (not unlink)


class SubscriptionTier(str, Enum):
    """KiteConnect API subscription tier"""
    UNKNOWN = "unknown"  # Not yet detected
    PERSONAL = "personal"  # Free tier - trading only, no market data
    CONNECT = "connect"  # Paid tier (Rs. 500/month) - trading + market data
    STARTUP = "startup"  # Startup program - free with full features


# Link Trading Account schemas

class LinkTradingAccountRequest(BaseModel):
    """
    Link a new trading account (broker account) to user

    The user will become the owner with full access.
    """
    broker: BrokerType = Field(
        ...,
        description="Broker type (kite, upstox, etc.)"
    )
    broker_user_id: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Broker's user ID (e.g., Kite client ID)"
    )
    api_key: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="API key from broker"
    )
    api_secret: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="API secret from broker"
    )
    password: str = Field(
        ...,
        min_length=4,
        max_length=255,
        description="Broker account password used for session bootstrap"
    )
    totp_seed: str = Field(
        ...,
        min_length=16,
        max_length=64,
        description="TOTP secret in Base32 format"
    )
    access_token: Optional[str] = Field(
        None,
        max_length=500,
        description="Access token (if already obtained)"
    )
    account_name: Optional[str] = Field(
        None,
        max_length=100,
        description="Friendly name for account (e.g., 'My Trading Account')"
    )

    @validator('broker_user_id', 'api_key', 'api_secret', 'password', 'totp_seed')
    def trim_whitespace(cls, v):
        if isinstance(v, str):
            return v.strip()
        return v


class LinkTradingAccountResponse(BaseModel):
    """Link trading account response"""
    trading_account_id: int
    user_id: int
    broker: str
    broker_user_id: str
    account_name: Optional[str]
    status: str
    message: str = "Trading account linked successfully"


# Get Trading Accounts schemas

class TradingAccountSummary(BaseModel):
    """Trading account summary for list view"""
    trading_account_id: int
    broker: str
    broker_user_id: str
    account_name: Optional[str]
    status: str
    is_owner: bool
    permissions: List[str]  # If shared access, what permissions
    linked_at: str  # ISO timestamp
    last_used_at: Optional[str]  # ISO timestamp
    subscription_tier: str  # unknown/personal/connect/startup
    subscription_tier_last_checked: Optional[str]  # ISO timestamp
    market_data_available: bool


class GetTradingAccountsResponse(BaseModel):
    """List of trading accounts accessible to user"""
    user_id: int
    owned_accounts: List[TradingAccountSummary] = Field(
        default_factory=list,
        description="Accounts owned by user (full access)"
    )
    shared_accounts: List[TradingAccountSummary] = Field(
        default_factory=list,
        description="Accounts shared with user (via memberships)"
    )
    total_accounts: int


# Rotate Credentials schemas

class RotateCredentialsRequest(BaseModel):
    """
    Rotate API credentials for trading account

    Used when API keys expire or need to be refreshed.
    """
    api_key: Optional[str] = Field(
        None,
        max_length=255,
        description="New API key (optional, only if changed)"
    )
    api_secret: Optional[str] = Field(
        None,
        max_length=255,
        description="New API secret (optional, only if changed)"
    )
    access_token: Optional[str] = Field(
        None,
        max_length=500,
        description="New access token (optional)"
    )
    password: Optional[str] = Field(
        None,
        max_length=255,
        description="New broker password (optional)"
    )
    totp_seed: Optional[str] = Field(
        None,
        max_length=64,
        description="New TOTP seed in Base32 format (optional)"
    )


class RotateCredentialsResponse(BaseModel):
    """Rotate credentials response"""
    trading_account_id: int
    message: str = "Credentials rotated successfully"
    status: str


# Membership (Shared Access) schemas

class GrantMembershipRequest(BaseModel):
    """
    Grant shared access to trading account

    Allows owner to share their account with other users.
    """
    user_email: str = Field(
        ...,
        description="Email of user to grant access to"
    )
    permissions: List[MembershipPermission] = Field(
        ...,
        min_items=1,
        description="Permissions to grant (view, trade, manage)"
    )
    note: Optional[str] = Field(
        None,
        max_length=500,
        description="Optional note about why access was granted"
    )

    @validator('permissions')
    def unique_permissions(cls, v):
        if len(v) != len(set(v)):
            raise ValueError("Duplicate permissions not allowed")
        return v


class GrantMembershipResponse(BaseModel):
    """Grant membership response"""
    membership_id: int
    trading_account_id: int
    user_id: int  # User granted access
    user_email: str
    permissions: List[str]
    granted_by: int  # Owner who granted access
    message: str = "Membership granted successfully"


class RevokeMembershipResponse(BaseModel):
    """Revoke membership response"""
    membership_id: int
    trading_account_id: int
    user_id: int
    revoked_by: int
    message: str = "Membership revoked successfully"


# Membership list schema

class MembershipInfo(BaseModel):
    """Information about a trading account membership"""
    membership_id: int
    trading_account_id: int
    user_id: int
    user_email: str
    user_name: str
    permissions: List[str]
    granted_by: int
    granted_at: str  # ISO timestamp
    note: Optional[str]


class GetMembershipsResponse(BaseModel):
    """List of memberships for a trading account"""
    trading_account_id: int
    owner_id: int
    memberships: List[MembershipInfo]
    total_members: int


# Internal endpoint schema (service-to-service)

class GetCredentialsRequest(BaseModel):
    """Internal request to get decrypted credentials"""
    trading_account_id: int
    requesting_service: str = Field(
        ...,
        description="Service requesting credentials (for audit)"
    )


class GetCredentialsResponse(BaseModel):
    """Internal response with decrypted credentials"""
    trading_account_id: int
    broker: str
    broker_user_id: str
    account_name: Optional[str]
    api_key: str  # Decrypted
    api_secret: str  # Decrypted
    access_token: Optional[str]  # Decrypted
    password: str
    totp_seed: str
    status: str
    subscription_tier: str  # unknown/personal/connect/startup
    market_data_available: bool
    warning: str = "SENSITIVE: Handle credentials securely. Do not log or persist."


# Permission check schema

class CheckTradingAccountPermissionRequest(BaseModel):
    """Check user's permissions on trading account"""
    trading_account_id: int
    required_permissions: List[str] = Field(
        default_factory=list,
        description="Required permissions to check"
    )


class CheckTradingAccountPermissionResponse(BaseModel):
    """Trading account permission check response"""
    trading_account_id: int
    user_id: int
    has_access: bool
    is_owner: bool
    permissions: List[str]  # Actual permissions user has
    reason: Optional[str] = Field(
        None,
        description="Reason if access denied"
    )


# Unlink (delete) schema

class UnlinkTradingAccountResponse(BaseModel):
    """Unlink trading account response"""
    trading_account_id: int
    message: str = "Trading account unlinked successfully"
    memberships_revoked: int = Field(
        0,
        description="Number of memberships that were revoked"
    )


# Subscription Tier Detection schemas

class DetectSubscriptionTierResponse(BaseModel):
    """Response from subscription tier detection"""
    trading_account_id: int
    subscription_tier: str  # unknown/personal/connect/startup
    market_data_available: bool
    last_checked: str  # ISO timestamp
    detection_method: str  # e.g., "quote_api_test", "websocket_test", "cached"
    message: Optional[str] = None


class UpdateSubscriptionTierRequest(BaseModel):
    """Manual override of subscription tier (for testing or correction)"""
    subscription_tier: SubscriptionTier


class UpdateSubscriptionTierResponse(BaseModel):
    """Response from manual subscription tier update"""
    trading_account_id: int
    subscription_tier: str
    market_data_available: bool
    message: str = "Subscription tier updated successfully"
