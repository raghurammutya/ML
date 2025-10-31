# Ticker Service - New Features Integration Guide

**Service**: Ticker Service (v2.0)
**Base URL**: `http://localhost:8080`
**Date**: 2025-10-31

## Overview

The ticker service now provides advanced order management features including real-time WebSocket streaming, webhook notifications, batch order execution, and improved reliability through database persistence.

---

## 1. WebSocket Order Streaming (NEW)

**Real-time order status updates without polling**

### Endpoint
```
WS: ws://localhost:8080/advanced/ws/orders/{account_id}
```

### Quick Start (JavaScript)
```javascript
const ws = new WebSocket('ws://localhost:8080/advanced/ws/orders/primary');

ws.onmessage = (event) => {
    const update = JSON.parse(event.data);
    if (update.type === 'order_update') {
        console.log('Order updated:', update.data);
        // Update your UI here
    }
};

// Keep-alive (send every 30s)
setInterval(() => ws.send('ping'), 30000);
```

### Message Format
```json
{
    "type": "order_update",
    "account_id": "primary",
    "data": {
        "order_id": "230405000123456",
        "status": "COMPLETE",
        "filled_quantity": 50,
        "average_price": 19500.25
    },
    "timestamp": "2025-10-31T09:15:30.123Z"
}
```

### Use Cases
- Live order status dashboard
- Real-time position tracking
- Instant order failure alerts

---

## 2. Webhook Notifications (NEW)

**HTTP callbacks when order events occur**

### Register Webhook
```bash
POST /advanced/webhooks
Content-Type: application/json

{
    "url": "https://your-app.com/webhook",
    "account_id": "primary",
    "events": ["order_completed", "order_failed"],
    "secret": "your-secret-key"
}
```

### Response
```json
{
    "webhook_id": "978b941d-1339-4158-b0aa-43f5467717d1",
    "url": "https://your-app.com/webhook",
    "active": true
}
```

### Your Webhook Endpoint
Your server will receive HTTP POST:
```
POST https://your-app.com/webhook
Content-Type: application/json
X-Webhook-Secret: your-secret-key

{
    "event": "order_completed",
    "account_id": "primary",
    "data": {
        "order_id": "230405000123456",
        "status": "COMPLETE",
        ...
    },
    "timestamp": "2025-10-31T09:15:30.123Z"
}
```

### Available Events
- `order_placed` - Order successfully placed
- `order_completed` - Order fully filled
- `order_failed` - Order placement/execution failed
- `order_cancelled` - Order cancelled
- `order_rejected` - Order rejected by exchange

### Use Cases
- Send SMS/email alerts
- Update external databases
- Trigger risk management systems
- Integration with third-party platforms

---

## 3. Batch Order Execution (NEW)

**Submit multiple orders atomically with rollback**

### Endpoint
```bash
POST /advanced/batch-orders
Content-Type: application/json

{
    "orders": [
        {
            "exchange": "NFO",
            "tradingsymbol": "NIFTY25NOVFUT",
            "transaction_type": "BUY",
            "quantity": 50,
            "product": "NRML",
            "order_type": "MARKET"
        },
        {
            "exchange": "NFO",
            "tradingsymbol": "BANKNIFTY25NOVFUT",
            "transaction_type": "BUY",
            "quantity": 25,
            "product": "NRML",
            "order_type": "LIMIT",
            "price": 45500.0
        }
    ],
    "account_id": "primary",
    "rollback_on_failure": true
}
```

### Response
```json
{
    "batch_id": "550e8400-e29b-41d4-a716-446655440000",
    "success": true,
    "total_orders": 2,
    "succeeded": 2,
    "failed": 0,
    "created_at": "2025-10-31T09:15:00.000Z",
    "completed_at": "2025-10-31T09:15:05.123Z"
}
```

### Rollback Behavior
- **`rollback_on_failure: true`** (default): If any order fails, all successful orders are cancelled
- **`rollback_on_failure: false`**: Partial success allowed

### Use Cases
- Spread orders (buy + sell simultaneously)
- Multi-leg option strategies
- Portfolio rebalancing
- Risk management (all-or-nothing execution)

