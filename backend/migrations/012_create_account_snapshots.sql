-- Migration 012: Create Account Snapshot Tables
-- Purpose: Store historical snapshots of positions, holdings, and funds
-- Date: 2025-10-31

-- ============================================================================
-- Position Snapshots (Time-series)
-- ============================================================================

CREATE TABLE IF NOT EXISTS position_snapshots (
    snapshot_time TIMESTAMPTZ NOT NULL,
    account_id VARCHAR(255) NOT NULL,
    tradingsymbol VARCHAR(100) NOT NULL,
    exchange VARCHAR(20),
    product_type VARCHAR(50),
    quantity NUMERIC(20,8),
    average_price NUMERIC(20,8),
    last_price NUMERIC(20,8),
    market_value NUMERIC(20,8),
    unrealized_pnl NUMERIC(20,8),
    realized_pnl NUMERIC(20,8),
    margin_used NUMERIC(20,8),
    side VARCHAR(10),  -- 'long' or 'short'
    strike_price NUMERIC(20,8),
    expiry_date DATE,
    option_type VARCHAR(10),  -- 'CE' or 'PE'
    snapshot_data JSONB DEFAULT '{}'::jsonb,  -- Full position data from ticker_service
    PRIMARY KEY (snapshot_time, account_id, tradingsymbol)
);

-- Create TimescaleDB hypertable for position_snapshots
SELECT create_hypertable(
    'position_snapshots',
    'snapshot_time',
    if_not_exists => TRUE,
    chunk_time_interval => INTERVAL '1 day'
);

-- Indexes for efficient queries
CREATE INDEX IF NOT EXISTS idx_position_snapshots_account
    ON position_snapshots(account_id, snapshot_time DESC);

CREATE INDEX IF NOT EXISTS idx_position_snapshots_symbol
    ON position_snapshots(account_id, tradingsymbol, snapshot_time DESC);

CREATE INDEX IF NOT EXISTS idx_position_snapshots_time
    ON position_snapshots(snapshot_time DESC);

-- Compression policy (compress data older than 7 days)
SELECT add_compression_policy('position_snapshots', INTERVAL '7 days', if_not_exists => TRUE);

-- Retention policy (keep data for 90 days)
SELECT add_retention_policy('position_snapshots', INTERVAL '90 days', if_not_exists => TRUE);

-- ============================================================================
-- Holdings Snapshots (Time-series)
-- ============================================================================

CREATE TABLE IF NOT EXISTS holdings_snapshots (
    snapshot_time TIMESTAMPTZ NOT NULL,
    account_id VARCHAR(255) NOT NULL,
    tradingsymbol VARCHAR(100) NOT NULL,
    exchange VARCHAR(20),
    quantity NUMERIC(20,8),
    average_price NUMERIC(20,8),
    current_price NUMERIC(20,8),
    market_value NUMERIC(20,8),
    pnl NUMERIC(20,8),
    day_change NUMERIC(20,8),
    day_change_percent NUMERIC(10,4),
    holding_type VARCHAR(50) DEFAULT 'equity',  -- 'equity', 'etf', 'mf'
    snapshot_data JSONB DEFAULT '{}'::jsonb,  -- Full holding data from ticker_service
    PRIMARY KEY (snapshot_time, account_id, tradingsymbol)
);

-- Create TimescaleDB hypertable for holdings_snapshots
SELECT create_hypertable(
    'holdings_snapshots',
    'snapshot_time',
    if_not_exists => TRUE,
    chunk_time_interval => INTERVAL '1 day'
);

-- Indexes for efficient queries
CREATE INDEX IF NOT EXISTS idx_holdings_snapshots_account
    ON holdings_snapshots(account_id, snapshot_time DESC);

CREATE INDEX IF NOT EXISTS idx_holdings_snapshots_symbol
    ON holdings_snapshots(account_id, tradingsymbol, snapshot_time DESC);

CREATE INDEX IF NOT EXISTS idx_holdings_snapshots_time
    ON holdings_snapshots(snapshot_time DESC);

-- Compression policy (compress data older than 7 days)
SELECT add_compression_policy('holdings_snapshots', INTERVAL '7 days', if_not_exists => TRUE);

-- Retention policy (keep data for 90 days)
SELECT add_retention_policy('holdings_snapshots', INTERVAL '90 days', if_not_exists => TRUE);

-- ============================================================================
-- Funds Snapshots (Time-series)
-- ============================================================================

CREATE TABLE IF NOT EXISTS funds_snapshots (
    snapshot_time TIMESTAMPTZ NOT NULL,
    account_id VARCHAR(255) NOT NULL,
    segment VARCHAR(20) NOT NULL,  -- 'equity', 'commodity', etc.
    available_cash NUMERIC(12,2),
    available_margin NUMERIC(12,2),
    used_margin NUMERIC(12,2),
    net NUMERIC(12,2),
    collateral NUMERIC(12,2),
    opening_balance NUMERIC(12,2),
    payin NUMERIC(12,2),
    payout NUMERIC(12,2),
    realized_pnl NUMERIC(12,2),
    unrealized_pnl NUMERIC(12,2),
    snapshot_data JSONB DEFAULT '{}'::jsonb,  -- Full funds data from ticker_service
    PRIMARY KEY (snapshot_time, account_id, segment)
);

