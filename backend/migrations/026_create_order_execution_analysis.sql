-- Migration: Create order_execution_analysis table
-- Purpose: Store pre-execution market depth analysis for smart order execution
-- Created: 2025-11-09

-- Create order_execution_analysis table
CREATE TABLE IF NOT EXISTS order_execution_analysis (
    id BIGSERIAL PRIMARY KEY,
    order_id BIGINT REFERENCES orders(id) ON DELETE SET NULL,
    strategy_id BIGINT REFERENCES strategies(id) ON DELETE CASCADE,

    -- Pre-execution analysis
    analyzed_at TIMESTAMPTZ DEFAULT NOW(),
    bid_ask_spread_abs DECIMAL(20, 8),
    bid_ask_spread_pct DECIMAL(10, 4),
    liquidity_tier VARCHAR(20),  -- HIGH, MEDIUM, LOW, ILLIQUID
    liquidity_score INTEGER,  -- 0-100

    -- Market impact estimation
    estimated_fill_price DECIMAL(20, 8),
    market_impact_bps INTEGER,  -- Basis points
    market_impact_cost DECIMAL(20, 2),  -- Absolute cost in rupees
    levels_to_consume INTEGER,  -- How many price levels needed
    can_fill_completely BOOLEAN,

    -- Execution decision
    recommended_action VARCHAR(50),  -- EXECUTE, ALERT_USER, REJECT
    recommended_order_type VARCHAR(20),  -- MARKET, LIMIT, ICEBERG, TWAP
    warnings JSONB DEFAULT '[]'::jsonb,  -- List of warnings

    -- Actual execution results (filled after order execution)
    actual_fill_price DECIMAL(20, 8),
    actual_slippage DECIMAL(20, 8),
    execution_quality_score INTEGER,  -- 0-100, how well did we execute

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_order_exec_analysis_order_id ON order_execution_analysis(order_id);
CREATE INDEX IF NOT EXISTS idx_order_exec_analysis_strategy_id ON order_execution_analysis(strategy_id);
CREATE INDEX IF NOT EXISTS idx_order_exec_analysis_analyzed_at ON order_execution_analysis(analyzed_at);
CREATE INDEX IF NOT EXISTS idx_order_exec_analysis_liquidity_tier ON order_execution_analysis(liquidity_tier);

-- Add comment
COMMENT ON TABLE order_execution_analysis IS 'Pre-execution market depth analysis and post-execution quality metrics';
COMMENT ON COLUMN order_execution_analysis.bid_ask_spread_pct IS 'Spread as percentage at time of analysis';
COMMENT ON COLUMN order_execution_analysis.market_impact_bps IS 'Estimated market impact in basis points';
COMMENT ON COLUMN order_execution_analysis.execution_quality_score IS 'Post-execution quality score (0-100)';
