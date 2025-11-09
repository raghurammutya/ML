# Dependency Injection Refactor - Implementation Plan

**Created:** 2025-11-09 04:20 UTC
**Status:** PLANNED (Not yet executed)
**Estimated Effort:** 16-20 hours
**Priority:** P1 - HIGH (Not blocking production)

---

## Current State Analysis

### Global Singletons Found

```python
# app/accounts.py
_orchestrator_instance: SessionOrchestrator | None = None

def get_orchestrator() -> SessionOrchestrator:
    global _orchestrator_instance
    ...

# app/crypto.py
_encryption_instance: CredentialEncryption | None = None

def get_encryption() -> CredentialEncryption:
    global _encryption_instance
    ...

# Additional global state:
# - app/generator.py: ticker_loop (module-level instance)
# - app/subscription_store.py: subscription_store (module-level instance)
# - app/instrument_registry.py: instrument_registry (module-level instance)
# - app/redis_client.py: redis_publisher (module-level instance)
```

### Current Initialization (app/main.py)

The application already has a `lifespan` context manager that:
1. Initializes `redis_publisher` (module-level global)
2. Initializes account store
3. Starts `ticker_loop` (module-level global)
4. Initializes trade sync service
5. Starts strike rebalancer
6. Initializes OrderExecutor via `init_executor()`

### Problem

Most components are accessed as module-level globals:
```python
# Current pattern (BAD)
from app.generator import ticker_loop
from app.subscription_store import subscription_store
from app.instrument_registry import instrument_registry

# Used directly in routes
ticker_loop.do_something()
subscription_store.get_subscriptions()
```

This makes testing difficult because:
- Can't easily mock dependencies
- Can't run tests in parallel
- Hidden initialization dependencies
- Shared state between tests

---

## Proposed Solution

### Phase 1: Create Dependency Injection Infrastructure ✅ DONE

**File:** `app/dependencies.py` (created)

Provides dependency injection functions:
- `get_orchestrator_dep(request) -> SessionOrchestrator`
- `get_encryption_dep(request) -> CredentialEncryption`
- `get_ticker_loop_dep(request) -> MultiAccountTickerLoop`
- `get_greeks_calculator_dep(request) -> GreeksCalculator`
- `get_instrument_registry_dep(request) -> InstrumentRegistry`
- `get_executor_dep(request) -> OrderExecutor`
- `get_redis_publisher_dep(request) -> ResilientRedisPublisher`
- `get_subscription_store_dep(request) -> SubscriptionStore`

Type aliases for convenience:
- `OrchestratorDep`
- `EncryptionDep`
- `TickerLoopDep`
- etc.

### Phase 2: Update main.py Lifespan Manager

**Current pattern:**
```python
await redis_publisher.connect()
await ticker_loop.start()
```

**Proposed pattern:**
```python
# Initialize and attach to app.state
app.state.redis_publisher = ResilientRedisPublisher(...)
await app.state.redis_publisher.connect()

app.state.ticker_loop = MultiAccountTickerLoop(...)
await app.state.ticker_loop.start()

app.state.orchestrator = SessionOrchestrator(...)
app.state.encryption = CredentialEncryption(...)
# etc.
```

**Complexity:** MEDIUM
- Many components have complex initialization
- Some components depend on each other (initialization order matters)
- Need to ensure backward compatibility during migration

### Phase 3: Update Route Handlers

**Affected Files:** 50+ endpoints across multiple route files

**Before:**
```python
from app.generator import ticker_loop

@app.get("/status")
async def get_status():
    return ticker_loop.get_status()
```

**After:**
```python
from app.dependencies import TickerLoopDep

@app.get("/status")
async def get_status(ticker_loop: TickerLoopDep):
    return ticker_loop.get_status()
```

**Complexity:** HIGH
- Manual inspection of 50+ endpoints required
- Risk of missing dependencies
- Need to test each endpoint after modification

### Phase 4: Remove Global Singletons

**Delete singleton getters:**
```python
# app/accounts.py - DELETE
def get_orchestrator() -> SessionOrchestrator:
    ...

# app/crypto.py - DELETE
def get_encryption() -> CredentialEncryption:
    ...
```

**Update module-level globals:**
```python
# app/generator.py - REFACTOR
# Before:
ticker_loop = MultiAccountTickerLoop()

# After:
# Remove module-level instance, create in main.py lifespan
```

**Complexity:** HIGH
- Need to ensure no code still references old globals
- Backward compatibility concerns
- Risk of runtime errors if references missed

### Phase 5: Update Tests

**Update test fixtures:**
```python
# Before:
def test_something():
    from app.generator import ticker_loop
    # ticker_loop is global singleton

# After:
@pytest.fixture
def app_with_mocks():
    app = FastAPI()
    app.state.ticker_loop = Mock(spec=MultiAccountTickerLoop)
    return app

def test_something(app_with_mocks):
    client = TestClient(app_with_mocks)
    # Use injected mock
```

**Complexity:** MEDIUM
- Need to update all existing tests
- Some tests may break due to dependency changes
- Need comprehensive testing after refactor

---

## Implementation Risks

### HIGH RISK

1. **Breaking Production Code**
   - Extensive changes to core application structure
   - Risk of missing global references
   - Initialization order dependencies

2. **Testing Complexity**
   - All tests need updating
   - Risk of test failures cascading
   - Hard to isolate issues

3. **Rollback Difficulty**
   - Large number of files modified
   - Hard to revert partial changes
   - May require multiple commits

### MEDIUM RISK

4. **Initialization Order**
   - Some components depend on others (orchestrator needs DB, ticker_loop needs orchestrator)
   - Current implicit ordering may break
   - Need to explicitly document dependencies

