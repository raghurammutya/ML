# PHASE 1 IMPLEMENTATION - ROLE-SPECIFIC PROMPTS
**Optimized for Claude Code CLI**

**Date**: November 8, 2025
**Phase**: Phase 1 - Critical Reliability Improvements
**Estimated Duration**: 21-28 hours
**Risk Level**: LOW-MEDIUM

---

## OVERVIEW

This document contains 5 carefully crafted, role-specific prompts for implementing Phase 1 improvements using Claude Code CLI. Each prompt follows best practices for prompt engineering and Claude CLI syntax.

**Implementation Order**:
1. **Senior Backend Engineer** - Task Exception Handler (2-3 hours)
2. **Senior Backend Engineer** - Bounded Reload Queue (3-4 hours)
3. **Concurrency Expert** - Fix Mock State Races (4-5 hours)
4. **Reliability Engineer** - Redis Circuit Breaker (3-4 hours)
5. **Performance Engineer** - Memory Leak Fix (3-4 hours)

---

## PROMPT 1: TASK EXCEPTION HANDLER
**Role**: Senior Backend Engineer
**Priority**: CRITICAL
**Estimated Time**: 2-3 hours
**Files**: NEW: `app/utils/task_monitor.py`, MODIFY: `app/main.py`, `app/generator.py`

### Prompt

```text
You are a senior backend engineer implementing critical reliability improvements for a production asyncio service.

## OBJECTIVE
Implement a global task exception handler to prevent silent failures in background asyncio tasks.

## CONTEXT
The ticker_service uses fire-and-forget asyncio tasks that can fail silently:
- `_stream_underlying()` task (generator.py:157)
- `_stream_account()` tasks (generator.py:161-166)

If these tasks crash, streaming stops with NO logging or alerts.

## REQUIREMENTS

### 1. Create TaskMonitor Utility
Create NEW file: `app/utils/task_monitor.py`

Implement:
```python
class TaskMonitor:
    """Monitors asyncio tasks and logs unhandled exceptions"""

    def __init__(self, loop: Optional[asyncio.AbstractEventLoop] = None):
        # Set up global exception handler

    @staticmethod
    async def monitored_task(coro, task_name: str, on_error=None):
        # Wrap coroutine with exception handling

    def create_monitored_task(self, coro, task_name: str, on_error=None):
        # Create task with monitoring
```

**Key Features**:
- Global exception handler via `loop.set_exception_handler()`
- Wrap tasks to catch and log all exceptions
- Support optional error callbacks
- Log with structured context (task name, exception, stack trace)
- Handle `asyncio.CancelledError` properly (re-raise)

### 2. Integrate in main.py
**File**: `app/main.py`
**Location**: lifespan context manager (~line 80-100)

```python
from app.utils.task_monitor import TaskMonitor

@asynccontextmanager
async def lifespan(app: FastAPI):
    # NEW: Set up global task exception monitoring
    task_monitor = TaskMonitor(asyncio.get_running_loop())
    app.state.task_monitor = task_monitor
    logger.info("Global task exception handler enabled")

    # ... rest of lifespan ...
```

### 3. Update MultiAccountTickerLoop
**File**: `app/generator.py`

**Modify constructor** to accept `task_monitor` parameter:
```python
def __init__(
    self,
    settings,
    registry,
    subscription_store,
    publisher=None,
    task_monitor=None,  # NEW
):
    self._task_monitor = task_monitor
```

**Modify start() method** (line 157):
```python
# BEFORE:
self._underlying_task = asyncio.create_task(self._stream_underlying())

# AFTER:
if self._task_monitor:
    self._underlying_task = self._task_monitor.create_monitored_task(
        self._stream_underlying(),
        task_name="stream_underlying",
        on_error=self._on_underlying_stream_error,
    )
```

**Add error callback**:
```python
async def _on_underlying_stream_error(self, exc: Exception):
    logger.critical(f"Underlying stream failed: {exc}", exc_info=True)
