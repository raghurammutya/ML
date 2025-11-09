"""
WebSocket Position Stream Manager

Connects to ticker_service WebSocket and relays position updates to:
1. Database (account_position table)
2. PositionTracker (for event detection)
3. Frontend clients via RealTimeHub
"""

import asyncio
import json
import logging
from typing import Optional, Dict, Set
from datetime import datetime, timezone
import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException

from .realtime import RealTimeHub
from .config import get_settings
from .database import DataManager
from .services.position_tracker import PositionTracker


logger = logging.getLogger(__name__)
settings = get_settings()


class PositionStreamManager:
    """
    Manages WebSocket connections to ticker_service for real-time position updates.
    Updates database, triggers PositionTracker events, and broadcasts to frontend.
    """

    def __init__(
        self,
        ticker_url: str,
        realtime_hub: RealTimeHub,
        data_manager: DataManager,
        position_tracker: PositionTracker
    ):
        """
        Initialize PositionStreamManager.

        Args:
            ticker_url: Base URL for ticker_service (e.g., http://localhost:8080)
            realtime_hub: RealTimeHub instance for broadcasting to frontend
            data_manager: DataManager for database operations
            position_tracker: PositionTracker for event detection
        """
        # Convert http:// to ws://
        self._ws_base_url = ticker_url.replace("http://", "ws://").replace("https://", "wss://")
        self._hub = realtime_hub
        self._dm = data_manager
        self._tracker = position_tracker
        self._active_accounts: Set[str] = set()
        self._connections: Dict[str, asyncio.Task] = {}
        self._running = False
        logger.info(f"PositionStreamManager initialized with ws_url={self._ws_base_url}")

    async def start(self, account_ids: Optional[list] = None):
        """
        Start position streaming for specified accounts.

        Args:
            account_ids: List of account IDs to stream. If None, streams default account.
        """
        if self._running:
            logger.warning("PositionStreamManager already running")
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
                logger.info(f"Started position stream for account: {account_id}")

    async def stop(self):
        """Stop all position stream connections."""
        self._running = False

        # Cancel all connection tasks
        for account_id, task in self._connections.items():
            task.cancel()
            logger.info(f"Stopping position stream for account: {account_id}")

        # Wait for all tasks to finish
        if self._connections:
            await asyncio.gather(*self._connections.values(), return_exceptions=True)

        self._connections.clear()
        self._active_accounts.clear()
        logger.info("PositionStreamManager stopped")

    async def _connect_account(self, account_id: str):
        """
        Connect to ticker_service WebSocket for an account.
        Automatically reconnects on disconnection.

        Args:
            account_id: Account identifier
        """
        ws_url = f"{self._ws_base_url}/advanced/ws/positions/{account_id}"
        retry_delay = 1  # Start with 1 second
        max_retry_delay = 60  # Max 60 seconds between retries

        while self._running:
            try:
                logger.info(f"Connecting to ticker_service position WebSocket: {ws_url}")

                async with websockets.connect(
                    ws_url,
                    ping_interval=20,
                    ping_timeout=10,
                    close_timeout=5
                ) as websocket:
                    logger.info(f"Connected to position stream for account: {account_id}")
                    retry_delay = 1  # Reset retry delay on successful connection

                    # Listen for messages
                    async for message in websocket:
                        try:
                            await self._handle_message(account_id, message)
                        except Exception as e:
                            logger.exception(f"Error handling position message: {e}")

            except ConnectionClosed:
                if self._running:
                    logger.warning(
                        f"Position WebSocket closed for {account_id}, "
                        f"reconnecting in {retry_delay}s"
                    )
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, max_retry_delay)
                else:
                    logger.info(f"Position WebSocket closed for {account_id} (shutdown)")
                    break

            except WebSocketException as e:
                if self._running:
                    logger.error(
                        f"WebSocket error for {account_id}: {e}, "
                        f"reconnecting in {retry_delay}s"
                    )
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, max_retry_delay)
                else:
                    break

            except Exception as e:
                if self._running:
                    logger.exception(
                        f"Unexpected error in position stream for {account_id}: {e}, "
                        f"reconnecting in {retry_delay}s"
                    )
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, max_retry_delay)
                else:
                    break

        logger.info(f"Position stream stopped for account: {account_id}")

    async def _handle_message(self, account_id: str, message: str):
        """
        Handle incoming position update message.

        Args:
            account_id: Account identifier
            message: JSON message from WebSocket
        """
        try:
            data = json.loads(message)
            message_type = data.get("type")

            if message_type == "positions":
                # Full position update
                positions = data.get("data", [])
                await self._handle_position_update(account_id, positions)

            elif message_type == "position_update":
                # Single position update
                position = data.get("data")
                if position:
                    await self._handle_position_update(account_id, [position])

            elif message_type == "heartbeat":
                # Heartbeat from server
                logger.debug(f"Received position stream heartbeat for {account_id}")

            elif message_type == "error":
                # Error message
                error_msg = data.get("message", "Unknown error")
                logger.error(f"Position stream error for {account_id}: {error_msg}")

            else:
                logger.warning(f"Unknown position message type: {message_type}")

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in position message: {e}")
        except Exception as e:
            logger.exception(f"Error processing position message: {e}")

    async def _handle_position_update(self, account_id: str, positions: list):
        """
        Process position update.

        Steps:
        1. Update database (account_position table)
        2. Trigger PositionTracker for event detection
        3. Broadcast to frontend via RealTimeHub

        Args:
            account_id: Account identifier
            positions: List of position dicts from ticker_service
        """
        logger.debug(f"Processing position update for {account_id}: {len(positions)} positions")

        try:
            # Step 1: Update database
            await self._update_database(account_id, positions)

            # Step 2: Trigger PositionTracker (this will emit events to OrderCleanupWorker)
            await self._tracker.on_position_update(account_id, positions)

            # Step 3: Broadcast to frontend
            await self._broadcast_to_frontend(account_id, positions)

            logger.debug(f"Position update complete for {account_id}")

        except Exception as e:
            logger.exception(f"Error handling position update: {e}")

    async def _update_database(self, account_id: str, positions: list):
        """
        Update account_position table with new position data.

        Args:
            account_id: Account identifier
            positions: List of position dicts
        """
        if not self._dm.pool:
            logger.error("Database pool not available")
            return

        try:
            async with self._dm.pool.acquire() as conn:
                # Start transaction
                async with conn.transaction():
                    # Get existing positions for this account
                    existing_query = """
                        SELECT tradingsymbol, exchange, product
                        FROM account_position
                        WHERE account_id = $1
                    """
                    existing_rows = await conn.fetch(existing_query, account_id)
                    existing_keys = {
                        (row['tradingsymbol'], row['exchange'], row['product'])
                        for row in existing_rows
                    }

                    # Track position keys from update
                    updated_keys = set()

                    # Upsert each position
                    upsert_query = """
                        INSERT INTO account_position (
                            account_id, tradingsymbol, exchange, instrument_token,
                            product, quantity, average_price, last_price,
                            pnl, day_pnl, synced_at, updated_at, raw_data
                        ) VALUES (
                            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13
                        )
                        ON CONFLICT (account_id, tradingsymbol, exchange, product)
                        DO UPDATE SET
                            instrument_token = EXCLUDED.instrument_token,
                            quantity = EXCLUDED.quantity,
                            average_price = EXCLUDED.average_price,
                            last_price = EXCLUDED.last_price,
                            pnl = EXCLUDED.pnl,
                            day_pnl = EXCLUDED.day_pnl,
                            synced_at = EXCLUDED.synced_at,
                            updated_at = EXCLUDED.updated_at,
                            raw_data = EXCLUDED.raw_data
                    """

                    for pos in positions:
                        tradingsymbol = pos.get("tradingsymbol")
                        exchange = pos.get("exchange")
                        product = pos.get("product")

                        # Skip if missing required fields
                        if not all([tradingsymbol, exchange, product]):
                            logger.warning(f"Skipping position with missing fields: {pos}")
                            continue

                        updated_keys.add((tradingsymbol, exchange, product))

                        await conn.execute(
                            upsert_query,
                            account_id,
                            tradingsymbol,
                            exchange,
                            pos.get("instrument_token"),
                            product,
                            pos.get("quantity", 0),
                            pos.get("average_price", 0.0),
                            pos.get("last_price", 0.0),
                            pos.get("pnl", 0.0),
                            pos.get("day_pnl", 0.0),
                            datetime.now(timezone.utc),
                            datetime.now(timezone.utc),
                            json.dumps(pos)
                        )

                    # Delete positions that are no longer in the update (closed positions)
                    closed_keys = existing_keys - updated_keys
                    if closed_keys:
                        delete_query = """
                            DELETE FROM account_position
                            WHERE account_id = $1
                              AND (tradingsymbol, exchange, product) = ANY($2::record[])
                        """
                        # Convert to list of tuples for PostgreSQL
                        closed_list = list(closed_keys)
                        await conn.execute(delete_query, account_id, closed_list)

                        logger.info(
                            f"Deleted {len(closed_keys)} closed positions for {account_id}"
                        )

            logger.debug(f"Database updated with {len(positions)} positions for {account_id}")

        except Exception as e:
            logger.exception(f"Error updating position database: {e}")

    async def _broadcast_to_frontend(self, account_id: str, positions: list):
        """
        Broadcast position update to frontend clients.

        Args:
            account_id: Account identifier
            positions: List of position dicts
        """
        try:
            message = {
                "type": "position_update",
                "account_id": account_id,
                "data": positions,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

            # Broadcast to all connected clients
            await self._hub.broadcast(
                f"positions:{account_id}",
                message
            )

            logger.debug(f"Broadcasted position update to frontend for {account_id}")

        except Exception as e:
            logger.exception(f"Error broadcasting position update: {e}")
