# P0 CRITICAL: WebSocket Communication Test Suite

**Role:** QA Engineer + Backend Engineer
**Priority:** P0 - CRITICAL (Availability Risk)
**Estimated Effort:** 16 hours
**Dependencies:** None
**Target Coverage:** 85% on routes_websocket.py

---

## Objective

Create comprehensive test suite for WebSocket endpoints to prevent client disconnections, data loss, and ensure real-time tick delivery reliability.

**Current State:** 0% test coverage (0 tests for 173 LOC)
**Risk:** Client disconnections causing revenue loss, data loss from missed ticks, silent failures

---

## Context

From QA Assessment (Phase 4):
> WebSocket communication has **0% test coverage**. Untested code includes:
> - WebSocket authentication
> - Connection lifecycle management
> - Real-time tick broadcasting
> - Error handling and reconnection
> - Subscription filtering

**Business Impact:**
- Missed trading signals → lost revenue
- Customer churn from unreliable data
- Reputational damage from service quality issues

---

## Test Suite Structure

```
tests/integration/test_websocket.py              (15 tests - Connection + Broadcasting)
tests/load/test_websocket_performance.py         (5 tests - Performance + Stress)
tests/integration/test_websocket_security.py     (5 tests - Auth + Security)
```

---

## Task 1: Connection Lifecycle Tests (5 tests)

### Test QA-WS-001: WebSocket Connection Established

```python
# tests/integration/test_websocket.py

import pytest
import asyncio
import websockets
import json
from urllib.parse import urljoin

@pytest.fixture
def websocket_url():
    """WebSocket endpoint URL"""
    return "ws://localhost:8000/ws/ticks"

@pytest.fixture
def auth_headers(valid_jwt_token):
    """Authentication headers for WebSocket"""
    return {
        "Authorization": f"Bearer {valid_jwt_token}"
    }

@pytest.mark.asyncio
async def test_websocket_connection_established(websocket_url):
    """
    Test ID: QA-WS-001
    Description: Verify successful WebSocket connection

    Given: Service is running
    When: Client connects to WebSocket endpoint
    Then: Connection established successfully
    """
    # ARRANGE & ACT
    async with websockets.connect(websocket_url) as websocket:
        # ASSERT
        assert websocket.open, "WebSocket connection should be open"
        assert websocket.state == websockets.protocol.State.OPEN

        # Send ping, verify pong
        pong_waiter = await websocket.ping()
        await asyncio.wait_for(pong_waiter, timeout=5.0)
```

### Test QA-WS-002: Unauthenticated Connection Rejected

```python
@pytest.mark.asyncio
async def test_websocket_authentication_required():
    """
    Test ID: QA-WS-002
    Description: Verify unauthenticated connections rejected

    Given: No authentication token provided
    When: Client attempts to connect
    Then: Connection rejected with 401/1008 close code
    """
    # ARRANGE
    websocket_url = "ws://localhost:8000/ws/ticks"

    # ACT & ASSERT
    with pytest.raises(websockets.exceptions.ConnectionClosedError) as exc_info:
        async with websockets.connect(websocket_url):
            pass  # Should not reach here

    # Verify close code indicates authentication failure
    assert exc_info.value.code == 1008, "Should close with policy violation (1008)"
    assert "Authentication required" in str(exc_info.value.reason)
```

### Test QA-WS-003: Authenticated Connection Success

```python
@pytest.mark.asyncio
async def test_websocket_authentication_with_valid_token(websocket_url, valid_jwt_token):
    """
    Test ID: QA-WS-003
    Description: Verify JWT token authentication

    Given: Valid JWT token provided
    When: Client connects with Authorization header
    Then: Connection accepted
    """
    # ARRANGE
    # WebSocket auth via subprotocol or query param
    auth_url = f"{websocket_url}?token={valid_jwt_token}"

    # ACT
    async with websockets.connect(auth_url) as websocket:
        # ASSERT
        assert websocket.open, "Authenticated connection should succeed"

        # Verify welcome message
        welcome_msg = await asyncio.wait_for(
            websocket.recv(),
            timeout=2.0
        )
        welcome_data = json.loads(welcome_msg)

        assert welcome_data["type"] == "connection"
        assert welcome_data["status"] == "connected"
        assert "session_id" in welcome_data
```

### Test QA-WS-004: Graceful Disconnect

