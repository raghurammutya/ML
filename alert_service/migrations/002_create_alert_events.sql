-- Migration 002: Create Alert Events Table (TimescaleDB Hypertable)
-- Date: 2025-11-01
-- Purpose: Store alert trigger history for analytics and audit

-- Alert events table (will be converted to hypertable)
CREATE TABLE IF NOT EXISTS alert_events (
    event_id UUID DEFAULT gen_random_uuid(),
    alert_id UUID NOT NULL REFERENCES alerts(alert_id) ON DELETE CASCADE,

    -- Event details
    triggered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status VARCHAR(20) NOT NULL DEFAULT 'triggered',

    -- Trigger context
    trigger_value JSONB,
    evaluation_result JSONB,

    -- Notification tracking
    notification_sent BOOLEAN DEFAULT false,
    notification_channels TEXT[],
    notification_ids JSONB,

    -- User actions
    acknowledged_at TIMESTAMPTZ,
    acknowledged_by VARCHAR(100),
    snoozed_until TIMESTAMPTZ,
    resolved_at TIMESTAMPTZ,
    resolved_by VARCHAR(100),

    -- Metadata
    metadata JSONB,

    -- Primary key (composite for hypertable)
    PRIMARY KEY (event_id, triggered_at),

    -- Constraints
    CONSTRAINT valid_event_status CHECK (status IN ('triggered', 'acknowledged', 'snoozed', 'resolved'))
);

-- Convert to TimescaleDB hypertable (7-day chunks)
SELECT create_hypertable(
    'alert_events',
    'triggered_at',
    if_not_exists => TRUE,
    chunk_time_interval => INTERVAL '7 days'
);

-- Indexes for performance
CREATE INDEX idx_alert_events_alert_id ON alert_events(alert_id, triggered_at DESC);
CREATE INDEX idx_alert_events_status ON alert_events(status, triggered_at DESC);

-- Composite index for user queries (requires join with alerts table)
CREATE INDEX idx_alert_events_notification_sent ON alert_events(notification_sent, triggered_at DESC)
    WHERE notification_sent = false;

-- GIN index for JSONB fields
CREATE INDEX idx_alert_events_trigger_value ON alert_events USING GIN (trigger_value);
CREATE INDEX idx_alert_events_evaluation_result ON alert_events USING GIN (evaluation_result);

-- Retention policy: Keep events for 6 months
SELECT add_retention_policy(
    'alert_events',
    INTERVAL '180 days',
    if_not_exists => TRUE
);

-- Comments
COMMENT ON TABLE alert_events IS 'Alert trigger history (TimescaleDB hypertable)';
COMMENT ON COLUMN alert_events.event_id IS 'Unique event identifier';
COMMENT ON COLUMN alert_events.alert_id IS 'Reference to parent alert';
COMMENT ON COLUMN alert_events.trigger_value IS 'Actual values that triggered the alert (e.g., {current_price: 24150, threshold: 24000})';
COMMENT ON COLUMN alert_events.evaluation_result IS 'Full evaluation context for debugging';
COMMENT ON COLUMN alert_events.notification_ids IS 'Channel-specific message IDs (e.g., {telegram: "12345", fcm: "abc"})';
COMMENT ON COLUMN alert_events.status IS 'Event lifecycle: triggered -> acknowledged/snoozed -> resolved';

-- Verify hypertable creation
SELECT * FROM timescaledb_information.hypertables WHERE hypertable_name = 'alert_events';

-- Show table structure
\d alert_events
