-- Migration 018: Create FO Expiry Metadata
-- Date: 2025-11-05
-- Purpose: Support relative expiry labeling (NWeek+1, NMonth+0) for FO analytics streaming

-- =====================================================
-- 1. EXPIRY CLASSIFICATION FUNCTION
-- =====================================================

CREATE OR REPLACE FUNCTION classify_expiry(expiry_date DATE)
RETURNS TABLE(is_weekly BOOLEAN, is_monthly BOOLEAN, is_quarterly BOOLEAN)
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE
    next_week DATE;
    is_thursday BOOLEAN;
    is_last_thursday BOOLEAN;
BEGIN
    -- Check if Thursday (NSE F&O expiries are on Thursdays)
    -- EXTRACT(DOW FROM date): 0=Sunday, 1=Monday, ..., 4=Thursday
    is_thursday := EXTRACT(DOW FROM expiry_date) = 4;

    IF NOT is_thursday THEN
        -- Not a Thursday - not a valid expiry
        RETURN QUERY SELECT FALSE, FALSE, FALSE;
        RETURN;
    END IF;

    -- Check if this is the last Thursday of the month
    -- Strategy: Add 7 days and check if month changes
    next_week := expiry_date + INTERVAL '7 days';
    is_last_thursday := EXTRACT(MONTH FROM next_week) != EXTRACT(MONTH FROM expiry_date);

    IF is_last_thursday THEN
        -- This is a monthly expiry
        -- Check if it's also quarterly (Mar/Jun/Sep/Dec)
        IF EXTRACT(MONTH FROM expiry_date) IN (3, 6, 9, 12) THEN
            -- Quarterly expiry
            RETURN QUERY SELECT FALSE, TRUE, TRUE;
        ELSE
            -- Just monthly
            RETURN QUERY SELECT FALSE, TRUE, FALSE;
        END IF;
    ELSE
        -- This is a weekly expiry
        RETURN QUERY SELECT TRUE, FALSE, FALSE;
    END IF;
END;
$$;

COMMENT ON FUNCTION classify_expiry IS 'Classify F&O expiry date as weekly, monthly, or quarterly based on NSE rules';

-- =====================================================
-- 2. HELPER FUNCTION: Get NSE Holidays
-- =====================================================

CREATE OR REPLACE FUNCTION get_nse_holidays(
    year_param INTEGER
)
RETURNS TABLE(holiday_date DATE)
LANGUAGE SQL
STABLE
AS $$
    SELECT ce.event_date::DATE
    FROM calendar_events ce
    JOIN calendar_types ct ON ce.calendar_type_id = ct.id
    WHERE ct.code = 'NSE'
      AND ce.event_type = 'holiday'
      AND ce.is_trading_day = false
      AND EXTRACT(YEAR FROM ce.event_date) = year_param
    ORDER BY ce.event_date;
$$;

COMMENT ON FUNCTION get_nse_holidays IS 'Get all NSE market holidays for a given year from calendar_events';

-- =====================================================
-- 3. HELPER FUNCTION: Is Business Day
-- =====================================================

CREATE OR REPLACE FUNCTION is_business_day(
    check_date DATE,
    year_param INTEGER DEFAULT EXTRACT(YEAR FROM CURRENT_DATE)::INTEGER
)
RETURNS BOOLEAN
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    is_weekday BOOLEAN;
    is_holiday BOOLEAN;
BEGIN
    -- Check if weekday (Mon-Fri)
    -- DOW: 0=Sunday, 1=Monday, 2=Tuesday, 3=Wednesday, 4=Thursday, 5=Friday, 6=Saturday
    is_weekday := EXTRACT(DOW FROM check_date) BETWEEN 1 AND 5;

    IF NOT is_weekday THEN
        RETURN FALSE;
    END IF;

    -- Check if holiday
    SELECT EXISTS (
        SELECT 1
        FROM calendar_events ce
        JOIN calendar_types ct ON ce.calendar_type_id = ct.id
        WHERE ct.code = 'NSE'
          AND ce.event_date = check_date
          AND ce.event_type = 'holiday'
          AND ce.is_trading_day = false
    ) INTO is_holiday;

    RETURN NOT is_holiday;
END;
$$;

COMMENT ON FUNCTION is_business_day IS 'Check if a given date is an NSE trading day (Mon-Fri, not a holiday)';

-- =====================================================
-- 4. FO_EXPIRY_METADATA TABLE (for pre-computed labels)
-- =====================================================

-- This table stores pre-computed expiry labels for fast lookup
-- Updated nightly via scheduled job

