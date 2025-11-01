# Ticker Service Response - Backend Action Plan

**Date**: November 1, 2025
**Status**: Ready to Execute
**Coordination Required**: Yes (Integration Testing)

---

## Executive Summary

### Great News! ✅

The ticker service team has provided **excellent responses** with clear timelines and commitment:

1. **✅ Incremental updates ARE possible** - No technical limitations
2. **✅ Redis pub/sub already works** - No webhook needed
3. **✅ Timeline is short** - 4-6 hours for P1 features
4. **✅ Testing collaboration confirmed** - They need our help
5. **✅ Load limits are generous** - 1500-2000 subscriptions per account

### Key Takeaways

| Item | Ticker Service Status | Backend Action Required |
|------|----------------------|------------------------|
| Incremental Updates | Will implement (2-3 hours) | Wait for deployment, then integrate |
| Redis Pub/Sub Events | Will add lifecycle events (1-2 hours) | Implement event listener NOW |
| Status Endpoint | Will enhance (1 hour) | Use for subscription validation |
| Integration Testing | Need our help (essential) | Dedicate 1 engineer for Week 1 |
| Load Limits | 1500-2000 per account safe | Design for 4500 total (3 accounts) |

---

## Timeline from Ticker Service

### Their Proposed Schedule

**Week 1** (Nov 2-8):
```
Day 1 (Nov 2): Implementation + unit tests
Day 2 (Nov 3): Integration testing with Backend Team
Day 3 (Nov 4): Deployment to staging
Day 4 (Nov 5): Production deployment
```

**Week 2** (Nov 9-15):
```
Mon: Staging deployment
Tue-Thu: Staging monitoring
Fri: Production deployment
```

### Critical: Integration Testing Week

**They need us for**:
- Tue (Nov 3): Joint integration testing (full day)
- Wed (Nov 4): High load + failure scenario testing (half day)

**Required from Backend Team**:
- 1 engineer dedicated for Nov 3-4
- Staging environment access
- Test instrument list
- FOStreamConsumer code review

---

## What Backend Should Do NOW

### Priority 1: Prepare for Integration Testing (Immediate)

#### Task 1.1: Provide Staging Environment Access

**Deliverable**: Staging environment details for ticker service team

```yaml
# staging_environment.yaml

redis:
  host: staging-redis.internal
  port: 6379
  channels:
    - ticker:nifty:options
    - ticker:nifty:underlying
    - ticker:nifty:events  # NEW: For subscription events

timescaledb:
  host: staging-timescale.internal
  port: 5432
  database: tradingview_staging
  tables:
    - fo_option_strike_bars
    - fo_expiry_metrics
    - futures_bars
    - nifty50_ohlc

backend_api:
  url: http://staging-backend:8081
  endpoints:
    - GET /fo/strike-distribution
    - GET /fo/moneyness-series
    - GET /marks/latest

test_credentials:
  api_key: "staging_test_key_..."
  basic_auth: "test:password"
```

**Action**: Create this file and share with ticker service team **today (Nov 1)**

---

#### Task 1.2: Define Test Instrument List

**Deliverable**: Specific instrument tokens to test with

```python
# test_instruments.py

TEST_INSTRUMENTS = {
    "underlying": {
        "nifty50": {
            "name": "NIFTY 50",
            "instrument_token": 256265,  # Example
            "expected_frequency": "5 seconds",
        }
    },

    "options": {
        "nifty_weekly": [
            {
                "tradingsymbol": "NIFTY25NOV24500CE",
                "instrument_token": 13660418,  # Example
                "strike": 24500,
                "option_type": "CE",
                "expiry": "2025-11-28",
                "priority": "high",  # ATM
            },
            {
                "tradingsymbol": "NIFTY25NOV24500PE",
                "instrument_token": 13660419,  # Example
                "strike": 24500,
                "option_type": "PE",
                "expiry": "2025-11-28",
                "priority": "high",  # ATM
            },
            # Add 10 more strikes for testing (24000-25000 range)
        ]
    },

    "futures": {
        "nifty_fut": {
            "tradingsymbol": "NIFTY25NOVFUT",
            "instrument_token": 256266,  # Example
            "expiry": "2025-11-28",
        }
    },
}

# Expected data characteristics
EXPECTED_BEHAVIOR = {
    "tick_frequency": {
        "atm_options": "1-10 ticks/minute",
        "otm_options": "0-3 ticks/minute",
        "underlying": "every 5 seconds",
    },
    "data_latency": {
        "target": "< 100ms (P99)",
        "acceptable": "< 500ms",
    },
    "data_fields": {
        "options": ["ltp", "volume", "oi", "iv", "delta", "gamma", "theta", "vega"],
        "underlying": ["open", "high", "low", "close", "volume"],
    }
}
```

