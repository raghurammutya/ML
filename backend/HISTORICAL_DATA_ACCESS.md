# Historical Data Access - N Candles Back

**Date**: 2025-10-31
**Purpose**: Guide for accessing historical data N candles back in time

---

## Overview

This guide explains how Python algo services can access historical data from **N candles ago**. The backend stores complete time-series data for market metrics but has limitations on account data.

### Data Availability Summary

| Data Type | Historical Access | Storage | N Candles Back |
|-----------|------------------|---------|----------------|
| **OHLCV** | ✅ Full | TimescaleDB `minute_bars` | Yes |
| **Greeks (IV/Delta/Gamma/etc)** | ✅ Full | TimescaleDB `fo_option_strike_bars` | Yes |
| **Open Interest** | ✅ Full | `fo_option_strike_bars` | Yes |
| **OI Change** | ✅ Calculated | Derived from OI series | Yes |
| **PCR (Put-Call Ratio)** | ✅ Full | Calculated from OI data | Yes |
| **Orders** | ✅ Full | `orders` table with timestamps | Yes |
| **Positions** | ❌ Current only | `positions` table (no snapshots) | **No** |
| **Holdings** | ❌ Current only | `holdings` table (no snapshots) | **No** |
| **Funds** | ❌ Current only | `account_funds` table (no snapshots) | **No** |

---

## 1. OHLCV - N Candles Back ✅

### Database Schema
```sql
Table: minute_bars
- time: timestamp (partition key)
- open, high, low, close: numeric(12,4)
- volume: bigint
- symbol: text
- resolution: smallint (minutes: 1, 5, 15, 60, 1440)
```

### Method 1: Query Specific Time Range

```python
from datetime import datetime, timedelta

def get_ohlcv_n_candles_back(symbol: str, timeframe_minutes: int, n_candles: int) -> List[Dict]:
    """
    Get OHLCV data for N candles back from now.

    Args:
        symbol: "NIFTY50", "BANKNIFTY", etc.
        timeframe_minutes: 1, 5, 15, 60, 1440 (day)
        n_candles: Number of candles to fetch

    Returns:
        List of candles from oldest to newest
    """
    # Calculate time range
    to_ts = datetime.now()
    from_ts = to_ts - timedelta(minutes=timeframe_minutes * n_candles)

    # Fetch data
    response = httpx.get("http://localhost:8009/historical/series", params={
        "symbol": symbol,
        "underlying": symbol,
        "interval": f"{timeframe_minutes}minute",
        "from_ts": from_ts.isoformat(),
        "to_ts": to_ts.isoformat()
    })

    candles = response.json()["data"]
    return candles

# Example: Get last 20 five-minute candles
candles = get_ohlcv_n_candles_back("NIFTY50", timeframe_minutes=5, n_candles=20)

# Access specific candles
current_candle = candles[-1]        # Most recent (N=0)
one_candle_back = candles[-2]       # 1 candle back (N=1)
two_candles_back = candles[-3]      # 2 candles back (N=2)
ten_candles_back = candles[-11]     # 10 candles back (N=10)

print(f"Current close: {current_candle['close']}")
print(f"1 candle back: {one_candle_back['close']}")
print(f"10 candles back: {ten_candles_back['close']}")
```

### Method 2: Get Specific Candle

```python
def get_candle_at_offset(symbol: str, timeframe_minutes: int, n: int) -> Dict:
    """
    Get the candle N periods back.

    Args:
        n: 0 = current, 1 = one candle back, 2 = two candles back, etc.
    """
    to_ts = datetime.now() - timedelta(minutes=timeframe_minutes * n)
    from_ts = to_ts - timedelta(minutes=timeframe_minutes)

    response = httpx.get("http://localhost:8009/historical/series", params={
        "symbol": symbol,
        "underlying": symbol,
        "interval": f"{timeframe_minutes}minute",
        "from_ts": from_ts.isoformat(),
        "to_ts": to_ts.isoformat()
    })

    candles = response.json()["data"]
    return candles[0] if candles else None

# Example: Get close price from 5 candles ago (5min timeframe)
candle_5_back = get_candle_at_offset("NIFTY50", 5, n=5)
print(f"Close 5 candles ago: {candle_5_back['close']}")
```

