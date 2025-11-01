"""
Calendar Service API - Production-Ready Version
Provides market calendar, holidays, and trading hours information

Version: 2.0 (Production-Ready)
Changes:
- Added calendar code validation
- Added comprehensive error handling
- Added structured logging
- Added health check endpoint
- Added input validation
- Added caching layer
"""

from fastapi import APIRouter, Depends, Query, HTTPException
from datetime import date, datetime, time, timedelta
from typing import Optional, List, Dict
from pydantic import BaseModel, Field
import pytz
import asyncpg
import logging

from app.database import DataManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/calendar", tags=["calendar"])

# Global data manager
_data_manager: Optional[DataManager] = None

# In-memory cache for calendar validation (reduces DB queries)
_valid_calendars_cache: Optional[set] = None
_cache_timestamp: Optional[datetime] = None
CACHE_TTL_SECONDS = 300  # 5 minutes

def set_data_manager(dm: DataManager):
    global _data_manager
    _data_manager = dm
    logger.info("Calendar service: DataManager initialized")

async def get_dm() -> DataManager:
    if not _data_manager:
        logger.error("Calendar service: DataManager not available")
        raise HTTPException(status_code=503, detail="Calendar service unavailable")
    return _data_manager

IST = pytz.timezone('Asia/Kolkata')

# Allowed calendar codes (for validation)
VALID_CALENDAR_CODES = {'NSE', 'BSE', 'MCX', 'NCDEX', 'NSE_CURRENCY', 'BSE_CURRENCY'}

# Date validation limits
MIN_YEAR = 2020
MAX_YEAR = 2030


# =====================================================
# MODELS WITH VALIDATION
# =====================================================

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


class HealthStatus(BaseModel):
    status: str
    timestamp: datetime
    database: str
    calendars_available: int
    cache_status: str


# =====================================================
# VALIDATION HELPERS
# =====================================================

async def validate_calendar_code(calendar: str, dm: DataManager) -> str:
    """
    Validate calendar code exists in database

    Returns: Uppercase calendar code
    Raises: HTTPException 404 if invalid
    """
    calendar_upper = calendar.upper()

    # Quick check against known codes
    if calendar_upper not in VALID_CALENDAR_CODES:
        logger.warning(f"Invalid calendar code requested: {calendar}")
        raise HTTPException(
            status_code=404,
            detail=f"Calendar '{calendar}' not found. Valid calendars: {', '.join(sorted(VALID_CALENDAR_CODES))}"
        )

    # Verify in database (with caching)
    global _valid_calendars_cache, _cache_timestamp
    now = datetime.now(IST)

    # Refresh cache if expired
    if _valid_calendars_cache is None or _cache_timestamp is None or \
       (now - _cache_timestamp).total_seconds() > CACHE_TTL_SECONDS:
        try:
            async with dm.pool.acquire() as conn:
                result = await conn.fetch(
                    "SELECT code FROM calendar_types WHERE is_active = true"
                )
                _valid_calendars_cache = {row['code'] for row in result}
                _cache_timestamp = now
                logger.debug(f"Calendar cache refreshed: {len(_valid_calendars_cache)} calendars")
        except Exception as e:
            logger.error(f"Failed to refresh calendar cache: {e}")
            # Fall back to static list if DB fails
            _valid_calendars_cache = VALID_CALENDAR_CODES

    if calendar_upper not in _valid_calendars_cache:
        logger.warning(f"Calendar {calendar} not in active calendars")
        raise HTTPException(
            status_code=404,
            detail=f"Calendar '{calendar}' is not active or does not exist"
        )

    return calendar_upper


def validate_year(year: int) -> int:
    """Validate year is within reasonable bounds"""
    if year < MIN_YEAR or year > MAX_YEAR:
        raise HTTPException(
            status_code=400,
            detail=f"Year must be between {MIN_YEAR} and {MAX_YEAR}"
        )
    return year


def validate_date(check_date: date) -> date:
    """Validate date is within reasonable bounds"""
    if check_date.year < MIN_YEAR or check_date.year > MAX_YEAR:
        raise HTTPException(
            status_code=400,
            detail=f"Date year must be between {MIN_YEAR} and {MAX_YEAR}"
        )
    return check_date


# =====================================================
# HEALTH CHECK ENDPOINT
# =====================================================

@router.get("/health", response_model=HealthStatus)
async def health_check(dm: DataManager = Depends(get_dm)):
    """
    Health check endpoint for monitoring

    Returns:
        - Database connectivity status
        - Number of available calendars
        - Cache status
        - Current timestamp (IST)
    """
    try:
        async with dm.pool.acquire() as conn:
            # Test database connection
            await conn.fetchval("SELECT 1")

            # Count active calendars
            calendar_count = await conn.fetchval(
                "SELECT COUNT(*) FROM calendar_types WHERE is_active = true"
            )

            # Cache status
            cache_status = "active" if _valid_calendars_cache else "cold"

            logger.debug("Health check: OK")

            return HealthStatus(
                status="healthy",
                timestamp=datetime.now(IST),
                database="connected",
                calendars_available=calendar_count,
                cache_status=cache_status
            )
    except asyncpg.PostgresError as e:
        logger.error(f"Health check failed: Database error: {e}")
        raise HTTPException(
            status_code=503,
            detail="Database connection failed"
        )
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(
            status_code=503,
            detail="Service unavailable"
        )


# =====================================================
# MAIN ENDPOINTS
# =====================================================

