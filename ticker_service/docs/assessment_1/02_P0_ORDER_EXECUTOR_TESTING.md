# P0 CRITICAL: Order Executor Test Suite

**Role:** QA Engineer + Backend Engineer
**Priority:** P0 - CRITICAL (Financial Risk)
**Estimated Effort:** 24 hours
**Dependencies:** None
**Target Coverage:** 90% on order_executor.py

---

## Objective

Create comprehensive test suite for order execution module to prevent financial losses from untested order placement, modification, and cancellation logic.

**Current State:** 0% test coverage (0 tests for 242 LOC)
**Risk:** Potential financial losses from duplicate orders, wrong quantities, failed orders

---

## Context

From QA Assessment (Phase 4):
> Order execution has **0% test coverage**. Untested code includes:
> - Order submission queue
> - Rate limiting logic
> - Circuit breaker integration
> - Task cleanup (LRU eviction)
> - Error recovery workflows

**Financial Risk Scenarios:**
1. Duplicate orders → $1000s loss per incident
2. Wrong quantity/price → potentially unlimited loss
3. Failed but unreported orders → missed opportunities
4. Memory leaks → service crashes → trading halted

---

## Test Suite Structure

```
tests/unit/test_order_executor.py          (20 tests - Happy path + Error handling)
tests/integration/test_order_executor_integration.py  (10 tests - Full workflows)
tests/load/test_order_executor_load.py     (5 tests - Performance + Stress)
```

---

## Task 1: Unit Tests - Happy Path (5 tests)

### Test QA-ORD-001: Submit Order Success

```python
# tests/unit/test_order_executor.py

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from app.order_executor import OrderExecutor, OrderTask
from app.kite.client import KiteClient

@pytest.fixture
def mock_kite_client():
    """Mock KiteClient for testing"""
    client = Mock(spec=KiteClient)
    client.place_order = AsyncMock(return_value="ORDER_123456")
    client.modify_order = AsyncMock(return_value="ORDER_123456")
    client.cancel_order = AsyncMock(return_value="ORDER_123456")
    return client

@pytest.fixture
async def executor(mock_kite_client):
    """Create OrderExecutor with mocked dependencies"""
    with patch('app.order_executor.get_client', return_value=mock_kite_client):
        exec = OrderExecutor(max_tasks=10)
        await exec.start_worker()
        yield exec
        await exec.stop_worker()

@pytest.mark.asyncio
async def test_submit_order_success(executor, mock_kite_client):
    """
    Test ID: QA-ORD-001
    Description: Verify successful order submission and ID return

    Given: Executor initialized and worker running
    When: Submit valid order
    Then: Order ID returned, task created with 'pending' status
    """
    # ARRANGE
    order = OrderTask(
        account_id="primary",
        tradingsymbol="INFY",
        exchange="NSE",
        transaction_type="BUY",
        quantity=1,
        product="CNC",
        order_type="MARKET"
    )

    # ACT
    order_id = await executor.submit(order)

    # ASSERT
    assert order_id is not None, "Order ID should be returned"
    assert isinstance(order_id, str), "Order ID should be string"
    assert order_id in executor._tasks, "Task should be tracked in executor"
    assert executor._tasks[order_id].status == "pending", "Initial status should be pending"

    # Wait for worker to process
    await asyncio.sleep(0.5)

    # Verify order was placed via Kite API
    mock_kite_client.place_order.assert_called_once()
    assert executor._tasks[order_id].status in ("executing", "completed")
```

### Test QA-ORD-002: Worker Processes Pending Orders

```python
@pytest.mark.asyncio
async def test_worker_processes_pending_orders(executor, mock_kite_client):
    """
    Test ID: QA-ORD-002
    Description: Verify worker picks up and processes pending orders

    Given: Worker is running
    When: Order submitted to queue
    Then: Worker processes order within 1 second
    """
    # ARRANGE
    order = OrderTask(
        account_id="primary",
        tradingsymbol="RELIANCE",
        exchange="NSE",
        transaction_type="SELL",
        quantity=10,
        product="MIS",
        order_type="LIMIT",
        price=2500.0
    )

    # ACT
    order_id = await executor.submit(order)

    # Wait for processing
    max_wait = 2.0  # seconds
    waited = 0.0
    while executor._tasks[order_id].status == "pending" and waited < max_wait:
        await asyncio.sleep(0.1)
        waited += 0.1

    # ASSERT
    assert waited < max_wait, f"Order not processed within {max_wait}s"
    assert executor._tasks[order_id].status in ("executing", "completed")
    mock_kite_client.place_order.assert_called_once_with(
        tradingsymbol="RELIANCE",
        exchange="NSE",
        transaction_type="SELL",
        quantity=10,
        product="MIS",
        order_type="LIMIT",
        price=2500.0
    )
```

