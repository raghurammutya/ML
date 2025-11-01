"""
Alert Pydantic Models
Defines request/response schemas for alerts
"""

from datetime import datetime, time
from typing import Optional, List, Dict, Any
from uuid import UUID
from pydantic import BaseModel, Field, field_validator


class AlertBase(BaseModel):
    """Base alert model with common fields."""

    name: str = Field(..., min_length=1, max_length=255, description="Alert name")
    description: Optional[str] = Field(None, description="Alert description")
    alert_type: str = Field(..., description="Alert type")
    priority: str = Field(default="medium", description="Alert priority")
    condition_config: Dict[str, Any] = Field(..., description="Condition configuration")

    symbol: Optional[str] = Field(None, max_length=50, description="Trading symbol")
    symbols: Optional[List[str]] = Field(None, description="Multiple symbols")
    exchange: Optional[str] = Field(None, max_length=10, description="Exchange")

    notification_channels: List[str] = Field(
        default=["telegram"], description="Notification channels"
    )
    notification_config: Optional[Dict[str, Any]] = Field(
        None, description="Channel-specific config"
    )
    notification_template: Optional[str] = Field(None, description="Custom message template")

    evaluation_interval_seconds: int = Field(
        default=60, ge=10, le=3600, description="Evaluation interval (10-3600 seconds)"
    )
    evaluation_window_start: Optional[time] = Field(None, description="Start time for evaluation")
    evaluation_window_end: Optional[time] = Field(None, description="End time for evaluation")
    max_triggers_per_day: Optional[int] = Field(None, ge=1, description="Daily trigger limit")
    cooldown_seconds: int = Field(default=300, ge=0, description="Cooldown between triggers")

    expires_at: Optional[datetime] = Field(None, description="Alert expiration time")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Custom metadata")

    @field_validator("alert_type")
    @classmethod
    def validate_alert_type(cls, v: str) -> str:
        """Validate alert type."""
        valid_types = {"price", "indicator", "position", "greek", "order", "time", "custom", "strategy"}
        if v not in valid_types:
            raise ValueError(f"alert_type must be one of {valid_types}, got '{v}'")
        return v

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v: str) -> str:
        """Validate priority."""
        valid_priorities = {"low", "medium", "high", "critical"}
        if v not in valid_priorities:
            raise ValueError(f"priority must be one of {valid_priorities}, got '{v}'")
        return v

    @field_validator("notification_channels")
    @classmethod
    def validate_channels(cls, v: List[str]) -> List[str]:
        """Validate notification channels."""
        valid_channels = {"telegram", "fcm", "apns", "email", "sms", "webhook"}
        for channel in v:
            if channel not in valid_channels:
                raise ValueError(f"Invalid channel '{channel}'. Must be one of {valid_channels}")
        return v


class AlertCreate(AlertBase):
    """Model for creating a new alert."""

    account_id: Optional[str] = Field(None, description="Trading account ID")
    strategy_id: Optional[UUID] = Field(None, description="Strategy ID")


class AlertUpdate(BaseModel):
    """Model for updating an existing alert."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    priority: Optional[str] = None
    condition_config: Optional[Dict[str, Any]] = None
    status: Optional[str] = None

    notification_channels: Optional[List[str]] = None
    notification_config: Optional[Dict[str, Any]] = None
    notification_template: Optional[str] = None

    evaluation_interval_seconds: Optional[int] = Field(None, ge=10, le=3600)
    evaluation_window_start: Optional[time] = None
    evaluation_window_end: Optional[time] = None
    max_triggers_per_day: Optional[int] = Field(None, ge=1)
    cooldown_seconds: Optional[int] = Field(None, ge=0)

    expires_at: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v: Optional[str]) -> Optional[str]:
        """Validate priority."""
        if v is None:
            return v
        valid_priorities = {"low", "medium", "high", "critical"}
        if v not in valid_priorities:
            raise ValueError(f"priority must be one of {valid_priorities}, got '{v}'")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
        """Validate status."""
        if v is None:
            return v
        valid_statuses = {"active", "paused", "triggered", "expired", "deleted"}
        if v not in valid_statuses:
            raise ValueError(f"status must be one of {valid_statuses}, got '{v}'")
        return v


class Alert(AlertBase):
    """Complete alert model with all fields."""

    alert_id: UUID
    user_id: str
    account_id: Optional[str] = None
    strategy_id: Optional[UUID] = None

    condition_type: str
    status: str

    trigger_count: int = 0
    last_triggered_at: Optional[datetime] = None
    last_evaluated_at: Optional[datetime] = None
    evaluation_count: int = 0

    created_at: datetime
    updated_at: datetime
    created_by: Optional[str] = None

    class Config:
        from_attributes = True


class AlertList(BaseModel):
    """Paginated list of alerts."""

    status: str = "success"
    count: int
    alerts: List[Alert]
    total: Optional[int] = None
    page: Optional[int] = None
    page_size: Optional[int] = None


class AlertActionResponse(BaseModel):
    """Response for alert actions (pause, resume, acknowledge, etc.)."""

    status: str = "success"
    alert_id: UUID
    action: str
    message: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class AlertTestResult(BaseModel):
    """Result from testing an alert condition."""

    would_trigger: bool
    current_value: Optional[Any] = None
    threshold: Optional[Any] = None
    condition_met: bool
    evaluation_time_ms: float
    message: str
    evaluation_details: Optional[Dict[str, Any]] = None
