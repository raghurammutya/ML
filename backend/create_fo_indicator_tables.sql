-- FO indicator persistence layer
-- Run this script inside the Timescale/PostgreSQL database that powers the TradingView backend.

CREATE TABLE IF NOT EXISTS fo_option_strike_bars (
    bucket_time TIMESTAMPTZ NOT NULL,
    timeframe TEXT NOT NULL,
    symbol TEXT NOT NULL,
    expiry DATE NOT NULL,
    strike NUMERIC(10,2) NOT NULL,
    underlying_close DOUBLE PRECISION,
    call_iv_avg DOUBLE PRECISION,
    put_iv_avg DOUBLE PRECISION,
    call_delta_avg DOUBLE PRECISION,
    put_delta_avg DOUBLE PRECISION,
    call_gamma_avg DOUBLE PRECISION,
    put_gamma_avg DOUBLE PRECISION,
    call_theta_avg DOUBLE PRECISION,
    put_theta_avg DOUBLE PRECISION,
    call_vega_avg DOUBLE PRECISION,
    put_vega_avg DOUBLE PRECISION,
    call_volume DOUBLE PRECISION,
    put_volume DOUBLE PRECISION,
    call_count INTEGER,
    put_count INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY(symbol, expiry, timeframe, bucket_time, strike)
);