### Test QA-ORD-003: Modify Order Success

```python
@pytest.mark.asyncio
async def test_modify_order_success(executor, mock_kite_client):
    """
    Test ID: QA-ORD-003
    Description: Verify order modification workflow

    Given: Order already placed
    When: Modify order with new quantity/price
    Then: Modification successful, task updated
    """
    # ARRANGE - Place initial order
    order = OrderTask(
        account_id="primary",
        tradingsymbol="TCS",
        exchange="NSE",
        transaction_type="BUY",
        quantity=5,
        product="CNC",
        order_type="LIMIT",
        price=3500.0
    )
    order_id = await executor.submit(order)
    await asyncio.sleep(0.5)  # Wait for placement

    # ACT - Modify order
    modify_result = await executor.modify(
        order_id=order_id,
        quantity=10,  # Increase quantity
        price=3450.0  # Lower price
    )

    # ASSERT
    assert modify_result is True, "Modification should succeed"
    mock_kite_client.modify_order.assert_called_once()
    call_args = mock_kite_client.modify_order.call_args
    assert call_args.kwargs['quantity'] == 10
    assert call_args.kwargs['price'] == 3450.0
```

### Test QA-ORD-004: Cancel Order Success

```python
@pytest.mark.asyncio
async def test_cancel_order_success(executor, mock_kite_client):
    """
    Test ID: QA-ORD-004
    Description: Verify order cancellation workflow

    Given: Order placed and pending
    When: Cancel order
    Then: Order cancelled, status updated to 'cancelled'
    """
    # ARRANGE
    order = OrderTask(
        account_id="primary",
        tradingsymbol="SBIN",
        exchange="NSE",
        transaction_type="BUY",
        quantity=20,
        product="MIS",
        order_type="LIMIT",
        price=600.0
    )
    order_id = await executor.submit(order)
    await asyncio.sleep(0.5)

    # ACT
    cancel_result = await executor.cancel(order_id)

    # ASSERT
    assert cancel_result is True, "Cancellation should succeed"
    mock_kite_client.cancel_order.assert_called_once()
    assert executor._tasks[order_id].status == "cancelled"
```

### Test QA-ORD-005: Circuit Breaker Allows Normal Operation

```python
@pytest.mark.asyncio
async def test_circuit_breaker_allows_normal_operation(executor, mock_kite_client):
    """
    Test ID: QA-ORD-005
    Description: Verify circuit breaker stays closed during normal ops

    Given: Circuit breaker initialized
    When: Submit 5 successful orders
    Then: All orders processed, circuit breaker remains CLOSED
    """
    # ARRANGE
    orders = [
        OrderTask(
            account_id="primary",
            tradingsymbol=f"STOCK{i}",
            exchange="NSE",
            transaction_type="BUY",
            quantity=1,
            product="CNC",
            order_type="MARKET"
        )
        for i in range(5)
    ]

    # ACT
    order_ids = []
    for order in orders:
        order_id = await executor.submit(order)
        order_ids.append(order_id)

    await asyncio.sleep(1.0)  # Wait for all to process

    # ASSERT
    assert executor._circuit_breaker.state == "CLOSED", "Circuit should remain closed"
    assert mock_kite_client.place_order.call_count == 5

    for order_id in order_ids:
        assert executor._tasks[order_id].status == "completed"
```

---

## Task 2: Unit Tests - Error Handling (8 tests)

### Test QA-ORD-006: Kite API Failure Handling

```python
@pytest.mark.asyncio
async def test_submit_order_kite_api_failure(executor):
    """
    Test ID: QA-ORD-006
    Description: Verify graceful handling of Kite API errors

    Given: Kite API will raise exception
    When: Submit order
    Then: Order marked as failed, circuit breaker records failure
    """
    # ARRANGE
    with patch('app.order_executor.get_client') as mock_get_client:
        mock_client = Mock(spec=KiteClient)
        mock_client.place_order = AsyncMock(
            side_effect=Exception("Network timeout")
        )
        mock_get_client.return_value = mock_client

        order = OrderTask(
            account_id="primary",
            tradingsymbol="ERROR_STOCK",
            exchange="NSE",
            transaction_type="BUY",
            quantity=1,
            product="CNC",
            order_type="MARKET"
        )

        # ACT
        order_id = await executor.submit(order)
        await asyncio.sleep(0.5)

        # ASSERT
        assert executor._tasks[order_id].status == "failed"
        assert "Network timeout" in executor._tasks[order_id].error_message

        # Verify circuit breaker recorded failure
        assert executor._circuit_breaker.failure_count == 1
```