```python
@pytest.mark.asyncio
async def test_websocket_graceful_disconnect(websocket_url, valid_jwt_token):
    """
    Test ID: QA-WS-004
    Description: Verify clean disconnection without resource leaks

    Given: Active WebSocket connection
    When: Client closes connection
    Then: Server cleans up resources, no memory leak
    """
    # ARRANGE
    import psutil
    import os

    process = psutil.Process(os.getpid())
    initial_connections = len(process.connections())
    initial_memory = process.memory_info().rss

    # ACT
    for i in range(10):
        auth_url = f"{websocket_url}?token={valid_jwt_token}"
        async with websockets.connect(auth_url) as websocket:
            await websocket.send(json.dumps({"action": "ping"}))
            await websocket.recv()
            # Connection closes here

    await asyncio.sleep(1.0)  # Allow cleanup

    # ASSERT
    final_connections = len(process.connections())
    final_memory = process.memory_info().rss

    assert final_connections <= initial_connections + 2, "Should not leak connections"
    memory_increase = final_memory - initial_memory
    assert memory_increase < 10 * 1024 * 1024, "Should not leak > 10MB memory"
```

### Test QA-WS-005: Automatic Reconnection

```python
@pytest.mark.asyncio
async def test_websocket_reconnection_after_disconnect():
    """
    Test ID: QA-WS-005
    Description: Verify client can reconnect after disconnect

    Given: Client was previously connected
    When: Connection drops and client reconnects
    Then: New connection established successfully
    """
    # ARRANGE
    websocket_url = "ws://localhost:8000/ws/ticks"
    token = "valid_test_token"

    # ACT - First connection
    auth_url = f"{websocket_url}?token={token}"
    ws1 = await websockets.connect(auth_url)
    session_id_1 = (await ws1.recv())['session_id']

    # Close connection
    await ws1.close()
    await asyncio.sleep(0.5)

    # Reconnect
    ws2 = await websockets.connect(auth_url)
    session_id_2 = (await ws2.recv())['session_id']

    # ASSERT
    assert ws2.open, "Reconnection should succeed"
    assert session_id_2 != session_id_1, "New session should have different ID"

    await ws2.close()
```

---

## Task 2: Real-Time Broadcasting Tests (4 tests)

### Test QA-WS-006: Receive Option Tick Broadcast

```python
@pytest.mark.asyncio
async def test_receive_option_tick_broadcast(websocket_url, valid_jwt_token):
    """
    Test ID: QA-WS-006
    Description: Verify client receives option ticks

    Given: Client connected and subscribed to option instrument
    When: Option tick generated
    Then: Client receives tick within 200ms
    """
    # ARRANGE
    from app.generator import MultiAccountTickerLoop
    import time

    auth_url = f"{websocket_url}?token={valid_jwt_token}"

    async with websockets.connect(auth_url) as websocket:
        # Subscribe to specific instrument
        subscribe_msg = {
            "action": "subscribe",
            "instruments": [256265]  # NIFTY option token
        }
        await websocket.send(json.dumps(subscribe_msg))

        # ACT - Trigger tick generation (mock or real)
        # This requires test fixtures to inject ticks
        start_time = time.time()

        # Wait for tick
        tick_msg = await asyncio.wait_for(
            websocket.recv(),
            timeout=5.0
        )

        end_time = time.time()
        latency = (end_time - start_time) * 1000  # ms

        # ASSERT
        tick_data = json.loads(tick_msg)
        assert tick_data["type"] == "option_tick"
        assert tick_data["instrument_token"] == 256265
        assert "last_price" in tick_data
        assert "greeks" in tick_data
        assert latency < 200, f"Tick delivery latency {latency}ms > 200ms"
```

### Test QA-WS-007: Receive Underlying Tick Broadcast

```python
@pytest.mark.asyncio
async def test_receive_underlying_tick_broadcast(websocket_url, valid_jwt_token):
    """
    Test ID: QA-WS-007
    Description: Verify client receives underlying ticks

    Given: Client subscribed to NIFTY underlying
    When: Underlying tick generated
    Then: Client receives tick with OHLC data
    """
    # ARRANGE
    auth_url = f"{websocket_url}?token={valid_jwt_token}"

    async with websockets.connect(auth_url) as websocket:
        # Subscribe to underlying
        subscribe_msg = {
            "action": "subscribe",
            "symbol": "NIFTY",
            "type": "underlying"
        }
        await websocket.send(json.dumps(subscribe_msg))

        # ACT
        tick_msg = await asyncio.wait_for(
            websocket.recv(),
            timeout=5.0
        )

        # ASSERT
        tick_data = json.loads(tick_msg)
        assert tick_data["type"] == "underlying_bar"
        assert tick_data["symbol"] == "NIFTY"
        assert all(k in tick_data for k in ["open", "high", "low", "close", "volume"])
```

