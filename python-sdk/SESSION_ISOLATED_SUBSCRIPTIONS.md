# Session-Isolated Indicator Subscriptions Architecture

## Problem Statement

When a user (via frontend or SDK) subscribes to indicators for a symbol, they should **only** receive:
- Indicators THEY subscribed to in THIS specific session
- NOT indicators subscribed by other users
- NOT indicators subscribed by the same user in different tabs/sessions

## Example Scenario

```
User: alice@example.com

Tab 1 (Session A):
  - Subscribes to: NIFTY50 + RSI(14) + MACD(12,26,9)
  - Should receive: OHLCV + Greeks + OI + RSI + MACD

Tab 2 (Session B) - SAME USER, DIFFERENT TAB:
  - Subscribes to: NIFTY50 + SMA(20) + BBANDS(20,2)
  - Should receive: OHLCV + Greeks + OI + SMA + BBANDS
  - Should NOT receive: RSI or MACD (those belong to Session A)

Different User (bob@example.com):
  - Subscribes to: NIFTY50 + RSI(14)
  - Should receive: OHLCV + Greeks + OI + RSI
  - Should NOT receive: Alice's MACD, SMA, or BBANDS
```

---

## Architecture Design

### 1. Session Identification

Each subscription is uniquely identified by:
```python
subscription_key = (user_id, session_id, symbol, timeframe)
```

**Session ID Sources** (in priority order):
1. **WebSocket Connection ID** (best for WebSocket streams)
2. **JWT Session Claim** (for REST API calls)
3. **Cookie Session ID** (fallback)

### 2. Subscription Data Structure

```python
# Backend maintains per-connection subscriptions
subscriptions = {
    # WebSocket Connection ID → Subscription Details
    "ws_conn_abc123": {
        "user_id": "alice@example.com",
        "session_id": "session_xyz",
        "symbol": "NIFTY50",
        "timeframe": "5min",
        "indicators": {
            "RSI_14_100": {"name": "RSI", "params": {"length": 14, "scalar": 100}},
            "MACD_12_26_9": {"name": "MACD", "params": {"fast": 12, "slow": 26, "signal": 9}}
        },
        "subscribed_at": "2025-11-04T10:30:00Z",
        "last_heartbeat": "2025-11-04T10:35:00Z"
    },

    # SAME USER, DIFFERENT TAB
    "ws_conn_def456": {
        "user_id": "alice@example.com",  # Same user
        "session_id": "session_pqr",      # Different session
        "symbol": "NIFTY50",
        "timeframe": "5min",
        "indicators": {
            "SMA_20": {"name": "SMA", "params": {"length": 20}},
            "BBANDS_20_2": {"name": "BBANDS", "params": {"length": 20, "std": 2}}
        },
        "subscribed_at": "2025-11-04T10:32:00Z",
        "last_heartbeat": "2025-11-04T10:35:00Z"
    },

    # DIFFERENT USER
    "ws_conn_ghi789": {
        "user_id": "bob@example.com",     # Different user
        "session_id": "session_mno",
        "symbol": "NIFTY50",
        "timeframe": "5min",
        "indicators": {
            "RSI_14_100": {"name": "RSI", "params": {"length": 14, "scalar": 100}}
        },
        "subscribed_at": "2025-11-04T10:31:00Z",
        "last_heartbeat": "2025-11-04T10:35:00Z"
    }
}
```

### 3. Shared Computation, Filtered Delivery

**Key Principle**: Compute once, deliver selectively.

```python
# Backend computes indicators ONCE (shared)
indicator_cache = {
    "NIFTY50:5min:RSI_14_100": {
        "value": 67.3,
        "timestamp": "2025-11-04T10:35:00Z",
        "subscribers": ["ws_conn_abc123", "ws_conn_ghi789"]  # Both Alice Tab1 and Bob
    },
    "NIFTY50:5min:MACD_12_26_9": {
        "value": {"MACD": 12.5, "MACDh": 3.2, "MACDs": 9.3},
        "timestamp": "2025-11-04T10:35:00Z",
        "subscribers": ["ws_conn_abc123"]  # Only Alice Tab1
    },
    "NIFTY50:5min:SMA_20": {
        "value": 24125.5,
        "timestamp": "2025-11-04T10:35:00Z",
        "subscribers": ["ws_conn_def456"]  # Only Alice Tab2
    }
}

# When broadcasting updates:
async def broadcast_indicator_update(symbol, timeframe, indicator_id, data):
    """
    Send indicator update ONLY to WebSocket connections that subscribed to it.
    """
    cache_key = f"{symbol}:{timeframe}:{indicator_id}"
    subscribers = indicator_cache[cache_key]["subscribers"]

    for ws_conn_id in subscribers:
        subscription = subscriptions[ws_conn_id]

        # Build message with ONLY this connection's subscribed indicators
        message = {
            "type": "indicator_update",
            "symbol": symbol,
            "timeframe": timeframe,
            "timestamp": data["timestamp"],
            "ohlcv": get_ohlcv(symbol, timeframe),  # Always included
            "greeks": get_greeks(symbol, timeframe),  # Always included
            "oi": get_oi(symbol, timeframe),  # Always included
            "indicators": {}  # FILTERED per connection
        }

        # Add ONLY the indicators THIS connection subscribed to
        for indicator_id in subscription["indicators"].keys():
            if indicator_id == indicator_id:  # This specific update
                message["indicators"][indicator_id] = data

        # Send to WebSocket
        await websocket_connections[ws_conn_id].send(message)
```

