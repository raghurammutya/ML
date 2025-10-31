# app/services/indicator_cache.py
"""
Indicator Cache Service

Smart caching layer for computed indicators with TTL-based expiration.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import pandas as pd

import redis.asyncio as redis

logger = logging.getLogger("app.services.indicator_cache")


class IndicatorCache:
    """Smart caching for indicator values with TTL."""

    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client

        # TTL settings (in seconds)
        self.ttl_by_timeframe = {
            "1": 60,       # 1min -> 60s TTL
            "5": 300,      # 5min -> 300s TTL
            "15": 900,     # 15min -> 900s TTL
            "60": 3600,    # 1hour -> 3600s TTL
            "day": 86400,  # 1day -> 86400s TTL
        }

        self.default_ttl = 300  # 5 minutes default

    # ========== Latest Value Cache ==========

    async def get_latest(
        self,
        symbol: str,
        timeframe: str,
        indicator_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get latest cached indicator value.

        Args:
            symbol: Symbol
            timeframe: Timeframe
            indicator_id: Indicator ID

        Returns:
            Dict with value and metadata, or None
        """
        key = self._latest_key(symbol, timeframe, indicator_id)

        try:
            data = await self.redis.get(key)
            if data is None:
                return None

            return json.loads(data)

        except Exception as e:
            logger.error(f"Failed to get latest value from cache: {e}")
            return None

    async def set_latest(
        self,
        symbol: str,
        timeframe: str,
        indicator_id: str,
        value: Any,
        timestamp: Optional[datetime] = None,
        candle_time: Optional[datetime] = None
    ):
        """
        Cache latest indicator value.

        Args:
            symbol: Symbol
            timeframe: Timeframe
            indicator_id: Indicator ID
            value: Indicator value (float or dict for multi-value indicators)
            timestamp: Computation timestamp
            candle_time: Candle timestamp
        """
        if timestamp is None:
            timestamp = datetime.now()

        if candle_time is None:
            candle_time = timestamp

        key = self._latest_key(symbol, timeframe, indicator_id)
        ttl = self._get_ttl(timeframe)

        data = {
            "value": value,
            "timestamp": timestamp.isoformat(),
            "candle_time": candle_time.isoformat(),
            "indicator_id": indicator_id
        }

        try:
            await self.redis.setex(
                key,
                ttl,
                json.dumps(data, default=str)
            )

        except Exception as e:
            logger.error(f"Failed to cache latest value: {e}")

    async def invalidate_latest(
        self,
        symbol: str,
        timeframe: str,
        indicator_id: Optional[str] = None
    ):
        """
        Invalidate latest value cache.

        Args:
            symbol: Symbol
            timeframe: Timeframe
            indicator_id: Optional specific indicator (if None, invalidates all)
        """
        if indicator_id:
            key = self._latest_key(symbol, timeframe, indicator_id)
            await self.redis.delete(key)
        else:
            # Invalidate all indicators for this symbol/timeframe
            pattern = self._latest_key(symbol, timeframe, "*")
            await self._delete_pattern(pattern)

    # ========== Historical Series Cache ==========

    async def get_series(
        self,
        symbol: str,
        timeframe: str,
        indicator_id: str,
        from_ts: datetime,
        to_ts: datetime
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Get cached historical series.

        Args:
            symbol: Symbol
            timeframe: Timeframe
            indicator_id: Indicator ID
            from_ts: Start time
            to_ts: End time

        Returns:
            List of {time, value} dicts, or None
        """
        key = self._series_key(symbol, timeframe, indicator_id, from_ts, to_ts)

        try:
            data = await self.redis.get(key)
            if data is None:
                return None

            return json.loads(data)

        except Exception as e:
            logger.error(f"Failed to get series from cache: {e}")
            return None

    async def set_series(
        self,
        symbol: str,
        timeframe: str,
        indicator_id: str,
        from_ts: datetime,
        to_ts: datetime,
        series: List[Dict[str, Any]],
        ttl: Optional[int] = None
    ):
        """
        Cache historical series.

        Args:
            symbol: Symbol
            timeframe: Timeframe
            indicator_id: Indicator ID
            from_ts: Start time
            to_ts: End time
            series: List of {time, value} dicts
            ttl: Optional TTL (default: 600s = 10min)
        """
        key = self._series_key(symbol, timeframe, indicator_id, from_ts, to_ts)

        if ttl is None:
            ttl = 600  # 10 minutes for series cache

        try:
            await self.redis.setex(
                key,
                ttl,
                json.dumps(series, default=str)
            )

        except Exception as e:
            logger.error(f"Failed to cache series: {e}")

    # ========== OHLCV Cache (for reuse across indicators) ==========

    async def get_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        from_ts: datetime,
        to_ts: datetime
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Get cached OHLCV data.

        Args:
            symbol: Symbol
            timeframe: Timeframe
            from_ts: Start time
            to_ts: End time

        Returns:
            List of OHLCV dicts, or None
        """
        key = self._ohlcv_key(symbol, timeframe, from_ts, to_ts)

        try:
            data = await self.redis.get(key)
            if data is None:
                return None

            return json.loads(data)

        except Exception as e:
            logger.error(f"Failed to get OHLCV from cache: {e}")
            return None

    async def set_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        from_ts: datetime,
        to_ts: datetime,
        ohlcv: List[Dict[str, Any]]
    ):
        """
        Cache OHLCV data.

        Args:
            symbol: Symbol
            timeframe: Timeframe
            from_ts: Start time
            to_ts: End time
            ohlcv: List of OHLCV dicts
        """
        key = self._ohlcv_key(symbol, timeframe, from_ts, to_ts)
        ttl = self._get_ttl(timeframe)

        try:
            await self.redis.setex(
                key,
                ttl,
                json.dumps(ohlcv, default=str)
            )

        except Exception as e:
            logger.error(f"Failed to cache OHLCV: {e}")

    # ========== Batch Operations ==========

    async def get_latest_batch(
        self,
        symbol: str,
        timeframe: str,
        indicator_ids: List[str]
    ) -> Dict[str, Optional[Dict[str, Any]]]:
        """
        Get latest values for multiple indicators in batch.

        Args:
            symbol: Symbol
            timeframe: Timeframe
            indicator_ids: List of indicator IDs

        Returns:
            Dict mapping indicator_id -> cached value (or None)
        """
        keys = [self._latest_key(symbol, timeframe, ind_id) for ind_id in indicator_ids]

        try:
            # Use pipeline for efficient batch get
            pipe = self.redis.pipeline()
            for key in keys:
                pipe.get(key)

            results = await pipe.execute()

            # Map results back to indicator IDs
            output = {}
            for i, indicator_id in enumerate(indicator_ids):
                if results[i] is not None:
                    try:
                        output[indicator_id] = json.loads(results[i])
                    except Exception as e:
                        logger.error(f"Failed to parse cached value for {indicator_id}: {e}")
                        output[indicator_id] = None
                else:
                    output[indicator_id] = None

            return output

        except Exception as e:
            logger.error(f"Failed to get latest batch: {e}")
            return {ind_id: None for ind_id in indicator_ids}

    async def set_latest_batch(
        self,
        symbol: str,
        timeframe: str,
        values: Dict[str, Any],
        timestamp: Optional[datetime] = None
    ):
        """
        Set latest values for multiple indicators in batch.

        Args:
            symbol: Symbol
            timeframe: Timeframe
            values: Dict mapping indicator_id -> value
            timestamp: Computation timestamp
        """
        if timestamp is None:
            timestamp = datetime.now()

        ttl = self._get_ttl(timeframe)

        try:
            pipe = self.redis.pipeline()

            for indicator_id, value in values.items():
                key = self._latest_key(symbol, timeframe, indicator_id)
                data = {
                    "value": value,
                    "timestamp": timestamp.isoformat(),
                    "indicator_id": indicator_id
                }
                pipe.setex(key, ttl, json.dumps(data, default=str))

            await pipe.execute()

        except Exception as e:
            logger.error(f"Failed to set latest batch: {e}")

    # ========== Cache Invalidation ==========

    async def invalidate_symbol(self, symbol: str, timeframe: Optional[str] = None):
        """
        Invalidate all cache for symbol (and optionally timeframe).

        Args:
            symbol: Symbol to invalidate
            timeframe: Optional timeframe filter
        """
        if timeframe:
            patterns = [
                self._latest_key(symbol, timeframe, "*"),
                self._series_key_pattern(symbol, timeframe),
                self._ohlcv_key_pattern(symbol, timeframe)
            ]
        else:
            patterns = [
                f"indicator_value:{symbol}:*",
                f"indicator_series:{symbol}:*",
                f"ohlcv_cache:{symbol}:*"
            ]

        for pattern in patterns:
            await self._delete_pattern(pattern)

    async def invalidate_all(self):
        """Invalidate entire indicator cache."""
        patterns = [
            "indicator_value:*",
            "indicator_series:*",
            "ohlcv_cache:*"
        ]

        for pattern in patterns:
            await self._delete_pattern(pattern)

    # ========== Helper Methods ==========

    def _latest_key(self, symbol: str, timeframe: str, indicator_id: str) -> str:
        """Get Redis key for latest value."""
        return f"indicator_value:{symbol}:{timeframe}:{indicator_id}:latest"

    def _series_key(
        self,
        symbol: str,
        timeframe: str,
        indicator_id: str,
        from_ts: datetime,
        to_ts: datetime
    ) -> str:
        """Get Redis key for series cache."""
        from_str = from_ts.strftime("%Y%m%d%H%M")
        to_str = to_ts.strftime("%Y%m%d%H%M")
        return f"indicator_series:{symbol}:{timeframe}:{indicator_id}:{from_str}:{to_str}"

    def _series_key_pattern(self, symbol: str, timeframe: str) -> str:
        """Get Redis key pattern for series."""
        return f"indicator_series:{symbol}:{timeframe}:*"

    def _ohlcv_key(
        self,
        symbol: str,
        timeframe: str,
        from_ts: datetime,
        to_ts: datetime
    ) -> str:
        """Get Redis key for OHLCV cache."""
        from_str = from_ts.strftime("%Y%m%d%H%M")
        to_str = to_ts.strftime("%Y%m%d%H%M")
        return f"ohlcv_cache:{symbol}:{timeframe}:{from_str}:{to_str}"

    def _ohlcv_key_pattern(self, symbol: str, timeframe: str) -> str:
        """Get Redis key pattern for OHLCV."""
        return f"ohlcv_cache:{symbol}:{timeframe}:*"

    def _get_ttl(self, timeframe: str) -> int:
        """Get TTL for timeframe."""
        # Normalize timeframe
        tf = timeframe.lower().strip()
        for key in self.ttl_by_timeframe:
            if tf in [key, f"{key}min", f"{key}minute"]:
                return self.ttl_by_timeframe[key]

        return self.default_ttl

    async def _delete_pattern(self, pattern: str):
        """Delete all keys matching pattern."""
        try:
            cursor = 0
            while True:
                cursor, keys = await self.redis.scan(cursor, match=pattern, count=100)

                if keys:
                    await self.redis.delete(*keys)

                if cursor == 0:
                    break

        except Exception as e:
            logger.error(f"Failed to delete pattern {pattern}: {e}")
