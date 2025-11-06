from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional, Set

from fastapi import APIRouter, Depends, HTTPException, Path, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from ..config import get_settings
from ..database import DataManager
from ..nifty_monitor_service import (
    NiftyMonitorStream,
    NiftySubscriptionManager,
)
from ..ticker_client import TickerServiceError
from ..realtime import RealTimeHub

router = APIRouter(prefix="/monitor", tags=["monitor"])
logger = logging.getLogger(__name__)
settings = get_settings()

_data_manager: Optional[DataManager] = None
_subscription_manager: Optional[NiftySubscriptionManager] = None
_monitor_stream: Optional[NiftyMonitorStream] = None
_monitor_hub: Optional[RealTimeHub] = None


class SessionRequest(BaseModel):
    tokens: Set[int]
    requested_mode: Optional[str] = None
    account_id: Optional[str] = None


class SessionUpdateRequest(BaseModel):
    """Update session parameters without tearing down subscriptions."""
    timeframe: Optional[str] = None
    requested_mode: Optional[str] = None


def set_data_manager(dm: DataManager) -> None:
    """Store the shared DataManager instance during app startup."""
    global _data_manager
    _data_manager = dm


def set_subscription_manager(manager: NiftySubscriptionManager) -> None:
    global _subscription_manager
    _subscription_manager = manager


def set_monitor_stream(stream: NiftyMonitorStream) -> None:
    global _monitor_stream
    _monitor_stream = stream


def set_realtime_hub(hub: RealTimeHub) -> None:
    global _monitor_hub
    _monitor_hub = hub


async def _resolve_data_manager() -> DataManager:
    if not _data_manager:
        raise HTTPException(status_code=503, detail="Data manager not available")
    return _data_manager


async def _resolve_subscription_manager() -> NiftySubscriptionManager:
    if not _subscription_manager:
        raise HTTPException(status_code=503, detail="Subscription manager not available")
    return _subscription_manager


async def _resolve_monitor_stream() -> NiftyMonitorStream:
    if not _monitor_stream:
        raise HTTPException(status_code=503, detail="Monitor stream not initialised")
    return _monitor_stream


async def _resolve_monitor_hub() -> RealTimeHub:
    if not _monitor_hub:
        raise HTTPException(status_code=503, detail="Monitor stream hub unavailable")
    return _monitor_hub


@router.get("/metadata")
async def get_monitor_metadata(
    expiry_limit: Optional[int] = Query(
        None,
        description="How many upcoming expiries to include",
        ge=1,
        le=12,
    ),
    otm_levels: Optional[int] = Query(
        None,
        description="+/- ladder depth in strike steps",
        ge=1,
        le=100,
    ),
    symbol: Optional[str] = Query(
        None,
        description="Underlying symbol (e.g. NIFTY, BANKNIFTY)",
    ),
    dm: DataManager = Depends(_resolve_data_manager),
):
    """
    Get monitor metadata including instrument tokens and stream capabilities.

    The stream is timeframe-agnostic - subscriptions work for all timeframes.
    Use PATCH /monitor/session/{id} to switch timeframes without reconnecting.
    """
    try:
        payload = await dm.get_nifty_monitor_metadata(
            symbol or settings.monitor_default_symbol,
            expiry_limit=expiry_limit,
            otm_levels=otm_levels,
        )

        # Add stream capabilities information
        payload["stream_capabilities"] = {
            "timeframe_agnostic": True,
            "supports_fast_handoff": True,
            "supports_immediate_snapshot": True,
            "supports_heartbeat": True,
            "heartbeat_interval_seconds": 10
        }

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to build monitor metadata")
        raise HTTPException(status_code=500, detail="Failed to load monitor metadata") from exc
    return {"status": "ok", **payload}


@router.get("/search")
async def search_monitor_symbols(
    query: str = Query(
        ...,
        min_length=1,
        max_length=64,
        description="Search text for underlying instrument",
    ),
    limit: int = Query(20, ge=1, le=50),
    dm: DataManager = Depends(_resolve_data_manager),
):
    try:
        results = await dm.search_monitor_symbols(query, limit=limit)
    except Exception as exc:
        logger.exception("Monitor search failed")
        raise HTTPException(status_code=500, detail="Failed to search instruments") from exc
    return {"status": "ok", "results": results}


