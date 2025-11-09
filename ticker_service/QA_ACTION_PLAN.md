# QA ACTION PLAN - IMPLEMENTATION GUIDE
## Ticker Service Testing Strategy - Week-by-Week Breakdown

**Document Purpose**: Actionable implementation guide for QA team  
**Timeline**: 8 weeks to production-ready test coverage  
**Team Size**: 2 QA Engineers + 1 Developer (Part-time)  
**Current Coverage**: 11% → Target: 85%  

---

## QUICK START CHECKLIST

### Day 1: Setup (4 hours)
- [ ] Clone repository
- [ ] Setup Python 3.12 virtual environment
- [ ] Install dependencies: `pip install -r requirements.txt`
- [ ] Run existing tests: `pytest`
- [ ] Verify coverage report: `pytest --cov=app --cov-report=html`
- [ ] Review existing test patterns in `tests/unit/test_tick_validator.py`
- [ ] Setup IDE test runner (PyCharm, VSCode)

### Day 2: Infrastructure (4 hours)
- [ ] Create `.github/workflows/test.yml` (CI/CD pipeline)
- [ ] Setup PostgreSQL test database
- [ ] Setup Redis test instance
- [ ] Configure test environment variables
- [ ] Test CI/CD pipeline with existing tests

---

## WEEK 1: P0 CRITICAL TESTS - ORDER EXECUTION

**Goal**: Test order execution framework (0% → 90% coverage)  
**Effort**: 24 hours  
**Risk**: CRITICAL - Financial transactions  

### Monday-Tuesday: Unit Tests (12 hours)

**File**: `tests/unit/test_order_executor.py` (NEW)

**Tests to Implement** (20 tests):

