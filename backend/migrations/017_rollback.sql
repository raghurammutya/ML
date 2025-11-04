-- Migration 017 Rollback: Revert to Old Enriched Views
-- Purpose: Emergency rollback if v2 aggregates have issues
--
-- WARNING: Only use this if you encounter critical issues after migration 017
-- This will restore the old enriched views with JOINs (slower performance)

BEGIN;

RAISE NOTICE '========================================';
RAISE NOTICE 'ROLLING BACK MIGRATION 017';
RAISE NOTICE '========================================';

-- ============================================================================
-- STEP 1: Rename Current Production Tables Back to V2
-- ============================================================================

DO $$
BEGIN
    RAISE NOTICE 'Reverting production tables to v2 suffix...';

    -- Rename current production tables back to v2
    ALTER MATERIALIZED VIEW IF EXISTS fo_option_strike_bars_5min
    RENAME TO fo_option_strike_bars_5min_v2;

    ALTER MATERIALIZED VIEW IF EXISTS fo_option_strike_bars_15min
    RENAME TO fo_option_strike_bars_15min_v2;

    RAISE NOTICE '✅ Renamed to v2 suffix';
END$$;

-- ============================================================================
-- STEP 2: Restore Old Aggregates
-- ============================================================================

DO $$
BEGIN
    RAISE NOTICE 'Restoring old aggregates...';

    -- Rename old aggregates back to production names
    ALTER MATERIALIZED VIEW IF EXISTS fo_option_strike_bars_5min_old
    RENAME TO fo_option_strike_bars_5min;

    ALTER MATERIALIZED VIEW IF EXISTS fo_option_strike_bars_15min_old
    RENAME TO fo_option_strike_bars_15min;

    RAISE NOTICE '✅ Restored old aggregates';
END$$;

-- ============================================================================
-- STEP 3: Recreate Enriched Views
-- ============================================================================

RAISE NOTICE 'Recreating enriched views with JOINs...';

-- Recreate 5min enriched view
CREATE OR REPLACE VIEW fo_option_strike_bars_5min_enriched AS
SELECT
    agg.bucket_time,
    agg.timeframe,
    agg.symbol,
    agg.expiry,
    agg.strike,
    agg.underlying_close,
    agg.call_iv_avg,
    agg.put_iv_avg,
    agg.call_delta_avg,
    agg.put_delta_avg,
    agg.call_gamma_avg,
    agg.put_gamma_avg,
    agg.call_theta_avg,
    agg.put_theta_avg,
    agg.call_vega_avg,
    agg.put_vega_avg,
    agg.call_volume,
    agg.put_volume,
    agg.call_count,
    agg.put_count,
    agg.created_at,
    agg.updated_at,
    COALESCE(MAX(base.call_oi_sum), 0) AS call_oi_sum,
    COALESCE(MAX(base.put_oi_sum), 0) AS put_oi_sum
FROM fo_option_strike_bars_5min agg
LEFT JOIN fo_option_strike_bars base
    ON base.timeframe = '1min'
    AND base.symbol = agg.symbol
    AND base.expiry = agg.expiry
    AND base.strike = agg.strike
    AND base.bucket_time >= agg.bucket_time
    AND base.bucket_time < agg.bucket_time + INTERVAL '5 minutes'
GROUP BY
    agg.bucket_time, agg.timeframe, agg.symbol, agg.expiry, agg.strike,
    agg.underlying_close, agg.call_iv_avg, agg.put_iv_avg,
    agg.call_delta_avg, agg.put_delta_avg, agg.call_gamma_avg,
    agg.put_gamma_avg, agg.call_theta_avg, agg.put_theta_avg,
    agg.call_vega_avg, agg.put_vega_avg, agg.call_volume, agg.put_volume,
    agg.call_count, agg.put_count, agg.created_at, agg.updated_at;

-- Recreate 15min enriched view
CREATE OR REPLACE VIEW fo_option_strike_bars_15min_enriched AS
SELECT
    agg.bucket_time,
    agg.timeframe,
    agg.symbol,
    agg.expiry,
    agg.strike,
    agg.underlying_close,
    agg.call_iv_avg,
    agg.put_iv_avg,
    agg.call_delta_avg,
    agg.put_delta_avg,
    agg.call_gamma_avg,
    agg.put_gamma_avg,
    agg.call_theta_avg,
    agg.put_theta_avg,
    agg.call_vega_avg,
    agg.put_vega_avg,
    agg.call_volume,
    agg.put_volume,
    agg.call_count,
    agg.put_count,
    agg.created_at,
    agg.updated_at,
    COALESCE(MAX(base.call_oi_sum), 0) AS call_oi_sum,
    COALESCE(MAX(base.put_oi_sum), 0) AS put_oi_sum
FROM fo_option_strike_bars_15min agg
LEFT JOIN fo_option_strike_bars base
    ON base.timeframe = '1min'
    AND base.symbol = agg.symbol
    AND base.expiry = agg.expiry
    AND base.strike = agg.strike
    AND base.bucket_time >= agg.bucket_time
    AND base.bucket_time < agg.bucket_time + INTERVAL '15 minutes'
GROUP BY
    agg.bucket_time, agg.timeframe, agg.symbol, agg.expiry, agg.strike,
    agg.underlying_close, agg.call_iv_avg, agg.put_iv_avg,
    agg.call_delta_avg, agg.put_delta_avg, agg.call_gamma_avg,
    agg.put_gamma_avg, agg.call_theta_avg, agg.put_theta_avg,
    agg.call_vega_avg, agg.put_vega_avg, agg.call_volume, agg.put_volume,
    agg.call_count, agg.put_count, agg.created_at, agg.updated_at;

RAISE NOTICE '✅ Recreated enriched views';

-- ============================================================================
-- STEP 4: Update FO Expiry Metrics Views
-- ============================================================================

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
    CASE WHEN total_call_volume > 0 THEN total_put_volume / total_call_volume ELSE NULL END AS pcr,
    fo_compute_max_pain(strike_list, call_volumes, put_volumes) AS max_pain_strike,
    bucket_time AS created_at,
    bucket_time AS updated_at
FROM strike_rollup;

-- ============================================================================
-- STEP 5: Grant Permissions
-- ============================================================================

GRANT SELECT ON fo_option_strike_bars_5min TO stocksblitz;
GRANT SELECT ON fo_option_strike_bars_15min TO stocksblitz;
GRANT SELECT ON fo_option_strike_bars_5min_enriched TO stocksblitz;
GRANT SELECT ON fo_option_strike_bars_15min_enriched TO stocksblitz;
GRANT SELECT ON fo_expiry_metrics_5min TO stocksblitz;
GRANT SELECT ON fo_expiry_metrics_15min TO stocksblitz;

COMMIT;

-- ============================================================================
-- Verification
-- ============================================================================

DO $$
BEGIN
    RAISE NOTICE '';
    RAISE NOTICE '========================================';
    RAISE NOTICE '✅ ROLLBACK COMPLETE';
    RAISE NOTICE '========================================';
    RAISE NOTICE '';
    RAISE NOTICE 'System has been reverted to old enriched views';
    RAISE NOTICE 'Performance will be slower (JOINs re-enabled)';
    RAISE NOTICE '';
    RAISE NOTICE 'NEXT STEPS:';
    RAISE NOTICE '  1. Investigate what went wrong with v2 aggregates';
    RAISE NOTICE '  2. Fix issues and re-run migration 016 + 017';
    RAISE NOTICE '  3. Report issue to development team';
    RAISE NOTICE '========================================';
END$$;
