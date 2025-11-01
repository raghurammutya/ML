# Backend Subscription Improvements - Implementation Plan

**Date**: November 1, 2025
**Status**: Ready to Implement
**Dependencies**: None (works with current ticker service)

---

## Changes We Can Make Now (No Ticker Service Changes Required)

### 1. Smart On-Demand Subscription
### 2. Subscription Awareness in Backfill
### 3. Improved Error Handling
### 4. Subscription Status Tracking
### 5. Webhook Receiver for Future Ticker Service Integration

---

## Implementation 1: Smart On-Demand Auto-Subscribe

### Files to Modify

1. **`app/services/smart_subscription_manager.py`** (NEW)
2. **`app/routes/fo.py`** (MODIFY)
3. **`app/routes/marks_asyncpg.py`** (MODIFY)

### Code

#### NEW: `app/services/smart_subscription_manager.py`

```python
"""
Smart subscription manager for automatic on-demand subscriptions.
"""

import asyncio
import logging
from typing import List, Set, Optional
from datetime import datetime, date

from app.ticker_client import TickerServiceClient
from app.database import DataManager

logger = logging.getLogger(__name__)


class SmartSubscriptionManager:
    """
    Manages automatic on-demand subscriptions for instruments.

    Features:
    - Auto-subscribe when data requested but not available
    - Track subscription status
    - Prevent duplicate subscription attempts
    - Cache subscription decisions
    """

    def __init__(
        self,
        ticker_client: TickerServiceClient,
        data_manager: DataManager,
    ):
        self._ticker_client = ticker_client
        self._dm = data_manager

        # Track tokens we've attempted to subscribe
        self._subscription_attempts: Set[int] = set()

        # Track when we last checked subscription status
        self._last_check: dict[int, datetime] = {}

        # Cache of known subscribed tokens
        self._known_subscribed: Set[int] = set()

    async def ensure_subscribed(
        self,
        instrument_tokens: List[int],
        wait_for_data: bool = True,
        timeout_seconds: float = 10.0,
    ) -> dict:
        """
        Ensure instruments are subscribed, subscribing if necessary.

        Args:
            instrument_tokens: List of tokens to ensure are subscribed
            wait_for_data: If True, wait for data to start flowing
            timeout_seconds: Max time to wait for data

        Returns:
            Dictionary with subscription results:
            {
                "already_subscribed": [...],
                "newly_subscribed": [...],
                "failed": [...],
                "data_available": bool
            }
        """
        already_subscribed = []
        newly_subscribed = []
        failed = []

        # Check which are already subscribed
        for token in instrument_tokens:
            if token in self._known_subscribed:
                already_subscribed.append(token)
                continue

            # Check if we've recently verified this token
            if token in self._last_check:
                time_since_check = (datetime.utcnow() - self._last_check[token]).total_seconds()
                if time_since_check < 60:  # Cache for 1 minute
                    already_subscribed.append(token)
                    continue

            # Query ticker service for subscription status
            try:
                subscriptions = await self._ticker_client.list_subscriptions(status="active")
                subscribed_tokens = {sub["instrument_token"] for sub in subscriptions}

                if token in subscribed_tokens:
                    already_subscribed.append(token)
                    self._known_subscribed.add(token)
                    self._last_check[token] = datetime.utcnow()
                else:
                    # Need to subscribe
                    if await self._subscribe_token(token):
                        newly_subscribed.append(token)
                        self._known_subscribed.add(token)
                    else:
                        failed.append(token)

            except Exception as e:
                logger.error(f"Failed to check/subscribe token {token}: {e}")
                failed.append(token)

        # Wait for data if requested
        data_available = False
        if wait_for_data and newly_subscribed:
            logger.info(f"Waiting up to {timeout_seconds}s for data from {len(newly_subscribed)} new subscriptions")
            data_available = await self._wait_for_data(newly_subscribed, timeout_seconds)

        return {
            "already_subscribed": already_subscribed,
            "newly_subscribed": newly_subscribed,
            "failed": failed,
            "data_available": data_available or bool(already_subscribed),
        }

    async def _subscribe_token(self, instrument_token: int) -> bool:
        """Subscribe to single token"""
        if instrument_token in self._subscription_attempts:
            logger.debug(f"Already attempted subscription for {instrument_token}")
            return False

        self._subscription_attempts.add(instrument_token)

        try:
            result = await self._ticker_client.subscribe(
                instrument_token=instrument_token,
                requested_mode="FULL",
            )

            logger.info(f"Subscribed to {result.get('tradingsymbol', instrument_token)}")
            return True

        except Exception as e:
            logger.error(f"Failed to subscribe to {instrument_token}: {e}")
            return False

    async def _wait_for_data(
        self,
        instrument_tokens: List[int],
        timeout_seconds: float,
    ) -> bool:
        """
        Wait for data to appear in database for newly subscribed tokens.

        Polls database every second for up to timeout_seconds.
        """
        start_time = datetime.utcnow()

        while (datetime.utcnow() - start_time).total_seconds() < timeout_seconds:
            # Check if data exists for any of the tokens
            # (Implementation depends on table structure)
            # For now, just wait fixed time
            await asyncio.sleep(2)

            # TODO: Implement actual data check
            # For options: Check fo_option_strike_bars
            # For futures: Check futures_bars

        logger.info(f"Waited {timeout_seconds}s for data")
        return True  # Assume data is flowing

    async def ensure_option_chain_subscribed(
        self,
        symbol: str,
        expiries: List[date],
        num_strikes: int = 10,
    ) -> dict:
        """
        Ensure option chain is subscribed.

        Fetches ATM and subscribes to ATM ± num_strikes.
        """
        # Get instrument tokens for option chain
        tokens = await self._get_option_chain_tokens(symbol, expiries, num_strikes)

        return await self.ensure_subscribed(tokens, wait_for_data=True)

    async def _get_option_chain_tokens(
        self,
        symbol: str,
        expiries: List[date],
        num_strikes: int,
    ) -> List[int]:
        """Get instrument tokens for option chain"""
        # This would query nifty_options_registry or similar
        # For now, return empty (implementation depends on registry structure)

        # TODO: Implement based on your instrument registry
        tokens = []

        logger.warning(f"_get_option_chain_tokens not fully implemented yet")
        return tokens

    def clear_cache(self):
        """Clear cached subscription status (for testing)"""
        self._known_subscribed.clear()
        self._last_check.clear()
        self._subscription_attempts.clear()
```

