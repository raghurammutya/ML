# Multi-Timeframe Data Sharing Architecture

## Problem Statement

For a single symbol (e.g., NIFTY50), users may request data across multiple timeframes:
- **OHLCV**: 1min, 5min, 15min, 30min, 1h, 4h, 1d
- **Greeks** (IV, Delta, Gamma, Theta, Vega): Per option contract
- **OI (Open Interest)**: Real-time and historical
- **Technical Indicators**: RSI, MACD, etc. per timeframe

**Challenges**:
1. Avoid redundant computation for the same symbol across timeframes
2. Efficiently share base data (ticks, 1min bars) to derive higher timeframes
3. Cache strategy for multi-timeframe access
4. Handle real-time updates propagating across timeframes

---

## Architecture Overview

### 1. Data Hierarchy and Resampling Strategy

```
Raw Ticks (Real-time)
    ↓
1-minute OHLCV (Base timeframe)
    ↓ Resample
5-minute OHLCV ← 15-minute OHLCV ← 30-minute OHLCV ← 1-hour OHLCV ← 4-hour OHLCV ← Daily OHLCV
    ↓                ↓                  ↓                   ↓                ↓              ↓
Indicators        Indicators         Indicators         Indicators       Indicators    Indicators
(RSI, MACD)       (RSI, MACD)        (RSI, MACD)        (RSI, MACD)      (RSI, MACD)   (RSI, MACD)
```

**Key Principle**:
- Store **1-minute bars** as the atomic unit in TimescaleDB
- **Derive** all higher timeframes from 1-minute bars using continuous aggregates or on-demand resampling
- Cache computed indicators per timeframe in Redis with TTL

---

## 2. Redis Cache Structure

### 2.1 OHLCV Cache

```python
# Key pattern for OHLCV
ohlcv_key = f"ohlcv:{symbol}:{timeframe}:latest"

# Example:
# ohlcv:NIFTY50:1min:latest
# ohlcv:NIFTY50:5min:latest
# ohlcv:NIFTY50:15min:latest

# Value structure:
{
    "ts": 1730369100,       # Unix timestamp (bar start time)
    "open": 26050.25,
    "high": 26075.50,
    "low": 26040.00,
    "close": 26062.75,
    "volume": 15420,
    "timeframe": "5min",
    "is_complete": true     # True if bar is closed, False if still building
}
```

**TTL Strategy**:
```python
def get_ohlcv_ttl(timeframe: str) -> int:
    """Get TTL for OHLCV data based on timeframe"""
    ttl_map = {
        "1min": 120,      # 2 minutes (slightly longer than bar interval)
        "5min": 600,      # 10 minutes
        "15min": 1800,    # 30 minutes
        "30min": 3600,    # 1 hour
        "1h": 7200,       # 2 hours
        "4h": 28800,      # 8 hours
        "1d": 172800      # 2 days
    }
    return ttl_map.get(timeframe, 300)
```

### 2.2 Greeks Cache (Per Option Contract)

```python
# Key pattern for Greeks
greeks_key = f"greeks:{symbol}:{strike}:{option_type}:latest"

# Example:
# greeks:NIFTY50:26000:CE:latest
# greeks:NIFTY50:26000:PE:latest

# Value structure:
{
    "ts": 1730369100,
    "iv": 0.1523,           # Implied Volatility
    "delta": 0.5234,
    "gamma": 0.000134,
    "theta": -12.45,
    "vega": 8.23,
    "rho": 2.15,
    "underlying_price": 26062.75
}

# TTL: 60 seconds (Greeks change frequently with underlying price)
```

### 2.3 OI (Open Interest) Cache

```python
# Key pattern for OI
oi_key = f"oi:{symbol}:{strike}:{option_type}:latest"

# Example:
# oi:NIFTY50:26000:CE:latest

# Value structure:
{
    "ts": 1730369100,
    "oi": 1234567,
    "oi_change": 5432,      # Change since last update
    "volume": 98765
}

# TTL: 300 seconds (OI updates less frequently than price)
```

### 2.4 Indicator Cache (Per Timeframe)

