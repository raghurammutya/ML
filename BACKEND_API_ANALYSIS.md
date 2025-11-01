# Backend API Structure Analysis
## Compatibility Assessment with Alert Service

**Analysis Date:** 2025-11-01
**Backend Location:** `/mnt/stocksblitz-data/Quantagro/tradingview-viz/backend`
**Current Branch:** feature/nifty-monitor

---

## EXECUTIVE SUMMARY

The backend API is **feature-rich and production-ready** with comprehensive endpoints for data access, but the alert service will need to implement specific integration patterns for optimal compatibility.

### Key Findings:
- CORS is configured and allows localhost connections
- API Key authentication is available and production-ready
- RESTful endpoints return JSON (standard format)
- WebSocket streaming for real-time data available
- Position/P&L data accessible via accounts endpoints
- Greeks (IV, Delta, Gamma, Theta, Vega) available through FO endpoints
- Market calendar/trading hours available

---

## 1. CORS CONFIGURATION

**Status:** CONFIGURED ✓

### Configuration Location
- **File:** `/mnt/stocksblitz-data/Quantagro/tradingview-viz/backend/app/main.py` (lines 293-302)
- **Method:** FastAPI CORSMiddleware

### Current Settings
```python
cors_origins: ["http://localhost:3000", "http://localhost:5173", "http://localhost:8080"]
cors_credentials: True
cors_methods: ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"]
cors_headers: ["Content-Type", "Authorization", "X-Requested-With", "Accept"]
```

### For Alert Service Integration
The alert service can be added to CORS origins by updating `backend/app/config.py`:
```python
# Add alert service URL to cors_origins
cors_origins: ["http://localhost:3000", ..., "http://alert-service:PORT"]
```

**Production Recommendation:** Replace wildcard with specific origins in production.

---

## 2. AUTHENTICATION - API KEYS

**Status:** FULLY IMPLEMENTED ✓

### Authentication Method
- **Type:** Bearer Token (HTTP Authorization Header)
- **Implementation:** `backend/app/auth.py` (63 classes, 388 lines)
- **Format:** `Authorization: Bearer sb_prefix_secret`

### API Key Capabilities
- Automatic rate limiting (configurable)
- IP whitelist support
- Account access control
- Permission-based access (can_read, can_trade, can_cancel)
- Expiration support
- Usage audit logging

### API Key Management Endpoints
```
POST   /api-keys              - Create new API key
GET    /api-keys              - List keys
GET    /api-keys/{key_id}     - Get specific key
DELETE /api-keys/{key_id}     - Revoke key
POST   /api-keys/validate     - Validate key
```

### For Alert Service
The alert service should:
1. Request an API key with `can_read: True` permission
2. Use Bearer token in all API requests: `Authorization: Bearer <api_key>`
3. Handle 401 (invalid key) and 403 (permission denied) responses
4. Implement rate limit handling (default: 200 requests/min)

---

## 3. EXISTING API ENDPOINTS

### 3.1 MARKET DATA ENDPOINTS

#### Marks (Charting Data)
```
GET  /marks              - Get TradingView marks (labels)
GET  /marks/raw          - Get raw marks data
```
**Response Format:** JSON (TradingView UDF compatible)

#### Historical Data
```
GET  /historical/series  - Get OHLC time series data
```
**Parameters:** symbol, from, to, resolution
**Response:** JSON with time arrays [t], [o], [h], [l], [c]

#### Calendar Data
```
GET  /calendar/health              - Health check
GET  /calendar/status              - Market status for specific date
GET  /calendar/holidays            - List holidays
GET  /calendar/next-trading-day    - Next trading day
GET  /calendar/calendars           - Available calendars
```
**Parameters:** calendar_code (NSE, BSE, MCX, etc.), date
**Response:** JSON with trading hours, holiday info

---

### 3.2 TECHNICAL INDICATORS

#### CPR (Central Pivot Range)
```
GET  /indicators/cpr              - Get CPR data
GET  /indicators/available        - List available indicators
```
**Parameters:** symbol, from, to, resolution
**Response:** CPR levels (Pivot, R1/R2/R3, S1/S2/S3)

#### Dynamic Indicators API
```
POST /indicators/subscribe         - Subscribe to indicators (API key required)
POST /indicators/unsubscribe       - Unsubscribe
GET  /indicators/current           - Get current indicator values
GET  /indicators/history           - Historical indicator data
GET  /indicators/at-offset         - Values at specific bar offset
POST /indicators/batch             - Batch query multiple indicators
GET  /indicators/health            - Indicator service health
```
**Supported Indicators:** RSI, SMA, EMA, MACD, Bollinger Bands, ATR, etc.

