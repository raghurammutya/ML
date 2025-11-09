"""
F&O WebSocket endpoints for real-time data streaming.
"""
import time
import json
import logging
import asyncio
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState
from websockets.exceptions import ConnectionClosed, ConnectionClosedOK

from ...config import get_settings
from ...database import _normalize_symbol
from ...realtime import RealTimeHub

router = APIRouter()
settings = get_settings()
logger = logging.getLogger(__name__)

# Global hub reference - will be set by main.py via set_realtime_hub()
_hub: Optional[RealTimeHub] = None


def set_realtime_hub(hub: RealTimeHub) -> None:
    """
    Set the global RealTimeHub instance.

    This function should be called from main.py during application startup
    to inject the hub dependency into this module.

    Args:
        hub: RealTimeHub instance
    """
    global _hub
    _hub = hub


def _classify_moneyness_bucket(strike: float, underlying: float, gap: int = 50) -> str:
    """
    Classify strike into moneyness bucket.

    Args:
        strike: Strike price
        underlying: Current underlying price
        gap: Strike gap (default 50 for NIFTY)

    Returns:
        Bucket label: "ATM", "OTM1", "OTM2", "ITM1", "ITM2", etc.
    """
    offset = strike - underlying
    level = int(round(offset / gap))

    if level == 0:
        return "ATM"
    elif level > 0:
        return f"OTM{min(abs(level), 10)}"
    else:
        return f"ITM{min(abs(level), 10)}"


@router.websocket("/stream-aggregated")
async def fo_stream_aggregated(websocket: WebSocket) -> None:
    """
    WebSocket endpoint for aggregated FO analytics stream.

    Emits all FO analytics in one stream with expiry labels so the
    TradingDashboard stays lightweight.

    All updates include:
    - expiry_relative_label (e.g., "NWeek+1", "NMonth+0")
    - relative_rank (1, 2, 3... for weeklies; 0 for monthly)

    Connection URL:
    ```
    ws://localhost:8081/fo/stream-aggregated?symbol=NIFTY
    ```

    Query Parameters:
        symbol: Underlying symbol (default: from settings)

    Message Format:
    ```json
    {
        "type": "fo_bucket",
        "symbol": "NIFTY",
        "expiry": "2024-11-07",
        "expiry_relative_label": "NWeek+1",
        "relative_rank": 1,
        "bucket_time": "2024-11-05T10:30:00Z",
        "underlying_close": 24500.0,
        "strikes": [
            {
                "strike": 24500,
                "moneyness_bucket": "ATM",
                "call": {...},
                "put": {...}
            }
        ]
    }
    ```
    """
    if _hub is None:
        await websocket.close(code=1013)
        logger.warning("FO stream-aggregated rejected: hub not initialized")
        return

    await websocket.accept()

    # Parse query params
    query_params = dict(websocket.query_params)
    symbol = query_params.get("symbol", settings.monitor_default_symbol)
    symbol_norm = _normalize_symbol(symbol)

    # Get DataManager instance from app state (global variable in main.py)
    from app.main import data_manager as dm

    # Get initial expiry label map
    label_map = await dm.get_expiry_label_map(symbol_norm)

    queue = await _hub.subscribe()
    logger.info(f"FO stream-aggregated connection accepted for {symbol_norm}")

    try:
        last_sent = time.time()
        idle_timeout = 60
        heartbeat_interval = 30
        last_ping = time.time()
        label_refresh_interval = 300  # Refresh labels every 5 minutes
        last_label_refresh = time.time()

        while True:
            # Refresh label map periodically
            if time.time() - last_label_refresh >= label_refresh_interval:
                try:
                    label_map = await dm.get_expiry_label_map(symbol_norm)
                    last_label_refresh = time.time()
                    logger.debug(f"Refreshed expiry label map for {symbol_norm}")
                except Exception as e:
                    logger.warning(f"Failed to refresh label map: {e}")

            # Wait for message from the hub queue
            try:
                message = await asyncio.wait_for(queue.get(), timeout=5.0)
            except asyncio.TimeoutError:
                message = None

            # Process and enhance message with expiry labels
            if message and websocket.client_state == WebSocketState.CONNECTED:
                message_type = message.get("type")

                # Only process FO bucket messages
                if message_type == "fo_bucket":
                    msg_symbol = message.get("symbol", "").upper()

                    # Filter by requested symbol
                    if msg_symbol == symbol_norm.upper():
                        # Enhance message with expiry labels
                        expiry_str = message.get("expiry")
                        if expiry_str:
                            try:
                                expiry_date = datetime.fromisoformat(expiry_str).date()
                                expiry_label, relative_rank = label_map.get(expiry_date, ("Unknown", 999))

                                # Add labels to message
                                message["expiry_relative_label"] = expiry_label
                                message["relative_rank"] = relative_rank

                                # Enhance each strike with moneyness bucket
                                underlying = message.get("underlying_close")
                                if underlying and "strikes" in message:
                                    for strike_data in message["strikes"]:
                                        strike = strike_data.get("strike")
                                        if strike:
                                            bucket = _classify_moneyness_bucket(
                                                strike,
                                                underlying,
                                                settings.fo_strike_gap
                                            )
                                            strike_data["moneyness_bucket"] = bucket

                            except (ValueError, AttributeError) as e:
                                logger.warning(f"Failed to parse expiry {expiry_str}: {e}")

                        # Send enhanced message
                        try:
                            await websocket.send_json(message)
                            last_sent = time.time()
                        except (ConnectionClosed, ConnectionClosedOK):
                            logger.info("WebSocket closed during send")
                            break
                        except Exception as exc:
                            logger.error("WebSocket send error: %s", exc)
                            break

            # Heartbeat ping
            if time.time() - last_ping >= heartbeat_interval:
                try:
                    await websocket.send_json({"type": "ping", "timestamp": datetime.now(timezone.utc).isoformat()})
                    last_ping = time.time()
                except ConnectionClosed:
                    logger.info("FO stream-aggregated closed during ping")
                    break

            # Idle timeout
            if time.time() - last_sent > idle_timeout:
                logger.info("FO stream-aggregated idle timeout — closing")
                await websocket.close(code=1000)
                break

    except Exception as exc:
        logger.error("FO stream-aggregated error: %s", exc, exc_info=True)
    finally:
        await _hub.unsubscribe(queue)
        logger.info(f"FO stream-aggregated connection closed for {symbol_norm}")