```python
import pytest
from app.order_executor import OrderExecutor, OrderTask, TaskStatus, CircuitState

@pytest.fixture
def executor():
    """Fixture providing OrderExecutor instance"""
    return OrderExecutor(max_workers=5, circuit_failure_threshold=3)

@pytest.fixture
def mock_kite_client():
    """Mock KiteConnect client for testing"""
    from unittest.mock import MagicMock, AsyncMock
    client = MagicMock()
    client.place_order = AsyncMock(return_value={"order_id": "123456"})
    client.modify_order = AsyncMock(return_value={"order_id": "123456"})
    client.cancel_order = AsyncMock(return_value={"order_id": "123456"})
    return client

# Test 1-5: Basic Operations
@pytest.mark.unit
@pytest.mark.asyncio
async def test_place_order_success(executor, mock_kite_client):
    """Test successful order placement"""
    task = OrderTask(
        task_id="task-1",
        idempotency_key="idem-1",
        operation="place_order",
        params={"exchange": "NFO", "tradingsymbol": "NIFTY25NOVFUT", 
                "transaction_type": "BUY", "quantity": 50},
        account_id="primary"
    )
    
    result = await executor.execute_task(task, mock_kite_client)
    
    assert result.status == TaskStatus.COMPLETED
    assert result.result["order_id"] == "123456"
    assert result.attempts == 1
    mock_kite_client.place_order.assert_called_once()

@pytest.mark.unit
@pytest.mark.asyncio
async def test_place_order_network_error_retry(executor, mock_kite_client):
    """Test retry on network error"""
    from requests.exceptions import ConnectionError
    
    # Fail twice, succeed on third attempt
    mock_kite_client.place_order.side_effect = [
        ConnectionError("Network error"),
        ConnectionError("Network error"),
        {"order_id": "123456"}
    ]
    
    task = OrderTask(
        task_id="task-2",
        idempotency_key="idem-2",
        operation="place_order",
        params={"exchange": "NFO", "tradingsymbol": "NIFTY25NOVFUT"},
        account_id="primary",
        max_attempts=5
    )
    
    result = await executor.execute_task(task, mock_kite_client)
    
    assert result.status == TaskStatus.COMPLETED
    assert result.attempts == 3
    assert mock_kite_client.place_order.call_count == 3

@pytest.mark.unit
@pytest.mark.asyncio
async def test_place_order_max_retries_exceeded(executor, mock_kite_client):
    """Test failure after max retries"""
    from requests.exceptions import ConnectionError
    
    mock_kite_client.place_order.side_effect = ConnectionError("Network error")
    
    task = OrderTask(
        task_id="task-3",
        idempotency_key="idem-3",
        operation="place_order",
        params={"exchange": "NFO", "tradingsymbol": "NIFTY25NOVFUT"},
        account_id="primary",
        max_attempts=3
    )
    
    result = await executor.execute_task(task, mock_kite_client)
    
    assert result.status == TaskStatus.DEAD_LETTER
    assert result.attempts == 3
    assert "Network error" in result.last_error

@pytest.mark.unit
@pytest.mark.asyncio
async def test_modify_order_idempotency(executor, mock_kite_client):
    """Test idempotency prevents duplicate modifications"""
    task = OrderTask(
        task_id="task-4",
        idempotency_key="idem-modify-1",
        operation="modify_order",
        params={"order_id": "123", "quantity": 100},
        account_id="primary"
    )
    
    # Execute twice with same idempotency key
    result1 = await executor.execute_task(task, mock_kite_client)
    result2 = await executor.execute_task(task, mock_kite_client)
    
    assert result1.status == TaskStatus.COMPLETED
    assert result2.status == TaskStatus.COMPLETED
    # Should only call Kite API once
    assert mock_kite_client.modify_order.call_count == 1

@pytest.mark.unit
@pytest.mark.asyncio
async def test_cancel_order_success(executor, mock_kite_client):
    """Test successful order cancellation"""
    task = OrderTask(
        task_id="task-5",
        idempotency_key="idem-cancel-1",
        operation="cancel_order",
        params={"order_id": "123456"},
        account_id="primary"
    )
    
    result = await executor.execute_task(task, mock_kite_client)
    
    assert result.status == TaskStatus.COMPLETED
    mock_kite_client.cancel_order.assert_called_once_with(
        order_id="123456"
    )

# Test 6-10: Circuit Breaker
@pytest.mark.unit
@pytest.mark.asyncio
async def test_circuit_breaker_opens_after_failures(executor, mock_kite_client):
    """Test circuit breaker opens after threshold failures"""
    from kiteconnect.exceptions import NetworkException
    
    mock_kite_client.place_order.side_effect = NetworkException("Service unavailable")
    
    # Execute 3 tasks to trigger circuit breaker (threshold=3)
    tasks = [
        OrderTask(
            task_id=f"task-{i}",
            idempotency_key=f"idem-{i}",
            operation="place_order",
            params={"exchange": "NFO"},
            account_id="primary",
            max_attempts=1
        ) for i in range(3)
    ]
    
    for task in tasks:
        await executor.execute_task(task, mock_kite_client)
    
    # Circuit should now be OPEN
    assert executor.get_circuit_state() == CircuitState.OPEN

@pytest.mark.unit
@pytest.mark.asyncio
async def test_circuit_breaker_rejects_when_open(executor, mock_kite_client):
    """Test circuit breaker rejects requests when open"""
    # Force circuit open
    await executor._circuit_breaker.force_open()
    
    task = OrderTask(
        task_id="task-6",
        idempotency_key="idem-6",
        operation="place_order",
        params={"exchange": "NFO"},
        account_id="primary"
    )
    
    result = await executor.execute_task(task, mock_kite_client)
    
    assert result.status == TaskStatus.FAILED
    assert "circuit breaker" in result.last_error.lower()
    # Should not call Kite API
    mock_kite_client.place_order.assert_not_called()

@pytest.mark.unit
@pytest.mark.asyncio
async def test_circuit_breaker_half_open_recovery(executor, mock_kite_client):
    """Test circuit breaker recovery through HALF_OPEN state"""
    import asyncio
    
    # Force circuit open
    await executor._circuit_breaker.force_open()
    
    # Wait for recovery timeout (mock time)
    await asyncio.sleep(executor._circuit_breaker.recovery_timeout + 0.1)
    
    # Next request should be allowed (HALF_OPEN)
    mock_kite_client.place_order.return_value = {"order_id": "123"}
    
    task = OrderTask(
        task_id="task-7",
        idempotency_key="idem-7",
        operation="place_order",
        params={"exchange": "NFO"},
        account_id="primary"
    )
    
    result = await executor.execute_task(task, mock_kite_client)
    
    assert result.status == TaskStatus.COMPLETED
    # Circuit should close after successful request
    assert executor.get_circuit_state() == CircuitState.CLOSED

# Test 11-15: Task Management
@pytest.mark.unit
@pytest.mark.asyncio
async def test_concurrent_task_execution(executor, mock_kite_client):
    """Test concurrent execution of multiple tasks"""
    import asyncio
    
    tasks = [
        OrderTask(
            task_id=f"task-{i}",
            idempotency_key=f"idem-{i}",
            operation="place_order",
            params={"exchange": "NFO"},
            account_id="primary"
        ) for i in range(10)
    ]
    
    results = await asyncio.gather(
        *[executor.execute_task(task, mock_kite_client) for task in tasks]
    )
    
    assert len(results) == 10
    assert all(r.status == TaskStatus.COMPLETED for r in results)

@pytest.mark.unit
@pytest.mark.asyncio
async def test_task_status_transitions(executor, mock_kite_client):
    """Test task status transitions through lifecycle"""
    from requests.exceptions import ConnectionError
    
    # Fail once, then succeed
    mock_kite_client.place_order.side_effect = [
        ConnectionError("Temporary failure"),
        {"order_id": "123"}
    ]
    
    task = OrderTask(
        task_id="task-8",
        idempotency_key="idem-8",
        operation="place_order",
        params={"exchange": "NFO"},
        account_id="primary"
    )
    
    # Initial status
    assert task.status == TaskStatus.PENDING
    
    result = await executor.execute_task(task, mock_kite_client)
    
    # Final status
    assert result.status == TaskStatus.COMPLETED
    # Check status was RETRYING in between
    # (would need status history tracking in implementation)

@pytest.mark.unit
@pytest.mark.asyncio
async def test_exponential_backoff(executor, mock_kite_client):
    """Test exponential backoff between retries"""
    import time
    from requests.exceptions import ConnectionError
    
    mock_kite_client.place_order.side_effect = [
        ConnectionError("Retry 1"),
        ConnectionError("Retry 2"),
        {"order_id": "123"}
    ]
    
    task = OrderTask(
        task_id="task-9",
        idempotency_key="idem-9",
        operation="place_order",
        params={"exchange": "NFO"},
        account_id="primary"
    )
    
    start = time.time()
    result = await executor.execute_task(task, mock_kite_client)
    elapsed = time.time() - start
    
    # With exponential backoff: 1s + 2s = 3s minimum
    assert elapsed >= 3.0
    assert result.status == TaskStatus.COMPLETED

@pytest.mark.unit
@pytest.mark.asyncio
async def test_dead_letter_queue_handling(executor, mock_kite_client):
    """Test tasks moved to dead letter queue after max retries"""
    from kiteconnect.exceptions import InputException
    
    # Unrecoverable error
    mock_kite_client.place_order.side_effect = InputException("Invalid params")
    
    task = OrderTask(
        task_id="task-10",
        idempotency_key="idem-10",
        operation="place_order",
        params={"exchange": "NFO"},
        account_id="primary",
        max_attempts=3
    )
    
    result = await executor.execute_task(task, mock_kite_client)
    
    assert result.status == TaskStatus.DEAD_LETTER
    # Verify task is in dead letter queue
    dead_letters = await executor.get_dead_letter_tasks()
    assert task.task_id in [t.task_id for t in dead_letters]

@pytest.mark.unit
def test_task_persistence(executor):
    """Test task state persistence"""
    task = OrderTask(
        task_id="task-11",
        idempotency_key="idem-11",
        operation="place_order",
        params={"exchange": "NFO"},
        account_id="primary"
    )
    
    # Save task
    executor.save_task(task)
    
    # Retrieve task
    retrieved = executor.get_task("task-11")
    
    assert retrieved.task_id == task.task_id
    assert retrieved.idempotency_key == task.idempotency_key
    assert retrieved.status == task.status

# Test 16-20: Error Handling
@pytest.mark.unit
@pytest.mark.asyncio
async def test_invalid_operation_raises_error(executor, mock_kite_client):
    """Test invalid operation raises appropriate error"""
    task = OrderTask(
        task_id="task-12",
        idempotency_key="idem-12",
        operation="invalid_operation",  # Invalid
        params={},
        account_id="primary"
    )
    
    with pytest.raises(ValueError, match="Invalid operation"):
        await executor.execute_task(task, mock_kite_client)

@pytest.mark.unit
@pytest.mark.asyncio
async def test_missing_params_raises_error(executor, mock_kite_client):
    """Test missing required params raises error"""
    task = OrderTask(
        task_id="task-13",
        idempotency_key="idem-13",
        operation="place_order",
        params={},  # Missing required params
        account_id="primary"
    )
    
    result = await executor.execute_task(task, mock_kite_client)
    
    assert result.status == TaskStatus.FAILED
    assert "missing" in result.last_error.lower()

@pytest.mark.unit
@pytest.mark.asyncio
async def test_task_timeout(executor, mock_kite_client):
    """Test task execution timeout"""
    import asyncio
    
    async def slow_place_order(**kwargs):
        await asyncio.sleep(10)  # Simulate slow response
        return {"order_id": "123"}
    
    mock_kite_client.place_order = slow_place_order
    
    task = OrderTask(
        task_id="task-14",
        idempotency_key="idem-14",
        operation="place_order",
        params={"exchange": "NFO"},
        account_id="primary"
    )
    
    # Set short timeout
    executor.set_timeout(2.0)
    
    result = await executor.execute_task(task, mock_kite_client)
    
    assert result.status in [TaskStatus.FAILED, TaskStatus.RETRYING]
    assert "timeout" in result.last_error.lower()

@pytest.mark.unit
async def test_executor_cleanup(executor):
    """Test executor cleanup releases resources"""
    await executor.start()
    
    # Verify executor is running
    assert executor.is_running()
    
    await executor.shutdown()
    
    # Verify cleanup
    assert not executor.is_running()
    assert executor._worker_pool is None

@pytest.mark.unit
async def test_executor_stats(executor, mock_kite_client):
    """Test executor statistics tracking"""
    # Execute some tasks
    tasks = [
        OrderTask(
            task_id=f"task-stats-{i}",
            idempotency_key=f"idem-stats-{i}",
            operation="place_order",
            params={"exchange": "NFO"},
            account_id="primary"
        ) for i in range(5)
    ]
    
    for task in tasks:
        await executor.execute_task(task, mock_kite_client)
    
    stats = executor.get_stats()
    
    assert stats["total_tasks"] == 5
    assert stats["completed"] == 5
    assert stats["failed"] == 0
```

