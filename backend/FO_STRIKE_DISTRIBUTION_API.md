# FO Strike Distribution API - Enhanced Response

## Endpoint: `/fo/strike-distribution`

### Query Parameters:
- `symbol`: Underlying symbol (e.g., NIFTY, BANKNIFTY)
- `timeframe`: Time granularity (1min, 5min, 15min)
- `indicator`: Primary indicator to fetch (iv, delta, gamma, theta, vega, oi, pcr)
- `option_side`: Filter by option type - 'call', 'put', or None for both
- `expiry[]`: Array of expiry dates (YYYY-MM-DD format)
- `bucket_time`: Optional timestamp for historical data (Unix timestamp)

### Response Structure:

```json
{
  "status": "ok",
  "symbol": "NIFTY",
  "timeframe": "5min",
  "indicator": "iv",
  "option_side": "call",  // or "put" or null
  "series": [
    {
      "expiry": "2025-11-07",
      "bucket_time": 1699334400,
      "call": [  // Only included if option_side is null or "call"
        {
          "strike": 19500,
          
          // Standard Greeks
          "iv": 0.1823,
          "delta": 0.4521,
          "gamma": 0.000145,
          "theta": -12.34,
          "vega": 45.67,
          
          // Enhanced Greeks
          "rho": 0.000234,
          "theta_daily": -12.34,  // Daily theta decay
          
          // Pricing Metrics
          "intrinsic": 50.00,     // Intrinsic value
          "extrinsic": 125.50,    // Time value
          "premium": 175.50,      // Market price (intrinsic + extrinsic)
          "ltp": 175.50,          // Last traded price (same as premium)
          "model_price": 170.25,  // Black-Scholes theoretical price
          
          // Premium/Discount Analysis
          "premium_discount_abs": 5.25,    // premium - model_price
          "premium_discount_pct": 3.08,    // (premium - model_price) / model_price * 100
          
          // Volume & OI
          "volume": 15000,
          "oi": 250000,          // Open Interest
          "pcr": 0.85,           // Put-Call Ratio for this strike
          
          // Market Depth Metrics
          "liquidity_score": 85.5,        // 0-100 score
          "spread_abs": 0.50,             // Absolute bid-ask spread
          "spread_pct": 0.28,             // Spread as % of mid-price
          "depth_imbalance": -5.25,       // Order book imbalance %
          "book_pressure": 0.0234,        // Buy/sell pressure [-1, 1]
          "microprice": 175.48,           // Weighted mid-price
          
          // Moneyness Classification
          "moneyness": "CALL_OTM1"        // ATM, ITM1-10, OTM1-10
        }
      ],
      "put": [  // Only included if option_side is null or "put"
        {
          // Same structure as call objects
          "strike": 19500,
          "iv": 0.1956,
          "delta": -0.5479,
          // ... all other fields
          "moneyness": "PUT_OTM1"
        }
      ],
      "metadata": {
        "strike_count": 101,
        "has_greeks": true,
        "has_oi": true,
        "atm_strike": 19525,
        "underlying_price": 19534.75,
        
        // Expiry-level Aggregates
        "total_call_oi": 5000000,
        "total_put_oi": 4250000,
        "pcr": 0.850,              // Expiry-level PCR
        "max_pain_strike": 19500    // Maximum pain strike
      }
    }
  ],
  "metadata": {
    "total_expiries": 2,
    "underlying_price": 19534.75,
    "strike_range": "ATM ± 50 strikes",
    "data_available": true
  }
}
```

## Key Features:

### 1. **Option Side Filtering**
- Request only calls with `option_side=call`
- Request only puts with `option_side=put`
- Get both by omitting the parameter or setting it to null

### 2. **Real-time vs Historical**
- Real-time: Omit `bucket_time` to get latest data
- Historical: Provide `bucket_time` as Unix timestamp

### 3. **Comprehensive Greeks**
- Standard: IV, Delta, Gamma, Theta, Vega
- Enhanced: Rho, Daily Theta

### 4. **Pricing Intelligence**
- Market Price (Premium/LTP)
- Model Price (Black-Scholes)
- Premium/Discount analysis
- Intrinsic & Extrinsic breakdown

### 5. **Market Microstructure**
- Liquidity scoring
- Bid-ask spreads
- Order book imbalance
- Microprice calculation

### 6. **Risk Metrics**
- Open Interest (OI)
- Put-Call Ratio (PCR) at strike and expiry level
- Max Pain calculation
- Moneyness classification

## Frontend Usage Example:

```javascript
// Left panel - Calls only
const callData = await fetchFoStrikeDistribution({
  symbol: 'NIFTY',
  timeframe: '5min',
  indicator: 'iv',
  option_side: 'call',
  expiry: ['2025-11-07', '2025-11-14']
});

// Right panel - Puts only
const putData = await fetchFoStrikeDistribution({
  symbol: 'NIFTY',
  timeframe: '5min',
  indicator: 'iv',
  option_side: 'put',
  expiry: ['2025-11-07', '2025-11-14']
});
```

## Notes:
- All monetary values are in the currency of the underlying
- Percentages are expressed as decimals (0.18 = 18%)
- Greeks follow standard market conventions
- Max Pain is calculated using a simplified algorithm based on OI
- Market depth metrics are aggregated over the timeframe period