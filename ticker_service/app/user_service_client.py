from __future__ import annotations

from typing import Any, Dict, List

import httpx
from loguru import logger

from .config import get_settings


def fetch_remote_trading_accounts() -> List[Dict[str, Any]]:
    """
    Fetch decrypted trading-account credentials from the user service.
    Returns an empty list if integration is disabled or misconfigured.
    """
    settings = get_settings()
    if not settings.use_user_service_accounts or not settings.user_service_base_url:
        return []

    base_url = settings.user_service_base_url.rstrip("/")
    url = f"{base_url}/api/v1/trading-accounts/internal"
    params = {"requesting_service": settings.app_name, "status_filter": "ACTIVE"}
    headers: Dict[str, str] = {}
    if settings.user_service_service_token:
        headers["X-Service-Token"] = settings.user_service_service_token

    logger.info("Fetching Kite account credentials from user service at %s", url)
    try:
        response = httpx.get(url, params=params, headers=headers, timeout=15.0)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise ValueError("Unexpected response format from user service")
        logger.info("Received %d trading accounts from user service", len(payload))
        return payload
    except httpx.HTTPError as exc:
        logger.error("Failed to fetch trading accounts from user service: %s", exc)
    except Exception as exc:
        logger.exception("Unexpected error while fetching accounts from user service: %s", exc)
    return []
