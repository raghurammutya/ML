-- =====================================================
-- Migration 019: Normalize NIFTY symbol variations
-- =====================================================
-- Purpose: Fix "NIFTY50" vs "NIFTY 50" vs "NIFTY" confusion
-- Canonical: "NIFTY" (simple, clean, matches FO instrument name)
-- =====================================================

BEGIN;

-- =====================================================
-- STEP 1: Create normalization function
-- =====================================================
CREATE OR REPLACE FUNCTION normalize_symbol(input_symbol TEXT)
RETURNS TEXT AS $$
DECLARE
    canonical TEXT;
BEGIN
    -- Trim and uppercase
    canonical := UPPER(TRIM(input_symbol));

    -- Remove exchange prefixes
    canonical := REGEXP_REPLACE(canonical, '^NSE:', '');
    canonical := REGEXP_REPLACE(canonical, '^BSE:', '');
    canonical := REGEXP_REPLACE(canonical, '^MCX:', '');

    -- Normalize NIFTY variations
    IF canonical IN ('NIFTY50', 'NIFTY 50', 'NIFTY-50') THEN
        RETURN 'NIFTY';
    END IF;

    -- Normalize BANKNIFTY variations
    IF canonical IN ('BANK NIFTY', 'NIFTY BANK', 'BANKNIFTY') THEN
        RETURN 'BANKNIFTY';
    END IF;

    -- Normalize FINNIFTY variations
    IF canonical IN ('FINNIFTY', 'NIFTY FIN SERVICE', 'NIFTYFIN', 'FIN NIFTY') THEN
        RETURN 'FINNIFTY';
    END IF;

    -- Normalize MIDCPNIFTY variations
    IF canonical IN ('MIDCPNIFTY', 'NIFTY MIDCAP SELECT', 'MIDCAP NIFTY') THEN
        RETURN 'MIDCPNIFTY';
    END IF;

    -- Return as-is if no rule matches
    RETURN canonical;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- =====================================================
-- STEP 2: Migrate existing data
-- =====================================================

-- Show current state before migration
DO $$
BEGIN
    RAISE NOTICE '=== BEFORE MIGRATION ===';
END $$;

SELECT 'fo_option_strike_bars' as table_name, symbol, COUNT(*) as rows
FROM fo_option_strike_bars
WHERE symbol IN ('NIFTY', 'NIFTY50', 'NIFTY 50')
GROUP BY symbol
UNION ALL
SELECT 'minute_bars', symbol, COUNT(*)
FROM minute_bars
WHERE symbol IN ('NIFTY', 'NIFTY50', 'NIFTY 50')
GROUP BY symbol
UNION ALL
SELECT 'fo_expiry_metrics', symbol, COUNT(*)
FROM fo_expiry_metrics
WHERE symbol IN ('NIFTY', 'NIFTY50', 'NIFTY 50')
GROUP BY symbol;

-- Backup counts
DO $$
DECLARE
    fo_before INTEGER;
    minute_before INTEGER;
    expiry_before INTEGER;
BEGIN
    SELECT COUNT(*) INTO fo_before FROM fo_option_strike_bars;
    SELECT COUNT(*) INTO minute_before FROM minute_bars;
    SELECT COUNT(*) INTO expiry_before FROM fo_expiry_metrics;

    RAISE NOTICE 'Total rows before: fo_option_strike_bars=%, minute_bars=%, fo_expiry_metrics=%',
        fo_before, minute_before, expiry_before;
END $$;

-- Update fo_option_strike_bars
UPDATE fo_option_strike_bars
SET symbol = normalize_symbol(symbol)
WHERE symbol IN ('NIFTY50', 'NIFTY 50', 'NIFTY-50')
   OR symbol IN ('BANK NIFTY', 'NIFTY BANK')
   OR symbol IN ('FINNIFTY', 'NIFTY FIN SERVICE')
   OR symbol IN ('MIDCPNIFTY', 'NIFTY MIDCAP SELECT');

