"""
Subscription Tier Detection Service

Detects KiteConnect subscription tier (Personal vs Connect) by attempting
market data API calls and handling permission errors.
"""

import logging
from datetime import datetime, timedelta
from typing import Tuple, Optional

from kiteconnect import KiteConnect
from kiteconnect.exceptions import PermissionException, TokenException

logger = logging.getLogger(__name__)


class SubscriptionTierDetector:
    """
    Detects KiteConnect subscription tier via error-based detection.

    KiteConnect does not provide a direct API to query subscription tier.
    We detect it by attempting to call market data APIs and catching permission errors.
    """

    # Cache duration before re-detecting tier
    TIER_CACHE_HOURS = 24

    @staticmethod
    def should_refresh_tier(last_checked: Optional[datetime]) -> bool:
        """
        Check if subscription tier detection should be refreshed.

        Args:
            last_checked: Last time tier was detected

        Returns:
            True if tier should be re-detected
        """
        if not last_checked:
            return True  # Never checked

        hours_since_check = (datetime.utcnow() - last_checked).total_seconds() / 3600
        return hours_since_check >= SubscriptionTierDetector.TIER_CACHE_HOURS

    @staticmethod
    async def detect_tier(
        api_key: str,
        access_token: str
    ) -> Tuple[str, bool, str]:
        """
        Detect subscription tier by attempting quote API call.

        Args:
            api_key: KiteConnect API key
            access_token: Active access token

        Returns:
            Tuple of (tier, market_data_available, detection_method)
            tier: 'connect', 'personal', or 'unknown'
            market_data_available: True if can access market data
            detection_method: How tier was detected
        """
        logger.info(f"Detecting subscription tier for API key: {api_key[:10]}...")

        try:
            # Create KiteConnect client
            kite = KiteConnect(api_key=api_key)
            kite.set_access_token(access_token)

            # Attempt to fetch quote (requires paid subscription)
            # Using NIFTY 50 as it's always available
            logger.debug("Attempting quote API call to detect tier...")
            quote = kite.quote("NSE:NIFTY 50")

            if quote and isinstance(quote, dict):
                # Success! User has market data access
                logger.info(f"Quote API successful - tier: CONNECT (has market data)")
                return ("connect", True, "quote_api_test")

        except PermissionException as e:
            # Permission denied - user has Personal API (free tier)
            error_msg = str(e)
            logger.info(
                f"Permission denied on quote API - tier: PERSONAL (no market data). "
                f"Error: {error_msg}"
            )

            # Verify it's the expected permission error
            if "Insufficient permission" in error_msg or "not free" in error_msg.lower():
                return ("personal", False, "quote_api_test")

            # Unknown permission error
            logger.warning(f"Unexpected permission error: {error_msg}")
            return ("unknown", False, "quote_api_error")

        except TokenException as e:
            # Token invalid or expired
            logger.error(f"Token error during tier detection: {str(e)}")
            return ("unknown", False, "token_error")

        except Exception as e:
            # Other error (network, server, etc.)
            logger.error(f"Unexpected error during tier detection: {str(e)}", exc_info=True)
            return ("unknown", False, "detection_error")

        # Should not reach here
        logger.warning("Quote API returned unexpected response")
        return ("unknown", False, "unexpected_response")

    @staticmethod
    def tier_to_string_description(tier: str) -> str:
        """
        Get human-readable description of subscription tier.

        Args:
            tier: Tier code ('connect', 'personal', 'unknown')

        Returns:
            Human-readable description
        """
        descriptions = {
            "connect": "Kite Connect (Rs. 500/month) - Trading + Market Data",
            "personal": "Personal API (Free) - Trading Only",
            "startup": "Startup Program (Free) - Full Features",
            "unknown": "Unknown - Not yet detected or error"
        }
        return descriptions.get(tier, "Unknown tier")

    @staticmethod
    def get_tier_capabilities(tier: str) -> dict:
        """
        Get capabilities for a given subscription tier.

        Args:
            tier: Tier code

        Returns:
            Dictionary of capabilities
        """
        if tier == "connect" or tier == "startup":
            return {
                "order_placement": True,
                "position_tracking": True,
                "holdings": True,
                "funds": True,
                "market_data": True,
                "historical_data": True,
                "websocket_ticks": True,
                "market_depth": True,
            }
        elif tier == "personal":
            return {
                "order_placement": True,
                "position_tracking": True,
                "holdings": True,
                "funds": True,
                "market_data": False,
                "historical_data": False,
                "websocket_ticks": False,
                "market_depth": False,
            }
        else:  # unknown
            return {
                "order_placement": False,
                "position_tracking": False,
                "holdings": False,
                "funds": False,
                "market_data": False,
                "historical_data": False,
                "websocket_ticks": False,
                "market_depth": False,
            }
