# app/services/indicator_subscription_manager.py
"""
Indicator Subscription Manager

Manages indicator subscriptions using Redis.
Tracks which indicators are actively subscribed and by how many clients.
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional, Set, Any
import json

import redis.asyncio as redis

logger = logging.getLogger("app.services.indicator_subscription_manager")


class IndicatorSubscriptionManager:
    """Manage indicator subscriptions in Redis."""

    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client

    # ========== Subscription Management ==========

    async def subscribe(
        self,
        client_id: str,
        symbol: str,
        timeframe: str,
        indicator_ids: List[str]
    ) -> Dict[str, Any]:
        """
        Subscribe client to indicators.

        Args:
            client_id: Unique client identifier
            symbol: Symbol (e.g., "NIFTY50")
            timeframe: Timeframe (e.g., "5min")
            indicator_ids: List of indicator IDs (e.g., ["RSI_14", "SMA_20"])

        Returns:
            Dict with subscription details
        """
        key = self._subscription_key(symbol, timeframe)
        results = []

        for indicator_id in indicator_ids:
            # Add to active subscriptions set
            await self.redis.sadd(key, indicator_id)

            # Track subscriber count
            meta_key = self._meta_key(symbol, timeframe, indicator_id)
            count = await self.redis.hincrby(meta_key, "subscriber_count", 1)

            # Store subscription metadata
            if count == 1:
                # First subscriber - initialize metadata
                await self.redis.hset(meta_key, mapping={
                    "created_at": datetime.now().isoformat(),
                    "last_computed": "",
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "indicator_id": indicator_id
                })

            # Track client subscription
            client_key = self._client_key(client_id)
            await self.redis.sadd(
                client_key,
                self._encode_subscription(symbol, timeframe, indicator_id)
            )

            results.append({
                "indicator_id": indicator_id,
                "symbol": symbol,
                "timeframe": timeframe,
                "subscriber_count": count,
                "status": "subscribed"
            })

            logger.info(
                f"Client {client_id} subscribed to {indicator_id} "
                f"({symbol} {timeframe}), subscribers: {count}"
            )

        return {
            "status": "success",
            "client_id": client_id,
            "subscriptions": results
        }

    async def unsubscribe(
        self,
        client_id: str,
        symbol: str,
        timeframe: str,
        indicator_ids: List[str]
    ) -> Dict[str, Any]:
        """
        Unsubscribe client from indicators.

        Args:
            client_id: Client identifier
            symbol: Symbol
            timeframe: Timeframe
            indicator_ids: Indicator IDs to unsubscribe

        Returns:
            Dict with unsubscription details
        """
        key = self._subscription_key(symbol, timeframe)
        results = []

        for indicator_id in indicator_ids:
            # Decrement subscriber count
            meta_key = self._meta_key(symbol, timeframe, indicator_id)
            count = await self.redis.hincrby(meta_key, "subscriber_count", -1)

            # If no subscribers left, remove from active set
            if count <= 0:
                await self.redis.srem(key, indicator_id)
                await self.redis.delete(meta_key)
                logger.info(f"Removed {indicator_id} (no subscribers)")

            # Remove from client subscriptions
            client_key = self._client_key(client_id)
            await self.redis.srem(
                client_key,
                self._encode_subscription(symbol, timeframe, indicator_id)
            )

            results.append({
                "indicator_id": indicator_id,
                "symbol": symbol,
                "timeframe": timeframe,
                "subscriber_count": max(0, count),
                "status": "unsubscribed"
            })

            logger.info(
                f"Client {client_id} unsubscribed from {indicator_id} "
                f"({symbol} {timeframe}), remaining: {max(0, count)}"
            )

        return {
            "status": "success",
            "client_id": client_id,
            "unsubscribed": results
        }

    async def unsubscribe_all(self, client_id: str) -> Dict[str, Any]:
        """
        Unsubscribe client from all indicators.

        Args:
            client_id: Client identifier

        Returns:
            Dict with unsubscription details
        """
        client_key = self._client_key(client_id)

        # Get all subscriptions for this client
        subscriptions = await self.redis.smembers(client_key)

        unsubscribed = []
        for sub_encoded in subscriptions:
            try:
                symbol, timeframe, indicator_id = self._decode_subscription(sub_encoded)

                # Unsubscribe from each
                result = await self.unsubscribe(
                    client_id, symbol, timeframe, [indicator_id]
                )

                unsubscribed.extend(result["unsubscribed"])

            except Exception as e:
                logger.error(f"Failed to unsubscribe {sub_encoded}: {e}")

        # Delete client tracking key
        await self.redis.delete(client_key)

        return {
            "status": "success",
            "client_id": client_id,
            "unsubscribed_count": len(unsubscribed),
            "unsubscribed": unsubscribed
        }

    # ========== Query Methods ==========

    async def get_active_indicators(
        self,
        symbol: str,
        timeframe: str
    ) -> List[str]:
        """
        Get all actively subscribed indicators for symbol/timeframe.

        Args:
            symbol: Symbol
            timeframe: Timeframe

        Returns:
            List of indicator IDs
        """
        key = self._subscription_key(symbol, timeframe)
        indicators = await self.redis.smembers(key)
        return list(indicators)

    async def get_subscriber_count(
        self,
        symbol: str,
        timeframe: str,
        indicator_id: str
    ) -> int:
        """
        Get subscriber count for specific indicator.

        Args:
            symbol: Symbol
            timeframe: Timeframe
            indicator_id: Indicator ID

        Returns:
            Subscriber count
        """
        meta_key = self._meta_key(symbol, timeframe, indicator_id)
        count = await self.redis.hget(meta_key, "subscriber_count")

        if count is None:
            return 0

        try:
            return int(count)
        except (ValueError, TypeError):
            return 0

    async def get_client_subscriptions(
        self,
        client_id: str
    ) -> List[Dict[str, str]]:
        """
        Get all subscriptions for a client.

        Args:
            client_id: Client identifier

        Returns:
            List of subscription dicts
        """
        client_key = self._client_key(client_id)
        subscriptions = await self.redis.smembers(client_key)

        results = []
        for sub_encoded in subscriptions:
            try:
                symbol, timeframe, indicator_id = self._decode_subscription(sub_encoded)
                results.append({
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "indicator_id": indicator_id
                })
            except Exception as e:
                logger.error(f"Failed to decode subscription {sub_encoded}: {e}")

        return results

    async def is_subscribed(
        self,
        symbol: str,
        timeframe: str,
        indicator_id: str
    ) -> bool:
        """
        Check if indicator is actively subscribed.

        Args:
            symbol: Symbol
            timeframe: Timeframe
            indicator_id: Indicator ID

        Returns:
            True if subscribed, False otherwise
        """
        key = self._subscription_key(symbol, timeframe)
        return await self.redis.sismember(key, indicator_id)

    async def update_last_computed(
        self,
        symbol: str,
        timeframe: str,
        indicator_id: str,
        timestamp: Optional[datetime] = None
    ):
        """
        Update last computed timestamp for indicator.

        Args:
            symbol: Symbol
            timeframe: Timeframe
            indicator_id: Indicator ID
            timestamp: Computation timestamp (default: now)
        """
        if timestamp is None:
            timestamp = datetime.now()

        meta_key = self._meta_key(symbol, timeframe, indicator_id)
        await self.redis.hset(meta_key, "last_computed", timestamp.isoformat())

    async def get_metadata(
        self,
        symbol: str,
        timeframe: str,
        indicator_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get metadata for indicator subscription.

        Args:
            symbol: Symbol
            timeframe: Timeframe
            indicator_id: Indicator ID

        Returns:
            Metadata dict or None
        """
        meta_key = self._meta_key(symbol, timeframe, indicator_id)
        data = await self.redis.hgetall(meta_key)

        if not data:
            return None

        return data

    # ========== Cleanup Methods ==========

    async def cleanup_inactive(self, max_idle_seconds: int = 3600):
        """
        Cleanup subscriptions with no subscribers.

        Args:
            max_idle_seconds: Maximum idle time before cleanup
        """
        # This would require scanning all keys
        # For now, cleanup happens automatically on unsubscribe
        pass

    # ========== Helper Methods ==========

    def _subscription_key(self, symbol: str, timeframe: str) -> str:
        """Get Redis key for active subscriptions."""
        return f"indicator_subs:{symbol}:{timeframe}"

    def _meta_key(self, symbol: str, timeframe: str, indicator_id: str) -> str:
        """Get Redis key for subscription metadata."""
        return f"indicator_meta:{symbol}:{timeframe}:{indicator_id}"

    def _client_key(self, client_id: str) -> str:
        """Get Redis key for client subscriptions."""
        return f"indicator_client:{client_id}"

    def _encode_subscription(
        self,
        symbol: str,
        timeframe: str,
        indicator_id: str
    ) -> str:
        """Encode subscription as string."""
        return f"{symbol}|{timeframe}|{indicator_id}"

    def _decode_subscription(self, encoded: str) -> tuple:
        """Decode subscription string."""
        parts = encoded.split("|")
        if len(parts) != 3:
            raise ValueError(f"Invalid subscription encoding: {encoded}")
        return parts[0], parts[1], parts[2]
