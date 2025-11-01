# Frontend-Backend Integration Summary

## Quick Reference

### Core Files Analyzed

1. **API Client Setup**
   - File: `/mnt/stocksblitz-data/Quantagro/tradingview-viz/frontend/src/services/api.ts`
   - Key: Centralized Axios instance with base URL configuration
   - Technology: Axios 1.6.2
   - Timeout: 120 seconds

2. **Service Layer Examples**
   - Trading Service: `/mnt/stocksblitz-data/Quantagro/tradingview-viz/frontend/src/services/trading.ts`
   - Labels Service: `/mnt/stocksblitz-data/Quantagro/tradingview-viz/frontend/src/services/labels.ts`
   - FO Service: `/mnt/stocksblitz-data/Quantagro/tradingview-viz/frontend/src/services/fo.ts`
   - Monitor Service: `/mnt/stocksblitz-data/Quantagro/tradingview-viz/frontend/src/services/monitor.ts`
   - Replay Service: `/mnt/stocksblitz-data/Quantagro/tradingview-viz/frontend/src/services/replay.ts`

3. **Backend Services**
   - Alert Service: `/mnt/stocksblitz-data/Quantagro/tradingview-viz/alert_service/app/main.py`
   - Alert Routes: `/mnt/stocksblitz-data/Quantagro/tradingview-viz/alert_service/app/routes/alerts.py`

### Current Service Integration Patterns

#### Pattern 1: Simple REST API
```
File: frontend/src/services/trading.ts
- Base URL: `/accounts`
- Methods: GET, POST, PATCH, DELETE
- Error Handling: Graceful degradation (return defaults)
- Response Format: { status: 'success' | 'error', data: T }
```

#### Pattern 2: WebSocket Real-Time
```
Files: 
- frontend/src/services/labels.ts
- frontend/src/services/monitor.ts
- frontend/src/services/fo.ts

Features:
- Dynamic URL building (supports absolute and relative URLs)
- Automatic protocol switching (http→ws, https→wss)
- Message subscription pattern
- JSON message parsing with error handling
- Auto-reconnect on disconnect
```

#### Pattern 3: Error Handling
```
Service Level:
- try-catch with console logging
- Return sensible defaults instead of throwing
- Validate response structure before using

Component Level:
- ErrorBoundary for React errors
- try-finally in useEffect hooks
- Silent error handling for non-critical operations
```

---

## Current Frontend Architecture

### Directory Structure
```
frontend/
├── src/
│   ├── services/           # API client layer
│   │   ├── api.ts         # Shared Axios instance
│   │   ├── trading.ts     # Trading accounts, orders, positions
│   │   ├── labels.ts      # ML labels CRUD + WebSocket
│   │   ├── fo.ts          # Derivatives indicators
│   │   ├── monitor.ts     # Monitor real-time data
│   │   ├── replay.ts      # Replay functionality
│   │   └── cprIndicator.ts
│   ├── types/             # TypeScript interfaces
│   │   ├── types.ts       # Main types
│   │   ├── labels.ts      # Label-specific types
│   │   └── replay.ts      # Replay-specific types
│   ├── pages/             # Page components
│   │   └── MonitorPage.tsx
│   ├── components/        # React components
│   │   ├── ErrorBoundary.tsx
│   │   ├── nifty-monitor/ # Monitor-specific components
│   │   ├── trading/       # Trading components
│   │   └── ...
│   ├── hooks/             # Custom React hooks
│   │   ├── useReplayMode.ts
│   │   └── useTabManager.ts
│   ├── context/           # React context (to be added)
│   ├── App.tsx
│   └── main.tsx
├── vite.config.ts         # Vite configuration with proxies
└── package.json           # Dependencies
```

### Technology Stack
- **HTTP Client**: Axios 1.6.2
- **Real-time**: Native WebSocket API
- **UI Framework**: React 18.2.0
- **Chart Library**: lightweight-charts 4.2.3
- **Language**: TypeScript 5.3.2
- **Build Tool**: Vite 5.0.4

---

## How Each Service Currently Works

### 1. Trading Service - Account Management

**File**: `frontend/src/services/trading.ts`