**Action**: Create this file and share **today (Nov 1)**

---

#### Task 1.3: Review FOStreamConsumer

**Deliverable**: Share FOStreamConsumer code with ticker service team

**Current Location**: `backend/app/fo_stream.py`

**What to share**:
1. Code walkthrough document
2. Data transformation logic
3. Error handling approach
4. Performance characteristics

**Action**: Create documentation **today (Nov 1)**

---

### Priority 2: Implement Subscription Event Listener (NOW)

#### Why NOW?

Ticker service will add Redis pub/sub for subscription events in **1-2 hours**. We should be ready to receive those events.

#### Implementation

**File**: `backend/app/services/subscription_event_listener.py` (NEW)

```python
"""
Listen to subscription lifecycle events from ticker service.

Triggers immediate backfill when subscriptions are created.
"""

import asyncio
import json
import logging
from typing import Optional
from datetime import datetime

import redis.asyncio as redis

from app.config import settings
from app.backfill import BackfillManager

logger = logging.getLogger(__name__)


class SubscriptionEventListener:
    """
    Listens to ticker service subscription events via Redis pub/sub.

    Events:
    - subscription_created: Triggers immediate backfill
    - subscription_deleted: Can clean up resources
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        backfill_manager: Optional[BackfillManager] = None,
    ):
        self._redis = redis_client
        self._backfill_manager = backfill_manager
        self._pubsub = None
        self._running = False
        self._task = None

    async def start(self):
        """Start listening to subscription events"""
        if self._running:
            logger.warning("Subscription event listener already running")
            return

        self._running = True

        # Subscribe to ticker service events channel
        self._pubsub = self._redis.pubsub()
        await self._pubsub.subscribe(f"{settings.redis_channel_prefix}:events")

        logger.info("Subscribed to ticker service events: %s:events", settings.redis_channel_prefix)

        # Start background task
        self._task = asyncio.create_task(self._listen_loop())

    async def stop(self):
        """Stop listening"""
        self._running = False

        if self._pubsub:
            await self._pubsub.unsubscribe()
            await self._pubsub.close()

        if self._task:
            await self._task

        logger.info("Subscription event listener stopped")

    async def _listen_loop(self):
        """Main listening loop"""
        logger.info("Subscription event listener started")

        try:
            while self._running:
                message = await self._pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=1.0,
                )

                if message and message["type"] == "message":
                    await self._handle_event(message["data"])

        except asyncio.CancelledError:
            logger.info("Subscription event listener cancelled")
        except Exception as e:
            logger.error("Subscription event listener error: %s", e, exc_info=True)
        finally:
            self._running = False

    async def _handle_event(self, data: bytes):
        """Handle subscription event"""
        try:
            event = json.loads(data)

            event_type = event.get("event_type")
            instrument_token = event.get("instrument_token")
            metadata = event.get("metadata", {})

            logger.info(
                "Received subscription event: %s for token %s",
                event_type,
                instrument_token,
            )

            if event_type == "subscription_created":
                await self._handle_subscription_created(instrument_token, metadata)

            elif event_type == "subscription_deleted":
                await self._handle_subscription_deleted(instrument_token, metadata)

            else:
                logger.warning("Unknown event type: %s", event_type)

        except json.JSONDecodeError as e:
            logger.error("Failed to parse subscription event: %s", e)
        except Exception as e:
            logger.error("Error handling subscription event: %s", e, exc_info=True)

    async def _handle_subscription_created(
        self,
        instrument_token: int,
        metadata: dict,
    ):
        """Handle subscription created event"""
        tradingsymbol = metadata.get("tradingsymbol", "unknown")

        logger.info(
            "Subscription created: %s (token: %s), triggering immediate backfill",
            tradingsymbol,
            instrument_token,
        )

        # Trigger immediate backfill if available
        if self._backfill_manager:
            try:
                # Run in background (don't block event loop)
                asyncio.create_task(
                    self._backfill_manager.backfill_instrument_immediate(
                        instrument_token
                    )
                )

                logger.info("Immediate backfill scheduled for token %s", instrument_token)

            except Exception as e:
                logger.error(
                    "Failed to trigger immediate backfill for %s: %s",
                    instrument_token,
                    e,
                )
        else:
            logger.warning("Backfill manager not available, skipping immediate backfill")

    async def _handle_subscription_deleted(
        self,
        instrument_token: int,
        metadata: dict,
    ):
        """Handle subscription deleted event"""
        tradingsymbol = metadata.get("tradingsymbol", "unknown")

        logger.info(
            "Subscription deleted: %s (token: %s)",
            tradingsymbol,
            instrument_token,
        )

        # Could implement cleanup logic here
        # For example:
        # - Stop processing this instrument in real-time consumer
        # - Mark data as stale in cache
        # - Alert monitoring system
```