---

### 3.3 FUTURES & OPTIONS (FO) ENDPOINTS

#### FO Instruments
```
GET  /fo/indicators              - List available FO indicators
GET  /fo/instruments/search      - Search for option/futures contracts
GET  /fo/expiries                - List available expiries
GET  /fo/moneyness-series        - Greeks by moneyness
GET  /fo/strike-distribution     - Option chain distribution
```

#### Greek Calculations Available
The system tracks these Greeks:
- **IV** (Implied Volatility) - ATM/OTM/ITM levels
- **Delta** - Directional sensitivity
- **Gamma** - Delta acceleration
- **Theta** - Time decay
- **Vega** - Volatility sensitivity
- **Open Interest (OI)** - Position concentration
- **PCR** (Put-Call Ratio) - Market sentiment
- **Max Pain** - Expiry-based pain levels

#### Example FO Search Query
```
GET /fo/instruments/search
   ?symbol=NIFTY
   &segment=NFO-OPT
   &expiry_from=2025-11-01
   &option_type=CE
   &strike_min=19400
   &strike_max=19600
```

**Response:** List of matched instruments with Greeks data

#### FO WebSocket Stream
```
WebSocket /fo/stream
```
**Purpose:** Real-time Greeks and market data updates
**Authentication:** Via query parameter (API key)

---

### 3.4 ACCOUNT & POSITION ENDPOINTS

#### Trading Accounts Management
```
POST   /accounts/trading-accounts          - Create account
GET    /accounts/trading-accounts          - List accounts
POST   /accounts/trading-accounts/reload   - Reload accounts
PUT    /accounts/trading-accounts/{id}     - Update account
DELETE /accounts/trading-accounts/{id}     - Delete account
```

#### Position & P&L Endpoints
```
GET  /accounts/{account_id}/positions              - Current positions
GET  /accounts/{account_id}/positions/history      - Position history
GET  /accounts/{account_id}/positions/at-time      - Positions at specific time

POST /accounts/{account_id}/sync                   - Force sync account data

GET  /accounts/{account_id}/orders                 - List orders
POST /accounts/{account_id}/orders                 - Place order
DELETE /accounts/{account_id}/orders/{order_id}    - Cancel order
PATCH /accounts/{account_id}/orders/{order_id}     - Modify order

GET  /accounts/{account_id}/holdings               - Holdings/Delivery
GET  /accounts/{account_id}/holdings/history       - Holdings history

GET  /accounts/{account_id}/funds                  - Margins/Available funds
GET  /accounts/{account_id}/funds/history          - Funds history
GET  /accounts/{account_id}/funds/at-time          - Funds at specific time
```

#### Position Response Example
```json
{
  "status": "success",
  "account_id": "user123",
  "count": 2,
  "total_pnl": 5000.50,
  "day_pnl": 1200.75,
  "positions": [
    {
      "tradingsymbol": "NIFTY25NOVFUT",
      "exchange": "NFO",
      "quantity": 50,
      "average_price": 19500.00,
      "last_price": 19600.00,
      "pnl": 5000.00,
      "day_pnl": 1200.75,
      "multiplier": 1
    }
  ]
}
```

---

### 3.5 ORDER MANAGEMENT ENDPOINTS

#### Single Orders
```
POST   /accounts/{account_id}/orders                  - Place order
DELETE /accounts/{account_id}/orders/{order_id}       - Cancel
PATCH  /accounts/{account_id}/orders/{order_id}       - Modify
```

#### Batch Orders (Multi-leg strategies)
```
POST /accounts/{account_id}/batch-orders              - Place multiple orders
POST /accounts/{account_id}/orders/cancel-batch       - Cancel multiple
POST /accounts/{account_id}/orders/cancel-all         - Cancel all pending
```

#### Order Types Supported
- MARKET
- LIMIT
- SL (Stop Loss)
- SL-M (Stop Loss + Market)

#### Products
- MIS (Margin Intraday)
- NRML (Normal - Overnight)
- CNC (Cash & Carry)

---

### 3.6 REAL-TIME STREAMING (WebSockets)

