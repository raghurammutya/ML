"""
Strategy Management API Routes

Provides endpoints for:
- Strategy CRUD operations
- Strategy instrument management
- Strategy M2M history
- Strategy performance metrics
- Payoff graph calculations

Phase 2.5: Strategy System
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Path
from typing import List, Optional, Dict, Any
from datetime import datetime, date, timedelta
from decimal import Decimal
import logging

from ..database import get_db_pool
from ..dependencies import verify_jwt_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/strategies", tags=["strategies"])


# =============================================================================
# Request/Response Models
# =============================================================================

from pydantic import BaseModel, Field


class CreateStrategyRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200, description="Strategy name")
    description: Optional[str] = Field(None, description="Strategy description")
    tags: Optional[List[str]] = Field(default_factory=list, description="Strategy tags")


class UpdateStrategyRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    tags: Optional[List[str]] = None


class StrategyResponse(BaseModel):
    strategy_id: int
    name: str
    description: Optional[str]
    tags: List[str]
    status: str
    is_default: bool
    created_at: datetime
    updated_at: datetime
    archived_at: Optional[datetime]
    current_pnl: Decimal
    current_m2m: Decimal
    total_capital_deployed: Decimal
    total_margin_used: Decimal
    instrument_count: int


class AddInstrumentRequest(BaseModel):
    tradingsymbol: str = Field(..., description="Trading symbol (e.g., NIFTY25N0724500CE)")
    exchange: str = Field(..., description="Exchange (e.g., NFO, NSE)")
    direction: str = Field(..., pattern="^(BUY|SELL)$", description="BUY or SELL")
    quantity: int = Field(..., gt=0, description="Quantity")
    entry_price: Decimal = Field(..., gt=0, description="Entry price")
    notes: Optional[str] = Field(None, description="Optional notes")


class UpdateInstrumentRequest(BaseModel):
    quantity: Optional[int] = Field(None, gt=0)
    entry_price: Optional[Decimal] = Field(None, gt=0)
    notes: Optional[str] = None


class InstrumentResponse(BaseModel):
    id: int
    strategy_id: int
    tradingsymbol: str
    exchange: str
    direction: str
    quantity: int
    entry_price: Decimal
    current_price: Optional[Decimal]
    current_pnl: Optional[Decimal]
    added_at: datetime
    notes: Optional[str]


class M2MCandleResponse(BaseModel):
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal


class PerformanceMetricsResponse(BaseModel):
    metric_date: date
    day_pnl: Decimal
    cumulative_pnl: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: Decimal
    roi_percent: Decimal


# =============================================================================
# Helper Functions
# =============================================================================

async def get_trading_account_id(jwt_payload: Dict[str, Any], account_id_header: Optional[str]) -> str:
    """Extract trading account ID from JWT or header."""
    if account_id_header:
        return account_id_header

    # Try to get from JWT payload
    account_ids = jwt_payload.get('acct_ids', [])
    if not account_ids:
        raise HTTPException(status_code=400, detail="No trading account found")

    return account_ids[0]  # Use first account


async def verify_strategy_access(pool, strategy_id: int, trading_account_id: str):
    """Verify user has access to the strategy."""
    async with pool.acquire() as conn:
        result = await conn.fetchrow("""
            SELECT strategy_id FROM strategy
            WHERE strategy_id = $1 AND trading_account_id = $2
        """, strategy_id, trading_account_id)

        if not result:
            raise HTTPException(status_code=404, detail="Strategy not found or access denied")


# =============================================================================
# Strategy CRUD Endpoints
# =============================================================================

@router.post("", response_model=StrategyResponse, status_code=201)
async def create_strategy(
    request: CreateStrategyRequest,
    account_id: str = Query(..., description="Trading account ID"),
    jwt_payload: Dict[str, Any] = Depends(verify_jwt_token),
    pool=Depends(get_db_pool)
):
    """
    Create a new strategy.

    The strategy will be created for the specified trading account.
    """
    user_id = jwt_payload.get('sub', 'unknown')

    try:
        async with pool.acquire() as conn:
            # Check if strategy name already exists for this account
            existing = await conn.fetchrow("""
                SELECT strategy_id FROM strategy
                WHERE trading_account_id = $1 AND strategy_name = $2
            """, account_id, request.name)

            if existing:
                raise HTTPException(
                    status_code=409,
                    detail=f"Strategy with name '{request.name}' already exists"
                )

            # Create strategy
            result = await conn.fetchrow("""
                INSERT INTO strategy (
                    trading_account_id,
                    strategy_name,
                    strategy_type,
                    description,
                    tags,
                    is_default,
                    status,
                    is_active,
                    created_by
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                RETURNING strategy_id, strategy_name, description, tags, status,
                          is_default, created_at, updated_at, archived_at,
                          total_pnl, current_m2m, total_capital_deployed,
                          total_margin_used
            """, account_id, request.name, 'manual', request.description,
                 request.tags, False, 'active', True, user_id)

            # Get instrument count
            instrument_count = 0

            return StrategyResponse(
                strategy_id=result['strategy_id'],
                name=result['strategy_name'],
                description=result['description'],
                tags=result['tags'] or [],
                status=result['status'],
                is_default=result['is_default'],
                created_at=result['created_at'],
                updated_at=result['updated_at'],
                archived_at=result['archived_at'],
                current_pnl=result['total_pnl'] or Decimal('0'),
                current_m2m=result['current_m2m'] or Decimal('0'),
                total_capital_deployed=result['total_capital_deployed'] or Decimal('0'),
                total_margin_used=result['total_margin_used'] or Decimal('0'),
                instrument_count=instrument_count
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create strategy: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("", response_model=List[StrategyResponse])
async def list_strategies(
    account_id: str = Query(..., description="Trading account ID"),
    status: Optional[str] = Query(None, description="Filter by status"),
    jwt_payload: Dict[str, Any] = Depends(verify_jwt_token),
    pool=Depends(get_db_pool)
):
    """
    List all strategies for a trading account.

    Default strategy is always included and appears first in the list.
    """
    try:
        async with pool.acquire() as conn:
            query = """
                SELECT
                    s.strategy_id,
                    s.strategy_name,
                    s.description,
                    s.tags,
                    s.status,
                    s.is_default,
                    s.created_at,
                    s.updated_at,
                    s.archived_at,
                    s.total_pnl,
                    s.current_m2m,
                    s.total_capital_deployed,
                    s.total_margin_used,
                    COUNT(si.id) as instrument_count
                FROM strategy s
                LEFT JOIN strategy_instruments si ON s.strategy_id = si.strategy_id
                WHERE s.trading_account_id = $1
            """
            params = [account_id]

            if status:
                query += " AND s.status = $2"
                params.append(status)

            query += """
                GROUP BY s.strategy_id
                ORDER BY s.is_default DESC, s.created_at DESC
            """

            rows = await conn.fetch(query, *params)

            return [
                StrategyResponse(
                    strategy_id=row['strategy_id'],
                    name=row['strategy_name'],
                    description=row['description'],
                    tags=row['tags'] or [],
                    status=row['status'],
                    is_default=row['is_default'],
                    created_at=row['created_at'],
                    updated_at=row['updated_at'],
                    archived_at=row['archived_at'],
                    current_pnl=row['total_pnl'] or Decimal('0'),
                    current_m2m=row['current_m2m'] or Decimal('0'),
                    total_capital_deployed=row['total_capital_deployed'] or Decimal('0'),
                    total_margin_used=row['total_margin_used'] or Decimal('0'),
                    instrument_count=row['instrument_count']
                )
                for row in rows
            ]

    except Exception as e:
        logger.error(f"Failed to list strategies: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{strategy_id}", response_model=StrategyResponse)
async def get_strategy(
    strategy_id: int = Path(..., description="Strategy ID"),
    account_id: str = Query(..., description="Trading account ID"),
    jwt_payload: Dict[str, Any] = Depends(verify_jwt_token),
    pool=Depends(get_db_pool)
):
    """Get details of a specific strategy."""
    try:
        await verify_strategy_access(pool, strategy_id, account_id)

        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT
                    s.strategy_id,
                    s.strategy_name,
                    s.description,
                    s.tags,
                    s.status,
                    s.is_default,
                    s.created_at,
                    s.updated_at,
                    s.archived_at,
                    s.total_pnl,
                    s.current_m2m,
                    s.total_capital_deployed,
                    s.total_margin_used,
                    COUNT(si.id) as instrument_count
                FROM strategy s
                LEFT JOIN strategy_instruments si ON s.strategy_id = si.strategy_id
                WHERE s.strategy_id = $1
                GROUP BY s.strategy_id
            """, strategy_id)

            if not row:
                raise HTTPException(status_code=404, detail="Strategy not found")

            return StrategyResponse(
                strategy_id=row['strategy_id'],
                name=row['strategy_name'],
                description=row['description'],
                tags=row['tags'] or [],
                status=row['status'],
                is_default=row['is_default'],
                created_at=row['created_at'],
                updated_at=row['updated_at'],
                archived_at=row['archived_at'],
                current_pnl=row['total_pnl'] or Decimal('0'),
                current_m2m=row['current_m2m'] or Decimal('0'),
                total_capital_deployed=row['total_capital_deployed'] or Decimal('0'),
                total_margin_used=row['total_margin_used'] or Decimal('0'),
                instrument_count=row['instrument_count']
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get strategy: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{strategy_id}", response_model=StrategyResponse)
async def update_strategy(
    request: UpdateStrategyRequest,
    strategy_id: int = Path(..., description="Strategy ID"),
    account_id: str = Query(..., description="Trading account ID"),
    jwt_payload: Dict[str, Any] = Depends(verify_jwt_token),
    pool=Depends(get_db_pool)
):
    """Update strategy metadata (name, description, tags)."""
    try:
        await verify_strategy_access(pool, strategy_id, account_id)

        async with pool.acquire() as conn:
            # Check if it's a default strategy (cannot rename)
            is_default = await conn.fetchval("""
                SELECT is_default FROM strategy WHERE strategy_id = $1
            """, strategy_id)

            if is_default and request.name:
                raise HTTPException(
                    status_code=400,
                    detail="Cannot rename default strategy"
                )

            # Build UPDATE query dynamically
            updates = []
            params = []
            param_index = 1

            if request.name:
                updates.append(f"strategy_name = ${param_index}")
                params.append(request.name)
                param_index += 1

            if request.description is not None:
                updates.append(f"description = ${param_index}")
                params.append(request.description)
                param_index += 1

            if request.tags is not None:
                updates.append(f"tags = ${param_index}")
                params.append(request.tags)
                param_index += 1

            if not updates:
                # Nothing to update, just return current strategy
                return await get_strategy(strategy_id, account_id, jwt_payload, pool)

            params.append(strategy_id)
            query = f"""
                UPDATE strategy
                SET {', '.join(updates)}
                WHERE strategy_id = ${param_index}
            """

            await conn.execute(query, *params)

            # Return updated strategy
            return await get_strategy(strategy_id, account_id, jwt_payload, pool)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update strategy: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{strategy_id}")
async def archive_strategy(
    strategy_id: int = Path(..., description="Strategy ID"),
    account_id: str = Query(..., description="Trading account ID"),
    jwt_payload: Dict[str, Any] = Depends(verify_jwt_token),
    pool=Depends(get_db_pool)
):
    """
    Archive a strategy.

    Default strategy cannot be archived.
    Archived strategies remain in database for historical tracking.
    """
    try:
        await verify_strategy_access(pool, strategy_id, account_id)

        async with pool.acquire() as conn:
            # Check if it's a default strategy
            is_default = await conn.fetchval("""
                SELECT is_default FROM strategy WHERE strategy_id = $1
            """, strategy_id)

            if is_default:
                raise HTTPException(
                    status_code=400,
                    detail="Cannot archive default strategy"
                )

            # Archive strategy
            await conn.execute("""
                UPDATE strategy
                SET status = 'archived',
                    is_active = FALSE,
                    archived_at = NOW()
                WHERE strategy_id = $1
            """, strategy_id)

            return {
                "strategy_id": strategy_id,
                "status": "archived",
                "archived_at": datetime.utcnow()
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to archive strategy: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Strategy Instruments Endpoints (Part 1 - will continue in next response)
# =============================================================================

@router.post("/{strategy_id}/instruments", response_model=InstrumentResponse, status_code=201)
async def add_instrument(
    request: AddInstrumentRequest,
    strategy_id: int = Path(..., description="Strategy ID"),
    account_id: str = Query(..., description="Trading account ID"),
    jwt_payload: Dict[str, Any] = Depends(verify_jwt_token),
    pool=Depends(get_db_pool)
):
    """Add an instrument to a strategy manually."""
    try:
        await verify_strategy_access(pool, strategy_id, account_id)

        async with pool.acquire() as conn:
            result = await conn.fetchrow("""
                INSERT INTO strategy_instruments (
                    strategy_id, tradingsymbol, exchange, direction,
                    quantity, entry_price, notes
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                RETURNING id, strategy_id, tradingsymbol, exchange, direction,
                          quantity, entry_price, current_price, current_pnl,
                          added_at, notes
            """, strategy_id, request.tradingsymbol, request.exchange,
                 request.direction, request.quantity, request.entry_price,
                 request.notes)

            return InstrumentResponse(**dict(result))

    except Exception as e:
        logger.error(f"Failed to add instrument: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{strategy_id}/instruments", response_model=List[InstrumentResponse])
async def list_instruments(
    strategy_id: int = Path(..., description="Strategy ID"),
    account_id: str = Query(..., description="Trading account ID"),
    jwt_payload: Dict[str, Any] = Depends(verify_jwt_token),
    pool=Depends(get_db_pool)
):
    """List all instruments in a strategy."""
    try:
        await verify_strategy_access(pool, strategy_id, account_id)

        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, strategy_id, tradingsymbol, exchange, direction,
                       quantity, entry_price, current_price, current_pnl,
                       added_at, notes
                FROM strategy_instruments
                WHERE strategy_id = $1
                ORDER BY added_at DESC
            """, strategy_id)

            return [InstrumentResponse(**dict(row)) for row in rows]

    except Exception as e:
        logger.error(f"Failed to list instruments: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{strategy_id}/instruments/{instrument_id}")
async def remove_instrument(
    strategy_id: int = Path(..., description="Strategy ID"),
    instrument_id: int = Path(..., description="Instrument ID"),
    account_id: str = Query(..., description="Trading account ID"),
    jwt_payload: Dict[str, Any] = Depends(verify_jwt_token),
    pool=Depends(get_db_pool)
):
    """Remove an instrument from a strategy."""
    try:
        await verify_strategy_access(pool, strategy_id, account_id)

        async with pool.acquire() as conn:
            result = await conn.execute("""
                DELETE FROM strategy_instruments
                WHERE id = $1 AND strategy_id = $2
            """, instrument_id, strategy_id)

            if result == "DELETE 0":
                raise HTTPException(status_code=404, detail="Instrument not found")

            return {"success": True, "message": "Instrument removed"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to remove instrument: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Strategy M2M History
# =============================================================================

@router.get("/{strategy_id}/m2m", response_model=List[M2MCandleResponse])
async def get_m2m_history(
    strategy_id: int = Path(..., description="Strategy ID"),
    account_id: str = Query(..., description="Trading account ID"),
    from_time: datetime = Query(..., description="Start time"),
    to_time: datetime = Query(..., description="End time"),
    jwt_payload: Dict[str, Any] = Depends(verify_jwt_token),
    pool=Depends(get_db_pool)
):
    """Get minute-wise M2M history for a strategy."""
    try:
        await verify_strategy_access(pool, strategy_id, account_id)

        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT timestamp, open, high, low, close
                FROM strategy_m2m_candles
                WHERE strategy_id = $1
                  AND timestamp >= $2
                  AND timestamp <= $3
                ORDER BY timestamp ASC
            """, strategy_id, from_time, to_time)

            return [M2MCandleResponse(**dict(row)) for row in rows]

    except Exception as e:
        logger.error(f"Failed to get M2M history: {e}")
        raise HTTPException(status_code=500, detail=str(e))
