-- Migration 003: Create Notification Preferences and Log Tables
-- Date: 2025-11-01
-- Purpose: User notification settings and delivery tracking

-- Notification preferences table
CREATE TABLE IF NOT EXISTS notification_preferences (
    user_id VARCHAR(100) PRIMARY KEY,

    -- Channel configurations
    telegram_enabled BOOLEAN DEFAULT false,
    telegram_chat_id VARCHAR(100),
    telegram_bot_token VARCHAR(255),

    fcm_enabled BOOLEAN DEFAULT false,
    fcm_device_tokens TEXT[],

    email_enabled BOOLEAN DEFAULT false,
    email_addresses TEXT[],

    -- Global settings
    quiet_hours_start TIME,
    quiet_hours_end TIME,
    quiet_hours_timezone VARCHAR(50) DEFAULT 'Asia/Kolkata',

    max_notifications_per_hour INT DEFAULT 50,
    priority_threshold VARCHAR(20) DEFAULT 'low',

    -- Preferences
    notification_format VARCHAR(20) DEFAULT 'rich',
    include_chart_images BOOLEAN DEFAULT false,

    -- Lifecycle
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Audit
    metadata JSONB,

    -- Constraints
    CONSTRAINT valid_priority_threshold CHECK (priority_threshold IN ('low', 'medium', 'high', 'critical')),
    CONSTRAINT valid_notification_format CHECK (notification_format IN ('rich', 'compact', 'minimal'))
);

-- Indexes
CREATE INDEX idx_notif_prefs_telegram ON notification_preferences(telegram_chat_id)
    WHERE telegram_enabled = true;
CREATE INDEX idx_notif_prefs_fcm ON notification_preferences(fcm_device_tokens)
    WHERE fcm_enabled = true USING GIN;

-- Comments
COMMENT ON TABLE notification_preferences IS 'User-specific notification preferences and channel configurations';
COMMENT ON COLUMN notification_preferences.telegram_chat_id IS 'Telegram chat ID obtained during bot setup';
COMMENT ON COLUMN notification_preferences.quiet_hours_start IS 'Do-not-disturb window start (only send priority >= priority_threshold)';
COMMENT ON COLUMN notification_preferences.max_notifications_per_hour IS 'Rate limit per user (default: 50)';
COMMENT ON COLUMN notification_preferences.priority_threshold IS 'During quiet hours, only send alerts >= this priority';
COMMENT ON COLUMN notification_preferences.notification_format IS 'Message style: rich (detailed), compact (brief), minimal (terse)';

-- Trigger to update updated_at
CREATE OR REPLACE FUNCTION update_notification_preferences_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_notification_preferences_updated_at
    BEFORE UPDATE ON notification_preferences
    FOR EACH ROW
    EXECUTE FUNCTION update_notification_preferences_updated_at();

-- Notification log table (TimescaleDB hypertable)
CREATE TABLE IF NOT EXISTS notification_log (
    log_id UUID DEFAULT gen_random_uuid(),
    event_id UUID NOT NULL,  -- References alert_events.event_id

    -- Notification details
    sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    channel VARCHAR(50) NOT NULL,
    recipient VARCHAR(255) NOT NULL,

    -- Delivery status
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    status_code INT,
    error_message TEXT,

    -- Content
    message_id VARCHAR(255),
    message_content TEXT,
    message_metadata JSONB,

    -- Tracking
    delivered_at TIMESTAMPTZ,
    read_at TIMESTAMPTZ,
    clicked BOOLEAN DEFAULT false,

    -- Primary key (composite for hypertable)
    PRIMARY KEY (log_id, sent_at),

    -- Constraints
    CONSTRAINT valid_channel CHECK (channel IN ('telegram', 'fcm', 'apns', 'email', 'sms', 'webhook')),
    CONSTRAINT valid_notification_status CHECK (status IN ('pending', 'sent', 'delivered', 'failed', 'read'))
);

-- Convert to TimescaleDB hypertable (7-day chunks)
SELECT create_hypertable(
    'notification_log',
    'sent_at',
    if_not_exists => TRUE,
    chunk_time_interval => INTERVAL '7 days'
);

-- Indexes for performance
CREATE INDEX idx_notif_log_event_id ON notification_log(event_id, sent_at DESC);
CREATE INDEX idx_notif_log_status ON notification_log(status, sent_at DESC)
    WHERE status IN ('pending', 'failed');
CREATE INDEX idx_notif_log_channel ON notification_log(channel, sent_at DESC);
CREATE INDEX idx_notif_log_recipient ON notification_log(recipient, sent_at DESC);

-- Retention policy: Keep logs for 90 days
SELECT add_retention_policy(
    'notification_log',
    INTERVAL '90 days',
    if_not_exists => TRUE
);

-- Comments
COMMENT ON TABLE notification_log IS 'Notification delivery tracking (TimescaleDB hypertable)';
COMMENT ON COLUMN notification_log.event_id IS 'Reference to alert event that triggered notification';
COMMENT ON COLUMN notification_log.channel IS 'Delivery channel: telegram, fcm, apns, email, sms, webhook';
COMMENT ON COLUMN notification_log.recipient IS 'Channel-specific recipient (chat_id, device_token, email)';
COMMENT ON COLUMN notification_log.message_id IS 'Provider-specific message ID for tracking';
COMMENT ON COLUMN notification_log.status IS 'Delivery status: pending -> sent -> delivered -> read (or failed)';

-- Verify hypertable creation
SELECT * FROM timescaledb_information.hypertables WHERE hypertable_name = 'notification_log';

-- Show table structure
\d notification_preferences
\d notification_log
