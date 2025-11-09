"""
Calendar Admin API - Holiday Management
Provides CRUD operations for managing holidays and special trading sessions

Version: 1.0
Features:
- Create/Update/Delete holidays
- Bulk import from CSV/JSON
- API key authentication
- Automatic cache invalidation
- Audit logging
"""

from fastapi import APIRouter, Depends, HTTPException, Header
from datetime import date, time as time_type
from typing import Optional, List
from pydantic import BaseModel, validator
import asyncpg
import logging
import csv
import io
import os

from app.database import DataManager

logger = logging.getLogger(__name__)

try:
    from fastapi import UploadFile, File
    UPLOAD_AVAILABLE = True
except ImportError:
    UPLOAD_AVAILABLE = False
    logger.warning("python-multipart not installed - bulk import disabled")

router = APIRouter(prefix="/admin/calendar", tags=["admin"])

# API Key for authentication - MUST be set in environment
API_KEY = os.getenv("CALENDAR_ADMIN_API_KEY")

# Validate API key is properly configured
if not API_KEY:
    raise RuntimeError(
        "CALENDAR_ADMIN_API_KEY environment variable must be set. "
        "Application cannot start without a strong admin API key."
    )

if API_KEY == "change-me-in-production" or len(API_KEY) < 32:
    raise RuntimeError(
        "CALENDAR_ADMIN_API_KEY must be at least 32 characters and cannot use default value. "
        f"Current length: {len(API_KEY)}"
    )

# Global data manager
_data_manager: Optional[DataManager] = None

def set_data_manager(dm: DataManager):
    global _data_manager
    _data_manager = dm

async def get_dm() -> DataManager:
    if not _data_manager:
        raise HTTPException(status_code=503, detail="Admin service not available")
    return _data_manager


# =====================================================
# AUTHENTICATION
# =====================================================

async def verify_api_key(x_api_key: str = Header(...)):
    """Verify API key for admin operations"""
    if x_api_key != API_KEY:
        logger.warning(f"Invalid API key attempt")
        raise HTTPException(
            status_code=401,
            detail="Invalid API key"
        )
    return x_api_key


# =====================================================
# MODELS
# =====================================================

class HolidayCreate(BaseModel):
    calendar: str
    date: date
    name: str
    event_type: str = "holiday"  # 'holiday', 'special_hours'
    is_trading_day: bool = False
    special_start: Optional[time_type] = None
    special_end: Optional[time_type] = None
    category: str = "market_holiday"
    description: Optional[str] = None

    @validator('event_type')
    def validate_event_type(cls, v):
        allowed = ['holiday', 'special_hours', 'early_close', 'extended_hours']
        if v not in allowed:
            raise ValueError(f"event_type must be one of {allowed}")
        return v

    @validator('special_start', 'special_end')
    def validate_special_hours(cls, v, values):
        if values.get('event_type') == 'special_hours' and v is None:
            raise ValueError("special_start and special_end required for special_hours events")
        return v


class HolidayUpdate(BaseModel):
    name: Optional[str] = None
    event_type: Optional[str] = None
    is_trading_day: Optional[bool] = None
    special_start: Optional[time_type] = None
    special_end: Optional[time_type] = None
    category: Optional[str] = None
    description: Optional[str] = None


class HolidayResponse(BaseModel):
    id: int
    calendar: str
    date: date
    name: str
    event_type: str
    is_trading_day: bool
    special_start: Optional[time_type]
    special_end: Optional[time_type]
    category: str
    description: Optional[str]
    created_at: str


# =====================================================
# ADMIN ENDPOINTS
# =====================================================

