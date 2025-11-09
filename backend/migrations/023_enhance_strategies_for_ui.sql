-- Migration 023: Enhance Strategies for UI-based Manual Strategy Management
-- Phase 2.5: Strategy System
--
-- This migration enhances the existing strategy table to support:
-- - UI-based manual strategy creation (freeform names)
-- - Manual instrument assignments (buy/sell, price, qty)
-- - Per-trading-account strategies (not multi-account)
-- - Default strategy per trading account
-- - Minute-wise M2M tracking

-- =============================================================================
-- 1. Modify existing strategy table
-- =============================================================================

-- Add new columns for UI-based strategies
ALTER TABLE strategy
ADD COLUMN IF NOT EXISTS trading_account_id VARCHAR(100) REFERENCES trading_account(account_id) ON DELETE CASCADE,
ADD COLUMN IF NOT EXISTS is_default BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS tags TEXT[],
ADD COLUMN IF NOT EXISTS current_m2m NUMERIC(15, 2) DEFAULT 0,
ADD COLUMN IF NOT EXISTS total_capital_deployed NUMERIC(15, 2) DEFAULT 0,
ADD COLUMN IF NOT EXISTS total_margin_used NUMERIC(15, 2) DEFAULT 0,
ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ;

-- Update strategy_type to allow 'manual' and 'default'
COMMENT ON COLUMN strategy.strategy_type IS 'Strategy type: manual, default, scalping, hedging, etc.';

-- Make account_ids nullable (for single-account strategies)
ALTER TABLE strategy
ALTER COLUMN account_ids DROP NOT NULL;

-- Add index for trading_account_id
CREATE INDEX IF NOT EXISTS idx_strategy_trading_account ON strategy(trading_account_id);

-- Add unique constraint for default strategies per account
CREATE UNIQUE INDEX IF NOT EXISTS idx_strategy_default_per_account
ON strategy(trading_account_id)
WHERE is_default = TRUE;


-- =============================================================================
-- 2. Create strategy_instruments table
-- =============================================================================

