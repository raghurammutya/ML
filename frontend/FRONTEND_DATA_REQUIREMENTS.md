# Frontend Data Requirements Specification

**Date:** 2025-11-02
**Status:** Production Ready (Backend Phase 1A Complete)
**Frontend Version:** Monitor Dashboard v2.0

---

## Executive Summary

The frontend Nifty Options Monitor requires real-time and historical options data across multiple dimensions. This document specifies exact data requirements for optimal user experience.

### Current Performance (Post Phase 1A Migration)

| Metric | Performance |
|--------|-------------|
| **API Response Time** | 234ms (was 139s) |
| **Database Query** | 13ms (was 6s with JOINs) |
| **Improvement** | **594x faster** |
| **Status** | ✅ Production Ready |

---

## 1. REAL-TIME MODE - Data Requirements

### 1.1 Vertical Panels (Strike Distribution View)

**Purpose:** Display IV/Greeks/OI/Volume across strike prices for selected expiries

**Current Endpoint:** `GET /fo/strike-distribution`

**Update Frequency:** Every 5 seconds (via polling or WebSocket)

**Request Parameters:**
```json
{
  "symbol": "NIFTY",           // Normalized from NIFTY50
  "timeframe": "5min",         // 1min | 5min | 15min
  "indicator": "iv",           // iv | delta | gamma | theta | vega | volume | oi | pcr
  "expiry": [                  // Array of selected expiries (user selects 1-5)
    "2025-11-04",
    "2025-11-11",
    "2025-11-18"
  ],
  "strike_range": 10,          // ATM ± 10 strikes (21 total strikes)
  "bucket_time": null          // null = latest, or specific timestamp for replay
}
```

**Expected Response:**
```json
{
  "status": "ok",
  "symbol": "NIFTY50",
  "timeframe": "5min",
  "indicator": "iv",
  "series": [
    {
      "expiry": "2025-11-04",
      "bucket_time": 1762052100,
      "points": [
        {
          "strike": 24700.0,
          "value": 0.2033,              // Combined value (for PCR, volume)
          "call": 0.1848,               // CALL-side value (required!)
          "put": 0.2218,                // PUT-side value (required!)
          "call_oi": 14.0,
          "put_oi": 13.0,
          "bucket_time": 1762052100,
          "underlying": 25184.94
        },
        // ... 20 more strikes (ATM ± 10)
      ]
    },
    {
      "expiry": "2025-11-11",
      "bucket_time": 1762052100,
      "points": [...]
    },
    {
      "expiry": "2025-11-18",
      "bucket_time": 1762052100,
      "points": [...]
    }
  ]
}
```

**Data Volume:**
- 3 expiries × 21 strikes × 8 fields = 504 data points per panel
- 8 panels (IV, Delta, Gamma, Theta, Vega, Volume, OI, PCR)
- **Total: ~4,000 data points** per update
- **Update: Every 5 seconds**

**Critical Fields:**
- ✅ `call` and `put` MUST be separate (frontend splits into CALL/PUT series)
- ✅ `underlying` needed for ATM calculation
- ✅ `bucket_time` needed for time synchronization
- ✅ `call_oi` and `put_oi` for reference (displayed in tooltip)

**Frontend Rendering:**
- Each expiry rendered as separate line (unique color)
- CALL side: Solid line
- PUT side: Dashed line
- Y-axis: Strike price (aligned across all panels)
- X-axis: Indicator value

---

### 1.2 Horizontal Panels (Moneyness Ladder View)

**Purpose:** Display IV/Greeks aggregated by moneyness buckets (ATM, ITM1-10, OTM1-10)

**Current Endpoint:** `GET /fo/moneyness-series`

**Update Frequency:** Every 5 seconds

**Request Parameters:**
```json
{
  "symbol": "NIFTY",
  "timeframe": "5min",
  "indicator": "iv",
  "option_side": "call",       // call | put | null (both)
  "expiry": ["2025-11-04", "2025-11-11", "2025-11-18"],
  "from": 1762000000,          // Start timestamp (for range queries)
  "to": 1762052100             // End timestamp
}
```

