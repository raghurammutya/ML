# Shared Computation Pattern for Multi-User Scenarios

## Overview

When multiple users request the same indicator (symbol, timeframe, parameters), the system should:
1. ✅ Compute once
2. ✅ Serve many from cache
3. ✅ Prevent duplicate computations
4. ✅ Handle concurrent requests gracefully

---

## Architecture: Compute-Once-Serve-Many

### Scenario 1: Sequential Requests

```
Timeline:
T+0s:  User A requests RSI_14 on NIFTY50 5min
       → Cache miss
       → Compute RSI_14
       → Store in Redis with TTL=600s
       → Return to User A

T+5s:  User B requests RSI_14 on NIFTY50 5min
       → Cache hit! ✅
       → Return cached value to User B
       → NO computation needed

T+10s: User C requests RSI_14 on NIFTY50 5min
       → Cache hit! ✅
       → Return cached value to User C
       → NO computation needed
```

**Result**: 1 computation serves 3 users

---

### Scenario 2: Concurrent Requests (Race Condition)

**Problem**: Multiple users request at the exact same time, before cache is populated.

```
Timeline:
T+0.000s:  User A requests RSI_14 → Checks cache (miss) → Starts computation
T+0.001s:  User B requests RSI_14 → Checks cache (miss) → Starts computation ❌ DUPLICATE!
T+0.002s:  User C requests RSI_14 → Checks cache (miss) → Starts computation ❌ DUPLICATE!
```

**Solution**: Distributed lock pattern

---

## Implementation: Distributed Lock Pattern

```python
# app/services/indicator_cache_manager.py

import redis.asyncio as redis
import json
import asyncio
from typing import Dict, Optional
from contextlib import asynccontextmanager

class IndicatorCacheManager:
    """
    Manages indicator computation with distributed locking to prevent
    duplicate computations when multiple users request the same indicator.
    """

    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self.lock_timeout = 30  # 30 seconds max computation time

    async def get_or_compute_indicator(
        self,
        symbol: str,
        timeframe: str,
        indicator_id: str,
        compute_fn,  # Function to compute indicator if not cached
        ttl: int = 600
    ) -> Dict:
        """
        Get indicator value from cache, or compute if not available.
        Uses distributed lock to prevent duplicate computations.

        Args:
            symbol: e.g., "NIFTY50"
            timeframe: e.g., "5min"
            indicator_id: e.g., "RSI_14"
            compute_fn: Async function to compute indicator value
            ttl: Cache TTL in seconds

        Returns:
            Indicator value dict
        """
        cache_key = f"indicator:{symbol}:{timeframe}:{indicator_id}:latest"

        # 1. Try cache first (fast path)
        cached = await self.redis.get(cache_key)
        if cached:
            # ✅ Cache hit - return immediately
            return json.loads(cached)

        # 2. Cache miss - need to compute
        # But use distributed lock to prevent duplicate computations
        lock_key = f"lock:indicator:{symbol}:{timeframe}:{indicator_id}"

        async with self._acquire_lock(lock_key):
            # 3. Double-check cache after acquiring lock
            # (another process might have computed it while we waited for lock)
            cached = await self.redis.get(cache_key)
            if cached:
                # ✅ Another process computed it - use that result
                return json.loads(cached)

            # 4. Still not cached - we're the first, compute it
            value = await compute_fn(symbol, timeframe, indicator_id)

            # 5. Store in cache
            await self.redis.set(
                cache_key,
                json.dumps(value),
                ex=ttl
            )

            return value

    @asynccontextmanager
    async def _acquire_lock(self, lock_key: str):
        """
        Acquire distributed lock using Redis.
        Uses SET NX (set if not exists) with timeout.
        """
        lock_acquired = False
        lock_value = f"{asyncio.current_task().get_name()}_{id(asyncio.current_task())}"

        try:
            # Try to acquire lock (non-blocking with retries)
            for attempt in range(50):  # Try for up to 5 seconds (50 * 100ms)
                # SET NX EX - atomic set if not exists with expiration
                lock_acquired = await self.redis.set(
                    lock_key,
                    lock_value,
                    nx=True,  # Only set if not exists
                    ex=self.lock_timeout
                )

                if lock_acquired:
                    # ✅ Lock acquired
                    break

                # Lock is held by another process - wait and retry
                await asyncio.sleep(0.1)  # 100ms

            if not lock_acquired:
                # Timeout - proceed anyway (safety measure)
                # This prevents deadlock if lock holder crashes
                print(f"Warning: Could not acquire lock for {lock_key}, proceeding anyway")

            yield

        finally:
            # Release lock (only if we acquired it)
            if lock_acquired:
                # Use Lua script for atomic check-and-delete
                release_script = """
                if redis.call("get", KEYS[1]) == ARGV[1] then
                    return redis.call("del", KEYS[1])
                else
                    return 0
                end
                """
                await self.redis.eval(release_script, 1, lock_key, lock_value)
```

