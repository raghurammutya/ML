# Real-Time Data Contract for MonitorPage

This document specifies the exact API endpoints and WebSocket message formats expected by the frontend to display real-time data.

---

## 1. Main Chart - Underlying Candles (Real-time)

### Issue
- LTP updates in header every second
- Chart does NOT show candle being built in real-time

### Expected WebSocket Message

**Connection**: WebSocket to `/ws/monitor/stream`

**Subscribe Message** (sent by frontend):
```json
{
  "action": "subscribe",
  "symbol": "NIFTY50",
  "timeframe": "5",
  "expiries": ["2025-11-04", "2025-11-11"],
  "session_id": "abc123"
}
```

**Expected Update Message** (from server):
```json
{
  "type": "monitor_snapshot",
  "timestamp": "2025-10-31T10:30:45Z",
  "symbol": "NIFTY50",
  "timeframe": "5",
  "ltp": 24350.75,
  "change_percent": 1.23,
  "candles": [
    {
      "time": "2025-10-31T10:25:00Z",
      "open": 24340.50,
      "high": 24355.00,
      "low": 24338.25,
      "close": 24350.75,
      "volume": 125000
    }
  ],
  "fo_buckets": []
}
```

**Or Delta Update Message**:
```json
{
  "type": "monitor_update",
  "timestamp": "2025-10-31T10:30:46Z",
  "symbol": "NIFTY50",
  "ltp": 24351.00,
  "change_percent": 1.24,
  "last_candle": {
    "time": "2025-10-31T10:25:00Z",
    "open": 24340.50,
    "high": 24355.00,
    "low": 24338.25,
    "close": 24351.00,
    "volume": 125200
  }
}
```

### Frontend Code Reference
**File**: `frontend/src/services/monitor.ts`

**Function**: `connectMonitorStream()`
```typescript
// Line ~50-100
export function connectMonitorStream(
  symbol: string,
  timeframe: string,
  expiries: string[],
  sessionId: string,
  onMessage: (data: MonitorStreamMessage) => void
): () => void
```

**What Frontend Does**:
1. Connects to WebSocket
2. Sends subscribe message
3. Expects `monitor_snapshot` or `monitor_update` messages
4. Calls `onMessage()` callback with parsed data

**MonitorPage Integration**:
**File**: `frontend/src/pages/MonitorPage.tsx`

**Lines**: ~446-505
```typescript
useEffect(() => {
  if (!sessionId || !metadata) return

  const disconnect = connectMonitorStream(
    underlying,
    timeframe,
    selectedExpiries,
    sessionId,
    (msg) => {
      if (msg.type === 'monitor_snapshot') {
        // Update chart with candles
        setCandles(msg.candles || [])
        setLtp(msg.ltp)
        setChangePercent(msg.change_percent)
      } else if (msg.type === 'monitor_update') {
        // Update last candle
        if (msg.last_candle) {
          setCandles(prev => {
            const updated = [...prev]
            const lastIdx = updated.findIndex(c => c.time === msg.last_candle!.time)
            if (lastIdx >= 0) {
              updated[lastIdx] = msg.last_candle!
            } else {
              updated.push(msg.last_candle!)
            }
            return updated
          })
        }
        if (msg.ltp) setLtp(msg.ltp)
        if (msg.change_percent) setChangePercent(msg.change_percent)
      }
    }
  )

  return disconnect
}, [sessionId, metadata, underlying, timeframe, selectedExpiries])
```

### Debug Steps
1. Open browser DevTools → Network → WS (WebSocket)
2. Find connection to `/ws/monitor/stream`
3. Check messages:
   - Is subscribe message being sent?
   - Are `monitor_snapshot` or `monitor_update` messages received?
   - What is the actual message format?

4. Check backend logs:
   ```bash
   docker compose logs backend | grep -i monitor
   ```

---

## 2. Horizontal Panels - Moneyness Series (IV, Delta, Gamma, etc.)

### Issue
- Horizontal panels load but show NO DATA (empty charts)

### Expected Data Source

**Option 1: HTTP Endpoint** (for historical backfill)

**Endpoint**: `GET /fo/moneyness-series`

**Query Params**:
```
symbol=NIFTY50
timeframe=5
indicator=iv
option_side=both
expiry=2025-11-04,2025-11-11
from=1730358000
to=1730379600
```

