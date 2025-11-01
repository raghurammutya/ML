# Integration Testing Guide - Subscription Events

**Date**: November 1, 2025
**Status**: Ready for Testing
**Purpose**: Guide for testing subscription event integration between ticker service and backend

---

## Overview

This guide covers testing the complete subscription event flow:

```
Ticker Service → Redis Pub/Sub → Backend Event Listener → Immediate Backfill → TimescaleDB
```

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Local Testing (Without Ticker Service)](#local-testing-without-ticker-service)
3. [Integration Testing (With Ticker Service)](#integration-testing-with-ticker-service)
4. [Test Scenarios](#test-scenarios)
5. [Expected Outcomes](#expected-outcomes)
6. [Troubleshooting](#troubleshooting)
7. [Performance Benchmarks](#performance-benchmarks)

---

## Prerequisites

### Required Services Running

- ✅ Redis (localhost:6379 or configured URL)
- ✅ TimescaleDB (with stocksblitz_unified database)
- ✅ Backend API (localhost:8000 or configured port)
- ⚠️ Ticker Service (localhost:8080) - only for integration tests

### Required Configuration

**Backend `.env`**:
```bash
# Subscription event listener
SUBSCRIPTION_EVENTS_ENABLED=true
REDIS_CHANNEL_PREFIX=ticker:nifty

# Backfill settings
BACKFILL_ENABLED=true
BACKFILL_IMMEDIATE_ON_SUBSCRIBE=true
BACKFILL_SUBSCRIPTION_AWARE=true

# Redis
REDIS_URL=redis://localhost:6379

# Database
DB_HOST=localhost
DB_PORT=5432
DB_NAME=stocksblitz_unified
DB_USER=stocksblitz
DB_PASSWORD=stocksblitz123
```

### Test Instruments

**Option Contract** (for testing):
```json
{
  "instrument_token": 13660418,
  "tradingsymbol": "NIFTY25NOV24500CE",
  "segment": "NFO-OPT",
  "exchange": "NFO"
}
```

**Future Contract** (for testing):
```json
{
  "instrument_token": 13660674,
  "tradingsymbol": "NIFTY25NOVFUT",
  "segment": "NFO-FUT",
  "exchange": "NFO"
}
```

**Underlying** (for testing):
```json
{
  "instrument_token": 256265,
  "tradingsymbol": "NIFTY 50",
  "segment": "INDICES",
  "exchange": "NSE"
}
```

---

## Local Testing (Without Ticker Service)

### Test 1: Backend Startup Verification

**Objective**: Verify subscription event listener starts successfully

**Steps**:

1. **Start backend**:
```bash
cd /home/stocksadmin/Quantagro/tradingview-viz/backend
poetry run uvicorn app.main:app --reload --log-level=info
```

2. **Check logs for**:
```
INFO - Subscription event listener started
INFO - Subscribed to ticker service events: ticker:nifty:events
```

**Expected Result**: ✅ Listener starts without errors

---

### Test 2: Simulated Subscription Created Event

**Objective**: Verify backend receives and processes subscription_created events

**Terminal 1 - Backend Running**:
```bash
poetry run uvicorn app.main:app --reload --log-level=info
# Watch for log messages
```

**Terminal 2 - Publish Test Event**:
```bash
redis-cli PUBLISH ticker:nifty:events '{
  "event_type": "subscription_created",
  "instrument_token": 256265,
  "metadata": {
    "tradingsymbol": "NIFTY 50",
    "segment": "INDICES",
    "requested_mode": "FULL",
    "account_id": "primary"
  },
  "timestamp": 1730462400
}'
```

**Expected Backend Logs**:
```
INFO - Received subscription event: subscription_created for token 256265
INFO - Subscription created: NIFTY 50 (token: 256265), triggering immediate backfill
INFO - Starting immediate backfill for instrument token 256265
INFO - Immediate backfill: underlying NIFTY 50 - {N} bars
INFO - Immediate backfill completed for instrument 256265 (NIFTY 50)
```

**Verification**:
```sql
-- Check if data was inserted
SELECT COUNT(*), MIN(time), MAX(time)
FROM minute_bars
WHERE symbol = 'NIFTY 50'
  AND time > NOW() - INTERVAL '2 hours';
```

**Expected Result**: ✅ Bars inserted within last 2 hours

---

### Test 3: Simulated Subscription Removed Event

**Objective**: Verify backend handles subscription_removed events

**Terminal 2 - Publish Removal Event**:
```bash
redis-cli PUBLISH ticker:nifty:events '{
  "event_type": "subscription_removed",
  "instrument_token": 256265,
  "metadata": {
    "tradingsymbol": "NIFTY 50",
    "segment": "INDICES"
  },
  "timestamp": 1730462500
}'
```

**Expected Backend Logs**:
```
INFO - Received subscription event: subscription_removed for token 256265
INFO - Subscription deleted: NIFTY 50 (token: 256265)
```

**Expected Result**: ✅ Event logged, no errors

---

### Test 4: Multiple Simultaneous Events

**Objective**: Verify backend handles concurrent subscription events

**Terminal 2 - Publish Multiple Events**:
```bash
# Publish 3 events rapidly
redis-cli PUBLISH ticker:nifty:events '{"event_type":"subscription_created","instrument_token":256265,"metadata":{"tradingsymbol":"NIFTY 50","segment":"INDICES"},"timestamp":1730462400}'

redis-cli PUBLISH ticker:nifty:events '{"event_type":"subscription_created","instrument_token":13660418,"metadata":{"tradingsymbol":"NIFTY25NOV24500CE","segment":"NFO-OPT"},"timestamp":1730462401}'

redis-cli PUBLISH ticker:nifty:events '{"event_type":"subscription_created","instrument_token":13660674,"metadata":{"tradingsymbol":"NIFTY25NOVFUT","segment":"NFO-FUT"},"timestamp":1730462402}'
```

**Expected Result**: ✅ All events processed without blocking

---

### Test 5: Invalid Event Handling

**Objective**: Verify graceful handling of malformed events

**Terminal 2 - Publish Invalid Event**:
```bash
# Missing instrument_token
redis-cli PUBLISH ticker:nifty:events '{
  "event_type": "subscription_created",
  "metadata": {"tradingsymbol": "TEST"}
}'

# Invalid JSON
redis-cli PUBLISH ticker:nifty:events 'this is not json'

# Unknown event type
redis-cli PUBLISH ticker:nifty:events '{
  "event_type": "unknown_event",
  "instrument_token": 123
}'
```

**Expected Backend Logs**:
```
ERROR - Failed to parse subscription event: ...
WARNING - Unknown event type: unknown_event
```

**Expected Result**: ✅ Errors logged but service continues running

---

## Integration Testing (With Ticker Service)

### Prerequisites

- ✅ Ticker service running on localhost:8080
- ✅ Ticker service has incremental subscription updates implemented
- ✅ Ticker service publishes events to `ticker:nifty:events`

---

### Test 6: End-to-End Subscription Flow

**Objective**: Verify complete flow from subscription API call to data in database

**Terminal 1 - Backend Running**:
```bash
cd /home/stocksadmin/Quantagro/tradingview-viz/backend
poetry run uvicorn app.main:app --reload --log-level=info
```

**Terminal 2 - Monitor Redis Events**:
```bash
redis-cli SUBSCRIBE ticker:nifty:events
```

**Terminal 3 - Subscribe via Ticker Service API**:
```bash
curl -X POST http://localhost:8080/subscriptions \
  -H "Content-Type: application/json" \
  -d '{
    "instrument_token": 13660418,
    "requested_mode": "FULL"
  }'
```

**Expected Flow**:

1. **Ticker Service API Response** (Terminal 3):
```json
{
  "status": "subscribed",
  "instrument_token": 13660418,
  "tradingsymbol": "NIFTY25NOV24500CE"
}
```

2. **Redis Event Published** (Terminal 2):
```
1) "message"
2) "ticker:nifty:events"
3) "{\"event_type\":\"subscription_created\",\"instrument_token\":13660418,...}"
```

3. **Backend Processes Event** (Terminal 1):
```
INFO - Received subscription event: subscription_created for token 13660418
INFO - Starting immediate backfill for instrument token 13660418
INFO - Immediate backfill completed for instrument 13660418
```

4. **Verify Real-Time Data** (30 seconds later):
```bash
redis-cli
> SUBSCRIBE ticker:nifty:options
# Should see live ticks for token 13660418
```

5. **Verify Historical Data**:
```sql
SELECT COUNT(*), MIN(bucket_time), MAX(bucket_time)
FROM fo_strike_distribution
WHERE symbol = 'NIFTY50'
  AND bucket_time > NOW() - INTERVAL '2 hours';
```

**Expected Result**:
- ✅ Subscription created in <1 second
- ✅ Event published to Redis
- ✅ Backend triggered immediate backfill
- ✅ Historical data available within 30 seconds
- ✅ Real-time data flowing

---

### Test 7: Subscription Removal Flow

**Objective**: Verify cleanup when subscription removed

**Terminal 3 - Remove Subscription**:
```bash
curl -X DELETE http://localhost:8080/subscriptions/13660418
```

**Expected**:
1. Ticker service publishes `subscription_removed` event
2. Backend logs subscription deletion
3. Real-time data stops flowing for this token

---

### Test 8: High Load - Subscribe to Option Chain

**Objective**: Test performance with multiple subscriptions

**Terminal 3 - Subscribe to Full Chain**:
```bash
# Get option chain tokens
curl -X GET http://localhost:8080/instruments?segment=NFO-OPT&underlying=NIFTY

# Subscribe to top 20 strikes
for token in 13660418 13660674 13660930 ...; do
  curl -X POST http://localhost:8080/subscriptions \
    -H "Content-Type: application/json" \
    -d "{\"instrument_token\": $token, \"requested_mode\": \"FULL\"}"
  sleep 0.1  # Rate limit
done
```

**Monitor**:
- Backend logs: All events processed
- Redis monitor: Events published successfully
- Database: Historical data inserted for all tokens

**Expected Result**:
- ✅ All subscriptions created in <20 seconds (20 tokens × <1 sec each)
- ✅ All immediate backfills triggered
- ✅ No events lost

---

## Test Scenarios

### Scenario 1: User Opens Monitor Page

**User Action**: Opens Nifty Monitor page in frontend

**Expected Backend Flow**:
1. Frontend requests option chain metadata
2. Backend returns metadata (may be empty if not subscribed)
3. Frontend calls backend API to subscribe to ATM options
4. Backend calls ticker service subscription API
5. Ticker service publishes subscription events
6. Backend event listener triggers immediate backfill
7. Within 30 seconds, historical data available
8. Real-time updates start flowing immediately

**Success Criteria**:
- ✅ Initial page load shows "loading" state
- ✅ Historical data appears within 30 seconds
- ✅ Real-time updates start immediately
- ✅ No errors in logs

---

### Scenario 2: User Changes Expiry

**User Action**: Switches from Nov expiry to Dec expiry

**Expected Backend Flow**:
1. Frontend unsubscribes from Nov options (optional)
2. Frontend subscribes to Dec options
3. Ticker service publishes multiple subscription_created events
4. Backend triggers immediate backfill for each Dec option
5. Historical data available within 30 seconds

**Success Criteria**:
- ✅ Dec options data loads within 30 seconds
- ✅ Nov options continue updating (if not unsubscribed)
- ✅ No disruption to Nov data flow

---

### Scenario 3: Backend Restart During Active Subscriptions

**Test Steps**:
1. Subscribe to 10 options via ticker service
2. Verify data flowing
3. Restart backend service
4. Verify data continues flowing

**Expected Result**:
- ✅ Event listener reconnects to Redis
- ✅ Existing subscriptions continue (ticker service maintains them)
- ✅ No data loss after restart

---

### Scenario 4: Redis Outage

**Test Steps**:
1. Subscribe to options
2. Stop Redis service
3. Wait 30 seconds
4. Start Redis service

**Expected Result**:
- ✅ Backend logs Redis connection error
- ✅ Backend attempts reconnection
- ✅ Event listener restarts automatically
- ✅ No crash, graceful degradation

---

### Scenario 5: Ticker Service Outage

**Test Steps**:
1. Stop ticker service
2. Attempt subscription via API (should fail)
3. Start ticker service
4. Retry subscription

**Expected Result**:
- ✅ Backend handles API errors gracefully
- ✅ No events published during outage
- ✅ Subscriptions work after recovery

---

## Expected Outcomes

### Performance Benchmarks

| Metric | Target | Acceptable | Unacceptable |
|--------|--------|------------|--------------|
| **Subscription activation** | <1 second | <2 seconds | >5 seconds |
| **Event processing latency** | <100ms | <500ms | >1 second |
| **Immediate backfill start** | <500ms | <2 seconds | >5 seconds |
| **Historical data available** | <30 seconds | <60 seconds | >120 seconds |
| **Real-time data latency** | <100ms | <500ms | >1 second |
| **Concurrent subscriptions** | 50/second | 20/second | <10/second |

### Log Messages to Monitor

**Success Indicators** ✅:
```
INFO - Subscription event listener started
INFO - Subscribed to ticker service events: ticker:nifty:events
INFO - Received subscription event: subscription_created for token {token}
INFO - Starting immediate backfill for instrument token {token}
INFO - Immediate backfill completed for instrument {token}
```

**Warning Indicators** ⚠️:
```
WARNING - Instrument {token} not found in database
WARNING - No candles returned for underlying {symbol}
WARNING - Could not parse expiry date: {expiry}
```

**Error Indicators** ❌:
```
ERROR - Failed to parse subscription event: {error}
ERROR - Immediate backfill failed for token {token}: {error}
ERROR - Failed to fetch instrument details for token {token}: {error}
ERROR - Subscription event listener error: {error}
```

---

## Troubleshooting

### Issue: Event Listener Not Starting

**Symptoms**:
- No log message: "Subscription event listener started"

**Checks**:
1. `SUBSCRIPTION_EVENTS_ENABLED=true` in .env
2. Redis connection successful
3. No errors in startup logs

**Solution**:
```bash
# Check config
poetry run python -c "from app.config import get_settings; print(get_settings().subscription_events_enabled)"

# Check Redis
redis-cli PING

# Check logs
grep "Subscription event listener" logs/backend.log
```

---

### Issue: Events Not Received

**Symptoms**:
- Redis event published but backend doesn't log it

**Checks**:
1. Verify channel name: `ticker:nifty:events`
2. Check `REDIS_CHANNEL_PREFIX=ticker:nifty`
3. Verify event listener is subscribed

**Debug**:
```bash
# In backend container/terminal
redis-cli
> PUBSUB CHANNELS ticker:nifty:*
# Should show: "ticker:nifty:events"

> PUBSUB NUMSUB ticker:nifty:events
# Should show: at least 1 subscriber
```

---

### Issue: Immediate Backfill Not Triggered

**Symptoms**:
- Event received but no backfill log messages

**Checks**:
1. `BACKFILL_IMMEDIATE_ON_SUBSCRIBE=true`
2. Backfill manager initialized in main.py
3. No errors in event handler

**Debug**:
```python
# Check if method exists
# In Python shell:
from app.backfill import BackfillManager
print(hasattr(BackfillManager, 'backfill_instrument_immediate'))
# Should print: True
```

---

### Issue: Instrument Not Found in Database

**Symptoms**:
```
WARNING - Instrument {token} not found in database
```

**Solution**:
```sql
-- Check if instrument exists
SELECT * FROM instruments WHERE instrument_token = 13660418;

-- If not found, insert it (or wait for instrument sync)
-- Ticker service should sync instruments periodically
```

---

### Issue: No Historical Data After Backfill

**Symptoms**:
- Backfill completes but no data in database

**Checks**:
1. Verify ticker service has historical data API
2. Check if instrument token is valid
3. Verify database write permissions

**Debug**:
```bash
# Test ticker service historical API
curl "http://localhost:8080/historical?instrument_token=256265&interval=minute&from_ts=$(date -u -d '2 hours ago' '+%Y-%m-%dT%H:%M:%S')&to_ts=$(date -u '+%Y-%m-%dT%H:%M:%S')"

# Check database
psql -U stocksblitz -d stocksblitz_unified -c "
  SELECT tablename FROM pg_tables
  WHERE schemaname = 'public' AND tablename LIKE '%minute%';
"
```

---

### Issue: High Latency (>5 seconds)

**Symptoms**:
- Subscription takes >5 seconds
- Backfill start delayed

**Possible Causes**:
1. Ticker service slow to subscribe
2. Database query slow
3. Network issues

**Debug**:
```bash
# Check ticker service response time
time curl -X POST http://localhost:8080/subscriptions -d '{"instrument_token":256265}'

# Check database query performance
psql -U stocksblitz -d stocksblitz_unified -c "
  EXPLAIN ANALYZE
  SELECT * FROM instruments WHERE instrument_token = 256265;
"

# Check Redis latency
redis-cli --latency-history
```

---

## Performance Benchmarks

### Expected Timing Breakdown

**Subscription Flow** (Target: <30 seconds total):

```
1. API Call to Ticker Service               100-500ms
2. Ticker Service Subscribe to WebSocket    100-300ms
3. Ticker Service Persist Subscription      50-100ms
4. Ticker Service Publish Event             5-10ms
   ────────────────────────────────────────────────────
   Subtotal: Subscription Active            255-910ms ✅

5. Backend Receive Event                    10-50ms
6. Backend Query Instrument Details         20-100ms
7. Backend Fetch Historical Data            2-10s
8. Backend Store in Database                1-5s
   ────────────────────────────────────────────────────
   Subtotal: Historical Data Ready          3-15s ✅

Total: Subscription + Historical Data       3-16s ✅
```

### Monitoring Queries

**Event Processing Rate**:
```sql
-- Count events processed in last hour
SELECT COUNT(*) FROM logs
WHERE message LIKE '%Received subscription event%'
  AND timestamp > NOW() - INTERVAL '1 hour';
```

**Backfill Success Rate**:
```sql
-- Count successful vs failed backfills
SELECT
  SUM(CASE WHEN message LIKE '%completed%' THEN 1 ELSE 0 END) as successful,
  SUM(CASE WHEN message LIKE '%failed%' THEN 1 ELSE 0 END) as failed
FROM logs
WHERE message LIKE '%Immediate backfill%'
  AND timestamp > NOW() - INTERVAL '1 hour';
```

**Average Backfill Duration**:
```bash
# Parse logs for timing
grep "Starting immediate backfill" backend.log | tail -100 > start.txt
grep "Immediate backfill completed" backend.log | tail -100 > end.txt
# Calculate duration between start and end timestamps
```

---

## Checklist for Integration Testing

### Pre-Testing Checklist

- [ ] Backend .env configured correctly
- [ ] Redis running and accessible
- [ ] TimescaleDB running with stocksblitz_unified database
- [ ] Ticker service running (for integration tests)
- [ ] Instruments table populated
- [ ] Test instrument tokens identified

### Local Testing Checklist

- [ ] Test 1: Backend startup ✅
- [ ] Test 2: Simulated subscription_created ✅
- [ ] Test 3: Simulated subscription_removed ✅
- [ ] Test 4: Multiple simultaneous events ✅
- [ ] Test 5: Invalid event handling ✅

### Integration Testing Checklist

- [ ] Test 6: End-to-end subscription flow ✅
- [ ] Test 7: Subscription removal flow ✅
- [ ] Test 8: High load (20+ subscriptions) ✅

### Scenario Testing Checklist

- [ ] Scenario 1: User opens monitor page ✅
- [ ] Scenario 2: User changes expiry ✅
- [ ] Scenario 3: Backend restart ✅
- [ ] Scenario 4: Redis outage ✅
- [ ] Scenario 5: Ticker service outage ✅

### Performance Verification

- [ ] Subscription activation <2 seconds ✅
- [ ] Event processing latency <500ms ✅
- [ ] Historical data available <60 seconds ✅
- [ ] No memory leaks after 1000 events ✅
- [ ] No errors after 1 hour of operation ✅

---

## Next Steps After Testing

### If All Tests Pass ✅

1. **Document results** in test report
2. **Deploy to staging** environment
3. **Monitor staging** for 24 hours
4. **Schedule production deployment** (Nov 13)

### If Tests Fail ❌

1. **Document failures** with logs and screenshots
2. **Identify root cause** using troubleshooting guide
3. **Fix issues** in development
4. **Retest** using this guide
5. **Update documentation** with learnings

---

## Support and Questions

**For Issues During Testing**:
1. Check [Troubleshooting](#troubleshooting) section first
2. Review logs for error patterns
3. Check Redis and database connectivity
4. Consult with ticker service team if events not publishing

**For Integration Questions**:
- Event schema: See `INTEGRATION_COMPATIBILITY_VERIFICATION.md`
- Backend architecture: See `SUBSCRIPTION_AND_BACKFILL_ANALYSIS.md`
- Ticker service: See `ticker_service/INCREMENTAL_SUBSCRIPTIONS_IMPLEMENTATION.md`

---

**Document Version**: 1.0
**Last Updated**: November 1, 2025
**Status**: Ready for Integration Testing
**Next Review**: After first integration test cycle (Nov 3-4)
