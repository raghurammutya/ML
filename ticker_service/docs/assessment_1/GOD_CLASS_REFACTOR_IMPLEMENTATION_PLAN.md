# God Class Refactor - Implementation Plan

**Created:** 2025-11-09 04:30 UTC
**Status:** PLANNED (Not yet executed)
**Estimated Effort:** 24-32 hours
**Priority:** P1 - HIGH (Not blocking production)
**Dependency:** Prompt #5 (Dependency Injection) recommended first

---

## Current State Analysis

### God Class: MultiAccountTickerLoop

**File:** `app/generator.py`
**Size:** 757 lines
**Methods:** 23 methods
**Cyclomatic Complexity:** 40 (threshold: 15)
**Cognitive Complexity:** 60 (threshold: 20)

**Responsibilities (7 distinct):**
1. **Stream Orchestration** - Managing account streaming tasks
2. **Subscription Management** - Loading/reconciling subscriptions
3. **Mock Data Generation** - Generating data during off-market hours
4. **Historical Bootstrapping** - Backfilling missing data
5. **Tick Processing** - Coordinating validation/processing
6. **Market Hours Detection** - Determining market status
7. **Health Monitoring** - Tracking system health

### Problems

**Maintainability:**
- 757 lines = high cognitive load
- Multiple responsibilities violate Single Responsibility Principle
- Hard to understand what component does what
- Changes in one area affect unrelated areas

**Testability:**
- Difficult to test individual responsibilities
- Mocking requires understanding entire class
- Can't test subscription logic without stream logic
- Integration tests required for unit-testable code

**Reusability:**
- Mock data logic coupled to streaming logic
- Can't reuse subscription management elsewhere
- Historical bootstrapping tied to ticker loop

---

## Proposed Decomposition

### Target Architecture

```
TickerServiceOrchestrator (Main coordinator)
├── StreamOrchestrator (Stream management)
├── SubscriptionCoordinator (Subscription lifecycle)
├── MockDataCoordinator (Mock data generation)
└── HistoricalBootstrapper (Historical data backfill)
```

### Class 1: StreamOrchestrator (~150 LOC)

**Responsibility:** Manage real-time streaming from KiteConnect

**Methods:**
- `start_streaming(accounts, subscriptions)`
- `stop_streaming()`
- `get_active_streams()`
- `get_stream_health()`
- `_start_account_stream(account_id)`
- `_stop_account_stream(account_id)`

**Dependencies:**
- SessionOrchestrator (manages Kite sessions)
- TickBatcher
- TickProcessor

### Class 2: SubscriptionCoordinator (~180 LOC)

**Responsibility:** Handle subscription lifecycle

**Methods:**
- `load_subscriptions_from_db()`
- `reload_subscriptions()`
- `reconcile_subscriptions(new_subs, old_subs)`
- `distribute_subscriptions_across_accounts()`
- `validate_subscription_limits()`

**Dependencies:**
- SubscriptionStore
- InstrumentRegistry
- KiteClient (for subscription API)

### Class 3: MockDataCoordinator (~200 LOC)

**Responsibility:** Generate mock data during off-market hours

**Methods:**
- `is_market_open()`
- `generate_mock_tick_data(instruments)`
- `ensure_mock_seed_data()`
- `_generate_option_snapshot()`
- `_generate_futures_snapshot()`

**Dependencies:**
- GreeksCalculator
- InstrumentRegistry
- RedisPublisher

### Class 4: HistoricalBootstrapper (~150 LOC)

**Responsibility:** Backfill missing historical data

**Methods:**
- `backfill_missing_history(instrument)`
- `fetch_historical_data(symbol, from_date, to_date)`
- `store_historical_data(data)`

**Dependencies:**
- KiteClient
- Database connection
- InstrumentRegistry

### Class 5: TickerServiceOrchestrator (~200 LOC)

**Responsibility:** Coordinate all components

**Methods:**
- `start()`
- `stop()`
- `reload_subscriptions()`
- `get_status()`
- `_startup_sequence()`
- `_shutdown_sequence()`

**Dependencies:**
- StreamOrchestrator
- SubscriptionCoordinator
- MockDataCoordinator
- HistoricalBootstrapper

---

## Implementation Approach

### Option A: Big Bang Refactor (24-32 hours)

**Steps:**
1. Create 5 new files with new classes
2. Extract code from god class to new classes
3. Update all imports across codebase
4. Update tests
5. Delete god class

**Pros:**
- Clean break from old structure
- Forces complete rethink of design