---

## Usage in API Endpoints

### Example: Indicator API

```python
# app/routes/indicators_api.py

from fastapi import APIRouter, Depends
from typing import List

router = APIRouter(prefix="/indicators", tags=["Indicators"])

@router.get("/{symbol}/current")
async def get_current_indicators(
    symbol: str,
    timeframe: str,
    indicators: str,  # Comma-separated: "RSI_14,MACD_12_26_9"
    cache_manager: IndicatorCacheManager = Depends(get_cache_manager),
    indicator_computer: IndicatorComputer = Depends(get_indicator_computer)
):
    """
    Get current indicator values.
    Multiple users requesting same indicators get cached results.
    """
    indicator_ids = indicators.split(',')

    results = {}

    for indicator_id in indicator_ids:
        # Define compute function
        async def compute_fn(sym, tf, ind_id):
            # Parse indicator name and params from ID
            # e.g., "RSI_14" → name="RSI", params={"length": 14}
            name, params = parse_indicator_id(ind_id)

            # Fetch OHLCV data
            ohlcv = await fetch_ohlcv(sym, tf, lookback=100)

            # Compute indicator
            value = await indicator_computer.compute(name, params, ohlcv)

            return {
                "ts": int(time.time()),
                "value": value,
                "timeframe": tf
            }

        # Get or compute with caching
        results[indicator_id] = await cache_manager.get_or_compute_indicator(
            symbol=symbol,
            timeframe=timeframe,
            indicator_id=indicator_id,
            compute_fn=compute_fn,
            ttl=get_indicator_ttl(timeframe)
        )

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "indicators": results
    }
```

---

## Flow Diagram: Concurrent Requests with Lock

```
User A, B, C all request RSI_14 on NIFTY50 5min at T+0s

┌─────────┐      ┌─────────┐      ┌─────────┐
│ User A  │      │ User B  │      │ User C  │
└────┬────┘      └────┬────┘      └────┬────┘
     │                │                │
     │                │                │
     ├─── Check cache ────────────────┤
     │    (miss)           (miss)  (miss)
     │                │                │
     ├─── Try acquire lock ───────────┤
     │    ✅ SUCCESS     ❌ FAIL   ❌ FAIL
     │                │                │
     │                ├─ Wait for lock─┤
     │                │                │
     ├─ Double-check cache             │
     │    (still miss)                 │
     │                │                │
     ├─ COMPUTE RSI_14                 │
     │    (10ms)                       │
     │                │                │
     ├─ Store in cache                 │
     │    TTL=600s                     │
     │                │                │
     ├─ Release lock                   │
     │                │                │
     │                ├─ Lock released ┤
     │                │                │
     │                ├─ Check cache ──┤
     │                │   ✅ HIT!  ✅ HIT!
     │                │                │
     ├─ Return to User A               │
     │                ├─ Return to User B
     │                │                ├─ Return to User C
     ▼                ▼                ▼
```

**Result**: 1 computation, 3 users served, no duplicates!

---

## Integration with Subscription Management

For even better efficiency, combine with subscription-based computation:

