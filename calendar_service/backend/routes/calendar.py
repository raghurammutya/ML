"""
Calendar Service API
Provides market calendar, holidays, and trading hours information

Endpoints:
- GET /calendar/status - Current market status
- GET /calendar/holidays - List holidays
- GET /calendar/trading-days - Get trading days in range
- POST /calendar/holidays - Add holiday (admin)
- GET /calendar/next-trading-day - Get next trading day
"""

from fastapi import APIRouter, Depends, Query, HTTPException
from datetime import date, datetime, time, timedelta
from typing import Optional, List
import asyncpg
from pydantic import BaseModel, Field
import pytz

from app.database import DataManager

router = APIRouter(prefix="/calendar", tags=["calendar"])

# Global data manager instance
_data_manager: Optional[DataManager] = None

def set_data_manager(dm: DataManager):
    """Set the data manager instance"""
    global _data_manager
    _data_manager = dm

async def get_data_manager() -> DataManager:
    """Get the data manager instance"""
    if not _data_manager:
        raise HTTPException(status_code=503, detail="Data manager not available")
    return _data_manager

IST = pytz.timezone('Asia/Kolkata')


# =====================================================
# MODELS
# =====================================================

class MarketStatus(BaseModel):
    """Current market status"""
    calendar_code: str
    date: date
    is_trading_day: bool
    is_holiday: bool
    is_weekend: bool
    current_session: str  # 'pre-market', 'trading', 'post-market', 'closed'
    holiday_name: Optional[str] = None

    # Trading hours
    session_start: Optional[time] = None
    session_end: Optional[time] = None
    pre_market_start: Optional[time] = None
    pre_market_end: Optional[time] = None
    post_market_start: Optional[time] = None
    post_market_end: Optional[time] = None

    # Next trading info
    next_trading_day: Optional[date] = None
    time_until_open: Optional[str] = None  # Human readable


class Holiday(BaseModel):
    """Holiday information"""
    date: date
    name: str
    category: str
    calendar_code: str
    is_trading_day: bool = False
    verified: bool = False


class TradingDay(BaseModel):
    """Trading day information"""
    date: date
    is_trading_day: bool
    session_type: str
    trading_start: Optional[time] = None
    trading_end: Optional[time] = None


class AddHolidayRequest(BaseModel):
    """Request to add a holiday"""
    calendar_code: str = Field(..., description="Calendar type (NSE, BSE, MCX, etc.)")
    date: date = Field(..., description="Holiday date")
    name: str = Field(..., description="Holiday name")
    category: str = Field(default="market_holiday", description="Category")
    is_trading_day: bool = Field(default=False, description="Is market open with special hours")
    special_start: Optional[time] = Field(None, description="Special session start time")
    special_end: Optional[time] = Field(None, description="Special session end time")


# =====================================================
# HELPER FUNCTIONS
# =====================================================

def get_current_session(
    current_time: time,
    pre_start: Optional[time],
    pre_end: Optional[time],
    trading_start: time,
    trading_end: time,
    post_start: Optional[time],
    post_end: Optional[time]
) -> str:
    """Determine current trading session based on time"""

    if pre_start and pre_end and pre_start <= current_time < pre_end:
        return "pre-market"

    if trading_start <= current_time < trading_end:
        return "trading"

    if post_start and post_end and post_start <= current_time < post_end:
        return "post-market"

    return "closed"


