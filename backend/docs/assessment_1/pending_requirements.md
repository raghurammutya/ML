# Backend Service - Pending Requirements Analysis

**Date**: 2025-11-09
**Status**: Assessment Complete
**Service**: Backend Service (Port 8081)

---

## Executive Summary

The backend service has **significant planned functionality** that remains incomplete. Based on comprehensive documentation analysis, approximately **60-70% of planned features for Phase 2.5 (Strategy System)** are **NOT YET IMPLEMENTED**.

### Implementation Status Overview

| Feature Area | Status | Completion % | Priority |
|--------------|--------|--------------|----------|
| **KiteConnect Integration** | ✅ Complete | 100% | HIGH |
| **F&O Analytics & Premium/Discount** | ✅ Complete | 100% | HIGH |
| **Futures Position Analysis** | ✅ Complete | 100% | MEDIUM |
| **Strategy System (Phase 2.5 Day 1)** | ❌ Not Started | 0% | **CRITICAL** |
| **Strategy M2M Worker (Phase 2.5 Day 2)** | ❌ Not Started | 0% | **CRITICAL** |
| **Strategy Frontend Components (Phase 2.5 Day 3)** | ❌ Not Started | 0% | **CRITICAL** |
| **Payoff Graphs & Greeks (Phase 2.5 Day 4)** | ❌ Not Started | 0% | **CRITICAL** |

---

## 1. Phase 2.5: Strategy System (MAJOR INCOMPLETE FEATURE)

### Overview

The **Strategy System** is a comprehensive framework designed to allow users to:
- Create and manage custom trading strategies
- Track P&L per strategy independently
- Manually assign instruments to strategies with buy/sell directions
- Generate payoff graphs for option strategies
- Calculate and display Greeks (Delta, Gamma, Theta, Vega)
- Track minute-wise Mark-to-Market (M2M) in OHLC candle format

**Current Status**: ❌ **0% Complete** - Only design documents exist, no code implemented

---

### 1.1 Database Schema (Day 1) - NOT IMPLEMENTED

#### Missing Tables

**strategies**
```sql
CREATE TABLE strategies (
  strategy_id SERIAL PRIMARY KEY,
  trading_account_id INT NOT NULL REFERENCES trading_accounts(id),
  user_id INT NOT NULL,

  -- Basic info
  name VARCHAR(200) NOT NULL,
  description TEXT,
  tags TEXT[],

  -- Status
  status VARCHAR(20) DEFAULT 'active',
  is_default BOOLEAN DEFAULT FALSE,

  -- Timestamps
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  archived_at TIMESTAMPTZ,

  -- Current metrics
  current_pnl DECIMAL(15,2) DEFAULT 0,
  current_m2m DECIMAL(15,2) DEFAULT 0,
  total_capital_deployed DECIMAL(15,2) DEFAULT 0,
  total_margin_used DECIMAL(15,2) DEFAULT 0,

  UNIQUE(trading_account_id, name)
);
```

**strategy_instruments** (Manual instrument assignments)
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
  entry_price DECIMAL(10,2) NOT NULL,

  -- Timestamps
  added_at TIMESTAMPTZ DEFAULT NOW(),

  -- Metadata
  notes TEXT
);
```

**strategy_m2m_candles** (Minute-wise M2M tracking)
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
  instrument_count INT,

  UNIQUE(strategy_id, timestamp)
);
```

