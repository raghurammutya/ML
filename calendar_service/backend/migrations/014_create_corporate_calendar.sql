-- Migration 014: Create Corporate Calendar (Instruments & Corporate Actions)
-- Date: 2025-11-04
-- Purpose: Add corporate actions tracking for BSE/NSE instruments

-- =====================================================
-- 1. INSTRUMENTS TABLE (Symbol Resolution)
-- =====================================================

CREATE TABLE instruments (
    id SERIAL PRIMARY KEY,

    -- Symbol identification
    symbol TEXT NOT NULL,              -- Trading symbol (e.g., 'TCS', 'RELIANCE')
    isin TEXT,                         -- International Securities ID (optional, but unique if provided)

    -- Exchange-specific codes
    nse_symbol TEXT,                   -- NSE trading symbol
    bse_code INTEGER,                  -- BSE scrip code

    -- Company info
    company_name TEXT NOT NULL,
    industry TEXT,
    sector TEXT,

    -- Metadata
    exchange TEXT NOT NULL,            -- 'NSE', 'BSE', 'BOTH'
    instrument_type TEXT DEFAULT 'EQ', -- 'EQ', 'FO', 'DEBT', 'CURRENCY', 'COMMODITY'
    is_active BOOLEAN DEFAULT true,

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Constraints
    UNIQUE(symbol, exchange),
    CONSTRAINT valid_exchange CHECK (exchange IN ('NSE', 'BSE', 'BOTH', 'MCX', 'NCDEX')),
    CONSTRAINT valid_instrument_type CHECK (instrument_type IN ('EQ', 'FO', 'DEBT', 'CURRENCY', 'COMMODITY'))
);

-- Unique constraint on ISIN only if it's not null
CREATE UNIQUE INDEX idx_instruments_isin_unique ON instruments(isin) WHERE isin IS NOT NULL;

-- Indexes for performance
CREATE INDEX idx_instruments_symbol ON instruments(symbol);
CREATE INDEX idx_instruments_nse_symbol ON instruments(nse_symbol);
CREATE INDEX idx_instruments_bse_code ON instruments(bse_code);
CREATE INDEX idx_instruments_company_name ON instruments(company_name);
CREATE INDEX idx_instruments_exchange ON instruments(exchange);

-- =====================================================
-- 2. CORPORATE ACTIONS TABLE
-- =====================================================

CREATE TABLE corporate_actions (
    id SERIAL PRIMARY KEY,

    -- Link to instrument
    instrument_id INTEGER REFERENCES instruments(id) ON DELETE CASCADE,

    -- Action identification
    action_type TEXT NOT NULL,         -- 'DIVIDEND', 'BONUS', 'SPLIT', etc.
    action_category TEXT DEFAULT 'corporate_action',

    -- Key dates
    ex_date DATE,                      -- Ex-date (most important for trading)
    record_date DATE,                  -- Record date
    announcement_date DATE,            -- When announced
    effective_date DATE,               -- When effective (for mergers, etc.)
    payment_date DATE,                 -- Payment date (for dividends)

    -- Date ranges (for book closure, buyback)
    start_date DATE,
    end_date DATE,

    -- Action-specific data (stored as JSONB for flexibility)
    action_data JSONB DEFAULT '{}',
    -- Examples:
    -- Dividend: {"amount": 10.50, "currency": "INR", "type": "interim|final|special"}
    -- Bonus: {"ratio": "1:2", "old_shares": 1, "new_shares": 2}
    -- Split: {"old_fv": 10, "new_fv": 2, "ratio": "1:5"}
    -- Rights: {"ratio": "1:3", "price": 150.00, "subscription_start": "2025-01-01", "subscription_end": "2025-01-15"}

    -- Display info
    title TEXT NOT NULL,               -- "Dividend - Rs 10.50 per share"
    description TEXT,
    purpose TEXT,                      -- Purpose of book closure, etc.

    -- Source tracking
    source TEXT NOT NULL,              -- 'BSE', 'NSE', 'NSE,BSE', 'manual', 'API'
    source_url TEXT,
    source_id TEXT,                    -- Original ID from source
    verified BOOLEAN DEFAULT false,

    -- Impact
    price_adjustment_factor DECIMAL(10, 6), -- For splits/bonus (e.g., 0.5 for 1:2 split)

    -- Status
    status TEXT DEFAULT 'announced',   -- 'announced', 'upcoming', 'completed', 'cancelled'

    -- Metadata
    notes TEXT,
    metadata JSONB DEFAULT '{}',

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Constraints
    CONSTRAINT valid_action_type CHECK (action_type IN (
        'DIVIDEND', 'BONUS', 'SPLIT', 'RIGHTS', 'AGM', 'EGM',
        'BOOK_CLOSURE', 'BUYBACK', 'MERGER', 'DEMERGER'
    )),
    CONSTRAINT valid_status CHECK (status IN ('announced', 'upcoming', 'completed', 'cancelled')),
    CONSTRAINT date_range_valid CHECK (start_date IS NULL OR end_date IS NULL OR start_date <= end_date),
    CONSTRAINT ex_record_date_valid CHECK (ex_date IS NULL OR record_date IS NULL OR ex_date <= record_date)
);