CREATE TABLE IF NOT EXISTS strategy_instruments (
  id SERIAL PRIMARY KEY,
  strategy_id INTEGER NOT NULL REFERENCES strategy(strategy_id) ON DELETE CASCADE,

  -- Instrument identification
  tradingsymbol VARCHAR(50) NOT NULL,
  exchange VARCHAR(10) NOT NULL,
  instrument_token BIGINT,

  -- Position details (manual entry)
  direction VARCHAR(4) NOT NULL CHECK (direction IN ('BUY', 'SELL')),
  quantity INTEGER NOT NULL,
  entry_price NUMERIC(12, 2) NOT NULL,

  -- Current state (updated by worker)
  current_price NUMERIC(12, 2),
  current_pnl NUMERIC(15, 2),

  -- Timestamps
  added_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  -- User notes
  notes TEXT,

  -- Metadata
  metadata JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX idx_strategy_instruments_strategy ON strategy_instruments(strategy_id);
CREATE INDEX idx_strategy_instruments_symbol ON strategy_instruments(tradingsymbol);

-- Trigger for updated_at
CREATE TRIGGER update_strategy_instruments_updated_at
BEFORE UPDATE ON strategy_instruments
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();


-- =============================================================================
-- 3. Create strategy_m2m_candles table (TimescaleDB hypertable)
-- =============================================================================

CREATE TABLE IF NOT EXISTS strategy_m2m_candles (
  timestamp TIMESTAMPTZ NOT NULL,
  strategy_id INTEGER NOT NULL REFERENCES strategy(strategy_id) ON DELETE CASCADE,

  -- OHLC for M2M
  open NUMERIC(15, 2) NOT NULL,
  high NUMERIC(15, 2) NOT NULL,
  low NUMERIC(15, 2) NOT NULL,
  close NUMERIC(15, 2) NOT NULL,

  -- Metadata
  instrument_count INTEGER DEFAULT 0,
  volume INTEGER DEFAULT 0,  -- For future use

  PRIMARY KEY (timestamp, strategy_id)
);

-- Convert to TimescaleDB hypertable (1-minute chunks aggregated into 1-day chunks)
SELECT create_hypertable(
  'strategy_m2m_candles',
  'timestamp',
  chunk_time_interval => INTERVAL '1 day',
  if_not_exists => TRUE
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_m2m_strategy_time ON strategy_m2m_candles(strategy_id, timestamp DESC);

-- Enable compression (after 7 days)
ALTER TABLE strategy_m2m_candles SET (
  timescaledb.compress,
  timescaledb.compress_segmentby = 'strategy_id',
  timescaledb.compress_orderby = 'timestamp DESC'
);

SELECT add_compression_policy('strategy_m2m_candles', INTERVAL '7 days', if_not_exists => TRUE);


-- =============================================================================
-- 4. Create strategy_performance_daily table
-- =============================================================================

CREATE TABLE IF NOT EXISTS strategy_performance_daily (
  id SERIAL PRIMARY KEY,
  strategy_id INTEGER NOT NULL REFERENCES strategy(strategy_id) ON DELETE CASCADE,
  date DATE NOT NULL,

  -- P&L metrics
  day_pnl NUMERIC(15, 2) DEFAULT 0,
  cumulative_pnl NUMERIC(15, 2) DEFAULT 0,
  realized_pnl NUMERIC(15, 2) DEFAULT 0,
  unrealized_pnl NUMERIC(15, 2) DEFAULT 0,

  -- Position metrics
  open_positions INTEGER DEFAULT 0,
  closed_positions INTEGER DEFAULT 0,
  avg_position_size NUMERIC(15, 2) DEFAULT 0,

  -- Trading metrics
  total_trades INTEGER DEFAULT 0,
  winning_trades INTEGER DEFAULT 0,
  losing_trades INTEGER DEFAULT 0,
  win_rate NUMERIC(5, 2) DEFAULT 0,

  -- Capital metrics
  capital_deployed NUMERIC(15, 2) DEFAULT 0,
  margin_used NUMERIC(15, 2) DEFAULT 0,
  max_drawdown NUMERIC(15, 2) DEFAULT 0,

  -- Risk metrics
  sharpe_ratio NUMERIC(8, 4) DEFAULT 0,
  sortino_ratio NUMERIC(8, 4) DEFAULT 0,
  max_consecutive_losses INTEGER DEFAULT 0,

  -- ROI
  roi_percent NUMERIC(8, 4) DEFAULT 0,

  -- Timestamps
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  UNIQUE(strategy_id, date)
);

CREATE INDEX idx_perf_strategy_date ON strategy_performance_daily(strategy_id, date DESC);

-- Trigger for updated_at
CREATE TRIGGER update_strategy_performance_updated_at
BEFORE UPDATE ON strategy_performance_daily
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();


-- =============================================================================
-- 5. Add strategy_id to existing tables (if not exists)
-- =============================================================================

-- account_order already has strategy_id (line 97 in 008 migration)
-- Just ensure it's nullable and indexed
ALTER TABLE account_order ALTER COLUMN strategy_id DROP NOT NULL IF EXISTS;

-- Add strategy_id to account_position if not exists
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'account_position' AND column_name = 'strategy_id'
  ) THEN
    ALTER TABLE account_position ADD COLUMN strategy_id INTEGER REFERENCES strategy(strategy_id);
    CREATE INDEX idx_account_position_strategy ON account_position(strategy_id) WHERE strategy_id IS NOT NULL;
  END IF;
END $$;

-- Add strategy_id to account_holding if not exists
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'account_holding' AND column_name = 'strategy_id'
  ) THEN
    ALTER TABLE account_holding ADD COLUMN strategy_id INTEGER REFERENCES strategy(strategy_id);
    CREATE INDEX idx_account_holding_strategy ON account_holding(strategy_id) WHERE strategy_id IS NOT NULL;
  END IF;