```python
# Key pattern for indicators
indicator_key = f"indicator:{symbol}:{timeframe}:{indicator_id}:latest"

# Example:
# indicator:NIFTY50:5min:RSI_14:latest
# indicator:NIFTY50:15min:MACD_12_26_9:latest

# Value structure:
{
    "ts": 1730369100,
    "value": 67.34,         # For single-value indicators like RSI
    # OR for multi-value indicators like MACD:
    "values": {
        "MACD": 12.45,
        "MACDs": 10.23,
        "MACDh": 2.22
    },
    "timeframe": "5min",
    "computed_at": 1730369105
}

# TTL: Same as OHLCV for that timeframe
```

---

## 3. Data Computation Pipeline

### 3.1 Real-time Tick Processing

```python
# app/services/multi_timeframe_processor.py

from typing import Dict, List
import redis.asyncio as redis
import json
from datetime import datetime, timedelta

class MultiTimeframeProcessor:
    """
    Processes incoming ticks and updates OHLCV across multiple timeframes.
    """

    TIMEFRAMES = ["1min", "5min", "15min", "30min", "1h", "4h", "1d"]

    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client

    async def process_tick(self, symbol: str, tick_data: Dict):
        """
        Process incoming tick and update OHLCV for all timeframes.
        """
        price = tick_data['price']
        volume = tick_data.get('volume', 0)
        ts = tick_data['ts']

        # Update 1-minute bar (base timeframe)
        await self._update_ohlcv_bar(
            symbol=symbol,
            timeframe="1min",
            price=price,
            volume=volume,
            ts=ts
        )

        # Check if any higher timeframe bars need updating
        await self._check_and_resample(symbol, ts)

    async def _update_ohlcv_bar(
        self,
        symbol: str,
        timeframe: str,
        price: float,
        volume: int,
        ts: int
    ):
        """
        Update OHLCV bar for a specific timeframe.
        """
        bar_key = f"ohlcv:{symbol}:{timeframe}:current"

        # Get current bar
        bar_data = await self.redis.get(bar_key)

        bar_start = self._get_bar_start_time(ts, timeframe)

        if bar_data:
            bar = json.loads(bar_data)

            # Check if this tick belongs to current bar
            if bar['bar_start'] == bar_start:
                # Update existing bar
                bar['high'] = max(bar['high'], price)
                bar['low'] = min(bar['low'], price)
                bar['close'] = price
                bar['volume'] += volume
                bar['last_update'] = ts
            else:
                # Close previous bar and start new one
                await self._close_bar(symbol, timeframe, bar)

                # Start new bar
                bar = self._create_new_bar(bar_start, price, volume, ts)
        else:
            # First bar
            bar = self._create_new_bar(bar_start, price, volume, ts)

        # Save updated bar
        await self.redis.set(bar_key, json.dumps(bar))

        # Also update "latest" key for quick access
        latest_key = f"ohlcv:{symbol}:{timeframe}:latest"
        await self.redis.set(
            latest_key,
            json.dumps({
                "ts": bar_start,
                "open": bar['open'],
                "high": bar['high'],
                "low": bar['low'],
                "close": bar['close'],
                "volume": bar['volume'],
                "timeframe": timeframe,
                "is_complete": False
            }),
            ex=self._get_ttl(timeframe)
        )

    def _get_bar_start_time(self, ts: int, timeframe: str) -> int:
        """
        Get the start timestamp of the bar that contains ts.
        """
        dt = datetime.fromtimestamp(ts)

        if timeframe == "1min":
            bar_start = dt.replace(second=0, microsecond=0)
        elif timeframe == "5min":
            minute = (dt.minute // 5) * 5
            bar_start = dt.replace(minute=minute, second=0, microsecond=0)
        elif timeframe == "15min":
            minute = (dt.minute // 15) * 15
            bar_start = dt.replace(minute=minute, second=0, microsecond=0)
        elif timeframe == "30min":
            minute = (dt.minute // 30) * 30
            bar_start = dt.replace(minute=minute, second=0, microsecond=0)
        elif timeframe == "1h":
            bar_start = dt.replace(minute=0, second=0, microsecond=0)
        elif timeframe == "4h":
            hour = (dt.hour // 4) * 4
            bar_start = dt.replace(hour=hour, minute=0, second=0, microsecond=0)
        elif timeframe == "1d":
            bar_start = dt.replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            bar_start = dt

        return int(bar_start.timestamp())

    def _create_new_bar(self, bar_start: int, price: float, volume: int, ts: int) -> Dict:
        """Create a new OHLCV bar"""
        return {
            "bar_start": bar_start,
            "open": price,
            "high": price,
            "low": price,
            "close": price,
            "volume": volume,
            "last_update": ts
        }

    async def _close_bar(self, symbol: str, timeframe: str, bar: Dict):
        """
        Close a completed bar and persist to database.
        Also trigger indicator computation.
        """
        # Update "latest" key with complete bar
        latest_key = f"ohlcv:{symbol}:{timeframe}:latest"
        await self.redis.set(
            latest_key,
            json.dumps({
                "ts": bar['bar_start'],
                "open": bar['open'],
                "high": bar['high'],
                "low": bar['low'],
                "close": bar['close'],
                "volume": bar['volume'],
                "timeframe": timeframe,
                "is_complete": True
            }),
            ex=self._get_ttl(timeframe)
        )

        # Persist to TimescaleDB (for historical data)
        # This would be done via background task or queue
        await self._persist_to_db(symbol, timeframe, bar)

        # Trigger indicator recalculation
        await self._trigger_indicator_update(symbol, timeframe)

    async def _check_and_resample(self, symbol: str, ts: int):
        """
        Check if higher timeframe bars need to be resampled from 1-minute bars.
        """
        for timeframe in ["5min", "15min", "30min", "1h", "4h", "1d"]:
            bar_start = self._get_bar_start_time(ts, timeframe)

            # Check if this is a new bar boundary
            current_bar_key = f"ohlcv:{symbol}:{timeframe}:current"
            current_bar_data = await self.redis.get(current_bar_key)

            if current_bar_data:
                current_bar = json.loads(current_bar_data)
                if current_bar['bar_start'] != bar_start:
                    # New bar - resample from 1-minute data
                    await self._resample_from_base(symbol, timeframe, bar_start)

    async def _resample_from_base(self, symbol: str, timeframe: str, bar_start: int):
        """
        Resample higher timeframe bar from 1-minute bars.
        """
        # Determine how many 1-minute bars to aggregate
        interval_minutes = self._get_interval_minutes(timeframe)

        # Fetch 1-minute bars from Redis or DB
        minute_bars = await self._fetch_minute_bars(
            symbol,
            start_ts=bar_start,
            count=interval_minutes
        )

        if not minute_bars:
            return

        # Aggregate into higher timeframe bar
        aggregated = {
            "bar_start": bar_start,
            "open": minute_bars[0]['open'],
            "high": max(bar['high'] for bar in minute_bars),
            "low": min(bar['low'] for bar in minute_bars),
            "close": minute_bars[-1]['close'],
            "volume": sum(bar['volume'] for bar in minute_bars),
            "last_update": minute_bars[-1]['last_update']
        }

        # Save aggregated bar
        bar_key = f"ohlcv:{symbol}:{timeframe}:current"
        await self.redis.set(bar_key, json.dumps(aggregated))

    def _get_interval_minutes(self, timeframe: str) -> int:
        """Get number of minutes in timeframe"""
        interval_map = {
            "1min": 1,
            "5min": 5,
            "15min": 15,
            "30min": 30,
            "1h": 60,
            "4h": 240,
            "1d": 1440
        }
        return interval_map.get(timeframe, 1)

    def _get_ttl(self, timeframe: str) -> int:
        """Get Redis TTL for timeframe"""
        ttl_map = {
            "1min": 120,
            "5min": 600,
            "15min": 1800,
            "30min": 3600,
            "1h": 7200,
            "4h": 28800,
            "1d": 172800
        }
        return ttl_map.get(timeframe, 300)

    async def _persist_to_db(self, symbol: str, timeframe: str, bar: Dict):
        """Persist completed bar to TimescaleDB"""
        # This would insert into minute_bars table
        # Implementation depends on your DB connection setup
        pass

    async def _trigger_indicator_update(self, symbol: str, timeframe: str):
        """Trigger indicator recalculation for this symbol/timeframe"""
        # Publish event for indicator service to pick up
        await self.redis.publish(
            "indicator_updates",
            json.dumps({
                "symbol": symbol,
                "timeframe": timeframe,
                "action": "recalculate"
            })
        )

    async def _fetch_minute_bars(self, symbol: str, start_ts: int, count: int) -> List[Dict]:
        """Fetch 1-minute bars from Redis or DB"""
        # Implementation would fetch from Redis cache first,
        # fall back to DB if needed
        pass
```