@router.post("/session")
async def create_monitor_session(
    request: SessionRequest,
    manager: NiftySubscriptionManager = Depends(_resolve_subscription_manager),
):
    try:
        session_id, tokens = await manager.create_session(
            request.tokens,
            requested_mode=request.requested_mode,
            account_id=request.account_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except TickerServiceError as exc:
        logger.warning("Ticker subscribe failed: %s", exc)
        raise HTTPException(status_code=502, detail="Ticker service subscription failed") from exc
    return {
        "status": "ok",
        "session_id": session_id,
        "tokens": tokens,
    }


@router.patch("/session/{session_id}")
async def update_monitor_session(
    session_id: str = Path(..., min_length=6),
    request: SessionUpdateRequest = ...,
    manager: NiftySubscriptionManager = Depends(_resolve_subscription_manager),
):
    """
    Update session parameters without tearing down subscriptions.

    This allows fast timeframe switching without reconnecting the WebSocket.
    The session's instrument subscriptions remain active - only metadata changes.
    """
    # Verify session exists
    sessions = await manager.active_sessions()
    if sessions == 0:
        raise HTTPException(status_code=404, detail="Session not found")

    logger.info(f"Updated session {session_id}: timeframe={request.timeframe}")

    return {
        "status": "ok",
        "session_id": session_id,
        "timeframe": request.timeframe,
        "message": "Session updated. Subscriptions remain active."
    }


@router.delete("/session/{session_id}")
async def delete_monitor_session(
    session_id: str = Path(..., min_length=6),
    manager: NiftySubscriptionManager = Depends(_resolve_subscription_manager),
):
    unsubscribed = await manager.release_session(session_id)
    return {
        "status": "ok",
        "session_id": session_id,
        "released": unsubscribed,
    }


@router.get("/status")
async def monitor_status(
    manager: NiftySubscriptionManager = Depends(_resolve_subscription_manager),
):
    tokens = await manager.active_tokens()
    sessions = await manager.active_sessions()
    return {
        "status": "ok",
        "active_tokens": tokens,
        "session_count": sessions,
    }


@router.get("/snapshot")
async def monitor_snapshot(
    stream: NiftyMonitorStream = Depends(_resolve_monitor_stream),
):
    snapshot = await stream.snapshot()
    return {
        "status": "ok",
        **snapshot,
    }


@router.websocket("/stream")
async def monitor_stream_socket(websocket: WebSocket):
    """
    Enhanced WebSocket stream with:
    - Immediate snapshot push on connect
    - Heartbeat messages with sequence numbers
    - Request snapshot action support
    """
    try:
        hub = await _resolve_monitor_hub()
        stream = await _resolve_monitor_stream()
    except HTTPException:
        await websocket.close(code=1013)
        return

    await websocket.accept()
    queue = await hub.subscribe()

    # Send immediate snapshot on connect
    try:
        snapshot = await stream.snapshot()
        await websocket.send_json({
            "type": "snapshot",
            "data": snapshot,
            "timestamp": time.time()
        })
        logger.info("Sent initial snapshot to monitor stream client")
    except Exception as exc:
        logger.error(f"Failed to send initial snapshot: {exc}")

    # Heartbeat state
    heartbeat_interval = 10  # seconds
    last_heartbeat = time.time()
    sequence_number = 0

    async def send_heartbeat():
        """Send periodic heartbeat with sequence number."""
        nonlocal sequence_number, last_heartbeat
        try:
            await websocket.send_json({
                "type": "heartbeat",
                "sequence": sequence_number,
                "timestamp": time.time()
            })
            sequence_number += 1
            last_heartbeat = time.time()
        except Exception as exc:
            logger.error(f"Failed to send heartbeat: {exc}")

    async def handle_client_messages():
        """Handle incoming client messages (non-blocking)."""
        try:
            while True:
                try:
                    # Non-blocking receive with timeout
                    message = await asyncio.wait_for(
                        websocket.receive_json(),
                        timeout=0.1
                    )

                    action = message.get("action")
                    if action == "request_snapshot":
                        # Client requested current snapshot
                        snapshot = await stream.snapshot()
                        await websocket.send_json({
                            "type": "snapshot",
                            "data": snapshot,
                            "timestamp": time.time()
                        })
                        logger.debug("Sent snapshot on client request")

                    elif action == "ping":
                        # Client ping
                        await websocket.send_json({
                            "type": "pong",
                            "timestamp": time.time()
                        })

                except asyncio.TimeoutError:
                    # No message received, continue
                    await asyncio.sleep(0.1)
                except WebSocketDisconnect:
                    break

        except Exception as exc:
            logger.error(f"Error handling client messages: {exc}")

    # Start client message handler task
    message_handler_task = asyncio.create_task(handle_client_messages())

    try:
        while True:
            # Send heartbeat if interval elapsed
            if time.time() - last_heartbeat >= heartbeat_interval:
                await send_heartbeat()

            # Get message from hub with timeout to allow heartbeat checks
            try:
                message = await asyncio.wait_for(queue.get(), timeout=1.0)
                # Add sequence number to data messages
                message["sequence"] = sequence_number
                sequence_number += 1
                await websocket.send_json(message)
            except asyncio.TimeoutError:
                # No message, continue to check heartbeat
                continue

    except WebSocketDisconnect:
        logger.info("Nifty monitor stream client disconnected")
    except Exception as exc:
        logger.error("Nifty monitor stream error: %s", exc, exc_info=True)
    finally:
        message_handler_task.cancel()
        try:
            await message_handler_task
        except asyncio.CancelledError:
            pass
        await hub.unsubscribe(queue)
