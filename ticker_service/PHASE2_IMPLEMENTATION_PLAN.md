# TICKER SERVICE - PHASE 1 IMPLEMENTATION PLAN
**Detailed Implementation Guide with Code Examples**

**Date**: November 8, 2025
**Target Completion**: Week 1 (7 days)
**Total Effort**: 18-24 hours
**Risk Level**: LOW-MEDIUM

---

## TABLE OF CONTENTS

1. [Overview](#overview)
2. [Implementation Priority 1: Task Exception Handler](#implementation-priority-1-task-exception-handler)
3. [Implementation Priority 2: Bound Reload Queue](#implementation-priority-2-bound-reload-queue)
4. [Implementation Priority 3: Fix Mock State Races](#implementation-priority-3-fix-mock-state-races)
5. [Implementation Priority 4: Add Redis Circuit Breaker](#implementation-priority-4-add-redis-circuit-breaker)
6. [Implementation Priority 5: Fix Memory Leak in Mock State](#implementation-priority-5-fix-memory-leak-in-mock-state)
7. [Testing Strategy](#testing-strategy)
8. [Deployment Plan](#deployment-plan)

---

## OVERVIEW

###  Scope of Phase 1

Phase 1 focuses on **critical reliability improvements** that prevent silent failures and data loss. All changes are **100% backward compatible** and preserve existing functionality.

### Success Criteria

- ✅ Zero silent task failures (all exceptions logged and alerted)
- ✅ No unbounded resource growth (queues, dictionaries)
- ✅ No race conditions in mock data generation
- ✅ Graceful degradation when Redis unavailable
- ✅ All existing tests pass
- ✅ No performance regression

### Timeline

| Day | Tasks | Hours |
|-----|-------|-------|
| **Day 1** | Implementation Priority 1 (Task Exception Handler) | 2-3 |
| **Day 2** | Implementation Priority 2 (Bound Reload Queue) | 3-4 |
| **Day 3** | Implementation Priority 3 (Fix Mock State Races) | 4-5 |
| **Day 4** | Implementation Priority 4 (Redis Circuit Breaker) | 3-4 |
| **Day 5** | Implementation Priority 5 (Memory Leak Fix) | 3-4 |
| **Day 6-7** | Testing, Documentation, Deployment | 6-8 |

---

## IMPLEMENTATION PRIORITY 1: Task Exception Handler

### Objective
Capture all unhandled exceptions from background asyncio tasks to prevent silent failures.

### Current Problem

```python
# app/generator.py:157-161
self._underlying_task = asyncio.create_task(self._stream_underlying())

for account_id, acc_instruments in accounts_map.items():
    task = asyncio.create_task(self._stream_account(account_id, acc_instruments))
    self._account_tasks[account_id] = task
```

If any of these tasks crash, the exception is lost and streaming stops silently.

### Implementation Steps

#### Step 1.1: Create Task Monitor Utility

**File**: `app/utils/task_monitor.py` (NEW FILE)

```python
"""
Task monitoring and exception handling utilities.
"""
import asyncio
import logging
from typing import Callable, Coroutine, Any, Optional

logger = logging.getLogger(__name__)


class TaskMonitor:
    """
    Monitors asyncio tasks and logs unhandled exceptions.
    """

    def __init__(self, loop: Optional[asyncio.AbstractEventLoop] = None):
        self._loop = loop or asyncio.get_running_loop()
        self._setup_exception_handler()

    def _setup_exception_handler(self):
        """Set up global exception handler for unhandled task exceptions"""
        def exception_handler(loop: asyncio.AbstractEventLoop, context: dict):
            exc = context.get("exception")
            task = context.get("task")
            message = context.get("message", "Unhandled exception in task")

            logger.critical(
                f"Unhandled asyncio exception: {message}",
                exc_info=exc,
                extra={
                    "task": str(task),
                    "task_name": task.get_name() if task else None,
                    "context": context,
                },
            )

            # Optional: Add alerting here (PagerDuty, Slack, etc.)
            # await self._send_alert(message, exc, task)

        self._loop.set_exception_handler(exception_handler)
        logger.info("Global task exception handler registered")

    @staticmethod
    async def monitored_task(
        coro: Coroutine,
        task_name: str,
        on_error: Optional[Callable[[Exception], Any]] = None,
    ) -> None:
        """
        Wrap a coroutine with exception handling.

        Args:
            coro: The coroutine to execute
            task_name: Human-readable name for logging
            on_error: Optional callback when task fails
        """
        try:
            await coro
        except asyncio.CancelledError:
            logger.info(f"Task '{task_name}' was cancelled")
            raise  # Re-raise to properly propagate cancellation
        except Exception as exc:
            logger.critical(
                f"Task '{task_name}' failed with exception",
                exc_info=True,
                extra={"task_name": task_name, "error": str(exc)},
            )

            if on_error:
                try:
                    result = on_error(exc)
                    if asyncio.iscoroutine(result):
                        await result
                except Exception as callback_exc:
                    logger.exception(
                        f"Error callback for '{task_name}' failed: {callback_exc}"
                    )

            # Don't re-raise - let the task die gracefully
            # The exception has been logged and alerted

    def create_monitored_task(
        self,
        coro: Coroutine,
        task_name: str,
        on_error: Optional[Callable[[Exception], Any]] = None,
    ) -> asyncio.Task:
        """
        Create a task with automatic exception monitoring.

        Args:
            coro: The coroutine to execute
            task_name: Human-readable name for logging
            on_error: Optional callback when task fails

        Returns:
            asyncio.Task with monitoring
        """
        wrapped_coro = self.monitored_task(coro, task_name, on_error)
        task = self._loop.create_task(wrapped_coro)
        task.set_name(task_name)
        return task
```

#### Step 1.2: Integrate TaskMonitor in main.py

**File**: `app/main.py`

**Location**: In the lifespan context manager (around line 80-100)

```python
# BEFORE (lines ~80-100)
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting ticker service...")

    # ... existing initialization ...

    yield

    logger.info("Shutting down ticker service...")
    # ... existing cleanup ...


# AFTER
from app.utils.task_monitor import TaskMonitor

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting ticker service...")

    # NEW: Set up global task exception monitoring
    task_monitor = TaskMonitor(asyncio.get_running_loop())
    app.state.task_monitor = task_monitor
    logger.info("Global task exception handler enabled")

    # ... existing initialization ...

    yield

    logger.info("Shutting down ticker service...")
    # ... existing cleanup ...
```

#### Step 1.3: Update MultiAccountTickerLoop to Use TaskMonitor

**File**: `app/generator.py`

**Location**: Lines 157-163

```python
# BEFORE
async def start(self) -> None:
    if self._running:
        logger.warning("MultiAccountTickerLoop is already running")
        return

    self._running = True
    self._stop_event = asyncio.Event()

    # Start tasks WITHOUT exception handling
    self._underlying_task = asyncio.create_task(self._stream_underlying())

# AFTER
from app.utils.task_monitor import TaskMonitor

class MultiAccountTickerLoop:
    def __init__(
        self,
        settings: Settings,
        registry: InstrumentRegistry,
        subscription_store: SubscriptionStore,
        publisher: Optional[RedisPublisher] = None,
        task_monitor: Optional[TaskMonitor] = None,  # NEW parameter
    ):
        # ... existing initialization ...
        self._task_monitor = task_monitor  # NEW: Store task monitor

    async def start(self) -> None:
        if self._running:
            logger.warning("MultiAccountTickerLoop is already running")
            return

        self._running = True
        self._stop_event = asyncio.Event()

        # NEW: Create underlying task with monitoring
        if self._task_monitor:
            self._underlying_task = self._task_monitor.create_monitored_task(
                self._stream_underlying(),
                task_name="stream_underlying",
                on_error=self._on_underlying_stream_error,
            )
        else:
            # Fallback if no task monitor provided
            self._underlying_task = asyncio.create_task(self._stream_underlying())
            logger.warning("Task monitor not available - using unmonitored task")

    async def _on_underlying_stream_error(self, exc: Exception) -> None:
        """Callback when underlying stream task fails"""
        logger.critical(
            f"Underlying stream failed critically: {exc}",
            exc_info=True,
            extra={"component": "ticker_loop", "stream": "underlying"}
        )
        # Optional: Attempt restart
        # await asyncio.sleep(5.0)
        # await self.start()
```

**Location**: Lines 161-166 (account tasks)

```python
# BEFORE
for account_id, acc_instruments in accounts_map.items():
    task = asyncio.create_task(self._stream_account(account_id, acc_instruments))
    self._account_tasks[account_id] = task

# AFTER
for account_id, acc_instruments in accounts_map.items():
    if self._task_monitor:
        task = self._task_monitor.create_monitored_task(
            self._stream_account(account_id, acc_instruments),
            task_name=f"stream_account_{account_id}",
            on_error=lambda exc, aid=account_id: self._on_account_stream_error(aid, exc),
        )
    else:
        task = asyncio.create_task(self._stream_account(account_id, acc_instruments))
        logger.warning(f"Creating unmonitored task for account {account_id}")

    self._account_tasks[account_id] = task

async def _on_account_stream_error(self, account_id: str, exc: Exception) -> None:
    """Callback when account stream task fails"""
    logger.critical(
        f"Account stream for {account_id} failed critically: {exc}",
        exc_info=True,
        extra={"component": "ticker_loop", "account_id": account_id}
    )
    # Remove failed task from tracking
    if account_id in self._account_tasks:
        del self._account_tasks[account_id]
```

#### Step 1.4: Update main.py to Pass TaskMonitor

**File**: `app/main.py`

**Location**: Where MultiAccountTickerLoop is instantiated (around line 90-100)

```python
# BEFORE
ticker_loop = MultiAccountTickerLoop(
    settings=settings,
    registry=instrument_registry,
    subscription_store=subscription_store,
    publisher=redis_publisher,
)

# AFTER
ticker_loop = MultiAccountTickerLoop(
    settings=settings,
    registry=instrument_registry,
    subscription_store=subscription_store,
    publisher=redis_publisher,
    task_monitor=app.state.task_monitor,  # NEW: Pass task monitor
)
```

### Testing Steps

1. **Unit Test**: TaskMonitor captures exceptions

```python
# tests/unit/test_task_monitor.py
import asyncio
import pytest
from app.utils.task_monitor import TaskMonitor


@pytest.mark.asyncio
async def test_task_monitor_captures_exception():
    """Test that TaskMonitor captures and logs unhandled exceptions"""

    async def failing_task():
        await asyncio.sleep(0.1)
        raise ValueError("Test exception")

    monitor = TaskMonitor()

    task = monitor.create_monitored_task(
        failing_task(),
        task_name="test_failing_task"
    )

    # Wait for task to complete
    await asyncio.sleep(0.2)

    # Task should have completed (not hanging)
    assert task.done()
    # Exception should NOT propagate (handled by monitor)
    # Logs should contain the exception (check in integration test)
```

2. **Integration Test**: Inject failure in stream_account

```python
# tests/integration/test_ticker_loop_monitoring.py
import asyncio
import pytest
from app.generator import MultiAccountTickerLoop
from app.utils.task_monitor import TaskMonitor


@pytest.mark.asyncio
async def test_account_stream_failure_logged(mock_dependencies):
    """Test that account stream failures are captured and logged"""

    monitor = TaskMonitor()
    ticker_loop = MultiAccountTickerLoop(
        ...  # dependencies
        task_monitor=monitor
    )

    # Inject failure in KiteClient
    mock_client = mock_dependencies["kite_client"]
    mock_client.subscribe_tokens.side_effect = RuntimeError("Mock failure")

    await ticker_loop.start()
    await asyncio.sleep(1.0)

    # Check logs contain exception
    # Check account task was removed from _account_tasks
    assert "account_1" not in ticker_loop._account_tasks
```

### Rollback Plan

If issues arise:
1. Remove `task_monitor` parameter from MultiAccountTickerLoop
2. Revert to original `asyncio.create_task()` calls
3. Keep TaskMonitor utility for future use

### Verification Checklist

- [ ] TaskMonitor utility created and tested
- [ ] Global exception handler registered in lifespan
- [ ] MultiAccountTickerLoop accepts TaskMonitor parameter
- [ ] All background tasks use monitored_task wrapper
- [ ] Unit tests pass (test_task_monitor.py)
- [ ] Integration tests pass
- [ ] Logs show exceptions from failing tasks
- [ ] No performance regression (latency < 1ms overhead)

---

## IMPLEMENTATION PRIORITY 2: Bound Reload Queue

### Objective
Prevent unlimited concurrent subscription reloads that exhaust resources.

### Current Problem

```python
# app/generator.py:203-220
def reload_subscriptions_async(self) -> None:
    """Trigger a subscription reload (non-blocking)"""
    async def _reload():
        await self.reload_subscriptions()

    asyncio.create_task(_reload())  # NO QUEUE LIMIT!
```

Rapid API calls create unlimited concurrent reloads:
```bash
POST /subscriptions (token=1) → reload task #1 created
POST /subscriptions (token=2) → reload task #2 created
POST /subscriptions (token=3) → reload task #3 created
# ... 100 concurrent reloads running!
```

### Implementation Steps

#### Step 2.1: Create Subscription Reloader Utility

**File**: `app/utils/subscription_reloader.py` (NEW FILE)

```python
"""
Bounded subscription reloader with deduplication.
"""
import asyncio
import logging
import time
from typing import Callable, Coroutine, Optional

logger = logging.getLogger(__name__)


class SubscriptionReloader:
    """
    Manages subscription reload requests with:
    - Rate limiting (max 1 reload at a time)
    - Deduplication (coalesce multiple requests)
    - Debouncing (wait for burst of requests to complete)
    """

    def __init__(
        self,
        reload_fn: Callable[[], Coroutine],
        debounce_seconds: float = 1.0,
        max_reload_frequency_seconds: float = 5.0,
    ):
        """
        Args:
            reload_fn: Async function to call when reload triggered
            debounce_seconds: Wait this long after last trigger before reloading
            max_reload_frequency_seconds: Minimum time between reloads
        """
        self._reload_fn = reload_fn
        self._debounce_seconds = debounce_seconds
        self._max_reload_frequency = max_reload_frequency_seconds

        self._reload_semaphore = asyncio.Semaphore(1)  # Only 1 reload at a time
        self._reload_pending = asyncio.Event()
        self._reloader_task: Optional[asyncio.Task] = None
        self._running = False

        self._last_reload_time = 0.0
        self._pending_count = 0

    async def start(self):
        """Start the background reloader loop"""
        if self._running:
            logger.warning("SubscriptionReloader already running")
            return

        self._running = True
        self._reloader_task = asyncio.create_task(self._reloader_loop())
        logger.info("SubscriptionReloader started")

    async def stop(self):
        """Stop the background reloader loop"""
        self._running = False
        self._reload_pending.set()  # Wake up loop

        if self._reloader_task:
            await self._reloader_task

        logger.info("SubscriptionReloader stopped")

    def trigger_reload(self) -> None:
        """
        Request a subscription reload (non-blocking).

        Multiple rapid triggers will be coalesced into a single reload.
        """
        self._pending_count += 1
        self._reload_pending.set()
        logger.debug(f"Reload triggered (pending count: {self._pending_count})")

    async def _reloader_loop(self):
        """Background loop that processes reload requests"""
        while self._running:
            try:
                # Wait for reload request
                await self._reload_pending.wait()
                self._reload_pending.clear()

                if not self._running:
                    break

                # Debounce: Wait for burst of requests to complete
                await asyncio.sleep(self._debounce_seconds)

                # Check if minimum reload frequency has elapsed
                elapsed_since_last = time.time() - self._last_reload_time
                if elapsed_since_last < self._max_reload_frequency:
                    wait_time = self._max_reload_frequency - elapsed_since_last
                    logger.debug(f"Rate limiting: waiting {wait_time:.1f}s before reload")
                    await asyncio.sleep(wait_time)

                # Acquire semaphore (ensures only 1 reload at a time)
                async with self._reload_semaphore:
                    pending_count = self._pending_count
                    self._pending_count = 0

                    logger.info(f"Executing subscription reload (coalesced {pending_count} requests)")
                    start_time = time.time()

                    try:
                        await self._reload_fn()
                        duration = time.time() - start_time
                        logger.info(f"Subscription reload completed in {duration:.2f}s")
                    except Exception as exc:
                        logger.exception(f"Subscription reload failed: {exc}")

                    self._last_reload_time = time.time()

            except asyncio.CancelledError:
                logger.info("SubscriptionReloader loop cancelled")
                break
            except Exception as exc:
                logger.exception(f"Unexpected error in reloader loop: {exc}")
                await asyncio.sleep(1.0)  # Prevent tight loop on error
```

#### Step 2.2: Integrate SubscriptionReloader in MultiAccountTickerLoop

**File**: `app/generator.py`

**Location**: Constructor (around line 70-85)

```python
# BEFORE
def __init__(self, ...):
    # ... existing initialization ...

# AFTER
from app.utils.subscription_reloader import SubscriptionReloader

def __init__(
    self,
    settings: Settings,
    registry: InstrumentRegistry,
    subscription_store: SubscriptionStore,
    publisher: Optional[RedisPublisher] = None,
    task_monitor: Optional[TaskMonitor] = None,
):
    # ... existing initialization ...

    # NEW: Create bounded subscription reloader
    self._subscription_reloader = SubscriptionReloader(
        reload_fn=self._perform_reload,  # Separate method for actual reload
        debounce_seconds=1.0,  # Wait 1s after last trigger
        max_reload_frequency_seconds=5.0,  # Max 1 reload per 5 seconds
    )
```

**Location**: Lines 203-220 (reload_subscriptions_async)

```python
# BEFORE
def reload_subscriptions_async(self) -> None:
    """Trigger a subscription reload without blocking the caller"""
    async def _reload():
        await self.reload_subscriptions()

    asyncio.create_task(_reload())

# AFTER
def reload_subscriptions_async(self) -> None:
    """
    Trigger a subscription reload without blocking the caller.

    Multiple rapid calls will be coalesced into a single reload.
    """
    self._subscription_reloader.trigger_reload()
```

**Location**: Lines 221-303 (reload_subscriptions) - refactor into _perform_reload

```python
# BEFORE
async def reload_subscriptions(self) -> None:
    """Full implementation of reload logic"""
    # ... 80+ lines of code ...

# AFTER
async def _perform_reload(self) -> None:
    """
    Internal method: Perform actual subscription reload.

    Called by SubscriptionReloader, not directly.
    """
    # Move existing reload_subscriptions implementation here
    # ... (same 80+ lines, just renamed method)

async def reload_subscriptions(self) -> None:
    """
    Public API: Reload subscriptions immediately (blocking).

    For most use cases, prefer reload_subscriptions_async().
    """
    # Directly call the implementation (bypass SubscriptionReloader)
    await self._perform_reload()
```

#### Step 2.3: Start/Stop SubscriptionReloader in Lifecycle

**File**: `app/generator.py`

**Location**: start() and stop() methods

```python
# In start() method (after line 157)
async def start(self) -> None:
    # ... existing code ...

    # NEW: Start subscription reloader
    await self._subscription_reloader.start()

    # ... rest of existing code ...


# In stop() method (after line 195)
async def stop(self) -> None:
    # ... existing code ...

    # NEW: Stop subscription reloader
    await self._subscription_reloader.stop()

    # ... rest of existing code ...
```

### Testing Steps

1. **Unit Test**: Reloader coalesces multiple triggers

```python
# tests/unit/test_subscription_reloader.py
import asyncio
import pytest
from app.utils.subscription_reloader import SubscriptionReloader


@pytest.mark.asyncio
async def test_reloader_coalesces_requests():
    """Test that multiple rapid triggers are coalesced"""
    reload_count = 0

    async def mock_reload():
        nonlocal reload_count
        reload_count += 1
        await asyncio.sleep(0.1)

    reloader = SubscriptionReloader(
        reload_fn=mock_reload,
        debounce_seconds=0.2,
        max_reload_frequency_seconds=1.0,
    )

    await reloader.start()

    # Trigger 10 rapid reloads
    for _ in range(10):
        reloader.trigger_reload()
        await asyncio.sleep(0.01)

    # Wait for reloads to complete
    await asyncio.sleep(1.5)

    # Should have coalesced into 1-2 reloads max
    assert reload_count <= 2

    await reloader.stop()
```

2. **Integration Test**: API spam doesn't create 100 tasks

```python
# tests/integration/test_reload_queue_bounded.py
import asyncio
import pytest
from fastapi.testclient import TestClient


@pytest.mark.asyncio
async def test_rapid_subscriptions_bounded(client: TestClient):
    """Test that rapid subscription requests don't exhaust resources"""

    # Make 50 rapid subscription requests
    tasks = []
    for i in range(50):
        task = client.post("/subscriptions", json={"instrument_token": 256265 + i})
        tasks.append(task)

    # All should succeed (not timeout)
    responses = await asyncio.gather(*tasks)
    assert all(r.status_code in (200, 201) for r in responses)

    # Check that only 1-2 actual reloads happened (check logs)
    # This prevents resource exhaustion
```

### Rollback Plan

1. Revert `reload_subscriptions_async()` to original implementation
2. Keep SubscriptionReloader for future use

### Verification Checklist

- [ ] SubscriptionReloader utility created
- [ ] MultiAccountTickerLoop uses SubscriptionReloader
- [ ] Rapid triggers are coalesced (unit test)
- [ ] Max 1 reload at a time (semaphore enforced)
- [ ] API spam doesn't create unbounded tasks
- [ ] Performance: Debouncing doesn't delay critical reloads
- [ ] Logs show "coalesced N requests" messages

---

## IMPLEMENTATION PRIORITY 3: Fix Mock State Races

### Objective
Eliminate race conditions in mock data generation using immutable snapshots.

### Current Problem

**File**: `app/generator.py:313-361`

```python
# Double-check locking (anti-pattern)
if self._mock_underlying_state is not None:
    return  # Quick check WITHOUT lock

async with self._mock_seed_lock:
    if self._mock_underlying_state is not None:
        return  # Check again AFTER lock
    # Initialize state - but race condition exists!
    self._mock_underlying_state = MockUnderlyingState(...)
```

**Race Timeline**:
```
Thread A: Check state is None (line 313) → True
Thread B: Check state is None (line 313) → True (RACE!)
Thread A: Acquire lock, initialize state
Thread B: Acquire lock, RE-INITIALIZE state (overwrites A)
```

### Implementation Steps

#### Step 3.1: Make MockUnderlyingState Immutable

**File**: `app/generator.py`

**Location**: Around lines 36-45 (MockUnderlyingState dataclass)

```python
# BEFORE
@dataclass
class MockUnderlyingState:
    symbol: str
    last_close: float
    base_volume: int
    bar_start_minute: int
    bar_duration: int
    simulated_ohlc_ts: int

# AFTER
from dataclasses import dataclass, field

@dataclass(frozen=True)  # Make immutable
class MockUnderlyingSnapshot:
    """Immutable snapshot of underlying mock state (thread-safe)"""
    symbol: str
    last_close: float
    base_volume: int
    timestamp: float  # When this snapshot was created
    bar_start_minute: int
    bar_duration: int
    simulated_ohlc_ts: int


# Keep mutable internal state (not exposed)
@dataclass
class _MockUnderlyingBuilder:
    """Internal builder for mock state (not thread-safe, use under lock)"""
    symbol: str
    last_close: float
    base_volume: int
    bar_start_minute: int
    bar_duration: int
    simulated_ohlc_ts: int

    def build_snapshot(self) -> MockUnderlyingSnapshot:
        """Create immutable snapshot of current state"""
        return MockUnderlyingSnapshot(
            symbol=self.symbol,
            last_close=self.last_close,
            base_volume=self.base_volume,
            timestamp=time.time(),
            bar_start_minute=self.bar_start_minute,
            bar_duration=self.bar_duration,
            simulated_ohlc_ts=self.simulated_ohlc_ts,
        )
```

#### Step 3.2: Update _ensure_mock_underlying_seed

**File**: `app/generator.py`

**Location**: Lines 313-361

```python
# BEFORE
async def _ensure_mock_underlying_seed(self):
    if self._mock_underlying_state is not None:
        return

    async with self._mock_seed_lock:
        if self._mock_underlying_state is not None:
            return
        # ... initialize mutable state ...

# AFTER
class MultiAccountTickerLoop:
    def __init__(self, ...):
        # Store BUILDER internally (mutable, protected by lock)
        self._mock_underlying_builder: Optional[_MockUnderlyingBuilder] = None
        # Expose SNAPSHOT publicly (immutable, safe to read anytime)
        self._mock_underlying_snapshot: Optional[MockUnderlyingSnapshot] = None
        self._mock_seed_lock = asyncio.Lock()

    async def _ensure_mock_underlying_seed(self):
        """Ensure mock underlying state is seeded (creates immutable snapshot)"""
        # Quick check WITHOUT lock (safe because snapshot is immutable)
        if self._mock_underlying_snapshot is not None:
            return

        # Need to initialize
        async with self._mock_seed_lock:
            # Double-check after acquiring lock
            if self._mock_underlying_snapshot is not None:
                return  # Another thread initialized while we waited

            logger.info("Seeding mock underlying state...")
            now = int(time.time())
            from_ts = now - settings.mock_history_minutes * 60

            # Fetch historical data
            candles = await self._fetch_underlying_candles(
                underlying_symbol=settings.nifty_quote_symbol,
                from_ts=from_ts,
                to_ts=now,
                interval="minute"
            )

            if not candles:
                logger.warning("No historical candles available for mock seed")
                return

            last_candle = candles[-1]
            close_price = last_candle["close"]

            # Create BUILDER (mutable, only used under lock)
            self._mock_underlying_builder = _MockUnderlyingBuilder(
                symbol=settings.nifty_quote_symbol,
                last_close=close_price,
                base_volume=int(last_candle.get("volume", 1000)),
                bar_start_minute=int(time.time() // 60),
                bar_duration=settings.stream_interval_seconds,
                simulated_ohlc_ts=now,
            )

            # Create immutable SNAPSHOT for consumers
            self._mock_underlying_snapshot = self._mock_underlying_builder.build_snapshot()
            logger.info(f"Mock underlying seeded: {self._mock_underlying_snapshot}")
```

#### Step 3.3: Update _generate_mock_underlying_bar to Use Snapshot

**File**: `app/generator.py`

**Location**: Lines 362-394

```python
# BEFORE
async def _generate_mock_underlying_bar(self) -> Dict[str, Any]:
    state = self._mock_underlying_state  # Mutable! Race condition!
    if state is None:
        return {}
    # ... mutate state.last_close, state.base_volume ...

# AFTER
async def _generate_mock_underlying_bar(self) -> Dict[str, Any]:
    """Generate mock underlying bar using immutable snapshot"""

    # Read snapshot (NO LOCK NEEDED - immutable!)
    snapshot = self._mock_underlying_snapshot
    if snapshot is None:
        return {}

    # Generate new values based on snapshot (don't mutate snapshot!)
    variation_bps = settings.mock_price_variation_bps / 10000.0
    price_delta = snapshot.last_close * random.uniform(-variation_bps, variation_bps)
    new_price = max(snapshot.last_close + price_delta, 0.01)

    volume_variation = random.uniform(0.9, 1.1)
    volume = int(snapshot.base_volume * volume_variation)

    now_ts = int(time.time())

    bar = {
        "date": now_ts,
        "open": snapshot.last_close,
        "high": max(snapshot.last_close, new_price),
        "low": min(snapshot.last_close, new_price),
        "close": new_price,
        "volume": volume,
    }

    # Update builder UNDER LOCK, then create new snapshot
    async with self._mock_seed_lock:
        if self._mock_underlying_builder:
            # Mutate builder (safe - we have lock)
            self._mock_underlying_builder.last_close = new_price
            self._mock_underlying_builder.base_volume = volume
            self._mock_underlying_builder.simulated_ohlc_ts = now_ts

            # Create NEW immutable snapshot
            self._mock_underlying_snapshot = self._mock_underlying_builder.build_snapshot()

    return bar
```

#### Step 3.4: Apply Same Pattern to MockOptionState

**File**: `app/generator.py`

**Location**: Lines 46-62 (MockOptionState dataclass)

```python
# BEFORE
@dataclass
class MockOptionState:
    instrument: Instrument
    seed_price: float
    last_price: float
    seed_volume: int
    seed_oi: int
    # ... other mutable fields ...

# AFTER
@dataclass(frozen=True)  # Immutable
class MockOptionSnapshot:
    """Immutable snapshot of option mock state"""
    instrument: Instrument
    timestamp: float
    last_price: float
    volume: int
    oi: int
    # ... other fields (all immutable) ...


@dataclass
class _MockOptionBuilder:
    """Internal builder for option mock state"""
    instrument: Instrument
    seed_price: float
    last_price: float
    seed_volume: int
    seed_oi: int
    # ... other mutable fields ...

    def build_snapshot(self) -> MockOptionSnapshot:
        """Create immutable snapshot"""
        return MockOptionSnapshot(
            instrument=self.instrument,
            timestamp=time.time(),
            last_price=self.last_price,
            volume=self.seed_volume,
            oi=self.seed_oi,
            # ... other fields ...
        )
```

**Location**: Lines 88-90 (option state dictionary)

```python
# BEFORE
self._mock_option_state: Dict[int, MockOptionState] = {}

# AFTER
# Internal builders (mutable, use under lock)
self._mock_option_builders: Dict[int, _MockOptionBuilder] = {}
# Public snapshots (immutable, safe to read anytime)
self._mock_option_snapshots: Dict[int, MockOptionSnapshot] = {}
```

**Location**: Lines 395-408 (_ensure_mock_option_seed)

```python
# BEFORE
async def _ensure_mock_option_seed(self, client: KiteClient, instruments: Iterable[Instrument]):
    missing = [inst for inst in instruments if inst.instrument_token not in self._mock_option_state]
    # ... seed and add to _mock_option_state ...

# AFTER
async def _ensure_mock_option_seed(self, client: KiteClient, instruments: Iterable[Instrument]):
    """Ensure mock option state is seeded for all instruments"""
    missing = [inst for inst in instruments if inst.instrument_token not in self._mock_option_snapshots]
    if not missing:
        return

    async with self._mock_seed_lock:
        # Double-check after lock
        still_missing = [inst for inst in missing if inst.instrument_token not in self._mock_option_snapshots]

        for instrument in still_missing:
            # Seed builder (mutable, under lock)
            builder = await self._seed_option_builder(client, instrument)
            if builder:
                self._mock_option_builders[instrument.instrument_token] = builder
                # Create immutable snapshot
                self._mock_option_snapshots[instrument.instrument_token] = builder.build_snapshot()
```

**Location**: Lines 528-551 (_generate_mock_option_snapshot)

```python
# BEFORE
async def _generate_mock_option_snapshot(self, token: int) -> Optional[OptionSnapshot]:
    state = self._mock_option_state.get(token)  # Mutable!
    if not state:
        return None
    # ... mutate state ...

# AFTER
async def _generate_mock_option_snapshot(self, token: int) -> Optional[OptionSnapshot]:
    """Generate mock option snapshot from immutable state"""

    # Read snapshot (NO LOCK - immutable!)
    snapshot = self._mock_option_snapshots.get(token)
    if not snapshot:
        return None

    # Generate new values based on snapshot
    variation_bps = settings.mock_price_variation_bps / 10000.0
    price_delta = snapshot.last_price * random.uniform(-variation_bps, variation_bps)
    new_price = max(snapshot.last_price + price_delta, 0.01)

    # ... generate other fields ...

    # Update builder UNDER LOCK
    async with self._mock_seed_lock:
        builder = self._mock_option_builders.get(token)
        if builder:
            builder.last_price = new_price
            builder.seed_volume = new_volume
            builder.seed_oi = new_oi
            # Create new snapshot
            self._mock_option_snapshots[token] = builder.build_snapshot()

    return option_snapshot
```

### Testing Steps

1. **Unit Test**: Concurrent reads don't see torn data

```python
# tests/unit/test_mock_state_concurrency.py
import asyncio
import pytest
from app.generator import MultiAccountTickerLoop


@pytest.mark.asyncio
async def test_mock_state_concurrent_access():
    """Test that concurrent mock state access is thread-safe"""

    ticker_loop = MultiAccountTickerLoop(...)

    async def reader():
        """Read mock state concurrently"""
        for _ in range(100):
            snapshot = ticker_loop._mock_underlying_snapshot
            if snapshot:
                # Verify snapshot is consistent (immutable)
                assert snapshot.last_close > 0
                assert snapshot.base_volume > 0
            await asyncio.sleep(0.001)

    async def writer():
        """Generate mock bars concurrently"""
        for _ in range(100):
            await ticker_loop._generate_mock_underlying_bar()
            await asyncio.sleep(0.001)

    # Run readers and writers concurrently
    await asyncio.gather(
        reader(), reader(), reader(),  # 3 readers
        writer(), writer()  # 2 writers
    )

    # No exceptions = success!
```

2. **Integration Test**: Mock data during market transition

```python
# tests/integration/test_mock_transition.py
@pytest.mark.asyncio
async def test_market_hours_transition_mock_data():
    """Test mock data generation during market hours transition"""

    # Set market close time to NOW + 30 seconds
    settings.market_close_time = (datetime.now() + timedelta(seconds=30)).time()

    ticker_loop = MultiAccountTickerLoop(...)
    await ticker_loop.start()

    # Wait for transition
    await asyncio.sleep(35)

    # Verify mock data is being generated
    snapshot = ticker_loop._mock_underlying_snapshot
    assert snapshot is not None
    assert snapshot.last_close > 0

    await ticker_loop.stop()
```

### Rollback Plan

1. Revert to mutable `MockUnderlyingState` and `MockOptionState`
2. Keep lock-based approach (less safe but functional)

### Verification Checklist

- [ ] MockUnderlyingSnapshot is frozen (immutable)
- [ ] MockOptionSnapshot is frozen (immutable)
- [ ] Builders are only mutated under lock
- [ ] Snapshots can be read without lock
- [ ] Concurrent access test passes
- [ ] Mock data quality unchanged
- [ ] No performance regression

---

## IMPLEMENTATION PRIORITY 4: Add Redis Circuit Breaker

### Objective
Implement circuit breaker pattern for Redis publishing to prevent cascading failures.

### Current Problem

**File**: `app/redis_client.py:43-62`

```python
async def publish(self, channel: str, message: str) -> None:
    for attempt in (1, 2):
        try:
            await self._client.publish(channel, message)
            return
        except (RedisConnectionError, RedisTimeoutError):
            await self._reset()
    raise RuntimeError("Failed after retries")  # BLOCKS until fixed!
```

If Redis is down, ALL ticks fail and streaming stops.

### Implementation Steps

#### Step 4.1: Create CircuitBreaker Utility

**File**: `app/utils/circuit_breaker.py` (NEW FILE)

```python
"""
Circuit breaker pattern implementation.
"""
import asyncio
import enum
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)


class CircuitState(enum.Enum):
    """Circuit breaker states"""
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing - reject requests
    HALF_OPEN = "half_open"  # Testing if recovered


class CircuitBreaker:
    """
    Circuit breaker for protecting against cascading failures.

    States:
    - CLOSED: Normal operation, allow requests
    - OPEN: Too many failures, reject requests immediately
    - HALF_OPEN: Testing recovery, allow limited requests
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout_seconds: float = 60.0,
        half_open_max_attempts: int = 3,
        name: str = "circuit_breaker",
    ):
        """
        Args:
            failure_threshold: Number of failures before opening circuit
            recovery_timeout_seconds: How long to wait before testing recovery
            half_open_max_attempts: Number of test attempts in HALF_OPEN state
            name: Human-readable name for logging
        """
        self.name = name
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout_seconds
        self._half_open_max_attempts = half_open_max_attempts

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time = 0.0
        self._half_open_attempts = 0

        self._lock = asyncio.Lock()

        logger.info(
            f"CircuitBreaker '{name}' initialized: "
            f"threshold={failure_threshold}, timeout={recovery_timeout_seconds}s"
        )

    async def can_execute(self) -> bool:
        """Check if circuit allows execution"""
        async with self._lock:
            if self._state == CircuitState.CLOSED:
                return True

            if self._state == CircuitState.OPEN:
                # Check if recovery timeout has elapsed
                elapsed = time.time() - self._last_failure_time
                if elapsed >= self._recovery_timeout:
                    logger.info(f"CircuitBreaker '{self.name}' entering HALF_OPEN state")
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_attempts = 0
                    return True

                # Still in timeout, reject
                return False

            if self._state == CircuitState.HALF_OPEN:
                # Allow limited attempts
                if self._half_open_attempts < self._half_open_max_attempts:
                    return True
                return False

        return False

    async def record_success(self) -> None:
        """Record a successful execution"""
        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                # Success in HALF_OPEN -> back to CLOSED
                logger.info(f"CircuitBreaker '{self.name}' recovered, state -> CLOSED")
                self._state = CircuitState.CLOSED
                self._failure_count = 0
                self._half_open_attempts = 0

            elif self._state == CircuitState.CLOSED:
                # Reset failure count on success
                self._failure_count = 0

    async def record_failure(self, error: Optional[Exception] = None) -> None:
        """Record a failed execution"""
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()

            if self._state == CircuitState.HALF_OPEN:
                # Failure in HALF_OPEN -> back to OPEN
                self._half_open_attempts += 1
                if self._half_open_attempts >= self._half_open_max_attempts:
                    logger.warning(
                        f"CircuitBreaker '{self.name}' failed recovery, state -> OPEN"
                    )
                    self._state = CircuitState.OPEN

            elif self._state == CircuitState.CLOSED:
                # Check if threshold exceeded
                if self._failure_count >= self._failure_threshold:
                    logger.error(
                        f"CircuitBreaker '{self.name}' OPENED "
                        f"({self._failure_count} failures, error: {error})"
                    )
                    self._state = CircuitState.OPEN

    def get_state(self) -> CircuitState:
        """Get current circuit state"""
        return self._state

    def get_failure_count(self) -> int:
        """Get current failure count"""
        return self._failure_count
```

#### Step 4.2: Integrate CircuitBreaker in RedisPublisher

**File**: `app/redis_client.py`

**Location**: Constructor and publish method

```python
# BEFORE
class RedisPublisher:
    def __init__(self, url: str):
        self._url = url
        self._client: Optional[redis.Redis] = None

# AFTER
from app.utils.circuit_breaker import CircuitBreaker, CircuitState

class RedisPublisher:
    def __init__(self, url: str):
        self._url = url
        self._client: Optional[redis.Redis] = None

        # NEW: Add circuit breaker
        self._circuit_breaker = CircuitBreaker(
            failure_threshold=10,  # Open after 10 failures
            recovery_timeout_seconds=60.0,  # Test recovery after 60s
            half_open_max_attempts=3,  # Allow 3 test attempts
            name="redis_publisher"
        )

        # Track metrics
        self._total_publish_attempts = 0
        self._total_publish_failures = 0
        self._total_drops_circuit_open = 0
```

**Location**: publish() method (lines 43-62)

```python
# BEFORE
async def publish(self, channel: str, message: str) -> None:
    for attempt in (1, 2):
        try:
            await self._client.publish(channel, message)
            return
        except (RedisConnectionError, RedisTimeoutError):
            await self._reset()
    raise RuntimeError("Failed after retries")

# AFTER
async def publish(self, channel: str, message: str) -> None:
    """
    Publish message to Redis channel with circuit breaker protection.

    If circuit is OPEN, message is dropped (logged) instead of blocking.
    """
    self._total_publish_attempts += 1

    # Check circuit breaker state
    if not await self._circuit_breaker.can_execute():
        self._total_drops_circuit_open += 1

        # Log periodically (not every drop)
        if self._total_drops_circuit_open % 100 == 1:
            logger.warning(
                f"Redis circuit OPEN, dropping messages "
                f"({self._total_drops_circuit_open} drops so far)"
            )

        # Drop message gracefully (don't block streaming)
        return

    # Attempt publish with retries
    for attempt in (1, 2):
        try:
            if self._client is None:
                await self._connect()

            await self._client.publish(channel, message)

            # SUCCESS - record in circuit breaker
            await self._circuit_breaker.record_success()
            return

        except (RedisConnectionError, RedisTimeoutError) as exc:
            logger.warning(
                f"Redis publish failed (attempt {attempt}/2): {exc}",
                extra={"channel": channel, "error": str(exc)}
            )
            await self._reset()

            if attempt == 2:
                # FINAL FAILURE - record in circuit breaker
                self._total_publish_failures += 1
                await self._circuit_breaker.record_failure(exc)

                logger.error(
                    f"Redis publish failed after retries, circuit may open "
                    f"(failures: {self._circuit_breaker.get_failure_count()}/{self._circuit_breaker._failure_threshold})"
                )

                # Don't raise - let caller continue (graceful degradation)
                return

        except Exception as exc:
            # Unexpected error - record and propagate
            logger.exception(f"Unexpected Redis error: {exc}")
            await self._circuit_breaker.record_failure(exc)
            raise
```

#### Step 4.3: Add Prometheus Metrics for Circuit Breaker

**File**: `app/redis_client.py`

**Location**: Add metrics to class

```python
from prometheus_client import Counter, Gauge

# Module-level metrics
redis_publish_total = Counter(
    "redis_publish_total",
    "Total Redis publish attempts"
)
redis_publish_failures = Counter(
    "redis_publish_failures",
    "Total Redis publish failures"
)
redis_circuit_open_drops = Counter(
    "redis_circuit_open_drops",
    "Messages dropped due to circuit breaker OPEN"
)
redis_circuit_state = Gauge(
    "redis_circuit_state",
    "Redis circuit breaker state (0=closed, 1=open, 2=half_open)"
)


class RedisPublisher:
    async def publish(self, channel: str, message: str) -> None:
        redis_publish_total.inc()

        if not await self._circuit_breaker.can_execute():
            redis_circuit_open_drops.inc()
            # ... drop message ...

        # ... attempt publish ...

        except ... as exc:
            redis_publish_failures.inc()
            # ... handle failure ...

    def get_metrics(self) -> dict:
        """Return circuit breaker metrics for monitoring"""
        state = self._circuit_breaker.get_state()
        state_value = {
            CircuitState.CLOSED: 0,
            CircuitState.OPEN: 1,
            CircuitState.HALF_OPEN: 2,
        }.get(state, -1)

        redis_circuit_state.set(state_value)

        return {
            "circuit_state": state.value,
            "failure_count": self._circuit_breaker.get_failure_count(),
            "total_attempts": self._total_publish_attempts,
            "total_failures": self._total_publish_failures,
            "total_drops": self._total_drops_circuit_open,
        }
```

#### Step 4.4: Add Health Check for Redis Circuit

**File**: `app/main.py`

**Location**: /health endpoint (around line 420-450)

```python
# BEFORE
@app.get("/health", tags=["meta"])
async def health():
    # ... existing checks ...
    return {
        "status": "ok",
        # ... existing fields ...
    }

# AFTER
@app.get("/health", tags=["meta"])
async def health():
    # ... existing checks ...

    # NEW: Add Redis circuit breaker status
    redis_metrics = redis_publisher.get_metrics() if redis_publisher else {}

    return {
        "status": "ok",
        # ... existing fields ...
        "redis": {
            "connected": redis_publisher._client is not None if redis_publisher else False,
            "circuit_state": redis_metrics.get("circuit_state", "unknown"),
            "failure_count": redis_metrics.get("failure_count", 0),
            "total_drops": redis_metrics.get("total_drops", 0),
        }
    }
```

### Testing Steps

1. **Unit Test**: Circuit breaker state transitions

```python
# tests/unit/test_circuit_breaker.py
import pytest
from app.utils.circuit_breaker import CircuitBreaker, CircuitState


@pytest.mark.asyncio
async def test_circuit_breaker_opens_after_threshold():
    """Test that circuit opens after failure threshold"""

    breaker = CircuitBreaker(
        failure_threshold=3,
        recovery_timeout_seconds=1.0,
        name="test"
    )

    # Initially CLOSED
    assert breaker.get_state() == CircuitState.CLOSED
    assert await breaker.can_execute()

    # Record 3 failures
    for _ in range(3):
        await breaker.record_failure()

    # Should be OPEN now
    assert breaker.get_state() == CircuitState.OPEN
    assert not await breaker.can_execute()


@pytest.mark.asyncio
async def test_circuit_breaker_recovers():
    """Test that circuit attempts recovery after timeout"""

    breaker = CircuitBreaker(
        failure_threshold=2,
        recovery_timeout_seconds=0.1,  # Short timeout for testing
        name="test"
    )

    # Force OPEN
    await breaker.record_failure()
    await breaker.record_failure()
    assert breaker.get_state() == CircuitState.OPEN

    # Wait for recovery timeout
    await asyncio.sleep(0.15)

    # Should allow HALF_OPEN attempt
    assert await breaker.can_execute()

    # Record success -> back to CLOSED
    await breaker.record_success()
    assert breaker.get_state() == CircuitState.CLOSED
```

2. **Integration Test**: Redis failure triggers circuit

```python
# tests/integration/test_redis_circuit_breaker.py
import pytest
from app.redis_client import RedisPublisher


@pytest.mark.asyncio
async def test_redis_circuit_opens_on_failure():
    """Test that Redis circuit opens after failures"""

    # Create publisher with invalid URL
    publisher = RedisPublisher(url="redis://invalid-host:6379")

    # Attempt to publish (will fail)
    for _ in range(10):
        await publisher.publish("test_channel", "test_message")

    # Circuit should be OPEN
    metrics = publisher.get_metrics()
    assert metrics["circuit_state"] == "open"
    assert metrics["total_drops"] > 0  # Messages dropped
```

### Rollback Plan

1. Remove circuit breaker from RedisPublisher
2. Revert to original retry logic
3. Keep CircuitBreaker utility for future use

### Verification Checklist

- [ ] CircuitBreaker utility created and tested
- [ ] RedisPublisher integrates circuit breaker
- [ ] Circuit opens after 10 failures
- [ ] Circuit attempts recovery after 60s
- [ ] Messages dropped (not blocking) when circuit open
- [ ] Prometheus metrics track circuit state
- [ ] Health endpoint shows circuit status
- [ ] Logs indicate when circuit opens/closes

---

## IMPLEMENTATION PRIORITY 5: Fix Memory Leak in Mock State

### Objective
Prevent unbounded growth of mock state dictionaries by implementing LRU eviction and expiry cleanup.

### Current Problem

**File**: `app/generator.py:88-90, 395-408`

Mock state dictionaries grow unbounded:
- After 1 month: ~5,000 contracts = 1MB
- After 1 year: ~60,000 contracts = 12MB+ memory leak

### Implementation Steps

#### Step 5.1: Add LRU Eviction to Mock Option State

**File**: `app/generator.py`

**Location**: Around line 88-90

```python
# BEFORE
self._mock_option_state: Dict[int, MockOptionState] = {}

# AFTER
from collections import OrderedDict

self._mock_option_state_max_size = 5000  # Configurable limit
self._mock_option_state: OrderedDict[int, MockOptionState] = OrderedDict()
```

**Location**: _ensure_mock_option_seed method (lines 395-408)

```python
# BEFORE
async def _ensure_mock_option_seed(self, client: KiteClient, instruments: Iterable[Instrument]):
    missing = [inst for inst in instruments if inst.instrument_token not in self._mock_option_state]
    # ... seed new instruments ...
    self._mock_option_state[instrument.instrument_token] = state

# AFTER
async def _ensure_mock_option_seed(self, client: KiteClient, instruments: Iterable[Instrument]):
    missing = [inst for inst in instruments if inst.instrument_token not in self._mock_option_state]
    if not missing:
        return

    now = int(time.time())
    from_ts = now - settings.mock_history_minutes * 60
    today_market = self._now_market().date()

    async with self._mock_seed_lock:
        # STEP 1: Cleanup expired options FIRST (before adding new)
        expired_tokens = []
        for token, state in list(self._mock_option_state.items()):
            if state.instrument.expiry and state.instrument.expiry < today_market:
                expired_tokens.append(token)

        for token in expired_tokens:
            del self._mock_option_state[token]

        if expired_tokens:
            logger.info(f"Removed {len(expired_tokens)} expired mock option states")

        # STEP 2: Enforce max size using LRU eviction
        while len(self._mock_option_state) >= self._mock_option_state_max_size:
            evicted_token, evicted_state = self._mock_option_state.popitem(last=False)  # Remove oldest
            logger.debug(
                f"Evicted LRU mock state for token {evicted_token} "
                f"(symbol: {evicted_state.instrument.tradingsymbol})"
            )

        # STEP 3: Now seed new instruments
        still_missing = [inst for inst in missing if inst.instrument_token not in self._mock_option_state]

        for instrument in still_missing:
            state = await self._seed_option_state(client, instrument, from_ts, now)
            if state:
                # Add to END (most recently used)
                self._mock_option_state[instrument.instrument_token] = state
```

#### Step 5.2: Add Background Cleanup Task

**File**: `app/generator.py`

**Location**: Add new method and background task

```python
class MultiAccountTickerLoop:
    def __init__(self, ...):
        # ... existing initialization ...

        # NEW: Track cleanup task
        self._cleanup_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        # ... existing start code ...

        # NEW: Start background cleanup task
        if self._task_monitor:
            self._cleanup_task = self._task_monitor.create_monitored_task(
                self._mock_state_cleanup_loop(),
                task_name="mock_state_cleanup",
            )
        else:
            self._cleanup_task = asyncio.create_task(self._mock_state_cleanup_loop())

    async def stop(self) -> None:
        # ... existing stop code ...

        # NEW: Stop cleanup task
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

    async def _mock_state_cleanup_loop(self):
        """
        Background task: Periodically cleanup expired mock state.

        Runs every 5 minutes, removes expired options.
        """
        logger.info("Mock state cleanup loop started")

        while self._running and not self._stop_event.is_set():
            try:
                # Wait 5 minutes between cleanups
                await asyncio.sleep(300)

                if not self._running:
                    break

                # Cleanup expired options
                await self._cleanup_expired_mock_state()

            except asyncio.CancelledError:
                logger.info("Mock state cleanup loop cancelled")
                break
            except Exception as exc:
                logger.exception(f"Error in mock state cleanup loop: {exc}")
                await asyncio.sleep(60)  # Retry after 1 minute

        logger.info("Mock state cleanup loop stopped")

    async def _cleanup_expired_mock_state(self):
        """Remove expired mock state entries"""
        today_market = self._now_market().date()

        async with self._mock_seed_lock:
            # Cleanup expired options
            expired_option_tokens = []
            for token, state in list(self._mock_option_state.items()):
                if state.instrument.expiry and state.instrument.expiry < today_market:
                    expired_option_tokens.append(token)

            for token in expired_option_tokens:
                del self._mock_option_state[token]

            if expired_option_tokens:
                logger.info(
                    f"Cleaned up {len(expired_option_tokens)} expired mock option states, "
                    f"remaining: {len(self._mock_option_state)}"
                )

            # Log current size
            if len(self._mock_option_state) > 0:
                logger.debug(
                    f"Mock state size: {len(self._mock_option_state)} options "
                    f"(max: {self._mock_option_state_max_size})"
                )
```

#### Step 5.3: Add Configuration for Max Size

**File**: `app/config.py`

**Location**: Add new settings field

```python
class Settings(BaseSettings):
    # ... existing fields ...

    # NEW: Mock state management
    mock_state_max_size: int = Field(
        default=5000,
        description="Maximum number of instruments in mock state cache (LRU eviction)",
    )
    mock_state_cleanup_interval_seconds: int = Field(
        default=300,
        description="Interval for background cleanup of expired mock state (seconds)",
    )
```

**File**: `app/generator.py`

**Location**: Update to use config

```python
# In __init__
self._mock_option_state_max_size = settings.mock_state_max_size
```

### Testing Steps

1. **Unit Test**: LRU eviction works

```python
# tests/unit/test_mock_state_eviction.py
import pytest
from collections import OrderedDict
from app.generator import MultiAccountTickerLoop


@pytest.mark.asyncio
async def test_mock_state_lru_eviction():
    """Test that mock state evicts oldest entries when full"""

    ticker_loop = MultiAccountTickerLoop(...)
    ticker_loop._mock_option_state_max_size = 10  # Small size for testing

    # Seed 15 instruments (exceeds limit)
    instruments = [mock_instrument(token=i) for i in range(15)]
    await ticker_loop._ensure_mock_option_seed(mock_client, instruments)

    # Should have evicted 5 oldest, keeping 10 newest
    assert len(ticker_loop._mock_option_state) == 10

    # Oldest (0-4) should be evicted
    assert 0 not in ticker_loop._mock_option_state
    assert 4 not in ticker_loop._mock_option_state

    # Newest (5-14) should be present
    assert 5 in ticker_loop._mock_option_state
    assert 14 in ticker_loop._mock_option_state
```

2. **Integration Test**: Expired options cleaned up

```python
# tests/integration/test_mock_cleanup.py
@pytest.mark.asyncio
async def test_expired_options_cleanup():
    """Test that expired options are removed from mock state"""

    ticker_loop = MultiAccountTickerLoop(...)

    # Create expired option (expiry = yesterday)
    yesterday = (datetime.now() - timedelta(days=1)).date()
    expired_instrument = Instrument(
        instrument_token=12345,
        tradingsymbol="NIFTY2410018000CE",
        expiry=yesterday,  # Expired!
        ...
    )

    # Seed it
    await ticker_loop._ensure_mock_option_seed(mock_client, [expired_instrument])
    assert 12345 in ticker_loop._mock_option_state

    # Run cleanup
    await ticker_loop._cleanup_expired_mock_state()

    # Should be removed
    assert 12345 not in ticker_loop._mock_option_state
```

3. **Load Test**: Memory usage doesn't grow unbounded

```python
# tests/load/test_mock_memory_leak.py
import psutil
import os


@pytest.mark.asyncio
async def test_mock_state_memory_usage():
    """Test that memory usage plateaus (no leak)"""

    process = psutil.Process(os.getpid())
    initial_memory = process.memory_info().rss / 1024 / 1024  # MB

    ticker_loop = MultiAccountTickerLoop(...)
    await ticker_loop.start()

    # Simulate 1000 option seeds (should trigger eviction)
    for i in range(1000):
        instruments = [mock_instrument(token=i * 1000 + j) for j in range(10)]
        await ticker_loop._ensure_mock_option_seed(mock_client, instruments)

    final_memory = process.memory_info().rss / 1024 / 1024  # MB
    memory_growth = final_memory - initial_memory

    # Memory should grow by < 50MB (not unbounded)
    assert memory_growth < 50, f"Memory grew by {memory_growth}MB (potential leak)"

    await ticker_loop.stop()
```

### Rollback Plan

1. Revert OrderedDict to regular Dict
2. Remove cleanup task
3. Keep configuration for future use

### Verification Checklist

- [ ] OrderedDict used for mock state
- [ ] LRU eviction when max_size exceeded
- [ ] Expired options cleaned up every 5 minutes
- [ ] Background cleanup task registered
- [ ] Configuration added for max_size
- [ ] Unit tests pass (eviction works)
- [ ] Integration tests pass (cleanup works)
- [ ] Load test confirms no memory leak
- [ ] Logs show cleanup activity

---

## TESTING STRATEGY

### Unit Tests

**Location**: `tests/unit/`

**New Test Files**:
1. `test_task_monitor.py` - Task exception handling
2. `test_subscription_reloader.py` - Reload queue management
3. `test_mock_state_concurrency.py` - Mock state thread safety
4. `test_circuit_breaker.py` - Circuit breaker state machine
5. `test_mock_state_eviction.py` - LRU eviction logic

**Coverage Target**: 90%+ for new code

### Integration Tests

**Location**: `tests/integration/`

**New Test Files**:
1. `test_ticker_loop_monitoring.py` - End-to-end task monitoring
2. `test_reload_queue_bounded.py` - API spam handling
3. `test_mock_transition.py` - Market hours transitions
4. `test_redis_circuit_breaker.py` - Redis failure scenarios
5. `test_mock_cleanup.py` - Cleanup task verification

**Scenarios**:
- Task failures are logged and recovered
- Rapid API calls don't exhaust resources
- Mock data quality during transitions
- Graceful degradation when Redis down
- Memory usage plateaus over time

### Regression Tests

**Existing Tests**: All existing tests MUST pass

**Command**:
```bash
pytest tests/ -v --cov=app --cov-report=html
```

**Acceptance Criteria**:
- 100% of existing tests pass
- No performance regression (< 5% slower)
- No functional changes (behavior identical)

### Manual Testing

**Checklist**:
- [ ] Start service in dev environment
- [ ] Subscribe to 100+ instruments
- [ ] Monitor logs for task exceptions
- [ ] Trigger rapid subscription changes
- [ ] Verify mock data during market hours transition
- [ ] Simulate Redis outage (stop Redis container)
- [ ] Check health endpoint shows circuit status
- [ ] Monitor memory usage over 1 hour
- [ ] Verify Prometheus metrics

---

## DEPLOYMENT PLAN

### Pre-Deployment Checklist

- [ ] All Phase 1 implementations complete
- [ ] All unit tests pass (90%+ coverage)
- [ ] All integration tests pass
- [ ] All regression tests pass
- [ ] Manual testing completed
- [ ] Documentation updated
- [ ] Rollback plan documented
- [ ] Monitoring alerts configured

### Deployment Steps

#### Step 1: Deploy to Dev Environment

```bash
# 1. Pull latest code
git pull origin feature/phase1-improvements

# 2. Run tests
pytest tests/ -v --cov=app

# 3. Build Docker image
docker build -t ticker-service:phase1 .

# 4. Deploy to dev
docker-compose -f docker-compose.dev.yml up -d

# 5. Monitor logs
docker logs -f ticker-service

# 6. Check health endpoint
curl http://localhost:8000/health
```

**Verification**:
- Service starts successfully
- No errors in logs
- Health endpoint returns OK
- Metrics available at /metrics

#### Step 2: Soak Test (24 hours)

**Monitor**:
- Memory usage (should plateau)
- CPU usage (< 10% baseline)
- Redis circuit state (should be CLOSED)
- Task exception logs (should be empty)
- WebSocket connections (should be stable)

**Acceptance Criteria**:
- Zero crashes
- Zero memory leaks
- Zero silent failures
- < 100ms p95 latency

#### Step 3: Deploy to Staging

```bash
# 1. Promote dev image to staging
docker tag ticker-service:phase1 ticker-service:staging

# 2. Deploy to staging
kubectl apply -f k8s/staging/

# 3. Monitor rollout
kubectl rollout status deployment/ticker-service -n staging

# 4. Run smoke tests
pytest tests/smoke/ --env=staging
```

**Verification**:
- All smoke tests pass
- Live traffic processing correctly
- No increase in error rate

#### Step 4: Canary Deployment to Production

```bash
# 1. Deploy 10% traffic to new version
kubectl apply -f k8s/production/canary.yml

# 2. Monitor metrics (30 minutes)
# - Error rate
# - Latency (p95, p99)
# - Memory/CPU usage
# - Circuit breaker state

# 3. If healthy, increase to 50%
kubectl scale deployment/ticker-service-canary --replicas=5

# 4. Monitor (30 minutes)

# 5. If healthy, full rollout
kubectl apply -f k8s/production/deployment.yml
```

#### Step 5: Post-Deployment Verification

- [ ] Health checks passing
- [ ] Metrics dashboard shows green
- [ ] No increase in error rate
- [ ] Latency within SLOs
- [ ] Memory usage stable
- [ ] Circuit breaker state = CLOSED
- [ ] Task exception handler working (inject test failure)

### Rollback Procedure

If issues detected:

```bash
# 1. Immediate rollback
kubectl rollout undo deployment/ticker-service -n production

# 2. Verify rollback
kubectl rollout status deployment/ticker-service -n production

# 3. Check service health
curl https://ticker-service.prod/health

# 4. Investigate logs
kubectl logs deployment/ticker-service -n production --previous
```

**Triggers for Rollback**:
- Error rate > 1%
- p95 latency > 200ms (double baseline)
- Memory leak detected (> 20% growth/hour)
- Circuit breaker stuck OPEN
- Service crashes

---

## SUMMARY

### Phase 1 Deliverables

1. ✅ **Task Exception Handler**: Prevent silent task failures
2. ✅ **Bounded Reload Queue**: Prevent resource exhaustion
3. ✅ **Fix Mock State Races**: Thread-safe mock data
4. ✅ **Redis Circuit Breaker**: Graceful degradation
5. ✅ **Memory Leak Fix**: LRU eviction + cleanup

### Effort Summary

| Priority | Description | Effort | Risk |
|----------|-------------|--------|------|
| 1 | Task Exception Handler | 2-3 hours | LOW |
| 2 | Bound Reload Queue | 3-4 hours | LOW |
| 3 | Fix Mock State Races | 4-5 hours | MEDIUM |
| 4 | Redis Circuit Breaker | 3-4 hours | LOW |
| 5 | Memory Leak Fix | 3-4 hours | LOW |
| **Testing** | Unit + Integration + Regression | 6-8 hours | - |
| **TOTAL** | **Phase 1 Complete** | **21-28 hours** | **LOW-MEDIUM** |

### Expected Improvements

**Reliability**:
- ✅ Zero silent failures (100% exception visibility)
- ✅ Graceful degradation when Redis down
- ✅ No resource exhaustion from API spam

**Stability**:
- ✅ No race conditions in mock data
- ✅ No memory leaks in long-running deployments
- ✅ Bounded resource usage (queues, dictionaries)

**Observability**:
- ✅ All task exceptions logged and alerted
- ✅ Circuit breaker state visible in metrics
- ✅ Memory usage tracked and bounded

**Backward Compatibility**:
- ✅ 100% functional parity maintained
- ✅ No API changes
- ✅ No database migrations
- ✅ Incremental deployment possible

---

**Phase 1 Implementation Plan Version**: 1.0
**Date**: November 8, 2025
**Status**: READY FOR IMPLEMENTATION
