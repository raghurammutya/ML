# Technical Indicators System - Architecture

**Date**: 2025-10-31
**Status**: Design Phase

---

## Overview

A dynamic technical indicators system that computes indicators on-the-fly using `pandas_ta`, supports multiple timeframes, parameter customization, and provides both REST and WebSocket APIs with smart caching.

---

## Requirements

### Functional Requirements

1. **Dynamic Indicator Specification**
   - Support any pandas_ta indicator: RSI, SMA, EMA, MACD, Bollinger Bands, ATR, etc.
   - Customizable parameters: `RSI(14)`, `RSI(10,2)`, `SMA(20)`, `BBANDS(20,2)`
   - Multi-timeframe: 1min, 5min, 15min, 60min, day

2. **Historical Values**
   - Query indicator values N candles back
   - Batch fetch: get indicator series (e.g., last 100 values)

3. **Real-time Updates**
   - Subscribe to indicators for real-time computation
   - WebSocket streaming as new candles form
   - Unsubscribe when no longer needed

4. **Smart Caching**
   - Cache computed indicators to avoid recomputation
   - TTL-based expiration (1min indicators: 60s TTL, 5min: 300s TTL)
   - Invalidate on new candle data

5. **Performance**
   - Handle 100+ concurrent indicator subscriptions
   - Sub-100ms computation time for common indicators
   - Efficient OHLCV data fetching

---

## Architecture

### Components

```
┌─────────────────────────────────────────────────────────────┐
│                     Client (Python Algo)                     │
└─────────────────────┬───────────────────────────────────────┘
                      │
        ┌─────────────┴──────────────┐
        │                            │
        ▼                            ▼
  ┌──────────┐               ┌──────────────┐
  │ REST API │               │  WebSocket   │
  │          │               │   Streaming  │
  └────┬─────┘               └───────┬──────┘
       │                             │
       │    ┌────────────────────────┘
       │    │
       ▼    ▼
┌──────────────────────────────────────────────┐
│      Indicator Subscription Manager          │
│  - Track active subscriptions                │
│  - Redis: indicator_subs:<symbol>:<tf>       │
└─────────────────┬────────────────────────────┘
                  │
                  ▼
┌──────────────────────────────────────────────┐
│         Indicator Computer Service           │
│  - pandas_ta integration                     │
│  - Compute indicators on OHLCV data          │
│  - Support all pandas_ta indicators          │
└─────────────────┬────────────────────────────┘
                  │
        ┌─────────┴─────────┐
        │                   │
        ▼                   ▼
┌─────────────┐      ┌──────────────┐
│ Cache Layer │      │   Database   │
│   (Redis)   │      │ (TimescaleDB)│
│             │      │              │
│ - Indicator │      │ - minute_bars│
│   values    │      │ - OHLCV data │
│ - TTL-based │      │              │
└─────────────┘      └──────────────┘
```

---

## Data Model

### 1. Indicator Subscription (Redis)

```python
# Redis key format: indicator_subs:{symbol}:{timeframe}
# Value: Set of indicator specs

Key: "indicator_subs:NIFTY50:5min"
Value: {
    "RSI_14",           # RSI with period 14
    "RSI_10_2",         # RSI with period 10, scalar 2
    "SMA_20",           # SMA with period 20
    "EMA_50",           # EMA with period 50
    "MACD_12_26_9",     # MACD with fast=12, slow=26, signal=9
    "BBANDS_20_2"       # Bollinger Bands with period 20, stddev 2
}

# Subscription metadata
Key: "indicator_sub_meta:{symbol}:{timeframe}:{indicator_spec}"
Value: {
    "subscriber_count": 3,
    "created_at": "2025-10-31T10:00:00Z",
    "last_computed": "2025-10-31T10:05:00Z",
    "ttl": 300  # seconds
}
```

### 2. Cached Indicator Values (Redis)

