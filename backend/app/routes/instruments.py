# app/routes/instruments.py
"""
Instruments API - List and filter tradeable symbols from instrument_registry

Provides endpoints to:
- List all instruments
- Filter by classification (stocks, futures, options, indices)
- Search by name/symbol
- Filter by segment/exchange
- Get instrument details
"""

import logging
import json
import hashlib
from typing import Optional, List
from fastapi import APIRouter, Query, HTTPException, Depends, Request
from pydantic import BaseModel

from app.database import DataManager
from app.jwt_auth import get_optional_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/instruments", tags=["instruments"])

# Global data manager (set by main.py)
_data_manager: Optional[DataManager] = None


def set_data_manager(dm: DataManager):
    """Set the data manager instance."""
    global _data_manager
    _data_manager = dm


async def get_data_manager() -> DataManager:
    """Dependency to get data manager."""
    if _data_manager is None:
        raise HTTPException(status_code=500, detail="Data manager not initialized")
    return _data_manager


# ========== Cache Helper Functions ==========

def _make_cache_key(prefix: str, **kwargs) -> str:
    """Create a cache key from prefix and kwargs."""
    # Sort kwargs for consistent keys
    sorted_items = sorted(kwargs.items())
    key_data = json.dumps(sorted_items, sort_keys=True)
    key_hash = hashlib.md5(key_data.encode()).hexdigest()[:12]
    return f"instruments:{prefix}:{key_hash}"


async def _get_cached(request: Request, cache_key: str):
    """Get value from Redis cache."""
    try:
        redis_client = request.app.state.redis_client
        cached = await redis_client.get(cache_key)
        if cached:
            return json.loads(cached)
    except Exception as e:
        logger.warning(f"Cache get failed: {e}")
    return None


async def _set_cached(request: Request, cache_key: str, value: dict, ttl: int = 300):
    """Set value in Redis cache with TTL."""
    try:
        redis_client = request.app.state.redis_client
        await redis_client.setex(cache_key, ttl, json.dumps(value))
    except Exception as e:
        logger.warning(f"Cache set failed: {e}")


# ========== Response Models ==========

class InstrumentSummary(BaseModel):
    """Summary information for an instrument."""
    instrument_token: int
    tradingsymbol: str
    name: Optional[str] = None
    segment: Optional[str] = None
    instrument_type: Optional[str] = None
    exchange: Optional[str] = None
    expiry: Optional[str] = None
    strike: Optional[float] = None
    lot_size: Optional[int] = None


class InstrumentDetail(InstrumentSummary):
    """Detailed instrument information."""
    tick_size: Optional[float] = None
    is_active: bool
    last_refreshed_at: Optional[str] = None


class InstrumentListResponse(BaseModel):
    """Response for instrument list queries."""
    status: str
    total: int
    instruments: List[InstrumentSummary]
    filters_applied: dict


class InstrumentStatsResponse(BaseModel):
    """Statistics about instruments in the registry."""
    status: str
    total_instruments: int
    active_instruments: int
    by_classification: dict
    by_segment: dict
    by_exchange: dict


# ========== Helper Functions ==========

def classify_instrument(instrument_type: str, segment: str) -> str:
    """
    Classify instrument into: stock, future, option, index, commodity

    Args:
        instrument_type: Type (EQ, FUT, CE, PE)
        segment: Segment (NSE, BSE, NFO-FUT, NFO-OPT, INDICES, etc.)

    Returns:
        Classification string
    """
    if segment == "INDICES":
        return "index"
    elif instrument_type == "EQ":
        return "stock"
    elif instrument_type == "FUT":
        if "MCX" in segment or "CDS" in segment:
            return "commodity"
        return "future"
    elif instrument_type in ["CE", "PE"]:
        if "MCX" in segment or "CDS" in segment:
            return "commodity_option"
        return "option"
    return "other"