**Validation**:
```bash
pytest tests/unit/test_order_executor.py -v
# Expected: 20/20 tests passing
```

---

### Wednesday-Thursday: Integration Tests (12 hours)

**File**: `tests/integration/test_order_lifecycle.py` (NEW)

**Tests to Implement** (10 tests):

```python
import pytest
from app.order_executor import get_executor
from app.kite.client import KiteClient

@pytest.fixture
async def kite_client_mock():
    """Mock KiteClient with realistic responses"""
    # Implementation details...
    pass

@pytest.mark.integration
@pytest.mark.asyncio
async def test_complete_order_flow_buy_sell(async_client, kite_client_mock):
    """Test complete order flow: Place BUY → Modify → Place SELL"""
    # 1. Place BUY order
    buy_response = await async_client.post("/orders/regular", json={
        "exchange": "NFO",
        "tradingsymbol": "NIFTY25NOVFUT",
        "transaction_type": "BUY",
        "quantity": 50,
        "product": "NRML",
        "order_type": "MARKET"
    })
    
    assert buy_response.status_code == 200
    buy_order = buy_response.json()
    assert buy_order["status"] == "success"
    order_id = buy_order["data"]["order_id"]
    
    # 2. Modify order quantity
    modify_response = await async_client.put(f"/orders/regular/{order_id}", json={
        "quantity": 75
    })
    
    assert modify_response.status_code == 200
    
    # 3. Place SELL order to square off
    sell_response = await async_client.post("/orders/regular", json={
        "exchange": "NFO",
        "tradingsymbol": "NIFTY25NOVFUT",
        "transaction_type": "SELL",
        "quantity": 75,
        "product": "NRML",
        "order_type": "MARKET"
    })
    
    assert sell_response.status_code == 200

# Additional integration tests...
# test_order_modification_flow()
# test_order_cancellation_flow()
# test_batch_order_atomic_rollback()
# test_order_persistence_across_restarts()
# test_order_with_invalid_params_rejected()
# test_order_rate_limiting()
# test_order_execution_timeout()
# test_concurrent_orders_same_account()
# test_order_status_tracking()
```

