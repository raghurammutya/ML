# Ticker Service - Improvement Features Documentation

This document provides comprehensive documentation for the advanced features implemented in the ticker service, including WebSocket streaming, webhook notifications, batch order execution, and database task persistence.

## Table of Contents
1. [WebSocket Order Streaming](#1-websocket-order-streaming)
2. [Webhook Notifications](#2-webhook-notifications)
3. [Batch Order Execution](#3-batch-order-execution)
4. [Database Task Persistence](#4-database-task-persistence)
5. [Testing Guide](#5-testing-guide)
6. [Troubleshooting](#6-troubleshooting)

---

## 1. WebSocket Order Streaming

**Location**: `app/websocket_orders.py`, `app/routes_advanced.py`

### Overview
WebSocket order streaming provides real-time, bidirectional communication for order updates, eliminating the need for polling. Clients connect to a WebSocket endpoint and receive live order status updates as they occur.

### Architecture

```
┌─────────────┐         WebSocket          ┌──────────────────┐
│   Client    │ ◄─────────────────────────► │ OrderStreamMgr   │
│ (Frontend)  │    /ws/orders/{account_id}  │                  │
└─────────────┘                             └──────────────────┘
                                                     ▲
                                                     │
                                                     │ broadcast_order_update()
                                                     │
                                            ┌────────┴─────────┐
                                            │ OrderExecutor    │
                                            │   (on events)    │
                                            └──────────────────┘
```

### Implementation Details

**OrderStreamManager Class** (`app/websocket_orders.py:18-101`)
- Manages WebSocket connections per account
- Broadcasts order updates to connected clients
- Handles connection lifecycle (connect, disconnect, cleanup)

### API Endpoint

**WebSocket Connection**: `GET /advanced/ws/orders/{account_id}`

**Example (JavaScript):**
```javascript
const ws = new WebSocket('ws://localhost:8080/advanced/ws/orders/primary');

ws.onopen = () => {
    console.log('Connected to order stream');
};

ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    console.log('Order update:', data);

    switch(data.type) {
        case 'connected':
            console.log('Welcome message received');
            break;
        case 'order_update':
            console.log('Order status:', data.data);
            break;
    }
};

ws.onerror = (error) => {
    console.error('WebSocket error:', error);
};

ws.onclose = () => {
    console.log('Disconnected from order stream');
};

// Keep connection alive
setInterval(() => {
    if (ws.readyState === WebSocket.OPEN) {
        ws.send('ping');
    }
}, 30000);
```

**Example (Python):**
```python
import asyncio
import websockets
import json

async def stream_orders():
    uri = "ws://localhost:8080/advanced/ws/orders/primary"

    async with websockets.connect(uri) as websocket:
        # Receive welcome message
        welcome = await websocket.recv()
        print(f"Connected: {welcome}")

        # Listen for order updates
        while True:
            try:
                message = await websocket.recv()
                data = json.loads(message)
                print(f"Order update: {data}")
            except websockets.ConnectionClosed:
                print("Connection closed")
                break

asyncio.run(stream_orders())
```

### Message Format

**Welcome Message:**
```json
{
    "type": "connected",
    "account_id": "primary",
    "timestamp": "2025-10-31T08:42:13.585Z"
}
```

**Order Update Message:**
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

**Task Status Update:**
```json
{
    "type": "order_update",
    "account_id": "primary",
    "data": {
        "event": "task_status",
        "task_id": "task_abc123",
        "status": "completed",
        "result": {...}
    },
    "timestamp": "2025-10-31T09:15:30.123Z"
}
```

### Connection Management

**Get Connection Stats**: `GET /advanced/ws/stats`
```bash
curl http://localhost:8080/advanced/ws/stats
```

**Response:**
```json
{
    "total_connections": 5
}
```

### Best Practices

1. **Heartbeat/Keepalive**: Send ping messages every 30 seconds to keep connection alive
2. **Reconnection Logic**: Implement exponential backoff for reconnections
3. **Error Handling**: Always handle connection errors and closed events
4. **Message Validation**: Validate message structure before processing

### Example Integration

```typescript
// TypeScript/React WebSocket Hook
import { useEffect, useState } from 'react';

interface OrderUpdate {
    type: string;
    account_id: string;
    data: any;
    timestamp: string;
}

export const useOrderStream = (accountId: string) => {
    const [orders, setOrders] = useState<OrderUpdate[]>([]);
    const [connected, setConnected] = useState(false);

    useEffect(() => {
        const ws = new WebSocket(
            `ws://localhost:8080/advanced/ws/orders/${accountId}`
        );

        ws.onopen = () => setConnected(true);

        ws.onmessage = (event) => {
            const update: OrderUpdate = JSON.parse(event.data);

            if (update.type === 'order_update') {
                setOrders(prev => [...prev, update]);
            }
        };

        ws.onclose = () => setConnected(false);

        // Cleanup on unmount
        return () => ws.close();
    }, [accountId]);

    return { orders, connected };
};
```

---

## 2. Webhook Notifications

**Location**: `app/webhooks.py`, `app/routes_advanced.py`

### Overview
Webhook notifications deliver HTTP POST callbacks to registered URLs when order events occur, enabling event-driven architectures and third-party integrations.

### Architecture

```
┌──────────────────┐      Event Occurs      ┌──────────────────┐
│ OrderExecutor    │ ────────────────────► │ WebhookManager   │
│                  │                         │                  │
└──────────────────┘                         └──────────────────┘
                                                     │
                                                     │ HTTP POST
                                                     ▼
                                            ┌──────────────────┐
                                            │  Your Webhook    │
                                            │  Endpoint        │
                                            └──────────────────┘
```

### Implementation Details

**WebhookManager Class** (`app/webhooks.py:29-100`)
- Manages webhook subscriptions
- Delivers HTTP POST notifications asynchronously
- Supports webhook authentication via secrets

### API Endpoints

#### Create Webhook
**POST** `/advanced/webhooks`

**Request:**
```json
{
    "url": "https://your-domain.com/webhook",
    "account_id": "primary",
    "events": ["order_placed", "order_completed", "order_failed"],
    "secret": "your-secret-key"
}
```

**Response:**
```json
{
    "webhook_id": "978b941d-1339-4158-b0aa-43f5467717d1",
    "url": "https://your-domain.com/webhook",
    "account_id": "primary",
    "events": ["order_placed", "order_completed", "order_failed"],
    "active": true,
    "created_at": "2025-10-31T08:42:47.598360Z"
}
```

**Example:**
```bash
curl -X POST http://localhost:8080/advanced/webhooks \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://your-domain.com/webhook",
    "account_id": "primary",
    "events": ["order_completed", "order_failed"],
    "secret": "my-secret-123"
  }'
```

#### List Webhooks
**GET** `/advanced/webhooks?account_id={account_id}`

**Example:**
```bash
# List all webhooks
curl http://localhost:8080/advanced/webhooks

# List webhooks for specific account
curl http://localhost:8080/advanced/webhooks?account_id=primary
```

**Response:**
```json
[
    {
        "webhook_id": "978b941d-1339-4158-b0aa-43f5467717d1",
        "url": "https://your-domain.com/webhook",
        "account_id": "primary",
        "events": ["order_completed", "order_failed"],
        "active": true,
        "created_at": "2025-10-31T08:42:47.598360Z"
    }
]
```

#### Delete Webhook
**DELETE** `/advanced/webhooks/{webhook_id}`

**Example:**
```bash
curl -X DELETE http://localhost:8080/advanced/webhooks/978b941d-1339-4158-b0aa-43f5467717d1
```

**Response:**
```json
{
    "success": true,
    "webhook_id": "978b941d-1339-4158-b0aa-43f5467717d1"
}
```

### Webhook Payload Format

When an event occurs, the webhook endpoint receives an HTTP POST request:

**Headers:**
```
Content-Type: application/json
X-Webhook-Secret: your-secret-key
```

**Body:**
```json
{
    "event": "order_completed",
    "account_id": "primary",
    "data": {
        "order_id": "230405000123456",
        "status": "COMPLETE",
        "filled_quantity": 50,
        "average_price": 19500.25,
        "transaction_type": "BUY",
        "tradingsymbol": "NIFTY25NOVFUT"
    },
    "timestamp": "2025-10-31T09:15:30.123Z"
}
```

### Available Events

- `order_placed` - Order successfully placed
- `order_completed` - Order fully filled
- `order_failed` - Order placement or execution failed
- `order_cancelled` - Order cancelled
- `order_rejected` - Order rejected by exchange

### Implementing a Webhook Server

**Example (Express.js):**
```javascript
const express = require('express');
const crypto = require('crypto');

const app = express();
app.use(express.json());

// Verify webhook signature
function verifySignature(payload, secret, signature) {
    const expectedSignature = crypto
        .createHmac('sha256', secret)
        .update(JSON.stringify(payload))
        .digest('hex');

    return signature === expectedSignature;
}

app.post('/webhook', (req, res) => {
    const secret = req.headers['x-webhook-secret'];
    const payload = req.body;

    // Verify secret (if required)
    if (secret !== 'my-secret-123') {
        return res.status(401).send('Unauthorized');
    }

    console.log('Webhook received:', payload);

    switch(payload.event) {
        case 'order_completed':
            console.log('Order completed:', payload.data.order_id);
            // Handle order completion
            break;

        case 'order_failed':
            console.log('Order failed:', payload.data);
            // Handle order failure
            break;
    }

    res.status(200).send('OK');
});

app.listen(3000, () => {
    console.log('Webhook server listening on port 3000');
});
```

**Example (FastAPI/Python):**
```python
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

app = FastAPI()

class WebhookPayload(BaseModel):
    event: str
    account_id: str
    data: dict
    timestamp: str

@app.post("/webhook")
async def handle_webhook(
    payload: WebhookPayload,
    x_webhook_secret: str = Header(None)
):
    # Verify secret
    if x_webhook_secret != "my-secret-123":
        raise HTTPException(status_code=401, detail="Unauthorized")

    print(f"Webhook received: {payload.event}")

    if payload.event == "order_completed":
        print(f"Order completed: {payload.data}")
        # Handle order completion
    elif payload.event == "order_failed":
        print(f"Order failed: {payload.data}")
        # Handle order failure

    return {"status": "ok"}
```

### Best Practices

1. **Idempotency**: Handle duplicate webhook deliveries gracefully
2. **Timeouts**: Respond quickly (< 5 seconds) to avoid retries
3. **Secret Verification**: Always verify the webhook secret
4. **Error Handling**: Log errors but return 200 OK to prevent retries
5. **Async Processing**: Queue webhook data for async processing if needed

---

## 3. Batch Order Execution

**Location**: `app/batch_orders.py`, `app/routes_advanced.py`

### Overview
Batch order execution allows submitting multiple orders atomically with optional rollback on failure, ensuring all-or-nothing execution semantics.

### Architecture

```
┌──────────────┐                ┌─────────────────────┐
│   Client     │   Batch Order  │ BatchOrderExecutor  │
│              │ ──────────────► │                     │
└──────────────┘                └─────────────────────┘
                                          │
                                          │ For each order
                                          ▼
                                ┌─────────────────────┐
                                │  OrderExecutor      │
                                │  submit_task()      │
                                └─────────────────────┘
                                          │
                                          │ On failure & rollback=true
                                          ▼
                                ┌─────────────────────┐
                                │  Cancel all orders  │
                                │  (rollback)         │
                                └─────────────────────┘
```

### API Endpoint

**POST** `/advanced/batch-orders`

**Request:**
```json
{
    "orders": [
        {
            "exchange": "NFO",
            "tradingsymbol": "NIFTY25NOVFUT",
            "transaction_type": "BUY",
            "quantity": 50,
            "product": "NRML",
            "order_type": "MARKET",
            "variety": "regular"
        },
        {
            "exchange": "NFO",
            "tradingsymbol": "BANKNIFTY25NOVFUT",
            "transaction_type": "BUY",
            "quantity": 25,
            "product": "NRML",
            "order_type": "LIMIT",
            "price": 45500.0,
            "variety": "regular"
        }
    ],
    "account_id": "primary",
    "rollback_on_failure": true
}
```

**Response:**
```json
{
    "batch_id": "550e8400-e29b-41d4-a716-446655440000",
    "success": true,
    "total_orders": 2,
    "succeeded": 2,
    "failed": 0,
    "created_at": "2025-10-31T09:15:00.000Z",
    "completed_at": "2025-10-31T09:15:05.123Z",
    "error": null
}
```

### Request Parameters

**BatchOrdersRequest:**
- `orders` (required): List of order requests
- `account_id` (default: "primary"): Trading account to use
- `rollback_on_failure` (default: true): Cancel all orders if any fails

**BatchOrderRequest (single order):**
- `exchange` (required): Exchange (NSE, NFO, BSE, etc.)
- `tradingsymbol` (required): Trading symbol
- `transaction_type` (required): BUY or SELL
- `quantity` (required): Order quantity
- `product` (required): MIS, NRML, CNC
- `order_type` (required): MARKET, LIMIT, SL, SL-M
- `variety` (default: "regular"): Order variety
- `price` (optional): Limit price (required for LIMIT orders)
- `trigger_price` (optional): Trigger price (required for SL orders)
- `validity` (default: "DAY"): Order validity
- `tag` (optional): Custom tag

### Examples

**Example 1: Market Orders**
```bash
curl -X POST http://localhost:8080/advanced/batch-orders \
  -H "Content-Type: application/json" \
  -d '{
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
            "order_type": "MARKET"
        }
    ],
    "account_id": "primary",
    "rollback_on_failure": true
  }'