END $$;


-- =============================================================================
-- 6. Create function to auto-create default strategy for new accounts
-- =============================================================================

CREATE OR REPLACE FUNCTION create_default_strategy_for_account()
RETURNS TRIGGER AS $$
BEGIN
  -- Create default strategy for new trading account
  INSERT INTO strategy (
    trading_account_id,
    strategy_name,
    strategy_type,
    description,
    is_default,
    status,
    is_active,
    created_by
  ) VALUES (
    NEW.account_id,
    'Default Strategy',
    'default',
    'Auto-created default strategy for all unassigned positions',
    TRUE,
    'active',
    TRUE,
    NEW.account_id  -- Use account_id as creator for now
  );

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger to auto-create default strategy
DROP TRIGGER IF EXISTS trigger_create_default_strategy_for_account ON trading_account;
CREATE TRIGGER trigger_create_default_strategy_for_account
AFTER INSERT ON trading_account
FOR EACH ROW
EXECUTE FUNCTION create_default_strategy_for_account();


-- =============================================================================
-- 7. Backfill default strategies for existing accounts
-- =============================================================================

-- Create default strategy for any trading accounts without one
INSERT INTO strategy (
  trading_account_id,
  strategy_name,
  strategy_type,
  description,
  is_default,
  status,
  is_active,
  created_by
)
SELECT
  ta.account_id,
  'Default Strategy',
  'default',
  'Auto-created default strategy for all unassigned positions',
  TRUE,
  'active',
  TRUE,
  ta.account_id
FROM trading_account ta
WHERE NOT EXISTS (
  SELECT 1 FROM strategy s
  WHERE s.trading_account_id = ta.account_id
  AND s.is_default = TRUE
)
ON CONFLICT DO NOTHING;


-- =============================================================================
-- 8. Comments for documentation
-- =============================================================================

COMMENT ON TABLE strategy IS 'Strategy configurations - supports both automated (SDK) and manual (UI) strategies';
COMMENT ON TABLE strategy_instruments IS 'Manual instrument assignments for UI-based strategies';
COMMENT ON TABLE strategy_m2m_candles IS 'Minute-wise OHLC candles for strategy M2M tracking';
COMMENT ON TABLE strategy_performance_daily IS 'Daily performance snapshots for strategies';

COMMENT ON COLUMN strategy.is_default IS 'Default strategy contains all positions not assigned to custom strategies';
COMMENT ON COLUMN strategy.trading_account_id IS 'Single trading account this strategy belongs to (NULL for multi-account SDK strategies)';
COMMENT ON COLUMN strategy_instruments.direction IS 'BUY = -ve cash flow (paid), SELL = +ve cash flow (received)';
COMMENT ON COLUMN strategy_instruments.entry_price IS 'Entry price - can be system calculated or manual override';


-- =============================================================================
-- 9. Grant permissions (adjust as needed)
-- =============================================================================

-- GRANT SELECT, INSERT, UPDATE, DELETE ON strategy_instruments TO your_app_user;
-- GRANT SELECT, INSERT, UPDATE, DELETE ON strategy_m2m_candles TO your_app_user;
-- GRANT SELECT, INSERT, UPDATE, DELETE ON strategy_performance_daily TO your_app_user;
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO your_app_user;


-- =============================================================================
-- Migration complete
-- =============================================================================

-- Verify tables created
DO $$
DECLARE
  table_count INTEGER;
BEGIN
  SELECT COUNT(*) INTO table_count
  FROM information_schema.tables
  WHERE table_schema = 'public'
  AND table_name IN ('strategy_instruments', 'strategy_m2m_candles', 'strategy_performance_daily');

  IF table_count = 3 THEN
    RAISE NOTICE 'Migration 023 completed successfully. All strategy tables created.';
  ELSE
    RAISE EXCEPTION 'Migration 023 failed. Expected 3 new tables, found %', table_count;
  END IF;
END $$;
