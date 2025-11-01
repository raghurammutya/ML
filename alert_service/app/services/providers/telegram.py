"""
Telegram Notification Provider
Sends alerts via Telegram Bot API
Adapted from margin-planner telegram_notification_service.py
"""

import logging
import httpx
from typing import Dict, Any, Optional

from .base import NotificationProvider, NotificationResult

logger = logging.getLogger(__name__)


class TelegramProvider(NotificationProvider):
    """Telegram Bot API notification provider."""

    def __init__(self, bot_token: str):
        """
        Initialize Telegram provider.

        Args:
            bot_token: Telegram bot token from BotFather
        """
        self.bot_token = bot_token
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
        self.client = httpx.AsyncClient(timeout=10.0)

    async def send(
        self,
        recipient: str,  # chat_id
        message: str,
        priority: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> NotificationResult:
        """
        Send message via Telegram Bot API.

        Args:
            recipient: Telegram chat_id
            message: Message text (supports Markdown)
            priority: Alert priority (low, medium, high, critical)
            metadata: Alert metadata (alert_id, event_id, etc.)

        Returns:
            NotificationResult with delivery status
        """
        try:
            # Format message with priority emoji
            emoji_map = {
                "critical": "🚨",
                "high": "⚠️",
                "medium": "ℹ️",
                "low": "📢",
            }
            emoji = emoji_map.get(priority, "📢")
            formatted_message = f"{emoji} {message}"

            # Build request payload
            url = f"{self.base_url}/sendMessage"
            payload = {
                "chat_id": recipient,
                "text": formatted_message,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True,
            }

            # Add interactive buttons for critical/high priority alerts
            if priority in ["critical", "high"] and metadata:
                payload["reply_markup"] = self._build_reply_markup(metadata)

            # Send message
            response = await self.client.post(url, json=payload)
            response.raise_for_status()
            result = response.json()

            if result.get("ok"):
                logger.info(f"Telegram message sent to {recipient}: {result['result']['message_id']}")
                return NotificationResult(
                    success=True,
                    message_id=str(result["result"]["message_id"]),
                    provider_response=result,
                )
            else:
                logger.error(f"Telegram API error: {result}")
                return NotificationResult(
                    success=False,
                    error_message=result.get("description", "Unknown error"),
                    provider_response=result,
                )

        except httpx.HTTPStatusError as e:
            logger.error(f"Telegram HTTP error: {e.response.status_code} - {e.response.text}")
            return NotificationResult(
                success=False,
                error_message=f"HTTP {e.response.status_code}: {e.response.text}",
            )
        except Exception as e:
            logger.error(f"Telegram send failed: {e}", exc_info=True)
            return NotificationResult(
                success=False,
                error_message=str(e),
            )

    async def validate_recipient(self, recipient: str) -> bool:
        """
        Validate Telegram chat_id.

        Args:
            recipient: Telegram chat_id

        Returns:
            True if valid format (numeric or starts with -)
        """
        try:
            # Telegram chat_id is numeric (can be negative for groups)
            int(recipient)
            return True
        except ValueError:
            return False

    async def get_status(self, message_id: str) -> Optional[str]:
        """
        Get message delivery status.

        Note: Telegram doesn't provide a direct API for message status.
        This would require webhook setup to receive updates.

        Args:
            message_id: Telegram message_id

        Returns:
            Status string (always "sent" for Telegram)
        """
        # Telegram doesn't provide status API
        # Would need webhook to track delivery/read status
        return "sent"

    async def get_bot_info(self) -> Dict[str, Any]:
        """
        Get information about the bot.

        Returns:
            Bot information from Telegram API
        """
        try:
            url = f"{self.base_url}/getMe"
            response = await self.client.get(url)
            response.raise_for_status()
            result = response.json()

            if result.get("ok"):
                return result["result"]
            else:
                logger.error(f"Failed to get bot info: {result}")
                return {"error": result.get("description")}

        except Exception as e:
            logger.error(f"Failed to get bot info: {e}")
            return {"error": str(e)}

    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()

    def _build_reply_markup(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Build interactive button markup for Telegram message.

        Args:
            metadata: Alert metadata with event_id, alert_id

        Returns:
            reply_markup JSON
        """
        event_id = metadata.get("event_id", "")
        alert_id = metadata.get("alert_id", "")

        return {
            "inline_keyboard": [
                [
                    {
                        "text": "✅ Acknowledge",
                        "callback_data": f"ack:{event_id}",
                    },
                    {
                        "text": "💤 Snooze 1h",
                        "callback_data": f"snooze:{event_id}:3600",
                    },
                ],
                [
                    {
                        "text": "🔕 Pause Alert",
                        "callback_data": f"pause:{alert_id}",
                    },
                ],
            ]
        }


def format_alert_message(
    alert_name: str,
    alert_type: str,
    trigger_value: Dict[str, Any],
    symbol: Optional[str] = None,
    message_format: str = "rich",
) -> str:
    """
    Format alert message for Telegram.

    Args:
        alert_name: Alert name
        alert_type: Alert type (price, indicator, position, etc.)
        trigger_value: Trigger data (current_value, threshold, etc.)
        symbol: Trading symbol
        message_format: Format style (rich, compact, minimal)

    Returns:
        Formatted message string (Markdown)
    """
    if message_format == "minimal":
        return f"🔔 {alert_name}"

    if message_format == "compact":
        parts = [f"🔔 *{alert_name}*"]
        if symbol:
            parts.append(f"Symbol: {symbol}")
        if "current_value" in trigger_value:
            parts.append(f"Value: {trigger_value['current_value']}")
        return "\n".join(parts)

    # Rich format (default)
    lines = [
        f"🔔 *Alert: {alert_name}*",
        "",
        f"*Type:* {alert_type.title()}",
    ]

    if symbol:
        lines.append(f"*Symbol:* {symbol}")

    # Add trigger details based on alert type
    if alert_type == "price":
        current = trigger_value.get("current_value")
        threshold = trigger_value.get("threshold")
        operator = trigger_value.get("operator", "")
        if current and threshold:
            lines.extend([
                "",
                f"*Current:* ₹{current:,.2f}",
                f"*Threshold:* {operator} ₹{threshold:,.2f}",
            ])

    elif alert_type == "position":
        pnl = trigger_value.get("current_value")
        threshold = trigger_value.get("threshold")
        if pnl is not None and threshold is not None:
            lines.extend([
                "",
                f"*P&L:* ₹{pnl:,.2f}",
                f"*Threshold:* ₹{threshold:,.2f}",
            ])

    elif alert_type == "indicator":
        value = trigger_value.get("current_value")
        threshold = trigger_value.get("threshold")
        indicator = trigger_value.get("indicator", "")
        if value and threshold:
            lines.extend([
                "",
                f"*Indicator:* {indicator.upper()}",
                f"*Value:* {value:.2f}",
                f"*Threshold:* {threshold:.2f}",
            ])

    # Add timestamp
    from datetime import datetime
    lines.extend([
        "",
        f"*Time:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}",
    ])

    return "\n".join(lines)