**Expected Response:**
```json
{
  "status": "ok",
  "symbol": "NIFTY50",
  "timeframe": "5min",
  "indicator": "iv",
  "series": [
    {
      "expiry": "2025-11-04",
      "bars": [
        {
          "bucket_time": 1762052100,
          "underlying": 25184.94,
          "moneyness": [
            {
              "bucket": "ITM10",     // Deep ITM
              "value": 0.085,
              "strike_count": 2,     // Number of strikes in bucket
              "total_oi": 2500
            },
            // ... ITM9 through ITM1
            {
              "bucket": "ATM",
              "value": 0.185,
              "strike_count": 3,
              "total_oi": 45000
            },
            // ... OTM1 through OTM10
          ]
        }
      ]
    }
  ]
}
```

**Data Volume:**
- 3 expiries × 21 moneyness buckets × 4 fields = 252 data points per panel
- 7 panels (IV, Delta, Gamma, Theta, Vega, Volume, OI)
- **Total: ~1,800 data points** per update
- **Update: Every 5 seconds**

---

### 1.3 Main Chart (Underlying Price)

**Purpose:** Display NIFTY50 spot/futures price with technical indicators

**Current Endpoint:** `/history` (TradingView UDF protocol)

**Update Frequency:** Real-time (WebSocket or 1-second polling)

**Data Required:**
- Symbol: NIFTY50
- OHLCV (Open, High, Low, Close, Volume)
- Timeframe: User-selected (1min, 5min, 15min, 1hour, 1day)

**Current Status:** ✅ Already implemented and working

---

## 2. REPLAY MODE - Historical Analysis

### 2.1 Time-Based Playback

**Purpose:** Allow users to replay historical market conditions

**New Endpoint Needed:** `GET /fo/historical-range`

**Request Parameters:**
```json
{
  "symbol": "NIFTY",
  "timeframe": "5min",
  "indicators": ["iv", "delta", "gamma"],  // Multiple indicators at once
  "expiry": ["2025-11-04", "2025-11-11"],
  "from": 1762000000,                     // 09:15 AM
  "to": 1762020900,                       // 03:30 PM (market close)
  "strike_range": 10                      // ATM ± 10
}
```

**Expected Response:**
```json
{
  "status": "ok",
  "symbol": "NIFTY50",
  "timeframe": "5min",
  "buckets": [
    {
      "bucket_time": 1762000000,
      "underlying": 25100.50,
      "indicators": {
        "iv": {
          "expiries": [
            {
              "expiry": "2025-11-04",
              "strikes": [
                {
                  "strike": 24700.0,
                  "call": 0.185,
                  "put": 0.220,
                  "call_oi": 14500,
                  "put_oi": 12300
                },
                // ... more strikes
              ]
            }
          ]
        },
        "delta": {...},
        "gamma": {...}
      }
    },
    // ... more buckets (75 buckets for intraday)
  ]
}
```

**Data Volume for Replay:**

| Time Range | Buckets (5min) | Data Points (3 expiries × 21 strikes × 8 indicators) |
|------------|----------------|------------------------------------------------------|
| 1 hour | 12 | ~48,000 |
| Intraday (09:15-15:30) | 75 | ~300,000 |
| 1 day | 288 | ~1.2M |
| 1 week | 2,016 | ~8.4M |

**Performance Requirements:**
- 1 hour range: < 2 seconds
- Intraday range: < 5 seconds
- 1 day range: < 15 seconds
- 1 week range: < 60 seconds (or paginated)

**Optimization Strategy:**
- Use TimescaleDB continuous aggregates (already implemented ✅)
- Add Redis cache for popular time ranges
- Consider compression for large responses
- Support pagination for week+ queries

---

## 3. CHART POPUP - Strike History View

### 3.1 Individual Strike Time Series

**Purpose:** When user right-clicks vertical panel → "Show Chart", display full history for that strike across all expiries

**New Endpoint Needed:** `GET /fo/strike-history`

**Request Parameters:**
```json
{
  "symbol": "NIFTY",
  "strike": 24700.0,
  "underlying": "NIFTY",          // For display
  "from": 1762000000,             // Start of day or user-selected
  "to": 1762052100,               // Current time or user-selected
  "timeframe": "5min",
  "expiries": [                   // All available expiries for this strike
    "2025-11-04",
    "2025-11-11",
    "2025-11-18"
  ]
}
```

