# Ticker Service Change Requests

**Date**: November 1, 2025
**Requested By**: Backend Team
**Priority**: High

---

## Executive Summary

The backend team has identified several issues with the current subscription and data flow architecture. These changes to ticker_service would significantly improve system performance, reduce disruptions, and enable better user experience.

---

## Priority 1: Incremental Subscription Updates (HIGH)

### Current Problem

**Issue**: Adding/removing a single subscription triggers a full reload of ALL WebSocket streams.

**Current Code** (`ticker_service/app/generator.py`):
```python
async def reload_subscriptions(self):
    """Reload subscriptions from database"""
    if self._running:
        await self.stop()  # ← Stops ALL streams
    await self.start()     # ← Restarts from scratch
```

**Impact**:
- 2-5 second disruption to ALL active subscriptions
- All clients experience data gaps
- Scales poorly (1000 subscriptions = 1000 instrument disruptions)

### Requested Change

**Add incremental subscription methods**:

```python
# NEW METHODS in MultiAccountTickerLoop

async def add_subscription_incremental(
    self,
    instrument_token: int,
    tradingsymbol: str,
    requested_mode: str = "FULL"
) -> bool:
    """
    Add single subscription without disrupting existing streams.

    Returns:
        True if added successfully, False if failed
    """
    # 1. Find account with capacity (< 1000 instruments)
    target_account = self._find_account_with_capacity()
    if not target_account:
        logger.error("No account has capacity for new subscription")
        return False

    # 2. Add to WebSocket WITHOUT stopping stream
    try:
        async with self._orchestrator.borrow(target_account) as client:
            await client.subscribe_tokens(
                [instrument_token],
                mode=self._parse_mode(requested_mode)
            )

        # 3. Update in-memory assignments
        instrument = Instrument(
            instrument_token=instrument_token,
            tradingsymbol=tradingsymbol,
            requested_mode=requested_mode
        )
        self._assignments[target_account].append(instrument)

        logger.info(f"Added subscription {tradingsymbol} to {target_account} incrementally")
        return True

    except Exception as e:
        logger.error(f"Failed to add subscription {tradingsymbol}: {e}")
        return False


async def remove_subscription_incremental(
    self,
    instrument_token: int
) -> bool:
    """
    Remove single subscription without disrupting others.

    Returns:
        True if removed successfully, False if not found
    """
    # 1. Find which account has this subscription
    target_account = None
    instrument = None

    for account_id, instruments in self._assignments.items():
        for inst in instruments:
            if inst.instrument_token == instrument_token:
                target_account = account_id
                instrument = inst
                break
        if target_account:
            break

    if not target_account:
        logger.warning(f"Subscription {instrument_token} not found in any account")
        return False

    # 2. Remove from WebSocket WITHOUT stopping stream
    try:
        async with self._orchestrator.borrow(target_account) as client:
            await client.unsubscribe_tokens([instrument_token])

        # 3. Update in-memory assignments
        self._assignments[target_account].remove(instrument)

        logger.info(f"Removed subscription {instrument_token} from {target_account} incrementally")
        return True

    except Exception as e:
        logger.error(f"Failed to remove subscription {instrument_token}: {e}")
        return False


def _find_account_with_capacity(self) -> Optional[str]:
    """Find account with < 1000 instruments"""
    for account_id, instruments in self._assignments.items():
        if len(instruments) < 1000:  # Kite limit
            return account_id
    return None
```

**Update API endpoints** (`ticker_service/app/main.py`):

```python
@app.post("/subscriptions", response_model=SubscriptionResponse, status_code=201)
async def create_subscription(
    request: Request,
    payload: SubscriptionRequest,
    incremental: bool = Query(True, description="Use incremental update (recommended)")
):
    # ... validation logic ...

    # Persist to database
    await subscription_store.upsert(...)

    if incremental and ticker_loop._running:
        # NEW: Incremental update (no disruption)
        success = await ticker_loop.add_subscription_incremental(
            instrument_token=payload.instrument_token,
            tradingsymbol=tradingsymbol,
            requested_mode=requested_mode
        )

        if success:
            logger.info(f"Subscription added incrementally: {tradingsymbol}")
        else:
            logger.warning(f"Incremental add failed, falling back to full reload")
            await ticker_loop.reload_subscriptions()
    else:
        # OLD: Full reload (use as fallback)
        await ticker_loop.reload_subscriptions()

    return response


@app.delete("/subscriptions/{instrument_token}", status_code=204)
async def delete_subscription(
    instrument_token: int,
    incremental: bool = Query(True, description="Use incremental update (recommended)")
):
    # Mark inactive in database
    await subscription_store.mark_inactive(instrument_token)

    if incremental and ticker_loop._running:
        # NEW: Incremental removal
        await ticker_loop.remove_subscription_incremental(instrument_token)
    else:
        # OLD: Full reload
        await ticker_loop.reload_subscriptions()

    return Response(status_code=204)
```

