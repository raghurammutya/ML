-- Migration 014: Alter instruments table and create corporate actions tables
-- Date: 2025-11-04
-- Purpose: Add corporate actions support to existing instruments table

-- =====================================================
-- 1. ALTER INSTRUMENTS TABLE - Add corporate action fields
-- =====================================================

-- Add new columns to existing instruments table
DO $$
BEGIN
    -- Add ISIN if it doesn't exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'instruments' AND column_name = 'isin') THEN
        ALTER TABLE instruments ADD COLUMN isin TEXT;
        CREATE UNIQUE INDEX idx_instruments_isin_unique ON instruments(isin) WHERE isin IS NOT NULL;
    END IF;

    -- Add NSE symbol if it doesn't exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'instruments' AND column_name = 'nse_symbol') THEN
        ALTER TABLE instruments ADD COLUMN nse_symbol TEXT;
        CREATE INDEX idx_instruments_nse_symbol ON instruments(nse_symbol);
    END IF;

    -- Add BSE code if it doesn't exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'instruments' AND column_name = 'bse_code') THEN
        ALTER TABLE instruments ADD COLUMN bse_code INTEGER;
        CREATE INDEX idx_instruments_bse_code ON instruments(bse_code);
    END IF;

    -- Add company_name if it doesn't exist (may use existing 'name' field)
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'instruments' AND column_name = 'company_name') THEN
        ALTER TABLE instruments ADD COLUMN company_name TEXT;
        -- Copy from name field if exists
        UPDATE instruments SET company_name = name WHERE company_name IS NULL AND name IS NOT NULL;
    END IF;

    -- Add industry if it doesn't exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'instruments' AND column_name = 'industry') THEN
        ALTER TABLE instruments ADD COLUMN industry TEXT;
    END IF;

    -- Add sector if it doesn't exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'instruments' AND column_name = 'sector') THEN
        ALTER TABLE instruments ADD COLUMN sector TEXT;
    END IF;
END $$;

COMMENT ON COLUMN instruments.isin IS 'International Securities Identification Number';
COMMENT ON COLUMN instruments.nse_symbol IS 'NSE trading symbol';
COMMENT ON COLUMN instruments.bse_code IS 'BSE scrip code';
COMMENT ON COLUMN instruments.company_name IS 'Full company name';
COMMENT ON COLUMN instruments.industry IS 'Industry classification';
COMMENT ON COLUMN instruments.sector IS 'Sector classification';

-- =====================================================
-- 2. CREATE CORPORATE ACTIONS TABLE
-- =====================================================

