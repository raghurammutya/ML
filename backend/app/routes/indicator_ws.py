# app/routes/indicator_ws.py
"""
WebSocket Streaming for Technical Indicators

Provides real-time indicator updates via WebSocket connection.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Set, Optional, Any
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, Depends
from pydantic import BaseModel, ValidationError

from app.auth import require_api_key_ws
from app.database import DataManager
from app.routes.indicators import get_data_manager
from app.services.indicator_computer import IndicatorComputer, IndicatorSpec
from app.services.indicator_subscription_manager import IndicatorSubscriptionManager
from app.services.indicator_cache import IndicatorCache

import redis.asyncio as redis

logger = logging.getLogger("app.routes.indicator_ws")

router = APIRouter(prefix="/indicators", tags=["indicators-ws"])


# ========== WebSocket Message Models ==========

class SubscribeMessage(BaseModel):
    """Client -> Server: Subscribe to indicators."""
    action: str = "subscribe"
    symbol: str
    timeframe: str
    indicators: list  # List of dicts: {"name": "RSI", "params": {"length": 14}}


class UnsubscribeMessage(BaseModel):
    """Client -> Server: Unsubscribe from indicators."""
    action: str = "unsubscribe"
    symbol: str
    timeframe: str
    indicators: list  # List of indicator IDs: ["RSI_14", "SMA_20"]


class IndicatorUpdate(BaseModel):
    """Server -> Client: Indicator value update."""
    type: str = "indicator_update"
    symbol: str
    timeframe: str
    indicator_id: str
    value: Any
    timestamp: str
    candle_time: Optional[str] = None


class ErrorMessage(BaseModel):
    """Server -> Client: Error notification."""
    type: str = "error"
    message: str
    error_code: Optional[str] = None


class SuccessMessage(BaseModel):
    """Server -> Client: Success confirmation."""
    type: str = "success"
    message: str
    data: Optional[Dict[str, Any]] = None


# ========== Dependency Injection ==========

async def get_redis() -> redis.Redis:
    """Get Redis client."""
    r = redis.Redis(
        host='localhost',
        port=6379,
        db=0,
        decode_responses=True
    )
    try:
        yield r
    finally:
        await r.close()


async def get_subscription_manager(
    redis_client: redis.Redis = Depends(get_redis)
) -> IndicatorSubscriptionManager:
    """Get subscription manager instance."""
    return IndicatorSubscriptionManager(redis_client)


async def get_indicator_computer(
    dm: DataManager = Depends(get_data_manager)
) -> IndicatorComputer:
    """Get indicator computer instance."""
    return IndicatorComputer(dm)


async def get_indicator_cache(
    redis_client: redis.Redis = Depends(get_redis)
) -> IndicatorCache:
    """Get indicator cache instance."""
    return IndicatorCache(redis_client)


# ========== WebSocket Connection Manager ==========

class IndicatorConnectionManager:
    """Manage WebSocket connections and their subscriptions."""

    def __init__(self):
        # WebSocket -> client_id mapping
        self.active_connections: Dict[WebSocket, str] = {}

        # client_id -> Set of (symbol, timeframe, indicator_id) subscriptions
        self.client_subscriptions: Dict[str, Set[tuple]] = {}

    async def connect(self, websocket: WebSocket, client_id: str):
        """Register new WebSocket connection."""
        await websocket.accept()
        self.active_connections[websocket] = client_id
        self.client_subscriptions[client_id] = set()
        logger.info(f"Client {client_id} connected via WebSocket")

    def disconnect(self, websocket: WebSocket):
        """Unregister WebSocket connection."""
        client_id = self.active_connections.get(websocket)
        if client_id:
            del self.active_connections[websocket]
            if client_id in self.client_subscriptions:
                del self.client_subscriptions[client_id]
            logger.info(f"Client {client_id} disconnected")
        return client_id

    def add_subscription(self, client_id: str, symbol: str, timeframe: str, indicator_id: str):
        """Track client subscription."""
        if client_id not in self.client_subscriptions:
            self.client_subscriptions[client_id] = set()
        self.client_subscriptions[client_id].add((symbol, timeframe, indicator_id))

    def remove_subscription(self, client_id: str, symbol: str, timeframe: str, indicator_id: str):
        """Remove client subscription."""
        if client_id in self.client_subscriptions:
            self.client_subscriptions[client_id].discard((symbol, timeframe, indicator_id))

    def get_subscriptions(self, client_id: str) -> Set[tuple]:
        """Get all subscriptions for client."""
        return self.client_subscriptions.get(client_id, set())

    async def send_to_client(self, websocket: WebSocket, message: Dict[str, Any]):
        """Send message to specific client."""
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.error(f"Failed to send to client: {e}")

    async def broadcast_indicator_update(
        self,
        symbol: str,
        timeframe: str,
        indicator_id: str,
        value: Any,
        timestamp: datetime,
        candle_time: Optional[datetime] = None
    ):
        """Broadcast indicator update to all subscribed clients."""
        update = IndicatorUpdate(
            symbol=symbol,
            timeframe=timeframe,
            indicator_id=indicator_id,
            value=value,
            timestamp=timestamp.isoformat(),
            candle_time=candle_time.isoformat() if candle_time else None
        )

        # Find all clients subscribed to this indicator
        for websocket, client_id in self.active_connections.items():
            subscriptions = self.client_subscriptions.get(client_id, set())
            if (symbol, timeframe, indicator_id) in subscriptions:
                await self.send_to_client(websocket, update.dict())


# Global connection manager
manager = IndicatorConnectionManager()


# ========== WebSocket Endpoint ==========

@router.websocket("/stream")
async def indicator_stream(
    websocket: WebSocket,
    api_key: str = Query(..., description="API key for authentication")
):
    """
    WebSocket endpoint for real-time indicator updates.

    **Authentication**: Pass API key as query parameter
    ```
    ws://localhost:8009/indicators/stream?api_key=sb_XXXXXXXX_YYYYYYYY
    ```

    **Client -> Server Messages**:

    1. Subscribe to indicators:
    ```json
    {
      "action": "subscribe",
      "symbol": "NIFTY50",
      "timeframe": "5min",
      "indicators": [
        {"name": "RSI", "params": {"length": 14}},
        {"name": "SMA", "params": {"length": 20}}
      ]
    }
    ```

    2. Unsubscribe from indicators:
    ```json
    {
      "action": "unsubscribe",
      "symbol": "NIFTY50",
      "timeframe": "5min",
      "indicators": ["RSI_14", "SMA_20"]
    }
    ```

    **Server -> Client Messages**:

    1. Indicator update:
    ```json
    {
      "type": "indicator_update",
      "symbol": "NIFTY50",
      "timeframe": "5min",
      "indicator_id": "RSI_14",
      "value": 62.5,
      "timestamp": "2025-10-31T12:00:00Z",
      "candle_time": "2025-10-31T11:55:00Z"
    }
    ```

    2. Success confirmation:
    ```json
    {
      "type": "success",
      "message": "Subscribed to 2 indicators",
      "data": {"subscriptions": ["RSI_14", "SMA_20"]}
    }
    ```

    3. Error notification:
    ```json
    {
      "type": "error",
      "message": "Invalid indicator name: FOO",
      "error_code": "INVALID_INDICATOR"
    }
    ```
    """
    # Authenticate via query parameter
    auth_result = await require_api_key_ws(api_key)
    if not auth_result:
        await websocket.close(code=1008, reason="Invalid API key")
        return

    client_id = str(auth_result.key_id)

    # Initialize services
    redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
    dm = await anext(get_data_manager())

    sub_manager = IndicatorSubscriptionManager(redis_client)
    computer = IndicatorComputer(dm)
    cache = IndicatorCache(redis_client)

    # Connect client
    await manager.connect(websocket, client_id)

    try:
        # Send welcome message
        welcome = SuccessMessage(
            message=f"Connected to indicator stream (client: {client_id})",
            data={"timestamp": datetime.now(timezone.utc).isoformat()}
        )
        await manager.send_to_client(websocket, welcome.dict())

        # Main message loop
        while True:
            try:
                # Receive message from client
                data = await websocket.receive_json()
                action = data.get("action")

                if action == "subscribe":
                    await handle_subscribe(
                        websocket, client_id, data,
                        sub_manager, computer, cache
                    )

                elif action == "unsubscribe":
                    await handle_unsubscribe(
                        websocket, client_id, data,
                        sub_manager
                    )

                elif action == "ping":
                    # Heartbeat
                    pong = {"type": "pong", "timestamp": datetime.now(timezone.utc).isoformat()}
                    await manager.send_to_client(websocket, pong)

                else:
                    error = ErrorMessage(
                        message=f"Unknown action: {action}",
                        error_code="UNKNOWN_ACTION"
                    )
                    await manager.send_to_client(websocket, error.dict())

            except ValidationError as e:
                error = ErrorMessage(
                    message=f"Invalid message format: {str(e)}",
                    error_code="VALIDATION_ERROR"
                )
                await manager.send_to_client(websocket, error.dict())

            except json.JSONDecodeError:
                error = ErrorMessage(
                    message="Invalid JSON",
                    error_code="JSON_ERROR"
                )
                await manager.send_to_client(websocket, error.dict())

    except WebSocketDisconnect:
        logger.info(f"Client {client_id} disconnected")

    except Exception as e:
        logger.error(f"WebSocket error for client {client_id}: {e}")

    finally:
        # Cleanup on disconnect
        await cleanup_client(client_id, sub_manager, redis_client, dm)
        manager.disconnect(websocket)


# ========== Message Handlers ==========

async def handle_subscribe(
    websocket: WebSocket,
    client_id: str,
    data: Dict[str, Any],
    sub_manager: IndicatorSubscriptionManager,
    computer: IndicatorComputer,
    cache: IndicatorCache
):
    """Handle subscribe action."""
    try:
        # Validate message
        msg = SubscribeMessage(**data)

        # Parse indicators
        indicator_ids = []
        for ind in msg.indicators:
            try:
                ind_id = IndicatorSpec.create_id(ind["name"], ind["params"])
                indicator_ids.append(ind_id)
            except Exception as e:
                error = ErrorMessage(
                    message=f"Invalid indicator spec: {ind}",
                    error_code="INVALID_INDICATOR"
                )
                await manager.send_to_client(websocket, error.dict())
                return

        # Subscribe in Redis
        result = await sub_manager.subscribe(
            client_id, msg.symbol, msg.timeframe, indicator_ids
        )

        # Track in connection manager
        for ind_id in indicator_ids:
            manager.add_subscription(client_id, msg.symbol, msg.timeframe, ind_id)

        # Trigger initial computation and send current values
        initial_values = {}
        for ind_id in indicator_ids:
            # Check cache first
            cached = await cache.get_latest(msg.symbol, msg.timeframe, ind_id)

            if cached:
                initial_values[ind_id] = cached["value"]

                # Send initial update
                update = IndicatorUpdate(
                    symbol=msg.symbol,
                    timeframe=msg.timeframe,
                    indicator_id=ind_id,
                    value=cached["value"],
                    timestamp=cached["timestamp"],
                    candle_time=cached.get("candle_time")
                )
                await manager.send_to_client(websocket, update.dict())

            else:
                # Compute and cache
                try:
                    spec = IndicatorSpec.parse(ind_id)
                    series = await computer.compute_indicator(
                        msg.symbol, msg.timeframe, spec, lookback=100
                    )

                    if series is not None and len(series) > 0:
                        # Get latest value
                        if hasattr(series, 'iloc'):
                            latest_value = float(series.iloc[-1])
                        else:
                            latest_value = series

                        timestamp = datetime.now(timezone.utc)

                        # Cache it
                        await cache.set_latest(
                            msg.symbol, msg.timeframe, ind_id,
                            latest_value, timestamp
                        )

                        initial_values[ind_id] = latest_value

                        # Send initial update
                        update = IndicatorUpdate(
                            symbol=msg.symbol,
                            timeframe=msg.timeframe,
                            indicator_id=ind_id,
                            value=latest_value,
                            timestamp=timestamp.isoformat()
                        )
                        await manager.send_to_client(websocket, update.dict())

                except Exception as e:
                    logger.error(f"Failed to compute {ind_id}: {e}")

        # Send success confirmation
        success = SuccessMessage(
            message=f"Subscribed to {len(indicator_ids)} indicators",
            data={
                "subscriptions": indicator_ids,
                "initial_values": initial_values
            }
        )
        await manager.send_to_client(websocket, success.dict())

        logger.info(
            f"Client {client_id} subscribed to {indicator_ids} "
            f"({msg.symbol} {msg.timeframe})"
        )

    except Exception as e:
        logger.error(f"Subscribe error: {e}")
        error = ErrorMessage(
            message=f"Subscribe failed: {str(e)}",
            error_code="SUBSCRIBE_ERROR"
        )
        await manager.send_to_client(websocket, error.dict())


async def handle_unsubscribe(
    websocket: WebSocket,
    client_id: str,
    data: Dict[str, Any],
    sub_manager: IndicatorSubscriptionManager
):
    """Handle unsubscribe action."""
    try:
        # Validate message
        msg = UnsubscribeMessage(**data)

        # Unsubscribe in Redis
        result = await sub_manager.unsubscribe(
            client_id, msg.symbol, msg.timeframe, msg.indicators
        )

        # Remove from connection manager
        for ind_id in msg.indicators:
            manager.remove_subscription(client_id, msg.symbol, msg.timeframe, ind_id)

        # Send confirmation
        success = SuccessMessage(
            message=f"Unsubscribed from {len(msg.indicators)} indicators",
            data={"unsubscribed": msg.indicators}
        )
        await manager.send_to_client(websocket, success.dict())

        logger.info(
            f"Client {client_id} unsubscribed from {msg.indicators} "
            f"({msg.symbol} {msg.timeframe})"
        )

    except Exception as e:
        logger.error(f"Unsubscribe error: {e}")
        error = ErrorMessage(
            message=f"Unsubscribe failed: {str(e)}",
            error_code="UNSUBSCRIBE_ERROR"
        )
        await manager.send_to_client(websocket, error.dict())


async def cleanup_client(
    client_id: str,
    sub_manager: IndicatorSubscriptionManager,
    redis_client: redis.Redis,
    dm: DataManager
):
    """Cleanup client subscriptions on disconnect."""
    try:
        # Get all subscriptions for this client
        subscriptions = manager.get_subscriptions(client_id)

        # Group by (symbol, timeframe)
        by_symbol_tf = {}
        for symbol, timeframe, indicator_id in subscriptions:
            key = (symbol, timeframe)
            if key not in by_symbol_tf:
                by_symbol_tf[key] = []
            by_symbol_tf[key].append(indicator_id)

        # Unsubscribe from all
        for (symbol, timeframe), indicator_ids in by_symbol_tf.items():
            try:
                await sub_manager.unsubscribe(client_id, symbol, timeframe, indicator_ids)
                logger.info(f"Cleaned up {len(indicator_ids)} subscriptions for {client_id}")
            except Exception as e:
                logger.error(f"Cleanup error for {client_id}: {e}")

    except Exception as e:
        logger.error(f"Failed to cleanup client {client_id}: {e}")

    finally:
        # Close connections
        try:
            await redis_client.close()
        except:
            pass


# ========== Background Task: Stream Updates ==========

async def stream_indicator_updates_task(
    redis_client: redis.Redis,
    dm: DataManager
):
    """
    Background task to compute and stream indicator updates.

    This task runs continuously and:
    1. Monitors Redis for active indicator subscriptions
    2. Computes new values when candles update
    3. Broadcasts updates to subscribed WebSocket clients

    NOTE: This should be started as a background task in main.py
    """
    sub_manager = IndicatorSubscriptionManager(redis_client)
    computer = IndicatorComputer(dm)
    cache = IndicatorCache(redis_client)

    logger.info("Indicator streaming task started")

    while True:
        try:
            # Get all active symbol/timeframe combinations
            # For now, we'll focus on NIFTY50 with common timeframes
            # In production, this should scan Redis for active subscriptions

            symbols_timeframes = [
                ("NIFTY50", "1"),
                ("NIFTY50", "5"),
                ("NIFTY50", "15"),
                ("NIFTY50", "60"),
            ]

            for symbol, timeframe in symbols_timeframes:
                # Get active indicators for this symbol/timeframe
                indicator_ids = await sub_manager.get_active_indicators(symbol, timeframe)

                if not indicator_ids:
                    continue  # No active subscriptions

                # Parse specs
                specs = []
                for ind_id in indicator_ids:
                    try:
                        spec = IndicatorSpec.parse(ind_id)
                        specs.append(spec)
                    except Exception as e:
                        logger.error(f"Failed to parse {ind_id}: {e}")

                if not specs:
                    continue

                # Batch compute indicators
                try:
                    results = await computer.compute_batch(symbol, timeframe, specs)
                    timestamp = datetime.now(timezone.utc)

                    for ind_id, series in results.items():
                        if series is None or len(series) == 0:
                            continue

                        # Extract latest value
                        try:
                            if hasattr(series, 'iloc'):
                                latest_value = float(series.iloc[-1])
                            else:
                                latest_value = series

                            # Cache it
                            await cache.set_latest(
                                symbol, timeframe, ind_id,
                                latest_value, timestamp
                            )

                            # Update metadata
                            await sub_manager.update_last_computed(
                                symbol, timeframe, ind_id, timestamp
                            )

                            # Broadcast to WebSocket clients
                            await manager.broadcast_indicator_update(
                                symbol, timeframe, ind_id,
                                latest_value, timestamp
                            )

                        except Exception as e:
                            logger.error(f"Failed to process {ind_id}: {e}")

                except Exception as e:
                    logger.error(f"Batch compute failed for {symbol} {timeframe}: {e}")

            # Sleep based on shortest timeframe (1min = 60s)
            await asyncio.sleep(60)

        except Exception as e:
            logger.error(f"Streaming task error: {e}")
            await asyncio.sleep(10)  # Brief pause on error


# ========== Export ==========

__all__ = [
    "router",
    "manager",
    "stream_indicator_updates_task"
]