**Benefits**:
- ✅ Zero disruption to existing subscriptions
- ✅ Instant activation (no restart delay)
- ✅ Scales to thousands of subscriptions
- ✅ Backward compatible (can still use full reload)

---

## Priority 2: Backfill Webhook/Event Notification (HIGH)

### Current Problem

**Issue**: Backend doesn't know when new subscriptions are created, so backfill runs on fixed 5-minute schedule.

**Impact**:
- 5-10 minute gap before historical data available
- Poor user experience

### Requested Change

**Add webhook/event notification when subscription is created**:

```python
# NEW: Add webhook configuration
class Settings:
    # ... existing settings ...

    # Webhook URL to notify backend of subscription events
    subscription_webhook_url: str = Field(
        default="http://backend:8000/internal/subscription-events",
        description="Backend webhook URL for subscription events"
    )
    subscription_webhook_enabled: bool = Field(
        default=True,
        description="Enable webhook notifications"
    )


# NEW: Webhook notification helper
async def notify_subscription_event(
    event_type: str,  # "created", "deleted", "activated", "deactivated"
    instrument_token: int,
    tradingsymbol: str,
    metadata: Dict = None
):
    """Send webhook to backend about subscription events"""
    if not settings.subscription_webhook_enabled:
        return

    try:
        payload = {
            "event_type": event_type,
            "instrument_token": instrument_token,
            "tradingsymbol": tradingsymbol,
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": metadata or {}
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                settings.subscription_webhook_url,
                json=payload,
                timeout=5.0
            )

            if response.status_code == 200:
                logger.debug(f"Webhook sent: {event_type} for {tradingsymbol}")
            else:
                logger.warning(f"Webhook failed: {response.status_code}")

    except Exception as e:
        logger.error(f"Webhook error: {e}")
        # Don't fail subscription on webhook error


# Update subscription endpoints
@app.post("/subscriptions")
async def create_subscription(...):
    # ... existing logic ...

    # NEW: Send webhook after successful subscription
    await notify_subscription_event(
        event_type="created",
        instrument_token=payload.instrument_token,
        tradingsymbol=tradingsymbol,
        metadata={
            "requested_mode": requested_mode,
            "account_id": account_id,
            "segment": metadata.segment
        }
    )

    return response
```

**Backend will implement receiver**:
```python
# backend/app/routes/internal.py (Backend will implement)

@router.post("/subscription-events")
async def handle_subscription_event(event: SubscriptionEvent):
    """
    Receive webhook from ticker service about subscription events.
    Trigger immediate backfill for new subscriptions.
    """
    if event.event_type == "created":
        # Trigger backfill immediately
        asyncio.create_task(
            backfill_manager.backfill_instrument_immediate(event.instrument_token)
        )

    return {"status": "ok"}
```

**Alternative: Redis Pub/Sub** (if webhook not preferred):

```python
# Publish to Redis instead of webhook
await redis_client.publish(
    "ticker:subscription_events",
    json.dumps({
        "event_type": "created",
        "instrument_token": instrument_token,
        "tradingsymbol": tradingsymbol
    })
)
```

**Benefits**:
- ✅ Backend knows about subscriptions immediately
- ✅ Can trigger backfill instantly (not waiting 5 minutes)
- ✅ Better user experience (historical data in 10-30 seconds)

---

## Priority 3: Subscription Status/Health Endpoint (MEDIUM)

### Current Problem

**Issue**: Backend can't query which instruments are currently subscribed and streaming.

**Impact**:
- Can't validate if subscription is active
- Can't detect streaming failures
- Can't provide accurate status to users

### Requested Change

**Add detailed status endpoint**:

```python
# NEW ENDPOINT
@app.get("/subscriptions/status", response_model=SubscriptionStatusResponse)
async def get_subscription_status():
    """
    Get current subscription status across all accounts.

    Returns detailed information about:
    - Which instruments are subscribed
    - Which account each instrument is assigned to
    - Last tick timestamp per instrument
    - Stream health per account
    """
    status = {
        "total_subscriptions": 0,
        "accounts": {},
        "streaming": ticker_loop._running,
        "last_reload": ticker_loop._last_reload_time,
    }

    for account_id, instruments in ticker_loop._assignments.items():
        account_status = {
            "instrument_count": len(instruments),
            "instruments": [],
            "last_tick_time": ticker_loop._last_tick_at.get(account_id),
            "task_running": account_id in ticker_loop._account_tasks,
        }

        for inst in instruments:
            account_status["instruments"].append({
                "instrument_token": inst.instrument_token,
                "tradingsymbol": inst.tradingsymbol,
                "requested_mode": inst.requested_mode,
            })

        status["accounts"][account_id] = account_status
        status["total_subscriptions"] += len(instruments)

    return status


# Response model
class SubscriptionStatusResponse(BaseModel):
    total_subscriptions: int
    streaming: bool
    last_reload: Optional[datetime]
    accounts: Dict[str, AccountStatus]


class AccountStatus(BaseModel):
    instrument_count: int
    instruments: List[InstrumentInfo]
    last_tick_time: Optional[float]
    task_running: bool


class InstrumentInfo(BaseModel):
    instrument_token: int
    tradingsymbol: str
    requested_mode: str
```

