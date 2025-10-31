-- Migration 008: Create Trading Accounts and Strategies tables
-- Sprint 4: Multi-Account Trading and Strategy Management

-- 1. Trading Accounts Table
-- Stores account metadata and credentials
CREATE TABLE IF NOT EXISTS trading_account (
    account_id VARCHAR(100) PRIMARY KEY,  -- user_id from ticker_service
    account_name VARCHAR(255) NOT NULL,
    broker VARCHAR(50) NOT NULL DEFAULT 'zerodha',
    is_active BOOLEAN NOT NULL DEFAULT true,

    -- Account status
    login_status VARCHAR(20) DEFAULT 'logged_out',  -- logged_out, logged_in, session_expired, error
    last_login_at TIMESTAMPTZ,
    last_sync_at TIMESTAMPTZ,

    -- Metadata
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Additional info
    metadata JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX idx_trading_account_active ON trading_account(is_active);
CREATE INDEX idx_trading_account_status ON trading_account(login_status);


-- 2. Account Positions Table
-- Caches current positions from ticker_service
CREATE TABLE IF NOT EXISTS account_position (
    id SERIAL PRIMARY KEY,
    account_id VARCHAR(100) NOT NULL REFERENCES trading_account(account_id) ON DELETE CASCADE,

    -- Position identification
    tradingsymbol VARCHAR(100) NOT NULL,
    exchange VARCHAR(20) NOT NULL,
    instrument_token BIGINT,

    -- Position details
    product VARCHAR(20),  -- MIS, NRML, CNC
    quantity INTEGER NOT NULL,
    average_price NUMERIC(12, 2),
    last_price NUMERIC(12, 2),

    -- P&L
    pnl NUMERIC(12, 2),
    day_pnl NUMERIC(12, 2),

    -- Timestamps
    synced_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Raw data from ticker_service
    raw_data JSONB DEFAULT '{}'::jsonb,

    UNIQUE(account_id, tradingsymbol, exchange, product)
);

CREATE INDEX idx_account_position_account ON account_position(account_id);
CREATE INDEX idx_account_position_symbol ON account_position(tradingsymbol);
CREATE INDEX idx_account_position_synced ON account_position(synced_at DESC);


-- 3. Account Orders Table
-- Tracks order history and status
CREATE TABLE IF NOT EXISTS account_order (
    order_id VARCHAR(100) PRIMARY KEY,
    account_id VARCHAR(100) NOT NULL REFERENCES trading_account(account_id) ON DELETE CASCADE,

    -- Order identification
    tradingsymbol VARCHAR(100) NOT NULL,
    exchange VARCHAR(20) NOT NULL,
    instrument_token BIGINT,

    -- Order details
    transaction_type VARCHAR(10),  -- BUY, SELL
    order_type VARCHAR(20),  -- MARKET, LIMIT, SL, SL-M
    product VARCHAR(20),  -- MIS, NRML, CNC
    quantity INTEGER NOT NULL,
    price NUMERIC(12, 2),
    trigger_price NUMERIC(12, 2),

    -- Order status
    status VARCHAR(20),  -- PENDING, OPEN, COMPLETE, CANCELLED, REJECTED
    status_message TEXT,
    filled_quantity INTEGER DEFAULT 0,
    average_price NUMERIC(12, 2),

    -- Timestamps
    placed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    synced_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Strategy linkage (NULL for manual orders)
    strategy_id INTEGER,

    -- Raw data from ticker_service
    raw_data JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX idx_account_order_account ON account_order(account_id);
CREATE INDEX idx_account_order_status ON account_order(status);
CREATE INDEX idx_account_order_strategy ON account_order(strategy_id) WHERE strategy_id IS NOT NULL;
CREATE INDEX idx_account_order_placed ON account_order(placed_at DESC);


-- 4. Account Holdings Table
-- Long-term holdings (delivery positions)
CREATE TABLE IF NOT EXISTS account_holding (
    id SERIAL PRIMARY KEY,
    account_id VARCHAR(100) NOT NULL REFERENCES trading_account(account_id) ON DELETE CASCADE,

    -- Holding identification
    tradingsymbol VARCHAR(100) NOT NULL,
    exchange VARCHAR(20) NOT NULL,
    isin VARCHAR(20),

    -- Holding details
    quantity INTEGER NOT NULL,
    average_price NUMERIC(12, 2),
    last_price NUMERIC(12, 2),

    -- P&L
    pnl NUMERIC(12, 2),
    day_pnl NUMERIC(12, 2),

    -- Timestamps
    synced_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Raw data from ticker_service
    raw_data JSONB DEFAULT '{}'::jsonb,

    UNIQUE(account_id, tradingsymbol, exchange)
);

CREATE INDEX idx_account_holding_account ON account_holding(account_id);
CREATE INDEX idx_account_holding_symbol ON account_holding(tradingsymbol);


-- 5. Account Funds Table
-- Margin and funds information
CREATE TABLE IF NOT EXISTS account_funds (
    id SERIAL PRIMARY KEY,
    account_id VARCHAR(100) NOT NULL REFERENCES trading_account(account_id) ON DELETE CASCADE,

    -- Fund segments
    segment VARCHAR(20) NOT NULL,  -- equity, commodity

    -- Available funds
    available_cash NUMERIC(12, 2),
    available_margin NUMERIC(12, 2),

    -- Used funds
    used_margin NUMERIC(12, 2),

    -- Limits
    net NUMERIC(12, 2),

    -- Timestamps
    synced_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Raw data from ticker_service
    raw_data JSONB DEFAULT '{}'::jsonb,

    UNIQUE(account_id, segment)
);

CREATE INDEX idx_account_funds_account ON account_funds(account_id);
CREATE INDEX idx_account_funds_synced ON account_funds(synced_at DESC);


-- 6. Strategy Table
-- Strategy configurations
CREATE TABLE IF NOT EXISTS strategy (
    strategy_id SERIAL PRIMARY KEY,
    strategy_name VARCHAR(255) NOT NULL,
    description TEXT,

    -- Strategy type and configuration
    strategy_type VARCHAR(50) NOT NULL,  -- scalping, hedging, spreads, etc.
    config JSONB NOT NULL DEFAULT '{}'::jsonb,

    -- Account associations (array of account_ids)
    account_ids TEXT[] NOT NULL,

    -- Status
    status VARCHAR(20) NOT NULL DEFAULT 'draft',  -- draft, active, paused, stopped
    is_active BOOLEAN NOT NULL DEFAULT false,

    -- Performance tracking
    total_pnl NUMERIC(12, 2) DEFAULT 0,
    total_trades INTEGER DEFAULT 0,

    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    stopped_at TIMESTAMPTZ,

    -- Creator/owner
    created_by VARCHAR(100),

    -- Metadata
    metadata JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX idx_strategy_status ON strategy(status);
CREATE INDEX idx_strategy_active ON strategy(is_active);
CREATE INDEX idx_strategy_type ON strategy(strategy_type);
CREATE INDEX idx_strategy_accounts ON strategy USING GIN(account_ids);


-- 7. Strategy Snapshots Table (TimescaleDB Hypertable)
-- Time-series data for strategy performance tracking
CREATE TABLE IF NOT EXISTS strategy_snapshot (
    snapshot_time TIMESTAMPTZ NOT NULL,
    strategy_id INTEGER NOT NULL REFERENCES strategy(strategy_id) ON DELETE CASCADE,

    -- Performance metrics
    total_pnl NUMERIC(12, 2),
    day_pnl NUMERIC(12, 2),
    unrealized_pnl NUMERIC(12, 2),
    realized_pnl NUMERIC(12, 2),

    -- Position metrics
    open_positions INTEGER,
    total_quantity INTEGER,

    -- Capital metrics
    capital_deployed NUMERIC(12, 2),
    margin_used NUMERIC(12, 2),

    -- Trading metrics
    total_trades INTEGER,
    winning_trades INTEGER,
    losing_trades INTEGER,

    -- Risk metrics
    max_drawdown NUMERIC(12, 2),
    sharpe_ratio NUMERIC(8, 4),

    -- Detailed data
    positions JSONB DEFAULT '[]'::jsonb,
    orders JSONB DEFAULT '[]'::jsonb,

    PRIMARY KEY (snapshot_time, strategy_id)
);

-- Convert to TimescaleDB hypertable
SELECT create_hypertable('strategy_snapshot', 'snapshot_time',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);

CREATE INDEX idx_strategy_snapshot_strategy ON strategy_snapshot(strategy_id, snapshot_time DESC);
CREATE INDEX idx_strategy_snapshot_pnl ON strategy_snapshot(strategy_id, total_pnl);


-- Update triggers for updated_at columns
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_trading_account_updated_at BEFORE UPDATE ON trading_account
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_account_position_updated_at BEFORE UPDATE ON account_position
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_account_order_updated_at BEFORE UPDATE ON account_order
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_account_holding_updated_at BEFORE UPDATE ON account_holding
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_account_funds_updated_at BEFORE UPDATE ON account_funds
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_strategy_updated_at BEFORE UPDATE ON strategy
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();


-- Grant permissions (adjust as needed for your setup)
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO your_app_user;
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO your_app_user;

-- Comments for documentation
COMMENT ON TABLE trading_account IS 'Stores trading account credentials and metadata';
COMMENT ON TABLE account_position IS 'Caches current positions from ticker_service';
COMMENT ON TABLE account_order IS 'Tracks order history and status';
COMMENT ON TABLE account_holding IS 'Stores long-term delivery holdings';
COMMENT ON TABLE account_funds IS 'Margin and funds information by segment';
COMMENT ON TABLE strategy IS 'Strategy configurations and metadata';
COMMENT ON TABLE strategy_snapshot IS 'Time-series snapshots of strategy performance';