### Test QA-ORD-007: Circuit Breaker Opens After Threshold

```python
@pytest.mark.asyncio
async def test_circuit_breaker_opens_after_threshold(executor):
    """
    Test ID: QA-ORD-007
    Description: Verify circuit opens after 5 consecutive failures

    Given: Circuit breaker threshold = 5
    When: Submit 5 orders that fail
    Then: Circuit state == OPEN, 6th order rejected immediately
    """
    # ARRANGE
    with patch('app.order_executor.get_client') as mock_get_client:
        mock_client = Mock(spec=KiteClient)
        mock_client.place_order = AsyncMock(
            side_effect=Exception("API down")
        )
        mock_get_client.return_value = mock_client

        # ACT - Submit 5 failing orders
        for i in range(5):
            order = OrderTask(
                account_id="primary",
                tradingsymbol=f"FAIL{i}",
                exchange="NSE",
                transaction_type="BUY",
                quantity=1,
                product="CNC",
                order_type="MARKET"
            )
            order_id = await executor.submit(order)
            await asyncio.sleep(0.2)

        # ASSERT - Circuit should be OPEN
        assert executor._circuit_breaker.state == "OPEN"

        # Try 6th order - should be rejected immediately
        order6 = OrderTask(
            account_id="primary",
            tradingsymbol="REJECTED",
            exchange="NSE",
            transaction_type="BUY",
            quantity=1,
            product="CNC",
            order_type="MARKET"
        )

        with pytest.raises(Exception, match="Circuit breaker is OPEN"):
            await executor.submit(order6)
```

### Test QA-ORD-008: Circuit Breaker Recovery

```python
@pytest.mark.asyncio
async def test_circuit_breaker_recovers_to_closed():
    """
    Test ID: QA-ORD-008
    Description: Verify circuit recovers after timeout

    Given: Circuit breaker is OPEN
    When: Wait 60s (recovery timeout)
    Then: Circuit transitions to HALF_OPEN, success → CLOSED
    """
    # ARRANGE
    executor = OrderExecutor(
        max_tasks=10,
        circuit_breaker_timeout=2.0  # 2 seconds for testing
    )
    await executor.start_worker()

    # Open circuit by causing failures
    with patch('app.order_executor.get_client') as mock_get_client:
        mock_client = Mock(spec=KiteClient)
        mock_client.place_order = AsyncMock(side_effect=Exception("Fail"))
        mock_get_client.return_value = mock_client

        for i in range(5):
            order = OrderTask(
                account_id="primary",
                tradingsymbol=f"FAIL{i}",
                exchange="NSE",
                transaction_type="BUY",
                quantity=1,
                product="CNC",
                order_type="MARKET"
            )
            await executor.submit(order)
            await asyncio.sleep(0.1)

    assert executor._circuit_breaker.state == "OPEN"

    # ACT - Wait for recovery timeout
    await asyncio.sleep(2.5)

    # Submit successful order
    with patch('app.order_executor.get_client') as mock_get_client:
        mock_client = Mock(spec=KiteClient)
        mock_client.place_order = AsyncMock(return_value="SUCCESS_ORDER")
        mock_get_client.return_value = mock_client

        order = OrderTask(
            account_id="primary",
            tradingsymbol="RECOVERY",
            exchange="NSE",
            transaction_type="BUY",
            quantity=1,
            product="CNC",
            order_type="MARKET"
        )
        order_id = await executor.submit(order)
        await asyncio.sleep(0.5)

    # ASSERT
    assert executor._circuit_breaker.state == "CLOSED"
    assert executor._tasks[order_id].status == "completed"

    await executor.stop_worker()
```

### Test QA-ORD-009: Rate Limit Enforcement

```python
@pytest.mark.asyncio
async def test_rate_limit_enforcement():
    """
    Test ID: QA-ORD-009
    Description: Verify rate limiter prevents excessive orders

    Given: Rate limit = 10 orders/second
    When: Submit 15 orders rapidly
    Then: 11th-15th orders delayed until next window
    """
    # ARRANGE
    executor = OrderExecutor(
        max_tasks=100,
        rate_limit_orders_per_second=10
    )
    await executor.start_worker()

    mock_client = Mock(spec=KiteClient)
    mock_client.place_order = AsyncMock(return_value="ORDER_ID")

    # ACT
    import time
    start_time = time.time()

    with patch('app.order_executor.get_client', return_value=mock_client):
        order_ids = []
        for i in range(15):
            order = OrderTask(
                account_id="primary",
                tradingsymbol=f"STOCK{i}",
                exchange="NSE",
                transaction_type="BUY",
                quantity=1,
                product="CNC",
                order_type="MARKET"
            )
            order_id = await executor.submit(order)
            order_ids.append(order_id)

        await asyncio.sleep(2.0)  # Wait for processing

    end_time = time.time()
    elapsed = end_time - start_time

    # ASSERT
    # First 10 orders processed in <1 second
    # Next 5 orders delayed to next second
    assert elapsed >= 1.0, "Rate limiting should enforce delay"
    assert elapsed < 3.0, "Should complete within 2 seconds"
    assert mock_client.place_order.call_count == 15

    await executor.stop_worker()
```

### Test QA-ORD-010: Task Cleanup on Max Capacity

```python
@pytest.mark.asyncio
async def test_task_cleanup_on_max_capacity():
    """
    Test ID: QA-ORD-010
    Description: Verify LRU eviction when max_tasks reached

    Given: max_tasks = 100
    When: Submit 101 orders
    Then: Oldest completed task evicted
    """
    # ARRANGE
    executor = OrderExecutor(max_tasks=100)
    await executor.start_worker()

    mock_client = Mock(spec=KiteClient)
    mock_client.place_order = AsyncMock(return_value="ORDER_ID")

    # ACT
    with patch('app.order_executor.get_client', return_value=mock_client):
        order_ids = []
        for i in range(101):
            order = OrderTask(
                account_id="primary",
                tradingsymbol=f"STOCK{i}",
                exchange="NSE",
                transaction_type="BUY",
                quantity=1,
                product="CNC",
                order_type="MARKET"
            )
            order_id = await executor.submit(order)
            order_ids.append(order_id)
            await asyncio.sleep(0.01)  # Allow processing

        await asyncio.sleep(2.0)  # Wait for all to complete

    # ASSERT
    assert len(executor._tasks) <= 100, "Should evict oldest tasks"

    # First order should be evicted
    assert order_ids[0] not in executor._tasks, "Oldest task should be evicted"

    # Last order should still exist
    assert order_ids[-1] in executor._tasks, "Newest task should remain"

    await executor.stop_worker()
```

---

## Task 3: Integration Tests (10 tests)

Create `tests/integration/test_order_executor_integration.py` with:
- Full workflow: Submit → Wait → Verify Kite API called
- Multi-account order distribution
- Order history persistence to database
- Order status webhooks
- Concurrent order submission from multiple threads
- Database transaction rollback on failure
- Audit trail verification
- Order reconciliation with Kite
- Margin validation before order placement
- GTT (Good Till Triggered) order workflows

---

## Task 4: Load Tests (5 tests)

Create `tests/load/test_order_executor_load.py` with:
- Sustained 100 orders/second for 5 minutes
- Burst: 1000 orders in 10 seconds
- Memory stability over 1 hour
- Circuit breaker under high load
- Task cleanup efficiency

---

## Acceptance Criteria

- [ ] 20 unit tests passing
- [ ] 10 integration tests passing
- [ ] 5 load tests passing
- [ ] **90%+ line coverage on order_executor.py**
- [ ] No flaky tests (100% pass rate over 10 runs)
- [ ] Performance: < 100ms average order submission latency
- [ ] All tests documented with Test IDs and descriptions
- [ ] Test fixtures reusable across test files
- [ ] CI/CD pipeline configured to run tests automatically

---

## Success Metrics

**Coverage Target:**
```
order_executor.py:        90% (216/242 LOC)
  submit():               100%
  modify():               100%
  cancel():               100%
  _worker_loop():         95%
  _process_order():       100%
  _cleanup_tasks():       100%
  _apply_rate_limit():    90%
```

**Test Quality:**
- No false positives
- No flaky tests
- Fast execution (< 30 seconds for full suite)
- Clear failure messages

---

## Sign-Off

- [ ] QA Lead: _____________________ Date: _____
- [ ] Backend Lead: _____________________ Date: _____
- [ ] Engineering Director: _____________________ Date: _____