#### Available WebSocket Endpoints
```
WebSocket /fo/stream                    - FO Greeks & Greeks streaming
WebSocket /indicators/stream            - Indicator updates
WebSocket /orders/{account_id}          - Order updates
WebSocket /orders                       - Multi-account orders
WebSocket /labels/stream                - Label/mark updates
WebSocket /nifty-monitor/stream         - Nifty index monitoring
```

#### WebSocket Authentication
```javascript
// Connect with API key as query parameter
ws://backend-url/fo/stream?api_key=sb_prefix_secret
```

---

## 4. RESPONSE FORMAT ANALYSIS

### All Endpoints Return JSON ✓

#### Standard Response Structure
```json
{
  "status": "success|error",
  "data": { ... },
  "error": "error message (if status=error)"
}
```

#### Examples:

**Positions Response:**
```json
{
  "status": "success",
  "account_id": "user123",
  "count": 5,
  "total_pnl": 12345.67,
  "day_pnl": 2345.67,
  "positions": [...]
}
```

**Greeks Response:**
```json
{
  "status": "ok",
  "symbol": "NIFTY",
  "indicators": [
    {
      "name": "IV",
      "data": [
        {"strike": 19500, "ce_iv": 18.5, "pe_iv": 18.2},
        ...
      ]
    }
  ]
}
```

**Orders Response:**
```json
{
  "status": "success",
  "account_id": "user123",
  "count": 3,
  "orders": [
    {
      "order_id": "230405000123456",
      "tradingsymbol": "NIFTY25NOVFUT",
      "status": "COMPLETE",
      "filled_quantity": 50,
      "average_price": 19500.00
    }
  ]
}
```

---

## 5. MIDDLEWARE & FEATURES

### Middleware Stack
1. **ErrorHandlingMiddleware** - Standard error responses
2. **RequestLoggingMiddleware** - Request/response logging + process time headers
3. **CorrelationIdMiddleware** - Request tracking for debugging
4. **Metrics Middleware** - Prometheus metrics collection

### Health Checks
```
GET /health
GET /accounts/health/status
GET /calendar/health
GET /indicators/health
```

### Monitoring
```
GET /metrics  - Prometheus metrics
```

---

## 6. ALERT SERVICE COMPATIBILITY CHECKLIST

### What's Available for Alert Service
- [x] REST API for data access (no GraphQL needed)
- [x] JSON response format
- [x] API key authentication
- [x] Position & P&L data endpoints
- [x] Greeks (IV, Delta, Gamma, Theta, Vega) via FO endpoints
- [x] Market calendar/trading hours
- [x] Order placement & cancellation
- [x] WebSocket real-time updates
- [x] Batch operations
- [x] Historical data access
- [x] Health check endpoints
- [x] CORS support

### What Alert Service Needs to Implement
1. **API Key Storage** - Securely store API key
2. **Bearer Token Implementation** - Use Authorization header
3. **Rate Limiting Handling** - Implement backoff for 429 responses
4. **WebSocket Connection** - For real-time order/position updates
5. **Timestamp Handling** - Unix timestamps for historical queries
6. **Error Handling** - Handle 401, 403, 404, 500 responses

---

## 7. POTENTIALLY MISSING ENDPOINTS FOR ALERTS

Based on alert service requirements, these endpoints might need to be added:

### Alert Trigger Evaluation (Currently Missing)
```
POST /alerts/evaluate                    - Evaluate if alert triggers
POST /alerts/batch-evaluate              - Evaluate multiple conditions
```

### Real-time Alert Notifications (Currently Missing)
```
WebSocket /alerts/stream                 - Real-time alert events
POST /alerts/triggers                    - Create alert trigger
GET  /alerts/triggers                    - List active triggers
DELETE /alerts/triggers/{trigger_id}     - Remove trigger
```

### Greeks at Specific Time (Partially Available)
```
GET /fo/greeks/at-time?symbol=...&timestamp=...&greek=IV
```
Need to verify if this endpoint exists for historical Greeks lookups.

### Consolidated P&L View (Partially Available)
```
GET /accounts/consolidated-pnl           - Aggregate across accounts
GET /accounts/pnl-history                - P&L over time
```
Available but via individual account endpoints - might need aggregation helper.

---

## 8. IMPLEMENTATION RECOMMENDATIONS

