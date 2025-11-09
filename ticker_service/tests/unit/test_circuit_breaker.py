"""
Unit tests for CircuitBreaker utility.

Tests the circuit breaker pattern implementation for fault tolerance.
"""
import asyncio
import pytest
from app.utils.circuit_breaker import CircuitBreaker, CircuitState


@pytest.mark.asyncio
async def test_circuit_starts_closed():
    """Test that circuit breaker starts in CLOSED state"""
    breaker = CircuitBreaker(name="test")

    assert breaker.get_state() == CircuitState.CLOSED
    assert await breaker.can_execute()
    assert breaker.get_failure_count() == 0


@pytest.mark.asyncio
async def test_circuit_opens_after_threshold():
    """Test that circuit opens after failure threshold is reached"""
    breaker = CircuitBreaker(failure_threshold=3, name="test")

    # Initially CLOSED
    assert breaker.get_state() == CircuitState.CLOSED
    assert await breaker.can_execute()

    # Record 2 failures - should stay CLOSED
    await breaker.record_failure()
    await breaker.record_failure()
    assert breaker.get_state() == CircuitState.CLOSED
    assert await breaker.can_execute()
    assert breaker.get_failure_count() == 2

    # 3rd failure - should OPEN
    await breaker.record_failure()
    assert breaker.get_state() == CircuitState.OPEN
    assert not await breaker.can_execute()
    assert breaker.get_failure_count() == 3


@pytest.mark.asyncio
async def test_circuit_rejects_when_open():
    """Test that circuit rejects operations when OPEN"""
    breaker = CircuitBreaker(failure_threshold=2, name="test")

    # Force OPEN
    await breaker.record_failure()
    await breaker.record_failure()

    assert breaker.get_state() == CircuitState.OPEN

    # Should reject multiple times
    for _ in range(5):
        assert not await breaker.can_execute()


@pytest.mark.asyncio
async def test_circuit_recovers_after_timeout():
    """Test that circuit transitions to HALF_OPEN after timeout"""
    breaker = CircuitBreaker(
        failure_threshold=2,
        recovery_timeout_seconds=0.1,  # Short timeout for testing
        name="test"
    )

    # Force OPEN
    await breaker.record_failure()
    await breaker.record_failure()

    assert breaker.get_state() == CircuitState.OPEN
    assert not await breaker.can_execute()

    # Wait for recovery timeout
    await asyncio.sleep(0.15)

    # Should transition to HALF_OPEN and allow test
    assert await breaker.can_execute()
    assert breaker.get_state() == CircuitState.HALF_OPEN


@pytest.mark.asyncio
async def test_half_open_to_closed_on_success():
    """Test that circuit closes after successful operation in HALF_OPEN"""
    breaker = CircuitBreaker(
        failure_threshold=2,
        recovery_timeout_seconds=0.1,
        name="test"
    )

    # Force OPEN
    await breaker.record_failure()
    await breaker.record_failure()

    # Wait for timeout
    await asyncio.sleep(0.15)

    # Should be HALF_OPEN
    assert await breaker.can_execute()
    assert breaker.get_state() == CircuitState.HALF_OPEN

    # Success → CLOSED
    await breaker.record_success()
    assert breaker.get_state() == CircuitState.CLOSED
    assert breaker.get_failure_count() == 0


@pytest.mark.asyncio
async def test_half_open_to_open_on_failure():
    """Test that circuit reopens if HALF_OPEN operation fails"""
    breaker = CircuitBreaker(
        failure_threshold=2,
        recovery_timeout_seconds=0.1,
        name="test"
    )

    # Force OPEN
    await breaker.record_failure()
    await breaker.record_failure()

    # Wait for timeout
    await asyncio.sleep(0.15)

    # Should be HALF_OPEN
    assert await breaker.can_execute()
    assert breaker.get_state() == CircuitState.HALF_OPEN

    # Failure → back to OPEN
    await breaker.record_failure()
    assert breaker.get_state() == CircuitState.OPEN
    assert not await breaker.can_execute()


