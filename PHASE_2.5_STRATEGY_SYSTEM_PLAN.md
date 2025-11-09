# Phase 2.5: Strategy System Implementation Plan

## Overview

The Strategy System allows users to organize and track trading activity across multiple strategies simultaneously. Each strategy maintains its own P&L, positions, orders, and performance metrics.

**Timeline**: 4-5 days
**Priority**: **HIGH** - Must be implemented before Phase 3 (Order Management)

---

## Core Concepts

### 1. Strategy Definition
- **Freeform Names**: Users can name strategies anything (not predefined types)
- **Manual Instrument Assignment**: Users manually add instruments to strategies with:
  - Symbol/tradingsymbol
  - Buy/Sell direction (Buy = -ve outflow, Sell = +ve inflow)
  - Price
  - Quantity
- **Payoff Graph**: Visual representation of strategy P&L across price ranges
- **Greeks Calculation**: For options strategies (delta, gamma, theta, vega, IV)

### 2. Default Strategy Behavior
- **All positions exist in default strategy initially**
- **When moving to custom strategy**: Position remains visible in default strategy also
  - Default: Shows full quantity (e.g., 100)
  - Custom: Shows allocated quantity (e.g., 40)
  - **Rationale**: Users need to see total exposure in default view
  - **P&L Calculation**: Each strategy calculates P&L independently on its allocated quantity

### 3. Strategy Exit vs Position Exit
- **Exit Strategy** (extreme action):
  - Used when assigned instruments to wrong strategy by mistake
  - Positions remain in default strategy
  - Strategy archived for historical reference
- **Close Position** (normal action):
  - Closes the actual position in the market
  - Position marked as closed in ALL strategies containing it
  - Remains in strategy history for performance tracking

### 4. Minute-wise M2M Tracking
- **Storage Model**: OHLC candles for strategy M2M every minute
- **Calculation Formula**:
  ```
  For each instrument in strategy:
    - Buy positions: -ve (cash outflow)
    - Sell positions: +ve (cash inflow)

  Strategy M2M = Σ(instrument_ltp × qty × direction)
  where direction = -1 for Buy, +1 for Sell
  ```
- **Example**:
  ```
  Strategy: Iron Condor
    - Buy NIFTY 24500 CE: qty=50, price=100 → -5,000
    - Sell NIFTY 24600 CE: qty=50, price=150 → +7,500
    - Buy NIFTY 24800 CE: qty=50, price=50  → -2,500

  At 10:00 AM:
    LTPs: 120, 130, 40
    M2M = (120×50×-1) + (130×50×+1) + (40×50×-1)
        = -6,000 + 6,500 - 2,000
        = -1,500 (loss of 1,500)

  Store as: timestamp=10:00, open=-1500, high=-1400, low=-1600, close=-1500
  ```
- **Backend Service**: Handles M2M storage (NOT ticker_service)
- **Data Dependency**: Must have OHLC data for all underlying instruments to avoid corrupted calculations

---

## Database Schema

### 1. Strategies Table
```sql
CREATE TABLE strategies (
  strategy_id SERIAL PRIMARY KEY,
  trading_account_id INT NOT NULL REFERENCES trading_accounts(id),
  user_id INT NOT NULL,  -- Creator

  -- Basic info
  name VARCHAR(200) NOT NULL,
  description TEXT,
  tags TEXT[],  -- Freeform tags for filtering

  -- Status
  status VARCHAR(20) DEFAULT 'active',  -- active, archived, deleted
  is_default BOOLEAN DEFAULT FALSE,

  -- Timestamps
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  archived_at TIMESTAMPTZ,

  -- Current metrics (real-time)
  current_pnl DECIMAL(15,2) DEFAULT 0,
  current_m2m DECIMAL(15,2) DEFAULT 0,
  total_capital_deployed DECIMAL(15,2) DEFAULT 0,
  total_margin_used DECIMAL(15,2) DEFAULT 0,

  -- Constraints
  UNIQUE(trading_account_id, name),  -- Unique names per account
  INDEX idx_strategies_account (trading_account_id),
  INDEX idx_strategies_user (user_id),
  INDEX idx_strategies_status (status)
);

-- Create default strategy for each trading account
CREATE FUNCTION create_default_strategy()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO strategies (trading_account_id, user_id, name, is_default)
  VALUES (NEW.id, NEW.owner_user_id, 'Default Strategy', TRUE);
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_create_default_strategy
AFTER INSERT ON trading_accounts
FOR EACH ROW
EXECUTE FUNCTION create_default_strategy();
```