CREATE TABLE IF NOT EXISTS corporate_actions (
    id SERIAL PRIMARY KEY,

    -- Link to instrument
    instrument_id BIGINT REFERENCES instruments(id) ON DELETE CASCADE,

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
    price_adjustment_factor DECIMAL(10, 6), -- For splits/bonus

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

-- Create unique constraint on source_id to prevent duplicates
CREATE UNIQUE INDEX IF NOT EXISTS idx_corporate_actions_source_unique
ON corporate_actions(source_id) WHERE source_id IS NOT NULL;

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_corporate_actions_instrument ON corporate_actions(instrument_id);
CREATE INDEX IF NOT EXISTS idx_corporate_actions_type ON corporate_actions(action_type);
CREATE INDEX IF NOT EXISTS idx_corporate_actions_ex_date ON corporate_actions(ex_date);
CREATE INDEX IF NOT EXISTS idx_corporate_actions_record_date ON corporate_actions(record_date);
CREATE INDEX IF NOT EXISTS idx_corporate_actions_payment_date ON corporate_actions(payment_date);
CREATE INDEX IF NOT EXISTS idx_corporate_actions_source ON corporate_actions(source);
CREATE INDEX IF NOT EXISTS idx_corporate_actions_status ON corporate_actions(status);

-- Composite indexes for common queries
CREATE INDEX IF NOT EXISTS idx_corporate_actions_instrument_ex_date ON corporate_actions(instrument_id, ex_date);
CREATE INDEX IF NOT EXISTS idx_corporate_actions_type_ex_date ON corporate_actions(action_type, ex_date);
CREATE INDEX IF NOT EXISTS idx_corporate_actions_instrument_status ON corporate_actions(instrument_id, status);

-- =====================================================
-- 3. CORPORATE ACTIONS CACHE TABLE
-- =====================================================

CREATE TABLE IF NOT EXISTS corporate_actions_cache (
    id SERIAL PRIMARY KEY,
    cache_key TEXT UNIQUE NOT NULL,
    data JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    hit_count INTEGER DEFAULT 0,
    CONSTRAINT valid_expiry CHECK (expires_at > created_at)
);

CREATE INDEX IF NOT EXISTS idx_corporate_actions_cache_key ON corporate_actions_cache(cache_key);
CREATE INDEX IF NOT EXISTS idx_corporate_actions_cache_expiry ON corporate_actions_cache(expires_at);

-- =====================================================
-- 4. HELPER FUNCTIONS
-- =====================================================

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
            v_old_fv := (p_action_data->>'old_fv')::DECIMAL;
            v_new_fv := (p_action_data->>'new_fv')::DECIMAL;
            IF v_old_fv > 0 AND v_new_fv > 0 THEN
                RETURN v_old_fv / v_new_fv;
            END IF;

        WHEN 'BONUS' THEN
            v_old_shares := (p_action_data->>'old_shares')::INTEGER;
            v_new_shares := (p_action_data->>'new_shares')::INTEGER;
            IF v_old_shares > 0 THEN
                RETURN (v_old_shares + v_new_shares)::DECIMAL / v_old_shares;
            END IF;

        ELSE
            RETURN 1.0;
    END CASE;

    RETURN 1.0;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- Trigger for auto-calculating price adjustment
CREATE OR REPLACE FUNCTION auto_calculate_price_adjustment()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.price_adjustment_factor IS NULL THEN
        NEW.price_adjustment_factor := calculate_price_adjustment(
            NEW.action_type,
            NEW.action_data
        );
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS corporate_actions_auto_adjustment ON corporate_actions;
CREATE TRIGGER corporate_actions_auto_adjustment
    BEFORE INSERT OR UPDATE ON corporate_actions
    FOR EACH ROW
    WHEN (NEW.action_type IN ('SPLIT', 'BONUS'))
    EXECUTE FUNCTION auto_calculate_price_adjustment();

-- Trigger for updating updated_at
DROP TRIGGER IF EXISTS corporate_actions_updated_at ON corporate_actions;
CREATE TRIGGER corporate_actions_updated_at
    BEFORE UPDATE ON corporate_actions
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();

-- Function to cleanup expired cache
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

-- =====================================================
-- 5. COMMENTS
-- =====================================================

COMMENT ON TABLE corporate_actions IS 'Corporate actions (dividends, bonus, splits, etc.) for instruments';
COMMENT ON TABLE corporate_actions_cache IS 'Cache for frequently accessed corporate actions queries';
COMMENT ON FUNCTION calculate_price_adjustment IS 'Calculate price adjustment factor for splits and bonus issues';
COMMENT ON FUNCTION cleanup_expired_cache IS 'Delete expired cache entries, returns number of deleted rows';

-- =====================================================
-- 6. SAMPLE DATA
-- =====================================================

-- Update existing instruments with ISIN/NSE/BSE codes (if not already set)
-- This is optional - you can populate this data via the fetcher service

DO $$
BEGIN
    -- Only add sample data if instruments table has less than 5 rows with ISIN
    IF (SELECT COUNT(*) FROM instruments WHERE isin IS NOT NULL) < 5 THEN
        -- TCS
        INSERT INTO instruments (instrument_key, symbol, exchange, asset_type, name, company_name, isin, nse_symbol, bse_code, is_active)
        VALUES ('NSE:TCS', 'TCS', 'NSE', 'EQ', 'Tata Consultancy Services Ltd', 'Tata Consultancy Services Ltd', 'INE467B01029', 'TCS', 532540, true)
        ON CONFLICT (instrument_key) DO UPDATE SET
            isin = EXCLUDED.isin,
            nse_symbol = EXCLUDED.nse_symbol,
            bse_code = EXCLUDED.bse_code,
            company_name = EXCLUDED.company_name;

        -- RELIANCE
        INSERT INTO instruments (instrument_key, symbol, exchange, asset_type, name, company_name, isin, nse_symbol, bse_code, is_active)
        VALUES ('NSE:RELIANCE', 'RELIANCE', 'NSE', 'EQ', 'Reliance Industries Ltd', 'Reliance Industries Ltd', 'INE002A01018', 'RELIANCE', 500325, true)
        ON CONFLICT (instrument_key) DO UPDATE SET
            isin = EXCLUDED.isin,
            nse_symbol = EXCLUDED.nse_symbol,
            bse_code = EXCLUDED.bse_code,
            company_name = EXCLUDED.company_name;

        -- INFY
        INSERT INTO instruments (instrument_key, symbol, exchange, asset_type, name, company_name, isin, nse_symbol, bse_code, is_active)
        VALUES ('NSE:INFY', 'INFY', 'NSE', 'EQ', 'Infosys Ltd', 'Infosys Ltd', 'INE009A01021', 'INFY', 500209, true)
        ON CONFLICT (instrument_key) DO UPDATE SET
            isin = EXCLUDED.isin,
            nse_symbol = EXCLUDED.nse_symbol,
            bse_code = EXCLUDED.bse_code,
            company_name = EXCLUDED.company_name;
    END IF;
END $$;

-- =====================================================
-- END OF MIGRATION
-- =====================================================
