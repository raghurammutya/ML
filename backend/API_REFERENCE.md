# Backend API Reference for KiteConnect Integration

## Base URL
- **Development**: `http://localhost:8081`
- **Production**: `https://api.yourplatform.com`

## Authentication
All requests must include a valid JWT token from the user_service:

```
Authorization: Bearer <jwt_token>
```

For account-specific operations, include:
```
X-Account-ID: <kite_user_id>
```

---

## 1. Trading Accounts API

### 1.1 List All Accounts
**Endpoint**: `GET /accounts`

**Query Parameters**:
- `user_id` (optional): Filter by user_id

**Response**:
```json
{
  "status": "success",
  "count": 2,
  "accounts": [
    {
      "account_id": "DW1234",
      "user_id": "user_123",
      "broker": "zerodha",
      "status": "active",
      "total_pnl": 15234.50,
      "day_pnl": 1250.00,
      "position_count": 5,
      "available_margin": 125000.00
    }
  ]
}
```

### 1.2 Get Account Details
**Endpoint**: `GET /accounts/{account_id}`

**Response**:
```json
{
  "status": "success",
  "account": {
    "account_id": "DW1234",
    "user_id": "user_123",
    "broker": "zerodha",
    "status": "active",
    "email": "user@example.com",
    "user_name": "John Doe",
    "total_pnl": 15234.50,
    "day_pnl": 1250.00
  }
}
```

### 1.3 Sync Account Data
**Endpoint**: `POST /accounts/{account_id}/sync`

**Request Body**:
```json
{
  "force": false
}
```

**Response**:
```json
{
  "status": "success",
  "synced_at": "2025-11-07T10:30:00Z",
  "positions_count": 5,
  "orders_count": 12,
  "holdings_count": 3
}
```

---

## 2. Positions API

### 2.1 Get Positions
**Endpoint**: `GET /accounts/{account_id}/positions`

**Query Parameters**:
- `fresh` (optional, boolean): Fetch fresh data from ticker_service (default: false)

**Response**:
```json
{
  "status": "success",
  "account_id": "DW1234",
  "count": 5,
  "total_pnl": 15234.50,
  "day_pnl": 1250.00,
  "positions": [
    {
      "tradingsymbol": "NIFTY25NOVFUT",
      "exchange": "NFO",
      "product": "NRML",
      "quantity": 75,
      "average_price": 24500.50,
      "last_price": 24550.00,
      "pnl": 3712.50,
      "m2m": 3712.50,
      "day_pnl": 500.00,
      "value": 1841287.50,
      "buy_quantity": 75,
      "buy_price": 24500.50,
      "sell_quantity": 0,
      "sell_price": 0,
      "overnight_quantity": 75
    }
  ]
}
```

---

## 3. Orders API

### 3.1 Get Orders
**Endpoint**: `GET /accounts/{account_id}/orders`

**Query Parameters**:
- `status` (optional): Filter by status (OPEN, COMPLETE, REJECTED, CANCELLED)
- `limit` (optional, default: 100): Max orders to return

**Response**:
```json
{
  "status": "success",
  "account_id": "DW1234",
  "count": 12,
  "orders": [
    {
      "order_id": "240711000012345",
      "exchange_order_id": "1234567890",
      "tradingsymbol": "NIFTY24NOVFUT",
      "exchange": "NFO",
      "transaction_type": "BUY",
      "order_type": "LIMIT",
      "product": "NRML",
      "quantity": 75,
      "pending_quantity": 0,
      "filled_quantity": 75,
      "price": 24500.00,
      "average_price": 24500.50,
      "status": "COMPLETE",
      "status_message": "Order executed",
      "order_timestamp": "2025-11-07T09:15:23Z",
      "exchange_timestamp": "2025-11-07T09:15:24Z"
    }
  ]
}
```

### 3.2 Place Order
**Endpoint**: `POST /accounts/{account_id}/orders`

**Request Body**:
```json
{
  "tradingsymbol": "NIFTY25NOVFUT",
  "exchange": "NFO",
  "transaction_type": "BUY",
  "quantity": 75,
  "order_type": "LIMIT",
  "product": "NRML",
  "price": 24500.00,
  "validity": "DAY",
  "tag": "strategy1"
}
```

**Validation Rules**:
- `tradingsymbol`: Required, 1-50 characters
- `exchange`: Required, one of: NSE, NFO, BSE, BFO, MCX
- `transaction_type`: Required, BUY or SELL
- `quantity`: Required, 1-10000
- `order_type`: Required, one of: MARKET, LIMIT, SL, SL-M
- `product`: Required, one of: CNC, MIS, NRML
- `price`: Required for LIMIT and SL orders
- `trigger_price`: Required for SL and SL-M orders
- `validity`: Optional, DAY or IOC (default: DAY)

**Response**:
```json
{
  "status": "success",
  "account_id": "DW1234",
  "success": true,
  "order_id": "240711000012345",
  "message": "Order placed successfully"
}
```

**Error Response**:
```json
{
  "status": "error",
  "success": false,
  "error": "Insufficient margin"
}
```