### Method 3: Batch Fetch with Offsets

```python
def get_multiple_candle_offsets(symbol: str, timeframe_minutes: int, offsets: List[int]) -> Dict[int, Dict]:
    """
    Get multiple specific candles by offset.

    Args:
        offsets: [0, 1, 5, 10] for current, 1 back, 5 back, 10 back

    Returns:
        {0: {candle_data}, 1: {candle_data}, 5: {candle_data}, ...}
    """
    max_offset = max(offsets)
    candles = get_ohlcv_n_candles_back(symbol, timeframe_minutes, max_offset + 1)

    result = {}
    for offset in offsets:
        if offset < len(candles):
            result[offset] = candles[-(offset + 1)]  # -1 for current, -2 for 1 back, etc.

    return result

# Example: Get current, 1 back, 5 back, 10 back
candle_map = get_multiple_candle_offsets("NIFTY50", 5, [0, 1, 5, 10])
print(f"Current: {candle_map[0]['close']}")
print(f"1 back: {candle_map[1]['close']}")
print(f"5 back: {candle_map[5]['close']}")
print(f"10 back: {candle_map[10]['close']}")
```

---

## 2. Greeks & Indicators - N Candles Back ✅

### Database Schema
```sql
Table: fo_option_strike_bars
- bucket_time: timestamp (partition key)
- timeframe: text (1min, 5min, etc.)
- symbol, expiry, strike
- call_iv_avg, put_iv_avg
- call_delta_avg, put_delta_avg
- call_gamma_avg, put_gamma_avg
- call_theta_avg, put_theta_avg
- call_vega_avg, put_vega_avg
- call_oi_sum, put_oi_sum
- call_volume, put_volume
```

### Get Greeks N Candles Back

```python
def get_greeks_n_candles_back(symbol: str, indicator: str, timeframe: str,
                              n_candles: int, option_side: str = "both",
                              expiry: Optional[str] = None) -> List[Dict]:
    """
    Get Greeks data for N candles back.

    Args:
        symbol: "NIFTY50", "BANKNIFTY"
        indicator: "iv", "delta", "gamma", "theta", "vega", "oi", "pcr"
        timeframe: "1", "5", "15", "60"
        n_candles: Number of candles to fetch
        option_side: "call", "put", "both"
        expiry: Optional expiry date filter
    """
    # Calculate time range (assuming timeframe in minutes)
    timeframe_minutes = int(timeframe) if timeframe.isdigit() else 5
    to_ts = datetime.now()
    from_ts = to_ts - timedelta(minutes=timeframe_minutes * n_candles)

    params = {
        "symbol": symbol,
        "timeframe": timeframe,
        "indicator": indicator,
        "option_side": option_side,
        "from_ts": from_ts.isoformat(),
        "to_ts": to_ts.isoformat(),
        "limit": n_candles + 10  # Buffer for gaps
    }

    if expiry:
        params["expiry[]"] = expiry

    response = httpx.get("http://localhost:8009/fo/moneyness-series", params=params)
    series = response.json()["series"]

    return series

# Example: Get IV for last 20 candles
iv_series = get_greeks_n_candles_back("NIFTY50", "iv", "5", n_candles=20, option_side="call")

# Access specific candles
current_iv = iv_series[-1]          # Current candle
one_back_iv = iv_series[-2]         # 1 candle back
five_back_iv = iv_series[-6]        # 5 candles back

print(f"Current ATM IV: {current_iv['ATM']}")
print(f"1 candle back ATM IV: {one_back_iv['ATM']}")
print(f"5 candles back ATM IV: {five_back_iv['ATM']}")

# Calculate IV change
iv_change = current_iv['ATM'] - one_back_iv['ATM']
print(f"IV change: {iv_change}")
```

### Get Strike-Level Data N Candles Back

