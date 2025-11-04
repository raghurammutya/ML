# Indicator Subscription Management Architecture

## Problem Statement

When multiple users subscribe to technical indicators with different:
- Instruments (NIFTY50, BANKNIFTY, stocks)
- Timeframes (1min, 5min, 15min, 1h, 1d)
- Indicators (RSI, MACD, BB, etc.)
- Parameters (RSI(14) vs RSI(21))

We need to:
1. ✅ Subscribe indicators on initial call
2. ✅ Unsubscribe after use
3. ✅ Clean up unconsumed indicator outputs
4. ✅ Prevent memory leaks
5. ✅ Handle mock data lifecycle

---

## Recommended Architecture

### 1. Reference Counting with TTL

**Concept**: Track active subscribers per indicator and auto-cleanup inactive ones.

```python
# Redis data structure
subscription_key = f"indicator_sub:{symbol}:{timeframe}:{indicator_id}"

# Structure:
{
    "indicator_id": "RSI_14",
    "symbol": "NIFTY50",
    "timeframe": "5min",
    "ref_count": 3,                    # Number of active subscribers
    "subscribers": {
        "user_123_session_abc": {
            "last_active": 1730369100,  # Unix timestamp
            "websocket_id": "ws_xyz"
        },
        "user_456_session_def": {
            "last_active": 1730369105,
            "websocket_id": "ws_abc"
        }
    },
    "created_at": 1730365000,
    "last_accessed": 1730369105,
    "ttl": 300  # 5 minutes of inactivity before cleanup
}
```

**Implementation**:

