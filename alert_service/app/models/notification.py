"""
Notification Models
Defines notification preferences and delivery tracking
"""

from datetime import datetime, time
from typing import Optional, List, Dict, Any
from uuid import UUID
from pydantic import BaseModel, Field, field_validator


class NotificationPreferences(BaseModel):
    """User notification preferences."""

    user_id: str

    # Channel configurations
    telegram_enabled: bool = False
    telegram_chat_id: Optional[str] = None
    telegram_bot_token: Optional[str] = None

    fcm_enabled: bool = False
    fcm_device_tokens: List[str] = Field(default_factory=list)

    email_enabled: bool = False
    email_addresses: List[str] = Field(default_factory=list)

    # Global settings
    quiet_hours_start: Optional[time] = None
    quiet_hours_end: Optional[time] = None
    quiet_hours_timezone: str = "Asia/Kolkata"

    max_notifications_per_hour: int = Field(default=50, ge=1, le=500)
    priority_threshold: str = Field(default="low", description="Min priority during quiet hours")

    # Preferences
    notification_format: str = Field(default="rich", description="Message format style")
    include_chart_images: bool = False

    # Lifecycle
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    metadata: Optional[Dict[str, Any]] = None

    @field_validator("priority_threshold")
    @classmethod
    def validate_priority_threshold(cls, v: str) -> str:
        """Validate priority threshold."""
        valid_priorities = {"low", "medium", "high", "critical"}
        if v not in valid_priorities:
            raise ValueError(f"priority_threshold must be one of {valid_priorities}")
        return v

    @field_validator("notification_format")
    @classmethod
    def validate_notification_format(cls, v: str) -> str:
        """Validate notification format."""
        valid_formats = {"rich", "compact", "minimal"}
        if v not in valid_formats:
            raise ValueError(f"notification_format must be one of {valid_formats}")
        return v

    class Config:
        from_attributes = True


class NotificationPreferencesUpdate(BaseModel):
    """Update notification preferences."""

    telegram_enabled: Optional[bool] = None
    telegram_chat_id: Optional[str] = None

    fcm_enabled: Optional[bool] = None
    fcm_device_tokens: Optional[List[str]] = None

    email_enabled: Optional[bool] = None
    email_addresses: Optional[List[str]] = None

    quiet_hours_start: Optional[time] = None
    quiet_hours_end: Optional[time] = None
    quiet_hours_timezone: Optional[str] = None

    max_notifications_per_hour: Optional[int] = Field(None, ge=1, le=500)
    priority_threshold: Optional[str] = None

    notification_format: Optional[str] = None
    include_chart_images: Optional[bool] = None

    metadata: Optional[Dict[str, Any]] = None


class NotificationLog(BaseModel):
    """Notification delivery log entry."""

    log_id: UUID
    event_id: UUID

    sent_at: datetime
    channel: str
    recipient: str

    status: str
    status_code: Optional[int] = None
    error_message: Optional[str] = None

    message_id: Optional[str] = None
    message_content: Optional[str] = None
    message_metadata: Optional[Dict[str, Any]] = None

    delivered_at: Optional[datetime] = None
    read_at: Optional[datetime] = None
    clicked: bool = False

    class Config:
        from_attributes = True


class NotificationResult(BaseModel):
    """Result of sending a notification."""

    success: bool
    message_id: Optional[str] = None
    channel: str
    recipient: str
    error_message: Optional[str] = None
    provider_response: Optional[Dict[str, Any]] = None


class TelegramSetupRequest(BaseModel):
    """Request to set up Telegram notifications."""

    user_id: str
    bot_token: Optional[str] = None  # If None, use service default


class TelegramSetupResponse(BaseModel):
    """Response for Telegram setup."""

    bot_username: str
    setup_link: str
    verification_token: str
    expires_in: int  # seconds
    instructions: str