**Expected Response:**
```json
{
  "status": "ok",
  "symbol": "NIFTY50",
  "strike": 24700.0,
  "timeframe": "5min",
  "series": [
    {
      "expiry": "2025-11-04",
      "bars": [
        {
          "bucket_time": 1762000000,
          "underlying_close": 25100.50,

          // Premium (LTP)
          "call_ltp": 125.50,
          "put_ltp": 98.25,
          "call_volume": 1250,
          "put_volume": 980,

          // Greeks
          "call_iv": 0.1848,
          "put_iv": 0.2218,
          "call_delta": 0.45,
          "put_delta": -0.55,
          "call_gamma": 0.012,
          "put_gamma": 0.012,
          "call_theta": -15.3,
          "put_theta": -12.1,
          "call_vega": 8.5,
          "put_vega": 9.2,

          // Open Interest
          "call_oi": 14523,
          "put_oi": 13876,
          "call_oi_change": 250,
          "put_oi_change": -120
        },
        // ... more bars
      ]
    },
    {
      "expiry": "2025-11-11",
      "bars": [...]
    },
    {
      "expiry": "2025-11-18",
      "bars": [...]
    }
  ]
}
```

**Data Volume:**
- 3 expiries × 75 bars (intraday) × 15 fields = ~3,375 data points
- **Latency Requirement:** < 1 second (user is waiting for popup)

**Frontend Display:**
- Multi-series line chart
- Each expiry = separate series
- Show CALL and PUT side-by-side or overlaid
- Toggle between Premium, Greeks, OI views

---

## 4. METADATA & CONFIGURATION

### 4.1 Available Expiries

**Endpoint:** `GET /fo/expiries`

**Update Frequency:** Once per day (or on page load)

**Response:**
```json
{
  "symbol": "NIFTY",
  "expiries": [
    {
      "date": "2025-11-04",
      "daysToExpiry": 2,
      "type": "weekly",
      "tradingSymbol": "NIFTY2511044"
    },
    {
      "date": "2025-11-11",
      "daysToExpiry": 9,
      "type": "weekly",
      "tradingSymbol": "NIFTY25111"
    },
    {
      "date": "2025-11-28",
      "daysToExpiry": 26,
      "type": "monthly",
      "tradingSymbol": "NIFTY25NOV"
    }
  ]
}
```

**Current Status:** ✅ Already implemented

---

### 4.2 Indicator Panel Definitions

**Endpoint:** `GET /fo/indicators`

**Update Frequency:** Once on page load

**Response:**
```json
{
  "indicators": [
    {
      "id": "iv_strike_panel",
      "label": "IV by Strike",
      "indicator": "iv",
      "orientation": "vertical",
      "default": true
    },
    {
      "id": "delta_strike_panel",
      "label": "Delta by Strike",
      "indicator": "delta",
      "orientation": "vertical",
      "default": false
    },
    // ... more indicators
  ]
}
```

**Current Status:** ✅ Already implemented

---

## 5. PERFORMANCE SUMMARY

### Current Performance (Phase 1A Complete)

| Endpoint | Before | After | Improvement |
|----------|--------|-------|-------------|
| `/fo/strike-distribution` | 139 seconds | **234ms** | **594x faster** |
| Database query (63 strikes) | 6 seconds | **13ms** | **462x faster** |
| JOIN operations | 63 per request | **0** | **Eliminated** |

### Performance Targets

| Use Case | Target Latency | Current Status |
|----------|----------------|----------------|
| Vertical Panels (Latest) | < 500ms | ✅ 234ms |
| Horizontal Panels (Latest) | < 500ms | ⏳ Not tested |
| Strike History Popup | < 1s | ⏳ Endpoint needed |
| Replay (1 hour) | < 2s | ⏳ Endpoint needed |
| Replay (Intraday) | < 5s | ⏳ Endpoint needed |
| Expiries List | < 1s | ✅ Working |
| Indicator Config | < 1s | ✅ Working |

---

## 6. DATA QUALITY REQUIREMENTS

### 6.1 Critical Fields (Must Have)

For all vertical panels:
- ✅ `call` and `put` values (separate, not combined)
- ✅ `call_oi` and `put_oi`
- ✅ `underlying_close` (for ATM calculation)
- ✅ `bucket_time` (for time synchronization)
- ✅ `strike`
- ✅ `expiry`