5. **Performance Impact**
   - Dependency injection adds minimal overhead
   - Need to validate no performance regression
   - May affect startup time

### LOW RISK

6. **Type Safety**
   - FastAPI's Depends() provides good type checking
   - Should catch most issues at development time
   - IDE support for dependency injection

---

## Recommended Approach

### Option A: Full Refactor (16-20 hours)

**Pros:**
- Eliminates all global state
- Enables parallel test execution
- Improves long-term maintainability

**Cons:**
- High risk of regressions
- Extensive testing required
- Blocks other development

**Recommendation:** NOT RECOMMENDED for current sprint

### Option B: Incremental Migration (Phase-by-phase)

**Phase 1 (COMPLETED):** Create dependency injection infrastructure
**Phase 2 (Week 1):** Update main.py lifespan, attach to app.state
**Phase 3 (Week 2):** Update route handlers incrementally (5-10 endpoints/day)
**Phase 4 (Week 3):** Remove old globals, ensure backward compatibility
**Phase 5 (Week 4):** Update tests, full validation

**Pros:**
- Lower risk per change
- Can test incrementally
- Easy to rollback individual phases
- Doesn't block other work

**Cons:**
- Longer overall timeline (4 weeks)
- Mixed patterns during migration
- Need to maintain both old and new patterns

**Recommendation:** RECOMMENDED approach

### Option C: Defer to Post-Launch (RECOMMENDED)

**Do Now:**
- ✅ Create dependency injection infrastructure (DONE)
- ✅ Document implementation plan (DONE)
- Add to technical debt backlog

**Do After Launch:**
- Schedule 4-week sprint for incremental migration
- Dedicate QA resources for testing
- Plan production monitoring

**Pros:**
- Zero risk to current launch
- Can plan resources properly
- Can learn from production usage first

**Cons:**
- Technical debt accumulates
- Longer time with testability issues

**Recommendation:** STRONGLY RECOMMENDED

---

## Decision Matrix

| Criteria | Option A (Full) | Option B (Incremental) | Option C (Defer) |
|----------|----------------|----------------------|-----------------|
| Risk to Launch | ⚠️ HIGH | ⚠️ MEDIUM | ✅ NONE |
| Time Required | 16-20 hours | 4 weeks | 0 hours now |
| Testing Effort | ⚠️ HIGH | ✅ MEDIUM | ✅ NONE |
| Rollback Ease | ❌ DIFFICULT | ⚠️ MODERATE | ✅ N/A |
| Long-term Value | ✅ HIGH | ✅ HIGH | ✅ HIGH (later) |
| **RECOMMENDATION** | ❌ NO | ⚠️ MAYBE | ✅ YES |

---

## Implementation Checklist (When Executed)

### Phase 1: Infrastructure ✅ DONE
- [x] Create `app/dependencies.py`
- [x] Define all dependency functions
- [x] Create type aliases

### Phase 2: Lifespan Manager (2 hours)
- [ ] Update `app/main.py` lifespan
- [ ] Initialize components and attach to `app.state`
- [ ] Maintain backward compatibility with module globals
- [ ] Test startup/shutdown

### Phase 3: Route Handlers (8 hours)
- [ ] Update `routes_account.py` (5 endpoints)
- [ ] Update `routes_orders.py` (15 endpoints)
- [ ] Update `routes_portfolio.py` (3 endpoints)
- [ ] Update `routes_gtt.py` (8 endpoints)
- [ ] Update `routes_mf.py` (10 endpoints)
- [ ] Update `routes_trading_accounts.py` (10 endpoints)
- [ ] Update `routes_advanced.py` (20 endpoints)
- [ ] Update WebSocket routes
- [ ] Test each route after modification

### Phase 4: Remove Globals (2 hours)
- [ ] Delete `get_orchestrator()` from `accounts.py`
- [ ] Delete `get_encryption()` from `crypto.py`
- [ ] Remove module-level globals (ticker_loop, etc.)
- [ ] Search codebase for remaining references
- [ ] Fix any lingering imports

### Phase 5: Update Tests (4 hours)
- [ ] Create test fixtures with mocked dependencies
- [ ] Update all unit tests
- [ ] Update all integration tests
- [ ] Run full test suite
- [ ] Fix any failures

### Phase 6: Validation (2 hours)
- [ ] Full test suite passes
- [ ] Manual testing of all endpoints
- [ ] Performance testing (no regressions)
- [ ] Documentation updated
- [ ] Code review

---

## Success Metrics

**Pre-Refactor:**
- Global singletons: 8+
- Module-level instances: 5+
- Tests can run in parallel: NO
- Easy to mock dependencies: NO

**Post-Refactor:**
- Global singletons: 0
- Module-level instances: 0
- Tests can run in parallel: YES
- Easy to mock dependencies: YES
- Performance regression: <1%
- Test pass rate: 100%

---

## Conclusion

**Current Status:** Phase 1 (Infrastructure) COMPLETED

**Recommended Next Steps:**
1. **Approve deferral** to post-launch sprint
2. **Create JIRA ticket** for tracking
3. **Schedule 4-week sprint** after production deployment
4. **Assign dedicated QA resources** for testing
5. **Plan production monitoring** during migration

**Production Impact:** ZERO (infrastructure created but not yet used)

**Long-term Value:** HIGH (improves testability, maintainability, parallel testing)

---

**Sign-Off Required:**
- [ ] Engineering Lead: _____________________ Date: _____
- [ ] QA Lead: _____________________ Date: _____
- [ ] Product Manager: _____________________ Date: _____

**Decision:** □ Proceed Now  □ Incremental  ☑ Defer to Post-Launch

---

**Document Version:** 1.0
**Last Updated:** 2025-11-09 04:25 UTC
