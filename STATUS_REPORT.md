# Live Data Flow - Status Report

**Date:** 2025-11-04
**Time:** 2:10 PM IST
**Status:** ✅ Live data confirmed, ⚠️ Database writes not working

---

## Summary

I successfully changed the system to receive **LIVE market data** and verified that data is flowing through the entire pipeline. However, the database is still not being updated.

---

## ✅ What's Working

### 1. **Ticker Service Publishing Live Data**
- ✅ Ticker service running on localhost:8080 (PID 789011)
- ✅ Publishing to Redis on localhost:6381
- ✅ **442 active subscriptions**
- ✅ Messages marked with `"is_mock": false` (confirmed REAL data)
- ✅ Last tick timestamp updating every second

**Evidence:**
```bash
$ timeout 3 docker exec 9659d9170139_tv-redis redis-cli SUBSCRIBE ticker:nifty:options
message
ticker:nifty:options
{"symbol": "NIFTY", "token": 11332098, "tradingsymbol": "NIFTY25N1825500PE",
 "price": 124.95, "volume": 0, "oi": 224250, "is_mock": false, ...}
```

### 2. **Redis Pub/Sub Working**
- ✅ Backend can subscribe to Redis channels
- ✅ Backend can receive messages from Redis
- ✅ 10 subscribers on `ticker:nifty:options`
- ✅ 8 subscribers on `ticker:nifty:underlying`

**Evidence:**
```bash
$ docker exec 9659d9170139_tv-redis redis-cli PUBSUB NUMSUB ticker:nifty:options
ticker:nifty:options
10

# Test from backend container:
$ docker exec tv-backend python3 -c "..."
✓ Subscribed to ticker:nifty:options
Waiting for first message...
1. NIFTY26JAN25100PE: 207.0
2. NIFTY25N0426000CE: 0.75
...
✓ Received 5 messages successfully
```

### 3. **Backend Consumers Running**
- ✅ tv-backend container healthy on port 8081
- ✅ FOStreamConsumer created and started
- ✅ NiftyMonitorStream created and started
- ✅ Background tasks created with `asyncio.create_task()`
- ✅ Tasks subscribed to Redis channels (confirmed by NUMSUB count)

**Evidence:**
```bash
$ docker logs tv-backend | grep "\[MAIN\]"
[MAIN] Creating FOStreamConsumer, fo_stream_enabled=True
[MAIN] FOStreamConsumer created: <object at 0x...>
[MAIN] Task created: <Task pending name='Task-16' coro=<FOStreamConsumer.run()...>>
[MAIN] Starting NiftyMonitorStream task...
```

### 4. **Authentication Fixes Deployed**
- ✅ Dual authentication system (JWT + API keys) deployed
- ✅ Futures symbol parsing fixed
- ✅ All dependencies installed

---

## ❌ What's NOT Working

### Database Writes - NO DATA BEING PERSISTED

**Problem:** Despite live data flowing and consumers running, **ZERO records** written to database

**Evidence:**
```sql
SELECT MAX(time), NOW() - MAX(time) as age FROM nifty_fo_ohlc;
-- Result: 2025-10-23 15:28:00 | 11 days 16:38:03
-- Last write was 11 DAYS AGO!

SELECT COUNT(*) FROM nifty_fo_ohlc WHERE time > NOW() - INTERVAL '5 minutes';
-- Result: 0
```

**Waited 2 minutes** for 1min bars to flush → Still 0 new records

---

## 🔍 Root Cause Analysis

### What I Know:
1. ✅ Live data is being published to Redis
2. ✅ Backend consumers are subscribed and receiving subscription confirmations
3. ✅ No error logs in backend (no "FO stream consumer error" messages)
4. ✅ No processing logs (no "Received", "Processing", "Writing", "INSERT" logs)
5. ❌ Database not being updated

