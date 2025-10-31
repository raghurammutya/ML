"""
Timeframe normalization and conversion utilities.
Consolidated from multiple implementations across the codebase.
"""

from typing import Optional


def normalize_timeframe(resolution: str) -> str:
    """
    Convert a TradingView-style resolution (e.g., "1D", "60", "1W") into our
    canonical timeframe names ("1min", "1day", etc.). Also accepts our own
    timeframe names and returns them unchanged.

    Args:
        resolution: TradingView resolution string

    Returns:
        Canonical timeframe string

    Examples:
        >>> normalize_timeframe("1")
        '1min'
        >>> normalize_timeframe("60")
        '1hour'
        >>> normalize_timeframe("1D")
        '1day'
        >>> normalize_timeframe("1min")
        '1min'
    """
    r = (resolution or "").strip().upper()
    if not r:
        return "1min"

    # Already in canonical form
    canonical_timeframes = {
        "1MIN", "5MIN", "15MIN", "30MIN",
        "1HOUR", "2HOUR", "4HOUR",
        "1DAY", "1WEEK", "1MONTH"
    }
    if r in canonical_timeframes:
        return r.lower()

    # TradingView minute resolutions (numeric strings)
    minute_map = {
        "1": "1min",
        "3": "3min",
        "5": "5min",
        "15": "15min",
        "30": "30min",
        "45": "45min",
        "60": "1hour",
        "120": "2hour",
        "180": "3hour",
        "240": "4hour",
    }
    if r in minute_map:
        return minute_map[r]

    # TradingView suffix style (1D, 1W, 1M)
    if r.endswith("D"):
        return "1day"
    if r.endswith("W"):
        return "1week"
    if r.endswith("M") and not r.endswith("MIN"):
        return "1month"

    # Default to 1min if unrecognized
    return "1min"


def timeframe_to_seconds(timeframe: str) -> int:
    """
    Convert a timeframe string to seconds.

    Args:
        timeframe: Canonical timeframe (e.g., "1min", "5min", "1hour", "1day")

    Returns:
        Number of seconds in the timeframe

    Examples:
        >>> timeframe_to_seconds("1min")
        60
        >>> timeframe_to_seconds("5min")
        300
        >>> timeframe_to_seconds("1hour")
        3600
        >>> timeframe_to_seconds("1day")
        86400
    """
    tf = normalize_timeframe(timeframe).lower()

    timeframe_map = {
        "1min": 60,
        "3min": 180,
        "5min": 300,
        "15min": 900,
        "30min": 1800,
        "45min": 2700,
        "1hour": 3600,
        "2hour": 7200,
        "3hour": 10800,
        "4hour": 14400,
        "1day": 86400,
        "1week": 604800,
        "1month": 2592000,  # Approximate (30 days)
    }

    return timeframe_map.get(tf, 60)


def timeframe_to_resolution(timeframe: str) -> str:
    """
    Convert canonical timeframe to TradingView resolution string.

    Args:
        timeframe: Canonical timeframe

    Returns:
        TradingView resolution string

    Examples:
        >>> timeframe_to_resolution("1min")
        '1'
        >>> timeframe_to_resolution("1hour")
        '60'
        >>> timeframe_to_resolution("1day")
        '1D'
    """
    tf = normalize_timeframe(timeframe).lower()

    resolution_map = {
        "1min": "1",
        "3min": "3",
        "5min": "5",
        "15min": "15",
        "30min": "30",
        "45min": "45",
        "1hour": "60",
        "2hour": "120",
        "3hour": "180",
        "4hour": "240",
        "1day": "1D",
        "1week": "1W",
        "1month": "1M",
    }

    return resolution_map.get(tf, "1")


def timeframe_to_interval_literal(timeframe: str) -> Optional[str]:
    """
    Convert timeframe to PostgreSQL interval literal for time_bucket.

    Args:
        timeframe: Canonical timeframe

    Returns:
        PostgreSQL interval string (e.g., "1 minute", "1 hour", "1 day")

    Examples:
        >>> timeframe_to_interval_literal("1min")
        '1 minute'
        >>> timeframe_to_interval_literal("5min")
        '5 minutes'
        >>> timeframe_to_interval_literal("1hour")
        '1 hour'
    """
    tf = normalize_timeframe(timeframe).lower()

    # Map to PostgreSQL interval literals
    interval_map = {
        "1min": "1 minute",
        "3min": "3 minutes",
        "5min": "5 minutes",
        "15min": "15 minutes",
        "30min": "30 minutes",
        "45min": "45 minutes",
        "1hour": "1 hour",
        "2hour": "2 hours",
        "3hour": "3 hours",
        "4hour": "4 hours",
        "1day": "1 day",
        "1week": "1 week",
        "1month": "1 month",
    }

    return interval_map.get(tf)
