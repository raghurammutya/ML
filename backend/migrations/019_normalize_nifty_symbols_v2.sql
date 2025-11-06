-- =====================================================
-- Migration 019: Normalize NIFTY symbol variations (V2 - Handle Duplicates)
-- =====================================================
-- Purpose: Fix "NIFTY50" vs "NIFTY 50" vs "NIFTY" confusion
-- Canonical: "NIFTY" (simple, clean, matches FO instrument name)
-- Strategy: Delete duplicates, keeping NIFTY50 data (more complete), then rename all to NIFTY
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

    -- Remove exchange prefixes (NSE:, BSE:, MCX:)
    canonical := REGEXP_REPLACE(canonical, '^(NSE|BSE|MCX):', '');

    -- Remove common suffixes used by different platforms
    -- .NS (NSE), .BO (BSE/Bombay), -EQ (equity), .NSE, .BSE
    canonical := REGEXP_REPLACE(canonical, '\.(NS|BO|NSE|BSE)$', '');
    canonical := REGEXP_REPLACE(canonical, '-EQ$', '');
    canonical := REGEXP_REPLACE(canonical, '-BE$', '');  -- B Group equity

    -- Remove index prefix (e.g., "^NSEI" -> "NSEI")
    IF LEFT(canonical, 1) = '^' THEN
        canonical := SUBSTRING(canonical FROM 2);
    END IF;

    -- Normalize NIFTY variations
    IF canonical IN ('NIFTY50', 'NIFTY 50', 'NIFTY-50', 'NSEI') THEN
        RETURN 'NIFTY';
    END IF;

    -- Normalize BANKNIFTY variations
    IF canonical IN ('BANK NIFTY', 'NIFTY BANK', 'BANKNIFTY', 'BANKNIFTY1!') THEN
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

    -- Normalize SENSEX variations
    IF canonical IN ('SENSEX', 'BSE SENSEX', 'BSESN') THEN
        RETURN 'SENSEX';
    END IF;

    -- Return as-is if no rule matches
    RETURN canonical;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- =====================================================
-- STEP 2: Show current state
-- =====================================================
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

-- =====================================================
-- STEP 3: Handle minute_bars duplicates
-- =====================================================
DO $$
DECLARE
    deleted_count INTEGER;
BEGIN
    RAISE NOTICE 'Removing duplicate minute_bars entries (keeping NIFTY50, deleting NIFTY 50)...';

    -- Delete "NIFTY 50" rows that have matching "NIFTY50" rows
    DELETE FROM minute_bars m1
    WHERE m1.symbol = 'NIFTY 50'
    AND EXISTS (
        SELECT 1 FROM minute_bars m2
        WHERE m2.symbol = 'NIFTY50'
        AND m2.resolution = m1.resolution
        AND m2.time = m1.time
    );

    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RAISE NOTICE 'Deleted % duplicate minute_bars rows', deleted_count;
END $$;

-- =====================================================
-- STEP 4: Handle fo_option_strike_bars duplicates
-- =====================================================
DO $$
DECLARE
    deleted_count INTEGER;
BEGIN
    RAISE NOTICE 'Removing duplicate fo_option_strike_bars entries (keeping NIFTY50, deleting NIFTY 50)...';

    -- Delete "NIFTY 50" rows that have matching "NIFTY50" rows
    DELETE FROM fo_option_strike_bars f1
    WHERE f1.symbol = 'NIFTY 50'
    AND EXISTS (
        SELECT 1 FROM fo_option_strike_bars f2
        WHERE f2.symbol = 'NIFTY50'
        AND f2.timeframe = f1.timeframe
        AND f2.expiry = f1.expiry
        AND f2.strike = f1.strike
        AND f2.bucket_time = f1.bucket_time
    );

    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RAISE NOTICE 'Deleted % duplicate fo_option_strike_bars rows', deleted_count;
END $$;

-- =====================================================
-- STEP 5: Handle fo_expiry_metrics duplicates
-- =====================================================
DO $$
DECLARE
    deleted_count INTEGER;
