-- Migration: Create statement parsing and funds categorization tables
-- Purpose: Store and categorize Zerodha statement transactions for margin analysis
-- Created: 2025-11-09

-- ============================================================================
-- 1. Statement Uploads Table
-- ============================================================================
CREATE TABLE IF NOT EXISTS statement_uploads (
    id BIGSERIAL PRIMARY KEY,

    -- Ownership
    account_id VARCHAR(100) NOT NULL,
    uploaded_by VARCHAR(100),  -- User ID who uploaded

    -- File metadata
    filename VARCHAR(255) NOT NULL,
    file_size_bytes BIGINT,
    file_hash VARCHAR(64),  -- SHA256 for deduplication

    -- Parsing status
    status VARCHAR(20) DEFAULT 'pending',  -- pending, processing, completed, failed
    parsed_at TIMESTAMPTZ,
    error_message TEXT,

    -- Statement period
    statement_start_date DATE,
    statement_end_date DATE,

    -- Summary stats
    total_transactions INTEGER DEFAULT 0,
    total_debits DECIMAL(15, 2) DEFAULT 0,
    total_credits DECIMAL(15, 2) DEFAULT 0,

    -- Timestamps
    uploaded_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Metadata
    metadata JSONB DEFAULT '{}'::jsonb,

    -- Prevent duplicate uploads
    UNIQUE(account_id, file_hash)
);

-- ============================================================================
-- 2. Statement Transactions Table (TimescaleDB hypertable)
-- ============================================================================
CREATE TABLE IF NOT EXISTS statement_transactions (
    id BIGSERIAL,

    -- Foreign key to upload
    upload_id BIGINT NOT NULL REFERENCES statement_uploads(id) ON DELETE CASCADE,
    account_id VARCHAR(100) NOT NULL,

    -- Transaction identification
    transaction_date TIMESTAMPTZ NOT NULL,
    transaction_type VARCHAR(50),  -- buy, sell, dividend, interest, etc.
    description TEXT,

    -- Instrument details (if applicable)
    tradingsymbol VARCHAR(100),
    exchange VARCHAR(20),
    instrument_type VARCHAR(20),  -- EQ, FUT, CE, PE
    segment VARCHAR(20),  -- equity, fno, currency, commodity

    -- Financial details
    quantity INTEGER,
    price DECIMAL(15, 4),
    debit DECIMAL(15, 2) DEFAULT 0,
    credit DECIMAL(15, 2) DEFAULT 0,
    balance DECIMAL(15, 2),

    -- Categorization
    category VARCHAR(50),  -- equity_intraday, fno_premium, delivery_acquisition, etc.
    subcategory VARCHAR(50),
    is_margin_blocked BOOLEAN DEFAULT FALSE,

    -- Original data
    raw_data JSONB,

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),

    PRIMARY KEY (id, transaction_date)
);

-- Convert to TimescaleDB hypertable for efficient time-series queries
SELECT create_hypertable(
    'statement_transactions',
    'transaction_date',
    if_not_exists => TRUE,
    migrate_data => TRUE
);

-- ============================================================================
-- 3. Funds Category Summary Table (Materialized View Alternative)
-- ============================================================================
CREATE TABLE IF NOT EXISTS funds_category_summary (
    id BIGSERIAL PRIMARY KEY,

    account_id VARCHAR(100) NOT NULL,
    upload_id BIGINT REFERENCES statement_uploads(id) ON DELETE CASCADE,

    -- Date range
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,

    -- Category-wise totals
    equity_intraday DECIMAL(15, 2) DEFAULT 0,
    equity_delivery_acquisition DECIMAL(15, 2) DEFAULT 0,
    equity_delivery_sale DECIMAL(15, 2) DEFAULT 0,
    fno_premium_paid DECIMAL(15, 2) DEFAULT 0,
    fno_premium_received DECIMAL(15, 2) DEFAULT 0,
    fno_futures_margin DECIMAL(15, 2) DEFAULT 0,
    fno_settlement DECIMAL(15, 2) DEFAULT 0,
    ipo_application DECIMAL(15, 2) DEFAULT 0,
    dividend_received DECIMAL(15, 2) DEFAULT 0,
    interest_charged DECIMAL(15, 2) DEFAULT 0,
    charges_taxes DECIMAL(15, 2) DEFAULT 0,
    funds_transfer_in DECIMAL(15, 2) DEFAULT 0,
    funds_transfer_out DECIMAL(15, 2) DEFAULT 0,
    other DECIMAL(15, 2) DEFAULT 0,

    -- Margin metrics
    total_margin_blocked DECIMAL(15, 2) DEFAULT 0,
    peak_margin_blocked DECIMAL(15, 2) DEFAULT 0,
    avg_daily_margin DECIMAL(15, 2) DEFAULT 0,

    -- Timestamps
    calculated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Unique constraint per account + date range
    UNIQUE(account_id, start_date, end_date)
);

