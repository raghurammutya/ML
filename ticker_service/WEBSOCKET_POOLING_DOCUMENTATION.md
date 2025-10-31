# WebSocket Connection Pooling

## Overview

The ticker service now implements **automatic WebSocket connection pooling** to scale beyond Kite Connect's 1000 instrument limit per WebSocket connection. The pool automatically creates additional connections as needed when subscriptions exceed capacity.

## Key Features

- **Automatic Scaling**: Creates new WebSocket connections automatically when hitting the 1000 instrument limit
- **Load Balancing**: Distributes subscriptions evenly across available connections
- **Connection Health Monitoring**: Tracks connection status and capacity utilization
- **Automatic Reconnection**: Each connection in the pool handles reconnection independently
- **Unified API**: No changes required in existing subscription code - pooling is transparent

## Architecture

### Components

1. **KiteWebSocketPool** (`app/kite/websocket_pool.py`)
   - Manages multiple KiteTicker WebSocket connections
   - Handles subscription routing and load balancing
   - Tracks connection health and statistics

2. **WebSocketConnection** (dataclass)
   - Represents a single WebSocket connection in the pool
   - Tracks subscribed tokens and available capacity
   - Manages connection state (connected/disconnected)

3. **KiteClient Integration** (`app/kite/client.py`)
   - Modified to use WebSocketPool instead of single KiteTicker
   - Transparent pool initialization on first subscription
   - Maintains same public API for backward compatibility

## Configuration

### Environment Variables / Settings

```python
# Maximum instruments per WebSocket connection (default: 1000)
max_instruments_per_ws_connection: int = 1000
```

Add to `.env` file:
```bash
MAX_INSTRUMENTS_PER_WS_CONNECTION=1000  # Can be adjusted if needed
```

Or in `config.py`:
```python
class Settings(BaseSettings):
    max_instruments_per_ws_connection: int = Field(
        default=1000,
        description="Maximum instruments per WebSocket connection"
    )
```

## Usage

### Basic Usage (Transparent)

No code changes required! Existing subscription code automatically uses pooling:

```python
# This automatically uses pooling if >1000 instruments
await client.subscribe_tokens(
    tokens=instrument_tokens,  # Can be >1000
    on_ticks=tick_handler,
    on_error=error_handler
)
```

### Monitoring Pool Statistics

#### Get All Accounts' Pool Stats

```bash
GET /advanced/websocket-pool/stats
```

Response:
```json
{
    "total_accounts": 1,
    "accounts": {
        "primary": {
            "account_id": "primary",
            "total_connections": 3,
            "total_target_tokens": 2500,
            "total_subscribed_tokens": 2500,
            "max_instruments_per_connection": 1000,
            "total_capacity": 3000,
            "connections": [
                {
                    "connection_id": 0,
                    "connected": true,
                    "subscribed_tokens": 1000,
                    "capacity": 1000,
                    "available_capacity": 0,
                    "utilization_percent": 100.0
                },
                {
                    "connection_id": 1,
                    "connected": true,
                    "subscribed_tokens": 1000,
                    "capacity": 1000,
                    "available_capacity": 0,
                    "utilization_percent": 100.0
                },
                {
                    "connection_id": 2,
                    "connected": true,
                    "subscribed_tokens": 500,
                    "capacity": 1000,
                    "available_capacity": 500,
                    "utilization_percent": 50.0
                }
            ],
            "statistics": {
                "total_connections_created": 3,
                "total_subscriptions": 2500,
                "total_unsubscriptions": 0
            }
        }
    },
    "note": "Each connection can handle up to max_instruments_per_ws_connection instruments (default: 1000)"
}
```

#### Get Specific Account's Pool Stats

```bash
GET /advanced/websocket-pool/stats/{account_id}
```

Example:
```bash
curl http://localhost:8080/advanced/websocket-pool/stats/primary | jq
```

## How It Works

### Subscription Flow

1. **First Subscription (0-1000 instruments)**
   - Pool creates first WebSocket connection
   - Subscribes all tokens to connection #0

2. **Exceeding 1000 Instruments**
   - Pool detects connection #0 is at capacity
   - Automatically creates connection #1
   - Routes new subscriptions to connection #1

3. **Continued Scaling**
   - Process repeats for every 1000 instruments
   - Pool creates connections #2, #3, #4, etc. as needed

### Connection Management

Each connection in the pool:
- Runs in its own thread via KiteTicker's threaded mode
- Handles reconnection automatically
- Resubscribes tokens after reconnect
- Reports ticks to the unified tick handler

### Load Balancing Strategy

The pool uses a simple **first-fit** strategy:
1. Check existing connections for available capacity
2. If found, add subscription to that connection
3. If no capacity available, create new connection
4. Add subscription to new connection

## Example Scenarios

### Scenario 1: Small Option Chain (< 1000 instruments)

```python
# Subscribe to 500 option contracts
tokens = [token for token in option_chain[:500]]
await client.subscribe_tokens(tokens, on_ticks=handler)
```

**Result:**
- Pool creates 1 WebSocket connection
- All 500 subscriptions on connection #0
- 500 slots remaining on connection #0

### Scenario 2: Large Option Chain (> 1000 instruments)

```python
# Subscribe to 2500 option contracts
tokens = [token for token in option_chain[:2500]]
await client.subscribe_tokens(tokens, on_ticks=handler)
```