**Validation**:
```bash
pytest tests/integration/test_order_lifecycle.py -v
# Expected: 10/10 tests passing
```

---

## WEEK 2: P0 CRITICAL TESTS - WEBSOCKET & GREEKS

**Goal**: Test WebSocket and Greeks calculation  
**Effort**: 24 hours  

### Monday-Tuesday: WebSocket Testing (12 hours)

**File**: `tests/integration/test_websocket_lifecycle.py` (NEW)

**Tests to Implement** (15 tests):

```python
import pytest
import websockets
import json

@pytest.mark.integration
@pytest.mark.asyncio
async def test_websocket_connect_with_auth():
    """Test WebSocket connection with valid authentication"""
    uri = "ws://localhost:8000/ws"
    headers = {"Authorization": "Bearer valid-token"}
    
    async with websockets.connect(uri, extra_headers=headers) as ws:
        # Send ping
        await ws.send(json.dumps({"type": "ping"}))
        
        # Receive pong
        response = await ws.recv()
        data = json.loads(response)
        
        assert data["type"] == "pong"

@pytest.mark.integration
@pytest.mark.asyncio
async def test_websocket_connect_without_auth_rejected():
    """Test WebSocket connection without auth is rejected"""
    uri = "ws://localhost:8000/ws"
    
    with pytest.raises(websockets.exceptions.InvalidStatusCode) as exc:
        async with websockets.connect(uri):
            pass
    
    assert exc.value.status_code == 401

@pytest.mark.integration
@pytest.mark.asyncio
async def test_websocket_receive_ticks():
    """Test client receives tick data"""
    uri = "ws://localhost:8000/ws"
    headers = {"Authorization": "Bearer valid-token"}
    
    async with websockets.connect(uri, extra_headers=headers) as ws:
        # Subscribe to instrument
        await ws.send(json.dumps({
            "type": "subscribe",
            "instruments": [256265]  # NIFTY 50
        }))
        
        # Wait for tick
        tick_received = False
        for _ in range(10):
            message = await ws.recv()
            data = json.loads(message)
            
            if data.get("type") == "tick":
                tick_received = True
                assert "instrument_token" in data
                assert "last_price" in data
                break
        
        assert tick_received

# Additional tests...
# test_websocket_subscription_updates()
# test_websocket_disconnect_cleanup()
# test_websocket_reconnect_resume_state()
# test_multiple_concurrent_websocket_clients()
# test_websocket_max_connections_limit()
# test_websocket_message_rate_limiting()
# test_websocket_ping_pong_keepalive()
# test_websocket_invalid_message_format()
# test_websocket_subscription_limit()
# test_websocket_unsubscribe()
# test_websocket_connection_timeout()
# test_websocket_broadcast_to_multiple_clients()
```