### 2. Strategy Instruments (Manual Assignments)
```sql
CREATE TABLE strategy_instruments (
  id SERIAL PRIMARY KEY,
  strategy_id INT NOT NULL REFERENCES strategies(strategy_id) ON DELETE CASCADE,

  -- Instrument info
  tradingsymbol VARCHAR(50) NOT NULL,
  exchange VARCHAR(10) NOT NULL,
  instrument_token INT,

  -- Position details
  direction VARCHAR(4) NOT NULL CHECK (direction IN ('BUY', 'SELL')),
  quantity INT NOT NULL,
  entry_price DECIMAL(10,2) NOT NULL,  -- Can be manual override

  -- Timestamps
  added_at TIMESTAMPTZ DEFAULT NOW(),

  -- Metadata
  notes TEXT,

  INDEX idx_strategy_instruments_strategy (strategy_id),
  INDEX idx_strategy_instruments_symbol (tradingsymbol)
);
```

### 3. Add strategy_id to existing tables
```sql
-- Positions
ALTER TABLE positions
ADD COLUMN strategy_id INT REFERENCES strategies(strategy_id);

-- Orders
ALTER TABLE orders
ADD COLUMN strategy_id INT REFERENCES strategies(strategy_id);

-- Holdings (if applicable)
ALTER TABLE holdings
ADD COLUMN strategy_id INT REFERENCES strategies(strategy_id);

-- Create indexes
CREATE INDEX idx_positions_strategy ON positions(strategy_id);
CREATE INDEX idx_orders_strategy ON orders(strategy_id);
CREATE INDEX idx_holdings_strategy ON holdings(strategy_id);
```

### 4. Strategy M2M History (Minute Candles)
```sql
CREATE TABLE strategy_m2m_candles (
  id BIGSERIAL PRIMARY KEY,
  strategy_id INT NOT NULL REFERENCES strategies(strategy_id) ON DELETE CASCADE,

  -- Timestamp (minute precision)
  timestamp TIMESTAMPTZ NOT NULL,

  -- OHLC for M2M
  open DECIMAL(15,2) NOT NULL,
  high DECIMAL(15,2) NOT NULL,
  low DECIMAL(15,2) NOT NULL,
  close DECIMAL(15,2) NOT NULL,

  -- Metadata
  instrument_count INT,  -- Number of instruments in strategy at this time

  -- Constraints
  UNIQUE(strategy_id, timestamp),
  INDEX idx_m2m_strategy_time (strategy_id, timestamp DESC)
);

-- Partition by month for performance
CREATE TABLE strategy_m2m_candles_y2025m01 PARTITION OF strategy_m2m_candles
FOR VALUES FROM ('2025-01-01') TO ('2025-02-01');

CREATE TABLE strategy_m2m_candles_y2025m02 PARTITION OF strategy_m2m_candles
FOR VALUES FROM ('2025-02-01') TO ('2025-03-01');

-- ... create partitions for each month
```

### 5. Strategy Performance Snapshots (Daily)
```sql
CREATE TABLE strategy_performance_daily (
  id SERIAL PRIMARY KEY,
  strategy_id INT NOT NULL REFERENCES strategies(strategy_id) ON DELETE CASCADE,
  date DATE NOT NULL,

  -- P&L metrics
  day_pnl DECIMAL(15,2),
  cumulative_pnl DECIMAL(15,2),
  realized_pnl DECIMAL(15,2),
  unrealized_pnl DECIMAL(15,2),

  -- Position metrics
  open_positions INT,
  closed_positions INT,
  avg_position_size DECIMAL(15,2),

  -- Trading metrics
  total_trades INT,
  winning_trades INT,
  losing_trades INT,
  win_rate DECIMAL(5,2),

  -- Capital metrics
  capital_deployed DECIMAL(15,2),
  margin_used DECIMAL(15,2),
  max_drawdown DECIMAL(15,2),

  -- Risk metrics
  sharpe_ratio DECIMAL(8,4),
  sortino_ratio DECIMAL(8,4),
  max_consecutive_losses INT,

  -- ROI
  roi_percent DECIMAL(8,4),

  UNIQUE(strategy_id, date),
  INDEX idx_perf_strategy_date (strategy_id, date DESC)
);
```

---