---

## Implementation

### Backend: Subscription Manager

```python
# app/services/session_subscription_manager.py

from typing import Dict, Set, Optional
import asyncio
from datetime import datetime

class SessionSubscriptionManager:
    """
    Manages indicator subscriptions with session-level isolation.

    Key Principle:
    - Compute indicators ONCE (shared computation)
    - Deliver indicators ONLY to sessions that subscribed (filtered delivery)
    """

    def __init__(self, redis_client):
        self.redis = redis_client
        # WebSocket ID → Subscription metadata
        self.subscriptions: Dict[str, Dict] = {}
        # Indicator ID → Set of WebSocket IDs subscribed to it
        self.indicator_subscribers: Dict[str, Set[str]] = {}

    async def subscribe(
        self,
        ws_conn_id: str,
        user_id: str,
        session_id: str,
        symbol: str,
        timeframe: str,
        indicators: Dict[str, Dict]
    ):
        """
        Subscribe a specific session to indicators.

        Args:
            ws_conn_id: WebSocket connection ID (unique per tab/session)
            user_id: User email
            session_id: Session identifier (from JWT or cookie)
            symbol: Symbol (e.g., "NIFTY50")
            timeframe: Timeframe (e.g., "5min")
            indicators: Dict of {indicator_id: {name, params}}
        """
        # Store subscription metadata
        self.subscriptions[ws_conn_id] = {
            "user_id": user_id,
            "session_id": session_id,
            "symbol": symbol,
            "timeframe": timeframe,
            "indicators": indicators,
            "subscribed_at": datetime.now().isoformat(),
            "last_heartbeat": datetime.now().isoformat()
        }

        # Track which WebSocket connections are subscribed to each indicator
        for indicator_id in indicators.keys():
            cache_key = f"{symbol}:{timeframe}:{indicator_id}"

            if cache_key not in self.indicator_subscribers:
                self.indicator_subscribers[cache_key] = set()

            self.indicator_subscribers[cache_key].add(ws_conn_id)

            # Increment ref count in Redis (for cleanup)
            await self.redis.sadd(f"indicator_subscribers:{cache_key}", ws_conn_id)

        return {
            "status": "subscribed",
            "ws_conn_id": ws_conn_id,
            "indicators": list(indicators.keys())
        }

    async def unsubscribe(self, ws_conn_id: str):
        """
        Unsubscribe a session from all its indicators.

        Called when:
        - User explicitly unsubscribes
        - WebSocket connection closes
        - Tab is closed
        """
        if ws_conn_id not in self.subscriptions:
            return

        subscription = self.subscriptions[ws_conn_id]
        symbol = subscription["symbol"]
        timeframe = subscription["timeframe"]

        # Remove from indicator subscribers
        for indicator_id in subscription["indicators"].keys():
            cache_key = f"{symbol}:{timeframe}:{indicator_id}"

            if cache_key in self.indicator_subscribers:
                self.indicator_subscribers[cache_key].discard(ws_conn_id)

                # Decrement ref count in Redis
                await self.redis.srem(f"indicator_subscribers:{cache_key}", ws_conn_id)

                # If no more subscribers, stop computing this indicator
                if len(self.indicator_subscribers[cache_key]) == 0:
                    await self._stop_indicator_computation(cache_key)
                    del self.indicator_subscribers[cache_key]

        # Remove subscription
        del self.subscriptions[ws_conn_id]

    async def broadcast_indicator_update(
        self,
        symbol: str,
        timeframe: str,
        indicator_id: str,
        indicator_data: Dict
    ):
        """
        Broadcast indicator update ONLY to sessions subscribed to it.

        This is the KEY method for session isolation.
        """
        cache_key = f"{symbol}:{timeframe}:{indicator_id}"

        # Get all WebSocket connections subscribed to this indicator
        subscribers = self.indicator_subscribers.get(cache_key, set())

        for ws_conn_id in subscribers:
            subscription = self.subscriptions.get(ws_conn_id)
            if not subscription:
                continue

            # Build message with data for THIS connection only
            message = await self._build_session_message(
                ws_conn_id,
                subscription,
                {indicator_id: indicator_data}
            )

            # Send via WebSocket
            await self._send_to_websocket(ws_conn_id, message)

    async def _build_session_message(
        self,
        ws_conn_id: str,
        subscription: Dict,
        indicator_updates: Dict[str, Dict]
    ) -> Dict:
        """
        Build message containing ONLY data subscribed by this session.
        """
        symbol = subscription["symbol"]
        timeframe = subscription["timeframe"]

        # Always include base data
        message = {
            "type": "market_update",
            "symbol": symbol,
            "timeframe": timeframe,
            "timestamp": datetime.now().isoformat(),
            "ohlcv": await self._get_ohlcv(symbol, timeframe),
            "greeks": await self._get_greeks(symbol, timeframe),
            "oi": await self._get_oi(symbol, timeframe),
            "indicators": {}
        }

        # Add ONLY indicators this session subscribed to
        for indicator_id, data in indicator_updates.items():
            if indicator_id in subscription["indicators"]:
                message["indicators"][indicator_id] = data

        return message

    def get_session_indicators(self, ws_conn_id: str) -> Optional[Dict]:
        """
        Get indicators subscribed by a specific session.

        Used for:
        - REST API responses
        - Initial data load
        - Debugging
        """
        if ws_conn_id not in self.subscriptions:
            return None

        return self.subscriptions[ws_conn_id]["indicators"]

    def get_indicator_subscriber_count(self, symbol: str, timeframe: str, indicator_id: str) -> int:
        """
        Get number of sessions subscribed to an indicator.

        Used for:
        - Deciding whether to compute indicator
        - Monitoring/metrics
        """
        cache_key = f"{symbol}:{timeframe}:{indicator_id}"
        return len(self.indicator_subscribers.get(cache_key, set()))
```