---

### Wednesday-Thursday: Greeks Calculation (12 hours)

**File**: `tests/unit/test_greeks_calculator_comprehensive.py` (EXPAND EXISTING)

**Tests to Implement** (25 tests):

```python
import pytest
import math
from datetime import datetime, date, timedelta
from app.greeks_calculator import GreeksCalculator

@pytest.fixture
def calculator():
    return GreeksCalculator(
        interest_rate=0.10,
        dividend_yield=0.0,
        expiry_time_hour=15,
        expiry_time_minute=30,
        market_timezone="Asia/Kolkata"
    )

# Black-Scholes Validation Tests
@pytest.mark.unit
def test_black_scholes_call_option_atm(calculator):
    """Test Black-Scholes for ATM call option"""
    spot = 24000.0
    strike = 24000.0
    time_to_expiry = 30 / 365.0  # 30 days
    volatility = 0.15  # 15%
    
    price = calculator.black_scholes_call(
        spot, strike, time_to_expiry, volatility
    )
    
    # ATM call should be positive
    assert price > 0
    # Rough validation (can be refined with known values)
    assert 200 < price < 400

@pytest.mark.unit
def test_black_scholes_put_option_atm(calculator):
    """Test Black-Scholes for ATM put option"""
    spot = 24000.0
    strike = 24000.0
    time_to_expiry = 30 / 365.0
    volatility = 0.15
    
    price = calculator.black_scholes_put(
        spot, strike, time_to_expiry, volatility
    )
    
    # ATM put should be positive
    assert price > 0
    # Put-Call parity check (approximate)
    call_price = calculator.black_scholes_call(
        spot, strike, time_to_expiry, volatility
    )
    # C - P ≈ S - K*e^(-rt)
    parity_diff = abs((call_price - price) - (spot - strike))
    assert parity_diff < 50  # Allow some tolerance

@pytest.mark.unit
def test_delta_calculation_call_itm(calculator):
    """Test delta for ITM call option"""
    spot = 24000.0
    strike = 23500.0  # ITM
    time_to_expiry = 30 / 365.0
    volatility = 0.15
    
    delta = calculator.calculate_delta(
        "CE", spot, strike, time_to_expiry, volatility
    )
    
    # ITM call delta should be high (close to 1)
    assert 0.7 < delta < 1.0

@pytest.mark.unit
def test_delta_calculation_call_otm(calculator):
    """Test delta for OTM call option"""
    spot = 24000.0
    strike = 24500.0  # OTM
    time_to_expiry = 30 / 365.0
    volatility = 0.15
    
    delta = calculator.calculate_delta(
        "CE", spot, strike, time_to_expiry, volatility
    )
    
    # OTM call delta should be low
    assert 0.0 < delta < 0.5

@pytest.mark.unit
def test_delta_calculation_put_itm(calculator):
    """Test delta for ITM put option"""
    spot = 24000.0
    strike = 24500.0  # ITM for put
    time_to_expiry = 30 / 365.0
    volatility = 0.15
    
    delta = calculator.calculate_delta(
        "PE", spot, strike, time_to_expiry, volatility
    )
    
    # ITM put delta should be negative and high magnitude
    assert -1.0 < delta < -0.7

@pytest.mark.unit
def test_gamma_calculation_atm_highest(calculator):
    """Test gamma is highest for ATM options"""
    spot = 24000.0
    time_to_expiry = 30 / 365.0
    volatility = 0.15
    
    gamma_atm = calculator.calculate_gamma(
        spot, 24000.0, time_to_expiry, volatility
    )
    
    gamma_itm = calculator.calculate_gamma(
        spot, 23500.0, time_to_expiry, volatility
    )
    
    gamma_otm = calculator.calculate_gamma(
        spot, 24500.0, time_to_expiry, volatility
    )
    
    # ATM gamma should be highest
    assert gamma_atm > gamma_itm
    assert gamma_atm > gamma_otm

@pytest.mark.unit
def test_theta_time_decay_increases_near_expiry(calculator):
    """Test theta increases as expiry approaches"""
    spot = 24000.0
    strike = 24000.0
    volatility = 0.15
    
    theta_30_days = calculator.calculate_theta(
        "CE", spot, strike, 30/365.0, volatility
    )
    
    theta_7_days = calculator.calculate_theta(
        "CE", spot, strike, 7/365.0, volatility
    )
    
    # Theta (time decay) should increase near expiry
    assert abs(theta_7_days) > abs(theta_30_days)

@pytest.mark.unit
def test_vega_calculation_positive(calculator):
    """Test vega is positive for long options"""
    spot = 24000.0
    strike = 24000.0
    time_to_expiry = 30 / 365.0
    volatility = 0.15
    
    vega = calculator.calculate_vega(
        spot, strike, time_to_expiry, volatility
    )
    
    # Vega should be positive
    assert vega > 0

# Edge Case Tests
@pytest.mark.unit
def test_greeks_at_expiry(calculator):
    """Test Greeks at expiration"""
    spot = 24000.0
    strike = 24000.0
    time_to_expiry = 0.0  # At expiry
    volatility = 0.15
    
    # At expiry, time value should be zero
    call_price = calculator.black_scholes_call(
        spot, strike, time_to_expiry, volatility
    )
    
    # For ATM, call price should be ~0 at expiry
    assert call_price < 10

@pytest.mark.unit
def test_greeks_deep_itm_call(calculator):
    """Test Greeks for deep ITM call"""
    spot = 24000.0
    strike = 22000.0  # Deep ITM
    time_to_expiry = 30 / 365.0
    volatility = 0.15
    
    delta = calculator.calculate_delta(
        "CE", spot, strike, time_to_expiry, volatility
    )
    
    # Deep ITM delta should be very close to 1
    assert delta > 0.95

@pytest.mark.unit
def test_greeks_deep_otm_call(calculator):
    """Test Greeks for deep OTM call"""
    spot = 24000.0
    strike = 26000.0  # Deep OTM
    time_to_expiry = 30 / 365.0
    volatility = 0.15
    
    delta = calculator.calculate_delta(
        "CE", spot, strike, time_to_expiry, volatility
    )
    
    # Deep OTM delta should be very close to 0
    assert delta < 0.05

@pytest.mark.unit
def test_negative_time_to_expiry_handling(calculator):
    """Test handling of negative time to expiry"""
    spot = 24000.0
    strike = 24000.0
    time_to_expiry = -1.0  # Invalid: past expiry
    volatility = 0.15
    
    with pytest.raises(ValueError, match="Time to expiry cannot be negative"):
        calculator.black_scholes_call(
            spot, strike, time_to_expiry, volatility
        )

@pytest.mark.unit
def test_zero_volatility_edge_case(calculator):
    """Test handling of zero volatility"""
    spot = 24000.0
    strike = 24000.0
    time_to_expiry = 30 / 365.0
    volatility = 0.0  # Zero volatility
    
    # Should handle gracefully (intrinsic value only)
    price = calculator.black_scholes_call(
        spot, strike, time_to_expiry, volatility
    )
    
    # For ATM with zero vol, price should be small
    assert 0 <= price < 100

@pytest.mark.unit
def test_extreme_strike_prices(calculator):
    """Test Greeks with extreme strike prices"""
    spot = 24000.0
    strike_far_otm = 50000.0
    time_to_expiry = 30 / 365.0
    volatility = 0.15
    
    delta = calculator.calculate_delta(
        "CE", spot, strike_far_otm, time_to_expiry, volatility
    )
    
    # Far OTM delta should be near zero
    assert 0 <= delta < 0.01

# Integration Test
@pytest.mark.unit
def test_greeks_consistency_call_put_parity(calculator):
    """Test Greeks satisfy call-put parity"""
    spot = 24000.0
    strike = 24000.0
    time_to_expiry = 30 / 365.0
    volatility = 0.15
    
    call_price = calculator.black_scholes_call(
        spot, strike, time_to_expiry, volatility
    )
    
    put_price = calculator.black_scholes_put(
        spot, strike, time_to_expiry, volatility
    )
    
    # Put-Call Parity: C - P = S - K*e^(-rt)
    pv_strike = strike * math.exp(
        -calculator.interest_rate * time_to_expiry
    )
    parity_lhs = call_price - put_price
    parity_rhs = spot - pv_strike
    
    # Allow 1% tolerance
    assert abs(parity_lhs - parity_rhs) / parity_rhs < 0.01

# Performance Test
@pytest.mark.unit
def test_greeks_calculation_performance(calculator):
    """Test Greeks calculation performance"""
    import time
    
    spot = 24000.0
    strike = 24000.0
    time_to_expiry = 30 / 365.0
    volatility = 0.15
    
    iterations = 1000
    start = time.perf_counter()
    
    for _ in range(iterations):
        calculator.calculate_all_greeks(
            "CE", spot, strike, time_to_expiry, volatility
        )
    
    elapsed = time.perf_counter() - start
    avg_time_ms = (elapsed / iterations) * 1000
    
    # Should calculate Greeks in <1ms on average
    assert avg_time_ms < 1.0

# Additional 10 tests...
# (Implement remaining tests following similar patterns)
```