## Backend APIs (Backend Service - Port 8081)

### Strategy CRUD

#### 1. Create Strategy
```
POST /strategies

Headers:
  Authorization: Bearer <jwt_token>
  X-Account-ID: <trading_account_id>

Body:
{
  "name": "Iron Condor - Nov Expiry",
  "description": "4-leg iron condor on NIFTY",
  "tags": ["iron_condor", "nifty", "weekly"]
}

Response:
{
  "strategy_id": 123,
  "name": "Iron Condor - Nov Expiry",
  "status": "active",
  "is_default": false,
  "created_at": "2025-11-07T10:30:00Z",
  "current_pnl": 0,
  "current_m2m": 0
}
```

#### 2. List Strategies
```
GET /strategies?account_id=<trading_account_id>

Response:
{
  "strategies": [
    {
      "strategy_id": 1,
      "name": "Default Strategy",
      "is_default": true,
      "status": "active",
      "current_pnl": 15000,
      "current_m2m": 12000,
      "instrument_count": 25,
      "created_at": "2025-11-01T09:00:00Z"
    },
    {
      "strategy_id": 123,
      "name": "Iron Condor - Nov Expiry",
      "is_default": false,
      "status": "active",
      "current_pnl": 2500,
      "current_m2m": 2100,
      "instrument_count": 4,
      "created_at": "2025-11-07T10:30:00Z"
    }
  ]
}
```

#### 3. Get Strategy Details
```
GET /strategies/{strategy_id}

Response:
{
  "strategy_id": 123,
  "name": "Iron Condor - Nov Expiry",
  "description": "4-leg iron condor on NIFTY",
  "tags": ["iron_condor", "nifty", "weekly"],
  "status": "active",
  "is_default": false,
  "created_at": "2025-11-07T10:30:00Z",
  "current_pnl": 2500,
  "current_m2m": 2100,
  "total_capital_deployed": 50000,
  "total_margin_used": 35000,
  "instruments": [
    {
      "tradingsymbol": "NIFTY25N0724500CE",
      "direction": "BUY",
      "quantity": 50,
      "entry_price": 100.00,
      "current_price": 110.00,
      "pnl": 500
    },
    // ... more instruments
  ],
  "performance": {
    "total_trades": 15,
    "winning_trades": 9,
    "losing_trades": 6,
    "win_rate": 60.0,
    "roi_percent": 5.0,
    "sharpe_ratio": 1.25
  }
}
```

#### 4. Update Strategy
```
PUT /strategies/{strategy_id}

Body:
{
  "name": "Iron Condor - Nov Expiry (Adjusted)",
  "description": "Updated description",
  "tags": ["iron_condor", "nifty", "weekly", "adjusted"]
}

Response: <same as GET>
```

#### 5. Archive Strategy
```
DELETE /strategies/{strategy_id}

Body:
{
  "move_to_default": false  // If true, moves positions back to default
}

Response:
{
  "strategy_id": 123,
  "status": "archived",
  "archived_at": "2025-11-07T15:00:00Z"
}
```

### Strategy Instruments

#### 6. Add Instrument to Strategy
```
POST /strategies/{strategy_id}/instruments

Body:
{
  "tradingsymbol": "NIFTY25N0724500CE",
  "exchange": "NFO",
  "direction": "BUY",  // BUY or SELL
  "quantity": 50,
  "entry_price": 100.00,  // Manual entry price
  "notes": "Long call leg"
}

Response:
{
  "id": 456,
  "strategy_id": 123,
  "tradingsymbol": "NIFTY25N0724500CE",
  "direction": "BUY",
  "quantity": 50,
  "entry_price": 100.00,
  "current_price": 110.00,
  "pnl": 500,
  "added_at": "2025-11-07T10:35:00Z"
}
```

#### 7. Remove Instrument from Strategy
```
DELETE /strategies/{strategy_id}/instruments/{instrument_id}

Response:
{
  "success": true,
  "message": "Instrument removed from strategy"
}
```

#### 8. Update Instrument Entry Price
```
PUT /strategies/{strategy_id}/instruments/{instrument_id}

Body:
{
  "entry_price": 105.00,  // Manual override
  "quantity": 60,
  "notes": "Averaged up"
}

Response: <same as add instrument>
```

### Strategy Positions & Orders

