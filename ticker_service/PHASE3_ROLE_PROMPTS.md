# PHASE 3 ROLE-BASED PROMPTS
**Service Extraction - Part 2: Advanced Refactoring**

**Date**: November 8, 2025
**Prerequisites**: Phase 1 (Critical Fixes) + Phase 2 (God Class Extraction Part 1) Complete
**Target**: Extract 3 additional services to further reduce complexity in MultiAccountTickerLoop

---

## OVERVIEW

Phase 3 continues the service-oriented refactoring started in Phase 2. After successfully extracting MockDataGenerator, SubscriptionReconciler, and HistoricalBootstrapper, we now tackle the remaining complex responsibilities in MultiAccountTickerLoop:

1. **WebSocket Manager** - WebSocket connection lifecycle and message handling
2. **Account Orchestrator** - Account session management and coordination
3. **Tick Processor** - Tick data processing and routing logic

---

## ARCHITECTURAL CONTEXT

### Current State (After Phase 2)
```
app/generator.py (851 lines)
├── Streaming coordination (✅ lean)
├── WebSocket management (❌ needs extraction)
├── Account orchestration (❌ needs extraction)
├── Tick processing (❌ needs extraction)
└── Services (✅ extracted in Phase 2):
    ├── MockDataGenerator
    ├── SubscriptionReconciler
    └── HistoricalBootstrapper
```

### Target State (After Phase 3)
```
app/generator.py (<500 lines)
├── High-level streaming coordination only
└── Services (6 focused services):
    ├── MockDataGenerator (Phase 2)
    ├── SubscriptionReconciler (Phase 2)
    ├── HistoricalBootstrapper (Phase 2)
    ├── WebSocketManager (Phase 3) ← NEW
    ├── AccountOrchestrator (Phase 3) ← NEW
    └── TickProcessor (Phase 3) ← NEW
```

---

## SUCCESS CRITERIA

- ✅ Extract 3 new services (WebSocketManager, AccountOrchestrator, TickProcessor)
- ✅ Reduce generator.py from 851 lines to <500 lines (~40% additional reduction)
- ✅ Maintain 100% backward compatibility
- ✅ All Phase 1 + Phase 2 tests continue passing (71+ tests)
- ✅ Add 15+ new integration tests for Phase 3 services
- ✅ No performance degradation
- ✅ Services are independently testable and reusable

---

## PROMPT 1: Extract WebSocket Manager

### Role
You are a senior backend engineer specializing in WebSocket architectures and connection lifecycle management.

### Context
The MultiAccountTickerLoop currently handles WebSocket connections inline, mixing connection management with streaming logic. This makes it difficult to:
- Test WebSocket behavior independently
- Reuse connection logic across different contexts
- Handle connection failures gracefully
- Monitor WebSocket health

### Task
Extract all WebSocket-related logic into a dedicated `WebSocketManager` service.

### Implementation Steps

1. **Create `app/services/websocket_manager.py`**
   - Extract WebSocket connection establishment logic
   - Extract connection pooling/session management
   - Extract message sending/receiving logic
   - Extract reconnection and error handling
   - Add connection health monitoring

2. **Key Responsibilities**
   ```python
   class WebSocketManager:
       async def connect_account(self, account_id: str, client: KiteClient) -> WebSocketConnection
       async def disconnect_account(self, account_id: str) -> None
       async def subscribe_tokens(self, account_id: str, tokens: List[int]) -> None
       async def unsubscribe_tokens(self, account_id: str, tokens: List[int]) -> None
       async def send_message(self, account_id: str, message: dict) -> None
       def get_connection_status(self, account_id: str) -> ConnectionStatus
       async def reconnect_account(self, account_id: str) -> None
       async def close_all_connections(self) -> None
   ```

3. **Integration Points**
   - Inject WebSocketManager into MultiAccountTickerLoop constructor
   - Replace direct WebSocket calls with manager methods
   - Update `_run_live_stream()` to use manager for subscriptions
   - Update `stop()` to use `close_all_connections()`