CREATE TABLE IF NOT EXISTS fo_expiry_metadata (
    id SERIAL PRIMARY KEY,

    -- Identification
    symbol TEXT NOT NULL,
    expiry DATE NOT NULL,
    as_of_date DATE NOT NULL,  -- The date these labels are computed for

    -- Classification
    is_weekly BOOLEAN NOT NULL,
    is_monthly BOOLEAN NOT NULL,
    is_quarterly BOOLEAN NOT NULL,

    -- Relative labels
    relative_label TEXT NOT NULL,  -- e.g., "NWeek+1", "NMonth+0"
    relative_rank INTEGER NOT NULL,  -- 1, 2, 3... for weeklies; 0 for monthly

    -- Metadata
    days_to_expiry INTEGER,
    computed_at TIMESTAMPTZ DEFAULT NOW(),

    -- Unique constraint: one label per symbol-expiry-as_of_date combination
    CONSTRAINT unique_expiry_label UNIQUE (symbol, expiry, as_of_date)
);

-- Indexes for fast lookup
CREATE INDEX idx_fo_expiry_meta_symbol_date ON fo_expiry_metadata(symbol, as_of_date, expiry);
CREATE INDEX idx_fo_expiry_meta_expiry ON fo_expiry_metadata(expiry);
CREATE INDEX idx_fo_expiry_meta_as_of_date ON fo_expiry_metadata(as_of_date);

COMMENT ON TABLE fo_expiry_metadata IS 'Pre-computed expiry labels for FO analytics (updated nightly)';
COMMENT ON COLUMN fo_expiry_metadata.relative_label IS 'Human-readable label like NWeek+1, NMonth+0';
COMMENT ON COLUMN fo_expiry_metadata.relative_rank IS 'Numeric rank: 1+ for weeklies (nearest=1), 0 for monthly';
COMMENT ON COLUMN fo_expiry_metadata.as_of_date IS 'The reference date these labels were computed for (allows historical lookup)';

-- =====================================================
-- 5. FUNCTION: Compute Expiry Labels for a Symbol
-- =====================================================

CREATE OR REPLACE FUNCTION compute_expiry_labels(
    symbol_param TEXT,
    as_of_date_param DATE DEFAULT CURRENT_DATE
)
RETURNS TABLE(
    expiry DATE,
    is_weekly BOOLEAN,
    is_monthly BOOLEAN,
    is_quarterly BOOLEAN,
    relative_label TEXT,
    relative_rank INTEGER,
    days_to_expiry INTEGER
)
LANGUAGE plpgsql
AS $$
DECLARE
    expiry_rec RECORD;
    weekly_count INTEGER := 0;
    monthly_count INTEGER := 0;
    classification RECORD;
BEGIN
    -- Get all future expiries for this symbol
    FOR expiry_rec IN (
        SELECT DISTINCT e.expiry
        FROM fo_option_strike_bars e
        WHERE e.symbol = symbol_param
          AND e.expiry >= as_of_date_param
        ORDER BY e.expiry
    )
    LOOP
        -- Classify this expiry
        SELECT * INTO classification
        FROM classify_expiry(expiry_rec.expiry)
        LIMIT 1;

        -- Determine label and rank
        IF classification.is_weekly THEN
            weekly_count := weekly_count + 1;
            RETURN QUERY SELECT
                expiry_rec.expiry,
                classification.is_weekly,
                classification.is_monthly,
                classification.is_quarterly,
                'NWeek+' || weekly_count::TEXT,
                weekly_count,
                (expiry_rec.expiry - as_of_date_param)::INTEGER;

        ELSIF classification.is_monthly THEN
            RETURN QUERY SELECT
                expiry_rec.expiry,
                classification.is_weekly,
                classification.is_monthly,
                classification.is_quarterly,
                'NMonth+' || monthly_count::TEXT,
                0,  -- Monthly gets rank 0
                (expiry_rec.expiry - as_of_date_param)::INTEGER;

            monthly_count := monthly_count + 1;
        END IF;
        -- Note: Non-Thursday expiries are silently skipped
    END LOOP;
END;
$$;

COMMENT ON FUNCTION compute_expiry_labels IS 'Compute relative labels for all expiries of a symbol as of a specific date';

-- =====================================================
-- 6. FUNCTION: Refresh Expiry Metadata for All Symbols
-- =====================================================

CREATE OR REPLACE FUNCTION refresh_expiry_metadata(
    as_of_date_param DATE DEFAULT CURRENT_DATE
)
RETURNS INTEGER
LANGUAGE plpgsql
AS $$
DECLARE
    symbol_rec RECORD;
    inserted_count INTEGER := 0;
    label_rec RECORD;
