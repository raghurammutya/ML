# Data Gap Analysis: Frontend vs Backend

**Date:** October 31, 2025
**Analysis Type:** Realistic Assessment from Frontend Perspective

---

## Executive Summary

The frontend is **not receiving usable data** for charts and panels despite backend endpoints being functional. The primary issues are:

1. **Symbol Mismatch**: Frontend requests "NIFTY50", backend database has "NIFTY"
2. **Stale Historical Data**: Database has only 3 records from October 26 (5 days old)
3. **No Real-time Data Flow**: Monitor snapshot returns empty data
4. **Nginx Configuration Error**: Session creation still timing out (504)
5. **Incomplete Data Pipeline**: Ticker service → Backend → Database → Frontend chain is broken

---

## 1. Main Chart (UnderlyingChart)

### Frontend Expects
- **Endpoint**: `/tradingview-api/history?symbol=NIFTY50&resolution=5&from=X&to=Y`
- **Data Structure**:
```typescript
{
  s: "ok",
  t: [timestamps],  // Unix timestamps
  c: [close prices],
  o: [open prices],
  h: [high prices],
  l: [low prices],
  v: [volumes]
}
```

### Backend Provides
- **Database Table**: `nifty50_ohlc` (15,060 records) ✅
- **Sample Response**:
```json
{
  "s": "ok",
  "t": [...],  // Has 36077 bytes of data
  "c": [...],
  "o": [...],
  "h": [...],
  "l": [...],
  "v": [...]
}
```

### Status: **✅ WORKING**
The main chart should be rendering. If not visible, check:
- Chart container CSS visibility
- TradingView Lightweight Charts initialization errors
- Browser console for JavaScript errors

---

## 2. Horizontal Panels (Moneyness-based: ATM/OTM/ITM)

### Frontend Expects
- **Endpoint**: `/tradingview-api/fo/moneyness-series?symbol=NIFTY50&timeframe=5&indicator=oi&option_side=both&expiry[]=2025-11-04&expiry[]=2025-11-11`
- **Data Structure**:
```typescript
{
  status: "ok",
  symbol: "NIFTY50",
  timeframe: "5min",
  indicator: "oi",
  series: [
    {
      time: 1730000000,  // Unix timestamp
      atm: 12345,
      otm_1: 10000,
      otm_2: 8000,
      itm_1: 9000,
      itm_2: 7000
    },
    // ... more data points
  ]
}
```

### Backend Provides
```json
{
  "status": "ok",
  "symbol": "NIFTY50",
  "timeframe": "5min",
  "indicator": "oi",
  "series": []  // ❌ EMPTY
}
```

### Root Cause Analysis
1. **Database Has Wrong Symbol**:
   - Frontend requests: `NIFTY50`
   - Database contains: `NIFTY`
   - Backend query fails to find matching records

2. **Stale Historical Data**:
   ```sql
   SELECT symbol, timeframe, expiry, bucket_time, pcr, max_pain_strike
   FROM fo_expiry_metrics
   ORDER BY bucket_time DESC LIMIT 5;

   symbol | timeframe |   expiry   |      bucket_time       | pcr  | max_pain_strike
   --------+-----------+------------+------------------------+------+-----------------
   NIFTY  | 1min      | 2025-11-07 | 2025-10-26 06:38:00+00 | 0.96 |           25000
   NIFTY  | 1min      | 2025-11-14 | 2025-10-26 06:38:00+00 | 0.96 |           25000
   NIFTY  | 1min      | 2025-11-21 | 2025-10-26 06:38:00+00 | 0.96 |           25000
   ```
   - Only **3 records total** in `fo_expiry_metrics`
   - Last updated: **October 26, 2025** (5 days ago)
   - Missing **5-minute and 15-minute** timeframes

3. **Incomplete Moneyness Aggregation**:
   - Table schema has: `total_call_volume`, `total_put_volume`, `pcr`, `max_pain_strike`
   - Frontend needs: `atm`, `otm_1`, `otm_2`, `itm_1`, `itm_2` (moneyness buckets)
   - **Schema mismatch**: Backend is not calculating moneyness-based aggregations