**File**: `backend/app/main.py` (MODIFY)

```python
# Add to imports
from app.services.subscription_event_listener import SubscriptionEventListener

# Initialize listener
subscription_event_listener = None

# In startup
@app.on_event("startup")
async def startup():
    # ... existing startup code ...

    # Start subscription event listener
    global subscription_event_listener
    if settings.subscription_events_enabled:
        subscription_event_listener = SubscriptionEventListener(
            redis_client=redis_client,
            backfill_manager=backfill_manager,
        )
        await subscription_event_listener.start()
        logger.info("Subscription event listener started")
    else:
        logger.info("Subscription event listener disabled")

# In shutdown
@app.on_event("shutdown")
async def shutdown():
    # ... existing shutdown code ...

    # Stop subscription event listener
    if subscription_event_listener:
        await subscription_event_listener.stop()
```

**File**: `backend/app/config.py` (MODIFY)

```python
# Add setting
subscription_events_enabled: bool = Field(
    default=True,
    description="Enable subscription event listener from ticker service"
)

redis_channel_prefix: str = Field(
    default="ticker:nifty",
    description="Redis pub/sub channel prefix"
)
```

**Action**: Implement this **today (Nov 1)** so it's ready when ticker service deploys

---

### Priority 3: Implement Smart Auto-Subscribe (OPTIONAL - Can Wait)

#### Status

This can wait until **after** ticker service implements incremental updates.

**Why wait?**
- Current full reload causes 2-5 second disruption
- Auto-subscribing would trigger that disruption
- Better to wait for incremental updates (no disruption)

**When to implement?**
- After Nov 5 (when ticker service deploys incremental updates)

---

### Priority 4: Update Backfill for Subscription Awareness (Can Do Now)

#### Implementation

**File**: `backend/app/backfill.py` (MODIFY - already documented in previous plan)

```python
# Add method to BackfillManager

async def _get_active_subscriptions(self) -> Set[int]:
    """
    Query ticker service for actively subscribed tokens.

    Returns:
        Set of instrument tokens that are subscribed
    """
    try:
        # Call ticker service API
        response = await self._ticker_client.list_subscriptions(status="active")

        tokens = {sub["instrument_token"] for sub in response}

        logger.info("Found %d active subscriptions from ticker service", len(tokens))
        return tokens

    except Exception as e:
        logger.error("Failed to fetch active subscriptions: %s", e)
        return set()  # Fallback to empty (will use metadata-based approach)


async def _tick(self):
    """
    Main backfill tick - UPDATED to be subscription-aware
    """
    try:
        # NEW: Get active subscriptions
        active_tokens = await self._get_active_subscriptions()

        # If no active subscriptions found, fall back to metadata
        if not active_tokens:
            logger.warning("No active subscriptions found, using metadata-based backfill")
            # ... existing metadata-based logic ...
            return

        # Backfill only subscribed instruments
        logger.info("Backfilling %d subscribed instruments", len(active_tokens))

        # Group tokens by type (underlying, futures, options)
        for token in active_tokens:
            try:
                # Fetch metadata for token
                metadata = await self._get_token_metadata(token)

                if not metadata:
                    logger.warning("No metadata for token %s, skipping", token)
                    continue

                # Backfill based on type
                if metadata["segment"] == "NFO-OPT":
                    await self._backfill_option_token(token, metadata)
                elif metadata["segment"] == "NFO-FUT":
                    await self._backfill_futures_token(token, metadata)
                # ... etc

            except Exception as e:
                logger.error("Failed to backfill token %s: %s", token, e)
                continue

    except Exception as e:
        logger.error("Backfill tick failed: %s", e, exc_info=True)
```

**Action**: Implement this **today or tomorrow (Nov 1-2)**

---

## Integration Testing Preparation

### What Backend Team Needs to Deliver

#### 1. Staging Environment (Due: Today)

**Create file**: `backend/STAGING_ENVIRONMENT.md`

Contents:
- Redis connection details
- TimescaleDB connection details
- Backend API URLs
- Test credentials
- Expected data formats

#### 2. Test Instrument List (Due: Today)

**Create file**: `backend/TEST_INSTRUMENTS.json`

