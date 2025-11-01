"""
Integration tests for incremental subscription updates
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from app.generator import MultiAccountTickerLoop
from app.schema import Instrument
from app.subscription_store import SubscriptionRecord
from datetime import datetime, timezone


@pytest.fixture
async def mock_orchestrator():
    """Create a mock SessionOrchestrator"""
    orchestrator = MagicMock()
    orchestrator.list_accounts.return_value = ["test_account"]

    # Mock borrow context manager
    mock_client = MagicMock()
    mock_client._ws_pool = MagicMock()
    mock_client._pool_started = True
    mock_client._ws_pool.subscribe_tokens = AsyncMock()
    mock_client._ws_pool.unsubscribe_tokens = MagicMock()

    async def mock_borrow(account_id=None):
        class MockContext:
            async def __aenter__(self):
                return mock_client
            async def __aexit__(self, *args):
                pass
        return MockContext()

    orchestrator.borrow = mock_borrow

    return orchestrator, mock_client


@pytest.mark.asyncio
async def test_add_subscription_incremental_when_not_running(mock_orchestrator):
    """Test adding subscription when ticker loop is not running"""
    orchestrator, _ = mock_orchestrator
    ticker_loop = MultiAccountTickerLoop(orchestrator)

    # Mock instrument registry
    with patch('app.generator.instrument_registry') as mock_registry:
        mock_metadata = MagicMock()
        mock_metadata.is_active = True
        mock_metadata.to_instrument.return_value = Instrument(
            symbol="NIFTY",
            instrument_token=12345,
            strike=24500.0,
            expiry="2025-11-28",
            instrument_type="CE"
        )
        mock_registry.fetch_metadata = AsyncMock(return_value=mock_metadata)

        # Mock subscription store
        with patch('app.generator.subscription_store') as mock_store:
            mock_store.update_account = AsyncMock()

            # Add subscription when not running
            await ticker_loop.add_subscription_incremental(12345, "FULL")

            # Should update the store but not subscribe to WebSocket
            mock_store.update_account.assert_called_once_with(12345, None)


@pytest.mark.asyncio
async def test_add_subscription_incremental_when_running(mock_orchestrator):
    """Test adding subscription when ticker loop is running"""
    orchestrator, mock_client = mock_orchestrator
    ticker_loop = MultiAccountTickerLoop(orchestrator)

    # Set loop as running with existing assignments
    ticker_loop._running = True
    ticker_loop._assignments = {"test_account": []}
    ticker_loop._token_maps = {"test_account": {}}

    # Mock instrument registry
    with patch('app.generator.instrument_registry') as mock_registry:
        mock_metadata = MagicMock()
        mock_metadata.is_active = True
        test_instrument = Instrument(
            symbol="NIFTY",
            instrument_token=12345,
            strike=24500.0,
            expiry="2025-11-28",
            instrument_type="CE"
        )
        mock_metadata.to_instrument.return_value = test_instrument
        mock_registry.fetch_metadata = AsyncMock(return_value=mock_metadata)

        # Mock subscription store
        with patch('app.generator.subscription_store') as mock_store:
            mock_store.update_account = AsyncMock()

            # Add subscription when running
            await ticker_loop.add_subscription_incremental(12345, "FULL")

            # Should subscribe to WebSocket pool
            mock_client._ws_pool.subscribe_tokens.assert_called_once_with([12345])

            # Should update assignments and token_maps
            assert test_instrument in ticker_loop._assignments["test_account"]
            assert 12345 in ticker_loop._token_maps["test_account"]
            assert ticker_loop._token_maps["test_account"][12345] == test_instrument


@pytest.mark.asyncio
async def test_add_subscription_incremental_duplicate(mock_orchestrator):
    """Test adding a subscription that already exists"""
    orchestrator, mock_client = mock_orchestrator
    ticker_loop = MultiAccountTickerLoop(orchestrator)

    # Set loop as running with existing subscription
    ticker_loop._running = True
    existing_instrument = Instrument(
        symbol="NIFTY",
        instrument_token=12345,
        strike=24500.0,
        expiry="2025-11-28",
        instrument_type="CE"
    )
    ticker_loop._assignments = {"test_account": [existing_instrument]}
    ticker_loop._token_maps = {"test_account": {12345: existing_instrument}}

    # Mock instrument registry
    with patch('app.generator.instrument_registry') as mock_registry:
        mock_metadata = MagicMock()
        mock_metadata.is_active = True
        mock_metadata.to_instrument.return_value = existing_instrument
        mock_registry.fetch_metadata = AsyncMock(return_value=mock_metadata)

        # Add duplicate subscription
        await ticker_loop.add_subscription_incremental(12345, "FULL")

        # Should not call WebSocket subscribe (already subscribed)
        mock_client._ws_pool.subscribe_tokens.assert_not_called()


@pytest.mark.asyncio
async def test_remove_subscription_incremental_when_subscribed(mock_orchestrator):
    """Test removing an existing subscription"""
    orchestrator, mock_client = mock_orchestrator
    ticker_loop = MultiAccountTickerLoop(orchestrator)

    # Set loop as running with existing subscription
    ticker_loop._running = True
    existing_instrument = Instrument(
        symbol="NIFTY",
        instrument_token=12345,
        strike=24500.0,
        expiry="2025-11-28",
        instrument_type="CE"
    )
    ticker_loop._assignments = {"test_account": [existing_instrument]}
    ticker_loop._token_maps = {"test_account": {12345: existing_instrument}}

    # Remove subscription
    await ticker_loop.remove_subscription_incremental(12345)

    # Should unsubscribe from WebSocket pool
    mock_client._ws_pool.unsubscribe_tokens.assert_called_once_with([12345])

    # Should remove from assignments and token_maps
    assert existing_instrument not in ticker_loop._assignments.get("test_account", [])
    assert 12345 not in ticker_loop._token_maps.get("test_account", {})


@pytest.mark.asyncio
async def test_remove_subscription_incremental_not_found(mock_orchestrator):
    """Test removing a subscription that doesn't exist"""
    orchestrator, mock_client = mock_orchestrator
    ticker_loop = MultiAccountTickerLoop(orchestrator)

    # Set loop as running with no subscriptions
    ticker_loop._running = True
    ticker_loop._assignments = {}
    ticker_loop._token_maps = {}

    # Remove non-existent subscription (should not raise error)
    await ticker_loop.remove_subscription_incremental(99999)

    # Should not call WebSocket unsubscribe
    mock_client._ws_pool.unsubscribe_tokens.assert_not_called()


