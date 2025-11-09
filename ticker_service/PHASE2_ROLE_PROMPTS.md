# TICKER SERVICE - PHASE 2 ROLE-BASED PROMPTS
**Refactoring & Architectural Improvements**

**Date**: November 8, 2025
**Phase**: 2 (Refactoring)
**Prerequisites**: Phase 1 Complete ✅
**Total Estimated Time**: 16-20 hours
**Risk Level**: MEDIUM

---

## OVERVIEW

Phase 2 focuses on **refactoring the God Class anti-pattern** in generator.py (1,184 lines) by extracting distinct responsibilities into separate, focused classes. This improves maintainability, testability, and reduces coupling.

### Goals
- ✅ Extract Mock Data Generator from MultiAccountTickerLoop
- ✅ Extract Subscription Reconciler logic
- ✅ Extract Historical Bootstrapper
- ✅ Improve test coverage through better modularity
- ✅ Maintain 100% backward compatibility

### Success Criteria
- All existing tests pass
- generator.py reduced from 1,184 lines to <600 lines
- Each extracted class has >80% test coverage
- No performance regression
- API surface unchanged

---

## PROMPT 1: EXTRACT MOCK DATA GENERATOR
**Role**: Refactoring Specialist
**Priority**: HIGH
**Estimated Time**: 4-5 hours
**Files**: NEW: `app/services/mock_generator.py`, MODIFY: `app/generator.py`

### Prompt

```text
You are a refactoring specialist improving code maintainability by extracting cohesive responsibilities.

## OBJECTIVE
Extract mock data generation logic from MultiAccountTickerLoop into a dedicated MockDataGenerator class.

## CONTEXT
Current generator.py has 1,184 lines with mixed responsibilities. Mock data generation (lines 313-551, 836-919) is self-contained and can be extracted.

## REQUIREMENTS

### 1. Create MockDataGenerator Service
Create NEW file: `app/services/mock_generator.py`

```python
"""
Mock data generation service for option streaming.

Generates realistic mock data for underlying and option instruments
when market is closed or live data unavailable.
"""
from __future__ import annotations

import asyncio
import random
import time
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Optional

from loguru import logger

from app.config import get_settings
from app.schema import Instrument, OptionSnapshot, DepthLevel, MarketDepth
from app.greeks_calculator import GreeksCalculator
from app.kite.client import KiteClient

settings = get_settings()


@dataclass(frozen=True)
class MockUnderlyingSnapshot:
    """Thread-safe immutable snapshot of mock underlying state"""
    symbol: str
    base_open: float
    base_high: float
    base_low: float
    base_close: float
    base_volume: int
    last_close: float
    timestamp: float


@dataclass
class _MockUnderlyingBuilder:
    """Internal mutable builder for mock underlying state (use ONLY under lock)"""
    symbol: str
    base_open: float
    base_high: float
    base_low: float
    base_close: float
    base_volume: int
    last_close: float

    def build_snapshot(self) -> MockUnderlyingSnapshot:
        """Create immutable snapshot from current builder state"""
        return MockUnderlyingSnapshot(
            symbol=self.symbol,
            base_open=self.base_open,
            base_high=self.base_high,
            base_low=self.base_low,
            base_close=self.base_close,
            base_volume=self.base_volume,
            last_close=self.last_close,
            timestamp=time.time(),
        )


@dataclass(frozen=True)
class MockOptionSnapshot:
    """Thread-safe immutable snapshot of mock option state"""
    instrument: Instrument
    base_price: float
    last_price: float
    base_volume: int
    base_oi: int
    iv: float
    delta: float
    gamma: float
    theta: float
    vega: float
    timestamp: float


@dataclass
class _MockOptionBuilder:
    """Internal mutable builder for mock option state (use ONLY under lock)"""
    instrument: Instrument
    base_price: float
    last_price: float
    base_volume: int
    base_oi: int
    iv: float
    delta: float
    gamma: float
    theta: float
    vega: float

    def build_snapshot(self) -> MockOptionSnapshot:
        """Create immutable snapshot from current builder state"""
        return MockOptionSnapshot(
            instrument=self.instrument,
            base_price=self.base_price,
            last_price=self.last_price,
            base_volume=self.base_volume,
            base_oi=self.base_oi,
            iv=self.iv,
            delta=self.delta,
            gamma=self.gamma,
            theta=self.theta,
            vega=self.vega,
            timestamp=time.time(),
        )