```

**Example 2: Limit Orders with Rollback**
```python
import requests

batch_request = {
    "orders": [
        {
            "exchange": "NFO",
            "tradingsymbol": "NIFTY25NOVFUT",
            "transaction_type": "BUY",
            "quantity": 50,
            "product": "NRML",
            "order_type": "LIMIT",
            "price": 19500.0
        },
        {
            "exchange": "NFO",
            "tradingsymbol": "NIFTY25NOVFUT",
            "transaction_type": "SELL",
            "quantity": 50,
            "product": "NRML",
            "order_type": "LIMIT",
            "price": 19600.0
        }
    ],
    "account_id": "primary",
    "rollback_on_failure": True
}

response = requests.post(
    "http://localhost:8080/advanced/batch-orders",
    json=batch_request
)

result = response.json()
print(f"Batch {result['batch_id']}: {result['succeeded']}/{result['total_orders']} succeeded")
```

### Rollback Behavior

**With `rollback_on_failure: true` (default):**
1. Orders are executed sequentially
2. If any order fails, all previously successful orders are cancelled
3. Response indicates failure with error details

**With `rollback_on_failure: false`:**
1. Orders are executed sequentially
2. Failures are logged but execution continues
3. Response includes partial success details

**Rollback Example Response:**
```json
{
    "batch_id": "550e8400-e29b-41d4-a716-446655440000",
    "success": false,
    "total_orders": 3,
    "succeeded": 0,
    "failed": 3,
    "created_at": "2025-10-31T09:15:00.000Z",
    "completed_at": "2025-10-31T09:15:02.456Z",
    "error": "Order 2 failed: Insufficient funds. Rolled back 2 orders."
}
```

### Use Cases

1. **Spread Orders**: Buy and sell simultaneously (pairs trading)
2. **Multi-Leg Strategies**: Iron Condor, Butterfly, etc.
3. **Portfolio Rebalancing**: Multiple order execution with atomicity
4. **Risk Management**: All-or-nothing execution to avoid partial fills

### Best Practices

1. **Order Count**: Keep batches small (< 10 orders) for faster execution
2. **Rollback Strategy**: Use `rollback_on_failure: true` for critical strategies
3. **Error Handling**: Always check the `success` field before processing
4. **Tagging**: Use custom tags to track batch orders
5. **Monitoring**: Monitor `succeeded` vs `failed` counts

---

## 4. Database Task Persistence

**Location**: `app/task_persistence.py`

### Overview
Database task persistence ensures order tasks survive service restarts by storing them in PostgreSQL. Pending tasks are automatically recovered on startup.

### Architecture

```
┌──────────────────┐         Save Task        ┌──────────────────┐
│ OrderExecutor    │ ─────────────────────────► │   TaskStore      │
│                  │                            │  (PostgreSQL)    │
│                  │ ◄───────────────────────── │                  │
└──────────────────┘      Load Pending         └──────────────────┘
        │                                               │
        │                                               │
        │  On Restart                                  │
        └───────────────────────────────────────────────┘
                     Resume pending tasks