async def compute_market_status(
    pool: asyncpg.Pool,
    calendar_code: str,
    check_date: date,
    current_time: Optional[time] = None
) -> MarketStatus:
    """Compute market status for a given date and calendar"""

    async with pool.acquire() as conn:
        # Get calendar type
        calendar = await conn.fetchrow(
        "SELECT * FROM calendar_types WHERE code = $1 AND is_active = true",
        calendar_code
    )

    if not calendar:
        raise HTTPException(status_code=404, detail=f"Calendar {calendar_code} not found")

    # Check if it's a weekend
    day_of_week = check_date.weekday()  # 0=Monday, 6=Sunday
    is_weekend = day_of_week in [5, 6]  # Saturday, Sunday

    # Check for holiday/event
    event = await conn.fetchrow("""
        SELECT * FROM calendar_events
        WHERE calendar_type_id = $1
        AND event_date = $2
        ORDER BY is_trading_day DESC  -- Prefer trading day events
        LIMIT 1
    """, calendar['id'], check_date)

    # Get regular trading session
    session = await conn.fetchrow("""
        SELECT * FROM trading_sessions
        WHERE calendar_type_id = $1
        AND session_type = 'regular'
        AND is_active = true
        AND (applies_to_days IS NULL OR $2 = ANY(applies_to_days))
    """, calendar['id'], day_of_week + 1)  # SQL days: 1=Monday

    # Determine status
    is_holiday = bool(event and not event['is_trading_day'])
    is_trading_day = False
    holiday_name = None
    session_start = None
    session_end = None
    pre_start = None
    pre_end = None
    post_start = None
    post_end = None

    if event:
        holiday_name = event['event_name']

        if event['is_trading_day']:
            # Special trading day
            is_trading_day = True
            session_start = event['special_start']
            session_end = event['special_end']
        else:
            is_trading_day = False

    elif not is_weekend and session:
        # Regular trading day
        is_trading_day = True
        session_start = session['trading_start']
        session_end = session['trading_end']
        pre_start = session['pre_market_start']
        pre_end = session['pre_market_end']
        post_start = session['post_market_start']
        post_end = session['post_market_end']

    # Determine current session
    if current_time and is_trading_day and session_start and session_end:
        current_session = get_current_session(
            current_time,
            pre_start,
            pre_end,
            session_start,
            session_end,
            post_start,
            post_end
        )
    else:
        current_session = "closed"

    # Find next trading day
    next_trading_day = None
    if not is_trading_day:
        next_trading_day = await conn.fetchval("""
            WITH future_dates AS (
                SELECT generate_series($1::date + 1, $1::date + 30, '1 day'::interval)::date AS future_date
            )
            SELECT fd.future_date
            FROM future_dates fd
            LEFT JOIN calendar_events ce ON
                ce.calendar_type_id = $2
                AND ce.event_date = fd.future_date
                AND ce.is_trading_day = false
            WHERE EXTRACT(DOW FROM fd.future_date) NOT IN (0, 6)  -- Not weekend
            AND ce.id IS NULL  -- No holiday
            ORDER BY fd.future_date
            LIMIT 1
        """, check_date, calendar['id'])

    return MarketStatus(
        calendar_code=calendar_code,
        date=check_date,
        is_trading_day=is_trading_day,
        is_holiday=is_holiday,
        is_weekend=is_weekend,
        current_session=current_session,
        holiday_name=holiday_name,
        session_start=session_start,
        session_end=session_end,
        pre_market_start=pre_start,
        pre_market_end=pre_end,
        post_market_start=post_start,
        post_market_end=post_end,
        next_trading_day=next_trading_day,
    )


# =====================================================
# ENDPOINTS
# =====================================================

@router.get("/status", response_model=MarketStatus)
async def get_market_status(
    calendar: str = Query("NSE", description="Calendar code (NSE, BSE, MCX, etc.)"),
    check_date: Optional[date] = Query(None, description="Date to check (default: today)"),
    conn: asyncpg.Connection = Depends(get_db_connection)
):
    """
    Get market status for a specific calendar and date

    Returns:
        - Whether it's a trading day
        - Current session (pre-market, trading, post-market, closed)
        - Trading hours
        - Next trading day if closed
    """
    check_date = check_date or date.today()

    # Get current time in IST
    now_ist = datetime.now(IST)
    current_time = now_ist.time() if check_date == date.today() else None

    return await compute_market_status(conn, calendar.upper(), check_date, current_time)


@router.get("/holidays", response_model=List[Holiday])
async def get_holidays(
    calendar: str = Query("NSE", description="Calendar code"),
    year: Optional[int] = Query(None, description="Year (default: current year)"),
    from_date: Optional[date] = Query(None, description="Start date"),
    to_date: Optional[date] = Query(None, description="End date"),
    conn: asyncpg.Connection = Depends(get_db_connection)
):
    """
    Get list of holidays for a calendar

    Filter by year OR date range
    """
    # Get calendar ID
    calendar_id = await conn.fetchval(
        "SELECT id FROM calendar_types WHERE code = $1",
        calendar.upper()
    )

    if not calendar_id:
        raise HTTPException(status_code=404, detail=f"Calendar {calendar} not found")

    # Build query based on filters
    if from_date and to_date:
        query = """
            SELECT event_date, event_name, category, is_trading_day, verified
            FROM calendar_events
            WHERE calendar_type_id = $1
            AND event_date BETWEEN $2 AND $3
            AND is_trading_day = false
            ORDER BY event_date
        """
        params = [calendar_id, from_date, to_date]

    else:
        year = year or datetime.now().year
        query = """
            SELECT event_date, event_name, category, is_trading_day, verified
            FROM calendar_events
            WHERE calendar_type_id = $1
            AND EXTRACT(YEAR FROM event_date) = $2
            AND is_trading_day = false
            ORDER BY event_date
        """
        params = [calendar_id, year]

    holidays = await conn.fetch(query, *params)

    return [
        Holiday(
            date=h['event_date'],
            name=h['event_name'],
            category=h['category'],
            calendar_code=calendar.upper(),
            is_trading_day=h['is_trading_day'],
            verified=h['verified']
        )
        for h in holidays
    ]