class MockDataGenerator:
    """
    Generates realistic mock data for option streaming.

    Responsibilities:
    - Seed mock state from live quotes/historical data
    - Generate mock underlying bars
    - Generate mock option snapshots
    - Cleanup expired mock state
    - LRU eviction for memory management
    """

    def __init__(
        self,
        market_tz,
        greeks_calculator: Optional[GreeksCalculator] = None,
        last_underlying_price_getter: Optional[callable] = None,
    ):
        """
        Initialize mock data generator.

        Args:
            market_tz: ZoneInfo timezone for market hours
            greeks_calculator: Optional GreeksCalculator for IV/Greeks
            last_underlying_price_getter: Optional callable to get current underlying price
        """
        self._market_tz = market_tz
        self._greeks_calculator = greeks_calculator or GreeksCalculator()
        self._get_last_underlying_price = last_underlying_price_getter

        # Builder + Snapshot pattern for thread-safe mock state
        self._mock_option_builders: OrderedDict[int, _MockOptionBuilder] = OrderedDict()
        self._mock_underlying_builder: _MockUnderlyingBuilder | None = None

        # Snapshots are immutable, safe to read without lock
        self._mock_option_snapshots: OrderedDict[int, MockOptionSnapshot] = OrderedDict()
        self._mock_underlying_snapshot: MockUnderlyingSnapshot | None = None

        # LRU eviction to prevent memory leak
        self._mock_state_max_size = settings.mock_state_max_size
        self._mock_seed_lock = asyncio.Lock()

    async def ensure_underlying_seeded(self, client: KiteClient) -> None:
        """
        Ensure mock underlying state is seeded.

        Args:
            client: KiteClient for fetching live quotes
        """
        # Quick check WITHOUT lock (safe - snapshot is immutable)
        if self._mock_underlying_snapshot is not None:
            return

        async with self._mock_seed_lock:
            # Double-check AFTER lock
            if self._mock_underlying_snapshot is not None:
                return

            try:
                quote = await client.get_quote([settings.nifty_quote_symbol])
            except Exception as exc:
                logger.error("Failed to seed mock underlying quote: %s", exc)
                return

            payload = quote.get(settings.nifty_quote_symbol)
            if not payload:
                logger.warning("Mock underlying seed missing quote for %s", settings.nifty_quote_symbol)
                return

            ohlc = payload.get("ohlc") or {}
            last_price = float(payload.get("last_price") or ohlc.get("close") or 0.0)
            if not last_price:
                logger.warning("Mock underlying seed missing price data for %s", settings.nifty_quote_symbol)
                return

            base_open = float(ohlc.get("open") or last_price)
            base_high = float(ohlc.get("high") or last_price)
            base_low = float(ohlc.get("low") or last_price)
            base_close = float(ohlc.get("close") or last_price)
            volume = int(payload.get("volume") or 0)
            if not volume:
                volume = 1000

            # Create builder (mutable, under lock)
            self._mock_underlying_builder = _MockUnderlyingBuilder(
                symbol=settings.fo_underlying or settings.nifty_symbol or "NIFTY",
                base_open=base_open,
                base_high=base_high,
                base_low=base_low,
                base_close=base_close,
                base_volume=volume,
                last_close=base_close,
            )

            # Create snapshot (immutable, for consumers)
            self._mock_underlying_snapshot = self._mock_underlying_builder.build_snapshot()

            logger.info("Seeded mock underlying state | symbol=%s close=%.2f volume=%d",
                        self._mock_underlying_snapshot.symbol,
                        self._mock_underlying_snapshot.last_close,
                        self._mock_underlying_snapshot.base_volume)

    async def generate_underlying_bar(self) -> Dict:
        """
        Generate mock underlying bar.

        Returns:
            Dict with OHLCV data
        """
        # Read snapshot (NO LOCK - immutable!)
        snapshot = self._mock_underlying_snapshot
        if snapshot is None:
            return {}

        # Generate new values based on snapshot
        variance = settings.mock_price_variation_bps / 10_000.0
        drift = random.uniform(-variance, variance)
        new_close = max(0.01, snapshot.last_close * (1 + drift))
        open_price = snapshot.last_close

        high = max(open_price, new_close, snapshot.base_high, new_close * (1 + variance))
        low = min(open_price, new_close, snapshot.base_low, new_close * (1 - variance))

        volume_variance = max(int(snapshot.base_volume * settings.mock_volume_variation), 50)
        volume = max(0, snapshot.base_volume + random.randint(-volume_variance, volume_variance))

        # Update builder UNDER LOCK, create new snapshot
        async with self._mock_seed_lock:
            if self._mock_underlying_builder:
                self._mock_underlying_builder.last_close = new_close
                self._mock_underlying_builder.base_close = (self._mock_underlying_builder.base_close * 0.9) + (new_close * 0.1)
                self._mock_underlying_builder.base_volume = max(100, int((self._mock_underlying_builder.base_volume * 0.8) + (volume * 0.2)))

                # Create NEW snapshot
                self._mock_underlying_snapshot = self._mock_underlying_builder.build_snapshot()

        return {
            "symbol": snapshot.symbol,
            "open": round(open_price, 2),
            "high": round(high, 2),
            "low": round(low, 2),
            "close": round(new_close, 2),
            "volume": volume,
            "ts": int(time.time()),
            "is_mock": False,
        }

    # ... Additional methods for option seeding, generation, cleanup ...
    # (Move from generator.py: _ensure_mock_option_seed, _seed_option_state,
    #  _generate_mock_option_snapshot, _cleanup_expired_mock_state, etc.)

    async def reset_state(self) -> None:
        """Reset all mock state"""
        async with self._mock_seed_lock:
            self._mock_option_builders.clear()
            self._mock_option_snapshots.clear()
            self._mock_underlying_builder = None
            self._mock_underlying_snapshot = None