Contents:
- 20-30 option tokens for testing
- Underlying token
- Futures token
- Expected tick frequency
- Expected data fields

#### 3. FOStreamConsumer Documentation (Due: Today)

**Create file**: `backend/FOSTREAM_DOCUMENTATION.md`

Contents:
- Architecture overview
- Data transformation logic
- Error handling approach
- Performance characteristics
- Known limitations

#### 4. Database Verification Queries (Due: Today)

**Create file**: `backend/TEST_QUERIES.sql`

Sample queries to verify data correctness:

```sql
-- Verify options data arrived
SELECT
    tradingsymbol,
    MAX(bucket_time) as last_bar,
    COUNT(*) as bar_count
FROM fo_option_strike_bars
WHERE bucket_time > NOW() - INTERVAL '1 hour'
GROUP BY tradingsymbol
ORDER BY last_bar DESC;

-- Verify underlying data
SELECT
    MAX(time) as last_bar,
    COUNT(*) as bar_count
FROM nifty50_ohlc
WHERE time > NOW() - INTERVAL '1 hour';

-- Check for data gaps
SELECT
    bucket_time,
    COUNT(DISTINCT tradingsymbol) as symbol_count
FROM fo_option_strike_bars
WHERE bucket_time > NOW() - INTERVAL '1 hour'
GROUP BY bucket_time
ORDER BY bucket_time;
```

---

### Integration Testing Schedule

**Confirmed Dates**:
- **Tue Nov 3**: Full day joint testing (8 hours)
- **Wed Nov 4**: Half day failure scenarios (4 hours)

**Backend Team Requirement**: 1 engineer dedicated for these dates

**Test Scenarios** (from ticker service team):

1. **Basic Subscription Flow** (1 hour)
   - Subscribe to option
   - Verify data flows end-to-end
   - Verify frontend query works

2. **Subscription Event Integration** (2 hours)
   - Verify event received
   - Verify immediate backfill triggered
   - Verify historical data available within 30 seconds

3. **High Load Testing** (3 hours)
   - Subscribe to 500 options simultaneously
   - Monitor throughput and latency
   - Verify no data loss

4. **Failure Scenarios** (2 hours)
   - Simulate WebSocket disconnection
   - Simulate Redis outage
   - Verify graceful degradation

---

## Configuration Changes Needed

### Backend Configuration

**File**: `backend/.env.staging`

```bash
# Subscription event listener
SUBSCRIPTION_EVENTS_ENABLED=true
REDIS_CHANNEL_PREFIX=ticker:nifty

# Backfill improvements
BACKFILL_SUBSCRIPTION_AWARE=true
BACKFILL_IMMEDIATE_ON_SUBSCRIBE=true

# Smart subscription (disabled until incremental updates deployed)
SMART_SUBSCRIPTION_ENABLED=false  # Enable after Nov 5

# Ticker service
TICKER_SERVICE_URL=http://ticker-service:8080
TICKER_SERVICE_TIMEOUT=30
```

---

## Timeline Summary

### Week 1: Implementation & Testing

| Date | Ticker Service | Backend Team | Status |
|------|---------------|--------------|--------|
| **Nov 1 (Today)** | - | Prepare for integration (deliverables above) | 🔴 IN PROGRESS |
| **Nov 2 (Mon)** | Implement P1 features | Implement event listener + subscription-aware backfill | 🟡 SCHEDULED |
| **Nov 3 (Tue)** | Integration testing | Integration testing (1 engineer full day) | 🟡 SCHEDULED |
| **Nov 4 (Wed)** | Deploy to staging | Integration testing (half day) + Monitor staging | 🟡 SCHEDULED |
| **Nov 5 (Thu)** | Prod deployment prep | Monitor staging | 🟡 SCHEDULED |

### Week 2: Staging & Production

| Date | Ticker Service | Backend Team | Status |
|------|---------------|--------------|--------|
| **Nov 9 (Mon)** | Staging deployment | Monitor staging | 🟡 SCHEDULED |
| **Nov 10-12** | Staging monitoring | Verify end-to-end flow | 🟡 SCHEDULED |
| **Nov 13 (Fri)** | Production deployment | Verify production + Enable smart auto-subscribe | 🟡 SCHEDULED |

---

## Key Decisions Needed from Backend Team

### Decision 1: Engineer Assignment

**Question**: Who will be the dedicated engineer for integration testing (Nov 3-4)?

**Requirements**:
- Familiar with FOStreamConsumer
- Familiar with TimescaleDB
- Can debug Redis pub/sub issues
- Available full day Nov 3, half day Nov 4

