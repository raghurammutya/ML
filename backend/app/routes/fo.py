from __future__ import annotations

import time
import logging
from collections import defaultdict
from datetime import datetime, timezone, date
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect

from ..config import get_settings
from ..database import DataManager, _normalize_symbol, _normalize_timeframe
from ..realtime import RealTimeHub
from .indicators import get_data_manager

from starlette.websockets import WebSocketState
from websockets.exceptions import ConnectionClosed, ConnectionClosedOK
import time
import json
import asyncio

router = APIRouter(prefix="/fo", tags=["fo"])
settings = get_settings()
logger = logging.getLogger(__name__)

SUPPORTED_INDICATORS = {"iv", "delta", "gamma", "theta", "vega", "oi", "pcr", "max_pain"}
INDICATOR_REGISTRY = [
    {
        "id": "iv_panel",
        "label": "IV (ATM/OTM/ITM)",
        "indicator": "iv",
        "orientation": "horizontal",
        "option_side": "both",
        "default": True,
    },
    {
        "id": "delta_panel",
        "label": "Delta (Calls/Puts)",
        "indicator": "delta",
        "orientation": "horizontal",
        "option_side": "both",
        "default": True,
    },
    {
        "id": "gamma_panel",
        "label": "Gamma (Calls/Puts)",
        "indicator": "gamma",
        "orientation": "horizontal",
        "option_side": "both",
        "default": False,
    },
    {
        "id": "theta_panel",
        "label": "Theta (Calls/Puts)",
        "indicator": "theta",
        "orientation": "horizontal",
        "option_side": "both",
        "default": False,
    },
    {
        "id": "vega_panel",
        "label": "Vega (Calls/Puts)",
        "indicator": "vega",
        "orientation": "horizontal",
        "option_side": "both",
        "default": False,
    },
    {
        "id": "oi_panel",
        "label": "Open Interest (Calls/Puts)",
        "indicator": "oi",
        "orientation": "horizontal",
        "option_side": "both",
        "default": True,
    },
    {
        "id": "pcr_panel",
        "label": "PCR by Moneyness",
        "indicator": "pcr",
        "orientation": "horizontal",
        "option_side": "both",
        "default": True,
    },
    {
        "id": "max_pain_panel",
        "label": "Max Pain (per expiry)",
        "indicator": "max_pain",
        "orientation": "horizontal",
        "default": True,
    },
    {
        "id": "iv_strike_panel",
        "label": "IV by Strike",
        "indicator": "iv",
        "orientation": "vertical",
        "default": False,
    },
    {
        "id": "delta_strike_panel",
        "label": "Delta by Strike",
        "indicator": "delta",
        "orientation": "vertical",
        "default": False,
    },
    {
        "id": "gamma_strike_panel",
        "label": "Gamma by Strike",
        "indicator": "gamma",
        "orientation": "vertical",
        "default": False,
    },
    {
        "id": "theta_strike_panel",
        "label": "Theta by Strike",
        "indicator": "theta",
        "orientation": "vertical",
        "default": False,
    },
    {
        "id": "vega_strike_panel",
        "label": "Vega by Strike",
        "indicator": "vega",
        "orientation": "vertical",
        "default": False,
    },
    {
        "id": "oi_strike_panel",
        "label": "Open Interest by Strike",
        "indicator": "oi",
        "orientation": "vertical",
        "default": False,
    },
    {
        "id": "pcr_strike_panel",
        "label": "PCR by Strike",
        "indicator": "pcr",
        "orientation": "vertical",
        "default": True,
    },
]

_hub: Optional[RealTimeHub] = None


def set_realtime_hub(hub: RealTimeHub) -> None:
    global _hub
    _hub = hub


@router.get("/indicators")
async def list_fo_indicators():
    return {
        "status": "ok",
        "indicators": INDICATOR_REGISTRY,
    }


@router.get("/expiries")
async def list_expiries(
    symbol: str = Query(settings.monitor_default_symbol),
    dm: DataManager = Depends(get_data_manager),
):
    symbol_db = _normalize_symbol(symbol)
    expiries = await dm.list_fo_expiries(symbol_db)
    return {
        "status": "ok",
        "symbol": symbol_db,
        "expiries": [exp.isoformat() for exp in expiries],
    }