```

### Database Schema

**Table: `order_tasks`**
```sql
CREATE TABLE IF NOT EXISTS order_tasks (
    task_id TEXT PRIMARY KEY,
    idempotency_key TEXT NOT NULL UNIQUE,
    operation TEXT NOT NULL,
    params JSONB NOT NULL,
    status TEXT NOT NULL,
    attempts INTEGER DEFAULT 0,
    max_attempts INTEGER DEFAULT 5,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    last_error TEXT,
    result JSONB,
    account_id TEXT NOT NULL
);

CREATE INDEX idx_order_tasks_status
ON order_tasks(status)
WHERE status IN ('pending', 'retrying');

CREATE INDEX idx_order_tasks_account
ON order_tasks(account_id);
```

### TaskStore API

**Initialize Database:**
```python
from app.task_persistence import TaskStore

# Create store
task_store = TaskStore(connection_string="postgresql://user:pass@host/db")

# Initialize (creates table and indexes)
await task_store.initialize()
```

**Save Task:**
```python
from app.order_executor import OrderTask, TaskStatus

task = OrderTask(
    task_id="task_123",
    idempotency_key="idempotency_123",
    operation="place_order",
    params={"exchange": "NFO", "tradingsymbol": "NIFTY25NOVFUT", ...},
    status=TaskStatus.PENDING,
    account_id="primary"
)