4. **Methods to Extract from generator.py**
   - Look for WebSocket connection setup code
   - Look for subscribe/unsubscribe token logic
   - Look for WebSocket error handling
   - Look for connection state tracking

### Testing Requirements

Create `tests/integration/test_websocket_manager.py`:
- Test connection establishment
- Test subscription/unsubscription
- Test reconnection on failure
- Test connection health monitoring
- Test graceful shutdown

### Acceptance Criteria
- [ ] WebSocketManager service created (~200-300 lines)
- [ ] All WebSocket logic moved out of generator.py
- [ ] Integration tests pass (5+ tests)
- [ ] All Phase 1+2 tests still pass
- [ ] WebSocket behavior unchanged

---

## PROMPT 2: Extract Account Orchestrator

### Role
You are a senior backend engineer specializing in distributed systems and resource orchestration.

### Context
The MultiAccountTickerLoop manages multiple Kite accounts and their streaming sessions. This orchestration logic is mixed with streaming logic, making it hard to:
- Add/remove accounts dynamically
- Monitor account health independently
- Test account lifecycle without streaming
- Handle per-account errors gracefully

### Task
Extract all account orchestration logic into a dedicated `AccountOrchestrator` service.

### Implementation Steps

1. **Create `app/services/account_orchestrator.py`**
   - Extract account session initialization
   - Extract account-to-instrument assignment logic
   - Extract account health tracking
   - Extract account error handling and recovery
   - Add account lifecycle management

2. **Key Responsibilities**
   ```python
   class AccountOrchestrator:
       async def initialize_accounts(self) -> Dict[str, KiteClient]
       async def assign_instruments(self, accounts: List[str], instruments: List[Instrument]) -> Dict[str, List[Instrument]]
       async def start_account_session(self, account_id: str, instruments: List[Instrument]) -> None
       async def stop_account_session(self, account_id: str) -> None
       def get_account_health(self, account_id: str) -> AccountHealth
       async def handle_account_error(self, account_id: str, error: Exception) -> None
       async def shutdown_all_accounts(self) -> None
   ```

3. **Integration Points**
   - Inject AccountOrchestrator into MultiAccountTickerLoop constructor
   - Replace account initialization with orchestrator methods
   - Use orchestrator for account-to-instrument assignments
   - Use orchestrator for per-account error handling

4. **Methods to Extract from generator.py**
   - Look for account initialization logic in `start()`
   - Look for account task creation and tracking
   - Look for account error callbacks
   - Look for account cleanup in `stop()`

### Testing Requirements

Create `tests/integration/test_account_orchestrator.py`:
- Test account initialization
- Test instrument assignment (round-robin)
- Test account session lifecycle
- Test account error handling
- Test graceful shutdown

### Acceptance Criteria
- [ ] AccountOrchestrator service created (~200-250 lines)
- [ ] All account orchestration moved out of generator.py
- [ ] Integration tests pass (5+ tests)
- [ ] All Phase 1+2 tests still pass
- [ ] Account behavior unchanged

---

## PROMPT 3: Extract Tick Processor

### Role
You are a senior backend engineer specializing in real-time data processing and event-driven architectures.

### Context
The MultiAccountTickerLoop processes incoming tick data, transforms it, calculates Greeks, and publishes to Redis. This processing logic is scattered across multiple methods, making it hard to:
- Test tick processing independently
- Add new transformations or enrichments
- Monitor processing performance
- Handle processing errors gracefully

### Task
Extract all tick processing logic into a dedicated `TickProcessor` service.

### Implementation Steps

1. **Create `app/services/tick_processor.py`**
   - Extract tick transformation logic
   - Extract Greeks calculation integration
   - Extract depth data processing
   - Extract tick validation and enrichment
   - Add processing metrics and monitoring

2. **Key Responsibilities**
   ```python
   class TickProcessor:
       async def process_underlying_tick(self, tick: dict) -> ProcessedTick
       async def process_option_tick(self, tick: dict, instrument: Instrument) -> ProcessedOptionTick
       async def enrich_with_greeks(self, tick: ProcessedOptionTick, underlying_price: float) -> EnrichedTick
       async def validate_tick(self, tick: dict) -> bool
       async def transform_depth(self, depth_data: dict) -> MarketDepth
       def get_processing_stats(self) -> ProcessingStats
   ```