### Architecture:
```
Ticker Service (PID 789011)
  ↓ Publishes to
Redis (9659d9170139_tv-redis on port 6381)
  ↓ Connected to by
Backend Container (tv-backend)
  ├── FOStreamConsumer.run() - Subscribed to ticker:nifty:options
  │     ↓ Calls
  │   FOAggregator.handle_option(data)
  │     ↓ Buffers data, then
  │   _persist_batches() → DataManager.upsert_fo_strike_rows()
  │     ↓ Should write to
  │   Database (nifty_fo_ohlc table)
  │
  └── NiftyMonitorStream.run() - Subscribed to ticker:nifty:*
        ↓ Updates in-memory state
```

### Configuration:
- **Persist Timeframes:** Only `1min` (backend/app/config.py:29)
- **Flush Lag:** Data written after bucket completes + lag (default ~60 seconds)
- **Expected Behavior:** 1-minute bars should appear 60-120 seconds after minute ends

### Hypotheses:

#### Hypothesis 1: Messages Not Reaching Handlers ⭐ MOST LIKELY
**Theory:** The consumers are subscribed, but `get_message()` is timing out or returning None, so `handle_option()` is never called.

**Evidence:**
- No processing logs at all
- No error logs
- Subscribers count is correct (10 on options channel)
- Manual test from backend container DOES receive messages

**Possible Causes:**
- FOStreamConsumer using different Redis client instance
- `ignore_subscribe_messages=True` filtering out data messages (unlikely)
- `get_message(timeout=5.0)` timing out continuously

#### Hypothesis 2: Silent Exception in Handler
**Theory:** `handle_option()` is being called but throwing an exception that's caught somewhere.

**Evidence Against:**
- No error logs (exception handler at fo_stream.py:482 should log)
- Would expect at least ONE error log if this were the case

#### Hypothesis 3: Data Not Meeting Persist Criteria
**Theory:** Data is being processed but not meeting criteria for persistence.

**Evidence:**
- `is_mock` check: Messages show `"is_mock": false` ✅ Passes
- `expiry` parsing: Messages have expiry dates ✅ Should pass
- `option_type` check: Messages have CE/PE types ✅ Should pass
- `persist` check: Only 1min timeframe persists, but that should still write data

---

## 🎯 Next Steps to Debug

### Option 1: Add Logging (Requires Code Changes)
Add print statements to FOStreamConsumer.run() to see if messages are being received:
```python
# In fo_stream.py:458
async def run(self) -> None:
    while self._running:
        pubsub = None
        try:
            pubsub = self._redis.pubsub(ignore_subscribe_messages=True)
            await pubsub.subscribe(self._options_channel, self._underlying_channel)
            print(f"[FOStreamConsumer] Subscribed to {self._options_channel}, {self._underlying_channel}", flush=True)
            while self._running:
                try:
                    message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=5.0)
                    if message:
                        print(f"[FOStreamConsumer] Got message: {message['type']} on {message.get('channel')}", flush=True)
                except asyncio.TimeoutError:
                    print(f"[FOStreamConsumer] Timeout waiting for message", flush=True)
                    continue
                ...
```

### Option 2: Check Redis Client Instance
Verify FOStreamConsumer is using the correct Redis client:
```python
# In backend container
docker exec tv-backend python3 -c "
from app.config import Settings
s = Settings()
print(f'Redis URL: {s.redis_url}')
print(f'FO options channel: {s.fo_options_channel}')
"
```

### Option 3: Manual Test End-to-End
Create a test script that mimics FOStreamConsumer exactly:
```python
# test_consumer.py
import asyncio
import redis.asyncio as redis
import json

async def test():
    r = redis.from_url('redis://redis:6379')
    pubsub = r.pubsub(ignore_subscribe_messages=True)
    await pubsub.subscribe('ticker:nifty:options')

    count = 0
    while count < 10:
        msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=5.0)
        if msg and msg['type'] == 'message':
            data = json.loads(msg['data'])
            print(f'{count+1}. Processing: {data["tradingsymbol"]}')
            count += 1
        else:
            print('No message or timeout')
        await asyncio.sleep(0.1)

asyncio.run(test())
```