---

### Decision 2: Test Instrument Selection

**Question**: Which specific option strikes should we test with?

**Recommendation**:
- NIFTY ATM ± 10 strikes (21 strikes × 2 = 42 options)
- Weekly expiry (nearest)
- Monthly expiry (nearest)

**Action**: Provide specific instrument tokens

---

### Decision 3: Performance SLA

**Question**: What are acceptable performance targets?

**Ticker service assumes**:
- Latency: P99 < 100ms (tick to database)
- Throughput: 10,000 ticks/second
- Data loss: 0%

**Confirm or adjust**: What are your actual requirements?

---

### Decision 4: Subscription Target

**Question**: How many subscriptions do we plan to maintain?

**Ticker service recommends**: 1500 per account (4500 total with 3 accounts)

**This covers**:
- NIFTY: 3 expiries × 21 strikes × 2 = 126 options
- BANKNIFTY: 3 expiries × 21 strikes × 2 = 126 options
- FINNIFTY: 3 expiries × 21 strikes × 2 = 126 options
- Total: ~380 options + underlying + futures = **~400 instruments**

**Confirm**: Is this sufficient for your use case?

---

## Immediate Action Items (Today - Nov 1)

### Must Do Today ⚡

1. **[ ] Create staging environment document**
   - File: `backend/STAGING_ENVIRONMENT.md`
   - Owner: DevOps/Backend Lead
   - Time: 30 minutes

2. **[ ] Define test instrument list**
   - File: `backend/TEST_INSTRUMENTS.json`
   - Owner: Backend Engineer
   - Time: 1 hour

3. **[ ] Document FOStreamConsumer**
   - File: `backend/FOSTREAM_DOCUMENTATION.md`
   - Owner: Backend Engineer
   - Time: 2 hours

4. **[ ] Create test queries**
   - File: `backend/TEST_QUERIES.sql`
   - Owner: Backend Engineer
   - Time: 30 minutes

5. **[ ] Assign integration testing engineer**
   - Decision: Who will work with ticker service team Nov 3-4?
   - Owner: Backend Lead
   - Time: 5 minutes

6. **[ ] Share deliverables with ticker service team**
   - Method: Email or Slack
   - Owner: Backend Lead
   - Time: 10 minutes

### Should Do Today (Nice to Have) ⭐

7. **[ ] Implement subscription event listener**
   - File: `backend/app/services/subscription_event_listener.py`
   - Owner: Backend Engineer
   - Time: 2-3 hours

8. **[ ] Update backfill for subscription awareness**
   - File: `backend/app/backfill.py`
   - Owner: Backend Engineer
   - Time: 2 hours

---

## Communication Plan

### Today (Nov 1)

**Backend Lead should send to ticker service team**:

```
Subject: Backend Team Ready for Integration - Deliverables Attached

Hi Ticker Service Team,

Thank you for the comprehensive responses! We're ready to collaborate.

Attached/Linked:
1. Staging environment details
2. Test instrument list
3. FOStreamConsumer documentation
4. Database verification queries

Integration Testing:
- Engineer assigned: [NAME]
- Available: Nov 3 (full day), Nov 4 (half day)
- Confirmed: We'll be ready

Questions:
1. Confirmed: Redis pub/sub for events (no webhook needed) ✅
2. Confirmed: Load target of 1500/account is sufficient ✅
3. Request: Can you share event schema draft before implementation?

Next Steps:
- We'll implement event listener by Nov 2
- Ready for integration testing Nov 3
- Let's schedule a 30-min kickoff call Nov 2 morning

Thanks,
[Backend Team Lead]
```

---

## Summary: What Backend Team Should Do

### Today (Nov 1) - Priority 1

✅ **Deliver to Ticker Service Team**:
1. Staging environment access
2. Test instrument list
3. FOStreamConsumer documentation
4. Test verification queries
5. Assign engineer for Nov 3-4

### Tomorrow (Nov 2) - Priority 2

✅ **Implement Features**:
1. Subscription event listener (2-3 hours)
2. Subscription-aware backfill (2 hours)
3. Deploy to staging

### Nov 3-4 - Priority 3

✅ **Integration Testing**:
1. Collaborate with ticker service team
2. Test all scenarios
3. Fix issues in real-time

### Nov 5+ - Priority 4

✅ **Monitor & Deploy**:
1. Monitor staging
2. Deploy to production
3. Enable smart auto-subscribe feature

---

**Status**: Ready to execute
**Next Step**: Create deliverables for ticker service team TODAY
**Owner**: Backend Team Lead
**Timeline**: Start immediately

