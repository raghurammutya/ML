# Implementation Prompt: Phase 2.5 Strategy System Completion (Weeks 4-12)

**Priority**: P1 (Feature Completion)
**Estimated Duration**: 29-40 hours (6-8 weeks, 1-2 engineers)
**Prerequisites**: Security remediation + Critical testing complete
**Blocking**: Full feature parity (not blocking production)

---

## Objective

Complete the **Phase 2.5 Strategy System** implementation (currently 70% incomplete) to enable users to create, manage, and monitor multi-instrument F&O trading strategies with real-time P&L tracking.

**Current State**: Design documents exist, zero implementation
**Target State**: Fully functional strategy system with 7 frontend components and backend APIs

**Success Criteria**: Users can create strategies, add instruments, view real-time M2M, and export P&L reports.

---

## Context

**Working Directory**: `/mnt/stocksblitz-data/Quantagro/tradingview-viz/backend`
**Reference**: `/docs/assessment_1/pending_requirements.md`
**Planning Docs**:
- `PHASE_2.5_DAY3_IMPLEMENTATION_PROMPT.md`
- `PHASE_2.5_DAY4_DESIGN.md`
- `PHASE_2.5_STRATEGY_SYSTEM_PLAN.md`

**Current Completion**: 30% (design docs only)
**Estimated Effort**: 29-40 hours total

---

## Missing Components (70% Incomplete)

### Backend (12-18 hours)
1. Database migrations: 4 new tables (2 hours)
2. Backend routes: 10+ API endpoints (8-10 hours)
3. M2M calculation worker (2-3 hours)
4. WebSocket streaming (1-2 hours)

### Frontend (17-22 hours)
1. StrategySelector component (2-3 hours)
2. CreateStrategyModal component (3-4 hours)
3. AddInstrumentModal component (3-4 hours)
4. StrategyInstrumentsPanel component (3-4 hours)
5. StrategyPnlPanel component (2-3 hours)
6. StrategyM2MChart component (4-6 hours)

---

## Task 1: Database Migrations (4 tables) - Day 1-2

### Migration 025: Create strategies table

```sql
-- migrations/025_create_strategies_table.sql
CREATE TABLE IF NOT EXISTS strategies (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    account_id INTEGER,  -- Optional: link to trading account
    name VARCHAR(100) NOT NULL,
    description TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    target_profit DECIMAL(15, 2),  -- Optional target profit
    stop_loss DECIMAL(15, 2),      -- Optional stop loss
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT strategies_status_check CHECK (status IN ('active', 'closed', 'archived')),
    CONSTRAINT strategies_user_id_fk FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX idx_strategies_user_id ON strategies(user_id);
CREATE INDEX idx_strategies_account_id ON strategies(account_id);
CREATE INDEX idx_strategies_status ON strategies(status);

COMMENT ON TABLE strategies IS 'User-defined multi-instrument F&O trading strategies';
COMMENT ON COLUMN strategies.status IS 'active: Strategy is active and tracked, closed: Strategy completed, archived: Soft deleted';
```

### Migration 026: Create strategy_instruments table

```sql
-- migrations/026_create_strategy_instruments_table.sql
CREATE TABLE IF NOT EXISTS strategy_instruments (
    id SERIAL PRIMARY KEY,
    strategy_id INTEGER NOT NULL,
    instrument_token BIGINT NOT NULL,
    tradingsymbol VARCHAR(50) NOT NULL,
    segment VARCHAR(10) NOT NULL,  -- 'FO' for F&O
    direction VARCHAR(4) NOT NULL,  -- 'BUY' or 'SELL'
    quantity INTEGER NOT NULL,
    entry_price DECIMAL(15, 2) NOT NULL,
    entry_time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    exit_price DECIMAL(15, 2),
    exit_time TIMESTAMPTZ,
    realized_pnl DECIMAL(15, 2),  -- Filled when position is exited
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT strategy_instruments_strategy_id_fk FOREIGN KEY (strategy_id) REFERENCES strategies(id) ON DELETE CASCADE,
    CONSTRAINT strategy_instruments_direction_check CHECK (direction IN ('BUY', 'SELL')),
    CONSTRAINT strategy_instruments_quantity_positive CHECK (quantity > 0)
);

CREATE INDEX idx_strategy_instruments_strategy_id ON strategy_instruments(strategy_id);
CREATE INDEX idx_strategy_instruments_token ON strategy_instruments(instrument_token);

COMMENT ON TABLE strategy_instruments IS 'Instruments (legs) within a strategy';
COMMENT ON COLUMN strategy_instruments.realized_pnl IS 'Profit/Loss when position is exited (entry_price - exit_price) × quantity';
```