@router.post("/holidays", response_model=HolidayResponse)
async def create_holiday(
    holiday: HolidayCreate,
    dm: DataManager = Depends(get_dm),
    api_key: str = Depends(verify_api_key)
):
    """
    Create a new holiday or special trading session

    Requires X-API-Key header for authentication

    Examples:
    - Regular holiday: is_trading_day=false
    - Muhurat trading: event_type='special_hours', special_start='18:15', special_end='19:15'
    - Early close: event_type='early_close', special_end='13:00'
    """
    try:
        async with dm.pool.acquire() as conn:
            # Get calendar type ID
            calendar_id = await conn.fetchval(
                "SELECT id FROM calendar_types WHERE code = $1",
                holiday.calendar.upper()
            )

            if not calendar_id:
                raise HTTPException(status_code=404, detail=f"Calendar '{holiday.calendar}' not found")

            # Check for duplicates
            existing = await conn.fetchval("""
                SELECT id FROM calendar_events
                WHERE calendar_type_id = $1 AND event_date = $2 AND event_name = $3
            """, calendar_id, holiday.date, holiday.name)

            if existing:
                raise HTTPException(
                    status_code=409,
                    detail=f"Holiday '{holiday.name}' already exists for {holiday.date}"
                )

            # Insert holiday
            result = await conn.fetchrow("""
                INSERT INTO calendar_events (
                    calendar_type_id, event_date, event_name, event_type,
                    is_trading_day, special_start, special_end,
                    category, description, source
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                RETURNING id, event_date, event_name, event_type,
                          is_trading_day, special_start, special_end,
                          category, description, created_at
            """,
                calendar_id, holiday.date, holiday.name, holiday.event_type,
                holiday.is_trading_day, holiday.special_start, holiday.special_end,
                holiday.category, holiday.description, "Admin API"
            )

            logger.info(
                f"Holiday created: {holiday.name} on {holiday.date} for {holiday.calendar} "
                f"(type: {holiday.event_type})"
            )

            return HolidayResponse(
                id=result['id'],
                calendar=holiday.calendar.upper(),
                date=result['event_date'],
                name=result['event_name'],
                event_type=result['event_type'],
                is_trading_day=result['is_trading_day'],
                special_start=result['special_start'],
                special_end=result['special_end'],
                category=result['category'],
                description=result['description'],
                created_at=str(result['created_at'])
            )

    except HTTPException:
        raise
    except asyncpg.PostgresError as e:
        logger.error(f"Database error creating holiday: {e}")
        raise HTTPException(status_code=503, detail="Database error")
    except Exception as e:
        logger.error(f"Error creating holiday: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/holidays/{holiday_id}", response_model=HolidayResponse)
