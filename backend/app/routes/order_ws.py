"""
WebSocket Routes for Real-time Order Updates
Frontend clients connect here to receive order updates.
"""

import logging
from typing import Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
import asyncio

from ..realtime import RealTimeHub


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ws", tags=["websocket"])

# Global hub will be set by main.py
_order_hub: Optional[RealTimeHub] = None


def set_order_hub(hub: RealTimeHub):
    """Set the RealTimeHub instance for order updates."""
    global _order_hub
    _order_hub = hub
    logger.info("Order hub set for WebSocket routes")


@router.websocket("/orders/{account_id}")
async def order_updates_websocket(
    websocket: WebSocket,
    account_id: str
):
    """
    WebSocket endpoint for real-time order updates.

    Frontend clients connect here to receive order updates for a specific account.

    Args:
        websocket: WebSocket connection
        account_id: Account identifier (e.g., "primary")

    Message Format (from backend to frontend):
    {
        "type": "order_update",
        "account_id": "primary",
        "data": {
            "order_id": "230405000123456",
            "status": "COMPLETE",
            "filled_quantity": 50,
            "average_price": 19500.25,
            ...
        },
        "timestamp": "2025-10-31T09:15:30.123Z"
    }
    """
    if not _order_hub:
        logger.error("Order hub not initialized")
        await websocket.close(code=1011, reason="Service not ready")
        return

    await websocket.accept()
    logger.info(f"WebSocket connection established for account: {account_id}")

    # Subscribe to account-specific channel
    channel = f"account:{account_id}:orders"
    client_id = f"ws-{id(websocket)}"

    try:
        # Register client with hub
        await _order_hub.connect(client_id, websocket)
        await _order_hub.subscribe(client_id, channel)

        # Send connection confirmation
        await websocket.send_json({
            "type": "connection_established",
            "account_id": account_id,
            "message": "Connected to real-time order updates"
        })

        # Keep connection alive and handle incoming messages
        while True:
            try:
                # Receive messages from frontend (e.g., ping, subscribe commands)
                data = await websocket.receive_text()

                # Handle ping
                if data == "ping":
                    await websocket.send_text("pong")
                    continue

                # Handle subscribe to additional channels
                if data.startswith("subscribe:"):
                    new_channel = data.split(":", 1)[1]
                    await _order_hub.subscribe(client_id, new_channel)
                    logger.info(f"Client {client_id} subscribed to {new_channel}")
                    continue

                # Handle unsubscribe
                if data.startswith("unsubscribe:"):
                    old_channel = data.split(":", 1)[1]
                    await _order_hub.unsubscribe(client_id, old_channel)
                    logger.info(f"Client {client_id} unsubscribed from {old_channel}")
                    continue

            except asyncio.TimeoutError:
                # No message received, continue
                continue

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for account: {account_id}")

    except Exception as e:
        logger.error(f"WebSocket error for account {account_id}: {e}", exc_info=True)

    finally:
        # Cleanup: Remove client from hub
        await _order_hub.disconnect(client_id)
        logger.info(f"WebSocket connection closed for account: {account_id}")


@router.websocket("/orders")
async def all_orders_websocket(websocket: WebSocket):
    """
    WebSocket endpoint for all order updates (across all accounts).

    This is useful for admin dashboards or multi-account monitoring.

    Message Format: Same as /orders/{account_id}
    """
    if not _order_hub:
        logger.error("Order hub not initialized")
        await websocket.close(code=1011, reason="Service not ready")
        return

    await websocket.accept()
    logger.info("WebSocket connection established for all orders")

    # Subscribe to general orders channel
    channel = "orders"
    client_id = f"ws-all-{id(websocket)}"

    try:
        # Register client with hub
        await _order_hub.connect(client_id, websocket)
        await _order_hub.subscribe(client_id, channel)

        # Send connection confirmation
        await websocket.send_json({
            "type": "connection_established",
            "message": "Connected to all order updates"
        })

        # Keep connection alive
        while True:
            try:
                data = await websocket.receive_text()

                # Handle ping
                if data == "ping":
                    await websocket.send_text("pong")

            except asyncio.TimeoutError:
                continue

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected for all orders")

    except Exception as e:
        logger.error(f"WebSocket error for all orders: {e}", exc_info=True)

    finally:
        # Cleanup
        await _order_hub.disconnect(client_id)
        logger.info("WebSocket connection closed for all orders")


@router.get("/status")
async def websocket_status():
    """
    Get WebSocket connection status.

    Returns:
        Status information about active WebSocket connections
    """
    if not _order_hub:
        return {"status": "not_initialized", "clients": 0}

    return {
        "status": "active",
        "total_clients": len(_order_hub._clients),
        "channels": list(_order_hub._subscriptions.keys()) if hasattr(_order_hub, "_subscriptions") else []
    }
