"""
WebSocket endpoints for real-time tick data streaming.

Provides authenticated WebSocket connections for users to subscribe to
instrument tick data. All users share the same data stream (broadcast model).
"""

import asyncio
import json
from typing import Set, Dict, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from loguru import logger

from .jwt_auth import verify_ws_token, JWTAuthError
from .redis_client import redis_publisher

router = APIRouter()

# Active WebSocket connections
# Structure: {connection_id: {"websocket": WebSocket, "user_id": str, "subscriptions": Set[int]}}
active_connections: Dict[str, dict] = {}

# Track which tokens are actively subscribed by any client
# Structure: {instrument_token: set of connection_ids}
token_subscribers: Dict[int, Set[str]] = {}

# Redis Pub/Sub task
redis_listener_task: Optional[asyncio.Task] = None


class ConnectionManager:
    """Manages WebSocket connections and subscriptions"""

    def __init__(self):
        self.active_connections = active_connections
        self.token_subscribers = token_subscribers

    async def connect(self, connection_id: str, websocket: WebSocket, user_id: str):
        """Register a new WebSocket connection"""
        await websocket.accept()
        self.active_connections[connection_id] = {
            "websocket": websocket,
            "user_id": user_id,
            "subscriptions": set(),
            "connected_at": datetime.now(timezone.utc)
        }
        logger.info(f"WebSocket connected: connection_id={connection_id}, user_id={user_id}")

    def disconnect(self, connection_id: str):
        """Remove a WebSocket connection and clean up subscriptions"""
        if connection_id in self.active_connections:
            conn_data = self.active_connections[connection_id]

            # Remove from token subscribers
            for token in conn_data["subscriptions"]:
                if token in self.token_subscribers:
                    self.token_subscribers[token].discard(connection_id)
                    if not self.token_subscribers[token]:
                        del self.token_subscribers[token]

            del self.active_connections[connection_id]
            logger.info(f"WebSocket disconnected: connection_id={connection_id}")

    def subscribe(self, connection_id: str, tokens: list[int]) -> dict:
        """Subscribe a connection to instrument tokens"""
        if connection_id not in self.active_connections:
            return {"error": "Connection not found"}

        conn_data = self.active_connections[connection_id]
        newly_subscribed = []

        for token in tokens:
            if token not in conn_data["subscriptions"]:
                conn_data["subscriptions"].add(token)

                # Add to global token subscribers
                if token not in self.token_subscribers:
                    self.token_subscribers[token] = set()
                self.token_subscribers[token].add(connection_id)

                newly_subscribed.append(token)

        logger.info(
            f"Connection {connection_id} subscribed to {len(newly_subscribed)} tokens "
            f"(total: {len(conn_data['subscriptions'])})"
        )

        return {
            "status": "success",
            "subscribed": newly_subscribed,
            "total_subscriptions": len(conn_data["subscriptions"])
        }

    def unsubscribe(self, connection_id: str, tokens: list[int]) -> dict:
        """Unsubscribe a connection from instrument tokens"""
        if connection_id not in self.active_connections:
            return {"error": "Connection not found"}

        conn_data = self.active_connections[connection_id]
        unsubscribed = []

        for token in tokens:
            if token in conn_data["subscriptions"]:
                conn_data["subscriptions"].discard(token)

                # Remove from global token subscribers
                if token in self.token_subscribers:
                    self.token_subscribers[token].discard(connection_id)
                    if not self.token_subscribers[token]:
                        del self.token_subscribers[token]

                unsubscribed.append(token)

        logger.info(
            f"Connection {connection_id} unsubscribed from {len(unsubscribed)} tokens "
            f"(remaining: {len(conn_data['subscriptions'])})"
        )

        return {
            "status": "success",
            "unsubscribed": unsubscribed,
            "total_subscriptions": len(conn_data["subscriptions"])
        }

    async def broadcast_tick(self, instrument_token: int, tick_data: dict):
        """Broadcast tick data to all subscribed connections"""
        if instrument_token not in self.token_subscribers:
            return  # No subscribers for this token

        subscriber_ids = list(self.token_subscribers[instrument_token])
        disconnected = []

        for connection_id in subscriber_ids:
            if connection_id not in self.active_connections:
                disconnected.append(connection_id)
                continue

            conn_data = self.active_connections[connection_id]
            websocket = conn_data["websocket"]

            try:
                await websocket.send_json({
                    "type": "tick",
                    "data": tick_data
                })
            except Exception as e:
                logger.error(f"Error sending tick to {connection_id}: {e}")
                disconnected.append(connection_id)

        # Clean up disconnected clients
        for connection_id in disconnected:
            self.disconnect(connection_id)

    def get_stats(self) -> dict:
        """Get connection statistics"""
        total_connections = len(self.active_connections)
        total_unique_subscriptions = len(self.token_subscribers)

        # Calculate total subscriptions across all connections
        total_subscriptions = sum(
            len(conn["subscriptions"])
            for conn in self.active_connections.values()
        )

        return {
            "active_connections": total_connections,
            "total_subscriptions": total_subscriptions,
            "unique_tokens_subscribed": total_unique_subscriptions,
            "connections": [
                {
                    "connection_id": conn_id,
                    "user_id": conn_data["user_id"],
                    "subscriptions": len(conn_data["subscriptions"]),
                    "connected_at": conn_data["connected_at"].isoformat()
                }
                for conn_id, conn_data in self.active_connections.items()
            ]
        }


# Global connection manager instance
manager = ConnectionManager()