**Cons:**
- Very high risk
- All-or-nothing - hard to rollback
- Requires extensive testing
- Blocks other development

**Recommendation:** ❌ NOT RECOMMENDED

### Option B: Strangler Fig Pattern (Incremental)

**Week 1:** Extract SubscriptionCoordinator
- Create new file `app/services/subscription_coordinator.py`
- Extract subscription methods
- Update god class to delegate to new class
- God class keeps facade methods for backward compatibility
- Test thoroughly

**Week 2:** Extract MockDataCoordinator
- Create new file `app/services/mock_data_coordinator.py`
- Extract mock data methods
- Update god class to delegate
- Test mock data generation

**Week 3:** Extract StreamOrchestrator & HistoricalBootstrapper
- Create `app/services/stream_orchestrator.py`
- Create `app/services/historical_bootstrapper.py`
- Extract remaining methods
- Update god class to delegate

**Week 4:** Replace God Class with TickerServiceOrchestrator
- Create `app/services/ticker_service_orchestrator.py`
- Migrate remaining logic
- Update all imports
- Delete old god class

**Pros:**
- Lower risk per change
- Can test incrementally
- Easy to rollback individual steps
- Maintains backward compatibility during migration
- Doesn't block other work

**Cons:**
- Takes 4 weeks total
- Temporary duplication of code
- Mixed architecture during transition

**Recommendation:** ✅ RECOMMENDED

### Option C: Defer to Post-Launch

**Do Now:**
- ✅ Document refactoring plan
- ✅ Identify class responsibilities
- ✅ Create task breakdown
- Add to technical debt backlog

**Do After Launch:**
- Schedule 4-week sprint for Strangler Fig migration
- Dedicate senior engineer for refactoring
- Plan comprehensive testing

**Pros:**
- Zero risk to launch
- Can plan resources properly
- Can learn from production usage

**Cons:**
- Technical debt continues
- Maintainability remains low

**Recommendation:** ✅ STRONGLY RECOMMENDED

---

## Risks & Challenges

### HIGH RISK

1. **Breaking Existing Functionality**
   - God class is central to application
   - Used by multiple components
   - Complex initialization sequence
   - Hidden dependencies

2. **Testing Complexity**
   - Current code likely under-tested
   - Refactoring may reveal bugs
   - Need comprehensive integration tests
   - Hard to validate equivalence

3. **Performance Degradation**
   - Adding indirection layers
   - More object creation
   - May affect latency

### MEDIUM RISK

4. **Dependency Entanglement**
   - Circular dependencies possible
   - Initialization order matters
   - Some methods may need multiple components

5. **Incomplete Extraction**
   - May discover shared state
   - Some methods may not fit cleanly
   - Edge cases may be missed

### LOW RISK

6. **Developer Confusion**
   - New architecture to learn
   - Documentation needed
   - Code reviews required

---

## Success Criteria

**Before Refactor:**
- Single class: 757 LOC
- Methods: 23
- Responsibilities: 7
- Cyclomatic complexity: 40
- Test coverage: ~20%
- Easy to understand: ❌ NO

**After Refactor:**
- Largest class: <200 LOC
- Average methods per class: <8
- Responsibilities per class: 1
- Max cyclomatic complexity: <15
- Test coverage: >60%
- Easy to understand: ✅ YES

---

## Prerequisites

**Strongly Recommended:**
1. ✅ Complete Prompt #5 (Dependency Injection) first
   - Refactor is much easier with DI in place
   - Can inject new components easily
   - Tests are easier to write

**Nice to Have:**
2. Increase test coverage on existing god class
   - Establishes baseline behavior
   - Catch regressions during refactor
   - Validate equivalence

---

## Estimated Effort Breakdown

### Option B (Strangler Fig - RECOMMENDED)

**Week 1:** SubscriptionCoordinator extraction (6-8 hours)
- Create new file (1 hour)
- Extract methods (3 hours)
- Update tests (2 hours)
- Integration testing (1 hour)

**Week 2:** MockDataCoordinator extraction (6-8 hours)
- Create new file (1 hour)
- Extract methods (3 hours)
- Update tests (2 hours)
- Integration testing (1 hour)

**Week 3:** StreamOrchestrator & HistoricalBootstrapper (8-10 hours)
- Create two new files (1 hour each)
- Extract methods (4 hours)
- Update tests (2 hours)
- Integration testing (2 hours)

**Week 4:** TickerServiceOrchestrator replacement (8-10 hours)
- Create orchestrator (2 hours)
- Migrate remaining logic (2 hours)
- Update all imports (2 hours)
- Full test suite (2 hours)
- Delete god class (1 hour)