### 6.2 Current Data Issues

**Issue:** Latest buckets have zero IV values

**Evidence:**
```sql
-- Latest bucket (02:55:00): call_iv = 0, put_iv = 0
-- Historical bucket (01:35:00): call_iv = 0.105, put_iv = 0.127
```

**Impact:** Frontend displays empty charts

**Recommended Fix:**
1. Investigate why IV calculation stopped after 01:35
2. Check if real-time ticker feed is populating IV
3. Verify continuous aggregate refresh includes IV columns
4. For testing: Seed recent buckets with realistic IV data

**Temporary Workaround:**
- Frontend can request specific bucket_time (e.g., `?bucket_time=1762046100` for 01:35 data)
- This allows testing frontend display with known-good data

---

## 7. WEBSOCKET REAL-TIME UPDATES (Future Enhancement)

### 7.1 Proposed WebSocket Architecture

**Endpoint:** `ws://backend:8000/fo/stream`

**Benefits:**
- Push updates every 5 seconds (vs polling)
- Reduced HTTP overhead
- Real-time synchronization across all panels
- Lower backend load

**Message Format:**
```json
{
  "type": "vertical_update",
  "timestamp": 1762052100,
  "symbol": "NIFTY50",
  "panels": {
    "iv": {
      "series": [
        {
          "expiry": "2025-11-04",
          "points": [...]
        }
      ]
    },
    "delta": {...},
    // ... all subscribed indicators
  }
}
```

**Current Status:** ⏳ Phase 1B or 2A

---

## 8. CACHING STRATEGY RECOMMENDATIONS

### 8.1 Backend Cache (Redis)

**Phase 1B Implementation (Ready to Deploy):**

```python
# L1: Memory cache (1 second TTL)
# L2: Redis cache (5 second TTL)

@cache(ttl=5, key="fo:snapshot:{symbol}:{timeframe}:{expiries}")
async def get_strike_distribution(...):
    # Query database only if cache miss
    ...
```

**Expected Improvement:**
- 90% cache hit rate
- Sub-50ms response for cached data
- 90% reduction in database load

**Current Status:** ✅ Implementation ready (DUAL_CACHE_IMPLEMENTATION.md)

---

### 8.2 Frontend Cache (Client-Side)

**Strategy:**
- Cache last response for each panel
- Show stale data with timestamp warning if backend slow
- Implement optimistic updates
- Use localStorage for replay mode bookmarks

**Implementation:**
```javascript
// Cache in React state or localStorage
const cachedData = {
  timestamp: Date.now(),
  data: {...},
  ttl: 5000  // 5 seconds
}

// Show cached data while fetching fresh
if (Date.now() - cachedData.timestamp < cachedData.ttl) {
  renderPanels(cachedData.data)  // Show immediately
  fetchFresh()                    // Fetch in background
}
```

---

## 9. RECOMMENDED API ENHANCEMENTS

### 9.1 Aggregated Snapshot Endpoint

**New Endpoint:** `GET /fo/monitor-snapshot`

**Purpose:** Fetch all panel data in single request

**Request:**
```json
{
  "symbol": "NIFTY",
  "timeframe": "5min",
  "expiries": ["2025-11-04", "2025-11-11", "2025-11-18"],
  "vertical_indicators": ["iv", "delta", "gamma"],
  "horizontal_indicators": ["iv", "delta"],
  "strike_range": 10
}
```

**Response:**
```json
{
  "bucket_time": 1762052100,
  "underlying": 25184.94,
  "vertical_panels": {
    "iv": { series: [...] },
    "delta": { series: [...] },
    "gamma": { series: [...] }
  },
  "horizontal_panels": {
    "iv": { series: [...] },
    "delta": { series: [...] }
  },
  "cache_ttl": 5  // Seconds until next update
}
```

**Benefits:**
- 1 HTTP request instead of 8+ separate requests
- Better caching (cache entire snapshot)
- Atomic update (all panels synchronized)
- Reduced network overhead

**Expected Performance:**
- Current (8 requests × 234ms): ~2 seconds total
- Optimized (1 request): < 500ms total
- **4x faster page load**

---

## 10. DATABASE SCHEMA VERIFICATION

### 10.1 Required Columns in Continuous Aggregates