```

### 2. Update MultiAccountTickerLoop to Use MockDataGenerator
**File**: `app/generator.py`

**In __init__**:
```python
def __init__(self, orchestrator: SessionOrchestrator | None = None, task_monitor: Optional[Any] = None):
    # ... existing code ...

    # NEW: Inject MockDataGenerator
    from app.services.mock_generator import MockDataGenerator
    self._mock_generator = MockDataGenerator(
        market_tz=self._market_tz,
        greeks_calculator=self._greeks_calculator,
        last_underlying_price_getter=lambda: self._last_underlying_price,
    )
```

**Replace all mock calls**:
```python
# OLD:
await self._ensure_mock_underlying_seed(client)
bar = await self._generate_mock_underlying_bar()
await self._ensure_mock_option_seed(client, instruments)
snapshot = await self._generate_mock_option_snapshot(instrument)
await self._reset_mock_state()

# NEW:
await self._mock_generator.ensure_underlying_seeded(client)
bar = await self._mock_generator.generate_underlying_bar()
await self._mock_generator.ensure_options_seeded(client, instruments)
snapshot = await self._mock_generator.generate_option_snapshot(instrument)
await self._mock_generator.reset_state()
```

**Delete old methods** (lines to remove):
- `_ensure_mock_underlying_seed`
- `_generate_mock_underlying_bar`
- `_ensure_mock_option_seed`
- `_seed_option_state`
- `_generate_mock_option_snapshot`
- `_cleanup_expired_mock_state`
- `_cleanup_expired_mock_state_internal`
- `_mock_state_cleanup_loop`
- All MockOption/MockUnderlying dataclasses

### 3. Update Tests
**File**: `tests/unit/test_mock_generator.py` (NEW)

Create unit tests for MockDataGenerator:
```python
import pytest
from app.services.mock_generator import MockDataGenerator


@pytest.mark.asyncio
async def test_underlying_seeding():
    """Test underlying state seeding from live quotes"""
    # ... test implementation ...


@pytest.mark.asyncio
async def test_option_seeding():
    """Test option state seeding"""
    # ... test implementation ...


@pytest.mark.asyncio
async def test_lru_eviction():
    """Test LRU eviction still works after extraction"""
    # ... test implementation ...
