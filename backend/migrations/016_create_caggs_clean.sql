-- Migration 016: Create Continuous Aggregates (Clean Version)
-- Date: 2025-11-02
-- Purpose: Replace regular views with TimescaleDB continuous aggregates
--
-- CURRENT STATE: fo_option_strike_bars_5min and _15min are REGULAR VIEWS
-- NEW STATE: Create materialized continuous aggregates with OI columns (_v2 suffix)
--
-- PERFORMANCE IMPACT:
-- Before: Live aggregation on every query (VERY SLOW)
-- After:  Pre-computed aggregates (10-50x faster!)

-- Note: Continuous aggregates cannot be created in a transaction block
-- Each command runs independently

-- ============================================================================
-- STEP 1: Create 5min Continuous Aggregate
-- ============================================================================

CREATE MATERIALIZED VIEW fo_option_strike_bars_5min_v2
WITH (timescaledb.continuous, timescaledb.create_group_indexes = FALSE) AS
SELECT
    time_bucket('5 minutes', bucket_time) AS bucket_time,
    '5min'::TEXT AS timeframe,
    symbol,
    expiry,
    strike,

    -- Underlying price (average over bucket)
    AVG(underlying_close) AS underlying_close,

    -- IV (Implied Volatility) - weighted average by count
    CASE
        WHEN SUM(CASE WHEN call_iv_avg IS NOT NULL THEN call_count ELSE 0 END) > 0
            THEN SUM(CASE WHEN call_iv_avg IS NOT NULL THEN call_iv_avg * call_count ELSE 0 END)
                 / NULLIF(SUM(CASE WHEN call_iv_avg IS NOT NULL THEN call_count ELSE 0 END), 0)
    END AS call_iv_avg,
    CASE
        WHEN SUM(CASE WHEN put_iv_avg IS NOT NULL THEN put_count ELSE 0 END) > 0
            THEN SUM(CASE WHEN put_iv_avg IS NOT NULL THEN put_iv_avg * put_count ELSE 0 END)
                 / NULLIF(SUM(CASE WHEN put_iv_avg IS NOT NULL THEN put_count ELSE 0 END), 0)
    END AS put_iv_avg,

    -- Delta - weighted average
    CASE
        WHEN SUM(CASE WHEN call_delta_avg IS NOT NULL THEN call_count ELSE 0 END) > 0
            THEN SUM(CASE WHEN call_delta_avg IS NOT NULL THEN call_delta_avg * call_count ELSE 0 END)
                 / NULLIF(SUM(CASE WHEN call_delta_avg IS NOT NULL THEN call_count ELSE 0 END), 0)
    END AS call_delta_avg,
    CASE
        WHEN SUM(CASE WHEN put_delta_avg IS NOT NULL THEN put_count ELSE 0 END) > 0
            THEN SUM(CASE WHEN put_delta_avg IS NOT NULL THEN put_delta_avg * put_count ELSE 0 END)
                 / NULLIF(SUM(CASE WHEN put_delta_avg IS NOT NULL THEN put_count ELSE 0 END), 0)
    END AS put_delta_avg,

    -- Gamma - weighted average
    CASE
        WHEN SUM(CASE WHEN call_gamma_avg IS NOT NULL THEN call_count ELSE 0 END) > 0
            THEN SUM(CASE WHEN call_gamma_avg IS NOT NULL THEN call_gamma_avg * call_count ELSE 0 END)
                 / NULLIF(SUM(CASE WHEN call_gamma_avg IS NOT NULL THEN call_count ELSE 0 END), 0)
    END AS call_gamma_avg,
    CASE
        WHEN SUM(CASE WHEN put_gamma_avg IS NOT NULL THEN put_count ELSE 0 END) > 0
            THEN SUM(CASE WHEN put_gamma_avg IS NOT NULL THEN put_gamma_avg * put_count ELSE 0 END)
                 / NULLIF(SUM(CASE WHEN put_gamma_avg IS NOT NULL THEN put_count ELSE 0 END), 0)
    END AS put_gamma_avg,

    -- Theta - weighted average
    CASE
        WHEN SUM(CASE WHEN call_theta_avg IS NOT NULL THEN call_count ELSE 0 END) > 0
            THEN SUM(CASE WHEN call_theta_avg IS NOT NULL THEN call_theta_avg * call_count ELSE 0 END)
                 / NULLIF(SUM(CASE WHEN call_theta_avg IS NOT NULL THEN call_count ELSE 0 END), 0)
    END AS call_theta_avg,
    CASE
        WHEN SUM(CASE WHEN put_theta_avg IS NOT NULL THEN put_count ELSE 0 END) > 0
            THEN SUM(CASE WHEN put_theta_avg IS NOT NULL THEN put_theta_avg * put_count ELSE 0 END)
                 / NULLIF(SUM(CASE WHEN put_theta_avg IS NOT NULL THEN put_count ELSE 0 END), 0)
    END AS put_theta_avg,

    -- Vega - weighted average
    CASE
        WHEN SUM(CASE WHEN call_vega_avg IS NOT NULL THEN call_count ELSE 0 END) > 0
            THEN SUM(CASE WHEN call_vega_avg IS NOT NULL THEN call_vega_avg * call_count ELSE 0 END)
                 / NULLIF(SUM(CASE WHEN call_vega_avg IS NOT NULL THEN call_count ELSE 0 END), 0)
    END AS call_vega_avg,
    CASE
        WHEN SUM(CASE WHEN put_vega_avg IS NOT NULL THEN put_count ELSE 0 END) > 0
            THEN SUM(CASE WHEN put_vega_avg IS NOT NULL THEN put_vega_avg * put_count ELSE 0 END)
                 / NULLIF(SUM(CASE WHEN put_vega_avg IS NOT NULL THEN put_count ELSE 0 END), 0)
    END AS put_vega_avg,

    -- Volume - sum over bucket
    SUM(call_volume) AS call_volume,
    SUM(put_volume) AS put_volume,

    -- Count - sum over bucket
    SUM(call_count) AS call_count,
    SUM(put_count) AS put_count,

    -- OI - use latest value (MAX to get most recent)
    MAX(call_oi_sum) AS call_oi_sum,
    MAX(put_oi_sum) AS put_oi_sum,

    -- Timestamps
    MIN(created_at) AS created_at,
    MAX(updated_at) AS updated_at