---

## 4. Shared Data Access Layer

### 4.1 Multi-Timeframe Data Manager

```python
# app/services/multi_timeframe_manager.py

class MultiTimeframeDataManager:
    """
    Unified interface for accessing OHLCV, Greeks, OI, and Indicators
    across multiple timeframes.
    """

    def __init__(self, redis_client: redis.Redis, db_pool):
        self.redis = redis_client
        self.db = db_pool

    async def get_ohlcv(
        self,
        symbol: str,
        timeframes: List[str],
        lookback: int = 100
    ) -> Dict[str, List[Dict]]:
        """
        Get OHLCV data for multiple timeframes.

        Returns:
        {
            "1min": [{ts, o, h, l, c, v}, ...],
            "5min": [{ts, o, h, l, c, v}, ...],
            "15min": [{ts, o, h, l, c, v}, ...]
        }
        """
        result = {}

        for timeframe in timeframes:
            # Try Redis cache first
            cached = await self._get_ohlcv_from_cache(symbol, timeframe, lookback)

            if cached:
                result[timeframe] = cached
            else:
                # Fall back to DB
                db_data = await self._get_ohlcv_from_db(symbol, timeframe, lookback)
                result[timeframe] = db_data

                # Cache for next time
                await self._cache_ohlcv_series(symbol, timeframe, db_data)

        return result

    async def get_current_ohlcv(
        self,
        symbol: str,
        timeframes: List[str]
    ) -> Dict[str, Dict]:
        """
        Get latest OHLCV bar for multiple timeframes.

        Returns:
        {
            "1min": {ts, o, h, l, c, v, is_complete},
            "5min": {ts, o, h, l, c, v, is_complete}
        }
        """
        result = {}

        for timeframe in timeframes:
            key = f"ohlcv:{symbol}:{timeframe}:latest"
            data = await self.redis.get(key)

            if data:
                result[timeframe] = json.loads(data)
            else:
                result[timeframe] = None

        return result

    async def get_indicators(
        self,
        symbol: str,
        timeframes: List[str],
        indicators: List[str]
    ) -> Dict[str, Dict[str, Dict]]:
        """
        Get indicator values across multiple timeframes.

        Returns:
        {
            "1min": {
                "RSI_14": {ts, value},
                "MACD_12_26_9": {ts, values: {MACD, MACDs, MACDh}}
            },
            "5min": {...}
        }
        """
        result = {}

        for timeframe in timeframes:
            result[timeframe] = {}

            for indicator_id in indicators:
                key = f"indicator:{symbol}:{timeframe}:{indicator_id}:latest"
                data = await self.redis.get(key)

                if data:
                    result[timeframe][indicator_id] = json.loads(data)
                else:
                    result[timeframe][indicator_id] = None

        return result

    async def get_greeks_for_chain(
        self,
        symbol: str,
        strikes: List[int],
        option_types: List[str] = ["CE", "PE"]
    ) -> Dict[str, Dict]:
        """
        Get Greeks for multiple strikes (option chain).

        Returns:
        {
            "26000_CE": {ts, iv, delta, gamma, theta, vega, rho},
            "26000_PE": {ts, iv, delta, gamma, theta, vega, rho},
            "26050_CE": {...}
        }
        """
        result = {}

        for strike in strikes:
            for opt_type in option_types:
                key = f"greeks:{symbol}:{strike}:{opt_type}:latest"
                data = await self.redis.get(key)

                identifier = f"{strike}_{opt_type}"
                if data:
                    result[identifier] = json.loads(data)
                else:
                    result[identifier] = None

        return result

    async def get_oi_for_chain(
        self,
        symbol: str,
        strikes: List[int],
        option_types: List[str] = ["CE", "PE"]
    ) -> Dict[str, Dict]:
        """
        Get OI data for multiple strikes.
        """
        result = {}

        for strike in strikes:
            for opt_type in option_types:
                key = f"oi:{symbol}:{strike}:{opt_type}:latest"
                data = await self.redis.get(key)

                identifier = f"{strike}_{opt_type}"
                if data:
                    result[identifier] = json.loads(data)
                else:
                    result[identifier] = None

        return result

    async def _get_ohlcv_from_cache(
        self,
        symbol: str,
        timeframe: str,
        lookback: int
    ) -> List[Dict]:
        """Get OHLCV series from Redis cache"""
        # Check if we have cached series
        series_key = f"ohlcv:{symbol}:{timeframe}:series"
        series_data = await self.redis.get(series_key)

        if series_data:
            series = json.loads(series_data)
            return series[-lookback:]  # Return last N bars

        return None

    async def _get_ohlcv_from_db(
        self,
        symbol: str,
        timeframe: str,
        lookback: int
    ) -> List[Dict]:
        """Fetch OHLCV from TimescaleDB"""
        # Query minute_bars with time_bucket for resampling
        # Implementation depends on DB schema
        pass

    async def _cache_ohlcv_series(
        self,
        symbol: str,
        timeframe: str,
        data: List[Dict]
    ):
        """Cache OHLCV series in Redis"""
        series_key = f"ohlcv:{symbol}:{timeframe}:series"
        ttl = self._get_series_ttl(timeframe)

        await self.redis.set(
            series_key,
            json.dumps(data),
            ex=ttl
        )

    def _get_series_ttl(self, timeframe: str) -> int:
        """Get TTL for cached series"""
        ttl_map = {
            "1min": 300,      # 5 minutes
            "5min": 1800,     # 30 minutes
            "15min": 3600,    # 1 hour
            "30min": 7200,    # 2 hours
            "1h": 14400,      # 4 hours
            "4h": 43200,      # 12 hours
            "1d": 86400       # 24 hours
        }
        return ttl_map.get(timeframe, 600)
```