### Migration 027: Create strategy_m2m_candles table (TimescaleDB hypertable)

```sql
-- migrations/027_create_strategy_m2m_candles_table.sql
CREATE TABLE IF NOT EXISTS strategy_m2m_candles (
    strategy_id INTEGER NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    open DECIMAL(15, 2) NOT NULL,
    high DECIMAL(15, 2) NOT NULL,
    low DECIMAL(15, 2) NOT NULL,
    close DECIMAL(15, 2) NOT NULL,

    PRIMARY KEY (strategy_id, timestamp),
    CONSTRAINT strategy_m2m_strategy_id_fk FOREIGN KEY (strategy_id) REFERENCES strategies(id) ON DELETE CASCADE
);

-- Convert to TimescaleDB hypertable (1-minute candles)
SELECT create_hypertable(
    'strategy_m2m_candles',
    'timestamp',
    chunk_time_interval => INTERVAL '1 month',
    if_not_exists => TRUE
);

-- Continuous aggregate: 5-minute M2M candles
CREATE MATERIALIZED VIEW strategy_m2m_5min
WITH (timescaledb.continuous) AS
SELECT
    strategy_id,
    time_bucket('5 minutes', timestamp) AS bucket,
    FIRST(open, timestamp) AS open,
    MAX(high) AS high,
    MIN(low) AS low,
    LAST(close, timestamp) AS close
FROM strategy_m2m_candles
GROUP BY strategy_id, bucket
WITH NO DATA;

-- Refresh policy: Update 5-minute aggregates every 1 minute
SELECT add_continuous_aggregate_policy('strategy_m2m_5min',
    start_offset => INTERVAL '1 day',
    end_offset => INTERVAL '1 minute',
    schedule_interval => INTERVAL '1 minute'
);

COMMENT ON TABLE strategy_m2m_candles IS 'Real-time strategy Mark-to-Market 1-minute OHLC candles';
```

### Migration 028: Create strategy_performance_daily table

```sql
-- migrations/028_create_strategy_performance_daily_table.sql
CREATE TABLE IF NOT EXISTS strategy_performance_daily (
    id SERIAL PRIMARY KEY,
    strategy_id INTEGER NOT NULL,
    date DATE NOT NULL,
    realized_pnl DECIMAL(15, 2) NOT NULL DEFAULT 0,  -- Sum of closed positions
    unrealized_pnl DECIMAL(15, 2) NOT NULL DEFAULT 0,  -- M2M of open positions
    total_pnl DECIMAL(15, 2) NOT NULL DEFAULT 0,  -- realized + unrealized
    max_m2m DECIMAL(15, 2),  -- Highest M2M during day
    min_m2m DECIMAL(15, 2),  -- Lowest M2M during day
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (strategy_id, date),
    CONSTRAINT strategy_performance_strategy_id_fk FOREIGN KEY (strategy_id) REFERENCES strategies(id) ON DELETE CASCADE
);

CREATE INDEX idx_strategy_performance_strategy_id ON strategy_performance_daily(strategy_id);
CREATE INDEX idx_strategy_performance_date ON strategy_performance_daily(date);

COMMENT ON TABLE strategy_performance_daily IS 'Daily aggregated strategy performance metrics';
```

### Run migrations

```bash
cd /mnt/stocksblitz-data/Quantagro/tradingview-viz/backend

# Execute migrations in order
PGPASSWORD=stocksblitz123 psql -U stocksblitz -d stocksblitz_unified -h localhost -f migrations/025_create_strategies_table.sql
PGPASSWORD=stocksblitz123 psql -U stocksblitz -d stocksblitz_unified -h localhost -f migrations/026_create_strategy_instruments_table.sql
PGPASSWORD=stocksblitz123 psql -U stocksblitz -d stocksblitz_unified -h localhost -f migrations/027_create_strategy_m2m_candles_table.sql
PGPASSWORD=stocksblitz123 psql -U stocksblitz -d stocksblitz_unified -h localhost -f migrations/028_create_strategy_performance_daily_table.sql

# Verify tables created
PGPASSWORD=stocksblitz123 psql -U stocksblitz -d stocksblitz_unified -h localhost -c "\dt strategies*"
```

