-- Migration 001: Create Alerts Table
-- Date: 2025-11-01
-- Purpose: Create alert system for real-time trading notifications

-- Main alerts table
CREATE TABLE IF NOT EXISTS alerts (
    alert_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Ownership (future-proof for user_service)
    user_id VARCHAR(100) NOT NULL,
    account_id VARCHAR(100),
    strategy_id UUID,

    -- Alert metadata
    name VARCHAR(255) NOT NULL,
    description TEXT,
    alert_type VARCHAR(50) NOT NULL,
    priority VARCHAR(20) NOT NULL DEFAULT 'medium',

    -- Condition specification
    condition_type VARCHAR(50) NOT NULL,
    condition_config JSONB NOT NULL,

    -- Scope
    symbol VARCHAR(50),
    symbols TEXT[],
    exchange VARCHAR(10),

    -- Notification configuration
    notification_channels TEXT[] NOT NULL DEFAULT ARRAY['telegram'],
    notification_config JSONB,
    notification_template TEXT,

    -- State
    status VARCHAR(20) NOT NULL DEFAULT 'active',

    -- Evaluation settings
    evaluation_interval_seconds INT DEFAULT 60,
    evaluation_window_start TIME,
    evaluation_window_end TIME,
    max_triggers_per_day INT,
    cooldown_seconds INT DEFAULT 300,

    -- Trigger tracking
    trigger_count INT DEFAULT 0,
    last_triggered_at TIMESTAMPTZ,
    last_evaluated_at TIMESTAMPTZ,
    evaluation_count BIGINT DEFAULT 0,

    -- Lifecycle
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ,
    created_by VARCHAR(100),

    -- Audit
    metadata JSONB,

    -- Constraints
    CONSTRAINT valid_priority CHECK (priority IN ('low', 'medium', 'high', 'critical')),
    CONSTRAINT valid_status CHECK (status IN ('active', 'paused', 'triggered', 'expired', 'deleted')),
    CONSTRAINT valid_alert_type CHECK (alert_type IN ('price', 'indicator', 'position', 'greek', 'order', 'time', 'custom', 'strategy')),
    CONSTRAINT valid_evaluation_interval CHECK (evaluation_interval_seconds >= 10),
    CONSTRAINT valid_cooldown CHECK (cooldown_seconds >= 0)
);

-- Indexes for performance
CREATE INDEX idx_alerts_user_id ON alerts(user_id, status) WHERE status = 'active';
CREATE INDEX idx_alerts_status ON alerts(status) WHERE status = 'active';
CREATE INDEX idx_alerts_symbol ON alerts(symbol) WHERE symbol IS NOT NULL AND status = 'active';
CREATE INDEX idx_alerts_next_eval ON alerts(last_evaluated_at) WHERE status = 'active';
CREATE INDEX idx_alerts_expires_at ON alerts(expires_at) WHERE expires_at IS NOT NULL;
CREATE INDEX idx_alerts_condition_type ON alerts(alert_type, condition_type);

-- GIN index for JSONB condition queries
CREATE INDEX idx_alerts_condition_config ON alerts USING GIN (condition_config);

-- Comments
COMMENT ON TABLE alerts IS 'User-defined alerts for market events and trading conditions';
COMMENT ON COLUMN alerts.alert_id IS 'Unique alert identifier';
COMMENT ON COLUMN alerts.user_id IS 'User identifier from API key or user_service (future)';
COMMENT ON COLUMN alerts.condition_config IS 'JSONB structure depends on condition_type. See condition schemas in design doc.';
COMMENT ON COLUMN alerts.evaluation_interval_seconds IS 'Minimum 10 seconds. Lower values increase load.';
COMMENT ON COLUMN alerts.cooldown_seconds IS 'Prevents alert spam. Minimum time between consecutive triggers.';
COMMENT ON COLUMN alerts.status IS 'Alert state: active (evaluating), paused (disabled), triggered (one-time fired), expired, deleted';

-- Trigger to update updated_at
CREATE OR REPLACE FUNCTION update_alerts_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_alerts_updated_at
    BEFORE UPDATE ON alerts
    FOR EACH ROW
    EXECUTE FUNCTION update_alerts_updated_at();

-- Verify table creation
SELECT
    schemaname,
    tablename,
    tableowner
FROM pg_tables
WHERE tablename = 'alerts';

-- Show table structure
\d alerts
