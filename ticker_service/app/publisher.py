from __future__ import annotations

import json
import time
from typing import Dict, Any

from loguru import logger

from .config import get_settings
from .redis_client import redis_publisher
from .schema import OptionSnapshot

settings = get_settings()


async def publish_option_snapshot(snapshot: OptionSnapshot) -> None:
    channel = f"{settings.publish_channel_prefix}:options"
    message = json.dumps(snapshot.to_payload())
    await redis_publisher.publish(channel, message)
    is_mock = snapshot.is_mock
    logger.debug("Published option snapshot to %s (is_mock=%s)", channel, is_mock)


async def publish_underlying_bar(bar: Dict[str, Any]) -> None:
    channel = f"{settings.publish_channel_prefix}:underlying"
    await redis_publisher.publish(channel, json.dumps(bar))
    is_mock = bar.get("is_mock", False)
    logger.debug("Published underlying bar to %s (is_mock=%s)", channel, is_mock)


async def publish_subscription_event(
    event_type: str,
    instrument_token: int,
    metadata: Dict[str, Any]
) -> None:
    """
    Publish subscription lifecycle events to Redis for backend consumption.

    Args:
        event_type: Type of event ('subscription_created', 'subscription_removed')
        instrument_token: The instrument token
        metadata: Additional metadata about the subscription
    """
    channel = f"{settings.publish_channel_prefix}:events"
    event = {
        "event_type": event_type,
        "instrument_token": instrument_token,
        "metadata": metadata,
        "timestamp": int(time.time())
    }
    message = json.dumps(event)
    await redis_publisher.publish(channel, message)
    logger.info(
        "Published subscription event | type=%s token=%s channel=%s",
        event_type,
        instrument_token,
        channel
    )