await task_store.save(task)
```

**Load Pending Tasks (on restart):**
```python
# Automatically called on service startup
pending_tasks = await task_store.load_pending()

for task in pending_tasks:
    print(f"Resuming task: {task.task_id} - {task.operation}")
    # OrderExecutor will resume execution
```

**Get Single Task:**
```python
task = await task_store.get("task_123")
if task:
    print(f"Task status: {task.status.value}")
```

**Cleanup Old Tasks:**
```python
# Delete completed tasks older than 7 days
deleted_count = await task_store.delete_old_completed(days=7)
print(f"Deleted {deleted_count} old tasks")
```

### Task Lifecycle

```
┌─────────┐     submit_task()     ┌─────────┐     execute()      ┌───────────┐
│ PENDING │ ───────────────────► │ RUNNING │ ────────────────► │ COMPLETED │
└─────────┘                       └─────────┘                    └───────────┘
     │                                 │                                │
     │                                 │ on error                       │
     │                                 ▼                                │
     │                            ┌──────────┐      max retries         │
     │                            │ RETRYING │ ────────────────────────► │
     │                            └──────────┘                           │
     │                                 │                                │
     │                                 │ max attempts exceeded          │
     │                                 ▼                                │
     │                            ┌─────────────┐                       │
     └───────────────────────────►│ DEAD_LETTER │◄──────────────────────┘
                                  └─────────────┘
                                         │
                                         │ manual intervention
                                         ▼
                                   Investigate & retry