BEGIN
    RAISE NOTICE 'Removing duplicate fo_expiry_metrics entries (keeping NIFTY50, deleting NIFTY 50)...';

    -- Delete "NIFTY 50" rows that have matching "NIFTY50" rows
    DELETE FROM fo_expiry_metrics e1
    WHERE e1.symbol = 'NIFTY 50'
    AND EXISTS (
        SELECT 1 FROM fo_expiry_metrics e2
        WHERE e2.symbol = 'NIFTY50'
        AND e2.timeframe = e1.timeframe
        AND e2.expiry = e1.expiry
        AND e2.bucket_time = e1.bucket_time
    );

    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RAISE NOTICE 'Deleted % duplicate fo_expiry_metrics rows', deleted_count;
END $$;

-- =====================================================
-- STEP 6: Now safely rename to canonical symbol
-- =====================================================
DO $$
BEGIN
    RAISE NOTICE 'Renaming all variations to canonical symbols...';
END $$;

-- Update minute_bars
UPDATE minute_bars
SET symbol = 'NIFTY'
WHERE symbol IN ('NIFTY50', 'NIFTY 50');

-- Update fo_option_strike_bars
UPDATE fo_option_strike_bars
SET symbol = 'NIFTY'
WHERE symbol IN ('NIFTY50', 'NIFTY 50');

-- Update fo_expiry_metrics
UPDATE fo_expiry_metrics
SET symbol = 'NIFTY'
WHERE symbol IN ('NIFTY50', 'NIFTY 50');

-- Also normalize other indices
UPDATE minute_bars
SET symbol = normalize_symbol(symbol)
WHERE symbol IN ('BANK NIFTY', 'NIFTY BANK', 'FINNIFTY', 'NIFTY FIN SERVICE', 'MIDCPNIFTY', 'NIFTY MIDCAP SELECT');

UPDATE fo_option_strike_bars
SET symbol = normalize_symbol(symbol)
WHERE symbol IN ('BANK NIFTY', 'NIFTY BANK', 'FINNIFTY', 'NIFTY FIN SERVICE', 'MIDCPNIFTY', 'NIFTY MIDCAP SELECT');

UPDATE fo_expiry_metrics
SET symbol = normalize_symbol(symbol)
WHERE symbol IN ('BANK NIFTY', 'NIFTY BANK', 'FINNIFTY', 'NIFTY FIN SERVICE', 'MIDCPNIFTY', 'NIFTY MIDCAP SELECT');

-- =====================================================
-- STEP 7: Show state after migration
-- =====================================================
DO $$
BEGIN
    RAISE NOTICE '=== AFTER MIGRATION ===';
END $$;

SELECT 'fo_option_strike_bars' as table_name, symbol, COUNT(*) as rows
FROM fo_option_strike_bars
WHERE symbol IN ('NIFTY', 'NIFTY50', 'NIFTY 50', 'BANKNIFTY', 'FINNIFTY', 'MIDCPNIFTY')
GROUP BY symbol
UNION ALL
SELECT 'minute_bars', symbol, COUNT(*)
FROM minute_bars
WHERE symbol IN ('NIFTY', 'NIFTY50', 'NIFTY 50', 'BANKNIFTY', 'FINNIFTY', 'MIDCPNIFTY')
GROUP BY symbol
UNION ALL
SELECT 'fo_expiry_metrics', symbol, COUNT(*)
FROM fo_expiry_metrics
WHERE symbol IN ('NIFTY', 'NIFTY50', 'NIFTY 50', 'BANKNIFTY', 'FINNIFTY', 'MIDCPNIFTY')
GROUP BY symbol
ORDER BY table_name, symbol;

-- =====================================================
-- STEP 8: Add auto-normalization triggers
-- =====================================================
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
-- STEP 9: Final verification
-- =====================================================
DO $$
BEGIN
    RAISE NOTICE '=== MIGRATION COMPLETE ===';
    RAISE NOTICE 'Canonical symbols: NIFTY, BANKNIFTY, FINNIFTY, MIDCPNIFTY';
    RAISE NOTICE 'Auto-normalization triggers installed';
    RAISE NOTICE 'All future inserts will automatically use canonical symbols';
    RAISE NOTICE 'This supports multi-broker integration (Kite, Angel, Upstox, Fyers, etc.)';
END $$;

COMMIT;