### WebSocket Handler

```python
# app/routes/indicator_ws.py

from fastapi import WebSocket, WebSocketDisconnect
from app.services.session_subscription_manager import SessionSubscriptionManager

async def indicator_websocket_handler(
    websocket: WebSocket,
    user_id: str,  # From JWT
    session_id: str  # From JWT or cookie
):
    """
    WebSocket handler for indicator streaming.

    Session-isolated: Each connection only receives indicators it subscribed to.
    """
    await websocket.accept()

    # Generate unique connection ID
    ws_conn_id = f"ws_{user_id}_{session_id}_{int(time.time()*1000)}"

    sub_manager = get_subscription_manager()

    try:
        while True:
            # Receive subscription request
            message = await websocket.receive_json()

            if message["type"] == "subscribe":
                # Subscribe this connection to indicators
                await sub_manager.subscribe(
                    ws_conn_id=ws_conn_id,
                    user_id=user_id,
                    session_id=session_id,
                    symbol=message["symbol"],
                    timeframe=message["timeframe"],
                    indicators=message["indicators"]  # {indicator_id: {name, params}}
                )

                # Send confirmation
                await websocket.send_json({
                    "type": "subscribed",
                    "ws_conn_id": ws_conn_id,
                    "indicators": list(message["indicators"].keys())
                })

            elif message["type"] == "unsubscribe":
                await sub_manager.unsubscribe(ws_conn_id)

            elif message["type"] == "heartbeat":
                # Keep connection alive
                await websocket.send_json({"type": "heartbeat_ack"})

    except WebSocketDisconnect:
        # Clean up when connection closes
        await sub_manager.unsubscribe(ws_conn_id)
```

### REST API (Alternative to WebSocket)