BEGIN
    -- Get all distinct symbols from fo_option_strike_bars
    FOR symbol_rec IN (
        SELECT DISTINCT symbol
        FROM fo_option_strike_bars
    )
    LOOP
        -- Compute labels for this symbol
        FOR label_rec IN (
            SELECT *
            FROM compute_expiry_labels(symbol_rec.symbol, as_of_date_param)
        )
        LOOP
            -- Insert or update
            INSERT INTO fo_expiry_metadata (
                symbol,
                expiry,
                as_of_date,
                is_weekly,
                is_monthly,
                is_quarterly,
                relative_label,
                relative_rank,
                days_to_expiry
            ) VALUES (
                symbol_rec.symbol,
                label_rec.expiry,
                as_of_date_param,
                label_rec.is_weekly,
                label_rec.is_monthly,
                label_rec.is_quarterly,
                label_rec.relative_label,
                label_rec.relative_rank,
                label_rec.days_to_expiry
            )
            ON CONFLICT (symbol, expiry, as_of_date)
            DO UPDATE SET
                is_weekly = EXCLUDED.is_weekly,
                is_monthly = EXCLUDED.is_monthly,
                is_quarterly = EXCLUDED.is_quarterly,
                relative_label = EXCLUDED.relative_label,
                relative_rank = EXCLUDED.relative_rank,
                days_to_expiry = EXCLUDED.days_to_expiry,
                computed_at = NOW();

            inserted_count := inserted_count + 1;
        END LOOP;
    END LOOP;

    RETURN inserted_count;
END;
$$;

COMMENT ON FUNCTION refresh_expiry_metadata IS 'Refresh expiry metadata for all symbols (run nightly via cron)';

-- =====================================================
-- 7. INITIAL POPULATION
-- =====================================================

-- Populate labels for today
SELECT refresh_expiry_metadata(CURRENT_DATE);

-- Optional: Populate labels for past 7 days (for backfill support)
DO $$
DECLARE
    days_back INTEGER := 7;
    current_day DATE;
BEGIN
    FOR i IN 1..days_back LOOP
        current_day := CURRENT_DATE - INTERVAL '1 day' * i;
        PERFORM refresh_expiry_metadata(current_day);
    END LOOP;
END $$;

-- =====================================================
-- 8. SCHEDULED REFRESH (using pg_cron if available)
-- =====================================================

-- Note: pg_cron extension must be installed
-- CREATE EXTENSION IF NOT EXISTS pg_cron;

-- Schedule daily refresh at 6:00 AM IST (00:30 UTC)
-- Uncomment the following lines if pg_cron is available:

/*
SELECT cron.schedule(
    'refresh-expiry-labels-daily',
    '30 0 * * *',  -- 6:00 AM IST = 00:30 UTC
    $$SELECT refresh_expiry_metadata(CURRENT_DATE)$$
);
*/

-- Alternative: If pg_cron is not available, this can be called via:
-- - Python scheduler (APScheduler, Celery)
-- - System cron job calling: psql -c "SELECT refresh_expiry_metadata(CURRENT_DATE)"
-- - Application startup hook

COMMENT ON FUNCTION refresh_expiry_metadata IS 'Run daily at 6 AM IST to update expiry labels for current date';

-- =====================================================
-- 9. CLEANUP FUNCTION (optional)
-- =====================================================

CREATE OR REPLACE FUNCTION cleanup_old_expiry_metadata(
    days_to_keep INTEGER DEFAULT 90
)
RETURNS INTEGER
LANGUAGE plpgsql
AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    -- Delete metadata older than N days
    DELETE FROM fo_expiry_metadata
    WHERE as_of_date < CURRENT_DATE - INTERVAL '1 day' * days_to_keep;

    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$;

COMMENT ON FUNCTION cleanup_old_expiry_metadata IS 'Delete old expiry metadata to prevent table bloat (run weekly)';

-- =====================================================
-- 10. VERIFICATION QUERY
-- =====================================================

-- Verify the setup works
DO $$
DECLARE
    label_count INTEGER;
    symbol_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO label_count FROM fo_expiry_metadata WHERE as_of_date = CURRENT_DATE;
    SELECT COUNT(DISTINCT symbol) INTO symbol_count FROM fo_expiry_metadata WHERE as_of_date = CURRENT_DATE;

    RAISE NOTICE 'Expiry metadata initialized:';
    RAISE NOTICE '  - % labels computed', label_count;
    RAISE NOTICE '  - % symbols processed', symbol_count;
    RAISE NOTICE '  - For as_of_date: %', CURRENT_DATE;
END $$;