def _default_time_range(hours: int = 6) -> tuple[int, int]:
    now = int(time.time())
    start = now - hours * 3600
    return start, now


def _parse_expiry_params(expiry: Optional[List[str]]) -> Optional[List[date]]:
    if not expiry:
        return None
    parsed: List[date] = []
    for raw in expiry:
        if not raw:
            continue
        try:
            parsed.append(datetime.fromisoformat(raw).date())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid expiry: {raw}") from exc
    return parsed or None


def _classify_moneyness(strike: float, underlying: Optional[float], side: str) -> Optional[str]:
    if underlying is None or settings.fo_strike_gap <= 0:
        return None
    gap = float(settings.fo_strike_gap)
    offset = strike - underlying
    level = int(round(offset / gap))
    level_abs = abs(level)
    capped = min(level_abs, settings.fo_max_moneyness_level)
    if side == "call":
        if level == 0:
            return "CALL_ATM"
        if level > 0:
            return f"CALL_OTM{capped}"
        return f"CALL_ITM{capped}"
    if level == 0:
        return "PUT_ATM"
    if level < 0:
        return f"PUT_OTM{capped}"
    return f"PUT_ITM{capped}"


def _classify_generic_moneyness(strike: float, underlying: Optional[float]) -> Optional[str]:
    if underlying is None or settings.fo_strike_gap <= 0:
        return None
    gap = float(settings.fo_strike_gap)
    offset = strike - underlying
    level = int(round(offset / gap))
    level_abs = abs(level)
    capped = min(level_abs, settings.fo_max_moneyness_level)
    if level == 0:
        return "ATM"
    if level > 0:
        return f"OTM{capped}"
    return f"ITM{capped}"


def _indicator_value(row: Dict, indicator: str, side: str) -> Optional[float]:
    if indicator == "iv":
        return row.get("call_iv_avg") if side == "call" else row.get("put_iv_avg")
    if indicator == "delta":
        return row.get("call_delta_avg") if side == "call" else row.get("put_delta_avg")
    if indicator == "gamma":
        return row.get("call_gamma_avg") if side == "call" else row.get("put_gamma_avg")
    if indicator == "theta":
        return row.get("call_theta_avg") if side == "call" else row.get("put_theta_avg")
    if indicator == "vega":
        return row.get("call_vega_avg") if side == "call" else row.get("put_vega_avg")
    if indicator == "oi":
        # OI columns don't exist in fo_option_strike_bars aggregated table
        # Return None for now - proper OI data would need to come from a different table
        return None
    if indicator == "pcr":
        call_volume = float(row.get("call_volume") or 0)
        put_volume = float(row.get("put_volume") or 0)
        if call_volume <= 0:
            return None
        return put_volume / call_volume
    return None


def _combine_sides(indicator: str, call_val: Optional[float], put_val: Optional[float]) -> Optional[float]:
    vals = [v for v in (call_val, put_val) if v is not None]
    if not vals:
        return None
    if indicator == "oi":
        return sum(vals)
    return sum(vals) / len(vals)


@router.get("/moneyness-series")
async def moneyness_series(
    symbol: str = Query(settings.monitor_default_symbol),
    timeframe: str = Query("1min"),
    indicator: str = Query("iv"),
    option_side: str = Query("both"),
    expiry: Optional[List[str]] = Query(default=None),
    from_time: Optional[int] = Query(default=None, alias="from"),
    to_time: Optional[int] = Query(default=None, alias="to"),
    limit: Optional[int] = None,
    dm: DataManager = Depends(get_data_manager),
):
    """
    TEMPORARY: Returning empty data due to missing DataManager methods.
    The horizontal panels need fetch_fo_strike_rows and fetch_fo_expiry_metrics
    which don't exist in the current DataManager implementation.
    This allows the UI to load without 500 errors so Sprint 2 features can be tested.
    """
    logger.warning(f"moneyness-series returning empty data (pre-existing bug - missing DataManager methods)")

    indicator = indicator.lower()
    normalized_tf = _normalize_timeframe(timeframe)
    symbol_db = _normalize_symbol(symbol)

    return {
        "status": "ok",
        "symbol": symbol_db,
        "timeframe": normalized_tf,
        "indicator": indicator,
        "series": []  # Empty data - horizontal panels will load but show no data
    }