**strategy_performance_daily** (Daily performance snapshots)
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
  roi_percent DECIMAL(8,4),

  UNIQUE(strategy_id, date)
);
```

#### Missing Migrations

**Required Migration Files**:
1. `migrations/025_create_strategies_table.sql`
2. `migrations/026_create_strategy_instruments.sql`
3. `migrations/027_create_strategy_m2m_candles.sql`
4. `migrations/028_create_strategy_performance_daily.sql`
5. `migrations/029_add_strategy_id_to_positions_orders.sql`

#### Missing Database Functions

**create_default_strategy()** - Trigger function to auto-create default strategy for new trading accounts

---

### 1.2 Backend APIs (Day 1) - NOT IMPLEMENTED

#### Missing API Endpoints

**Strategy CRUD**:
- `POST /strategies` - Create new strategy
- `GET /strategies?account_id={id}` - List all strategies
- `GET /strategies/{strategy_id}` - Get strategy details
- `PUT /strategies/{strategy_id}` - Update strategy
- `DELETE /strategies/{strategy_id}` - Archive/delete strategy

**Strategy Instruments**:
- `POST /strategies/{strategy_id}/instruments` - Add instrument manually
- `GET /strategies/{strategy_id}/instruments` - List instruments
- `PUT /strategies/{strategy_id}/instruments/{id}` - Update instrument
- `DELETE /strategies/{strategy_id}/instruments/{id}` - Remove instrument

**Strategy Positions & Orders**:
- `GET /strategies/{strategy_id}/positions` - Get positions for strategy
- `GET /strategies/{strategy_id}/orders` - Get orders for strategy

**Strategy M2M & Performance**:
- `GET /strategies/{strategy_id}/m2m` - Get M2M history (minute candles)
- `GET /strategies/{strategy_id}/performance` - Get daily performance metrics

**Payoff & Greeks**:
- `POST /strategies/{strategy_id}/payoff` - Calculate payoff graph
- `GET /strategies/{strategy_id}/greeks` - Calculate net Greeks

#### Missing Backend Files

**Required Files**:
1. `app/routes/strategies.py` - Strategy CRUD endpoints (NEW FILE)
2. `app/services/strategy_service.py` - Strategy business logic (NEW FILE)
3. `app/services/payoff_service.py` - Payoff calculation using opstrat (NEW FILE)
4. `app/services/greeks_service.py` - Greeks calculation (NEW FILE)

---

### 1.3 M2M Calculation Engine (Day 2) - NOT IMPLEMENTED

#### Missing Background Worker

**Purpose**: Calculate and store Mark-to-Market (M2M) for all active strategies every minute.

**Required File**: `app/workers/strategy_m2m_worker.py`

**Key Responsibilities**:
1. Run every minute (cron-like background task)
2. Fetch all active strategies from database
3. For each strategy:
   - Get all instruments in strategy
   - Fetch current LTP (Last Traded Price) from Redis/Ticker Service
   - Calculate M2M using formula:
     ```
     For BUY positions: M2M = -(current_price - entry_price) × quantity
     For SELL positions: M2M = (current_price - entry_price) × quantity
     Total Strategy M2M = Σ(all instrument M2Ms)
     ```
   - Store as OHLC candle in `strategy_m2m_candles` table
4. Update `strategies.current_m2m` field

**Dependencies**:
- Redis client for LTP caching
- Ticker Service HTTP client for fallback LTP fetching
- Database connection pool
- AsyncIO task scheduling

**Not Implemented**:
- ❌ Worker class
- ❌ M2M calculation logic
- ❌ LTP fetching from Redis/Ticker
- ❌ OHLC candle storage
- ❌ Error handling and retry logic
- ❌ Integration with FastAPI startup

---

### 1.4 Frontend Components (Day 3) - NOT IMPLEMENTED

#### Missing React Components

**Core Components** (7 components):

1. **StrategySelector.tsx** - Dropdown to select active strategy
   - Shows all strategies with P&L color coding
   - Default strategy always at top
   - Create new strategy button

2. **CreateStrategyModal.tsx** - Modal for creating new strategy
   - Fields: Name, Description, Tags
   - Validation and error handling

3. **StrategyInstrumentsPanel.tsx** - Table showing instruments in strategy
   - Columns: Symbol, Direction, Qty, Entry Price, LTP, P&L
   - Add/Edit/Remove buttons
   - Payoff graph button

4. **AddInstrumentModal.tsx** - Modal to manually add instrument
   - Symbol search (autocomplete)
   - Direction (Buy/Sell)
   - Quantity and Entry Price
   - Notes field

5. **StrategyPnlPanel.tsx** - Summary metrics panel
   - Current P&L, M2M
   - Total Capital Deployed
   - ROI%, Win Rate

6. **StrategyM2MChart.tsx** - Real-time M2M chart
   - Line chart using minute candles
   - Timeframe selector (1D, 1W, 1M)
   - Zoom/pan controls

7. **StrategyPerformancePanel.tsx** - Historical performance
   - Daily P&L chart
   - Cumulative P&L curve
   - Drawdown chart
   - Sharpe ratio, Win/loss distribution

#### Missing Context & Services

**StrategyContext.tsx** - React Context for strategy state management

**Services**:
- `frontend/src/services/strategies.ts` - API client for strategy endpoints
- `frontend/src/types/strategy.ts` - TypeScript type definitions

#### Missing Integration

**Updates to Existing Components**:
- `TradingAccountContext.tsx` - Add strategy state management
- `TradingDashboard.tsx` - Integrate strategy components
- `PositionsPanel.tsx` - Add strategy filter dropdown

---

### 1.5 Payoff Graphs & Greeks (Day 4) - NOT IMPLEMENTED

#### Missing Backend Services

**PayoffService** (`app/services/payoff_service.py`):
- Uses `opstrat` Python library (NOT INSTALLED)
- Generates payoff diagram as base64-encoded PNG image
- Calculates:
  - Max profit and max loss
  - Breakeven points
  - Risk-reward ratio
- Returns payoff data points for custom charting

**GreeksService** (`app/services/greeks_service.py`):
- Calculates net Greeks for strategy
- Greeks: Delta, Gamma, Theta, Vega, IV
- Position-weighted aggregation:
  ```
  Net Delta = Σ(delta × quantity × lot_size × direction_multiplier)
  where direction_multiplier = +1 for BUY, -1 for SELL
  ```
- Per-instrument Greeks breakdown

#### Missing Database Functions

**get_strategy_greeks(p_strategy_id)** - PostgreSQL function for Greeks calculation
- Joins `strategy_instruments` with `instruments` table
- Aggregates weighted Greeks
- Returns net Greeks and average IV

**Note**: Migration file `024_add_instrument_metadata_to_strategies.sql` is mentioned in design but **NOT FOUND** in actual migrations.

#### Missing Python Dependency

**opstrat** library (version 0.1.7) - NOT INSTALLED
- Required for payoff diagram generation
- Handles complex multi-leg option strategies
- Missing from `requirements.txt`

#### Missing Frontend Components

**StrategyPayoffPanel.tsx**:
- Displays payoff diagram image
- Shows max profit, max loss, breakeven points
- Spot price adjustment slider
- Risk-reward ratio badge

**StrategyGreeksPanel.tsx**:
- Displays net Greeks (Delta, Gamma, Theta, Vega, IV)
- Instrument Greeks breakdown (toggleable)
- Color-coded positive/negative values
- Tooltips explaining each Greek

---

## 2. Premium/Discount Metrics - PARTIALLY IMPLEMENTED

### Status: ⚠️ **Planned but Not Verified**

**Document Reference**: `PREMIUM_AND_FUTURES_IMPLEMENTATION.md`

### Missing Features

**Premium/Discount Metrics for Options**:
- `premium_abs` - Absolute premium/discount
  - Formula: `(intrinsic + extrinsic) - model_price`
- `premium_pct` - Percentage premium/discount
  - Formula: `((intrinsic + extrinsic) - model_price) / model_price * 100`

**Implementation Status**:
- ✅ Design complete
- ✅ SQL expressions documented
- ⚠️ **Unclear if implemented** in `app/routes/fo.py`
- ❓ **Requires verification** with actual code inspection

**Missing Verification**:
1. Check if `premium_abs` and `premium_pct` are in `column_map` dictionary
2. Verify moneyness_series() function at line ~487-518
3. Verify strike_distribution() function at line ~617+

---

## 3. Additional Incomplete Features

### 3.1 Advanced Order Management (Phase 3 - NOT STARTED)

**Mentioned in documentation but not implemented**:
- Order assignment to strategies
- GTT (Good Till Triggered) orders
- Basket orders with strategy assignment
- Order modification/cancellation via UI

### 3.2 Real-time WebSocket Updates (Phase 4 - NOT STARTED)

**Mentioned but not implemented**:
- Strategy M2M streaming via WebSocket
- Real-time Greeks updates
- Live payoff graph updates

### 3.3 Advanced Analytics (Future Enhancements)

**Listed as "Optional Enhancements"**:
- Interactive payoff chart (Recharts instead of PNG)
- Greeks timeline (historical tracking)
- What-if analysis (volatility/time adjustment)
- Strategy comparison (side-by-side)
- Risk alerts (threshold notifications)
- Custom payoff overlays (pre-expiry curves)

---

## 4. Migration Status Analysis

### Existing Migrations (Backend)

**Found Migrations**:
- `022_update_caggs_with_new_columns.sql`
- `023_enhance_strategies_for_ui.sql`
- `023_enhance_strategies_for_ui_v2.sql`
- `024_add_instrument_metadata_to_strategies.sql`

**Issue**: Migrations 022-024 are **UNTRACKED** in git (shown as `??` in git status)

**Missing Migrations** (Referenced in Plans):
- `025_create_strategies_table.sql` ❌
- `026_create_strategy_instruments.sql` ❌
- `027_create_strategy_m2m_candles.sql` ❌
- `028_create_strategy_performance_daily.sql` ❌
- `029_add_strategy_id_to_positions_orders.sql` ❌

### Migration Integrity Risk

**Problem**: Untracked migration files may contain:
- Strategies table schema (possibly already created?)
- Greeks calculation functions
- Instrument metadata enhancements

**Action Required**: Inspect untracked migrations to determine actual database state.

---

## 5. Dependency Management Issues

### Missing Python Dependencies

**From Phase 2.5 Day 4 Plan**:
```
opstrat==0.1.7  # NOT in requirements.txt
```

**Current State**:
- ❌ Not installed
- ❌ Not in `backend/requirements.txt`
- ❌ PayoffService cannot function without it

### Existing Dependencies (Need Verification)

**From `backend/requirements.txt`** (modified but not committed):
- FastAPI, Uvicorn, asyncpg, etc. (standard deps)
- **Unknown**: If any strategy-related deps already added

---

## 6. Frontend Integration Gaps

### Missing TypeScript Types

**Required Type Definitions** (not in `frontend/src/types.ts`):

```typescript
// Strategy types
interface Strategy {
  strategy_id: number;
  strategy_name: string;
  trading_account_id: string;
  description?: string;
  status: 'active' | 'closed' | 'archived';
  is_default: boolean;
  tags?: string[];
  total_pnl?: number;
  current_m2m?: number;
  created_at: string;
  updated_at: string;
  instrument_count?: number;
}

