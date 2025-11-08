-- Development environment database initialization
-- This script creates a subset of production data for development

-- Create extension
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Create tables (same structure as production)
CREATE TABLE IF NOT EXISTS nifty50_ohlc (
    timestamp TIMESTAMPTZ NOT NULL,
    open DECIMAL(10,2) NOT NULL,
    high DECIMAL(10,2) NOT NULL,
    low DECIMAL(10,2) NOT NULL,
    close DECIMAL(10,2) NOT NULL,
    volume BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ml_labeled_data (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,
    symbol VARCHAR(20) NOT NULL DEFAULT 'NIFTY50',
    prediction INTEGER NOT NULL CHECK (prediction IN (-1, 0, 1)),
    confidence DECIMAL(5,4) NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    model_version VARCHAR(50) NOT NULL,
    features JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Convert to hypertables
SELECT create_hypertable('nifty50_ohlc', 'timestamp', if_not_exists => TRUE);
SELECT create_hypertable('ml_labeled_data', 'timestamp', if_not_exists => TRUE);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_nifty50_ohlc_timestamp ON nifty50_ohlc (timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_ml_labeled_data_timestamp ON ml_labeled_data (timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_ml_labeled_data_symbol ON ml_labeled_data (symbol, timestamp DESC);

-- Create continuous aggregates for different timeframes
CREATE MATERIALIZED VIEW IF NOT EXISTS nifty50_5min
WITH (timescaledb.continuous) AS
SELECT 
    time_bucket('5 minutes', timestamp) AS bucket,
    first(open, timestamp) AS open,
    max(high) AS high,
    min(low) AS low,
    last(close, timestamp) AS close,
    sum(volume) AS volume
FROM nifty50_ohlc
GROUP BY bucket
WITH NO DATA;

CREATE MATERIALIZED VIEW IF NOT EXISTS nifty50_15min
WITH (timescaledb.continuous) AS
SELECT 
    time_bucket('15 minutes', timestamp) AS bucket,
    first(open, timestamp) AS open,
    max(high) AS high,
    min(low) AS low,
    last(close, timestamp) AS close,
    sum(volume) AS volume
FROM nifty50_ohlc
GROUP BY bucket
WITH NO DATA;

CREATE MATERIALIZED VIEW IF NOT EXISTS nifty50_daily
WITH (timescaledb.continuous) AS
SELECT 
    time_bucket('1 day', timestamp) AS bucket,
    first(open, timestamp) AS open,
    max(high) AS high,
    min(low) AS low,
    last(close, timestamp) AS close,
    sum(volume) AS volume
FROM nifty50_ohlc
GROUP BY bucket
WITH NO DATA;

-- Add refresh policies
SELECT add_continuous_aggregate_policy('nifty50_5min',
    start_offset => INTERVAL '1 hour',
    end_offset => INTERVAL '5 minutes',
    schedule_interval => INTERVAL '5 minutes',
    if_not_exists => TRUE);

SELECT add_continuous_aggregate_policy('nifty50_15min',
    start_offset => INTERVAL '3 hours',
    end_offset => INTERVAL '15 minutes',
    schedule_interval => INTERVAL '15 minutes',
    if_not_exists => TRUE);

SELECT add_continuous_aggregate_policy('nifty50_daily',
    start_offset => INTERVAL '7 days',
    end_offset => INTERVAL '1 day',
    schedule_interval => INTERVAL '1 hour',
    if_not_exists => TRUE);

-- Insert sample data for development (last 3 months)
-- This would be populated by your data migration script
INSERT INTO nifty50_ohlc (timestamp, open, high, low, close, volume)
SELECT 
    generate_series(
        NOW() - INTERVAL '3 months',
        NOW(),
        INTERVAL '1 minute'
    ) AS timestamp,
    22000 + (random() * 2000 - 1000) AS open,
    22000 + (random() * 2000 - 1000) + (random() * 100) AS high,
    22000 + (random() * 2000 - 1000) - (random() * 100) AS low,
    22000 + (random() * 2000 - 1000) AS close,
    (random() * 1000000)::BIGINT AS volume
WHERE EXTRACT(DOW FROM generate_series(
        NOW() - INTERVAL '3 months',
        NOW(),
        INTERVAL '1 minute'
    )) NOT IN (0, 6) -- Exclude weekends
    AND EXTRACT(HOUR FROM generate_series(
        NOW() - INTERVAL '3 months',
        NOW(),
        INTERVAL '1 minute'
    )) BETWEEN 9 AND 15; -- Market hours only

-- Create user for application
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'app_user') THEN
        CREATE ROLE app_user WITH LOGIN PASSWORD 'app_password_dev';
    END IF;
END
$$;

-- Grant permissions
GRANT CONNECT ON DATABASE stocksblitz_unified TO app_user;
GRANT USAGE ON SCHEMA public TO app_user;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO app_user;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app_user;