@pytest.mark.asyncio
async def test_half_open_limits_attempts():
    """Test that HALF_OPEN state limits number of test attempts"""
    breaker = CircuitBreaker(
        failure_threshold=2,
        recovery_timeout_seconds=0.1,
        half_open_max_attempts=3,
        name="test"
    )

    # Force OPEN
    await breaker.record_failure()
    await breaker.record_failure()

    # Wait for timeout
    await asyncio.sleep(0.15)

    # Should allow 3 attempts in HALF_OPEN
    assert await breaker.can_execute()  # Attempt 1
    assert await breaker.can_execute()  # Attempt 2
    assert await breaker.can_execute()  # Attempt 3
    assert not await breaker.can_execute()  # Attempt 4 - rejected


@pytest.mark.asyncio
async def test_success_resets_failure_count_in_closed():
    """Test that success resets failure count in CLOSED state"""
    breaker = CircuitBreaker(failure_threshold=5, name="test")

    # Accumulate some failures
    await breaker.record_failure()
    await breaker.record_failure()
    await breaker.record_failure()

    assert breaker.get_failure_count() == 3
    assert breaker.get_state() == CircuitState.CLOSED

    # Success should reset count
    await breaker.record_success()
    assert breaker.get_failure_count() == 0
    assert breaker.get_state() == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_manual_reset():
    """Test manual circuit reset"""
    breaker = CircuitBreaker(failure_threshold=2, name="test")

    # Force OPEN
    await breaker.record_failure()
    await breaker.record_failure()

    assert breaker.get_state() == CircuitState.OPEN
    assert breaker.get_failure_count() == 2

    # Manual reset
    await breaker.reset()

    assert breaker.get_state() == CircuitState.CLOSED
    assert breaker.get_failure_count() == 0
    assert await breaker.can_execute()


@pytest.mark.asyncio
async def test_concurrent_failure_recording():
    """Test that concurrent failure recording is thread-safe"""
    breaker = CircuitBreaker(failure_threshold=10, name="test")

    async def record_failures():
        for _ in range(5):
            await breaker.record_failure()
            await asyncio.sleep(0.001)

    # Record failures concurrently
    await asyncio.gather(
        record_failures(),
        record_failures(),
    )

    # Should have exactly 10 failures
    assert breaker.get_failure_count() == 10
    assert breaker.get_state() == CircuitState.OPEN


@pytest.mark.asyncio
async def test_circuit_with_exception_info():
    """Test that circuit breaker handles exception info"""
    breaker = CircuitBreaker(failure_threshold=2, name="test")

    error = RuntimeError("Test error")

    await breaker.record_failure(error)
    await breaker.record_failure(error)

    assert breaker.get_state() == CircuitState.OPEN


@pytest.mark.asyncio
async def test_multiple_recovery_cycles():
    """Test multiple open/recovery cycles"""
    breaker = CircuitBreaker(
        failure_threshold=2,
        recovery_timeout_seconds=0.1,
        name="test"
    )

    # Cycle 1: OPEN → HALF_OPEN → CLOSED
    await breaker.record_failure()
    await breaker.record_failure()
    assert breaker.get_state() == CircuitState.OPEN

    await asyncio.sleep(0.15)
    assert await breaker.can_execute()
    await breaker.record_success()
    assert breaker.get_state() == CircuitState.CLOSED

    # Cycle 2: OPEN → HALF_OPEN → OPEN (failed recovery)
    await breaker.record_failure()
    await breaker.record_failure()
    assert breaker.get_state() == CircuitState.OPEN

    await asyncio.sleep(0.15)
    assert await breaker.can_execute()
    await breaker.record_failure()
    assert breaker.get_state() == CircuitState.OPEN

    # Cycle 3: OPEN → HALF_OPEN → CLOSED
    await asyncio.sleep(0.15)
    assert await breaker.can_execute()
    await breaker.record_success()
    assert breaker.get_state() == CircuitState.CLOSED