```

### Integration with OrderExecutor

The OrderExecutor automatically integrates with TaskStore:

**Automatic Persistence:**
```python
# When task is submitted
task = await executor.submit_task("place_order", params, account_id)
# ↓ Automatically saved to database

# On status change
task.status = TaskStatus.COMPLETED
# ↓ Automatically updated in database
```

**Automatic Recovery on Restart:**
```python
# On service startup (in lifespan)
await executor.start_worker(client_factory)
# ↓ Loads pending tasks from database
# ↓ Resumes execution automatically
```

### Monitoring Tasks

**Query Pending Tasks:**
```sql
SELECT task_id, operation, status, attempts, created_at, last_error
FROM order_tasks
WHERE status IN ('pending', 'retrying')
ORDER BY created_at;
```

**Query Failed Tasks:**
```sql
SELECT task_id, operation, attempts, last_error, created_at
FROM order_tasks
WHERE status = 'dead_letter'
ORDER BY updated_at DESC
LIMIT 10;
```

**Task Stats:**
```sql
SELECT
    status,
    COUNT(*) as count,
    AVG(attempts) as avg_attempts
FROM order_tasks
GROUP BY status;
```

### Configuration

**Environment Variables:**
```bash
# PostgreSQL connection
DATABASE_URL=postgresql://user:password@localhost:5432/tradingdb

