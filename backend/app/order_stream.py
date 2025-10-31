"""
WebSocket Order Stream Manager
Connects to ticker_service WebSocket and relays order updates to frontend clients.
"""

import asyncio
import json
import logging
from typing import Optional, Dict, Set
from datetime import datetime
import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException

from .realtime import RealTimeHub
from .config import get_settings


logger = logging.getLogger(__name__)
settings = get_settings()


class OrderStreamManager:
    """
    Manages WebSocket connections to ticker_service for real-time order updates.
    Relays updates to frontend clients via RealTimeHub.
    """

    def __init__(self, ticker_url: str, realtime_hub: RealTimeHub):
        """
        Initialize OrderStreamManager.

        Args:
            ticker_url: Base URL for ticker_service (e.g., http://localhost:8080)
            realtime_hub: RealTimeHub instance for broadcasting to frontend
        """
        # Convert http:// to ws://
        self._ws_base_url = ticker_url.replace("http://", "ws://").replace("https://", "wss://")
        self._hub = realtime_hub
        self._active_accounts: Set[str] = set()
        self._connections: Dict[str, asyncio.Task] = {}
        self._running = False
        logger.info(f"OrderStreamManager initialized with ws_url={self._ws_base_url}")

    async def start(self, account_ids: Optional[list] = None):
        """
        Start order streaming for specified accounts.

        Args:
            account_ids: List of account IDs to stream. If None, streams default account.
        """
        if self._running:
            logger.warning("OrderStreamManager already running")
            return

        self._running = True

        # Default to primary account if none specified
        if not account_ids:
            account_ids = [settings.ticker_service_account_id or "primary"]

        # Start connection for each account
        for account_id in account_ids:
            if account_id not in self._active_accounts:
                task = asyncio.create_task(self._connect_account(account_id))
                self._connections[account_id] = task
                self._active_accounts.add(account_id)
                logger.info(f"Started order stream for account: {account_id}")

    async def stop(self):
        """Stop all order stream connections."""
        self._running = False

        # Cancel all connection tasks
        for account_id, task in self._connections.items():
            task.cancel()
            logger.info(f"Stopping order stream for account: {account_id}")

        # Wait for all tasks to finish
        if self._connections:
            await asyncio.gather(*self._connections.values(), return_exceptions=True)

        self._connections.clear()
        self._active_accounts.clear()
        logger.info("OrderStreamManager stopped")

    async def _connect_account(self, account_id: str):
        """
        Connect to ticker_service WebSocket for an account.
        Automatically reconnects on disconnection.

        Args:
            account_id: Account identifier
        """
        ws_url = f"{self._ws_base_url}/advanced/ws/orders/{account_id}"
        retry_delay = 1  # Start with 1 second
        max_retry_delay = 60  # Max 60 seconds between retries

        while self._running:
            try:
                logger.info(f"Connecting to ticker_service WebSocket: {ws_url}")

                async with websockets.connect(
                    ws_url,
                    ping_interval=30,
                    ping_timeout=10,
                    close_timeout=5
                ) as websocket:
                    logger.info(f"WebSocket connected for account: {account_id}")
                    retry_delay = 1  # Reset retry delay on successful connection

                    # Keep-alive task
                    keep_alive_task = asyncio.create_task(
                        self._send_keep_alive(websocket)
                    )

                    try:
                        # Listen for messages
                        async for message in websocket:
                            await self._handle_message(account_id, message)
                    finally:
                        keep_alive_task.cancel()

            except ConnectionClosed as e:
                logger.warning(f"WebSocket closed for {account_id}: {e}. Reconnecting in {retry_delay}s...")

            except WebSocketException as e:
                logger.error(f"WebSocket error for {account_id}: {e}. Reconnecting in {retry_delay}s...")

            except Exception as e:
                logger.error(f"Unexpected error in order stream for {account_id}: {e}", exc_info=True)

            # Wait before reconnecting (exponential backoff)
            if self._running:
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, max_retry_delay)

    async def _send_keep_alive(self, websocket):
        """
        Send periodic ping messages to keep connection alive.

        Args:
            websocket: WebSocket connection
        """
        try:
            while True:
                await asyncio.sleep(30)
                await websocket.send("ping")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Keep-alive error: {e}")

    async def _handle_message(self, account_id: str, message: str):
        """
        Handle incoming WebSocket message from ticker_service.

        Args:
            account_id: Account identifier
            message: Raw message from ticker_service
        """
        try:
            # Ignore pong responses
            if message == "pong":
                return

            # Parse JSON message
            data = json.loads(message)

            # Validate message structure
            if not isinstance(data, dict) or "type" not in data:
                logger.warning(f"Invalid message format from ticker_service: {message}")
                return

            msg_type = data.get("type")

            # Handle order updates
            if msg_type == "order_update":
                await self._handle_order_update(account_id, data)

            # Handle other message types
            elif msg_type == "connection_established":
                logger.info(f"Connection established for account: {account_id}")

            elif msg_type == "error":
                logger.error(f"Error from ticker_service: {data.get('message')}")

            else:
                logger.debug(f"Unknown message type: {msg_type}")

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse message: {e}. Message: {message}")

        except Exception as e:
            logger.error(f"Error handling message: {e}", exc_info=True)

    async def _handle_order_update(self, account_id: str, data: Dict):
        """
        Handle order_update message and broadcast to frontend.

        Args:
            account_id: Account identifier
            data: Order update data from ticker_service
        """
        try:
            # Extract order data
            order_data = data.get("data", {})
            order_id = order_data.get("order_id")

            if not order_id:
                logger.warning(f"Order update missing order_id: {data}")
                return

            # Add timestamp if not present
            if "timestamp" not in data:
                data["timestamp"] = datetime.utcnow().isoformat() + "Z"

            # Log the update
            status = order_data.get("status")
            logger.info(
                f"Order update: account={account_id}, order_id={order_id}, status={status}"
            )

            # Broadcast to frontend clients subscribed to this account
            channel = f"account:{account_id}:orders"
            await self._hub.broadcast(channel, data)

            # Also broadcast to general orders channel
            await self._hub.broadcast("orders", data)

        except Exception as e:
            logger.error(f"Error handling order update: {e}", exc_info=True)

    async def get_status(self) -> Dict:
        """
        Get current status of order stream manager.

        Returns:
            Status dict with active accounts and connection states
        """
        return {
            "running": self._running,
            "active_accounts": list(self._active_accounts),
            "total_connections": len(self._connections),
            "hub_clients": len(self._hub._clients)
        }