3. **Integration Points**
   - Inject TickProcessor into MultiAccountTickerLoop constructor
   - Replace direct tick processing with processor methods
   - Use processor in both live and mock streaming paths
   - Use processor for tick validation before publishing

4. **Methods to Extract from generator.py**
   - Look for tick processing in `_stream_underlying()`
   - Look for tick processing in `_stream_account()`
   - Look for Greeks calculation calls
   - Look for depth data transformation

### Testing Requirements

Create `tests/integration/test_tick_processor.py`:
- Test underlying tick processing
- Test option tick processing
- Test Greeks enrichment
- Test tick validation
- Test depth transformation

### Acceptance Criteria
- [ ] TickProcessor service created (~250-300 lines)
- [ ] All tick processing moved out of generator.py
- [ ] Integration tests pass (5+ tests)
- [ ] All Phase 1+2 tests still pass
- [ ] Tick data quality unchanged

---

## PROMPT 4: Create Integration Tests

### Role
You are a senior QA engineer specializing in integration testing and service verification.

### Context
Phase 3 introduces 3 new services that must work together seamlessly with the existing Phase 2 services. We need comprehensive integration tests to verify:
- All 6 services work together correctly
- Service boundaries are clean
- Error handling works across services
- Performance is maintained

### Task
Create comprehensive integration tests for all Phase 3 services.

### Implementation Steps

1. **Create `tests/integration/test_phase3_services.py`**
   - Test WebSocketManager integration with MultiAccountTickerLoop
   - Test AccountOrchestrator integration with assignment logic
   - Test TickProcessor integration with streaming pipeline
   - Test all 6 services working together end-to-end

2. **Test Coverage**
   ```python
   # WebSocket Manager Tests (5 tests)
   test_websocket_manager_integration()
   test_websocket_connection_lifecycle()
   test_websocket_subscription_management()
   test_websocket_reconnection()
   test_websocket_graceful_shutdown()

   # Account Orchestrator Tests (5 tests)
   test_account_orchestrator_integration()
   test_account_initialization()
   test_instrument_assignment()
   test_account_error_handling()
   test_account_session_lifecycle()

   # Tick Processor Tests (5 tests)
   test_tick_processor_integration()
   test_underlying_tick_processing()
   test_option_tick_processing()
   test_greeks_enrichment()
   test_tick_validation()

   # End-to-End Tests (3 tests)
   test_all_services_work_together()
   test_service_error_isolation()
   test_service_dependency_injection()
   ```

3. **Integration Patterns to Test**
   - Dependency injection for all services
   - Service lifecycle coordination
   - Error propagation and handling
   - State management across services

### Acceptance Criteria
- [ ] 15+ new integration tests created
- [ ] All tests pass
- [ ] Test coverage for all service boundaries
- [ ] End-to-end workflow tested
- [ ] Error scenarios covered

---

## PROMPT 5: Final Cleanup & Documentation

### Role
You are a technical lead responsible for code quality, documentation, and production readiness.

### Context
Phase 3 implementation is complete. We need to ensure code quality, update documentation, verify all tests pass, and prepare for production deployment.

### Task
Perform final cleanup, verification, and documentation updates.

### Implementation Steps

1. **Code Cleanup**
   - Create `app/services/__init__.py` exports for new services
   - Remove any dead code from generator.py
   - Ensure consistent naming and style across all services
   - Verify no circular imports exist

2. **Update Documentation**
   - Update `PHASE3_IMPLEMENTATION_COMPLETE.md` with:
     - Final line counts for all files
     - Service responsibility matrix
     - Test results (total passing)
     - Performance metrics
     - Architecture diagrams

3. **Verification Checklist**
   - [ ] generator.py < 500 lines (target achieved)
   - [ ] All 6 services in app/services/ directory
   - [ ] All Phase 1 tests pass (44/44)
   - [ ] All Phase 2 tests pass (13/13)
   - [ ] All Phase 3 tests pass (15/15)
   - [ ] Total: 86+ tests passing
   - [ ] No circular imports
   - [ ] Services properly exported

