"""
F&O Instruments Search API.
"""
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from ...database import DataManager
from ..indicators import get_data_manager
from .helpers import SUPPORTED_SEGMENTS, SUPPORTED_OPTION_TYPES, SUPPORTED_INSTRUMENT_TYPES

router = APIRouter()
logger = logging.getLogger(__name__)


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
