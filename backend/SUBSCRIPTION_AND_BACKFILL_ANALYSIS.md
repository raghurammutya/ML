# Subscription Management & Backfill Architecture Analysis

**Date**: November 1, 2025
**Status**: Analysis Complete

---

## Executive Summary

### Your Questions Answered

**Q1: How does the backend handle subscriptions? Is it smart/on-demand?**
- **Answer**: ❌ **NO**, it's **NOT** smart/on-demand. It uses a **pre-subscription model**.
- Subscriptions must be explicitly created via API calls to ticker service
- No automatic subscription when data is requested
- **Issue**: If user requests data for unsubscribed instrument, returns empty data

**Q2: Does backfill proactively fetch data when instruments are subscribed?**
- **Answer**: ❌ **NO**, backfill is NOT triggered by subscriptions.
- Backfill runs on a fixed 5-minute schedule, independent of subscriptions
- It detects gaps by querying the database, not subscription events
- **Issue**: Can lead to delays getting historical data after new subscription

---

## Part A: Subscription Management Architecture

### Current Implementation: Pre-Subscription Model

```
┌─────────────────────────────────────────────────────────────────┐
│                     SUBSCRIPTION FLOW                           │
└─────────────────────────────────────────────────────────────────┘

1. MANUAL SETUP (Required)
   └─► POST /subscriptions (ticker service API)
       ├─► Validates instrument exists
       ├─► Persists to PostgreSQL (instrument_subscriptions table)
       └─► Triggers FULL RELOAD of all WebSocket streams

2. DATA STARTS FLOWING (5-10 seconds after subscription)
   └─► Ticker Service WebSocket → Redis pub/sub → Backend → Database

3. USER REQUESTS DATA
   └─► GET /fo/strike-distribution
       ├─► Queries database
       ├─► Returns data IF subscribed
       └─► Returns EMPTY if not subscribed (no auto-subscribe)
```

### How It Works

#### Ticker Service (Manages WebSocket Subscriptions)

**Location**: `/mnt/stocksblitz-data/Quantagro/tradingview-viz/ticker_service`

```python
# PostgreSQL-backed subscriptions (persistent across restarts)
CREATE TABLE instrument_subscriptions (
    instrument_token BIGINT PRIMARY KEY,
    tradingsymbol TEXT NOT NULL,
    segment TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',  -- 'active' or 'inactive'
    requested_mode TEXT NOT NULL DEFAULT 'FULL',  -- 'FULL', 'QUOTE', 'LTP'
    account_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
```

**On Startup**:
1. Loads ALL active subscriptions from database
2. Distributes instruments across available Kite accounts (load balancing)
3. Establishes WebSocket connections
4. Starts streaming immediately

**On New Subscription** (POST /subscriptions):
1. Validates instrument exists in registry
2. Persists to database
3. **Stops ALL WebSocket streams** ⚠️
4. Reloads plan from database
5. **Restarts ALL streams** (~2-5 second disruption)

#### Backend (Consumes Data from Redis)

**Location**: `/home/stocksadmin/Quantagro/tradingview-viz/backend`

```python
# Backend does NOT manage subscriptions
# It only consumes data from Redis streams

@router.get("/fo/strike-distribution")
async def strike_distribution(...):
    # Queries database for aggregated data
    rows = await dm.fetch_latest_fo_strike_rows(...)

    # If no data (not subscribed), returns empty
    return {"status": "ok", "series": []}  # No error, no auto-subscribe
```

### Instrument Type Handling

#### 1. Underlying (NIFTY50 Index)

```python
# NOT subscription-based
# Polled every 5 seconds automatically
# Always active when ticker_loop is running

async def _stream_underlying(self):
    while not self._stop_event.is_set():
        if self._is_market_hours():
            quote = await client.get_quote(["NIFTY 50"])
            await publish_underlying_bar(quote)
        await asyncio.sleep(5)  # Fixed interval
```

**Characteristics**:
- ✅ Always available (no subscription needed)
- ✅ Single instrument
- ✅ Polled, not streamed

#### 2. Futures

```python
# Require explicit subscription
# Same as options

await ticker_client.subscribe(
    instrument_token=256265,  # NIFTY25NOVFUT
    requested_mode="FULL"
)
```

**Characteristics**:
- ❌ Must be subscribed explicitly
- ✅ Streamed via WebSocket
- ✅ Stored in `futures_bars` table

