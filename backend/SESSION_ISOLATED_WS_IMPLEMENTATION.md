# Session-Isolated WebSocket Implementation Plan

## Overview

Update `/home/stocksadmin/Quantagro/tradingview-viz/backend/app/routes/indicator_ws.py` to use session-isolated subscriptions.

## Key Changes Required

### 1. Authentication Change
**Current**: API key via query parameter
```python
api_key: str = Query(..., description="API key for authentication")
auth_result = await require_api_key_ws(api_key)
client_id = str(auth_result.key_id)
```

**New**: JWT token via query parameter or header
```python
token: str = Query(..., description="JWT token for authentication")
# Verify JWT and extract user data
user_data = await verify_jwt_token_ws(token)
user_id = user_data["email"]
session_id = user_data["session_id"]
```

### 2. WebSocket Connection ID
**Current**: Uses `client_id` from API key
```python
client_id = str(auth_result.key_id)
```

**New**: Generate unique ID per WebSocket connection
```python
import uuid
ws_conn_id = f"ws_{uuid.uuid4().hex[:12]}"
```

### 3. Subscription Manager
**Current**: Uses `IndicatorSubscriptionManager` (tracks by client_id)
```python
sub_manager = IndicatorSubscriptionManager(redis_client)
await sub_manager.subscribe(client_id, symbol, timeframe, indicator_ids)
```

**New**: Uses `SessionSubscriptionManager` (tracks by ws_conn_id + session + user)
```python
from app.services.session_subscription_manager import get_subscription_manager
sub_manager = get_subscription_manager()

# Convert indicator list to dict format
indicators_dict = {}
for ind in msg.indicators:
    ind_id = IndicatorSpec.create_id(ind["name"], ind["params"])
    indicators_dict[ind_id] = {
        "name": ind["name"],
        "params": ind["params"]
    }

await sub_manager.subscribe(
    ws_conn_id=ws_conn_id,
    user_id=user_id,
    session_id=session_id,
    symbol=msg.symbol,
    timeframe=msg.timeframe,
    indicators=indicators_dict
)
```

### 4. Connection Manager
**Current**: `IndicatorConnectionManager` tracks by client_id
```python
class IndicatorConnectionManager:
    self.active_connections: Dict[WebSocket, str] = {}  # WebSocket -> client_id
    self.client_subscriptions: Dict[str, Set[tuple]] = {}  # client_id -> subscriptions
```

**New**: Track by ws_conn_id, maps to WebSocket objects for sending
```python
class SessionConnectionManager:
    self.active_connections: Dict[str, WebSocket] = {}  # ws_conn_id -> WebSocket
    # No need to track subscriptions here - that's in SessionSubscriptionManager
```

### 5. Broadcast Logic
**Current**: Broadcast to all clients subscribed to indicator
```python
async def broadcast_indicator_update(self, symbol, timeframe, indicator_id, value, timestamp):
    for websocket, client_id in self.active_connections.items():
        subscriptions = self.client_subscriptions.get(client_id, set())
        if (symbol, timeframe, indicator_id) in subscriptions:
            await self.send_to_client(websocket, update.dict())
```

**New**: Query SessionSubscriptionManager for subscribers, then send
```python
async def broadcast_indicator_update(self, sub_manager, symbol, timeframe, indicator_id, value, timestamp):
    # Get all WebSocket connection IDs subscribed to this indicator
    subscribers = sub_manager.get_indicator_subscribers(symbol, timeframe, indicator_id)

    update = IndicatorUpdate(...)

    for ws_conn_id in subscribers:
        websocket = self.active_connections.get(ws_conn_id)
        if websocket:
            await self.send_to_client(websocket, update.dict())
```

## Implementation Steps

1. ✅ Initialize `SessionSubscriptionManager` in `main.py`
2. Create JWT verification helper for WebSockets
3. Update WebSocket endpoint authentication
4. Update connection manager to use `ws_conn_id`
5. Update subscribe/unsubscribe handlers
6. Update broadcast logic
7. Update cleanup logic

## Testing Plan

1. Connect with valid JWT token
2. Subscribe to indicators
3. Verify only subscribed indicators are received
4. Open second tab/connection with same user
5. Subscribe to different indicators in second tab
6. Verify each tab receives only its subscribed indicators
7. Close one tab, verify other continues working
8. Test heartbeat mechanism

## Session Isolation Guarantee

The architecture ensures that:

- Each browser tab = unique `ws_conn_id`
- Each `ws_conn_id` has its own subscription list
- Broadcasts are filtered by `ws_conn_id` membership
- User A in Tab 1 cannot see User B's data
- User A in Tab 1 cannot see User A in Tab 2's data

This provides **complete session-level isolation** as required.