```python
def get_strike_data_n_candles_back(symbol: str, indicator: str,
                                   timeframe: str, n_candles: int,
                                   expiry: Optional[str] = None) -> List[Dict]:
    """Get data across all strikes for N candles back."""

    timeframe_minutes = int(timeframe) if timeframe.isdigit() else 5
    to_ts = datetime.now()
    from_ts = to_ts - timedelta(minutes=timeframe_minutes * n_candles)

    params = {
        "symbol": symbol,
        "timeframe": timeframe,
        "indicator": indicator,
        "from_ts": from_ts.isoformat(),
        "to_ts": to_ts.isoformat()
    }

    if expiry:
        params["expiry[]"] = expiry

    response = httpx.get("http://localhost:8009/fo/strike-distribution", params=params)
    return response.json()["series"]

# Example: Get OI distribution 5 candles back
oi_history = get_strike_data_n_candles_back("NIFTY50", "oi", "5", n_candles=5)

# Current OI distribution
current_oi = [strike for strike in oi_history if strike['bucket_time'] == oi_history[-1]['bucket_time']]

# 3 candles back - find strikes with matching older bucket_time
# Note: Response may have multiple strikes per bucket_time, need to filter by time
```

---

## 3. Open Interest Change - N Candles Back ✅

OI change is calculated from OI time-series data:

```python
def get_oi_change_n_candles_back(symbol: str, timeframe: str,
                                 n_candles: int, expiry: Optional[str] = None) -> List[Dict]:
    """
    Calculate OI change for N candles back.

    Returns:
        List of dicts with bucket_time, ATM_change, OTM1_change, etc.
    """
    # Fetch N+1 candles to calculate change
    oi_series = get_greeks_n_candles_back(
        symbol=symbol,
        indicator="oi",
        timeframe=timeframe,
        n_candles=n_candles + 1,
        option_side="both",
        expiry=expiry
    )

    # Calculate changes
    changes = []
    for i in range(1, len(oi_series)):
        current = oi_series[i]
        previous = oi_series[i-1]

        change_data = {
            "bucket_time": current["bucket_time"],
            "candles_back": len(oi_series) - i - 1
        }

        # Calculate change for each moneyness level
        for key in current.keys():
            if key != "bucket_time" and key in previous:
                change_data[f"{key}_change"] = current[key] - previous[key]

        changes.append(change_data)

    return changes

# Example: Get OI change for last 10 candles
oi_changes = get_oi_change_n_candles_back("NIFTY50", "5", n_candles=10)

# Access specific OI changes
current_change = oi_changes[-1]     # Latest OI change
five_back_change = oi_changes[-6]   # 5 candles ago

print(f"Current ATM OI change: {current_change['ATM_change']}")
print(f"5 candles back ATM OI change: {five_back_change['ATM_change']}")
```

---

## 4. PCR (Put-Call Ratio) - N Candles Back ✅

```python
def get_pcr_n_candles_back(symbol: str, timeframe: str,
                           n_candles: int, expiry: Optional[str] = None) -> List[Dict]:
    """Get PCR for N candles back."""

    return get_greeks_n_candles_back(
        symbol=symbol,
        indicator="pcr",
        timeframe=timeframe,
        n_candles=n_candles,
        option_side="both",
        expiry=expiry
    )

# Example: Get PCR for last 20 candles
pcr_series = get_pcr_n_candles_back("NIFTY50", "5", n_candles=20)

# Access specific PCR values
current_pcr = pcr_series[-1]['ATM']
five_back_pcr = pcr_series[-6]['ATM']

print(f"Current PCR: {current_pcr}")
print(f"5 candles back PCR: {five_back_pcr}")
print(f"PCR change: {current_pcr - five_back_pcr}")
```

---

## 5. LTP (Last Traded Price) - N Candles Back ✅

### Underlying LTP N Candles Back

```python
def get_underlying_ltp_n_candles_back(symbol: str, timeframe_minutes: int,
                                       n: int) -> float:
    """
    Get underlying LTP from N candles ago.

    Args:
        n: 0 = current, 1 = one candle back, etc.

    Returns:
        Close price N candles ago
    """
    candle = get_candle_at_offset(symbol, timeframe_minutes, n)
    return candle['close'] if candle else None

# Example: Get NIFTY50 LTP from 5 candles ago
ltp_5_back = get_underlying_ltp_n_candles_back("NIFTY50", timeframe_minutes=5, n=5)
print(f"NIFTY50 LTP 5 candles ago: {ltp_5_back}")
```