```python
# Single value cache
Key: "indicator_value:{symbol}:{timeframe}:{indicator_spec}:{timestamp}"
Value: {
    "value": 64.5,      # For single-value indicators (RSI, SMA, etc.)
    "timestamp": 1730369100,
    "candle_time": "2025-10-31T10:05:00Z",
    "computed_at": "2025-10-31T10:05:02Z"
}
TTL: 300 seconds (5min for 5min timeframe)

# Multi-value cache (for indicators like BBANDS, MACD)
Key: "indicator_value:{symbol}:{timeframe}:BBANDS_20_2:{timestamp}"
Value: {
    "BBU_20_2.0": 23150.5,   # Upper band
    "BBM_20_2.0": 23100.0,   # Middle band
    "BBL_20_2.0": 23050.5,   # Lower band
    "timestamp": 1730369100,
    "candle_time": "2025-10-31T10:05:00Z"
}

# Series cache (for batch queries)
Key: "indicator_series:{symbol}:{timeframe}:{indicator_spec}:{from_ts}:{to_ts}"
Value: [
    {"time": 1730369100, "value": 64.5},
    {"time": 1730369400, "value": 65.2},
    {"time": 1730369700, "value": 63.8},
    ...
]
TTL: 600 seconds
```

### 3. Historical Snapshots (TimescaleDB)

```sql
-- Position snapshots
CREATE TABLE position_snapshots (
    snapshot_time TIMESTAMPTZ NOT NULL,
    account_id VARCHAR(255) NOT NULL,
    tradingsymbol VARCHAR(100) NOT NULL,
    quantity NUMERIC(20,8),
    average_price NUMERIC(20,8),
    last_price NUMERIC(20,8),
    unrealized_pnl NUMERIC(20,8),
    realized_pnl NUMERIC(20,8),
    product_type VARCHAR(50),
    margin_used NUMERIC(20,8),
    snapshot_data JSONB,
    PRIMARY KEY (snapshot_time, account_id, tradingsymbol)
);

SELECT create_hypertable('position_snapshots', 'snapshot_time');
CREATE INDEX idx_position_snapshots_account ON position_snapshots(account_id, snapshot_time DESC);

-- Holdings snapshots
CREATE TABLE holdings_snapshots (
    snapshot_time TIMESTAMPTZ NOT NULL,
    account_id VARCHAR(255) NOT NULL,
    tradingsymbol VARCHAR(100) NOT NULL,
    quantity NUMERIC(20,8),
    average_price NUMERIC(20,8),
    current_price NUMERIC(20,8),
    market_value NUMERIC(20,8),
    day_change NUMERIC(20,8),
    snapshot_data JSONB,
    PRIMARY KEY (snapshot_time, account_id, tradingsymbol)
);

SELECT create_hypertable('holdings_snapshots', 'snapshot_time');
CREATE INDEX idx_holdings_snapshots_account ON holdings_snapshots(account_id, snapshot_time DESC);

-- Funds snapshots
CREATE TABLE funds_snapshots (
    snapshot_time TIMESTAMPTZ NOT NULL,
    account_id VARCHAR(255) NOT NULL,
    segment VARCHAR(20) NOT NULL,
    available_cash NUMERIC(12,2),
    available_margin NUMERIC(12,2),
    used_margin NUMERIC(12,2),
    net NUMERIC(12,2),
    snapshot_data JSONB,
    PRIMARY KEY (snapshot_time, account_id, segment)
);

SELECT create_hypertable('funds_snapshots', 'snapshot_time');
CREATE INDEX idx_funds_snapshots_account ON funds_snapshots(account_id, segment, snapshot_time DESC);
```

---

## API Design

### REST API

#### 1. Subscribe to Indicator

```http
POST /indicators/subscribe
Content-Type: application/json
Authorization: Bearer {api_key}

{
  "symbol": "NIFTY50",
  "timeframe": "5min",
  "indicators": [
    {"name": "RSI", "params": {"length": 14}},
    {"name": "RSI", "params": {"length": 10, "scalar": 2}},
    {"name": "SMA", "params": {"length": 20}},
    {"name": "EMA", "params": {"length": 50}},
    {"name": "MACD", "params": {"fast": 12, "slow": 26, "signal": 9}},
    {"name": "BBANDS", "params": {"length": 20, "std": 2}}
  ]
}

Response:
{
  "status": "success",
  "subscriptions": [
    {
      "indicator_id": "RSI_14",
      "symbol": "NIFTY50",
      "timeframe": "5min",
      "status": "active",
      "expires_at": "2025-10-31T10:30:00Z"
    },
    ...
  ]
}
```