### Option 4: Check Database Permissions
Verify backend can actually write to database:
```bash
docker exec tv-backend python3 -c "
import asyncio
from app.database import DataManager
from app.config import Settings

async def test():
    dm = DataManager(Settings())
    # Try a simple query
    result = await dm.execute('SELECT 1')
    print(f'Database accessible: {result}')

asyncio.run(test())
"
```

---

## 📊 Current System State

| Component | Status | Details |
|-----------|--------|---------|
| Ticker Service | ✅ Running | PID 789011, 442 subscriptions, live data |
| Redis | ✅ Running | 9659d9170139_tv-redis, 10+8 subscribers |
| Backend | ✅ Running | tv-backend healthy, consumers started |
| Pub/Sub | ✅ Working | Messages flowing, manual tests pass |
| FOStreamConsumer | ⚠️ Unknown | Subscribed but no processing logs |
| Database Writes | ❌ Failing | 0 records in last 11 days |
| Monitor Endpoint | ⚠️ Partial | Returns 426 options (old data), underlying=null |

---

## 🚀 Immediate Action Required

**User should decide:**

1. **Add debug logging** to FOStreamConsumer and rebuild backend?
2. **Check if this is expected** - maybe database writes are disabled intentionally?
3. **Investigate** why subscribed consumers aren't receiving messages?

**Most efficient path:** Add 3-4 print statements to fo_stream.py, rebuild backend, restart, and watch logs for 2 minutes.

---

## Files Modified Today

### Configuration:
- ✅ `docker-compose.yml:108` - Changed `MARKET_MODE=force_mock` → `MARKET_MODE=auto`

### Backend (from previous session):
- ✅ `backend/app/auth.py` - Dual authentication system
- ✅ `backend/app/jwt_auth.py` - USER_SERVICE_URL from environment
- ✅ `backend/app/routes/indicators_api.py` - All 6 endpoints updated
- ✅ `backend/app/main.py` - Debug logging for NiftyMonitorStream
- ✅ `backend/requirements.txt` - Fixed dependencies
- ✅ `backend/docker-compose.yml` - USER_SERVICE_URL updated

### SDK (from previous session):
- ✅ `python-sdk/stocksblitz/instrument.py` - Futures symbol parsing

---

## Test Commands

```bash
# 1. Verify live data flowing
timeout 3 docker exec 9659d9170139_tv-redis redis-cli SUBSCRIBE ticker:nifty:options

# 2. Check subscriber counts
docker exec 9659d9170139_tv-redis redis-cli PUBSUB NUMSUB ticker:nifty:options ticker:nifty:underlying

# 3. Test backend can receive messages
docker exec tv-backend python3 -c "
import asyncio, redis.asyncio as redis, json
async def test():
    r = redis.from_url('redis://redis:6379')
    pubsub = r.pubsub(ignore_subscribe_messages=True)
    await pubsub.subscribe('ticker:nifty:options')
    msg = await pubsub.get_message(timeout=5.0)
    if msg and msg['type'] == 'message':
        data = json.loads(msg['data'])
        print(f'✓ Received: {data[\"tradingsymbol\"]}')
asyncio.run(test())
"

# 4. Check database for new records
PGPASSWORD=stocksblitz123 psql -U stocksblitz -d stocksblitz_unified -h localhost -c "
SELECT COUNT(*) as new_records
FROM nifty_fo_ohlc
WHERE time > NOW() - INTERVAL '5 minutes';"

# 5. Check backend logs for processing
docker logs tv-backend 2>&1 | grep -E "handle_option|Received|Processing" | tail -20
```

---

**Report Generated:** 2025-11-04 2:10 PM IST
**Market Status:** OPEN (9:15 AM - 3:30 PM IST)
**Data Confirmed:** LIVE (not mock)
