-- Migration: Create order_cost_breakdown table
-- Purpose: Store complete cost breakdown for orders (brokerage, taxes, charges)
-- Created: 2025-11-09

-- Create order_cost_breakdown table
CREATE TABLE IF NOT EXISTS order_cost_breakdown (
    id BIGSERIAL PRIMARY KEY,
    order_id BIGINT REFERENCES orders(id) ON DELETE SET NULL,
    strategy_id BIGINT REFERENCES strategies(id) ON DELETE CASCADE,

    -- Order details
    order_value DECIMAL(20, 2) NOT NULL,
    quantity INTEGER NOT NULL,
    price DECIMAL(20, 8) NOT NULL,
    side VARCHAR(10) NOT NULL,  -- BUY, SELL
    segment VARCHAR(20) NOT NULL,  -- equity, futures, options

    -- Cost breakdown
    brokerage DECIMAL(20, 2) DEFAULT 0,
    stt DECIMAL(20, 2) DEFAULT 0,  -- Securities Transaction Tax
    exchange_charges DECIMAL(20, 2) DEFAULT 0,
    gst DECIMAL(20, 2) DEFAULT 0,  -- 18% on brokerage + exchange charges
    sebi_charges DECIMAL(20, 2) DEFAULT 0,  -- ₹10 per crore
    stamp_duty DECIMAL(20, 2) DEFAULT 0,  -- 0.002% on buy side
    total_charges DECIMAL(20, 2) DEFAULT 0,
    net_cost DECIMAL(20, 2) DEFAULT 0,  -- order_value + total_charges (BUY) or - total_charges (SELL)

    -- Margin (if applicable for F&O)
    margin_required DECIMAL(20, 2),
    span_margin DECIMAL(20, 2),
    exposure_margin DECIMAL(20, 2),
    premium_margin DECIMAL(20, 2),  -- For option selling

    -- Metadata
    calculated_at TIMESTAMPTZ DEFAULT NOW(),
    broker VARCHAR(50) DEFAULT 'zerodha',  -- For multi-broker support later

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_order_cost_order_id ON order_cost_breakdown(order_id);
CREATE INDEX IF NOT EXISTS idx_order_cost_strategy_id ON order_cost_breakdown(strategy_id);
CREATE INDEX IF NOT EXISTS idx_order_cost_calculated_at ON order_cost_breakdown(calculated_at);
CREATE INDEX IF NOT EXISTS idx_order_cost_segment ON order_cost_breakdown(segment);

-- Add comments
COMMENT ON TABLE order_cost_breakdown IS 'Complete cost breakdown for orders including brokerage, taxes, and margins';
COMMENT ON COLUMN order_cost_breakdown.brokerage IS 'Brokerage charges (Zerodha: ₹20 flat for options, 0.03% for futures/equity)';
COMMENT ON COLUMN order_cost_breakdown.stt IS 'Securities Transaction Tax (varies by segment and side)';
COMMENT ON COLUMN order_cost_breakdown.gst IS '18% GST on brokerage + exchange charges';
COMMENT ON COLUMN order_cost_breakdown.sebi_charges IS 'SEBI charges: ₹10 per crore turnover';
COMMENT ON COLUMN order_cost_breakdown.stamp_duty IS 'Stamp duty: 0.002% on buy side for F&O';