-- Update minute_bars
UPDATE minute_bars
SET symbol = normalize_symbol(symbol)
WHERE symbol IN ('NIFTY50', 'NIFTY 50', 'NIFTY-50')
   OR symbol IN ('BANK NIFTY', 'NIFTY BANK')
   OR symbol IN ('FINNIFTY', 'NIFTY FIN SERVICE')
   OR symbol IN ('MIDCPNIFTY', 'NIFTY MIDCAP SELECT');

-- Update fo_expiry_metrics
UPDATE fo_expiry_metrics
SET symbol = normalize_symbol(symbol)
WHERE symbol IN ('NIFTY50', 'NIFTY 50', 'NIFTY-50')
   OR symbol IN ('BANK NIFTY', 'NIFTY BANK')
   OR symbol IN ('FINNIFTY', 'NIFTY FIN SERVICE')
   OR symbol IN ('MIDCPNIFTY', 'NIFTY MIDCAP SELECT');

-- Show state after migration
DO $$
BEGIN
    RAISE NOTICE '=== AFTER MIGRATION ===';
END $$;

SELECT 'fo_option_strike_bars' as table_name, symbol, COUNT(*) as rows
FROM fo_option_strike_bars
WHERE symbol IN ('NIFTY', 'NIFTY50', 'NIFTY 50')
GROUP BY symbol
UNION ALL
SELECT 'minute_bars', symbol, COUNT(*)
FROM minute_bars
WHERE symbol IN ('NIFTY', 'NIFTY50', 'NIFTY 50')
GROUP BY symbol
UNION ALL
SELECT 'fo_expiry_metrics', symbol, COUNT(*)
FROM fo_expiry_metrics
WHERE symbol IN ('NIFTY', 'NIFTY50', 'NIFTY 50')
GROUP BY symbol;

-- Verify no data loss
DO $$
DECLARE
    fo_after INTEGER;
    minute_after INTEGER;
    expiry_after INTEGER;
BEGIN
    SELECT COUNT(*) INTO fo_after FROM fo_option_strike_bars;
    SELECT COUNT(*) INTO minute_after FROM minute_bars;
    SELECT COUNT(*) INTO expiry_after FROM fo_expiry_metrics;

    RAISE NOTICE 'Total rows after: fo_option_strike_bars=%, minute_bars=%, fo_expiry_metrics=%',
        fo_after, minute_after, expiry_after;
END $$;

-- =====================================================
-- STEP 3: Add auto-normalization triggers
-- =====================================================

-- Create trigger function
CREATE OR REPLACE FUNCTION auto_normalize_symbol()
RETURNS TRIGGER AS $$
BEGIN
    NEW.symbol := normalize_symbol(NEW.symbol);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply to fo_option_strike_bars
DROP TRIGGER IF EXISTS normalize_symbol_on_insert ON fo_option_strike_bars;
CREATE TRIGGER normalize_symbol_on_insert
    BEFORE INSERT OR UPDATE OF symbol ON fo_option_strike_bars
    FOR EACH ROW
    EXECUTE FUNCTION auto_normalize_symbol();

-- Apply to minute_bars
DROP TRIGGER IF EXISTS normalize_symbol_on_insert ON minute_bars;
CREATE TRIGGER normalize_symbol_on_insert
    BEFORE INSERT OR UPDATE OF symbol ON minute_bars
    FOR EACH ROW
    EXECUTE FUNCTION auto_normalize_symbol();

-- Apply to fo_expiry_metrics
DROP TRIGGER IF EXISTS normalize_symbol_on_insert ON fo_expiry_metrics;
CREATE TRIGGER normalize_symbol_on_insert
    BEFORE INSERT OR UPDATE OF symbol ON fo_expiry_metrics
    FOR EACH ROW
    EXECUTE FUNCTION auto_normalize_symbol();

-- =====================================================
-- STEP 4: Verify and log results
-- =====================================================

DO $$
BEGIN
    RAISE NOTICE '=== MIGRATION COMPLETE ===';
    RAISE NOTICE 'Canonical symbols: NIFTY, BANKNIFTY, FINNIFTY, MIDCPNIFTY';
    RAISE NOTICE 'Auto-normalization triggers installed on: fo_option_strike_bars, minute_bars, fo_expiry_metrics';
    RAISE NOTICE 'Future inserts will automatically normalize to canonical symbols';
END $$;

COMMIT;