**Validation**:
- [ ] All 4 tables created successfully
- [ ] TimescaleDB hypertable configured for strategy_m2m_candles
- [ ] Continuous aggregate strategy_m2m_5min created
- [ ] Foreign key constraints validated

**Effort**: 2 hours

---

## Task 2: Backend Routes (10+ API endpoints) - Days 3-7

### Create routes/strategies.py

```python
# app/routes/strategies.py - NEW FILE
from fastapi import APIRouter, HTTPException, Depends, status
from typing import List, Optional
from decimal import Decimal
from datetime import datetime, date
from pydantic import BaseModel, Field
from app.database import get_pool, validate_sort_params
import logging

router = APIRouter(prefix="/strategies", tags=["Strategies"])
logger = logging.getLogger(__name__)

# Pydantic models
class StrategyCreate(BaseModel):
    """Request model for creating a new strategy."""
    user_id: int = Field(..., description="User ID")
    account_id: Optional[int] = Field(None, description="Trading account ID")
    name: str = Field(..., min_length=1, max_length=100, description="Strategy name")
    description: Optional[str] = Field(None, description="Strategy description")
    target_profit: Optional[Decimal] = Field(None, description="Target profit (optional)")
    stop_loss: Optional[Decimal] = Field(None, description="Stop loss (optional)")

class InstrumentAdd(BaseModel):
    """Request model for adding instrument to strategy."""
    instrument_token: int = Field(..., description="Instrument token from Kite")
    tradingsymbol: str = Field(..., description="Trading symbol")
    segment: str = Field(default="FO", description="Segment (FO for F&O)")
    direction: str = Field(..., description="BUY or SELL")
    quantity: int = Field(..., gt=0, description="Quantity (must be > 0)")
    entry_price: Decimal = Field(..., description="Entry price")

class StrategyResponse(BaseModel):
    """Response model for strategy."""
    id: int
    user_id: int
    account_id: Optional[int]
    name: str
    description: Optional[str]
    status: str
    target_profit: Optional[Decimal]
    stop_loss: Optional[Decimal]
    total_m2m: Optional[Decimal]  # Current unrealized P&L
    created_at: datetime
    updated_at: datetime


@router.post("", status_code=status.HTTP_201_CREATED, response_model=StrategyResponse)
async def create_strategy(strategy: StrategyCreate):
    """
    Create a new strategy.

    Args:
        strategy: Strategy creation request

    Returns:
        Created strategy with ID
    """
    pool = await get_pool()

    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow("""
                INSERT INTO strategies (
                    user_id, account_id, name, description,
                    target_profit, stop_loss, status
                )
                VALUES ($1, $2, $3, $4, $5, $6, 'active')
                RETURNING *
            """,
                strategy.user_id,
                strategy.account_id,
                strategy.name,
                strategy.description,
                strategy.target_profit,
                strategy.stop_loss
            )

            logger.info(f"Strategy created: id={row['id']}, name={row['name']}")

            return {
                **dict(row),
                "total_m2m": Decimal("0.00")  # New strategy, no M2M yet
            }

        except Exception as e:
            logger.error(f"Failed to create strategy: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create strategy"
            )


@router.get("", response_model=dict)
async def get_strategies(
    user_id: int,
    status: Optional[str] = None,
    sort_by: str = "created_at",
    order: str = "DESC",
    limit: int = 50,
    offset: int = 0
):
    """
    Get all strategies for a user.

    Args:
        user_id: User ID
        status: Filter by status (active, closed, archived)
        sort_by: Sort column (validated against whitelist)
        order: Sort order (ASC or DESC)
        limit: Number of results (max 100)
        offset: Pagination offset

    Returns:
        List of strategies with metadata
    """
    pool = await get_pool()

    # Validate sort parameters (SQL injection protection)
    allowed_columns = {"created_at", "updated_at", "name", "status"}
    safe_sort_by, safe_order = validate_sort_params(sort_by, order, allowed_columns)

    # Clamp limit
    limit = min(limit, 100)

    async with pool.acquire() as conn:
        # Build query with optional status filter
        where_clause = "WHERE user_id = $1"
        params = [user_id]

        if status:
            where_clause += " AND status = $2"
            params.append(status)

        query = f"""
            SELECT
                s.*,
                (
                    SELECT SUM(
                        CASE
                            WHEN si.direction = 'BUY' THEN (ltp.ltp - si.entry_price) * si.quantity * -1
                            WHEN si.direction = 'SELL' THEN (ltp.ltp - si.entry_price) * si.quantity * 1
                        END
                    )
                    FROM strategy_instruments si
                    LEFT JOIN LATERAL (
                        SELECT last_traded_price AS ltp
                        FROM instrument_ticks
                        WHERE instrument_token = si.instrument_token
                        ORDER BY timestamp DESC
                        LIMIT 1
                    ) ltp ON TRUE
                    WHERE si.strategy_id = s.id
                      AND si.exit_time IS NULL  -- Only open positions
                ) AS total_m2m
            FROM strategies s
            {where_clause}
            ORDER BY {safe_sort_by} {safe_order}
            LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}
        """

        params.extend([limit, offset])

        rows = await conn.fetch(query, *params)

        # Get total count
        count_query = f"SELECT COUNT(*) FROM strategies {where_clause}"
        total_count = await conn.fetchval(count_query, *params[:len(params) - 2])

        strategies = [dict(row) for row in rows]

        return {
            "strategies": strategies,
            "total_count": total_count,
            "limit": limit,
            "offset": offset
        }


@router.get("/{strategy_id}", response_model=StrategyResponse)
async def get_strategy(strategy_id: int, user_id: int):
    """
    Get strategy by ID.

    Args:
        strategy_id: Strategy ID
        user_id: User ID (for authorization)

    Returns:
        Strategy details with current M2M
    """
    pool = await get_pool()

    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT
                s.*,
                (
                    SELECT SUM(
                        CASE
                            WHEN si.direction = 'BUY' THEN (ltp.ltp - si.entry_price) * si.quantity * -1
                            WHEN si.direction = 'SELL' THEN (ltp.ltp - si.entry_price) * si.quantity * 1
                        END
                    )
                    FROM strategy_instruments si
                    LEFT JOIN LATERAL (
                        SELECT last_traded_price AS ltp
                        FROM instrument_ticks
                        WHERE instrument_token = si.instrument_token
                        ORDER BY timestamp DESC
                        LIMIT 1
                    ) ltp ON TRUE
                    WHERE si.strategy_id = s.id
                      AND si.exit_time IS NULL
                ) AS total_m2m
            FROM strategies s
            WHERE s.id = $1 AND s.user_id = $2
        """, strategy_id, user_id)

        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Strategy not found"
            )

        return dict(row)


@router.post("/{strategy_id}/instruments", status_code=status.HTTP_201_CREATED)
async def add_instrument_to_strategy(strategy_id: int, user_id: int, instrument: InstrumentAdd):
    """
    Add instrument (leg) to strategy.

    Args:
        strategy_id: Strategy ID
        user_id: User ID (for authorization)
        instrument: Instrument details

    Returns:
        Created instrument
    """
    pool = await get_pool()

    async with pool.acquire() as conn:
        # Verify strategy ownership
        strategy = await conn.fetchrow("""
            SELECT id FROM strategies WHERE id = $1 AND user_id = $2
        """, strategy_id, user_id)

        if not strategy:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Strategy not found or access denied"
            )

        # Insert instrument
        row = await conn.fetchrow("""
            INSERT INTO strategy_instruments (
                strategy_id, instrument_token, tradingsymbol, segment,
                direction, quantity, entry_price
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING *
        """,
            strategy_id,
            instrument.instrument_token,
            instrument.tradingsymbol,
            instrument.segment,
            instrument.direction,
            instrument.quantity,
            instrument.entry_price
        )

        logger.info(f"Instrument added to strategy: strategy_id={strategy_id}, symbol={instrument.tradingsymbol}")

        return dict(row)


@router.get("/{strategy_id}/instruments")
async def get_strategy_instruments(strategy_id: int, user_id: int):
    """
    Get all instruments in a strategy.

    Args:
        strategy_id: Strategy ID
        user_id: User ID (for authorization)

    Returns:
        List of instruments with current LTP and unrealized P&L
    """
    pool = await get_pool()

    async with pool.acquire() as conn:
        # Verify ownership
        strategy = await conn.fetchrow("""
            SELECT id FROM strategies WHERE id = $1 AND user_id = $2
        """, strategy_id, user_id)

        if not strategy:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Strategy not found or access denied"
            )

        # Fetch instruments with LTP and unrealized P&L
        rows = await conn.fetch("""
            SELECT
                si.*,
                ltp.ltp AS current_ltp,
                CASE
                    WHEN si.direction = 'BUY' THEN (ltp.ltp - si.entry_price) * si.quantity * -1
                    WHEN si.direction = 'SELL' THEN (ltp.ltp - si.entry_price) * si.quantity * 1
                END AS unrealized_pnl
            FROM strategy_instruments si
            LEFT JOIN LATERAL (
                SELECT last_traded_price AS ltp
                FROM instrument_ticks
                WHERE instrument_token = si.instrument_token
                ORDER BY timestamp DESC
                LIMIT 1
            ) ltp ON TRUE
            WHERE si.strategy_id = $1
              AND si.exit_time IS NULL
            ORDER BY si.created_at ASC
        """, strategy_id)

        instruments = [dict(row) for row in rows]

        return {"instruments": instruments}


# Additional endpoints (6 more):
# - PATCH /{strategy_id} (update strategy name, description, target_profit, stop_loss)
# - DELETE /{strategy_id} (soft delete - set status='archived')
# - DELETE /{strategy_id}/instruments/{instrument_id} (remove leg)
# - GET /{strategy_id}/m2m/timeseries (M2M chart data)
# - GET /{strategy_id}/performance/daily (daily P&L aggregates)
# - POST /{strategy_id}/close (close all positions, finalize strategy)
```