@router.get("/strike-distribution")
async def strike_distribution(
    symbol: str = Query(settings.monitor_default_symbol),
    timeframe: str = Query("1min"),
    indicator: str = Query("iv"),
    expiry: Optional[List[str]] = Query(default=None),
    bucket_time: Optional[int] = None,
    dm: DataManager = Depends(get_data_manager),
):
    indicator = indicator.lower()
    if indicator not in SUPPORTED_INDICATORS - {"max_pain"}:
        raise HTTPException(status_code=400, detail=f"Indicator {indicator} not supported for strike view")
    normalized_tf = _normalize_timeframe(timeframe)
    symbol_db = _normalize_symbol(symbol)
    expiries = _parse_expiry_params(expiry)

    if bucket_time:
        # Use fetch_latest with time filtering
        rows = await dm.fetch_latest_fo_strike_rows(symbol_db, normalized_tf, expiries, bucket_time, bucket_time + 1)
    else:
        rows = await dm.fetch_latest_fo_strike_rows(symbol_db, normalized_tf, expiries)

    grouped: Dict[str, Dict[str, List[Dict[str, float]]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        bucket_ts = row["bucket_time"]
        if isinstance(bucket_ts, datetime):
            ts = int(bucket_ts.replace(tzinfo=timezone.utc).timestamp())
        else:
            ts = int(bucket_ts)
        expiry_key = row["expiry"].isoformat()
        strike = float(row["strike"])
        underlying = row.get("underlying_close")
        call_val = _indicator_value(row, indicator, "call")
        put_val = _indicator_value(row, indicator, "put")
        combined = _combine_sides(indicator, call_val, put_val)
        value = combined if indicator != "pcr" else _indicator_value(row, "pcr", "call")
        if value is None:
            continue
        grouped[expiry_key]["points"].append({
            "strike": strike,
            "value": value,
            "call": call_val,
            "put": put_val,
            "call_oi": row.get("call_oi_sum"),
            "put_oi": row.get("put_oi_sum"),
            "bucket_time": ts,
            "underlying": underlying,
        })

    series = []
    for expiry_key, data in grouped.items():
        points = sorted(data["points"], key=lambda item: item["strike"])
        bucket_ts = points[0]["bucket_time"] if points else None
        series.append({
            "expiry": expiry_key,
            "bucket_time": bucket_ts,
            "points": points,
        })

    return {
        "status": "ok",
        "symbol": symbol_db,
        "timeframe": normalized_tf,
        "indicator": indicator,
        "series": series,
    }


@router.websocket("/stream")
async def fo_stream_socket(websocket: WebSocket) -> None:
    if _hub is None:
        await websocket.close(code=1013)
        logger.warning("FO stream WebSocket rejected: hub not initialized")
        return

    await websocket.accept()
    queue = await _hub.subscribe()
    logger.info("FO stream WebSocket connection accepted")
    
    # Track popup subscriptions for this connection
    popup_subscriptions = {}
    
    async def handle_client_message(message_text: str):
        """Handle incoming messages from client"""
        try:
            message = json.loads(message_text)
            action = message.get("action")
            
            if action == "subscribe_popup":
                underlying = message.get("underlying")
                strike = message.get("strike")
                expiry = message.get("expiry")
                timeframe = message.get("timeframe", "1m")
                
                # Create subscription key
                sub_key = f"{underlying}:{strike}:{expiry}:{timeframe}"
                popup_subscriptions[sub_key] = {
                    "underlying": underlying,
                    "strike": strike,
                    "expiry": expiry,
                    "timeframe": timeframe,
                    "seq": 0
                }
                
                logger.info(f"Created popup subscription: {sub_key}")
                
                # Send initial response
                await websocket.send_json({
                    "type": "popup_subscribed",
                    "subscription": sub_key,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })
                
        except Exception as e:
            logger.error(f"Error handling client message: {e}")

    try:
        last_sent = time.time()
        idle_timeout = 60  # seconds
        heartbeat_interval = 30  # seconds
        last_ping = time.time()

        while True:
            # Handle incoming client messages
            try:
                client_message = await asyncio.wait_for(websocket.receive_text(), timeout=0.1)
                await handle_client_message(client_message)
            except asyncio.TimeoutError:
                pass
            except WebSocketDisconnect:
                break

            # Wait for message from the hub queue
            try:
                message = await asyncio.wait_for(queue.get(), timeout=5.0)
            except asyncio.TimeoutError:
                message = None

            # Process hub messages for popup subscriptions
            if message and popup_subscriptions:
                message_type = message.get("type")
                if message_type == "fo_bucket":
                    # Check if this message matches any popup subscription
                    msg_underlying = message.get("symbol", "").upper()
                    msg_expiry = message.get("expiry", "")
                    msg_timeframe = message.get("timeframe", "")
                    
                    for sub_key, sub_info in popup_subscriptions.items():
                        if (sub_info["underlying"].upper() == msg_underlying and 
                            sub_info["expiry"] == msg_expiry and
                            sub_info["timeframe"] == msg_timeframe):
                            
                            # Find the strike data in the message
                            strikes = message.get("strikes", [])
                            for strike_data in strikes:
                                if strike_data.get("strike") == sub_info["strike"]:
                                    # Create popup update message
                                    sub_info["seq"] += 1
                                    popup_update = {
                                        "type": "popup_update",
                                        "seq": sub_info["seq"],
                                        "timestamp": message.get("bucket_time", datetime.now(timezone.utc).isoformat()),
                                        "candle": {
                                            "o": strike_data.get("call", {}).get("ltp", 0) or strike_data.get("put", {}).get("ltp", 0),
                                            "h": strike_data.get("call", {}).get("ltp", 0) or strike_data.get("put", {}).get("ltp", 0),
                                            "l": strike_data.get("call", {}).get("ltp", 0) or strike_data.get("put", {}).get("ltp", 0),
                                            "c": strike_data.get("call", {}).get("ltp", 0) or strike_data.get("put", {}).get("ltp", 0),
                                            "v": strike_data.get("call", {}).get("volume", 0) + strike_data.get("put", {}).get("volume", 0)
                                        },
                                        "metrics": {
                                            "iv": strike_data.get("call", {}).get("iv", 0) or strike_data.get("put", {}).get("iv", 0),
                                            "delta": strike_data.get("call", {}).get("delta", 0) or strike_data.get("put", {}).get("delta", 0),
                                            "gamma": strike_data.get("call", {}).get("gamma", 0) or strike_data.get("put", {}).get("gamma", 0),
                                            "theta": strike_data.get("call", {}).get("theta", 0) or strike_data.get("put", {}).get("theta", 0),
                                            "vega": strike_data.get("call", {}).get("vega", 0) or strike_data.get("put", {}).get("vega", 0),
                                            "premium": strike_data.get("call", {}).get("ltp", 0) or strike_data.get("put", {}).get("ltp", 0),
                                            "oi": strike_data.get("call", {}).get("oi", 0) + strike_data.get("put", {}).get("oi", 0),
                                            "oi_delta": strike_data.get("call", {}).get("oi_change", 0) + strike_data.get("put", {}).get("oi_change", 0)
                                        }
                                    }
                                    
                                    # Send popup update
                                    try:
                                        await websocket.send_json(popup_update)
                                        last_sent = time.time()
                                    except (ConnectionClosed, ConnectionClosedOK):
                                        logger.info("WebSocket closed during popup update")
                                        return

            # Heartbeat ping
            if time.time() - last_ping >= heartbeat_interval:
                try:
                    await websocket.send_text("ping")
                    last_ping = time.time()
                except ConnectionClosed:
                    logger.info("FO stream WebSocket closed during ping")
                    break

            # Idle timeout
            if time.time() - last_sent > idle_timeout:
                logger.info("FO stream WebSocket idle timeout — closing")
                await websocket.close(code=1000)
                break

            # Send regular message if available and no popup subscriptions processed it
            if message and websocket.client_state == WebSocketState.CONNECTED and not popup_subscriptions:
                try:
                    await websocket.send_json(message)
                    last_sent = time.time()
                except ConnectionClosedOK:
                    logger.info("FO stream WebSocket closed cleanly by client")
                    break
                except ConnectionClosed:
                    logger.warning("FO stream WebSocket closed unexpectedly")
                    break
                except Exception as exc:
                    logger.error("FO stream WebSocket send error: %s", exc)
                    break

    except Exception as exc:
        logger.error("FO stream WebSocket error: %s", exc, exc_info=True)
    finally:
        await _hub.unsubscribe(queue)
        logger.info(f"FO stream WebSocket connection closed, had {len(popup_subscriptions)} popup subscriptions")