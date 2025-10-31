-- Rollback Migration: Drop enriched views for FO option strike bars
-- Date: 2025-10-31
-- Purpose: Rollback enriched views if needed
--
-- IMPORTANT: Before running this rollback:
-- 1. Ensure backend application is using base tables or non-enriched aggregates
-- 2. Update FO_STRIKE_TABLES in app/database.py to point to original tables
-- 3. Restart backend containers
--
-- To rollback the application code changes:
-- 1. Revert app/routes/fo.py _indicator_value() to return None for OI
-- 2. Redeploy backend

BEGIN;

-- Drop enriched views
DROP VIEW IF EXISTS fo_option_strike_bars_15min_enriched;
DROP VIEW IF EXISTS fo_option_strike_bars_5min_enriched;

-- Verify cleanup
DO $$
DECLARE
    view_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO view_count
    FROM information_schema.views
    WHERE table_name LIKE '%_enriched';

    IF view_count > 0 THEN
        RAISE EXCEPTION 'Rollback failed: enriched views still exist';
    END IF;

    RAISE NOTICE 'Rollback complete. All enriched views dropped successfully.';
END $$;

COMMIT;