4. **Final Verification**
   ```bash
   # Run complete test suite
   pytest tests/ -v

   # Check line counts
   wc -l app/generator.py app/services/*.py

   # Verify exports
   python -c "from app.services import *; print('All services importable')"

   # Check for circular imports
   python -c "import app.generator; print('No circular imports')"
   ```

### Acceptance Criteria
- [ ] All cleanup complete
- [ ] Documentation updated and accurate
- [ ] All 86+ tests passing
- [ ] generator.py < 500 lines
- [ ] Production-ready code quality

---

## IMPLEMENTATION SEQUENCE

### Week 1: Core Service Extractions
- **Days 1-2**: PROMPT 1 (WebSocket Manager) - 6-8 hours
- **Days 3-4**: PROMPT 2 (Account Orchestrator) - 6-8 hours
- **Days 5-6**: PROMPT 3 (Tick Processor) - 6-8 hours

### Week 2: Testing & Finalization
- **Day 7**: PROMPT 4 (Integration Tests) - 4-6 hours
- **Day 8**: PROMPT 5 (Cleanup & Docs) - 2-4 hours

**Total Estimated Effort**: 24-34 hours

---

## DEPENDENCIES

### Prerequisites
- ✅ Phase 1 Complete (Critical Fixes)
- ✅ Phase 2 Complete (God Class Extraction Part 1)
- ✅ All 71 tests passing
- ✅ No pending bugs or issues

### Service Dependencies
```
WebSocketManager (independent)
AccountOrchestrator (depends on WebSocketManager)
TickProcessor (independent)
MultiAccountTickerLoop (orchestrates all services)
```

---

## ROLLBACK STRATEGY

Each prompt can be rolled back independently:

1. **If PROMPT 1 fails**: Keep WebSocket logic in generator.py
2. **If PROMPT 2 fails**: Keep account logic in generator.py
3. **If PROMPT 3 fails**: Keep tick processing in generator.py
4. **Complete rollback**: Revert to Phase 2 state (generator.py = 851 lines)

All rollbacks maintain Phase 1+2 improvements.

---

## MONITORING & METRICS

### Success Metrics
- **Code Complexity**: generator.py < 500 lines (40% reduction from Phase 2)
- **Test Coverage**: 86+ tests passing (100% pass rate)
- **Service Count**: 6 focused services (up from 3)
- **Backward Compatibility**: 100% preserved
- **Performance**: No degradation (< 5% variance)

### Red Flags (Stop Implementation)
- ❌ Any Phase 1 or Phase 2 tests fail
- ❌ Performance regression > 10%
- ❌ Circular imports detected
- ❌ Memory leaks introduced
- ❌ Breaking changes to public API

---

## PHASE 3 BENEFITS

### Developer Experience
- **Easier Testing**: All services independently testable
- **Faster Development**: Clear service boundaries
- **Better Debugging**: Service-level error isolation
- **Code Reusability**: Services can be used independently

### System Reliability
- **Fault Isolation**: Service failures don't cascade
- **Graceful Degradation**: Each service can fail independently
- **Better Monitoring**: Per-service health checks
- **Easier Maintenance**: Smaller, focused units

### Architecture Quality
- **SOLID Principles**: All services follow single responsibility
- **Low Coupling**: Services have minimal dependencies
- **High Cohesion**: Each service has clear, focused purpose
- **Testability**: 100% unit testable services

---

## CONCLUSION

Phase 3 completes the service-oriented refactoring of MultiAccountTickerLoop. After Phase 3:

- **Before Phase 1**: 1,484 lines God Class with critical bugs
- **After Phase 2**: 851 lines with 3 extracted services
- **After Phase 3**: <500 lines with 6 focused services (~66% total reduction)

This represents a **complete architectural transformation** while maintaining 100% backward compatibility and preserving all functionality.

---

**Document Version**: 1.0
**Author**: Claude Code (Sonnet 4.5)
**Date**: November 8, 2025
**Status**: READY FOR IMPLEMENTATION