interface StrategyInstrument {
  id: number;
  strategy_id: number;
  tradingsymbol: string;
  exchange: 'NSE' | 'NFO' | 'BSE';
  direction: 'BUY' | 'SELL';
  quantity: number;
  entry_price: number;
  current_price?: number;
  current_pnl?: number;
  // ... more fields
}

interface M2MCandle {
  strategy_id: number;
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  instrument_count: number;
}
```

### Missing Service Layer

**API Client Functions** (not in `frontend/src/services/strategies.ts`):
- `fetchStrategies(accountId)`
- `createStrategy(accountId, data)`
- `addInstrument(strategyId, accountId, data)`
- `fetchStrategyM2M(strategyId, accountId, startTime, endTime)`
- `getStrategyPayoff(strategyId, accountId, spotPrice, spotRange)`
- `getStrategyGreeks(strategyId, accountId, includeInstruments)`

---

## 7. Testing & Documentation Gaps

### Missing Test Files

**No tests found for**:
- Strategy CRUD operations
- M2M calculation worker
- Payoff service
- Greeks service
- Strategy API endpoints

### Missing Documentation

**User-Facing Documentation**:
- ❌ Strategy System user guide
- ❌ How to create and manage strategies
- ❌ Understanding payoff graphs
- ❌ Greeks interpretation guide

**Developer Documentation**:
- ❌ M2M calculation algorithm explanation
- ❌ Strategy architecture diagram
- ❌ Database schema documentation (for strategies)

---

## 8. Summary of Pending Requirements

### Critical (Blocking Production)

1. **Strategies Database Schema** (Day 1)
   - 4 new tables
   - 5 new migrations
   - Database functions and triggers

2. **Strategy CRUD APIs** (Day 1)
   - 10+ new endpoints
   - 4 new backend service files

3. **M2M Calculation Engine** (Day 2)
   - Background worker
   - LTP fetching logic
   - OHLC candle storage

4. **Strategy Frontend Components** (Day 3)
   - 7 new React components
   - Context provider
   - Service layer
   - TypeScript types

5. **Payoff & Greeks** (Day 4)
   - opstrat library integration
   - PayoffService implementation
   - GreeksService implementation
   - 2 new frontend panels

### High Priority (Functional Completeness)

6. **Premium/Discount Metrics Verification**
   - Verify implementation in fo.py
   - Test with real data

7. **Migration Integrity**
   - Inspect untracked migrations (022-024)
   - Determine database state
   - Create missing migrations (025-029)

8. **Dependency Management**
   - Add opstrat to requirements.txt
   - Test installation

### Medium Priority (Quality & UX)

9. **Testing**
   - Unit tests for services
   - Integration tests for APIs
   - End-to-end tests for workflows

10. **Documentation**
    - User guides
    - API documentation
    - Architecture diagrams

---

## 9. Estimated Implementation Effort

### Time Estimates (from Design Documents)

| Phase | Description | Estimated Time | Status |
|-------|-------------|----------------|--------|
| Day 1 | Database & Backend APIs | 6-8 hours | ❌ Not Started |
| Day 2 | M2M Calculation Engine | 4-6 hours | ❌ Not Started |
| Day 3 | Frontend Components | 6-8 hours | ❌ Not Started |
| Day 4 | Payoff Graphs & Greeks | 5-8 hours | ❌ Not Started |
| Testing & Polish | Integration & Testing | 8-10 hours | ❌ Not Started |
| **Total** | **Phase 2.5 Complete** | **29-40 hours (4-5 days)** | **0% Complete** |

### Risk Assessment

**Complexity**: HIGH
**Dependencies**: CRITICAL (blocks Phase 3 - Order Management)
**Technical Debt**: ACCUMULATING (design-code divergence)

---

## 10. Recommendations

### Immediate Actions

1. **Prioritize Phase 2.5 Day 1**:
   - Implement strategies database schema
   - Create backend CRUD APIs
   - Get basic strategy creation working

2. **Inspect Untracked Migrations**:
   - Read migrations 022-024
   - Determine what's already in database
   - Avoid duplicate migrations

3. **Verify Premium/Discount Implementation**:
   - Inspect `app/routes/fo.py` code
   - Test /fo/moneyness-series endpoint
   - Confirm premium_abs and premium_pct work

### Short-term (Next Sprint)

4. **Complete M2M Worker**:
   - Critical for strategy P&L tracking
   - Test with mock strategies first

5. **Build Core Frontend Components**:
   - StrategySelector
   - CreateStrategyModal
   - StrategyInstrumentsPanel

### Long-term (Next Quarter)

6. **Payoff Graphs & Greeks**:
   - Install opstrat
   - Implement PayoffService
   - Build visualization panels

7. **Advanced Features** (Phase 3+):
   - Order management with strategy assignment
   - Real-time WebSocket updates
   - Advanced analytics

---

## 11. Impact Analysis

### User Impact

**Current State**:
- ✅ Users can view F&O analytics
- ✅ Users can see positions and orders (basic)
- ❌ **Users CANNOT organize trades into strategies**
- ❌ **Users CANNOT track P&L per strategy**
- ❌ **Users CANNOT see payoff graphs**
- ❌ **Users CANNOT view Greeks**

### Business Impact

**Revenue Risk**: HIGH
- Strategy management is a core feature for professional traders
- Missing functionality reduces competitive advantage
- May delay user acquisition/retention

**Technical Debt**: MEDIUM-HIGH
- Large gap between design and implementation
- Accumulating backlog of features
- Risk of design staleness

---

## 12. Conclusion

The backend service has **substantial incomplete work** concentrated in **Phase 2.5 (Strategy System)**. An estimated **29-40 hours of development** are required to complete the designed features.

**Key Findings**:
1. ✅ KiteConnect integration is complete and production-ready
2. ✅ F&O analytics are functional
3. ❌ **Entire Strategy System (70% of Phase 2.5) is NOT implemented**
4. ❌ **Critical M2M calculation engine is missing**
5. ❌ **All strategy frontend components are missing**
6. ❌ **Payoff graphs and Greeks are not implemented**

**Critical Path**: Database schema → Backend APIs → M2M Worker → Frontend Components → Payoff/Greeks

**Recommendation**: **Prioritize completion of Strategy System** before proceeding to Phase 3 (Order Management), as strategies are a foundational feature.

---

**Document Version**: 1.0
**Last Updated**: 2025-11-09
**Next Review**: After Phase 2.5 Day 1 completion