**Table:** `fo_option_strike_bars_5min`

```sql
CREATE MATERIALIZED VIEW fo_option_strike_bars_5min
WITH (timescaledb.continuous) AS
SELECT
  time_bucket('5 minutes', bucket_time) AS bucket_time,
  symbol,
  expiry,
  strike,

  -- Underlying
  AVG(underlying_close) AS underlying_close,

  -- Implied Volatility (CRITICAL!)
  AVG(call_iv_avg) AS call_iv_avg,
  AVG(put_iv_avg) AS put_iv_avg,

  -- Greeks
  AVG(call_delta_avg) AS call_delta_avg,
  AVG(put_delta_avg) AS put_delta_avg,
  AVG(call_gamma_avg) AS call_gamma_avg,
  AVG(put_gamma_avg) AS put_gamma_avg,
  AVG(call_theta_avg) AS call_theta_avg,
  AVG(put_theta_avg) AS put_theta_avg,
  AVG(call_vega_avg) AS call_vega_avg,
  AVG(put_vega_avg) AS put_vega_avg,

  -- Volume
  SUM(call_volume_sum) AS call_volume_sum,
  SUM(put_volume_sum) AS put_volume_sum,

  -- Open Interest (MUST USE MAX, NOT AVG!)
  MAX(call_oi_sum) AS call_oi_sum,
  MAX(put_oi_sum) AS put_oi_sum,

  -- Premium (LTP)
  AVG(call_ltp_avg) AS call_ltp_avg,
  AVG(put_ltp_avg) AS put_ltp_avg,

  -- Aggregation count
  SUM(call_count) AS call_count,
  SUM(put_count) AS put_count

FROM fo_option_strike_bars
GROUP BY time_bucket('5 minutes', bucket_time), symbol, expiry, strike;
```

**Current Status:** ✅ Implemented in Phase 1A (with OI columns)

---

### 10.2 Indexes Required

```sql
-- Fast latest bucket lookup
CREATE INDEX idx_fo_5min_latest
ON fo_option_strike_bars_5min (symbol, expiry, bucket_time DESC);

-- Fast strike history lookup
CREATE INDEX idx_fo_5min_strike_history
ON fo_option_strike_bars_5min (symbol, strike, expiry, bucket_time DESC);

-- Fast moneyness lookup (Phase 2A)
CREATE INDEX idx_fo_5min_moneyness
ON fo_option_strike_bars_5min (symbol, expiry, moneyness_bucket, bucket_time DESC);
```

**Current Status:**
- ✅ Latest bucket index (primary key)
- ⏳ Strike history index (recommended)
- ⏳ Moneyness index (Phase 2A)

---

## 11. TESTING & VERIFICATION

### 11.1 Performance Testing

**Test 1: Vertical Panel Load Time**
```bash
time curl "http://localhost:8081/fo/strike-distribution?symbol=NIFTY&timeframe=5&indicator=iv&expiry=2025-11-04&expiry=2025-11-11&expiry=2025-11-18"
```
**Target:** < 500ms
**Current:** 234ms ✅

**Test 2: Multiple Indicators in Parallel**
```bash
# Frontend makes 8 parallel requests
for indicator in iv delta gamma theta vega volume oi pcr; do
  curl "http://localhost:8081/fo/strike-distribution?symbol=NIFTY&timeframe=5&indicator=$indicator&expiry=2025-11-04" &
done
wait
```
**Target:** All complete within 1 second
**Current:** ⏳ Not tested

**Test 3: Data Volume**
```bash
curl -s "http://localhost:8081/fo/strike-distribution..." | jq '.series | length'
# Should return: 3 (expiries)

curl -s "http://localhost:8081/fo/strike-distribution..." | jq '.series[0].points | length'
# Should return: 21 (strikes)
```
**Current:** ✅ Verified (3 expiries × 21 strikes)

---

### 11.2 Data Quality Testing

**Test 1: Verify CALL/PUT Separation**
```bash
curl -s "http://localhost:8081/fo/strike-distribution..." | jq '.series[0].points[0] | {strike, call, put}'
```
**Expected:**
```json
{
  "strike": 24700.0,
  "call": 0.1848,  // ✅ Non-null
  "put": 0.2218    // ✅ Non-null
}
```
**Current:** ✅ Structure correct (but values are 0 in latest bucket)

