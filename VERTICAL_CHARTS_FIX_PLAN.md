# Fix Plan: Vertical Charts Not Showing Data

## Executive Summary
The vertical Put/Call panels on http://5.223.52.98/trading-dashboard/ are not displaying Greek metrics (Delta, Gamma, Theta, Vega, IV, PCR, Premium, Decay) because:

1. **Expiry 2025-11-04 (NWeek+0)** has **ZERO Greek values** in database (only OI data exists)
2. **Later expiries (NWeek+1, NWeek+2, etc.)** have **valid Greek data**
3. The frontend is correctly requesting and receiving data
4. The issue is purely **backend data quality** for the nearest expiry

## Current Data State (Verified)

### Database Analysis
```sql
-- Query results from fo_option_strike_bars table:
expiry      | strike_count | nonzero_delta_count | nonzero_oi_count
------------|--------------|---------------------|------------------
2025-11-04  |         1968 |                   0 |             1968  ← PROBLEM: No Greeks
2025-11-11  |        10230 |                5724 |            10199  ← HAS Greeks
2025-11-18  |         9569 |                4783 |             8090  ← HAS Greeks
2025-11-25  |        11737 |                5937 |            10426  ← HAS Greeks
```

**Key Finding**: Expiry `2025-11-04` has 1,968 rows with OI data but **ZERO rows with Delta/Greeks data**.

### API Response Verification

**NWeek+0 (2025-11-04) - NO GREEKS:**
```bash
curl "http://5.223.52.98/tradingview-api/fo/strike-distribution?symbol=NIFTY50&timeframe=5&indicator=delta&option_side=put&expiry=NWeek%2B0"
```
Response:
```json
{
  "strike": 25000,
  "delta": 0.0,  ← ALL ZEROS
  "gamma": 0.0,
  "theta": 0.0,
  "vega": 0.0,
  "iv": 0.0,
  "oi": 101949  ← Only OI has data
}
```

**NWeek+1 (2025-11-11) - HAS GREEKS:**
```bash
curl "http://5.223.52.98/tradingview-api/fo/strike-distribution?symbol=NIFTY50&timeframe=5&indicator=delta&option_side=put&expiry=NWeek%2B1"
```
Response:
```json
{
  "strike": 25000,
  "delta": -0.0032,  ← Valid delta
  "gamma": 0.000011,  ← Valid gamma
  "theta": -0.0027,
  "vega": 0.0028,
  "iv": 0.319  ← Valid IV
}
```

### Frontend Request Flow (WORKING CORRECTLY)

1. **useFoAnalytics.ts:520** - Fetches expiries from `/fo/expiries`
   - Returns: `["2025-11-04", "2025-11-11", "2025-11-18", ...]`

2. **useFoAnalytics.ts:527-545** - Converts to v2 format with relative labels
   - `2025-11-04` → `NWeek+0`
   - `2025-11-11` → `NWeek+1`
   - `2025-11-28` → `NMonth+0`

3. **useFoAnalytics.ts:570** - Takes first 6 expiries
   - `expiries = ["2025-11-04", "2025-11-11", "2025-11-18", "2025-11-25", "2025-12-02", "2025-12-09"]`

4. **useFoAnalytics.ts:592-633** - Fetches strike distribution for all indicators
   - Makes separate API calls for `call` and `put` sides
   - Indicators: delta, gamma, theta, rho, vega, iv, oi, pcr, premium, decay

5. **useFoAnalytics.ts:432-446** - Extracts indicator values
   - Uses `extractIndicatorValue()` to get the value for each indicator
   - Filters out entries where `value == null`
   - **0.0 is NOT null, so it passes through**

6. **useFoAnalytics.ts:448-466** - Fallback to synthetic data
   - ONLY if `calls.length === 0` OR `puts.length === 0`
   - Since backend returns data (with zeros), synthetic data is NOT used

7. **SideTabsPanel.tsx:339-356** - Renders charts
   - Gets strike lines from `analytics.strike[indicator]`
   - Applies expiry and moneyness filters
   - Creates chart data from decorated lines

## Root Cause

The issue is in the **ticker service** or **data ingestion pipeline** for expiry `2025-11-04`:

1. **OI (Open Interest)** is being written correctly
2. **Greeks (IV, Delta, Gamma, Theta, Vega, Rho)** are being written as **0.0** instead of calculated values
3. This affects ONLY the nearest expiry (2025-11-04), while later expiries have correct data

## Why Charts Show "Awaiting strike distribution"

The frontend logic in **SideTabsPanel.tsx:584-586**:
```typescript
{activeLines.length ? (
  <ResponsiveContainer>...</ResponsiveContainer>
) : (
  <div className={styles.emptyState}>
    {analytics.loading ? 'Loading analytics…' : 'Awaiting strike distribution'}
  </div>
)}
```

When all Greek values are 0.0:
- The chart receives data points: `[{strike: 25000, value: 0}, {strike: 25500, value: 0}, ...]`
- The chart renders, but all lines are flat at y=0
- For indicators like Delta (range -1 to 1), a flat line at 0 looks like no data

## Fix Plan (Backend Team)

### Priority 1: Fix Greeks Calculation for Expiry 2025-11-04

**Location**: Ticker Service / Data Ingestion Pipeline

**Investigation Steps**:
1. Check why Greeks calculation is failing for `2025-11-04` specifically
2. Verify if this is an expiry-specific issue or a time-based issue (e.g., options expiring today)
3. Check if underlying price, volatility, or other inputs are missing for this expiry
4. Review logs for errors during Greeks calculation for this expiry