### Register routes in main.py

```python
# app/main.py - ADD IMPORT
from app.routes import strategies

# Add router
app.include_router(strategies.router)
```

**Validation**:
- [ ] All 10+ API endpoints functional
- [ ] Multi-account isolation enforced (user_id check)
- [ ] SQL injection protection (whitelisted sort columns)
- [ ] Decimal precision maintained in P&L calculations

**Effort**: 8-10 hours

---

## Task 3: M2M Calculation Worker - Days 8-9

### Create worker

```python
# app/workers/strategy_m2m_worker.py - NEW FILE
import asyncio
import logging
from decimal import Decimal
from datetime import datetime, timedelta
from app.database import get_pool

logger = logging.getLogger(__name__)

async def calculate_strategy_m2m_worker():
    """
    Background worker to calculate strategy M2M every 1 minute and store as OHLC candles.

    Runs continuously, wakes up every 60 seconds.
    """
    logger.info("Strategy M2M calculation worker started")

    while True:
        try:
            await calculate_and_store_m2m()
            await asyncio.sleep(60)  # Run every 1 minute

        except Exception as e:
            logger.error(f"Strategy M2M worker error: {e}", exc_info=True)
            await asyncio.sleep(10)  # Retry after 10 seconds on error


async def calculate_and_store_m2m():
    """Calculate M2M for all active strategies and store as 1-minute OHLC candles."""
    pool = await get_pool()

    async with pool.acquire() as conn:
        # Get all active strategies
        strategies = await conn.fetch("""
            SELECT id FROM strategies WHERE status = 'active'
        """)

        if not strategies:
            logger.debug("No active strategies to calculate M2M")
            return

        logger.info(f"Calculating M2M for {len(strategies)} active strategies")

        for strategy_row in strategies:
            strategy_id = strategy_row['id']

            try:
                # Calculate current M2M
                m2m = await calculate_strategy_m2m_snapshot(conn, strategy_id)

                # Store M2M as 1-minute candle (open=high=low=close=m2m)
                await store_m2m_candle(conn, strategy_id, m2m)

            except Exception as e:
                logger.error(f"Failed to calculate M2M for strategy_id={strategy_id}: {e}")


async def calculate_strategy_m2m_snapshot(conn, strategy_id: int) -> Decimal:
    """
    Calculate current M2M for a strategy.

    Args:
        conn: Database connection
        strategy_id: Strategy ID

    Returns:
        Current M2M (unrealized P&L)
    """
    m2m_value = await conn.fetchval("""
        SELECT SUM(
            CASE
                WHEN si.direction = 'BUY' THEN (ltp.ltp - si.entry_price) * si.quantity * -1
                WHEN si.direction = 'SELL' THEN (ltp.ltp - si.entry_price) * si.quantity * 1
            END
        )
        FROM strategy_instruments si
        LEFT JOIN LATERAL (
            SELECT last_traded_price AS ltp
            FROM instrument_ticks
            WHERE instrument_token = si.instrument_token
            ORDER BY timestamp DESC
            LIMIT 1
        ) ltp ON TRUE
        WHERE si.strategy_id = $1
          AND si.exit_time IS NULL  -- Only open positions
    """, strategy_id)

    return m2m_value if m2m_value is not None else Decimal("0.00")


async def store_m2m_candle(conn, strategy_id: int, m2m: Decimal):
    """
    Store M2M as 1-minute OHLC candle (with upsert logic).

    Args:
        conn: Database connection
        strategy_id: Strategy ID
        m2m: Current M2M value
    """
    # Round timestamp to nearest minute
    now = datetime.utcnow().replace(second=0, microsecond=0)

    # Upsert: if candle exists for this minute, update high/low/close
    await conn.execute("""
        INSERT INTO strategy_m2m_candles (strategy_id, timestamp, open, high, low, close)
        VALUES ($1, $2, $3, $3, $3, $3)
        ON CONFLICT (strategy_id, timestamp)
        DO UPDATE SET
            high = GREATEST(strategy_m2m_candles.high, EXCLUDED.close),
            low = LEAST(strategy_m2m_candles.low, EXCLUDED.close),
            close = EXCLUDED.close
    """, strategy_id, now, m2m)

    logger.debug(f"M2M candle stored: strategy_id={strategy_id}, timestamp={now}, m2m={m2m}")
```

