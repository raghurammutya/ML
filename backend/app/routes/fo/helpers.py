"""
Shared helper functions and constants for F&O routes.
"""
from datetime import datetime, timezone, date, timedelta
from typing import Dict, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)

# Supported values
SUPPORTED_INDICATORS = {"iv", "delta", "gamma", "theta", "vega", "rho", "oi", "pcr", "max_pain", "premium", "decay"}
SUPPORTED_SEGMENTS = {"NFO-OPT", "NFO-FUT", "CDS-OPT", "CDS-FUT", "MCX-OPT", "MCX-FUT"}
SUPPORTED_OPTION_TYPES = {"CE", "PE"}
SUPPORTED_INSTRUMENT_TYPES = {"CE", "PE", "FUT"}


def default_time_range(hours: int = 6) -> Tuple[int, int]:
    """
    Generate default time range for queries.

    Args:
        hours: Number of hours to look back

    Returns:
        Tuple of (start_timestamp, end_timestamp) in seconds
    """
    now_ts = int(datetime.now(timezone.utc).timestamp())
    start_ts = now_ts - (hours * 3600)
    return start_ts, now_ts


def parse_expiry_params(expiry: Optional[List[str]]) -> Optional[List[date]]:
    """
    Parse expiry date strings into date objects.

    Args:
        expiry: List of expiry date strings in YYYY-MM-DD format

    Returns:
        List of date objects, or None if input is None
    """
    if not expiry:
        return None

    parsed_dates = []
    for exp_str in expiry:
        try:
            parsed_dates.append(datetime.strptime(exp_str, "%Y-%m-%d").date())
        except ValueError:
            logger.warning(f"Invalid expiry format: {exp_str}")
            continue

    return parsed_dates if parsed_dates else None


def classify_moneyness(strike: float, underlying: Optional[float], side: str) -> Optional[str]:
    """
    Classify moneyness based on strike price and underlying price.

    Args:
        strike: Strike price
        underlying: Current underlying price
        side: Option side ("CE" for calls, "PE" for puts)

    Returns:
        Moneyness classification: "ITM", "ATM", "OTM", or None
    """
    if underlying is None:
        return None

    diff_pct = abs(strike - underlying) / underlying * 100

    # ATM: within 0.5% of underlying
    if diff_pct < 0.5:
        return "ATM"

    # For calls
    if side == "CE":
        return "ITM" if strike < underlying else "OTM"

    # For puts
    if side == "PE":
        return "ITM" if strike > underlying else "OTM"

    return None


def classify_generic_moneyness(strike: float, underlying: Optional[float]) -> Optional[str]:
    """
    Generic moneyness classification without considering option type.

    Args:
        strike: Strike price
        underlying: Current underlying price

    Returns:
        Simplified moneyness: "ATM", "OTM_CALL", "ITM_CALL", "OTM_PUT", "ITM_PUT"
    """
    if underlying is None:
        return None

    diff_pct = abs(strike - underlying) / underlying * 100

    # ATM: within 0.5%
    if diff_pct < 0.5:
        return "ATM"

    if strike < underlying:
        return "ITM_CALL"  # or OTM_PUT
    else:
        return "OTM_CALL"  # or ITM_PUT


def classify_moneyness_bucket(strike: float, underlying: float, gap: int = 50) -> str:
    """
    Classify moneyness into bucketed ranges.

    Args:
        strike: Strike price
        underlying: Current underlying price
        gap: Strike gap for bucketing (default 50)

    Returns:
        Bucket label like "ATM", "+1 (19450-19500)", "-2 (19300-19350)"
    """
    diff = strike - underlying

    # ATM bucket
    if abs(diff) < gap / 2:
        return "ATM"

    # Calculate bucket number
    bucket_num = int(diff / gap)

    # Format bucket label
    if bucket_num > 0:
        lower = underlying + (bucket_num * gap)
        upper = lower + gap
        return f"+{bucket_num} ({int(lower)}-{int(upper)})"
    else:
        upper = underlying + (bucket_num * gap)
        lower = upper - gap
        return f"{bucket_num} ({int(lower)}-{int(upper)})"


def indicator_value(row: Dict, indicator: str, side: str) -> Optional[float]:
    """
    Extract indicator value from a row based on side.

    Args:
        row: Database row dictionary
        indicator: Indicator name (iv, delta, gamma, etc.)
        side: Option side ("CE" or "PE")

    Returns:
        Indicator value, or None if not available
    """
    # Map indicator to column names
    call_col = f"{indicator}_call" if indicator != "oi" else "oi_call"
    put_col = f"{indicator}_put" if indicator != "oi" else "oi_put"

    if side == "CE":
        return row.get(call_col)
    elif side == "PE":
        return row.get(put_col)

    return None


def combine_sides(indicator: str, call_val: Optional[float], put_val: Optional[float]) -> Optional[float]:
    """
    Combine call and put values for an indicator.

    Args:
        indicator: Indicator name
        call_val: Call value
        put_val: Put value

    Returns:
        Combined value based on indicator type
    """
    # For PCR (Put-Call Ratio), divide put by call
    if indicator == "pcr":
        if call_val and call_val != 0 and put_val:
            return put_val / call_val
        return None

    # For other indicators, sum the values
    if call_val is not None and put_val is not None:
        return call_val + put_val
    elif call_val is not None:
        return call_val
    elif put_val is not None:
        return put_val

    return None


def classify_moneyness_v2(strike: float, underlying: float, option_type: str) -> str:
    """
    Classify moneyness for v2 endpoints.

    Args:
        strike: Strike price
        underlying: Current underlying price
        option_type: "CE" or "PE"

    Returns:
        Moneyness classification: "ITM", "ATM", "OTM"
    """
    diff_pct = abs(strike - underlying) / underlying * 100

    # ATM: within 0.5%
    if diff_pct < 0.5:
        return "ATM"

    # Calls
    if option_type == "CE":
        return "ITM" if strike < underlying else "OTM"

    # Puts
    return "ITM" if strike > underlying else "OTM"