### Test QA-WS-008: Subscription Filtering

```python
@pytest.mark.asyncio
async def test_subscription_filtering(websocket_url, valid_jwt_token):
    """
    Test ID: QA-WS-008
    Description: Verify clients only receive subscribed instruments

    Given: Client subscribed to NIFTY only
    When: NIFTY and BANKNIFTY ticks generated
    Then: Client receives only NIFTY ticks
    """
    # ARRANGE
    auth_url = f"{websocket_url}?token={valid_jwt_token}"

    async with websockets.connect(auth_url) as websocket:
        # Subscribe to NIFTY only
        subscribe_msg = {
            "action": "subscribe",
            "symbols": ["NIFTY"]
        }
        await websocket.send(json.dumps(subscribe_msg))

        # ACT - Generate ticks for both NIFTY and BANKNIFTY
        # (Test fixture should inject ticks)

        # Collect messages for 2 seconds
        received_symbols = set()
        try:
            for _ in range(10):
                tick_msg = await asyncio.wait_for(
                    websocket.recv(),
                    timeout=0.5
                )
                tick_data = json.loads(tick_msg)
                if tick_data.get("type") in ("option_tick", "underlying_bar"):
                    received_symbols.add(tick_data.get("symbol"))
        except asyncio.TimeoutError:
            pass  # No more messages

        # ASSERT
        assert "NIFTY" in received_symbols, "Should receive NIFTY ticks"
        assert "BANKNIFTY" not in received_symbols, "Should NOT receive BANKNIFTY ticks"
```

### Test QA-WS-009: Multiple Concurrent Clients

```python
@pytest.mark.asyncio
async def test_multiple_concurrent_clients(websocket_url, valid_jwt_token):
    """
    Test ID: QA-WS-009
    Description: Verify multiple clients receive same broadcasts

    Given: 100 clients connected
    When: Tick broadcasted
    Then: All 100 clients receive tick
    """
    # ARRANGE
    num_clients = 100
    auth_url = f"{websocket_url}?token={valid_jwt_token}"

    # Connect 100 clients
    websockets_list = []
    for i in range(num_clients):
        ws = await websockets.connect(auth_url)
        await ws.send(json.dumps({"action": "subscribe", "symbols": ["NIFTY"]}))
        websockets_list.append(ws)

    # ACT - Wait for tick broadcast
    received_count = 0
    for ws in websockets_list:
        try:
            msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
            if json.loads(msg).get("type") in ("option_tick", "underlying_bar"):
                received_count += 1
        except asyncio.TimeoutError:
            pass

    # ASSERT
    assert received_count >= 95, f"Only {received_count}/100 clients received tick"

    # Cleanup
    for ws in websockets_list:
        await ws.close()
```

---

## Task 3: Error Handling Tests (3 tests)

### Test QA-WS-010: Invalid Message Handling

```python
@pytest.mark.asyncio
async def test_invalid_message_handling(websocket_url, valid_jwt_token):
    """
    Test ID: QA-WS-010
    Description: Verify malformed messages don't crash server

    Given: Client connected
    When: Send invalid JSON
    Then: Server responds with error, connection stays open
    """
    # ARRANGE
    auth_url = f"{websocket_url}?token={valid_jwt_token}"

    async with websockets.connect(auth_url) as websocket:
        # ACT - Send invalid JSON
        await websocket.send("{ invalid json")

        # Wait for error response
        response = await asyncio.wait_for(
            websocket.recv(),
            timeout=2.0
        )

        # ASSERT
        error_data = json.loads(response)
        assert error_data["type"] == "error"
        assert "Invalid message format" in error_data["message"]

        # Verify connection still open
        assert websocket.open, "Connection should remain open after error"

        # Verify can still send valid messages
        await websocket.send(json.dumps({"action": "ping"}))
        pong = await websocket.recv()
        assert json.loads(pong)["type"] == "pong"
```

### Test QA-WS-011: Connection Timeout

```python
@pytest.mark.asyncio
async def test_connection_timeout():
    """
    Test ID: QA-WS-011
    Description: Verify idle connections time out

    Given: Client connected but idle
    When: No activity for configured timeout (e.g., 5 minutes)
    Then: Server closes connection with timeout reason
    """
    # ARRANGE
    websocket_url = "ws://localhost:8000/ws/ticks"
    token = "valid_test_token"
    auth_url = f"{websocket_url}?token={token}"

    # This test requires timeout configuration in app
    # Set timeout to 5 seconds for testing
    async with websockets.connect(auth_url) as websocket:
        # ACT - Wait without sending any messages
        try:
            await asyncio.wait_for(
                websocket.recv(),
                timeout=10.0
            )
        except websockets.exceptions.ConnectionClosed as e:
            # ASSERT
            assert e.code == 1000 or e.code == 1001, "Should close with normal/going away"
            assert "timeout" in str(e.reason).lower() or "idle" in str(e.reason).lower()
```

### Test QA-WS-012: Max Connections Limit

```python
@pytest.mark.asyncio
async def test_max_connections_limit():
    """
    Test ID: QA-WS-012
    Description: Verify max concurrent connections enforced

    Given: Max connections = 1000 (configurable)
    When: 1001st client attempts to connect
    Then: Connection rejected with appropriate error
    """
    # ARRANGE
    # This test requires configuration of max_connections in app
    # For testing, set to low value like 10

    websocket_url = "ws://localhost:8000/ws/ticks"
    token = "valid_test_token"
    auth_url = f"{websocket_url}?token={token}"

    max_connections = 10  # From config
    websockets_list = []

    try:
        # ACT - Connect max_connections clients
        for i in range(max_connections):
            ws = await websockets.connect(auth_url)
            websockets_list.append(ws)

        # Try to connect one more (should fail)
        with pytest.raises(websockets.exceptions.ConnectionClosedError) as exc_info:
            ws_excess = await websockets.connect(auth_url)
            await asyncio.sleep(0.5)  # Wait for server to reject

        # ASSERT
        assert exc_info.value.code == 1008, "Should reject with policy violation"
        assert "max connections" in str(exc_info.value.reason).lower()

    finally:
        # Cleanup
        for ws in websockets_list:
            await ws.close()
```

---

## Task 4: Performance Tests (3 tests)

### Test QA-WS-013: Broadcast Latency

```python
# tests/load/test_websocket_performance.py

@pytest.mark.asyncio
async def test_broadcast_latency():
    """
    Test ID: QA-WS-013
    Description: Verify tick delivery latency < 100ms p99

    Given: 50 clients connected
    When: 1000 ticks broadcasted
    Then: p99 latency < 100ms, p50 < 50ms
    """
    # ARRANGE
    import time
    import numpy as np

    websocket_url = "ws://localhost:8000/ws/ticks"
    token = "valid_test_token"
    auth_url = f"{websocket_url}?token={token}"

    num_clients = 50
    websockets_list = []

    # Connect clients
    for i in range(num_clients):
        ws = await websockets.connect(auth_url)
        await ws.send(json.dumps({"action": "subscribe", "symbols": ["NIFTY"]}))
        websockets_list.append(ws)

    # ACT - Measure latencies
    latencies = []

    async def measure_client_latency(ws):
        for _ in range(20):  # 20 ticks per client
            start = time.time()
            msg = await ws.recv()
            end = time.time()
            latency_ms = (end - start) * 1000
            latencies.append(latency_ms)

    # Run concurrently for all clients
    await asyncio.gather(*[
        measure_client_latency(ws) for ws in websockets_list
    ])

    # ASSERT
    latencies_array = np.array(latencies)
    p50 = np.percentile(latencies_array, 50)
    p95 = np.percentile(latencies_array, 95)
    p99 = np.percentile(latencies_array, 99)

    assert p50 < 50, f"p50 latency {p50}ms exceeds 50ms"
    assert p99 < 100, f"p99 latency {p99}ms exceeds 100ms"

    # Cleanup
    for ws in websockets_list:
        await ws.close()
```

### Test QA-WS-014: High Throughput Broadcasting

```python
@pytest.mark.asyncio
async def test_high_throughput_broadcasting():
    """
    Test ID: QA-WS-014
    Description: Verify 10,000 ticks/sec broadcast capability

    Given: 100 clients connected
    When: Broadcast 10,000 ticks in 1 second
    Then: All clients receive all ticks, no drops
    """
    # ARRANGE
    websocket_url = "ws://localhost:8000/ws/ticks"
    token = "valid_test_token"
    auth_url = f"{websocket_url}?token={token}"

    num_clients = 100
    expected_ticks = 10000

    websockets_list = []
    for i in range(num_clients):
        ws = await websockets.connect(auth_url)
        await ws.send(json.dumps({"action": "subscribe", "symbols": ["NIFTY"]}))
        websockets_list.append(ws)

    # ACT - Generate high throughput ticks
    # (Requires test fixture to generate 10K ticks/sec)

    received_counts = []

    async def count_received_ticks(ws):
        count = 0
        try:
            while True:
                msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
                if json.loads(msg).get("type") in ("option_tick", "underlying_bar"):
                    count += 1
        except asyncio.TimeoutError:
            pass
        received_counts.append(count)

    await asyncio.gather(*[count_received_ticks(ws) for ws in websockets_list])

    # ASSERT
    min_received = min(received_counts)
    max_received = max(received_counts)
    avg_received = sum(received_counts) / len(received_counts)

    assert min_received >= expected_ticks * 0.95, f"Client lost ticks: {min_received}/{expected_ticks}"
    assert avg_received >= expected_ticks * 0.98, f"Average drops: {avg_received}/{expected_ticks}"

    # Cleanup
    for ws in websockets_list:
        await ws.close()
```

### Test QA-WS-015: Memory Stability Over Time

```python
@pytest.mark.asyncio
async def test_memory_stability_over_time():
    """
    Test ID: QA-WS-015
    Description: Verify no memory leaks over 1 hour

    Given: Service running with active WebSocket connections
    When: Connections open/close repeatedly for 1 hour (simulated with 5 min)
    Then: Memory usage remains stable (< 10% increase)
    """
    # ARRANGE
    import psutil
    import os

    process = psutil.Process(os.getpid())
    initial_memory = process.memory_info().rss

    websocket_url = "ws://localhost:8000/ws/ticks"
    token = "valid_test_token"
    auth_url = f"{websocket_url}?token={token}"

    # ACT - Simulate 1 hour of connections (5 min for testing)
    duration_seconds = 300  # 5 minutes
    start_time = time.time()

    while time.time() - start_time < duration_seconds:
        # Connect 10 clients
        websockets_list = []
        for i in range(10):
            ws = await websockets.connect(auth_url)
            websockets_list.append(ws)

        # Receive some ticks
        await asyncio.sleep(1.0)

        # Disconnect all
        for ws in websockets_list:
            await ws.close()

        await asyncio.sleep(0.5)  # Allow cleanup

    # ASSERT
    final_memory = process.memory_info().rss
    memory_increase_pct = ((final_memory - initial_memory) / initial_memory) * 100

    assert memory_increase_pct < 10, f"Memory increased by {memory_increase_pct}% (> 10%)"
```

---

## Acceptance Criteria

- [ ] 15 integration tests passing (connection + broadcasting)
- [ ] 5 load tests passing (performance + stress)
- [ ] 5 security tests passing (auth + validation)
- [ ] **85%+ line coverage on routes_websocket.py**
- [ ] p99 broadcast latency < 100ms
- [ ] Memory stable over 1 hour test
- [ ] 100 concurrent clients supported
- [ ] No flaky tests (100% pass rate over 10 runs)

---

## Success Metrics

**Coverage Target:**
```
routes_websocket.py:       85% (147/173 LOC)
  websocket_endpoint():    100%
  handle_subscribe():      100%
  handle_unsubscribe():    95%
  broadcast_tick():        100%
  authenticate_ws():       100%
  cleanup_connection():    90%
```

**Performance Targets:**
- p50 latency: < 50ms
- p99 latency: < 100ms
- Throughput: 10,000 ticks/sec
- Concurrent connections: 100+
- Memory leak: < 10% over 1 hour

---

## Sign-Off

- [ ] QA Lead: _____________________ Date: _____
- [ ] Backend Lead: _____________________ Date: _____
- [ ] Engineering Director: _____________________ Date: _____
