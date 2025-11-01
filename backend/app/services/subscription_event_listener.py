"""
Listen to subscription lifecycle events from ticker service.

Triggers immediate backfill when subscriptions are created.
"""

import asyncio
import json
import logging
from typing import Optional
from datetime import datetime

import redis.asyncio as redis

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class SubscriptionEventListener:
    """
    Listens to ticker service subscription events via Redis pub/sub.

    Events:
    - subscription_created: Triggers immediate backfill
    - subscription_deleted: Can clean up resources
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        backfill_manager=None,  # Avoid circular import
    ):
        self._redis = redis_client
        self._backfill_manager = backfill_manager
        self._pubsub = None
        self._running = False
        self._task = None

    async def start(self):
        """Start listening to subscription events"""
        if self._running:
            logger.warning("Subscription event listener already running")
            return

        self._running = True

        # Subscribe to ticker service events channel
        self._pubsub = self._redis.pubsub()
        channel = f"{settings.redis_channel_prefix}:events"
        await self._pubsub.subscribe(channel)

        logger.info(f"Subscribed to ticker service events: {channel}")

        # Start background task
        self._task = asyncio.create_task(self._listen_loop())

    async def stop(self):
        """Stop listening"""
        self._running = False

        if self._pubsub:
            await self._pubsub.unsubscribe()
            await self._pubsub.close()

        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("Subscription event listener task did not stop gracefully")

        logger.info("Subscription event listener stopped")

    async def _listen_loop(self):
        """Main listening loop"""
        logger.info("Subscription event listener started")

        try:
            while self._running:
                try:
                    message = await self._pubsub.get_message(
                        ignore_subscribe_messages=True,
                        timeout=1.0,
                    )

                    if message and message["type"] == "message":
                        await self._handle_event(message["data"])

                except asyncio.TimeoutError:
                    # Normal timeout, continue
                    continue

        except asyncio.CancelledError:
            logger.info("Subscription event listener cancelled")
        except Exception as e:
            logger.error(f"Subscription event listener error: {e}", exc_info=True)
        finally:
            self._running = False

    async def _handle_event(self, data: bytes):
        """Handle subscription event"""
        try:
            event = json.loads(data)

            event_type = event.get("event_type")
            instrument_token = event.get("instrument_token")
            metadata = event.get("metadata", {})

            logger.info(
                f"Received subscription event: {event_type} for token {instrument_token}"
            )

            if event_type == "subscription_created":
                await self._handle_subscription_created(instrument_token, metadata)

            elif event_type in ["subscription_deleted", "subscription_removed"]:
                await self._handle_subscription_deleted(instrument_token, metadata)

            else:
                logger.warning(f"Unknown event type: {event_type}")

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse subscription event: {e}")
        except Exception as e:
            logger.error(f"Error handling subscription event: {e}", exc_info=True)

    async def _handle_subscription_created(
        self,
        instrument_token: int,
        metadata: dict,
    ):
        """Handle subscription created event"""
        tradingsymbol = metadata.get("tradingsymbol", "unknown")

        logger.info(
            f"Subscription created: {tradingsymbol} (token: {instrument_token}), "
            f"triggering immediate backfill"
        )

        # Trigger immediate backfill if available
        if self._backfill_manager:
            try:
                # Check if backfill manager has the method
                if hasattr(self._backfill_manager, 'backfill_instrument_immediate'):
                    # Run in background (don't block event loop)
                    asyncio.create_task(
                        self._backfill_manager.backfill_instrument_immediate(
                            instrument_token
                        )
                    )

                    logger.info(f"Immediate backfill scheduled for token {instrument_token}")
                else:
                    logger.warning(
                        f"Backfill manager does not support immediate backfill, "
                        f"will be backfilled in next scheduled cycle"
                    )

            except Exception as e:
                logger.error(
                    f"Failed to trigger immediate backfill for {instrument_token}: {e}"
                )
        else:
            logger.warning(
                "Backfill manager not available, skipping immediate backfill. "
                "Will be backfilled in next scheduled cycle."
            )

    async def _handle_subscription_deleted(
        self,
        instrument_token: int,
        metadata: dict,
    ):
        """Handle subscription deleted event"""
        tradingsymbol = metadata.get("tradingsymbol", "unknown")

        logger.info(
            f"Subscription deleted: {tradingsymbol} (token: {instrument_token})"
        )

        # Could implement cleanup logic here
        # For example:
        # - Stop processing this instrument in real-time consumer
        # - Mark data as stale in cache
        # - Alert monitoring system

        # For now, just log it
        logger.debug(
            f"No cleanup action configured for subscription deletion of {instrument_token}"
        )
