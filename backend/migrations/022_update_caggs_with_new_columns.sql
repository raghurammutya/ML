-- Migration 022: Update Continuous Aggregates with Enhanced Greeks and Liquidity Metrics
-- Date: 2025-11-06
-- Purpose: Add columns from migrations 020 (Enhanced Greeks) and 021 (Liquidity Metrics) to continuous aggregates
--
-- BACKGROUND:
-- - Migration 020 added: intrinsic, extrinsic, model_price, theta_daily, rho_per_1pct (5 cols × 2 = 10 cols)
-- - Migration 021 added: 17 liquidity/market depth metrics
-- - Migration 016 created continuous aggregates BEFORE these columns existed
-- - API queries the continuous aggregates, not the base table
--
-- RESULT: "column does not exist" errors when querying new metrics via API
--
-- SOLUTION: Drop and recreate continuous aggregates with all columns

-- ============================================================================
-- STEP 1: Drop Existing Continuous Aggregates
-- ============================================================================

DROP MATERIALIZED VIEW IF EXISTS fo_option_strike_bars_5min_v2 CASCADE;
DROP MATERIALIZED VIEW IF EXISTS fo_option_strike_bars_15min_v2 CASCADE;

-- ============================================================================
-- STEP 2: Create 5min Continuous Aggregate with ALL Columns
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

    -- ========================================================================
    -- EXISTING GREEKS (Standard Greeks - IV, Delta, Gamma, Theta, Vega)
    -- ========================================================================

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

    -- ========================================================================
    -- ENHANCED GREEKS (Migration 020) - Weighted average by count
    -- ========================================================================

    -- Intrinsic Value
    CASE
        WHEN SUM(CASE WHEN call_intrinsic_avg IS NOT NULL THEN call_count ELSE 0 END) > 0
            THEN SUM(CASE WHEN call_intrinsic_avg IS NOT NULL THEN call_intrinsic_avg * call_count ELSE 0 END)
                 / NULLIF(SUM(CASE WHEN call_intrinsic_avg IS NOT NULL THEN call_count ELSE 0 END), 0)
    END AS call_intrinsic_avg,
    CASE
        WHEN SUM(CASE WHEN put_intrinsic_avg IS NOT NULL THEN put_count ELSE 0 END) > 0
            THEN SUM(CASE WHEN put_intrinsic_avg IS NOT NULL THEN put_intrinsic_avg * put_count ELSE 0 END)
                 / NULLIF(SUM(CASE WHEN put_intrinsic_avg IS NOT NULL THEN put_count ELSE 0 END), 0)
    END AS put_intrinsic_avg,

    -- Extrinsic Value
    CASE
        WHEN SUM(CASE WHEN call_extrinsic_avg IS NOT NULL THEN call_count ELSE 0 END) > 0
            THEN SUM(CASE WHEN call_extrinsic_avg IS NOT NULL THEN call_extrinsic_avg * call_count ELSE 0 END)
                 / NULLIF(SUM(CASE WHEN call_extrinsic_avg IS NOT NULL THEN call_count ELSE 0 END), 0)
    END AS call_extrinsic_avg,
    CASE
        WHEN SUM(CASE WHEN put_extrinsic_avg IS NOT NULL THEN put_count ELSE 0 END) > 0
            THEN SUM(CASE WHEN put_extrinsic_avg IS NOT NULL THEN put_extrinsic_avg * put_count ELSE 0 END)
                 / NULLIF(SUM(CASE WHEN put_extrinsic_avg IS NOT NULL THEN put_count ELSE 0 END), 0)
    END AS put_extrinsic_avg,

    -- Model Price (Black-Scholes theoretical price)
    CASE
        WHEN SUM(CASE WHEN call_model_price_avg IS NOT NULL THEN call_count ELSE 0 END) > 0
            THEN SUM(CASE WHEN call_model_price_avg IS NOT NULL THEN call_model_price_avg * call_count ELSE 0 END)
                 / NULLIF(SUM(CASE WHEN call_model_price_avg IS NOT NULL THEN call_count ELSE 0 END), 0)
    END AS call_model_price_avg,
    CASE
        WHEN SUM(CASE WHEN put_model_price_avg IS NOT NULL THEN put_count ELSE 0 END) > 0
            THEN SUM(CASE WHEN put_model_price_avg IS NOT NULL THEN put_model_price_avg * put_count ELSE 0 END)
                 / NULLIF(SUM(CASE WHEN put_model_price_avg IS NOT NULL THEN put_count ELSE 0 END), 0)
    END AS put_model_price_avg,

    -- Theta Daily (decay per day)
    CASE
        WHEN SUM(CASE WHEN call_theta_daily_avg IS NOT NULL THEN call_count ELSE 0 END) > 0
            THEN SUM(CASE WHEN call_theta_daily_avg IS NOT NULL THEN call_theta_daily_avg * call_count ELSE 0 END)
                 / NULLIF(SUM(CASE WHEN call_theta_daily_avg IS NOT NULL THEN call_count ELSE 0 END), 0)
    END AS call_theta_daily_avg,
    CASE
        WHEN SUM(CASE WHEN put_theta_daily_avg IS NOT NULL THEN put_count ELSE 0 END) > 0
            THEN SUM(CASE WHEN put_theta_daily_avg IS NOT NULL THEN put_theta_daily_avg * put_count ELSE 0 END)
                 / NULLIF(SUM(CASE WHEN put_theta_daily_avg IS NOT NULL THEN put_count ELSE 0 END), 0)
    END AS put_theta_daily_avg,

    -- Rho per 1% rate change
    CASE
        WHEN SUM(CASE WHEN call_rho_per_1pct_avg IS NOT NULL THEN call_count ELSE 0 END) > 0
            THEN SUM(CASE WHEN call_rho_per_1pct_avg IS NOT NULL THEN call_rho_per_1pct_avg * call_count ELSE 0 END)
                 / NULLIF(SUM(CASE WHEN call_rho_per_1pct_avg IS NOT NULL THEN call_count ELSE 0 END), 0)
    END AS call_rho_per_1pct_avg,
    CASE
        WHEN SUM(CASE WHEN put_rho_per_1pct_avg IS NOT NULL THEN put_count ELSE 0 END) > 0
            THEN SUM(CASE WHEN put_rho_per_1pct_avg IS NOT NULL THEN put_rho_per_1pct_avg * put_count ELSE 0 END)
                 / NULLIF(SUM(CASE WHEN put_rho_per_1pct_avg IS NOT NULL THEN put_count ELSE 0 END), 0)
    END AS put_rho_per_1pct_avg,

    -- ========================================================================
    -- LIQUIDITY METRICS (Migration 021)
    -- ========================================================================

    -- Liquidity Score (0-100)
    AVG(liquidity_score_avg) AS liquidity_score_avg,
    MIN(liquidity_score_min) AS liquidity_score_min,

    -- Liquidity Tier (most common: HIGH/MEDIUM/LOW/ILLIQUID)
    MODE() WITHIN GROUP (ORDER BY liquidity_tier) AS liquidity_tier,

    -- Spread Metrics
    AVG(spread_abs_avg) AS spread_abs_avg,
    AVG(spread_pct_avg) AS spread_pct_avg,
    MAX(spread_pct_max) AS spread_pct_max,

    -- Order Book Imbalance
    AVG(depth_imbalance_pct_avg) AS depth_imbalance_pct_avg,
    AVG(book_pressure_avg) AS book_pressure_avg,

    -- Depth Quantities (average then cast to integer)
    CAST(AVG(total_bid_quantity_avg) AS INTEGER) AS total_bid_quantity_avg,
    CAST(AVG(total_ask_quantity_avg) AS INTEGER) AS total_ask_quantity_avg,
    CAST(AVG(depth_at_best_bid_avg) AS INTEGER) AS depth_at_best_bid_avg,
    CAST(AVG(depth_at_best_ask_avg) AS INTEGER) AS depth_at_best_ask_avg,

    -- Advanced Metrics
    AVG(microprice_avg) AS microprice_avg,
    AVG(market_impact_100_avg) AS market_impact_100_avg,

    -- Illiquid Detection (sum tick counts, compute ratio)
    SUM(illiquid_tick_count) AS illiquid_tick_count,
    SUM(total_tick_count) AS total_tick_count,
    CASE
        WHEN SUM(total_tick_count) > 0
            THEN (SUM(illiquid_tick_count)::float / SUM(total_tick_count)) > 0.5
        ELSE FALSE
    END AS is_illiquid,

    -- ========================================================================
    -- VOLUME, COUNT, OI, TIMESTAMPS (Original columns)
    -- ========================================================================

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
-- STEP 3: Add Refresh Policy for 5min Aggregate
-- ============================================================================

