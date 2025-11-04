# app/routes/indicator_ws_session.py
"""
Session-Isolated WebSocket Streaming for Technical Indicators

Provides real-time indicator updates via WebSocket with session-level isolation.
Each WebSocket connection (tab) receives only the indicators it subscribed to.
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Optional, Any
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, Request
from pydantic import BaseModel, ValidationError

from app.jwt_auth import verify_jwt_token_string, JWTAuthError
from app.services.session_subscription_manager import get_subscription_manager
from app.services.indicator_computer import IndicatorComputer, IndicatorSpec
from app.services.indicator_cache import IndicatorCache
from app.database import DataManager
import redis.asyncio as redis

logger = logging.getLogger("app.routes.indicator_ws_session")

router = APIRouter(prefix="/indicators/v2", tags=["indicators-ws-v2"])


# ========== WebSocket Message Models ==========

class SubscribeMessage(BaseModel):
    """Client -> Server: Subscribe to indicators."""
    action: str = "subscribe"
    symbol: str
    timeframe: str
    indicators: list  # List of dicts: {"name": "RSI", "params": {"length": 14}}


class UnsubscribeMessage(BaseModel):
    """Client -> Server: Unsubscribe from all indicators."""
    action: str = "unsubscribe"


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


# ========== Session Connection Manager ==========

class SessionConnectionManager:
    """
    Manage WebSocket connections with session-level tracking.

    Key difference from old implementation:
    - Maps ws_conn_id -> WebSocket (not client_id -> WebSocket)
    - Subscriptions tracked in SessionSubscriptionManager (not here)
    """

    def __init__(self):
        # ws_conn_id -> WebSocket object
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, ws_conn_id: str, websocket: WebSocket):
        """Register new WebSocket connection."""
        await websocket.accept()
        self.active_connections[ws_conn_id] = websocket
        logger.info(f"Session {ws_conn_id} connected via WebSocket")

    def disconnect(self, ws_conn_id: str):
        """Unregister WebSocket connection."""
        if ws_conn_id in self.active_connections:
            del self.active_connections[ws_conn_id]
            logger.info(f"Session {ws_conn_id} disconnected")

    async def send_to_session(self, ws_conn_id: str, message: Dict[str, Any]):
        """Send message to specific session."""
        websocket = self.active_connections.get(ws_conn_id)
        if websocket:
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.error(f"Failed to send to session {ws_conn_id}: {e}")

    async def broadcast_indicator_update(
        self,
        sub_manager,
        symbol: str,
        timeframe: str,
        indicator_id: str,
        value: Any,
        timestamp: datetime,
        candle_time: Optional[datetime] = None
    ):
        """
        Broadcast indicator update to subscribed sessions only.

        This is the key session isolation mechanism:
        - Query SessionSubscriptionManager for subscribers
        - Only send to those specific ws_conn_ids
        """
        # Get all sessions subscribed to this indicator
        subscribers = sub_manager.get_indicator_subscribers(symbol, timeframe, indicator_id)

        if not subscribers:
            return  # No one subscribed

        update = IndicatorUpdate(
            symbol=symbol,
            timeframe=timeframe,
            indicator_id=indicator_id,
            value=value,
            timestamp=timestamp.isoformat(),
            candle_time=candle_time.isoformat() if candle_time else None
        )

        # Send to each subscribed session
        for ws_conn_id in subscribers:
            await self.send_to_session(ws_conn_id, update.dict())

        logger.debug(
            f"Broadcast {indicator_id} to {len(subscribers)} sessions "
            f"(values: {value})"
        )


# Global connection manager
manager = SessionConnectionManager()


# ========== WebSocket Endpoint ==========

@router.websocket("/stream")
async def indicator_stream_v2(
    websocket: WebSocket,
    request: Request,
    token: Optional[str] = Query(None, description="JWT token for authentication")
):
    """
    WebSocket endpoint for real-time indicator updates with session isolation.

    **Authentication**: Pass JWT token as query parameter
    ```
    ws://localhost:8081/indicators/v2/stream?token=eyJhbGciOi...
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

    2. Unsubscribe from all indicators:
    ```json
    {
      "action": "unsubscribe"
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
      "timestamp": "2025-11-04T12:00:00Z"
    }
    ```

    2. Success confirmation:
    ```json
    {
      "type": "success",
      "message": "Subscribed to 2 indicators"
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
    # Authenticate via JWT token
    if not token:
        await websocket.close(code=1008, reason="Missing JWT token")
        return

    try:
        user_data = await verify_jwt_token_string(token)
        user_id = user_data["email"]
        session_id = user_data.get("session_id", "unknown")
    except JWTAuthError as e:
        await websocket.close(code=1008, reason=str(e))
        return

    # Generate unique WebSocket connection ID
    ws_conn_id = f"ws_{uuid.uuid4().hex[:12]}"

    # Get services from app state
    sub_manager = get_subscription_manager()
    redis_client = request.app.state.redis_client
    data_manager = request.app.state.data_manager

    computer = IndicatorComputer(data_manager)
    cache = IndicatorCache(redis_client)

    # Connect session
    await manager.connect(ws_conn_id, websocket)

    try:
        # Send welcome message
        welcome = SuccessMessage(
            message=f"Connected to indicator stream (session: {ws_conn_id})",
            data={
                "ws_conn_id": ws_conn_id,
                "user_id": user_id,
                "session_id": session_id,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        )
        await manager.send_to_session(ws_conn_id, welcome.dict())

        # Main message loop
        while True:
            try:
                # Receive message from client
                data = await websocket.receive_json()
                action = data.get("action")

                if action == "subscribe":
                    await handle_subscribe(
                        ws_conn_id, user_id, session_id, data,
                        sub_manager, computer, cache
                    )

                elif action == "unsubscribe":
                    await handle_unsubscribe(ws_conn_id, sub_manager)

                elif action == "ping":
                    # Heartbeat
                    await sub_manager.update_heartbeat(ws_conn_id)
                    pong = {"type": "pong", "timestamp": datetime.now(timezone.utc).isoformat()}
                    await manager.send_to_session(ws_conn_id, pong)

                else:
                    error = ErrorMessage(
                        message=f"Unknown action: {action}",
                        error_code="UNKNOWN_ACTION"
                    )
                    await manager.send_to_session(ws_conn_id, error.dict())

            except ValidationError as e:
                error = ErrorMessage(
                    message=f"Invalid message format: {str(e)}",
                    error_code="VALIDATION_ERROR"
                )
                await manager.send_to_session(ws_conn_id, error.dict())

            except json.JSONDecodeError:
                error = ErrorMessage(
                    message="Invalid JSON",
                    error_code="JSON_ERROR"
                )
                await manager.send_to_session(ws_conn_id, error.dict())

    except WebSocketDisconnect:
        logger.info(f"Session {ws_conn_id} disconnected")

    except Exception as e:
        logger.error(f"WebSocket error for session {ws_conn_id}: {e}")

    finally:
        # Cleanup on disconnect
        await cleanup_session(ws_conn_id, sub_manager)
        manager.disconnect(ws_conn_id)


# ========== Message Handlers ==========

async def handle_subscribe(
    ws_conn_id: str,
    user_id: str,
    session_id: str,
    data: Dict[str, Any],
    sub_manager,
    computer: IndicatorComputer,
    cache: IndicatorCache
):
    """Handle subscribe action."""
    try:
        # Validate message
        msg = SubscribeMessage(**data)

        # Convert indicator list to dict format
        indicators_dict = {}
        for ind in msg.indicators:
            try:
                ind_id = IndicatorSpec.create_id(ind["name"], ind["params"])
                indicators_dict[ind_id] = {
                    "name": ind["name"],
                    "params": ind["params"]
                }
            except Exception as e:
                error = ErrorMessage(
                    message=f"Invalid indicator spec: {ind}",
                    error_code="INVALID_INDICATOR"
                )
                await manager.send_to_session(ws_conn_id, error.dict())
                return

        # Subscribe in SessionSubscriptionManager
        result = await sub_manager.subscribe(
            ws_conn_id=ws_conn_id,
            user_id=user_id,
            session_id=session_id,
            symbol=msg.symbol,
            timeframe=msg.timeframe,
            indicators=indicators_dict
        )

        # Send initial values from cache or compute
        initial_values = {}
        for ind_id in indicators_dict.keys():
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
                await manager.send_to_session(ws_conn_id, update.dict())

        # Send success confirmation
        success = SuccessMessage(
            message=f"Subscribed to {len(indicators_dict)} indicators",
            data={
                "indicators": list(indicators_dict.keys()),
                "initial_values": initial_values
            }
        )
        await manager.send_to_session(ws_conn_id, success.dict())

        logger.info(
            f"Session {ws_conn_id} (user={user_id}) subscribed to "
            f"{list(indicators_dict.keys())} ({msg.symbol} {msg.timeframe})"
        )

    except Exception as e:
        logger.error(f"Subscribe error: {e}")
        error = ErrorMessage(
            message=f"Subscribe failed: {str(e)}",
            error_code="SUBSCRIBE_ERROR"
        )
        await manager.send_to_session(ws_conn_id, error.dict())


async def handle_unsubscribe(ws_conn_id: str, sub_manager):
    """Handle unsubscribe action."""
    try:
        # Unsubscribe from all indicators
        result = await sub_manager.unsubscribe(ws_conn_id)

        if result["status"] == "unsubscribed":
            # Send confirmation
            success = SuccessMessage(
                message=f"Unsubscribed from all indicators",
                data=result
            )
            await manager.send_to_session(ws_conn_id, success.dict())

            logger.info(f"Session {ws_conn_id} unsubscribed from all indicators")

    except Exception as e:
        logger.error(f"Unsubscribe error: {e}")
        error = ErrorMessage(
            message=f"Unsubscribe failed: {str(e)}",
            error_code="UNSUBSCRIBE_ERROR"
        )
        await manager.send_to_session(ws_conn_id, error.dict())


async def cleanup_session(ws_conn_id: str, sub_manager):
    """Cleanup session subscriptions on disconnect."""
    try:
        # Unsubscribe from all
        await sub_manager.unsubscribe(ws_conn_id)
        logger.info(f"Cleaned up subscriptions for session {ws_conn_id}")

    except Exception as e:
        logger.error(f"Failed to cleanup session {ws_conn_id}: {e}")


# ========== Background Task: Stream Updates ==========

async def stream_indicator_updates_task_v2(
    redis_client: redis.Redis,
    dm: DataManager
):
    """
    Background task to compute and stream indicator updates.

    This task runs continuously and:
    1. Monitors Redis for active indicator subscriptions
    2. Computes new values when candles update
    3. Broadcasts updates to subscribed WebSocket sessions

    NOTE: This should be started as a background task in main.py
    """
    sub_manager = get_subscription_manager()
    computer = IndicatorComputer(dm)
    cache = IndicatorCache(redis_client)

    logger.info("Indicator streaming task (v2 - session-isolated) started")

    while True:
        try:
            # Get all active subscriptions
            stats = sub_manager.get_subscription_stats()

            if stats["total_connections"] == 0:
                await asyncio.sleep(5)  # No active connections
                continue

            # Get unique symbol/timeframe combinations from active subscriptions
            # For now, focus on NIFTY50 with common timeframes
            symbols_timeframes = [
                ("NIFTY50", "1"),
                ("NIFTY50", "5"),
                ("NIFTY50", "15"),
                ("NIFTY50", "60"),
            ]

            for symbol, timeframe in symbols_timeframes:
                # Get all subscriptions for this symbol/timeframe
                all_subscriptions = sub_manager.get_all_active_subscriptions()

                # Find unique indicators for this symbol/timeframe
                unique_indicators = set()
                for ws_conn_id, subscription in all_subscriptions.items():
                    if subscription["symbol"] == symbol and subscription["timeframe"] == timeframe:
                        unique_indicators.update(subscription["indicators"].keys())

                if not unique_indicators:
                    continue  # No subscriptions for this symbol/timeframe

                # Parse specs
                specs = []
                for ind_id in unique_indicators:
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

                            # Broadcast to subscribed sessions (session-filtered)
                            await manager.broadcast_indicator_update(
                                sub_manager,
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
    "stream_indicator_updates_task_v2"
]
