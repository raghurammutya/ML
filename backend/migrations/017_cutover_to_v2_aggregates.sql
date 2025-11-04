-- Migration 017: Atomic Cutover to V2 Aggregates
-- Date: 2025-11-02
-- Purpose: Switch from enriched views (with JOINs) to v2 aggregates (with OI columns)
--
-- PREREQUISITES:
-- 1. Migration 016 must be completed successfully
-- 2. fo_option_strike_bars_5min_v2 and fo_option_strike_bars_15min_v2 must exist
-- 3. New aggregates must be verified to have OI data
--
-- DEPLOYMENT STRATEGY:
-- This migration performs an atomic rename operation:
-- 1. Rename old aggregates to _old suffix (backup)
-- 2. Rename v2 aggregates to production names (instant cutover)
-- 3. Drop old enriched views (no longer needed)
--
-- ZERO DOWNTIME:
-- Application code using FO_STRIKE_TABLES mapping will automatically use new tables
-- No application restart required

BEGIN;

-- ============================================================================
-- STEP 1: Pre-flight Checks
-- ============================================================================

DO $$
DECLARE
    v5_exists BOOLEAN;
    v15_exists BOOLEAN;
    v5_has_oi BOOLEAN;
    v15_has_oi BOOLEAN;
    v5_row_count INTEGER;
    v15_row_count INTEGER;
BEGIN
    RAISE NOTICE '========================================';
    RAISE NOTICE 'PRE-FLIGHT CHECKS';
    RAISE NOTICE '========================================';

    -- Check that v2 aggregates exist
    SELECT EXISTS (
        SELECT 1 FROM pg_matviews WHERE matviewname = 'fo_option_strike_bars_5min_v2'
    ) INTO v5_exists;

    SELECT EXISTS (
        SELECT 1 FROM pg_matviews WHERE matviewname = 'fo_option_strike_bars_15min_v2'
    ) INTO v15_exists;

    IF NOT v5_exists THEN
        RAISE EXCEPTION 'fo_option_strike_bars_5min_v2 does not exist. Run migration 016 first.';
    END IF;

    IF NOT v15_exists THEN
        RAISE EXCEPTION 'fo_option_strike_bars_15min_v2 does not exist. Run migration 016 first.';
    END IF;

    RAISE NOTICE '✅ V2 aggregates exist';

    -- Check that v2 aggregates have OI data
    SELECT EXISTS (
        SELECT 1 FROM fo_option_strike_bars_5min_v2
        WHERE call_oi_sum IS NOT NULL OR put_oi_sum IS NOT NULL
        LIMIT 1
    ) INTO v5_has_oi;

    SELECT EXISTS (
        SELECT 1 FROM fo_option_strike_bars_15min_v2
        WHERE call_oi_sum IS NOT NULL OR put_oi_sum IS NOT NULL
        LIMIT 1
    ) INTO v15_has_oi;

    IF NOT v5_has_oi THEN
        RAISE EXCEPTION 'fo_option_strike_bars_5min_v2 has no OI data. Refresh and verify first.';
    END IF;

    IF NOT v15_has_oi THEN
        RAISE EXCEPTION 'fo_option_strike_bars_15min_v2 has no OI data. Refresh and verify first.';
    END IF;

    RAISE NOTICE '✅ V2 aggregates have OI data';

    -- Check row counts
    SELECT COUNT(*) INTO v5_row_count FROM fo_option_strike_bars_5min_v2;
    SELECT COUNT(*) INTO v15_row_count FROM fo_option_strike_bars_15min_v2;

    RAISE NOTICE 'V2 aggregate row counts: 5min=%, 15min=%', v5_row_count, v15_row_count;

    IF v5_row_count = 0 OR v15_row_count = 0 THEN
        RAISE EXCEPTION 'V2 aggregates are empty. Refresh and verify first.';
    END IF;

    RAISE NOTICE '✅ V2 aggregates have data';
    RAISE NOTICE 'Pre-flight checks PASSED. Proceeding with cutover...';
    RAISE NOTICE '========================================';
END$$;

-- ============================================================================
-- STEP 2: Backup Old Aggregates (Safety)
-- ============================================================================

