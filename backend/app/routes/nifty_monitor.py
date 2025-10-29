from __future__ import annotations

import logging
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
        le=30,
    ),
    symbol: Optional[str] = Query(
        None,
        description="Underlying symbol (e.g. NIFTY, BANKNIFTY)",
    ),
    dm: DataManager = Depends(_resolve_data_manager),
):
    try:
        payload = await dm.get_nifty_monitor_metadata(
            symbol or settings.monitor_default_symbol,
            expiry_limit=expiry_limit,
            otm_levels=otm_levels,
        )
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
    try:
        hub = await _resolve_monitor_hub()
    except HTTPException:
        await websocket.close(code=1013)
        return

    await websocket.accept()
    queue = await hub.subscribe()
    try:
        while True:
            message = await queue.get()
            await websocket.send_json(message)
    except WebSocketDisconnect:
        logger.info("Nifty monitor stream client disconnected")
    except Exception as exc:
        logger.error("Nifty monitor stream error: %s", exc, exc_info=True)
    finally:
        await hub.unsubscribe(queue)
