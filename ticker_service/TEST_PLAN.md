# Comprehensive Test Plan - Ticker Service
**Production-Critical Testing Strategy**

**Version**: 1.0
**Date**: November 8, 2025
**Service**: ticker_service
**Zero Tolerance for Regressions**

---

## Table of Contents
1. [Test Strategy](#1-test-strategy)
2. [Test Coverage Goals](#2-test-coverage-goals)
3. [Detailed Test Cases by Component](#3-detailed-test-cases-by-component)
4. [Performance Test Cases](#4-performance-test-cases)
5. [Regression Test Suite](#5-regression-test-suite)
6. [Test Infrastructure Requirements](#6-test-infrastructure-requirements)
7. [Test Execution Plan](#7-test-execution-plan)
8. [Test Automation Strategy](#8-test-automation-strategy)

---

## 1. Test Strategy

### 1.1 Unit Testing Approach

**Objective**: Test individual components in isolation with mocked dependencies.

**Principles**:
- **Fast Execution**: Each unit test should complete in < 100ms
- **Isolated**: No external dependencies (Redis, PostgreSQL, Kite API)
- **Deterministic**: Same input always produces same output
- **Comprehensive**: Cover all code paths including error conditions

**Tools**:
- pytest (test framework)
- pytest-asyncio (async test support)
- unittest.mock / pytest-mock (mocking)
- pytest-cov (coverage tracking)

**Scope**:
- Business logic functions
- Data transformations
- Calculation algorithms (Greeks, IV)
- State management classes
- Configuration validation
- Helper utilities

**Mocking Strategy**:
```python
# Mock external dependencies at module boundaries
@pytest.fixture
def mock_redis():
    return AsyncMock(spec=RedisPublisher)

@pytest.fixture
def mock_kite_client():
    return AsyncMock(spec=KiteClient)

# Test with mocked dependencies
async def test_publish_option_snapshot(mock_redis):
    snapshot = OptionSnapshot(...)
    await publish_option_snapshot(snapshot, redis_pub=mock_redis)
    mock_redis.publish.assert_called_once()
```

### 1.2 Integration Testing Approach

**Objective**: Test component interactions with real dependencies.

**Principles**:
- **Realistic Environment**: Use actual Redis, PostgreSQL (test databases)
- **Controlled Data**: Pre-seeded test data with known states
- **Transactional**: Each test runs in isolation (rollback after test)
- **End-to-End Flows**: Test complete request/response cycles

**Tools**:
- Docker Compose (test environment)
- pytest fixtures (database setup/teardown)
- testcontainers-python (optional, for ephemeral containers)

**Scope**:
- REST API endpoints (full request → response)
- WebSocket connections and messaging
- Database CRUD operations
- Redis pub/sub messaging
- Multi-component workflows

**Test Environment Setup**:
```yaml
# docker-compose.test.yml
services:
  redis-test:
    image: redis:7-alpine
    ports:
      - "6380:6379"

  postgres-test:
    image: timescale/timescaledb:latest-pg16
    environment:
      POSTGRES_DB: ticker_test
      POSTGRES_USER: test_user
      POSTGRES_PASSWORD: test_pass
    ports:
      - "5433:5432"
```

### 1.3 End-to-End Testing Approach

**Objective**: Test complete user scenarios from client perspective.

**Principles**:
- **Black Box**: Test through public APIs only
- **Real Workflows**: Simulate actual user interactions
- **Production-Like**: Environment mirrors production configuration
- **Data Validation**: Verify correctness of data flow end-to-end

**Tools**:
- httpx (async HTTP client)
- websockets (WebSocket client)
- pytest-xdist (parallel execution)

**Scope**:
- Complete subscription lifecycle (create → stream → deactivate)
- Multi-account orchestration flows
- Historical data fetching with Greeks enrichment
- Order execution workflows
- WebSocket streaming scenarios

**Example E2E Test**:
```python
@pytest.mark.e2e
async def test_subscription_lifecycle_e2e(api_client, ws_client):
    # 1. Create subscription
    response = await api_client.post("/subscriptions", json={
        "instrument_token": 256265,
        "mode": "FULL"
    })
    assert response.status_code == 200

    # 2. Connect WebSocket and subscribe
    await ws_client.connect()
    await ws_client.send({"action": "subscribe", "tokens": [256265]})

    # 3. Verify tick received
    tick = await asyncio.wait_for(ws_client.receive(), timeout=5.0)
    assert tick["type"] == "tick"
    assert tick["data"]["instrument_token"] == 256265

    # 4. Deactivate subscription
    response = await api_client.delete("/subscriptions/256265")
    assert response.status_code == 200

    # 5. Verify no more ticks
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(ws_client.receive(), timeout=2.0)
```

### 1.4 Performance/Load Testing Strategy

**Objective**: Validate system behavior under high load and stress conditions.

**Principles**:
- **Baseline Metrics**: Establish performance baselines
- **Scalability Validation**: Test scaling beyond current limits
- **Resource Monitoring**: Track CPU, memory, connections during tests
- **Degradation Analysis**: Identify breaking points

**Tools**:
- locust (load testing framework)
- pytest-benchmark (micro-benchmarks)
- prometheus + grafana (metrics collection)

**Test Types**:
1. **Load Tests**: Sustained load at expected capacity
2. **Stress Tests**: Push beyond capacity to find limits
3. **Spike Tests**: Sudden load increases
4. **Soak Tests**: Extended duration (8+ hours)

**Key Metrics**:
- Tick publish latency (p50, p95, p99)
- WebSocket connection capacity
- Subscription reload time
- API endpoint response times
- Memory consumption over time
- Redis/PostgreSQL connection pool saturation

### 1.5 Regression Testing Strategy

**Objective**: Ensure NO existing functionality breaks during changes.

**Principles**:
- **Golden Master**: Capture current behavior as baseline
- **Snapshot Testing**: Compare outputs against known-good states
- **Contract Testing**: Verify API contracts unchanged
- **Backward Compatibility**: Ensure clients continue to work

**Approach**:
1. **API Contract Tests**: Validate exact response schemas
2. **Data Accuracy Tests**: Verify Greeks calculations match baseline
3. **State Persistence Tests**: Ensure data survives restarts
4. **Protocol Tests**: WebSocket message format unchanged

**Tools**:
- pytest-snapshot (snapshot testing)
- pydantic (schema validation)
- hypothesis (property-based testing)

---

## 2. Test Coverage Goals

### 2.1 Current Coverage Baseline

**Current State**:
- **Test Lines**: 455 lines
- **Code Lines**: 12,180 lines
- **Coverage**: ~4%
- **Test Files**: 5 files

**Coverage by Component** (Current):
```
Component                    | Lines | Tested | Coverage
-----------------------------|-------|--------|----------
Configuration (config.py)    |   287 |     91 |    32%
Authentication (auth.py)     |   407 |     76 |    19%
Runtime State               |   150 |     67 |    45%
API Endpoints               |   621 |     72 |    12%
MultiAccountTickerLoop      |  1184 |      0 |     0%
WebSocket Pool              |   150 |      0 |     0%
Greeks Calculator           |   596 |      0 |     0%
Order Executor              |   451 |      0 |     0%
Subscription Management     |   200 |      0 |     0%
```

### 2.2 Target Coverage Goals

**Phase 1 (Week 1-2): Critical Components - Target 60%**
- MultiAccountTickerLoop: 60% (startup, shutdown, basic streaming)
- WebSocket Pool: 70% (connection management, subscription)
- Order Executor: 65% (task lifecycle, circuit breaker)
- Configuration: 90% (all validators)

**Phase 2 (Week 3-4): Core Business Logic - Target 75%**
- Greeks Calculator: 90% (all calculation paths)
- Subscription Management: 85% (CRUD operations)
- Historical Greeks Enricher: 75% (enrichment logic)
- Redis Publisher: 80% (publish, retry, error handling)

**Phase 3 (Week 5-6): Integration & Edge Cases - Target 85%**
- API Endpoints: 90% (all routes, error conditions)
- WebSocket Server: 85% (connection management, broadcasting)
- Account Store: 80% (multi-account orchestration)
- Error Recovery: 100% (all error paths tested)

**Final Target (Week 8): Production Ready - Target 85%+**
- Overall line coverage: 85%
- Branch coverage: 75%
- Critical paths: 100%
- Error handling: 100%

### 2.3 Priority Areas Requiring Tests

**Priority 1 (Critical - Zero Downtime Risk)**:
1. MultiAccountTickerLoop startup/shutdown sequences
2. WebSocket Pool deadlock prevention (RLock verification)
3. Order Executor circuit breaker state machine
4. Redis connection failover and retry logic
5. Database connection pool exhaustion scenarios

**Priority 2 (High - Data Accuracy Risk)**:
1. Greeks calculation correctness (delta, gamma, theta, vega)
2. Implied volatility derivation edge cases
3. Mock data generation consistency
4. Historical Greeks enrichment accuracy
5. Subscription state reconciliation

**Priority 3 (Medium - Operational Risk)**:
1. API endpoint authorization and authentication
2. Rate limiting enforcement
3. Health check endpoint accuracy
4. Concurrent subscription reload handling
5. Account failover mechanisms

**Priority 4 (Low - Enhancement Risk)**:
1. Logging format consistency
2. Metrics accuracy
3. Configuration validation edge cases
4. Backpressure monitoring thresholds

---

## 3. Detailed Test Cases by Component

### 3.1 MultiAccountTickerLoop (generator.py)

#### Test Suite: Startup/Shutdown

**TC-MATL-001: Normal Startup Sequence**
- **Priority**: CRITICAL
- **Preconditions**:
  - Valid account credentials configured
  - Redis and PostgreSQL accessible
  - At least 1 active subscription in database
- **Test Steps**:
  1. Create MultiAccountTickerLoop instance
  2. Call `start()` method
  3. Wait for startup completion (max 10s)
  4. Verify `_account_tasks` contains tasks for each account
  5. Verify `_underlying_task` is created
  6. Verify `_running` flag is True
- **Expected Results**:
  - All account tasks created and running
  - Underlying aggregation task running
  - No exceptions raised
  - Health check shows "running"
- **Regression Risk**: HIGH (service won't start if broken)

**TC-MATL-002: Startup with No Active Subscriptions**
- **Priority**: HIGH
- **Preconditions**: Database has zero active subscriptions
- **Test Steps**:
  1. Start ticker loop with empty subscription list
  2. Verify startup completes successfully
  3. Verify no account tasks created
  4. Verify underlying task still created (for future subscriptions)
- **Expected Results**:
  - Startup succeeds even with no subscriptions
  - Service remains in ready state
  - Can accept new subscriptions dynamically
- **Regression Risk**: MEDIUM

**TC-MATL-003: Graceful Shutdown**
- **Priority**: CRITICAL
- **Preconditions**: Ticker loop running with active subscriptions
- **Test Steps**:
  1. Start ticker loop
  2. Wait for tasks to be running
  3. Call `stop()` method
  4. Verify `_stop_event` is set
  5. Verify all tasks complete within 30 seconds
  6. Verify no lingering tasks
- **Expected Results**:
  - All tasks terminate cleanly
  - No exceptions logged
  - Resources released (WebSocket connections closed)
  - No zombie tasks remaining
- **Regression Risk**: CRITICAL (memory leaks, hung processes)

**TC-MATL-004: Shutdown During Active Streaming**
- **Priority**: CRITICAL
- **Preconditions**:
  - Ticker loop streaming ticks actively
  - Multiple accounts with subscriptions
- **Test Steps**:
  1. Start streaming with 100+ subscriptions
  2. Generate mock ticks for 5 seconds
  3. Call `stop()` during active streaming
  4. Measure shutdown time
  5. Verify all ticks published before shutdown complete
- **Expected Results**:
  - Shutdown completes within 30 seconds
  - No data loss (all queued ticks published)
  - Clean task cancellation
  - No exceptions during shutdown
- **Regression Risk**: CRITICAL

**TC-MATL-005: Startup Failure - Redis Unavailable**
- **Priority**: HIGH
- **Preconditions**: Redis service stopped/unreachable
- **Test Steps**:
  1. Stop Redis container
  2. Attempt to start ticker loop
  3. Verify appropriate exception raised
  4. Verify error message contains "Redis"
  5. Verify no partial state created
- **Expected Results**:
  - Startup fails with clear error message
  - No zombie tasks created
  - Service can retry startup after Redis restored
- **Regression Risk**: MEDIUM

#### Test Suite: Subscription Management

**TC-MATL-010: Reload Subscriptions - Add New**
- **Priority**: CRITICAL
- **Preconditions**:
  - Ticker loop running with 10 subscriptions
  - Database has 5 new subscriptions added
- **Test Steps**:
  1. Record current subscription count
  2. Add 5 new subscriptions to database
  3. Call `reload_subscriptions_async()`
  4. Wait for reload to complete (max 60s)
  5. Verify new subscriptions are streaming
  6. Verify old subscriptions still active
- **Expected Results**:
  - New subscriptions added without disrupting existing
  - Total subscriptions = 15
  - All subscriptions receive ticks
  - Reload completes within 60 seconds
- **Regression Risk**: CRITICAL (100+ second timeout previously)

**TC-MATL-011: Reload Subscriptions - Remove Existing**
- **Priority**: CRITICAL
- **Preconditions**: Ticker loop with 20 subscriptions
- **Test Steps**:
  1. Mark 10 subscriptions as inactive in database
  2. Trigger reload
  3. Verify inactive subscriptions unsubscribed from WebSocket
  4. Verify active subscriptions continue streaming
  5. Verify WebSocket pool connection count reduced if appropriate
- **Expected Results**:
  - Inactive subscriptions removed cleanly
  - No ticks for inactive subscriptions
  - Active subscriptions unaffected
  - Resources released (connections, memory)
- **Regression Risk**: HIGH

**TC-MATL-012: Concurrent Reload Requests**
- **Priority**: HIGH
- **Preconditions**: Ticker loop running
- **Test Steps**:
  1. Trigger 5 concurrent `reload_subscriptions_async()` calls
  2. Monitor `_reconcile_lock` acquisition
  3. Verify only 1 reload executes at a time
  4. Verify subsequent calls skip duplicate work
  5. Verify no deadlocks occur
- **Expected Results**:
  - Lock prevents concurrent reloads
  - Duplicate reloads skipped (log message)
  - Final state correct after all calls complete
  - No deadlocks or race conditions
- **Regression Risk**: HIGH (race condition risk)

**TC-MATL-013: Reload During Market Hours with Real Streaming**
- **Priority**: CRITICAL
- **Preconditions**:
  - Market hours active
  - Real Kite API streaming ticks
- **Test Steps**:
  1. Start with 50 subscriptions streaming
  2. Add 10 new subscriptions
  3. Trigger reload
  4. Monitor tick stream during reload
  5. Verify no tick gaps > 5 seconds
- **Expected Results**:
  - Reload completes without stopping tick stream
  - New subscriptions start streaming within 10 seconds
  - Existing subscriptions maintain continuous ticks
  - No data loss
- **Regression Risk**: CRITICAL

#### Test Suite: Mock Data Generation

**TC-MATL-020: Mock Data Initialization**
- **Priority**: HIGH
- **Preconditions**:
  - ENABLE_MOCK_DATA=true
  - Outside market hours (or mocked time)
- **Test Steps**:
  1. Start ticker loop
  2. Verify `_ensure_mock_underlying_seed()` called
  3. Verify `_mock_underlying_state` initialized
  4. Verify `_mock_option_state` dict populated
  5. Check mock data has realistic base values
- **Expected Results**:
  - Mock state initialized exactly once (double-check lock works)
  - Base prices within configured ranges
  - All subscribed options have mock state
  - Initialization completes within 5 seconds
- **Regression Risk**: MEDIUM

**TC-MATL-021: Mock Option Tick Generation**
- **Priority**: HIGH
- **Preconditions**: Mock state initialized
- **Test Steps**:
  1. Generate 100 consecutive mock option ticks
  2. Verify price variation within `mock_price_variation_bps`
  3. Verify volume variation within `mock_volume_variation`
  4. Verify all Greeks present (delta, gamma, theta, vega)
  5. Verify Greeks values realistic (delta 0-1 for calls)
- **Expected Results**:
  - All ticks have valid prices (> 0)
  - Price variation follows configured bounds
  - Greeks calculations correct
  - Timestamps monotonically increasing
  - No NaN or Infinity values
- **Regression Risk**: MEDIUM

**TC-MATL-022: Mock Underlying Bar Aggregation**
- **Priority**: MEDIUM
- **Preconditions**: Mock underlying state active
- **Test Steps**:
  1. Generate underlying bars for 60 seconds
  2. Verify OHLC bars created at `stream_interval_seconds`
  3. Verify O <= H, L <= C relationships
  4. Verify volume aggregation realistic
  5. Verify bars published to Redis
- **Expected Results**:
  - Bars generated at correct interval
  - OHLC relationships valid
  - Volume within realistic ranges
  - Published to "ticker:nifty:underlying" channel
- **Regression Risk**: LOW

**TC-MATL-023: Mock Data Seed Concurrency**
- **Priority**: MEDIUM
- **Preconditions**: Multiple account tasks starting simultaneously
- **Test Steps**:
  1. Start 5 account tasks concurrently
  2. All call `_ensure_mock_underlying_seed()` simultaneously
  3. Monitor lock acquisition and initialization
  4. Verify initialization happens exactly once
  5. Verify no race conditions or torn reads
- **Expected Results**:
  - Double-check locking pattern works correctly
  - State initialized exactly once
  - No concurrent modification exceptions
  - All tasks get consistent state snapshot
- **Regression Risk**: MEDIUM (race condition)

#### Test Suite: Real-Time Streaming

**TC-MATL-030: Single Account Streaming**
- **Priority**: CRITICAL
- **Preconditions**:
  - 1 Kite account configured
  - 50 option subscriptions
  - Redis accessible
- **Test Steps**:
  1. Start streaming for single account
  2. Mock KiteTicker callbacks with 10 ticks/second
  3. Monitor Redis publish calls
  4. Verify all ticks published within 100ms
  5. Verify Greeks calculations included
- **Expected Results**:
  - All ticks published to Redis
  - Publish latency p95 < 100ms
  - Greeks values present and valid
  - No exceptions logged
  - Memory stable over 60 second test
- **Regression Risk**: CRITICAL

**TC-MATL-031: Multi-Account Load Balancing**
- **Priority**: CRITICAL
- **Preconditions**:
  - 3 Kite accounts configured
  - 1500 subscriptions (500 per account)
- **Test Steps**:
  1. Verify subscriptions distributed across accounts
  2. Verify each account has ≤ 1000 subscriptions (Kite limit)
  3. Start streaming all accounts
  4. Monitor per-account tick rates
  5. Verify load balanced (no single account overloaded)
- **Expected Results**:
  - Subscriptions distributed evenly
  - No account exceeds 1000 subscriptions
  - All accounts streaming simultaneously
  - Combined tick rate = sum of individual rates
  - No account failover triggered
- **Regression Risk**: CRITICAL

**TC-MATL-032: Streaming Error Recovery**
- **Priority**: CRITICAL
- **Preconditions**: Active streaming in progress
- **Test Steps**:
  1. Simulate KiteTicker exception in callback
  2. Verify error logged with context
  3. Verify streaming continues for other subscriptions
  4. Verify failed instrument retried
  5. Verify no cascading failures
- **Expected Results**:
  - Single tick failure doesn't stop stream
  - Error logged with instrument token
  - Other subscriptions unaffected
  - Retry mechanism activated
  - Circuit breaker monitors failure rate
- **Regression Risk**: HIGH

**TC-MATL-033: Underlying Bar Aggregation Across Accounts**
- **Priority**: HIGH
- **Preconditions**: 3 accounts each streaming underlying
- **Test Steps**:
  1. Each account receives different underlying ticks
  2. Verify aggregator combines all ticks
  3. Verify single consolidated bar published
  4. Verify OHLC reflects all account data
  5. Verify volume aggregated correctly
- **Expected Results**:
  - Single bar published per interval
  - Bar reflects data from all accounts
  - High = max(all account highs)
  - Low = min(all account lows)
  - Volume = sum(all account volumes)
- **Regression Risk**: MEDIUM

#### Test Suite: Account Failover

**TC-MATL-040: Account Rate Limit Failover**
- **Priority**: CRITICAL
- **Preconditions**:
  - 2+ accounts configured
  - Rate limit triggered on primary account
- **Test Steps**:
  1. Configure primary account to simulate rate limit (429)
  2. Attempt subscription
  3. Verify failover to secondary account
  4. Verify subscription succeeds on secondary
  5. Verify primary account marked as rate-limited
- **Expected Results**:
  - Failover occurs within 5 seconds
  - Subscription succeeds on secondary account
  - Circuit breaker opens for primary account
  - Recovery attempted after timeout (60s)
  - No data loss during failover
- **Regression Risk**: CRITICAL

**TC-MATL-041: Account Reconnection After Disconnect**
- **Priority**: CRITICAL
- **Preconditions**: Account streaming actively
- **Test Steps**:
  1. Simulate WebSocket disconnection
  2. Monitor KiteTicker auto-reconnect
  3. Verify subscriptions re-established
  4. Verify tick stream resumes
  5. Measure reconnection time
- **Expected Results**:
  - Reconnection automatic (KiteTicker library)
  - Subscriptions re-established within 30 seconds
  - No permanent data loss
  - Gap in ticks during reconnection acceptable
  - Reconnection logged
- **Regression Risk**: HIGH

#### Test Suite: Race Conditions

**TC-MATL-050: Concurrent Reload During Streaming**
- **Priority**: CRITICAL
- **Preconditions**:
  - Active streaming with 100+ subscriptions
  - Reload triggered during tick processing
- **Test Steps**:
  1. Start streaming at high tick rate (50 ticks/sec)
  2. Trigger `reload_subscriptions_async()` during streaming
  3. Monitor for deadlocks or lock contention
  4. Verify streaming continues during reload
  5. Verify reload completes successfully
- **Expected Results**:
  - No deadlocks occur
  - Streaming pauses briefly (< 1s) during reload
  - Reload completes within 60 seconds
  - Final state correct (all subscriptions active)
  - No lost ticks
- **Regression Risk**: CRITICAL

**TC-MATL-051: Mock State Access Race Condition**
- **Priority**: MEDIUM
- **Preconditions**: Mock data enabled
- **Test Steps**:
  1. Start 5 account tasks concurrently
  2. All tasks read `_mock_underlying_state` simultaneously
  3. Seed task updates state during reads
  4. Verify no torn reads (partial state observed)
  5. Verify no exceptions raised
- **Expected Results**:
  - All tasks get consistent state view
  - No AttributeError exceptions
  - No race condition warnings
  - State updates atomic
  - Reads return valid MockUnderlyingState or None
- **Regression Risk**: MEDIUM

---

### 3.2 KiteWebSocketPool (websocket_pool.py)

#### Test Suite: Connection Pooling

**TC-WSP-001: Single Connection Creation**
- **Priority**: CRITICAL
- **Preconditions**: Pool initialized with 0 connections
- **Test Steps**:
  1. Subscribe to 500 tokens
  2. Verify single WebSocket connection created
  3. Verify connection subscribed to all 500 tokens
  4. Verify pool metrics show 1 connection
  5. Verify subscription count = 500
- **Expected Results**:
  - Exactly 1 connection created
  - All tokens subscribed successfully
  - Metrics accurate (subscribed_tokens=500)
  - Connection status = connected
- **Regression Risk**: HIGH

**TC-WSP-002: Multi-Connection Scaling**
- **Priority**: CRITICAL
- **Preconditions**: Pool empty
- **Test Steps**:
  1. Subscribe to 1500 tokens (exceeds 1000 limit)
  2. Verify 2 connections created automatically
  3. Verify first connection has 1000 tokens
  4. Verify second connection has 500 tokens
  5. Verify load balancing algorithm
- **Expected Results**:
  - 2 connections created automatically
  - Token distribution: [1000, 500]
  - Both connections active and streaming
  - Pool capacity utilization = 60% (1500/2500)
  - Metrics show 2 connections
- **Regression Risk**: CRITICAL

**TC-WSP-003: Connection Pool Reuse**
- **Priority**: MEDIUM
- **Preconditions**: Pool with 2 connections (1500 tokens total)
- **Test Steps**:
  1. Unsubscribe 600 tokens from various connections
  2. Subscribe 400 new tokens
  3. Verify existing connections reused
  4. Verify no new connections created
  5. Verify tokens distributed to fill gaps
- **Expected Results**:
  - No new connections created
  - Tokens added to connections with capacity
  - Total subscriptions = 900 + 400 = 1300
  - Connections: [1000, 300]
  - Connection count remains 2
- **Regression Risk**: MEDIUM

**TC-WSP-004: Connection Cleanup on Unsubscribe All**
- **Priority**: MEDIUM
- **Preconditions**: 3 connections with varying loads
- **Test Steps**:
  1. Unsubscribe all tokens from connection 3
  2. Verify connection 3 closed
  3. Verify pool size reduced to 2
  4. Verify metrics updated
  5. Verify memory released
- **Expected Results**:
  - Empty connection closed automatically
  - Pool size = 2
  - Metrics show 2 connections
  - WebSocket connection terminated cleanly
  - Memory usage decreases
- **Regression Risk**: LOW

#### Test Suite: Subscribe/Unsubscribe Operations

**TC-WSP-010: Basic Subscribe Operation**
- **Priority**: CRITICAL
- **Preconditions**: Pool initialized, 1 connection available
- **Test Steps**:
  1. Call `subscribe([token1, token2, token3])`
  2. Verify KiteTicker subscribe() called with tokens
  3. Verify tokens added to connection's subscribed set
  4. Verify metrics incremented (total_subscriptions += 3)
  5. Verify operation completes within 1 second
- **Expected Results**:
  - All tokens subscribed successfully
  - Connection tracking updated
  - Metrics accurate
  - No exceptions raised
  - Thread-safe operation
- **Regression Risk**: CRITICAL

**TC-WSP-011: Subscribe with Timeout**
- **Priority**: HIGH
- **Preconditions**: Simulate slow KiteTicker response
- **Test Steps**:
  1. Mock KiteTicker subscribe() to delay 15 seconds
  2. Call subscribe() with 10-second timeout
  3. Verify TimeoutError raised
  4. Verify partial subscription state rolled back
  5. Verify metrics show error
- **Expected Results**:
  - TimeoutError raised after 10 seconds
  - Tokens NOT added to tracking (rollback)
  - Metrics show subscription_errors += 1
  - Connection state remains consistent
  - Retry possible
- **Regression Risk**: MEDIUM

**TC-WSP-012: Unsubscribe Operation**
- **Priority**: HIGH
- **Preconditions**: Connection with 100 subscribed tokens
- **Test Steps**:
  1. Unsubscribe 20 tokens
  2. Verify KiteTicker unsubscribe() called
  3. Verify tokens removed from tracking
  4. Verify metrics updated (unsubscriptions += 20)
  5. Verify remaining 80 tokens still subscribed
- **Expected Results**:
  - Specified tokens unsubscribed
  - Tracking updated correctly
  - Metrics accurate
  - Other subscriptions unaffected
  - No errors
- **Regression Risk**: MEDIUM

**TC-WSP-013: Subscribe to Already Subscribed Token**
- **Priority**: MEDIUM
- **Preconditions**: Token 256265 already subscribed
- **Test Steps**:
  1. Attempt to subscribe token 256265 again
  2. Verify duplicate detected
  3. Verify no duplicate subscribe call to KiteTicker
  4. Verify warning logged
  5. Verify operation idempotent
- **Expected Results**:
  - Duplicate detected and skipped
  - Warning logged: "Token 256265 already subscribed"
  - Metrics unchanged
  - No duplicate subscription
  - Operation completes successfully
- **Regression Risk**: LOW

#### Test Suite: Deadlock Prevention (RLock Fix)

**TC-WSP-020: RLock Reentrant Acquisition**
- **Priority**: CRITICAL (REGRESSION TEST)
- **Preconditions**: Pool with RLock (not basic Lock)
- **Test Steps**:
  1. Call `subscribe_tokens([token1])`
  2. Verify `subscribe_tokens()` acquires `_pool_lock`
  3. Verify `_get_or_create_connection_for_tokens()` called
  4. Verify inner method also acquires `_pool_lock` (reentrant)
  5. Verify no deadlock occurs
  6. Verify operation completes within 2 seconds
- **Expected Results**:
  - Reentrant lock allows same thread to acquire twice
  - No deadlock (previously would hang indefinitely)
  - Subscribe completes successfully
  - Service remains responsive
  - All subsequent operations work
- **Regression Risk**: CRITICAL (previously caused 100+ second timeouts)

**TC-WSP-021: Concurrent Subscribe from Multiple Threads**
- **Priority**: HIGH
- **Preconditions**: Pool accessible from multiple threads
- **Test Steps**:
  1. Spawn 5 threads simultaneously
  2. Each thread subscribes to 100 different tokens
  3. Monitor lock contention and acquisition
  4. Verify all subscriptions complete
  5. Verify final state: 500 tokens subscribed
- **Expected Results**:
  - RLock serializes access correctly
  - No deadlocks or race conditions
  - All 500 tokens subscribed
  - No duplicate subscriptions
  - No lost subscriptions
  - All threads complete within 10 seconds
- **Regression Risk**: CRITICAL

#### Test Suite: Health Monitoring

**TC-WSP-030: Health Check Loop**
- **Priority**: MEDIUM
- **Preconditions**: Pool with 2 active connections
- **Test Steps**:
  1. Monitor `_health_check_loop()` execution
  2. Verify loop checks each connection's last tick time
  3. Simulate stale connection (no ticks for 60 seconds)
  4. Verify health check detects stale connection
  5. Verify reconnection triggered
- **Expected Results**:
  - Health checks run every 30 seconds
  - Stale connections detected
  - Reconnection attempted automatically
  - Metrics updated (connected_status gauge)
  - Healthy connections unaffected
- **Regression Risk**: MEDIUM

**TC-WSP-031: Reconnection on Failure**
- **Priority**: HIGH
- **Preconditions**: Connection fails mid-stream
- **Test Steps**:
  1. Simulate WebSocket connection error
  2. Verify error handler triggered
  3. Verify connection marked as disconnected
  4. Verify automatic reconnection attempt
  5. Verify subscriptions re-established after reconnect
- **Expected Results**:
  - Error detected within 5 seconds
  - Reconnection initiated automatically
  - Subscriptions restored after reconnect
  - Tick stream resumes
  - Temporary gap in data acceptable
- **Regression Risk**: HIGH

#### Test Suite: Thread Safety

**TC-WSP-040: Concurrent Subscribe and Unsubscribe**
- **Priority**: HIGH
- **Preconditions**: Pool with 500 subscribed tokens
- **Test Steps**:
  1. Thread 1: Subscribe 100 new tokens
  2. Thread 2: Unsubscribe 50 existing tokens
  3. Thread 3: Subscribe 75 new tokens
  4. All operations concurrent
  5. Verify final state consistent
- **Expected Results**:
  - RLock prevents race conditions
  - Final subscription count = 500 + 100 - 50 + 75 = 625
  - No torn reads/writes
  - No data corruption
  - All operations complete successfully
- **Regression Risk**: HIGH

**TC-WSP-041: Metrics Consistency Under Load**
- **Priority**: MEDIUM
- **Preconditions**: Pool under high subscription/unsubscription load
- **Test Steps**:
  1. Perform 1000 subscribe/unsubscribe operations rapidly
  2. Query metrics after each 100 operations
  3. Verify metrics remain consistent with actual state
  4. Verify no counter overflow or negative values
  5. Verify gauge values match actual counts
- **Expected Results**:
  - Metrics always match actual state
  - No race conditions in metric updates
  - Counters monotonically increasing
  - Gauges reflect current state accurately
  - No metric anomalies
- **Regression Risk**: MEDIUM

---

### 3.3 WebSocket Server (routes_websocket.py)

#### Test Suite: Client Connection/Disconnection

**TC-WSS-001: Successful Client Connection**
- **Priority**: CRITICAL
- **Preconditions**:
  - Valid JWT token
  - WebSocket server running
- **Test Steps**:
  1. Connect WebSocket client with valid JWT
  2. Verify JWT token validated
  3. Verify connection accepted
  4. Verify "connected" message received
  5. Verify connection added to ConnectionManager
- **Expected Results**:
  - Connection established successfully
  - Response: `{"type": "connected", "connection_id": "...", "user": {...}}`
  - Connection tracked in `active_connections`
  - User info extracted from JWT
  - Metrics: active_ws_connections += 1
- **Regression Risk**: CRITICAL

**TC-WSS-002: Connection Rejection - Invalid JWT**
- **Priority**: CRITICAL
- **Preconditions**: Invalid/expired JWT token
- **Test Steps**:
  1. Attempt connection with invalid JWT
  2. Verify token validation fails
  3. Verify connection rejected with 403 status
  4. Verify error message sent to client
  5. Verify no connection created in manager
- **Expected Results**:
  - Connection refused
  - HTTP 403 Forbidden status
  - Error message: "Invalid or expired token"
  - No connection in active_connections
  - Metrics: ws_auth_failures += 1
- **Regression Risk**: CRITICAL

**TC-WSS-003: Connection Rejection - Missing Token**
- **Priority**: HIGH
- **Preconditions**: No token query parameter
- **Test Steps**:
  1. Attempt connection without ?token=... parameter
  2. Verify connection rejected immediately
  3. Verify appropriate error response
- **Expected Results**:
  - Connection refused
  - HTTP 401 Unauthorized
  - Error: "Token required"
  - No authentication attempted
- **Regression Risk**: HIGH

**TC-WSS-004: Graceful Client Disconnection**
- **Priority**: HIGH
- **Preconditions**: Client connected and active
- **Test Steps**:
  1. Establish connection
  2. Client sends close frame
  3. Verify server removes connection from manager
  4. Verify subscriptions cleaned up
  5. Verify resources released
- **Expected Results**:
  - Connection removed from active_connections
  - Token subscriptions cleared
  - Close frame acknowledged
  - Metrics: active_ws_connections -= 1
  - No memory leak
- **Regression Risk**: MEDIUM

**TC-WSS-005: Ungraceful Client Disconnection**
- **Priority**: MEDIUM
- **Preconditions**: Client connected
- **Test Steps**:
  1. Simulate network failure (client drops connection)
  2. Verify server detects disconnection
  3. Verify cleanup occurs within timeout
  4. Verify resources released
- **Expected Results**:
  - Disconnection detected within 30 seconds
  - Connection cleaned up automatically
  - Subscriptions removed
  - No dangling connections
- **Regression Risk**: MEDIUM

#### Test Suite: Authentication (JWT)

**TC-WSS-010: Valid JWT Token Verification**
- **Priority**: CRITICAL
- **Preconditions**: Valid JWT from user_service
- **Test Steps**:
  1. Generate valid JWT with user claims
  2. Connect with JWT
  3. Verify `verify_ws_token()` called
  4. Verify user info extracted (user_id, email, name)
  5. Verify connection authorized
- **Expected Results**:
  - Token validated successfully
  - User claims extracted: {user_id, email, name}
  - Connection established
  - User context available for logging
- **Regression Risk**: HIGH

**TC-WSS-011: Expired JWT Token**
- **Priority**: HIGH
- **Preconditions**: JWT with exp claim in past
- **Test Steps**:
  1. Generate expired JWT
  2. Attempt connection
  3. Verify token validation fails
  4. Verify connection rejected
- **Expected Results**:
  - Token validation fails
  - Error: "Token expired"
  - Connection rejected
  - No connection created
- **Regression Risk**: HIGH

**TC-WSS-012: JWT with Invalid Signature**
- **Priority**: CRITICAL
- **Preconditions**: JWT with tampered signature
- **Test Steps**:
  1. Generate JWT and modify signature
  2. Attempt connection
  3. Verify signature validation fails
  4. Verify connection rejected with security error
- **Expected Results**:
  - Signature verification fails
  - Error: "Invalid token signature"
  - Connection rejected
  - Security event logged
- **Regression Risk**: CRITICAL

#### Test Suite: Message Protocol

**TC-WSS-020: Subscribe Action**
- **Priority**: CRITICAL
- **Preconditions**: Client connected
- **Test Steps**:
  1. Send: `{"action": "subscribe", "tokens": [256265, 260105]}`
  2. Verify tokens added to ConnectionManager subscriptions
  3. Verify response received
  4. Verify client tracked as subscriber for tokens
- **Expected Results**:
  - Response: `{"type": "subscribed", "tokens": [256265, 260105], "total": 2}`
  - Client added to `token_subscribers[256265]`
  - Client added to `token_subscribers[260105]`
  - Ready to receive ticks for those tokens
- **Regression Risk**: CRITICAL

**TC-WSS-021: Unsubscribe Action**
- **Priority**: HIGH
- **Preconditions**:
  - Client subscribed to [256265, 260105]
- **Test Steps**:
  1. Send: `{"action": "unsubscribe", "tokens": [256265]}`
  2. Verify token 256265 removed from subscriptions
  3. Verify token 260105 still subscribed
  4. Verify response received
- **Expected Results**:
  - Response: `{"type": "unsubscribed", "tokens": [256265], "total": 1}`
  - Client removed from `token_subscribers[256265]`
  - Client remains in `token_subscribers[260105]`
  - No ticks received for 256265 after unsubscribe
- **Regression Risk**: HIGH

**TC-WSS-022: Ping/Pong Keepalive**
- **Priority**: MEDIUM
- **Preconditions**: Client connected
- **Test Steps**:
  1. Send: `{"action": "ping"}`
  2. Verify pong response received
  3. Measure round-trip time
- **Expected Results**:
  - Response: `{"type": "pong"}`
  - Response within 100ms
  - Connection remains alive
- **Regression Risk**: LOW

**TC-WSS-023: Invalid Message Format**
- **Priority**: MEDIUM
- **Preconditions**: Client connected
- **Test Steps**:
  1. Send invalid JSON: `{broken json`
  2. Verify error response received
  3. Verify connection remains open (no disconnect)
  4. Verify error logged
- **Expected Results**:
  - Response: `{"type": "error", "message": "Invalid JSON"}`
  - Connection remains open
  - Error logged with context
  - Client can retry
- **Regression Risk**: LOW

**TC-WSS-024: Unknown Action**
- **Priority**: LOW
- **Preconditions**: Client connected
- **Test Steps**:
  1. Send: `{"action": "unknown_action"}`
  2. Verify error response
  3. Verify connection stable
- **Expected Results**:
  - Response: `{"type": "error", "message": "Unknown action"}`
  - Connection remains open
  - No side effects
- **Regression Risk**: LOW

#### Test Suite: Broadcasting

**TC-WSS-030: Broadcast Tick to Subscribers**
- **Priority**: CRITICAL
- **Preconditions**:
  - 3 clients connected and subscribed to token 256265
  - 2 clients subscribed to token 260105
- **Test Steps**:
  1. Publish tick for token 256265 to Redis
  2. Verify Redis listener receives tick
  3. Verify `broadcast_tick()` called with token and data
  4. Verify all 3 subscribers for 256265 receive tick
  5. Verify 2 subscribers for 260105 do NOT receive tick
- **Expected Results**:
  - All 3 subscribers for 256265 receive: `{"type": "tick", "data": {...}}`
  - Subscribers for 260105 receive nothing
  - Broadcast completes within 50ms
  - Metrics: ticks_broadcast += 1
- **Regression Risk**: CRITICAL

**TC-WSS-031: Broadcast to Disconnected Client**
- **Priority**: MEDIUM
- **Preconditions**:
  - Client subscribed but disconnects before tick arrives
- **Test Steps**:
  1. Client subscribes to token 256265
  2. Client disconnects (connection closed)
  3. Tick published for 256265
  4. Verify broadcast skips disconnected client
  5. Verify no exception raised
- **Expected Results**:
  - Disconnected client skipped silently
  - Broadcast continues to other clients
  - No errors logged
  - Cleanup occurs on next broadcast attempt
- **Regression Risk**: MEDIUM

**TC-WSS-032: High-Frequency Broadcasting**
- **Priority**: HIGH
- **Preconditions**:
  - 10 clients subscribed to same token
  - 100 ticks/second rate
- **Test Steps**:
  1. Publish 100 ticks in 1 second
  2. Monitor broadcast latency for each tick
  3. Verify all clients receive all ticks
  4. Measure p95/p99 latency
- **Expected Results**:
  - All clients receive all 100 ticks
  - p95 broadcast latency < 100ms
  - p99 broadcast latency < 200ms
  - No tick drops
  - No backpressure errors
- **Regression Risk**: HIGH

#### Test Suite: Redis Pub/Sub Integration

**TC-WSS-040: Redis Listener Startup**
- **Priority**: CRITICAL
- **Preconditions**: Redis accessible
- **Test Steps**:
  1. Start WebSocket server
  2. Verify `redis_tick_listener()` task created
  3. Verify Redis pub/sub connection established
  4. Verify pattern subscription to "ticker:*"
  5. Verify listener running
- **Expected Results**:
  - Listener task created and running
  - Subscribed to pattern: "ticker:*"
  - Ready to receive messages
  - Task doesn't crash during startup
- **Regression Risk**: CRITICAL

**TC-WSS-041: Redis Message Processing**
- **Priority**: CRITICAL
- **Preconditions**: Listener active
- **Test Steps**:
  1. Publish message to "ticker:nifty:options" channel
  2. Verify listener receives pmessage
  3. Verify message parsed as JSON
  4. Verify `broadcast_tick()` called with parsed data
  5. Verify tick delivered to subscribers
- **Expected Results**:
  - Message received within 10ms
  - JSON parsed successfully
  - Broadcast triggered
  - Subscribers receive tick
- **Regression Risk**: CRITICAL

**TC-WSS-042: Redis Connection Failure Recovery**
- **Priority**: HIGH
- **Preconditions**: Listener running
- **Test Steps**:
  1. Stop Redis server
  2. Verify listener detects connection failure
  3. Verify reconnection attempted
  4. Restart Redis server
  5. Verify listener reconnects and resumes
- **Expected Results**:
  - Connection failure detected
  - Reconnection attempts logged
  - Automatic recovery after Redis restart
  - Subscription restored
  - No manual intervention required
- **Regression Risk**: HIGH

**TC-WSS-043: Invalid JSON from Redis**
- **Priority**: MEDIUM
- **Preconditions**: Listener active
- **Test Steps**:
  1. Publish invalid JSON to Redis channel
  2. Verify listener catches JSON parse error
  3. Verify error logged with message content
  4. Verify listener continues processing subsequent messages
- **Expected Results**:
  - Parse error caught and logged
  - Invalid message skipped
  - Listener remains active
  - Next valid message processed normally
- **Regression Risk**: MEDIUM

---

### 3.4 Greeks Calculator

#### Test Suite: Black-Scholes Calculations

**TC-GRK-001: Call Option Delta Calculation**
- **Priority**: CRITICAL
- **Preconditions**: GreeksCalculator initialized
- **Test Steps**:
  1. Calculate Greeks for ATM call option
     - Spot: 19000, Strike: 19000, IV: 0.15, Time: 7 days
  2. Verify delta approximately 0.5 (ATM call)
  3. Calculate Greeks for ITM call (spot > strike)
     - Spot: 19500, Strike: 19000
  4. Verify delta > 0.5 (ITM call has higher delta)
  5. Calculate Greeks for OTM call (spot < strike)
     - Spot: 18500, Strike: 19000
  6. Verify delta < 0.5 (OTM call has lower delta)
- **Expected Results**:
  - ATM call delta: 0.45 - 0.55
  - ITM call delta: > 0.55
  - OTM call delta: < 0.45
  - Delta always between 0 and 1 for calls
  - Calculations match Black-Scholes model
- **Regression Risk**: CRITICAL (data accuracy)

**TC-GRK-002: Put Option Delta Calculation**
- **Priority**: CRITICAL
- **Test Steps**:
  1. Calculate Greeks for ATM put option
  2. Verify delta approximately -0.5
  3. Calculate for ITM put (spot < strike)
  4. Verify delta < -0.5 (more negative)
  5. Calculate for OTM put (spot > strike)
  6. Verify delta > -0.5 (less negative)
- **Expected Results**:
  - ATM put delta: -0.55 to -0.45
  - ITM put delta: < -0.55
  - OTM put delta: > -0.45
  - Delta always between -1 and 0 for puts
- **Regression Risk**: CRITICAL

**TC-GRK-003: Gamma Calculation Symmetry**
- **Priority**: HIGH
- **Test Steps**:
  1. Calculate gamma for call and put at same strike
  2. Verify gamma identical for both (put-call symmetry)
  3. Verify gamma highest for ATM options
  4. Verify gamma decreases for deep ITM/OTM
- **Expected Results**:
  - Call gamma = Put gamma (same strike/spot/time)
  - ATM gamma > ITM gamma
  - ATM gamma > OTM gamma
  - Gamma always positive
  - Gamma decreases as expiry approaches
- **Regression Risk**: HIGH

**TC-GRK-004: Theta (Time Decay) Calculation**
- **Priority**: HIGH
- **Test Steps**:
  1. Calculate theta for ATM option with 30 days to expiry
  2. Verify theta negative (time decay)
  3. Calculate theta for same option with 7 days to expiry
  4. Verify theta more negative (accelerated decay)
  5. Calculate theta for 1 day to expiry
  6. Verify theta highly negative
- **Expected Results**:
  - Theta always negative (for long options)
  - Theta_7days < Theta_30days (more negative)
  - Theta_1day << Theta_7days (much more negative)
  - Theta accelerates near expiry
- **Regression Risk**: HIGH

**TC-GRK-005: Vega (Volatility Sensitivity) Calculation**
- **Priority**: MEDIUM
- **Test Steps**:
  1. Calculate vega for ATM option
  2. Verify vega positive
  3. Verify vega higher for longer-dated options
  4. Verify vega lower for deep ITM/OTM options
- **Expected Results**:
  - Vega always positive
  - Vega_30days > Vega_7days
  - ATM vega > OTM vega
  - Vega in realistic range (0-100)
- **Regression Risk**: MEDIUM

#### Test Suite: Implied Volatility Derivation

**TC-GRK-010: IV from Market Price**
- **Priority**: CRITICAL
- **Test Steps**:
  1. Use known option price: Rs. 250
  2. Calculate implied volatility
  3. Verify IV in realistic range (5% - 50%)
  4. Use calculated IV to reprice option
  5. Verify reprice matches original market price (within 1%)
- **Expected Results**:
  - IV derived successfully
  - IV between 0.05 and 0.50
  - Reprice accuracy within 1% of market price
  - No convergence failures
- **Regression Risk**: CRITICAL

**TC-GRK-011: IV for Zero Premium**
- **Priority**: HIGH
- **Test Steps**:
  1. Attempt IV calculation for option price = 0
  2. Verify graceful handling
  3. Verify default IV returned (or 0.0)
  4. Verify no exception raised
- **Expected Results**:
  - No exception raised
  - Returns default IV (0.0 or configured default)
  - Warning logged
  - Calculation continues
- **Regression Risk**: MEDIUM

**TC-GRK-012: IV for Deeply OTM Option**
- **Priority**: MEDIUM
- **Test Steps**:
  1. Calculate IV for option with 0.01 price (deeply OTM)
  2. Verify IV derivation converges or fails gracefully
  3. Verify no infinite loop
  4. Verify reasonable IV returned
- **Expected Results**:
  - Convergence within 100 iterations or timeout
  - IV returned or default used
  - No infinite loop
  - Warning if convergence failed
- **Regression Risk**: MEDIUM

#### Test Suite: Edge Cases

**TC-GRK-020: Zero Time to Expiry**
- **Priority**: CRITICAL
- **Test Steps**:
  1. Calculate Greeks with time_to_expiry = 0.0
  2. Verify graceful handling (no division by zero)
  3. Verify realistic Greek values returned
- **Expected Results**:
  - No exception raised
  - Delta = 1.0 (for ITM call) or 0.0 (for OTM call)
  - Theta = 0.0 (no time left)
  - Vega = 0.0 (no sensitivity)
  - Gamma = 0.0 or very small
- **Regression Risk**: CRITICAL

**TC-GRK-021: Negative Time to Expiry**
- **Priority**: HIGH
- **Test Steps**:
  1. Attempt calculation with negative time_to_expiry
  2. Verify error handling
  3. Verify appropriate error message
- **Expected Results**:
  - ValueError or similar exception raised
  - Error message: "Time to expiry must be >= 0"
  - No calculation attempted
- **Regression Risk**: MEDIUM

**TC-GRK-022: Extreme Volatility Values**
- **Priority**: MEDIUM
- **Test Steps**:
  1. Calculate with IV = 1.0 (100% volatility)
  2. Verify calculation completes
  3. Calculate with IV = 0.01 (1% volatility)
  4. Verify calculation completes
  5. Verify Greeks in expected ranges
- **Expected Results**:
  - Both calculations complete
  - High IV → Higher option prices, higher vega
  - Low IV → Lower option prices, lower vega
  - No overflow or underflow
- **Regression Risk**: MEDIUM

**TC-GRK-023: NaN/Infinity Inputs**
- **Priority**: HIGH
- **Test Steps**:
  1. Call calculate_greeks with NaN spot price
  2. Verify error raised or 0.0 returned
  3. Call with Infinity strike price
  4. Verify graceful handling
- **Expected Results**:
  - Invalid inputs detected
  - Error raised or default values returned
  - No NaN propagation to output
  - Warning logged
- **Regression Risk**: HIGH

#### Test Suite: Historical Greeks Enrichment

**TC-GRK-030: Enrich Single Candle**
- **Priority**: CRITICAL
- **Preconditions**:
  - Option candle with OHLC
  - Underlying price available
- **Test Steps**:
  1. Call `enrich_option_candles()` with single candle
  2. Verify Greeks calculated using candle close price
  3. Verify all Greeks present (delta, gamma, theta, vega)
  4. Verify original candle data preserved
  5. Verify "greeks" field added
- **Expected Results**:
  - Original candle unchanged
  - New field: `candle["greeks"] = {delta, gamma, theta, vega}`
  - Greeks calculated at candle timestamp
  - Underlying price fetched for same timestamp
- **Regression Risk**: CRITICAL

**TC-GRK-031: Enrich Multiple Candles**
- **Priority**: CRITICAL
- **Test Steps**:
  1. Enrich 100 historical candles
  2. Verify all candles enriched
  3. Verify underlying data fetched efficiently (batch)
  4. Verify no N+1 query pattern
- **Expected Results**:
  - All 100 candles enriched
  - Underlying data fetched in single or few queries
  - Enrichment completes within 5 seconds
  - No database query explosion
- **Regression Risk**: HIGH (N+1 query issue identified)

**TC-GRK-032: Missing Underlying Data**
- **Priority**: MEDIUM
- **Test Steps**:
  1. Enrich option candle where underlying data unavailable
  2. Verify graceful fallback
  3. Verify candle returned without Greeks or with estimate
- **Expected Results**:
  - Warning logged: "Underlying data not found"
  - Candle returned (possibly without Greeks)
  - Or Greeks estimated using last known underlying price
  - No exception raised
  - Process continues for other candles
- **Regression Risk**: MEDIUM

---

### 3.5 Order Executor

#### Test Suite: Task Lifecycle

**TC-ORD-001: Create and Execute Order Task**
- **Priority**: CRITICAL
- **Preconditions**: OrderExecutor started
- **Test Steps**:
  1. Create OrderTask: place_order with params
  2. Submit task to executor
  3. Verify task queued with PENDING status
  4. Wait for execution
  5. Verify task status changes: PENDING → RUNNING → COMPLETED
  6. Verify result populated
- **Expected Results**:
  - Task queued immediately
  - Execution starts within poll_interval (1 second)
  - Status transitions correct
  - Result contains order_id and status
  - Execution completes within 5 seconds
- **Regression Risk**: CRITICAL

**TC-ORD-002: Task Retry on Transient Failure**
- **Priority**: CRITICAL
- **Test Steps**:
  1. Mock Kite API to fail once, then succeed
  2. Submit order task
  3. Verify first attempt fails
  4. Verify task status: RUNNING → RETRYING
  5. Verify second attempt succeeds
  6. Verify final status: COMPLETED
- **Expected Results**:
  - First failure logged
  - Task status = RETRYING
  - Backoff delay applied (exponential)
  - Second attempt succeeds
  - Final status = COMPLETED
  - Retry count tracked
- **Regression Risk**: CRITICAL

**TC-ORD-003: Task Fails After Max Retries**
- **Priority**: HIGH
- **Test Steps**:
  1. Mock Kite API to always fail
  2. Submit task with max_attempts = 3
  3. Verify 3 attempts made
  4. Verify final status: DEAD_LETTER
  5. Verify task added to dead letter queue
- **Expected Results**:
  - Exactly 3 attempts made
  - Each attempt logged with context
  - Final status = DEAD_LETTER
  - Error details preserved
  - Task removed from active queue
- **Regression Risk**: HIGH

**TC-ORD-004: Idempotency Key Prevents Duplicate Execution**
- **Priority**: CRITICAL
- **Test Steps**:
  1. Submit task with idempotency_key = "key1"
  2. Wait for completion
  3. Submit identical task with same idempotency_key
  4. Verify second task skipped or returns cached result
- **Expected Results**:
  - Second task detected as duplicate
  - Returns result from first execution
  - No duplicate order placed
  - Idempotency enforced
- **Regression Risk**: CRITICAL

#### Test Suite: Circuit Breaker State Machine

**TC-ORD-010: Circuit Breaker CLOSED State**
- **Priority**: HIGH
- **Preconditions**: Circuit breaker initialized (CLOSED)
- **Test Steps**:
  1. Execute 10 successful order tasks
  2. Verify circuit breaker remains CLOSED
  3. Verify failure_count = 0
  4. Verify all tasks execute immediately
- **Expected Results**:
  - All tasks execute without delay
  - Circuit breaker state = CLOSED
  - Failure count resets after each success
  - No artificial delays
- **Regression Risk**: MEDIUM

**TC-ORD-011: Circuit Breaker Opens After Failures**
- **Priority**: CRITICAL
- **Test Steps**:
  1. Mock Kite API to return rate limit (429) errors
  2. Submit 5 consecutive order tasks
  3. Verify all 5 fail
  4. Verify circuit breaker opens after 5th failure
  5. Verify state = OPEN
- **Expected Results**:
  - First 5 tasks attempted and failed
  - Failure threshold = 5 reached
  - Circuit breaker state changes: CLOSED → OPEN
  - Open timestamp recorded
  - Metrics: circuit_breaker_opens += 1
- **Regression Risk**: CRITICAL

**TC-ORD-012: Circuit Breaker Rejects Requests When OPEN**
- **Priority**: CRITICAL
- **Preconditions**: Circuit breaker in OPEN state
- **Test Steps**:
  1. Submit new order task
  2. Verify `can_execute()` returns False
  3. Verify task not executed
  4. Verify task status = RETRYING (will retry after timeout)
- **Expected Results**:
  - Task not executed immediately
  - Error: "Circuit breaker open"
  - Task queued for retry after recovery_timeout
  - Circuit breaker state remains OPEN
- **Regression Risk**: CRITICAL

**TC-ORD-013: Circuit Breaker Enters HALF_OPEN After Timeout**
- **Priority**: HIGH
- **Preconditions**: Circuit breaker OPEN for 60+ seconds
- **Test Steps**:
  1. Wait for recovery_timeout (60 seconds)
  2. Submit new order task
  3. Verify circuit breaker transitions: OPEN → HALF_OPEN
  4. Verify task execution allowed
- **Expected Results**:
  - After 60 seconds, state = HALF_OPEN
  - Next task allowed to execute (test request)
  - Limited concurrency in HALF_OPEN (max 3 calls)
- **Regression Risk**: HIGH

**TC-ORD-014: Circuit Breaker Closes After Successful Test**
- **Priority**: HIGH
- **Preconditions**: Circuit breaker HALF_OPEN
- **Test Steps**:
  1. Submit order task
  2. Mock Kite API to succeed
  3. Verify task succeeds
  4. Verify circuit breaker closes: HALF_OPEN → CLOSED
  5. Verify failure_count reset to 0
- **Expected Results**:
  - Test request succeeds
  - Circuit breaker state = CLOSED
  - Failure count = 0
  - Normal operation resumed
  - Metrics: circuit_breaker_closes += 1
- **Regression Risk**: HIGH

**TC-ORD-015: Circuit Breaker Reopens on HALF_OPEN Failure**
- **Priority**: HIGH
- **Preconditions**: Circuit breaker HALF_OPEN
- **Test Steps**:
  1. Submit order task
  2. Mock Kite API to fail
  3. Verify circuit breaker reopens: HALF_OPEN → OPEN
  4. Verify recovery timeout restarted
- **Expected Results**:
  - Test request fails
  - Circuit breaker state = OPEN
  - New recovery timeout started (60s)
  - Subsequent requests rejected
- **Regression Risk**: HIGH

#### Test Suite: Retry Logic

**TC-ORD-020: Exponential Backoff**
- **Priority**: MEDIUM
- **Test Steps**:
  1. Create task that fails repeatedly
  2. Monitor retry intervals
  3. Verify exponential backoff: 1s, 2s, 4s, 8s, 16s
  4. Verify max backoff cap applied
- **Expected Results**:
  - Retry delays follow exponential pattern
  - Delays: approximately 1, 2, 4, 8, 16 seconds
  - Max backoff respected (e.g., 30s cap)
  - Total retry time reasonable
- **Regression Risk**: LOW

**TC-ORD-021: Retry Only on Retryable Errors**
- **Priority**: HIGH
- **Test Steps**:
  1. Submit task that fails with non-retryable error (e.g., invalid params)
  2. Verify task fails immediately
  3. Verify no retry attempted
  4. Verify status = DEAD_LETTER
- **Expected Results**:
  - Non-retryable errors fail immediately
  - No retry attempts
  - Clear error message in result
  - Status = DEAD_LETTER
- **Regression Risk**: MEDIUM

#### Test Suite: Dead Letter Queue

**TC-ORD-030: Task Added to DLQ After Max Retries**
- **Priority**: HIGH
- **Test Steps**:
  1. Submit task that always fails
  2. Wait for max_attempts exhausted
  3. Verify task in dead letter queue
  4. Verify task metadata preserved
- **Expected Results**:
  - Task in DLQ with status = DEAD_LETTER
  - All attempt details logged
  - Error details preserved
  - Task can be inspected/retried manually
- **Regression Risk**: MEDIUM

**TC-ORD-031: DLQ Task Retrieval**
- **Priority**: MEDIUM
- **Test Steps**:
  1. Query dead letter queue
  2. Verify all failed tasks returned
  3. Verify task details complete
- **Expected Results**:
  - All DLQ tasks retrievable
  - Task IDs, errors, timestamps available
  - Can filter by error type
- **Regression Risk**: LOW

---

### 3.6 Subscription Management

#### Test Suite: CRUD Operations

**TC-SUB-001: Create Subscription**
- **Priority**: CRITICAL
- **Preconditions**: Instrument token valid in registry
- **Test Steps**:
  1. POST /subscriptions with valid instrument_token
  2. Verify subscription created in database
  3. Verify status = "active"
  4. Verify account_id assigned
  5. Verify timestamps populated
- **Expected Results**:
  - HTTP 200 response
  - Subscription record in database
  - Fields: {token, tradingsymbol, segment, status="active", account_id, created_at, updated_at}
  - Subscription immediately active
- **Regression Risk**: CRITICAL

**TC-SUB-002: Create Duplicate Subscription**
- **Priority**: HIGH
- **Test Steps**:
  1. Create subscription for token 256265
  2. Attempt to create again for same token
  3. Verify upsert behavior (update existing)
  4. Verify no duplicate created
- **Expected Results**:
  - Second request updates existing subscription
  - No duplicate record
  - updated_at timestamp changed
  - Status remains "active"
- **Regression Risk**: MEDIUM

**TC-SUB-003: List Active Subscriptions**
- **Priority**: HIGH
- **Preconditions**: Database has mix of active and inactive subscriptions
- **Test Steps**:
  1. GET /subscriptions?status=active
  2. Verify only active subscriptions returned
  3. Verify pagination works (if implemented)
- **Expected Results**:
  - Only subscriptions with status="active" returned
  - Inactive subscriptions excluded
  - Response format: `{"subscriptions": [...]}`
  - Count matches database query
- **Regression Risk**: MEDIUM

**TC-SUB-004: Deactivate Subscription**
- **Priority**: CRITICAL
- **Test Steps**:
  1. DELETE /subscriptions/{token}
  2. Verify subscription marked as inactive
  3. Verify not deleted from database (soft delete)
  4. Verify streaming stops for token
- **Expected Results**:
  - HTTP 200 response
  - Subscription status changed to "inactive"
  - Record still in database
  - Unsubscribed from WebSocket pool
  - No more ticks for token
- **Regression Risk**: CRITICAL

**TC-SUB-005: Update Account Assignment**
- **Priority**: MEDIUM
- **Test Steps**:
  1. Update subscription account_id
  2. Verify database updated
  3. Verify subscription migrated to new account
- **Expected Results**:
  - Account ID updated
  - Subscription moves to new account's task
  - Streaming continues without interruption
- **Regression Risk**: MEDIUM

#### Test Suite: State Persistence

**TC-SUB-010: Subscriptions Survive Restart**
- **Priority**: CRITICAL
- **Preconditions**: 50 active subscriptions in database
- **Test Steps**:
  1. Stop ticker_service
  2. Restart ticker_service
  3. Verify all 50 subscriptions reloaded
  4. Verify streaming resumes
- **Expected Results**:
  - All active subscriptions loaded on startup
  - Streaming resumes within 30 seconds
  - No subscriptions lost
  - State matches pre-restart
- **Regression Risk**: CRITICAL

**TC-SUB-011: Account Assignment Persistence**
- **Priority**: HIGH
- **Test Steps**:
  1. Create subscriptions distributed across 3 accounts
  2. Restart service
  3. Verify account assignments preserved
  4. Verify no re-balancing on restart (assignments stable)
- **Expected Results**:
  - Each subscription returns to same account
  - No unnecessary rebalancing
  - Assignments stable across restarts
- **Regression Risk**: MEDIUM

#### Test Suite: Active/Inactive Transitions

**TC-SUB-020: Activate Inactive Subscription**
- **Priority**: MEDIUM
- **Test Steps**:
  1. Create subscription with status="inactive"
  2. Update status to "active"
  3. Verify streaming starts
- **Expected Results**:
  - Subscription activated
  - Streaming begins within 10 seconds
  - Ticks received
- **Regression Risk**: MEDIUM

**TC-SUB-021: Reactivate Deactivated Subscription**
- **Priority**: MEDIUM
- **Test Steps**:
  1. Deactivate active subscription
  2. Reactivate same subscription
  3. Verify streaming resumes
- **Expected Results**:
  - Status: active → inactive → active
  - Streaming stops then resumes
  - No data corruption
- **Regression Risk**: LOW

---

### 3.7 Error Handling & Resilience

#### Test Suite: Redis Connection Failures

**TC-ERR-001: Redis Publish Failure with Retry**
- **Priority**: CRITICAL
- **Preconditions**: Redis available initially
- **Test Steps**:
  1. Start streaming ticks
  2. Stop Redis mid-stream
  3. Verify publish fails
  4. Verify retry attempted (2 attempts)
  5. Restart Redis
  6. Verify recovery and publish succeeds
- **Expected Results**:
  - First publish fails
  - Retry attempted automatically
  - Error logged with context
  - After Redis restart, publishes resume
  - No data loss after recovery
- **Regression Risk**: CRITICAL

**TC-ERR-002: Redis Unavailable on Startup**
- **Priority**: HIGH
- **Test Steps**:
  1. Stop Redis
  2. Attempt to start ticker_service
  3. Verify startup fails gracefully
  4. Verify clear error message
- **Expected Results**:
  - Startup fails with Redis connection error
  - Error message: "Failed to connect to Redis"
  - No partial state created
  - Service can restart after Redis available
- **Regression Risk**: HIGH

**TC-ERR-003: Redis Connection Reset Mid-Stream**
- **Priority**: HIGH
- **Test Steps**:
  1. Active streaming in progress
  2. Trigger Redis connection reset
  3. Verify automatic reconnection
  4. Verify streaming resumes
- **Expected Results**:
  - Connection reset detected
  - Reconnection attempted automatically
  - Streaming resumes within 10 seconds
  - Temporary tick gap acceptable
- **Regression Risk**: HIGH

#### Test Suite: Database Connection Failures

**TC-ERR-010: PostgreSQL Connection Pool Exhaustion**
- **Priority**: HIGH
- **Preconditions**: Connection pool max_size=5
- **Test Steps**:
  1. Create 5 concurrent long-running queries
  2. Attempt 6th query
  3. Verify timeout after 10 seconds
  4. Verify appropriate error raised
- **Expected Results**:
  - 6th connection waits for available connection
  - After 10s timeout, error raised
  - Error: "Connection pool timeout"
  - Pool state recovers after queries complete
- **Regression Risk**: MEDIUM

**TC-ERR-011: Database Unavailable on Startup**
- **Priority**: CRITICAL
- **Test Steps**:
  1. Stop PostgreSQL
  2. Attempt to start ticker_service
  3. Verify startup fails
  4. Verify error message clear
- **Expected Results**:
  - Startup fails gracefully
  - Error: "Failed to connect to database"
  - No zombie processes
  - Can retry after database restored
- **Regression Risk**: CRITICAL

**TC-ERR-012: Database Connection Lost During Operation**
- **Priority**: HIGH
- **Test Steps**:
  1. Service running normally
  2. Stop PostgreSQL
  3. Attempt subscription reload
  4. Verify error handled gracefully
  5. Restart PostgreSQL
  6. Verify recovery
- **Expected Results**:
  - Database query fails with connection error
  - Error logged
  - Service remains running (degraded mode)
  - After database restart, queries resume
- **Regression Risk**: HIGH

#### Test Suite: Kite API Errors

**TC-ERR-020: Rate Limit (429) Error**
- **Priority**: CRITICAL
- **Test Steps**:
  1. Simulate Kite API 429 response
  2. Verify circuit breaker triggered
  3. Verify failover to next account
  4. Verify operation retried on different account
- **Expected Results**:
  - Rate limit detected
  - Circuit breaker increments failure count
  - Account marked as rate-limited
  - Failover to next account
  - Operation succeeds on alternate account
- **Regression Risk**: CRITICAL

**TC-ERR-021: Kite API Timeout**
- **Priority**: HIGH
- **Test Steps**:
  1. Mock Kite API to timeout (no response)
  2. Verify timeout after configured duration (10s)
  3. Verify retry attempted
  4. Verify eventual failover if retries exhausted
- **Expected Results**:
  - Request times out after 10 seconds
  - Timeout error logged
  - Retry attempted with backoff
  - After max retries, failover to next account
- **Regression Risk**: HIGH

**TC-ERR-022: Invalid API Credentials**
- **Priority**: CRITICAL
- **Test Steps**:
  1. Configure invalid API key
  2. Attempt to start ticker_service
  3. Verify authentication fails
  4. Verify clear error message
- **Expected Results**:
  - Authentication fails
  - Error: "Invalid API credentials"
  - Startup aborted
  - Account skipped (if multi-account)
- **Regression Risk**: CRITICAL

**TC-ERR-023: Malformed API Response**
- **Priority**: MEDIUM
- **Test Steps**:
  1. Mock Kite API to return invalid JSON
  2. Verify parsing error caught
  3. Verify error logged with response content
  4. Verify operation retried or skipped
- **Expected Results**:
  - JSON parse error caught
  - Error logged with raw response
  - Operation retried or marked as failed
  - Service remains stable
- **Regression Risk**: MEDIUM

#### Test Suite: Network Failures

**TC-ERR-030: Network Partition During Streaming**
- **Priority**: MEDIUM
- **Preconditions**: Simulate network failure
- **Test Steps**:
  1. Active streaming in progress
  2. Drop all network packets (simulate partition)
  3. Verify streaming tasks detect failure
  4. Restore network
  5. Verify recovery
- **Expected Results**:
  - Network failure detected within 30 seconds
  - Reconnection attempted
  - After network restored, streaming resumes
  - Temporary data gap acceptable
- **Regression Risk**: MEDIUM

**TC-ERR-031: DNS Resolution Failure**
- **Priority**: LOW
- **Test Steps**:
  1. Configure invalid hostname for Redis/PostgreSQL
  2. Attempt startup
  3. Verify DNS resolution error caught
  4. Verify clear error message
- **Expected Results**:
  - DNS error detected
  - Error: "Failed to resolve hostname"
  - Startup aborted
  - Can retry after DNS fixed
- **Regression Risk**: LOW

#### Test Suite: Recovery Scenarios

**TC-ERR-040: Full System Recovery After Failures**
- **Priority**: CRITICAL
- **Test Steps**:
  1. Simulate cascading failures (Redis, PostgreSQL, Kite API all fail)
  2. Verify service enters degraded mode
  3. Restore services one by one
  4. Verify incremental recovery
  5. Verify full functionality restored
- **Expected Results**:
  - Service survives multiple failures
  - Degraded mode activated
  - Health check shows degraded status
  - As services restore, functionality returns
  - Final state: full operation restored
- **Regression Risk**: CRITICAL

**TC-ERR-041: Graceful Degradation**
- **Priority**: HIGH
- **Test Steps**:
  1. Disable non-critical component (e.g., order executor)
  2. Verify core streaming continues
  3. Verify health check shows partial degradation
- **Expected Results**:
  - Core streaming unaffected
  - Health check: `{"status": "degraded", "reason": "order_executor_unavailable"}`
  - Non-critical features disabled
  - Critical features operational
- **Regression Risk**: MEDIUM

---

## 4. Performance Test Cases

### 4.1 Load Testing

**TC-PERF-001: Sustained Load - 500 Concurrent Subscriptions**
- **Priority**: CRITICAL
- **Objective**: Validate system handles expected production load
- **Test Steps**:
  1. Configure 500 option subscriptions across 1 account
  2. Generate mock ticks at 10 ticks/second per instrument
  3. Maintain load for 30 minutes
  4. Monitor: CPU, memory, tick latency, publish rate
- **Success Criteria**:
  - Tick publish latency p95 < 100ms
  - Tick publish latency p99 < 200ms
  - Memory stable (no leaks, < 10% growth over 30 min)
  - CPU utilization < 50%
  - No errors or warnings in logs
  - All ticks published successfully (0% drop rate)
- **Regression Risk**: CRITICAL

**TC-PERF-002: High Load - 1000 Concurrent Subscriptions**
- **Priority**: HIGH
- **Objective**: Test scaling to 1000 instrument limit
- **Test Steps**:
  1. Configure 1000 subscriptions (single account max)
  2. Generate ticks at 20 ticks/second per instrument
  3. Run for 15 minutes
  4. Measure throughput, latency, resource usage
- **Success Criteria**:
  - Total throughput: 20,000 ticks/second processed
  - p95 latency < 150ms
  - p99 latency < 300ms
  - Memory < 1 GB
  - CPU < 70%
  - Backpressure level = HEALTHY or WARNING (not CRITICAL)
- **Regression Risk**: HIGH

**TC-PERF-003: Multi-Account Load - 2000 Subscriptions**
- **Priority**: HIGH
- **Objective**: Validate multi-account orchestration performance
- **Test Steps**:
  1. Configure 2000 subscriptions across 2 accounts (1000 each)
  2. Generate ticks at 15 ticks/second
  3. Run for 20 minutes
  4. Monitor per-account metrics and aggregate
- **Success Criteria**:
  - Both accounts streaming simultaneously
  - Load balanced evenly (1000/1000)
  - Combined throughput: 30,000 ticks/second
  - p95 latency < 150ms
  - No account failovers
  - Memory < 1.5 GB
- **Regression Risk**: HIGH

### 4.2 Stress Testing

**TC-PERF-010: Stress Test - 3000 Subscriptions**
- **Priority**: MEDIUM
- **Objective**: Find breaking point beyond normal capacity
- **Test Steps**:
  1. Configure 3000 subscriptions across 3 accounts
  2. Generate ticks at 25 ticks/second
  3. Run until system degrades or 10 minutes
  4. Identify bottlenecks
- **Success Criteria**:
  - System handles load or degrades gracefully
  - Backpressure monitoring triggers warnings
  - No crashes or data corruption
  - Clear metrics showing saturation point
  - Identify bottleneck (CPU, memory, Redis, network)
- **Expected Degradation**:
  - Latency p99 may exceed 500ms
  - Some tick drops acceptable (< 5%)
  - Backpressure level = CRITICAL or OVERLOAD
- **Regression Risk**: MEDIUM

**TC-PERF-011: Memory Stress - Sustained High Subscription Count**
- **Priority**: MEDIUM
- **Objective**: Detect memory leaks
- **Test Steps**:
  1. Run 1000 subscriptions for 8 hours (overnight)
  2. Monitor memory usage every 5 minutes
  3. Calculate memory growth rate
- **Success Criteria**:
  - Memory growth < 5% per hour
  - No unbounded growth (leak)
  - Memory stabilizes after initial ramp-up
  - Final memory < 1.5 GB
- **Regression Risk**: MEDIUM

### 4.3 Latency Measurements

**TC-PERF-020: Tick Publish Latency Baseline**
- **Priority**: CRITICAL
- **Objective**: Establish baseline latency metrics
- **Test Steps**:
  1. Subscribe to 100 instruments
  2. Generate 1000 ticks with timestamps
  3. Measure time from tick generation to Redis publish
  4. Calculate p50, p95, p99, max latencies
- **Success Criteria**:
  - p50 latency < 20ms
  - p95 latency < 50ms
  - p99 latency < 100ms
  - Max latency < 200ms
- **Regression Risk**: CRITICAL (baseline for future comparisons)

**TC-PERF-021: End-to-End WebSocket Latency**
- **Priority**: HIGH
- **Objective**: Measure client-perceived latency
- **Test Steps**:
  1. Connect WebSocket client
  2. Subscribe to instrument
  3. Generate tick with timestamp
  4. Measure time from generation to client receipt
  5. Include: generation → Redis → listener → broadcast → client
- **Success Criteria**:
  - p50 E2E latency < 50ms
  - p95 E2E latency < 150ms
  - p99 E2E latency < 300ms
- **Regression Risk**: HIGH

**TC-PERF-022: Subscription Reload Latency**
- **Priority**: HIGH
- **Objective**: Measure reload operation performance
- **Test Steps**:
  1. Start with 500 active subscriptions
  2. Add 100 new subscriptions to database
  3. Trigger reload
  4. Measure time to complete reload
  5. Measure impact on ongoing streaming
- **Success Criteria**:
  - Reload completes within 30 seconds
  - Streaming continues with minimal interruption (< 2s pause)
  - New subscriptions active within 60 seconds
  - No tick losses during reload
- **Regression Risk**: CRITICAL (previously had 100+ second timeout)

### 4.4 Backpressure Scenarios

**TC-PERF-030: Redis Slow Consumer**
- **Priority**: HIGH
- **Objective**: Test backpressure handling when Redis slow
- **Test Steps**:
  1. Artificially slow Redis publish operations (100ms delay)
  2. Generate high tick rate (50 ticks/second)
  3. Monitor backpressure metrics
  4. Verify backpressure level escalates appropriately
- **Success Criteria**:
  - Backpressure level escalates: HEALTHY → WARNING → CRITICAL
  - Pending publishes queue tracked
  - Dropped messages counted (if threshold exceeded)
  - Service doesn't crash under backpressure
  - Recovery after Redis returns to normal speed
- **Regression Risk**: HIGH

**TC-PERF-031: WebSocket Client Slow Consumer**
- **Priority**: MEDIUM
- **Objective**: Handle slow WebSocket clients gracefully
- **Test Steps**:
  1. Connect client that processes ticks slowly (intentional delay)
  2. Stream ticks at normal rate
  3. Monitor client's receive buffer
  4. Verify server doesn't block on slow client
- **Success Criteria**:
  - Fast clients unaffected by slow client
  - Slow client's buffer grows but doesn't block server
  - Optional: Slow client disconnected after buffer threshold
  - Server remains responsive
- **Regression Risk**: MEDIUM

### 4.5 Soak Testing

**TC-PERF-040: 8-Hour Soak Test**
- **Priority**: HIGH
- **Objective**: Detect memory leaks and resource exhaustion
- **Test Steps**:
  1. Configure 500 subscriptions
  2. Run continuous streaming for 8 hours
  3. Monitor: memory, CPU, file descriptors, connections
  4. Check for degradation over time
- **Success Criteria**:
  - Memory stable (< 5% growth over 8 hours)
  - CPU utilization consistent
  - No file descriptor leaks
  - No connection pool leaks
  - Performance metrics stable (no degradation)
  - No crashes or restarts
- **Regression Risk**: MEDIUM

---

## 5. Regression Test Suite

### 5.1 API Contract Tests

**Purpose**: Ensure API response schemas unchanged

**TC-REG-001: GET /subscriptions Response Schema**
- **Test**: Validate exact response format
- **Expected Schema**:
```json
{
  "subscriptions": [
    {
      "instrument_token": "integer",
      "tradingsymbol": "string",
      "segment": "string",
      "status": "string (active|inactive)",
      "requested_mode": "string (FULL|QUOTE|LTP)",
      "account_id": "string | null",
      "created_at": "ISO 8601 timestamp",
      "updated_at": "ISO 8601 timestamp"
    }
  ]
}
```
- **Regression Risk**: CRITICAL (breaking change for clients)

**TC-REG-002: POST /subscriptions Response**
- **Expected Schema**:
```json
{
  "message": "Subscription created",
  "instrument_token": "integer"
}
```
- **Status Code**: 200
- **Regression Risk**: HIGH

**TC-REG-003: GET /history Response Schema**
- **Expected Schema**:
```json
{
  "candles": [
    {
      "date": "ISO 8601 timestamp",
      "open": "float",
      "high": "float",
      "low": "float",
      "close": "float",
      "volume": "integer",
      "oi": "integer | null",
      "greeks": {
        "delta": "float",
        "gamma": "float",
        "theta": "float",
        "vega": "float"
      } | null
    }
  ]
}
```
- **Regression Risk**: CRITICAL

**TC-REG-004: GET /health Response Schema**
- **Expected Schema**:
```json
{
  "status": "ok | degraded",
  "environment": "string",
  "ticker": {
    "running": "boolean",
    "active_subscriptions": "integer",
    "accounts": {}
  },
  "dependencies": {
    "redis": "string",
    "database": "string",
    "instrument_registry": {}
  }
}
```
- **Regression Risk**: HIGH

### 5.2 Data Accuracy Tests

**TC-REG-010: Greeks Calculation Baseline**
- **Purpose**: Ensure Greeks calculations unchanged
- **Method**: Golden master testing
- **Test Steps**:
  1. Load test dataset with known option parameters
  2. Calculate Greeks for each test case
  3. Compare results against baseline file (snapshot)
  4. Verify all values match within 0.01% tolerance
- **Test Cases**: 100 scenarios covering:
  - ATM/ITM/OTM options
  - Various time to expiry (1 day to 90 days)
  - Various volatility levels (10% to 50%)
  - Calls and puts
- **Regression Risk**: CRITICAL

**TC-REG-011: Mock Data Generation Consistency**
- **Purpose**: Ensure mock data format unchanged
- **Test Steps**:
  1. Generate 100 mock option ticks
  2. Validate each tick against schema
  3. Verify all required fields present
  4. Verify value ranges consistent
- **Expected Fields**:
  - instrument_token, last_price, volume, oi
  - delta, gamma, theta, vega
  - timestamp, is_mock=true
- **Regression Risk**: MEDIUM

### 5.3 State Persistence Tests

**TC-REG-020: Subscription State Survives Restart**
- **Purpose**: Ensure no data loss on restart
- **Test Steps**:
  1. Create 50 subscriptions with specific attributes
  2. Stop service
  3. Restart service
  4. Verify all 50 subscriptions restored exactly
  5. Verify attributes unchanged (account_id, mode, etc.)
- **Regression Risk**: CRITICAL

**TC-REG-021: Account Assignment Stability**
- **Purpose**: Ensure deterministic account assignment
- **Test Steps**:
  1. Create subscriptions across multiple accounts
  2. Record account assignments
  3. Restart service 3 times
  4. Verify assignments remain stable
- **Regression Risk**: MEDIUM

### 5.4 WebSocket Protocol Tests

**TC-REG-030: Message Format Unchanged**
- **Purpose**: Ensure WebSocket protocol stable
- **Test Steps**:
  1. Validate all WebSocket message types against schema
  2. Types: connected, subscribed, unsubscribed, tick, error, pong
  3. Verify no new required fields added
  4. Verify no existing fields removed
- **Regression Risk**: CRITICAL (breaking change for clients)

**TC-REG-031: Tick Data Format**
- **Purpose**: Ensure tick payload schema stable
- **Expected Tick Format**:
```json
{
  "type": "tick",
  "data": {
    "instrument_token": "integer",
    "tradingsymbol": "string",
    "last_price": "float",
    "volume": "integer",
    "oi": "integer",
    "delta": "float",
    "gamma": "float",
    "theta": "float",
    "vega": "float",
    "timestamp": "ISO 8601",
    "is_mock": "boolean"
  }
}
```
- **Regression Risk**: CRITICAL

### 5.5 Behavior Regression Tests

**TC-REG-040: Subscription Reload Time**
- **Purpose**: Ensure reload performance not degraded
- **Baseline**: < 30 seconds for 100 subscriptions
- **Test**: Add 100 subscriptions and trigger reload
- **Pass Criteria**: Completes within baseline time
- **Regression Risk**: HIGH (previously had 100+ second issue)

**TC-REG-041: Deadlock Prevention**
- **Purpose**: Ensure RLock fix remains effective
- **Test**:
  1. Subscribe 500 tokens concurrently from 5 threads
  2. Verify no deadlocks
  3. Verify completion within 10 seconds
- **Baseline**: No timeouts
- **Regression Risk**: CRITICAL

**TC-REG-042: Circuit Breaker Thresholds**
- **Purpose**: Ensure circuit breaker configuration unchanged
- **Test**: Verify failure_threshold=5, recovery_timeout=60s
- **Regression Risk**: MEDIUM

---

## 6. Test Infrastructure Requirements

### 6.1 Mock Objects Needed

**Priority 1 (Critical for Unit Tests)**:

1. **MockKiteClient**
   - Mock methods: subscribe(), unsubscribe(), get_quote(), fetch_historical()
   - Configurable responses and delays
   - Simulate errors (rate limits, timeouts, invalid responses)
   ```python
   class MockKiteClient:
       def __init__(self):
           self._subscribed_tokens = set()
           self._responses = {}

       async def subscribe(self, tokens):
           if self._should_fail("subscribe"):
               raise Exception("Rate limit")
           self._subscribed_tokens.update(tokens)

       def configure_response(self, method, response):
           self._responses[method] = response
   ```

2. **MockRedisPublisher**
   - Mock publish(), connect(), _reset()
   - Track publish calls for verification
   - Simulate connection failures
   ```python
   class MockRedisPublisher:
       def __init__(self):
           self.published_messages = []
           self._connected = True

       async def publish(self, channel, message):
           if not self._connected:
               raise ConnectionError()
           self.published_messages.append((channel, message))
   ```

3. **MockSubscriptionStore**
   - Mock all CRUD operations
   - In-memory storage for test isolation
   - Configurable errors
   ```python
   class MockSubscriptionStore:
       def __init__(self):
           self._subscriptions = {}

       async def upsert(self, subscription):
           self._subscriptions[subscription.instrument_token] = subscription

       async def list_active(self):
           return [s for s in self._subscriptions.values() if s.status == "active"]
   ```

4. **MockInstrumentRegistry**
   - Mock get_metadata(), refresh()
   - Pre-populated test instruments
   ```python
   class MockInstrumentRegistry:
       def __init__(self):
           self._cache = {
               256265: InstrumentMetadata(token=256265, tradingsymbol="NIFTY25JAN19000CE", ...),
               260105: InstrumentMetadata(token=260105, tradingsymbol="NIFTY25JAN19000PE", ...)
           }

       async def get_metadata(self, token):
           return self._cache.get(token)
   ```

5. **MockSessionOrchestrator**
   - Mock borrow(), get_client_for_api_call()
   - Simulate account failover
   ```python
   class MockSessionOrchestrator:
       def __init__(self):
           self.accounts = {"account1": MockKiteClient(), "account2": MockKiteClient()}

       @contextmanager
       async def borrow(self, account_id):
           yield self.accounts[account_id]
   ```

**Priority 2 (Helpful for Integration Tests)**:

6. **MockWebSocketClient**
   - Simulate WebSocket client connections
   - Send/receive messages
   ```python
   class MockWebSocketClient:
       async def connect(self, url, token):
           # Establish connection

       async def send(self, message):
           # Send JSON message

       async def receive(self):
           # Receive message from server
   ```

7. **MockTimeProvider**
   - Control time for testing market hours logic
   ```python
   class MockTimeProvider:
       def __init__(self, fixed_time=None):
           self._time = fixed_time or datetime.now()

       def now(self):
           return self._time

       def advance(self, delta):
           self._time += delta
   ```

### 6.2 Test Fixtures

**Fixtures in conftest.py**:

```python
# pytest conftest.py

import pytest
from app.config import Settings
from tests.mocks import (
    MockKiteClient, MockRedisPublisher, MockSubscriptionStore,
    MockInstrumentRegistry, MockSessionOrchestrator
)

@pytest.fixture
def mock_settings():
    """Test configuration"""
    return Settings(
        environment="test",
        api_key_enabled=False,
        enable_mock_data=True,
        redis_url="redis://localhost:6380/0",
        instrument_db_host="localhost",
        instrument_db_port=5433,
        instrument_db_name="ticker_test",
        instrument_db_user="test_user",
        instrument_db_password="test_pass",
    )

@pytest.fixture
def mock_kite_client():
    """Mock Kite API client"""
    return MockKiteClient()

@pytest.fixture
def mock_redis():
    """Mock Redis publisher"""
    return MockRedisPublisher()

@pytest.fixture
def mock_subscription_store():
    """Mock subscription store"""
    return MockSubscriptionStore()

@pytest.fixture
def mock_instrument_registry():
    """Mock instrument registry"""
    return MockInstrumentRegistry()

@pytest.fixture
def mock_orchestrator(mock_kite_client):
    """Mock session orchestrator"""
    return MockSessionOrchestrator()

@pytest.fixture
async def test_db():
    """Real test database connection"""
    # Setup: Create tables
    pool = await create_test_db_pool()
    await init_test_schema(pool)

    yield pool

    # Teardown: Clean up
    await cleanup_test_db(pool)
    await pool.close()

@pytest.fixture
async def test_redis():
    """Real test Redis connection"""
    client = await aioredis.from_url("redis://localhost:6380/0")
    await client.flushdb()  # Clear test database

    yield client

    await client.flushdb()
    await client.close()

@pytest.fixture
def sample_option_snapshot():
    """Sample option snapshot for testing"""
    return OptionSnapshot(
        instrument_token=256265,
        tradingsymbol="NIFTY25JAN19000CE",
        last_price=250.0,
        volume=100000,
        oi=500000,
        delta=0.55,
        gamma=0.002,
        theta=-15.5,
        vega=45.2,
        timestamp=datetime.now(timezone.utc),
        is_mock=False
    )

@pytest.fixture
def sample_candles():
    """Sample historical candles"""
    return [
        {
            "date": "2025-01-08T09:15:00Z",
            "open": 240.0,
            "high": 260.0,
            "low": 235.0,
            "close": 250.0,
            "volume": 10000,
            "oi": 50000
        },
        # ... more candles
    ]
```

### 6.3 Test Data Generators

**Utility functions for generating test data**:

```python
# tests/generators.py

from typing import List
import random
from datetime import datetime, timedelta
from app.schema import InstrumentMetadata, OptionSnapshot

def generate_test_instruments(count: int = 100) -> List[InstrumentMetadata]:
    """Generate test instrument metadata"""
    instruments = []
    for i in range(count):
        token = 256000 + i
        strike = 19000 + (i * 50)
        instruments.append(InstrumentMetadata(
            instrument_token=token,
            tradingsymbol=f"NIFTY25JAN{strike}CE",
            name="NIFTY",
            segment="NFO-OPT",
            strike=strike,
            expiry=datetime(2025, 1, 30),
            exchange="NFO",
            instrument_type="CE",
            lot_size=25,
            tick_size=0.05
        ))
    return instruments

def generate_test_ticks(instrument_token: int, count: int = 100) -> List[dict]:
    """Generate test tick data"""
    ticks = []
    base_price = 250.0
    for i in range(count):
        ticks.append({
            "instrument_token": instrument_token,
            "last_price": base_price + random.uniform(-10, 10),
            "volume": random.randint(1000, 10000),
            "oi": random.randint(10000, 100000),
            "timestamp": datetime.now() - timedelta(seconds=count - i)
        })
    return ticks

def generate_test_candles(
    count: int = 100,
    base_price: float = 250.0,
    interval_minutes: int = 1
) -> List[dict]:
    """Generate test candle data"""
    candles = []
    current_time = datetime.now()
    current_price = base_price

    for i in range(count):
        open_price = current_price
        high_price = open_price + random.uniform(0, 10)
        low_price = open_price - random.uniform(0, 10)
        close_price = random.uniform(low_price, high_price)

        candles.append({
            "date": (current_time - timedelta(minutes=count-i)).isoformat(),
            "open": round(open_price, 2),
            "high": round(high_price, 2),
            "low": round(low_price, 2),
            "close": round(close_price, 2),
            "volume": random.randint(1000, 10000),
            "oi": random.randint(10000, 100000)
        })

        current_price = close_price

    return candles
```

### 6.4 CI/CD Integration

**GitHub Actions Workflow** (`.github/workflows/test.yml`):

```yaml
name: Test Suite

on:
  push:
    branches: [ main, develop, feature/* ]
  pull_request:
    branches: [ main, develop ]

jobs:
  test:
    runs-on: ubuntu-latest

    services:
      redis:
        image: redis:7-alpine
        ports:
          - 6380:6379
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

      postgres:
        image: timescale/timescaledb:latest-pg16
        env:
          POSTGRES_DB: ticker_test
          POSTGRES_USER: test_user
          POSTGRES_PASSWORD: test_pass
        ports:
          - 5433:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v3

      - name: Set up Python 3.11
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Cache dependencies
        uses: actions/cache@v3
        with:
          path: ~/.cache/pip
          key: ${{ runner.os }}-pip-${{ hashFiles('requirements.txt') }}

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pytest pytest-cov pytest-asyncio pytest-xdist

      - name: Run unit tests
        run: pytest tests/unit -v --cov=app --cov-report=xml -n auto

      - name: Run integration tests
        run: pytest tests/integration -v -n auto
        env:
          REDIS_URL: redis://localhost:6380/0
          INSTRUMENT_DB_HOST: localhost
          INSTRUMENT_DB_PORT: 5433
          INSTRUMENT_DB_NAME: ticker_test
          INSTRUMENT_DB_USER: test_user
          INSTRUMENT_DB_PASSWORD: test_pass

      - name: Upload coverage to Codecov
        uses: codecov/codecov-action@v3
        with:
          file: ./coverage.xml
          fail_ci_if_error: true

      - name: Check coverage threshold
        run: |
          coverage report --fail-under=70
```

**Docker Compose for Local Testing**:

```yaml
# docker-compose.test.yml
version: '3.8'

services:
  redis-test:
    image: redis:7-alpine
    ports:
      - "6380:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5

  postgres-test:
    image: timescale/timescaledb:latest-pg16
    environment:
      POSTGRES_DB: ticker_test
      POSTGRES_USER: test_user
      POSTGRES_PASSWORD: test_pass
    ports:
      - "5433:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U test_user"]
      interval: 5s
      timeout: 3s
      retries: 5

  ticker-test:
    build: .
    command: pytest tests/ -v --cov=app --cov-report=html
    environment:
      ENVIRONMENT: test
      REDIS_URL: redis://redis-test:6379/0
      INSTRUMENT_DB_HOST: postgres-test
      INSTRUMENT_DB_PORT: 5432
      INSTRUMENT_DB_NAME: ticker_test
      INSTRUMENT_DB_USER: test_user
      INSTRUMENT_DB_PASSWORD: test_pass
      API_KEY_ENABLED: "false"
      ENABLE_MOCK_DATA: "true"
    depends_on:
      redis-test:
        condition: service_healthy
      postgres-test:
        condition: service_healthy
    volumes:
      - ./htmlcov:/app/htmlcov
```

**Local Test Execution Script**:

```bash
#!/bin/bash
# scripts/run_tests.sh

set -e

echo "Starting test environment..."
docker-compose -f docker-compose.test.yml up -d redis-test postgres-test

echo "Waiting for services to be healthy..."
sleep 5

echo "Running unit tests..."
pytest tests/unit -v --cov=app --cov-report=term-missing -n auto

echo "Running integration tests..."
pytest tests/integration -v -n auto

echo "Running end-to-end tests..."
pytest tests/e2e -v

echo "Generating coverage report..."
coverage html

echo "Cleaning up..."
docker-compose -f docker-compose.test.yml down

echo "Tests complete! Coverage report: htmlcov/index.html"
```

---

## 7. Test Execution Plan

### 7.1 Test Phases

**Phase 1: Unit Tests** (Week 1-2)
- **Objective**: Achieve 60% unit test coverage
- **Duration**: 2 weeks
- **Focus**:
  - Configuration validation
  - Greeks calculations
  - Mock data generation
  - Helper utilities
  - Business logic functions
- **Success Criteria**:
  - 60% line coverage
  - All critical functions tested
  - 100% passing tests
  - < 5 minute execution time
- **Deliverables**:
  - 200+ unit tests
  - Mock objects library
  - Test fixtures
  - Coverage report

**Phase 2: Integration Tests** (Week 3-4)
- **Objective**: Test component interactions
- **Duration**: 2 weeks
- **Focus**:
  - REST API endpoints
  - Database operations
  - Redis pub/sub
  - Multi-component flows
- **Success Criteria**:
  - All API endpoints tested
  - Database integration verified
  - Redis integration verified
  - 100% passing tests
  - < 10 minute execution time
- **Deliverables**:
  - 100+ integration tests
  - Test database setup scripts
  - Docker Compose test environment

**Phase 3: End-to-End Tests** (Week 5-6)
- **Objective**: Validate complete user scenarios
- **Duration**: 2 weeks
- **Focus**:
  - Subscription lifecycle
  - WebSocket streaming
  - Order execution workflows
  - Multi-account orchestration
- **Success Criteria**:
  - All critical user flows tested
  - E2E scenarios pass reliably
  - < 20 minute execution time
- **Deliverables**:
  - 50+ E2E tests
  - WebSocket client test utilities
  - Scenario test data

**Phase 4: Performance Tests** (Week 7)
- **Objective**: Validate performance and scalability
- **Duration**: 1 week
- **Focus**:
  - Load testing (500-1000 subscriptions)
  - Stress testing (beyond capacity)
  - Latency measurements
  - Soak testing (8 hours)
- **Success Criteria**:
  - All performance benchmarks met
  - No memory leaks detected
  - Bottlenecks identified
- **Deliverables**:
  - Performance test suite (Locust)
  - Benchmark reports
  - Performance baseline document

**Phase 5: Regression Tests** (Week 8)
- **Objective**: Create comprehensive regression suite
- **Duration**: 1 week
- **Focus**:
  - API contract tests
  - Data accuracy baselines
  - Behavior regression tests
  - Critical bug prevention tests
- **Success Criteria**:
  - All regression tests pass
  - Baselines established
  - CI/CD integrated
- **Deliverables**:
  - Regression test suite
  - Golden master test data
  - Snapshot baselines

### 7.2 Success Criteria for Each Phase

**Phase 1 Success Metrics**:
- ✅ 60% unit test coverage achieved
- ✅ Zero failing tests
- ✅ All critical bugs from code review addressed
- ✅ Mock infrastructure complete
- ✅ Tests run in CI/CD pipeline

**Phase 2 Success Metrics**:
- ✅ 75% overall coverage (unit + integration)
- ✅ All REST endpoints tested
- ✅ Database integration stable
- ✅ Redis integration stable
- ✅ Integration tests run in CI/CD

**Phase 3 Success Metrics**:
- ✅ 80% overall coverage
- ✅ All user scenarios covered
- ✅ WebSocket streaming validated
- ✅ Multi-account flows tested
- ✅ E2E tests in CI/CD

**Phase 4 Success Metrics**:
- ✅ Performance baselines established
- ✅ Load tests pass at expected capacity
- ✅ No memory leaks detected in soak tests
- ✅ Latency targets met
- ✅ Scalability limits documented

**Phase 5 Success Metrics**:
- ✅ 85% overall coverage
- ✅ Regression suite complete
- ✅ All critical paths protected
- ✅ Automated in CI/CD
- ✅ Documentation updated

### 7.3 Rollback Criteria

**Situations requiring test phase rollback**:

1. **Critical Test Failures**:
   - > 5% of tests failing
   - **Action**: Stop phase, fix failures, restart

2. **Coverage Regression**:
   - Coverage drops below phase target
   - **Action**: Add missing tests, restart phase

3. **Performance Degradation**:
   - New tests cause > 20% slowdown
   - **Action**: Optimize tests or parallelize

4. **Infrastructure Instability**:
   - Test environment unreliable (> 10% flakiness)
   - **Action**: Fix environment, restart

5. **Blocker Bugs Discovered**:
   - Critical bugs found during testing
   - **Action**: Pause testing, fix bugs, retest

**Rollback Process**:
1. Document failure reason
2. Create rollback ticket
3. Fix underlying issue
4. Re-run affected test phase
5. Verify success criteria met
6. Resume next phase

---

## 8. Test Automation Strategy

### 8.1 Tests to Automate (Priority Order)

**Tier 1: CI/CD Pipeline (Run on Every Commit)**
- All unit tests (fast, < 5 min)
- Critical integration tests (< 10 min)
- Smoke tests (basic health checks)
- Linting and code quality checks
- Coverage threshold enforcement

**Tier 2: Pre-Merge (Run on Pull Requests)**
- Full integration test suite
- E2E tests for modified components
- Regression tests for affected areas
- Security scans
- Performance benchmarks (quick)

**Tier 3: Nightly (Run Daily)**
- Full E2E test suite
- Performance load tests
- Extended integration tests
- Compatibility tests
- Documentation build

**Tier 4: Weekly (Run on Schedule)**
- Soak tests (8+ hours)
- Stress tests
- Full regression suite
- Cross-platform tests
- Dependency updates + tests

**Tier 5: Manual (Run on Demand)**
- Exploratory testing
- Security penetration tests
- Chaos engineering tests
- Production smoke tests (post-deploy)

### 8.2 CI/CD Pipeline Integration

**Pipeline Stages**:

```yaml
# .github/workflows/ci-cd.yml

stages:
  - lint
  - unit-test
  - integration-test
  - build
  - e2e-test
  - deploy-staging
  - smoke-test-staging
  - deploy-production
  - smoke-test-production

# Stage 1: Lint & Static Analysis
lint:
  stage: lint
  script:
    - flake8 app/ --max-line-length=120
    - black app/ --check
    - mypy app/ --strict
    - bandit app/ -r  # Security linting
  fast_finish: true  # Fail fast

# Stage 2: Unit Tests
unit-test:
  stage: unit-test
  script:
    - pytest tests/unit -v --cov=app --cov-report=xml -n auto
    - coverage report --fail-under=60
  artifacts:
    reports:
      coverage_report:
        coverage_format: cobertura
        path: coverage.xml

# Stage 3: Integration Tests
integration-test:
  stage: integration-test
  services:
    - redis:7-alpine
    - timescale/timescaledb:latest-pg16
  script:
    - pytest tests/integration -v -n auto
  dependencies:
    - unit-test

# Stage 4: Build Docker Image
build:
  stage: build
  script:
    - docker build -t ticker-service:$CI_COMMIT_SHA .
    - docker tag ticker-service:$CI_COMMIT_SHA ticker-service:latest
  only:
    - main
    - develop

# Stage 5: E2E Tests
e2e-test:
  stage: e2e-test
  script:
    - docker-compose -f docker-compose.test.yml up -d
    - pytest tests/e2e -v
    - docker-compose -f docker-compose.test.yml down
  dependencies:
    - build
  only:
    - main
    - develop

# Stage 6: Deploy to Staging
deploy-staging:
  stage: deploy-staging
  script:
    - kubectl apply -f k8s/staging/
    - kubectl rollout status deployment/ticker-service -n staging
  only:
    - develop
  when: manual  # Require manual approval

# Stage 7: Smoke Tests on Staging
smoke-test-staging:
  stage: smoke-test-staging
  script:
    - pytest tests/smoke -v --env=staging
  dependencies:
    - deploy-staging

# Stage 8: Deploy to Production
deploy-production:
  stage: deploy-production
  script:
    - kubectl apply -f k8s/production/
    - kubectl rollout status deployment/ticker-service -n production
  only:
    - main
  when: manual  # Require manual approval
  environment:
    name: production

# Stage 9: Smoke Tests on Production
smoke-test-production:
  stage: smoke-test-production
  script:
    - pytest tests/smoke -v --env=production
  dependencies:
    - deploy-production
```

### 8.3 Continuous Testing Approach

**Test Execution Strategy**:

| Trigger | Tests Run | Duration | Purpose |
|---------|-----------|----------|---------|
| **Every Commit** | Unit tests + lint | 5-10 min | Fast feedback |
| **Pull Request** | Unit + Integration + affected E2E | 15-20 min | Pre-merge validation |
| **Merge to Develop** | Full test suite | 30-40 min | Integration branch validation |
| **Merge to Main** | Full suite + performance | 60 min | Release validation |
| **Nightly** | Full suite + extended tests | 2-3 hours | Comprehensive validation |
| **Weekly** | Full suite + soak + stress | 8-12 hours | Stability validation |

**Test Parallelization**:
- Use pytest-xdist for parallel execution
- Split tests across multiple runners
- Distribute by test duration (longest first)

**Test Optimization**:
```python
# pytest.ini
[pytest]
# Parallel execution
addopts = -n auto  # Auto-detect CPU cores

# Fast failure
addopts = --maxfail=5  # Stop after 5 failures

# Test ordering (run fast tests first)
addopts = --ff  # Failed tests first
addopts = --nf  # New tests first
```

**Flaky Test Management**:
```python
# Retry flaky tests automatically
@pytest.mark.flaky(reruns=3, reruns_delay=2)
async def test_websocket_connection():
    # Flaky due to network timing
    ...

# Quarantine unstable tests
@pytest.mark.quarantine
async def test_unstable_feature():
    # Known to be unstable, run separately
    ...
```

**Test Artifacts**:
- Coverage reports (HTML + XML)
- Test execution logs
- Performance benchmark results
- Failed test screenshots (if applicable)
- Test timing reports

**Monitoring & Alerts**:
- Slack/email alerts on test failures
- Coverage trend tracking
- Test execution time monitoring
- Flaky test detection and reporting

---

## Test Plan Summary

This comprehensive test plan provides:

1. **Strategic Approach**: Clear testing strategy for unit, integration, E2E, performance, and regression testing
2. **Coverage Goals**: Phased approach from 4% to 85% coverage over 8 weeks
3. **700+ Test Cases**: Detailed test cases covering all major components and scenarios
4. **Zero Regression Tolerance**: Extensive regression suite to protect existing functionality
5. **Production-Critical Focus**: Emphasis on critical paths and high-risk areas
6. **Complete Infrastructure**: Mocks, fixtures, test data generators, CI/CD integration
7. **Phased Execution**: 8-week plan with clear success criteria and rollback procedures
8. **Automation Strategy**: Tiered automation from every commit to weekly schedules

**Estimated Effort**:
- **Initial Setup**: 1 week (infrastructure, mocks, fixtures)
- **Test Development**: 6 weeks (unit, integration, E2E, performance)
- **Regression Suite**: 1 week (baselines, golden masters)
- **Total**: 8 weeks to comprehensive test coverage

**Key Success Metrics**:
- ✅ 85% code coverage
- ✅ 100% critical path coverage
- ✅ Zero tolerance for regressions
- ✅ All tests automated in CI/CD
- ✅ Performance baselines established
- ✅ Production-ready quality

This test plan ensures the ticker_service maintains its production-critical quality standards while enabling confident future development and refactoring.