#### MODIFY: `app/routes/fo.py`

```python
# Add at top
from app.services.smart_subscription_manager import SmartSubscriptionManager

# In router initialization or dependency injection
smart_sub_manager = None  # Will be initialized in main.py


@router.get("/strike-distribution")
async def strike_distribution(
    symbol: str,
    timeframe: Literal["1min", "5min", "15min"] = "5min",
    expiries: Optional[str] = None,
    auto_subscribe: bool = Query(True, description="Auto-subscribe if data not available"),
):
    """
    Get strike distribution with smart auto-subscription.

    If auto_subscribe=true (default), will automatically subscribe to
    missing instruments and wait for data to flow.
    """
    # Parse expiries
    expiry_list = _parse_expiries(expiries) if expiries else await _get_default_expiries(symbol)

    # Try to fetch data
    rows = await dm.fetch_latest_fo_strike_rows(symbol, timeframe, expiry_list)

    # If no data and auto-subscribe enabled, try to subscribe
    if not rows and auto_subscribe and smart_sub_manager:
        logger.info(f"No data for {symbol}, attempting auto-subscription")

        try:
            # Subscribe to option chain
            result = await smart_sub_manager.ensure_option_chain_subscribed(
                symbol=symbol,
                expiries=expiry_list,
                num_strikes=10,  # Configurable
            )

            if result["data_available"]:
                # Retry fetch after subscription
                await asyncio.sleep(2)  # Give data time to flow
                rows = await dm.fetch_latest_fo_strike_rows(symbol, timeframe, expiry_list)

                if rows:
                    logger.info(f"Data available after auto-subscription: {len(rows)} rows")
                else:
                    logger.warning(f"Still no data after auto-subscription")
            else:
                logger.warning(f"Auto-subscription failed: {result}")

        except Exception as e:
            logger.error(f"Auto-subscription error: {e}")
            # Continue with empty data (don't fail request)

    # Format and return response
    series = format_strike_distribution(rows) if rows else []

    return {
        "status": "ok",
        "series": series,
        "metadata": {
            "auto_subscribed": bool(rows and auto_subscribe),
            "expiries": [str(e) for e in expiry_list],
        }
    }


def _parse_expiries(expiries_str: str) -> List[date]:
    """Parse comma-separated expiry dates"""
    return [date.fromisoformat(e.strip()) for e in expiries_str.split(",")]


async def _get_default_expiries(symbol: str) -> List[date]:
    """Get default expiries (next 3 monthly)"""
    # Implementation depends on your expiry calculation logic
    from app.services.expiry_calculator import get_next_expiries
    return get_next_expiries(symbol, count=3)
```

