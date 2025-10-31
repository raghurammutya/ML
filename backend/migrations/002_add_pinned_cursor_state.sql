-- Migration 002: Add pinned cursor state support to ml_labels
-- This migration ensures the metadata JSONB field can store pinnedCursorState

-- The metadata field is already JSONB, so we just need to update any existing
-- labels to ensure they have the proper structure

-- Add comment to document the pinnedCursorState field structure
COMMENT ON COLUMN ml_labels.metadata IS 'JSONB metadata including timeframe, nearest_candle_timestamp_utc, sample_offset_seconds, price, and optional pinnedCursorState with fields: cursorUtc, timeframe, playbackSpeed, isFollowingMain, windowStartUtc, windowEndUtc';

-- Create an index for efficient queries on pinnedCursorState
CREATE INDEX IF NOT EXISTS idx_ml_labels_pinned_cursor 
ON ml_labels USING GIN ((metadata->'pinnedCursorState')) 
WHERE metadata ? 'pinnedCursorState';

-- Add a check constraint to ensure pinnedCursorState has valid structure when present
ALTER TABLE ml_labels 
ADD CONSTRAINT chk_pinned_cursor_state 
CHECK (
    metadata->'pinnedCursorState' IS NULL OR 
    (
        jsonb_typeof(metadata->'pinnedCursorState') = 'object' AND
        metadata->'pinnedCursorState' ? 'cursorUtc' AND
        metadata->'pinnedCursorState' ? 'timeframe' AND
        metadata->'pinnedCursorState' ? 'playbackSpeed' AND
        metadata->'pinnedCursorState' ? 'isFollowingMain'
    )
);

-- Update any existing labels that might not have the complete metadata structure
UPDATE ml_labels 
SET metadata = metadata || jsonb_build_object('pinnedCursorState', null)
WHERE NOT (metadata ? 'pinnedCursorState');

-- Create partial index for labels with pinned cursors for faster lookups
CREATE INDEX IF NOT EXISTS idx_ml_labels_with_pinned_cursor 
ON ml_labels (symbol, (metadata->>'timeframe'), created_at)
WHERE metadata->'pinnedCursorState' IS NOT NULL;

-- Log migration completion
INSERT INTO schema_migrations (version, applied_at) 
VALUES ('002', NOW()) 
ON CONFLICT (version) DO UPDATE SET applied_at = NOW();