async def redis_tick_listener():
    """
    Background task that listens to Redis Pub/Sub for tick data
    and broadcasts to WebSocket clients.
    """
    import redis.asyncio as aioredis
    import os

    redis_client = None

    try:
        # Connect to Redis (use same URL as main redis_publisher)
        redis_url = os.getenv("REDIS_URL", "redis://127.0.0.1:6381/0")
        redis_client = aioredis.from_url(
            redis_url,
            decode_responses=True
        )
        logger.info(f"Redis tick listener connecting to {redis_url.split('@')[1] if '@' in redis_url else redis_url}")

        pubsub = redis_client.pubsub()

        # Subscribe to ticker channels
        # Pattern: ticker:* to catch all ticker channels (underlying, options, etc.)
        await pubsub.psubscribe("ticker:*")

        logger.info("Redis tick listener started, listening to ticker:* channels")

        async for message in pubsub.listen():
            if message["type"] == "pmessage":
                try:
                    channel = message["channel"]
                    data = message["data"]

                    # Parse tick data
                    if isinstance(data, str):
                        tick_data = json.loads(data)
                    else:
                        tick_data = data

                    # Extract instrument token from tick data
                    instrument_token = tick_data.get("instrument_token")

                    if instrument_token:
                        # Broadcast to subscribed WebSocket clients
                        await manager.broadcast_tick(instrument_token, tick_data)

                except Exception as e:
                    logger.error(f"Error processing tick from Redis: {e}", exc_info=True)

    except Exception as e:
        logger.error(f"Redis listener error: {e}", exc_info=True)

    finally:
        if redis_client:
            await redis_client.close()
        logger.info("Redis tick listener stopped")


async def start_websocket_services():
    """Start WebSocket-related background services"""
    global redis_listener_task
    redis_listener_task = asyncio.create_task(redis_tick_listener())
    logger.info("Started Redis tick listener task")


async def stop_websocket_services():
    """Stop WebSocket-related background services"""
    global redis_listener_task
    if redis_listener_task:
        redis_listener_task.cancel()
        try:
            await redis_listener_task
        except asyncio.CancelledError:
            pass
        logger.info("Stopped Redis tick listener task")


@router.websocket("/ws/ticks")
async def websocket_ticks(
    websocket: WebSocket,
    token: str = Query(..., description="JWT authentication token")
):
    """
    WebSocket endpoint for real-time tick data streaming.

    Authentication:
        - Requires valid JWT token from user_service as query parameter
        - Example: ws://localhost:8080/ws/ticks?token=eyJ0eXAiOiJKV1Q...

    Message Protocol:
        Client -> Server:
            {"action": "subscribe", "tokens": [256265, 260105]}
            {"action": "unsubscribe", "tokens": [256265]}
            {"action": "ping"}

        Server -> Client:
            {"type": "connected", "connection_id": "...", "user": {...}}
            {"type": "subscribed", "tokens": [...], "total": 10}
            {"type": "unsubscribed", "tokens": [...], "total": 5}
            {"type": "tick", "data": {...}}
            {"type": "error", "message": "..."}
            {"type": "pong"}

    Usage:
        All authenticated users can subscribe to any instrument tokens.
        Tick data is broadcast to all subscribers (shared data model).
    """
    connection_id = f"{id(websocket)}_{datetime.now(timezone.utc).timestamp()}"

    try:
        # Authenticate user with JWT
        try:
            user_payload = await verify_ws_token(token)
            user_id = user_payload.get("sub")

            if not user_id:
                await websocket.close(code=1008, reason="Invalid token payload")
                return

        except JWTAuthError as e:
            logger.warning(f"WebSocket authentication failed: {e.detail}")
            await websocket.close(code=1008, reason=f"Authentication failed: {e.detail}")
            return

        # Accept connection and register
        await manager.connect(connection_id, websocket, user_id)

        # Send connection confirmation
        await websocket.send_json({
            "type": "connected",
            "connection_id": connection_id,
            "user": {
                "user_id": user_id,
                "email": user_payload.get("email"),
                "name": user_payload.get("name")
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

        # Message handling loop
        while True:
            try:
                # Receive message from client
                message = await websocket.receive_json()
                action = message.get("action")

                if action == "subscribe":
                    tokens = message.get("tokens", [])
                    if not isinstance(tokens, list):
                        await websocket.send_json({
                            "type": "error",
                            "message": "tokens must be a list of instrument tokens"
                        })
                        continue

                    result = manager.subscribe(connection_id, tokens)
                    await websocket.send_json({
                        "type": "subscribed",
                        "tokens": result.get("subscribed", []),
                        "total": result.get("total_subscriptions", 0)
                    })

                elif action == "unsubscribe":
                    tokens = message.get("tokens", [])
                    if not isinstance(tokens, list):
                        await websocket.send_json({
                            "type": "error",
                            "message": "tokens must be a list of instrument tokens"
                        })
                        continue

                    result = manager.unsubscribe(connection_id, tokens)
                    await websocket.send_json({
                        "type": "unsubscribed",
                        "tokens": result.get("unsubscribed", []),
                        "total": result.get("total_subscriptions", 0)
                    })

                elif action == "ping":
                    await websocket.send_json({"type": "pong"})

                else:
                    await websocket.send_json({
                        "type": "error",
                        "message": f"Unknown action: {action}"
                    })

            except WebSocketDisconnect:
                break
            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": "error",
                    "message": "Invalid JSON message"
                })
            except Exception as e:
                logger.error(f"Error handling WebSocket message: {e}", exc_info=True)
                await websocket.send_json({
                    "type": "error",
                    "message": "Internal server error"
                })

    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)

    finally:
        # Clean up connection
        manager.disconnect(connection_id)


@router.get("/ws/stats")
async def websocket_stats():
    """
    Get WebSocket connection statistics.

    Returns information about active connections and subscriptions.
    """
    return manager.get_stats()
