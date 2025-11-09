# P1 HIGH: Eliminate Global Singletons via Dependency Injection

**Role:** Senior Backend Engineer
**Priority:** P1 - HIGH (Testability & Maintainability)
**Estimated Effort:** 16 hours
**Dependencies:** None
**Target:** Remove all 19 global singletons

---

## Objective

Replace global singleton anti-pattern with FastAPI dependency injection to improve testability, enable multiple instances for testing, and eliminate hidden dependencies.

**Current State:** 19 global singleton instances
**Impact:** Impossible to test in isolation, thread safety concerns, hidden initialization order dependencies

---

## Context

From Code Review (Phase 3):
> **CR-001: Global Singleton Anti-Pattern (19 Instances)** - CRITICAL
>
> Problems:
> - Hidden dependencies make testing difficult
> - Impossible to create multiple instances for testing
> - Race conditions during initialization
> - Thread-safety concerns with lazy initialization

---

## Affected Modules

```python
# Current global singletons (19 instances)
app/accounts.py:            get_orchestrator()
app/order_executor.py:      get_executor()
app/redis_publisher_v2.py:  get_resilient_publisher()
app/subscription_store.py:  subscription_store
app/instrument_registry.py: instrument_registry
app/greeks_calculator.py:   get_greeks_calculator()
# ... 13 more instances
```

---

## Refactoring Strategy

### Before (Anti-Pattern):
```python
# app/order_executor.py
_executor_instance: OrderExecutor | None = None

def get_executor() -> OrderExecutor:
    """Global singleton - ANTI-PATTERN"""
    global _executor_instance
    if _executor_instance is None:
        _executor_instance = OrderExecutor()
    return _executor_instance

# app/routes_orders.py
from app.order_executor import get_executor

@app.post("/orders")
async def place_order(order: OrderRequest):
    executor = get_executor()  # Hidden global dependency!
    return await executor.submit(order)
```

### After (Dependency Injection):
```python
# app/dependencies.py (NEW FILE)
from fastapi import Request, Depends
from app.order_executor import OrderExecutor
from app.accounts import SessionOrchestrator
from app.redis_publisher_v2 import ResilientRedisPublisher

def get_executor_dep(request: Request) -> OrderExecutor:
    """Dependency injection for OrderExecutor"""
    return request.app.state.executor

def get_orchestrator_dep(request: Request) -> SessionOrchestrator:
    """Dependency injection for SessionOrchestrator"""
    return request.app.state.orchestrator

def get_redis_publisher_dep(request: Request) -> ResilientRedisPublisher:
    """Dependency injection for ResilientRedisPublisher"""
    return request.app.state.redis_publisher

# app/main.py - Initialize during startup
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Initialize all singletons during startup
    app.state.executor = OrderExecutor(max_tasks=10000)
    app.state.orchestrator = SessionOrchestrator()
    app.state.redis_publisher = ResilientRedisPublisher()
    app.state.greeks_calculator = GreeksCalculator()
    app.state.subscription_store = SubscriptionStore()
    app.state.instrument_registry = InstrumentRegistry()

    # Start background workers
    await app.state.executor.start_worker()
    await app.state.orchestrator.initialize()

    try:
        yield  # Application runs
    finally:
        # Cleanup on shutdown
        await app.state.executor.stop_worker()
        await app.state.orchestrator.shutdown()
        await app.state.redis_publisher.close()

app = FastAPI(lifespan=lifespan)

# app/routes_orders.py - Explicit dependencies
from app.dependencies import get_executor_dep

@app.post("/orders")
async def place_order(
    order: OrderRequest,
    executor: OrderExecutor = Depends(get_executor_dep)  # Explicit!
):
    """Place order with injected executor"""
    return await executor.submit(order)
```

---

## Implementation Tasks

### Task 1: Create Dependency Injection Module (2 hours)

Create `app/dependencies.py`:
```python
from fastapi import Request
from typing import Annotated
from app.order_executor import OrderExecutor
from app.accounts import SessionOrchestrator
from app.redis_publisher_v2 import ResilientRedisPublisher
from app.greeks_calculator import GreeksCalculator
from app.subscription_store import SubscriptionStore
from app.instrument_registry import InstrumentRegistry
from app.generator import MultiAccountTickerLoop

# Type aliases for dependency injection
ExecutorDep = Annotated[OrderExecutor, Depends(get_executor_dep)]
OrchestratorDep = Annotated[SessionOrchestrator, Depends(get_orchestrator_dep)]
RedisPublisherDep = Annotated[ResilientRedisPublisher, Depends(get_redis_publisher_dep)]
GreeksCalculatorDep = Annotated[GreeksCalculator, Depends(get_greeks_calculator_dep)]

def get_executor_dep(request: Request) -> OrderExecutor:
    return request.app.state.executor

def get_orchestrator_dep(request: Request) -> SessionOrchestrator:
    return request.app.state.orchestrator

def get_redis_publisher_dep(request: Request) -> ResilientRedisPublisher:
    return request.app.state.redis_publisher

def get_greeks_calculator_dep(request: Request) -> GreeksCalculator:
    return request.app.state.greeks_calculator

def get_subscription_store_dep(request: Request) -> SubscriptionStore:
    return request.app.state.subscription_store

def get_instrument_registry_dep(request: Request) -> InstrumentRegistry:
    return request.app.state.instrument_registry

def get_ticker_loop_dep(request: Request) -> MultiAccountTickerLoop:
    return request.app.state.ticker_loop
```

---

### Task 2: Update main.py Lifespan (2 hours)

```python
# app/main.py

from contextlib import asynccontextmanager
from app.order_executor import OrderExecutor
from app.accounts import SessionOrchestrator
from app.redis_publisher_v2 import ResilientRedisPublisher
from app.greeks_calculator import GreeksCalculator
from app.subscription_store import SubscriptionStore
from app.instrument_registry import InstrumentRegistry
from app.generator import MultiAccountTickerLoop

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and cleanup application dependencies"""

    # 1. Initialize database connections
    app.state.db_pool = await asyncpg.create_pool(
        database=settings.instrument_db_name,
        user=settings.instrument_db_user,
        password=settings.instrument_db_password,
        host=settings.instrument_db_host,
        port=settings.instrument_db_port,
        min_size=5,
        max_size=20
    )

    # 2. Initialize registries (depend on DB)
    app.state.instrument_registry = InstrumentRegistry(app.state.db_pool)
    await app.state.instrument_registry.load_instruments()

    app.state.subscription_store = SubscriptionStore(app.state.db_pool)

    # 3. Initialize calculators (stateless)
    app.state.greeks_calculator = GreeksCalculator()

    # 4. Initialize publishers (depend on Redis)
    app.state.redis_publisher = ResilientRedisPublisher(
        redis_url=settings.redis_url
    )
    await app.state.redis_publisher.initialize()

    # 5. Initialize orchestrator (depends on DB, Redis)
    app.state.orchestrator = SessionOrchestrator(
        db_pool=app.state.db_pool
    )
    await app.state.orchestrator.initialize()

    # 6. Initialize executor (depends on orchestrator)
    app.state.executor = OrderExecutor(
        max_tasks=settings.max_order_tasks,
        orchestrator=app.state.orchestrator
    )
    await app.state.executor.start_worker()

    # 7. Initialize ticker loop (depends on all above)
    app.state.ticker_loop = MultiAccountTickerLoop(
        orchestrator=app.state.orchestrator,
        redis_publisher=app.state.redis_publisher,
        greeks_calculator=app.state.greeks_calculator,
        subscription_store=app.state.subscription_store,
        instrument_registry=app.state.instrument_registry
    )
    await app.state.ticker_loop.start()

    logger.info("Application initialized successfully")

    try:
        yield  # Application runs
    finally:
        # Shutdown in reverse order
        logger.info("Shutting down application...")

        await app.state.ticker_loop.stop()
        await app.state.executor.stop_worker()
        await app.state.orchestrator.shutdown()
        await app.state.redis_publisher.close()
        await app.state.db_pool.close()

        logger.info("Application shutdown complete")

app = FastAPI(lifespan=lifespan)
```

---

### Task 3: Update All Route Handlers (6 hours)

```python
# app/routes_orders.py
from app.dependencies import ExecutorDep, OrchestratorDep

@app.post("/orders")
async def place_order(
    order: OrderRequest,
    executor: ExecutorDep  # Injected dependency!
):
    """Place order using dependency injection"""
    order_id = await executor.submit(order)
    return {"order_id": order_id, "status": "submitted"}

@app.get("/orders/{order_id}")
async def get_order(
    order_id: str,
    executor: ExecutorDep
):
    """Get order status"""
    return await executor.get_task(order_id)

# app/routes_subscriptions.py
from app.dependencies import SubscriptionStoreDep, TickerLoopDep

@app.post("/subscriptions")
async def create_subscription(
    subscription: SubscriptionRequest,
    subscription_store: SubscriptionStoreDep,
    ticker_loop: TickerLoopDep
):
    """Create subscription with injected dependencies"""
    await subscription_store.add_subscription(subscription)
    await ticker_loop.reload_subscriptions()
    return {"status": "subscribed"}

# Update ALL 50+ endpoints similarly
```

