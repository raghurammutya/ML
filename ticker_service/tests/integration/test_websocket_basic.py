"""
WebSocket Basic Tests - P0 Critical Coverage

Tests WebSocket connection lifecycle and subscription management.
Target: 85% coverage on routes_websocket.py
"""

import pytest
import asyncio
import json
from unittest.mock import Mock, AsyncMock, patch, MagicMock

from app.routes_websocket import ConnectionManager


@pytest.fixture
def connection_manager():
    """Create fresh ConnectionManager for each test"""
    manager = ConnectionManager()
    # Clear any state from previous tests
    manager.active_connections.clear()
    manager.token_subscribers.clear()
    return manager


@pytest.fixture
def mock_websocket():
    """Mock WebSocket connection"""
    ws = MagicMock()
    ws.accept = AsyncMock()
    ws.send_text = AsyncMock()
    ws.send_json = AsyncMock()
    ws.close = AsyncMock()
    return ws


# ============================================================================
# CONNECTION LIFECYCLE TESTS (QA-WS-001 to QA-WS-005)
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.integration
async def test_websocket_connection_established(connection_manager, mock_websocket):
    """
    Test ID: QA-WS-001
    Description: Verify WebSocket connection is established

    Given: ConnectionManager initialized
    When: Client connects
    Then: Connection accepted and tracked
    """
    # ACT
    await connection_manager.connect(
        connection_id="conn_1",
        websocket=mock_websocket,
        user_id="user_123"
    )

    # ASSERT
    assert "conn_1" in connection_manager.active_connections
    assert connection_manager.active_connections["conn_1"]["user_id"] == "user_123"
    assert len(connection_manager.active_connections["conn_1"]["subscriptions"]) == 0
    mock_websocket.accept.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_websocket_graceful_disconnect(connection_manager, mock_websocket):
    """
    Test ID: QA-WS-004
    Description: Verify clean disconnection without resource leaks

    Given: Active connection
    When: Client disconnects
    Then: Connection removed, subscriptions cleaned up
    """
    # ARRANGE - Connect and subscribe
    await connection_manager.connect("conn_1", mock_websocket, "user_123")
    connection_manager.subscribe("conn_1", [256265, 256777])

    # ACT
    connection_manager.disconnect("conn_1")

    # ASSERT
    assert "conn_1" not in connection_manager.active_connections
    assert 256265 not in connection_manager.token_subscribers
    assert 256777 not in connection_manager.token_subscribers


@pytest.mark.asyncio
@pytest.mark.integration
async def test_multiple_connections_isolated(connection_manager, mock_websocket):
    """
    Test: Verify multiple connections are isolated

    Given: Multiple connections exist
    When: Each subscribes to different tokens
    Then: Subscriptions are isolated
    """
    # ARRANGE
    ws1 = MagicMock()
    ws1.accept = AsyncMock()
    ws2 = MagicMock()
    ws2.accept = AsyncMock()

    # ACT
    await connection_manager.connect("conn_1", ws1, "user_1")
    await connection_manager.connect("conn_2", ws2, "user_2")

    connection_manager.subscribe("conn_1", [256265])
    connection_manager.subscribe("conn_2", [256777])

    # ASSERT
    assert len(connection_manager.active_connections) == 2
    assert 256265 in connection_manager.active_connections["conn_1"]["subscriptions"]
    assert 256777 in connection_manager.active_connections["conn_2"]["subscriptions"]
    assert 256265 not in connection_manager.active_connections["conn_2"]["subscriptions"]


# ============================================================================
# SUBSCRIPTION MANAGEMENT TESTS (QA-WS-006 to QA-WS-009)
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.integration
async def test_subscribe_to_instruments(connection_manager, mock_websocket):
    """
    Test ID: QA-WS-006
    Description: Verify subscription to instruments

    Given: Connected client
    When: Subscribe to instrument tokens
    Then: Tokens added to subscriptions
    """
    # ARRANGE
    await connection_manager.connect("conn_1", mock_websocket, "user_123")

    # ACT
    result = connection_manager.subscribe("conn_1", [256265, 256777, 257545])

    # ASSERT
    assert result["status"] == "success"
    assert len(result["subscribed"]) == 3
    assert result["total_subscriptions"] == 3

    conn_data = connection_manager.active_connections["conn_1"]
    assert 256265 in conn_data["subscriptions"]
    assert 256777 in conn_data["subscriptions"]
    assert 257545 in conn_data["subscriptions"]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_subscribe_idempotent(connection_manager, mock_websocket):
    """
    Test: Verify subscribing to same token twice is idempotent

    Given: Client already subscribed to token
    When: Subscribe to same token again
    Then: Token not duplicated, no error
    """
    # ARRANGE
    await connection_manager.connect("conn_1", mock_websocket, "user_123")
    connection_manager.subscribe("conn_1", [256265])

    # ACT - Subscribe again
    result = connection_manager.subscribe("conn_1", [256265, 256777])

    # ASSERT
    assert result["status"] == "success"
    assert 256265 in result["subscribed"] or len(result["subscribed"]) == 1
    assert result["total_subscriptions"] == 2  # Only 256265 and 256777