# Task retention (days)
TASK_RETENTION_DAYS=7

# Cleanup schedule (cron format)
TASK_CLEANUP_SCHEDULE="0 2 * * *"  # 2 AM daily
```

### Best Practices

1. **Idempotency**: Always use unique idempotency keys
2. **Cleanup**: Schedule regular cleanup of old completed tasks
3. **Monitoring**: Monitor dead letter queue for failures
4. **Retries**: Configure appropriate max_attempts per operation
5. **Database**: Use connection pooling for better performance

---

## 5. Testing Guide

### Prerequisites
```bash
# Ensure service is running
docker-compose up -d ticker-service

# Check health
curl http://localhost:8080/health
```

### Test 1: Prometheus Metrics
```bash
curl http://localhost:8080/metrics | head -30
```

**Expected Output:**
```
# HELP python_gc_objects_collected_total Objects collected during gc
# TYPE python_gc_objects_collected_total counter
python_gc_objects_collected_total{generation="0"} 10411.0
...
```

### Test 2: WebSocket Connection
```javascript
// Browser console test
const ws = new WebSocket('ws://localhost:8080/advanced/ws/orders/primary');
ws.onopen = () => console.log('Connected');
ws.onmessage = (e) => console.log('Message:', e.data);
ws.onerror = (e) => console.error('Error:', e);
```

**Expected Output:**
```
Connected
Message: {"type":"connected","account_id":"primary","timestamp":"2025-10-31T..."}
```

### Test 3: Webhook Creation
```bash
curl -X POST http://localhost:8080/advanced/webhooks \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://webhook.site/unique-id",
    "account_id": "primary",
    "events": ["order_completed"],
    "secret": "test-secret"
  }'
```

**Expected Output:**
```json
{
  "webhook_id": "...",
  "url": "https://webhook.site/unique-id",
  "active": true,
  ...
}
```

### Test 4: Batch Order Execution
```bash
# Note: This will place real orders! Use with caution
curl -X POST http://localhost:8080/advanced/batch-orders \
  -H "Content-Type: application/json" \
  -d '{
    "orders": [
        {
            "exchange": "NFO",
            "tradingsymbol": "NIFTY25NOVFUT",
            "transaction_type": "BUY",
            "quantity": 1,
            "product": "MIS",
            "order_type": "MARKET"
        }
    ],
    "account_id": "primary",
    "rollback_on_failure": true
  }'
```

### Test 5: Database Persistence
```bash
# Check pending tasks in database
docker exec -it tv-db psql -U tradinguser -d tradingdb -c \
  "SELECT task_id, operation, status FROM order_tasks WHERE status='pending';"