**Usage Example**:
```bash
curl http://ticker-service:8080/subscriptions/status | jq

{
  "total_subscriptions": 441,
  "streaming": true,
  "last_reload": "2025-11-01T10:30:00Z",
  "accounts": {
    "primary": {
      "instrument_count": 441,
      "last_tick_time": 1730462450.123,
      "task_running": true,
      "instruments": [
        {
          "instrument_token": 13660418,
          "tradingsymbol": "NIFTY25NOV24500CE",
          "requested_mode": "FULL"
        },
        ...
      ]
    }
  }
}
```

**Benefits**:
- ✅ Backend can validate subscriptions are active
- ✅ Can detect streaming failures
- ✅ Better monitoring and debugging

---

## Priority 4: Graceful Error Handling for Expired Instruments (MEDIUM)

### Current Problem

**Issue**: Requesting history for expired options returns 404, but no distinction from other errors.

**Impact**:
- Backend blacklists expired options permanently
- Can't differentiate between "expired" vs "API error"

### Requested Change

**Add error codes to history endpoint**:

```python
# ticker_service/app/main.py

@app.get("/history")
async def get_history(instrument_token: int, ...):
    try:
        # Attempt to fetch history
        data = await fetch_kite_history(instrument_token, ...)
        return {"status": "ok", "data": data}

    except HTTPException as e:
        if e.status_code == 404:
            # Check if instrument is expired
            metadata = await instrument_registry.fetch_metadata(instrument_token)
            if metadata and metadata.expiry:
                if metadata.expiry < date.today():
                    # Return special error code for expired instruments
                    raise HTTPException(
                        status_code=410,  # 410 Gone (not 404)
                        detail={
                            "error_code": "INSTRUMENT_EXPIRED",
                            "message": f"Instrument {metadata.tradingsymbol} expired on {metadata.expiry}",
                            "expiry_date": metadata.expiry.isoformat(),
                            "is_permanent": True  # ← Backend knows not to retry
                        }
                    )

        # Re-raise other errors
        raise


# Alternative: Add error_code field to all responses
{
    "status": "error",
    "error_code": "INSTRUMENT_EXPIRED",  # or "RATE_LIMIT", "API_ERROR", etc.
    "message": "...",
    "is_permanent": true,  # Don't retry
    "metadata": {...}
}
```

**Benefits**:
- ✅ Backend can handle expired instruments gracefully
- ✅ No permanent blacklisting of expired options
- ✅ Better error handling and retry logic

---

## Priority 5: Bulk Subscription API (LOW)

### Current Problem

**Issue**: Frontend needs to subscribe to 20+ option strikes, requires 20+ API calls.

**Impact**:
- High latency (20 sequential calls)
- Network overhead
- 20 separate reload cycles (if not using incremental)

### Requested Change

**Add bulk subscription endpoint**:

```python
# NEW ENDPOINT
@app.post("/subscriptions/bulk", response_model=BulkSubscriptionResponse)
async def create_bulk_subscriptions(
    payload: BulkSubscriptionRequest,
    incremental: bool = Query(True)
):
    """
    Create multiple subscriptions in a single API call.

    Processes all subscriptions and adds them incrementally (if supported).
    """
    results = []

    for item in payload.subscriptions:
        try:
            # Validate and persist
            metadata = await instrument_registry.fetch_metadata(item.instrument_token)
            await subscription_store.upsert(
                instrument_token=item.instrument_token,
                tradingsymbol=metadata.tradingsymbol,
                segment=metadata.segment,
                requested_mode=item.requested_mode,
            )

            # Add incrementally
            if incremental and ticker_loop._running:
                success = await ticker_loop.add_subscription_incremental(
                    instrument_token=item.instrument_token,
                    tradingsymbol=metadata.tradingsymbol,
                    requested_mode=item.requested_mode,
                )

                results.append({
                    "instrument_token": item.instrument_token,
                    "status": "success" if success else "failed",
                    "tradingsymbol": metadata.tradingsymbol,
                })

        except Exception as e:
            results.append({
                "instrument_token": item.instrument_token,
                "status": "error",
                "error": str(e),
            })

    # If incremental failed for any, do full reload as fallback
    if any(r["status"] == "failed" for r in results):
        await ticker_loop.reload_subscriptions()

    return {"results": results}


# Request model
class BulkSubscriptionRequest(BaseModel):
    subscriptions: List[SubscriptionItem]


class SubscriptionItem(BaseModel):
    instrument_token: int
    requested_mode: str = "FULL"
```

