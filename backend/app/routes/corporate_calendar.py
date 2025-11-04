"""
Corporate Calendar API Routes

Provides endpoints for querying corporate actions (dividends, bonus, splits, etc.)
"""

from fastapi import APIRouter, Depends, Query, HTTPException, Path
from datetime import date, datetime, timedelta
from typing import Optional, List
from pydantic import BaseModel, Field
from enum import Enum
import json as json_lib

from app.database import DataManager

router = APIRouter(prefix="/calendar/corporate-actions", tags=["corporate-calendar"])

# Global data manager
_data_manager: Optional[DataManager] = None


def set_data_manager(dm: DataManager):
    global _data_manager
    _data_manager = dm


async def get_dm() -> DataManager:
    if not _data_manager:
        raise HTTPException(status_code=503, detail="Data manager not available")
    return _data_manager


# =====================================================
# MODELS
# =====================================================

class ActionType(str, Enum):
    """Corporate action types"""
    DIVIDEND = "DIVIDEND"
    BONUS = "BONUS"
    SPLIT = "SPLIT"
    RIGHTS = "RIGHTS"
    AGM = "AGM"
    EGM = "EGM"
    BOOK_CLOSURE = "BOOK_CLOSURE"
    BUYBACK = "BUYBACK"
    MERGER = "MERGER"
    DEMERGER = "DEMERGER"


class ActionStatus(str, Enum):
    """Corporate action status"""
    ANNOUNCED = "announced"
    UPCOMING = "upcoming"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class Instrument(BaseModel):
    """Instrument/Symbol information"""
    id: int
    symbol: str
    company_name: str
    isin: Optional[str]
    nse_symbol: Optional[str]
    bse_code: Optional[int]
    exchange: str


class CorporateAction(BaseModel):
    """Corporate action details"""
    id: int
    instrument: Instrument
    action_type: str
    title: str

    # Dates
    ex_date: Optional[date] = None
    record_date: Optional[date] = None
    payment_date: Optional[date] = None
    announcement_date: Optional[date] = None
    effective_date: Optional[date] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None

    # Additional info
    action_data: dict = Field(default_factory=dict)
    description: Optional[str] = None
    purpose: Optional[str] = None

    # Metadata
    source: str
    status: str
    price_adjustment_factor: Optional[float] = None

    # Timestamps
    created_at: datetime
    updated_at: datetime


class CorporateActionSummary(BaseModel):
    """Summary of corporate actions"""
    total_actions: int
    by_type: dict
    date_range: dict


class UpcomingActionsResponse(BaseModel):
    """Response for upcoming actions endpoint"""
    summary: CorporateActionSummary
    actions: List[CorporateAction]


# Helper function to parse action_data
def parse_action_data(action_data):
    """Parse action_data from database (handles both dict and JSON string)"""
    if action_data is None:
        return {}
    if isinstance(action_data, str):
        try:
            return json_lib.loads(action_data)
        except:
            return {}
    return action_data


# =====================================================
# ENDPOINTS
# =====================================================

