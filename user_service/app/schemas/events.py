"""
Event schemas for pub/sub messaging

Events are published to Redis pub/sub channels when important actions occur.
Other services can subscribe to these events to stay in sync.
"""

from typing import Optional, Dict, Any, List
from datetime import datetime
from pydantic import BaseModel, Field
from enum import Enum


class EventType(str, Enum):
    """Event type enumeration"""
    # User lifecycle events
    USER_REGISTERED = "user.registered"
    USER_UPDATED = "user.updated"
    USER_DEACTIVATED = "user.deactivated"
    USER_ACTIVATED = "user.activated"
    USER_DELETED = "user.deleted"

    # Authentication events
    LOGIN_SUCCESS = "login.success"
    LOGIN_FAILED = "login.failed"
    LOGOUT = "logout"
    TOKEN_REFRESHED = "token.refreshed"

    # MFA events
    MFA_ENABLED = "mfa.enabled"
    MFA_DISABLED = "mfa.disabled"
    MFA_VERIFIED = "mfa.verified"
    MFA_FAILED = "mfa.failed"

    # Authorization events
    PERMISSION_GRANTED = "permission.granted"
    PERMISSION_REVOKED = "permission.revoked"
    ROLE_ASSIGNED = "role.assigned"
    ROLE_REVOKED = "role.revoked"

    # Preferences events
    PREFERENCES_UPDATED = "preferences.updated"

    # Trading account events
    TRADING_ACCOUNT_LINKED = "trading_account.linked"
    TRADING_ACCOUNT_UNLINKED = "trading_account.unlinked"
    TRADING_ACCOUNT_UPDATED = "trading_account.updated"
    MEMBERSHIP_GRANTED = "membership.granted"
    MEMBERSHIP_REVOKED = "membership.revoked"

    # Password events
    PASSWORD_CHANGED = "password.changed"
    PASSWORD_RESET_REQUESTED = "password.reset_requested"
    PASSWORD_RESET_COMPLETED = "password.reset_completed"

    # Session events
    SESSION_CREATED = "session.created"
    SESSION_REVOKED = "session.revoked"


class EventPriority(str, Enum):
    """Event priority for routing and processing"""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class Event(BaseModel):
    """
    Base event model for all published events

    All events follow this structure for consistent processing.
    """
    event_id: str = Field(
        ...,
        description="Unique event ID (UUID)"
    )
    event_type: EventType = Field(
        ...,
        description="Type of event"
    )
    timestamp: str = Field(
        ...,
        description="Event timestamp (ISO 8601 format)"
    )
    source: str = Field(
        default="user_service",
        description="Service that generated the event"
    )
    priority: EventPriority = Field(
        default=EventPriority.NORMAL,
        description="Event priority for routing"
    )
    subject: Optional[str] = Field(
        None,
        description="Subject of the event (e.g., user:123)"
    )
    actor: Optional[str] = Field(
        None,
        description="Actor who triggered the event (e.g., user:456)"
    )
    resource: Optional[str] = Field(
        None,
        description="Resource affected (e.g., trading_account:789)"
    )
    data: Dict[str, Any] = Field(
        default_factory=dict,
        description="Event-specific data payload"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata (IP, user agent, etc.)"
    )

    class Config:
        use_enum_values = True


# Specific event payload schemas

class UserRegisteredEvent(BaseModel):
    """User registration event payload"""
    user_id: int
    email: str
    name: str
    status: str
    roles: List[str]


class UserUpdatedEvent(BaseModel):
    """User profile update event payload"""
    user_id: int
    updated_fields: List[str]


class UserDeactivatedEvent(BaseModel):
    """User deactivation event payload"""
    user_id: int
    reason: Optional[str] = None
    deactivated_by: Optional[int] = None


class LoginSuccessEvent(BaseModel):
    """Successful login event payload"""
    user_id: int
    session_id: str
    mfa_verified: bool
    device_fingerprint: Optional[str] = None


class MfaEnabledEvent(BaseModel):
    """MFA enabled event payload"""
    user_id: int
    method: str = "totp"
    backup_codes_count: int


class MfaDisabledEvent(BaseModel):
    """MFA disabled event payload"""
    user_id: int
    method: str = "totp"


class RoleAssignedEvent(BaseModel):
    """Role assignment event payload"""
    user_id: int
    role_name: str
    granted_by: Optional[int] = None
    current_roles: List[str]


class RoleRevokedEvent(BaseModel):
    """Role revocation event payload"""
    user_id: int
    role_name: str
    revoked_by: Optional[int] = None
    current_roles: List[str]


class PreferencesUpdatedEvent(BaseModel):
    """User preferences update event payload"""
    user_id: int
    default_trading_account_id: Optional[int] = None


class TradingAccountLinkedEvent(BaseModel):
    """Trading account linked event payload"""
    user_id: int
    trading_account_id: int
    broker: str


class TradingAccountUnlinkedEvent(BaseModel):
    """Trading account unlinked event payload"""
    user_id: int
    trading_account_id: int
    broker: str


class MembershipGrantedEvent(BaseModel):
    """Trading account membership granted event payload"""
    user_id: int
    trading_account_id: int
    membership_id: int
    permissions: List[str]
    granted_by: int


class MembershipRevokedEvent(BaseModel):
    """Trading account membership revoked event payload"""
    user_id: int
    trading_account_id: int
    membership_id: int
    revoked_by: int


class PasswordChangedEvent(BaseModel):
    """Password changed event payload"""
    user_id: int
    changed_via: str  # "profile", "reset"