```

## CONSTRAINTS
- ✅ **100% backward compatible** - Same API surface
- ✅ **Move code, don't rewrite** - Extract as-is first
- ✅ **All existing tests pass** - No regressions
- ✅ **No performance impact** - Just reorganization

## TESTING REQUIREMENTS
- All mock state concurrency tests still pass
- All mock eviction tests still pass
- All mock cleanup tests still pass
- New unit tests for MockDataGenerator class

## VERIFICATION CHECKLIST
- [ ] MockDataGenerator class created
- [ ] All mock methods moved from generator.py
- [ ] MultiAccountTickerLoop uses injected MockDataGenerator
- [ ] All tests pass (old + new)
- [ ] generator.py line count reduced
- [ ] No circular imports

## DELIVERABLES
1. NEW: `app/services/mock_generator.py`
2. MODIFIED: `app/generator.py` (remove mock logic)
3. NEW: `tests/unit/test_mock_generator.py`
4. Updated existing tests if needed

Begin implementation. Report progress after each major step.
```

---

## PROMPT 2: EXTRACT SUBSCRIPTION RECONCILER
**Role**: Refactoring Specialist
**Priority**: MEDIUM
**Estimated Time**: 3-4 hours
**Files**: NEW: `app/services/subscription_reconciler.py`, MODIFY: `app/generator.py`

### Prompt

```text
You are a refactoring specialist extracting subscription reconciliation logic.

## OBJECTIVE
Extract subscription reload/reconciliation logic from MultiAccountTickerLoop into SubscriptionReconciler.

## CONTEXT
Lines 308-365 in generator.py handle subscription reconciliation with DB. This can be extracted into a focused service.

## REQUIREMENTS

### 1. Create SubscriptionReconciler Service
Create NEW file: `app/services/subscription_reconciler.py`

```python
"""
Subscription reconciliation service.

Syncs runtime subscription state with database, handles reload requests.
"""
from __future__ import annotations

import asyncio
from typing import Dict, List, Any

from loguru import logger

from app.subscription_store import subscription_store
from app.instrument_registry import instrument_registry
from app.schema import Instrument
from app.utils.subscription_reloader import SubscriptionReloader


class SubscriptionReconciler:
    """
    Manages subscription reconciliation and reloads.

    Responsibilities:
    - Load subscription plan from database
    - Build instrument assignments for accounts
    - Handle subscription reload requests
    - Coordinate with SubscriptionReloader for rate limiting
    """

    def __init__(self):
        """Initialize subscription reconciler"""
        self._subscription_reloader: SubscriptionReloader | None = None
        self._reload_callback: callable | None = None

    def initialize_reloader(self, reload_callback: callable) -> None:
        """
        Initialize the subscription reloader with callback.

        Args:
            reload_callback: Async function to call when reload needed
        """
        self._reload_callback = reload_callback
        self._subscription_reloader = SubscriptionReloader(
            reload_fn=reload_callback,
            debounce_seconds=1.0,
            max_reload_frequency_seconds=5.0,
        )

    async def start_reloader(self) -> None:
        """Start the subscription reloader background task"""
        if self._subscription_reloader:
            await self._subscription_reloader.start()

    async def stop_reloader(self) -> None:
        """Stop the subscription reloader background task"""
        if self._subscription_reloader:
            await self._subscription_reloader.stop()

    async def load_subscription_plan(self) -> List[Dict[str, Any]]:
        """
        Load active subscription plan from database.

        Returns:
            List of subscription records
        """
        all_records = await subscription_store.get_active_subscriptions()
        plan_items = []

        for record in all_records:
            try:
                instrument = await instrument_registry.get_by_token(record.instrument_token)
                if instrument:
                    plan_items.append({
                        "record": record,
                        "instrument": instrument,
                    })
            except Exception as exc:
                logger.warning(
                    "Failed to resolve instrument for token %s: %s",
                    record.instrument_token,
                    exc,
                )

        logger.info(f"Loaded {len(plan_items)} active subscriptions from DB")
        return plan_items

    async def build_assignments(
        self,
        plan_items: List[Dict],
        available_accounts: List[str],
    ) -> Dict[str, List[Instrument]]:
        """
        Build instrument assignments for accounts.

        Args:
            plan_items: List of {record, instrument} dicts
            available_accounts: List of account IDs

        Returns:
            Dict mapping account_id -> list of instruments
        """
        if not available_accounts:
            return {}

        # Round-robin assignment
        assignments: Dict[str, List[Instrument]] = {acc: [] for acc in available_accounts}

        for idx, item in enumerate(plan_items):
            account_id = available_accounts[idx % len(available_accounts)]
            assignments[account_id].append(item["instrument"])

        # Filter out empty assignments
        return {acc: insts for acc, insts in assignments.items() if insts}

    def trigger_reload(self) -> None:
        """Trigger a subscription reload (non-blocking)"""
        if self._subscription_reloader:
            self._subscription_reloader.trigger_reload()
        else:
            logger.warning("Subscription reloader not initialized, ignoring reload trigger")

    async def reload_subscriptions_blocking(self) -> None:
        """Blocking reload of subscriptions (for API endpoint)"""
        if self._reload_callback:
            await self._reload_callback()
        else:
            logger.warning("Reload callback not set, cannot perform reload")