DO $$
BEGIN
    RAISE NOTICE 'Backing up old aggregates...';

    -- Rename old aggregates to _old suffix
    -- This keeps them as backup in case we need to rollback

    -- Check if old aggregates exist before renaming
    IF EXISTS (SELECT 1 FROM pg_matviews WHERE matviewname = 'fo_option_strike_bars_5min') THEN
        ALTER MATERIALIZED VIEW fo_option_strike_bars_5min
        RENAME TO fo_option_strike_bars_5min_old;
        RAISE NOTICE '✅ Renamed fo_option_strike_bars_5min → fo_option_strike_bars_5min_old';
    END IF;

    IF EXISTS (SELECT 1 FROM pg_matviews WHERE matviewname = 'fo_option_strike_bars_15min') THEN
        ALTER MATERIALIZED VIEW fo_option_strike_bars_15min
        RENAME TO fo_option_strike_bars_15min_old;
        RAISE NOTICE '✅ Renamed fo_option_strike_bars_15min → fo_option_strike_bars_15min_old';
    END IF;
END$$;

-- ============================================================================
-- STEP 3: Atomic Cutover - Rename V2 to Production Names
-- ============================================================================

DO $$
BEGIN
    RAISE NOTICE '';
    RAISE NOTICE '⚡ ATOMIC CUTOVER IN PROGRESS...';

    -- Rename v2 aggregates to production names
    -- This is atomic - application code will instantly use new tables
    ALTER MATERIALIZED VIEW fo_option_strike_bars_5min_v2
    RENAME TO fo_option_strike_bars_5min;

    ALTER MATERIALIZED VIEW fo_option_strike_bars_15min_v2
    RENAME TO fo_option_strike_bars_15min;

    RAISE NOTICE '✅ CUTOVER COMPLETE';
    RAISE NOTICE '   fo_option_strike_bars_5min_v2 → fo_option_strike_bars_5min';
    RAISE NOTICE '   fo_option_strike_bars_15min_v2 → fo_option_strike_bars_15min';
    RAISE NOTICE '';
END$$;

-- ============================================================================
-- STEP 4: Drop Old Enriched Views (No Longer Needed)
-- ============================================================================

DO $$
BEGIN
    RAISE NOTICE 'Cleaning up old enriched views...';

    -- Drop enriched views that used JOINs
    DROP VIEW IF EXISTS fo_option_strike_bars_5min_enriched CASCADE;
    DROP VIEW IF EXISTS fo_option_strike_bars_15min_enriched CASCADE;

    RAISE NOTICE '✅ Dropped fo_option_strike_bars_5min_enriched';
    RAISE NOTICE '✅ Dropped fo_option_strike_bars_15min_enriched';
    RAISE NOTICE '';
    RAISE NOTICE '🎉 No more expensive JOINs!';
END$$;

-- ============================================================================
-- STEP 5: Update FO Expiry Metrics Views
-- ============================================================================

-- The expiry metrics views need to be recreated to use new aggregate names

DROP VIEW IF EXISTS fo_expiry_metrics_5min CASCADE;
DROP VIEW IF EXISTS fo_expiry_metrics_15min CASCADE;

CREATE OR REPLACE VIEW fo_expiry_metrics_5min AS
WITH strike_rollup AS (
    SELECT
        bucket_time,
        symbol,
        expiry,
        AVG(underlying_close) AS underlying_close,
        SUM(call_volume) AS total_call_volume,
        SUM(put_volume) AS total_put_volume,
        SUM(call_oi_sum) AS total_call_oi,  -- NEW: Direct access to OI
        SUM(put_oi_sum) AS total_put_oi,    -- NEW: Direct access to OI
        ARRAY_AGG(strike ORDER BY strike) AS strike_list,
        ARRAY_AGG(call_volume ORDER BY strike) AS call_volumes,
        ARRAY_AGG(put_volume ORDER BY strike) AS put_volumes
    FROM fo_option_strike_bars_5min
    GROUP BY bucket_time, symbol, expiry
)
SELECT
    bucket_time,
    '5min'::TEXT AS timeframe,
    symbol,
    expiry,
    underlying_close,
    total_call_volume,
    total_put_volume,
    total_call_oi,
    total_put_oi,
    CASE WHEN total_call_volume > 0 THEN total_put_volume / total_call_volume ELSE NULL END AS pcr,
    fo_compute_max_pain(strike_list, call_volumes, put_volumes) AS max_pain_strike,
    bucket_time AS created_at,
    bucket_time AS updated_at
FROM strike_rollup;