class SessionRevokedEvent(BaseModel):
    """Session revoked event payload"""
    user_id: int
    session_id: str
    reason: str  # "logout", "admin_revoke", "security"


# Channel routing

class EventChannel(str, Enum):
    """
    Redis pub/sub channels for event routing

    Services subscribe to specific channels based on their needs.
    """
    # All events (for monitoring/logging services)
    ALL_EVENTS = "user_service.events.all"

    # User-related events
    USER_EVENTS = "user_service.events.user"

    # Authentication events
    AUTH_EVENTS = "user_service.events.auth"

    # Authorization events (role/permission changes)
    AUTHZ_EVENTS = "user_service.events.authz"

    # Trading account events
    TRADING_ACCOUNT_EVENTS = "user_service.events.trading_account"

    # Security-critical events (for security monitoring)
    SECURITY_EVENTS = "user_service.events.security"


# Event channel routing map
EVENT_CHANNEL_MAP: Dict[EventType, List[EventChannel]] = {
    # User events
    EventType.USER_REGISTERED: [EventChannel.USER_EVENTS, EventChannel.ALL_EVENTS],
    EventType.USER_UPDATED: [EventChannel.USER_EVENTS, EventChannel.ALL_EVENTS],
    EventType.USER_DEACTIVATED: [EventChannel.USER_EVENTS, EventChannel.SECURITY_EVENTS, EventChannel.ALL_EVENTS],
    EventType.USER_ACTIVATED: [EventChannel.USER_EVENTS, EventChannel.ALL_EVENTS],
    EventType.USER_DELETED: [EventChannel.USER_EVENTS, EventChannel.SECURITY_EVENTS, EventChannel.ALL_EVENTS],

    # Auth events
    EventType.LOGIN_SUCCESS: [EventChannel.AUTH_EVENTS, EventChannel.ALL_EVENTS],
    EventType.LOGIN_FAILED: [EventChannel.AUTH_EVENTS, EventChannel.SECURITY_EVENTS, EventChannel.ALL_EVENTS],
    EventType.LOGOUT: [EventChannel.AUTH_EVENTS, EventChannel.ALL_EVENTS],
    EventType.TOKEN_REFRESHED: [EventChannel.AUTH_EVENTS, EventChannel.ALL_EVENTS],

    # MFA events
    EventType.MFA_ENABLED: [EventChannel.AUTH_EVENTS, EventChannel.SECURITY_EVENTS, EventChannel.ALL_EVENTS],
    EventType.MFA_DISABLED: [EventChannel.AUTH_EVENTS, EventChannel.SECURITY_EVENTS, EventChannel.ALL_EVENTS],
    EventType.MFA_VERIFIED: [EventChannel.AUTH_EVENTS, EventChannel.ALL_EVENTS],
    EventType.MFA_FAILED: [EventChannel.AUTH_EVENTS, EventChannel.SECURITY_EVENTS, EventChannel.ALL_EVENTS],

    # Authz events
    EventType.PERMISSION_GRANTED: [EventChannel.AUTHZ_EVENTS, EventChannel.SECURITY_EVENTS, EventChannel.ALL_EVENTS],
    EventType.PERMISSION_REVOKED: [EventChannel.AUTHZ_EVENTS, EventChannel.SECURITY_EVENTS, EventChannel.ALL_EVENTS],
    EventType.ROLE_ASSIGNED: [EventChannel.AUTHZ_EVENTS, EventChannel.SECURITY_EVENTS, EventChannel.ALL_EVENTS],
    EventType.ROLE_REVOKED: [EventChannel.AUTHZ_EVENTS, EventChannel.SECURITY_EVENTS, EventChannel.ALL_EVENTS],

    # Preferences events
    EventType.PREFERENCES_UPDATED: [EventChannel.USER_EVENTS, EventChannel.ALL_EVENTS],

    # Trading account events
    EventType.TRADING_ACCOUNT_LINKED: [EventChannel.TRADING_ACCOUNT_EVENTS, EventChannel.ALL_EVENTS],
    EventType.TRADING_ACCOUNT_UNLINKED: [EventChannel.TRADING_ACCOUNT_EVENTS, EventChannel.ALL_EVENTS],
    EventType.TRADING_ACCOUNT_UPDATED: [EventChannel.TRADING_ACCOUNT_EVENTS, EventChannel.ALL_EVENTS],
    EventType.MEMBERSHIP_GRANTED: [EventChannel.TRADING_ACCOUNT_EVENTS, EventChannel.AUTHZ_EVENTS, EventChannel.ALL_EVENTS],
    EventType.MEMBERSHIP_REVOKED: [EventChannel.TRADING_ACCOUNT_EVENTS, EventChannel.AUTHZ_EVENTS, EventChannel.ALL_EVENTS],

    # Password events
    EventType.PASSWORD_CHANGED: [EventChannel.AUTH_EVENTS, EventChannel.SECURITY_EVENTS, EventChannel.ALL_EVENTS],
    EventType.PASSWORD_RESET_REQUESTED: [EventChannel.AUTH_EVENTS, EventChannel.SECURITY_EVENTS, EventChannel.ALL_EVENTS],
    EventType.PASSWORD_RESET_COMPLETED: [EventChannel.AUTH_EVENTS, EventChannel.SECURITY_EVENTS, EventChannel.ALL_EVENTS],

    # Session events
    EventType.SESSION_CREATED: [EventChannel.AUTH_EVENTS, EventChannel.ALL_EVENTS],
    EventType.SESSION_REVOKED: [EventChannel.AUTH_EVENTS, EventChannel.SECURITY_EVENTS, EventChannel.ALL_EVENTS],
}
