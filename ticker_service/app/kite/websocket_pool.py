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
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set

from loguru import logger

# Import Prometheus metrics
try:
    from ..metrics import (
        websocket_pool_connections,
        websocket_pool_subscribed_tokens,
        websocket_pool_target_tokens,
        websocket_pool_capacity_utilization,
        websocket_pool_subscriptions_total,
        websocket_pool_unsubscriptions_total,
        websocket_pool_subscription_errors_total,
        websocket_pool_connected_status,
    )
    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False
    logger.warning("Prometheus metrics not available for WebSocket pool")

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
        self._pool_lock = threading.RLock()  # Use RLock for reentrant locking (same thread can acquire multiple times)

        # Track which token is on which connection
        self._token_to_connection: Dict[int, int] = {}  # token -> connection_id

        # Target tokens (what we want to be subscribed to)
        self._target_tokens: Set[int] = set()

        # Statistics
        self.total_connections_created = 0
        self.total_subscriptions = 0
        self.total_unsubscriptions = 0

        # Health monitoring
        self._health_check_task: Optional[asyncio.Task] = None
        self._last_tick_time: Dict[int, float] = {}  # connection_id -> timestamp

        # Subscribe timeout handling
        self._subscribe_executor = ThreadPoolExecutor(
            max_workers=5,
            thread_name_prefix="ws_subscribe"
        )
        self._subscribe_timeout = 10.0  # 10 second timeout for subscribe operations

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        """Initialize the pool with the event loop and start health monitoring"""
        self._loop = loop

        # Start health check task
        self._health_check_task = loop.create_task(self._health_check_loop())

        logger.info(
            "WebSocket pool started for account %s (max per connection: %d, health monitoring: enabled)",
            self.account_id,
            self.max_instruments_per_connection,
        )

    def _create_connection(self) -> WebSocketConnection:
        """Create a new WebSocket connection"""
        logger.info("DEBUG: _create_connection() called for account %s", self.account_id)
        if not KiteTicker:
            raise RuntimeError("KiteTicker not available")

        connection_id = self._next_connection_id
        self._next_connection_id += 1
        logger.info("DEBUG: Creating connection #%d", connection_id)

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
            # Thread-safe state update
            with self._pool_lock:
                connection.connected = True

            logger.info(
                "WebSocket connection #%d connected for account %s",
                connection_id,
                self.account_id,
            )
            # Resubscribe tokens for this connection after reconnect
            self._sync_connection_subscriptions(connection)

        def _on_close(ws, code, reason):
            # Thread-safe state update
            with self._pool_lock:
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

            # Validate event loop exists and is not closed
            if not self._error_handler:
                return

            if not self._loop or self._loop.is_closed():
                logger.warning(
                    "Cannot dispatch error callback for connection #%d: event loop unavailable",
                    connection_id
                )
                return

            try:
                asyncio.run_coroutine_threadsafe(
                    self._error_handler(
                        self.account_id,
                        RuntimeError(f"WS connection #{connection_id} error {code}: {reason}"),
                    ),
                    self._loop,
                )
            except Exception as e:
                logger.exception(
                    "Failed to dispatch error callback for connection #%d: %s",
                    connection_id,
                    e
                )

        def _on_ticks(ws, ticks):
            logger.info(
                "DEBUG: _on_ticks fired for connection #%d: %d ticks received, handler=%s",
                connection_id,
                len(ticks) if ticks else 0,
                "SET" if self._tick_handler else "None"
            )

            # Update heartbeat timestamp
            self._last_tick_time[connection_id] = time.time()

            # Validate event loop exists and is not closed
            if not self._tick_handler:
                logger.error("CRITICAL: No tick handler registered for connection #%d - ticks will be dropped!", connection_id)
                return

            if not self._loop or self._loop.is_closed():
                logger.warning(
                    "Cannot dispatch ticks for connection #%d: event loop unavailable",
                    connection_id
                )
                return

            try:
                logger.info(
                    f"DEBUG: About to dispatch {len(ticks)} ticks for account {self.account_id}"
                )
                future = asyncio.run_coroutine_threadsafe(
                    self._tick_handler(self.account_id, ticks),
                    self._loop,
                )
                logger.info(f"DEBUG: Ticks dispatched successfully for connection #{connection_id}")
            except Exception as e:
                logger.exception(
                    f"EXCEPTION: Failed to dispatch ticks from connection #{connection_id}: {e}"
                )

        ticker.on_connect = _on_connect
        ticker.on_close = _on_close
        ticker.on_error = _on_error
        ticker.on_ticks = _on_ticks

        # Start the connection
        # IMPORTANT: ticker.connect() can block even with threaded=True when called from asyncio.
        # We need to call it in a dedicated daemon thread that won't be cleaned up.
        logger.info(
            "About to call ticker.connect() for connection #%d (api_key=%s, token=%s...)",
            connection_id,
            self.api_key[:10],
            self.access_token[:20]
        )

        # Run ticker.connect() in a daemon thread to avoid blocking
        # Must be daemon so it doesn't prevent shutdown, and must not be in a ThreadPoolExecutor
        # that gets cleaned up, as that would kill KiteTicker's background threads
        import threading

        def _start_connection():
            try:
                logger.info("Starting ticker.connect() in thread for connection #%d", connection_id)
                # Note: KiteTicker.connect() signature: connect(threaded=False, disable_ssl_verification=False, proxy=None)
                # It does NOT accept 'reconnect' parameter - reconnection is automatic
                ticker.connect(threaded=True, disable_ssl_verification=False)
                logger.info("ticker.connect() returned for connection #%d", connection_id)
            except Exception as e:
                logger.error(
                    f"ticker.connect() exception for connection #{connection_id}: {e}",
                    exc_info=True
                )

        connect_thread = threading.Thread(
            target=_start_connection,
            name=f"kite_connect_{self.account_id}_{connection_id}",
            daemon=True
        )
        connect_thread.start()

        # Give it a moment to start
        import time
        time.sleep(0.1)

        logger.info(
            "ticker.connect() initiated in daemon thread for connection #%d",
            connection_id
        )

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
        logger.info("DEBUG: _get_or_create_connection_for_tokens() called, token_count=%d, existing_connections=%d", token_count, len(self._connections))
        with self._pool_lock:
            logger.info("DEBUG: Lock acquired in _get_or_create_connection_for_tokens()")
            # Try to find existing connection with enough capacity
            for connection in self._connections:
                if connection.available_capacity() >= token_count:
                    logger.info("DEBUG: Found existing connection with capacity")
                    return connection

            # Need to create new connection
            logger.info("DEBUG: No suitable connection found, creating new one")
            connection = self._create_connection()
            self._connections.append(connection)
            return connection

    def _subscribe_with_timeout(
        self,
        connection: WebSocketConnection,
        tokens: List[int],
        mode: str
    ) -> bool:
        """
        Execute subscribe operation with timeout to prevent indefinite hangs.

        Args:
            connection: WebSocket connection to subscribe on
            tokens: List of instrument tokens to subscribe
            mode: Ticker mode (FULL, QUOTE, or LTP)

        Returns:
            True if subscription succeeded, False if timeout or error
        """
        def _do_subscribe():
            logger.info(
                "DEBUG: Subscribing %d tokens on connection #%d",
                len(tokens),
                connection.connection_id
            )
            connection.ticker.subscribe(tokens)
            logger.info("DEBUG: Subscribe() completed for connection #%d", connection.connection_id)

            # Set mode
            if mode == "FULL":
                logger.info("DEBUG: Setting MODE_FULL for connection #%d", connection.connection_id)
                connection.ticker.set_mode(connection.ticker.MODE_FULL, tokens)
            elif mode == "QUOTE":
                logger.info("DEBUG: Setting MODE_QUOTE for connection #%d", connection.connection_id)
                connection.ticker.set_mode(connection.ticker.MODE_QUOTE, tokens)
            else:
                logger.info("DEBUG: Setting MODE_LTP for connection #%d", connection.connection_id)
                connection.ticker.set_mode(connection.ticker.MODE_LTP, tokens)

            logger.info("DEBUG: set_mode() completed for connection #%d", connection.connection_id)

        future = self._subscribe_executor.submit(_do_subscribe)
        try:
            future.result(timeout=self._subscribe_timeout)
            return True
        except FuturesTimeoutError:
            logger.error(
                "Subscribe operation timeout after %.1fs for connection #%d (tokens=%s)",
                self._subscribe_timeout,
                connection.connection_id,
                tokens
            )
            return False
        except Exception as e:
            logger.exception(
                "Subscribe operation failed for connection #%d (tokens=%s): %s",
                connection.connection_id,
                tokens,
                e
            )
            return False

    def _sync_connection_subscriptions(self, connection: WebSocketConnection) -> None:
        """Sync subscriptions for a specific connection"""
        logger.info(
            "DEBUG _sync_connection_subscriptions: conn_id=%d connected=%s has_ws=%s tokens_count=%d",
            connection.connection_id,
            connection.connected,
            hasattr(connection.ticker, "ws"),
            len(connection.subscribed_tokens)
        )

        if not connection.connected or not hasattr(connection.ticker, "ws"):
            logger.warning(
                "Skipping sync for connection #%d: connected=%s has_ws=%s",
                connection.connection_id,
                connection.connected,
                hasattr(connection.ticker, "ws")
            )
            return

        tokens = list(connection.subscribed_tokens)
        if not tokens:
            logger.warning("No tokens to sync for connection #%d", connection.connection_id)
            return

        logger.info(
            "Syncing %d tokens for connection #%d (mode=%s) in batches",
            len(tokens),
            connection.connection_id,
            self.ticker_mode
        )

        mode = self.ticker_mode.upper()

        # Subscribe in batches of 100 to avoid overwhelming the WebSocket
        batch_size = 100
        total_success = True

        for i in range(0, len(tokens), batch_size):
            batch = tokens[i:i+batch_size]
            logger.info(
                "Syncing batch %d-%d (%d tokens) for connection #%d",
                i,
                min(i+batch_size, len(tokens)),
                len(batch),
                connection.connection_id
            )
            success = self._subscribe_with_timeout(connection, batch, mode)
            if not success:
                total_success = False
                logger.error(
                    "Failed to sync batch %d-%d for connection #%d",
                    i,
                    i+batch_size,
                    connection.connection_id
                )

        success = total_success

        if success:
            logger.info(
                "✓ Synced %d tokens for connection #%d (account %s)",
                len(tokens),
                connection.connection_id,
                self.account_id,
            )
        else:
            logger.error(
                "Failed to sync subscriptions for connection #%d (account %s) - timeout or error",
                connection.connection_id,
                self.account_id,
            )

            # Invoke error handler if registered
            if self._error_handler and self._loop and not self._loop.is_closed():
                try:
                    asyncio.run_coroutine_threadsafe(
                        self._error_handler(
                            self.account_id,
                            RuntimeError(
                                f"Subscription sync failed for connection #{connection.connection_id}: "
                                f"{len(tokens)} tokens timeout or error"
                            ),
                        ),
                        self._loop,
                    )
                except Exception as e:
                    logger.exception(
                        "Failed to dispatch error callback for subscription sync failure: %s",
                        e
                    )

    async def subscribe_tokens(self, tokens: List[int]) -> None:
        """Subscribe to tokens, automatically creating new connections if needed (async to prevent event loop blocking)"""
        if not tokens:
            return

        # Phase 1: Determine which tokens need subscription and assign to connections
        # Hold lock for entire state mutation to prevent race conditions
        pending_subscriptions = []  # List of (token, connection_id, connection)

        with self._pool_lock:
            self._target_tokens.update(tokens)

            # Determine which tokens need subscription (while holding lock)
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

            # Distribute tokens across connections (while holding lock)
            for token in tokens_to_subscribe:
                connection = self._get_or_create_connection_for_tokens(1)

                # Add token to connection metadata
                connection.subscribed_tokens.add(token)
                self._token_to_connection[token] = connection.connection_id

                # Track for actual subscription outside lock
                if connection.connected and hasattr(connection.ticker, "ws"):
                    pending_subscriptions.append((token, connection.connection_id, connection))

        # Phase 2: Perform actual network I/O outside lock
        # This prevents holding lock during potentially slow network operations
        # Run subscriptions in executor to prevent blocking event loop
        mode = self.ticker_mode.upper()

        async def _subscribe_token(token: int, conn_id: int, connection):
            """Subscribe a single token asynchronously"""
            # Run blocking subscribe operation in executor
            loop = asyncio.get_running_loop()
            success = await loop.run_in_executor(
                None,
                self._subscribe_with_timeout,
                connection,
                [token],
                mode
            )

            if success:
                with self._pool_lock:
                    self.total_subscriptions += 1
            else:
                # Remove from tracking on failure
                logger.error(
                    "Failed to subscribe token %d on connection #%d - timeout or error",
                    token,
                    conn_id,
                )
                with self._pool_lock:
                    connection.subscribed_tokens.discard(token)
                    if token in self._token_to_connection:
                        del self._token_to_connection[token]

                # Update error metrics
                if METRICS_AVAILABLE:
                    websocket_pool_subscription_errors_total.labels(
                        account_id=self.account_id,
                        error_type="timeout_or_error"
                    ).inc()

                # Invoke error handler if registered
                if self._error_handler and self._loop and not self._loop.is_closed():
                    try:
                        await self._error_handler(
                            self.account_id,
                            RuntimeError(
                                f"Failed to subscribe token {token} on connection #{conn_id}: "
                                f"timeout or error"
                            ),
                        )
                    except Exception as e:
                        logger.exception(
                            "Failed to dispatch error callback for token subscription failure: %s",
                            e
                        )

        # Subscribe all tokens concurrently (but still with timeout protection)
        await asyncio.gather(
            *[_subscribe_token(token, conn_id, connection)
              for token, conn_id, connection in pending_subscriptions],
            return_exceptions=True
        )

        logger.info(
            "Subscription complete for account %s: %d tokens across %d connections",
            self.account_id,
            len(self._target_tokens),
            len(self._connections),
        )

        # Update Prometheus metrics
        self._update_metrics()

        # Update subscription counter metrics
        if METRICS_AVAILABLE:
            websocket_pool_subscriptions_total.labels(account_id=self.account_id).inc(
                len(pending_subscriptions)
            )

    def unsubscribe_tokens(self, tokens: List[int]) -> None:
        """Unsubscribe from tokens (only removes from tracking on success)"""
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
                # Connection no longer exists, safe to remove from tracking
                with self._pool_lock:
                    if token in self._token_to_connection:
                        del self._token_to_connection[token]
                continue

            # Unsubscribe
            success = False
            if connection.connected and hasattr(connection.ticker, "ws"):
                try:
                    connection.ticker.unsubscribe([token])
                    self.total_unsubscriptions += 1
                    success = True
                except Exception:
                    logger.exception(
                        "Failed to unsubscribe token %d from connection #%d",
                        token,
                        connection_id,
                    )
            else:
                # Connection not active, safe to remove from tracking
                success = True

            # Only remove from tracking if unsubscribe succeeded
            if success:
                with self._pool_lock:
                    connection.subscribed_tokens.discard(token)
                    if token in self._token_to_connection:
                        del self._token_to_connection[token]

                # Update unsubscription counter
                if METRICS_AVAILABLE:
                    websocket_pool_unsubscriptions_total.labels(account_id=self.account_id).inc()

        # Update Prometheus metrics after all unsubscriptions
        self._update_metrics()

    async def _health_check_loop(self):
        """Background task that monitors connection health and detects stale connections"""
        logger.info("Connection health monitoring started for account %s", self.account_id)

        while True:
            try:
                await asyncio.sleep(30)  # Check every 30 seconds

                now = time.time()
                with self._pool_lock:
                    connections_to_check = list(self._connections)

                for connection in connections_to_check:
                    if not connection.connected:
                        continue

                    # Check if we've received ticks recently (60 second threshold)
                    last_tick = self._last_tick_time.get(connection.connection_id, now)
                    time_since_tick = now - last_tick

                    if time_since_tick > 60:
                        logger.warning(
                            "Connection #%d appears stale (no ticks for %.1fs). May need reconnection.",
                            connection.connection_id,
                            time_since_tick
                        )
                        # Note: KiteTicker handles reconnection automatically
                        # We just log the warning for monitoring purposes

            except asyncio.CancelledError:
                logger.info("Connection health monitoring stopped for account %s", self.account_id)
                break
            except Exception as e:
                logger.exception("Error in health check loop: %s", e)
                # Continue checking after error

    def stop_all(self) -> None:
        """Stop all WebSocket connections with forced cleanup to prevent resource leaks"""
        logger.info("Stopping all WebSocket connections for account %s", self.account_id)

        # Stop health check task
        if self._health_check_task:
            self._health_check_task.cancel()
            self._health_check_task = None
            logger.debug("Health check task cancelled")

        # Shutdown subscribe executor
        logger.debug("Shutting down subscribe executor")
        self._subscribe_executor.shutdown(wait=True, cancel_futures=True)
        logger.debug("Subscribe executor shutdown complete")

        with self._pool_lock:
            self._target_tokens.clear()
            self._token_to_connection.clear()

            for connection in self._connections:
                conn_id = connection.connection_id

                try:
                    # Step 1: Try graceful close
                    logger.debug("Closing connection #%d gracefully", conn_id)
                    connection.ticker.close()

                    # Step 2: Wait for thread termination (with timeout)
                    if hasattr(connection.ticker, '_thread') and connection.ticker._thread:
                        logger.debug("Waiting for connection #%d thread to terminate", conn_id)
                        connection.ticker._thread.join(timeout=5.0)

                        if connection.ticker._thread.is_alive():
                            logger.warning(
                                "Connection #%d thread did not terminate within timeout",
                                conn_id
                            )

                except Exception as e:
                    logger.error(
                        "Failed to close connection #%d gracefully: %s. Forcing cleanup.",
                        conn_id,
                        str(e)
                    )

                    # Step 3: Force cleanup on failure
                    try:
                        # Force close underlying WebSocket if accessible
                        if hasattr(connection.ticker, 'ws') and connection.ticker.ws:
                            logger.debug("Force closing WebSocket for connection #%d", conn_id)
                            connection.ticker.ws.close()

                        # Force stop the thread if accessible
                        if hasattr(connection.ticker, '_thread') and connection.ticker._thread:
                            # Note: Can't force kill threads in Python, but we tried graceful shutdown
                            logger.warning(
                                "Connection #%d thread may still be running after forced close",
                                conn_id
                            )
                    except Exception as force_error:
                        logger.exception(
                            "Failed to force close connection #%d: %s",
                            conn_id,
                            str(force_error)
                        )

                finally:
                    # Step 4: Always clean up connection state regardless of errors
                    connection.connected = False
                    connection.subscribed_tokens.clear()
                    logger.debug("Connection #%d state cleaned up", conn_id)

            self._connections.clear()

        logger.info("All WebSocket connections stopped for account %s", self.account_id)

        # Update metrics to reflect stopped state
        self._update_metrics()

    def _update_metrics(self) -> None:
        """Update Prometheus metrics based on current pool state"""
        if not METRICS_AVAILABLE:
            return

        with self._pool_lock:
            # Update connection count
            websocket_pool_connections.labels(account_id=self.account_id).set(
                len(self._connections)
            )

            # Update token counts
            total_subscribed = sum(len(c.subscribed_tokens) for c in self._connections)
            websocket_pool_subscribed_tokens.labels(account_id=self.account_id).set(
                total_subscribed
            )
            websocket_pool_target_tokens.labels(account_id=self.account_id).set(
                len(self._target_tokens)
            )

            # Update capacity utilization
            total_capacity = len(self._connections) * self.max_instruments_per_connection
            if total_capacity > 0:
                utilization = (total_subscribed / total_capacity) * 100
                websocket_pool_capacity_utilization.labels(account_id=self.account_id).set(
                    round(utilization, 2)
                )
            else:
                websocket_pool_capacity_utilization.labels(account_id=self.account_id).set(0)

            # Update per-connection status
            for connection in self._connections:
                websocket_pool_connected_status.labels(
                    account_id=self.account_id,
                    connection_id=str(connection.connection_id)
                ).set(1 if connection.connected else 0)

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