```python
# app/services/indicator_subscription_manager.py

from typing import Dict, Set, Optional
from datetime import datetime, timedelta
import redis.asyncio as redis
import json
import asyncio

class IndicatorSubscriptionManager:
    """
    Manages indicator subscriptions with reference counting and TTL cleanup.
    """

    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self.INACTIVE_TTL = 300  # 5 minutes
        self.CLEANUP_INTERVAL = 60  # Check every minute

    async def subscribe(
        self,
        user_id: str,
        session_id: str,
        symbol: str,
        timeframe: str,
        indicator_id: str,
        websocket_id: Optional[str] = None
    ) -> bool:
        """
        Subscribe a user to an indicator.
        Returns True if this is a new subscription (needs computation).
        """
        sub_key = f"indicator_sub:{symbol}:{timeframe}:{indicator_id}"
        subscriber_id = f"{user_id}_session_{session_id}"

        # Get current subscription state
        sub_data = await self.redis.get(sub_key)

        if sub_data:
            # Existing subscription - increment ref count
            sub = json.loads(sub_data)
            sub["subscribers"][subscriber_id] = {
                "last_active": int(datetime.utcnow().timestamp()),
                "websocket_id": websocket_id
            }
            sub["ref_count"] = len(sub["subscribers"])
            sub["last_accessed"] = int(datetime.utcnow().timestamp())

            await self.redis.set(sub_key, json.dumps(sub))

            # Reset TTL
            await self.redis.expire(sub_key, self.INACTIVE_TTL * 2)

            return False  # Already computing, no need to start
        else:
            # New subscription
            sub = {
                "indicator_id": indicator_id,
                "symbol": symbol,
                "timeframe": timeframe,
                "ref_count": 1,
                "subscribers": {
                    subscriber_id: {
                        "last_active": int(datetime.utcnow().timestamp()),
                        "websocket_id": websocket_id
                    }
                },
                "created_at": int(datetime.utcnow().timestamp()),
                "last_accessed": int(datetime.utcnow().timestamp()),
                "ttl": self.INACTIVE_TTL
            }

            await self.redis.set(sub_key, json.dumps(sub), ex=self.INACTIVE_TTL * 2)

            return True  # New subscription, start computation

    async def unsubscribe(
        self,
        user_id: str,
        session_id: str,
        symbol: str,
        timeframe: str,
        indicator_id: str
    ) -> bool:
        """
        Unsubscribe a user from an indicator.
        Returns True if this was the last subscriber (stop computation).
        """
        sub_key = f"indicator_sub:{symbol}:{timeframe}:{indicator_id}"
        subscriber_id = f"{user_id}_session_{session_id}"

        sub_data = await self.redis.get(sub_key)
        if not sub_data:
            return True  # Already cleaned up

        sub = json.loads(sub_data)

        # Remove this subscriber
        if subscriber_id in sub["subscribers"]:
            del sub["subscribers"][subscriber_id]

        sub["ref_count"] = len(sub["subscribers"])

        if sub["ref_count"] == 0:
            # Last subscriber - delete subscription
            await self.redis.delete(sub_key)
            return True  # Stop computation
        else:
            # Still has subscribers
            await self.redis.set(sub_key, json.dumps(sub))
            return False  # Keep computing

    async def heartbeat(
        self,
        user_id: str,
        session_id: str,
        symbol: str,
        timeframe: str,
        indicator_id: str
    ) -> bool:
        """
        Update last_active timestamp for a subscriber.
        Returns True if subscription is still active.
        """
        sub_key = f"indicator_sub:{symbol}:{timeframe}:{indicator_id}"
        subscriber_id = f"{user_id}_session_{session_id}"

        sub_data = await self.redis.get(sub_key)
        if not sub_data:
            return False  # Subscription expired

        sub = json.loads(sub_data)

        if subscriber_id in sub["subscribers"]:
            sub["subscribers"][subscriber_id]["last_active"] = int(datetime.utcnow().timestamp())
            sub["last_accessed"] = int(datetime.utcnow().timestamp())
            await self.redis.set(sub_key, json.dumps(sub))

            # Reset TTL
            await self.redis.expire(sub_key, self.INACTIVE_TTL * 2)

            return True
        else:
            return False  # Not subscribed

    async def cleanup_inactive_subscribers(self):
        """
        Background task to clean up inactive subscribers.
        Runs periodically to check for stale subscriptions.
        """
        now = int(datetime.utcnow().timestamp())

        # Get all subscription keys
        pattern = "indicator_sub:*"
        cursor = 0

        while True:
            cursor, keys = await self.redis.scan(cursor, match=pattern, count=100)

            for key in keys:
                sub_data = await self.redis.get(key)
                if not sub_data:
                    continue

                sub = json.loads(sub_data)
                modified = False

                # Check each subscriber
                for subscriber_id, info in list(sub["subscribers"].items()):
                    last_active = info["last_active"]

                    if now - last_active > self.INACTIVE_TTL:
                        # Inactive subscriber - remove
                        del sub["subscribers"][subscriber_id]
                        modified = True

                        print(f"Removed inactive subscriber {subscriber_id} from {key}")

                if modified:
                    sub["ref_count"] = len(sub["subscribers"])

                    if sub["ref_count"] == 0:
                        # No subscribers left - delete
                        await self.redis.delete(key)
                        print(f"Deleted subscription {key} - no active subscribers")
                    else:
                        # Update subscription
                        await self.redis.set(key, json.dumps(sub))

            if cursor == 0:
                break

    async def get_active_subscriptions(
        self,
        symbol: Optional[str] = None,
        timeframe: Optional[str] = None
    ) -> Dict:
        """
        Get all active subscriptions, optionally filtered by symbol/timeframe.
        """
        if symbol and timeframe:
            pattern = f"indicator_sub:{symbol}:{timeframe}:*"
        elif symbol:
            pattern = f"indicator_sub:{symbol}:*"
        else:
            pattern = "indicator_sub:*"

        subscriptions = {}
        cursor = 0

        while True:
            cursor, keys = await self.redis.scan(cursor, match=pattern, count=100)

            for key in keys:
                sub_data = await self.redis.get(key)
                if sub_data:
                    subscriptions[key.decode() if isinstance(key, bytes) else key] = json.loads(sub_data)

            if cursor == 0:
                break

        return subscriptions

    async def start_cleanup_task(self):
        """
        Start background cleanup task.
        """
        while True:
            try:
                await asyncio.sleep(self.CLEANUP_INTERVAL)
                await self.cleanup_inactive_subscribers()
            except Exception as e:
                print(f"Error in cleanup task: {e}")
                await asyncio.sleep(5)


# Usage in indicator service
async def on_startup():
    """FastAPI startup event"""
    redis_client = redis.from_url(settings.REDIS_URL, decode_responses=False)
    sub_manager = IndicatorSubscriptionManager(redis_client)

    # Start cleanup task
    asyncio.create_task(sub_manager.start_cleanup_task())
```