-- Indexes for performance
CREATE INDEX idx_corporate_actions_instrument ON corporate_actions(instrument_id);
CREATE INDEX idx_corporate_actions_type ON corporate_actions(action_type);
CREATE INDEX idx_corporate_actions_ex_date ON corporate_actions(ex_date);
CREATE INDEX idx_corporate_actions_record_date ON corporate_actions(record_date);
CREATE INDEX idx_corporate_actions_payment_date ON corporate_actions(payment_date);
CREATE INDEX idx_corporate_actions_source ON corporate_actions(source);
CREATE INDEX idx_corporate_actions_status ON corporate_actions(status);

-- Composite indexes for common queries
CREATE INDEX idx_corporate_actions_instrument_ex_date ON corporate_actions(instrument_id, ex_date);
CREATE INDEX idx_corporate_actions_type_ex_date ON corporate_actions(action_type, ex_date);
CREATE INDEX idx_corporate_actions_instrument_status ON corporate_actions(instrument_id, status);

-- =====================================================
-- 3. CORPORATE ACTIONS CACHE TABLE
-- =====================================================

CREATE TABLE corporate_actions_cache (
    id SERIAL PRIMARY KEY,

    -- Cache key
    cache_key TEXT UNIQUE NOT NULL,    -- e.g., "symbol:TCS:type:DIVIDEND:from:2025-01-01:to:2025-12-31"

    -- Cached data
    data JSONB NOT NULL,

    -- Cache metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    hit_count INTEGER DEFAULT 0,

    -- Constraints
    CONSTRAINT valid_expiry CHECK (expires_at > created_at)
);

CREATE INDEX idx_corporate_actions_cache_key ON corporate_actions_cache(cache_key);
CREATE INDEX idx_corporate_actions_cache_expiry ON corporate_actions_cache(expires_at);

-- =====================================================
-- 4. HELPER FUNCTIONS
-- =====================================================