```python
# app/routes/indicators_api.py

@router.get("/data/{symbol}")
async def get_indicator_data(
    symbol: str,
    timeframe: str = Query(...),
    session_id: str = Header(..., alias="X-Session-ID"),
    user: UserIdentity = Depends(require_api_key_or_jwt)
):
    """
    Get current indicator data for a specific session.

    Returns ONLY indicators subscribed by this session.
    """
    ws_conn_id = f"rest_{user.user_id}_{session_id}"

    sub_manager = get_subscription_manager()

    # Get this session's subscribed indicators
    session_indicators = sub_manager.get_session_indicators(ws_conn_id)

    if not session_indicators:
        raise HTTPException(
            status_code=404,
            detail="No active subscription for this session"
        )

    # Build response with ONLY this session's data
    response = {
        "symbol": symbol,
        "timeframe": timeframe,
        "timestamp": datetime.now().isoformat(),
        "ohlcv": await get_ohlcv(symbol, timeframe),
        "greeks": await get_greeks(symbol, timeframe),
        "oi": await get_oi(symbol, timeframe),
        "indicators": {}
    }

    # Fetch ONLY the indicators this session subscribed to
    for indicator_id, indicator_spec in session_indicators.items():
        indicator_data = await get_indicator_data(
            symbol, timeframe, indicator_id
        )
        response["indicators"][indicator_id] = indicator_data

    return response
```

---

## Frontend Implementation

### React Example (Multi-Tab Support)

```typescript
// services/indicatorSubscription.ts

import { v4 as uuidv4 } from 'uuid';

class IndicatorSubscriptionService {
  private ws: WebSocket | null = null;
  private sessionId: string;
  private subscriptions: Map<string, Set<string>> = new Map();

  constructor() {
    // Generate unique session ID for this tab/window
    this.sessionId = uuidv4();

    // Store in sessionStorage (unique per tab)
    sessionStorage.setItem('session_id', this.sessionId);
  }

  async connect(accessToken: string) {
    const sessionId = sessionStorage.getItem('session_id');

    this.ws = new WebSocket(
      `ws://localhost:8081/ws/indicators?token=${accessToken}&session_id=${sessionId}`
    );

    this.ws.onmessage = (event) => {
      const message = JSON.parse(event.data);

      // This message contains ONLY indicators subscribed by THIS tab
      this.handleMarketUpdate(message);
    };
  }

  async subscribe(
    symbol: string,
    timeframe: string,
    indicators: Array<{name: string, params: Record<string, any>}>
  ) {
    // Build indicator IDs
    const indicatorSpecs = indicators.reduce((acc, ind) => {
      const indicatorId = this.buildIndicatorId(ind.name, ind.params);
      acc[indicatorId] = ind;
      return acc;
    }, {} as Record<string, any>);

    // Send subscription request
    this.ws?.send(JSON.stringify({
      type: 'subscribe',
      symbol,
      timeframe,
      indicators: indicatorSpecs
    }));

    // Track locally
    const key = `${symbol}:${timeframe}`;
    this.subscriptions.set(key, new Set(Object.keys(indicatorSpecs)));
  }

  async unsubscribe(symbol: string, timeframe: string) {
    this.ws?.send(JSON.stringify({
      type: 'unsubscribe',
      symbol,
      timeframe
    }));

    this.subscriptions.delete(`${symbol}:${timeframe}`);
  }

  private handleMarketUpdate(message: any) {
    // Message contains ONLY indicators THIS tab subscribed to
    console.log('Indicators for THIS tab:', message.indicators);

    // Update UI
    this.updateChart(message);
  }

  private buildIndicatorId(name: string, params: Record<string, any>): string {
    const paramValues = Object.values(params);
    return [name, ...paramValues].join('_');
  }
}

// Usage in Component
function TradingChart() {
  const [indicators, setIndicators] = useState<string[]>([]);
  const subscriptionService = useRef(new IndicatorSubscriptionService());

  useEffect(() => {
    // Each tab gets its own subscription service with unique session ID
    subscriptionService.current.connect(accessToken);

    return () => {
      // Clean up when tab closes
      subscriptionService.current.disconnect();
    };
  }, []);

  const handleSubscribe = () => {
    // Subscribe THIS tab to specific indicators
    subscriptionService.current.subscribe('NIFTY50', '5min', [
      { name: 'RSI', params: { length: 14, scalar: 100 } },
      { name: 'MACD', params: { fast: 12, slow: 26, signal: 9 } }
    ]);
  };

  return (
    <div>
      <IndicatorSelector onSubscribe={handleSubscribe} />
      <Chart indicators={indicators} />
    </div>
  );
}
```

---

## Python SDK Implementation

```python
# python-sdk/stocksblitz/indicator_subscription.py

import uuid
from typing import Dict, List, Optional

