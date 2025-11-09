# Backend Issue: Greeks Are All Zero

## Issue Description
The vertical charts on the trading dashboard (http://5.223.52.98/trading-dashboard/) are not showing data for Delta, Gamma, Theta, Vega, IV, and other Greek metrics in the Put/Call side panels.

## Root Cause Analysis

### Database Investigation
```sql
SELECT symbol, expiry, strike, call_iv_avg, put_iv_avg, call_delta_avg, put_delta_avg, call_oi_sum, put_oi_sum
FROM fo_option_strike_bars
WHERE symbol = 'NIFTY' AND expiry = '2025-11-04'
ORDER BY bucket_time DESC LIMIT 10;
```

**Result**: All Greek columns (`call_iv_avg`, `put_iv_avg`, `call_delta_avg`, `put_delta_avg`, `call_gamma_avg`, `put_gamma_avg`, `call_theta_avg`, `put_theta_avg`, `call_vega_avg`, `put_vega_avg`) are **0**, while OI columns (`call_oi_sum`, `put_oi_sum`) have actual values.

### API Response
```bash
curl "http://5.223.52.98/tradingview-api/fo/strike-distribution?symbol=NIFTY50&timeframe=5&indicator=delta&option_side=put&expiry=NWeek%2B0"
```

**Response excerpt**:
```json
{
  "strike": 25000,
  "iv": 0.0,
  "delta": 0.0,
  "gamma": 0.0,
  "theta": 0.0,
  "vega": 0.0,
  "oi": 101949,
  "volume": 22764
}
```

## Impact
- **Put and Call vertical panels** show "Awaiting strike distribution" message
- **Only OI data works** because it has non-zero values
- **Max Pain metric works** because it's calculated at expiry level, not strike level
- Users cannot see critical Greek data for options analysis

## Expected Behavior
All Greek values should be populated with calculated values based on:
- Black-Scholes or other option pricing models
- Real-time market data (spot price, strike, time to expiry, risk-free rate, volatility)

## Tables/Files Requiring Fix

### 1. **Ticker Service** (`ticker_service/`)
The ticker service needs to:
- Calculate Greeks using the options pricing library
- Write calculated Greeks to `fo_option_strike_bars` table
- Ensure calculations happen for both calls and puts

### 2. **Database Table**: `fo_option_strike_bars`
Columns to populate:
- `call_iv_avg`, `put_iv_avg` (Implied Volatility)
- `call_delta_avg`, `put_delta_avg`
- `call_gamma_avg`, `put_gamma_avg`
- `call_theta_avg`, `put_theta_avg`
- `call_vega_avg`, `put_vega_avg`
- `call_rho_per_1pct_avg`, `put_rho_per_1pct_avg` (Rho)

### 3. **Backend API** (`backend/app/routes/fo.py`)
Currently at line 856+, the `strike_distribution` endpoint correctly maps database columns to API response, but since database values are 0, API returns 0.

## Temporary Frontend Workaround
The frontend has been configured to:
1. Use synthetic/fallback data for Greek indicators when all values are zero
2. Still display OI data correctly since it has real values
3. Show informative message when Greek data is unavailable

## Action Items for Backend Team
- [ ] Investigate why Greeks calculation is not happening in ticker service
- [ ] Verify options pricing library is properly integrated
- [ ] Ensure real-time tick data includes necessary inputs (underlying price, volatility, etc.)
- [ ] Add logging to Greeks calculation pipeline
- [ ] Test with sample option contract to verify calculations
- [ ] Backfill historical data if needed (optional)

## Testing After Fix
```bash
# Test that Greeks have non-zero values
curl "http://5.223.52.98/tradingview-api/fo/strike-distribution?symbol=NIFTY50&timeframe=5&indicator=delta&option_side=put&expiry=NWeek%2B0" | jq '.series[0].put[0:3] | map({strike, delta, gamma, iv})'

# Expected: delta, gamma, iv should be non-zero
```

## Timeline
- **Discovered**: November 7, 2025
- **Priority**: High (affects key dashboard functionality)
- **Assigned**: Backend/Ticker Service Team
