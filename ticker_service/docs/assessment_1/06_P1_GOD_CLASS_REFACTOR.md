# P1 HIGH: Refactor God Class - MultiAccountTickerLoop

**Role:** Senior Backend Engineer
**Priority:** P1 - HIGH (Maintainability & Cognitive Load)
**Estimated Effort:** 24 hours
**Dependencies:** 05_P1_DEPENDENCY_INJECTION_REFACTOR.md (recommended first)
**Target:** Split 757 LOC god class into 4 focused classes

---

## Objective

Decompose MultiAccountTickerLoop (757 lines, complexity 40) into focused, single-responsibility components following SOLID principles.

**Current State:**
- 757 lines in single class
- 23 methods
- 7 distinct responsibilities
- Cyclomatic complexity: 40 (threshold: 15)
- Cognitive complexity: 60 (threshold: 20)

---

## Refactoring Plan

### Current Structure (God Class):
```python
class MultiAccountTickerLoop:
    # TOO MANY RESPONSIBILITIES:
    # 1. Stream orchestration (managing account tasks)
    # 2. Subscription management (loading/reconciling)
    # 3. Mock data generation (off-market hours)
    # 4. Historical bootstrapping (backfilling data)
    # 5. Tick processing (coordinating validation/processing)
    # 6. Market hours detection
    # 7. Health monitoring

    def __init__(self, ...):  # 15+ dependencies
        pass

    async def start(self): ...  # Orchestration
    async def reload_subscriptions(self): ...  # Subscription mgmt
    async def _generate_mock_option_snapshot(self): ...  # Mock data
    async def _backfill_missing_history(self): ...  # Bootstrap
    async def _handle_ticks(self): ...  # Processing
    # ... 18 more methods
```

### Target Structure (4 Focused Classes):

```python
# 1. Stream Orchestration (~150 LOC)
class StreamOrchestrator:
    """Manages account streaming tasks"""
    async def start_streaming(self, accounts: List[Account]): ...
    async def stop_streaming(self): ...
    async def get_stream_health(self) -> Dict[str, Any]: ...

# 2. Subscription Coordination (~180 LOC)
class SubscriptionCoordinator:
    """Handles subscription lifecycle"""
    async def load_subscriptions(self) -> Dict[str, List[Instrument]]: ...
    async def reload_subscriptions(self): ...
    async def reconcile_subscriptions(self): ...

# 3. Mock Data Coordination (~200 LOC)
class MockDataCoordinator:
    """Manages mock data generation during off-hours"""
    async def generate_mock_data(self, instruments: List[Instrument]): ...
    def is_market_open(self) -> bool: ...
    async def _ensure_mock_seed(self): ...

# 4. Main Orchestrator (< 200 LOC)
class TickerServiceOrchestrator:
    """Coordinates all ticker service components"""
    def __init__(
        self,
        stream_orch: StreamOrchestrator,
        subscription_coord: SubscriptionCoordinator,
        mock_coord: MockDataCoordinator
    ): ...

    async def start(self):
        subscriptions = await self._subscriptions.load_subscriptions()
        if self._mock.is_market_open():
            await self._stream.start_streaming(subscriptions)
        else:
            await self._mock.generate_mock_data(subscriptions)
```

---

## Implementation Tasks

### Task 1: Extract SubscriptionCoordinator (6 hours)

```python
# app/services/subscription_coordinator.py (NEW FILE)

from typing import Dict, List
from app.models import Instrument
from app.subscription_store import SubscriptionStore
from app.instrument_registry import InstrumentRegistry

class SubscriptionCoordinator:
    """Handles all subscription lifecycle management"""

    def __init__(
        self,
        subscription_store: SubscriptionStore,
        instrument_registry: InstrumentRegistry
    ):
        self._store = subscription_store
        self._registry = instrument_registry
        self._reload_queue: asyncio.Queue = asyncio.Queue()

    async def load_subscriptions(self) -> Dict[str, List[Instrument]]:
        """Load subscriptions from database"""
        subscriptions = await self._store.get_all_subscriptions()

        # Group by account
        by_account = {}
        for sub in subscriptions:
            account_id = sub['account_id']
            instrument = self._registry.get_by_token(sub['instrument_token'])
            if account_id not in by_account:
                by_account[account_id] = []
            by_account[account_id].append(instrument)

        return by_account

    async def reload_subscriptions(self):
        """Queue subscription reload (debounced)"""
        await self._reload_queue.put(True)

    async def _reload_worker(self):
        """Process reload requests (debounced)"""
        while True:
            await self._reload_queue.get()
            await asyncio.sleep(0.5)  # Debounce

            # Drain queue
            while not self._reload_queue.empty():
                self._reload_queue.get_nowait()

            # Perform reload
            await self._do_reload()

    async def _do_reload(self):
        """Actual reload implementation"""
        logger.info("Reloading subscriptions...")
        new_subscriptions = await self.load_subscriptions()
        # Notify stream orchestrator of changes
        # (via callback or event)
```