-- ============================================================================
-- 4. Indexes for Performance
-- ============================================================================

-- Statement uploads indexes
CREATE INDEX IF NOT EXISTS idx_statement_uploads_account ON statement_uploads(account_id);
CREATE INDEX IF NOT EXISTS idx_statement_uploads_status ON statement_uploads(status);
CREATE INDEX IF NOT EXISTS idx_statement_uploads_dates ON statement_uploads(statement_start_date, statement_end_date);
CREATE INDEX IF NOT EXISTS idx_statement_uploads_uploaded_at ON statement_uploads(uploaded_at DESC);

-- Statement transactions indexes
CREATE INDEX IF NOT EXISTS idx_statement_txn_upload ON statement_transactions(upload_id);
CREATE INDEX IF NOT EXISTS idx_statement_txn_account ON statement_transactions(account_id);
CREATE INDEX IF NOT EXISTS idx_statement_txn_symbol ON statement_transactions(tradingsymbol) WHERE tradingsymbol IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_statement_txn_category ON statement_transactions(category);
CREATE INDEX IF NOT EXISTS idx_statement_txn_type ON statement_transactions(transaction_type);
CREATE INDEX IF NOT EXISTS idx_statement_txn_segment ON statement_transactions(segment);
CREATE INDEX IF NOT EXISTS idx_statement_txn_margin ON statement_transactions(is_margin_blocked) WHERE is_margin_blocked = TRUE;

-- Composite index for category analysis queries
CREATE INDEX IF NOT EXISTS idx_statement_txn_account_date_category
ON statement_transactions(account_id, transaction_date DESC, category);

-- GIN index for raw_data JSON queries
CREATE INDEX IF NOT EXISTS idx_statement_txn_raw_data_gin ON statement_transactions USING gin(raw_data);

-- Funds summary indexes
CREATE INDEX IF NOT EXISTS idx_funds_summary_account ON funds_category_summary(account_id);
CREATE INDEX IF NOT EXISTS idx_funds_summary_dates ON funds_category_summary(start_date, end_date);
CREATE INDEX IF NOT EXISTS idx_funds_summary_upload ON funds_category_summary(upload_id);

-- ============================================================================
-- 5. Table Comments
-- ============================================================================

COMMENT ON TABLE statement_uploads IS 'Tracks uploaded Zerodha statement files and parsing status';
COMMENT ON TABLE statement_transactions IS 'Individual transactions parsed from statements (TimescaleDB hypertable)';
COMMENT ON TABLE funds_category_summary IS 'Pre-calculated category-wise funds breakdown for fast querying';

COMMENT ON COLUMN statement_uploads.file_hash IS 'SHA256 hash for deduplication - prevent uploading same file twice';
COMMENT ON COLUMN statement_uploads.status IS 'Parsing status: pending, processing, completed, failed';

COMMENT ON COLUMN statement_transactions.category IS 'Primary categorization: equity_intraday, fno_premium, delivery_acquisition, etc.';
COMMENT ON COLUMN statement_transactions.is_margin_blocked IS 'TRUE if this transaction blocks margin (delivery buy, FNO premium, etc.)';

COMMENT ON COLUMN funds_category_summary.equity_intraday IS 'Total equity intraday turnover (blocked as margin)';
COMMENT ON COLUMN funds_category_summary.fno_premium_paid IS 'Total FNO premium paid (blocks margin)';
COMMENT ON COLUMN funds_category_summary.total_margin_blocked IS 'Total funds blocked as margin across all categories';

-- ============================================================================
-- 6. Helper Functions
-- ============================================================================

-- Function to calculate category summary for a date range
CREATE OR REPLACE FUNCTION calculate_funds_category_summary(
    p_account_id VARCHAR,
    p_start_date DATE,
    p_end_date DATE
)
RETURNS TABLE (
    category VARCHAR,
    total_debit DECIMAL,
    total_credit DECIMAL,
    net_amount DECIMAL,
    transaction_count BIGINT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        st.category,
        COALESCE(SUM(st.debit), 0) as total_debit,
        COALESCE(SUM(st.credit), 0) as total_credit,
        COALESCE(SUM(st.credit - st.debit), 0) as net_amount,
        COUNT(*) as transaction_count
    FROM statement_transactions st
    WHERE st.account_id = p_account_id
      AND st.transaction_date >= p_start_date::timestamptz
      AND st.transaction_date < (p_end_date::date + INTERVAL '1 day')::timestamptz
      AND st.category IS NOT NULL
    GROUP BY st.category
    ORDER BY net_amount DESC;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION calculate_funds_category_summary IS 'Calculate category-wise breakdown for a date range';
