-- Migration: Create strategy_settings table
-- Purpose: Store housekeeping, smart execution, and risk management settings per strategy
-- Created: 2025-11-09

-- Create strategy_settings table
CREATE TABLE IF NOT EXISTS strategy_settings (
    strategy_id BIGINT PRIMARY KEY REFERENCES strategies(id) ON DELETE CASCADE,

    -- Housekeeping settings
    auto_cleanup_enabled BOOLEAN DEFAULT TRUE,
    cleanup_sl_on_exit BOOLEAN DEFAULT TRUE,
    cleanup_target_on_exit BOOLEAN DEFAULT TRUE,
    cleanup_expired_instruments BOOLEAN DEFAULT TRUE,
    allow_orphaned_orders BOOLEAN DEFAULT FALSE,
    notify_on_orphan_detection BOOLEAN DEFAULT TRUE,
    auto_cancel_stale_orders BOOLEAN DEFAULT FALSE,
    stale_order_threshold_hours INTEGER DEFAULT 4,

    -- Smart execution settings
    max_order_spread_pct DECIMAL(10, 4) DEFAULT 0.5,  -- 0.5% max spread before alert
    min_liquidity_score INTEGER DEFAULT 50,  -- 0-100 scale
    require_user_approval_high_impact BOOLEAN DEFAULT TRUE,
    max_market_impact_bps INTEGER DEFAULT 50,  -- 50 basis points

    -- Margin management settings
    margin_buffer_pct DECIMAL(10, 4) DEFAULT 10.0,  -- 10% safety buffer
    check_margin_before_order BOOLEAN DEFAULT TRUE,

    -- Risk limits
    max_loss_per_strategy_pct DECIMAL(10, 4) DEFAULT 10.0,  -- 10% max loss
    max_loss_per_strategy_abs DECIMAL(20, 2),  -- Absolute loss limit (optional)
    max_position_size_per_instrument INTEGER,  -- Max lots per instrument (optional)
    max_orders_per_minute INTEGER DEFAULT 10,
    max_margin_utilization_pct DECIMAL(10, 4) DEFAULT 90.0,  -- 90% max
    auto_square_off_on_loss_limit BOOLEAN DEFAULT FALSE,

    -- Intraday settings
    is_intraday_strategy BOOLEAN DEFAULT FALSE,
    auto_square_off_time TIME DEFAULT '15:20:00',  -- 3:20 PM
    send_square_off_warning BOOLEAN DEFAULT TRUE,
    square_off_warning_time TIME DEFAULT '15:15:00',  -- 3:15 PM

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create index on created_at for performance
CREATE INDEX IF NOT EXISTS idx_strategy_settings_created_at ON strategy_settings(created_at);

-- Create trigger to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_strategy_settings_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_strategy_settings_updated_at
    BEFORE UPDATE ON strategy_settings
    FOR EACH ROW
    EXECUTE FUNCTION update_strategy_settings_updated_at();

-- Insert default settings for existing strategies
INSERT INTO strategy_settings (strategy_id)
SELECT id FROM strategies
WHERE id NOT IN (SELECT strategy_id FROM strategy_settings)
ON CONFLICT (strategy_id) DO NOTHING;

-- Add comment
COMMENT ON TABLE strategy_settings IS 'Strategy-level settings for housekeeping, smart execution, and risk management';