---

## 4. Enhanced Reliability (NEW)

**Database persistence for task recovery**

### What Changed
- All order tasks now persist to PostgreSQL
- Service restarts automatically resume pending tasks
- No manual intervention needed

### Visibility
Check task status via health endpoint:
```bash
GET /health
```

Response includes task statistics:
```json
{
    "status": "ok",
    "ticker": {
        "running": true,
        "tasks_pending": 5,
        "tasks_completed": 150
    }
}
```

---

## 5. Prometheus Metrics (NEW)

**Monitoring and observability**

### Endpoint
```bash
GET /metrics
```

### Available Metrics
- `http_requests_total` - Total HTTP requests by method/endpoint/status
- `order_requests_total` - Total orders by operation/account
- `order_execution_duration_seconds` - Order execution latency
- `circuit_breaker_state` - Circuit breaker status per account
- `active_websocket_connections` - Live WebSocket connections

### Use Cases
- Grafana dashboards
- Alerting (Prometheus AlertManager)
- Performance monitoring
- Capacity planning

---

## 6. Existing Features (Updated)

### Place Order
```bash
POST /orders/place
```

### Get Order Status
```bash
GET /orders/{order_id}
```

### Get Positions
```bash
GET /portfolio/positions
```

### Historical Data
```bash
GET /history?instrument_token={token}&from_ts={from}&to_ts={to}&interval=minute
```

### Subscriptions
```bash
POST /subscriptions
GET /subscriptions
DELETE /subscriptions/{instrument_token}
```

---

## Migration Guide

### For Real-time Updates
**Before (polling):**
```javascript
setInterval(() => {
    fetch('/orders/123').then(r => r.json()).then(updateUI);
}, 5000); // Poll every 5 seconds
```

**After (WebSocket):**
```javascript
const ws = new WebSocket('ws://localhost:8080/advanced/ws/orders/primary');
ws.onmessage = (e) => {
    const update = JSON.parse(e.data);
    if (update.type === 'order_update') updateUI(update.data);
};
```

### For Event-driven Workflows
**Before:**
```javascript
// Manual polling or cron jobs
```

**After (Webhooks):**
```javascript
// Register once
await registerWebhook({
    url: 'https://your-app.com/webhook',
    events: ['order_completed']
});

// Your server receives automatic notifications
```

### For Multi-order Execution
**Before (sequential):**
```javascript
const order1 = await placeOrder({...});
const order2 = await placeOrder({...});
// If order2 fails, order1 already placed (partial execution)
```

**After (batch with rollback):**
```javascript
const batch = await batchOrders({
    orders: [order1, order2],
    rollback_on_failure: true
});
// All-or-nothing execution
```

---

## Quick Reference

| Feature | Endpoint | Method | Use Case |
|---------|----------|--------|----------|
| WebSocket Stream | `/advanced/ws/orders/{account}` | WS | Real-time order updates |
| Create Webhook | `/advanced/webhooks` | POST | Event notifications |
| List Webhooks | `/advanced/webhooks` | GET | View active webhooks |
| Delete Webhook | `/advanced/webhooks/{id}` | DELETE | Unregister webhook |
| Batch Orders | `/advanced/batch-orders` | POST | Atomic multi-order execution |
| Metrics | `/metrics` | GET | Monitoring/observability |
| Health Check | `/health` | GET | Service status |

---

## Support

**Documentation**: `IMPROVEMENT_FEATURES_DOCUMENTATION.md` (detailed guide)

**Health Check**: `curl http://localhost:8080/health`

**Logs**: `docker logs tv-ticker`

**Questions**: Contact trading-platform-team@yourcompany.com

---

## Examples Repository

**JavaScript/React Example:**
```bash
git clone https://github.com/yourcompany/ticker-service-examples
cd ticker-service-examples/react-websocket
npm install && npm start
```

**Python Example:**
```bash
cd ticker-service-examples/python-webhooks
pip install -r requirements.txt
python webhook_server.py
```

---

**Version**: 2.0
**Released**: 2025-10-31
**Breaking Changes**: None (all features are additive)