```

---

## 6. Troubleshooting

### WebSocket Issues

**Issue**: Connection refused
```
Error: WebSocket connection to 'ws://localhost:8080/advanced/ws/orders/primary' failed
```

**Solution:**
1. Check service is running: `docker ps | grep tv-ticker`
2. Check logs: `docker logs tv-ticker`
3. Verify port mapping in docker-compose.yml

**Issue**: Messages not received
```
Connected but no messages
```

**Solution:**
1. Verify order events are being triggered
2. Check WebSocket is subscribed to correct account_id
3. Check logs for broadcast errors: `docker logs tv-ticker | grep broadcast`

### Webhook Issues

**Issue**: Webhooks not delivered
```
Webhook registered but no HTTP requests received
```

**Solution:**
1. Check webhook URL is publicly accessible
2. Verify webhook is active: `GET /advanced/webhooks`
3. Check logs: `docker logs tv-ticker | grep webhook`
4. Test webhook URL manually: `curl -X POST <your-url> -d '{"test": true}'`

**Issue**: Webhook authentication failed
```
401 Unauthorized
```

**Solution:**
1. Verify secret matches in both registration and verification
2. Check header name: `X-Webhook-Secret`

### Batch Order Issues

**Issue**: Batch order fails immediately
```json
{
  "success": false,
  "error": "Order 0 failed: ..."
}
```

**Solution:**
1. Check order parameters (tradingsymbol, quantity, price)
2. Verify account has sufficient funds
3. Check market hours and instrument liquidity
4. Review logs: `docker logs tv-ticker | grep batch`

**Issue**: Rollback not working
```
Orders placed but not cancelled on failure
```

**Solution:**
1. Verify `rollback_on_failure: true` in request
2. Check OrderExecutor has cancel_order support
3. Review batch execution logs

### Database Persistence Issues

**Issue**: Tasks not persisted
```
Service restart loses all pending tasks
```

**Solution:**
1. Check PostgreSQL connection: `docker exec tv-ticker env | grep DATABASE_URL`
2. Verify table exists: `docker exec -it tv-db psql -U tradinguser -d tradingdb -c "\dt"`
3. Check TaskStore initialization in logs

**Issue**: Database connection errors
```
asyncpg.exceptions.InvalidPasswordError
```

**Solution:**
1. Verify DATABASE_URL in environment
2. Check PostgreSQL is running: `docker ps | grep tv-db`
3. Test connection: `docker exec tv-db psql -U tradinguser -d tradingdb -c "SELECT 1"`

### General Issues

**Issue**: High memory usage
```
Container using > 2GB RAM
```

**Solution:**
1. Monitor WebSocket connections: `GET /advanced/ws/stats`
2. Cleanup old tasks: Schedule `delete_old_completed()`
3. Review logs for memory leaks

**Issue**: Service degraded
```json
{"status": "degraded", ...}
```

**Solution:**
1. Check health endpoint: `GET /health`
2. Verify all dependencies (Redis, PostgreSQL, Kite API)
3. Review logs: `docker logs tv-ticker --tail 100`

---

## Summary

**Implemented Features:**
1. ✅ **WebSocket Order Streaming** - Real-time bidirectional order updates
2. ✅ **Webhook Notifications** - HTTP callbacks for order events
3. ✅ **Batch Order Execution** - Atomic multi-order placement with rollback
4. ✅ **Database Task Persistence** - Survive restarts with PostgreSQL storage

**Benefits:**
- **Real-time Communication**: WebSocket eliminates polling overhead
- **Event-Driven Architecture**: Webhooks enable third-party integrations
- **Atomic Operations**: Batch orders ensure all-or-nothing execution
- **Reliability**: Database persistence prevents task loss on restarts

**Testing Status:**
- All endpoints tested and verified ✅
- No errors in production logs ✅
- Docker deployment successful ✅

**Next Steps:**
1. Monitor production metrics via `/metrics` endpoint
2. Set up webhook integrations for alerting
3. Schedule database cleanup tasks
4. Implement remaining improvements (Strategy Templates, Paper Trading, etc.)

---

**Document Version**: 1.0
**Last Updated**: 2025-10-31
**Author**: Generated with Claude Code