#### 9. Get Strategy Positions
```
GET /strategies/{strategy_id}/positions

Response:
{
  "positions": [
    {
      "tradingsymbol": "NIFTY25N0724500CE",
      "quantity": 50,
      "average_price": 100.00,
      "last_price": 110.00,
      "pnl": 500,
      "m2m": 500,
      "unrealised": 500,
      "realised": 0
    }
    // ... more positions
  ],
  "summary": {
    "total_pnl": 2500,
    "total_m2m": 2100,
    "open_positions": 4
  }
}
```

#### 10. Get Strategy Orders
```
GET /strategies/{strategy_id}/orders

Response:
{
  "orders": [
    {
      "order_id": "251107000123456",
      "tradingsymbol": "NIFTY25N0724500CE",
      "transaction_type": "BUY",
      "quantity": 50,
      "price": 100.00,
      "status": "COMPLETE",
      "order_timestamp": "2025-11-07T09:15:00Z"
    }
    // ... more orders
  ]
}
```

### Strategy M2M Tracking

#### 11. Get Strategy M2M History
```
GET /strategies/{strategy_id}/m2m?from=2025-11-07T00:00:00Z&to=2025-11-07T23:59:59Z&interval=1m

Response:
{
  "strategy_id": 123,
  "interval": "1m",
  "candles": [
    {
      "timestamp": "2025-11-07T09:15:00Z",
      "open": 1000.00,
      "high": 1200.00,
      "low": 950.00,
      "close": 1100.00
    },
    {
      "timestamp": "2025-11-07T09:16:00Z",
      "open": 1100.00,
      "high": 1150.00,
      "low": 1050.00,
      "close": 1125.00
    }
    // ... more candles
  ]
}
```

#### 12. Get Strategy Performance
```
GET /strategies/{strategy_id}/performance?from=2025-11-01&to=2025-11-07

Response:
{
  "strategy_id": 123,
  "daily_performance": [
    {
      "date": "2025-11-07",
      "day_pnl": 2500,
      "cumulative_pnl": 15000,
      "total_trades": 15,
      "win_rate": 60.0,
      "roi_percent": 5.0
    }
    // ... more days
  ],
  "overall": {
    "total_pnl": 15000,
    "roi_percent": 5.0,
    "sharpe_ratio": 1.25,
    "max_drawdown": -3000,
    "total_trades": 50,
    "win_rate": 62.0
  }
}
```

### Strategy Payoff & Greeks

#### 13. Calculate Payoff Graph
```
POST /strategies/{strategy_id}/payoff

Body:
{
  "spot_range": {
    "min": 24000,
    "max": 25000,
    "step": 10
  },
  "expiry_date": "2025-11-28"  // Optional: at expiry vs now
}

Response:
{
  "strategy_id": 123,
  "spot_prices": [24000, 24010, 24020, ...],
  "pnl_values": [-500, -480, -460, ...],
  "max_profit": 5000,
  "max_loss": -10000,
  "break_even_points": [24350, 24850],
  "greeks": {
    "delta": 0.25,
    "gamma": 0.015,
    "theta": -50,
    "vega": 120,
    "iv": 18.5
  }
}
```

---

## M2M Calculation Engine (Backend Service)