#### 2. Unsubscribe from Indicator

```http
POST /indicators/unsubscribe
Content-Type: application/json
Authorization: Bearer {api_key}

{
  "symbol": "NIFTY50",
  "timeframe": "5min",
  "indicator_ids": ["RSI_14", "SMA_20"]
}

Response:
{
  "status": "success",
  "unsubscribed": ["RSI_14", "SMA_20"]
}
```

#### 3. Get Current Indicator Values

```http
GET /indicators/current?symbol=NIFTY50&timeframe=5min&indicators=RSI_14,SMA_20,EMA_50
Authorization: Bearer {api_key}

Response:
{
  "status": "success",
  "symbol": "NIFTY50",
  "timeframe": "5min",
  "timestamp": 1730369100,
  "candle_time": "2025-10-31T10:05:00Z",
  "indicators": {
    "RSI_14": 64.5,
    "SMA_20": 23100.25,
    "EMA_50": 23050.75
  }
}
```

#### 4. Get Historical Indicator Values (N Candles Back)

```http
GET /indicators/history?symbol=NIFTY50&timeframe=5min&indicator=RSI_14&lookback=20
Authorization: Bearer {api_key}

Response:
{
  "status": "success",
  "symbol": "NIFTY50",
  "timeframe": "5min",
  "indicator": "RSI_14",
  "series": [
    {"time": 1730367600, "value": 62.3, "candles_back": 20},
    {"time": 1730367900, "value": 63.1, "candles_back": 19},
    {"time": 1730368200, "value": 64.2, "candles_back": 18},
    ...
    {"time": 1730369100, "value": 64.5, "candles_back": 0}
  ]
}
```

#### 5. Get Multiple Indicators at Specific Offset

```http
GET /indicators/at-offset?symbol=NIFTY50&timeframe=5min&indicators=RSI_14,SMA_20&offset=5
Authorization: Bearer {api_key}

Response:
{
  "status": "success",
  "symbol": "NIFTY50",
  "timeframe": "5min",
  "offset": 5,  # 5 candles back
  "timestamp": 1730367600,
  "indicators": {
    "RSI_14": 62.3,
    "SMA_20": 23095.5
  }
}
```

#### 6. Batch Query Multiple Timeframes

```http
POST /indicators/batch
Content-Type: application/json
Authorization: Bearer {api_key}

{
  "symbol": "NIFTY50",
  "queries": [
    {"timeframe": "1min", "indicator": "RSI_14", "lookback": 10},
    {"timeframe": "5min", "indicator": "RSI_14", "lookback": 20},
    {"timeframe": "15min", "indicator": "SMA_20", "lookback": 10}
  ]
}

Response:
{
  "status": "success",
  "results": [
    {
      "timeframe": "1min",
      "indicator": "RSI_14",
      "series": [...]
    },
    {
      "timeframe": "5min",
      "indicator": "RSI_14",
      "series": [...]
    },
    ...
  ]
}
```

---

### WebSocket API

#### Connection

```javascript
ws://localhost:8009/indicators/stream?api_key={api_key}
```

#### Subscribe Message

```json
{
  "action": "subscribe",
  "symbol": "NIFTY50",
  "timeframe": "5min",
  "indicators": ["RSI_14", "SMA_20", "EMA_50"]
}
```

#### Unsubscribe Message

```json
{
  "action": "unsubscribe",
  "symbol": "NIFTY50",
  "timeframe": "5min",
  "indicators": ["RSI_14"]
}
```

#### Update Message (Server → Client)