**Test 2: Verify OI Data**
```bash
curl -s "http://localhost:8081/fo/strike-distribution..." | jq '.series[0].points[0] | {call_oi, put_oi}'
```
**Expected:**
```json
{
  "call_oi": 14.0,   // ✅ Non-zero
  "put_oi": 13.0     // ✅ Non-zero
}
```
**Current:** ✅ Working

**Test 3: Verify Underlying Price**
```bash
curl -s "http://localhost:8081/fo/strike-distribution..." | jq '.series[0].points[0].underlying'
```
**Expected:** 25000-26000 (realistic NIFTY price)
**Current:** ✅ 25369.00

---

## 12. KNOWN ISSUES & BLOCKERS

### Issue 1: Zero IV Values in Latest Buckets

**Status:** 🔴 BLOCKER for frontend display

**Details:**
- Latest bucket (02:55:00): `call_iv = 0`, `put_iv = 0`
- Historical bucket (01:35:00): `call_iv = 0.105`, `put_iv = 0.127`
- OI values are present and correct

**Impact:** Frontend vertical panels show empty charts

**Root Cause:** Unknown (needs backend investigation)
- Possible causes:
  1. Real-time ticker feed stopped after 01:35
  2. Continuous aggregate refresh not picking up IV columns
  3. IV calculation logic issue

**Recommended Actions:**
1. Check ticker_service logs for IV feed issues
2. Verify continuous aggregate includes IV aggregation
3. Manually refresh continuous aggregate
4. Seed recent buckets with test data for frontend testing

**Workaround for Testing:**
```bash
# Test with historical data (01:35 bucket with IV values)
curl "http://localhost:8081/fo/strike-distribution?symbol=NIFTY&timeframe=5&indicator=iv&expiry=2025-11-04&bucket_time=1762046100"
```

---

### Issue 2: Missing Endpoints

**Status:** ⏳ PENDING for full functionality

**Required Endpoints:**
1. ❌ `/fo/strike-history` - For chart popup feature
2. ❌ `/fo/historical-range` - For replay mode
3. ❌ `/fo/monitor-snapshot` - For optimized loading (optional)

**Priority:**
- P0: `/fo/strike-history` (user-facing feature, right-click chart)
- P1: `/fo/historical-range` (replay mode for analysis)
- P2: `/fo/monitor-snapshot` (optimization, not critical)

---

## 13. NEXT STEPS

### Immediate (This Week)

1. **Fix Zero IV Issue** 🔴
   - Investigate why IV values stopped populating after 01:35
   - Verify continuous aggregate refresh
   - Seed test data if needed

2. **Implement Strike History Endpoint** 🟡
   - Endpoint: `GET /fo/strike-history`
   - Frontend right-click feature depends on this

3. **Test Horizontal Panels** 🟡
   - Verify `/fo/moneyness-series` performance
   - Test with multiple expiries

### Short-term (This Month)

4. **Deploy Redis Caching (Phase 1B)** 🟢
   - Implementation ready in `DUAL_CACHE_IMPLEMENTATION.md`
   - Expected: Additional 10-20x speedup
   - Target: Sub-50ms response times

5. **Implement Replay Mode** 🟡
   - Endpoint: `GET /fo/historical-range`
   - Support 1 hour, intraday, 1 day ranges

6. **WebSocket Real-Time Updates** 🟢
   - Replace polling with push notifications
   - Reduce backend load by 80%

### Long-term (Next Quarter)

7. **Add Moneyness Column (Phase 2A)** 🟢
   - Pre-compute moneyness buckets
   - 40% faster horizontal panel queries

8. **Latest Snapshot Materialized View (Phase 2B)** 🟢
   - Sub-100ms guaranteed for latest data
   - Refresh every 1 minute

9. **Python SDK (Phase 3)** 🟢
   - Type-safe API client
   - Benefits from all backend optimizations

---

## 14. CONTACT & SUPPORT

**Frontend Team:**
- Repository: `/home/stocksadmin/Quantagro/tradingview-viz/frontend`
- Dev Server: http://localhost:3001
- Production: TBD

