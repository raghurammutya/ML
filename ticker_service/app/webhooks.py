"""
Webhook Notifications System

Delivers HTTP POST callbacks when order status changes.
"""
from __future__ import annotations

import asyncio
import httpx
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone

from loguru import logger


@dataclass
class WebhookSubscription:
    """Webhook subscription configuration"""
    webhook_id: str
    url: str
    account_id: str
    events: List[str] = field(default_factory=lambda: ["order_placed", "order_completed", "order_failed"])
    secret: Optional[str] = None
    active: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class WebhookManager:
    """Manages webhook subscriptions and delivery"""

    def __init__(self):
        self._subscriptions: Dict[str, WebhookSubscription] = {}
        self._client = httpx.AsyncClient(timeout=10.0)

    def register(self, subscription: WebhookSubscription) -> None:
        """Register a webhook subscription"""
        self._subscriptions[subscription.webhook_id] = subscription
        logger.info(f"Registered webhook {subscription.webhook_id} for {subscription.url}")

    def unregister(self, webhook_id: str) -> bool:
        """Unregister a webhook subscription"""
        if webhook_id in self._subscriptions:
            del self._subscriptions[webhook_id]
            logger.info(f"Unregistered webhook {webhook_id}")
            return True
        return False

    async def notify(self, account_id: str, event: str, data: dict) -> None:
        """Send webhook notifications for an event"""
        subscriptions = [
            sub for sub in self._subscriptions.values()
            if sub.account_id == account_id and sub.active and event in sub.events
        ]

        if not subscriptions:
            return

        payload = {
            "event": event,
            "account_id": account_id,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        # Send webhooks concurrently
        tasks = [self._send_webhook(sub, payload) for sub in subscriptions]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _send_webhook(self, subscription: WebhookSubscription, payload: dict) -> None:
        """Send a single webhook"""
        try:
            headers = {"Content-Type": "application/json"}
            if subscription.secret:
                headers["X-Webhook-Secret"] = subscription.secret

            response = await self._client.post(
                subscription.url,
                json=payload,
                headers=headers
            )
            response.raise_for_status()
            logger.debug(f"Webhook delivered to {subscription.url}: {response.status_code}")

        except Exception as e:
            logger.error(f"Webhook delivery failed to {subscription.url}: {e}")

    def list_subscriptions(self, account_id: Optional[str] = None) -> List[WebhookSubscription]:
        """List webhook subscriptions"""
        if account_id:
            return [sub for sub in self._subscriptions.values() if sub.account_id == account_id]
        return list(self._subscriptions.values())

    async def close(self) -> None:
        """Close HTTP client"""
        await self._client.aclose()


# Global webhook manager
webhook_manager = WebhookManager()