@pytest.mark.asyncio
@pytest.mark.integration
async def test_unsubscribe_from_instruments(connection_manager, mock_websocket):
    """
    Test: Verify unsubscription from instruments

    Given: Client subscribed to tokens
    When: Unsubscribe from some tokens
    Then: Tokens removed from subscriptions
    """
    # ARRANGE
    await connection_manager.connect("conn_1", mock_websocket, "user_123")
    connection_manager.subscribe("conn_1", [256265, 256777, 257545])

    # ACT
    result = connection_manager.unsubscribe("conn_1", [256777])

    # ASSERT
    assert result["status"] == "success"
    assert 256777 in result["unsubscribed"]

    conn_data = connection_manager.active_connections["conn_1"]
    assert 256265 in conn_data["subscriptions"]
    assert 256777 not in conn_data["subscriptions"]
    assert 257545 in conn_data["subscriptions"]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_subscription_filtering(connection_manager, mock_websocket):
    """
    Test ID: QA-WS-008
    Description: Verify subscription filtering works

    Given: Connection subscribed to specific tokens
    When: Check which connections are subscribed
    Then: Only subscribed connections listed
    """
    # ARRANGE
    ws1 = MagicMock()
    ws1.accept = AsyncMock()
    ws2 = MagicMock()
    ws2.accept = AsyncMock()

    await connection_manager.connect("conn_1", ws1, "user_1")
    await connection_manager.connect("conn_2", ws2, "user_2")

    # ACT
    connection_manager.subscribe("conn_1", [256265])
    connection_manager.subscribe("conn_2", [256777])

    # ASSERT
    # Check token_subscribers mapping
    assert "conn_1" in connection_manager.token_subscribers[256265]
    assert "conn_2" in connection_manager.token_subscribers[256777]
    assert "conn_1" not in connection_manager.token_subscribers.get(256777, set())
    assert "conn_2" not in connection_manager.token_subscribers.get(256265, set())


# ============================================================================
# ERROR HANDLING TESTS (QA-WS-010 to QA-WS-012)
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.integration
async def test_subscribe_nonexistent_connection(connection_manager):
    """
    Test ID: QA-WS-010
    Description: Verify error handling for invalid connection

    Given: Connection does not exist
    When: Try to subscribe
    Then: Error returned
    """
    # ACT
    result = connection_manager.subscribe("nonexistent_conn", [256265])

    # ASSERT
    assert "error" in result
    assert result["error"] == "Connection not found"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_unsubscribe_nonexistent_connection(connection_manager):
    """
    Test: Verify error handling for unsubscribe on invalid connection

    Given: Connection does not exist
    When: Try to unsubscribe
    Then: Error returned
    """
    # ACT
    result = connection_manager.unsubscribe("nonexistent_conn", [256265])

    # ASSERT
    assert "error" in result
    assert result["error"] == "Connection not found"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_disconnect_nonexistent_connection(connection_manager):
    """
    Test: Verify disconnect handles nonexistent connection gracefully

    Given: Connection does not exist
    When: Try to disconnect
    Then: No error raised
    """
    # ACT & ASSERT - Should not raise exception
    connection_manager.disconnect("nonexistent_conn")

    # No assertion needed - if we get here, no exception was raised


# ============================================================================
# RESOURCE MANAGEMENT TESTS
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.integration
async def test_connection_cleanup_removes_all_subscriptions(connection_manager, mock_websocket):
    """
    Test: Verify disconnect cleans up all subscriptions

    Given: Connection with multiple subscriptions
    When: Disconnect
    Then: All token_subscribers entries cleaned
    """
    # ARRANGE
    await connection_manager.connect("conn_1", mock_websocket, "user_123")
    connection_manager.subscribe("conn_1", [256265, 256777, 257545])

    # ACT
    connection_manager.disconnect("conn_1")

    # ASSERT
    assert "conn_1" not in connection_manager.active_connections
    # All tokens should have no subscribers
    for token in [256265, 256777, 257545]:
        assert token not in connection_manager.token_subscribers or \
               "conn_1" not in connection_manager.token_subscribers[token]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_multiple_subscribers_same_token(connection_manager):
    """
    Test: Verify multiple connections can subscribe to same token

    Given: Multiple connections
    When: All subscribe to same token
    Then: Token has multiple subscribers
    """
    # ARRANGE
    ws1 = MagicMock()
    ws1.accept = AsyncMock()
    ws2 = MagicMock()
    ws2.accept = AsyncMock()
    ws3 = MagicMock()
    ws3.accept = AsyncMock()

    await connection_manager.connect("conn_1", ws1, "user_1")
    await connection_manager.connect("conn_2", ws2, "user_2")
    await connection_manager.connect("conn_3", ws3, "user_3")

    # ACT
    connection_manager.subscribe("conn_1", [256265])
    connection_manager.subscribe("conn_2", [256265])
    connection_manager.subscribe("conn_3", [256265])

    # ASSERT
    assert len(connection_manager.token_subscribers[256265]) == 3
    assert "conn_1" in connection_manager.token_subscribers[256265]
    assert "conn_2" in connection_manager.token_subscribers[256265]
    assert "conn_3" in connection_manager.token_subscribers[256265]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_partial_disconnect_preserves_other_subscribers(connection_manager):
    """
    Test: Verify disconnecting one client doesn't affect others

    Given: Multiple clients subscribed to same token
    When: One client disconnects
    Then: Other clients still subscribed
    """
    # ARRANGE
    ws1 = MagicMock()
    ws1.accept = AsyncMock()
    ws2 = MagicMock()
    ws2.accept = AsyncMock()

    await connection_manager.connect("conn_1", ws1, "user_1")
    await connection_manager.connect("conn_2", ws2, "user_2")

    connection_manager.subscribe("conn_1", [256265])
    connection_manager.subscribe("conn_2", [256265])

    # ACT
    connection_manager.disconnect("conn_1")

    # ASSERT
    assert "conn_1" not in connection_manager.active_connections
    assert "conn_2" in connection_manager.active_connections
    assert 256265 in connection_manager.token_subscribers
    assert "conn_2" in connection_manager.token_subscribers[256265]
    assert "conn_1" not in connection_manager.token_subscribers[256265]