---

### 2. Session-Based Lifecycle

**Concept**: Link indicator subscriptions to user sessions.

```python
# When user logs in
session_id = create_session(user_id)

# When user subscribes to indicator
await sub_manager.subscribe(
    user_id=user_id,
    session_id=session_id,
    symbol="NIFTY50",
    timeframe="5min",
    indicator_id="RSI_14"
)

# When user logs out or session expires
await cleanup_session_subscriptions(session_id)
```

**Implementation**:

```python
async def cleanup_session_subscriptions(session_id: str):
    """
    Clean up all subscriptions for a session.
    Called on logout or session expiry.
    """
    # Get all subscriptions for this session
    pattern = f"indicator_sub:*"
    cursor = 0

    while True:
        cursor, keys = await redis.scan(cursor, match=pattern, count=100)

        for key in keys:
            sub_data = await redis.get(key)
            if not sub_data:
                continue

            sub = json.loads(sub_data)

            # Find subscribers with this session_id
            for subscriber_id in list(sub["subscribers"].keys()):
                if f"_session_{session_id}" in subscriber_id:
                    user_id = subscriber_id.split("_session_")[0]

                    # Unsubscribe
                    await sub_manager.unsubscribe(
                        user_id=user_id,
                        session_id=session_id,
                        symbol=sub["symbol"],
                        timeframe=sub["timeframe"],
                        indicator_id=sub["indicator_id"]
                    )

        if cursor == 0:
            break
```

---

### 3. WebSocket Heartbeat

**Concept**: Require periodic pings to keep subscriptions alive.

```python
# Client sends ping every 30 seconds
{
    "action": "ping",
    "subscriptions": [
        {"symbol": "NIFTY50", "timeframe": "5min", "indicator": "RSI_14"},
        {"symbol": "NIFTY50", "timeframe": "5min", "indicator": "MACD_12_26_9"}
    ]
}

# Server updates last_active timestamp
for sub in message["subscriptions"]:
    await sub_manager.heartbeat(
        user_id=user_id,
        session_id=session_id,
        symbol=sub["symbol"],
        timeframe=sub["timeframe"],
        indicator_id=sub["indicator"]
    )
```

---

### 4. Mock Data Lifecycle

**Problem**: Mock data should not be permanently stored.

**Solutions**:

#### Option A: TTL on Mock Data

```python
# When storing mock indicator values
if is_mock_mode():
    # Short TTL for mock data (5 minutes)
    await redis.set(
        f"indicator_value:{symbol}:{timeframe}:{indicator_id}:latest",
        json.dumps(value),
        ex=300  # 5 minutes
    )
else:
    # Longer TTL for real data
    await redis.set(
        f"indicator_value:{symbol}:{timeframe}:{indicator_id}:latest",
        json.dumps(value),
        ex=get_ttl_for_timeframe(timeframe)  # 60s for 1min, 300s for 5min, etc.
    )
```

#### Option B: Mark Mock Data with Prefix

