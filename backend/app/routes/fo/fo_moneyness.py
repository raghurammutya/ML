"""
F&O Moneyness Analysis API endpoints.
"""
import logging
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from ...config import get_settings
from ...database import DataManager, _normalize_symbol, _normalize_timeframe, _fo_strike_table
from ...cache import CacheManager
from ...dependencies import get_cache_manager
from ..indicators import get_data_manager
from .helpers import SUPPORTED_INDICATORS

router = APIRouter()
settings = get_settings()
logger = logging.getLogger(__name__)


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
    cache: CacheManager = Depends(get_cache_manager),
):
    """
    Return time-series data grouped by moneyness buckets.

    Used by horizontal panels (IV, Delta, Gamma, Theta, Vega charts).
    Returns series grouped by expiry and moneyness level (ATM, OTM1, OTM2, ITM1, ITM2, etc.).

    Args:
        symbol: Underlying symbol
        timeframe: Data timeframe (1min, 5min, 15min)
        indicator: Indicator to analyze (iv, delta, gamma, theta, vega, oi, pcr, premium, decay)
        option_side: Filter by option type (call, put, both)
        expiry: List of expiry dates (YYYY-MM-DD format). Defaults to next 2 expiries.
        from_time: Start timestamp (Unix seconds)
        to_time: End timestamp (Unix seconds)
        limit: Maximum number of results

    Returns:
        Series data with points grouped by expiry and moneyness bucket
    """
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

    # Generate cache key
    cache_key = cache.get_cache_key(
        "fo:moneyness",
        symbol=symbol_db,
        tf=normalized_tf,
        ind=indicator,
        side=option_side,
        exp=",".join(e.isoformat() for e in expiry_dates) if expiry_dates else "default",
        ft=from_time,
        tt=to_time,
        limit=limit
    )

    # Try to get from cache
    cached_result = await cache.get(cache_key)
    if cached_result:
        logger.info(f"Cache hit for moneyness series: {cache_key}")
        return cached_result

    # Map indicator to column expression
    if option_side == "both":
        column_map = {
            "iv": "(COALESCE(call_iv_avg, 0) + COALESCE(put_iv_avg, 0)) / 2.0",
            "delta": "ABS(COALESCE(call_delta_avg, 0)) + ABS(COALESCE(put_delta_avg, 0))",
            "gamma": "(COALESCE(call_gamma_avg, 0) + COALESCE(put_gamma_avg, 0)) / 2.0",
            "theta": "(COALESCE(call_theta_avg, 0) + COALESCE(put_theta_avg, 0)) / 2.0",
            "vega": "(COALESCE(call_vega_avg, 0) + COALESCE(put_vega_avg, 0)) / 2.0",
            "rho": "(COALESCE(call_rho_per_1pct_avg, 0) + COALESCE(put_rho_per_1pct_avg, 0)) / 2.0",
            "oi": "COALESCE(call_oi_sum, 0) + COALESCE(put_oi_sum, 0)",
            "pcr": "CASE WHEN COALESCE(call_oi_sum, 0) > 0 THEN COALESCE(put_oi_sum, 0) / call_oi_sum ELSE NULL END",
            # Premium is the LTP (intrinsic + extrinsic)
            "premium": "((COALESCE(call_intrinsic_avg, 0) + COALESCE(call_extrinsic_avg, 0)) + (COALESCE(put_intrinsic_avg, 0) + COALESCE(put_extrinsic_avg, 0))) / 2.0",
            # Decay is the daily theta
            "decay": "(COALESCE(call_theta_daily_avg, 0) + COALESCE(put_theta_daily_avg, 0)) / 2.0",
            # Premium/Discount metrics (market_price - model_price)
            "premium_abs": "((COALESCE(call_intrinsic_avg, 0) + COALESCE(call_extrinsic_avg, 0) - COALESCE(call_model_price_avg, 0)) + (COALESCE(put_intrinsic_avg, 0) + COALESCE(put_extrinsic_avg, 0) - COALESCE(put_model_price_avg, 0))) / 2.0",
            "premium_pct": "((CASE WHEN COALESCE(call_model_price_avg, 0) > 0 THEN ((COALESCE(call_intrinsic_avg, 0) + COALESCE(call_extrinsic_avg, 0)) - call_model_price_avg) / call_model_price_avg * 100 ELSE 0 END) + (CASE WHEN COALESCE(put_model_price_avg, 0) > 0 THEN ((COALESCE(put_intrinsic_avg, 0) + COALESCE(put_extrinsic_avg, 0)) - put_model_price_avg) / put_model_price_avg * 100 ELSE 0 END)) / 2.0",
        }
    elif option_side == "call":
        column_map = {
            "iv": "call_iv_avg",
            "delta": "call_delta_avg",
            "gamma": "call_gamma_avg",
            "theta": "call_theta_avg",
            "vega": "call_vega_avg",
            "rho": "call_rho_per_1pct_avg",
            "oi": "call_oi_sum",
            # Premium is the LTP (intrinsic + extrinsic)
            "premium": "(COALESCE(call_intrinsic_avg, 0) + COALESCE(call_extrinsic_avg, 0))",
            # Decay is the daily theta
            "decay": "call_theta_daily_avg",
            # Premium/Discount metrics
            "premium_abs": "(COALESCE(call_intrinsic_avg, 0) + COALESCE(call_extrinsic_avg, 0)) - COALESCE(call_model_price_avg, 0)",
            "premium_pct": "CASE WHEN COALESCE(call_model_price_avg, 0) > 0 THEN ((COALESCE(call_intrinsic_avg, 0) + COALESCE(call_extrinsic_avg, 0)) - call_model_price_avg) / call_model_price_avg * 100 ELSE NULL END",
        }
    else:  # put
        column_map = {
            "iv": "put_iv_avg",
            "delta": "put_delta_avg",
            "gamma": "put_gamma_avg",
            "theta": "put_theta_avg",
            "vega": "put_vega_avg",
            "rho": "put_rho_per_1pct_avg",
            "oi": "put_oi_sum",
            # Premium is the LTP (intrinsic + extrinsic)
            "premium": "(COALESCE(put_intrinsic_avg, 0) + COALESCE(put_extrinsic_avg, 0))",
            # Decay is the daily theta
            "decay": "put_theta_daily_avg",
            # Premium/Discount metrics
            "premium_abs": "(COALESCE(put_intrinsic_avg, 0) + COALESCE(put_extrinsic_avg, 0)) - COALESCE(put_model_price_avg, 0)",
            "premium_pct": "CASE WHEN COALESCE(put_model_price_avg, 0) > 0 THEN ((COALESCE(put_intrinsic_avg, 0) + COALESCE(put_extrinsic_avg, 0)) - put_model_price_avg) / put_model_price_avg * 100 ELSE NULL END",
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

    result = {
        "status": "ok",
        "symbol": symbol_db,
        "timeframe": normalized_tf,
        "indicator": indicator,
        "series": series
    }

    # Cache the result
    # For real-time data (recent time range), use shorter TTL
    # For historical data (older time range), use longer TTL
    time_diff = to_dt - from_dt
    is_realtime = not from_time or (datetime.now(timezone.utc) - to_dt).total_seconds() < 300
    ttl = 30 if is_realtime else 300  # 30s for real-time, 5min for historical
    await cache.set(cache_key, result, ttl)
    logger.info(f"Cached moneyness series with TTL={ttl}s: {cache_key}")

    return result


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
            "rho": "(COALESCE(call_rho_per_1pct_avg, 0) + COALESCE(put_rho_per_1pct_avg, 0)) / 2.0",
            "oi": "COALESCE(call_oi_sum, 0) + COALESCE(put_oi_sum, 0)",
            "pcr": "CASE WHEN COALESCE(call_oi_sum, 0) > 0 THEN COALESCE(put_oi_sum, 0) / call_oi_sum ELSE NULL END",
            # Premium is the LTP (intrinsic + extrinsic)
            "premium": "((COALESCE(call_intrinsic_avg, 0) + COALESCE(call_extrinsic_avg, 0)) + (COALESCE(put_intrinsic_avg, 0) + COALESCE(put_extrinsic_avg, 0))) / 2.0",
            # Decay is the daily theta
            "decay": "(COALESCE(call_theta_daily_avg, 0) + COALESCE(put_theta_daily_avg, 0)) / 2.0",
            # Premium/Discount metrics (market_price - model_price)
            "premium_abs": "((COALESCE(call_intrinsic_avg, 0) + COALESCE(call_extrinsic_avg, 0) - COALESCE(call_model_price_avg, 0)) + (COALESCE(put_intrinsic_avg, 0) + COALESCE(put_extrinsic_avg, 0) - COALESCE(put_model_price_avg, 0))) / 2.0",
            "premium_pct": "((CASE WHEN COALESCE(call_model_price_avg, 0) > 0 THEN ((COALESCE(call_intrinsic_avg, 0) + COALESCE(call_extrinsic_avg, 0)) - call_model_price_avg) / call_model_price_avg * 100 ELSE 0 END) + (CASE WHEN COALESCE(put_model_price_avg, 0) > 0 THEN ((COALESCE(put_intrinsic_avg, 0) + COALESCE(put_extrinsic_avg, 0)) - put_model_price_avg) / put_model_price_avg * 100 ELSE 0 END)) / 2.0",
        }
    elif option_side == "call":
        column_map = {
            "iv": "call_iv_avg",
            "delta": "call_delta_avg",
            "gamma": "call_gamma_avg",
            "theta": "call_theta_avg",
            "vega": "call_vega_avg",
            "rho": "call_rho_per_1pct_avg",
            "oi": "call_oi_sum",
            # Premium is the LTP (intrinsic + extrinsic)
            "premium": "(COALESCE(call_intrinsic_avg, 0) + COALESCE(call_extrinsic_avg, 0))",
            # Decay is the daily theta
            "decay": "call_theta_daily_avg",
            # Premium/Discount metrics
            "premium_abs": "(COALESCE(call_intrinsic_avg, 0) + COALESCE(call_extrinsic_avg, 0)) - COALESCE(call_model_price_avg, 0)",
            "premium_pct": "CASE WHEN COALESCE(call_model_price_avg, 0) > 0 THEN ((COALESCE(call_intrinsic_avg, 0) + COALESCE(call_extrinsic_avg, 0)) - call_model_price_avg) / call_model_price_avg * 100 ELSE NULL END",
        }
    else:  # put
        column_map = {
            "iv": "put_iv_avg",
            "delta": "put_delta_avg",
            "gamma": "put_gamma_avg",
            "theta": "put_theta_avg",
            "vega": "put_vega_avg",
            "rho": "put_rho_per_1pct_avg",
            "oi": "put_oi_sum",
            # Premium is the LTP (intrinsic + extrinsic)
            "premium": "(COALESCE(put_intrinsic_avg, 0) + COALESCE(put_extrinsic_avg, 0))",
            # Decay is the daily theta
            "decay": "put_theta_daily_avg",
            # Premium/Discount metrics
            "premium_abs": "(COALESCE(put_intrinsic_avg, 0) + COALESCE(put_extrinsic_avg, 0)) - COALESCE(put_model_price_avg, 0)",
            "premium_pct": "CASE WHEN COALESCE(put_model_price_avg, 0) > 0 THEN ((COALESCE(put_intrinsic_avg, 0) + COALESCE(put_extrinsic_avg, 0)) - put_model_price_avg) / put_model_price_avg * 100 ELSE NULL END",
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