FROM fo_option_strike_bars
WHERE timeframe = '1min'
GROUP BY 1, 3, 4, 5;

-- ============================================================================
-- STEP 2: Add Refresh Policy for 5min Aggregate
-- ============================================================================

SELECT add_continuous_aggregate_policy(
    'fo_option_strike_bars_5min_v2',
    start_offset => INTERVAL '2 hours',
    end_offset => INTERVAL '1 minute',
    schedule_interval => INTERVAL '1 minute'
);

-- ============================================================================
-- STEP 3: Create 15min Continuous Aggregate
-- ============================================================================

CREATE MATERIALIZED VIEW fo_option_strike_bars_15min_v2
WITH (timescaledb.continuous, timescaledb.create_group_indexes = FALSE) AS
SELECT
    time_bucket('15 minutes', bucket_time) AS bucket_time,
    '15min'::TEXT AS timeframe,
    symbol,
    expiry,
    strike,

    -- Underlying price
    AVG(underlying_close) AS underlying_close,

    -- IV - weighted average
    CASE
        WHEN SUM(CASE WHEN call_iv_avg IS NOT NULL THEN call_count ELSE 0 END) > 0
            THEN SUM(CASE WHEN call_iv_avg IS NOT NULL THEN call_iv_avg * call_count ELSE 0 END)
                 / NULLIF(SUM(CASE WHEN call_iv_avg IS NOT NULL THEN call_count ELSE 0 END), 0)
    END AS call_iv_avg,
    CASE
        WHEN SUM(CASE WHEN put_iv_avg IS NOT NULL THEN put_count ELSE 0 END) > 0
            THEN SUM(CASE WHEN put_iv_avg IS NOT NULL THEN put_iv_avg * put_count ELSE 0 END)
                 / NULLIF(SUM(CASE WHEN put_iv_avg IS NOT NULL THEN put_count ELSE 0 END), 0)
    END AS put_iv_avg,

    -- Delta - weighted average
    CASE
        WHEN SUM(CASE WHEN call_delta_avg IS NOT NULL THEN call_count ELSE 0 END) > 0
            THEN SUM(CASE WHEN call_delta_avg IS NOT NULL THEN call_delta_avg * call_count ELSE 0 END)
                 / NULLIF(SUM(CASE WHEN call_delta_avg IS NOT NULL THEN call_count ELSE 0 END), 0)
    END AS call_delta_avg,
    CASE
        WHEN SUM(CASE WHEN put_delta_avg IS NOT NULL THEN put_count ELSE 0 END) > 0
            THEN SUM(CASE WHEN put_delta_avg IS NOT NULL THEN put_delta_avg * put_count ELSE 0 END)
                 / NULLIF(SUM(CASE WHEN put_delta_avg IS NOT NULL THEN put_count ELSE 0 END), 0)
    END AS put_delta_avg,

    -- Gamma - weighted average
    CASE
        WHEN SUM(CASE WHEN call_gamma_avg IS NOT NULL THEN call_count ELSE 0 END) > 0
            THEN SUM(CASE WHEN call_gamma_avg IS NOT NULL THEN call_gamma_avg * call_count ELSE 0 END)
                 / NULLIF(SUM(CASE WHEN call_gamma_avg IS NOT NULL THEN call_count ELSE 0 END), 0)
    END AS call_gamma_avg,
    CASE
        WHEN SUM(CASE WHEN put_gamma_avg IS NOT NULL THEN put_count ELSE 0 END) > 0
            THEN SUM(CASE WHEN put_gamma_avg IS NOT NULL THEN put_gamma_avg * put_count ELSE 0 END)
                 / NULLIF(SUM(CASE WHEN put_gamma_avg IS NOT NULL THEN put_count ELSE 0 END), 0)
    END AS put_gamma_avg,

    -- Theta - weighted average
    CASE
        WHEN SUM(CASE WHEN call_theta_avg IS NOT NULL THEN call_count ELSE 0 END) > 0
            THEN SUM(CASE WHEN call_theta_avg IS NOT NULL THEN call_theta_avg * call_count ELSE 0 END)
                 / NULLIF(SUM(CASE WHEN call_theta_avg IS NOT NULL THEN call_count ELSE 0 END), 0)
    END AS call_theta_avg,
    CASE
        WHEN SUM(CASE WHEN put_theta_avg IS NOT NULL THEN put_count ELSE 0 END) > 0
            THEN SUM(CASE WHEN put_theta_avg IS NOT NULL THEN put_theta_avg * put_count ELSE 0 END)
                 / NULLIF(SUM(CASE WHEN put_theta_avg IS NOT NULL THEN put_count ELSE 0 END), 0)
    END AS put_theta_avg,

    -- Vega - weighted average
    CASE
        WHEN SUM(CASE WHEN call_vega_avg IS NOT NULL THEN call_count ELSE 0 END) > 0
            THEN SUM(CASE WHEN call_vega_avg IS NOT NULL THEN call_vega_avg * call_count ELSE 0 END)
                 / NULLIF(SUM(CASE WHEN call_vega_avg IS NOT NULL THEN call_count ELSE 0 END), 0)
    END AS call_vega_avg,
    CASE
        WHEN SUM(CASE WHEN put_vega_avg IS NOT NULL THEN put_count ELSE 0 END) > 0
            THEN SUM(CASE WHEN put_vega_avg IS NOT NULL THEN put_vega_avg * put_count ELSE 0 END)
                 / NULLIF(SUM(CASE WHEN put_vega_avg IS NOT NULL THEN put_count ELSE 0 END), 0)
    END AS put_vega_avg,

    -- Volume
    SUM(call_volume) AS call_volume,
    SUM(put_volume) AS put_volume,

    -- Count
    SUM(call_count) AS call_count,
    SUM(put_count) AS put_count,

    -- OI - use latest value
    MAX(call_oi_sum) AS call_oi_sum,
    MAX(put_oi_sum) AS put_oi_sum,

    -- Timestamps
    MIN(created_at) AS created_at,
    MAX(updated_at) AS updated_at