**Validation**:
```bash
pytest tests/unit/test_greeks_calculator_comprehensive.py -v
pytest --cov=app/greeks_calculator.py --cov-report=term-missing
# Expected: 25/25 tests passing, 95%+ coverage
```

---

## WEEK 3-4: P1 HIGH PRIORITY - API & SECURITY

**Goal**: Comprehensive API and security testing  
**Effort**: 40 hours  

### Week 3: API Endpoint Testing (20 hours)

**File**: `tests/integration/test_api_endpoints_comprehensive.py` (EXPAND)

**Coverage Target**: All 50+ API endpoints

**Test Categories**:
1. Order Management (10 tests)
2. Portfolio Management (8 tests)
3. Account Management (6 tests)
4. GTT Orders (8 tests)
5. Mutual Funds (6 tests)
6. Advanced/Subscriptions (12 tests)

**Implementation Pattern**:
```python
@pytest.mark.integration
async def test_place_order_endpoint(async_client):
    """Test POST /orders/regular endpoint"""
    response = await async_client.post("/orders/regular", json={
        "exchange": "NFO",
        "tradingsymbol": "NIFTY25NOVFUT",
        "transaction_type": "BUY",
        "quantity": 50,
        "product": "NRML",
        "order_type": "MARKET"
    })
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "order_id" in data["data"]

# Similar tests for all endpoints...
```