---

### Task 4: Update Tests for Dependency Injection (4 hours)

```python
# tests/unit/test_order_executor.py

import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, AsyncMock
from app.main import app
from app.order_executor import OrderExecutor

@pytest.fixture
def mock_executor():
    """Create mock executor for testing"""
    executor = Mock(spec=OrderExecutor)
    executor.submit = AsyncMock(return_value="ORDER_123")
    executor.get_task = AsyncMock(return_value={"status": "completed"})
    return executor

@pytest.fixture
def client_with_mock_executor(mock_executor):
    """Test client with mocked executor"""
    # Override dependency
    app.state.executor = mock_executor
    return TestClient(app)

def test_place_order_with_mock(client_with_mock_executor, mock_executor):
    """Test order placement with mocked executor"""
    # ARRANGE
    order_data = {
        "account_id": "primary",
        "tradingsymbol": "INFY",
        "exchange": "NSE",
        "transaction_type": "BUY",
        "quantity": 1,
        "product": "CNC",
        "order_type": "MARKET"
    }

    # ACT
    response = client_with_mock_executor.post("/orders", json=order_data)

    # ASSERT
    assert response.status_code == 200
    assert response.json()["order_id"] == "ORDER_123"
    mock_executor.submit.assert_called_once()
```

---

### Task 5: Remove Old Global Singleton Code (2 hours)

```bash
# Delete all global singleton getters

# 1. Find all global singleton patterns
grep -r "global _.*_instance" app/

# 2. Remove getter functions
# app/order_executor.py - DELETE
def get_executor() -> OrderExecutor:
    global _executor_instance
    ...

# app/accounts.py - DELETE
def get_orchestrator() -> SessionOrchestrator:
    global _orchestrator_instance
    ...

# ... delete all 19 instances

# 3. Update imports across codebase
# Find all imports of deleted functions
grep -r "from app.order_executor import get_executor" .

# Replace with dependency injection
# Before:
from app.order_executor import get_executor
executor = get_executor()

# After:
from app.dependencies import get_executor_dep
# Use Depends(get_executor_dep) in route handlers
```

---

## Testing Strategy

### 1. Unit Tests (Now Possible!)

```python
def test_order_executor_isolated():
    """Test executor in complete isolation"""
    # Before: Impossible (global singleton)
    # After: Easy!

    executor = OrderExecutor(max_tasks=10)
    # Test with specific config, no global state!
```

### 2. Integration Tests

```python
@pytest.fixture
def app_with_test_deps():
    """Create app with test dependencies"""
    test_app = FastAPI()

    # Inject test-specific dependencies
    test_app.state.executor = OrderExecutor(max_tasks=5)  # Different config!
    test_app.state.redis_publisher = MockRedisPublisher()

    return test_app
```

### 3. Parallel Test Execution

```python
# Now possible! Each test gets its own instance
pytest tests/ -n 8  # Run 8 tests in parallel
```

---

## Migration Checklist

- [ ] Create app/dependencies.py with all dependency functions
- [ ] Update app/main.py with lifespan manager
- [ ] Update all route handlers (50+ endpoints) to use Depends()
- [ ] Update all tests to inject mock dependencies
- [ ] Delete old global singleton getters
- [ ] Remove global state variables (_instance, etc.)
- [ ] Update documentation
- [ ] Full test suite passes
- [ ] No flaky tests due to shared state

---

## Rollback Plan

```bash
# If issues found, can revert incrementally
git revert <commit_hash>

# Old global singletons preserved in git history
# Can cherry-pick specific modules if needed
```

---

## Acceptance Criteria

- [ ] Zero global singleton functions remaining
- [ ] All dependencies injected via Depends()
- [ ] Tests can run in parallel
- [ ] Tests can use mock dependencies easily
- [ ] No shared global state
- [ ] Full test suite passes (100%)
- [ ] No performance regression
- [ ] Documentation updated

---

## Sign-Off

- [ ] Backend Lead: _____________________ Date: _____
- [ ] Architecture Lead: _____________________ Date: _____
- [ ] QA Lead: _____________________ Date: _____