```

**Apply same pattern** to account tasks (lines 161-166).

### 4. Pass TaskMonitor from main.py
**File**: `app/main.py`
**Location**: Where MultiAccountTickerLoop is instantiated (~line 90-100)

```python
ticker_loop = MultiAccountTickerLoop(
    settings=settings,
    registry=instrument_registry,
    subscription_store=subscription_store,
    publisher=redis_publisher,
    task_monitor=app.state.task_monitor,  # NEW
)
```

## TESTING REQUIREMENTS

Create `tests/unit/test_task_monitor.py`:
```python
@pytest.mark.asyncio
async def test_task_monitor_captures_exception():
    """Test that TaskMonitor captures unhandled exceptions"""
    async def failing_task():
        raise ValueError("Test exception")

    monitor = TaskMonitor()
    task = monitor.create_monitored_task(failing_task(), "test")
    await asyncio.sleep(0.1)

    assert task.done()  # Task completed (not hanging)
```

## CONSTRAINTS
- ✅ **100% backward compatible** - no functional changes
- ✅ **Zero performance impact** - < 1ms overhead per task
- ✅ **Graceful fallback** - works if task_monitor is None
- ✅ **All existing tests pass**

## VERIFICATION CHECKLIST
- [ ] TaskMonitor utility created with tests
- [ ] Global exception handler registered in lifespan
- [ ] MultiAccountTickerLoop uses monitored tasks
- [ ] Error callbacks implemented
- [ ] Unit tests pass
- [ ] Logs show exceptions from failing tasks
- [ ] No performance regression

## DELIVERABLES
1. `app/utils/task_monitor.py` (NEW)
2. Modified `app/main.py` (global handler)
3. Modified `app/generator.py` (use monitored tasks)
4. `tests/unit/test_task_monitor.py` (NEW)
5. Updated documentation

Begin implementation. Report progress after each major step.
```

---

## PROMPT 2: BOUNDED RELOAD QUEUE
**Role**: Senior Backend Engineer
**Priority**: CRITICAL
**Estimated Time**: 3-4 hours
**Files**: NEW: `app/utils/subscription_reloader.py`, MODIFY: `app/generator.py`

### Prompt

```text
You are a senior backend engineer implementing resource protection for a production async service.

## OBJECTIVE
Prevent unlimited concurrent subscription reloads that exhaust database connections and memory.

## CONTEXT
Current code creates unbounded tasks:
```python
# generator.py:203-220
def reload_subscriptions_async(self):
    async def _reload():
        await self.reload_subscriptions()
    asyncio.create_task(_reload())  # NO LIMIT!
```

**Problem**: Rapid API calls create 100+ concurrent reloads, exhausting:
- Database connection pool (max_size=5)
- Memory (each reload holds ~10MB)
- Event loop capacity

## REQUIREMENTS

### 1. Create SubscriptionReloader Utility
Create NEW file: `app/utils/subscription_reloader.py`

Implement:
```python
class SubscriptionReloader:
    """
    Manages subscription reload requests with:
    - Rate limiting (max 1 reload at a time)
    - Deduplication (coalesce multiple requests)
    - Debouncing (wait for burst to complete)
    """

    def __init__(
        self,
        reload_fn: Callable,
        debounce_seconds=1.0,
        max_reload_frequency_seconds=5.0
    ):
        self._reload_semaphore = asyncio.Semaphore(1)  # Only 1 at a time
        self._reload_pending = asyncio.Event()
        # ...

    async def start(self):
        # Start background loop

    async def stop(self):
        # Stop background loop

    def trigger_reload(self):
        # Non-blocking trigger (coalesces multiple calls)

    async def _reloader_loop(self):
        # Background loop that processes requests
```

**Key Features**:
- **Semaphore**: Only 1 reload executes at a time
- **Debouncing**: Wait 1s after last trigger before executing
- **Rate limiting**: Minimum 5s between reloads
- **Coalescing**: Multiple rapid triggers → single reload
- **Logging**: Show how many requests were coalesced

### 2. Integrate in MultiAccountTickerLoop
**File**: `app/generator.py`

**Modify constructor** (line ~70-85):
```python
from app.utils.subscription_reloader import SubscriptionReloader