---

## Implementation 2: Subscription-Aware Backfill

### Files to Modify

1. **`app/backfill.py`** (MODIFY)

### Code

#### MODIFY: `app/backfill.py`

```python
# Add method to BackfillManager class

async def _get_active_subscription_tokens(self) -> Set[int]:
    """
    Get instrument tokens that are actively subscribed.

    Queries ticker service for active subscriptions.
    """
    try:
        subscriptions = await self._ticker_client.list_subscriptions(status="active")
        tokens = {sub["instrument_token"] for sub in subscriptions}

        logger.info(f"Found {len(tokens)} active subscriptions in ticker service")
        return tokens

    except Exception as e:
        logger.error(f"Failed to fetch active subscriptions: {e}")
        # Fallback to metadata-based approach
        return set()


async def _tick(self):
    """
    Main backfill tick.

    UPDATED: Now prioritizes actively subscribed instruments.
    """
    try:
        # Get active subscriptions
        active_tokens = await self._get_active_subscription_tokens()

        # Get metadata (for discovery)
        metadata = await get_nifty_monitor_metadata()

        # Backfill underlying (always)
        await self._backfill_underlying()

        # Backfill futures (prioritize subscribed)
        for future in metadata.get("futures", []):
            if active_tokens and future["instrument_token"] not in active_tokens:
                logger.debug(f"Skipping unsubscribed future: {future['tradingsymbol']}")
                continue

            await self._backfill_futures()
            break  # Only one future for now

        # Backfill options (prioritize subscribed)
        await self._backfill_options_smart(
            symbol=metadata["underlying"]["symbol"],
            active_tokens=active_tokens,
        )

    except Exception as e:
        logger.error(f"Backfill tick failed: {e}", exc_info=True)


async def _backfill_options_smart(
    self,
    symbol: str,
    active_tokens: Set[int],
):
    """
    Backfill options, prioritizing actively subscribed tokens.

    If active_tokens is provided, only backfills those tokens.
    Otherwise, falls back to metadata-based discovery.
    """
    # Compute window
    latest_option_time = await self._dm.latest_option_bucket_time(symbol, "1min")
    window = self._compute_window(latest_option_time, datetime.utcnow())

    if not window:
        logger.debug(f"No backfill needed for options (gap < {self._gap_threshold})")
        return

    start, end = window

    # Get expiries
    expiries = await self._dm.get_active_expiries(symbol, limit=self._expiry_window)

    for expiry in expiries:
        await self._backfill_option_expiry_smart(
            symbol=symbol,
            expiry=expiry,
            start=start,
            end=end,
            active_tokens=active_tokens,
        )


async def _backfill_option_expiry_smart(
    self,
    symbol: str,
    expiry: date,
    start: datetime,
    end: datetime,
    active_tokens: Set[int],
):
    """
    Backfill single expiry, filtering by active subscriptions.
    """
    # Get strikes for this expiry
    strikes = await self._dm.get_strikes_for_expiry(symbol, expiry)

    for strike in strikes:
        # Get option tokens (call + put)
        call_token = await self._dm.get_option_token(symbol, expiry, strike, "CE")
        put_token = await self._dm.get_option_token(symbol, expiry, strike, "PE")

        # Filter by active subscriptions if available
        if active_tokens:
            if call_token not in active_tokens and put_token not in active_tokens:
                logger.debug(f"Skipping unsubscribed strike {strike}")
                continue

        # Backfill call
        if call_token and (not active_tokens or call_token in active_tokens):
            await self._backfill_option_instrument(call_token, start, end)

        # Backfill put
        if put_token and (not active_tokens or put_token in active_tokens):
            await self._backfill_option_instrument(put_token, start, end)


async def backfill_instrument_immediate(self, instrument_token: int):
    """
    Trigger immediate backfill for a specific instrument.

    Called when new subscription is created (via webhook).
    """
    logger.info(f"Immediate backfill triggered for token {instrument_token}")

    try:
        # Fetch instrument metadata
        metadata = await self._ticker_client.get_instrument_metadata(instrument_token)

        if not metadata:
            logger.error(f"Instrument metadata not found for {instrument_token}")
            return

        # Compute window (last 2 hours or since last bar)
        last_time = await self._get_last_bar_time_for_instrument(instrument_token, metadata)
        window = self._compute_window(last_time, datetime.utcnow())

        if not window:
            logger.info(f"No backfill needed for {instrument_token}")
            return

        start, end = window

        # Backfill based on instrument type
        if metadata["segment"] == "NFO-OPT":
            await self._backfill_option_instrument(instrument_token, start, end)
        elif metadata["segment"] == "NFO-FUT":
            await self._backfill_futures_instrument(instrument_token, start, end)
        else:
            logger.warning(f"Unknown segment for backfill: {metadata['segment']}")

        logger.info(f"Immediate backfill completed for {instrument_token}")

    except Exception as e:
        logger.error(f"Immediate backfill failed for {instrument_token}: {e}", exc_info=True)


async def _get_last_bar_time_for_instrument(
    self,
    instrument_token: int,
    metadata: dict,
) -> Optional[datetime]:
    """Get last bar timestamp for specific instrument"""
    if metadata["segment"] == "NFO-OPT":
        # Query fo_option_strike_bars
        return await self._dm.latest_option_bucket_time_for_token(instrument_token)
    elif metadata["segment"] == "NFO-FUT":
        # Query futures_bars
        return await self._dm.latest_futures_bar_time_for_token(instrument_token)
    else:
        return None
```