```

### 2. Update MultiAccountTickerLoop
**File**: `app/generator.py`

**In __init__**:
```python
from app.services.subscription_reconciler import SubscriptionReconciler

self._reconciler = SubscriptionReconciler()
```

**In start()**:
```python
# Replace _load_subscription_plan():
plan_items = await self._reconciler.load_subscription_plan()

# Replace _build_assignments():
assignments = await self._reconciler.build_assignments(plan_items, available_accounts)

# Initialize reloader:
self._reconciler.initialize_reloader(self._perform_reload)
await self._reconciler.start_reloader()
```

**In stop()**:
```python
await self._reconciler.stop_reloader()
```

**Delete old methods**:
- `_load_subscription_plan`
- `_build_assignments`

## CONSTRAINTS
- ✅ **100% backward compatible**
- ✅ **Preserve reload logic exactly**
- ✅ **All tests pass**

## DELIVERABLES
1. NEW: `app/services/subscription_reconciler.py`
2. MODIFIED: `app/generator.py`
3. NEW: `tests/unit/test_subscription_reconciler.py`

Begin implementation.
```

---

## PROMPT 3: EXTRACT HISTORICAL BOOTSTRAPPER
**Role**: Refactoring Specialist
**Priority**: LOW
**Estimated Time**: 3-4 hours
**Files**: NEW: `app/services/historical_bootstrapper.py`, MODIFY: `app/generator.py`

### Prompt

```text
You are a refactoring specialist extracting historical data backfill logic.

## OBJECTIVE
Extract historical bootstrapping logic into dedicated HistoricalBootstrapper service.

## CONTEXT
Lines 966-1088 in generator.py handle historical data backfill. This can be extracted.

## REQUIREMENTS

### 1. Create HistoricalBootstrapper Service
Create NEW file: `app/services/historical_bootstrapper.py`

```python
"""
Historical data bootstrapping service.

Backfills missing historical data for option instruments.
"""
from __future__ import annotations

import asyncio
from typing import Dict, List
from datetime import datetime, timedelta

from loguru import logger

from app.schema import Instrument
from app.kite.client import KiteClient
from app.config import get_settings

settings = get_settings()


class HistoricalBootstrapper:
    """
    Manages historical data backfill for option instruments.

    Responsibilities:
    - Determine which accounts need historical bootstrap
    - Batch historical data requests
    - Coordinate with KiteClient for API calls
    """

    def __init__(self):
        """Initialize bootstrapper"""
        self._bootstrap_done: Dict[str, bool] = {}

    def is_bootstrap_done(self, account_id: str) -> bool:
        """Check if account has been bootstrapped"""
        return self._bootstrap_done.get(account_id, False)

    def mark_bootstrap_done(self, account_id: str) -> None:
        """Mark account as bootstrapped"""
        self._bootstrap_done[account_id] = True

    def reset_bootstrap_state(self) -> None:
        """Reset all bootstrap state"""
        self._bootstrap_done.clear()

    async def backfill_missing_history(
        self,
        account_id: str,
        instruments: List[Instrument],
        client: KiteClient,
    ) -> None:
        """
        Backfill missing historical data for instruments.

        Args:
            account_id: Account ID for logging
            instruments: List of instruments to backfill
            client: KiteClient for API calls
        """
        if self.is_bootstrap_done(account_id):
            logger.debug(f"Historical bootstrap already done for {account_id}, skipping")
            return

        logger.info(f"Starting historical bootstrap for {account_id} ({len(instruments)} instruments)")

        # Backfill logic moved from generator.py
        # ... (copy _backfill_missing_history implementation)

        self.mark_bootstrap_done(account_id)
        logger.info(f"Historical bootstrap complete for {account_id}")
