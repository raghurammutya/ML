"""
Notification Service
Manages notification delivery across multiple channels
"""

import logging
import json
from datetime import datetime, time as dt_time
from typing import Dict, Any, List, Optional
from uuid import UUID

import asyncpg

from ..database import DatabaseManager
from ..models.notification import NotificationPreferences, NotificationPreferencesUpdate
from .providers.base import NotificationProvider
from .providers.telegram import TelegramProvider, format_alert_message

logger = logging.getLogger(__name__)


class NotificationService:
    """
    Manages notification delivery and user preferences.
    """

    def __init__(self, db_manager: DatabaseManager, telegram_bot_token: str):
        self.db = db_manager
        self.providers: Dict[str, NotificationProvider] = {}

        # Initialize Telegram provider
        if telegram_bot_token:
            self.providers["telegram"] = TelegramProvider(telegram_bot_token)
            logger.info("Telegram provider initialized")

    async def send_notification(
        self,
        user_id: str,
        alert_id: UUID,
        event_id: UUID,
        alert_name: str,
        alert_type: str,
        priority: str,
        trigger_value: Dict[str, Any],
        symbol: Optional[str] = None,
        channels: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Send notification to user across specified channels.

        Args:
            user_id: User identifier
            alert_id: Alert identifier
            event_id: Event identifier
            alert_name: Alert name
            alert_type: Alert type
            priority: Alert priority
            trigger_value: Trigger data
            symbol: Trading symbol
            channels: Notification channels (default: from preferences)

        Returns:
            Dictionary with send results per channel
        """
        try:
            # Get user preferences
            prefs = await self.get_preferences(user_id)

            # Check quiet hours
            if prefs and not await self._check_quiet_hours(prefs, priority):
                logger.info(f"Skipping notification for user {user_id} (quiet hours)")
                return {"skipped": True, "reason": "quiet_hours"}

            # Check rate limits
            if prefs and not await self._check_rate_limit(user_id, prefs):
                logger.info(f"Skipping notification for user {user_id} (rate limit)")
                return {"skipped": True, "reason": "rate_limit"}

            # Determine channels to use
            if not channels:
                channels = self._get_enabled_channels(prefs)

            if not channels:
                logger.warning(f"No notification channels enabled for user {user_id}")
                return {"skipped": True, "reason": "no_channels"}

            # Format message
            message_format = prefs.notification_format if prefs else "rich"
            message = format_alert_message(
                alert_name=alert_name,
                alert_type=alert_type,
                trigger_value=trigger_value,
                symbol=symbol,
                message_format=message_format,
            )

            # Metadata for interactive buttons
            metadata = {
                "alert_id": str(alert_id),
                "event_id": str(event_id),
                "user_id": user_id,
            }

            # Send notifications
            results = {}
            for channel in channels:
                result = await self._send_to_channel(
                    channel=channel,
                    user_id=user_id,
                    recipient=self._get_recipient(prefs, channel),
                    message=message,
                    priority=priority,
                    metadata=metadata,
                )

                # Log notification
                if result:
                    await self._log_notification(
                        event_id=event_id,
                        channel=channel,
                        recipient=self._get_recipient(prefs, channel),
                        message=message,
                        result=result,
                    )

                results[channel] = result.to_dict() if result else {"error": "No provider"}

            return {"sent": True, "results": results}

        except Exception as e:
            logger.error(f"Failed to send notification: {e}", exc_info=True)
            return {"error": str(e)}

    async def get_preferences(self, user_id: str) -> Optional[NotificationPreferences]:
        """
        Get user notification preferences.

        Args:
            user_id: User identifier

        Returns:
            NotificationPreferences or None if not found
        """
        try:
            query = "SELECT * FROM notification_preferences WHERE user_id = $1"

            async with self.db.pool.acquire() as conn:
                row = await conn.fetchrow(query, user_id)

            if row:
                return NotificationPreferences(**dict(row))

            # Return default preferences if not found
            return NotificationPreferences(user_id=user_id)

        except Exception as e:
            logger.error(f"Failed to get preferences: {e}", exc_info=True)
            return None

    async def update_preferences(
        self,
        user_id: str,
        update_data: NotificationPreferencesUpdate,
    ) -> NotificationPreferences:
        """
        Update user notification preferences.

        Args:
            user_id: User identifier
            update_data: Fields to update

        Returns:
            Updated preferences
        """
        try:
            # Check if preferences exist
            existing = await self.get_preferences(user_id)

            if not existing or not existing.created_at:
                # Create new preferences
                query = """
                    INSERT INTO notification_preferences (
                        user_id, telegram_enabled, telegram_chat_id,
                        fcm_enabled, fcm_device_tokens,
                        email_enabled, email_addresses,
                        quiet_hours_start, quiet_hours_end, quiet_hours_timezone,
                        max_notifications_per_hour, priority_threshold,
                        notification_format, include_chart_images
                    ) VALUES (
                        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14
                    )
                    RETURNING *
                """

                async with self.db.pool.acquire() as conn:
                    row = await conn.fetchrow(
                        query,
                        user_id,
                        update_data.telegram_enabled if update_data.telegram_enabled is not None else False,
                        update_data.telegram_chat_id,
                        update_data.fcm_enabled if update_data.fcm_enabled is not None else False,
                        update_data.fcm_device_tokens or [],
                        update_data.email_enabled if update_data.email_enabled is not None else False,
                        update_data.email_addresses or [],
                        update_data.quiet_hours_start,
                        update_data.quiet_hours_end,
                        update_data.quiet_hours_timezone,
                        update_data.max_notifications_per_hour,
                        update_data.priority_threshold,
                        update_data.notification_format,
                        update_data.include_chart_images,
                    )

            else:
                # Update existing preferences
                update_fields = []
                params = []
                param_counter = 1

                field_mapping = {
                    "telegram_enabled": "telegram_enabled",
                    "telegram_chat_id": "telegram_chat_id",
                    "fcm_enabled": "fcm_enabled",
                    "fcm_device_tokens": "fcm_device_tokens",
                    "email_enabled": "email_enabled",
                    "email_addresses": "email_addresses",
                    "quiet_hours_start": "quiet_hours_start",
                    "quiet_hours_end": "quiet_hours_end",
                    "quiet_hours_timezone": "quiet_hours_timezone",
                    "max_notifications_per_hour": "max_notifications_per_hour",
                    "priority_threshold": "priority_threshold",
                    "notification_format": "notification_format",
                    "include_chart_images": "include_chart_images",
                }

                for field, db_column in field_mapping.items():
                    value = getattr(update_data, field, None)
                    if value is not None:
                        update_fields.append(f"{db_column} = ${param_counter}")
                        params.append(value)
                        param_counter += 1

                if not update_fields:
                    return existing

                query = f"""
                    UPDATE notification_preferences
                    SET {', '.join(update_fields)}, updated_at = NOW()
                    WHERE user_id = ${param_counter}
                    RETURNING *
                """
                params.append(user_id)

                async with self.db.pool.acquire() as conn:
                    row = await conn.fetchrow(query, *params)

            return NotificationPreferences(**dict(row))

        except Exception as e:
            logger.error(f"Failed to update preferences: {e}", exc_info=True)
            raise

    async def _send_to_channel(
        self,
        channel: str,
        user_id: str,
        recipient: Optional[str],
        message: str,
        priority: str,
        metadata: Dict[str, Any],
    ):
        """Send notification to specific channel."""
        if channel not in self.providers:
            logger.warning(f"No provider for channel: {channel}")
            return None

        if not recipient:
            logger.warning(f"No recipient configured for channel {channel} (user {user_id})")
            return None

        provider = self.providers[channel]
        return await provider.send(recipient, message, priority, metadata)

    def _get_enabled_channels(self, prefs: Optional[NotificationPreferences]) -> List[str]:
        """Get list of enabled notification channels."""
        if not prefs:
            return []

        channels = []
        if prefs.telegram_enabled and prefs.telegram_chat_id:
            channels.append("telegram")
        if prefs.fcm_enabled and prefs.fcm_device_tokens:
            channels.append("fcm")
        if prefs.email_enabled and prefs.email_addresses:
            channels.append("email")

        return channels

    def _get_recipient(self, prefs: Optional[NotificationPreferences], channel: str) -> Optional[str]:
        """Get recipient for specific channel."""
        if not prefs:
            return None

        if channel == "telegram":
            return prefs.telegram_chat_id
        elif channel == "fcm":
            return prefs.fcm_device_tokens[0] if prefs.fcm_device_tokens else None
        elif channel == "email":
            return prefs.email_addresses[0] if prefs.email_addresses else None

        return None

    async def _check_quiet_hours(self, prefs: NotificationPreferences, priority: str) -> bool:
        """
        Check if notification should be sent during quiet hours.

        Returns:
            True if should send, False if should skip
        """
        if not prefs.quiet_hours_start or not prefs.quiet_hours_end:
            return True

        # Get current time in user's timezone
        from datetime import datetime
        import pytz

        try:
            tz = pytz.timezone(prefs.quiet_hours_timezone)
            current_time = datetime.now(tz).time()

            # Check if in quiet hours
            start = prefs.quiet_hours_start
            end = prefs.quiet_hours_end

            if start <= end:
                in_quiet_hours = start <= current_time <= end
            else:
                # Handles overnight quiet hours (e.g., 22:00 - 08:00)
                in_quiet_hours = current_time >= start or current_time <= end

            if in_quiet_hours:
                # Check priority threshold
                priority_levels = {"low": 0, "medium": 1, "high": 2, "critical": 3}
                priority_value = priority_levels.get(priority, 0)
                threshold_value = priority_levels.get(prefs.priority_threshold, 0)

                return priority_value >= threshold_value

            return True

        except Exception as e:
            logger.error(f"Error checking quiet hours: {e}")
            return True  # Send on error

    async def _check_rate_limit(self, user_id: str, prefs: NotificationPreferences) -> bool:
        """
        Check if user has exceeded notification rate limit.

        Returns:
            True if can send, False if rate limited
        """
        try:
            # Count notifications sent in last hour
            query = """
                SELECT COUNT(*) as count
                FROM notification_log
                WHERE sent_at >= NOW() - INTERVAL '1 hour'
                  AND recipient = $1
                  AND status != 'failed'
            """

            # Get recipient for counting
            recipient = prefs.telegram_chat_id if prefs.telegram_enabled else None
            if not recipient:
                return True

            async with self.db.pool.acquire() as conn:
                row = await conn.fetchrow(query, recipient)

            count = row["count"] if row else 0
            return count < prefs.max_notifications_per_hour

        except Exception as e:
            logger.error(f"Error checking rate limit: {e}")
            return True  # Allow on error

    async def _log_notification(
        self,
        event_id: UUID,
        channel: str,
        recipient: str,
        message: str,
        result: Any,
    ):
        """Log notification delivery."""
        try:
            query = """
                INSERT INTO notification_log (
                    event_id, channel, recipient,
                    status, message_id, message_content
                ) VALUES ($1, $2, $3, $4, $5, $6)
            """

            status = "sent" if result.success else "failed"
            message_id = result.message_id if result.success else None

            async with self.db.pool.acquire() as conn:
                await conn.execute(
                    query,
                    str(event_id),
                    channel,
                    recipient,
                    status,
                    message_id,
                    message[:500],  # Truncate message for storage
                )

        except Exception as e:
            logger.error(f"Failed to log notification: {e}")

    async def close(self):
        """Close all notification providers."""
        for provider in self.providers.values():
            await provider.close()