---

## 5. API Endpoints for Multi-Timeframe Access

### 5.1 OHLCV Endpoints

```python
# app/routes/multi_timeframe_api.py

from fastapi import APIRouter, Depends, Query
from typing import List, Optional

router = APIRouter(prefix="/api/multi-timeframe", tags=["Multi-Timeframe"])

@router.get("/ohlcv/{symbol}")
async def get_ohlcv_multi_timeframe(
    symbol: str,
    timeframes: List[str] = Query(default=["1min", "5min", "15min"]),
    lookback: int = Query(default=100, le=1000),
    manager: MultiTimeframeDataManager = Depends(get_mtf_manager)
):
    """
    Get OHLCV data for multiple timeframes.

    Example:
    GET /api/multi-timeframe/ohlcv/NIFTY50?timeframes=1min&timeframes=5min&timeframes=15min&lookback=100
    """
    data = await manager.get_ohlcv(symbol, timeframes, lookback)

    return {
        "symbol": symbol,
        "timeframes": data
    }

@router.get("/ohlcv/{symbol}/current")
async def get_current_ohlcv_multi_timeframe(
    symbol: str,
    timeframes: List[str] = Query(default=["1min", "5min", "15min"]),
    manager: MultiTimeframeDataManager = Depends(get_mtf_manager)
):
    """
    Get latest OHLCV bar for multiple timeframes.

    Example:
    GET /api/multi-timeframe/ohlcv/NIFTY50/current?timeframes=1min&timeframes=5min
    """
    data = await manager.get_current_ohlcv(symbol, timeframes)

    return {
        "symbol": symbol,
        "current": data
    }
```

