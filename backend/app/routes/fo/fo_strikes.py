"""
F&O Strike Analysis API endpoints.
"""
import logging
from collections import defaultdict
from datetime import datetime, timezone, date, timedelta
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from ...config import get_settings
from ...database import DataManager, _normalize_symbol, _normalize_timeframe, _fo_strike_table
from ...cache import CacheManager
from ...dependencies import get_cache_manager
from ..indicators import get_data_manager
from .helpers import SUPPORTED_INDICATORS
from .fo_expiries import _resolve_relative_expiries

router = APIRouter()
settings = get_settings()
logger = logging.getLogger(__name__)


def _classify_moneyness(strike: float, underlying: float, option_type: str) -> str:
    """
    Classify strike into moneyness based on option type.

    For calls: ITM when strike < underlying, OTM when strike > underlying
    For puts: ITM when strike > underlying, OTM when strike < underlying

    Args:
        strike: Strike price
        underlying: Current underlying price
        option_type: "call" or "put"

    Returns:
        Moneyness classification: "ATM", "ITM1", "ITM2", "OTM1", "OTM2", etc.
    """
    gap = settings.fo_strike_gap  # 50 for NIFTY
    offset = strike - underlying
    level = int(round(abs(offset) / gap))

    if abs(offset) <= gap * 0.6:  # Within 60% of strike gap = ATM
        return "ATM"

    if option_type.lower() == "call":
        if strike < underlying:  # Calls are ITM when strike < spot
            return f"ITM{min(level, 10)}"
        else:  # Calls are OTM when strike > spot
            return f"OTM{min(level, 10)}"
    else:  # put
        if strike > underlying:  # Puts are ITM when strike > spot
            return f"ITM{min(level, 10)}"
        else:  # Puts are OTM when strike < spot
            return f"OTM{min(level, 10)}"


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
    """
    Combine call and put values for an indicator.

    Args:
        indicator: Indicator name
        call_val: Call value
        put_val: Put value

    Returns:
        Combined value (sum for OI, average for others)
    """
    vals = [v for v in (call_val, put_val) if v is not None]
    if not vals:
        return None
    if indicator == "oi":
        return sum(vals)
    return sum(vals) / len(vals)


def _parse_expiry_params(expiry: Optional[List[str]]) -> Optional[List[date]]:
    """
    Parse expiry date strings into date objects.

    Args:
        expiry: List of expiry date strings in YYYY-MM-DD format

    Returns:
        List of date objects, or None if input is None
    """
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