-- Function to get upcoming corporate actions for a symbol
CREATE OR REPLACE FUNCTION get_upcoming_corporate_actions(
    p_symbol TEXT,
    p_days_ahead INTEGER DEFAULT 30,
    p_action_type TEXT DEFAULT NULL
)
RETURNS TABLE (
    id INTEGER,
    symbol TEXT,
    company_name TEXT,
    action_type TEXT,
    title TEXT,
    ex_date DATE,
    record_date DATE,
    payment_date DATE,
    action_data JSONB,
    days_until INTEGER
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        ca.id,
        i.symbol,
        i.company_name,
        ca.action_type,
        ca.title,
        ca.ex_date,
        ca.record_date,
        ca.payment_date,
        ca.action_data,
        (ca.ex_date - CURRENT_DATE)::INTEGER AS days_until
    FROM corporate_actions ca
    JOIN instruments i ON ca.instrument_id = i.id
    WHERE i.symbol = p_symbol
    AND ca.ex_date >= CURRENT_DATE
    AND ca.ex_date <= CURRENT_DATE + p_days_ahead
    AND ca.status IN ('announced', 'upcoming')
    AND (p_action_type IS NULL OR ca.action_type = p_action_type)
    ORDER BY ca.ex_date ASC;
END;
$$ LANGUAGE plpgsql;

-- Function to get all corporate actions on a specific date
CREATE OR REPLACE FUNCTION get_corporate_actions_by_date(
    p_date DATE,
    p_action_type TEXT DEFAULT NULL
)
RETURNS TABLE (
    id INTEGER,
    symbol TEXT,
    company_name TEXT,
    action_type TEXT,
    title TEXT,
    ex_date DATE,
    record_date DATE,
    action_data JSONB
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        ca.id,
        i.symbol,
        i.company_name,
        ca.action_type,
        ca.title,
        ca.ex_date,
        ca.record_date,
        ca.action_data
    FROM corporate_actions ca
    JOIN instruments i ON ca.instrument_id = i.id
    WHERE ca.ex_date = p_date
    AND ca.status IN ('announced', 'upcoming', 'completed')
    AND (p_action_type IS NULL OR ca.action_type = p_action_type)
    ORDER BY i.symbol ASC;
END;
$$ LANGUAGE plpgsql;

-- Function to resolve instrument by symbol (handles BSE/NSE differences)
CREATE OR REPLACE FUNCTION resolve_instrument(
    p_symbol TEXT,
    p_exchange TEXT DEFAULT 'NSE'
)
RETURNS TABLE (
    instrument_id INTEGER,
    symbol TEXT,
    company_name TEXT,
    isin TEXT,
    nse_symbol TEXT,
    bse_code INTEGER
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        i.id,
        i.symbol,
        i.company_name,
        i.isin,
        i.nse_symbol,
        i.bse_code
    FROM instruments i
    WHERE
        (p_exchange = 'NSE' AND i.nse_symbol = p_symbol) OR
        (p_exchange = 'BSE' AND i.bse_code = p_symbol::INTEGER) OR
        (p_exchange = 'BOTH' AND (i.symbol = p_symbol OR i.nse_symbol = p_symbol)) OR
        i.symbol = p_symbol
    AND i.is_active = true
    LIMIT 1;
END;
$$ LANGUAGE plpgsql;

-- Function to calculate price adjustment factor for splits/bonus
CREATE OR REPLACE FUNCTION calculate_price_adjustment(
    p_action_type TEXT,
    p_action_data JSONB
)
RETURNS DECIMAL(10, 6) AS $$
DECLARE
    v_old_shares INTEGER;
    v_new_shares INTEGER;
    v_old_fv DECIMAL;
    v_new_fv DECIMAL;
BEGIN
    CASE p_action_type
        WHEN 'SPLIT' THEN
            -- For split, adjustment = old_fv / new_fv
            v_old_fv := (p_action_data->>'old_fv')::DECIMAL;
            v_new_fv := (p_action_data->>'new_fv')::DECIMAL;
            IF v_old_fv > 0 AND v_new_fv > 0 THEN
                RETURN v_old_fv / v_new_fv;
            END IF;

        WHEN 'BONUS' THEN
            -- For bonus 1:2, you get 2 new shares for 1 old share
            -- Adjustment = (old_shares + new_shares) / old_shares
            v_old_shares := (p_action_data->>'old_shares')::INTEGER;
            v_new_shares := (p_action_data->>'new_shares')::INTEGER;
            IF v_old_shares > 0 THEN
                RETURN (v_old_shares + v_new_shares)::DECIMAL / v_old_shares;
            END IF;

        ELSE
            RETURN 1.0; -- No adjustment
    END CASE;

    RETURN 1.0; -- Default no adjustment
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- =====================================================
-- 5. TRIGGER FOR AUTO-UPDATING TIMESTAMPS
-- =====================================================

CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER instruments_updated_at
    BEFORE UPDATE ON instruments
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER corporate_actions_updated_at
    BEFORE UPDATE ON corporate_actions
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();

-- =====================================================
-- 6. TRIGGER FOR AUTO-CALCULATING PRICE ADJUSTMENT
-- =====================================================

CREATE OR REPLACE FUNCTION auto_calculate_price_adjustment()
RETURNS TRIGGER AS $$
BEGIN
    -- Only calculate if not already set
    IF NEW.price_adjustment_factor IS NULL THEN
        NEW.price_adjustment_factor := calculate_price_adjustment(
            NEW.action_type,
            NEW.action_data
        );
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER corporate_actions_auto_adjustment
    BEFORE INSERT OR UPDATE ON corporate_actions
    FOR EACH ROW
    WHEN (NEW.action_type IN ('SPLIT', 'BONUS'))
    EXECUTE FUNCTION auto_calculate_price_adjustment();

-- =====================================================
-- 7. COMMENTS
-- =====================================================

COMMENT ON TABLE instruments IS 'Stores instrument/symbol information for NSE, BSE, and other exchanges with deduplication support';
COMMENT ON TABLE corporate_actions IS 'Stores corporate actions (dividends, bonus, splits, etc.) for instruments';
COMMENT ON TABLE corporate_actions_cache IS 'Cache for frequently accessed corporate actions queries';

COMMENT ON FUNCTION get_upcoming_corporate_actions IS 'Get upcoming corporate actions for a symbol within specified days';
COMMENT ON FUNCTION get_corporate_actions_by_date IS 'Get all corporate actions on a specific date';
COMMENT ON FUNCTION resolve_instrument IS 'Resolve instrument by symbol and exchange, handling BSE/NSE differences';
COMMENT ON FUNCTION calculate_price_adjustment IS 'Calculate price adjustment factor for splits and bonus issues';

-- =====================================================
-- 8. SAMPLE DATA (for testing)
-- =====================================================

-- Note: This will be populated by the data fetcher service
-- For now, we can add a few examples for testing

INSERT INTO instruments (symbol, isin, nse_symbol, bse_code, company_name, industry, sector, exchange, instrument_type) VALUES
('TCS', 'INE467B01029', 'TCS', 532540, 'Tata Consultancy Services Ltd', 'IT Services', 'Information Technology', 'BOTH', 'EQ'),
('RELIANCE', 'INE002A01018', 'RELIANCE', 500325, 'Reliance Industries Ltd', 'Refining', 'Energy', 'BOTH', 'EQ'),
('INFY', 'INE009A01021', 'INFY', 500209, 'Infosys Ltd', 'IT Services', 'Information Technology', 'BOTH', 'EQ'),
('HDFCBANK', 'INE040A01034', 'HDFCBANK', 500180, 'HDFC Bank Ltd', 'Banking', 'Financial Services', 'BOTH', 'EQ'),
('ICICIBANK', 'INE090A01021', 'ICICIBANK', 532174, 'ICICI Bank Ltd', 'Banking', 'Financial Services', 'BOTH', 'EQ')
ON CONFLICT (symbol, exchange) DO NOTHING;

-- Sample corporate actions (for testing)
INSERT INTO corporate_actions (
    instrument_id,
    action_type,
    title,
    ex_date,
    record_date,
    payment_date,
    action_data,
    source,
    status
) VALUES
(
    (SELECT id FROM instruments WHERE symbol = 'TCS' LIMIT 1),
    'DIVIDEND',
    'Interim Dividend - Rs 10.50 per share',
    '2025-06-15',
    '2025-06-16',
    '2025-07-05',
    '{"amount": 10.50, "currency": "INR", "type": "interim"}'::JSONB,
    'NSE',
    'announced'
),
(
    (SELECT id FROM instruments WHERE symbol = 'INFY' LIMIT 1),
    'BONUS',
    'Bonus Issue - 1:1',
    '2025-07-01',
    '2025-07-02',
    NULL,
    '{"ratio": "1:1", "old_shares": 1, "new_shares": 1}'::JSONB,
    'NSE,BSE',
    'announced'
),
(
    (SELECT id FROM instruments WHERE symbol = 'RELIANCE' LIMIT 1),
    'AGM',
    'Annual General Meeting',
    NULL,
    NULL,
    NULL,
    '{"meeting_date": "2025-08-15", "meeting_time": "14:00", "venue": "Virtual"}'::JSONB,
    'BSE',
    'announced'
)
ON CONFLICT DO NOTHING;

-- =====================================================
-- 9. CLEANUP FUNCTION (for maintenance)
-- =====================================================

-- Function to clean up expired cache entries
CREATE OR REPLACE FUNCTION cleanup_expired_cache()
RETURNS INTEGER AS $$
DECLARE
    v_deleted INTEGER;
BEGIN
    DELETE FROM corporate_actions_cache
    WHERE expires_at < NOW();

    GET DIAGNOSTICS v_deleted = ROW_COUNT;
    RETURN v_deleted;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION cleanup_expired_cache IS 'Delete expired cache entries, returns number of deleted rows';

-- =====================================================
-- END OF MIGRATION
-- =====================================================