### Option Premium N Candles Back

**⚠️ LIMITATION**: The backend does NOT currently store individual option contract OHLCV data.

**Available Data**:
- ✅ Greeks aggregated by moneyness (ATM, OTM1, etc.)
- ✅ OI and volume by strike
- ❌ Individual option premium prices (bid/ask/LTP)

**Workarounds**:

**Option 1: Use Current LTP Only**
```python
# Current option premium from ticker_service
def get_option_ltp_current(instrument_token: int) -> float:
    """Get current option premium only."""
    response = httpx.get("http://localhost:8080/quote", params={
        "instrument_token": instrument_token,
        "user_id": "primary"
    })
    return response.json()["last_price"]

# NOTE: Historical option premiums not available
```

**Option 2: Request Backend Enhancement**

To enable historical option premium tracking, the backend would need:
1. Store individual option contract OHLCV in new table
2. Add endpoint: `GET /fo/option-candles/{instrument_token}`

**Recommended Approach for Now**:
- Track current option premiums in your algo's state
- Store them yourself for historical analysis
- Or request backend enhancement (see Section 8)

---

## 6. Orders - N Candles Back ✅

### Database Schema
```sql
Table: orders
- created_at: timestamp (when order was created)
- placed_at: timestamp (when order was placed with broker)
- executed_at: timestamp (when order was executed)
- cancelled_at: timestamp (when order was cancelled)
- updated_at: timestamp (last update)
- status: varchar (pending, complete, cancelled, rejected)
```

### Get Orders from N Candles Ago

```python
def get_orders_n_candles_back(account_id: str, timeframe_minutes: int,
                              n: int, api_key: str) -> List[Dict]:
    """
    Get orders that were active N candles ago.

    Args:
        n: 0 = current candle, 1 = one candle back, etc.

    Returns:
        Orders that existed at that time
    """
    # Calculate the timestamp N candles ago
    target_time = datetime.now() - timedelta(minutes=timeframe_minutes * n)

    # Fetch all orders
    response = httpx.get(
        f"http://localhost:8009/accounts/{account_id}/orders",
        headers={"Authorization": f"Bearer {api_key}"}
    )

    all_orders = response.json()["data"]

    # Filter orders that existed at target_time
    orders_at_time = []
    for order in all_orders:
        created = datetime.fromisoformat(order['created_at'].replace('Z', '+00:00'))

        # Order must have been created before target_time
        if created <= target_time:
            # If executed/cancelled, it must have been after target_time
            # (otherwise order didn't exist at that time)
            executed = order.get('executed_at')
            cancelled = order.get('cancelled_at')

            still_active = True
            if executed:
                exec_time = datetime.fromisoformat(executed.replace('Z', '+00:00'))
                if exec_time < target_time:
                    still_active = False

            if cancelled:
                cancel_time = datetime.fromisoformat(cancelled.replace('Z', '+00:00'))
                if cancel_time < target_time:
                    still_active = False

            if still_active:
                orders_at_time.append(order)

    return orders_at_time

# Example: Get orders that were active 10 candles ago
orders_10_back = get_orders_n_candles_back("primary", timeframe_minutes=5, n=10, api_key=API_KEY)
print(f"Orders active 10 candles ago: {len(orders_10_back)}")
```

### Get Orders Placed Between N1 and N2 Candles Back

```python
def get_orders_between_candles(account_id: str, timeframe_minutes: int,
                               n1: int, n2: int, api_key: str) -> List[Dict]:
    """
    Get orders placed between N1 and N2 candles ago.

    Args:
        n1: Start offset (e.g., 5 candles ago)
        n2: End offset (e.g., 10 candles ago)
    """
    time_start = datetime.now() - timedelta(minutes=timeframe_minutes * max(n1, n2))
    time_end = datetime.now() - timedelta(minutes=timeframe_minutes * min(n1, n2))

    response = httpx.get(
        f"http://localhost:8009/accounts/{account_id}/orders",
        headers={"Authorization": f"Bearer {api_key}"}
    )

    all_orders = response.json()["data"]

    # Filter by placed_at timestamp
    filtered = []
    for order in all_orders:
        placed = datetime.fromisoformat(order['placed_at'].replace('Z', '+00:00'))
        if time_start <= placed <= time_end:
            filtered.append(order)

    return filtered

# Example: Get orders placed between 5 and 10 candles ago
orders_range = get_orders_between_candles("primary", 5, n1=5, n2=10, api_key=API_KEY)
```