**Likely Causes**:
- **Expiry too close**: If expiry is today or tomorrow, time-to-expiry is very small, Greeks calculation might fail
- **Missing inputs**: Underlying price, risk-free rate, or volatility might be missing for this expiry
- **Calculation exception**: Division by zero or other numerical errors for very short-dated options
- **Data pipeline issue**: Greeks calculation service might not be running for this specific expiry

**Files to Check**:
```
ticker_service/
├── Greeks calculation module
├── Option pricing library integration
└── Data writing to fo_option_strike_bars table
```

**Expected Fix**:
Ensure that for ALL expiries, including near-dated ones:
```python
# Pseudocode
for each option_contract:
    if has_market_data and has_underlying_price:
        greeks = calculate_greeks(
            spot=underlying_price,
            strike=option.strike,
            time_to_expiry=days_to_expiry / 365,
            volatility=implied_volatility or historical_volatility,
            risk_free_rate=current_rate,
            option_type='call' or 'put'
        )

        # Write to database
        write_to_db(
            call_iv_avg=greeks.iv if call else 0,
            put_iv_avg=greeks.iv if put else 0,
            call_delta_avg=greeks.delta if call else 0,
            put_delta_avg=greeks.delta if put else 0,
            call_gamma_avg=greeks.gamma if call else 0,
            put_gamma_avg=greeks.gamma if put else 0,
            # ... etc
        )
```

### Priority 2: Add Data Quality Checks

**Location**: Backend API (`backend/app/routes/fo.py`)

Add validation before returning data:
```python
# Around line 900-1000 in strike_distribution function
for series in result['series']:
    if series.get('call') or series.get('put'):
        # Check if all Greeks are zero
        all_zeros = all(
            point.get(indicator) == 0
            for point in (series.get('call', []) + series.get('put', []))
        )
        if all_zeros and indicator not in ['oi', 'volume']:
            logger.warning(
                f"All {indicator} values are zero for expiry {series.get('expiry')}. "
                f"Greeks calculation may have failed."
            )
```

### Priority 3: Backfill Historical Data (Optional)

If expiry 2025-11-04 is historical and should have had Greeks:
```sql
-- Run Greeks calculation on historical tick data
-- Backfill fo_option_strike_bars with calculated Greeks
```

## Testing After Fix

### Test 1: Verify Database Has Non-Zero Greeks
```sql
SELECT
    expiry,
    strike,
    put_delta_avg,
    put_gamma_avg,
    put_theta_avg,
    put_iv_avg
FROM fo_option_strike_bars
WHERE symbol = 'NIFTY'
  AND expiry = '2025-11-04'
  AND put_delta_avg <> 0
LIMIT 10;
```
**Expected**: Should return rows with non-zero Greek values.

### Test 2: Verify API Returns Non-Zero Greeks
```bash
curl -s "http://5.223.52.98/tradingview-api/fo/strike-distribution?symbol=NIFTY50&timeframe=5&indicator=delta&option_side=put&expiry=NWeek%2B0" \
  | jq '.series[0].put[0:3] | map({strike, delta, gamma, iv})'
```
**Expected Output**:
```json
[
  {
    "strike": 25000,
    "delta": -0.45,  ← Non-zero
    "gamma": 0.015,  ← Non-zero
    "iv": 0.18       ← Non-zero
  }
]
```

### Test 3: Verify Frontend Charts Display
1. Open http://5.223.52.98/trading-dashboard/
2. Look at **Put vertical panel** on the left
3. Click through tabs: Delta, Gamma, Theta, Vega, IV
4. **Expected**: Should see line charts with non-zero values, NOT "Awaiting strike distribution"

### Test 4: Verify All Expiries Have Data
```bash
for expiry in NWeek+0 NWeek+1 NMonth+0; do
    echo "=== Testing $expiry ==="
    curl -s "http://5.223.52.98/tradingview-api/fo/strike-distribution?symbol=NIFTY50&timeframe=5&indicator=delta&option_side=put&expiry=$expiry" \
      | jq '.series[0] | {expiry, has_data: (.put | length > 0), sample_delta: .put[0].delta}'
done
```

## Timeline & Ownership

| Task | Owner | Priority | Estimated Time |
|------|-------|----------|----------------|
| Investigate why Greeks are zero for 2025-11-04 | Ticker Service Team | P0 | 2 hours |
| Fix Greeks calculation for near-dated options | Ticker Service Team | P0 | 4 hours |
| Add data quality validation & logging | Backend Team | P1 | 2 hours |
| Test fix on staging/production | QA Team | P0 | 1 hour |
| Verify frontend charts display correctly | Frontend Team | P0 | 30 min |

**Total Estimated Time**: 1 business day

## Success Criteria

✅ All expiries in database have non-zero Greek values (where applicable)
✅ API `/fo/strike-distribution` returns non-zero Greeks for all expiries
✅ Vertical Put/Call panels display line charts for Delta, Gamma, Theta, Vega, IV
✅ Charts update in real-time as new data arrives
✅ No "Awaiting strike distribution" messages for valid expiries

## Notes

- **Frontend is working correctly** - No frontend changes needed
- **OI data is working** - Only Greeks are affected
- **Later expiries work** - Only nearest expiry (2025-11-04) is broken
- **Root cause is backend** - Greeks calculation or data ingestion pipeline

---

**Document Created**: 2025-11-07
**Status**: Awaiting Backend Team Action
**Contact**: Frontend team available for testing after fix