### Start worker in main.py

```python
# app/main.py - ADD IMPORT
from app.workers.strategy_m2m_worker import calculate_strategy_m2m_worker

# Add startup event
@app.on_event("startup")
async def startup_workers():
    """Start background workers on application startup."""
    asyncio.create_task(calculate_strategy_m2m_worker())
    logger.info("Background workers started")
```

**Validation**:
- [ ] M2M worker runs every 1 minute
- [ ] M2M calculated correctly for BUY/SELL positions
- [ ] OHLC candles stored in strategy_m2m_candles table
- [ ] Worker handles errors gracefully (retry logic)

**Effort**: 2-3 hours

---

## Task 4: Frontend Components (7 components) - Days 10-20

**Note**: Frontend implementation is outside backend scope. Refer to:
- `/docs/assessment_1/pending_requirements.md` (Section 4.2)
- Original planning docs: `PHASE_2.5_DAY3_IMPLEMENTATION_PROMPT.md`

**Components Needed** (17-22 hours frontend effort):
1. StrategySelector.tsx (2-3 hours)
2. CreateStrategyModal.tsx (3-4 hours)
3. AddInstrumentModal.tsx (3-4 hours)
4. StrategyInstrumentsPanel.tsx (3-4 hours)
5. StrategyPnlPanel.tsx (2-3 hours)
6. StrategyM2MChart.tsx (4-6 hours) - Integrate opstrat library for payoff graphs