### Status: **❌ NOT WORKING**
**Impact**: All horizontal panels show NO DATA:
- IV (ATM/OTM/ITM) - Empty
- Delta (Calls/Puts) - Empty
- OI (Calls/Puts) - Empty
- PCR by Moneyness - Empty (or showing incorrect data from wrong calculations)
- Max Pain - Returns 400 error

---

## 3. Vertical Panels (Strike-based Distribution)

### Frontend Expects
- **Endpoint**: `/tradingview-api/fo/strike-distribution?symbol=NIFTY50&timeframe=5&indicator=pcr&expiry[]=2025-11-04&expiry[]=2025-11-11`
- **Data Structure**:
```typescript
{
  status: "ok",
  symbol: "NIFTY50",
  timeframe: "5min",
  indicator: "pcr",
  data: [
    {
      time: 1730000000,
      strike: 24500,
      call: 0.85,
      put: 0.92,
      combined: 1.08
    },
    // ... more strikes
  ]
}
```

### Backend Provides
```json
{
  "status": "ok",
  "symbol": "NIFTY50",
  "timeframe": "5min",
  "indicator": "pcr",
  "data": []  // ❌ EMPTY
}
```

### Root Cause Analysis
1. **Database Query Returns Nothing**:
   - Table: `fo_option_strike_bars` (only 15 records)
   - Symbol mismatch: `NIFTY` vs `NIFTY50`
   - Stale data from October 26

2. **Strike Distribution Logic**:
   ```sql
   SELECT symbol, expiry, strike, bucket_time, call_iv_avg, put_iv_avg
   FROM fo_option_strike_bars
   WHERE symbol = 'NIFTY50'  -- ❌ No matches
   ORDER BY bucket_time DESC LIMIT 5;
   ```

### Status: **❌ NOT WORKING**
**Impact**: All vertical panels show NO DATA:
- IV by Strike - Empty
- Delta by Strike - Empty
- PCR by Strike - Empty
- OI by Strike - Empty

---

## 4. Real-time Data (WebSocket Streams)

### Frontend Expects
- **Monitor Stream**: `/tradingview-api/monitor/stream` → Underlying price + Greeks updates
- **FO Stream**: `/tradingview-api/fo/stream` → Aggregated options metrics
- **Labels Stream**: `/tradingview-api/labels/stream` → ML labels/signals

### Backend Provides
- **Monitor Snapshot**: `/tradingview-api/monitor/snapshot`
  ```json
  {
    "status": "ok",
    "data_count": 0,  // ❌ EMPTY
    "sample_entry": null
  }
  ```

### Real-time Data Flow Assessment

#### Ticker Service → Backend
```json
// Ticker service has subscriptions
[
  {
    "instrument_token": 12248578,
    "tradingsymbol": "NIFTY25N0427500CE",
    "status": "active",  // ✅ 1 active subscription
    "requested_mode": "FULL",
    "account_id": "primary"
  }
]
```

#### Backend → Database
- **Redis Channels**: `ticker:nifty:options`, `ticker:nifty:underlying`
- **Problem**: Data not flowing from Redis → TimescaleDB
- **Evidence**: Empty monitor snapshot, no recent database records

### Status: **❌ NOT WORKING**
**Impact**:
- Charts don't update in real-time
- No live Greeks updates
- Session creation fails with 504 timeout
- WebSocket connections open but receive no data

---

## 5. Session Creation (Critical for Real-time)

### Frontend Expects
- **Endpoint**: `POST /tradingview-api/monitor/session`
- **Payload**:
```json
{
  "symbol": "NIFTY50",
  "tokens": [256265, 260105, ...],  // ~100-200 tokens
  "requested_mode": "FULL",
  "account_id": "primary"
}
```
- **Timeout**: 2 minutes (120,000ms) set in `api.ts`

### Backend Status
- **Ticker Service Timeout**: 30 seconds ✅ (increased from 10s)
- **Nginx Timeout**: **60 seconds** ❌ (should be 300s)
- **Actual Behavior**:
  ```
  2025/10/31 11:34:14 [error] upstream timed out (110: Operation timed out)
  while reading response header from upstream
  request: "POST /tradingview-api/monitor/session HTTP/1.1"
  Status: 504
  ```

### Root Cause
**Nginx configuration error**:
- Configured timeout for `/tradingview-api/monitor/sessions` (plural)
- Actual endpoint is `/tradingview-api/monitor/session` (singular)
- Falls back to default 60-second timeout instead of 300 seconds