---

### Week 4: Security Testing (20 hours)

**Files to Create**:
- `tests/security/test_authentication.py` (8 tests)
- `tests/security/test_sql_injection.py` (6 tests)
- `tests/security/test_ssrf_protection.py` (4 tests)
- `tests/security/test_input_validation.py` (8 tests)
- `tests/security/test_rate_limiting.py` (6 tests)

**Implementation Example**:
```python
@pytest.mark.security
async def test_sql_injection_in_subscription_filter(async_client):
    """Test SQL injection prevention"""
    malicious_payload = "NIFTY'; DROP TABLE subscriptions; --"
    
    response = await async_client.get(
        f"/subscriptions?tradingsymbol={malicious_payload}"
    )
    
    # Should safely escape, not execute SQL
    assert response.status_code in [200, 400]
    
    # Verify table still exists
    from app.database import get_db
    async with get_db() as conn:
        result = await conn.fetchval(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_name = 'subscriptions'"
        )
        assert result == 1  # Table exists
```

---

## WEEK 5-8: P2 MEDIUM PRIORITY + CI/CD

**Goal**: Complete test coverage, automation, polish  
**Effort**: 40 hours  

### Week 5: Database & Redis (12 hours)
- Database integration tests
- Redis pub/sub tests
- Connection pool tests

### Week 6: Mock Data & Chaos (12 hours)
- Mock generator validation
- Chaos engineering tests
- Resilience testing

### Week 7: CI/CD & Regression (10 hours)
- GitHub Actions workflow
- Regression test suite
- Smoke tests

### Week 8: Documentation & Polish (6 hours)
- Test documentation
- Coverage reporting
- Final validation

---

## CONTINUOUS MONITORING

### Daily Activities
- [ ] Run test suite: `pytest`
- [ ] Check coverage: `pytest --cov=app --cov-report=term`
- [ ] Review failing tests
- [ ] Update test documentation

### Weekly Activities
- [ ] Run full test suite with coverage report
- [ ] Review code coverage gaps
- [ ] Update test roadmap
- [ ] Team sync on progress

### Quality Gates (Before Merge)
- [ ] All tests passing
- [ ] Coverage >= 85%
- [ ] No security findings
- [ ] Code review approved

---

## SUCCESS METRICS

### Week 1 Target
- ✅ 30 tests created (order execution)
- ✅ 30% overall coverage
- ✅ Order execution 90% coverage

### Week 2 Target
- ✅ 40 additional tests (WebSocket, Greeks)
- ✅ 50% overall coverage
- ✅ Greeks 95% coverage

### Week 4 Target
- ✅ 80 additional tests (API, security)
- ✅ 70% overall coverage
- ✅ All critical endpoints tested

### Week 8 Target
- ✅ 150+ total tests
- ✅ 85% overall coverage
- ✅ CI/CD pipeline operational
- ✅ Production-ready QA sign-off

---

**END OF ACTION PLAN**

For questions or issues, refer to:
- QA_COMPREHENSIVE_ASSESSMENT.md (detailed analysis)
- tests/README.md (test execution guide)
- tests/conftest.py (fixture reference)