@router.get("/", response_model=List[CorporateAction])
async def get_corporate_actions(
    symbol: str = Query(..., description="Stock symbol (e.g., 'TCS', 'RELIANCE')"),
    from_date: Optional[date] = Query(None, description="Start date (default: 30 days ago)"),
    to_date: Optional[date] = Query(None, description="End date (default: 90 days ahead)"),
    action_type: Optional[ActionType] = Query(None, description="Filter by action type"),
    status: Optional[ActionStatus] = Query(None, description="Filter by status"),
    dm: DataManager = Depends(get_dm)
):
    """
    Get corporate actions for a specific symbol

    Example:
        GET /calendar/corporate-actions/?symbol=TCS&from_date=2025-01-01&to_date=2025-12-31
    """
    # Set default date range
    from_date = from_date or (date.today() - timedelta(days=30))
    to_date = to_date or (date.today() + timedelta(days=90))

    async with dm.pool.acquire() as conn:
        # Build query
        conditions = ["i.symbol = $1", "ca.ex_date >= $2", "ca.ex_date <= $3"]
        params = [symbol.upper(), from_date, to_date]
        param_idx = 4

        if action_type:
            conditions.append(f"ca.action_type = ${param_idx}")
            params.append(action_type.value)
            param_idx += 1

        if status:
            conditions.append(f"ca.status = ${param_idx}")
            params.append(status.value)
            param_idx += 1

        where_clause = " AND ".join(conditions)

        # Execute query
        results = await conn.fetch(f"""
            SELECT
                ca.*,
                i.id as instrument_id,
                i.symbol,
                i.company_name,
                i.isin,
                i.nse_symbol,
                i.bse_code,
                i.exchange
            FROM corporate_actions ca
            JOIN instruments i ON ca.instrument_id = i.id
            WHERE {where_clause}
            ORDER BY ca.ex_date ASC, ca.created_at DESC
        """, *params)

        # Format response
        actions = []
        for row in results:
            instrument = Instrument(
                id=row['instrument_id'],
                symbol=row['symbol'],
                company_name=row['company_name'],
                isin=row['isin'],
                nse_symbol=row['nse_symbol'],
                bse_code=row['bse_code'],
                exchange=row['exchange']
            )

            action = CorporateAction(
                id=row['id'],
                instrument=instrument,
                action_type=row['action_type'],
                title=row['title'],
                ex_date=row['ex_date'],
                record_date=row['record_date'],
                payment_date=row['payment_date'],
                announcement_date=row['announcement_date'],
                effective_date=row['effective_date'],
                start_date=row['start_date'],
                end_date=row['end_date'],
                action_data=parse_action_data(row['action_data']),
                description=row['description'],
                purpose=row['purpose'],
                source=row['source'],
                status=row['status'],
                price_adjustment_factor=float(row['price_adjustment_factor']) if row['price_adjustment_factor'] else None,
                created_at=row['created_at'],
                updated_at=row['updated_at']
            )
            actions.append(action)

        return actions


@router.get("/upcoming", response_model=UpcomingActionsResponse)
async def get_upcoming_actions(
    days: int = Query(30, ge=1, le=365, description="Number of days ahead to look"),
    action_type: Optional[ActionType] = Query(None, description="Filter by action type"),
    symbols: Optional[str] = Query(None, description="Comma-separated list of symbols to filter"),
    dm: DataManager = Depends(get_dm)
):
    """
    Get upcoming corporate actions for the next N days

    Example:
        GET /calendar/corporate-actions/upcoming?days=30&action_type=DIVIDEND
    """
    from_date = date.today()
    to_date = date.today() + timedelta(days=days)

    async with dm.pool.acquire() as conn:
        # Build query
        conditions = [
            "ca.ex_date >= $1",
            "ca.ex_date <= $2",
            "ca.status IN ('announced', 'upcoming')"
        ]
        params = [from_date, to_date]
        param_idx = 3

        if action_type:
            conditions.append(f"ca.action_type = ${param_idx}")
            params.append(action_type.value)
            param_idx += 1

        if symbols:
            symbol_list = [s.strip().upper() for s in symbols.split(',')]
            conditions.append(f"i.symbol = ANY(${param_idx})")
            params.append(symbol_list)
            param_idx += 1

        where_clause = " AND ".join(conditions)

        # Get actions
        results = await conn.fetch(f"""
            SELECT
                ca.*,
                i.id as instrument_id,
                i.symbol,
                i.company_name,
                i.isin,
                i.nse_symbol,
                i.bse_code,
                i.exchange,
                (ca.ex_date - CURRENT_DATE) as days_until
            FROM corporate_actions ca
            JOIN instruments i ON ca.instrument_id = i.id
            WHERE {where_clause}
            ORDER BY ca.ex_date ASC, i.symbol ASC
        """, *params)

        # Get summary statistics
        summary_result = await conn.fetchrow(f"""
            SELECT
                COUNT(*) as total_actions,
                jsonb_object_agg(action_type, count) as by_type
            FROM (
                SELECT
                    ca.action_type,
                    COUNT(*) as count
                FROM corporate_actions ca
                JOIN instruments i ON ca.instrument_id = i.id
                WHERE {where_clause}
                GROUP BY ca.action_type
            ) as type_counts
        """, *params)

        # Format actions
        actions = []
        for row in results:
            instrument = Instrument(
                id=row['instrument_id'],
                symbol=row['symbol'],
                company_name=row['company_name'],
                isin=row['isin'],
                nse_symbol=row['nse_symbol'],
                bse_code=row['bse_code'],
                exchange=row['exchange']
            )

            action = CorporateAction(
                id=row['id'],
                instrument=instrument,
                action_type=row['action_type'],
                title=row['title'],
                ex_date=row['ex_date'],
                record_date=row['record_date'],
                payment_date=row['payment_date'],
                announcement_date=row['announcement_date'],
                effective_date=row['effective_date'],
                start_date=row['start_date'],
                end_date=row['end_date'],
                action_data=parse_action_data(row['action_data']),
                description=row['description'],
                purpose=row['purpose'],
                source=row['source'],
                status=row['status'],
                price_adjustment_factor=float(row['price_adjustment_factor']) if row['price_adjustment_factor'] else None,
                created_at=row['created_at'],
                updated_at=row['updated_at']
            )
            actions.append(action)

        # Build summary
        summary = CorporateActionSummary(
            total_actions=summary_result['total_actions'] or 0,
            by_type=parse_action_data(summary_result['by_type']),  # Parse JSON string
            date_range={
                'from': from_date.isoformat(),
                'to': to_date.isoformat()
            }
        )

        return UpcomingActionsResponse(
            summary=summary,
            actions=actions
        )