@router.get("/status", response_model=MarketStatus)
async def get_market_status(
    calendar: str = Query("NSE", description="Calendar code (NSE, BSE, MCX, etc.)"),
    check_date: Optional[date] = Query(None, description="Date to check (default: today)"),
    dm: DataManager = Depends(get_dm)
):
    """
    Get market status for a specific calendar and date

    Returns:
        - Whether it's a trading day
        - Current session (pre-market, trading, post-market, closed)
        - Trading hours
        - Next trading day if closed

    Raises:
        404: Calendar not found
        400: Invalid date
        503: Service unavailable
    """
    try:
        # Validate inputs
        calendar_code = await validate_calendar_code(calendar, dm)
        check_date = validate_date(check_date or date.today())

        now_ist = datetime.now(IST)
        current_time = now_ist.time() if check_date == date.today() else None

        logger.debug(f"Market status requested: {calendar_code} on {check_date}")

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
            """, calendar_code, check_date)

            is_holiday = bool(holiday and not holiday['is_trading_day'])
            holiday_name = holiday['event_name'] if holiday else None

            # Get trading session
            session = await conn.fetchrow("""
                SELECT ts.trading_start, ts.trading_end
                FROM trading_sessions ts
                JOIN calendar_types ct ON ts.calendar_type_id = ct.id
                WHERE ct.code = $1 AND ts.session_type = 'regular'
            """, calendar_code)

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
                """, check_date, calendar_code)

            logger.info(
                f"Market status: {calendar_code} {check_date} - "
                f"trading={is_trading_day}, session={current_session}, "
                f"holiday={holiday_name or 'none'}"
            )

            return MarketStatus(
                calendar_code=calendar_code,
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

    except HTTPException:
        raise
    except asyncpg.PostgresError as e:
        logger.error(f"Database error in get_market_status: {e}")
        raise HTTPException(
            status_code=503,
            detail="Calendar service database error"
        )
    except Exception as e:
        logger.error(f"Unexpected error in get_market_status: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )


@router.get("/holidays", response_model=List[Holiday])
async def get_holidays(
    calendar: str = Query("NSE", description="Calendar code"),
    year: Optional[int] = Query(None, description="Year (default: current year)"),
    dm: DataManager = Depends(get_dm)
):
    """
    Get list of holidays for a calendar

    Raises:
        404: Calendar not found
        400: Invalid year
        503: Service unavailable
    """
    try:
        # Validate inputs
        calendar_code = await validate_calendar_code(calendar, dm)
        year = validate_year(year or datetime.now().year)

        logger.debug(f"Holidays requested: {calendar_code} year {year}")

        async with dm.pool.acquire() as conn:
            holidays = await conn.fetch("""
                SELECT ce.event_date, ce.event_name, ce.category, ct.code
                FROM calendar_events ce
                JOIN calendar_types ct ON ce.calendar_type_id = ct.id
                WHERE ct.code = $1
                AND EXTRACT(YEAR FROM ce.event_date) = $2
                AND ce.category = 'market_holiday'
                ORDER BY ce.event_date
            """, calendar_code, year)

            logger.info(f"Holidays found: {calendar_code} {year} - {len(holidays)} holidays")

            return [
                Holiday(
                    date=h['event_date'],
                    name=h['event_name'],
                    category=h['category'],
                    calendar_code=h['code']
                )
                for h in holidays
            ]

    except HTTPException:
        raise
    except asyncpg.PostgresError as e:
        logger.error(f"Database error in get_holidays: {e}")
        raise HTTPException(
            status_code=503,
            detail="Calendar service database error"
        )
    except Exception as e:
        logger.error(f"Unexpected error in get_holidays: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )


@router.get("/next-trading-day")
async def get_next_trading_day(
    calendar: str = Query("NSE", description="Calendar code"),
    after_date: Optional[date] = Query(None, description="Find next trading day after this date"),
    dm: DataManager = Depends(get_dm)
):
    """
    Get next trading day after a given date

    Raises:
        404: Calendar not found or no trading day found
        400: Invalid date
        503: Service unavailable
    """
    try:
        # Validate inputs
        calendar_code = await validate_calendar_code(calendar, dm)
        after_date = validate_date(after_date or date.today())

        logger.debug(f"Next trading day requested: {calendar_code} after {after_date}")

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
            """, after_date, calendar_code)

            if not next_day:
                logger.warning(f"No trading day found: {calendar_code} after {after_date}")
                raise HTTPException(
                    status_code=404,
                    detail="No trading day found in next 60 days"
                )

            logger.info(f"Next trading day: {calendar_code} after {after_date} -> {next_day}")

            return {
                "calendar": calendar_code,
                "after_date": after_date,
                "next_trading_day": next_day,
                "days_until": (next_day - after_date).days
            }

    except HTTPException:
        raise
    except asyncpg.PostgresError as e:
        logger.error(f"Database error in get_next_trading_day: {e}")
        raise HTTPException(
            status_code=503,
            detail="Calendar service database error"
        )
    except Exception as e:
        logger.error(f"Unexpected error in get_next_trading_day: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )


@router.get("/calendars")
async def list_calendars(dm: DataManager = Depends(get_dm)):
    """
    List all available calendar types

    Raises:
        503: Service unavailable
    """
    try:
        logger.debug("List calendars requested")

        async with dm.pool.acquire() as conn:
            calendars = await conn.fetch("""
                SELECT code, name, description, category
                FROM calendar_types
                WHERE is_active = true
                ORDER BY category, code
            """)

            logger.info(f"Calendars listed: {len(calendars)} active calendars")

            return [dict(c) for c in calendars]

    except asyncpg.PostgresError as e:
        logger.error(f"Database error in list_calendars: {e}")
        raise HTTPException(
            status_code=503,
            detail="Calendar service database error"
        )
    except Exception as e:
        logger.error(f"Unexpected error in list_calendars: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )
