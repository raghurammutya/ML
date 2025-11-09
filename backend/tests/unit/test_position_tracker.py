"""
Tests for Position Tracker Service

Verify position state change detection and event emission.
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, Mock

from app.services.position_tracker import (
    PositionTracker,
    PositionEvent,
    PositionEventType,
    Position
)


@pytest.fixture
def tracker():
    """Create a fresh PositionTracker instance."""
    return PositionTracker()


@pytest.fixture
def sample_position_dict():
    """Sample position data from ticker_service."""
    return {
        "tradingsymbol": "NIFTY24NOV24000CE",
        "exchange": "NFO",
        "product": "MIS",
        "quantity": 50,
        "average_price": 145.50,
        "last_price": 150.25,
        "pnl": 237.50,
        "day_pnl": 237.50
    }


class TestPositionTrackerInitialization:
    """Test PositionTracker initialization."""

    def test_tracker_initializes_empty(self, tracker):
        """Test tracker starts with no positions."""
        positions = tracker.get_current_positions("primary")
        assert positions == {}

    def test_tracker_has_no_listeners_initially(self, tracker):
        """Test tracker starts with no listeners."""
        assert tracker._listeners == []


class TestListenerRegistration:
    """Test listener registration."""

    def test_register_listener(self, tracker):
        """Test registering a listener."""
        callback = Mock()
        tracker.register_listener(callback)

        assert len(tracker._listeners) == 1
        assert tracker._listeners[0][0] == callback
        assert tracker._listeners[0][1] is None

    def test_register_listener_with_filter(self, tracker):
        """Test registering a listener with filter."""
        callback = Mock()
        event_filter = lambda e: e.event_type == PositionEventType.POSITION_CLOSED

        tracker.register_listener(callback, event_filter)

        assert len(tracker._listeners) == 1
        assert tracker._listeners[0][1] == event_filter

    def test_register_multiple_listeners(self, tracker):
        """Test registering multiple listeners."""
        callback1 = Mock()
        callback2 = Mock()

        tracker.register_listener(callback1)
        tracker.register_listener(callback2)

        assert len(tracker._listeners) == 2


class TestPositionOpened:
    """Test POSITION_OPENED event detection."""

    @pytest.mark.asyncio
    async def test_new_position_emits_opened_event(self, tracker, sample_position_dict):
        """Test new position triggers POSITION_OPENED event."""
        callback = AsyncMock()
        tracker.register_listener(callback)

        await tracker.on_position_update("primary", [sample_position_dict])

        # Should emit 1 event
        assert callback.call_count == 1

        # Verify event details
        event: PositionEvent = callback.call_args[0][0]
        assert event.event_type == PositionEventType.POSITION_OPENED
        assert event.account_id == "primary"
        assert event.tradingsymbol == "NIFTY24NOV24000CE"
        assert event.quantity_before == 0
        assert event.quantity_after == 50
        assert event.quantity_delta == 50
        assert event.previous_position is None
        assert event.current_position is not None

    @pytest.mark.asyncio
    async def test_opened_position_stored_in_snapshot(self, tracker, sample_position_dict):
        """Test new position is stored in snapshot."""
        await tracker.on_position_update("primary", [sample_position_dict])

        positions = tracker.get_current_positions("primary")
        assert len(positions) == 1

        key = "NIFTY24NOV24000CE:NFO:MIS"
        assert key in positions
        assert positions[key].quantity == 50


class TestPositionClosed:
    """Test POSITION_CLOSED event detection."""

    @pytest.mark.asyncio
    async def test_position_removed_emits_closed_event(self, tracker, sample_position_dict):
        """Test position removal triggers POSITION_CLOSED event."""
        callback = AsyncMock()

        # First update: open position
        await tracker.on_position_update("primary", [sample_position_dict])

        # Register listener AFTER opening
        tracker.register_listener(callback)

        # Second update: empty positions (position closed)
        await tracker.on_position_update("primary", [])

        # Should emit 1 event
        assert callback.call_count == 1

        # Verify event details
        event: PositionEvent = callback.call_args[0][0]
        assert event.event_type == PositionEventType.POSITION_CLOSED
        assert event.quantity_before == 50
        assert event.quantity_after == 0
        assert event.quantity_delta == -50
        assert event.previous_position is not None
        assert event.current_position is None

    @pytest.mark.asyncio
    async def test_closed_position_removed_from_snapshot(self, tracker, sample_position_dict):
        """Test closed position is removed from snapshot."""
        await tracker.on_position_update("primary", [sample_position_dict])

        # Close position
        await tracker.on_position_update("primary", [])

        positions = tracker.get_current_positions("primary")
        assert len(positions) == 0


class TestPositionIncreased:
    """Test POSITION_INCREASED event detection."""

    @pytest.mark.asyncio
    async def test_quantity_increase_emits_increased_event(self, tracker, sample_position_dict):
        """Test quantity increase triggers POSITION_INCREASED event."""
        callback = AsyncMock()

        # Open position with 50 quantity
        await tracker.on_position_update("primary", [sample_position_dict])

        # Register listener
        tracker.register_listener(callback)

        # Increase to 100
        increased_position = sample_position_dict.copy()
        increased_position["quantity"] = 100
        await tracker.on_position_update("primary", [increased_position])

        # Should emit 1 event
        assert callback.call_count == 1

        # Verify event
        event: PositionEvent = callback.call_args[0][0]
        assert event.event_type == PositionEventType.POSITION_INCREASED
        assert event.quantity_before == 50
        assert event.quantity_after == 100
        assert event.quantity_delta == 50


class TestPositionReduced:
    """Test POSITION_REDUCED event detection."""

    @pytest.mark.asyncio
    async def test_quantity_decrease_emits_reduced_event(self, tracker, sample_position_dict):
        """Test quantity decrease triggers POSITION_REDUCED event."""
        callback = AsyncMock()

        # Open position with 50 quantity
        await tracker.on_position_update("primary", [sample_position_dict])

        # Register listener
        tracker.register_listener(callback)

        # Reduce to 25
        reduced_position = sample_position_dict.copy()
        reduced_position["quantity"] = 25
        await tracker.on_position_update("primary", [reduced_position])

        # Should emit 1 event
        assert callback.call_count == 1

        # Verify event
        event: PositionEvent = callback.call_args[0][0]
        assert event.event_type == PositionEventType.POSITION_REDUCED
        assert event.quantity_before == 50
        assert event.quantity_after == 25
        assert event.quantity_delta == -25


class TestPositionUpdated:
    """Test POSITION_UPDATED event detection."""

    @pytest.mark.asyncio
    async def test_price_change_emits_updated_event(self, tracker, sample_position_dict):
        """Test price change (no qty change) triggers POSITION_UPDATED event."""
        callback = AsyncMock()

        # Open position
        await tracker.on_position_update("primary", [sample_position_dict])

        # Register listener
        tracker.register_listener(callback)

        # Price change (quantity unchanged)
        updated_position = sample_position_dict.copy()
        updated_position["last_price"] = 155.00  # Price increased
        updated_position["pnl"] = 475.00  # PnL increased
        await tracker.on_position_update("primary", [updated_position])

        # Should emit 1 event
        assert callback.call_count == 1

        # Verify event
        event: PositionEvent = callback.call_args[0][0]
        assert event.event_type == PositionEventType.POSITION_UPDATED
        assert event.quantity_delta == 0
        assert event.current_position.last_price == 155.00


class TestEventFiltering:
    """Test event listener filtering."""

    @pytest.mark.asyncio
    async def test_filter_only_closed_events(self, tracker, sample_position_dict):
        """Test listener filter for POSITION_CLOSED events only."""
        callback = AsyncMock()

        # Filter for CLOSED events only
        closed_filter = lambda e: e.event_type == PositionEventType.POSITION_CLOSED
        tracker.register_listener(callback, closed_filter)

        # Open position (should not trigger callback)
        await tracker.on_position_update("primary", [sample_position_dict])
        assert callback.call_count == 0

        # Close position (should trigger callback)
        await tracker.on_position_update("primary", [])
        assert callback.call_count == 1

    @pytest.mark.asyncio
    async def test_filter_only_quantity_changes(self, tracker, sample_position_dict):
        """Test listener filter for quantity changes only."""
        callback = AsyncMock()

        # Filter for OPENED, INCREASED, REDUCED, CLOSED only
        qty_filter = lambda e: e.event_type in [
            PositionEventType.POSITION_OPENED,
            PositionEventType.POSITION_INCREASED,
            PositionEventType.POSITION_REDUCED,
            PositionEventType.POSITION_CLOSED
        ]
        tracker.register_listener(callback, qty_filter)

        # Open position (should trigger)
        await tracker.on_position_update("primary", [sample_position_dict])
        assert callback.call_count == 1

        # Price update only (should not trigger)
        updated_position = sample_position_dict.copy()
        updated_position["last_price"] = 155.00
        await tracker.on_position_update("primary", [updated_position])
        assert callback.call_count == 1  # Still 1 (not incremented)


class TestMultipleAccounts:
    """Test tracking multiple accounts."""

    @pytest.mark.asyncio
    async def test_track_multiple_accounts_separately(self, tracker, sample_position_dict):
        """Test tracking positions for multiple accounts."""
        # Update account 1
        await tracker.on_position_update("account1", [sample_position_dict])

        # Update account 2 with different position
        position2 = sample_position_dict.copy()
        position2["tradingsymbol"] = "BANKNIFTY24NOV48000CE"
        await tracker.on_position_update("account2", [position2])

        # Verify both accounts tracked separately
        positions1 = tracker.get_current_positions("account1")
        positions2 = tracker.get_current_positions("account2")

        assert len(positions1) == 1
        assert len(positions2) == 1
        assert "NIFTY24NOV24000CE:NFO:MIS" in positions1
        assert "BANKNIFTY24NOV48000CE:NFO:MIS" in positions2


class TestMultiplePositions:
    """Test tracking multiple positions in same account."""

    @pytest.mark.asyncio
    async def test_track_multiple_positions(self, tracker, sample_position_dict):
        """Test tracking multiple positions in same account."""
        position1 = sample_position_dict
        position2 = sample_position_dict.copy()
        position2["tradingsymbol"] = "BANKNIFTY24NOV48000CE"

        await tracker.on_position_update("primary", [position1, position2])

        positions = tracker.get_current_positions("primary")
        assert len(positions) == 2


class TestClearPositions:
    """Test clearing position snapshots."""

    @pytest.mark.asyncio
    async def test_clear_specific_account(self, tracker, sample_position_dict):
        """Test clearing positions for specific account."""
        await tracker.on_position_update("account1", [sample_position_dict])
        await tracker.on_position_update("account2", [sample_position_dict])

        tracker.clear_positions("account1")

        assert len(tracker.get_current_positions("account1")) == 0
        assert len(tracker.get_current_positions("account2")) == 1

    @pytest.mark.asyncio
    async def test_clear_all_accounts(self, tracker, sample_position_dict):
        """Test clearing all positions."""
        await tracker.on_position_update("account1", [sample_position_dict])
        await tracker.on_position_update("account2", [sample_position_dict])

        tracker.clear_positions()

        assert len(tracker.get_current_positions("account1")) == 0
        assert len(tracker.get_current_positions("account2")) == 0


class TestEventToDictSerialization:
    """Test PositionEvent to_dict() method."""

    @pytest.mark.asyncio
    async def test_event_to_dict(self, tracker, sample_position_dict):
        """Test event can be serialized to dict."""
        callback = AsyncMock()
        tracker.register_listener(callback)

        await tracker.on_position_update("primary", [sample_position_dict])

        event: PositionEvent = callback.call_args[0][0]
        event_dict = event.to_dict()

        assert isinstance(event_dict, dict)
        assert event_dict["event_type"] == PositionEventType.POSITION_OPENED
        assert event_dict["account_id"] == "primary"
        assert event_dict["tradingsymbol"] == "NIFTY24NOV24000CE"
        assert "timestamp" in event_dict
