-- Migration 000: Verify TimescaleDB Extension
-- Date: 2025-11-01
-- Purpose: Ensure TimescaleDB extension is installed before creating hypertables

-- Check if TimescaleDB extension exists
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_extension WHERE extname = 'timescaledb'
    ) THEN
        RAISE NOTICE 'TimescaleDB extension not found. Creating it now...';
        CREATE EXTENSION IF NOT EXISTS timescaledb;
        RAISE NOTICE 'TimescaleDB extension created successfully.';
    ELSE
        RAISE NOTICE 'TimescaleDB extension already exists.';
    END IF;
END
$$;

-- Verify extension
SELECT * FROM pg_extension WHERE extname = 'timescaledb';

-- Show TimescaleDB version
SELECT extversion FROM pg_extension WHERE extname = 'timescaledb';

-- Verify database is ready
SELECT 'Database is ready for alert_service migrations' AS status;