#### 3. Options

```python
# Primary use case - require subscription for EACH option contract

await ticker_client.subscribe(
    instrument_token=13660418,  # NIFTY25NOV24500CE
    requested_mode="FULL"
)
```

**Characteristics**:
- ❌ Must subscribe each strike/expiry individually
- ✅ WebSocket streaming with Greeks (IV, Delta, Gamma, Theta, Vega)
- ✅ Stored in `fo_option_strike_bars` table
- ⚠️ **No bulk subscription** for entire option chain

### What Happens When User Doesn't Need All Information?

**Current System**:
- ❌ **No granular control** - subscribing to an instrument gives you everything
- ❌ **No filtering** - all data published to Redis and stored in DB
- ❌ **No selective subscription** - can't subscribe to just Greeks without ticks

**Available Modes** (not granular enough):
```python
requested_mode = "FULL"   # OHLC + Volume + OI + Greeks
requested_mode = "QUOTE"  # LTP + Volume + OI (no Greeks)
requested_mode = "LTP"    # LTP only (minimal)
```

**Issue**: Even with "LTP" mode, backend stores all fields, just some are null.

---

## Part B: Backfill Mechanism

### Current Implementation: Scheduled Background Process

```
┌─────────────────────────────────────────────────────────────────┐
│                     BACKFILL WORKFLOW                           │
└─────────────────────────────────────────────────────────────────┘

EVERY 5 MINUTES (configurable):
1. Query database for last bar timestamp
   └─► SELECT MAX(bucket_time) FROM fo_option_strike_bars

2. Calculate gap
   └─► gap = now - last_bar_time
   └─► IF gap > 3 minutes: proceed to backfill

3. Fetch historical data from ticker service
   └─► GET /history?instrument_token=XXX&interval=minute&from_ts=...&to_ts=...

4. Store in database
   └─► INSERT INTO fo_option_strike_bars ... ON CONFLICT DO NOTHING

5. Sleep until next cycle
   └─► wait 5 minutes
```

### Backfill Configuration

**File**: `backend/app/config.py`

```python
backfill_enabled: bool = True
backfill_check_interval_seconds: int = 300      # Run every 5 minutes
backfill_gap_threshold_minutes: int = 3         # Only backfill if gap > 3 min
backfill_max_batch_minutes: int = 120           # Max 2 hours per batch
```

### What Data Gets Backfilled?

#### 1. Underlying (NIFTY50)
- OHLCV 1-minute bars
- Stored in: `nifty50_ohlc` table
- Fetches from: Ticker service `/history` endpoint

#### 2. Futures
- OHLCV + Open Interest + Greeks
- Stored in: `futures_bars` table
- Fetches for all active futures contracts

#### 3. Options (Most Complex)
- Greeks (IV, Delta, Gamma, Theta, Vega)
- Volume and OI per strike
- Stored in:
  - `fo_option_strike_bars` - Strike-level data
  - `fo_expiry_metrics` - Expiry-level metrics (PCR, max pain)
- Fetches for:
  - Multiple expiries (default: 3)
  - Multiple strikes per expiry (~21 strikes)
  - Both calls and puts

### Backfill Triggers

**When Backfill Runs**:
1. ✅ On startup (automatic)
2. ✅ Every 5 minutes (scheduled)
3. ✅ Manual script execution
4. ❌ **NOT triggered by subscriptions**
5. ❌ **NOT event-driven**

**Example Scenario**:

```
09:00 - User subscribes to NIFTY25NOV24500CE
09:00 - Real-time data starts flowing immediately
09:05 - Backfill runs (detects no historical data for this option)
09:05 - Backfill fetches last 2 hours (07:05-09:05)
09:10 - Historical data now available

Gap: 5-10 minutes between subscription and historical data availability
```

### Why Backfill Might Not Be Working Effectively

#### Issue #1: Not Subscription-Aware

```python
# Current: Backfill uses hardcoded metadata
async def _tick(self):
    metadata = await get_nifty_monitor_metadata()  # Fixed list
    # Might backfill instruments NOT subscribed
    # Might miss instruments THAT ARE subscribed
```

**Problem**: If metadata is stale, backfill processes wrong instruments.

#### Issue #2: Token Blacklisting

