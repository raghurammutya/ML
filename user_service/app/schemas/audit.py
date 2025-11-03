"""
Audit schemas

Audit trail and event logging for user actions.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, validator


class AuditEventResponse(BaseModel):
    """Single audit event"""
    event_id: str = Field(
        ...,
        description="Unique event ID"
    )
    event_type: str = Field(
        ...,
        description="Event type (e.g., 'user.login', 'password.changed')"
    )
    timestamp: str = Field(
        ...,
        description="Event timestamp (ISO 8601)"
    )
    subject: str = Field(
        ...,
        description="Subject of event (e.g., 'user:123')"
    )
    data: Dict[str, Any] = Field(
        default_factory=dict,
        description="Event data"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata (IP, user agent, etc.)"
    )
    priority: str = Field(
        default="normal",
        description="Event priority"
    )


class GetAuditEventsRequest(BaseModel):
    """Request parameters for getting audit events"""
    event_type: Optional[str] = Field(
        default=None,
        description="Filter by event type (e.g., 'user.login')"
    )
    start_date: Optional[datetime] = Field(
        default=None,
        description="Filter events after this date"
    )
    end_date: Optional[datetime] = Field(
        default=None,
        description="Filter events before this date"
    )
    limit: int = Field(
        default=100,
        ge=1,
        le=1000,
        description="Maximum number of events to return (1-1000)"
    )
    offset: int = Field(
        default=0,
        ge=0,
        description="Number of events to skip"
    )

    @validator('end_date')
    def validate_date_range(cls, v, values):
        """Validate that end_date is after start_date"""
        if v and 'start_date' in values and values['start_date']:
            if v < values['start_date']:
                raise ValueError("end_date must be after start_date")
        return v


class GetAuditEventsResponse(BaseModel):
    """Response for audit events query"""
    events: List[AuditEventResponse] = Field(
        default_factory=list,
        description="List of audit events"
    )
    total: int = Field(
        ...,
        description="Total number of matching events"
    )
    limit: int = Field(
        ...,
        description="Limit applied to query"
    )
    offset: int = Field(
        ...,
        description="Offset applied to query"
    )
    has_more: bool = Field(
        ...,
        description="Whether more events are available"
    )


class ExportAuditEventsRequest(BaseModel):
    """Request to export audit events"""
    format: str = Field(
        default="json",
        description="Export format: 'json' or 'csv'"
    )
    event_type: Optional[str] = Field(
        default=None,
        description="Filter by event type"
    )
    start_date: Optional[datetime] = Field(
        default=None,
        description="Filter events after this date"
    )
    end_date: Optional[datetime] = Field(
        default=None,
        description="Filter events before this date"
    )

    @validator('format')
    def validate_format(cls, v):
        """Validate export format"""
        allowed = ['json', 'csv']
        if v.lower() not in allowed:
            raise ValueError(f"format must be one of {allowed}")
        return v.lower()

    @validator('end_date')
    def validate_date_range(cls, v, values):
        """Validate that end_date is after start_date"""
        if v and 'start_date' in values and values['start_date']:
            if v < values['start_date']:
                raise ValueError("end_date must be after start_date")
        return v


class ExportAuditEventsResponse(BaseModel):
    """Response for audit export"""
    export_id: str = Field(
        ...,
        description="Unique export ID"
    )
    format: str = Field(
        ...,
        description="Export format"
    )
    total_events: int = Field(
        ...,
        description="Total events exported"
    )
    created_at: str = Field(
        ...,
        description="Export creation timestamp"
    )
    expires_at: str = Field(
        ...,
        description="Export expiration timestamp (24 hours)"
    )
    download_url: Optional[str] = Field(
        default=None,
        description="URL to download export (if available)"
    )
    data: Optional[Any] = Field(
        default=None,
        description="Export data (for small exports)"
    )