def __init__(self, ...):
    # ... existing init ...

    # NEW: Create reloader
    self._subscription_reloader = SubscriptionReloader(
        reload_fn=self._perform_reload,
        debounce_seconds=1.0,
        max_reload_frequency_seconds=5.0,
    )
```

**Modify reload_subscriptions_async** (line 203-220):
```python
# BEFORE:
def reload_subscriptions_async(self):
    async def _reload():
        await self.reload_subscriptions()
    asyncio.create_task(_reload())

# AFTER:
def reload_subscriptions_async(self):
    """Trigger reload (non-blocking, coalesced)"""
    self._subscription_reloader.trigger_reload()
```

**Rename reload_subscriptions → _perform_reload**:
```python
async def _perform_reload(self):
    """Internal: Actual reload implementation"""
    # Move existing reload_subscriptions() code here

async def reload_subscriptions(self):
    """Public API: Immediate reload (blocking)"""
    await self._perform_reload()
```

**Update lifecycle** (start/stop methods):
```python
async def start(self):
    # ... existing code ...
    await self._subscription_reloader.start()

async def stop(self):
    # ... existing code ...
    await self._subscription_reloader.stop()
```

## TESTING REQUIREMENTS

Create `tests/unit/test_subscription_reloader.py`:
```python
@pytest.mark.asyncio
async def test_reloader_coalesces_requests():
    reload_count = 0

    async def mock_reload():
        nonlocal reload_count
        reload_count += 1
        await asyncio.sleep(0.1)

    reloader = SubscriptionReloader(mock_reload, debounce_seconds=0.2)
    await reloader.start()

    # Trigger 10 rapid reloads
    for _ in range(10):
        reloader.trigger_reload()
        await asyncio.sleep(0.01)

    await asyncio.sleep(1.5)

    # Should coalesce into 1-2 reloads max
    assert reload_count <= 2
```

Create `tests/integration/test_reload_queue_bounded.py`:
```python
async def test_rapid_subscriptions_bounded(client):
    # Make 50 rapid subscription requests
    tasks = [
        client.post("/subscriptions", json={"instrument_token": 256265+i})
        for i in range(50)
    ]
    responses = await asyncio.gather(*tasks)

    # All should succeed (not timeout)
    assert all(r.status_code in (200, 201) for r in responses)
```

## CONSTRAINTS
- ✅ **100% backward compatible**
- ✅ **No API changes**
- ✅ **Graceful degradation** (works without reloader)
- ✅ **Existing tests pass**

## VERIFICATION CHECKLIST
- [ ] SubscriptionReloader utility created
- [ ] Unit tests pass (coalescing works)
- [ ] Integration tests pass (no resource exhaustion)
- [ ] Logs show "coalesced N requests"
- [ ] Max 1 reload at a time (verified in tests)
- [ ] Debouncing doesn't delay critical reloads

## DELIVERABLES
1. `app/utils/subscription_reloader.py` (NEW)
2. Modified `app/generator.py`
3. `tests/unit/test_subscription_reloader.py` (NEW)
4. `tests/integration/test_reload_queue_bounded.py` (NEW)

Begin implementation. Report progress after each major step.
```

---

## PROMPT 3: FIX MOCK STATE RACES
**Role**: Concurrency Expert
**Priority**: HIGH
**Estimated Time**: 4-5 hours
**Files**: MODIFY: `app/generator.py`

### Prompt

```text
You are a concurrency expert fixing race conditions in a production async service.

## OBJECTIVE
Eliminate race conditions in mock data generation using immutable snapshots.

## CONTEXT
Current code has double-check locking anti-pattern:
```python
# generator.py:313-361
if self._mock_underlying_state is not None:
    return  # Check WITHOUT lock

async with self._mock_seed_lock:
    if self._mock_underlying_state is not None:
        return  # Check AFTER lock
    self._mock_underlying_state = MockUnderlyingState(...)  # RACE!