@router.get("/trading-days", response_model=List[TradingDay])
async def get_trading_days(
    calendar: str = Query("NSE", description="Calendar code"),
    from_date: date = Query(..., description="Start date"),
    to_date: date = Query(..., description="End date"),
    conn: asyncpg.Connection = Depends(get_db_connection)
):
    """
    Get list of trading days in a date range

    Useful for backtesting and analysis
    """
    # Get calendar ID
    calendar_id = await conn.fetchval(
        "SELECT id FROM calendar_types WHERE code = $1",
        calendar.upper()
    )

    if not calendar_id:
        raise HTTPException(status_code=404, detail=f"Calendar {calendar} not found")

    # Generate all dates in range
    days = []
    current = from_date

    while current <= to_date:
        status = await compute_market_status(conn, calendar.upper(), current)

        days.append(TradingDay(
            date=current,
            is_trading_day=status.is_trading_day,
            session_type='regular' if status.is_trading_day else 'closed',
            trading_start=status.session_start,
            trading_end=status.session_end
        ))

        current += timedelta(days=1)

    return days


@router.get("/next-trading-day")
async def get_next_trading_day(
    calendar: str = Query("NSE", description="Calendar code"),
    after_date: Optional[date] = Query(None, description="Find next trading day after this date"),
    conn: asyncpg.Connection = Depends(get_db_connection)
):
    """Get next trading day after a given date (or today)"""

    after_date = after_date or date.today()

    # Get calendar ID
    calendar_id = await conn.fetchval(
        "SELECT id FROM calendar_types WHERE code = $1",
        calendar.upper()
    )

    if not calendar_id:
        raise HTTPException(status_code=404, detail=f"Calendar {calendar} not found")

    next_day = await conn.fetchval("""
        WITH future_dates AS (
            SELECT generate_series($1::date + 1, $1::date + 60, '1 day'::interval)::date AS future_date
        )
        SELECT fd.future_date
        FROM future_dates fd
        LEFT JOIN calendar_events ce ON
            ce.calendar_type_id = $2
            AND ce.event_date = fd.future_date
            AND ce.is_trading_day = false
        WHERE EXTRACT(DOW FROM fd.future_date) NOT IN (0, 6)  -- Not weekend
        AND ce.id IS NULL  -- No holiday
        ORDER BY fd.future_date
        LIMIT 1
    """, after_date, calendar_id)

    if not next_day:
        raise HTTPException(status_code=404, detail="No trading day found in next 60 days")

    return {
        "calendar": calendar.upper(),
        "after_date": after_date,
        "next_trading_day": next_day,
        "days_until": (next_day - after_date).days
    }


@router.post("/holidays", response_model=Holiday)
async def add_holiday(
    request: AddHolidayRequest,
    conn: asyncpg.Connection = Depends(get_db_connection)
):
    """
    Add or update a holiday (Admin endpoint)

    Use this to manually add holidays not in the official calendar
    or to override specific dates
    """
    # Get calendar ID
    calendar_id = await conn.fetchval(
        "SELECT id FROM calendar_types WHERE code = $1",
        request.calendar_code.upper()
    )

    if not calendar_id:
        raise HTTPException(
            status_code=404,
            detail=f"Calendar {request.calendar_code} not found"
        )

    # Insert or update
    await conn.execute("""
        INSERT INTO calendar_events (
            calendar_type_id,
            event_date,
            event_name,
            event_type,
            is_trading_day,
            category,
            special_start,
            special_end,
            source
        ) VALUES ($1, $2, $3, 'one_time', $4, $5, $6, $7, 'manual')
        ON CONFLICT (calendar_type_id, event_date, event_name)
        DO UPDATE SET
            is_trading_day = EXCLUDED.is_trading_day,
            category = EXCLUDED.category,
            special_start = EXCLUDED.special_start,
            special_end = EXCLUDED.special_end,
            updated_at = NOW()
    """,
        calendar_id,
        request.date,
        request.name,
        request.is_trading_day,
        request.category,
        request.special_start,
        request.special_end
    )

    return Holiday(
        date=request.date,
        name=request.name,
        category=request.category,
        calendar_code=request.calendar_code.upper(),
        is_trading_day=request.is_trading_day,
        verified=True
    )


@router.get("/calendars")
async def list_calendars(
    conn: asyncpg.Connection = Depends(get_db_connection)
):
    """List all available calendar types"""

    calendars = await conn.fetch("""
        SELECT code, name, description, category, is_active
        FROM calendar_types
        WHERE is_active = true
        ORDER BY category, code
    """)

    return [dict(c) for c in calendars]
