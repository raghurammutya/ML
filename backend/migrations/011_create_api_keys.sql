-- Migration 011: API Key Authentication System
-- Date: 2025-10-31
-- Purpose: Create API key system for algo trading authentication

-- API Keys table
CREATE TABLE IF NOT EXISTS api_keys (
    key_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key_hash VARCHAR(64) NOT NULL UNIQUE,  -- SHA-256 hash of API key
    key_prefix VARCHAR(8) NOT NULL,         -- First 8 chars for identification
    user_id VARCHAR(255) NOT NULL,
    strategy_id UUID,                       -- Optional: link to strategy
    name VARCHAR(255) NOT NULL,             -- Friendly name for key
    description TEXT,

    -- Permissions
    permissions JSONB DEFAULT '{"can_trade": false, "can_cancel": false, "can_read": true}'::jsonb,

    -- Rate limiting
    rate_limit_orders_per_sec INT DEFAULT 10,
    rate_limit_requests_per_min INT DEFAULT 200,

    -- Security
    ip_whitelist TEXT[],                    -- Allowed IPs (empty = allow all)
    allowed_accounts TEXT[],                -- Allowed trading accounts (empty = allow all)

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ,
    last_used_at TIMESTAMPTZ,
    is_active BOOLEAN DEFAULT true,

    -- Audit
    created_by VARCHAR(255),
    revoked_at TIMESTAMPTZ,
    revoked_by VARCHAR(255),
    revoke_reason TEXT
);

-- Indexes
CREATE INDEX idx_api_keys_user_id ON api_keys(user_id);
CREATE INDEX idx_api_keys_is_active ON api_keys(is_active) WHERE is_active = true;
CREATE INDEX idx_api_keys_expires_at ON api_keys(expires_at) WHERE expires_at IS NOT NULL;
CREATE INDEX idx_api_keys_key_prefix ON api_keys(key_prefix);

-- API Key Usage Logs (for audit trail)
CREATE TABLE IF NOT EXISTS api_key_usage (
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    key_id UUID NOT NULL REFERENCES api_keys(key_id) ON DELETE CASCADE,
    endpoint TEXT NOT NULL,
    method TEXT NOT NULL,
    ip_address INET,
    user_agent TEXT,
    status_code INT,
    response_time_ms FLOAT,
    error_message TEXT
);

-- Hypertable for time-series data (TimescaleDB)
SELECT create_hypertable('api_key_usage', 'timestamp', if_not_exists => TRUE, chunk_time_interval => INTERVAL '1 day');

-- Index for fast lookups
CREATE INDEX idx_api_key_usage_key_id ON api_key_usage(key_id, timestamp DESC);
CREATE INDEX idx_api_key_usage_timestamp ON api_key_usage(timestamp DESC);

-- Retention policy: Keep usage logs for 90 days
SELECT add_retention_policy('api_key_usage', INTERVAL '90 days', if_not_exists => TRUE);

-- Comments
COMMENT ON TABLE api_keys IS 'API keys for algo trading authentication';
COMMENT ON COLUMN api_keys.key_hash IS 'SHA-256 hash of the API key (never store plain text)';
COMMENT ON COLUMN api_keys.key_prefix IS 'First 8 characters of key for identification';
COMMENT ON COLUMN api_keys.permissions IS 'JSONB permissions: can_trade, can_cancel, can_read, can_modify';
COMMENT ON COLUMN api_keys.rate_limit_orders_per_sec IS 'Max orders per second (default 10 for Zerodha)';
COMMENT ON COLUMN api_keys.ip_whitelist IS 'Array of allowed IP addresses (empty = allow all)';

COMMENT ON TABLE api_key_usage IS 'Audit log of API key usage';

-- Sample data (for testing)
-- Generate a test API key: sb_test_12345678_abcdefghijklmnopqrstuvwxyz
-- SHA-256 hash: (use Python: hashlib.sha256(b'sb_test_12345678_abcdefghijklmnopqrstuvwxyz').hexdigest())
INSERT INTO api_keys (
    key_hash,
    key_prefix,
    user_id,
    name,
    description,
    permissions,
    rate_limit_orders_per_sec,
    rate_limit_requests_per_min,
    is_active
) VALUES (
    'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',  -- Replace with actual hash
    'sb_test_',
    'test_user',
    'Test API Key',
    'Development testing key with full permissions',
    '{"can_trade": true, "can_cancel": true, "can_read": true, "can_modify": true}'::jsonb,
    10,
    200,
    false  -- Disabled by default for safety
) ON CONFLICT DO NOTHING;

-- Verify
SELECT
    key_prefix,
    user_id,
    name,
    permissions,
    is_active,
    created_at
FROM api_keys
ORDER BY created_at;

-- Show table structure
\d api_keys
\d api_key_usage