**Expected Response**:
```json
{
  "status": "ok",
  "symbol": "NIFTY50",
  "timeframe": "5min",
  "indicator": "iv",
  "series": [
    {
      "expiry": "2025-11-04",
      "bucket": "ATM",
      "points": [
        {"time": 1730358000, "value": 0.185},
        {"time": 1730358300, "value": 0.187},
        {"time": 1730358600, "value": 0.189}
      ]
    },
    {
      "expiry": "2025-11-11",
      "bucket": "ATM",
      "points": [
        {"time": 1730358000, "value": 0.192},
        {"time": 1730358300, "value": 0.194}
      ]
    }
  ]
}
```

**IMPORTANT**: The `series` array MUST NOT be empty. Each series MUST have `points` array with data.

**Option 2: WebSocket Real-time Updates**

**Message Format** (included in `monitor_snapshot`):
```json
{
  "type": "monitor_snapshot",
  "timestamp": "2025-10-31T10:30:45Z",
  "symbol": "NIFTY50",
  "ltp": 24350.75,
  "candles": [...],
  "fo_buckets": [
    {
      "timestamp": "2025-10-31T10:30:00Z",
      "expiry": "2025-11-04",
      "strikes": [
        {
          "strike": 24300,
          "bucket": "ATM",
          "call": {
            "iv": 0.189,
            "delta": 0.52,
            "gamma": 0.003,
            "theta": -15.5,
            "vega": 12.3,
            "oi": 125000,
            "volume": 5400
          },
          "put": {
            "iv": 0.191,
            "delta": -0.48,
            "gamma": 0.003,
            "theta": -14.8,
            "vega": 12.1,
            "oi": 138000,
            "volume": 6200
          }
        }
      ]
    }
  ]
}
```

### Frontend Code Reference

**File**: `frontend/src/services/fo.ts`

**Function**: `fetchFoMoneynessSeries()`
```typescript
// Line ~80-120
export async function fetchFoMoneynessSeries(params: {
  symbol: string
  timeframe: string
  indicator: string
  optionSide?: string
  expiry?: string[]
  from?: number
  to?: number
  limit?: number
}): Promise<{ series: FoMoneynessSeries[] }>
```

**MonitorPage Integration**:
**File**: `frontend/src/pages/MonitorPage.tsx`

**Lines**: ~290-330
```typescript
useEffect(() => {
  if (!metadata) return

  const load = async () => {
    setLoadingHorizontalData(true)
    try {
      const data = await fetchFoMoneynessSeries({
        symbol: underlying,
        timeframe,
        indicator: panel.indicator,
        optionSide: panel.option_side,
        expiry: selectedExpiries,
        from: fromTs,
        to: toTs,
        limit: 500,
      })

      // data.series MUST have elements with points
      setSeriesData(data.series)
    } catch (error) {
      console.error('Failed to fetch moneyness series:', error)
    } finally {
      setLoadingHorizontalData(false)
    }
  }

  load()
}, [metadata, underlying, timeframe, panel, selectedExpiries])
```

### Current Issue (Documented in Sprint 2)

**File**: `backend/app/routes/fo.py`

**Line**: ~270

The endpoint currently returns:
```python
return {
    "status": "ok",
    "symbol": symbol_db,
    "timeframe": normalized_tf,
    "indicator": indicator,
    "series": []  # EMPTY - this is the bug
}
```

**Root Cause**:
- DataManager missing methods: `fetch_fo_strike_rows()`, `fetch_fo_expiry_metrics()`
- Database table `fo_option_strike_bars` missing OI columns: `call_oi_sum`, `put_oi_sum`

### What Backend Needs to Implement

**Required Method in DataManager**:
```python
async def fetch_fo_strike_rows(
    self,
    symbol: str,
    timeframe: str,
    expiries: List[str],
    from_time: datetime,
    to_time: datetime,
    limit: Optional[int] = None
) -> List[asyncpg.Record]:
    """
    Fetch aggregated strike data for horizontal panels.

    Returns rows with:
    - bucket_time (datetime)
    - strike (int)
    - expiry (date)
    - underlying_close (float)
    - call_iv_avg, put_iv_avg (float)
    - call_delta_avg, put_delta_avg (float)
    - call_gamma_avg, put_gamma_avg (float)
    - call_theta_avg, put_theta_avg (float)
    - call_vega_avg, put_vega_avg (float)
    - call_volume, put_volume (int)
    """
    query = """
        SELECT
            bucket_time,
            strike,
            expiry,
            underlying_close,
            call_iv_avg,
            put_iv_avg,
            call_delta_avg,
            put_delta_avg,
            call_gamma_avg,
            put_gamma_avg,
            call_theta_avg,
            put_theta_avg,
            call_vega_avg,
            put_vega_avg,
            call_volume,
            put_volume
        FROM fo_option_strike_bars
        WHERE symbol = $1
            AND timeframe = $2
            AND expiry = ANY($3)
            AND bucket_time >= $4
            AND bucket_time <= $5
        ORDER BY bucket_time, strike
        LIMIT $6
    """

    async with self.pool.acquire() as conn:
        rows = await conn.fetch(
            query,
            symbol,
            timeframe,
            expiries,
            from_time,
            to_time,
            limit or 10000
        )

    return rows
```