**Usage Example**:
```bash
curl -X POST http://ticker-service:8080/subscriptions/bulk \
  -H "Content-Type: application/json" \
  -d '{
    "subscriptions": [
      {"instrument_token": 13660418, "requested_mode": "FULL"},
      {"instrument_token": 13660419, "requested_mode": "FULL"},
      {"instrument_token": 13660420, "requested_mode": "FULL"}
    ]
  }'
```

**Benefits**:
- ✅ Single API call for entire option chain
- ✅ Lower latency
- ✅ Single incremental update (or single reload if incremental not available)

---

## Optional Enhancement: Subscription Templates

### Use Case

**Problem**: Users always subscribe to same patterns (e.g., "NIFTY ATM ±10 strikes for next 3 expiries").

### Requested Change

**Add template-based subscription**:

```python
# NEW ENDPOINT
@app.post("/subscriptions/template")
async def subscribe_from_template(
    template_type: str = Query(..., description="atm_strikes, otm_range, etc."),
    underlying: str = Query(..., description="NIFTY, BANKNIFTY, etc."),
    params: Dict = Body(...)
):
    """
    Subscribe using predefined templates.

    Templates:
    - atm_strikes: Subscribe to ATM ± N strikes
    - otm_range: Subscribe to strikes between OTM% and OTM%
    - full_chain: Subscribe to entire option chain
    """
    if template_type == "atm_strikes":
        # Get current underlying price
        quote = await get_underlying_quote(underlying)
        atm_strike = round_to_strike(quote.ltp)

        # Get option chain around ATM
        num_strikes = params.get("num_strikes", 10)
        expiries = params.get("expiries", [get_next_expiry()])

        tokens = await get_option_chain_tokens(
            underlying=underlying,
            center_strike=atm_strike,
            num_strikes=num_strikes,
            expiries=expiries,
        )

        # Bulk subscribe
        return await create_bulk_subscriptions(
            BulkSubscriptionRequest(subscriptions=[
                SubscriptionItem(instrument_token=token)
                for token in tokens
            ])
        )
```

**Benefits**:
- ✅ User-friendly API
- ✅ Single call for complex subscription patterns
- ✅ Reduces frontend complexity

---

## Summary Table

| Priority | Change | Effort | Impact | Backend Dependency |
|----------|--------|--------|--------|--------------------|
| **P1** | Incremental subscription updates | Medium | High | Low - Backend can continue using full reload |
| **P1** | Backfill webhook/event | Low | High | High - Backend needs webhook receiver |
| **P2** | Subscription status endpoint | Low | Medium | Medium - Backend can monitor health |
| **P2** | Graceful error handling | Low | Medium | Medium - Backend can handle errors better |
| **P3** | Bulk subscription API | Low | Low | Low - Backend can batch calls |
| **Optional** | Subscription templates | Medium | Low | None - Convenience feature |

---

## Implementation Order (Recommended)

### Phase 1 (This Sprint)
1. **Incremental subscription updates** - Biggest performance improvement
2. **Backfill webhook** - Enables immediate historical data

### Phase 2 (Next Sprint)
3. **Subscription status endpoint** - Better monitoring
4. **Graceful error handling** - Fix expired option issues

### Phase 3 (Future)
5. **Bulk subscription API** - Convenience improvement
6. **Subscription templates** - Advanced feature

---

## Testing Requirements

For each change, please provide:

1. **Unit tests** for new methods
2. **Integration tests** for API endpoints
3. **Load tests** for incremental updates (1000+ subscriptions)
4. **Documentation** updates in API docs

---

## Backward Compatibility

All changes should maintain backward compatibility:

- Incremental updates: Add `?incremental=true` query parameter (default true)
- Full reload still available as fallback
- Existing API contracts unchanged
- No breaking changes to response formats

---

## Questions for Ticker Service Team

1. **Incremental Updates**: Is there any technical limitation preventing incremental WebSocket subscription changes in KiteConnect SDK?

2. **Webhook vs PubSub**: Would you prefer HTTP webhook or Redis pub/sub for event notifications?

3. **Timeline**: What's the estimated timeline for implementing P1 changes?

4. **Testing**: Do you need backend team's help with integration testing?

5. **Load Limits**: What's the practical limit for number of subscriptions per account we should target?

---

**Prepared By**: Backend Team
**Review Requested**: Ticker Service Team
**Follow-up**: Please schedule a call to discuss timeline and implementation details