**Result:**
- Pool creates 3 WebSocket connections
- Connection #0: 1000 instruments (100% utilized)
- Connection #1: 1000 instruments (100% utilized)
- Connection #2: 500 instruments (50% utilized)
- Total capacity: 3000 instruments
- Total used: 2500 instruments

### Scenario 3: Multiple Underlyings

```python
# Subscribe to NIFTY + BANKNIFTY + FINNIFTY option chains
nifty_tokens = [...]      # 1200 instruments
banknifty_tokens = [...]  # 1200 instruments
finnifty_tokens = [...]   # 800 instruments

await client.subscribe_tokens(nifty_tokens, on_ticks=handler)
await client.subscribe_tokens(banknifty_tokens, on_ticks=handler)
await client.subscribe_tokens(finnifty_tokens, on_ticks=handler)
```

**Result:**
- Pool creates 4 WebSocket connections
- Connection #0: 1000 NIFTY (100%)
- Connection #1: 200 NIFTY + 800 BANKNIFTY (100%)
- Connection #2: 400 BANKNIFTY + 600 FINNIFTY (100%)
- Connection #3: 200 FINNIFTY (20%)
- Total: 3200 instruments across 4 connections

## Benefits

### Scalability
- Support unlimited instruments (N × 1000 per account)
- No manual connection management required
- Automatic scaling based on demand

### Reliability
- Independent reconnection per connection
- Failure in one connection doesn't affect others
- Connection health monitoring

### Performance
- Parallel data streaming across connections
- No bottlenecks from single connection
- Efficient load distribution

### Monitoring
- Real-time visibility into connection pool status
- Per-connection utilization metrics
- Historical statistics (subscriptions, connections created)

## API Endpoints

### 1. Get All Accounts Pool Stats
**Endpoint:** `GET /advanced/websocket-pool/stats`

**Description:** Returns WebSocket pool statistics for all accounts

**Response Fields:**
- `total_accounts`: Number of accounts with active pools
- `accounts`: Dictionary of per-account statistics
- `note`: Helpful reminder about capacity limits

### 2. Get Account Pool Stats
**Endpoint:** `GET /advanced/websocket-pool/stats/{account_id}`

**Description:** Returns WebSocket pool statistics for specific account

**Path Parameters:**
- `account_id`: The account identifier (e.g., "primary")

**Response Fields:**
- `account_id`: Account identifier
- `total_connections`: Number of active WebSocket connections
- `total_target_tokens`: Total instruments to be subscribed
- `total_subscribed_tokens`: Currently subscribed instruments
- `max_instruments_per_connection`: Capacity per connection
- `total_capacity`: Total capacity across all connections
- `connections`: Array of per-connection details
- `statistics`: Lifetime statistics

**Error Responses:**
- `404`: Account not found or has no active WebSocket pool

## Troubleshooting

### Issue: Pool shows 0 connections

**Cause:** No subscriptions have been made yet

**Solution:** Pool is lazy-initialized on first subscription. This is normal.

### Issue: Connections not scaling

**Check:**
1. Verify `max_instruments_per_ws_connection` setting
2. Check pool stats to see actual utilization
3. Review logs for connection creation messages

### Issue: Ticks not received

**Check:**
1. Verify all connections are showing `"connected": true`
2. Check for error messages in logs
3. Verify tick handler is properly set

### Issue: High latency with many connections

**Cause:** Too many connections may cause overhead

**Solution:**
- Consider if all subscriptions are necessary
- Implement subscription filtering
- Use connection pooling more efficiently

## Performance Considerations

### Memory Usage
- Each WebSocket connection uses ~1-2 MB memory
- For 10,000 instruments: ~10-20 MB additional memory
- Negligible for modern systems

### Network Bandwidth
- Each connection maintains separate WebSocket
- Bandwidth scales linearly with connections
- Typical: 1-5 KB/s per connection (depends on tick rate)

### CPU Usage
- Each connection runs in separate thread
- CPU usage scales with number of ticks received
- Modern systems handle 10+ connections easily

## Migration Guide

### From Single Connection to Pool

No changes required! The pool is backward compatible:

**Before (single connection):**
```python
await client.subscribe_tokens(tokens, on_ticks=handler)
```

**After (automatic pooling):**
```python
await client.subscribe_tokens(tokens, on_ticks=handler)  # Same code!
```

The only difference: Now supports >1000 instruments automatically.

## Future Enhancements

Potential improvements for future versions:

1. **Smart Load Balancing**
   - Consider connection latency when routing subscriptions
   - Rebalance subscriptions across connections
   - Implement weighted distribution strategies

2. **Connection Pooling Strategies**
   - Round-robin distribution
   - Least-loaded connection selection
   - Geographic/latency-aware routing

3. **Advanced Monitoring**
   - Per-connection tick rate metrics
   - Connection health scores
   - Automatic connection recycling

4. **Dynamic Scaling**
   - Automatic connection reduction during low activity
   - Connection warming for anticipated load
   - Predictive scaling based on historical patterns

## References

- [Kite Connect WebSocket Documentation](https://kite.trade/docs/connect/v3/websocket/)
- [Kite Connect Rate Limits](https://kite.trade/docs/connect/v3/exceptions/#api-rate-limit)
- WebSocket Pool Implementation: `app/kite/websocket_pool.py`
- KiteClient Integration: `app/kite/client.py`

## Support

For issues or questions:
1. Check this documentation
2. Review service logs: `docker logs tv-ticker`
3. Check pool stats: `GET /advanced/websocket-pool/stats`
4. Review rate limit stats: `GET /advanced/rate-limit/stats`
