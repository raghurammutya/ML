"""
Base Notification Provider
Abstract interface for notification providers
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional


class NotificationResult:
    """Result of sending a notification."""

    def __init__(
        self,
        success: bool,
        message_id: Optional[str] = None,
        error_message: Optional[str] = None,
        provider_response: Optional[Dict[str, Any]] = None,
    ):
        self.success = success
        self.message_id = message_id
        self.error_message = error_message
        self.provider_response = provider_response

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "message_id": self.message_id,
            "error_message": self.error_message,
            "provider_response": self.provider_response,
        }


class NotificationProvider(ABC):
    """Abstract base class for notification providers."""

    @abstractmethod
    async def send(
        self,
        recipient: str,
        message: str,
        priority: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> NotificationResult:
        """
        Send notification via this channel.

        Args:
            recipient: Channel-specific recipient (chat_id, email, device_token, etc.)
            message: Message content
            priority: Alert priority (low, medium, high, critical)
            metadata: Additional metadata (alert_id, event_id, etc.)

        Returns:
            NotificationResult with delivery status
        """
        pass

    @abstractmethod
    async def validate_recipient(self, recipient: str) -> bool:
        """
        Validate recipient identifier.

        Args:
            recipient: Recipient identifier

        Returns:
            True if valid, False otherwise
        """
        pass

    @abstractmethod
    async def get_status(self, message_id: str) -> Optional[str]:
        """
        Get delivery status of sent message.

        Args:
            message_id: Provider-specific message ID

        Returns:
            Status string or None if not found
        """
        pass

    async def close(self):
        """
        Close provider resources (HTTP clients, etc.).
        Override in subclass if needed.
        """
        pass