**Skip for backend implementation prompt.**

---

## Final Checklist

### Backend Implementation
- [ ] **Task 1**: Database migrations (4 tables)
- [ ] **Task 2**: Backend routes (10+ API endpoints)
- [ ] **Task 3**: M2M calculation worker

### Zero Regression Validation
- [ ] All existing API endpoints functional
- [ ] No breaking changes to database schema
- [ ] Existing tests pass

### Testing
- [ ] Create 30+ tests for strategy APIs
- [ ] Test M2M calculation worker
- [ ] Test multi-account isolation

### Documentation
- [ ] API documentation updated (Swagger)
- [ ] Database schema documented
- [ ] Worker architecture documented

---

## Success Metrics

**Before**:
- Phase 2.5 completion: 30% (design only)
- Strategy system: Not functional

**After**:
- Phase 2.5 completion: 100% (backend complete)
- Strategy system: Fully functional (pending frontend)

---

## Next Steps

1. **Week 4+**: Implement frontend components (17-22 hours)
2. **Ongoing**: Monitor M2M worker performance
3. **Future**: Add strategy templates (Iron Condor, Straddle, etc.)

---

**Estimated Effort**: 12-18 hours (backend only)
**Priority**: P1 - Feature Completion
**Impact**: HIGH - Unlocks strategy-based trading

---

**Last Updated**: 2025-11-09
**Owner**: Backend Team
**Next Review**: After backend implementation complete