```

**Race Scenario**:
```
Thread A: Check state is None (line 313) → True
Thread B: Check state is None (line 313) → True  # RACE!
Thread A: Acquire lock, initialize state
Thread B: Acquire lock, RE-INITIALIZE (overwrites A)
```

Additionally, mock state is **mutable** and accessed without locks in multiple places.

## REQUIREMENTS

### 1. Make MockUnderlyingState Immutable
**File**: `app/generator.py`
**Location**: Lines 36-45

**BEFORE**:
```python
@dataclass
class MockUnderlyingState:
    symbol: str
    last_close: float  # MUTABLE!
    base_volume: int   # MUTABLE!
    # ...
```

**AFTER**:
```python
@dataclass(frozen=True)  # Immutable
class MockUnderlyingSnapshot:
    """Thread-safe immutable snapshot"""
    symbol: str
    last_close: float
    base_volume: int
    timestamp: float
    # ...

@dataclass
class _MockUnderlyingBuilder:
    """Internal mutable builder (use ONLY under lock)"""
    symbol: str
    last_close: float
    base_volume: int
    # ...

    def build_snapshot(self) -> MockUnderlyingSnapshot:
        return MockUnderlyingSnapshot(...)
```

### 2. Update Class to Use Builder + Snapshot Pattern
**File**: `app/generator.py`

**Modify __init__** (line ~70-90):
```python
# Internal builder (mutable, protected by lock)
self._mock_underlying_builder: Optional[_MockUnderlyingBuilder] = None
# Public snapshot (immutable, safe to read anytime)
self._mock_underlying_snapshot: Optional[MockUnderlyingSnapshot] = None
self._mock_seed_lock = asyncio.Lock()
```

**Update _ensure_mock_underlying_seed** (line 313-361):
```python
async def _ensure_mock_underlying_seed(self):
    # Quick check WITHOUT lock (safe - snapshot is immutable)
    if self._mock_underlying_snapshot is not None:
        return

    async with self._mock_seed_lock:
        # Double-check AFTER lock
        if self._mock_underlying_snapshot is not None:
            return

        # Create builder (mutable, under lock)
        self._mock_underlying_builder = _MockUnderlyingBuilder(...)

        # Create snapshot (immutable, for consumers)
        self._mock_underlying_snapshot = self._mock_underlying_builder.build_snapshot()
```

**Update _generate_mock_underlying_bar** (line 362-394):
```python
async def _generate_mock_underlying_bar(self):
    # Read snapshot (NO LOCK - immutable!)
    snapshot = self._mock_underlying_snapshot
    if snapshot is None:
        return {}

    # Generate new values based on snapshot
    new_price = snapshot.last_close + random_delta

    # Update builder UNDER LOCK, create new snapshot
    async with self._mock_seed_lock:
        if self._mock_underlying_builder:
            self._mock_underlying_builder.last_close = new_price
            # Create NEW snapshot
            self._mock_underlying_snapshot = self._mock_underlying_builder.build_snapshot()

    return bar
```

### 3. Apply Same Pattern to MockOptionState
**Location**: Lines 46-62, 88-90, 395-551

Convert:
- `MockOptionState` → `MockOptionSnapshot` (frozen) + `_MockOptionBuilder`
- `self._mock_option_state` → `self._mock_option_snapshots` (Dict[int, MockOptionSnapshot])
- Add `self._mock_option_builders` (Dict[int, _MockOptionBuilder])

Update all methods that access mock option state:
- `_ensure_mock_option_seed`
- `_generate_mock_option_snapshot`
- Any other readers

## TESTING REQUIREMENTS

Create `tests/unit/test_mock_state_concurrency.py`:
```python
@pytest.mark.asyncio
async def test_mock_state_concurrent_access():
    """Test concurrent reads don't see torn data"""
    ticker_loop = MultiAccountTickerLoop(...)

    async def reader():
        for _ in range(100):
            snapshot = ticker_loop._mock_underlying_snapshot
            if snapshot:
                assert snapshot.last_close > 0  # Consistent
            await asyncio.sleep(0.001)

    async def writer():
        for _ in range(100):
            await ticker_loop._generate_mock_underlying_bar()
            await asyncio.sleep(0.001)

    # Run 3 readers + 2 writers concurrently
    await asyncio.gather(reader(), reader(), reader(), writer(), writer())