### Task 2: Extract MockDataCoordinator (4 hours)

```python
# app/services/mock_data_coordinator.py (NEW FILE)

from dataclasses import dataclass
from datetime import datetime, time
import pytz

@dataclass(frozen=True)
class MockUnderlyingSnapshot:
    """Immutable snapshot of underlying state"""
    symbol: str
    last_close: float
    base_volume: int
    timestamp: float

class MockDataCoordinator:
    """Manages mock data generation during off-market hours"""

    def __init__(self, config: Settings):
        self._config = config
        self._mock_underlying_state: MockUnderlyingSnapshot | None = None
        self._mock_option_state: OrderedDict[int, MockOptionState] = OrderedDict()
        self._mock_seed_lock = asyncio.Lock()
        self._ist = pytz.timezone('Asia/Kolkata')

    def is_market_open(self) -> bool:
        """Check if market is currently open"""
        now_ist = datetime.now(self._ist)
        current_time = now_ist.time()

        # Market hours: 9:15 AM - 3:30 PM IST
        market_open = time(9, 15)
        market_close = time(15, 30)

        # Check day of week (Mon-Fri)
        if now_ist.weekday() >= 5:  # Sat/Sun
            return False

        return market_open <= current_time <= market_close

    async def generate_mock_data(self, instruments: List[Instrument]):
        """Generate realistic mock data for instruments"""
        await self._ensure_mock_seed(instruments)

        for instrument in instruments:
            if instrument.segment == "INDICES":
                mock_tick = self._generate_mock_underlying_tick(instrument)
            else:
                mock_tick = self._generate_mock_option_tick(instrument)

            yield mock_tick

    async def _ensure_mock_seed(self, instruments: List[Instrument]):
        """Initialize mock state (thread-safe)"""
        async with self._mock_seed_lock:
            if self._mock_underlying_state is None:
                # Load last close from database
                last_close = await self._get_last_close()
                self._mock_underlying_state = MockUnderlyingSnapshot(
                    symbol="NIFTY",
                    last_close=last_close,
                    base_volume=1000000,
                    timestamp=time.time()
                )
```

### Task 3: Extract StreamOrchestrator (8 hours)

```python
# app/services/stream_orchestrator.py (NEW FILE)

from typing import Dict, List
from app.models import Instrument
from app.accounts import SessionOrchestrator

class StreamOrchestrator:
    """Manages live streaming tasks across accounts"""

    def __init__(
        self,
        session_orchestrator: SessionOrchestrator,
        tick_handler: Callable
    ):
        self._orchestrator = session_orchestrator
        self._tick_handler = tick_handler
        self._account_tasks: Dict[str, asyncio.Task] = {}
        self._assignments: Dict[str, List[Instrument]] = {}

    async def start_streaming(
        self,
        subscriptions: Dict[str, List[Instrument]]
    ):
        """Start streaming for all accounts"""
        self._assignments = subscriptions

        for account_id, instruments in subscriptions.items():
            task = asyncio.create_task(
                self._stream_account(account_id, instruments)
            )
            self._account_tasks[account_id] = task

    async def stop_streaming(self):
        """Stop all streaming tasks"""
        for account_id, task in self._account_tasks.items():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def get_stream_health(self) -> Dict[str, Any]:
        """Get health status of all streams"""
        health = {}
        for account_id, task in self._account_tasks.items():
            health[account_id] = {
                "running": not task.done(),
                "instruments": len(self._assignments.get(account_id, []))
            }
        return health

    async def _stream_account(
        self,
        account_id: str,
        instruments: List[Instrument]
    ):
        """Stream ticks for specific account"""
        while True:
            try:
                # Get WebSocket connection
                ws = await self._orchestrator.get_websocket(account_id)

                # Subscribe to instruments
                await ws.subscribe(instruments)

                # Handle ticks
                async for ticks in ws:
                    await self._tick_handler(account_id, ticks)

            except Exception as e:
                logger.error(f"Stream error for {account_id}: {e}")
                await asyncio.sleep(5.0)  # Backoff before retry
```