```json
{
  "type": "indicator_update",
  "symbol": "NIFTY50",
  "timeframe": "5min",
  "timestamp": 1730369100,
  "candle_time": "2025-10-31T10:05:00Z",
  "indicators": {
    "RSI_14": 64.5,
    "SMA_20": 23100.25,
    "EMA_50": 23050.75
  }
}
```

---

## Indicator Specification Format

### Standard Format

```
{indicator_name}_{param1}_{param2}_{...}
```

### Examples

| pandas_ta Call | Indicator ID | Description |
|---------------|--------------|-------------|
| `ta.rsi(close, length=14)` | `RSI_14` | RSI with period 14 |
| `ta.rsi(close, length=10, scalar=2)` | `RSI_10_2` | RSI with period 10, scalar 2 |
| `ta.sma(close, length=20)` | `SMA_20` | Simple Moving Average 20 |
| `ta.ema(close, length=50)` | `EMA_50` | Exponential Moving Average 50 |
| `ta.macd(close, fast=12, slow=26, signal=9)` | `MACD_12_26_9` | MACD with standard params |
| `ta.bbands(close, length=20, std=2)` | `BBANDS_20_2` | Bollinger Bands |
| `ta.atr(high, low, close, length=14)` | `ATR_14` | Average True Range |
| `ta.stoch(high, low, close, k=14, d=3)` | `STOCH_14_3` | Stochastic Oscillator |

---

## Caching Strategy

### Cache Levels

1. **L1 Cache: Latest Value** (Redis)
   - Key: `indicator_value:{symbol}:{tf}:{indicator}:latest`
   - TTL: Match timeframe (1min → 60s, 5min → 300s)
   - Invalidate on new candle

2. **L2 Cache: Historical Series** (Redis)
   - Key: `indicator_series:{symbol}:{tf}:{indicator}:{from}:{to}`
   - TTL: 600 seconds (10 minutes)
   - Store computed series to avoid recomputation

3. **L3 Cache: OHLCV Data** (Redis)
   - Key: `ohlcv_series:{symbol}:{tf}:{from}:{to}`
   - TTL: 300 seconds
   - Reuse OHLCV fetches across indicators

### Cache Invalidation

```python
# On new candle arrival
def on_new_candle(symbol: str, timeframe: str, candle_time: datetime):
    # Invalidate latest values
    redis.delete(f"indicator_value:{symbol}:{timeframe}:*:latest")

    # Trigger recomputation for active subscriptions
    active_indicators = get_active_subscriptions(symbol, timeframe)
    for indicator_id in active_indicators:
        compute_and_cache_indicator(symbol, timeframe, indicator_id)
```

### Smart Prefetching

```python
# When indicator is subscribed, prefetch recent OHLCV
def subscribe_indicator(symbol, timeframe, indicator_spec):
    # Most indicators need ~50-100 candles for accurate computation
    lookback = get_lookback_for_indicator(indicator_spec)  # e.g., 100 candles

    # Prefetch OHLCV if not in cache
    if not cache_exists(f"ohlcv_series:{symbol}:{timeframe}"):
        ohlcv = fetch_ohlcv(symbol, timeframe, lookback=lookback)
        cache_ohlcv(symbol, timeframe, ohlcv)

    # Compute initial value
    compute_and_cache_indicator(symbol, timeframe, indicator_spec)
```

---

## Performance Considerations

### Computation Optimization

1. **Batch Computation**
   - Compute all subscribed indicators for a symbol/timeframe together
   - Single OHLCV fetch for multiple indicators

2. **Incremental Computation**
   - For real-time updates, only compute on new candle
   - Use pandas rolling windows efficiently

3. **Parallel Processing**
   - Use asyncio for concurrent indicator computation
   - Compute different symbols/timeframes in parallel

### Resource Limits

```python
MAX_SUBSCRIPTIONS_PER_CLIENT = 50
MAX_HISTORICAL_LOOKBACK = 1000  # candles
INDICATOR_COMPUTATION_TIMEOUT = 5  # seconds
MAX_CONCURRENT_COMPUTATIONS = 100
```