### 5.2 Indicators Endpoint

```python
@router.get("/indicators/{symbol}")
async def get_indicators_multi_timeframe(
    symbol: str,
    timeframes: List[str] = Query(default=["5min", "15min"]),
    indicators: List[str] = Query(default=["RSI_14", "MACD_12_26_9"]),
    manager: MultiTimeframeDataManager = Depends(get_mtf_manager)
):
    """
    Get indicator values across multiple timeframes.

    Example:
    GET /api/multi-timeframe/indicators/NIFTY50?timeframes=5min&timeframes=15min&indicators=RSI_14&indicators=MACD_12_26_9
    """
    data = await manager.get_indicators(symbol, timeframes, indicators)

    return {
        "symbol": symbol,
        "indicators": data
    }
```

### 5.3 Options Chain Endpoint

```python
@router.get("/options-chain/{symbol}")
async def get_options_chain_multi_data(
    symbol: str,
    strikes: List[int] = Query(...),
    include_greeks: bool = Query(default=True),
    include_oi: bool = Query(default=True),
    manager: MultiTimeframeDataManager = Depends(get_mtf_manager)
):
    """
    Get Greeks and OI for multiple strikes in one call.

    Example:
    GET /api/multi-timeframe/options-chain/NIFTY50?strikes=26000&strikes=26050&strikes=26100&include_greeks=true&include_oi=true
    """
    result = {
        "symbol": symbol,
        "strikes": {}
    }

    if include_greeks:
        greeks_data = await manager.get_greeks_for_chain(symbol, strikes)
        result["greeks"] = greeks_data

    if include_oi:
        oi_data = await manager.get_oi_for_chain(symbol, strikes)
        result["oi"] = oi_data

    return result
```