### Background Worker
```python
# File: backend/app/workers/strategy_m2m_worker.py

"""
Strategy M2M Background Worker

Runs every minute to calculate and store M2M for all active strategies.
"""

import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Dict

class StrategyM2MWorker:
    def __init__(self, db_pool, redis_client, ticker_service_url):
        self.db = db_pool
        self.redis = redis_client
        self.ticker_url = ticker_service_url

    async def run_forever(self):
        """Run M2M calculation every minute."""
        while True:
            try:
                await self.calculate_all_strategies()
                await asyncio.sleep(60)  # Wait 1 minute
            except Exception as e:
                logger.error(f"M2M calculation error: {e}")
                await asyncio.sleep(10)  # Retry after 10s on error

    async def calculate_all_strategies(self):
        """Calculate M2M for all active strategies."""
        timestamp = datetime.utcnow().replace(second=0, microsecond=0)

        # Get all active strategies
        strategies = await self.db.fetch("""
            SELECT strategy_id, trading_account_id
            FROM strategies
            WHERE status = 'active'
        """)

        for strategy in strategies:
            await self.calculate_strategy_m2m(
                strategy['strategy_id'],
                strategy['trading_account_id'],
                timestamp
            )

    async def calculate_strategy_m2m(
        self,
        strategy_id: int,
        trading_account_id: int,
        timestamp: datetime
    ):
        """Calculate M2M for a single strategy."""

        # Get all instruments in strategy
        instruments = await self.db.fetch("""
            SELECT tradingsymbol, exchange, direction, quantity, entry_price
            FROM strategy_instruments
            WHERE strategy_id = $1
        """, strategy_id)

        if not instruments:
            return

        # Fetch current LTPs from ticker service or Redis cache
        ltps = await self.fetch_ltps([
            (inst['tradingsymbol'], inst['exchange'])
            for inst in instruments
        ])

        # Calculate M2M for each instrument
        m2m_values = []
        for inst in instruments:
            symbol = inst['tradingsymbol']
            ltp = ltps.get(symbol)

            if ltp is None:
                logger.warning(f"No LTP for {symbol}, skipping")
                continue

            # Buy = -ve (paid money), Sell = +ve (received money)
            direction_multiplier = -1 if inst['direction'] == 'BUY' else 1

            # M2M = (current_value - entry_value) × direction
            current_value = ltp * inst['quantity']
            entry_value = inst['entry_price'] * inst['quantity']

            # For BUY: -(current - entry) = entry - current (loss if ltp > entry)
            # For SELL: +(current - entry) = current - entry (profit if ltp < entry)
            m2m = (current_value - entry_value) * direction_multiplier
            m2m_values.append(m2m)

        # Total strategy M2M
        total_m2m = sum(m2m_values)

        # Store as OHLC (for now, all same since we calculate once per minute)
        # In production, you'd track ticks and calculate real OHLC
        await self.store_m2m_candle(
            strategy_id=strategy_id,
            timestamp=timestamp,
            open=total_m2m,
            high=total_m2m,
            low=total_m2m,
            close=total_m2m,
            instrument_count=len(instruments)
        )

        # Update strategy current M2M
        await self.db.execute("""
            UPDATE strategies
            SET current_m2m = $1, updated_at = $2
            WHERE strategy_id = $3
        """, total_m2m, timestamp, strategy_id)

    async def fetch_ltps(self, symbols: List[tuple]) -> Dict[str, Decimal]:
        """Fetch LTPs from Redis cache or ticker service."""
        ltps = {}

        for tradingsymbol, exchange in symbols:
            # Try Redis cache first
            cached = await self.redis.get(f"ltp:{exchange}:{tradingsymbol}")
            if cached:
                ltps[tradingsymbol] = Decimal(cached)
            else:
                # Fetch from ticker service
                # (implement HTTP call to ticker service)
                pass

        return ltps

    async def store_m2m_candle(
        self,
        strategy_id: int,
        timestamp: datetime,
        open: Decimal,
        high: Decimal,
        low: Decimal,
        close: Decimal,
        instrument_count: int
    ):
        """Store M2M candle in database."""
        await self.db.execute("""
            INSERT INTO strategy_m2m_candles
            (strategy_id, timestamp, open, high, low, close, instrument_count)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (strategy_id, timestamp) DO UPDATE
            SET open = EXCLUDED.open,
                high = EXCLUDED.high,
                low = EXCLUDED.low,
                close = EXCLUDED.close,
                instrument_count = EXCLUDED.instrument_count
        """, strategy_id, timestamp, open, high, low, close, instrument_count)
```

---

## Frontend Components

### 1. StrategySelector.tsx
Dropdown to select active strategy (similar to account selector).

**Location**: `frontend/src/components/tradingDashboard/StrategySelector.tsx`

**Features**:
- Shows all strategies for selected trading account
- Default strategy always at top
- Shows current P&L next to each strategy name
- Color-coded by P&L (green/red)

### 2. CreateStrategyModal.tsx
Modal to create new strategy.

**Location**: `frontend/src/components/tradingDashboard/CreateStrategyModal.tsx`

**Fields**:
- Strategy Name (required)
- Description (optional)
- Tags (optional, comma-separated)

### 3. StrategyInstrumentsPanel.tsx
Panel showing instruments in selected strategy.

**Location**: `frontend/src/components/tradingDashboard/StrategyInstrumentsPanel.tsx`

**Features**:
- Add instrument button (opens AddInstrumentModal)
- Table: Symbol | Direction | Qty | Entry Price | LTP | P&L
- Edit/Remove buttons for each instrument
- Payoff graph button (opens PayoffGraphModal)

### 4. AddInstrumentModal.tsx
Modal to manually add instrument to strategy.

