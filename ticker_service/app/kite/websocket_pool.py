"""
Kite WebSocket Connection Pool

Manages multiple KiteTicker WebSocket connections to scale beyond the 1000 instrument limit.
Each WebSocket connection can handle up to 1000 instruments. The pool automatically creates
additional connections as needed when subscriptions exceed capacity.

Features:
- Automatic connection pooling when hitting 1000 instrument limit
- Load balancing across connections
- Unified subscription management
- Connection health monitoring
- Automatic reconnection handling
"""
from __future__ import annotations

import asyncio
import threading
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set

from loguru import logger

try:
    from kiteconnect import KiteTicker
except ImportError:
    KiteTicker = None


TickHandler = Callable[[str, List[Dict[str, Any]]], Awaitable[None]]
ErrorHandler = Callable[[str, Exception], Awaitable[None]]


@dataclass
class WebSocketConnection:
    """Represents a single WebSocket connection in the pool"""
    connection_id: int
    ticker: Any  # KiteTicker
    subscribed_tokens: Set[int]
    connected: bool = False
    max_instruments: int = 1000

    def has_capacity(self) -> bool:
        """Check if this connection can accept more subscriptions"""
        return len(self.subscribed_tokens) < self.max_instruments

    def available_capacity(self) -> int:
        """Get number of available subscription slots"""
        return self.max_instruments - len(self.subscribed_tokens)