@router.get("/by-date", response_model=List[CorporateAction])
async def get_actions_by_date(
    ex_date: date = Query(..., description="Ex-date to query"),
    action_type: Optional[ActionType] = Query(None, description="Filter by action type"),
    dm: DataManager = Depends(get_dm)
):
    """
    Get all corporate actions for a specific ex-date

    Example:
        GET /calendar/corporate-actions/by-date?ex_date=2025-06-15
    """
    async with dm.pool.acquire() as conn:
        # Build query
        conditions = ["ca.ex_date = $1"]
        params = [ex_date]

        if action_type:
            conditions.append("ca.action_type = $2")
            params.append(action_type.value)

        where_clause = " AND ".join(conditions)

        # Execute query
        results = await conn.fetch(f"""
            SELECT
                ca.*,
                i.id as instrument_id,
                i.symbol,
                i.company_name,
                i.isin,
                i.nse_symbol,
                i.bse_code,
                i.exchange
            FROM corporate_actions ca
            JOIN instruments i ON ca.instrument_id = i.id
            WHERE {where_clause}
            ORDER BY i.symbol ASC
        """, *params)

        # Format response
        actions = []
        for row in results:
            instrument = Instrument(
                id=row['instrument_id'],
                symbol=row['symbol'],
                company_name=row['company_name'],
                isin=row['isin'],
                nse_symbol=row['nse_symbol'],
                bse_code=row['bse_code'],
                exchange=row['exchange']
            )

            action = CorporateAction(
                id=row['id'],
                instrument=instrument,
                action_type=row['action_type'],
                title=row['title'],
                ex_date=row['ex_date'],
                record_date=row['record_date'],
                payment_date=row['payment_date'],
                announcement_date=row['announcement_date'],
                effective_date=row['effective_date'],
                start_date=row['start_date'],
                end_date=row['end_date'],
                action_data=parse_action_data(row['action_data']),
                description=row['description'],
                purpose=row['purpose'],
                source=row['source'],
                status=row['status'],
                price_adjustment_factor=float(row['price_adjustment_factor']) if row['price_adjustment_factor'] else None,
                created_at=row['created_at'],
                updated_at=row['updated_at']
            )
            actions.append(action)

        return actions