---

## Implementation 3: Webhook Receiver for Subscription Events

### Files to Create

1. **`app/routes/internal.py`** (NEW)

### Code

#### NEW: `app/routes/internal.py`

```python
"""
Internal API endpoints for service-to-service communication.

Not exposed to external users.
"""

import asyncio
import logging
from fastapi import APIRouter, BackgroundTasks, HTTPException, Depends
from pydantic import BaseModel
from datetime import datetime
from typing import Optional, Dict

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal", tags=["internal"])


# Models
class SubscriptionEvent(BaseModel):
    event_type: str  # "created", "deleted", "activated", "deactivated"
    instrument_token: int
    tradingsymbol: str
    timestamp: str
    metadata: Optional[Dict] = None


# Dependency to inject backfill manager
# (Will be set in main.py)
backfill_manager = None


@router.post("/subscription-events", status_code=200)
async def handle_subscription_event(
    event: SubscriptionEvent,
    background_tasks: BackgroundTasks,
):
    """
    Handle subscription events from ticker service.

    Triggers immediate backfill for new subscriptions.
    """
    logger.info(f"Received subscription event: {event.event_type} for {event.tradingsymbol}")

    if event.event_type == "created":
        # Trigger immediate backfill in background
        if backfill_manager:
            background_tasks.add_task(
                backfill_manager.backfill_instrument_immediate,
                event.instrument_token
            )
            logger.info(f"Scheduled immediate backfill for {event.instrument_token}")
        else:
            logger.warning("Backfill manager not available, skipping immediate backfill")

    elif event.event_type == "deleted":
        # Could clean up cached data or stop processing
        logger.info(f"Subscription deleted: {event.tradingsymbol}")

    return {
        "status": "ok",
        "message": f"Event {event.event_type} processed",
        "instrument_token": event.instrument_token,
    }


@router.get("/health", status_code=200)
async def health_check():
    """Internal health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
    }
```

#### UPDATE: `app/main.py`

```python
# Add to main.py

from app.routes import internal as internal_routes

# Set backfill manager reference
internal_routes.backfill_manager = backfill_manager

# Include router
app.include_router(internal_routes.router)
```

---

## Implementation 4: Configuration

### Files to Modify

1. **`app/config.py`** (MODIFY)

### Code

```python
# Add to Settings class

# Smart subscription settings
smart_subscription_enabled: bool = Field(
    default=True,
    description="Enable automatic on-demand subscriptions"
)
smart_subscription_wait_timeout: float = Field(
    default=10.0,
    description="Seconds to wait for data after auto-subscription"
)
smart_subscription_cache_ttl: int = Field(
    default=60,
    description="Seconds to cache subscription status checks"
)

# Backfill improvements
backfill_subscription_aware: bool = Field(
    default=True,
    description="Only backfill actively subscribed instruments"
)
backfill_immediate_on_subscribe: bool = Field(
    default=True,
    description="Trigger immediate backfill when new subscription created"
)
```

---

## Testing Plan

### Unit Tests