SELECT create_hypertable('fo_option_strike_bars', 'bucket_time', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_fo_strike_symbol_tf ON fo_option_strike_bars (symbol, timeframe, bucket_time DESC);

ALTER TABLE fo_option_strike_bars
    SET (timescaledb.compress = TRUE,
         timescaledb.compress_segmentby = 'symbol,expiry,timeframe,strike');

DO $$
BEGIN
    BEGIN
        PERFORM add_compression_policy('fo_option_strike_bars', INTERVAL '2 days');
    EXCEPTION
        WHEN duplicate_object THEN
            RAISE NOTICE 'Compression policy for fo_option_strike_bars already exists';
    END;
END$$;

DO $$
BEGIN
    BEGIN
        PERFORM add_retention_policy('fo_option_strike_bars', INTERVAL '30 days');
    EXCEPTION
        WHEN duplicate_object THEN
            RAISE NOTICE 'Retention policy for fo_option_strike_bars already exists';
    END;
END$$;

CREATE TABLE IF NOT EXISTS fo_expiry_metrics (
    bucket_time TIMESTAMPTZ NOT NULL,
    timeframe TEXT NOT NULL,
    symbol TEXT NOT NULL,
    expiry DATE NOT NULL,
    underlying_close DOUBLE PRECISION,
    total_call_volume DOUBLE PRECISION,
    total_put_volume DOUBLE PRECISION,
    pcr DOUBLE PRECISION,
    max_pain_strike DOUBLE PRECISION,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY(symbol, expiry, timeframe, bucket_time)
);

SELECT create_hypertable('fo_expiry_metrics', 'bucket_time', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_fo_expiry_symbol_tf ON fo_expiry_metrics (symbol, timeframe, bucket_time DESC);

ALTER TABLE fo_expiry_metrics
    SET (timescaledb.compress = TRUE,
         timescaledb.compress_segmentby = 'symbol,expiry,timeframe');

DO $$
BEGIN
    BEGIN
        PERFORM add_compression_policy('fo_expiry_metrics', INTERVAL '2 days');
    EXCEPTION
        WHEN duplicate_object THEN
            RAISE NOTICE 'Compression policy for fo_expiry_metrics already exists';
    END;
END$$;

DO $$
BEGIN
    BEGIN
        PERFORM add_retention_policy('fo_expiry_metrics', INTERVAL '30 days');
    EXCEPTION
        WHEN duplicate_object THEN
            RAISE NOTICE 'Retention policy for fo_expiry_metrics already exists';
    END;
END$$;

CREATE OR REPLACE FUNCTION fo_compute_max_pain(
    strikes DOUBLE PRECISION[],
    call_volumes DOUBLE PRECISION[],
    put_volumes DOUBLE PRECISION[]
)
RETURNS DOUBLE PRECISION
LANGUAGE plpgsql
AS $$
DECLARE
    strike_count INTEGER;
    i INTEGER;
    j INTEGER;
    candidate DOUBLE PRECISION;
    candidate_loss DOUBLE PRECISION;
    best_loss DOUBLE PRECISION := NULL;
    best_strike DOUBLE PRECISION := NULL;
BEGIN
    strike_count := COALESCE(array_length(strikes, 1), 0);
    IF strike_count = 0 THEN
        RETURN NULL;
    END IF;

    FOR i IN 1..strike_count LOOP
        candidate := strikes[i];
        candidate_loss := 0;
        FOR j IN 1..strike_count LOOP
            candidate_loss := candidate_loss
                + GREATEST(0, strikes[j] - candidate) * COALESCE(call_volumes[j], 0)
                + GREATEST(0, candidate - strikes[j]) * COALESCE(put_volumes[j], 0);
        END LOOP;

        IF best_loss IS NULL OR candidate_loss < best_loss THEN
            best_loss := candidate_loss;
            best_strike := candidate;
        END IF;
    END LOOP;

    RETURN best_strike;
END;
$$;

CREATE MATERIALIZED VIEW IF NOT EXISTS fo_option_strike_bars_5min
WITH (timescaledb.continuous, timescaledb.create_group_indexes = FALSE) AS
SELECT
    time_bucket('5 minutes', bucket_time) AS bucket_time,
    '5min'::TEXT AS timeframe,
    symbol,
    expiry,
    strike,
    AVG(underlying_close) AS underlying_close,
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
    SUM(call_volume) AS call_volume,
    SUM(put_volume) AS put_volume,
    SUM(call_count) AS call_count,
    SUM(put_count) AS put_count,
    MIN(created_at) AS created_at,
    MAX(updated_at) AS updated_at
FROM fo_option_strike_bars
WHERE timeframe = '1min'
GROUP BY 1,3,4,5;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM timescaledb_information.jobs
        WHERE hypertable_name = 'fo_option_strike_bars_5min'
          AND proc_name = 'policy_refresh_continuous_aggregate'
    ) THEN
        PERFORM add_continuous_aggregate_policy(
            'fo_option_strike_bars_5min',
            start_offset => INTERVAL '2 hours',
            end_offset => INTERVAL '1 minute',
            schedule_interval => INTERVAL '1 minute'
        );
    END IF;
END$$;

CREATE MATERIALIZED VIEW IF NOT EXISTS fo_option_strike_bars_15min
WITH (timescaledb.continuous, timescaledb.create_group_indexes = FALSE) AS
SELECT
    time_bucket('15 minutes', bucket_time) AS bucket_time,
    '15min'::TEXT AS timeframe,
    symbol,
    expiry,
    strike,
    AVG(underlying_close) AS underlying_close,
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
    SUM(call_volume) AS call_volume,
    SUM(put_volume) AS put_volume,
    SUM(call_count) AS call_count,
    SUM(put_count) AS put_count,
    MIN(created_at) AS created_at,
    MAX(updated_at) AS updated_at
FROM fo_option_strike_bars
WHERE timeframe = '1min'
GROUP BY 1,3,4,5;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM timescaledb_information.jobs
        WHERE hypertable_name = 'fo_option_strike_bars_15min'
          AND proc_name = 'policy_refresh_continuous_aggregate'
    ) THEN
        PERFORM add_continuous_aggregate_policy(
            'fo_option_strike_bars_15min',
            start_offset => INTERVAL '6 hours',
            end_offset => INTERVAL '1 minute',
            schedule_interval => INTERVAL '5 minutes'
        );
    END IF;
END$$;

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