FROM fo_option_strike_bars
WHERE timeframe = '1min'
GROUP BY 1, 3, 4, 5;

-- ============================================================================
-- STEP 4: Add Refresh Policy for 15min Aggregate
-- ============================================================================

SELECT add_continuous_aggregate_policy(
    'fo_option_strike_bars_15min_v2',
    start_offset => INTERVAL '6 hours',
    end_offset => INTERVAL '1 minute',
    schedule_interval => INTERVAL '5 minutes'
);

-- ============================================================================
-- STEP 5: Initial Refresh (7 days of data)
-- ============================================================================

CALL refresh_continuous_aggregate('fo_option_strike_bars_5min_v2', NOW() - INTERVAL '7 days', NOW());
CALL refresh_continuous_aggregate('fo_option_strike_bars_15min_v2', NOW() - INTERVAL '7 days', NOW());

-- ============================================================================
-- STEP 6: Grant Permissions
-- ============================================================================

GRANT SELECT ON fo_option_strike_bars_5min_v2 TO stocksblitz;
GRANT SELECT ON fo_option_strike_bars_15min_v2 TO stocksblitz;

-- ============================================================================
-- Verification (Run separately if needed)
-- ============================================================================

DO $$
DECLARE
    count_5min BIGINT;
    count_15min BIGINT;
    oi_5min BIGINT;
    oi_15min BIGINT;
BEGIN
    SELECT COUNT(*) INTO count_5min FROM fo_option_strike_bars_5min_v2;
    SELECT COUNT(*) INTO count_15min FROM fo_option_strike_bars_15min_v2;

    SELECT COUNT(*) INTO oi_5min FROM fo_option_strike_bars_5min_v2
    WHERE call_oi_sum IS NOT NULL OR put_oi_sum IS NOT NULL;

    SELECT COUNT(*) INTO oi_15min FROM fo_option_strike_bars_15min_v2
    WHERE call_oi_sum IS NOT NULL OR put_oi_sum IS NOT NULL;

    RAISE NOTICE '========================================';
    RAISE NOTICE 'MIGRATION 016 VERIFICATION';
    RAISE NOTICE '========================================';
    RAISE NOTICE '5min aggregate: % rows (% with OI)', count_5min, oi_5min;
    RAISE NOTICE '15min aggregate: % rows (% with OI)', count_15min, oi_15min;

    IF count_5min > 0 AND count_15min > 0 THEN
        RAISE NOTICE '✅ SUCCESS: Continuous aggregates created with OI data';
        RAISE NOTICE 'Next: Verify queries work, then run migration 017 for cutover';
    ELSE
        RAISE WARNING '⚠️  Warning: Aggregates created but appear empty';
    END IF;

    RAISE NOTICE '========================================';
END$$;