```

### 2. Update MultiAccountTickerLoop
**File**: `app/generator.py`

```python
from app.services.historical_bootstrapper import HistoricalBootstrapper

# In __init__:
self._bootstrapper = HistoricalBootstrapper()

# In _stream_account:
if not self._bootstrapper.is_bootstrap_done(account_id):
    await self._bootstrapper.backfill_missing_history(account_id, instruments, client)

# In stop:
self._bootstrapper.reset_bootstrap_state()
```

**Delete**:
- `_historical_bootstrap_done` dict
- `_backfill_missing_history` method

## DELIVERABLES
1. NEW: `app/services/historical_bootstrapper.py`
2. MODIFIED: `app/generator.py`
3. NEW: `tests/unit/test_historical_bootstrapper.py`

Begin implementation.
```

---

## PROMPT 4: CREATE INTEGRATION TESTS
**Role**: QA Engineer
**Priority**: HIGH
**Estimated Time**: 2-3 hours
**Files**: NEW: `tests/integration/test_refactored_components.py`

### Prompt

```text
You are a QA engineer creating integration tests for refactored components.

## OBJECTIVE
Create integration tests that verify all extracted services work together correctly.

## REQUIREMENTS

Create `tests/integration/test_refactored_components.py`:

```python
"""
Integration tests for refactored Phase 2 components.

Verifies MockDataGenerator, SubscriptionReconciler, and HistoricalBootstrapper
work correctly when integrated with MultiAccountTickerLoop.
"""
import pytest
from app.generator import MultiAccountTickerLoop
from app.services.mock_generator import MockDataGenerator
from app.services.subscription_reconciler import SubscriptionReconciler
from app.services.historical_bootstrapper import HistoricalBootstrapper


@pytest.mark.asyncio
async def test_mock_generator_integration():
    """Test MockDataGenerator integrates correctly with ticker loop"""
    ticker_loop = MultiAccountTickerLoop()

    # Verify mock generator injected
    assert ticker_loop._mock_generator is not None
    assert isinstance(ticker_loop._mock_generator, MockDataGenerator)

    # Test mock data generation still works
    # ... assertions ...


@pytest.mark.asyncio
async def test_subscription_reconciler_integration():
    """Test SubscriptionReconciler integrates correctly"""
    ticker_loop = MultiAccountTickerLoop()

    # Verify reconciler injected
    assert ticker_loop._reconciler is not None
    assert isinstance(ticker_loop._reconciler, SubscriptionReconciler)

    # Test subscription loading still works
    # ... assertions ...


@pytest.mark.asyncio
async def test_historical_bootstrapper_integration():
    """Test HistoricalBootstrapper integrates correctly"""
    ticker_loop = MultiAccountTickerLoop()

    # Verify bootstrapper injected
    assert ticker_loop._bootstrapper is not None
    assert isinstance(ticker_loop._bootstrapper, HistoricalBootstrapper)

    # Test bootstrap tracking still works
    # ... assertions ...


@pytest.mark.asyncio
async def test_end_to_end_lifecycle():
    """Test complete start/stop lifecycle with refactored components"""
    ticker_loop = MultiAccountTickerLoop()

    # Should be able to start and stop cleanly
    await ticker_loop.start()
    await asyncio.sleep(1)
    await ticker_loop.stop()

    # Verify all components cleaned up
    # ... assertions ...
```

## DELIVERABLES
1. Comprehensive integration tests
2. End-to-end lifecycle tests
3. >90% coverage of integration paths

Begin implementation.
```

---

