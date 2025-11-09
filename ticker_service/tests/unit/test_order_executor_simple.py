"""
Simplified Order Executor Tests - P0 Critical Coverage

Focuses on core functionality with actual API.
"""

import pytest
import asyncio
from app.order_executor import (
    OrderExecutor,
    OrderTask,
    TaskStatus,
    CircuitBreaker,
    CircuitState,
)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_submit_task_creates_pending_task():
    """Verify task submission creates task in PENDING state"""
    executor = OrderExecutor(max_tasks=100)

    task = await executor.submit_task(
        operation="place_order",
        account_id="test_account",
        params={"symbol": "TEST", "qty": 10}
    )

    assert task is not None
    assert isinstance(task, OrderTask)
    assert task.status == TaskStatus.PENDING
    assert task.task_id in executor._tasks


@pytest.mark.asyncio
@pytest.mark.unit
async def test_idempotency_same_params_returns_same_task():
    """Verify idempotency - same params return same task"""
    executor = OrderExecutor(max_tasks=100)

    params = {"symbol": "INFY", "qty": 100, "price": 1500}

    task1 = await executor.submit_task(
        operation="place_order",
        account_id="primary",
        params=params
    )

    task2 = await executor.submit_task(
        operation="place_order",
        account_id="primary",
        params=params
    )

    assert task1.task_id == task2.task_id, "Idempotent requests should return same task"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_task_returns_existing_task():
    """Verify get_task retrieves task by ID"""
    executor = OrderExecutor(max_tasks=100)

    submitted_task = await executor.submit_task(
        operation="place_order",
        account_id="primary",
        params={"symbol": "RELIANCE"}
    )

    retrieved_task = executor.get_task(submitted_task.task_id)

    assert retrieved_task is not None
    assert retrieved_task.task_id == submitted_task.task_id


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_all_tasks_returns_list():
    """Verify get_all_tasks returns all submitted tasks"""
    executor = OrderExecutor(max_tasks=100)

    # Submit 3 tasks with different params to avoid idempotency
    await executor.submit_task(
        operation="place_order",
        account_id="primary",
        params={"symbol": "STOCK0", "qty": 10}
    )
    await executor.submit_task(
        operation="place_order",
        account_id="primary",
        params={"symbol": "STOCK1", "qty": 20}
    )
    await executor.submit_task(
        operation="place_order",
        account_id="primary",
        params={"symbol": "STOCK2", "qty": 30}
    )

    all_tasks = executor.get_all_tasks()

    assert len(all_tasks) >= 3, f"Expected at least 3 tasks, got {len(all_tasks)}"
    assert all(isinstance(t, OrderTask) for t in all_tasks)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_all_tasks_with_status_filter():
    """Verify get_all_tasks filters by status"""
    executor = OrderExecutor(max_tasks=100)

    # Submit tasks with different params
    task1 = await executor.submit_task(
        operation="place_order",
        account_id="primary",
        params={"symbol": "A", "qty": 1}
    )

    task2 = await executor.submit_task(
        operation="place_order",
        account_id="primary",
        params={"symbol": "B", "qty": 2}
    )

    # Manually set one to COMPLETED
    executor._tasks[task1.task_id].status = TaskStatus.COMPLETED

    # Get only pending tasks
    pending_tasks = executor.get_all_tasks(status=TaskStatus.PENDING)

    assert len(pending_tasks) >= 1, "Should have at least 1 pending task"
    assert any(t.task_id == task2.task_id for t in pending_tasks), "Task2 should be in pending list"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_circuit_breaker_closed_initially():
    """Verify circuit breaker starts in CLOSED state"""
    circuit = CircuitBreaker()

    assert circuit.state == CircuitState.CLOSED
    assert await circuit.can_execute() is True


@pytest.mark.asyncio
@pytest.mark.unit
async def test_circuit_breaker_opens_on_failures():
    """Verify circuit breaker opens after threshold failures"""
    circuit = CircuitBreaker(failure_threshold=3)

    # Record failures
    for _ in range(3):
        await circuit.record_failure()

    assert circuit.state == CircuitState.OPEN
    assert await circuit.can_execute() is False


@pytest.mark.asyncio
@pytest.mark.unit
async def test_circuit_breaker_transitions_to_half_open():
    """Verify circuit breaker transitions to HALF_OPEN after recovery timeout"""
    circuit = CircuitBreaker(failure_threshold=3, recovery_timeout=1)

    # Open circuit
    for _ in range(3):
        await circuit.record_failure()

    assert circuit.state == CircuitState.OPEN

    # Wait for recovery
    await asyncio.sleep(1.2)

    # Check can_execute (triggers transition)
    can_exec = await circuit.can_execute()

    assert circuit.state == CircuitState.HALF_OPEN
    assert can_exec is True  # HALF_OPEN allows test request


@pytest.mark.asyncio
@pytest.mark.unit
async def test_task_to_dict_serialization():
    """Verify OrderTask can serialize to dict"""
    task = OrderTask(
        task_id="test_123",
        idempotency_key="key_123",
        operation="place_order",
        params={"symbol": "TEST"},
        account_id="primary"
    )

    task_dict = task.to_dict()

    assert isinstance(task_dict, dict)
    assert task_dict["task_id"] == "test_123"
    assert task_dict["operation"] == "place_order"
    assert task_dict["status"] == "pending"
    assert "created_at" in task_dict


@pytest.mark.asyncio
@pytest.mark.unit
async def test_generate_idempotency_key_deterministic():
    """Verify idempotency key generation is deterministic"""
    params = {"symbol": "INFY", "qty": 100}

    key1 = OrderExecutor.generate_idempotency_key("place_order", params, "primary")
    key2 = OrderExecutor.generate_idempotency_key("place_order", params, "primary")

    assert key1 == key2, "Same params should generate same idempotency key"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_generate_idempotency_key_different_for_different_symbols():
    """Verify different symbols generate different idempotency keys"""
    params1 = {"symbol": "INFY", "qty": 100, "price": 1500}
    params2 = {"symbol": "RELIANCE", "qty": 100, "price": 1500}

    key1 = OrderExecutor.generate_idempotency_key("place_order", params1, "primary")
    key2 = OrderExecutor.generate_idempotency_key("place_order", params2, "primary")

    assert key1 != key2, f"Different symbols should generate different keys:\nkey1={key1}\nkey2={key2}"
