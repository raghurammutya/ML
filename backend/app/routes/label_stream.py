# app/routes/label_stream.py
import json
import logging
import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Dict, Any

from ..realtime import RealTimeHub

router = APIRouter()
logger = logging.getLogger(__name__)

# Global labels hub - will be set by main.py
labels_hub: RealTimeHub = None

def set_realtime_hub(hub: RealTimeHub):
    global labels_hub
    labels_hub = hub

@router.websocket("/labels/stream")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time label updates"""
    await websocket.accept()
    logger.info("Label WebSocket client connected")
    
    # Client state
    subscriptions: Dict[str, Any] = {}
    client_queue = asyncio.Queue()
    
    # Subscribe to labels hub
    if labels_hub:
        await labels_hub.subscribe(client_queue)
        logger.info("Client subscribed to labels hub")
    else:
        logger.warning("Labels hub not available")
    
    async def send_heartbeat():
        """Send periodic heartbeat to keep connection alive"""
        while True:
            try:
                await asyncio.sleep(30)  # Send heartbeat every 30 seconds
                await websocket.send_json({
                    "type": "heartbeat",
                    "timestamp": asyncio.get_event_loop().time()
                })
            except Exception as e:
                logger.error(f"Heartbeat failed: {e}")
                break
    
    async def handle_messages():
        """Handle incoming messages from client"""
        while True:
            try:
                data = await websocket.receive_text()
                message = json.loads(data)
                
                if message.get("action") == "subscribe":
                    # Store subscription info
                    channel = message.get("channel")
                    symbol = message.get("symbol")
                    timeframe = message.get("timeframe")
                    
                    if channel == "labels" and symbol and timeframe:
                        subscription_key = f"{symbol}:{timeframe}"
                        subscriptions[subscription_key] = {
                            "symbol": symbol,
                            "timeframe": timeframe
                        }
                        logger.info(f"Client subscribed to labels: {subscription_key}")
                        
                        # Send confirmation
                        await websocket.send_json({
                            "type": "subscription_confirmed",
                            "channel": "labels",
                            "symbol": symbol,
                            "timeframe": timeframe
                        })
                elif message.get("action") == "unsubscribe":
                    # Remove subscription
                    symbol = message.get("symbol")
                    timeframe = message.get("timeframe")
                    if symbol and timeframe:
                        subscription_key = f"{symbol}:{timeframe}"
                        subscriptions.pop(subscription_key, None)
                        logger.info(f"Client unsubscribed from labels: {subscription_key}")
                elif message.get("type") == "ping":
                    # Respond to ping
                    await websocket.send_json({
                        "type": "pong",
                        "timestamp": asyncio.get_event_loop().time()
                    })
                    
            except WebSocketDisconnect:
                break
            except json.JSONDecodeError:
                logger.warning("Received invalid JSON from client")
            except Exception as e:
                logger.error(f"Error handling client message: {e}")
                break
    
    async def broadcast_messages():
        """Forward messages from hub to client based on subscriptions"""
        while True:
            try:
                # Get message from hub
                message = await client_queue.get()
                
                # Check if message is relevant to client's subscriptions
                if message.get("type", "").startswith("label."):
                    payload = message.get("payload", {})
                    message_symbol = payload.get("symbol")
                    message_metadata = payload.get("metadata", {})
                    message_timeframe = message_metadata.get("timeframe")
                    
                    # Check if client is subscribed to this symbol/timeframe
                    should_send = False
                    if message_symbol and message_timeframe:
                        subscription_key = f"{message_symbol}:{message_timeframe}"
                        if subscription_key in subscriptions:
                            should_send = True
                    
                    # If no specific subscription filters, send all label messages
                    if not subscriptions:
                        should_send = True
                    
                    if should_send:
                        await websocket.send_json(message)
                        logger.debug(f"Sent label message to client: {message.get('type')}")
                
            except Exception as e:
                logger.error(f"Error broadcasting message: {e}")
                break
    
    # Start concurrent tasks
    heartbeat_task = asyncio.create_task(send_heartbeat())
    handle_task = asyncio.create_task(handle_messages())
    broadcast_task = asyncio.create_task(broadcast_messages())
    
    try:
        # Wait for any task to complete (usually means disconnection)
        done, pending = await asyncio.wait(
            [heartbeat_task, handle_task, broadcast_task],
            return_when=asyncio.FIRST_COMPLETED
        )
        
        # Cancel remaining tasks
        for task in pending:
            task.cancel()
            
    except WebSocketDisconnect:
        logger.info("Label WebSocket client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        # Cleanup
        if labels_hub and client_queue:
            await labels_hub.unsubscribe(client_queue)
        
        # Cancel any remaining tasks
        for task in [heartbeat_task, handle_task, broadcast_task]:
            if not task.done():
                task.cancel()
        
        logger.info("Label WebSocket connection closed")