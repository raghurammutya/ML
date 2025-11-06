-- Migration 021: Add Liquidity & Market Depth Metrics
-- Stores aggregated liquidity metrics for historical analysis

-- Add liquidity metrics columns
ALTER TABLE fo_option_strike_bars
ADD COLUMN IF NOT EXISTS liquidity_score_avg DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS liquidity_score_min DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS liquidity_tier VARCHAR(20),

ADD COLUMN IF NOT EXISTS spread_abs_avg DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS spread_pct_avg DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS spread_pct_max DOUBLE PRECISION,

ADD COLUMN IF NOT EXISTS depth_imbalance_pct_avg DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS book_pressure_avg DOUBLE PRECISION,

ADD COLUMN IF NOT EXISTS total_bid_quantity_avg INTEGER,
ADD COLUMN IF NOT EXISTS total_ask_quantity_avg INTEGER,
ADD COLUMN IF NOT EXISTS depth_at_best_bid_avg INTEGER,
ADD COLUMN IF NOT EXISTS depth_at_best_ask_avg INTEGER,

ADD COLUMN IF NOT EXISTS microprice_avg DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS market_impact_100_avg DOUBLE PRECISION,

ADD COLUMN IF NOT EXISTS is_illiquid BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS illiquid_tick_count INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS total_tick_count INTEGER DEFAULT 0;

-- Comments for documentation
COMMENT ON COLUMN fo_option_strike_bars.liquidity_score_avg IS 'Average liquidity score (0-100) over the bar period';
COMMENT ON COLUMN fo_option_strike_bars.liquidity_score_min IS 'Minimum liquidity score (worst case) in the bar';
COMMENT ON COLUMN fo_option_strike_bars.liquidity_tier IS 'Most frequent tier: HIGH/MEDIUM/LOW/ILLIQUID';

COMMENT ON COLUMN fo_option_strike_bars.spread_abs_avg IS 'Average absolute bid-ask spread';
COMMENT ON COLUMN fo_option_strike_bars.spread_pct_avg IS 'Average spread as % of mid-price';
COMMENT ON COLUMN fo_option_strike_bars.spread_pct_max IS 'Maximum spread % (worst case)';

COMMENT ON COLUMN fo_option_strike_bars.depth_imbalance_pct_avg IS 'Average order book imbalance %';
COMMENT ON COLUMN fo_option_strike_bars.book_pressure_avg IS 'Average book pressure [-1, 1]';

COMMENT ON COLUMN fo_option_strike_bars.is_illiquid IS 'TRUE if instrument was illiquid for >50% of bar period';
COMMENT ON COLUMN fo_option_strike_bars.illiquid_tick_count IS 'Number of ticks where liquidity_score < 40';
COMMENT ON COLUMN fo_option_strike_bars.total_tick_count IS 'Total ticks received in bar period';

-- Indexes for querying illiquid instruments
CREATE INDEX IF NOT EXISTS idx_fo_strike_illiquid
ON fo_option_strike_bars(is_illiquid, bucket_time DESC)
WHERE is_illiquid = TRUE;

CREATE INDEX IF NOT EXISTS idx_fo_strike_liquidity_score
ON fo_option_strike_bars(symbol, expiry, liquidity_score_avg)
WHERE liquidity_score_avg IS NOT NULL;

-- Index for spread analysis
CREATE INDEX IF NOT EXISTS idx_fo_strike_spread
ON fo_option_strike_bars(symbol, expiry, spread_pct_avg)
WHERE spread_pct_avg IS NOT NULL;
