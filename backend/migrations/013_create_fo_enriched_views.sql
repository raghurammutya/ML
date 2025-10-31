-- Migration: Create enriched views for FO option strike bars with OI columns
-- Date: 2025-10-31
-- Purpose: Add OI columns to continuous aggregate views via LEFT JOIN with base table
--
-- Background:
-- TimescaleDB continuous aggregates (fo_option_strike_bars_5min, fo_option_strike_bars_15min)
-- were created before call_oi_sum and put_oi_sum columns were added to the base table.
-- TimescaleDB doesn't automatically include columns added after aggregate creation.
-- This migration creates enriched wrapper views that fetch OI data via LEFT JOIN.

BEGIN;

-- Create enriched view for 5min aggregates with OI columns
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

-- Create enriched view for 15min aggregates with OI columns
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

-- Grant permissions (adjust as needed for your setup)
GRANT SELECT ON fo_option_strike_bars_5min_enriched TO stocksblitz;
GRANT SELECT ON fo_option_strike_bars_15min_enriched TO stocksblitz;

COMMIT;

-- Verification queries
DO $$
DECLARE
    view5_count INTEGER;
    view15_count INTEGER;
BEGIN
    -- Check 5min enriched view
    SELECT COUNT(*) INTO view5_count
    FROM fo_option_strike_bars_5min_enriched
    WHERE call_oi_sum > 0
    LIMIT 1;

    -- Check 15min enriched view
    SELECT COUNT(*) INTO view15_count
    FROM fo_option_strike_bars_15min_enriched
    WHERE call_oi_sum > 0
    LIMIT 1;

    RAISE NOTICE 'Migration complete. 5min enriched view has % rows with OI', view5_count;
    RAISE NOTICE 'Migration complete. 15min enriched view has % rows with OI', view15_count;
END $$;