```python
# If ticker service returns error, token gets blacklisted
if not self._dm.is_token_supported(instrument_token):
    logger.debug("Skipping unsupported token %s", instrument_token)
    return []

# On failure:
self._recent_failures[instrument_token] = now
self._dm.mark_token_no_history(instrument_token, str(exc))
```

**Problem**:
- Expired options return 404
- Token gets permanently blacklisted for the session
- Backfill stops trying
- **30-minute cooldown period** before retry

#### Issue #3: Batch Size Limitations

```python
backfill_max_batch_minutes: int = 120  # 2 hours max
```

**Problem**:
- System down for 6 hours → Takes 3 cycles (15 minutes) to catch up
- During high-volatility, processing may lag
- Can't catch up fast enough during market hours

#### Issue #4: Full Reload on Subscription Change

**Current Behavior**:
```python
# Adding ONE subscription triggers full reload
await ticker_client.subscribe(instrument_token=12345)
# → Stops ALL streams
# → Reloads plan from database
# → Restarts ALL streams (~2-5 second disruption)
```

**Problem**: Frequent subscription changes cause data gaps due to stream disruptions.

---

## Architecture Diagrams

### Subscription Flow

```
┌──────────────┐
│   Frontend   │
└──────┬───────┘
       │
       │ "I need NIFTY25NOV24500CE data"
       ↓
┌──────────────────────────────────────────────────────────┐
│                     Backend                              │
│                                                          │
│  GET /fo/strike-distribution?symbol=NIFTY&expiry=...    │
│  ├─► Query: SELECT * FROM fo_option_strike_bars         │
│  └─► Returns: [] (empty if not subscribed)              │
└──────────────────────────────────────────────────────────┘
       ↑
       │ No data? Must manually subscribe!
       │
┌──────┴───────────────────────────────────────────────────┐
│              Ticker Service                              │
│                                                          │
│  POST /subscriptions                                     │
│  {                                                       │
│    "instrument_token": 13660418,                        │
│    "requested_mode": "FULL"                             │
│  }                                                       │
│  ├─► INSERT INTO instrument_subscriptions               │
│  ├─► Stop ALL streams                                   │
│  ├─► Reload plan                                        │
│  └─► Restart streams with new subscription              │
└──────────────────────────────────────────────────────────┘
       ↓
       │ WebSocket → Redis → Backend → Database
       ↓
┌──────────────────────────────────────────────────────────┐
│  Now data flows automatically                           │
│  - Real-time ticks via WebSocket                        │
│  - Historical data via backfill (every 5 minutes)       │
└──────────────────────────────────────────────────────────┘
```

### Data Flow: Real-Time vs Backfill

```
┌─────────────────────────────────────────────────────────┐
│              REAL-TIME DATA FLOW                        │
└─────────────────────────────────────────────────────────┘

Kite WebSocket
    ↓ (live ticks)
Ticker Service
    ↓ (publish to Redis)
FOStreamConsumer
    ↓ (aggregate to 1min bars)
TimescaleDB
    ↓
API Response to Frontend

Latency: ~1-5 seconds

┌─────────────────────────────────────────────────────────┐
│            BACKFILL DATA FLOW                           │
└─────────────────────────────────────────────────────────┘

BackfillManager (every 5 min)
    ↓ (detect gaps)
Query Last Bar Time
    ↓ (gap > 3 minutes?)
Ticker Service /history API
    ↓ (fetch historical bars)
TimescaleDB
    ↓
API Response to Frontend

Latency: 0-10 minutes (depends on when backfill cycle runs)
```

---

## Key Problems Identified

### Problem 1: No Smart/On-Demand Subscription ⚠️

**Current**:
```python
# User requests data
response = await api.get("/fo/strike-distribution?symbol=NIFTY&expiry=2025-11-28")
# Returns: {"series": []}  # Empty if not subscribed
```

**Expected**:
```python
# Auto-subscribe on demand
response = await api.get("/fo/strike-distribution?symbol=NIFTY&expiry=2025-11-28")
# 1. Detect missing data
# 2. Auto-subscribe via ticker service
# 3. Wait 5-10 seconds for data to flow
# 4. Return data
```

### Problem 2: Backfill Not Triggered by Subscriptions ⚠️

**Current**:
```
09:00 - Subscribe to option
09:00 - Real-time data starts
09:05 - Backfill runs (scheduled)
09:05 - Historical data available

Gap: 5 minutes
```