**Location**: `frontend/src/components/tradingDashboard/AddInstrumentModal.tsx`

**Fields**:
- Symbol search (autocomplete from instrument database)
- Direction (Buy/Sell radio buttons)
- Quantity (number input)
- Entry Price (number input, with current LTP hint)
- Notes (optional)

### 5. StrategyPnlPanel.tsx
Summary panel showing strategy P&L metrics.

**Location**: `frontend/src/components/tradingDashboard/StrategyPnlPanel.tsx`

**Displays**:
- Current P&L (real-time)
- Current M2M
- Total Capital Deployed
- Total Margin Used
- ROI %
- Win Rate
- Total Trades

### 6. StrategyM2MChart.tsx
Real-time chart showing strategy M2M over time.

**Location**: `frontend/src/components/tradingDashboard/StrategyM2MChart.tsx`

**Features**:
- Line chart of M2M (minute candles)
- Timeframe selector (1D, 1W, 1M)
- Zoom/pan controls
- Hover tooltip showing exact M2M at timestamp

### 7. PayoffGraphModal.tsx
Modal showing strategy payoff graph.

**Location**: `frontend/src/components/tradingDashboard/PayoffGraphModal.tsx`

**Features**:
- X-axis: Spot prices (range around current spot)
- Y-axis: P&L
- Shows payoff curve
- Max profit/loss labels
- Break-even points highlighted
- Greeks displayed (if options involved)

### 8. StrategyPerformancePanel.tsx
Historical performance metrics.

**Location**: `frontend/src/components/tradingDashboard/StrategyPerformancePanel.tsx`

**Displays**:
- Daily P&L chart
- Cumulative P&L curve
- Drawdown chart
- Sharpe ratio
- Win/loss distribution
- Trade history

---

## Integration with Existing Components

### PositionsPanel.tsx
- Add strategy filter dropdown
- Show strategy name in table row
- Allow moving position to different strategy (right-click menu)

### OrdersPanel.tsx (Phase 3)
- Add "Strategy" dropdown in order placement form
- Default strategy pre-selected
- Show strategy name in orders table

### TradingAccountContext.tsx
Add strategy state:
```typescript
const TradingAccountContext = createContext<{
  // ... existing
  selectedStrategy: Strategy | null
  strategies: Strategy[]
  selectStrategy: (strategyId: number) => void
  refreshStrategies: () => Promise<void>
}>()
```

---

## Implementation Sequence

### Day 1: Database & Backend Foundation
1. Create database schema (migrations)
2. Create default strategies for existing accounts
3. Backend API endpoints: CRUD operations
4. Strategy instruments endpoints

### Day 2: M2M Calculation Engine
1. Implement M2M worker (background task)
2. LTP fetching logic (Redis + Ticker Service)
3. M2M storage (candles table)
4. Test M2M calculation with sample strategies

### Day 3: Frontend - Strategy Selector & Creation
1. StrategyContext.tsx
2. StrategySelector.tsx
3. CreateStrategyModal.tsx
4. StrategyPnlPanel.tsx
5. Integration with TradingAccountContext

### Day 4: Frontend - Instruments & Payoff
1. StrategyInstrumentsPanel.tsx
2. AddInstrumentModal.tsx
3. PayoffGraphModal.tsx (basic)
4. Greeks calculation API (backend)

### Day 5: Frontend - M2M Chart & Performance
1. StrategyM2MChart.tsx
2. StrategyPerformancePanel.tsx
3. Integration with PositionsPanel
4. Testing & polish

---

## Success Criteria

- [ ] User can create freeform named strategies
- [ ] User can manually add instruments (buy/sell, price, qty)
- [ ] Positions appear in both default and custom strategies
- [ ] M2M calculated every minute and stored as OHLC
- [ ] Payoff graph generated for strategies
- [ ] Greeks calculated for options strategies
- [ ] Strategy P&L tracked independently
- [ ] Historical performance metrics available
- [ ] Orders in Phase 3 can be assigned to strategies
- [ ] Python SDK strategy features work with UI

---

## Next Steps

After Phase 2.5 completion:
- **Phase 3**: Order Management (with strategy assignment)
- **Phase 4**: Real-time WebSocket updates (strategy M2M)
- **Phase 5**: Advanced features (GTT orders, basket orders with strategies)

**Question for User**: Should I proceed with this plan? Any adjustments needed?