### Debug Steps

1. **Check HTTP endpoint**:
   ```bash
   curl "http://localhost:8081/fo/moneyness-series?symbol=NIFTY50&timeframe=5&indicator=iv&option_side=both&expiry=2025-11-04&from=1730358000&to=1730379600"
   ```

   Expected: `series` array with data
   Current: `series: []` (empty)

2. **Check database has data**:
   ```sql
   SELECT COUNT(*) FROM fo_option_strike_bars
   WHERE symbol = 'NIFTY50'
     AND timeframe = '5min'
     AND bucket_time >= NOW() - INTERVAL '6 hours';
   ```

   Should return > 0

3. **Check table structure**:
   ```sql
   \d fo_option_strike_bars
   ```

   Should have columns:
   - call_iv_avg, put_iv_avg
   - call_delta_avg, put_delta_avg
   - call_gamma_avg, put_gamma_avg
   - call_theta_avg, put_theta_avg
   - call_vega_avg, put_vega_avg

---

## 3. Vertical Panels - Strike Distribution (Calls/Puts by Strike)

### Issue
- Vertical panels show headers but NO DATA

### Expected Data Source

**HTTP Endpoint**: `GET /fo/strike-distribution`

**Query Params**:
```
symbol=NIFTY50
timeframe=5
expiry=2025-11-04
timestamp=1730379600
```

**Expected Response**:
```json
{
  "status": "ok",
  "symbol": "NIFTY50",
  "timeframe": "5min",
  "expiry": "2025-11-04",
  "timestamp": "2025-10-31T10:30:00Z",
  "underlying_ltp": 24350.75,
  "strikes": [
    {
      "strike": 24200,
      "call": {
        "iv": 0.172,
        "delta": 0.78,
        "gamma": 0.002,
        "theta": -12.5,
        "vega": 10.2,
        "premium": 165.50,
        "oi": 95000,
        "volume": 3200
      },
      "put": {
        "iv": 0.205,
        "delta": -0.22,
        "gamma": 0.002,
        "theta": -8.3,
        "vega": 9.8,
        "premium": 15.75,
        "oi": 45000,
        "volume": 1800
      }
    },
    {
      "strike": 24250,
      "call": {...},
      "put": {...}
    },
    {
      "strike": 24300,
      "call": {...},
      "put": {...}
    }
  ]
}
```

### Frontend Code Reference

**File**: `frontend/src/services/fo.ts`

**Function**: `fetchFoStrikeDistribution()`
```typescript
// Line ~140-170
export async function fetchFoStrikeDistribution(params: {
  symbol: string
  timeframe: string
  expiry: string
  timestamp?: number
}): Promise<FoStrikeDistributionResponse>
```

**MonitorPage Integration**:
**File**: `frontend/src/pages/MonitorPage.tsx`

**Lines**: ~360-400
```typescript
useEffect(() => {
  if (!metadata || selectedExpiries.length === 0) return

  const load = async () => {
    setLoadingVerticalData(true)
    try {
      const data = await fetchFoStrikeDistribution({
        symbol: underlying,
        timeframe,
        expiry: selectedExpiries[0], // First expiry
        timestamp: Math.floor(Date.now() / 1000)
      })

      // data.strikes MUST have elements
      setStrikeData(data.strikes)
    } catch (error) {
      console.error('Failed to fetch strike distribution:', error)
    } finally {
      setLoadingVerticalData(false)
    }
  }

  load()
}, [metadata, underlying, timeframe, selectedExpiries])
```

### Backend Implementation Needed

**File**: `backend/app/routes/fo.py`

**Endpoint**: `GET /fo/strike-distribution`