---

## 7. Positions, Holdings, Funds - N Candles Back ❌

### ⚠️ LIMITATION: Historical Snapshots Not Stored

The backend **DOES NOT** store historical snapshots of:
- Positions
- Holdings
- Funds

**What IS Stored**:
- ✅ `updated_at` timestamp (when position was last updated)
- ✅ `created_at` timestamp (when position was first created)
- ❌ **Historical values** - Only current state is stored

**Why This Limitation Exists**:
- Positions/holdings/funds are fetched real-time from ticker_service
- Backend updates current state but doesn't snapshot history
- No time-series table for account state

### Workaround 1: Algo-Side State Tracking

**Recommended**: Your algo should maintain its own historical state:

```python
class AlgoStateTracker:
    """Track historical account state in algo memory."""

    def __init__(self):
        self.position_history = []  # List of (timestamp, positions)
        self.holdings_history = []
        self.funds_history = []

    def snapshot_current_state(self, client: AlgoTradingClient, account_id: str):
        """Take snapshot of current account state."""
        timestamp = datetime.now()

        positions = client.get_positions(account_id)
        holdings = client.get_holdings(account_id)
        funds = client.get_funds(account_id)

        self.position_history.append((timestamp, positions))
        self.holdings_history.append((timestamp, holdings))
        self.funds_history.append((timestamp, funds))

    def get_positions_n_candles_back(self, timeframe_minutes: int, n: int):
        """Get positions from N candles ago."""
        target_time = datetime.now() - timedelta(minutes=timeframe_minutes * n)

        # Find closest snapshot
        closest = None
        min_diff = float('inf')

        for timestamp, positions in self.position_history:
            diff = abs((timestamp - target_time).total_seconds())
            if diff < min_diff:
                min_diff = diff
                closest = positions

        return closest

    def get_pnl_change(self, timeframe_minutes: int, n: int):
        """Calculate PnL change over N candles."""
        current_positions = self.position_history[-1][1]
        past_positions = self.get_positions_n_candles_back(timeframe_minutes, n)

        if not past_positions:
            return None

        current_pnl = sum(pos['pnl'] for pos in current_positions)
        past_pnl = sum(pos['pnl'] for pos in past_positions)

        return current_pnl - past_pnl

# Usage in algo
tracker = AlgoStateTracker()

# In algo's main loop (every candle)
while trading:
    # Take snapshot at start of each candle
    tracker.snapshot_current_state(client, "primary")

    # Later: Access historical state
    positions_5_back = tracker.get_positions_n_candles_back(5, n=5)
    pnl_change = tracker.get_pnl_change(5, n=10)
```

### Workaround 2: Request Backend Enhancement

If you need historical positions/holdings/funds in the database:

**Backend Enhancement Needed**:
1. Create new tables:
   - `position_snapshots` (time-series table)
   - `holdings_snapshots` (time-series table)
   - `funds_snapshots` (time-series table)

2. Add scheduled job to snapshot every N minutes

3. Add new endpoints:
   - `GET /accounts/{id}/positions/history`
   - `GET /accounts/{id}/holdings/history`
   - `GET /accounts/{id}/funds/history`

**See Section 8 for implementation guide.**

---

## 8. Backend Enhancement: Historical Account Snapshots (Optional)

If you need historical positions/holdings/funds stored in the backend, here's what needs to be implemented:

### New Database Schema

```sql
-- Historical position snapshots
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

-- Historical holdings snapshots
CREATE TABLE holdings_snapshots (
    snapshot_time TIMESTAMPTZ NOT NULL,
    account_id VARCHAR(255) NOT NULL,
    tradingsymbol VARCHAR(100) NOT NULL,
    quantity NUMERIC(20,8),
    average_price NUMERIC(20,8),
    current_price NUMERIC(20,8),
    market_value NUMERIC(20,8),
    snapshot_data JSONB,
    PRIMARY KEY (snapshot_time, account_id, tradingsymbol)
);

SELECT create_hypertable('holdings_snapshots', 'snapshot_time');

-- Historical funds snapshots
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
```

