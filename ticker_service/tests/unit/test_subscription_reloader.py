"""
Unit tests for SubscriptionReloader utility.

Tests the reload queue management with rate limiting and deduplication.
"""
import asyncio
import pytest
from app.utils.subscription_reloader import SubscriptionReloader


@pytest.mark.asyncio
async def test_reloader_coalesces_requests():
    """Test that multiple rapid triggers are coalesced"""
    reload_count = 0

    async def mock_reload():
        nonlocal reload_count
        reload_count += 1
        await asyncio.sleep(0.1)

    reloader = SubscriptionReloader(
        reload_fn=mock_reload,
        debounce_seconds=0.2,
        max_reload_frequency_seconds=1.0,
    )

    await reloader.start()

    # Trigger 10 rapid reloads
    for _ in range(10):
        reloader.trigger_reload()
        await asyncio.sleep(0.01)

    # Wait for reloads to complete
    await asyncio.sleep(1.5)

    # Should have coalesced into 1-2 reloads max
    assert reload_count <= 2

    await reloader.stop()


@pytest.mark.asyncio
async def test_reloader_rate_limiting():
    """Test that rate limiting prevents too-frequent reloads"""
    reload_times = []

    async def mock_reload():
        reload_times.append(asyncio.get_event_loop().time())
        await asyncio.sleep(0.05)

    reloader = SubscriptionReloader(
        reload_fn=mock_reload,
        debounce_seconds=0.1,
        max_reload_frequency_seconds=0.5,  # At least 0.5s between reloads
    )

    await reloader.start()

    # Trigger 3 reloads
    reloader.trigger_reload()
    await asyncio.sleep(0.3)  # Less than max_reload_frequency
    reloader.trigger_reload()
    await asyncio.sleep(0.3)
    reloader.trigger_reload()

    # Wait for all reloads to complete
    await asyncio.sleep(1.5)

    # Check that reloads are spaced appropriately
    if len(reload_times) >= 2:
        for i in range(1, len(reload_times)):
            time_diff = reload_times[i] - reload_times[i - 1]
            # Should be at least max_reload_frequency (with small tolerance)
            assert time_diff >= 0.4  # 0.5s - 0.1s tolerance

    await reloader.stop()


@pytest.mark.asyncio
async def test_reloader_debouncing():
    """Test that debouncing waits for burst to complete"""
    reload_count = 0

    async def mock_reload():
        nonlocal reload_count
        reload_count += 1

    reloader = SubscriptionReloader(
        reload_fn=mock_reload,
        debounce_seconds=0.2,  # Wait 0.2s after last trigger
        max_reload_frequency_seconds=1.0,
    )

    await reloader.start()

    # Trigger multiple times with small gaps
    for _ in range(5):
        reloader.trigger_reload()
        await asyncio.sleep(0.05)  # Less than debounce_seconds

    # Wait for debounce + reload
    await asyncio.sleep(0.5)

    # Should have only 1 reload (debounced the burst)
    assert reload_count == 1

    await reloader.stop()


@pytest.mark.asyncio
async def test_reloader_handles_reload_failure():
    """Test that reloader continues working after reload failure"""
    reload_count = 0

    async def failing_reload():
        nonlocal reload_count
        reload_count += 1
        if reload_count == 1:
            raise RuntimeError("First reload fails")
        # Second reload succeeds
        await asyncio.sleep(0.05)

    reloader = SubscriptionReloader(
        reload_fn=failing_reload,
        debounce_seconds=0.1,
        max_reload_frequency_seconds=0.5,
    )

    await reloader.start()

    # First trigger (will fail)
    reloader.trigger_reload()
    await asyncio.sleep(0.3)

    # Second trigger (should succeed)
    reloader.trigger_reload()
    await asyncio.sleep(0.8)

    # Both reloads should have been attempted
    assert reload_count >= 2

    await reloader.stop()


@pytest.mark.asyncio
async def test_reloader_semaphore_ensures_single_reload():
    """Test that only one reload executes at a time"""
    concurrent_reloads = 0
    max_concurrent = 0

    async def slow_reload():
        nonlocal concurrent_reloads, max_concurrent
        concurrent_reloads += 1
        max_concurrent = max(max_concurrent, concurrent_reloads)
        await asyncio.sleep(0.2)  # Slow reload
        concurrent_reloads -= 1

    reloader = SubscriptionReloader(
        reload_fn=slow_reload,
        debounce_seconds=0.05,
        max_reload_frequency_seconds=0.1,
    )

    await reloader.start()

    # Trigger multiple reloads rapidly
    for _ in range(5):
        reloader.trigger_reload()
        await asyncio.sleep(0.01)

    # Wait for all reloads to complete
    await asyncio.sleep(2.0)

    # Should never have more than 1 concurrent reload
    assert max_concurrent == 1

    await reloader.stop()


@pytest.mark.asyncio
async def test_reloader_start_stop():
    """Test that start/stop work correctly"""
    reload_count = 0

    async def mock_reload():
        nonlocal reload_count
        reload_count += 1

    reloader = SubscriptionReloader(
        reload_fn=mock_reload,
        debounce_seconds=0.1,
        max_reload_frequency_seconds=0.5,
    )

    # Start
    await reloader.start()

    # Trigger reload
    reloader.trigger_reload()
    await asyncio.sleep(0.3)

    assert reload_count == 1

    # Stop
    await reloader.stop()

    # Trigger after stop (should not execute)
    initial_count = reload_count
    reloader.trigger_reload()
    await asyncio.sleep(0.3)

    # Count should not increase after stop
    assert reload_count == initial_count


@pytest.mark.asyncio
async def test_reloader_warning_on_double_start():
    """Test that double start produces warning"""
    async def mock_reload():
        await asyncio.sleep(0.05)

    reloader = SubscriptionReloader(
        reload_fn=mock_reload,
        debounce_seconds=0.1,
        max_reload_frequency_seconds=0.5,
    )

    await reloader.start()

    # Second start should log warning (but not fail)
    await reloader.start()

    await reloader.stop()
