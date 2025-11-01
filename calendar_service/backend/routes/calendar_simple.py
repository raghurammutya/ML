"""
Calendar Service API - Simplified Version
Provides market calendar, holidays, and trading hours information
"""

from fastapi import APIRouter, Depends, Query, HTTPException
from datetime import date, datetime, time, timedelta
from typing import Optional, List
from pydantic import BaseModel
import pytz

from app.database import DataManager

router = APIRouter(prefix="/calendar", tags=["calendar"])

# Global data manager
_data_manager: Optional[DataManager] = None

def set_data_manager(dm: DataManager):
    global _data_manager
    _data_manager = dm

async def get_dm() -> DataManager:
    if not _data_manager:
        raise HTTPException(status_code=503, detail="Data manager not available")
    return _data_manager

IST = pytz.timezone('Asia/Kolkata')


# Models
class MarketStatus(BaseModel):
    calendar_code: str
    date: date
    is_trading_day: bool
    is_holiday: bool
    is_weekend: bool
    current_session: str
    holiday_name: Optional[str] = None
    session_start: Optional[time] = None
    session_end: Optional[time] = None
    next_trading_day: Optional[date] = None


class Holiday(BaseModel):
    date: date
    name: str
    category: str
    calendar_code: str


# Endpoints
@router.get("/status", response_model=MarketStatus)
async def get_market_status(
    calendar: str = Query("NSE", description="Calendar code"),
    check_date: Optional[date] = Query(None, description="Date to check"),
    dm: DataManager = Depends(get_dm)
):
    """Get current market status"""
    check_date = check_date or date.today()
    now_ist = datetime.now(IST)
    current_time = now_ist.time() if check_date == date.today() else None

    async with dm.pool.acquire() as conn:
        # Check if weekend
        day_of_week = check_date.weekday()
        is_weekend = day_of_week in [5, 6]

        # Get holiday info
        holiday = await conn.fetchrow("""
            SELECT event_name, is_trading_day
            FROM calendar_events ce
            JOIN calendar_types ct ON ce.calendar_type_id = ct.id
            WHERE ct.code = $1 AND ce.event_date = $2
            AND ce.category = 'market_holiday'
        """, calendar.upper(), check_date)

        is_holiday = bool(holiday and not holiday['is_trading_day'])
        holiday_name = holiday['event_name'] if holiday else None

        # Get trading session
        session = await conn.fetchrow("""
            SELECT ts.trading_start, ts.trading_end
            FROM trading_sessions ts
            JOIN calendar_types ct ON ts.calendar_type_id = ct.id
            WHERE ct.code = $1 AND ts.session_type = 'regular'
        """, calendar.upper())

        is_trading_day = not is_weekend and not is_holiday

        # Determine current session
        current_session = "closed"
        if is_trading_day and current_time and session:
            if session['trading_start'] <= current_time < session['trading_end']:
                current_session = "trading"

        # Get next trading day
        next_trading = None
        if not is_trading_day:
            next_trading = await conn.fetchval("""
                WITH future_dates AS (
                    SELECT generate_series($1::date + 1, $1::date + 30, '1 day'::interval)::date AS d
                )
                SELECT fd.d
                FROM future_dates fd
                LEFT JOIN calendar_events ce ON
                    ce.event_date = fd.d
                    AND ce.calendar_type_id = (SELECT id FROM calendar_types WHERE code = $2)
                    AND ce.is_trading_day = false
                WHERE EXTRACT(DOW FROM fd.d) NOT IN (0, 6)
                AND ce.id IS NULL
                ORDER BY fd.d
                LIMIT 1
            """, check_date, calendar.upper())

        return MarketStatus(
            calendar_code=calendar.upper(),
            date=check_date,
            is_trading_day=is_trading_day,
            is_holiday=is_holiday,
            is_weekend=is_weekend,
            current_session=current_session,
            holiday_name=holiday_name,
            session_start=session['trading_start'] if session else None,
            session_end=session['trading_end'] if session else None,
            next_trading_day=next_trading
        )


@router.get("/holidays", response_model=List[Holiday])
async def get_holidays(
    calendar: str = Query("NSE"),
    year: Optional[int] = Query(None),
    dm: DataManager = Depends(get_dm)
):
    """Get list of holidays"""
    year = year or datetime.now().year

    async with dm.pool.acquire() as conn:
        holidays = await conn.fetch("""
            SELECT ce.event_date, ce.event_name, ce.category, ct.code
            FROM calendar_events ce
            JOIN calendar_types ct ON ce.calendar_type_id = ct.id
            WHERE ct.code = $1
            AND EXTRACT(YEAR FROM ce.event_date) = $2
            AND ce.category = 'market_holiday'
            ORDER BY ce.event_date
        """, calendar.upper(), year)

        return [
            Holiday(
                date=h['event_date'],
                name=h['event_name'],
                category=h['category'],
                calendar_code=h['code']
            )
            for h in holidays
        ]


@router.get("/next-trading-day")
async def get_next_trading_day(
    calendar: str = Query("NSE"),
    after_date: Optional[date] = Query(None),
    dm: DataManager = Depends(get_dm)
):
    """Get next trading day"""
    after_date = after_date or date.today()

    async with dm.pool.acquire() as conn:
        next_day = await conn.fetchval("""
            WITH future_dates AS (
                SELECT generate_series($1::date + 1, $1::date + 60, '1 day'::interval)::date AS d
            )
            SELECT fd.d
            FROM future_dates fd
            LEFT JOIN calendar_events ce ON
                ce.event_date = fd.d
                AND ce.calendar_type_id = (SELECT id FROM calendar_types WHERE code = $2)
                AND ce.is_trading_day = false
            WHERE EXTRACT(DOW FROM fd.d) NOT IN (0, 6)
            AND ce.id IS NULL
            ORDER BY fd.d
            LIMIT 1
        """, after_date, calendar.upper())

        if not next_day:
            raise HTTPException(status_code=404, detail="No trading day found in next 60 days")

        return {
            "calendar": calendar.upper(),
            "after_date": after_date,
            "next_trading_day": next_day,
            "days_until": (next_day - after_date).days
        }


@router.get("/calendars")
async def list_calendars(dm: DataManager = Depends(get_dm)):
    """List available calendars"""
    async with dm.pool.acquire() as conn:
        calendars = await conn.fetch("""
            SELECT code, name, description, category
            FROM calendar_types
            WHERE is_active = true
            ORDER BY category, code
        """)
        return [dict(c) for c in calendars]