SELECT add_continuous_aggregate_policy(
    'fo_option_strike_bars_5min_v2',
    start_offset => INTERVAL '2 hours',
    end_offset => INTERVAL '1 minute',
    schedule_interval => INTERVAL '1 minute'
);

-- ============================================================================
-- STEP 4: Create 15min Continuous Aggregate with ALL Columns
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

    -- ========================================================================
    -- EXISTING GREEKS (Standard Greeks - IV, Delta, Gamma, Theta, Vega)
    -- ========================================================================

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

    -- ========================================================================
    -- ENHANCED GREEKS (Migration 020) - Weighted average by count
    -- ========================================================================

    -- Intrinsic Value
    CASE
        WHEN SUM(CASE WHEN call_intrinsic_avg IS NOT NULL THEN call_count ELSE 0 END) > 0
            THEN SUM(CASE WHEN call_intrinsic_avg IS NOT NULL THEN call_intrinsic_avg * call_count ELSE 0 END)
                 / NULLIF(SUM(CASE WHEN call_intrinsic_avg IS NOT NULL THEN call_count ELSE 0 END), 0)
    END AS call_intrinsic_avg,
    CASE
        WHEN SUM(CASE WHEN put_intrinsic_avg IS NOT NULL THEN put_count ELSE 0 END) > 0
            THEN SUM(CASE WHEN put_intrinsic_avg IS NOT NULL THEN put_intrinsic_avg * put_count ELSE 0 END)
                 / NULLIF(SUM(CASE WHEN put_intrinsic_avg IS NOT NULL THEN put_count ELSE 0 END), 0)
    END AS put_intrinsic_avg,

    -- Extrinsic Value
    CASE
        WHEN SUM(CASE WHEN call_extrinsic_avg IS NOT NULL THEN call_count ELSE 0 END) > 0
            THEN SUM(CASE WHEN call_extrinsic_avg IS NOT NULL THEN call_extrinsic_avg * call_count ELSE 0 END)
                 / NULLIF(SUM(CASE WHEN call_extrinsic_avg IS NOT NULL THEN call_count ELSE 0 END), 0)
    END AS call_extrinsic_avg,
    CASE
        WHEN SUM(CASE WHEN put_extrinsic_avg IS NOT NULL THEN put_count ELSE 0 END) > 0
            THEN SUM(CASE WHEN put_extrinsic_avg IS NOT NULL THEN put_extrinsic_avg * put_count ELSE 0 END)
                 / NULLIF(SUM(CASE WHEN put_extrinsic_avg IS NOT NULL THEN put_count ELSE 0 END), 0)
    END AS put_extrinsic_avg,

    -- Model Price
    CASE
        WHEN SUM(CASE WHEN call_model_price_avg IS NOT NULL THEN call_count ELSE 0 END) > 0
            THEN SUM(CASE WHEN call_model_price_avg IS NOT NULL THEN call_model_price_avg * call_count ELSE 0 END)
                 / NULLIF(SUM(CASE WHEN call_model_price_avg IS NOT NULL THEN call_count ELSE 0 END), 0)
    END AS call_model_price_avg,
    CASE
        WHEN SUM(CASE WHEN put_model_price_avg IS NOT NULL THEN put_count ELSE 0 END) > 0
            THEN SUM(CASE WHEN put_model_price_avg IS NOT NULL THEN put_model_price_avg * put_count ELSE 0 END)
                 / NULLIF(SUM(CASE WHEN put_model_price_avg IS NOT NULL THEN put_count ELSE 0 END), 0)
    END AS put_model_price_avg,

    -- Theta Daily
    CASE
        WHEN SUM(CASE WHEN call_theta_daily_avg IS NOT NULL THEN call_count ELSE 0 END) > 0
            THEN SUM(CASE WHEN call_theta_daily_avg IS NOT NULL THEN call_theta_daily_avg * call_count ELSE 0 END)
                 / NULLIF(SUM(CASE WHEN call_theta_daily_avg IS NOT NULL THEN call_count ELSE 0 END), 0)
    END AS call_theta_daily_avg,
    CASE
        WHEN SUM(CASE WHEN put_theta_daily_avg IS NOT NULL THEN put_count ELSE 0 END) > 0
            THEN SUM(CASE WHEN put_theta_daily_avg IS NOT NULL THEN put_theta_daily_avg * put_count ELSE 0 END)
                 / NULLIF(SUM(CASE WHEN put_theta_daily_avg IS NOT NULL THEN put_count ELSE 0 END), 0)
    END AS put_theta_daily_avg,

    -- Rho per 1%
    CASE
        WHEN SUM(CASE WHEN call_rho_per_1pct_avg IS NOT NULL THEN call_count ELSE 0 END) > 0
            THEN SUM(CASE WHEN call_rho_per_1pct_avg IS NOT NULL THEN call_rho_per_1pct_avg * call_count ELSE 0 END)
                 / NULLIF(SUM(CASE WHEN call_rho_per_1pct_avg IS NOT NULL THEN call_count ELSE 0 END), 0)
    END AS call_rho_per_1pct_avg,
    CASE
        WHEN SUM(CASE WHEN put_rho_per_1pct_avg IS NOT NULL THEN put_count ELSE 0 END) > 0
            THEN SUM(CASE WHEN put_rho_per_1pct_avg IS NOT NULL THEN put_rho_per_1pct_avg * put_count ELSE 0 END)
                 / NULLIF(SUM(CASE WHEN put_rho_per_1pct_avg IS NOT NULL THEN put_count ELSE 0 END), 0)
    END AS put_rho_per_1pct_avg,

    -- ========================================================================
    -- LIQUIDITY METRICS (Migration 021)
    -- ========================================================================

    -- Liquidity Score
    AVG(liquidity_score_avg) AS liquidity_score_avg,
    MIN(liquidity_score_min) AS liquidity_score_min,

    -- Liquidity Tier
    MODE() WITHIN GROUP (ORDER BY liquidity_tier) AS liquidity_tier,

    -- Spread Metrics
    AVG(spread_abs_avg) AS spread_abs_avg,
    AVG(spread_pct_avg) AS spread_pct_avg,
    MAX(spread_pct_max) AS spread_pct_max,

    -- Imbalance
    AVG(depth_imbalance_pct_avg) AS depth_imbalance_pct_avg,
    AVG(book_pressure_avg) AS book_pressure_avg,

    -- Depth Quantities
    CAST(AVG(total_bid_quantity_avg) AS INTEGER) AS total_bid_quantity_avg,
    CAST(AVG(total_ask_quantity_avg) AS INTEGER) AS total_ask_quantity_avg,
    CAST(AVG(depth_at_best_bid_avg) AS INTEGER) AS depth_at_best_bid_avg,
    CAST(AVG(depth_at_best_ask_avg) AS INTEGER) AS depth_at_best_ask_avg,

    -- Advanced
    AVG(microprice_avg) AS microprice_avg,
    AVG(market_impact_100_avg) AS market_impact_100_avg,

    -- Illiquid Detection
    SUM(illiquid_tick_count) AS illiquid_tick_count,
    SUM(total_tick_count) AS total_tick_count,
    CASE
        WHEN SUM(total_tick_count) > 0
            THEN (SUM(illiquid_tick_count)::float / SUM(total_tick_count)) > 0.5
        ELSE FALSE
    END AS is_illiquid,

    -- ========================================================================
    -- VOLUME, COUNT, OI, TIMESTAMPS
    -- ========================================================================

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
-- STEP 5: Add Refresh Policy for 15min Aggregate
-- ============================================================================