```

## CONSTRAINTS
- ✅ **100% backward compatible**
- ✅ **No functional changes to mock data**
- ✅ **No performance regression**
- ✅ **All existing tests pass**

## VERIFICATION CHECKLIST
- [ ] MockUnderlyingSnapshot is frozen (immutable)
- [ ] MockOptionSnapshot is frozen (immutable)
- [ ] Builders only mutated under lock
- [ ] Snapshots read without lock
- [ ] Concurrent access test passes
- [ ] Mock data quality unchanged
- [ ] No performance regression

## DELIVERABLES
1. Modified `app/generator.py` (immutable snapshots)
2. `tests/unit/test_mock_state_concurrency.py` (NEW)
3. Updated documentation

Begin implementation. Report progress after each major step.
```

---

## PROMPT 4: REDIS CIRCUIT BREAKER
**Role**: Reliability Engineer
**Priority**: HIGH
**Estimated Time**: 3-4 hours
**Files**: NEW: `app/utils/circuit_breaker.py`, MODIFY: `app/redis_client.py`, `app/main.py`

### Prompt

```text
You are a reliability engineer implementing fault tolerance for a production service.

## OBJECTIVE
Add circuit breaker pattern to Redis publishing to prevent cascading failures.

## CONTEXT
Current code blocks indefinitely if Redis is down:
```python
# redis_client.py:43-62
async def publish(self, channel, message):
    for attempt in (1, 2):
        try:
            await self._client.publish(channel, message)
            return
        except RedisConnectionError:
            await self._reset()
    raise RuntimeError("Failed")  # BLOCKS streaming!
```

**Problem**: If Redis is unavailable, ALL ticks fail and streaming stops.

**Goal**: Gracefully degrade - drop messages when Redis down, continue streaming.

## REQUIREMENTS

### 1. Create CircuitBreaker Utility
Create NEW file: `app/utils/circuit_breaker.py`

Implement:
```python
class CircuitState(enum.Enum):
    CLOSED = "closed"       # Normal operation
    OPEN = "open"           # Failing - reject requests
    HALF_OPEN = "half_open" # Testing recovery

class CircuitBreaker:
    """Circuit breaker for protecting against cascading failures"""

    def __init__(
        self,
        failure_threshold=5,
        recovery_timeout_seconds=60.0,
        half_open_max_attempts=3,
        name="circuit_breaker"
    ):
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        # ...

    async def can_execute(self) -> bool:
        # CLOSED: Allow
        # OPEN: Check if timeout elapsed → HALF_OPEN
        # HALF_OPEN: Allow limited attempts

    async def record_success(self):
        # HALF_OPEN + success → CLOSED

    async def record_failure(self, error=None):
        # CLOSED + threshold → OPEN
        # HALF_OPEN + failure → stay OPEN
```

**Key Features**:
- State machine: CLOSED → OPEN → HALF_OPEN → CLOSED
- Open after N failures (default: 5)
- Test recovery after timeout (default: 60s)
- Thread-safe (use asyncio.Lock)

### 2. Integrate in RedisPublisher
**File**: `app/redis_client.py`

**Modify constructor**:
```python
from app.utils.circuit_breaker import CircuitBreaker

class RedisPublisher:
    def __init__(self, url):
        self._url = url
        self._client = None

        # NEW: Circuit breaker
        self._circuit_breaker = CircuitBreaker(
            failure_threshold=10,
            recovery_timeout_seconds=60.0,
            name="redis_publisher"
        )
```

**Modify publish()** (lines 43-62):
```python
async def publish(self, channel, message):
    # Check circuit state
    if not await self._circuit_breaker.can_execute():
        # Circuit OPEN - drop message gracefully
        logger.warning(f"Redis circuit OPEN, dropping message")
        return  # DON'T block streaming!

    # Attempt publish with retries
    for attempt in (1, 2):
        try:
            await self._client.publish(channel, message)
            await self._circuit_breaker.record_success()
            return
        except RedisConnectionError as exc:
            await self._reset()
            if attempt == 2:
                # Final failure
                await self._circuit_breaker.record_failure(exc)
                logger.error(f"Redis publish failed, circuit may open")
                return  # Drop, don't raise