-- Create TimescaleDB hypertable for funds_snapshots
SELECT create_hypertable(
    'funds_snapshots',
    'snapshot_time',
    if_not_exists => TRUE,
    chunk_time_interval => INTERVAL '1 day'
);

-- Indexes for efficient queries
CREATE INDEX IF NOT EXISTS idx_funds_snapshots_account
    ON funds_snapshots(account_id, segment, snapshot_time DESC);

CREATE INDEX IF NOT EXISTS idx_funds_snapshots_time
    ON funds_snapshots(snapshot_time DESC);

-- Compression policy (compress data older than 7 days)
SELECT add_compression_policy('funds_snapshots', INTERVAL '7 days', if_not_exists => TRUE);

-- Retention policy (keep data for 90 days)
SELECT add_retention_policy('funds_snapshots', INTERVAL '90 days', if_not_exists => TRUE);

-- ============================================================================
-- Continuous Aggregates for Daily Summaries
-- ============================================================================

-- Daily position summary
CREATE MATERIALIZED VIEW IF NOT EXISTS position_daily_summary
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 day', snapshot_time) AS day,
    account_id,
    tradingsymbol,
    AVG(quantity) AS avg_quantity,
    AVG(last_price) AS avg_price,
    AVG(unrealized_pnl) AS avg_unrealized_pnl,
    MAX(unrealized_pnl) AS max_unrealized_pnl,
    MIN(unrealized_pnl) AS min_unrealized_pnl,
    COUNT(*) AS snapshot_count
FROM position_snapshots
GROUP BY day, account_id, tradingsymbol;

-- Refresh policy for position_daily_summary
SELECT add_continuous_aggregate_policy('position_daily_summary',
    start_offset => INTERVAL '3 days',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour',
    if_not_exists => TRUE
);

-- Daily funds summary
CREATE MATERIALIZED VIEW IF NOT EXISTS funds_daily_summary
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 day', snapshot_time) AS day,
    account_id,
    segment,
    AVG(available_margin) AS avg_available_margin,
    AVG(used_margin) AS avg_used_margin,
    MAX(used_margin) AS max_used_margin,
    MIN(available_margin) AS min_available_margin,
    COUNT(*) AS snapshot_count
FROM funds_snapshots
GROUP BY day, account_id, segment;

-- Refresh policy for funds_daily_summary
SELECT add_continuous_aggregate_policy('funds_daily_summary',
    start_offset => INTERVAL '3 days',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour',
    if_not_exists => TRUE
);

-- ============================================================================
-- Helper Functions
-- ============================================================================

-- Function to get position snapshot at specific time
CREATE OR REPLACE FUNCTION get_positions_at_time(
    p_account_id VARCHAR(255),
    p_timestamp TIMESTAMPTZ
)
RETURNS TABLE (
    tradingsymbol VARCHAR(100),
    quantity NUMERIC(20,8),
    average_price NUMERIC(20,8),
    last_price NUMERIC(20,8),
    unrealized_pnl NUMERIC(20,8),
    snapshot_time TIMESTAMPTZ
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        ps.tradingsymbol,
        ps.quantity,
        ps.average_price,
        ps.last_price,
        ps.unrealized_pnl,
        ps.snapshot_time
    FROM position_snapshots ps
    WHERE ps.account_id = p_account_id
      AND ps.snapshot_time <= p_timestamp
      AND ps.snapshot_time = (
          SELECT MAX(snapshot_time)
          FROM position_snapshots
          WHERE account_id = p_account_id
            AND tradingsymbol = ps.tradingsymbol
            AND snapshot_time <= p_timestamp
      )
    ORDER BY ps.tradingsymbol;
END;
$$ LANGUAGE plpgsql;

-- Function to get funds snapshot at specific time
CREATE OR REPLACE FUNCTION get_funds_at_time(
    p_account_id VARCHAR(255),
    p_segment VARCHAR(20),
    p_timestamp TIMESTAMPTZ
)
RETURNS TABLE (
    available_cash NUMERIC(12,2),
    available_margin NUMERIC(12,2),
    used_margin NUMERIC(12,2),
    net NUMERIC(12,2),
    snapshot_time TIMESTAMPTZ
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        fs.available_cash,
        fs.available_margin,
        fs.used_margin,
        fs.net,
        fs.snapshot_time
    FROM funds_snapshots fs
    WHERE fs.account_id = p_account_id
      AND fs.segment = p_segment
      AND fs.snapshot_time <= p_timestamp
    ORDER BY fs.snapshot_time DESC
    LIMIT 1;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- Comments
-- ============================================================================

COMMENT ON TABLE position_snapshots IS 'Historical snapshots of trading positions taken every N minutes';
COMMENT ON TABLE holdings_snapshots IS 'Historical snapshots of long-term holdings taken every N minutes';
COMMENT ON TABLE funds_snapshots IS 'Historical snapshots of account funds and margins taken every N minutes';

COMMENT ON FUNCTION get_positions_at_time IS 'Retrieve position snapshot closest to specified timestamp';
COMMENT ON FUNCTION get_funds_at_time IS 'Retrieve funds snapshot closest to specified timestamp';