---

## 6. WebSocket Streaming with Multi-Timeframe Support

```python
# app/routes/multi_timeframe_ws.py

from fastapi import WebSocket, WebSocketDisconnect
import json
import asyncio

@router.websocket("/ws/multi-timeframe/{symbol}")
async def websocket_multi_timeframe(
    websocket: WebSocket,
    symbol: str
):
    """
    WebSocket endpoint for streaming multi-timeframe data.

    Client sends subscription message:
    {
        "action": "subscribe",
        "data_types": ["ohlcv", "indicators"],
        "timeframes": ["1min", "5min", "15min"],
        "indicators": ["RSI_14", "MACD_12_26_9"]
    }

    Server streams updates as they occur.
    """
    await websocket.accept()

    subscriptions = {
        "data_types": [],
        "timeframes": [],
        "indicators": []
    }

    try:
        # Get initial subscription preferences
        message = await websocket.receive_text()
        sub_data = json.loads(message)

        if sub_data.get("action") == "subscribe":
            subscriptions["data_types"] = sub_data.get("data_types", [])
            subscriptions["timeframes"] = sub_data.get("timeframes", [])
            subscriptions["indicators"] = sub_data.get("indicators", [])

        # Subscribe to Redis pub/sub channels
        pubsub = redis_client.pubsub()

        channels = []
        for timeframe in subscriptions["timeframes"]:
            channels.append(f"ohlcv_updates:{symbol}:{timeframe}")

            for indicator in subscriptions["indicators"]:
                channels.append(f"indicator_updates:{symbol}:{timeframe}:{indicator}")

        await pubsub.subscribe(*channels)

        # Stream updates
        async for message in pubsub.listen():
            if message['type'] == 'message':
                data = json.loads(message['data'])
                await websocket.send_json(data)

    except WebSocketDisconnect:
        await pubsub.unsubscribe()
        await pubsub.close()
```

---

## 7. TimescaleDB Continuous Aggregates

For efficient historical data queries across timeframes, use TimescaleDB continuous aggregates:

```sql
-- Create continuous aggregate for 5-minute OHLCV
CREATE MATERIALIZED VIEW ohlcv_5min
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('5 minutes', ts) AS bucket,
    symbol,
    FIRST(open, ts) AS open,
    MAX(high) AS high,
    MIN(low) AS low,
    LAST(close, ts) AS close,
    SUM(volume) AS volume
FROM minute_bars
GROUP BY bucket, symbol;

-- Create continuous aggregate for 15-minute OHLCV
CREATE MATERIALIZED VIEW ohlcv_15min
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('15 minutes', ts) AS bucket,
    symbol,
    FIRST(open, ts) AS open,
    MAX(high) AS high,
    MIN(low) AS low,
    LAST(close, ts) AS close,
    SUM(volume) AS volume
FROM minute_bars
GROUP BY bucket, symbol;

-- Create continuous aggregate for 1-hour OHLCV
CREATE MATERIALIZED VIEW ohlcv_1h
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', ts) AS bucket,
    symbol,
    FIRST(open, ts) AS open,
    MAX(high) AS high,
    MIN(low) AS low,
    LAST(close, ts) AS close,
    SUM(volume) AS volume
FROM minute_bars
GROUP BY bucket, symbol;

-- Create refresh policy (refresh every 5 minutes)
SELECT add_continuous_aggregate_policy('ohlcv_5min',
    start_offset => INTERVAL '1 day',
    end_offset => INTERVAL '1 minute',
    schedule_interval => INTERVAL '5 minutes');

SELECT add_continuous_aggregate_policy('ohlcv_15min',
    start_offset => INTERVAL '1 day',
    end_offset => INTERVAL '1 minute',
    schedule_interval => INTERVAL '15 minutes');

SELECT add_continuous_aggregate_policy('ohlcv_1h',
    start_offset => INTERVAL '1 day',
    end_offset => INTERVAL '1 minute',
    schedule_interval => INTERVAL '1 hour');
```

