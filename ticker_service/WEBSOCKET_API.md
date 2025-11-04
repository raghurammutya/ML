# Ticker Service WebSocket API

## Overview

The Ticker Service provides a secure WebSocket API for real-time market data streaming. All authenticated users share the same data stream (broadcast model), with load distributed across multiple Kite trading accounts internally.

## Architecture

```
Multiple Users (JWT authenticated)
    ↓
WebSocket: /ws/ticks
    ↓
Ticker Service (shared infrastructure)
    ↓
Redis Pub/Sub (ticks:*)
    ↓
Kite API (via WebSocket pool)
```

### Key Features

- **JWT Authentication**: Required for all WebSocket connections
- **Shared Data Model**: All users can subscribe to any instrument
- **Real-time Streaming**: Tick data broadcast from Redis Pub/Sub
- **Scalable**: Handles multiple concurrent connections
- **Secure**: Not exposed externally in production (Docker internal network)

## WebSocket Endpoint

### Connection

**URL**: `ws://localhost:8080/ws/ticks?token=<JWT_TOKEN>`

**Authentication**: JWT token from user_service as query parameter

**Example** (JavaScript):
```javascript
const token = "eyJ0eXAiOiJKV1QiLCJhbGc..."; // Get from user_service login
const ws = new WebSocket(`ws://localhost:8080/ws/ticks?token=${token}`);

ws.onopen = () => {
    console.log("Connected to ticker service");
};

ws.onmessage = (event) => {
    const message = JSON.parse(event.data);
    console.log("Received:", message);
};

ws.onerror = (error) => {
    console.error("WebSocket error:", error);
};

ws.onclose = (event) => {
    console.log("Disconnected:", event.code, event.reason);
};
```

### Message Protocol

#### Client → Server Messages

**Subscribe to instruments:**
```json
{
    "action": "subscribe",
    "tokens": [256265, 260105, 264969]
}
```

**Unsubscribe from instruments:**
```json
{
    "action": "unsubscribe",
    "tokens": [256265]
}
```

**Ping (keep-alive):**
```json
{
    "action": "ping"
}
```

#### Server → Client Messages

**Connection Confirmation:**
```json
{
    "type": "connected",
    "connection_id": "140234567890_1730691234.567",
    "user": {
        "user_id": "user_123",
        "email": "user@example.com",
        "name": "John Doe"
    },
    "timestamp": "2025-11-04T06:10:00.000Z"
}
```

**Subscription Confirmation:**
```json
{
    "type": "subscribed",
    "tokens": [256265, 260105, 264969],
    "total": 3
}
```

**Unsubscription Confirmation:**
```json
{
    "type": "unsubscribed",
    "tokens": [256265],
    "total": 2
}
```

**Tick Data:**
```json
{
    "type": "tick",
    "data": {
        "instrument_token": 256265,
        "tradingsymbol": "RELIANCE",
        "last_price": 2456.75,
        "volume": 1234567,
        "buy_quantity": 50000,
        "sell_quantity": 45000,
        "change": 12.50,
        "last_trade_time": "2025-11-04T06:10:05.123Z",
        ...
    }
}
```

**Pong (response to ping):**
```json
{
    "type": "pong"
}
```

**Error:**
```json
{
    "type": "error",
    "message": "Invalid token or action"
}
```

## Example Usage

### Python Client

```python
import asyncio
import json
import websockets

async def ticker_client(token):
    uri = f"ws://localhost:8080/ws/ticks?token={token}"

    async with websockets.connect(uri) as websocket:
        # Connection established
        message = await websocket.recv()
        print(f"Connected: {message}")

        # Subscribe to instruments
        subscribe_msg = {
            "action": "subscribe",
            "tokens": [256265, 260105]  # RELIANCE, HDFCBANK
        }
        await websocket.send(json.dumps(subscribe_msg))

        # Receive confirmation
        response = await websocket.recv()
        print(f"Subscribed: {response}")

        # Listen for ticks
        while True:
            try:
                message = await websocket.recv()
                data = json.loads(message)

                if data["type"] == "tick":
                    tick = data["data"]
                    print(f"Tick: {tick['tradingsymbol']} @ {tick['last_price']}")

            except websockets.ConnectionClosed:
                print("Connection closed")
                break

# Run client
token = "your_jwt_token_here"
asyncio.run(ticker_client(token))
```

### JavaScript/TypeScript Client

```typescript
class TickerClient {
    private ws: WebSocket | null = null;
    private subscriptions: Set<number> = new Set();

    connect(token: string) {
        this.ws = new WebSocket(`ws://localhost:8080/ws/ticks?token=${token}`);

        this.ws.onopen = () => {
            console.log("Connected to ticker service");
        };

        this.ws.onmessage = (event) => {
            const message = JSON.parse(event.data);
            this.handleMessage(message);
        };

        this.ws.onerror = (error) => {
            console.error("WebSocket error:", error);
        };

        this.ws.onclose = (event) => {
            console.log("Disconnected:", event.code, event.reason);
            // Implement reconnection logic here
        };
    }

    subscribe(tokens: number[]) {
        if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
            console.error("WebSocket not connected");
            return;
        }

        const message = {
            action: "subscribe",
            tokens: tokens
        };

        this.ws.send(JSON.stringify(message));
        tokens.forEach(token => this.subscriptions.add(token));
    }

    unsubscribe(tokens: number[]) {
        if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
            console.error("WebSocket not connected");
            return;
        }

        const message = {
            action: "unsubscribe",
            tokens: tokens
        };

        this.ws.send(JSON.stringify(message));
        tokens.forEach(token => this.subscriptions.delete(token));
    }

    private handleMessage(message: any) {
        switch (message.type) {
            case "connected":
                console.log("Connected as:", message.user.email);
                break;

            case "subscribed":
                console.log("Subscribed to:", message.tokens);
                break;

            case "tick":
                this.onTick(message.data);
                break;

            case "error":
                console.error("Server error:", message.message);
                break;
        }
    }

    private onTick(tickData: any) {
        // Override this method to handle tick data
        console.log("Tick:", tickData);
    }

    disconnect() {
        if (this.ws) {
            this.ws.close();
        }
    }
}

