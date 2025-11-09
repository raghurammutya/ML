-- Migration: Create order_cleanup_log table
-- Purpose: Audit log for automatic order cleanup actions
-- Created: 2025-11-09

-- Create order_cleanup_log table
CREATE TABLE IF NOT EXISTS order_cleanup_log (
    id BIGSERIAL PRIMARY KEY,

    -- Order identification
    order_id VARCHAR(100) NOT NULL,
    account_id VARCHAR(100) NOT NULL,
    strategy_id BIGINT,  -- NULL for manual orders

    -- Order details
    tradingsymbol VARCHAR(100),
    exchange VARCHAR(20),
    order_type VARCHAR(20),  -- SL, SL-M, LIMIT, etc.

    -- Cleanup details
    cleanup_reason VARCHAR(50),  -- position_closed, position_reduced, stale_order
    cleanup_action VARCHAR(20),  -- cancelled, skipped, failed
    was_auto BOOLEAN DEFAULT TRUE,  -- TRUE = auto cleanup, FALSE = manual/skipped

    -- Position state at cleanup time
    position_quantity_before INTEGER,  -- Position quantity before change
    position_quantity_after INTEGER,   -- Position quantity after change

    -- Timestamps
    cleaned_at TIMESTAMPTZ DEFAULT NOW(),

    -- Additional context (JSON)
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Create indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_cleanup_log_order ON order_cleanup_log(order_id);
CREATE INDEX IF NOT EXISTS idx_cleanup_log_account ON order_cleanup_log(account_id);
CREATE INDEX IF NOT EXISTS idx_cleanup_log_strategy ON order_cleanup_log(strategy_id) WHERE strategy_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_cleanup_log_cleaned_at ON order_cleanup_log(cleaned_at DESC);
CREATE INDEX IF NOT EXISTS idx_cleanup_log_reason ON order_cleanup_log(cleanup_reason);
CREATE INDEX IF NOT EXISTS idx_cleanup_log_action ON order_cleanup_log(cleanup_action);

-- Create index on metadata for JSON queries (e.g., filter by event_type)
CREATE INDEX IF NOT EXISTS idx_cleanup_log_metadata_gin ON order_cleanup_log USING gin(metadata);

-- Add comment
COMMENT ON TABLE order_cleanup_log IS 'Audit log for automatic order cleanup actions triggered by position changes';
COMMENT ON COLUMN order_cleanup_log.cleanup_reason IS 'Why cleanup was triggered: position_closed, position_reduced, stale_order';
COMMENT ON COLUMN order_cleanup_log.cleanup_action IS 'What action was taken: cancelled, skipped, failed';
COMMENT ON COLUMN order_cleanup_log.was_auto IS 'TRUE if auto-cleanup based on strategy settings, FALSE if skipped/manual';
COMMENT ON COLUMN order_cleanup_log.metadata IS 'Additional context: event_type, product, order_status, order_quantity';
