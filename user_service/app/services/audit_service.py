"""
Audit Service

Handles audit trail queries and exports for user actions.
"""

import json
import csv
import io
import secrets
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timedelta

from app.core.redis_client import RedisClient
from app.schemas.audit import AuditEventResponse


class AuditService:
    """Service for audit trail queries and exports"""

    def __init__(self, redis: RedisClient):
        self.redis = redis

    def get_user_audit_events(
        self,
        user_id: int,
        event_type: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Tuple[List[AuditEventResponse], int]:
        """
        Get audit events for a specific user

        Queries Redis streams for events related to the user and applies filters.

        Args:
            user_id: User ID to get events for
            event_type: Optional event type filter (e.g., 'user.login')
            start_date: Optional start date filter
            end_date: Optional end date filter
            limit: Maximum number of events to return (1-1000)
            offset: Number of events to skip

        Returns:
            Tuple of (events list, total count)

        Note:
            Events are stored in Redis streams with pattern 'events:{event_type}'.
            We query all event types and filter by subject (user:{user_id}).
        """
        # Define event types to query
        event_types = [
            "user.login",
            "user.logout",
            "user.registered",
            "user.updated",
            "user.deleted",
            "password.changed",
            "password.reset_requested",
            "password.reset_completed",
            "session.created",
            "session.revoked",
            "mfa.enabled",
            "mfa.disabled",
            "trading_account.linked",
            "trading_account.unlinked",
            "trading_account.credentials_updated",
            "permission.granted",
            "permission.revoked"
        ]

        # If event_type specified, only query that type
        if event_type:
            event_types = [event_type]

        all_events = []

        # Query each event type stream
        for et in event_types:
            stream_key = f"events:{et}"

            try:
                # Read all events from stream (XRANGE 0 +)
                # In production, this should use time-based ranges for efficiency
                stream_data = self.redis.client.xrange(stream_key, min="-", max="+")

                for event_id, event_data in stream_data:
                    # Decode bytes to strings
                    decoded_data = {}
                    for key, value in event_data.items():
                        k = key.decode() if isinstance(key, bytes) else key
                        v = value.decode() if isinstance(value, bytes) else value
                        decoded_data[k] = v

                    # Check if event is for this user
                    subject = decoded_data.get("subject", "")
                    if subject != f"user:{user_id}":
                        continue

                    # Parse event data
                    try:
                        data = json.loads(decoded_data.get("data", "{}"))
                        metadata = json.loads(decoded_data.get("metadata", "{}"))
                    except json.JSONDecodeError:
                        data = {}
                        metadata = {}

                    # Parse timestamp
                    timestamp_str = decoded_data.get("timestamp", "")
                    try:
                        event_timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                    except (ValueError, AttributeError):
                        # Skip events with invalid timestamps
                        continue

                    # Apply date filters
                    if start_date and event_timestamp < start_date:
                        continue
                    if end_date and event_timestamp > end_date:
                        continue

                    # Create event response
                    event = AuditEventResponse(
                        event_id=event_id.decode() if isinstance(event_id, bytes) else event_id,
                        event_type=decoded_data.get("event_type", et),
                        timestamp=timestamp_str,
                        subject=subject,
                        data=data,
                        metadata=metadata,
                        priority=decoded_data.get("priority", "normal")
                    )

                    all_events.append(event)

            except Exception as e:
                # Log error but continue with other streams
                print(f"Error reading stream {stream_key}: {e}")
                continue

        # Sort events by timestamp (newest first)
        all_events.sort(key=lambda e: e.timestamp, reverse=True)

        # Get total count
        total = len(all_events)

        # Apply pagination
        paginated_events = all_events[offset:offset + limit]

        return paginated_events, total

    def export_user_audit_events(
        self,
        user_id: int,
        export_format: str = "json",
        event_type: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Export audit events for a user

        Exports all matching events to JSON or CSV format.

        Args:
            user_id: User ID to export events for
            export_format: Export format ('json' or 'csv')
            event_type: Optional event type filter
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            Dictionary with export metadata and data

        Note:
            For large exports, this should be moved to background task.
            Currently returns data inline for simplicity.
        """
        # Get all events (no pagination for export)
        events, total = self.get_user_audit_events(
            user_id=user_id,
            event_type=event_type,
            start_date=start_date,
            end_date=end_date,
            limit=10000,  # Max export size
            offset=0
        )

        # Generate export ID
        export_id = secrets.token_urlsafe(16)

        # Create export
        if export_format == "json":
            # Convert to JSON
            events_data = [
                {
                    "event_id": e.event_id,
                    "event_type": e.event_type,
                    "timestamp": e.timestamp,
                    "subject": e.subject,
                    "data": e.data,
                    "metadata": e.metadata,
                    "priority": e.priority
                }
                for e in events
            ]

            export_data = json.dumps(events_data, indent=2)

        elif export_format == "csv":
            # Convert to CSV
            output = io.StringIO()
            writer = csv.writer(output)

            # Write header
            writer.writerow([
                "event_id",
                "event_type",
                "timestamp",
                "subject",
                "data",
                "metadata",
                "priority"
            ])

            # Write rows
            for e in events:
                writer.writerow([
                    e.event_id,
                    e.event_type,
                    e.timestamp,
                    e.subject,
                    json.dumps(e.data),
                    json.dumps(e.metadata),
                    e.priority
                ])

            export_data = output.getvalue()

        else:
            raise ValueError(f"Unsupported export format: {export_format}")

        # Store export in Redis with 24 hour expiry
        export_key = f"audit_export:{export_id}"
        self.redis.client.setex(
            export_key,
            86400,  # 24 hours
            export_data
        )

        # Calculate expiry
        created_at = datetime.utcnow()
        expires_at = created_at + timedelta(hours=24)

        return {
            "export_id": export_id,
            "format": export_format,
            "total_events": total,
            "created_at": created_at.isoformat(),
            "expires_at": expires_at.isoformat(),
            "download_url": None,  # TODO: Implement download endpoint
            "data": export_data if total < 100 else None  # Only include data for small exports
        }

    def get_export(self, export_id: str) -> Optional[str]:
        """
        Get export data by ID

        Args:
            export_id: Export ID

        Returns:
            Export data string or None if not found/expired
        """
        export_key = f"audit_export:{export_id}"
        export_data = self.redis.client.get(export_key)

        if not export_data:
            return None

        return export_data.decode() if isinstance(export_data, bytes) else export_data