### New Backend Service

```python
# app/services/account_snapshot_service.py
class AccountSnapshotService:
    """Service to snapshot account state periodically."""

    async def snapshot_account(self, account_id: str):
        """Take snapshot of positions, holdings, funds."""
        snapshot_time = datetime.now()

        # Fetch current state
        positions = await self.account_service.get_positions(account_id)
        holdings = await self.account_service.get_holdings(account_id)
        funds = await self.account_service.get_funds(account_id)

        # Store snapshots
        await self._store_position_snapshots(account_id, snapshot_time, positions)
        await self._store_holdings_snapshots(account_id, snapshot_time, holdings)
        await self._store_funds_snapshots(account_id, snapshot_time, funds)
```

### New API Endpoints

```python
@router.get("/accounts/{account_id}/positions/history")
async def get_position_history(
    account_id: str,
    from_ts: str,
    to_ts: str,
    tradingsymbol: Optional[str] = None
):
    """Get historical position snapshots."""
    ...

@router.get("/accounts/{account_id}/holdings/history")
async def get_holdings_history(account_id: str, from_ts: str, to_ts: str):
    """Get historical holdings snapshots."""
    ...

@router.get("/accounts/{account_id}/funds/history")
async def get_funds_history(account_id: str, from_ts: str, to_ts: str):
    """Get historical funds snapshots."""
    ...
```

**If you need this enhancement, let me know and I'll implement it!**

---

## 9. Complete Example: Trading Strategy with Historical Data