```python
# app/services/indicator_subscription_computer.py

class IndicatorSubscriptionComputer:
    """
    Computes indicators continuously for subscribed symbol/timeframe/indicator.
    Multiple users subscribing to same indicator share the computation.
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        subscription_manager: IndicatorSubscriptionManager,
        cache_manager: IndicatorCacheManager
    ):
        self.redis = redis_client
        self.sub_manager = subscription_manager
        self.cache_manager = cache_manager
        self.running_computations = {}  # Track active computation tasks

    async def handle_subscription(
        self,
        user_id: str,
        session_id: str,
        symbol: str,
        timeframe: str,
        indicator_id: str
    ):
        """
        Handle user subscription to an indicator.
        If this is the first subscriber, start continuous computation.
        If others already subscribed, join existing computation stream.
        """
        # Subscribe user (increments ref count)
        is_new = await self.sub_manager.subscribe(
            user_id=user_id,
            session_id=session_id,
            symbol=symbol,
            timeframe=timeframe,
            indicator_id=indicator_id
        )

        computation_key = f"{symbol}:{timeframe}:{indicator_id}"

        if is_new:
            # First subscriber - start continuous computation
            print(f"Starting computation for {computation_key} (first subscriber)")

            task = asyncio.create_task(
                self._continuous_computation(symbol, timeframe, indicator_id)
            )
            self.running_computations[computation_key] = task
        else:
            # Additional subscriber - computation already running
            print(f"User joined existing computation for {computation_key}")

    async def handle_unsubscription(
        self,
        user_id: str,
        session_id: str,
        symbol: str,
        timeframe: str,
        indicator_id: str
    ):
        """
        Handle user unsubscription.
        If this was the last subscriber, stop continuous computation.
        """
        is_last = await self.sub_manager.unsubscribe(
            user_id=user_id,
            session_id=session_id,
            symbol=symbol,
            timeframe=timeframe,
            indicator_id=indicator_id
        )

        computation_key = f"{symbol}:{timeframe}:{indicator_id}"

        if is_last:
            # Last subscriber - stop computation
            print(f"Stopping computation for {computation_key} (no more subscribers)")

            task = self.running_computations.get(computation_key)
            if task:
                task.cancel()
                del self.running_computations[computation_key]

    async def _continuous_computation(
        self,
        symbol: str,
        timeframe: str,
        indicator_id: str
    ):
        """
        Continuously compute indicator and update cache.
        Runs as long as there are active subscribers.
        """
        computation_interval = self._get_computation_interval(timeframe)

        try:
            while True:
                # Check if there are still subscribers
                sub_key = f"indicator_sub:{symbol}:{timeframe}:{indicator_id}"
                sub_data = await self.redis.get(sub_key)

                if not sub_data:
                    # No more subscribers - stop
                    print(f"No subscribers for {symbol}:{timeframe}:{indicator_id}, stopping")
                    break

                # Compute indicator
                try:
                    value = await self._compute_indicator_value(
                        symbol, timeframe, indicator_id
                    )

                    # Store in cache
                    cache_key = f"indicator:{symbol}:{timeframe}:{indicator_id}:latest"
                    await self.redis.set(
                        cache_key,
                        json.dumps(value),
                        ex=computation_interval * 2  # TTL = 2x computation interval
                    )

                    # Publish update to subscribers via WebSocket
                    await self.redis.publish(
                        f"indicator_updates:{symbol}:{timeframe}:{indicator_id}",
                        json.dumps(value)
                    )

                except Exception as e:
                    print(f"Error computing {indicator_id}: {e}")

                # Wait before next computation
                await asyncio.sleep(computation_interval)

        except asyncio.CancelledError:
            print(f"Computation cancelled for {symbol}:{timeframe}:{indicator_id}")

    def _get_computation_interval(self, timeframe: str) -> int:
        """Get how often to recompute indicator"""
        interval_map = {
            "1min": 60,      # Every 1 minute
            "5min": 300,     # Every 5 minutes
            "15min": 900,    # Every 15 minutes
            "30min": 1800,   # Every 30 minutes
            "1h": 3600,      # Every 1 hour
            "4h": 14400,     # Every 4 hours
            "1d": 86400      # Every 1 day
        }
        return interval_map.get(timeframe, 300)

    async def _compute_indicator_value(
        self,
        symbol: str,
        timeframe: str,
        indicator_id: str
    ) -> Dict:
        """Compute indicator value"""
        # Parse indicator
        name, params = parse_indicator_id(indicator_id)

        # Fetch OHLCV
        ohlcv = await fetch_ohlcv(symbol, timeframe, lookback=100)

        # Compute
        indicator_computer = IndicatorComputer()
        value = await indicator_computer.compute(name, params, ohlcv)

        return {
            "ts": int(time.time()),
            "value": value,
            "timeframe": timeframe
        }
```