**Backend Team:**
- Repository: `/home/stocksadmin/Quantagro/tradingview-viz/backend`
- Dev API: http://localhost:8081
- Phase 1A Migration: ✅ Complete (594x speedup)
- Phase 1B (Redis): ⏳ Ready to deploy

**Database:**
- TimescaleDB with continuous aggregates
- Current performance: 13ms queries
- Status: ✅ Production ready

---

## 15. APPENDIX

### A. Sample Frontend Code

**Fetching Vertical Panel Data:**
```typescript
// frontend/src/services/fo.ts
export const fetchFoStrikeDistribution = async (params: {
  symbol: string
  timeframe: string
  indicator: string
  expiry: string[]
  bucket_time?: number
}): Promise<FoStrikeDistributionResponse> => {
  const normalizedSymbol = normalizeFoSymbol(params.symbol)  // NIFTY50 → NIFTY
  const response = await api.get<FoStrikeDistributionResponse>('/fo/strike-distribution', {
    params: {
      symbol: normalizedSymbol,
      timeframe: params.timeframe,
      indicator: params.indicator,
      expiry: params.expiry,
      bucket_time: params.bucket_time,
    }
  })
  return response.data
}
```

**Rendering Vertical Panel:**
```typescript
// frontend/src/components/nifty-monitor/VerticalPanel.tsx
const scatterSeries = useMemo(() => {
  if (panel.indicator === 'iv') {
    // Split into CALL and PUT series
    const callSeries = data.map(series => ({
      expiry: series.expiry,
      side: 'call' as const,
      points: series.points.map(pt => ({
        ...pt,
        value: pt.call,  // Use CALL value
        expiry: series.expiry
      })),
    }))
    const putSeries = data.map(series => ({
      expiry: series.expiry,
      side: 'put' as const,
      points: series.points.map(pt => ({
        ...pt,
        value: pt.put,   // Use PUT value
        expiry: series.expiry
      })),
    }))
    return [...callSeries, ...putSeries]
  }
  // ... default handling
}, [data, panel.indicator])

return (
  <ScatterChart layout="vertical">
    <YAxis dataKey="strike" domain={priceRange} width={50} />
    <XAxis dataKey="value" hide />
    {scatterSeries.map((series) => (
      <Scatter
        key={`${series.expiry}-${series.side}`}
        data={series.points}
        stroke={colorMap[series.expiry]}
        strokeDasharray={series.side === 'put' ? '5 5' : undefined}  // Dashed for PUT
      />
    ))}
  </ScatterChart>
)
```

---

### B. Database Query Examples

**Get Latest IV for All Strikes:**
```sql
WITH latest AS (
  SELECT expiry, MAX(bucket_time) AS bucket_time
  FROM fo_option_strike_bars_5min
  WHERE symbol = 'NIFTY50'
  GROUP BY expiry
)
SELECT
  s.bucket_time,
  s.expiry,
  s.strike,
  s.call_iv_avg,
  s.put_iv_avg,
  s.call_oi_sum,
  s.put_oi_sum,
  s.underlying_close
FROM fo_option_strike_bars_5min s
JOIN latest l ON s.expiry = l.expiry AND s.bucket_time = l.bucket_time
WHERE s.symbol = 'NIFTY50'
  AND s.expiry IN ('2025-11-04', '2025-11-11', '2025-11-18')
ORDER BY s.expiry ASC, s.strike ASC;
```

**Get Strike History for Popup:**
```sql
SELECT
  bucket_time,
  expiry,
  underlying_close,
  call_iv_avg,
  put_iv_avg,
  call_delta_avg,
  put_delta_avg,
  call_oi_sum,
  put_oi_sum,
  call_ltp_avg,
  put_ltp_avg,
  call_volume_sum,
  put_volume_sum
FROM fo_option_strike_bars_5min
WHERE symbol = 'NIFTY50'
  AND strike = 24700.0
  AND expiry IN ('2025-11-04', '2025-11-11', '2025-11-18')
  AND bucket_time >= '2025-11-02 00:00:00+00'
  AND bucket_time <= '2025-11-02 23:59:59+00'
ORDER BY expiry ASC, bucket_time ASC;
```

---

**Document Version:** 1.0
**Last Updated:** 2025-11-02
**Status:** Production Ready (Phase 1A Complete)
**Next Review:** After Phase 1B deployment