```python
import httpx
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict

class HistoricalDataAlgo:
    """Example algo using historical data N candles back."""

    def __init__(self, api_key: str, account_id: str = "primary"):
        self.api_key = api_key
        self.account_id = account_id
        self.base_url = "http://localhost:8009"
        self.headers = {"Authorization": f"Bearer {api_key}"}

    def analyze_trend(self, symbol: str, timeframe: int, lookback: int):
        """
        Analyze price trend using N candles back.

        Args:
            timeframe: Candle timeframe in minutes (5, 15, 60)
            lookback: Number of candles to analyze
        """
        # Get last N candles
        candles = get_ohlcv_n_candles_back(symbol, timeframe, lookback)

        if len(candles) < lookback:
            print("Insufficient data")
            return None

        # Calculate trend metrics
        current = candles[-1]
        five_back = candles[-6]
        ten_back = candles[-11]

        trend_5 = (current['close'] - five_back['close']) / five_back['close'] * 100
        trend_10 = (current['close'] - ten_back['close']) / ten_back['close'] * 100

        # Calculate momentum
        momentum = []
        for i in range(1, len(candles)):
            change = (candles[i]['close'] - candles[i-1]['close']) / candles[i-1]['close'] * 100
            momentum.append(change)

        avg_momentum = sum(momentum) / len(momentum)

        return {
            "current_price": current['close'],
            "trend_5_candles": trend_5,
            "trend_10_candles": trend_10,
            "avg_momentum": avg_momentum,
            "direction": "bullish" if avg_momentum > 0 else "bearish"
        }

    def check_iv_expansion(self, symbol: str, timeframe: str, lookback: int):
        """
        Check if IV is expanding using historical IV data.
        """
        iv_series = get_greeks_n_candles_back(symbol, "iv", timeframe, lookback, "call")

        if len(iv_series) < lookback:
            return None

        current_iv = iv_series[-1]['ATM']
        five_back_iv = iv_series[-6]['ATM']
        ten_back_iv = iv_series[-11]['ATM']

        iv_change_5 = current_iv - five_back_iv
        iv_change_10 = current_iv - ten_back_iv

        # Check for rapid IV expansion
        is_expanding = iv_change_5 > 2.0 and iv_change_10 > 3.0

        return {
            "current_iv": current_iv,
            "iv_change_5_candles": iv_change_5,
            "iv_change_10_candles": iv_change_10,
            "is_expanding": is_expanding
        }

    def check_oi_buildup(self, symbol: str, timeframe: str, lookback: int):
        """
        Check for OI buildup using N candles back.
        """
        oi_changes = get_oi_change_n_candles_back(symbol, timeframe, lookback)

        # Sum OI changes over lookback period
        total_atm_change = sum(c['ATM_change'] for c in oi_changes if 'ATM_change' in c)
        total_otm1_change = sum(c['OTM1_change'] for c in oi_changes if 'OTM1_change' in c)

        # Significant buildup threshold (example: 10% increase)
        is_buildup = total_atm_change > 100000  # Adjust threshold as needed

        return {
            "atm_oi_change": total_atm_change,
            "otm1_oi_change": total_otm1_change,
            "has_buildup": is_buildup
        }

    def generate_signal(self):
        """
        Generate trading signal using historical data.
        """
        symbol = "NIFTY50"
        timeframe = 5  # 5-minute candles

        # Analyze multiple timeframes
        trend = self.analyze_trend(symbol, timeframe, lookback=20)
        iv_status = self.check_iv_expansion(symbol, "5", lookback=20)
        oi_status = self.check_oi_buildup(symbol, "5", lookback=20)

        print(f"\n=== Trading Signal Analysis ===")
        print(f"Trend: {trend['direction']}")
        print(f"5-candle change: {trend['trend_5_candles']:.2f}%")
        print(f"10-candle change: {trend['trend_10_candles']:.2f}%")
        print(f"\nIV Status:")
        print(f"Current IV: {iv_status['current_iv']:.2f}")
        print(f"IV expanding: {iv_status['is_expanding']}")
        print(f"\nOI Status:")
        print(f"ATM OI change: {oi_status['atm_oi_change']}")
        print(f"Has buildup: {oi_status['has_buildup']}")

        # Trading logic
        if (trend['direction'] == 'bullish' and
            trend['trend_5_candles'] > 0.5 and
            not iv_status['is_expanding']):

            return {"action": "BUY_CALL", "confidence": "HIGH"}

        elif (trend['direction'] == 'bearish' and
              trend['trend_5_candles'] < -0.5 and
              iv_status['is_expanding'] and
              oi_status['has_buildup']):

            return {"action": "BUY_PUT", "confidence": "HIGH"}

        else:
            return {"action": "WAIT", "confidence": "LOW"}


# Run algo
if __name__ == "__main__":
    algo = HistoricalDataAlgo(api_key="sb_xxx_yyy...")
    signal = algo.generate_signal()
    print(f"\n=== SIGNAL: {signal['action']} (Confidence: {signal['confidence']}) ===")
```

---

## Summary Table

| Data Access | N Candles Back | Method | Status |
|------------|----------------|--------|--------|
| **OHLCV** | ✅ Yes | Query `minute_bars` with time range | Production ready |
| **Greeks (IV/Delta/etc)** | ✅ Yes | Query `fo_option_strike_bars` | Production ready |
| **Open Interest** | ✅ Yes | Query `fo_option_strike_bars` | Production ready |
| **OI Change** | ✅ Yes | Calculate from OI series | Production ready |
| **PCR** | ✅ Yes | Query via `/fo/moneyness-series?indicator=pcr` | Production ready |
| **Underlying LTP** | ✅ Yes | Use OHLCV close price | Production ready |
| **Option Premium** | ❌ No | Not stored (enhancement needed) | Use workaround |
| **Orders** | ✅ Yes | Filter by timestamp fields | Production ready |
| **Positions** | ❌ No | Only current state (enhancement needed) | Use workaround |
| **Holdings** | ❌ No | Only current state (enhancement needed) | Use workaround |
| **Funds** | ❌ No | Only current state (enhancement needed) | Use workaround |

---

## Next Steps

1. ✅ **Use Available Historical Data**: OHLCV, Greeks, OI, PCR, Orders
2. ⚠️ **For Positions/Holdings/Funds**: Implement algo-side state tracking (see Section 7)
3. 📋 **Optional**: Request backend enhancement for historical snapshots (see Section 8)

---

**Questions or need the backend enhancement implemented?** Let me know!

**Last Updated**: 2025-10-31
**Status**: Production Ready (with noted limitations)