CREATE OR REPLACE VIEW fo_expiry_metrics_15min AS
WITH strike_rollup AS (
    SELECT
        bucket_time,
        symbol,
        expiry,
        AVG(underlying_close) AS underlying_close,
        SUM(call_volume) AS total_call_volume,
        SUM(put_volume) AS total_put_volume,
        SUM(call_oi_sum) AS total_call_oi,
        SUM(put_oi_sum) AS total_put_oi,
        ARRAY_AGG(strike ORDER BY strike) AS strike_list,
        ARRAY_AGG(call_volume ORDER BY strike) AS call_volumes,
        ARRAY_AGG(put_volume ORDER BY strike) AS put_volumes
    FROM fo_option_strike_bars_15min
    GROUP BY bucket_time, symbol, expiry
)
SELECT
    bucket_time,
    '15min'::TEXT AS timeframe,
    symbol,
    expiry,
    underlying_close,
    total_call_volume,
    total_put_volume,
    total_call_oi,
    total_put_oi,
    CASE WHEN total_call_volume > 0 THEN total_put_volume / total_call_volume ELSE NULL END AS pcr,
    fo_compute_max_pain(strike_list, call_volumes, put_volumes) AS max_pain_strike,
    bucket_time AS created_at,
    bucket_time AS updated_at
FROM strike_rollup;

RAISE NOTICE '✅ Updated fo_expiry_metrics views';

-- ============================================================================
-- STEP 6: Grant Permissions
-- ============================================================================

GRANT SELECT ON fo_option_strike_bars_5min TO stocksblitz;
GRANT SELECT ON fo_option_strike_bars_15min TO stocksblitz;
GRANT SELECT ON fo_expiry_metrics_5min TO stocksblitz;
GRANT SELECT ON fo_expiry_metrics_15min TO stocksblitz;

-- ============================================================================
-- STEP 7: Verification
-- ============================================================================

DO $$
DECLARE
    prod_5min_count INTEGER;
    prod_15min_count INTEGER;
    prod_5min_oi_count INTEGER;
    prod_15min_oi_count INTEGER;
BEGIN
    RAISE NOTICE '';
    RAISE NOTICE '========================================';
    RAISE NOTICE 'POST-CUTOVER VERIFICATION';
    RAISE NOTICE '========================================';

    -- Count rows in production tables
    SELECT COUNT(*) INTO prod_5min_count FROM fo_option_strike_bars_5min;
    SELECT COUNT(*) INTO prod_15min_count FROM fo_option_strike_bars_15min;

    -- Count rows with OI data
    SELECT COUNT(*) INTO prod_5min_oi_count
    FROM fo_option_strike_bars_5min
    WHERE call_oi_sum > 0 OR put_oi_sum > 0;

    SELECT COUNT(*) INTO prod_15min_oi_count
    FROM fo_option_strike_bars_15min
    WHERE call_oi_sum > 0 OR put_oi_sum > 0;

    RAISE NOTICE 'Production tables:';
    RAISE NOTICE '  fo_option_strike_bars_5min: % rows (% with OI)', prod_5min_count, prod_5min_oi_count;
    RAISE NOTICE '  fo_option_strike_bars_15min: % rows (% with OI)', prod_15min_count, prod_15min_oi_count;
    RAISE NOTICE '';

    -- Test query to verify OI columns are accessible
    PERFORM call_oi_sum, put_oi_sum
    FROM fo_option_strike_bars_5min
    LIMIT 1;

    PERFORM call_oi_sum, put_oi_sum
    FROM fo_option_strike_bars_15min
    LIMIT 1;

    RAISE NOTICE '✅ OI columns are directly accessible (no JOINs)';
    RAISE NOTICE '✅ Application code will automatically use new tables';
    RAISE NOTICE '';
    RAISE NOTICE '========================================';
    RAISE NOTICE '🎉 MIGRATION 017 COMPLETE';
    RAISE NOTICE '========================================';
    RAISE NOTICE '';
    RAISE NOTICE 'EXPECTED PERFORMANCE IMPROVEMENT:';
    RAISE NOTICE '  Query latency: 200-800ms → 50-200ms (3-5x faster)';
    RAISE NOTICE '  JOIN operations: 63 per request → 0';
    RAISE NOTICE '  Database load: Reduced by 30-40%';
    RAISE NOTICE '';
    RAISE NOTICE 'NEXT STEPS:';
    RAISE NOTICE '  1. Monitor application logs for errors';
    RAISE NOTICE '  2. Check /fo/strike-distribution endpoint performance';
    RAISE NOTICE '  3. If all looks good, run migration 018 to cleanup old tables';
    RAISE NOTICE '  4. Proceed with Phase 1B (Redis caching)';
    RAISE NOTICE '';
    RAISE NOTICE 'ROLLBACK (if needed):';
    RAISE NOTICE '  Run migrations/017_rollback.sql';
    RAISE NOTICE '========================================';
END$$;

COMMIT;