```

### 3. Add Prometheus Metrics
**File**: `app/redis_client.py`

```python
from prometheus_client import Counter, Gauge

redis_publish_total = Counter("redis_publish_total", "Total publish attempts")
redis_publish_failures = Counter("redis_publish_failures", "Total failures")
redis_circuit_open_drops = Counter("redis_circuit_open_drops", "Drops when circuit open")
redis_circuit_state = Gauge("redis_circuit_state", "Circuit state (0=closed, 1=open, 2=half_open)")

class RedisPublisher:
    async def publish(self, ...):
        redis_publish_total.inc()

        if not await self._circuit_breaker.can_execute():
            redis_circuit_open_drops.inc()
            # ...

        # ... on failure:
        redis_publish_failures.inc()
```

### 4. Add Health Check Endpoint
**File**: `app/main.py`
**Location**: /health endpoint (~line 420-450)

```python
@app.get("/health")
async def health():
    # ... existing checks ...

    # NEW: Redis circuit status
    redis_state = redis_publisher._circuit_breaker.get_state().value if redis_publisher else "unknown"

    return {
        "status": "ok",
        # ... existing fields ...
        "redis": {
            "connected": redis_publisher._client is not None,
            "circuit_state": redis_state,
            "failure_count": redis_publisher._circuit_breaker.get_failure_count(),
        }
    }
```

## TESTING REQUIREMENTS

Create `tests/unit/test_circuit_breaker.py`:
```python
@pytest.mark.asyncio
async def test_circuit_opens_after_threshold():
    breaker = CircuitBreaker(failure_threshold=3, name="test")

    # Initially CLOSED
    assert breaker.get_state() == CircuitState.CLOSED
    assert await breaker.can_execute()

    # Record 3 failures
    for _ in range(3):
        await breaker.record_failure()

    # Should be OPEN
    assert breaker.get_state() == CircuitState.OPEN
    assert not await breaker.can_execute()

@pytest.mark.asyncio
async def test_circuit_recovers():
    breaker = CircuitBreaker(
        failure_threshold=2,
        recovery_timeout_seconds=0.1  # Short for testing
    )

    # Force OPEN
    await breaker.record_failure()
    await breaker.record_failure()

    # Wait for timeout
    await asyncio.sleep(0.15)

    # Should allow test
    assert await breaker.can_execute()

    # Success → CLOSED
    await breaker.record_success()
    assert breaker.get_state() == CircuitState.CLOSED
```

## CONSTRAINTS
- ✅ **100% backward compatible**
- ✅ **Graceful degradation** (drop messages, don't block)
- ✅ **No performance impact** when Redis healthy
- ✅ **All existing tests pass**

## VERIFICATION CHECKLIST
- [ ] CircuitBreaker utility created and tested
- [ ] RedisPublisher integrates circuit breaker
- [ ] Circuit opens after 10 failures
- [ ] Messages dropped (not blocking) when OPEN
- [ ] Circuit attempts recovery after 60s
- [ ] Prometheus metrics track circuit state
- [ ] Health endpoint shows circuit status
- [ ] Logs indicate state changes

## DELIVERABLES
1. `app/utils/circuit_breaker.py` (NEW)
2. Modified `app/redis_client.py`
3. Modified `app/main.py` (/health endpoint)
4. `tests/unit/test_circuit_breaker.py` (NEW)

Begin implementation. Report progress after each major step.
```

---

## PROMPT 5: MEMORY LEAK FIX
**Role**: Performance Engineer
**Priority**: HIGH
**Estimated Time**: 3-4 hours
**Files**: MODIFY: `app/generator.py`, `app/config.py`

### Prompt

```text
You are a performance engineer fixing memory leaks in a production service.

## OBJECTIVE
Prevent unbounded growth of mock state dictionaries using LRU eviction and expiry cleanup.

## CONTEXT
Current code accumulates mock state indefinitely:
```python
# generator.py:88-90
self._mock_option_state: Dict[int, MockOptionState] = {}  # NO MAX SIZE!

# Line 395-408
for instrument in missing:
    state = await self._seed_option_state(...)
    self._mock_option_state[token] = state  # GROWS FOREVER!