**Benefits**:
- Pre-aggregated data for fast queries
- Automatic refresh policies
- No need to resample on every request
- Efficient storage with compression

---

## 8. Optimization Strategies

### 8.1 Lazy Computation

Only compute indicators for timeframes that have active subscribers:

```python
# Before computing indicator
if await subscription_manager.has_active_subscribers(symbol, timeframe, indicator_id):
    # Compute and cache
    value = await compute_indicator(symbol, timeframe, indicator_id)
    await cache_indicator_value(symbol, timeframe, indicator_id, value)
else:
    # Skip computation - no one is subscribed
    pass
```

### 8.2 Batch Updates

Update multiple timeframes in a single operation:

```python
async def update_all_timeframes(symbol: str, tick_data: Dict):
    """
    Update all subscribed timeframes in batch.
    """
    # Get active timeframe subscriptions
    active_timeframes = await subscription_manager.get_active_timeframes(symbol)

    # Update each timeframe in parallel
    tasks = [
        processor.process_tick_for_timeframe(symbol, tf, tick_data)
        for tf in active_timeframes
    ]

    await asyncio.gather(*tasks)
```

### 8.3 Data Deduplication

Share base OHLCV data across indicator calculations:

```python
# Cache OHLCV series once
ohlcv_series = await fetch_ohlcv(symbol, timeframe, lookback=100)

# Compute multiple indicators from same OHLCV data
rsi = compute_rsi(ohlcv_series, length=14)
macd = compute_macd(ohlcv_series, fast=12, slow=26, signal=9)
bbands = compute_bbands(ohlcv_series, length=20, std=2)

# Cache all results
await cache_indicators({
    "RSI_14": rsi,
    "MACD_12_26_9": macd,
    "BBANDS_20_2": bbands
})
```

---

## 9. Implementation Roadmap

### Phase 1: Foundation (Week 1)
- Implement `MultiTimeframeProcessor` for real-time tick processing
- Set up Redis cache structure for OHLCV across timeframes
- Create TimescaleDB continuous aggregates for 5min, 15min, 1h

### Phase 2: Data Access Layer (Week 2)
- Implement `MultiTimeframeDataManager` for unified data access
- Create REST API endpoints for multi-timeframe queries
- Add caching layer with proper TTLs

### Phase 3: Indicators (Week 3)
- Integrate indicator computation with multi-timeframe OHLCV
- Implement lazy computation based on subscriptions
- Add indicator caching per timeframe

### Phase 4: WebSocket Streaming (Week 4)
- Implement WebSocket endpoint for multi-timeframe streaming
- Add Redis pub/sub for real-time updates
- Handle client reconnection and subscription management

### Phase 5: Optimization (Week 5)
- Add batch update operations
- Implement data deduplication strategies
- Performance testing and tuning

---

## Summary

**Best Practices for Multi-Timeframe Data Sharing**:

1. **Single Source of Truth**: Store 1-minute bars as atomic unit, derive all higher timeframes
2. **Continuous Aggregates**: Use TimescaleDB for pre-computed aggregations
3. **Layered Caching**: Redis for hot data, DB for historical
4. **Lazy Computation**: Only compute indicators for active subscriptions
5. **Batch Operations**: Update multiple timeframes in parallel
6. **Smart TTLs**: Cache duration based on timeframe granularity
7. **Unified API**: Single interface for accessing all data types across timeframes

This ensures:
- ✅ No redundant computation for same symbol
- ✅ Efficient data sharing across timeframes
- ✅ Fast access via caching
- ✅ Real-time updates propagate correctly
- ✅ Scalable to many symbols and timeframes