### Task 4: Create Main Orchestrator (4 hours)

```python
# app/services/ticker_service_orchestrator.py (NEW FILE)

class TickerServiceOrchestrator:
    """Main coordinator - delegates to specialized components"""

    def __init__(
        self,
        stream_orchestrator: StreamOrchestrator,
        subscription_coordinator: SubscriptionCoordinator,
        mock_coordinator: MockDataCoordinator,
        tick_processor: TickProcessor
    ):
        self._stream = stream_orchestrator
        self._subscriptions = subscription_coordinator
        self._mock = mock_coordinator
        self._tick_processor = tick_processor

    async def start(self):
        """Start ticker service"""
        # Load subscriptions
        subscriptions = await self._subscriptions.load_subscriptions()

        if self._mock.is_market_open():
            # Market open: Start live streaming
            logger.info("Market open - starting live streaming")
            await self._stream.start_streaming(subscriptions)
        else:
            # Market closed: Generate mock data
            logger.info("Market closed - generating mock data")
            await self._start_mock_generation(subscriptions)

        # Start subscription reload worker
        asyncio.create_task(self._subscriptions._reload_worker())

    async def stop(self):
        """Stop ticker service"""
        await self._stream.stop_streaming()

    async def reload_subscriptions(self):
        """Reload subscriptions (public API)"""
        await self._subscriptions.reload_subscriptions()

    async def _start_mock_generation(self, subscriptions):
        """Generate mock ticks during off-hours"""
        async for mock_tick in self._mock.generate_mock_data(subscriptions):
            await self._tick_processor.process_tick(mock_tick, is_mock=True)
```

### Task 5: Migrate Existing Code (2 hours)

```bash
# 1. Update imports across codebase
# Before:
from app.generator import MultiAccountTickerLoop

# After:
from app.services.ticker_service_orchestrator import TickerServiceOrchestrator

# 2. Update initialization in main.py
# Before:
ticker_loop = MultiAccountTickerLoop(...)

# After:
stream_orch = StreamOrchestrator(...)
subscription_coord = SubscriptionCoordinator(...)
mock_coord = MockDataCoordinator(...)
ticker_orchestrator = TickerServiceOrchestrator(
    stream_orch, subscription_coord, mock_coord, tick_processor
)

# 3. Deprecate old class
# app/generator.py - Add deprecation warning
@deprecated("Use TickerServiceOrchestrator instead")
class MultiAccountTickerLoop:
    ...
```

---

## Benefits

**Before:**
- 757 LOC god class
- 23 methods
- 15+ dependencies
- Cyclomatic complexity: 40
- Impossible to unit test

**After:**
- 4 classes < 200 LOC each
- Single Responsibility Principle
- Clear dependencies
- Cyclomatic complexity < 15 per class
- Easy to unit test each component

---

## Testing Impact

```python
# Before: Can't test subscription logic separately
# After: Easy!

def test_subscription_coordinator_load():
    mock_store = Mock(spec=SubscriptionStore)
    mock_registry = Mock(spec=InstrumentRegistry)

    coordinator = SubscriptionCoordinator(mock_store, mock_registry)
    subscriptions = await coordinator.load_subscriptions()

    # Test in complete isolation!
```

---

## Acceptance Criteria

- [ ] SubscriptionCoordinator extracted (< 200 LOC)
- [ ] MockDataCoordinator extracted (< 200 LOC)
- [ ] StreamOrchestrator extracted (< 200 LOC)
- [ ] TickerServiceOrchestrator created (< 200 LOC)
- [ ] Old MultiAccountTickerLoop deprecated
- [ ] All tests passing
- [ ] Each new class has unit tests
- [ ] Cyclomatic complexity < 15 per class
- [ ] Documentation updated

---

## Sign-Off

- [ ] Backend Lead: _____________________ Date: _____
- [ ] Architecture Lead: _____________________ Date: _____