async def get_holiday(
    holiday_id: int,
    dm: DataManager = Depends(get_dm),
    api_key: str = Depends(verify_api_key)
):
    """Get holiday by ID"""
    try:
        async with dm.pool.acquire() as conn:
            result = await conn.fetchrow("""
                SELECT ce.id, ct.code as calendar, ce.event_date, ce.event_name,
                       ce.event_type, ce.is_trading_day, ce.special_start,
                       ce.special_end, ce.category, ce.description, ce.created_at
                FROM calendar_events ce
                JOIN calendar_types ct ON ce.calendar_type_id = ct.id
                WHERE ce.id = $1
            """, holiday_id)

            if not result:
                raise HTTPException(status_code=404, detail="Holiday not found")

            return HolidayResponse(
                id=result['id'],
                calendar=result['calendar'],
                date=result['event_date'],
                name=result['event_name'],
                event_type=result['event_type'],
                is_trading_day=result['is_trading_day'],
                special_start=result['special_start'],
                special_end=result['special_end'],
                category=result['category'],
                description=result['description'],
                created_at=str(result['created_at'])
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching holiday: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/holidays/{holiday_id}", response_model=HolidayResponse)
async def update_holiday(
    holiday_id: int,
    update: HolidayUpdate,
    dm: DataManager = Depends(get_dm),
    api_key: str = Depends(verify_api_key)
):
    """Update existing holiday"""
    try:
        async with dm.pool.acquire() as conn:
            # Build update query dynamically
            updates = []
            values = []
            param_count = 1

            if update.name is not None:
                updates.append(f"event_name = ${param_count}")
                values.append(update.name)
                param_count += 1

            if update.event_type is not None:
                updates.append(f"event_type = ${param_count}")
                values.append(update.event_type)
                param_count += 1

            if update.is_trading_day is not None:
                updates.append(f"is_trading_day = ${param_count}")
                values.append(update.is_trading_day)
                param_count += 1

            if update.special_start is not None:
                updates.append(f"special_start = ${param_count}")
                values.append(update.special_start)
                param_count += 1

            if update.special_end is not None:
                updates.append(f"special_end = ${param_count}")
                values.append(update.special_end)
                param_count += 1

            if update.category is not None:
                updates.append(f"category = ${param_count}")
                values.append(update.category)
                param_count += 1

            if update.description is not None:
                updates.append(f"description = ${param_count}")
                values.append(update.description)
                param_count += 1

            if not updates:
                raise HTTPException(status_code=400, detail="No fields to update")

            # Add updated_at
            updates.append(f"updated_at = NOW()")

            # Add holiday_id to values
            values.append(holiday_id)

            query = f"""
                UPDATE calendar_events
                SET {', '.join(updates)}
                WHERE id = ${param_count}
                RETURNING id, event_date, event_name, event_type,
                          is_trading_day, special_start, special_end,
                          category, description, created_at, calendar_type_id
            """

            result = await conn.fetchrow(query, *values)

            if not result:
                raise HTTPException(status_code=404, detail="Holiday not found")

            # Get calendar code
            calendar_code = await conn.fetchval(
                "SELECT code FROM calendar_types WHERE id = $1",
                result['calendar_type_id']
            )

            logger.info(f"Holiday updated: ID {holiday_id}")

            return HolidayResponse(
                id=result['id'],
                calendar=calendar_code,
                date=result['event_date'],
                name=result['event_name'],
                event_type=result['event_type'],
                is_trading_day=result['is_trading_day'],
                special_start=result['special_start'],
                special_end=result['special_end'],
                category=result['category'],
                description=result['description'],
                created_at=str(result['created_at'])
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating holiday: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/holidays/{holiday_id}")
async def delete_holiday(
    holiday_id: int,
    dm: DataManager = Depends(get_dm),
    api_key: str = Depends(verify_api_key)
):
    """Delete holiday"""
    try:
        async with dm.pool.acquire() as conn:
            result = await conn.fetchrow(
                "DELETE FROM calendar_events WHERE id = $1 RETURNING event_name, event_date",
                holiday_id
            )

            if not result:
                raise HTTPException(status_code=404, detail="Holiday not found")

            logger.info(f"Holiday deleted: {result['event_name']} on {result['event_date']}")

            return {
                "status": "deleted",
                "holiday": result['event_name'],
                "date": str(result['event_date'])
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting holiday: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


if UPLOAD_AVAILABLE:
    @router.post("/holidays/bulk-import")
    async def bulk_import_holidays(
        file: UploadFile = File(...),
        calendar: str = "NSE",
        dm: DataManager = Depends(get_dm),
        api_key: str = Depends(verify_api_key)
    ):
        """
        Bulk import holidays from CSV file

        CSV Format:
        date,name,event_type,is_trading_day,special_start,special_end,category,description
        2026-01-26,Republic Day,holiday,false,,,market_holiday,National holiday
        2026-11-01,Muhurat Trading,special_hours,true,18:15,19:15,special_session,Diwali trading

        Returns summary of imported/updated/failed records
        """
        try:
            # Read file content
            content = await file.read()
            decoded = content.decode('utf-8')
            csv_reader = csv.DictReader(io.StringIO(decoded))

            imported = 0
            updated = 0
            failed = []

            async with dm.pool.acquire() as conn:
                # Get calendar type ID
                calendar_id = await conn.fetchval(
                    "SELECT id FROM calendar_types WHERE code = $1",
                    calendar.upper()
                )

                if not calendar_id:
                    raise HTTPException(status_code=404, detail=f"Calendar '{calendar}' not found")

                for row_num, row in enumerate(csv_reader, start=2):
                    try:
                        # Parse row
                        event_date = date.fromisoformat(row['date'])
                        event_name = row['name']
                        event_type = row.get('event_type', 'holiday')
                        is_trading_day = row.get('is_trading_day', 'false').lower() == 'true'

                        special_start = None
                        special_end = None
                        if row.get('special_start'):
                            h, m = row['special_start'].split(':')
                            special_start = time_type(int(h), int(m))
                        if row.get('special_end'):
                            h, m = row['special_end'].split(':')
                            special_end = time_type(int(h), int(m))

                        category = row.get('category', 'market_holiday')
                        description = row.get('description', '')

                        # Try to insert or update
                        result = await conn.execute("""
                            INSERT INTO calendar_events (
                                calendar_type_id, event_date, event_name, event_type,
                                is_trading_day, special_start, special_end,
                                category, description, source
                            )
                            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                            ON CONFLICT (calendar_type_id, event_date, event_name)
                            DO UPDATE SET
                                event_type = EXCLUDED.event_type,
                                is_trading_day = EXCLUDED.is_trading_day,
                                special_start = EXCLUDED.special_start,
                                special_end = EXCLUDED.special_end,
                                category = EXCLUDED.category,
                                description = EXCLUDED.description,
                                updated_at = NOW()
                        """,
                            calendar_id, event_date, event_name, event_type,
                            is_trading_day, special_start, special_end,
                            category, description, "Bulk Import"
                        )

                        if "INSERT" in result:
                            imported += 1
                        else:
                            updated += 1

                    except Exception as e:
                        failed.append({
                            "row": row_num,
                            "data": row,
                            "error": str(e)
                        })

            logger.info(
                f"Bulk import completed: {imported} imported, {updated} updated, "
                f"{len(failed)} failed for calendar {calendar}"
            )

            return {
                "status": "completed",
                "calendar": calendar.upper(),
                "imported": imported,
                "updated": updated,
                "failed": len(failed),
                "errors": failed[:10] if failed else []  # Return first 10 errors
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error in bulk import: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Bulk import failed: {str(e)}")
else:
    logger.warning("Bulk import endpoint disabled - install python-multipart to enable")
