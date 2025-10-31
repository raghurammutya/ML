"""
WebSocket Order Streaming

Real-time order status updates via WebSocket instead of polling.
Clients connect to /ws/orders and receive live updates.
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Dict, Set
from datetime import datetime, timezone

from fastapi import WebSocket, WebSocketDisconnect
from loguru import logger


class OrderStreamManager:
    """Manages WebSocket connections for real-time order updates"""

    # Configuration
    MAX_CONNECTIONS_PER_ACCOUNT = 100
    HEARTBEAT_TIMEOUT = 60  # seconds - close connection if no ping received

    def __init__(self):
        # account_id -> set of WebSocket connections
        self._connections: Dict[str, Set[WebSocket]] = {}
        # WebSocket -> last ping time
        self._last_ping: Dict[WebSocket, float] = {}
        self._lock = asyncio.Lock()
        # Start heartbeat monitor task
        self._heartbeat_task = None

    async def connect(self, websocket: WebSocket, account_id: str) -> None:
        """Register a new WebSocket connection"""
        # Check connection limit
        async with self._lock:
            current_connections = len(self._connections.get(account_id, set()))
            if current_connections >= self.MAX_CONNECTIONS_PER_ACCOUNT:
                await websocket.close(code=1008, reason="Connection limit exceeded")
                logger.warning(f"WebSocket connection rejected for account {account_id}: Limit exceeded")
                return

        await websocket.accept()

        async with self._lock:
            if account_id not in self._connections:
                self._connections[account_id] = set()
            self._connections[account_id].add(websocket)
            # Initialize heartbeat tracking
            self._last_ping[websocket] = time.time()

        logger.info(f"WebSocket connected for account {account_id}. Total: {len(self._connections[account_id])}")

        # Start heartbeat monitor if not already running
        if self._heartbeat_task is None or self._heartbeat_task.done():
            self._heartbeat_task = asyncio.create_task(self._monitor_heartbeats())

        # Send welcome message
        await websocket.send_json({
            "type": "connected",
            "account_id": account_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

    async def disconnect(self, websocket: WebSocket, account_id: str) -> None:
        """Unregister a WebSocket connection"""
        async with self._lock:
            if account_id in self._connections:
                self._connections[account_id].discard(websocket)
                if not self._connections[account_id]:
                    del self._connections[account_id]

            # Clean up heartbeat tracking
            if websocket in self._last_ping:
                del self._last_ping[websocket]

        logger.info(f"WebSocket disconnected for account {account_id}")

    def update_ping(self, websocket: WebSocket) -> None:
        """Update last ping time for a WebSocket connection"""
        if websocket in self._last_ping:
            self._last_ping[websocket] = time.time()

    async def _monitor_heartbeats(self) -> None:
        """Monitor WebSocket connections and close stale ones"""
        while True:
            try:
                await asyncio.sleep(10)  # Check every 10 seconds

                now = time.time()
                stale_connections = []

                async with self._lock:
                    for websocket, last_ping in list(self._last_ping.items()):
                        if now - last_ping > self.HEARTBEAT_TIMEOUT:
                            stale_connections.append(websocket)

                # Close stale connections (outside lock)
                for websocket in stale_connections:
                    try:
                        await websocket.close(code=1000, reason="Heartbeat timeout")
                        logger.warning(f"Closed WebSocket connection due to heartbeat timeout")

                        # Clean up from all account lists
                        async with self._lock:
                            for account_id, connections in list(self._connections.items()):
                                if websocket in connections:
                                    connections.discard(websocket)
                                    if not connections:
                                        del self._connections[account_id]

                            if websocket in self._last_ping:
                                del self._last_ping[websocket]
                    except Exception as e:
                        logger.error(f"Error closing stale WebSocket: {e}")

            except Exception as e:
                logger.error(f"Error in heartbeat monitor: {e}")
                await asyncio.sleep(10)

    async def broadcast_order_update(self, account_id: str, order_data: dict) -> None:
        """Broadcast order update to all connected clients for an account"""
        async with self._lock:
            connections = self._connections.get(account_id, set()).copy()

        if not connections:
            return

        message = {
            "type": "order_update",
            "account_id": account_id,
            "data": order_data,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        # Send to all connections, removing dead ones
        dead_connections = set()
        for websocket in connections:
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.warning(f"Failed to send to WebSocket: {e}")
                dead_connections.add(websocket)

        # Clean up dead connections
        if dead_connections:
            async with self._lock:
                if account_id in self._connections:
                    self._connections[account_id] -= dead_connections

        logger.debug(f"Broadcasted order update to {len(connections) - len(dead_connections)} clients")

    async def broadcast_task_update(self, account_id: str, task_data: dict) -> None:
        """Broadcast task status update"""
        await self.broadcast_order_update(account_id, {
            "event": "task_status",
            **task_data
        })

    def get_connection_count(self, account_id: str = None) -> int:
        """Get number of active connections"""
        if account_id:
            return len(self._connections.get(account_id, set()))
        return sum(len(conns) for conns in self._connections.values())


# Global stream manager
order_stream_manager = OrderStreamManager()