```python
@router.get("/strike-distribution")
async def strike_distribution(
    symbol: str = Query(settings.monitor_default_symbol),
    timeframe: str = Query("5"),
    expiry: str = Query(...),
    timestamp: Optional[int] = Query(None),
    dm: DataManager = Depends(get_data_manager)
):
    """
    Get strike-by-strike metrics for a specific expiry at a timestamp.
    Used by vertical panels.
    """
    normalized_tf = _normalize_timeframe(timeframe)
    symbol_db = _normalize_symbol(symbol)

    if timestamp:
        query_time = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    else:
        query_time = datetime.now(timezone.utc)

    # Get latest bucket before or at query_time
    query = """
        SELECT
            strike,
            underlying_close,
            call_iv_avg,
            call_delta_avg,
            call_gamma_avg,
            call_theta_avg,
            call_vega_avg,
            put_iv_avg,
            put_delta_avg,
            put_gamma_avg,
            put_theta_avg,
            put_vega_avg
        FROM fo_option_strike_bars
        WHERE symbol = $1
            AND timeframe = $2
            AND expiry = $3
            AND bucket_time <= $4
        ORDER BY bucket_time DESC, strike
        LIMIT 50
    """

    async with dm.pool.acquire() as conn:
        rows = await conn.fetch(
            query,
            symbol_db,
            normalized_tf,
            expiry,
            query_time
        )

    if not rows:
        return {
            "status": "ok",
            "symbol": symbol_db,
            "timeframe": normalized_tf,
            "expiry": expiry,
            "timestamp": query_time.isoformat(),
            "underlying_ltp": None,
            "strikes": []
        }

    strikes = []
    underlying_ltp = rows[0]['underlying_close'] if rows else None

    for row in rows:
        strikes.append({
            "strike": int(row['strike']),
            "call": {
                "iv": float(row['call_iv_avg']) if row['call_iv_avg'] else None,
                "delta": float(row['call_delta_avg']) if row['call_delta_avg'] else None,
                "gamma": float(row['call_gamma_avg']) if row['call_gamma_avg'] else None,
                "theta": float(row['call_theta_avg']) if row['call_theta_avg'] else None,
                "vega": float(row['call_vega_avg']) if row['call_vega_avg'] else None,
                "premium": None,  # Not available in aggregated table
                "oi": None,
                "volume": None
            },
            "put": {
                "iv": float(row['put_iv_avg']) if row['put_iv_avg'] else None,
                "delta": float(row['put_delta_avg']) if row['put_delta_avg'] else None,
                "gamma": float(row['put_gamma_avg']) if row['put_gamma_avg'] else None,
                "theta": float(row['put_theta_avg']) if row['put_theta_avg'] else None,
                "vega": float(row['put_vega_avg']) if row['put_vega_avg'] else None,
                "premium": None,
                "oi": None,
                "volume": None
            }
        })

    return {
        "status": "ok",
        "symbol": symbol_db,
        "timeframe": normalized_tf,
        "expiry": expiry,
        "timestamp": query_time.isoformat(),
        "underlying_ltp": float(underlying_ltp) if underlying_ltp else None,
        "strikes": strikes
    }
```

### Debug Steps

1. **Check endpoint exists**:
   ```bash
   curl "http://localhost:8081/fo/strike-distribution?symbol=NIFTY50&timeframe=5&expiry=2025-11-04"
   ```

   Expected: `strikes` array with data
   Current: Likely 404 or `strikes: []`

2. **Check database**:
   ```sql
   SELECT strike, call_iv_avg, put_iv_avg
   FROM fo_option_strike_bars
   WHERE symbol = 'NIFTY50'
     AND expiry = '2025-11-04'
     AND bucket_time <= NOW()
   ORDER BY bucket_time DESC, strike
   LIMIT 10;
   ```

---

## 4. Real-time Updates Summary

### Data Flow

```
Backend → WebSocket (/ws/monitor/stream) → Frontend MonitorPage
                                          ↓
                            ┌─────────────┴─────────────┐
                            ↓                           ↓
                    UnderlyingChart              HorizontalPanel
                    (candle updates)           (moneyness series)
                                                       ↓
                                              VerticalPanel
                                             (strike metrics)
```

### Message Frequency
- **1 second cadence** during market hours
- Each message should contain:
  - Updated LTP
  - Last candle update (OHLCV)
  - Latest fo_buckets (optional, for panels)

### Complete WebSocket Message Example