**Total:** 28-36 hours over 4 weeks

---

## Decision Matrix

| Criteria | Option A (Big Bang) | Option B (Strangler) | Option C (Defer) |
|----------|-------------------|-------------------|-----------------|
| Risk to Launch | ⚠️ VERY HIGH | ⚠️ MEDIUM | ✅ NONE |
| Time Required | 24-32 hours | 28-36 hours | 0 hours now |
| Rollback Ease | ❌ VERY HARD | ✅ EASY | ✅ N/A |
| Testing Effort | ⚠️ VERY HIGH | ✅ INCREMENTAL | ✅ NONE |
| Long-term Value | ✅ HIGH | ✅ HIGH | ✅ HIGH (later) |
| **RECOMMENDATION** | ❌ NO | ⚠️ POST-LAUNCH | ✅ YES NOW |

---

## Implementation Checklist (When Executed)

### Prerequisites
- [ ] Complete Prompt #5 (Dependency Injection)
- [ ] Increase test coverage on generator.py to >40%
- [ ] Document current behavior with integration tests

### Week 1: SubscriptionCoordinator
- [ ] Create `app/services/subscription_coordinator.py`
- [ ] Extract subscription loading methods
- [ ] Extract subscription reconciliation
- [ ] Extract distribution logic
- [ ] Add unit tests (target: 80% coverage)
- [ ] Update god class to delegate
- [ ] Integration test pass

### Week 2: MockDataCoordinator
- [ ] Create `app/services/mock_data_coordinator.py`
- [ ] Extract market hours detection
- [ ] Extract mock data generation
- [ ] Extract seed data management
- [ ] Add unit tests (target: 80% coverage)
- [ ] Update god class to delegate
- [ ] Mock data validation tests

### Week 3: StreamOrchestrator & HistoricalBootstrapper
- [ ] Create `app/services/stream_orchestrator.py`
- [ ] Extract stream management
- [ ] Extract health monitoring
- [ ] Create `app/services/historical_bootstrapper.py`
- [ ] Extract backfill logic
- [ ] Add unit tests for both (target: 80%)
- [ ] Integration tests pass

### Week 4: Final Migration
- [ ] Create `app/services/ticker_service_orchestrator.py`
- [ ] Migrate startup/shutdown logic
- [ ] Update all imports in routes
- [ ] Update all imports in tests
- [ ] Full regression test suite
- [ ] Performance testing (no degradation)
- [ ] Delete `MultiAccountTickerLoop` class
- [ ] Update documentation

---

## Rollback Plan

### If Issues During Week 1-3:
- Revert specific week's changes
- God class facade methods maintain backward compatibility
- No impact on other components

### If Issues During Week 4:
- Keep god class as primary implementation
- New classes become internal helpers
- Can migrate imports incrementally

---

## Monitoring During Migration

**Key Metrics:**
- Startup time (<5% increase allowed)
- Memory usage (<10% increase allowed)
- Tick processing latency (<1% increase allowed)
- Stream connection stability (maintain current)
- Error rates (no increase)

**Alerts:**
- Any performance degradation >10%
- Any new error types
- Test failures
- Integration test failures

---

## Conclusion

**Current Status:** ANALYSIS COMPLETE, PLAN DOCUMENTED

**Recommended Decision:** DEFER TO POST-LAUNCH

**Rationale:**
1. All P0 work complete - no blocking issues
2. Requires Prompt #5 (DI) as prerequisite
3. High complexity - 4-week effort
4. Better executed with dedicated resources
5. Production-ready code exists (just not ideal structure)

**When to Execute:**
1. After successful production deployment
2. After completing Prompt #5 (Dependency Injection)
3. When dedicated 4-week sprint can be allocated
4. With senior engineer assigned full-time

**Expected Benefits (Post-Refactor):**
- 80% reduction in class size
- 60% reduction in complexity
- 3x improvement in testability
- Improved maintainability and developer velocity

---

**Sign-Off Required:**
- [ ] Engineering Lead: _____________________ Date: _____
- [ ] Tech Lead: _____________________ Date: _____
- [ ] Architecture Lead: _____________________ Date: _____

**Decision:** □ Proceed Now  □ Strangler Fig  ☑ Defer to Post-Launch

---

**Document Version:** 1.0
**Last Updated:** 2025-11-09 04:30 UTC
**Next Review:** Post-launch (after Prompt #5 completion)