**Expected**:
```
09:00 - Subscribe to option
09:00 - Real-time data starts
09:00 - Trigger backfill immediately for this option
09:01 - Historical data available

Gap: 1 minute
```

### Problem 3: Full Reload on Every Subscription Change ⚠️

**Current**:
- Adding 1 subscription → Restart ALL streams
- Disrupts ALL existing subscriptions
- 2-5 second data gap

**Expected**:
- Incremental subscription updates
- Only add/remove specific instrument from WebSocket
- No disruption to other streams

### Problem 4: No Granular Data Control ⚠️

**Current**:
- Subscribe to option → Get EVERYTHING (ticks, OHLC, Greeks, volume, OI)
- Can't subscribe to just Greeks
- Can't filter out unwanted data

**Expected**:
- Subscribe with field selectors
- Example: `requested_fields=["greeks", "oi"]` (skip tick-by-tick)
- Reduces bandwidth and storage

---

## Recommendations

### Priority 1: Implement Smart On-Demand Subscription

```python
# backend/app/routes/fo.py

@router.get("/strike-distribution")
async def strike_distribution(...):
    # 1. Try to fetch data
    rows = await dm.fetch_latest_fo_strike_rows(...)

    # 2. If empty, auto-subscribe
    if not rows:
        missing_tokens = await find_missing_option_tokens(symbol, expiries)

        # Subscribe to missing instruments
        for token in missing_tokens:
            await ticker_client.subscribe(token, requested_mode="FULL")

        # Wait for data to start flowing
        await asyncio.sleep(10)

        # Retry fetch
        rows = await dm.fetch_latest_fo_strike_rows(...)

    return format_response(rows)
```

**Benefits**:
- ✅ No manual subscription needed
- ✅ Automatic data availability
- ✅ Better user experience

### Priority 2: Event-Driven Backfill

```python
# ticker_service/app/main.py

@app.post("/subscriptions")
async def create_subscription(...):
    # 1. Persist subscription
    await subscription_store.upsert(...)

    # 2. Reload streams
    await ticker_loop.reload_subscriptions()

    # 3. Trigger backfill immediately (NEW)
    await notify_backend_to_backfill(instrument_token)

    return response
```

```python
# backend/app/backfill.py

async def on_subscription_created(instrument_token: int):
    """Immediate backfill for newly subscribed instrument"""
    # Fetch last 2 hours of data immediately
    await self._backfill_instrument(instrument_token)
```

**Benefits**:
- ✅ Immediate historical data availability
- ✅ No 5-minute wait for scheduled backfill
- ✅ Better user experience

### Priority 3: Incremental Subscription Updates

```python
# ticker_service/app/generator.py

async def add_subscription_incremental(self, instrument: Instrument):
    """Add subscription without full reload"""
    # 1. Find account with capacity
    target_account = self._find_account_with_capacity()

    # 2. Add to WebSocket (without stopping)
    async with self._orchestrator.borrow(target_account) as client:
        await client.subscribe_tokens([instrument.instrument_token])

    # 3. Update assignments
    self._assignments[target_account].append(instrument)

    # No stream disruption!
```

**Benefits**:
- ✅ No disruption to existing streams
- ✅ Instant activation
- ✅ Scalable

### Priority 4: Subscription Cleanup (Auto-Unsubscribe)

```python
# Track usage per subscription
class SubscriptionRefCounter:
    async def increment(self, token: int, client_id: str):
        # Track which clients are using this subscription
        await redis.sadd(f"sub:{token}:clients", client_id)

    async def decrement(self, token: int, client_id: str):
        # Remove client
        await redis.srem(f"sub:{token}:clients", client_id)

        # If no clients, auto-unsubscribe
        count = await redis.scard(f"sub:{token}:clients")
        if count == 0:
            await ticker_client.unsubscribe(token)
```

**Benefits**:
- ✅ Automatic cleanup of unused subscriptions
- ✅ Reduces WebSocket load
- ✅ Stays within Kite Connect limits (1000 instruments/account)

---

## Code Examples

### Example 1: Manual Subscription (Current Method)

