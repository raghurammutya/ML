from __future__ import annotations

import json
from typing import Dict, Any

from loguru import logger

from .config import get_settings
from .redis_client import redis_publisher
from .schema import OptionSnapshot

settings = get_settings()


async def publish_option_snapshot(snapshot: OptionSnapshot, is_mock: bool = False) -> None:
    channel = f"{settings.publish_channel_prefix}:options"
    payload = snapshot.to_payload()
    payload["is_mock"] = is_mock
    message = json.dumps(payload)
    await redis_publisher.publish(channel, message)
    logger.debug("Published option snapshot to %s (is_mock=%s)", channel, is_mock)


async def publish_underlying_bar(bar: Dict[str, Any], is_mock: bool = False) -> None:
    channel = f"{settings.publish_channel_prefix}:underlying"
    bar["is_mock"] = is_mock
    await redis_publisher.publish(channel, json.dumps(bar))
    logger.debug("Published underlying bar to %s (is_mock=%s)", channel, is_mock)
