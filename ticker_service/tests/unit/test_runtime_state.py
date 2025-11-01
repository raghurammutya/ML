"""
Unit tests for runtime state management
"""
import pytest

from app.runtime_state import RuntimeState


@pytest.mark.unit
async def test_runtime_state_default():
    """Test that runtime state initializes with config defaults"""
    state = RuntimeState()
    assert isinstance(state.mock_data_enabled, bool)
    assert state.mock_data_last_toggled is None


@pytest.mark.unit
async def test_set_mock_data_enabled():
    """Test enabling/disabling mock data"""
    state = RuntimeState()

    # Enable mock data
    await state.set_mock_data_enabled(True, changed_by="test")
    assert await state.get_mock_data_enabled() is True
    assert state.mock_data_toggled_by == "test"
    assert state.mock_data_last_toggled is not None

    # Disable mock data
    await state.set_mock_data_enabled(False, changed_by="admin")
    assert await state.get_mock_data_enabled() is False
    assert state.mock_data_toggled_by == "admin"


@pytest.mark.unit
async def test_runtime_state_thread_safety():
    """Test that runtime state is thread-safe"""
    import asyncio

    state = RuntimeState()

    # Run concurrent modifications
    async def toggle():
        await state.set_mock_data_enabled(True)
        await asyncio.sleep(0.001)
        await state.set_mock_data_enabled(False)

    # Should not raise any exceptions
    await asyncio.gather(*[toggle() for _ in range(10)])

    # Final state should be consistent
    result = await state.get_mock_data_enabled()
    assert isinstance(result, bool)


@pytest.mark.unit
async def test_get_state_summary():
    """Test getting state summary"""
    state = RuntimeState()
    await state.set_mock_data_enabled(True, changed_by="api")

    summary = await state.get_state_summary()

    assert "mock_data_enabled" in summary
    assert "mock_data_last_toggled" in summary
    assert "mock_data_toggled_by" in summary
    assert summary["mock_data_enabled"] is True
    assert summary["mock_data_toggled_by"] == "api"
