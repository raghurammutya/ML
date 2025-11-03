"""
Audit endpoints

Audit trail and event logging for user actions.
"""

from typing import Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.core.redis_client import get_redis, RedisClient
from app.api.dependencies import get_current_user
from app.models import User
from app.services.audit_service import AuditService
from app.schemas.audit import (
    GetAuditEventsResponse,
    AuditEventResponse,
    ExportAuditEventsRequest,
    ExportAuditEventsResponse
)


router = APIRouter()


@router.get("/events", response_model=GetAuditEventsResponse)
async def get_audit_events(
    event_type: Optional[str] = Query(
        default=None,
        description="Filter by event type (e.g., 'user.login')"
    ),
    start_date: Optional[datetime] = Query(
        default=None,
        description="Filter events after this date (ISO 8601)"
    ),
    end_date: Optional[datetime] = Query(
        default=None,
        description="Filter events before this date (ISO 8601)"
    ),
    limit: int = Query(
        default=100,
        ge=1,
        le=1000,
        description="Maximum number of events to return (1-1000)"
    ),
    offset: int = Query(
        default=0,
        ge=0,
        description="Number of events to skip (pagination)"
    ),
    current_user: User = Depends(get_current_user),
    redis: RedisClient = Depends(get_redis)
):
    """
    Get audit events for current user

    Returns paginated list of audit events (login, logout, password changes, etc.).

    **Query Parameters:**
    - event_type: Filter by specific event type (optional)
    - start_date: Filter events after this date (optional, ISO 8601 format)
    - end_date: Filter events before this date (optional, ISO 8601 format)
    - limit: Maximum events to return (default: 100, max: 1000)
    - offset: Skip N events for pagination (default: 0)

    **Returns:**
    - events: List of audit events
    - total: Total number of matching events
    - limit: Limit applied to query
    - offset: Offset applied to query
    - has_more: Whether more events are available

    **Event Types:**
    - user.login: User logged in
    - user.logout: User logged out
    - user.registered: User account created
    - user.updated: User profile updated
    - password.changed: Password changed
    - password.reset_requested: Password reset requested
    - password.reset_completed: Password reset completed
    - session.created: New session created
    - session.revoked: Session revoked
    - mfa.enabled: MFA enabled
    - mfa.disabled: MFA disabled
    - trading_account.linked: Trading account linked
    - trading_account.unlinked: Trading account unlinked
    - permission.granted: Permission granted
    - permission.revoked: Permission revoked

    **Example:**
    ```
    GET /v1/audit/events?event_type=user.login&limit=50&offset=0
    ```

    **Response Example:**
    ```json
    {
      "events": [
        {
          "event_id": "1234567890-0",
          "event_type": "user.login",
          "timestamp": "2025-01-15T10:30:00Z",
          "subject": "user:123",
          "data": {
            "user_id": 123,
            "session_id": "abc123",
            "auth_method": "password"
          },
          "metadata": {
            "ip": "192.168.1.1",
            "device_fingerprint": "xyz789"
          },
          "priority": "normal"
        }
      ],
      "total": 156,
      "limit": 50,
      "offset": 0,
      "has_more": true
    }
    ```

    **Errors:**
    - 401: Invalid or missing authentication token
    - 400: Invalid query parameters
    """
    audit_service = AuditService(redis)

    try:
        # Validate date range
        if start_date and end_date and end_date < start_date:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="end_date must be after start_date"
            )

        # Get events
        events, total = audit_service.get_user_audit_events(
            user_id=current_user.user_id,
            event_type=event_type,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            offset=offset
        )

        return GetAuditEventsResponse(
            events=events,
            total=total,
            limit=limit,
            offset=offset,
            has_more=(offset + len(events)) < total
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve audit events: {str(e)}"
        )


@router.post("/export", response_model=ExportAuditEventsResponse)
async def export_audit_events(
    request_data: ExportAuditEventsRequest,
    current_user: User = Depends(get_current_user),
    redis: RedisClient = Depends(get_redis)
):
    """
    Export audit events for current user

    Creates an export of audit events in JSON or CSV format.
    Exports are stored for 24 hours and can be downloaded.

    **Request Body:**
    - format: Export format ('json' or 'csv')
    - event_type: Optional event type filter
    - start_date: Optional start date filter (ISO 8601)
    - end_date: Optional end date filter (ISO 8601)

    **Returns:**
    - export_id: Unique export ID
    - format: Export format
    - total_events: Total events exported
    - created_at: Export creation timestamp
    - expires_at: Export expiration timestamp (24 hours)
    - download_url: URL to download export (TODO)
    - data: Export data (for small exports < 100 events)

    **Example Request:**
    ```json
    {
      "format": "json",
      "event_type": "user.login",
      "start_date": "2025-01-01T00:00:00Z",
      "end_date": "2025-01-31T23:59:59Z"
    }
    ```

    **Example Response:**
    ```json
    {
      "export_id": "abc123xyz",
      "format": "json",
      "total_events": 45,
      "created_at": "2025-01-15T10:30:00Z",
      "expires_at": "2025-01-16T10:30:00Z",
      "download_url": null,
      "data": "[{...}]"
    }
    ```

    **Notes:**
    - Exports are limited to 10,000 events max
    - Exports expire after 24 hours
    - For exports < 100 events, data is included in response
    - For larger exports, use download_url (TODO: implement)
    - In production, large exports should be background tasks

    **Errors:**
    - 401: Invalid or missing authentication token
    - 400: Invalid request parameters or format
    - 413: Export too large (> 10,000 events)
    """
    audit_service = AuditService(redis)

    try:
        # Validate date range
        if request_data.start_date and request_data.end_date:
            if request_data.end_date < request_data.start_date:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="end_date must be after start_date"
                )

        # Create export
        export_result = audit_service.export_user_audit_events(
            user_id=current_user.user_id,
            export_format=request_data.format,
            event_type=request_data.event_type,
            start_date=request_data.start_date,
            end_date=request_data.end_date
        )

        return ExportAuditEventsResponse(**export_result)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to export audit events: {str(e)}"
        )


@router.get("/export/{export_id}")
async def download_audit_export(
    export_id: str,
    current_user: User = Depends(get_current_user),
    redis: RedisClient = Depends(get_redis)
):
    """
    Download audit export by ID

    Downloads a previously created audit export.

    **Path Parameters:**
    - export_id: Export ID from export creation

    **Returns:**
    - Export data in requested format (JSON or CSV)

    **Example:**
    ```
    GET /v1/audit/export/abc123xyz
    ```

    **Errors:**
    - 401: Invalid or missing authentication token
    - 404: Export not found or expired
    """
    audit_service = AuditService(redis)

    # Get export data
    export_data = audit_service.get_export(export_id)

    if not export_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Export not found or expired"
        )

    # Return as plain text (client can parse based on format)
    # TODO: Set proper content-type header based on format
    return export_data