async def build_instrument_query(
    dm: DataManager,
    classification: Optional[str] = None,
    segment: Optional[str] = None,
    segments: Optional[List[str]] = None,
    exchange: Optional[str] = None,
    instrument_type: Optional[str] = None,
    search: Optional[str] = None,
    only_active: bool = True,
    limit: int = 100,
    offset: int = 0
) -> tuple[str, list]:
    """
    Build SQL query and parameters for instrument filtering.

    Returns:
        Tuple of (query_string, parameters)
    """
    conditions = []
    params = []
    param_count = 1

    # Base condition: active instruments
    if only_active:
        conditions.append("is_active = true")

    # Filter by classification
    if classification:
        classification = classification.lower()
        if classification == "stock":
            conditions.append("instrument_type = 'EQ' AND segment IN ('NSE', 'BSE')")
        elif classification == "future":
            conditions.append("instrument_type = 'FUT' AND segment LIKE 'NFO-%'")
        elif classification == "option":
            conditions.append("instrument_type IN ('CE', 'PE') AND segment LIKE 'NFO-%'")
        elif classification == "index":
            conditions.append("segment = 'INDICES'")
        elif classification == "commodity":
            conditions.append("(segment LIKE 'MCX-%' OR segment LIKE 'CDS-%')")

    # Filter by segment (single)
    if segment and not segments:
        conditions.append(f"segment = ${param_count}")
        params.append(segment)
        param_count += 1

    # Filter by segments (multiple)
    if segments and len(segments) > 0:
        conditions.append(f"segment = ANY(${param_count})")
        params.append(segments)
        param_count += 1

    # Filter by exchange
    if exchange:
        conditions.append(f"exchange = ${param_count}")
        params.append(exchange)
        param_count += 1

    # Filter by instrument_type
    if instrument_type:
        conditions.append(f"instrument_type = ${param_count}")
        params.append(instrument_type)
        param_count += 1

    # Search by name or tradingsymbol
    if search:
        conditions.append(
            f"(tradingsymbol ILIKE ${param_count} OR name ILIKE ${param_count})"
        )
        params.append(f"%{search}%")
        param_count += 1

    # Build WHERE clause
    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

    # Build full query
    query = f"""
        SELECT
            instrument_token, tradingsymbol, name, segment,
            instrument_type, exchange, expiry, strike, lot_size
        FROM instrument_registry
        {where_clause}
        ORDER BY tradingsymbol
        LIMIT ${param_count} OFFSET ${param_count + 1}
    """
    params.extend([limit, offset])

    return query, params


async def build_instrument_count_query(
    dm: DataManager,
    classification: Optional[str] = None,
    segment: Optional[str] = None,
    segments: Optional[List[str]] = None,
    exchange: Optional[str] = None,
    instrument_type: Optional[str] = None,
    search: Optional[str] = None,
    only_active: bool = True
) -> tuple[str, list]:
    """
    Build SQL COUNT query and parameters for instrument filtering.
    Uses same filter logic as build_instrument_query but returns count.

    Returns:
        Tuple of (count_query_string, parameters)
    """
    conditions = []
    params = []
    param_count = 1

    # Base condition: active instruments
    if only_active:
        conditions.append("is_active = true")

    # Filter by classification
    if classification:
        classification = classification.lower()
        if classification == "stock":
            conditions.append("instrument_type = 'EQ' AND segment IN ('NSE', 'BSE')")
        elif classification == "future":
            conditions.append("instrument_type = 'FUT' AND segment LIKE 'NFO-%'")
        elif classification == "option":
            conditions.append("instrument_type IN ('CE', 'PE') AND segment LIKE 'NFO-%'")
        elif classification == "index":
            conditions.append("segment = 'INDICES'")
        elif classification == "commodity":
            conditions.append("(segment LIKE 'MCX-%' OR segment LIKE 'CDS-%')")

    # Filter by segment (single)
    if segment and not segments:
        conditions.append(f"segment = ${param_count}")
        params.append(segment)
        param_count += 1

    # Filter by segments (multiple)
    if segments and len(segments) > 0:
        conditions.append(f"segment = ANY(${param_count})")
        params.append(segments)
        param_count += 1

    # Filter by exchange
    if exchange:
        conditions.append(f"exchange = ${param_count}")
        params.append(exchange)
        param_count += 1

    # Filter by instrument_type
    if instrument_type:
        conditions.append(f"instrument_type = ${param_count}")
        params.append(instrument_type)
        param_count += 1

    # Search by name or tradingsymbol
    if search:
        conditions.append(
            f"(tradingsymbol ILIKE ${param_count} OR name ILIKE ${param_count})"
        )
        params.append(f"%{search}%")
        param_count += 1

    # Build WHERE clause
    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

    # Build count query (no ORDER BY, no LIMIT/OFFSET)
    count_query = f"""
        SELECT COUNT(*)
        FROM instrument_registry
        {where_clause}
    """

    return count_query, params


# ========== API Endpoints ==========

@router.get("/list", response_model=InstrumentListResponse)
async def list_instruments(
    request: Request,
    classification: Optional[str] = Query(
        None,
        description="Filter by classification: stock, future, option, index, commodity"
    ),
    segment: Optional[str] = Query(
        None,
        description="Filter by segment: NSE, BSE, NFO-FUT, NFO-OPT, INDICES, etc."
    ),
    segments: Optional[List[str]] = Query(
        None,
        description="Filter by multiple segments (e.g., segments=NSE&segments=BSE)"
    ),
    exchange: Optional[str] = Query(
        None,
        description="Filter by exchange: NSE, BSE, NFO, MCX, etc."
    ),
    instrument_type: Optional[str] = Query(
        None,
        description="Filter by type: EQ, FUT, CE, PE"
    ),
    search: Optional[str] = Query(
        None,
        description="Search by name or tradingsymbol (case-insensitive)"
    ),
    only_active: bool = Query(
        True,
        description="Only return active instruments"
    ),
    limit: int = Query(
        100,
        ge=1,
        le=1000,
        description="Maximum number of results to return"
    ),
    offset: int = Query(
        0,
        ge=0,
        description="Number of results to skip (for pagination)"
    ),
    dm: DataManager = Depends(get_data_manager),
    user: Optional[dict] = Depends(get_optional_user)
):
    """
    List and filter tradeable instruments from instrument_registry.

    **Examples**:

    - List all stocks: `?classification=stock`
    - List NSE stocks: `?classification=stock&segment=NSE`
    - Search for "RELIANCE": `?search=RELIANCE`
    - List NIFTY options: `?classification=option&search=NIFTY`
    - List futures: `?classification=future`
    - List indices: `?classification=index`

    **Pagination**:
    - Use `limit` and `offset` for pagination
    - Example: Page 2 with 50 per page: `?limit=50&offset=50`

    **Classifications**:
    - `stock`: Equity instruments (NSE, BSE)
    - `future`: Futures contracts (NFO-FUT)
    - `option`: Options contracts (NFO-OPT)
    - `index`: Market indices
    - `commodity`: Commodity instruments (MCX, CDS)
    """
    # Cache only for common queries (offset=0, reasonable limits)
    # Search queries change frequently, so cache them for shorter duration
    cache_enabled = offset == 0 and limit <= 100
    cache_key = None

    if cache_enabled:
        cache_key = _make_cache_key(
            "list",
            classification=classification,
            segment=segment,
            segments=segments,
            exchange=exchange,
            instrument_type=instrument_type,
            search=search,
            only_active=only_active,
            limit=limit
        )
        cached = await _get_cached(request, cache_key)
        if cached:
            logger.debug(f"Returning cached list (cache_key={cache_key[:50]}...)")
            return InstrumentListResponse(**cached)

    try:
        # Build query
        query, params = await build_instrument_query(
            dm=dm,
            classification=classification,
            segment=segment,
            segments=segments,
            exchange=exchange,
            instrument_type=instrument_type,
            search=search,
            only_active=only_active,
            limit=limit,
            offset=offset
        )

        # Execute query
        async with dm.pool.acquire() as conn:
            rows = await conn.fetch(query, *params)

        # Convert to response models
        instruments = [
            InstrumentSummary(
                instrument_token=row["instrument_token"],
                tradingsymbol=row["tradingsymbol"],
                name=row["name"],
                segment=row["segment"],
                instrument_type=row["instrument_type"],
                exchange=row["exchange"],
                expiry=row["expiry"],
                strike=row["strike"],
                lot_size=row["lot_size"]
            )
            for row in rows
        ]

        # Get total count (without limit/offset) using dedicated count query
        count_query, count_params = await build_instrument_count_query(
            dm=dm,
            classification=classification,
            segment=segment,
            segments=segments,
            exchange=exchange,
            instrument_type=instrument_type,
            search=search,
            only_active=only_active
        )
        async with dm.pool.acquire() as conn:
            count_result = await conn.fetchval(count_query, *count_params)

        result = {
            "status": "success",
            "total": count_result,
            "instruments": [inst.dict() for inst in instruments],
            "filters_applied": {
                "classification": classification,
                "segment": segment,
                "segments": segments,
                "exchange": exchange,
                "instrument_type": instrument_type,
                "search": search,
                "only_active": only_active,
                "limit": limit,
                "offset": offset
            }
        }

        # Cache result if enabled (5 minutes for searches, 15 minutes for filters)
        if cache_enabled and cache_key:
            ttl = 300 if search else 900
            await _set_cached(request, cache_key, result, ttl=ttl)

        return InstrumentListResponse(**result)

    except Exception as e:
        logger.error(f"Error listing instruments: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list instruments: {str(e)}")