```python
# Different key prefix for mock data
if is_mock_mode():
    key_prefix = "mock_indicator_value"
else:
    key_prefix = "indicator_value"

# Periodic cleanup of all mock data
async def cleanup_mock_data():
    """Remove all mock indicator data"""
    pattern = "mock_indicator_value:*"
    cursor = 0

    while True:
        cursor, keys = await redis.scan(cursor, match=pattern, count=1000)

        if keys:
            await redis.delete(*keys)

        if cursor == 0:
            break
```

#### Option C: In-Memory Only for Mock

```python
# Don't persist mock data to Redis at all
if is_mock_mode():
    # Store in process memory with TTL
    mock_cache[key] = {
        "value": indicator_value,
        "expires_at": time.time() + 300
    }
else:
    # Store in Redis for real data
    await redis.set(key, json.dumps(value), ex=ttl)
```

---

## Recommended Implementation Strategy

### Phase 1: Reference Counting (Immediate)
```python
# Add to existing indicator service
@router.post("/indicators/subscribe")
async def subscribe_indicators(request: SubscribeRequest):
    for indicator_spec in request.indicators:
        is_new = await sub_manager.subscribe(
            user_id=current_user.id,
            session_id=request.session_id,
            symbol=request.symbol,
            timeframe=request.timeframe,
            indicator_id=indicator_spec.indicator_id
        )

        if is_new:
            # Start computing this indicator
            await start_indicator_computation(
                symbol=request.symbol,
                timeframe=request.timeframe,
                indicator_id=indicator_spec.indicator_id
            )
```

### Phase 2: Heartbeat/Ping (Week 1)
```python
# Add heartbeat endpoint
@router.post("/indicators/heartbeat")
async def heartbeat(request: HeartbeatRequest):
    results = []
    for sub in request.subscriptions:
        is_alive = await sub_manager.heartbeat(
            user_id=current_user.id,
            session_id=request.session_id,
            symbol=sub.symbol,
            timeframe=sub.timeframe,
            indicator_id=sub.indicator_id
        )
        results.append({"indicator": sub.indicator_id, "alive": is_alive})

    return {"status": "ok", "results": results}
```

### Phase 3: Session Cleanup (Week 2)
```python
# Hook into session expiry
@router.post("/auth/logout")
async def logout(session_id: str):
    # Clean up subscriptions
    await cleanup_session_subscriptions(session_id)

    # Regular logout
    await auth_service.logout(session_id)
```

### Phase 4: Mock Data Management (Week 2)
```python
# Separate mock and real data
if settings.MOCK_MODE:
    cache_manager = MockIndicatorCache(ttl=300)  # 5 min
else:
    cache_manager = RedisIndicatorCache(redis_client)
```

---

## Monitoring & Metrics

```python
# Add Prometheus metrics
indicator_subscriptions_total = Counter(
    "indicator_subscriptions_total",
    "Total indicator subscriptions",
    ["symbol", "timeframe", "indicator"]
)

indicator_active_subscriptions = Gauge(
    "indicator_active_subscriptions",
    "Currently active subscriptions",
    ["symbol", "timeframe"]
)

indicator_cleanup_runs = Counter(
    "indicator_cleanup_runs_total",
    "Number of cleanup runs"
)

# Expose metrics
@router.get("/indicators/metrics")
async def get_metrics():
    subs = await sub_manager.get_active_subscriptions()

    return {
        "total_subscriptions": len(subs),
        "by_symbol": aggregate_by_symbol(subs),
        "by_timeframe": aggregate_by_timeframe(subs),
        "total_subscribers": sum(s["ref_count"] for s in subs.values())
    }
```

---

## Summary

**Best Approach**: Combine all strategies

1. **Reference Counting**: Track active users per indicator
2. **TTL**: Auto-expire after inactivity
3. **Heartbeat**: Keep-alive mechanism
4. **Session Lifecycle**: Clean up on logout
5. **Mock Data Isolation**: Separate mock from real data

This ensures:
- ✅ No memory leaks
- ✅ Automatic cleanup
- ✅ Efficient resource usage
- ✅ Clear separation of mock/real data