### 3.3 Place Batch Orders
**Endpoint**: `POST /accounts/{account_id}/batch-orders`

**Request Body**:
```json
{
  "orders": [
    {
      "tradingsymbol": "NIFTY25NOVFUT",
      "exchange": "NFO",
      "transaction_type": "BUY",
      "quantity": 50,
      "order_type": "MARKET",
      "product": "NRML"
    },
    {
      "tradingsymbol": "BANKNIFTY25NOVFUT",
      "exchange": "NFO",
      "transaction_type": "SELL",
      "quantity": 25,
      "order_type": "LIMIT",
      "product": "NRML",
      "price": 45500.0
    }
  ],
  "rollback_on_failure": true
}
```

**Response**:
```json
{
  "status": "success",
  "account_id": "DW1234",
  "batch_id": "550e8400-e29b-41d4-a716-446655440000",
  "total_orders": 2,
  "succeeded": 2,
  "failed": 0,
  "order_ids": ["230405000123456", "230405000123457"]
}
```

---

## 4. Holdings API

### 4.1 Get Holdings
**Endpoint**: `GET /accounts/{account_id}/holdings`

**Response**:
```json
{
  "status": "success",
  "account_id": "DW1234",
  "count": 3,
  "total_pnl": 12550.00,
  "total_value": 362550.00,
  "holdings": [
    {
      "tradingsymbol": "TCS",
      "exchange": "NSE",
      "isin": "INE467B01029",
      "quantity": 10,
      "average_price": 3500.00,
      "last_price": 3625.50,
      "pnl": 1255.00,
      "product": "CNC",
      "collateral_quantity": 0,
      "collateral_type": ""
    }
  ]
}
```

---

## 5. Funds/Margins API

### 5.1 Get Funds
**Endpoint**: `GET /accounts/{account_id}/funds`

**Query Parameters**:
- `segment` (optional, default: equity): equity or commodity

**Response**:
```json
{
  "status": "success",
  "account_id": "DW1234",
  "funds": {
    "equity": {
      "enabled": true,
      "net": 150000.50,
      "available": {
        "cash": 150000.50,
        "intraday_payin": 0,
        "collateral": 0,
        "live_balance": 150000.50
      },
      "utilised": {
        "debits": 50000.00,
        "exposure": 25000.00,
        "m2m_realised": -500.00,
        "m2m_unrealised": 1200.00
      }
    },
    "commodity": {
      "enabled": true,
      "net": 50000.00,
      "available": {
        "cash": 50000.00
      },
      "utilised": {
        "debits": 0
      }
    }
  }
}
```

---

## 6. Order WebSocket API

### 6.1 WebSocket Connection
**Endpoint**: `ws://localhost:8081/ws/orders/{account_id}`

**Authentication**: Include JWT token as query parameter:
```
ws://localhost:8081/ws/orders/{account_id}?token=<jwt_token>
```

**Message Types**:

#### Order Update
```json
{
  "type": "order_update",
  "account_id": "DW1234",
  "order_id": "240711000012345",
  "status": "COMPLETE",
  "filled_quantity": 75,
  "average_price": 24500.50,
  "status_message": "Order executed",
  "timestamp": "2025-11-07T09:15:24Z"
}
```

#### Position Update
```json
{
  "type": "position_update",
  "account_id": "DW1234",
  "tradingsymbol": "NIFTY25NOVFUT",
  "quantity": 75,
  "pnl": 3712.50,
  "timestamp": "2025-11-07T09:15:24Z"
}
```

#### Heartbeat (send every 30 seconds)
```json
{
  "type": "ping"
}
```

#### Heartbeat Response
```json
{
  "type": "pong",
  "timestamp": "2025-11-07T09:15:24Z"
}
```

---

## 7. F&O Analytics API

### 7.1 Get Strike Distribution
**Endpoint**: `GET /fo/strike-distribution`

**Query Parameters**:
- `symbol`: Underlying symbol (e.g., NIFTY, BANKNIFTY)
- `timeframe`: Time granularity (1min, 5min, 15min)
- `indicator`: Primary indicator (iv, delta, gamma, theta, vega, oi, pcr)
- `option_side` (optional): Filter by option type (call, put, or omit for both)
- `expiry[]`: Array of expiry dates (YYYY-MM-DD format)
- `bucket_time` (optional): Unix timestamp for historical data

**Example**:
```
GET /fo/strike-distribution?symbol=NIFTY&timeframe=5min&indicator=iv&option_side=call&expiry[]=2025-11-07
```

**Response**: See FO_STRIKE_DISTRIBUTION_API.md for full response structure

### 7.2 Get Moneyness Series
**Endpoint**: `GET /fo/moneyness-series`

**Query Parameters**:
- `symbol`: Underlying symbol (NIFTY50, BANKNIFTY, etc.)
- `timeframe`: Time granularity (1min, 5min, 15min)
- `indicator`: Indicator to fetch (iv, delta, gamma, oi, pcr, premium_abs, premium_pct)
- `hours`: Hours of historical data (default: 6)