### Status: **❌ BLOCKING ISSUE**
**Impact**: Users see "Session: timeout" error and cannot use the monitor page

---

## 6. Trading Accounts

### Frontend Expects
- **Endpoint**: `/tradingview-api/accounts`
- **Data Structure**:
```typescript
{
  status: "success",
  count: 1,
  accounts: [
    {
      account_id: "XJ4540",
      account_name: "Raghuram (Primary)",
      total_pnl: 0.0,
      total_positions: 0
    }
  ]
}
```

### Backend Provides
```json
{
  "status": "success",
  "count": 1,
  "accounts": [
    {
      "account_id": "XJ4540",
      "account_name": "Raghuram (Primary)",
      "broker": "zerodha",
      "is_active": true,
      "total_pnl": 0.0,
      "total_positions": 0
    }
  ]
}
```

### Status: **✅ WORKING**
But accounts won't appear in toolbar because `total_positions: 0` (no exposure in current underlying)

---

## Summary of Critical Issues

### 🔴 **P0 - Blocking Issues**
1. **Session Creation 504 Timeout**
   - Fix: Correct nginx path from `/monitor/sessions` to `/monitor/session`
   - Impact: Users cannot start monitor sessions

2. **Symbol Mismatch: NIFTY vs NIFTY50**
   - Fix: Update database records OR map frontend "NIFTY50" → backend "NIFTY"
   - Impact: All panels show empty data

3. **No Real-time Data Flow**
   - Fix: Debug Redis → Backend → Database pipeline
   - Impact: No live updates, charts frozen

### 🟡 **P1 - Data Quality Issues**
4. **Stale Historical Data (5 days old)**
   - Fix: Run backfill or restart data ingestion
   - Impact: Panels show outdated information if they render at all

5. **Incomplete Database Schema**
   - Fix: Add moneyness aggregation columns to `fo_expiry_metrics`
   - Impact: Moneyness-based panels cannot render correctly

6. **Missing Timeframes**
   - Database has: `1min`
   - Frontend needs: `5min`, `15min`
   - Fix: Add aggregation views or continuous aggregates

### 🟢 **P2 - Enhancement Issues**
7. **Max Pain Endpoint Returns 400**
   - Likely missing `option_side` parameter or incorrect query
   - Low priority as other panels are broken

---

## Immediate Action Items

### 1. Fix Session Creation (5 minutes)
```bash
# Edit frontend/nginx.conf
- location /tradingview-api/monitor/sessions {
+ location /tradingview-api/monitor/session {

# Rebuild and restart
docker-compose build frontend
docker-compose up -d frontend
```

### 2. Fix Symbol Mismatch (Choose ONE)

**Option A: Update Database** (Recommended)
```sql
UPDATE fo_expiry_metrics SET symbol = 'NIFTY50' WHERE symbol = 'NIFTY';
UPDATE fo_option_strike_bars SET symbol = 'NIFTY50' WHERE symbol = 'NIFTY';
```

**Option B: Add Symbol Mapping in Backend**
```python
# In fo.py routes
def normalize_symbol(symbol: str) -> str:
    if symbol == "NIFTY50":
        return "NIFTY"
    return symbol
```

### 3. Restart Data Pipeline
```bash
# Check if FO stream consumer is running
docker logs tv-backend | grep "FO stream"

# Check Redis for recent data
docker exec tv-redis redis-cli SUBSCRIBE ticker:nifty:options
```

### 4. Verify Data Flow
```bash
# Check if new data is being inserted
docker exec tv-postgres-dev bash -c "PGPASSWORD=stocksblitz123 psql -h localhost -U stocksblitz -d stocksblitz_unified_dev -c \"SELECT MAX(bucket_time) FROM fo_expiry_metrics;\""
```

---

## Expected Results After Fixes

✅ Session creation completes in 30-120 seconds
✅ Status shows "Session: Active (N tokens)"
✅ Main chart displays NIFTY50 candlesticks
✅ Horizontal panels show IV/Delta/OI trends by moneyness
✅ Vertical panels show strike distribution
✅ PCR chart displays correct ratios
✅ Real-time updates flow every 1-5 seconds
✅ Trading accounts appear if they have positions

