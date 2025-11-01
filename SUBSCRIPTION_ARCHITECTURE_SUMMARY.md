# Subscription & Backfill Architecture - Summary

**Date**: November 1, 2025
**Purpose**: Clear answers to architecture questions

---

## Your Questions Answered

### Q1: Is subscription smart/on-demand? What if user doesn't need all information?

**Answer: ❌ NO - Current system is pre-subscription, NOT smart**

**Current Reality**:
- Must manually call `POST /subscriptions` API to subscribe
- When user requests data for unsubscribed instrument → returns empty
- **No automatic subscription**
- Adding 1 subscription → **Restarts ALL streams** (2-5 second gap)

**Granularity Issue**:
- Can't subscribe to just Greeks or just OHLC
- Options: `FULL` (everything), `QUOTE` (no Greeks), `LTP` (price only)
- Even with `LTP`, backend stores all fields (just some are null)

**Instrument Types**:
| Type | Subscription Required? | Notes |
|------|------------------------|-------|
| Underlying (NIFTY50) | ✅ No | Polled every 5s automatically |
| Futures | ❌ Yes | Must subscribe each contract |
| Options | ❌ Yes | Must subscribe EACH strike/expiry |

---

### Q2: Does backfill proactively fetch data when subscribed?

**Answer: ❌ NO - Backfill runs on fixed 5-minute schedule**

**Current Reality**:
- Runs every 5 minutes (configurable)
- **NOT triggered by subscriptions**
- Detects gaps by querying database
- Only backfills if gap > 3 minutes

**Timeline Example**:
```
09:00 - User subscribes to option
09:00 - Real-time data starts flowing
09:05 - Backfill runs (scheduled)
09:05 - Historical data available

Gap: 5-10 minutes before historical data
```

**Problems**:
1. Not subscription-aware (backfills wrong instruments)
2. Token blacklisting (expired options → permanent failure)
3. Batch limits (2 hours max per cycle)

---

## Documents Created

### 1. For Ticker Service Team

**File**: `TICKER_SERVICE_CHANGE_REQUESTS.md`

**Contents**:
- ✅ **P1: Incremental subscription updates** - Avoid full reload
- ✅ **P1: Backfill webhook/event** - Notify backend on subscription
- ✅ **P2: Subscription status endpoint** - Health monitoring
- ✅ **P2: Graceful error handling** - Fix expired option issues
- ✅ **P3: Bulk subscription API** - Subscribe to multiple at once

**Key Request**: Incremental updates to avoid 2-5 second disruption

### 2. For Backend Team (You)

**File**: `BACKEND_SUBSCRIPTION_IMPROVEMENTS.md`

**Contents**:
- ✅ **Smart on-demand subscription** - Auto-subscribe when data requested
- ✅ **Subscription-aware backfill** - Only backfill subscribed instruments
- ✅ **Webhook receiver** - Ready for ticker service events
- ✅ **Improved error handling** - No permanent blacklisting

**Status**: Ready to implement (no ticker service changes needed)

### 3. Architecture Analysis

**File**: `SUBSCRIPTION_AND_BACKFILL_ANALYSIS.md`

**Contents**:
- Complete architecture diagrams
- Detailed code examples
- Problem identification
- Recommendations

---

## Immediate Actions

### For You (Backend Team)

**Can implement NOW** (no dependencies):

1. **Smart auto-subscription** in `app/routes/fo.py`:
   ```python
   @router.get("/strike-distribution")
   async def strike_distribution(..., auto_subscribe: bool = True):
       rows = await dm.fetch_data(...)

       if not rows and auto_subscribe:
           # Auto-subscribe and retry
           await subscribe_missing_instruments(...)
           rows = await dm.fetch_data(...)

       return rows
   ```

2. **Subscription-aware backfill** in `app/backfill.py`:
   ```python
   async def _tick(self):
       # Get actively subscribed tokens from ticker service
       active_tokens = await get_active_subscriptions()

       # Only backfill subscribed instruments
       for token in active_tokens:
           await backfill_instrument(token)
   ```

3. **Webhook receiver** for future ticker service integration:
   ```python
   @router.post("/internal/subscription-events")
   async def handle_subscription_event(event):
       if event.type == "created":
           # Trigger immediate backfill
           await backfill_immediately(event.token)
   ```

**Estimated Effort**: 2-3 days development

**Risk**: Low (feature-flagged, backward compatible)

---

### For Ticker Service Team

**Priority 1** (High Impact):

1. **Incremental subscription updates**:
   - Add `add_subscription_incremental()` method
   - Avoid stopping ALL streams when adding one subscription
   - Estimated: 3-5 days

2. **Backfill webhook**:
   - POST to backend when subscription created
   - Enable immediate backfill (not waiting 5 minutes)
   - Estimated: 1 day

**Timeline Question**: When can ticker service team schedule this work?

---

## Architecture Diagrams

### Current Flow (Problems)

```
User Request
    ↓
Backend checks database
    ↓
No data found → Return empty ❌
    ↓
User must manually:
    1. Call POST /subscriptions
    2. Wait 2-5 seconds (full reload)
    3. Wait 5-10 minutes (backfill)
    4. Retry request
```

### Proposed Flow (Solution)

```
User Request
    ↓
Backend checks database
    ↓
No data found → Auto-subscribe ✅
    ↓
    ├─► Incremental add (no disruption)
    ├─► Trigger immediate backfill
    └─► Wait 10-30 seconds
    ↓
Return data to user
```

---

## Key Metrics

### Before Improvements

| Metric | Current |
|--------|---------|
| Time to first data | Manual subscription required |
| Historical data lag | 5-10 minutes |
| Disruption on subscribe | 2-5 seconds (all streams) |
| Backfill efficiency | 100+ instruments (many unsubscribed) |

### After Improvements

| Metric | Target |
|--------|--------|
| Time to first data | <30 seconds (auto) |
| Historical data lag | 10-30 seconds |
| Disruption on subscribe | 0 seconds (incremental) |
| Backfill efficiency | 20-50 instruments (only subscribed) |

---

## Next Steps

### This Week

1. **You**: Review backend implementation plan
2. **You**: Decide on feature flag rollout strategy
3. **You**: Contact ticker service team with change requests

### Next Week (Backend)

1. Implement smart auto-subscription
2. Implement subscription-aware backfill
3. Deploy with feature flags (disabled)
4. Test in staging

### Next Sprint (Ticker Service)

1. Schedule discussion with ticker service team
2. Review incremental subscription approach
3. Plan implementation timeline
4. Coordinate testing

---

## Questions for Ticker Service Team

When you contact them, ask:

1. **Incremental Updates**: Any technical blocker preventing incremental WebSocket changes?
2. **Timeline**: When can you schedule P1 work (incremental + webhook)?
3. **Testing**: Need our help with integration testing?
4. **Preference**: HTTP webhook or Redis pub/sub for events?
5. **Load Limits**: Practical limit for subscriptions per account?

---

## Files to Share

**With Ticker Service Team**:
- `TICKER_SERVICE_CHANGE_REQUESTS.md` - Detailed requirements

**With Backend Team**:
- `BACKEND_SUBSCRIPTION_IMPROVEMENTS.md` - Implementation plan

**For Reference**:
- `SUBSCRIPTION_AND_BACKFILL_ANALYSIS.md` - Full analysis

---

**Bottom Line**:
- ❌ Current system requires manual work, has delays, causes disruptions
- ✅ Backend can improve immediately (auto-subscribe, smart backfill)
- ✅ Ticker service improvements would eliminate disruptions and delays
- 🎯 Combined: Seamless user experience in <30 seconds

