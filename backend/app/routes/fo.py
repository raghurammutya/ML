from __future__ import annotations

import time
import logging
from collections import defaultdict
from datetime import datetime, timezone, date, timedelta
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect

from ..config import get_settings
from ..database import DataManager, _normalize_symbol, _normalize_timeframe, _fo_strike_table
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
SUPPORTED_SEGMENTS = {"NFO-OPT", "NFO-FUT", "CDS-OPT", "CDS-FUT", "MCX-OPT", "MCX-FUT"}
SUPPORTED_OPTION_TYPES = {"CE", "PE"}
SUPPORTED_INSTRUMENT_TYPES = {"CE", "PE", "FUT"}
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
        "default": True,
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


@router.get("/instruments/search")
async def search_instruments(
    symbol: Optional[str] = Query(None, description="Underlying symbol (e.g., NIFTY, BANKNIFTY)"),
    segment: Optional[str] = Query(None, description="Segment (NFO-OPT, NFO-FUT, CDS-OPT, etc.)"),
    expiry_from: Optional[str] = Query(None, description="Start expiry date (YYYY-MM-DD)"),
    expiry_to: Optional[str] = Query(None, description="End expiry date (YYYY-MM-DD)"),
    strike_min: Optional[float] = Query(None, description="Minimum strike price"),
    strike_max: Optional[float] = Query(None, description="Maximum strike price"),
    option_type: Optional[str] = Query(None, description="Option type (CE or PE)"),
    instrument_type: Optional[str] = Query(None, description="Instrument type (CE, PE, FUT)"),
    exchange: Optional[str] = Query(None, description="Exchange (NFO, CDS, MCX)"),
    limit: int = Query(100, le=1000, description="Maximum results (default 100, max 1000)"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    dm: DataManager = Depends(get_data_manager),
):
    """
    Search for tradable instruments with advanced filtering.

    Use this endpoint to discover option contracts and futures for algo trading.

    Examples:
    - Find ATM NIFTY options: ?symbol=NIFTY&strike_min=19400&strike_max=19600&expiry_from=2025-11-01
    - Find weekly BANKNIFTY PEs: ?symbol=BANKNIFTY&option_type=PE&expiry_to=2025-11-30
    - Find all NIFTY futures: ?symbol=NIFTY&instrument_type=FUT
    """
    # Build query conditions
    conditions = ["is_active = true"]
    params = []
    param_idx = 1

    if symbol:
        conditions.append(f"UPPER(name) = UPPER(${param_idx})")
        params.append(symbol)
        param_idx += 1

    if segment:
        if segment not in SUPPORTED_SEGMENTS:
            raise HTTPException(status_code=400, detail=f"Invalid segment. Supported: {SUPPORTED_SEGMENTS}")
        conditions.append(f"segment = ${param_idx}")
        params.append(segment)
        param_idx += 1

    if expiry_from:
        try:
            datetime.fromisoformat(expiry_from)
            conditions.append(f"expiry >= ${param_idx}")
            params.append(expiry_from)
            param_idx += 1
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid expiry_from format. Use YYYY-MM-DD")

    if expiry_to:
        try:
            datetime.fromisoformat(expiry_to)
            conditions.append(f"expiry <= ${param_idx}")
            params.append(expiry_to)
            param_idx += 1
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid expiry_to format. Use YYYY-MM-DD")

    if strike_min is not None:
        conditions.append(f"strike >= ${param_idx}")
        params.append(strike_min)
        param_idx += 1

    if strike_max is not None:
        conditions.append(f"strike <= ${param_idx}")
        params.append(strike_max)
        param_idx += 1

    if option_type:
        option_type_upper = option_type.upper()
        if option_type_upper not in SUPPORTED_OPTION_TYPES:
            raise HTTPException(status_code=400, detail=f"Invalid option_type. Supported: {SUPPORTED_OPTION_TYPES}")
        conditions.append(f"instrument_type = ${param_idx}")
        params.append(option_type_upper)
        param_idx += 1

    if instrument_type:
        instrument_type_upper = instrument_type.upper()
        if instrument_type_upper not in SUPPORTED_INSTRUMENT_TYPES:
            raise HTTPException(status_code=400, detail=f"Invalid instrument_type. Supported: {SUPPORTED_INSTRUMENT_TYPES}")
        conditions.append(f"instrument_type = ${param_idx}")
        params.append(instrument_type_upper)
        param_idx += 1

    if exchange:
        conditions.append(f"UPPER(exchange) = UPPER(${param_idx})")
        params.append(exchange)
        param_idx += 1

    # Build WHERE clause
    where_clause = " AND ".join(conditions) if conditions else "1=1"

    # Query database
    query = f"""
        SELECT
            instrument_token,
            tradingsymbol,
            name,
            segment,
            instrument_type,
            strike,
            expiry,
            tick_size,
            lot_size,
            exchange,
            last_refreshed_at
        FROM instrument_registry
        WHERE {where_clause}
        ORDER BY expiry, strike, instrument_type
        LIMIT ${param_idx} OFFSET ${param_idx + 1}
    """
    params.extend([limit, offset])

    try:
        async with dm.pool.acquire() as conn:
            rows = await conn.fetch(query, *params)

        instruments = []
        for row in rows:
            instruments.append({
                "instrument_token": row["instrument_token"],
                "tradingsymbol": row["tradingsymbol"],
                "name": row["name"],
                "segment": row["segment"],
                "instrument_type": row["instrument_type"],
                "strike": float(row["strike"]) if row["strike"] is not None else None,
                "expiry": row["expiry"],
                "tick_size": float(row["tick_size"]) if row["tick_size"] is not None else None,
                "lot_size": row["lot_size"],
                "exchange": row["exchange"],
                "last_refreshed_at": row["last_refreshed_at"].isoformat() if row["last_refreshed_at"] else None
            })

        return {
            "status": "success",
            "count": len(instruments),
            "limit": limit,
            "offset": offset,
            "instruments": instruments
        }

    except Exception as e:
        logger.error(f"Instrument search failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Database query failed: {str(e)}")


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
    """
    Extract indicator value from a database row.

    Args:
        row: Database row (asyncpg Record or dict)
        indicator: Indicator name (iv, delta, gamma, theta, vega, oi, pcr)
        side: Option side (call, put)

    Returns:
        Float value or None if not available

    Note:
        For OI (Open Interest) indicator:
        - Requires enriched views (fo_option_strike_bars_5min_enriched, fo_option_strike_bars_15min_enriched)
        - These views LEFT JOIN with base 1min table to fetch call_oi_sum/put_oi_sum columns
        - See migration 013_create_fo_enriched_views.sql
        - If enriched views are missing, OI will return None
    """
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
        # OI columns available in enriched views (migration 013)
        # Returns None if column doesn't exist (graceful degradation)
        try:
            return row.get("call_oi_sum") if side == "call" else row.get("put_oi_sum")
        except (KeyError, AttributeError):
            logger.warning(f"OI column not found in row - enriched views may be missing")
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
    Return time-series data grouped by moneyness buckets.
    Used by horizontal panels (IV, Delta, Gamma, Theta, Vega charts).
    """
    from collections import defaultdict

    # Normalize inputs
    normalized_tf = _normalize_timeframe(timeframe)
    symbol_db = _normalize_symbol(symbol)
    indicator = indicator.lower()

    # Parse expiries
    if expiry:
        expiry_dates = []
        for exp_str in expiry:
            try:
                expiry_dates.append(datetime.fromisoformat(exp_str).date())
            except ValueError:
                logger.warning(f"Invalid expiry format: {exp_str}")
                continue
    else:
        # Default: next 2 expiries
        expiry_dates = await dm.get_next_expiries(symbol_db, limit=2)

    if not expiry_dates:
        return {
            "status": "ok",
            "symbol": symbol_db,
            "timeframe": normalized_tf,
            "indicator": indicator,
            "series": []
        }

    # Time range (default: last 6 hours)
    if from_time and to_time:
        from_dt = datetime.fromtimestamp(from_time, tz=timezone.utc)
        to_dt = datetime.fromtimestamp(to_time, tz=timezone.utc)
    else:
        to_dt = datetime.now(timezone.utc)
        from_dt = to_dt - timedelta(hours=6)

    # Map indicator to column expression
    if option_side == "both":
        column_map = {
            "iv": "(COALESCE(call_iv_avg, 0) + COALESCE(put_iv_avg, 0)) / 2.0",
            "delta": "ABS(COALESCE(call_delta_avg, 0)) + ABS(COALESCE(put_delta_avg, 0))",
            "gamma": "(COALESCE(call_gamma_avg, 0) + COALESCE(put_gamma_avg, 0)) / 2.0",
            "theta": "(COALESCE(call_theta_avg, 0) + COALESCE(put_theta_avg, 0)) / 2.0",
            "vega": "(COALESCE(call_vega_avg, 0) + COALESCE(put_vega_avg, 0)) / 2.0",
            "oi": "COALESCE(call_oi_sum, 0) + COALESCE(put_oi_sum, 0)",
            "pcr": "CASE WHEN COALESCE(call_oi_sum, 0) > 0 THEN COALESCE(put_oi_sum, 0) / call_oi_sum ELSE NULL END",
        }
    elif option_side == "call":
        column_map = {
            "iv": "call_iv_avg",
            "delta": "call_delta_avg",
            "gamma": "call_gamma_avg",
            "theta": "call_theta_avg",
            "vega": "call_vega_avg",
            "oi": "call_oi_sum",
        }
    else:  # put
        column_map = {
            "iv": "put_iv_avg",
            "delta": "put_delta_avg",
            "gamma": "put_gamma_avg",
            "theta": "put_theta_avg",
            "vega": "put_vega_avg",
            "oi": "put_oi_sum",
        }

    value_expr = column_map.get(indicator)
    if not value_expr:
        raise HTTPException(status_code=400, detail=f"Invalid indicator: {indicator}")

    # Get correct table/view based on timeframe
    table_name = _fo_strike_table(timeframe)

    # Query database
    query = f"""
        SELECT
            bucket_time,
            expiry,
            strike,
            underlying_close,
            {value_expr} as value
        FROM {table_name}
        WHERE symbol = $1
          AND expiry = ANY($2)
          AND bucket_time BETWEEN $3 AND $4
          AND {value_expr} IS NOT NULL
        ORDER BY bucket_time, expiry, strike
    """

    async with dm.pool.acquire() as conn:
        rows = await conn.fetch(
            query,
            symbol_db,
            expiry_dates,
            from_dt,
            to_dt
        )

    logger.info(f"Moneyness query returned {len(rows)} rows for {symbol_db} timeframe={normalized_tf}")

    # Group by (expiry, bucket, time)
    # Store as {(expiry, bucket): {timestamp: value}}
    series_data = defaultdict(lambda: defaultdict(list))

    for row in rows:
        expiry_str = row['expiry'].isoformat()
        timestamp = int(row['bucket_time'].timestamp())
        strike = float(row['strike'])
        underlying = float(row['underlying_close']) if row['underlying_close'] else None
        value = float(row['value']) if row['value'] is not None else None

        if value is None or underlying is None:
            logger.debug(f"Skipping row: value={value}, underlying={underlying}")
            continue

        # Classify moneyness bucket
        bucket = _classify_moneyness_bucket(strike, underlying, settings.fo_strike_gap)

        # Store point - group by timestamp, average if multiple strikes in same bucket
        key = (expiry_str, bucket)
        series_data[key][timestamp].append(value)

    # Format response - average values at same timestamp
    series = []
    for (expiry_str, bucket), time_points in series_data.items():
        points = [
            {"time": ts, "value": round(sum(vals) / len(vals), 4)}
            for ts, vals in sorted(time_points.items())
        ]

        if points:
            series.append({
                "expiry": expiry_str,
                "bucket": bucket,
                "points": points
            })

    return {
        "status": "ok",
        "symbol": symbol_db,
        "timeframe": normalized_tf,
        "indicator": indicator,
        "series": series
    }


def _classify_moneyness_bucket(strike: float, underlying: float, gap: int = 50) -> str:
    """
    Classify strike into moneyness bucket.
    Returns: "ATM", "OTM1", "OTM2", "ITM1", "ITM2", etc.
    """
    offset = strike - underlying
    level = int(round(offset / gap))

    if level == 0:
        return "ATM"
    elif level > 0:
        return f"OTM{min(abs(level), 10)}"
    else:
        return f"ITM{min(abs(level), 10)}"


@router.get("/strike-distribution")
async def strike_distribution(
    symbol: str = Query(settings.monitor_default_symbol),
    timeframe: str = Query("5min"),  # Changed default from 1min to 5min for better data
    indicator: str = Query("iv"),
    expiry: Optional[List[str]] = Query(default=None),
    bucket_time: Optional[int] = None,
    strike_range: int = Query(50, description="ATM ± N strikes to return"),  # Increased to 50 for better coverage
    dm: DataManager = Depends(get_data_manager),
):
    """
    Return strike distribution for vertical panels.
    Frontend expects separate call/put arrays per expiry with complete Greek coverage.

    Returns format:
    {
      "series": [
        {
          "expiry": "2025-11-04",
          "call": [{"strike": 25000, "iv": 0.18, "delta": 0.45, ...}, ...],
          "put": [{"strike": 25000, "iv": 0.20, "delta": -0.55, ...}, ...]
        }
      ]
    }
    """
    indicator = indicator.lower()
    if indicator not in SUPPORTED_INDICATORS - {"max_pain"}:
        raise HTTPException(status_code=400, detail=f"Indicator {indicator} not supported for strike view")

    normalized_tf = _normalize_timeframe(timeframe)
    symbol_db = _normalize_symbol(symbol)
    expiries = _parse_expiry_params(expiry)

    if bucket_time:
        rows = await dm.fetch_latest_fo_strike_rows(symbol_db, normalized_tf, expiries, bucket_time, bucket_time + 1)
    else:
        rows = await dm.fetch_latest_fo_strike_rows(symbol_db, normalized_tf, expiries)

    logger.info(f"Strike distribution fetched {len(rows)} rows for {symbol_db} tf={normalized_tf} indicator={indicator}")
    if rows:
        sample_row = rows[0]
        logger.debug(f"Sample row keys: {list(sample_row.keys())}")
        logger.debug(f"Sample OI: call_oi_sum={sample_row.get('call_oi_sum')}, put_oi_sum={sample_row.get('put_oi_sum')}")

    # Get latest underlying price to determine ATM
    underlying_ltp = None
    for row in rows:
        if row.get("underlying_close"):
            underlying_ltp = float(row["underlying_close"])
            break

    # Calculate strike range if we have underlying price
    # Also verify the underlying price is reasonable (between 10000 and 50000 for NIFTY)
    if underlying_ltp and 10000 <= underlying_ltp <= 50000:
        gap = settings.fo_strike_gap  # 50 for NIFTY
        atm_strike = round(underlying_ltp / gap) * gap
        min_strike = atm_strike - (strike_range * gap)
        max_strike = atm_strike + (strike_range * gap)
        logger.info(f"Using strike range: {min_strike} to {max_strike} (ATM={atm_strike}, underlying={underlying_ltp})")
    else:
        # No filtering if we don't have underlying price or it's unreliable
        min_strike = None
        max_strike = None
        atm_strike = None
        if underlying_ltp:
            logger.warning(f"Unreliable underlying price {underlying_ltp}, returning all strikes")
        else:
            logger.info("No underlying price available, returning all strikes")

    # Group by expiry and strike, collecting latest data for each
    # Structure: {expiry: {strike: row_data}}
    expiry_strikes: Dict[str, Dict[float, Dict]] = defaultdict(dict)

    for row in rows:
        expiry_key = row["expiry"].isoformat()
        strike = float(row["strike"])

        # Filter by strike range (ATM ± N strikes)
        if min_strike is not None and max_strike is not None:
            if strike < min_strike or strike > max_strike:
                continue

        # Keep the latest data for each expiry-strike combo
        if strike not in expiry_strikes[expiry_key]:
            expiry_strikes[expiry_key][strike] = row
        else:
            # Compare bucket times, keep newer
            existing_ts = expiry_strikes[expiry_key][strike]["bucket_time"]
            new_ts = row["bucket_time"]
            if new_ts > existing_ts:
                expiry_strikes[expiry_key][strike] = row

    # Build series with separate call/put arrays
    series = []
    for expiry_key in sorted(expiry_strikes.keys()):
        strikes_data = expiry_strikes[expiry_key]

        if not strikes_data:
            continue

        call_strikes = []
        put_strikes = []
        bucket_ts = None

        for strike in sorted(strikes_data.keys()):
            row = strikes_data[strike]

            if bucket_ts is None:
                ts = row["bucket_time"]
                if isinstance(ts, datetime):
                    bucket_ts = int(ts.replace(tzinfo=timezone.utc).timestamp())
                else:
                    bucket_ts = int(ts)

            # Build call strike object with all Greeks
            call_obj = {"strike": strike}

            # Add all available Greeks (omit if 0 or None)
            if row.get("call_iv_avg"):
                call_obj["iv"] = round(float(row["call_iv_avg"]), 4)
            if row.get("call_delta_avg"):
                call_obj["delta"] = round(float(row["call_delta_avg"]), 4)
            if row.get("call_gamma_avg"):
                call_obj["gamma"] = round(float(row["call_gamma_avg"]), 6)
            if row.get("call_theta_avg"):
                call_obj["theta"] = round(float(row["call_theta_avg"]), 4)
            if row.get("call_vega_avg"):
                call_obj["vega"] = round(float(row["call_vega_avg"]), 4)
            if row.get("call_oi_sum"):
                call_obj["oi"] = int(float(row["call_oi_sum"]))

            # Build put strike object with all Greeks
            put_obj = {"strike": strike}

            if row.get("put_iv_avg"):
                put_obj["iv"] = round(float(row["put_iv_avg"]), 4)
            if row.get("put_delta_avg"):
                put_obj["delta"] = round(float(row["put_delta_avg"]), 4)
            if row.get("put_gamma_avg"):
                put_obj["gamma"] = round(float(row["put_gamma_avg"]), 6)
            if row.get("put_theta_avg"):
                put_obj["theta"] = round(float(row["put_theta_avg"]), 4)
            if row.get("put_vega_avg"):
                put_obj["vega"] = round(float(row["put_vega_avg"]), 4)
            if row.get("put_oi_sum"):
                put_obj["oi"] = int(float(row["put_oi_sum"]))

            call_strikes.append(call_obj)
            put_strikes.append(put_obj)

        # Determine data availability
        has_greeks = any(
            "iv" in s or "delta" in s or "gamma" in s
            for s in call_strikes + put_strikes
        )
        has_oi = any("oi" in s for s in call_strikes + put_strikes)

        series.append({
            "expiry": expiry_key,
            "bucket_time": bucket_ts,
            "call": call_strikes,
            "put": put_strikes,
            "metadata": {
                "strike_count": len(call_strikes),
                "has_greeks": has_greeks,
                "has_oi": has_oi,
                "atm_strike": atm_strike if underlying_ltp else None
            }
        })

    return {
        "status": "ok",
        "symbol": symbol_db,
        "timeframe": normalized_tf,
        "indicator": indicator,  # Kept for backwards compatibility
        "series": series,
        "metadata": {
            "total_expiries": len(series),
            "underlying_price": underlying_ltp,
            "strike_range": f"ATM ± {strike_range} strikes",
            "data_available": len(series) > 0
        }
    }


@router.get("/strike-history")
async def strike_history(
    symbol: str = Query(settings.monitor_default_symbol),
    strike: float = Query(..., description="Strike price"),
    expiry: str = Query(..., description="Expiry date (YYYY-MM-DD)"),
    timeframe: str = Query("5min"),
    from_time: Optional[int] = Query(default=None, alias="from", description="Start timestamp (Unix)"),
    to_time: Optional[int] = Query(default=None, alias="to", description="End timestamp (Unix)"),
    hours: int = Query(24, description="Hours of history (if from/to not provided)"),
    dm: DataManager = Depends(get_data_manager),
):
    """
    Return time-series data for a specific strike.
    Used by chart popups to show historical greeks and price action.

    Returns OHLCV data plus all greeks (IV, Delta, Gamma, Theta, Vega) and OI.
    """
    # Normalize inputs
    normalized_tf = _normalize_timeframe(timeframe)
    symbol_db = _normalize_symbol(symbol)

    # Parse expiry
    try:
        expiry_date = datetime.fromisoformat(expiry).date()
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid expiry format: {expiry}. Use YYYY-MM-DD")

    # Time range
    if from_time and to_time:
        from_dt = datetime.fromtimestamp(from_time, tz=timezone.utc)
        to_dt = datetime.fromtimestamp(to_time, tz=timezone.utc)
    else:
        to_dt = datetime.now(timezone.utc)
        from_dt = to_dt - timedelta(hours=hours)

    # Get correct table based on timeframe
    table_name = _fo_strike_table(timeframe)

    # Query database for this specific strike
    query = f"""
        SELECT
            bucket_time,
            strike,
            expiry,
            underlying_close,
            call_iv_avg,
            put_iv_avg,
            call_delta_avg,
            put_delta_avg,
            call_gamma_avg,
            put_gamma_avg,
            call_theta_avg,
            put_theta_avg,
            call_vega_avg,
            put_vega_avg,
            call_oi_sum,
            put_oi_sum,
            call_volume,
            put_volume
        FROM {table_name}
        WHERE symbol = $1
          AND strike = $2
          AND expiry = $3
          AND bucket_time BETWEEN $4 AND $5
        ORDER BY bucket_time ASC
    """

    async with dm.pool.acquire() as conn:
        rows = await conn.fetch(
            query,
            symbol_db,
            strike,
            expiry_date,
            from_dt,
            to_dt
        )

    logger.info(f"Strike history returned {len(rows)} rows for {symbol_db} strike={strike} expiry={expiry_date}")

    # Format response as OHLCV + greeks
    candles = []
    for row in rows:
        timestamp = int(row['bucket_time'].replace(tzinfo=timezone.utc).timestamp())

        candles.append({
            "time": timestamp,
            "underlying": float(row['underlying_close']) if row['underlying_close'] else None,
            "greeks": {
                "call_iv": float(row['call_iv_avg']) if row['call_iv_avg'] else None,
                "put_iv": float(row['put_iv_avg']) if row['put_iv_avg'] else None,
                "call_delta": float(row['call_delta_avg']) if row['call_delta_avg'] else None,
                "put_delta": float(row['put_delta_avg']) if row['put_delta_avg'] else None,
                "call_gamma": float(row['call_gamma_avg']) if row['call_gamma_avg'] else None,
                "put_gamma": float(row['put_gamma_avg']) if row['put_gamma_avg'] else None,
                "call_theta": float(row['call_theta_avg']) if row['call_theta_avg'] else None,
                "put_theta": float(row['put_theta_avg']) if row['put_theta_avg'] else None,
                "call_vega": float(row['call_vega_avg']) if row['call_vega_avg'] else None,
                "put_vega": float(row['put_vega_avg']) if row['put_vega_avg'] else None,
            },
            "oi": {
                "call": float(row['call_oi_sum']) if row['call_oi_sum'] else 0,
                "put": float(row['put_oi_sum']) if row['put_oi_sum'] else 0,
                "total": (float(row['call_oi_sum']) if row['call_oi_sum'] else 0) +
                        (float(row['put_oi_sum']) if row['put_oi_sum'] else 0),
            },
            "volume": {
                "call": float(row['call_volume']) if row['call_volume'] else 0,
                "put": float(row['put_volume']) if row['put_volume'] else 0,
                "total": (float(row['call_volume']) if row['call_volume'] else 0) +
                        (float(row['put_volume']) if row['put_volume'] else 0),
            }
        })

    return {
        "status": "ok",
        "symbol": symbol_db,
        "strike": strike,
        "expiry": expiry_date.isoformat(),
        "timeframe": normalized_tf,
        "from": from_dt.isoformat(),
        "to": to_dt.isoformat(),
        "candles": candles
    }


# =====================================================
# V2 ENDPOINTS - Enhanced with Expiry Labeling
# =====================================================

@router.get("/expiries-v2")
async def get_expiries_v2(
    symbol: str = Query(..., description="Underlying symbol (NIFTY, BANKNIFTY, etc.)"),
    backfill_days: int = Query(30, description="Days of historical labels to compute"),
    dm: DataManager = Depends(get_data_manager)
):
    """
    Get all expiries with relative labels and metadata.

    Returns:
    - is_weekly, is_monthly, is_quarterly flags
    - relative_label_today (e.g., "NWeek+1", "NMonth+0")
    - relative_label_timestamp (historical labels for each business day)

    Example:
    ```
    GET /fo/expiries-v2?symbol=NIFTY&backfill_days=30
    ```

    Response:
    ```json
    {
      "symbol": "NIFTY",
      "as_of_date": "2024-11-05",
      "expiries": [
        {
          "date": "2024-11-07",
          "is_weekly": true,
          "is_monthly": false,
          "relative_label_today": "NWeek+1",
          "relative_rank": 1,
          "relative_label_timestamp": [
            {"time": "2024-11-01", "label": "NWeek+2"},
            {"time": "2024-11-04", "label": "NWeek+1"}
          ]
        }
      ]
    }
    ```
    """
    from app.services.expiry_labeler import ExpiryLabeler

    symbol_norm = _normalize_symbol(symbol)
    as_of_date = date.today()

    # Get expiry metadata from database (pre-computed or on-the-fly)
    metadata_list = await dm.get_expiry_metadata(symbol_norm, as_of_date)

    if not metadata_list:
        raise HTTPException(status_code=404, detail=f"No expiries found for {symbol}")

    # Initialize labeler for historical computation
    labeler = ExpiryLabeler(dm.pool)

    expiries = []
    for meta in metadata_list:
        # Compute historical labels for this expiry
        historical = await labeler.compute_historical_labels(
            symbol_norm,
            meta['expiry'],
            backfill_days=backfill_days
        )

        expiries.append({
            "date": meta['expiry'].isoformat(),
            "is_weekly": meta['is_weekly'],
            "is_monthly": meta['is_monthly'],
            "is_quarterly": meta['is_quarterly'],
            "days_to_expiry": meta['days_to_expiry'],
            "relative_label_today": meta['relative_label'],
            "relative_rank": meta['relative_rank'],
            "relative_label_timestamp": [point.to_dict() for point in historical]
        })

    return {
        "symbol": symbol_norm,
        "as_of_date": as_of_date.isoformat(),
        "expiries": expiries
    }


@router.get("/moneyness-series-v2")
async def get_moneyness_series_v2(
    symbol: str = Query(..., description="Underlying symbol"),
    timeframe: str = Query("5min", description="Timeframe (1min, 5min, 15min)"),
    indicator: str = Query(..., description="Indicator (iv, delta, theta, vega, oi, pcr)"),
    option_side: str = Query("both", description="Option side (both, call, put)"),
    expiries: Optional[List[str]] = Query(None, description="List of expiry dates (YYYY-MM-DD)"),
    hours: int = Query(6, description="Lookback hours"),
    dm: DataManager = Depends(get_data_manager)
):
    """
    Get moneyness series with expiry labels (v2 - enhanced with relative labels).

    Each series point includes:
    - expiry_relative_label (e.g., "NWeek+1")
    - relative_rank (1, 2, 3... for weeklies; 0 for monthly)

    Example:
    ```
    GET /fo/moneyness-series-v2?symbol=NIFTY&timeframe=5min&indicator=iv&expiries[]=2024-11-07
    ```
    """
    from collections import defaultdict

    # Validate inputs
    symbol_norm = _normalize_symbol(symbol)
    normalized_tf = _normalize_timeframe(timeframe)

    if indicator not in SUPPORTED_INDICATORS:
        raise HTTPException(status_code=400, detail=f"Unsupported indicator: {indicator}")

    if option_side not in {"call", "put", "both"}:
        raise HTTPException(status_code=400, detail=f"Invalid option_side: {option_side}")

    # Parse expiries or get defaults
    if expiries:
        expiry_dates = []
        for exp_str in expiries:
            try:
                expiry_dates.append(datetime.fromisoformat(exp_str).date())
            except ValueError:
                logger.warning(f"Invalid expiry format: {exp_str}")
        if not expiry_dates:
            raise HTTPException(status_code=400, detail="No valid expiries provided")
    else:
        expiry_dates = await dm.get_next_expiries(symbol_norm, limit=2)

    if not expiry_dates:
        raise HTTPException(status_code=404, detail=f"No expiries found for {symbol_norm}")

    # Get expiry label map
    label_map = await dm.get_expiry_label_map(symbol_norm)

    # Calculate time range
    to_dt = datetime.now(timezone.utc)
    from_dt = to_dt - timedelta(hours=hours)

    # Map indicator to column expression
    if option_side == "both":
        column_map = {
            "iv": "(COALESCE(call_iv_avg, 0) + COALESCE(put_iv_avg, 0)) / 2.0",
            "delta": "ABS(COALESCE(call_delta_avg, 0)) + ABS(COALESCE(put_delta_avg, 0))",
            "gamma": "(COALESCE(call_gamma_avg, 0) + COALESCE(put_gamma_avg, 0)) / 2.0",
            "theta": "(COALESCE(call_theta_avg, 0) + COALESCE(put_theta_avg, 0)) / 2.0",
            "vega": "(COALESCE(call_vega_avg, 0) + COALESCE(put_vega_avg, 0)) / 2.0",
            "oi": "COALESCE(call_oi_sum, 0) + COALESCE(put_oi_sum, 0)",
            "pcr": "CASE WHEN COALESCE(call_oi_sum, 0) > 0 THEN COALESCE(put_oi_sum, 0) / call_oi_sum ELSE NULL END",
        }
    elif option_side == "call":
        column_map = {
            "iv": "call_iv_avg",
            "delta": "call_delta_avg",
            "gamma": "call_gamma_avg",
            "theta": "call_theta_avg",
            "vega": "call_vega_avg",
            "oi": "call_oi_sum",
        }
    else:  # put
        column_map = {
            "iv": "put_iv_avg",
            "delta": "put_delta_avg",
            "gamma": "put_gamma_avg",
            "theta": "put_theta_avg",
            "vega": "put_vega_avg",
            "oi": "put_oi_sum",
        }

    value_expr = column_map.get(indicator)
    if not value_expr:
        raise HTTPException(status_code=400, detail=f"Invalid indicator: {indicator}")

    # Get correct table/view based on timeframe
    table_name = _fo_strike_table(timeframe)

    # Query database
    query = f"""
        SELECT
            bucket_time,
            expiry,
            strike,
            underlying_close,
            {value_expr} as value
        FROM {table_name}
        WHERE symbol = $1
          AND expiry = ANY($2)
          AND bucket_time BETWEEN $3 AND $4
          AND {value_expr} IS NOT NULL
        ORDER BY bucket_time, expiry, strike
    """

    async with dm.pool.acquire() as conn:
        rows = await conn.fetch(
            query,
            symbol_norm,
            expiry_dates,
            from_dt,
            to_dt
        )

    logger.info(f"Moneyness-v2 query returned {len(rows)} rows for {symbol_norm} timeframe={normalized_tf}")

    # Group by (expiry, bucket, time)
    # Store as {(expiry, bucket): {timestamp: value}}
    series_data = defaultdict(lambda: defaultdict(list))

    for row in rows:
        expiry_key = row['expiry']
        expiry_str = expiry_key.isoformat()
        timestamp = int(row['bucket_time'].timestamp())
        strike = float(row['strike'])
        underlying = float(row['underlying_close']) if row['underlying_close'] else None
        value = float(row['value']) if row['value'] is not None else None

        if value is None or underlying is None:
            logger.debug(f"Skipping row: value={value}, underlying={underlying}")
            continue

        # Classify moneyness bucket
        bucket = _classify_moneyness_bucket(strike, underlying, settings.fo_strike_gap)

        # Get label and rank for this expiry
        expiry_label, relative_rank = label_map.get(expiry_key, ("Unknown", 999))

        # Store point - group by timestamp, average if multiple strikes in same bucket
        key = (expiry_str, bucket, expiry_label, relative_rank)
        series_data[key][timestamp].append(value)

    # Format response - average values at same timestamp
    series = []
    for (expiry_str, bucket, expiry_label, relative_rank), time_points in series_data.items():
        points = [
            {"time": ts, "value": round(sum(vals) / len(vals), 4)}
            for ts, vals in sorted(time_points.items())
        ]

        if points:
            series.append({
                "expiry": expiry_str,
                "expiry_relative_label": expiry_label,
                "relative_rank": relative_rank,
                "bucket": bucket,
                "points": points
            })

    return {
        "symbol": symbol_norm,
        "indicator": indicator,
        "timeframe": normalized_tf,
        "option_side": option_side,
        "series": series
    }


@router.get("/strike-distribution-v2")
async def get_strike_distribution_v2(
    symbol: str = Query(..., description="Underlying symbol"),
    timeframe: str = Query("5min", description="Timeframe"),
    indicator: str = Query("iv", description="Indicator"),
    expiries: Optional[List[str]] = Query(None, description="List of expiry dates"),
    strike_range: int = Query(30, description="ATM ± N strikes to return (default: 30 = 1500 point range for NIFTY)"),
    dm: DataManager = Depends(get_data_manager)
):
    """
    Get current strike distribution with expiry labels (v2).

    Returns strike data grouped by expiry, with each expiry including:
    - expiry_relative_label
    - relative_rank

    Example:
    ```
    GET /fo/strike-distribution-v2?symbol=NIFTY&indicator=iv&expiries[]=2024-11-07
    ```
    """
    symbol_norm = _normalize_symbol(symbol)
    normalized_tf = _normalize_timeframe(timeframe)

    if indicator not in SUPPORTED_INDICATORS - {"max_pain"}:
        raise HTTPException(status_code=400, detail=f"Unsupported indicator: {indicator}")

    # Parse expiries
    expiry_dates = _parse_expiry_params(expiries)
    if not expiry_dates:
        expiry_dates = await dm.get_next_expiries(symbol_norm, limit=2)

    if not expiry_dates:
        raise HTTPException(status_code=404, detail=f"No expiries found for {symbol_norm}")

    # Get label map
    label_map = await dm.get_expiry_label_map(symbol_norm)

    # Get latest data point
    table_name = _fo_strike_table(normalized_tf)

    query = f"""
        WITH latest_time AS (
            SELECT MAX(bucket_time) as max_time
            FROM {table_name}
            WHERE symbol = $1
              AND expiry = ANY($2)
        )
        SELECT
            bucket_time,
            expiry,
            strike,
            call_iv_avg,
            put_iv_avg,
            call_delta_avg,
            put_delta_avg,
            call_gamma_avg,
            put_gamma_avg,
            call_theta_avg,
            put_theta_avg,
            call_vega_avg,
            put_vega_avg,
            call_oi_sum,
            put_oi_sum,
            call_volume,
            put_volume,
            underlying_close
        FROM {table_name}
        WHERE symbol = $1
          AND expiry = ANY($2)
          AND bucket_time = (SELECT max_time FROM latest_time)
        ORDER BY expiry, strike
    """

    async with dm.pool.acquire() as conn:
        rows = await conn.fetch(query, symbol_norm, expiry_dates)

    logger.info(f"Strike distribution v2: fetched {len(rows)} rows for expiries={expiry_dates}")

    if not rows:
        raise HTTPException(status_code=404, detail="No data found for the specified criteria")

    # Get latest underlying price to determine ATM
    underlying_ltp = None
    for row in rows:
        if row.get("underlying_close"):
            underlying_ltp = float(row["underlying_close"])
            break

    # Calculate strike range if we have underlying price
    if underlying_ltp:
        gap = settings.fo_strike_gap  # 50 for NIFTY
        atm_strike = round(underlying_ltp / gap) * gap
        min_strike = atm_strike - (strike_range * gap)
        max_strike = atm_strike + (strike_range * gap)
    else:
        # No filtering if we don't have underlying price
        min_strike = None
        max_strike = None

    # Group by expiry
    grouped_by_expiry = {}
    filtered_count = 0

    for row in rows:
        expiry_key = row['expiry']
        expiry_str = expiry_key.isoformat()
        strike = float(row['strike'])

        # Filter by strike range (ATM ± N strikes)
        if min_strike is not None and max_strike is not None:
            if strike < min_strike or strike > max_strike:
                filtered_count += 1
                continue

        expiry_label, relative_rank = label_map.get(expiry_key, ("Unknown", 999))

        if expiry_str not in grouped_by_expiry:
            grouped_by_expiry[expiry_str] = {
                "expiry": expiry_str,
                "expiry_relative_label": expiry_label,
                "relative_rank": relative_rank,
                "underlying_price": float(row['underlying_close']) if row['underlying_close'] else None,
                "timestamp": int(row['bucket_time'].timestamp()),
                "points": []
            }

        # Get indicator value for call and put
        call_val = _indicator_value(row, indicator, "call")
        put_val = _indicator_value(row, indicator, "put")
        combined = _combine_sides(indicator, call_val, put_val)
        value = combined if indicator != "pcr" else _indicator_value(row, "pcr", "call")

        # Classify moneyness bucket
        underlying = row.get("underlying_close")
        bucket = _classify_moneyness_bucket(strike, underlying, settings.fo_strike_gap) if underlying else "Unknown"

        grouped_by_expiry[expiry_str]["points"].append({
            "strike": strike,
            "moneyness_bucket": bucket,
            "value": round(value, 4) if value is not None else None,
            "call": round(call_val, 4) if call_val is not None else None,
            "put": round(put_val, 4) if put_val is not None else None,
            "call_oi": float(row.get("call_oi_sum")) if row.get("call_oi_sum") else 0,
            "put_oi": float(row.get("put_oi_sum")) if row.get("put_oi_sum") else 0,
            "distance_from_atm": strike - underlying if underlying else None
        })

    logger.info(f"Strike distribution v2: processed {len(rows)} rows, filtered {filtered_count} by strike range, grouped into {len(grouped_by_expiry)} expiries with {sum(len(v['points']) for v in grouped_by_expiry.values())} total points")

    return {
        "symbol": symbol_norm,
        "indicator": indicator,
        "timeframe": normalized_tf,
        "grouped_by_expiry": list(grouped_by_expiry.values())
    }


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
