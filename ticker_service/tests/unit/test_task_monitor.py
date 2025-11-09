"""
Unit tests for TaskMonitor utility.

Tests the task monitoring and exception handling functionality.
"""
import asyncio
import pytest
from app.utils.task_monitor import TaskMonitor


@pytest.mark.asyncio
async def test_task_monitor_captures_exception():
    """Test that TaskMonitor captures and logs unhandled exceptions"""

    async def failing_task():
        await asyncio.sleep(0.01)
        raise ValueError("Test exception")

    monitor = TaskMonitor()

    task = monitor.create_monitored_task(
        failing_task(),
        task_name="test_failing_task"
    )

    # Wait for task to complete
    await asyncio.sleep(0.1)

    # Task should have completed (not hanging)
    assert task.done()

    # Exception should NOT propagate (handled by monitor)
    # Task result should be None since exception was caught
    try:
        result = task.result()
        assert result is None  # Task completed normally (exception was handled)
    except ValueError:
        pytest.fail("Exception should have been caught by monitor")


@pytest.mark.asyncio
async def test_task_monitor_successful_task():
    """Test that TaskMonitor handles successful tasks correctly"""

    async def successful_task():
        await asyncio.sleep(0.01)
        return "success"

    monitor = TaskMonitor()

    task = monitor.create_monitored_task(
        successful_task(),
        task_name="test_successful_task"
    )

    # Wait for task to complete
    await asyncio.sleep(0.1)

    # Task should complete successfully
    assert task.done()
    # Note: The monitored_task wrapper returns None, not the original result
    # This is by design - it's for fire-and-forget tasks


@pytest.mark.asyncio
async def test_task_monitor_with_error_callback():
    """Test that error callbacks are invoked on task failure"""

    callback_invoked = False
    captured_exception = None

    def error_callback(exc: Exception):
        nonlocal callback_invoked, captured_exception
        callback_invoked = True
        captured_exception = exc

    async def failing_task():
        await asyncio.sleep(0.01)
        raise RuntimeError("Test error")

    monitor = TaskMonitor()

    task = monitor.create_monitored_task(
        failing_task(),
        task_name="test_callback_task",
        on_error=error_callback
    )

    # Wait for task to complete
    await asyncio.sleep(0.1)

    # Callback should have been invoked
    assert callback_invoked
    assert isinstance(captured_exception, RuntimeError)
    assert str(captured_exception) == "Test error"


@pytest.mark.asyncio
async def test_task_monitor_with_async_error_callback():
    """Test that async error callbacks work correctly"""

    callback_invoked = False

    async def async_error_callback(exc: Exception):
        nonlocal callback_invoked
        await asyncio.sleep(0.01)
        callback_invoked = True

    async def failing_task():
        await asyncio.sleep(0.01)
        raise ValueError("Async callback test")

    monitor = TaskMonitor()

    task = monitor.create_monitored_task(
        failing_task(),
        task_name="test_async_callback",
        on_error=async_error_callback
    )

    # Wait for task and callback to complete
    await asyncio.sleep(0.15)

    # Async callback should have been invoked
    assert callback_invoked


@pytest.mark.asyncio
async def test_task_monitor_cancelled_task():
    """Test that cancelled tasks are handled properly"""

    async def long_running_task():
        await asyncio.sleep(10)  # Won't complete

    monitor = TaskMonitor()

    task = monitor.create_monitored_task(
        long_running_task(),
        task_name="test_cancelled_task"
    )

    # Cancel the task
    task.cancel()

    # Wait a bit
    await asyncio.sleep(0.1)

    # Task should be cancelled
    assert task.cancelled()


@pytest.mark.asyncio
async def test_task_monitor_multiple_tasks():
    """Test that monitor can handle multiple concurrent tasks"""

    results = {"task1": False, "task2": False, "task3": False}

    async def task_function(task_name: str):
        await asyncio.sleep(0.01)
        results[task_name] = True

    monitor = TaskMonitor()

    task1 = monitor.create_monitored_task(
        task_function("task1"),
        task_name="monitored_task_1"
    )
    task2 = monitor.create_monitored_task(
        task_function("task2"),
        task_name="monitored_task_2"
    )
    task3 = monitor.create_monitored_task(
        task_function("task3"),
        task_name="monitored_task_3"
    )

    # Wait for all tasks to complete
    await asyncio.sleep(0.1)

    # All tasks should have completed
    assert task1.done()
    assert task2.done()
    assert task3.done()
    assert all(results.values())


@pytest.mark.asyncio
async def test_task_monitor_error_in_callback():
    """Test that errors in callbacks don't crash the task"""

    def buggy_callback(exc: Exception):
        raise RuntimeError("Callback itself failed!")

    async def failing_task():
        await asyncio.sleep(0.01)
        raise ValueError("Original error")

    monitor = TaskMonitor()

    task = monitor.create_monitored_task(
        failing_task(),
        task_name="test_buggy_callback",
        on_error=buggy_callback
    )

    # Wait for task to complete
    await asyncio.sleep(0.1)

    # Task should complete despite buggy callback
    assert task.done()
    # No exception should propagate