```typescript
// HTTP Pattern: List all accounts
fetchAllAccounts() 
  → GET /accounts
  → Response: { status: 'success', accounts: [...] }
  → Maps to: TradingAccount[]

// HTTP Pattern: Get account positions
fetchAccountPositions(accountId, underlying?)
  → GET /accounts/{accountId}/positions
  → Filters by underlying if provided
  → Maps response fields to Position interface

// HTTP Pattern: Get account orders
fetchAccountOrders(accountId, underlying?)
  → GET /accounts/{accountId}/orders
  → Filters by underlying if provided
  → Maps response fields to Order interface

// HTTP Pattern: Get account funds
fetchAccountFunds(accountId)
  → GET /accounts/{accountId}/funds
  → Returns: { cash_balance, margin_used, available_margin }

// WebSocket Pattern (NOT YET IMPLEMENTED)
TradingWebSocketClient
  → Would connect to: ws://host/tradingview-api/ws/trading
  → Handlers: onOrderUpdate, onPositionUpdate, onFundsUpdate
  → Currently disabled with console warnings
```

**Error Handling**:
- Catches exceptions and logs to console
- Returns empty arrays/null for failed requests
- Some operations throw for critical failures (e.g., fetchAccountFunds)

---

### 2. Labels Service - ML Annotations

**File**: `frontend/src/services/labels.ts`

```typescript
// HTTP Pattern: CRUD operations
createLabel(label) → POST /api/labels
updateLabel(labelId, updates) → PATCH /api/labels/{labelId}
deleteLabel(...) → DELETE /api/labels
fetchLabels(symbol, timeframe, from?, to?) → GET /api/labels

// WebSocket Pattern: Real-time label updates
connectLabelStream()
  → WS: ws://host/tradingview-api/labels/stream
  → Subscribe message: { action: 'subscribe', channel: 'labels', symbol, timeframe }
  → Updates message: { type: 'label.created|updated|deleted', ... }

// WebSocket Pattern: Option popup updates
subscribePopup(ws, underlying, strike, expiry, timeframe)
  → Message: { action: 'subscribe_popup', ... }
  → Updates: { type: 'popup_update', seq, timestamp, candle, metrics }
```

**Special Features**:
- Intelligent WebSocket URL building for both relative and absolute URLs
- Protocol auto-switching (http→ws, https→wss)
- JSON message parsing with validation
- Timestamp conversion utilities (seconds ↔ ISO string)

---

### 3. FO (Derivatives) Service

**File**: `frontend/src/services/fo.ts`

```typescript
// HTTP Pattern: Get FO indicators
fetchFoIndicators()
  → GET /fo/indicators
  → Returns: FoIndicatorDefinition[]

// HTTP Pattern: Get expiries for symbol
fetchFoExpiries(symbol)
  → GET /fo/expiries?symbol=NIFTY
  → Symbol normalization: NIFTY50 → NIFTY

// HTTP Pattern: Get moneyness data
fetchFoMoneynessSeries({ symbol, timeframe, indicator, expiry, ... })
  → GET /fo/moneyness-series?params...
  → Returns: FoMoneynessSeriesResponse (series of points by expiry/bucket)

// HTTP Pattern: Get strike distribution
fetchFoStrikeDistribution({ symbol, timeframe, indicator, expiry, bucket_time })
  → GET /fo/strike-distribution?params...
  → Returns: FoStrikeDistributionResponse (points by strike level)

// WebSocket Pattern: Real-time FO data
connectFoStream()
  → WS: ws://host/tradingview-api/fo/stream
  → Receives: FoRealtimeBucket { type, strikes[], metrics }
  → Metrics: call_oi, put_oi, pcr, max_pain_strike
```

---

### 4. Monitor Service - Real-time Market Data

**File**: `frontend/src/services/monitor.ts`