**Response**:
```json
{
  "status": "ok",
  "symbol": "NIFTY50",
  "timeframe": "5min",
  "indicator": "iv",
  "series": [
    {
      "expiry": "2025-11-07",
      "data": [
        {
          "bucket_time": 1699334400,
          "moneyness": "ATM",
          "value": 0.1823,
          "volume": 15000,
          "oi": 250000
        }
      ]
    }
  ]
}
```

---

## 8. Futures Analytics API

### 8.1 Get Position Signals
**Endpoint**: `GET /futures/position-signals`

**Query Parameters**:
- `symbol`: Underlying symbol (NIFTY, BANKNIFTY)
- `timeframe`: Time granularity (1min, 5min, 15min)
- `contract` (optional): Specific contract or current month
- `hours`: Hours of historical data (default: 6)

**Response**:
```json
{
  "status": "success",
  "symbol": "NIFTY",
  "series": [
    {
      "time": "2025-11-07T10:30:00Z",
      "contract": "NIFTY25NOVFUT",
      "close": 24550.00,
      "open_interest": 5000000,
      "price_change_pct": 0.25,
      "oi_change_pct": 2.5,
      "position_signal": "LONG_BUILDUP",
      "signal_strength": 0.625
    }
  ]
}
```

### 8.2 Get Rollover Metrics
**Endpoint**: `GET /futures/rollover-metrics`

**Query Parameters**:
- `symbol`: Underlying symbol (NIFTY, BANKNIFTY)

**Response**:
```json
{
  "status": "success",
  "symbol": "NIFTY",
  "expiries": [
    {
      "expiry": "2025-11-25",
      "total_oi": 5000000,
      "oi_pct": 65.5,
      "days_to_expiry": 18,
      "rollover_pressure": 0.0
    },
    {
      "expiry": "2025-12-30",
      "total_oi": 2000000,
      "oi_pct": 26.2,
      "days_to_expiry": 53,
      "rollover_pressure": 0.0
    }
  ]
}
```

---

## 9. Error Handling

All errors follow this format:

```json
{
  "detail": "Error message description",
  "status_code": 400
}
```

### Common Error Codes:
- `400`: Bad Request (validation errors, invalid parameters)
- `401`: Unauthorized (missing or invalid JWT token)
- `403`: Forbidden (insufficient permissions)
- `404`: Not Found (account/resource not found)
- `500`: Internal Server Error (server-side issues)

---

## 10. Rate Limiting

- **Default**: 100 requests per minute per IP
- **Authenticated**: 1000 requests per minute per user
- **WebSocket**: 1 message per second max

Rate limit headers:
```
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 995
X-RateLimit-Reset: 1699334460
```

---

## 11. Frontend Integration Example

### Setting up Axios Instance

```typescript
import axios from 'axios';

const api = axios.create({
  baseURL: process.env.REACT_APP_API_BASE_URL || 'http://localhost:8081',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add auth token to all requests
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('jwt_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Add account ID header for account-specific requests
export const setAccountId = (accountId: string) => {
  api.defaults.headers.common['X-Account-ID'] = accountId;
};

export default api;
```

### Example: Fetching Positions

```typescript
import api from './api';

export const fetchPositions = async (accountId: string, fresh = false) => {
  const response = await api.get(`/accounts/${accountId}/positions`, {
    params: { fresh },
  });
  return response.data;
};
```

### Example: Placing Order

```typescript
export const placeOrder = async (
  accountId: string,
  orderData: OrderRequest
) => {
  const response = await api.post(
    `/accounts/${accountId}/orders`,
    orderData
  );
  return response.data;
};
```

### Example: WebSocket Connection

```typescript
const connectOrdersWebSocket = (accountId: string, token: string) => {
  const ws = new WebSocket(
    `ws://localhost:8081/ws/orders/${accountId}?token=${token}`
  );

  ws.onmessage = (event) => {
    const message = JSON.parse(event.data);

    if (message.type === 'order_update') {
      // Handle order update
      console.log('Order updated:', message);
    } else if (message.type === 'position_update') {
      // Handle position update
      console.log('Position updated:', message);
    }
  };

  ws.onclose = () => {
    // Reconnect after 5 seconds
    setTimeout(() => connectOrdersWebSocket(accountId, token), 5000);
  };

  // Send heartbeat every 30 seconds
  const heartbeat = setInterval(() => {
    if (ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'ping' }));
    }
  }, 30000);

  return () => {
    clearInterval(heartbeat);
    ws.close();
  };
};
```

---

## 12. Environment Variables

### Backend (.env)
```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=stocksblitz_unified
DB_USER=stocksblitz
DB_PASSWORD=stocksblitz123

REDIS_URL=redis://localhost:6379

TICKER_SERVICE_URL=http://localhost:8080
TICKER_SERVICE_TIMEOUT=30

# CORS Origins (comma-separated)
CORS_ORIGINS=http://localhost:3000,http://localhost:5173,http://localhost:8080,http://localhost:5174
```

### Frontend (.env)
```env
REACT_APP_API_BASE_URL=http://localhost:8081
REACT_APP_WS_URL=ws://localhost:8081
REACT_APP_USER_SERVICE_URL=http://localhost:8002
```

---

## Support

For questions or issues, contact the backend team or file an issue in the repository.