@router.websocket("/stream")
async def fo_stream_socket(websocket: WebSocket) -> None:
    """
    WebSocket endpoint for F&O real-time data streaming.

    Supports popup subscriptions for individual strike monitoring.

    Connection URL:
    ```
    ws://localhost:8081/fo/stream
    ```

    Client Messages:
    ```json
    {
        "action": "subscribe_popup",
        "underlying": "NIFTY",
        "strike": 24500,
        "expiry": "2024-11-07",
        "timeframe": "1m",
        "option_side": "call"
    }
    ```

    Server Messages:
    ```json
    {
        "type": "popup_update",
        "seq": 1,
        "timestamp": "2024-11-05T10:30:00Z",
        "candle": {
            "o": 150.0,
            "h": 155.0,
            "l": 148.0,
            "c": 152.0,
            "v": 1000
        },
        "metrics": {
            "iv": 0.18,
            "delta": 0.45,
            "gamma": 0.002,
            "theta": -0.05,
            "vega": 0.15,
            "premium": 152.0,
            "oi": 50000,
            "oi_delta": 1000
        },
        "option_side": "call"
    }
    ```
    """
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
                option_side = message.get("option_side", "call")

                if option_side not in {"call", "put", "both"}:
                    option_side = "call"

                # Create subscription key
                sub_key = f"{underlying}:{strike}:{expiry}:{timeframe}:{option_side}"
                popup_subscriptions[sub_key] = {
                    "underlying": underlying,
                    "strike": strike,
                    "expiry": expiry,
                    "timeframe": timeframe,
                    "option_side": option_side,
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
                                    side_key = sub_info.get("option_side", "call")
                                    primary_key = "call" if side_key == "call" else "put"
                                    secondary_key = "put" if primary_key == "call" else "call"

                                    primary = strike_data.get(primary_key, {}) or {}
                                    secondary = strike_data.get(secondary_key, {}) or {}

                                    price_raw = primary.get("ltp") or primary.get("close") or secondary.get("ltp")
                                    price_candidate = float(price_raw) if price_raw is not None else 0.0
                                    volume_candidate = int(primary.get("volume", 0) or 0)
                                    oi_candidate = int(primary.get("oi", 0) or 0)
                                    oi_delta_candidate = int(primary.get("oi_change", 0) or 0)

                                    popup_update = {
                                        "type": "popup_update",
                                        "seq": sub_info["seq"],
                                        "timestamp": message.get("bucket_time", datetime.now(timezone.utc).isoformat()),
                                        "candle": {
                                            "o": price_candidate or 0,
                                            "h": price_candidate or 0,
                                            "l": price_candidate or 0,
                                            "c": price_candidate or 0,
                                            "v": volume_candidate,
                                        },
                                        "metrics": {
                                            "iv": float(primary.get("iv") or secondary.get("iv") or 0),
                                            "delta": float(primary.get("delta") or secondary.get("delta") or 0),
                                            "gamma": float(primary.get("gamma") or secondary.get("gamma") or 0),
                                            "theta": float(primary.get("theta") or secondary.get("theta") or 0),
                                            "vega": float(primary.get("vega") or secondary.get("vega") or 0),
                                            "premium": price_candidate or 0,
                                            "oi": oi_candidate,
                                            "oi_delta": oi_delta_candidate,
                                        },
                                        "option_side": side_key,
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