@router.get("/detail/{instrument_token}", response_model=InstrumentDetail)
async def get_instrument_detail(
    instrument_token: int,
    dm: DataManager = Depends(get_data_manager),
    user: Optional[dict] = Depends(get_optional_user)
):
    """
    Get detailed information for a specific instrument.

    **Args**:
    - `instrument_token`: Unique instrument identifier

    **Returns**:
    - Complete instrument details including tick_size, is_active, last_refreshed_at
    """
    try:
        query = """
            SELECT
                instrument_token, tradingsymbol, name, segment, instrument_type,
                strike, expiry, tick_size, lot_size, exchange,
                is_active, last_refreshed_at
            FROM instrument_registry
            WHERE instrument_token = $1
        """

        async with dm.pool.acquire() as conn:
            row = await conn.fetchrow(query, instrument_token)

        if not row:
            raise HTTPException(status_code=404, detail=f"Instrument {instrument_token} not found")

        return InstrumentDetail(
            instrument_token=row["instrument_token"],
            tradingsymbol=row["tradingsymbol"],
            name=row["name"],
            segment=row["segment"],
            instrument_type=row["instrument_type"],
            exchange=row["exchange"],
            expiry=row["expiry"],
            strike=row["strike"],
            lot_size=row["lot_size"],
            tick_size=row["tick_size"],
            is_active=row["is_active"],
            last_refreshed_at=row["last_refreshed_at"].isoformat() if row["last_refreshed_at"] else None
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting instrument detail: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get instrument: {str(e)}")


@router.get("/stats", response_model=InstrumentStatsResponse)
async def get_instrument_stats(
    request: Request,
    dm: DataManager = Depends(get_data_manager),
    user: Optional[dict] = Depends(get_optional_user)
):
    """
    Get statistics about instruments in the registry.

    **Performance**: Cached for 1 hour, optimized single-query approach.

    **Returns**:
    - Total instruments count
    - Active instruments count
    - Breakdown by classification (stock, future, option, index, commodity)
    - Breakdown by segment
    - Breakdown by exchange
    """
    # Check cache first (cache for 1 hour)
    cache_key = _make_cache_key("stats")
    cached = await _get_cached(request, cache_key)
    if cached:
        logger.debug("Returning cached stats")
        return InstrumentStatsResponse(**cached)

    try:
        # Optimized single query with all aggregations
        query = """
            SELECT
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE is_active = true) as active,
                -- Segment breakdown
                jsonb_object_agg(
                    segment,
                    segment_count
                ) FILTER (WHERE segment IS NOT NULL) as segments,
                -- Exchange breakdown
                jsonb_object_agg(
                    exchange,
                    exchange_count
                ) FILTER (WHERE exchange IS NOT NULL AND exchange != '') as exchanges
            FROM (
                SELECT
                    segment,
                    exchange,
                    COUNT(*) FILTER (WHERE is_active = true) as segment_count,
                    COUNT(*) FILTER (WHERE is_active = true) as exchange_count
                FROM instrument_registry
                WHERE is_active = true
                GROUP BY GROUPING SETS ((segment), (exchange))
            ) sub
        """

        async with dm.pool.acquire() as conn:
            row = await conn.fetchrow(query)

        # Extract aggregated data
        total = row["total"]
        active = row["active"]
        by_segment = dict(row["segments"]) if row["segments"] else {}
        by_exchange = dict(row["exchanges"]) if row["exchanges"] else {}

        # Compute classification breakdown from segment data
        classification_query = """
            SELECT segment, instrument_type, COUNT(*) as count
            FROM instrument_registry
            WHERE is_active = true
            GROUP BY segment, instrument_type
        """

        async with dm.pool.acquire() as conn:
            type_rows = await conn.fetch(classification_query)

        by_classification = {
            "stock": 0,
            "future": 0,
            "option": 0,
            "index": 0,
            "commodity": 0,
            "commodity_option": 0,
            "other": 0
        }

        for type_row in type_rows:
            classification = classify_instrument(type_row["instrument_type"], type_row["segment"])
            by_classification[classification] += type_row["count"]

        result = {
            "status": "success",
            "total_instruments": total,
            "active_instruments": active,
            "by_classification": by_classification,
            "by_segment": by_segment,
            "by_exchange": by_exchange
        }

        # Cache for 1 hour (3600 seconds)
        await _set_cached(request, cache_key, result, ttl=3600)

        return InstrumentStatsResponse(**result)

    except Exception as e:
        logger.error(f"Error getting instrument stats: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")


@router.get("/search", response_model=InstrumentListResponse)
async def search_instruments(
    request: Request,
    q: str = Query(..., min_length=1, description="Search query (minimum 1 character)"),
    classification: Optional[str] = Query(None, description="Filter by classification"),
    limit: int = Query(20, ge=1, le=100, description="Maximum results"),
    dm: DataManager = Depends(get_data_manager),
    user: Optional[dict] = Depends(get_optional_user)
):
    """
    Search instruments by name or tradingsymbol.

    **Fast search endpoint** optimized for autocomplete/typeahead.

    **Examples**:
    - Search for "NIFTY": `?q=NIFTY`
    - Search stocks: `?q=RELI&classification=stock`
    - Search options: `?q=NIFTY&classification=option&limit=50`

    **Returns**:
    - Matching instruments sorted by relevance (exact matches first)
    """
    return await list_instruments(
        request=request,
        classification=classification,
        search=q,
        limit=limit,
        offset=0,
        only_active=True,
        dm=dm,
        user=user
    )


@router.get("/fo-enabled", response_model=InstrumentListResponse)
async def get_fo_enabled_stocks(
    request: Request,
    nse_only: bool = Query(
        True,
        description="If true and stock exists in both NSE and BSE, return only NSE"
    ),
    search: Optional[str] = Query(
        None,
        description="Search by name or tradingsymbol (case-insensitive, for type-ahead)"
    ),
    limit: int = Query(
        500,
        ge=1,
        le=2000,
        description="Maximum number of results to return"
    ),
    offset: int = Query(
        0,
        ge=0,
        description="Number of results to skip (for pagination)"
    ),
    dm: DataManager = Depends(get_data_manager),
    user: Optional[dict] = Depends(get_optional_user)
):
    """
    Get list of F&O-enabled stocks (stocks that have futures/options contracts).

    **How F&O stocks are identified**:
    - Stocks (instrument_type='EQ') that have corresponding derivatives in NFO segment
    - A stock is F&O-enabled if it has futures or options contracts listed

    **NSE vs BSE precedence**:
    - By default (`nse_only=true`), when a stock exists in both NSE and BSE, only NSE is returned
    - Set `nse_only=false` to get both NSE and BSE listings

    **Search filtering**:
    - Use `search` parameter for type-ahead functionality
    - Searches both tradingsymbol and name fields (case-insensitive)
    - Ideal for real-time filtering as user types

    **Examples**:
    - Get all F&O stocks (NSE only): `GET /instruments/fo-enabled`
    - Search F&O stocks: `GET /instruments/fo-enabled?search=RELI`
    - Type-ahead search: `GET /instruments/fo-enabled?search=NIFT&limit=20`
    - Get all F&O stocks (both exchanges): `GET /instruments/fo-enabled?nse_only=false`
    - Paginate results: `GET /instruments/fo-enabled?limit=100&offset=100`

    **Returns**:
    - List of equity instruments with F&O contracts
    - Each instrument includes: token, symbol, name, segment, exchange
    """
    # Cache key - include search in cache key, use offset=0 check for cache eligibility
    cache_enabled = offset == 0 and limit <= 500
    cache_key = None

    if cache_enabled:
        cache_key = _make_cache_key("fo_enabled", nse_only=nse_only, search=search, limit=limit)
        cached = await _get_cached(request, cache_key)
        if cached:
            logger.debug("Returning cached F&O enabled list")
            return InstrumentListResponse(**cached)

    try:
        # Build search condition
        search_condition = ""
        search_params = []
        param_offset = 1

        if search:
            search_condition = f"AND (i.tradingsymbol ILIKE ${param_offset} OR i.name ILIKE ${param_offset})"
            search_params = [f"%{search}%"]
            param_offset += 1

        # Query to get F&O-enabled stocks
        # NSE-only version uses DISTINCT ON to pick NSE over BSE
        # Note: F&O contracts use tradingsymbol as their 'name' field, so we join on i_eq.tradingsymbol = i_fo.name
        if nse_only:
            query = f"""
                WITH fo_stocks AS (
                    SELECT DISTINCT i_eq.tradingsymbol
                    FROM instrument_registry i_eq
                    INNER JOIN instrument_registry i_fo
                        ON i_eq.tradingsymbol = i_fo.name
                        AND i_fo.segment LIKE 'NFO-%'
                        AND i_fo.is_active = true
                    WHERE i_eq.instrument_type = 'EQ'
                      AND i_eq.is_active = true
                      AND i_eq.segment IN ('NSE', 'BSE')
                )
                SELECT DISTINCT ON (i.tradingsymbol)
                    i.instrument_token,
                    i.tradingsymbol,
                    i.name,
                    i.segment,
                    i.instrument_type,
                    i.exchange,
                    i.expiry,
                    i.strike,
                    i.lot_size
                FROM instrument_registry i
                INNER JOIN fo_stocks fs ON i.tradingsymbol = fs.tradingsymbol
                WHERE i.instrument_type = 'EQ'
                  AND i.is_active = true
                  AND i.segment IN ('NSE', 'BSE')
                  {search_condition}
                ORDER BY i.tradingsymbol,
                         CASE WHEN i.segment = 'NSE' THEN 0 ELSE 1 END,
                         i.tradingsymbol
                LIMIT ${param_offset} OFFSET ${param_offset + 1}
            """
            params = search_params + [limit, offset]
        else:
            # Return both NSE and BSE if available
            # Use same search_condition for consistency
            query = f"""
                SELECT DISTINCT
                    i_eq.instrument_token,
                    i_eq.tradingsymbol,
                    i_eq.name,
                    i_eq.segment,
                    i_eq.instrument_type,
                    i_eq.exchange,
                    i_eq.expiry,
                    i_eq.strike,
                    i_eq.lot_size
                FROM instrument_registry i_eq
                INNER JOIN instrument_registry i_fo
                    ON i_eq.tradingsymbol = i_fo.name
                    AND i_fo.segment LIKE 'NFO-%'
                    AND i_fo.is_active = true
                WHERE i_eq.instrument_type = 'EQ'
                  AND i_eq.is_active = true
                  AND i_eq.segment IN ('NSE', 'BSE')
                  {search_condition.replace('i.', 'i_eq.') if search else ''}
                ORDER BY i_eq.tradingsymbol, i_eq.segment, i_eq.tradingsymbol
                LIMIT ${param_offset} OFFSET ${param_offset + 1}
            """
            params = search_params + [limit, offset]

        # Execute query
        async with dm.pool.acquire() as conn:
            rows = await conn.fetch(query, *params)

        # Convert to response models
        instruments = [
            InstrumentSummary(
                instrument_token=row["instrument_token"],
                tradingsymbol=row["tradingsymbol"],
                name=row["name"],
                segment=row["segment"],
                instrument_type=row["instrument_type"],
                exchange=row["exchange"],
                expiry=row["expiry"],
                strike=row["strike"],
                lot_size=row["lot_size"]
            )
            for row in rows
        ]

        # Get total count (with search filter if applicable)
        if nse_only:
            count_query = f"""
                WITH fo_stocks AS (
                    SELECT DISTINCT i_eq.tradingsymbol
                    FROM instrument_registry i_eq
                    INNER JOIN instrument_registry i_fo
                        ON i_eq.tradingsymbol = i_fo.name
                        AND i_fo.segment LIKE 'NFO-%'
                        AND i_fo.is_active = true
                    WHERE i_eq.instrument_type = 'EQ'
                      AND i_eq.is_active = true
                      AND i_eq.segment IN ('NSE', 'BSE')
                )
                SELECT COUNT(DISTINCT i.tradingsymbol)
                FROM instrument_registry i
                INNER JOIN fo_stocks fs ON i.tradingsymbol = fs.tradingsymbol
                WHERE i.instrument_type = 'EQ'
                  AND i.is_active = true
                  AND i.segment IN ('NSE', 'BSE')
                  {search_condition}
            """
        else:
            count_query = f"""
                SELECT COUNT(DISTINCT i_eq.instrument_token)
                FROM instrument_registry i_eq
                INNER JOIN instrument_registry i_fo
                    ON i_eq.tradingsymbol = i_fo.name
                    AND i_fo.segment LIKE 'NFO-%'
                    AND i_fo.is_active = true
                WHERE i_eq.instrument_type = 'EQ'
                  AND i_eq.is_active = true
                  AND i_eq.segment IN ('NSE', 'BSE')
                  {search_condition.replace('i.', 'i_eq.') if search else ''}
            """

        async with dm.pool.acquire() as conn:
            count_result = await conn.fetchval(count_query, *search_params)

        result = {
            "status": "success",
            "total": count_result,
            "instruments": [inst.dict() for inst in instruments],
            "filters_applied": {
                "classification": "fo_enabled",
                "nse_only": nse_only,
                "segment": None,
                "segments": None,
                "exchange": None,
                "instrument_type": "EQ",
                "search": search,
                "only_active": True,
                "limit": limit,
                "offset": offset
            }
        }

        # Cache for shorter duration if search is active (5 min for search, 1 hour otherwise)
        if cache_enabled and cache_key:
            ttl = 300 if search else 3600
            await _set_cached(request, cache_key, result, ttl=ttl)

        return InstrumentListResponse(**result)

    except Exception as e:
        logger.error(f"Error getting F&O enabled stocks: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get F&O enabled stocks: {str(e)}")