## PROMPT 5: FINAL CLEANUP & DOCUMENTATION
**Role**: Tech Lead
**Priority**: HIGH
**Estimated Time**: 2-3 hours
**Files**: MODIFY: `app/generator.py`, NEW: `PHASE2_IMPLEMENTATION_COMPLETE.md`

### Prompt

```text
You are a tech lead finalizing Phase 2 refactoring.

## OBJECTIVE
Final cleanup, documentation, and verification of Phase 2 refactoring.

## REQUIREMENTS

### 1. Verify Line Count Reduction
**File**: `app/generator.py`

Target: Reduce from 1,184 lines to <600 lines

Run:
```bash
wc -l app/generator.py
```

Expected: ~400-600 lines (50% reduction)

### 2. Create Services Directory
Ensure all services properly organized:

```
app/services/
├── __init__.py
├── mock_generator.py
├── subscription_reconciler.py
└── historical_bootstrapper.py
```

### 3. Update Documentation
Create `PHASE2_IMPLEMENTATION_COMPLETE.md`:

```markdown
# Phase 2 Implementation Complete

## Summary
Successfully refactored MultiAccountTickerLoop God Class anti-pattern.

## Metrics
- **Before**: 1,184 lines, 5+ responsibilities
- **After**: <600 lines, focused orchestration
- **Extracted Services**: 3
- **Test Coverage**: >85%

## Services Extracted
1. MockDataGenerator - Mock data generation
2. SubscriptionReconciler - Subscription management
3. HistoricalBootstrapper - Historical data backfill

## Test Results
- All Phase 1 tests: PASS
- All Phase 2 tests: PASS
- Integration tests: PASS
- Total: XX/XX tests passing

## Benefits
- Improved maintainability
- Better testability
- Reduced coupling
- Clear separation of concerns
```

### 4. Run Full Test Suite
```bash
.venv/bin/python -m pytest -v
```

Verify ALL tests pass (Phase 1 + Phase 2).

### 5. Create services/__init__.py
```python
"""
Extracted services from MultiAccountTickerLoop refactoring.

Phase 2 implementation - extracted God Class anti-pattern.
"""
from .mock_generator import MockDataGenerator
from .subscription_reconciler import SubscriptionReconciler
from .historical_bootstrapper import HistoricalBootstrapper

__all__ = [
    "MockDataGenerator",
    "SubscriptionReconciler",
    "HistoricalBootstrapper",
]
```

## VERIFICATION CHECKLIST
- [ ] generator.py <600 lines
- [ ] All services in app/services/
- [ ] All Phase 1 tests pass
- [ ] All Phase 2 tests pass
- [ ] Integration tests pass
- [ ] Documentation complete
- [ ] No circular imports
- [ ] No performance regression

## DELIVERABLES
1. MODIFIED: `app/generator.py` (reduced size)
2. NEW: `app/services/__init__.py`
3. NEW: `PHASE2_IMPLEMENTATION_COMPLETE.md`
4. Verification that all tests pass

Begin implementation.
```

---

## IMPLEMENTATION ORDER

Execute prompts in sequence:

```
Day 1: PROMPT 1 (Extract MockDataGenerator)
       ↓
Day 2: PROMPT 2 (Extract SubscriptionReconciler)
       ↓
Day 3: PROMPT 3 (Extract HistoricalBootstrapper)
       ↓
Day 4: PROMPT 4 (Integration Tests)
       ↓
Day 5: PROMPT 5 (Final Cleanup & Documentation)
```

---

## SUCCESS CRITERIA

### Before Phase 2
- generator.py: 1,184 lines
- God Class with 5+ responsibilities
- Difficult to test
- High coupling

### After Phase 2
- generator.py: <600 lines (50% reduction)
- Clear separation of concerns
- 3 focused services
- >85% test coverage
- All tests passing
- 100% backward compatible

---

## ROLLBACK PLAN

If issues arise:
1. All changes in feature branch
2. Can revert to Phase 1 complete state
3. Services are opt-in (can disable and fall back)
4. Zero API changes (backward compatible)

---

**Prerequisites**: Phase 1 Complete ✅
**Estimated Total Time**: 16-20 hours
**Risk**: Medium (refactoring, but well-tested)
**Benefit**: High (maintainability, testability)
