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
        return row["call_iv_avg"] if side == "call" else row["put_iv_avg"]
    if indicator == "delta":
        return row["call_delta_avg"] if side == "call" else row["put_delta_avg"]
    if indicator == "gamma":
        return row["call_gamma_avg"] if side == "call" else row["put_gamma_avg"]
    if indicator == "theta":
        return row["call_theta_avg"] if side == "call" else row["put_theta_avg"]
    if indicator == "vega":
        return row["call_vega_avg"] if side == "call" else row["put_vega_avg"]
    if indicator == "oi":
        return row["call_oi_sum"] if side == "call" else row["put_oi_sum"]
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
    indicator = indicator.lower()
    if indicator not in SUPPORTED_INDICATORS:
        raise HTTPException(status_code=400, detail=f"Unsupported indicator {indicator}")
    normalized_tf = _normalize_timeframe(timeframe)
    symbol_db = _normalize_symbol(symbol)
    if not from_time or not to_time:
        from_time, to_time = _default_time_range()
    expiries = _parse_expiry_params(expiry)

    if indicator == "max_pain":
        rows = await dm.fetch_fo_expiry_metrics(symbol_db, normalized_tf, expiries, from_time, to_time)
        series = defaultdict(list)
        for row in rows:
            ts = int(row["bucket_time"].replace(tzinfo=timezone.utc).timestamp())
            series[row["expiry"].isoformat()].append({"time": ts, "value": row.get("max_pain_strike")})
        return {
            "status": "ok",
            "symbol": symbol_db,
            "timeframe": normalized_tf,
            "indicator": indicator,
            "series": [{"expiry": exp, "points": points} for exp, points in series.items()],
        }

    option_side = option_side.lower()
    if option_side not in {"call", "put", "both"}:
        raise HTTPException(status_code=400, detail="option_side must be call, put, or both")
    rows = await dm.fetch_fo_strike_rows(symbol_db, normalized_tf, expiries, from_time, to_time, limit)
    series: Dict[str, Dict[str, List[Dict[str, float]]]] = defaultdict(lambda: defaultdict(list))

    for row in rows:
        bucket_ts = row["bucket_time"]
        if isinstance(bucket_ts, datetime):
            ts = int(bucket_ts.replace(tzinfo=timezone.utc).timestamp())
        else:
            ts = int(bucket_ts)
        underlying = row.get("underlying_close")
        strike = float(row["strike"])
        expiry_key = row["expiry"].isoformat()

        if indicator == "pcr":
            bucket_label = _classify_generic_moneyness(strike, underlying)
            value = _indicator_value(row, indicator, "call")
            if bucket_label and value is not None:
                series[expiry_key][bucket_label].append({"time": ts, "value": value})
            continue

        sides = ["call", "put"] if option_side == "both" else [option_side]
        call_val = _indicator_value(row, indicator, "call")
        put_val = _indicator_value(row, indicator, "put")
        for side in sides:
            if option_side == "both":
                value = _combine_sides(indicator, call_val, put_val)
                label = _classify_generic_moneyness(strike, underlying)
                if label and value is not None:
                    series[expiry_key][label].append({"time": ts, "value": value})
                break
            value = _indicator_value(row, indicator, side)
            label = _classify_moneyness(strike, underlying, side)
            if label and value is not None:
                series[expiry_key][label].append({"time": ts, "value": value})

    payload = []
    for expiry_key, buckets in series.items():
        for bucket_label, points in buckets.items():
            payload.append({
                "expiry": expiry_key,
                "bucket": bucket_label,
                "points": points,
            })

    return {
        "status": "ok",
        "symbol": symbol_db,
        "timeframe": normalized_tf,
        "indicator": indicator,
        "series": payload,
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
        rows = await dm.fetch_fo_strike_rows(symbol_db, normalized_tf, expiries, bucket_time, bucket_time + 1)
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
async def fo_stream_socket(websocket: WebSocket):
    if not _hub:
        await websocket.close(code=1013)
        return
    await websocket.accept()
    queue = await _hub.subscribe()
    try:
        while True:
            message = await queue.get()
            await websocket.send_json(message)
    except WebSocketDisconnect:
        logger.info("FO stream client disconnected")
    except Exception as exc:
        logger.error("FO stream websocket error: %s", exc, exc_info=True)
    finally:
        await _hub.unsubscribe(queue)
