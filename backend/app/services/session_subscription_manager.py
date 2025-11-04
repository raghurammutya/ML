"""
Session-Isolated Subscription Manager

Manages indicator subscriptions with session-level isolation:
- Each WebSocket connection (session) has its own subscriptions
- Shared computation: Compute indicators once
- Filtered delivery: Send indicators only to sessions that subscribed
"""

import asyncio
import logging
from typing import Dict, Set, Optional, Any
from datetime import datetime
import redis.asyncio as redis

logger = logging.getLogger(__name__)


class SessionSubscriptionManager:
    """
    Manages indicator subscriptions with session-level isolation.

    Key Principles:
    1. Each WebSocket connection = unique session
    2. Subscriptions tracked per connection
    3. Compute indicators once (shared)
    4. Deliver indicators only to subscribers (filtered)
    """

    def __init__(self, redis_client: redis.Redis):
        """
        Initialize subscription manager.

        Args:
            redis_client: Redis client for persistence
        """
        self.redis = redis_client

        # WebSocket Connection ID → Subscription metadata
        self.subscriptions: Dict[str, Dict[str, Any]] = {}

        # Indicator Cache Key → Set of WebSocket IDs subscribed to it
        # Example: "NIFTY50:5min:RSI_14_100" → {"ws_abc123", "ws_def456"}
        self.indicator_subscribers: Dict[str, Set[str]] = {}

    async def subscribe(
        self,
        ws_conn_id: str,
        user_id: str,
        session_id: str,
        symbol: str,
        timeframe: str,
        indicators: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Subscribe a specific session to indicators.

        Args:
            ws_conn_id: WebSocket connection ID (unique per tab/session)
            user_id: User email/ID
            session_id: Session identifier (from JWT or cookie)
            symbol: Symbol (e.g., "NIFTY50")
            timeframe: Timeframe (e.g., "5min")
            indicators: Dict of {indicator_id: {name, params}}
                Example: {
                    "RSI_14_100": {"name": "RSI", "params": {"length": 14, "scalar": 100}},
                    "MACD_12_26_9": {"name": "MACD", "params": {"fast": 12, "slow": 26, "signal": 9}}
                }

        Returns:
            Subscription confirmation with indicator list
        """
        logger.info(
            f"Subscribing connection {ws_conn_id} (user={user_id}, session={session_id}) "
            f"to {len(indicators)} indicators for {symbol}:{timeframe}"
        )

        # Store subscription metadata
        self.subscriptions[ws_conn_id] = {
            "user_id": user_id,
            "session_id": session_id,
            "symbol": symbol,
            "timeframe": timeframe,
            "indicators": indicators,
            "subscribed_at": datetime.now().isoformat(),
            "last_heartbeat": datetime.now().isoformat()
        }

        # Track which WebSocket connections are subscribed to each indicator
        for indicator_id in indicators.keys():
            cache_key = f"{symbol}:{timeframe}:{indicator_id}"

            if cache_key not in self.indicator_subscribers:
                self.indicator_subscribers[cache_key] = set()

            self.indicator_subscribers[cache_key].add(ws_conn_id)

            # Persist to Redis (for fault tolerance)
            await self.redis.sadd(f"indicator_subscribers:{cache_key}", ws_conn_id)

            logger.debug(
                f"Indicator {cache_key} now has "
                f"{len(self.indicator_subscribers[cache_key])} subscribers"
            )

        return {
            "status": "subscribed",
            "ws_conn_id": ws_conn_id,
            "symbol": symbol,
            "timeframe": timeframe,
            "indicators": list(indicators.keys()),
            "subscriber_count": len(self.subscriptions)
        }

    async def unsubscribe(self, ws_conn_id: str) -> Dict[str, Any]:
        """
        Unsubscribe a session from all its indicators.

        Called when:
        - User explicitly unsubscribes
        - WebSocket connection closes
        - Tab is closed

        Args:
            ws_conn_id: WebSocket connection ID

        Returns:
            Unsubscription confirmation
        """
        if ws_conn_id not in self.subscriptions:
            logger.warning(f"Attempted to unsubscribe non-existent connection: {ws_conn_id}")
            return {"status": "not_found"}

        subscription = self.subscriptions[ws_conn_id]
        symbol = subscription["symbol"]
        timeframe = subscription["timeframe"]
        indicators = subscription["indicators"]

        logger.info(
            f"Unsubscribing connection {ws_conn_id} from "
            f"{len(indicators)} indicators for {symbol}:{timeframe}"
        )

        # Remove from indicator subscribers
        for indicator_id in indicators.keys():
            cache_key = f"{symbol}:{timeframe}:{indicator_id}"

            if cache_key in self.indicator_subscribers:
                self.indicator_subscribers[cache_key].discard(ws_conn_id)

                # Remove from Redis
                await self.redis.srem(f"indicator_subscribers:{cache_key}", ws_conn_id)

                subscriber_count = len(self.indicator_subscribers[cache_key])
                logger.debug(f"Indicator {cache_key} now has {subscriber_count} subscribers")

                # If no more subscribers, cleanup
                if subscriber_count == 0:
                    logger.info(f"No more subscribers for {cache_key}, cleaning up")
                    del self.indicator_subscribers[cache_key]
                    # Could trigger computation cleanup here

        # Remove subscription
        del self.subscriptions[ws_conn_id]

        return {
            "status": "unsubscribed",
            "ws_conn_id": ws_conn_id,
            "indicators_removed": list(indicators.keys())
        }

    async def update_heartbeat(self, ws_conn_id: str):
        """
        Update last heartbeat time for a connection.

        Used to detect stale connections.
        """
        if ws_conn_id in self.subscriptions:
            self.subscriptions[ws_conn_id]["last_heartbeat"] = datetime.now().isoformat()

    def get_session_subscription(self, ws_conn_id: str) -> Optional[Dict[str, Any]]:
        """
        Get subscription details for a specific session.

        Args:
            ws_conn_id: WebSocket connection ID

        Returns:
            Subscription metadata or None
        """
        return self.subscriptions.get(ws_conn_id)

    def get_session_indicators(self, ws_conn_id: str) -> Optional[Dict[str, Dict]]:
        """
        Get indicators subscribed by a specific session.

        Used for:
        - REST API responses
        - Initial data load
        - Debugging

        Args:
            ws_conn_id: WebSocket connection ID

        Returns:
            Dict of indicators or None
        """
        subscription = self.subscriptions.get(ws_conn_id)
        if not subscription:
            return None

        return subscription["indicators"]

    def get_indicator_subscribers(
        self,
        symbol: str,
        timeframe: str,
        indicator_id: str
    ) -> Set[str]:
        """
        Get all WebSocket connections subscribed to a specific indicator.

        Args:
            symbol: Symbol (e.g., "NIFTY50")
            timeframe: Timeframe (e.g., "5min")
            indicator_id: Indicator ID (e.g., "RSI_14_100")

        Returns:
            Set of WebSocket connection IDs
        """
        cache_key = f"{symbol}:{timeframe}:{indicator_id}"
        return self.indicator_subscribers.get(cache_key, set())

    def get_indicator_subscriber_count(
        self,
        symbol: str,
        timeframe: str,
        indicator_id: str
    ) -> int:
        """
        Get number of sessions subscribed to an indicator.

        Used for:
        - Deciding whether to compute indicator
        - Monitoring/metrics

        Args:
            symbol: Symbol
            timeframe: Timeframe
            indicator_id: Indicator ID

        Returns:
            Number of subscribers
        """
        subscribers = self.get_indicator_subscribers(symbol, timeframe, indicator_id)
        return len(subscribers)

    def has_subscribers(self, symbol: str, timeframe: str, indicator_id: str) -> bool:
        """
        Check if an indicator has any subscribers.

        Args:
            symbol: Symbol
            timeframe: Timeframe
            indicator_id: Indicator ID

        Returns:
            True if indicator has at least one subscriber
        """
        return self.get_indicator_subscriber_count(symbol, timeframe, indicator_id) > 0

    def get_all_active_subscriptions(self) -> Dict[str, Dict]:
        """
        Get all active subscriptions.

        Returns:
            Dict of all subscriptions
        """
        return self.subscriptions.copy()

    def get_subscription_stats(self) -> Dict[str, Any]:
        """
        Get subscription statistics.

        Returns:
            Stats dict with counts and metrics
        """
        total_connections = len(self.subscriptions)
        total_indicators = len(self.indicator_subscribers)

        # Count unique users
        unique_users = set(sub["user_id"] for sub in self.subscriptions.values())

        # Count indicators per symbol
        indicators_by_symbol = {}
        for cache_key in self.indicator_subscribers.keys():
            symbol = cache_key.split(":")[0]
            indicators_by_symbol[symbol] = indicators_by_symbol.get(symbol, 0) + 1

        return {
            "total_connections": total_connections,
            "total_unique_indicators": total_indicators,
            "total_unique_users": len(unique_users),
            "indicators_by_symbol": indicators_by_symbol,
            "timestamp": datetime.now().isoformat()
        }

    async def cleanup_stale_connections(self, max_age_seconds: int = 300):
        """
        Clean up connections that haven't sent a heartbeat recently.

        Args:
            max_age_seconds: Maximum age in seconds before considering connection stale
        """
        now = datetime.now()
        stale_connections = []

        for ws_conn_id, subscription in self.subscriptions.items():
            last_heartbeat = datetime.fromisoformat(subscription["last_heartbeat"])
            age = (now - last_heartbeat).total_seconds()

            if age > max_age_seconds:
                stale_connections.append(ws_conn_id)

        for ws_conn_id in stale_connections:
            logger.warning(f"Cleaning up stale connection: {ws_conn_id}")
            await self.unsubscribe(ws_conn_id)

        return len(stale_connections)


# Global instance (initialized in main.py)
_subscription_manager: Optional[SessionSubscriptionManager] = None


def init_subscription_manager(redis_client: redis.Redis):
    """Initialize global subscription manager."""
    global _subscription_manager
    _subscription_manager = SessionSubscriptionManager(redis_client)
    logger.info("Session subscription manager initialized")


def get_subscription_manager() -> SessionSubscriptionManager:
    """Get global subscription manager instance."""
    if _subscription_manager is None:
        raise RuntimeError("Subscription manager not initialized")
    return _subscription_manager