// Usage
const client = new TickerClient();
client.connect(jwtToken);

// Subscribe to instruments
client.subscribe([256265, 260105]);  // RELIANCE, HDFCBANK
```

## Security

### Authentication

- **Required**: Valid JWT token from user_service
- **Token Format**: Bearer token in query parameter
- **Validation**: RSA256 signature verification against user_service JWKS
- **Token Claims**: `sub` (user_id), `email`, `name`, `roles`, `permissions`

### Network Security (Production)

When running in Docker:
- Ticker service is on **internal network only** (`tv-network`)
- **NOT exposed** to external network
- Access only via:
  - Backend service (internal)
  - Nginx reverse proxy → Backend → Ticker (for authenticated users)

### Authorization Model

- **Authentication**: Required (must have valid JWT)
- **Authorization**: All authenticated users can subscribe to any instruments
- **Data Sharing**: Same tick data broadcast to all subscribers (shared model)
- **Rate Limiting**: Applied at API gateway/backend level

## Monitoring

### WebSocket Statistics

**Endpoint**: `GET /ws/stats`

**Response:**
```json
{
    "active_connections": 5,
    "total_subscriptions": 47,
    "unique_tokens_subscribed": 15,
    "connections": [
        {
            "connection_id": "140234567890_1730691234.567",
            "user_id": "user_123",
            "subscriptions": 10,
            "connected_at": "2025-11-04T06:10:00.000Z"
        }
    ]
}
```

### Health Check

**Endpoint**: `GET /health`

Includes ticker service status and WebSocket service status.

## Error Handling

### Connection Errors

**1. Invalid Token**
```
WebSocket closes with code 1008
Reason: "Authentication failed: <error detail>"
```

**2. Missing Token**
```
WebSocket closes with code 1008
Reason: "Missing authentication token"
```

**3. Expired Token**
```
WebSocket closes with code 1008
Reason: "Token expired"
```

### Runtime Errors

**Invalid Message Format:**
```json
{
    "type": "error",
    "message": "Invalid JSON message"
}
```

**Unknown Action:**
```json
{
    "type": "error",
    "message": "Unknown action: <action>"
}
```

**Invalid Tokens Format:**
```json
{
    "type": "error",
    "message": "tokens must be a list of instrument tokens"
}
```

## Best Practices

### Reconnection

Implement exponential backoff for reconnection:

```javascript
class ReconnectingTickerClient {
    private reconnectAttempts = 0;
    private maxReconnectDelay = 30000; // 30 seconds

    private getReconnectDelay(): number {
        const delay = Math.min(
            1000 * Math.pow(2, this.reconnectAttempts),
            this.maxReconnectDelay
        );
        this.reconnectAttempts++;
        return delay;
    }

    private reconnect() {
        const delay = this.getReconnectDelay();
        console.log(`Reconnecting in ${delay}ms...`);

        setTimeout(() => {
            this.connect(this.token);
        }, delay);
    }
}
```

### Heartbeat/Keep-Alive

Send periodic pings to keep connection alive:

```javascript
setInterval(() => {
    if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ action: "ping" }));
    }
}, 30000); // Every 30 seconds
```

### Subscription Management

- Subscribe to instruments in batches
- Unsubscribe when no longer needed
- Track active subscriptions client-side
- Resubscribe on reconnection

## Troubleshooting

### Connection Issues

1. **"Authentication failed"**
   - Verify JWT token is valid
   - Check token hasn't expired
   - Ensure token is from user_service

2. **"Connection timeout"**
   - Check network connectivity
   - Verify ticker service is running
   - Check firewall rules

3. **"No tick data received"**
   - Verify subscriptions were successful
   - Check if market is open
   - Monitor `/ws/stats` endpoint

### Performance

- **High latency**: Check network conditions, Redis performance
- **Missed ticks**: Increase client buffer size, optimize message processing
- **Connection drops**: Implement reconnection with exponential backoff

## Integration with User Service

### Getting JWT Token

**1. User Login:**
```bash
POST http://localhost:8001/v1/auth/login
Content-Type: application/json

{
    "email": "user@example.com",
    "password": "secure_password"
}
```

**Response:**
```json
{
    "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
    "token_type": "bearer",
    "expires_in": 3600,
    "user": {
        "user_id": "user_123",
        "email": "user@example.com"
    }
}
```

**2. Use Token for WebSocket:**
```javascript
const ws = new WebSocket(
    `ws://localhost:8080/ws/ticks?token=${response.access_token}`
);
```

## Production Deployment

### Docker Configuration (Recommended)

```yaml
# docker-compose.yml
ticker-service:
  build: ./ticker_service
  # NO external ports - internal only
  networks:
    - tv-network
  environment:
    - USER_SERVICE_URL=http://user-service:8001
    - REDIS_URL=redis://redis:6379/0
```

### Security Checklist

- [ ] JWT authentication enabled
- [ ] Ticker service NOT exposed externally
- [ ] Redis requires authentication
- [ ] TLS/SSL for production (via Nginx)
- [ ] Rate limiting configured
- [ ] Monitoring and alerting set up
- [ ] Connection limits configured

## Support

For issues or questions:
- Check logs: `logs/ticker_service.log`
- Monitor health: `GET /health`
- Check WebSocket stats: `GET /ws/stats`
- View metrics: `GET /metrics` (Prometheus format)