---

## Complete Flow: Multi-User Subscription

### Scenario: 5 users subscribe to RSI_14 on NIFTY50 5min

```
T+0s:  User 1 subscribes
       → First subscriber!
       → Start continuous computation task
       → Computes RSI_14 every 5 minutes
       → Stores in cache: indicator:NIFTY50:5min:RSI_14:latest

T+10s: User 2 subscribes
       → Ref count: 1 → 2
       → Computation already running ✅
       → User 2 gets cached value immediately

T+20s: User 3 subscribes
       → Ref count: 2 → 3
       → Computation already running ✅
       → User 3 gets cached value immediately

T+30s: User 4 subscribes
       → Ref count: 3 → 4
       → Computation already running ✅

T+40s: User 5 subscribes
       → Ref count: 4 → 5
       → Computation already running ✅

T+300s: (5 minutes later)
       → Continuous computation runs again
       → Updates cache with new RSI value
       → All 5 users receive WebSocket update simultaneously

T+600s: User 1, 2, 3 unsubscribe
       → Ref count: 5 → 4 → 3 → 2
       → Computation keeps running (still have subscribers)

T+700s: User 4 unsubscribes
       → Ref count: 2 → 1
       → Computation keeps running (still have 1 subscriber)

T+800s: User 5 unsubscribes
       → Ref count: 1 → 0
       → Last subscriber! Stop computation task ✅
       → Cache entry expires after TTL
```

**Result**:
- 1 continuous computation task
- Serves 5 users efficiently
- Automatically starts/stops based on demand
- No wasted resources when no one is subscribed

---

## Benefits Summary

| Scenario | Without Caching | With Cache + Lock | With Subscription |
|----------|----------------|-------------------|-------------------|
| **3 sequential users** | 3 computations | 1 computation | 1 computation |
| **3 concurrent users** | 3 computations | 1 computation | 1 computation |
| **5 users over 10 min** | 5 computations | 1-2 computations | 1 computation |
| **Continuous updates** | Poll-based (inefficient) | Poll-based | Push-based (WebSocket) |
| **Auto cleanup** | Manual | Via TTL | Via ref counting |

---

## Implementation Priority

### Phase 1 (Immediate): Cache-First Pattern
```python
# Simple cache lookup in API endpoints
cached = await redis.get(f"indicator:{symbol}:{timeframe}:{indicator_id}")
if cached:
    return json.loads(cached)
```

### Phase 2 (Week 1): Distributed Lock
```python
# Add IndicatorCacheManager with lock pattern
await cache_manager.get_or_compute_indicator(...)
```

### Phase 3 (Week 2): Subscription-Based Computation
```python
# Add continuous computation with ref counting
await subscription_computer.handle_subscription(...)
```

---

## Monitoring

Add metrics to track cache efficiency:

```python
from prometheus_client import Counter, Gauge

indicator_cache_hits = Counter(
    "indicator_cache_hits_total",
    "Number of cache hits",
    ["symbol", "timeframe", "indicator"]
)

indicator_cache_misses = Counter(
    "indicator_cache_misses_total",
    "Number of cache misses",
    ["symbol", "timeframe", "indicator"]
)

indicator_computations = Counter(
    "indicator_computations_total",
    "Number of actual computations",
    ["symbol", "timeframe", "indicator"]
)

indicator_shared_users = Gauge(
    "indicator_shared_users",
    "Number of users sharing same indicator computation",
    ["symbol", "timeframe", "indicator"]
)
```

**Target Metrics**:
- Cache hit rate: >95%
- Avg users per computation: >3
- Computation reuse ratio: >10:1

---

## Summary

✅ **Yes, multiple users requesting the same indicator get served from cache**

**How it works**:
1. **Cache-first lookup**: Check Redis before computing
2. **Distributed lock**: Prevent duplicate concurrent computations
3. **Subscription ref counting**: One continuous computation serves many users
4. **Automatic cleanup**: Stop computing when no more subscribers

**Efficiency gains**:
- 10x-100x fewer computations
- Sub-millisecond response for cached data
- Real-time WebSocket updates
- Automatic resource management