class KiteWebSocketPool:
    """
    Pool of KiteTicker WebSocket connections for scaling beyond 1000 instruments.

    Automatically creates new connections when existing ones reach capacity.
    Distributes subscriptions across connections for optimal load balancing.
    """

    def __init__(
        self,
        account_id: str,
        api_key: str,
        access_token: str,
        ws_root: str,
        ticker_mode: str = "LTP",
        max_instruments_per_connection: int = 1000,
        tick_handler: Optional[TickHandler] = None,
        error_handler: Optional[ErrorHandler] = None,
    ):
        self.account_id = account_id
        self.api_key = api_key
        self.access_token = access_token
        self.ws_root = ws_root
        self.ticker_mode = ticker_mode
        self.max_instruments_per_connection = max_instruments_per_connection

        self._tick_handler = tick_handler
        self._error_handler = error_handler
        self._loop: Optional[asyncio.AbstractEventLoop] = None

        self._connections: List[WebSocketConnection] = []
        self._next_connection_id = 0
        self._pool_lock = threading.Lock()

        # Track which token is on which connection
        self._token_to_connection: Dict[int, int] = {}  # token -> connection_id

        # Target tokens (what we want to be subscribed to)
        self._target_tokens: Set[int] = set()

        # Statistics
        self.total_connections_created = 0
        self.total_subscriptions = 0
        self.total_unsubscriptions = 0

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        """Initialize the pool with the event loop"""
        self._loop = loop
        logger.info(
            "WebSocket pool started for account %s (max per connection: %d)",
            self.account_id,
            self.max_instruments_per_connection,
        )

    def _create_connection(self) -> WebSocketConnection:
        """Create a new WebSocket connection"""
        if not KiteTicker:
            raise RuntimeError("KiteTicker not available")

        connection_id = self._next_connection_id
        self._next_connection_id += 1

        ticker = KiteTicker(
            api_key=self.api_key,
            access_token=self.access_token,
            root=self.ws_root,
            reconnect=True,
            reconnect_max_tries=50,
            reconnect_max_delay=60,
        )

        connection = WebSocketConnection(
            connection_id=connection_id,
            ticker=ticker,
            subscribed_tokens=set(),
            connected=False,
            max_instruments=self.max_instruments_per_connection,
        )

        # Set up callbacks
        def _on_connect(ws, response=None):
            connection.connected = True
            logger.info(
                "WebSocket connection #%d connected for account %s",
                connection_id,
                self.account_id,
            )
            # Resubscribe tokens for this connection after reconnect
            self._sync_connection_subscriptions(connection)

        def _on_close(ws, code, reason):
            connection.connected = False
            logger.warning(
                "WebSocket connection #%d closed for account %s (code=%s reason=%s)",
                connection_id,
                self.account_id,
                code,
                reason,
            )

        def _on_error(ws, code, reason):
            logger.error(
                "WebSocket connection #%d error for account %s (code=%s reason=%s)",
                connection_id,
                self.account_id,
                code,
                reason,
            )
            if self._error_handler and self._loop:
                asyncio.run_coroutine_threadsafe(
                    self._error_handler(
                        self.account_id,
                        RuntimeError(f"WS connection #{connection_id} error {code}: {reason}"),
                    ),
                    self._loop,
                )

        def _on_ticks(ws, ticks):
            if self._tick_handler and self._loop:
                asyncio.run_coroutine_threadsafe(
                    self._tick_handler(self.account_id, ticks),
                    self._loop,
                )

        ticker.on_connect = _on_connect
        ticker.on_close = _on_close
        ticker.on_error = _on_error
        ticker.on_ticks = _on_ticks

        # Start the connection
        ticker.connect(threaded=True, reconnect=True, disable_ssl_verification=False)

        self.total_connections_created += 1
        logger.info(
            "Created WebSocket connection #%d for account %s (total connections: %d)",
            connection_id,
            self.account_id,
            len(self._connections) + 1,
        )

        return connection

    def _get_or_create_connection_for_tokens(self, token_count: int) -> WebSocketConnection:
        """Get an existing connection with capacity or create a new one"""
        with self._pool_lock:
            # Try to find existing connection with enough capacity
            for connection in self._connections:
                if connection.available_capacity() >= token_count:
                    return connection

            # Need to create new connection
            connection = self._create_connection()
            self._connections.append(connection)
            return connection

    def _sync_connection_subscriptions(self, connection: WebSocketConnection) -> None:
        """Sync subscriptions for a specific connection"""
        if not connection.connected or not hasattr(connection.ticker, "ws"):
            return

        tokens = list(connection.subscribed_tokens)
        if not tokens:
            return

        try:
            # Subscribe to tokens
            connection.ticker.subscribe(tokens)

            # Set mode
            mode = self.ticker_mode.upper()
            if mode == "FULL":
                connection.ticker.set_mode(connection.ticker.MODE_FULL, tokens)
            elif mode == "QUOTE":
                connection.ticker.set_mode(connection.ticker.MODE_QUOTE, tokens)
            else:
                connection.ticker.set_mode(connection.ticker.MODE_LTP, tokens)

            logger.debug(
                "Synced %d tokens for connection #%d (account %s)",
                len(tokens),
                connection.connection_id,
                self.account_id,
            )
        except Exception:
            logger.exception(
                "Failed to sync subscriptions for connection #%d (account %s)",
                connection.connection_id,
                self.account_id,
            )

    def subscribe_tokens(self, tokens: List[int]) -> None:
        """Subscribe to tokens, automatically creating new connections if needed"""
        if not tokens:
            return

        with self._pool_lock:
            self._target_tokens.update(tokens)

        # Group tokens into batches that fit within connection capacity
        tokens_to_subscribe = [t for t in tokens if t not in self._token_to_connection]

        if not tokens_to_subscribe:
            logger.debug("All tokens already subscribed for account %s", self.account_id)
            return

        logger.info(
            "Subscribing to %d new tokens for account %s (total target: %d)",
            len(tokens_to_subscribe),
            self.account_id,
            len(self._target_tokens),
        )

        # Distribute tokens across connections
        for token in tokens_to_subscribe:
            connection = self._get_or_create_connection_for_tokens(1)

            # Add token to connection
            connection.subscribed_tokens.add(token)
            self._token_to_connection[token] = connection.connection_id

            # Subscribe if connection is ready
            if connection.connected and hasattr(connection.ticker, "ws"):
                try:
                    connection.ticker.subscribe([token])

                    # Set mode
                    mode = self.ticker_mode.upper()
                    if mode == "FULL":
                        connection.ticker.set_mode(connection.ticker.MODE_FULL, [token])
                    elif mode == "QUOTE":
                        connection.ticker.set_mode(connection.ticker.MODE_QUOTE, [token])
                    else:
                        connection.ticker.set_mode(connection.ticker.MODE_LTP, [token])

                    self.total_subscriptions += 1
                except Exception:
                    logger.exception(
                        "Failed to subscribe token %d on connection #%d",
                        token,
                        connection.connection_id,
                    )

        logger.info(
            "Subscription complete for account %s: %d tokens across %d connections",
            self.account_id,
            len(self._target_tokens),
            len(self._connections),
        )

    def unsubscribe_tokens(self, tokens: List[int]) -> None:
        """Unsubscribe from tokens"""
        if not tokens:
            return

        with self._pool_lock:
            for token in tokens:
                self._target_tokens.discard(token)

        for token in tokens:
            connection_id = self._token_to_connection.get(token)
            if connection_id is None:
                continue

            # Find the connection
            connection = next(
                (c for c in self._connections if c.connection_id == connection_id),
                None,
            )
            if not connection:
                continue

            # Unsubscribe
            if connection.connected and hasattr(connection.ticker, "ws"):
                try:
                    connection.ticker.unsubscribe([token])
                    self.total_unsubscriptions += 1
                except Exception:
                    logger.exception(
                        "Failed to unsubscribe token %d from connection #%d",
                        token,
                        connection_id,
                    )

            # Remove from tracking
            connection.subscribed_tokens.discard(token)
            del self._token_to_connection[token]

    def stop_all(self) -> None:
        """Stop all WebSocket connections"""
        logger.info("Stopping all WebSocket connections for account %s", self.account_id)

        with self._pool_lock:
            self._target_tokens.clear()
            self._token_to_connection.clear()

            for connection in self._connections:
                try:
                    connection.ticker.close()
                except Exception:
                    logger.exception(
                        "Failed to close connection #%d for account %s",
                        connection.connection_id,
                        self.account_id,
                    )

            self._connections.clear()

        logger.info("All WebSocket connections stopped for account %s", self.account_id)

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the connection pool"""
        with self._pool_lock:
            connection_stats = []
            for connection in self._connections:
                connection_stats.append({
                    "connection_id": connection.connection_id,
                    "connected": connection.connected,
                    "subscribed_tokens": len(connection.subscribed_tokens),
                    "capacity": connection.max_instruments,
                    "available_capacity": connection.available_capacity(),
                    "utilization_percent": round(
                        len(connection.subscribed_tokens) / connection.max_instruments * 100,
                        2,
                    ),
                })

            return {
                "account_id": self.account_id,
                "total_connections": len(self._connections),
                "total_target_tokens": len(self._target_tokens),
                "total_subscribed_tokens": sum(len(c.subscribed_tokens) for c in self._connections),
                "max_instruments_per_connection": self.max_instruments_per_connection,
                "total_capacity": len(self._connections) * self.max_instruments_per_connection,
                "connections": connection_stats,
                "statistics": {
                    "total_connections_created": self.total_connections_created,
                    "total_subscriptions": self.total_subscriptions,
                    "total_unsubscriptions": self.total_unsubscriptions,
                },
            }
