from __future__ import annotations

import json
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