@router.get("/strike-distribution")
async def strike_distribution(
    symbol: str = Query(settings.monitor_default_symbol),
    indicator: str = Query("iv"),
    option_side: Optional[str] = Query(None, description="Filter by option side: 'call', 'put', or None for both"),
    expiry: Optional[List[str]] = Query(default=None, description="Relative expiry labels like NWeek+0, NWeek+1, NMonth+0"),
    datetime_param: Optional[int] = Query(None, alias="datetime", description="Unix timestamp for historical data. If not provided, returns real-time data"),
    strike_range: int = Query(50, description="ATM ± N strikes to return"),
    dm: DataManager = Depends(get_data_manager),
    cache: CacheManager = Depends(get_cache_manager),
):
    """
    Return strike distribution for vertical panels.

    Frontend expects separate call/put arrays per expiry with complete Greek coverage.

    Args:
        symbol: Underlying symbol
        indicator: Greek indicator (iv, delta, gamma, theta, vega, oi, etc.)
        option_side: Filter results to only 'call' or 'put' options. If None, returns both.
        expiry: List of relative expiry labels (NWeek+0, NWeek+1, NMonth+0, etc.)
        datetime: Unix timestamp for historical data. If not provided, returns real-time data.
        strike_range: Number of strikes above and below ATM to include

    Returns format:
    {
      "series": [
        {
          "expiry": "2025-11-04",
          "relative_label": "NWeek+0",
          "call": [{"strike": 25000, "iv": 0.18, "delta": 0.45, ...}, ...],  // only if option_side is None or 'call'
          "put": [{"strike": 25000, "iv": 0.20, "delta": -0.55, ...}, ...]   // only if option_side is None or 'put'
        }
      ]
    }
    """
    indicator = indicator.lower()
    # Define strike-level supported indicators (all except max_pain which is expiry-level)
    STRIKE_SUPPORTED_INDICATORS = SUPPORTED_INDICATORS - {"max_pain"}
    if indicator not in STRIKE_SUPPORTED_INDICATORS:
        raise HTTPException(status_code=400, detail=f"Indicator {indicator} not supported for strike view. Supported: {sorted(STRIKE_SUPPORTED_INDICATORS)}")

    # Validate option_side parameter
    if option_side and option_side not in {"call", "put"}:
        raise HTTPException(status_code=400, detail=f"Invalid option_side: {option_side}. Must be 'call', 'put', or None")

    symbol_db = _normalize_symbol(symbol)

    # Determine if this is real-time or historical query
    is_realtime = datetime_param is None
    query_time = datetime.now(timezone.utc) if is_realtime else datetime.fromtimestamp(datetime_param, tz=timezone.utc)
    query_date = query_time.date()

    # Resolve relative expiry labels to actual dates
    label_to_expiry_map = {}
    expiry_to_label_map = {}
    expiries = []

    if expiry:
        logger.info(f"Received expiry params: {expiry}")
        # Check if these are relative labels or date strings
        if all(e.startswith(("NWeek", "NMonth", "NQuarter")) for e in expiry):
            # User provided relative labels, resolve them
            label_to_expiry_map = await _resolve_relative_expiries(dm, symbol_db, expiry, query_date)
            expiries = list(label_to_expiry_map.values())
            expiry_to_label_map = {v: k for k, v in label_to_expiry_map.items()}
            logger.info(f"Resolved relative labels: {label_to_expiry_map}")
        else:
            # User provided date strings, parse them
            expiries = _parse_expiry_params(expiry)
            logger.info(f"Parsed date strings to expiries: {expiries}")
    else:
        # No expiries specified, get next 2 expiries as of query date
        all_expiries = await dm.list_fo_expiries(symbol_db)
        future_expiries = [exp for exp in all_expiries if exp >= query_date]
        expiries = future_expiries[:2]

    # Determine appropriate timeframe for data fetching
    # Use 5min for real-time, 15min for historical queries
    timeframe = "5min" if is_realtime else "15min"
    normalized_tf = _normalize_timeframe(timeframe)

    # Generate cache key
    cache_key = cache.get_cache_key(
        "fo:strike_dist",
        symbol=symbol_db,
        tf=normalized_tf,
        ind=indicator,
        side=option_side or "both",
        exp=",".join(expiry) if expiry else "default",  # Use relative labels in cache key
        dt=datetime_param,
        sr=strike_range
    )

    # Try to get from cache
    cached_result = await cache.get(cache_key)
    if cached_result:
        logger.info(f"Cache hit for strike distribution: {cache_key}")
        return cached_result

    # Fetch from database
    if datetime_param:
        # Historical query - fetch data at specific timestamp
        start_time = int(query_time.timestamp())
        end_time = start_time + 1
        rows = await dm.fetch_latest_fo_strike_rows(symbol_db, normalized_tf, expiries, start_time, end_time)
    else:
        # Real-time query - fetch latest data
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

    # Calculate TOTAL OI across ALL expiries and strikes before building series
    # This gives us the complete market picture
    grand_total_call_oi = 0
    grand_total_put_oi = 0

    # Sum OI from all expiries and strikes in the raw data
    for exp_data in expiry_strikes.values():
        for strike_row in exp_data.values():
            if strike_row.get("call_oi_sum") is not None:
                grand_total_call_oi += int(float(strike_row["call_oi_sum"]))
            if strike_row.get("put_oi_sum") is not None:
                grand_total_put_oi += int(float(strike_row["put_oi_sum"]))

    # Calculate grand PCR across all expiries
    grand_pcr = (grand_total_put_oi / grand_total_call_oi) if grand_total_call_oi > 0 else None

    # Build series with separate call/put arrays
    series = []
    for expiry_key in sorted(expiry_strikes.keys()):
        strikes_data = expiry_strikes[expiry_key]

        if not strikes_data:
            continue

        call_strikes = []
        put_strikes = []
        bucket_ts = None

        # Calculate expiry-specific totals for expiry-level metadata
        expiry_call_oi = 0
        expiry_put_oi = 0

        # Sum OI from all strikes in the raw data for this expiry
        for strike_row in strikes_data.values():
            if strike_row.get("call_oi_sum") is not None:
                expiry_call_oi += int(float(strike_row["call_oi_sum"]))
            if strike_row.get("put_oi_sum") is not None:
                expiry_put_oi += int(float(strike_row["put_oi_sum"]))

        for strike in sorted(strikes_data.keys()):
            row = strikes_data[strike]

            if bucket_ts is None:
                ts = row["bucket_time"]
                if isinstance(ts, datetime):
                    bucket_ts = int(ts.replace(tzinfo=timezone.utc).timestamp())
                else:
                    bucket_ts = int(ts)

            # Build call strike object with all Greeks (only if option_side is None or 'call')
            if option_side is None or option_side == "call":
                call_obj = {"strike": strike}

                # Add all available Greeks (include if not None, even if zero)
                if row.get("call_iv_avg") is not None:
                    call_obj["iv"] = round(float(row["call_iv_avg"]), 4)
                if row.get("call_delta_avg") is not None:
                    call_obj["delta"] = round(float(row["call_delta_avg"]), 4)
                if row.get("call_gamma_avg") is not None:
                    call_obj["gamma"] = round(float(row["call_gamma_avg"]), 6)
                if row.get("call_theta_avg") is not None:
                    call_obj["theta"] = round(float(row["call_theta_avg"]), 4)
                if row.get("call_vega_avg") is not None:
                    call_obj["vega"] = round(float(row["call_vega_avg"]), 4)
                if row.get("call_oi_sum") is not None:
                    call_obj["oi"] = int(float(row["call_oi_sum"]))

                # Enhanced Greeks
                if row.get("call_rho_per_1pct_avg") is not None:
                    call_obj["rho"] = round(float(row["call_rho_per_1pct_avg"]), 6)
                if row.get("call_intrinsic_avg") is not None:
                    call_obj["intrinsic"] = round(float(row["call_intrinsic_avg"]), 2)
                if row.get("call_extrinsic_avg") is not None:
                    call_obj["extrinsic"] = round(float(row["call_extrinsic_avg"]), 2)
                if row.get("call_theta_daily_avg") is not None:
                    call_obj["theta_daily"] = round(float(row["call_theta_daily_avg"]), 4)
                    call_obj["decay"] = call_obj["theta_daily"]  # Add decay as an alias for theta_daily
                if row.get("call_model_price_avg") is not None:
                    call_obj["model_price"] = round(float(row["call_model_price_avg"]), 2)

                # Calculate premium/LTP and premium/discount
                intrinsic = float(row.get("call_intrinsic_avg", 0) or 0)
                extrinsic = float(row.get("call_extrinsic_avg", 0) or 0)
                model_price = float(row.get("call_model_price_avg", 0) or 0)

                if intrinsic > 0 or extrinsic > 0:
                    market_price = intrinsic + extrinsic
                    call_obj["premium"] = round(market_price, 2)
                    call_obj["ltp"] = call_obj["premium"]  # LTP is the premium/market price

                    # Calculate premium/discount vs model price
                    if model_price > 0:
                        premium_abs = market_price - model_price
                        premium_pct = (premium_abs / model_price) * 100
                        call_obj["premium_discount_abs"] = round(premium_abs, 2)
                        call_obj["premium_discount_pct"] = round(premium_pct, 2)

                # Volume
                if row.get("call_volume") is not None:
                    call_obj["volume"] = int(float(row["call_volume"]))

                # Market depth metrics
                if row.get("liquidity_score_avg") is not None:
                    call_obj["liquidity_score"] = round(float(row["liquidity_score_avg"]), 2)
                if row.get("spread_abs_avg") is not None:
                    call_obj["spread_abs"] = round(float(row["spread_abs_avg"]), 2)
                if row.get("spread_pct_avg") is not None:
                    call_obj["spread_pct"] = round(float(row["spread_pct_avg"]), 2)
                if row.get("depth_imbalance_pct_avg") is not None:
                    call_obj["depth_imbalance"] = round(float(row["depth_imbalance_pct_avg"]), 2)
                if row.get("book_pressure_avg") is not None:
                    call_obj["book_pressure"] = round(float(row["book_pressure_avg"]), 4)
                if row.get("microprice_avg") is not None:
                    call_obj["microprice"] = round(float(row["microprice_avg"]), 2)

                # Add moneyness classification
                if underlying_ltp:
                    call_obj["moneyness"] = _classify_moneyness(strike, underlying_ltp, "call")
                    call_obj["moneyness_bucket"] = call_obj["moneyness"]  # Add alias for compatibility

                # OI change will be calculated later for real-time data

                # Add strike-level PCR if we have both call and put OI
                call_oi = call_obj.get("oi", 0)
                put_oi = float(row.get("put_oi_sum", 0) or 0)
                if call_oi > 0 and put_oi > 0:
                    call_obj["pcr"] = round(put_oi / call_oi, 3)

                call_strikes.append(call_obj)

            # Build put strike object with all Greeks (only if option_side is None or 'put')
            if option_side is None or option_side == "put":
                put_obj = {"strike": strike}

                if row.get("put_iv_avg") is not None:
                    put_obj["iv"] = round(float(row["put_iv_avg"]), 4)
                if row.get("put_delta_avg") is not None:
                    put_obj["delta"] = round(float(row["put_delta_avg"]), 4)
                if row.get("put_gamma_avg") is not None:
                    put_obj["gamma"] = round(float(row["put_gamma_avg"]), 6)
                if row.get("put_theta_avg") is not None:
                    put_obj["theta"] = round(float(row["put_theta_avg"]), 4)
                if row.get("put_vega_avg") is not None:
                    put_obj["vega"] = round(float(row["put_vega_avg"]), 4)
                if row.get("put_oi_sum") is not None:
                    put_obj["oi"] = int(float(row["put_oi_sum"]))

                # Enhanced Greeks
                if row.get("put_rho_per_1pct_avg") is not None:
                    put_obj["rho"] = round(float(row["put_rho_per_1pct_avg"]), 6)
                if row.get("put_intrinsic_avg") is not None:
                    put_obj["intrinsic"] = round(float(row["put_intrinsic_avg"]), 2)
                if row.get("put_extrinsic_avg") is not None:
                    put_obj["extrinsic"] = round(float(row["put_extrinsic_avg"]), 2)
                if row.get("put_theta_daily_avg") is not None:
                    put_obj["theta_daily"] = round(float(row["put_theta_daily_avg"]), 4)
                    put_obj["decay"] = put_obj["theta_daily"]  # Add decay as an alias for theta_daily
                if row.get("put_model_price_avg") is not None:
                    put_obj["model_price"] = round(float(row["put_model_price_avg"]), 2)

                # Calculate premium/LTP and premium/discount
                intrinsic = float(row.get("put_intrinsic_avg", 0) or 0)
                extrinsic = float(row.get("put_extrinsic_avg", 0) or 0)
                model_price = float(row.get("put_model_price_avg", 0) or 0)

                if intrinsic > 0 or extrinsic > 0:
                    market_price = intrinsic + extrinsic
                    put_obj["premium"] = round(market_price, 2)
                    put_obj["ltp"] = put_obj["premium"]  # LTP is the premium/market price

                    # Calculate premium/discount vs model price
                    if model_price > 0:
                        premium_abs = market_price - model_price
                        premium_pct = (premium_abs / model_price) * 100
                        put_obj["premium_discount_abs"] = round(premium_abs, 2)
                        put_obj["premium_discount_pct"] = round(premium_pct, 2)

                # Volume
                if row.get("put_volume") is not None:
                    put_obj["volume"] = int(float(row["put_volume"]))

                # Market depth metrics (shared with calls)
                if row.get("liquidity_score_avg") is not None:
                    put_obj["liquidity_score"] = round(float(row["liquidity_score_avg"]), 2)
                if row.get("spread_abs_avg") is not None:
                    put_obj["spread_abs"] = round(float(row["spread_abs_avg"]), 2)
                if row.get("spread_pct_avg") is not None:
                    put_obj["spread_pct"] = round(float(row["spread_pct_avg"]), 2)
                if row.get("depth_imbalance_pct_avg") is not None:
                    put_obj["depth_imbalance"] = round(float(row["depth_imbalance_pct_avg"]), 2)
                if row.get("book_pressure_avg") is not None:
                    put_obj["book_pressure"] = round(float(row["book_pressure_avg"]), 4)
                if row.get("microprice_avg") is not None:
                    put_obj["microprice"] = round(float(row["microprice_avg"]), 2)

                # Add moneyness classification
                if underlying_ltp:
                    put_obj["moneyness"] = _classify_moneyness(strike, underlying_ltp, "put")
                    put_obj["moneyness_bucket"] = put_obj["moneyness"]  # Add alias for compatibility

                # OI change will be calculated later for real-time data

                # Add strike-level PCR if we have both call and put OI
                put_oi = put_obj.get("oi", 0)
                call_oi = float(row.get("call_oi_sum", 0) or 0)
                if call_oi > 0 and put_oi > 0:
                    put_obj["pcr"] = round(put_oi / call_oi, 3)

                put_strikes.append(put_obj)

        # Determine data availability
        has_greeks = any(
            "iv" in s or "delta" in s or "gamma" in s
            for s in call_strikes + put_strikes
        )
        has_oi = any("oi" in s for s in call_strikes + put_strikes)

        # Calculate expiry-specific PCR
        expiry_pcr = (expiry_put_oi / expiry_call_oi) if expiry_call_oi > 0 else None

        # Calculate max pain for this expiry
        max_pain_strike = None
        # Always calculate max pain from raw data if we have both call and put OI
        if expiry_call_oi > 0 and expiry_put_oi > 0:
            # Create a map of strikes to OI from raw data
            strike_oi_map = {}
            for strike, row in strikes_data.items():
                call_oi = int(float(row.get("call_oi_sum", 0) or 0))
                put_oi = int(float(row.get("put_oi_sum", 0) or 0))
                if call_oi > 0 or put_oi > 0:
                    strike_oi_map[strike] = {"call_oi": call_oi, "put_oi": put_oi}

            # Calculate max pain as the strike with minimum total payout
            min_payout = float('inf')
            for strike, oi_data in strike_oi_map.items():
                total_payout = 0
                # For each other strike, calculate payout
                for other_strike, other_oi in strike_oi_map.items():
                    if other_strike < strike:
                        # ITM puts
                        total_payout += (strike - other_strike) * other_oi["put_oi"]
                    elif other_strike > strike:
                        # ITM calls
                        total_payout += (other_strike - strike) * other_oi["call_oi"]

                if total_payout < min_payout:
                    min_payout = total_payout
                    max_pain_strike = strike

        # Build series entry based on option_side filter
        series_entry = {
            "expiry": expiry_key,
            "bucket_time": bucket_ts,
            "metadata": {
                "strike_count": len(call_strikes) + len(put_strikes),
                "has_greeks": has_greeks,
                "has_oi": has_oi,
                "atm_strike": atm_strike if underlying_ltp else None,
                "expiry_call_oi": expiry_call_oi,
                "expiry_put_oi": expiry_put_oi,
                "expiry_pcr": round(expiry_pcr, 3) if expiry_pcr is not None else None,
                "max_pain_strike": max_pain_strike
            }
        }

        # Add relative label if available
        expiry_date_obj = datetime.fromisoformat(expiry_key).date()
        if expiry_date_obj in expiry_to_label_map:
            series_entry["relative_label"] = expiry_to_label_map[expiry_date_obj]

        # Include call/put arrays based on option_side parameter
        if option_side is None or option_side == "call":
            series_entry["call"] = call_strikes
        if option_side is None or option_side == "put":
            series_entry["put"] = put_strikes

        series.append(series_entry)

    # Calculate OI changes for real-time data
    if is_realtime and any(entry.get("metadata", {}).get("has_oi", False) for entry in series):
        # Fetch previous period data to calculate OI changes
        # Use 1 hour ago for 5min timeframe
        prev_time = query_time - timedelta(hours=1)
        prev_start = int(prev_time.timestamp())
        prev_end = prev_start + 1

        try:
            prev_rows = await dm.fetch_latest_fo_strike_rows(symbol_db, normalized_tf, expiries, prev_start, prev_end)

            # Create a map of (expiry, strike) -> previous OI values
            prev_oi_map = {}
            for row in prev_rows:
                key = (row["expiry"].isoformat(), float(row["strike"]))
                prev_oi_map[key] = {
                    "call_oi": int(float(row.get("call_oi_sum", 0) or 0)),
                    "put_oi": int(float(row.get("put_oi_sum", 0) or 0))
                }

            # Update OI changes in the series
            for entry in series:
                expiry_key = entry["expiry"]

                if "call" in entry:
                    for call_strike in entry["call"]:
                        if "oi" in call_strike:
                            key = (expiry_key, call_strike["strike"])
                            if key in prev_oi_map:
                                current_oi = call_strike["oi"]
                                prev_oi = prev_oi_map[key]["call_oi"]
                                call_strike["oi_change"] = current_oi - prev_oi
                            else:
                                call_strike["oi_change"] = call_strike["oi"]  # All new OI

                if "put" in entry:
                    for put_strike in entry["put"]:
                        if "oi" in put_strike:
                            key = (expiry_key, put_strike["strike"])
                            if key in prev_oi_map:
                                current_oi = put_strike["oi"]
                                prev_oi = prev_oi_map[key]["put_oi"]
                                put_strike["oi_change"] = current_oi - prev_oi
                            else:
                                put_strike["oi_change"] = put_strike["oi"]  # All new OI
        except Exception as e:
            logger.warning(f"Failed to calculate OI changes: {e}")
            # Continue without OI changes

    result = {
        "status": "ok",
        "symbol": symbol_db,
        "indicator": indicator,
        "option_side": option_side,  # Include the filter that was applied
        "series": series,
        "metadata": {
            "total_expiries": len(series),
            "underlying_price": underlying_ltp,
            "strike_range": f"ATM ± {strike_range} strikes",
            "data_available": len(series) > 0,
            "total_call_oi": grand_total_call_oi,
            "total_put_oi": grand_total_put_oi,
            "pcr": round(grand_pcr, 3) if grand_pcr is not None else None,
            "query_time": query_time.isoformat(),
            "is_realtime": is_realtime,
            "timeframe_used": normalized_tf
        }
    }

    # Cache the result
    # For real-time data, use shorter TTL
    # For historical data, use longer TTL
    ttl = 30 if is_realtime else 300  # 30s for real-time, 5min for historical
    await cache.set(cache_key, result, ttl)
    logger.info(f"Cached strike distribution with TTL={ttl}s: {cache_key}")

    return result


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

    Args:
        symbol: Underlying symbol
        strike: Strike price
        expiry: Expiry date (YYYY-MM-DD)
        timeframe: Data timeframe (1min, 5min, 15min)
        from_time: Start timestamp (Unix seconds)
        to_time: End timestamp (Unix seconds)
        hours: Lookback hours if from/to not provided

    Returns:
        Candle data with greeks, OI, and volume for the specified strike
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