```python
from app.ticker_client import TickerServiceClient

ticker_client = TickerServiceClient(base_url="http://localhost:8080")

# Subscribe to NIFTY option
result = await ticker_client.subscribe(
    instrument_token=13660418,  # NIFTY25NOV24500CE
    requested_mode="FULL",
    account_id="primary"  # Optional
)

print(result)
# {
#     "instrument_token": 13660418,
#     "tradingsymbol": "NIFTY25NOV24500CE",
#     "status": "active",
#     "requested_mode": "FULL"
# }

# Wait 5-10 seconds for data to flow
await asyncio.sleep(10)

# Now query backend
response = await api.get("/fo/strike-distribution?symbol=NIFTY&expiry=2025-11-28")
# Should return data
```

### Example 2: Check Backfill Status

```python
from app.database import create_pool, DataManager
from datetime import datetime

async def check_backfill_gaps():
    pool = await create_pool()
    dm = DataManager(pool)

    # Check last option bar
    last_time = await dm.latest_option_bucket_time("NIFTY", "1min")

    if last_time:
        now = datetime.utcnow()
        gap_minutes = (now - last_time).total_seconds() / 60

        print(f"Last option bar: {last_time}")
        print(f"Current time: {now}")
        print(f"Gap: {gap_minutes:.1f} minutes")

        if gap_minutes > 5:
            print("⚠️ WARNING: Large gap detected!")
            print("Backfill should run in next scheduled cycle")
        else:
            print("✓ Data is recent")
    else:
        print("❌ No option data found")

    await pool.close()

# Run check
import asyncio
asyncio.run(check_backfill_gaps())
```

### Example 3: Force Immediate Backfill

```bash
# Manual backfill for specific time range
docker exec -it tv-backend-dev poetry run python \
  /app/backend/scripts/backfill_underlying.py \
  --from 2025-11-01T09:15:00+05:30 \
  --to   2025-11-01T15:30:00+05:30
```

---

## Summary Table

| Feature | Current Implementation | Recommended Implementation |
|---------|----------------------|---------------------------|
| **Subscription Model** | Pre-subscription (manual API calls) | Smart on-demand auto-subscribe |
| **Underlying** | Always polled (no subscription) | ✅ Keep as-is |
| **Futures** | Manual subscription per contract | Auto-subscribe on first request |
| **Options** | Manual subscription per strike | Auto-subscribe entire chain on demand |
| **Backfill Trigger** | Scheduled every 5 minutes | Event-driven + scheduled |
| **Subscription Updates** | Full reload (all streams restart) | Incremental updates |
| **Data Granularity** | All or nothing (FULL/QUOTE/LTP) | Field-level selectors |
| **Auto-Cleanup** | Manual unsubscribe | Ref counting + auto-unsubscribe |
| **Gap on New Subscription** | 5-10 minutes | 10-30 seconds |

---

## Next Steps

### Immediate Actions

1. **Verify Current State**:
   ```bash
   # Check active subscriptions
   curl http://localhost:8080/subscriptions | jq

   # Check backfill logs
   docker logs tv-backend-dev | grep -i backfill

   # Query last data timestamps
   psql -c "SELECT MAX(bucket_time) FROM fo_option_strike_bars"
   ```

2. **Test Manual Subscription Flow**:
   ```bash
   # Subscribe to one option
   curl -X POST http://localhost:8080/subscriptions \
     -H "Content-Type: application/json" \
     -d '{"instrument_token": 13660418, "requested_mode": "FULL"}'

   # Wait 10 seconds
   sleep 10

   # Check if data flowing
   curl "http://localhost:8081/fo/strike-distribution?symbol=NIFTY&expiry=2025-11-28"
   ```

3. **Monitor Backfill Effectiveness**:
   ```bash
   # Watch backfill cycles
   docker logs -f tv-backend-dev | grep "Backfilled"

   # Should see:
   # "Backfilled OHLC | symbol=NIFTY count=120 range=..."
   ```

### Short-Term Improvements (Next Sprint)

1. Implement smart on-demand subscription in backend routes
2. Add event-driven backfill trigger
3. Add subscription cleanup (auto-unsubscribe unused instruments)

### Long-Term Improvements (Next Month)

1. Implement incremental subscription updates
2. Add field-level data selectors
3. Add subscription analytics and monitoring
4. Implement subscription prioritization (ATM before OTM)

---

**Document Version**: 1.0
**Last Updated**: November 1, 2025
**Status**: Analysis Complete