@router.get("/all", response_model=List[CorporateAction])
async def get_all_actions(
    from_date: date = Query(..., description="Start date"),
    to_date: date = Query(..., description="End date"),
    action_type: Optional[ActionType] = Query(None, description="Filter by action type"),
    limit: int = Query(100, ge=1, le=1000, description="Max results to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    dm: DataManager = Depends(get_dm)
):
    """
    Get all corporate actions across all symbols for a date range

    Example:
        GET /calendar/corporate-actions/all?from_date=2025-01-01&to_date=2025-01-31&limit=50
    """
    # Validate date range
    if (to_date - from_date).days > 365:
        raise HTTPException(
            status_code=400,
            detail="Date range cannot exceed 365 days"
        )

    async with dm.pool.acquire() as conn:
        # Build query
        conditions = ["ca.ex_date >= $1", "ca.ex_date <= $2"]
        params = [from_date, to_date]
        param_idx = 3

        if action_type:
            conditions.append(f"ca.action_type = ${param_idx}")
            params.append(action_type.value)
            param_idx += 1

        where_clause = " AND ".join(conditions)

        # Execute query
        results = await conn.fetch(f"""
            SELECT
                ca.*,
                i.id as instrument_id,
                i.symbol,
                i.company_name,
                i.isin,
                i.nse_symbol,
                i.bse_code,
                i.exchange
            FROM corporate_actions ca
            JOIN instruments i ON ca.instrument_id = i.id
            WHERE {where_clause}
            ORDER BY ca.ex_date ASC, i.symbol ASC
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """, *params, limit, offset)

        # Format response
        actions = []
        for row in results:
            instrument = Instrument(
                id=row['instrument_id'],
                symbol=row['symbol'],
                company_name=row['company_name'],
                isin=row['isin'],
                nse_symbol=row['nse_symbol'],
                bse_code=row['bse_code'],
                exchange=row['exchange']
            )

            action = CorporateAction(
                id=row['id'],
                instrument=instrument,
                action_type=row['action_type'],
                title=row['title'],
                ex_date=row['ex_date'],
                record_date=row['record_date'],
                payment_date=row['payment_date'],
                announcement_date=row['announcement_date'],
                effective_date=row['effective_date'],
                start_date=row['start_date'],
                end_date=row['end_date'],
                action_data=parse_action_data(row['action_data']),
                description=row['description'],
                purpose=row['purpose'],
                source=row['source'],
                status=row['status'],
                price_adjustment_factor=float(row['price_adjustment_factor']) if row['price_adjustment_factor'] else None,
                created_at=row['created_at'],
                updated_at=row['updated_at']
            )
            actions.append(action)

        return actions


@router.get("/{action_id}", response_model=CorporateAction)
async def get_action_by_id(
    action_id: int = Path(..., description="Corporate action ID"),
    dm: DataManager = Depends(get_dm)
):
    """
    Get specific corporate action by ID

    Example:
        GET /calendar/corporate-actions/12345
    """
    async with dm.pool.acquire() as conn:
        result = await conn.fetchrow("""
            SELECT
                ca.*,
                i.id as instrument_id,
                i.symbol,
                i.company_name,
                i.isin,
                i.nse_symbol,
                i.bse_code,
                i.exchange
            FROM corporate_actions ca
            JOIN instruments i ON ca.instrument_id = i.id
            WHERE ca.id = $1
        """, action_id)

        if not result:
            raise HTTPException(
                status_code=404,
                detail=f"Corporate action {action_id} not found"
            )

        # Format response
        instrument = Instrument(
            id=result['instrument_id'],
            symbol=result['symbol'],
            company_name=result['company_name'],
            isin=result['isin'],
            nse_symbol=result['nse_symbol'],
            bse_code=result['bse_code'],
            exchange=result['exchange']
        )

        action = CorporateAction(
            id=result['id'],
            instrument=instrument,
            action_type=result['action_type'],
            title=result['title'],
            ex_date=result['ex_date'],
            record_date=result['record_date'],
            payment_date=result['payment_date'],
            announcement_date=result['announcement_date'],
            effective_date=result['effective_date'],
            start_date=result['start_date'],
            end_date=result['end_date'],
            action_data=result['action_data'] or {},
            description=result['description'],
            purpose=result['purpose'],
            source=result['source'],
            status=result['status'],
            price_adjustment_factor=float(result['price_adjustment_factor']) if result['price_adjustment_factor'] else None,
            created_at=result['created_at'],
            updated_at=result['updated_at']
        )

        return action


# =====================================================
# INSTRUMENTS ENDPOINTS
# =====================================================

@router.get("/instruments/search", response_model=List[Instrument])
async def search_instruments(
    q: str = Query(..., min_length=1, description="Search query (symbol or company name)"),
    limit: int = Query(10, ge=1, le=100),
    dm: DataManager = Depends(get_dm)
):
    """
    Search for instruments by symbol or company name

    Example:
        GET /calendar/corporate-actions/instruments/search?q=TATA
    """
    async with dm.pool.acquire() as conn:
        results = await conn.fetch("""
            SELECT id, symbol, company_name, isin, nse_symbol, bse_code, exchange
            FROM instruments
            WHERE
                is_active = true
                AND (
                    symbol ILIKE $1
                    OR company_name ILIKE $1
                    OR nse_symbol ILIKE $1
                )
            ORDER BY
                CASE
                    WHEN symbol = $2 THEN 1
                    WHEN symbol ILIKE $3 THEN 2
                    ELSE 3
                END,
                symbol
            LIMIT $4
        """, f"%{q}%", q.upper(), f"{q.upper()}%", limit)

        return [Instrument(**dict(r)) for r in results]