```

**Problem**:
- After 1 month: ~5,000 contracts = 1MB
- After 1 year: ~60,000 contracts = 12MB+ leak
- Expired options never removed

## REQUIREMENTS

### 1. Add LRU Eviction
**File**: `app/generator.py`
**Location**: Line 88-90

**BEFORE**:
```python
self._mock_option_state: Dict[int, MockOptionState] = {}
```

**AFTER**:
```python
from collections import OrderedDict

self._mock_option_state_max_size = 5000  # Configurable
self._mock_option_state: OrderedDict[int, MockOptionState] = OrderedDict()
```

### 2. Implement Cleanup in _ensure_mock_option_seed
**File**: `app/generator.py`
**Location**: Lines 395-408

```python
async def _ensure_mock_option_seed(self, client, instruments):
    missing = [inst for inst in instruments
               if inst.instrument_token not in self._mock_option_state]
    if not missing:
        return

    async with self._mock_seed_lock:
        # STEP 1: Cleanup expired options FIRST
        today = self._now_market().date()
        expired_tokens = [
            token for token, state in self._mock_option_state.items()
            if state.instrument.expiry < today
        ]
        for token in expired_tokens:
            del self._mock_option_state[token]

        if expired_tokens:
            logger.info(f"Removed {len(expired_tokens)} expired mock states")

        # STEP 2: Enforce max size (LRU eviction)
        while len(self._mock_option_state) >= self._mock_option_state_max_size:
            evicted_token, _ = self._mock_option_state.popitem(last=False)  # Oldest
            logger.debug(f"Evicted LRU mock state: {evicted_token}")

        # STEP 3: Seed new instruments
        for instrument in still_missing:
            state = await self._seed_option_state(...)
            if state:
                # Add to END (most recently used)
                self._mock_option_state[token] = state
```

### 3. Add Background Cleanup Task
**File**: `app/generator.py`

Add new method:
```python
async def _mock_state_cleanup_loop(self):
    """Background task: Cleanup expired mock state every 5 minutes"""
    logger.info("Mock state cleanup loop started")

    while self._running:
        try:
            await asyncio.sleep(300)  # 5 minutes

            if not self._running:
                break

            # Cleanup expired options
            await self._cleanup_expired_mock_state()

        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.exception(f"Cleanup loop error: {exc}")
            await asyncio.sleep(60)

async def _cleanup_expired_mock_state(self):
    """Remove expired mock state entries"""
    today = self._now_market().date()

    async with self._mock_seed_lock:
        expired_tokens = [
            token for token, state in self._mock_option_state.items()
            if state.instrument.expiry < today
        ]

        for token in expired_tokens:
            del self._mock_option_state[token]

        if expired_tokens:
            logger.info(f"Cleaned up {len(expired_tokens)} expired mock states, "
                       f"remaining: {len(self._mock_option_state)}")
```

**Start/stop cleanup task**:
```python
async def start(self):
    # ... existing code ...

    # NEW: Start cleanup task
    if self._task_monitor:
        self._cleanup_task = self._task_monitor.create_monitored_task(
            self._mock_state_cleanup_loop(),
            task_name="mock_state_cleanup"
        )

async def stop(self):
    # ... existing code ...

    # NEW: Stop cleanup task
    if self._cleanup_task:
        self._cleanup_task.cancel()
        await self._cleanup_task
```

### 4. Add Configuration
**File**: `app/config.py`

```python
class Settings(BaseSettings):
    # ... existing fields ...

    # NEW
    mock_state_max_size: int = Field(
        default=5000,
        description="Max instruments in mock state cache (LRU eviction)"
    )