class IndicatorSubscription:
    """
    Session-isolated indicator subscription for Python SDK.

    Each instance represents a unique session with its own subscriptions.
    """

    def __init__(self, api_client):
        self.api_client = api_client
        # Generate unique session ID for this SDK instance
        self.session_id = str(uuid.uuid4())
        self._subscriptions: Dict[str, List[str]] = {}

    def subscribe(
        self,
        symbol: str,
        timeframe: str,
        indicators: List[Dict[str, any]]
    ):
        """
        Subscribe to indicators for THIS session only.

        Example:
            >>> subscription.subscribe(
            ...     symbol="NIFTY50",
            ...     timeframe="5min",
            ...     indicators=[
            ...         {"name": "RSI", "params": {"length": 14, "scalar": 100}},
            ...         {"name": "MACD", "params": {"fast": 12, "slow": 26, "signal": 9}}
            ...     ]
            ... )
        """
        # Build indicator IDs
        indicator_specs = {}
        for ind in indicators:
            indicator_id = self._build_indicator_id(ind["name"], ind["params"])
            indicator_specs[indicator_id] = ind

        # Send subscription request with session ID
        response = self.api_client.post(
            "/indicators/subscribe",
            json={
                "symbol": symbol,
                "timeframe": timeframe,
                "indicators": indicator_specs,
                "session_id": self.session_id  # IMPORTANT: Session isolation
            }
        )

        # Track locally
        key = f"{symbol}:{timeframe}"
        self._subscriptions[key] = list(indicator_specs.keys())

        return response

    def get_data(self, symbol: str, timeframe: str) -> Dict:
        """
        Get current data for THIS session's subscriptions.

        Returns ONLY indicators subscribed by this session.
        """
        response = self.api_client.get(
            f"/indicators/data/{symbol}",
            params={"timeframe": timeframe},
            headers={"X-Session-ID": self.session_id}  # Session isolation
        )

        return response

    def unsubscribe(self, symbol: str, timeframe: str):
        """Unsubscribe from all indicators for symbol/timeframe."""
        self.api_client.post(
            "/indicators/unsubscribe",
            json={
                "symbol": symbol,
                "timeframe": timeframe,
                "session_id": self.session_id
            }
        )

        key = f"{symbol}:{timeframe}"
        if key in self._subscriptions:
            del self._subscriptions[key]

    def _build_indicator_id(self, name: str, params: Dict) -> str:
        """Build indicator ID from name and parameters."""
        param_values = list(params.values())
        return "_".join([name] + [str(v) for v in param_values])

    def __del__(self):
        """Clean up subscriptions when SDK instance is destroyed."""
        for key in list(self._subscriptions.keys()):
            symbol, timeframe = key.split(":")
            self.unsubscribe(symbol, timeframe)
```

---

## Summary

### Key Principles:

1. **Session-Level Isolation**:
   - Each tab/window/SDK instance = unique session
   - Subscriptions tracked per session, not per user

2. **Shared Computation**:
   - Backend computes RSI(14) for NIFTY50 ONCE
   - Multiple sessions can benefit from same computation

3. **Filtered Delivery**:
   - Each session receives ONLY indicators it subscribed to
   - WebSocket messages filtered by subscription

4. **Multi-Tab Support**:
   - Same user in different tabs = different sessions
   - Each tab can have different indicator subscriptions
   - No cross-contamination of data

5. **Identifier Hierarchy**:
   ```
   user_id → Can have multiple sessions
     ├─ session_id (Tab 1) → Can subscribe to multiple symbols
     │   ├─ symbol: NIFTY50, timeframe: 5min
     │   │   └─ indicators: [RSI_14_100, MACD_12_26_9]
     │   └─ symbol: BANKNIFTY, timeframe: 15min
     │       └─ indicators: [SMA_20]
     └─ session_id (Tab 2) → Different subscriptions
         └─ symbol: NIFTY50, timeframe: 5min
             └─ indicators: [BBANDS_20_2]  # Different from Tab 1!
   ```

### Data Flow:

```
1. User opens Tab 1, subscribes to RSI + MACD
   → Backend: Store subscription with ws_conn_id_1
   → Backend: Start computing RSI + MACD (if not already)

2. User opens Tab 2, subscribes to SMA
   → Backend: Store subscription with ws_conn_id_2 (different session!)
   → Backend: Start computing SMA (if not already)

3. RSI update ready
   → Backend: Find subscribers of RSI
   → Backend: Send RSI data to ws_conn_id_1 ONLY
   → Tab 1 receives: OHLCV + Greeks + OI + RSI + MACD
   → Tab 2 receives: NOTHING (not subscribed to RSI)

4. SMA update ready
   → Backend: Find subscribers of SMA
   → Backend: Send SMA data to ws_conn_id_2 ONLY
   → Tab 1 receives: NOTHING (not subscribed to SMA)
   → Tab 2 receives: OHLCV + Greeks + OI + SMA
```

**Result**: Perfect session isolation with efficient shared computation!