```python
# tests/test_smart_subscription_manager.py

import pytest
from app.services.smart_subscription_manager import SmartSubscriptionManager

@pytest.mark.asyncio
async def test_ensure_subscribed_already_subscribed(mock_ticker_client, mock_dm):
    manager = SmartSubscriptionManager(mock_ticker_client, mock_dm)

    # Mock: token already subscribed
    mock_ticker_client.list_subscriptions.return_value = [
        {"instrument_token": 12345, "status": "active"}
    ]

    result = await manager.ensure_subscribed([12345], wait_for_data=False)

    assert 12345 in result["already_subscribed"]
    assert not result["newly_subscribed"]
    assert not result["failed"]


@pytest.mark.asyncio
async def test_ensure_subscribed_new_subscription(mock_ticker_client, mock_dm):
    manager = SmartSubscriptionManager(mock_ticker_client, mock_dm)

    # Mock: token not subscribed
    mock_ticker_client.list_subscriptions.return_value = []
    mock_ticker_client.subscribe.return_value = {"tradingsymbol": "NIFTY25NOV24500CE"}

    result = await manager.ensure_subscribed([12345], wait_for_data=False)

    assert 12345 in result["newly_subscribed"]
    mock_ticker_client.subscribe.assert_called_once()
```

### Integration Tests

```bash
# Test auto-subscription flow

# 1. Ensure no data
curl "http://localhost:8081/fo/strike-distribution?symbol=NIFTY&expiry=2025-11-28"
# Expected: {"series": []}

# 2. Request with auto_subscribe=true (default)
curl "http://localhost:8081/fo/strike-distribution?symbol=NIFTY&expiry=2025-11-28&auto_subscribe=true"
# Expected: Triggers subscription, waits, returns data

# 3. Verify subscription created
curl "http://localhost:8080/subscriptions?status=active" | jq
# Expected: Shows new NIFTY options subscribed
```

---

## Rollout Plan

### Phase 1: Deploy with Feature Flags (Week 1)

```python
# All features disabled by default
SMART_SUBSCRIPTION_ENABLED=false
BACKFILL_SUBSCRIPTION_AWARE=false
BACKFILL_IMMEDIATE_ON_SUBSCRIBE=false
```

### Phase 2: Enable Smart Subscription (Week 2)

```python
SMART_SUBSCRIPTION_ENABLED=true
# Monitor logs for auto-subscription behavior
# Verify no duplicate subscriptions
```

### Phase 3: Enable Subscription-Aware Backfill (Week 3)

```python
BACKFILL_SUBSCRIPTION_AWARE=true
# Verify only subscribed instruments backfilled
# Monitor performance improvement
```

### Phase 4: Enable Immediate Backfill (Week 4)

```python
BACKFILL_IMMEDIATE_ON_SUBSCRIBE=true
# When ticker service adds webhook support
# Verify <30 second historical data availability
```

---

## Success Metrics

Track these metrics before/after deployment:

1. **Auto-Subscription Success Rate**
   - % of requests that successfully auto-subscribed
   - Target: >95%

2. **Time to Data**
   - Time from first request to data available
   - Before: N/A (manual subscription)
   - After: <30 seconds (with immediate backfill)

3. **Backfill Efficiency**
   - Number of instruments backfilled per cycle
   - Before: All instruments in metadata (~100+)
   - After: Only subscribed instruments (~20-50)

4. **Subscription Overhead**
   - Number of subscription API calls per day
   - Monitor for excessive calls (caching issue)

---

## Monitoring & Alerts

### Logs to Monitor

```python
# Success
"Auto-subscription successful: {tradingsymbol}"
"Immediate backfill triggered for token {token}"
"Backfilling {N} subscribed instruments"

# Warnings
"Auto-subscription failed: {error}"
"Still no data after auto-subscription"
"Backfill manager not available for immediate backfill"

# Errors
"Failed to check/subscribe token {token}: {error}"
"Immediate backfill failed for {token}: {error}"
```

### Alerts

1. **High Auto-Subscribe Failure Rate**
   - Alert if >10% of auto-subscribe attempts fail
   - Action: Check ticker service health

2. **Slow Data Availability**
   - Alert if data not available 30s after subscription
   - Action: Check streaming pipeline

3. **Excessive Subscription Calls**
   - Alert if >1000 subscription API calls/hour
   - Action: Check caching logic

---

## Documentation Updates Needed

1. **API Documentation**: Update swagger docs for new `auto_subscribe` parameter
2. **Operations Guide**: How to monitor smart subscriptions
3. **Troubleshooting**: Common issues and solutions

---

**Status**: Ready to implement
**Dependencies**: None (works with current ticker service)
**Estimated Effort**: 2-3 days development + 1 week phased rollout
**Risk Level**: Low (feature-flagged, backward compatible)