```

**File**: `app/generator.py` (use config):
```python
self._mock_option_state_max_size = settings.mock_state_max_size
```

## TESTING REQUIREMENTS

Create `tests/unit/test_mock_state_eviction.py`:
```python
@pytest.mark.asyncio
async def test_lru_eviction():
    """Test LRU eviction when max_size exceeded"""
    ticker_loop = MultiAccountTickerLoop(...)
    ticker_loop._mock_option_state_max_size = 10  # Small for testing

    # Seed 15 instruments (exceeds limit)
    instruments = [mock_instrument(token=i) for i in range(15)]
    await ticker_loop._ensure_mock_option_seed(mock_client, instruments)

    # Should evict 5 oldest, keep 10 newest
    assert len(ticker_loop._mock_option_state) == 10
    assert 0 not in ticker_loop._mock_option_state  # Oldest evicted
    assert 14 in ticker_loop._mock_option_state     # Newest kept
```

Create `tests/integration/test_mock_cleanup.py`:
```python
@pytest.mark.asyncio
async def test_expired_cleanup():
    """Test expired options removed"""
    ticker_loop = MultiAccountTickerLoop(...)

    # Create expired option
    yesterday = (datetime.now() - timedelta(days=1)).date()
    expired_inst = Instrument(token=12345, expiry=yesterday, ...)

    await ticker_loop._ensure_mock_option_seed(mock_client, [expired_inst])
    assert 12345 in ticker_loop._mock_option_state

    # Run cleanup
    await ticker_loop._cleanup_expired_mock_state()

    # Should be removed
    assert 12345 not in ticker_loop._mock_option_state
```

## CONSTRAINTS
- ✅ **100% backward compatible**
- ✅ **No functional changes to mock data**
- ✅ **Memory usage plateaus**
- ✅ **All existing tests pass**

## VERIFICATION CHECKLIST
- [ ] OrderedDict used for mock state
- [ ] LRU eviction when max_size exceeded
- [ ] Expired options cleaned every 5 minutes
- [ ] Background cleanup task started
- [ ] Configuration added
- [ ] Unit tests pass
- [ ] Memory usage plateaus (load test)
- [ ] Logs show cleanup activity

## DELIVERABLES
1. Modified `app/generator.py` (LRU + cleanup)
2. Modified `app/config.py` (new settings)
3. `tests/unit/test_mock_state_eviction.py` (NEW)
4. `tests/integration/test_mock_cleanup.py` (NEW)

Begin implementation. Report progress after each major step.
```

---

## USAGE INSTRUCTIONS

### For Claude Code CLI

Each prompt can be used directly with Claude Code CLI. Simply:

1. **Copy the entire prompt** (including context and requirements)
2. **Paste into Claude Code CLI**
3. **Let Claude implement autonomously**
4. **Review changes and run tests**
5. **Iterate if needed**

### Example Command

```bash
# Option 1: Paste prompt directly in interactive mode
claude-code

# Option 2: Pass prompt via file
cat PHASE1_ROLE_PROMPTS.md | claude-code --section="PROMPT 1"
```

### Best Practices

1. **One prompt at a time**: Don't mix multiple roles
2. **Review before merging**: Inspect generated code
3. **Run tests after each**: Verify no regressions
4. **Document changes**: Update CHANGELOG.md
5. **Commit incrementally**: One PR per prompt

### Order of Implementation

```
Day 1: PROMPT 1 (Task Exception Handler)
       ↓
Day 2: PROMPT 2 (Bounded Reload Queue)
       ↓
Day 3: PROMPT 3 (Fix Mock State Races)
       ↓
Day 4: PROMPT 4 (Redis Circuit Breaker)
       ↓
Day 5: PROMPT 5 (Memory Leak Fix)
       ↓
Day 6-7: Integration testing & deployment
```

---

## SUCCESS CRITERIA

### After All 5 Prompts Completed

✅ **Reliability**:
- Zero silent task failures
- Graceful degradation when Redis down
- No unbounded resource growth

✅ **Safety**:
- No race conditions in mock data
- Thread-safe concurrent access
- Proper error handling

✅ **Performance**:
- No memory leaks
- Memory usage plateaus
- < 5% performance overhead

✅ **Quality**:
- All existing tests pass
- New tests provide 90%+ coverage
- Code is well-documented

✅ **Backward Compatibility**:
- 100% functional parity
- No API changes
- No database migrations

---

**Document Version**: 1.0
**Date**: November 8, 2025
**Status**: READY FOR USE WITH CLAUDE CODE CLI