---

## Implementation Components

### 1. Indicator Parser

```python
class IndicatorSpec:
    """Parse indicator specification."""

    @staticmethod
    def parse(indicator_id: str) -> Dict:
        """
        Parse indicator ID into name and params.

        Examples:
            "RSI_14" → {"name": "RSI", "params": {"length": 14}}
            "MACD_12_26_9" → {"name": "MACD", "params": {"fast": 12, "slow": 26, "signal": 9}}
        """
        parts = indicator_id.split("_")
        name = parts[0]
        params = parts[1:]

        # Map to pandas_ta parameter names
        param_mapping = INDICATOR_PARAM_NAMES[name]  # e.g., {"RSI": ["length", "scalar"], ...}

        return {
            "name": name,
            "params": dict(zip(param_mapping, [float(p) for p in params]))
        }
```

### 2. Indicator Computer

```python
import pandas as pd
import pandas_ta as ta

class IndicatorComputer:
    """Compute technical indicators using pandas_ta."""

    async def compute(self, symbol: str, timeframe: str,
                     indicator_spec: Dict, lookback: int = 100) -> pd.Series:
        """
        Compute indicator values.

        Args:
            symbol: "NIFTY50"
            timeframe: "5min"
            indicator_spec: {"name": "RSI", "params": {"length": 14}}
            lookback: Number of candles needed

        Returns:
            pd.Series with indicator values
        """
        # Fetch OHLCV data
        ohlcv = await self.fetch_ohlcv(symbol, timeframe, lookback)
        df = pd.DataFrame(ohlcv)

        # Compute indicator
        name = indicator_spec["name"].lower()
        params = indicator_spec["params"]

        if name == "rsi":
            result = ta.rsi(df['close'], **params)
        elif name == "sma":
            result = ta.sma(df['close'], **params)
        elif name == "ema":
            result = ta.ema(df['close'], **params)
        elif name == "macd":
            result = ta.macd(df['close'], **params)
        elif name == "bbands":
            result = ta.bbands(df['close'], **params)
        elif name == "atr":
            result = ta.atr(df['high'], df['low'], df['close'], **params)
        # ... more indicators

        return result
```

### 3. Subscription Manager

```python
class IndicatorSubscriptionManager:
    """Manage indicator subscriptions."""

    async def subscribe(self, client_id: str, symbol: str,
                       timeframe: str, indicators: List[str]):
        """Subscribe client to indicators."""
        # Add to Redis set
        for indicator_id in indicators:
            await self.redis.sadd(
                f"indicator_subs:{symbol}:{timeframe}",
                indicator_id
            )

            # Track subscriber count
            await self.redis.hincrby(
                f"indicator_sub_meta:{symbol}:{timeframe}:{indicator_id}",
                "subscriber_count",
                1
            )

            # Trigger initial computation if not cached
            if not await self.is_cached(symbol, timeframe, indicator_id):
                await self.compute_and_cache(symbol, timeframe, indicator_id)

    async def unsubscribe(self, client_id: str, symbol: str,
                         timeframe: str, indicators: List[str]):
        """Unsubscribe client from indicators."""
        for indicator_id in indicators:
            count = await self.redis.hincrby(
                f"indicator_sub_meta:{symbol}:{timeframe}:{indicator_id}",
                "subscriber_count",
                -1
            )

            # If no subscribers left, remove from active set
            if count <= 0:
                await self.redis.srem(
                    f"indicator_subs:{symbol}:{timeframe}",
                    indicator_id
                )
```

---

## Deployment Checklist

- [ ] Install pandas_ta: `pip install pandas_ta`
- [ ] Create migration for snapshot tables
- [ ] Implement IndicatorComputer service
- [ ] Implement SubscriptionManager
- [ ] Implement REST API endpoints
- [ ] Implement WebSocket streaming
- [ ] Configure Redis caching
- [ ] Add background jobs for snapshot service
- [ ] Performance testing (100+ concurrent subscriptions)
- [ ] Documentation and examples

---

**Next**: Implementation in phases