```typescript
// HTTP Pattern: Get metadata for symbol
fetchMonitorMetadata({ symbol?, expiry_limit?, otm_levels? })
  → GET /monitor/metadata?params...
  → Returns: MonitorMetadataResponse
    ├── underlying: MonitorInstrument
    ├── futures: MonitorOptionLeg[]
    └── options: MonitorOptionExpiry[]

// HTTP Pattern: Create monitor session
createMonitorSession({ tokens, requested_mode?, account_id? })
  → POST /monitor/session
  → Returns: { session_id, tokens }

// HTTP Pattern: Delete session
deleteMonitorSession(sessionId)
  → DELETE /monitor/session/{sessionId}

// HTTP Pattern: Get snapshot
fetchMonitorSnapshot()
  → GET /monitor/snapshot
  → Returns: { underlying, options } data

// HTTP Pattern: Search symbols
searchMonitorSymbols(query, limit, signal?)
  → GET /monitor/search?query=...&limit=...
  → Returns: MonitorSearchResult[]

// WebSocket Pattern: Real-time updates
connectMonitorStream()
  → WS: ws://host/tradingview-api/monitor/stream
  → Receives: MonitorStreamMessage { channel, payload }
  → Auto-reconnect with 3s delay on disconnect
```

---

### 5. Replay Service - Historical Data Replay

**File**: `frontend/src/services/replay.ts`

```typescript
// HTTP Pattern: Fetch replay window
fetchReplayWindow({ underlying, timeframe, start, end, expiries, strikes, panels })
  → GET /replay/window?params...
  → Base URL: http://localhost:8081 (different from main API)

// WebSocket Pattern: Interactive replay
ReplayWebSocketClient
  → constructor(url)
  → connect(onMessage): Creates WS, auto-reconnect on close
  → send(message): Send JSON message
  → enterReplay(pageId, underlying, timeframe, cursor, windowSize)
  → exitReplay(pageId)
  → disconnect(): Clean up

// Auto-reconnect: 3 second delay
```

---

## Alert Service Backend

**File**: `/mnt/stocksblitz-data/Quantagro/tradingview-viz/alert_service/app/main.py`

### Current Backend Architecture
```
FastAPI Application
├── Port: (configured in settings)
├── CORS: Enabled for all origins
├── Middleware: Standard FastAPI middleware
├── Services:
│   ├── ConditionEvaluator: Evaluates alert conditions
│   ├── NotificationService: Sends notifications (Telegram)
│   └── EvaluationWorker: Background task processing
├── Database: PostgreSQL with asyncpg
├── Cache: Redis (TODO)
└── Routes:
    └── /alerts: Alert CRUD operations
```

### Current Alert Routes
**File**: `/mnt/stocksblitz-data/Quantagro/tradingview-viz/alert_service/app/routes/alerts.py`

```
POST   /alerts              Create alert
GET    /alerts              List user alerts
GET    /alerts/{alert_id}   Get specific alert
PATCH  /alerts/{alert_id}   Update alert
DELETE /alerts/{alert_id}   Delete alert
POST   /alerts/{alert_id}/trigger    Manually trigger
POST   /alerts/{alert_id}/test       Test alert condition
GET    /alerts/history      Get trigger history
```

---

## Integration Checklist for Alert Service

### Frontend Implementation
- [ ] Create `frontend/src/services/alerts.ts`
  - [ ] Define Alert, AlertCreate, AlertUpdate interfaces
  - [ ] Implement CRUD functions using shared `api` client
  - [ ] Implement WebSocket connection builder
  - [ ] Add message parsing utilities

- [ ] Create `frontend/src/context/AlertContext.tsx`
  - [ ] Provide alert list state
  - [ ] Manage WebSocket subscriptions
  - [ ] Handle triggered alerts

- [ ] Create `frontend/src/components/AlertPanel.tsx`
  - [ ] Display alerts list
  - [ ] Show triggered alerts
  - [ ] Create/edit/delete forms

- [ ] Update `frontend/vite.config.ts`
  - [ ] Add proxy for `/alerts` endpoint
  - [ ] Enable WebSocket (ws: true)

- [ ] Update `frontend/src/types.ts`
  - [ ] Add alert-related type definitions

- [ ] Integrate AlertProvider
  - [ ] Wrap main app or specific pages
  - [ ] Use useAlerts hook in components

### Backend Verification
- [ ] Alert Service has `/alerts` endpoints
- [ ] WebSocket endpoint available at `/alerts/stream`
- [ ] Response format matches Alert interface
- [ ] Error handling matches patterns

