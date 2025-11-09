-- Migration 023 v2: Enhance Strategies for UI-based Manual Strategy Management
-- Phase 2.5: Strategy System (Fixed version)

-- =============================================================================
-- 1. Modify existing strategy table
-- =============================================================================

ALTER TABLE strategy
ADD COLUMN IF NOT EXISTS trading_account_id VARCHAR(100) REFERENCES trading_account(account_id) ON DELETE CASCADE,
ADD COLUMN IF NOT EXISTS is_default BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS tags TEXT[],
ADD COLUMN IF NOT EXISTS current_m2m NUMERIC(15, 2) DEFAULT 0,
ADD COLUMN IF NOT EXISTS total_capital_deployed NUMERIC(15, 2) DEFAULT 0,
ADD COLUMN IF NOT EXISTS total_margin_used NUMERIC(15, 2) DEFAULT 0,
ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ;

ALTER TABLE strategy
ALTER COLUMN account_ids DROP NOT NULL;

CREATE INDEX IF NOT EXISTS idx_strategy_trading_account ON strategy(trading_account_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_strategy_default_per_account
ON strategy(trading_account_id)
WHERE is_default = TRUE;


-- =============================================================================
-- 2. Create strategy_instruments table
-- =============================================================================

CREATE TABLE IF NOT EXISTS strategy_instruments (
  id SERIAL PRIMARY KEY,
  strategy_id INTEGER NOT NULL REFERENCES strategy(strategy_id) ON DELETE CASCADE,

  tradingsymbol VARCHAR(50) NOT NULL,
  exchange VARCHAR(10) NOT NULL,
  instrument_token BIGINT,

  direction VARCHAR(4) NOT NULL CHECK (direction IN ('BUY', 'SELL')),
  quantity INTEGER NOT NULL,
  entry_price NUMERIC(12, 2) NOT NULL,

  current_price NUMERIC(12, 2),
  current_pnl NUMERIC(15, 2),

  added_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  notes TEXT,
  metadata JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_strategy_instruments_strategy ON strategy_instruments(strategy_id);
CREATE INDEX IF NOT EXISTS idx_strategy_instruments_symbol ON strategy_instruments(tradingsymbol);

CREATE TRIGGER update_strategy_instruments_updated_at
BEFORE UPDATE ON strategy_instruments
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();


-- =============================================================================
-- 3. Create strategy_m2m_candles table (TimescaleDB hypertable)
-- =============================================================================

CREATE TABLE IF NOT EXISTS strategy_m2m_candles (
  timestamp TIMESTAMPTZ NOT NULL,
  strategy_id INTEGER NOT NULL REFERENCES strategy(strategy_id) ON DELETE CASCADE,

  open NUMERIC(15, 2) NOT NULL,
  high NUMERIC(15, 2) NOT NULL,
  low NUMERIC(15, 2) NOT NULL,
  close NUMERIC(15, 2) NOT NULL,

  instrument_count INTEGER DEFAULT 0,
  volume INTEGER DEFAULT 0,

  PRIMARY KEY (timestamp, strategy_id)
);

SELECT create_hypertable(
  'strategy_m2m_candles',
  'timestamp',
  chunk_time_interval => INTERVAL '1 day',
  if_not_exists => TRUE
);

CREATE INDEX IF NOT EXISTS idx_m2m_strategy_time ON strategy_m2m_candles(strategy_id, timestamp DESC);

ALTER TABLE strategy_m2m_candles SET (
  timescaledb.compress,
  timescaledb.compress_segmentby = 'strategy_id',
  timescaledb.compress_orderby = 'timestamp DESC'
);

SELECT add_compression_policy('strategy_m2m_candles', INTERVAL '7 days', if_not_exists => TRUE);


-- =============================================================================
-- 4. Create strategy_pnl_metrics table (renamed from strategy_performance_daily)
-- =============================================================================

CREATE TABLE IF NOT EXISTS strategy_pnl_metrics (
  id SERIAL PRIMARY KEY,
  strategy_id INTEGER NOT NULL REFERENCES strategy(strategy_id) ON DELETE CASCADE,
  metric_date DATE NOT NULL,

  day_pnl NUMERIC(15, 2) DEFAULT 0,
  cumulative_pnl NUMERIC(15, 2) DEFAULT 0,
  realized_pnl NUMERIC(15, 2) DEFAULT 0,
  unrealized_pnl NUMERIC(15, 2) DEFAULT 0,

  open_positions INTEGER DEFAULT 0,
  closed_positions INTEGER DEFAULT 0,
  avg_position_size NUMERIC(15, 2) DEFAULT 0,

  total_trades INTEGER DEFAULT 0,
  winning_trades INTEGER DEFAULT 0,
  losing_trades INTEGER DEFAULT 0,
  win_rate NUMERIC(5, 2) DEFAULT 0,

  capital_deployed NUMERIC(15, 2) DEFAULT 0,
  margin_used NUMERIC(15, 2) DEFAULT 0,
  max_drawdown NUMERIC(15, 2) DEFAULT 0,

  sharpe_ratio NUMERIC(8, 4) DEFAULT 0,
  sortino_ratio NUMERIC(8, 4) DEFAULT 0,
  max_consecutive_losses INTEGER DEFAULT 0,

  roi_percent NUMERIC(8, 4) DEFAULT 0,

  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  UNIQUE(strategy_id, metric_date)
);

CREATE INDEX IF NOT EXISTS idx_pnl_metrics_strategy_date ON strategy_pnl_metrics(strategy_id, metric_date DESC);

CREATE TRIGGER update_strategy_pnl_metrics_updated_at
BEFORE UPDATE ON strategy_pnl_metrics
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();


-- =============================================================================
-- 5. Add strategy_id to existing tables
-- =============================================================================

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
-- 6. Create function to auto-create default strategy
-- =============================================================================

CREATE OR REPLACE FUNCTION create_default_strategy_for_account()
RETURNS TRIGGER AS $$
BEGIN
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
    NEW.account_id
  );

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_create_default_strategy_for_account ON trading_account;
CREATE TRIGGER trigger_create_default_strategy_for_account
AFTER INSERT ON trading_account
FOR EACH ROW
EXECUTE FUNCTION create_default_strategy_for_account();


-- =============================================================================
-- 7. Backfill default strategies for existing accounts
-- =============================================================================

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
-- 8. Comments
-- =============================================================================

COMMENT ON TABLE strategy IS 'Strategy configurations - supports both automated (SDK) and manual (UI) strategies';
COMMENT ON TABLE strategy_instruments IS 'Manual instrument assignments for UI-based strategies';
COMMENT ON TABLE strategy_m2m_candles IS 'Minute-wise OHLC candles for strategy M2M tracking';
COMMENT ON TABLE strategy_pnl_metrics IS 'Daily performance snapshots for strategies';

COMMENT ON COLUMN strategy.is_default IS 'Default strategy contains all positions not assigned to custom strategies';
COMMENT ON COLUMN strategy.trading_account_id IS 'Single trading account this strategy belongs to';
COMMENT ON COLUMN strategy_instruments.direction IS 'BUY = -ve cash flow (paid), SELL = +ve cash flow (received)';


-- Verify
DO $$
DECLARE
  table_count INTEGER;
BEGIN
  SELECT COUNT(*) INTO table_count
  FROM information_schema.tables
  WHERE table_schema = 'public'
  AND table_name IN ('strategy_instruments', 'strategy_m2m_candles', 'strategy_pnl_metrics');

  IF table_count = 3 THEN
    RAISE NOTICE 'Migration 023 v2 completed successfully. All strategy tables created.';
  ELSE
    RAISE EXCEPTION 'Migration 023 v2 failed. Expected 3 new tables, found %', table_count;
  END IF;
END $$;