```json
{
  "type": "monitor_snapshot",
  "timestamp": "2025-10-31T10:30:45.123Z",
  "symbol": "NIFTY50",
  "timeframe": "5",
  "ltp": 24350.75,
  "change_percent": 1.23,
  "candles": [
    {
      "time": "2025-10-31T10:25:00Z",
      "open": 24340.50,
      "high": 24355.00,
      "low": 24338.25,
      "close": 24350.75,
      "volume": 125000
    },
    {
      "time": "2025-10-31T10:20:00Z",
      "open": 24335.00,
      "high": 24342.50,
      "low": 24330.00,
      "close": 24340.50,
      "volume": 118000
    }
  ],
  "fo_buckets": [
    {
      "timestamp": "2025-10-31T10:25:00Z",
      "expiry": "2025-11-04",
      "strikes": [
        {
          "strike": 24300,
          "bucket": "ATM",
          "call": {
            "iv": 0.189,
            "delta": 0.52,
            "gamma": 0.003,
            "theta": -15.5,
            "vega": 12.3,
            "oi": 125000,
            "volume": 5400
          },
          "put": {
            "iv": 0.191,
            "delta": -0.48,
            "gamma": 0.003,
            "theta": -14.8,
            "vega": 12.1,
            "oi": 138000,
            "volume": 6200
          }
        }
      ]
    }
  ]
}
```

---

## 5. Quick Debug Checklist

### Frontend Console Checks

Open browser console and run:

```javascript
// Check if WebSocket is connected
console.log('WS Ready:', window.location)

// Check what data MonitorPage has
// (Set breakpoint in MonitorPage.tsx useEffect where connectMonitorStream is called)
```

### Backend Checks

```bash
# Check if WebSocket handler exists
docker compose logs backend | grep "ws/monitor/stream"

# Check if fo endpoints are registered
curl http://localhost:8081/docs
# Look for /fo/moneyness-series and /fo/strike-distribution

# Check database connectivity
docker compose exec backend python3 -c "
import asyncio
from app.database import create_pool

async def test():
    pool = await create_pool()
    async with pool.acquire() as conn:
        result = await conn.fetchval('SELECT COUNT(*) FROM fo_option_strike_bars')
        print(f'Rows in fo_option_strike_bars: {result}')

asyncio.run(test())
"
```

### Database Checks

```sql
-- Check if underlying data exists
SELECT COUNT(*) FROM underlying_bars
WHERE symbol = 'NIFTY50'
  AND bucket_time >= NOW() - INTERVAL '1 hour';

-- Check if FO data exists
SELECT COUNT(*) FROM fo_option_strike_bars
WHERE symbol = 'NIFTY50'
  AND bucket_time >= NOW() - INTERVAL '1 hour';

-- Check latest data
SELECT bucket_time, strike, call_iv_avg, put_iv_avg
FROM fo_option_strike_bars
WHERE symbol = 'NIFTY50'
ORDER BY bucket_time DESC
LIMIT 10;
```

---

## 6. Summary of Missing Implementations

### Confirmed Missing (as of Sprint 2):

1. **`/fo/moneyness-series` endpoint**:
   - Returns empty `series: []`
   - Needs `DataManager.fetch_fo_strike_rows()` method
   - Needs proper aggregation logic in `backend/app/routes/fo.py:270`

2. **`/fo/strike-distribution` endpoint**:
   - May not exist at all (needs verification)
   - If exists, likely returns empty data
   - Needs implementation as shown in Section 3

3. **WebSocket real-time updates**:
   - LTP updates work (header shows real-time value)
   - Candle updates may not be sent (chart doesn't update)
   - `fo_buckets` in WebSocket messages may be empty/missing

### What Frontend Expects (Already Implemented):

✅ TypeScript types for all data structures
✅ Service functions to call APIs
✅ WebSocket connection handling
✅ Chart rendering components
✅ Panel rendering components
✅ Error handling and loading states

### What Backend Must Provide:

❌ `/fo/moneyness-series` with non-empty series data
❌ `/fo/strike-distribution` with strike metrics
❌ WebSocket messages with `last_candle` updates every second
❌ WebSocket messages with `fo_buckets` (optional but recommended)

---

## Contact Points for Integration

If you implement the above endpoints and WebSocket messages, the frontend will automatically display the data. No frontend changes needed.

**Key files to modify**:
- `backend/app/routes/fo.py` - Fix moneyness-series, add strike-distribution
- `backend/app/database.py` - Add fetch_fo_strike_rows() method
- `backend/app/nifty_monitor_service.py` - Ensure WebSocket sends last_candle updates