SELECT add_continuous_aggregate_policy(
    'fo_option_strike_bars_15min_v2',
    start_offset => INTERVAL '6 hours',
    end_offset => INTERVAL '1 minute',
    schedule_interval => INTERVAL '5 minutes'
);

-- ============================================================================
-- STEP 6: Initial Refresh (7 days of data)
-- ============================================================================

CALL refresh_continuous_aggregate('fo_option_strike_bars_5min_v2', NOW() - INTERVAL '7 days', NOW());
CALL refresh_continuous_aggregate('fo_option_strike_bars_15min_v2', NOW() - INTERVAL '7 days', NOW());

-- ============================================================================
-- STEP 7: Grant Permissions
-- ============================================================================

GRANT SELECT ON fo_option_strike_bars_5min_v2 TO stocksblitz;
GRANT SELECT ON fo_option_strike_bars_15min_v2 TO stocksblitz;

-- ============================================================================
-- STEP 8: Verification
-- ============================================================================

DO $$
DECLARE
    count_5min BIGINT;
    count_15min BIGINT;
    rho_5min BIGINT;
    rho_15min BIGINT;
    liq_5min BIGINT;
    liq_15min BIGINT;
BEGIN
    SELECT COUNT(*) INTO count_5min FROM fo_option_strike_bars_5min_v2;
    SELECT COUNT(*) INTO count_15min FROM fo_option_strike_bars_15min_v2;

    -- Check for enhanced Greeks (RHO)
    SELECT COUNT(*) INTO rho_5min FROM fo_option_strike_bars_5min_v2
    WHERE call_rho_per_1pct_avg IS NOT NULL OR put_rho_per_1pct_avg IS NOT NULL;

    SELECT COUNT(*) INTO rho_15min FROM fo_option_strike_bars_15min_v2
    WHERE call_rho_per_1pct_avg IS NOT NULL OR put_rho_per_1pct_avg IS NOT NULL;

    -- Check for liquidity metrics
    SELECT COUNT(*) INTO liq_5min FROM fo_option_strike_bars_5min_v2
    WHERE liquidity_score_avg IS NOT NULL;

    SELECT COUNT(*) INTO liq_15min FROM fo_option_strike_bars_15min_v2
    WHERE liquidity_score_avg IS NOT NULL;

    RAISE NOTICE '========================================';
    RAISE NOTICE 'MIGRATION 022 VERIFICATION';
    RAISE NOTICE '========================================';
    RAISE NOTICE '5min aggregate: % rows', count_5min;
    RAISE NOTICE '  - Rows with RHO: %', rho_5min;
    RAISE NOTICE '  - Rows with liquidity: %', liq_5min;
    RAISE NOTICE '';
    RAISE NOTICE '15min aggregate: % rows', count_15min;
    RAISE NOTICE '  - Rows with RHO: %', rho_15min;
    RAISE NOTICE '  - Rows with liquidity: %', liq_15min;

    IF count_5min > 0 AND count_15min > 0 THEN
        RAISE NOTICE '';
        RAISE NOTICE '✅ SUCCESS: Continuous aggregates recreated';
        RAISE NOTICE '   - Enhanced Greeks: intrinsic, extrinsic, model_price, theta_daily, rho_per_1pct';
        RAISE NOTICE '   - Liquidity Metrics: 17 columns for market depth analysis';
    ELSE
        RAISE WARNING '⚠️  Warning: Aggregates created but appear empty';
    END IF;

    RAISE NOTICE '========================================';
END$$;
