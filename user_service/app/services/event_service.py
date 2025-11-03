"""
Event Publishing Service

Publishes events to Redis pub/sub channels for inter-service communication.
Other services can subscribe to these channels to react to user service events.

Architecture:
- Events published to Redis pub/sub
- Multiple channels for event filtering
- JSON serialization for cross-language compatibility
- Fire-and-forget pattern (non-blocking)
- Graceful degradation on publish failure (logs error, doesn't block operation)
"""

import uuid
import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
from redis import Redis

from app.core.redis_client import RedisClient
from app.schemas.events import (
    Event,
    EventType,
    EventPriority,
    EventChannel,
    EVENT_CHANNEL_MAP
)

logger = logging.getLogger(__name__)


class EventService:
    """Service for publishing events to Redis pub/sub"""

    def __init__(self, redis: RedisClient):
        self.redis = redis

    def publish_event(
        self,
        event_type: EventType,
        subject: Optional[str] = None,
        actor: Optional[str] = None,
        resource: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        priority: EventPriority = EventPriority.NORMAL
    ) -> Optional[str]:
        """
        Publish an event to Redis pub/sub channels

        Args:
            event_type: Type of event (from EventType enum)
            subject: Subject of the event (e.g., "user:123")
            actor: Actor who triggered the event (e.g., "user:456")
            resource: Resource affected (e.g., "trading_account:789")
            data: Event-specific data payload
            metadata: Additional metadata (IP, user agent, etc.)
            priority: Event priority

        Returns:
            Event ID (UUID) if published successfully, None on failure

        Example:
            event_service.publish_event(
                event_type=EventType.USER_REGISTERED,
                subject="user:123",
                data={"email": "user@example.com", "name": "John Doe"}
            )
        """
        try:
            # Generate event ID
            event_id = str(uuid.uuid4())

            # Create event
            event = Event(
                event_id=event_id,
                event_type=event_type,
                timestamp=datetime.utcnow().isoformat(),
                source="user_service",
                priority=priority,
                subject=subject,
                actor=actor,
                resource=resource,
                data=data or {},
                metadata=metadata or {}
            )

            # Serialize event to JSON
            event_json = event.model_dump_json()

            # Get target channels for this event type
            channels = EVENT_CHANNEL_MAP.get(event_type, [EventChannel.ALL_EVENTS])

            # Publish to all target channels
            published_count = 0
            for channel in channels:
                try:
                    # Redis PUBLISH command
                    subscriber_count = self.redis.client.publish(channel.value, event_json)
                    published_count += 1

                    logger.debug(
                        f"Published event {event_id} ({event_type.value}) to channel {channel.value} "
                        f"({subscriber_count} subscribers)"
                    )
                except Exception as e:
                    logger.error(
                        f"Failed to publish event {event_id} to channel {channel.value}: {str(e)}"
                    )

            if published_count > 0:
                logger.info(
                    f"Event {event_id} ({event_type.value}) published to {published_count} channels"
                )
                return event_id
            else:
                logger.warning(
                    f"Event {event_id} ({event_type.value}) not published to any channels"
                )
                return None

        except Exception as e:
            logger.error(f"Failed to publish event {event_type.value}: {str(e)}")
            # Graceful degradation: log error but don't raise
            # This ensures that event publishing failures don't break core operations
            return None

    def publish_user_registered(
        self,
        user_id: int,
        email: str,
        name: str,
        status: str,
        roles: List[str]
    ) -> Optional[str]:
        """Publish user.registered event"""
        return self.publish_event(
            event_type=EventType.USER_REGISTERED,
            subject=f"user:{user_id}",
            data={
                "user_id": user_id,
                "email": email,
                "name": name,
                "status": status,
                "roles": roles
            },
            priority=EventPriority.NORMAL
        )

    def publish_user_updated(
        self,
        user_id: int,
        updated_fields: List[str],
        actor_id: Optional[int] = None
    ) -> Optional[str]:
        """Publish user.updated event"""
        return self.publish_event(
            event_type=EventType.USER_UPDATED,
            subject=f"user:{user_id}",
            actor=f"user:{actor_id}" if actor_id else None,
            data={
                "user_id": user_id,
                "updated_fields": updated_fields
            }
        )

    def publish_user_deactivated(
        self,
        user_id: int,
        reason: Optional[str] = None,
        deactivated_by: Optional[int] = None
    ) -> Optional[str]:
        """Publish user.deactivated event"""
        return self.publish_event(
            event_type=EventType.USER_DEACTIVATED,
            subject=f"user:{user_id}",
            actor=f"user:{deactivated_by}" if deactivated_by else None,
            data={
                "user_id": user_id,
                "reason": reason
            },
            priority=EventPriority.HIGH
        )

    def publish_login_success(
        self,
        user_id: int,
        session_id: str,
        mfa_verified: bool,
        device_fingerprint: Optional[str] = None,
        ip: Optional[str] = None
    ) -> Optional[str]:
        """Publish login.success event"""
        return self.publish_event(
            event_type=EventType.LOGIN_SUCCESS,
            subject=f"user:{user_id}",
            data={
                "user_id": user_id,
                "session_id": session_id,
                "mfa_verified": mfa_verified,
                "device_fingerprint": device_fingerprint
            },
            metadata={
                "ip": ip
            }
        )

    def publish_mfa_enabled(
        self,
        user_id: int,
        method: str = "totp",
        backup_codes_count: int = 10
    ) -> Optional[str]:
        """Publish mfa.enabled event"""
        return self.publish_event(
            event_type=EventType.MFA_ENABLED,
            subject=f"user:{user_id}",
            data={
                "user_id": user_id,
                "method": method,
                "backup_codes_count": backup_codes_count
            },
            priority=EventPriority.HIGH
        )

    def publish_mfa_disabled(
        self,
        user_id: int,
        method: str = "totp"
    ) -> Optional[str]:
        """Publish mfa.disabled event"""
        return self.publish_event(
            event_type=EventType.MFA_DISABLED,
            subject=f"user:{user_id}",
            data={
                "user_id": user_id,
                "method": method
            },
            priority=EventPriority.HIGH
        )

    def publish_role_assigned(
        self,
        user_id: int,
        role_name: str,
        granted_by: Optional[int] = None,
        current_roles: Optional[List[str]] = None
    ) -> Optional[str]:
        """Publish role.assigned event"""
        return self.publish_event(
            event_type=EventType.ROLE_ASSIGNED,
            subject=f"user:{user_id}",
            actor=f"user:{granted_by}" if granted_by else None,
            data={
                "user_id": user_id,
                "role_name": role_name,
                "current_roles": current_roles or []
            },
            priority=EventPriority.HIGH
        )

    def publish_role_revoked(
        self,
        user_id: int,
        role_name: str,
        revoked_by: Optional[int] = None,
        current_roles: Optional[List[str]] = None
    ) -> Optional[str]:
        """Publish role.revoked event"""
        return self.publish_event(
            event_type=EventType.ROLE_REVOKED,
            subject=f"user:{user_id}",
            actor=f"user:{revoked_by}" if revoked_by else None,
            data={
                "user_id": user_id,
                "role_name": role_name,
                "current_roles": current_roles or []
            },
            priority=EventPriority.HIGH
        )

    def publish_preferences_updated(
        self,
        user_id: int,
        default_trading_account_id: Optional[int] = None
    ) -> Optional[str]:
        """Publish preferences.updated event"""
        return self.publish_event(
            event_type=EventType.PREFERENCES_UPDATED,
            subject=f"user:{user_id}",
            data={
                "user_id": user_id,
                "default_trading_account_id": default_trading_account_id
            }
        )

    def publish_trading_account_linked(
        self,
        user_id: int,
        trading_account_id: int,
        broker: str
    ) -> Optional[str]:
        """Publish trading_account.linked event"""
        return self.publish_event(
            event_type=EventType.TRADING_ACCOUNT_LINKED,
            subject=f"user:{user_id}",
            resource=f"trading_account:{trading_account_id}",
            data={
                "user_id": user_id,
                "trading_account_id": trading_account_id,
                "broker": broker
            },
            priority=EventPriority.HIGH
        )

    def publish_trading_account_unlinked(
        self,
        user_id: int,
        trading_account_id: int,
        broker: str
    ) -> Optional[str]:
        """Publish trading_account.unlinked event"""
        return self.publish_event(
            event_type=EventType.TRADING_ACCOUNT_UNLINKED,
            subject=f"user:{user_id}",
            resource=f"trading_account:{trading_account_id}",
            data={
                "user_id": user_id,
                "trading_account_id": trading_account_id,
                "broker": broker
            },
            priority=EventPriority.HIGH
        )

    def publish_membership_granted(
        self,
        user_id: int,
        trading_account_id: int,
        membership_id: int,
        permissions: List[str],
        granted_by: int
    ) -> Optional[str]:
        """Publish membership.granted event"""
        return self.publish_event(
            event_type=EventType.MEMBERSHIP_GRANTED,
            subject=f"user:{user_id}",
            actor=f"user:{granted_by}",
            resource=f"trading_account:{trading_account_id}",
            data={
                "user_id": user_id,
                "trading_account_id": trading_account_id,
                "membership_id": membership_id,
                "permissions": permissions
            },
            priority=EventPriority.HIGH
        )

    def publish_membership_revoked(
        self,
        user_id: int,
        trading_account_id: int,
        membership_id: int,
        revoked_by: int
    ) -> Optional[str]:
        """Publish membership.revoked event"""
        return self.publish_event(
            event_type=EventType.MEMBERSHIP_REVOKED,
            subject=f"user:{user_id}",
            actor=f"user:{revoked_by}",
            resource=f"trading_account:{trading_account_id}",
            data={
                "user_id": user_id,
                "trading_account_id": trading_account_id,
                "membership_id": membership_id
            },
            priority=EventPriority.HIGH
        )

    def publish_password_changed(
        self,
        user_id: int,
        changed_via: str = "profile"
    ) -> Optional[str]:
        """Publish password.changed event"""
        return self.publish_event(
            event_type=EventType.PASSWORD_CHANGED,
            subject=f"user:{user_id}",
            data={
                "user_id": user_id,
                "changed_via": changed_via
            },
            priority=EventPriority.HIGH
        )

    def publish_session_revoked(
        self,
        user_id: int,
        session_id: str,
        reason: str = "logout"
    ) -> Optional[str]:
        """Publish session.revoked event"""
        return self.publish_event(
            event_type=EventType.SESSION_REVOKED,
            subject=f"user:{user_id}",
            data={
                "user_id": user_id,
                "session_id": session_id,
                "reason": reason
            }
        )


# Singleton instance (optional)
_event_service: Optional[EventService] = None


def get_event_service(redis: RedisClient) -> EventService:
    """
    Get or create EventService singleton

    Args:
        redis: Redis client instance

    Returns:
        EventService instance
    """
    global _event_service
    if _event_service is None:
        _event_service = EventService(redis)
    return _event_service