@pytest.mark.asyncio
async def test_token_maps_updated_in_stream_account():
    """Test that token_maps are properly initialized in _stream_account"""
    orchestrator = MagicMock()
    ticker_loop = MultiAccountTickerLoop(orchestrator)

    test_instruments = [
        Instrument(
            symbol="NIFTY",
            instrument_token=12345,
            strike=24500.0,
            expiry="2025-11-28",
            instrument_type="CE"
        ),
        Instrument(
            symbol="NIFTY",
            instrument_token=12346,
            strike=24500.0,
            expiry="2025-11-28",
            instrument_type="PE"
        )
    ]

    # Mock the necessary parts
    mock_client = MagicMock()
    mock_client.ensure_session = AsyncMock()

    async def mock_borrow(account_id=None):
        class MockContext:
            async def __aenter__(self):
                return mock_client
            async def __aexit__(self, *args):
                pass
        return MockContext()

    orchestrator.borrow = mock_borrow

    # Set stop event so the loop exits immediately
    ticker_loop._stop_event.set()

    # Run stream_account (will exit immediately due to stop_event)
    await ticker_loop._stream_account("test_account", test_instruments)

    # Check that token_maps were initialized
    assert "test_account" in ticker_loop._token_maps
    assert 12345 in ticker_loop._token_maps["test_account"]
    assert 12346 in ticker_loop._token_maps["test_account"]


@pytest.mark.asyncio
async def test_incremental_subscription_with_capacity_limit():
    """Test that incremental subscription respects capacity limits"""
    orchestrator = MagicMock()
    orchestrator.list_accounts.return_value = ["account1", "account2"]

    ticker_loop = MultiAccountTickerLoop(orchestrator)
    ticker_loop._running = True

    # Fill account1 to capacity
    ticker_loop._assignments = {
        "account1": [Instrument(
            symbol="NIFTY",
            instrument_token=i,
            strike=24500.0,
            expiry="2025-11-28",
            instrument_type="CE"
        ) for i in range(1000)]
    }
    ticker_loop._token_maps = {"account1": {}}

    # Mock _available_accounts to return both accounts
    async def mock_available_accounts():
        return ["account1", "account2"]
    ticker_loop._available_accounts = mock_available_accounts

    # Find account with capacity should return account2 or account1
    account = await ticker_loop._find_account_with_capacity()

    # Should not return account1 (at capacity), should return account2 or None
    assert account != "account1" or account in ["account2", None]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