### Phase 1: Basic Integration (Week 1)
1. Create API key for alert service in backend
2. Implement HTTP client with Bearer token authentication
3. Query positions endpoint: `GET /accounts/{account_id}/positions`
4. Query orders endpoint: `GET /accounts/{account_id}/orders`
5. Query funds endpoint: `GET /accounts/{account_id}/funds`
6. Implement error handling (401, 403, 404, 500)

### Phase 2: Real-time Data (Week 2)
1. Connect to WebSocket `/orders/{account_id}` for order updates
2. Connect to WebSocket `/fo/stream` for Greeks updates
3. Implement reconnection logic with exponential backoff
4. Cache real-time data locally for alert evaluation

### Phase 3: Alert Triggers (Week 3)
1. Implement alert evaluation engine
2. Query Greeks on-demand via `/fo/instruments/search` + Greeks endpoints
3. Support trigger conditions: position P&L, Greek values, margin, price levels
4. Store trigger state in alert service database

### Phase 4: Production Hardening (Week 4)
1. Add request logging and monitoring
2. Implement circuit breaker for backend failures
3. Add comprehensive error recovery
4. Load test with realistic alert volume

---

## 9. CONFIGURATION REQUIREMENTS

### Backend Configuration for Alert Service
**File:** `backend/app/config.py`

Add alert service to CORS origins:
```python
cors_origins: [
    "http://localhost:3000",
    "http://localhost:5173", 
    "http://localhost:8080",
    "http://alert-service:8000"  # Add this
]
```

### Rate Limiting Defaults
- Default: 200 requests/minute
- Can be customized per API key
- WebSocket connections not rate limited (separate quota)

### Timeout Settings
- Query timeout: 30 seconds
- WebSocket timeout: 60 seconds
- Redis connection timeout: 30 seconds

---

## 10. KEY FINDINGS SUMMARY

| Aspect | Status | Details |
|--------|--------|---------|
| REST API | ✓ Complete | All major endpoints available |
| JSON Responses | ✓ Yes | Standard JSON format |
| CORS | ✓ Configured | Localhost origins allowed |
| Authentication | ✓ API Keys | Bearer token based |
| Positions/P&L | ✓ Available | Per account + historical |
| Greeks (IV/Delta/Gamma/Theta/Vega) | ✓ Available | Via `/fo/` endpoints |
| Orders | ✓ Full CRUD | Place, cancel, modify, batch |
| Calendar/Hours | ✓ Available | Multiple exchanges supported |
| WebSocket | ✓ Available | Real-time updates for orders/Greeks |
| Rate Limiting | ✓ Built-in | Per API key configurable |
| Health Checks | ✓ Multiple | Service level health endpoints |
| Error Handling | ✓ Standard | HTTP status codes + JSON errors |
| Alert Triggers | ✗ Not found | **NEEDS TO BE IMPLEMENTED** |
| Alert Notifications | ✗ Not found | **NEEDS TO BE IMPLEMENTED** |

---

## 11. INTEGRATION EXAMPLE

### Request: Get Current Positions
```http
GET /accounts/user123/positions HTTP/1.1
Host: backend.local:8000
Authorization: Bearer sb_abc123_def456...
Accept: application/json
```

### Response: Current Positions
```json
{
  "status": "success",
  "account_id": "user123",
  "count": 2,
  "total_pnl": 5000.50,
  "day_pnl": 1200.75,
  "positions": [
    {
      "tradingsymbol": "NIFTY25NOVFUT",
      "exchange": "NFO",
      "quantity": 50,
      "average_price": 19500.00,
      "last_price": 19625.50,
      "pnl": 6275.00,
      "day_pnl": 1200.75,
      "multiplier": 1
    },
    {
      "tradingsymbol": "BANKNIFTY25NOVFUT",
      "exchange": "NFO",
      "quantity": 25,
      "average_price": 45500.00,
      "last_price": 45200.00,
      "pnl": -7500.00,
      "day_pnl": 500.00,
      "multiplier": 1
    }
  ]
}
```

---

## CONCLUSION

The backend API is **production-ready and well-structured** for alert service integration. The primary work required is:

1. **Implement alert evaluation logic** - Determine when alerts trigger
2. **Add WebSocket support** - For real-time position/order monitoring
3. **Create alert storage layer** - Persist alert definitions and states
4. **Build notification system** - Email, Slack, SMS delivery (not in backend API)

The backend provides all necessary data access points. The alert service needs to implement the evaluation and notification logic on top of this API.

**Estimated Effort:** 2-3 weeks for basic functionality, 4 weeks for production-ready system with comprehensive monitoring.