### Vite Proxy Configuration
```typescript
'/alerts': {
  target: 'http://127.0.0.1:8090',  // Alert service port
  changeOrigin: true,
  ws: true,  // Enable WebSocket
}
```

---

## Key Patterns to Follow

### 1. Service Function Pattern
```typescript
export const functionName = async (params: ParamType): Promise<ReturnType> => {
  try {
    const response = await api.method<ReturnType>(`${API_BASE}...`, ...)
    return response.data
  } catch (error) {
    console.error('Specific error message:', error)
    return defaultValue  // or throw
  }
}
```

### 2. WebSocket Builder Pattern
```typescript
const buildWsUrl = (): string => {
  const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/tradingview-api'
  const isAbsolute = API_BASE_URL.startsWith('http')
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  
  if (isAbsolute) {
    const url = new URL(API_BASE_URL)
    url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
    url.pathname = `${url.pathname.replace(/\/$/, '')}/endpoint/stream`
    return url.toString()
  }
  
  return `${protocol}//${window.location.host}${API_BASE_URL}/endpoint/stream`
}
```

### 3. Component Hook Pattern
```typescript
useEffect(() => {
  const loadData = async () => {
    setLoading(true)
    try {
      const data = await fetchData()
      setState(data)
    } catch (error) {
      console.error('Error:', error)
    } finally {
      setLoading(false)
    }
  }
  
  loadData()
  
  return () => {
    // Cleanup
  }
}, [dependencies])
```

### 4. Context Provider Pattern
```typescript
const [state, setState] = useState(initialValue)

const Provider: React.FC<{ children }> = ({ children }) => (
  <Context.Provider value={{ state, setState }}>
    {children}
  </Context.Provider>
)

const useCustom = () => {
  const context = useContext(Context)
  if (!context) throw new Error('Must use within Provider')
  return context
}
```

---

## Testing the Integration

### Manual Testing
1. Check `frontend/src/services/alerts.ts` compiles
2. Test each HTTP method:
   ```bash
   curl -X POST http://localhost:3002/alerts \
     -H "Content-Type: application/json" \
     -d '{"name":"test","alert_type":"price","priority":"high","condition_config":{},"notification_channels":["telegram"]}'
   ```
3. Test WebSocket connection in browser console:
   ```javascript
   const ws = new WebSocket('ws://localhost:3002/alerts/stream')
   ws.onmessage = (e) => console.log(JSON.parse(e.data))
   ```

### Visual Verification
- Alerts appear in UI
- Creating/updating/deleting works
- Real-time triggers show in triggered list
- Error messages display properly

---

## Files Modified/Created

### Must Create
- `frontend/src/services/alerts.ts` - Service layer
- `frontend/src/context/AlertContext.tsx` - State management
- `frontend/src/components/AlertPanel.tsx` - UI component

### Must Modify
- `frontend/vite.config.ts` - Add alerts proxy
- `frontend/src/types.ts` - Add alert types
- `frontend/src/pages/MonitorPage.tsx` - Import AlertProvider

### Reference Files (Read-Only)
- `frontend/src/services/trading.ts` - Pattern reference
- `frontend/src/services/labels.ts` - WebSocket pattern
- `frontend/src/components/ErrorBoundary.tsx` - Error handling

---

## Common Issues & Solutions

### Issue: WebSocket connection refused
**Solution**: Ensure vite.config.ts has correct proxy target and port

### Issue: API returning 404
**Solution**: Check that backend endpoint matches service API_BASE constant

### Issue: Type errors in TypeScript
**Solution**: Ensure interfaces match actual API response structure

### Issue: Auto-reconnect loops
**Solution**: Add exponential backoff or max retry limits

---

## Next Steps

1. Review this guide with team
2. Implement alert service following patterns
3. Test each function individually
4. Integrate into MonitorPage
5. Add error handling and logging
6. Test WebSocket with real alerts
7. Deploy and monitor

---

## References

- Full Guide: `FRONTEND_INTEGRATION_GUIDE.md`
- Service Files: `frontend/src/services/*.ts`
- Type Definitions: `frontend/src/types/*.ts`
- Alert Service API: `alert_service/app/routes/alerts.py`
- Configuration: `frontend/vite.config.ts`

