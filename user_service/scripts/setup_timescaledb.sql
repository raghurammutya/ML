-- Setup TimescaleDB hypertable for auth_events
-- This script should be run after the initial migration

-- Enable TimescaleDB extension (if not already enabled)
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Convert auth_events to hypertable
-- Chunk by timestamp with 7-day intervals
SELECT create_hypertable(
    'auth_events',
    'timestamp',
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists => TRUE
);

-- Add retention policy (keep 2 years of audit data)
SELECT add_retention_policy(
    'auth_events',
    INTERVAL '2 years',
    if_not_exists => TRUE
);

-- Create continuous aggregate for daily auth events
CREATE MATERIALIZED VIEW IF NOT EXISTS auth_events_daily
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 day', timestamp) AS day,
    user_id,
    event_type,
    COUNT(*) AS event_count,
    COUNT(*) FILTER (WHERE event_type LIKE 'login.success') AS login_success_count,
    COUNT(*) FILTER (WHERE event_type LIKE 'login.failed') AS login_failed_count,
    COUNT(*) FILTER (WHERE risk_score = 'high') AS high_risk_count
FROM auth_events
GROUP BY day, user_id, event_type
WITH NO DATA;

-- Add refresh policy for continuous aggregate
SELECT add_continuous_aggregate_policy(
    'auth_events_daily',
    start_offset => INTERVAL '3 days',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour',
    if_not_exists => TRUE
);

-- Refresh the continuous aggregate with existing data
CALL refresh_continuous_aggregate('auth_events_daily', NULL, NULL);

COMMENT ON TABLE auth_events IS 'Audit log for authentication events - TimescaleDB hypertable';
COMMENT ON MATERIALIZED VIEW auth_events_daily IS 'Daily aggregates of authentication events';
