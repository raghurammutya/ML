-- Migration 009: Add Performance Indexes
-- Phase 2: High Priority - Performance Improvements

-- ============================================================================
-- 1. ML Labels Indexes (for labels.py queries)
-- ============================================================================

-- Note: ml_labels already has these indexes:
-- - idx_ml_labels_user_symbol (user_id, symbol)
-- - idx_ml_labels_timeframe ((metadata->>'timeframe'))
-- - idx_ml_labels_timestamp ((metadata->>'nearest_candle_timestamp_utc'))

-- Composite index for user queries with symbol and timeframe filtering
CREATE INDEX IF NOT EXISTS idx_ml_labels_user_symbol_tf
ON ml_labels(user_id, symbol, (metadata->>'timeframe'))
WHERE (metadata->>'timeframe') IS NOT NULL;

-- Index for created_at ordering (for recent labels queries)
CREATE INDEX IF NOT EXISTS idx_ml_labels_created
ON ml_labels(created_at DESC);

-- Index for label_type filtering
CREATE INDEX IF NOT EXISTS idx_ml_labels_type
ON ml_labels(label_type);

-- ============================================================================
-- 2. FO Option Strike Bars Indexes (for fo.py queries)
-- ============================================================================

-- Covering index for moneyness queries with all frequently accessed columns
-- This prevents PostgreSQL from needing to look up the actual row
CREATE INDEX IF NOT EXISTS idx_fo_strike_moneyness_cover
ON fo_option_strike_bars(symbol, expiry, timeframe, bucket_time, strike)
INCLUDE (underlying_close, call_iv_avg, put_iv_avg, call_delta_avg, put_delta_avg,
         call_gamma_avg, put_gamma_avg, call_volume, put_volume, call_oi_sum, put_oi_sum);

-- Index for strike distribution queries
CREATE INDEX IF NOT EXISTS idx_fo_strike_distribution
ON fo_option_strike_bars(expiry, strike, bucket_time DESC)
WHERE symbol = 'NIFTY50';

-- Index for time-series queries by strike
CREATE INDEX IF NOT EXISTS idx_fo_strike_timeseries
ON fo_option_strike_bars(symbol, strike, expiry, bucket_time DESC);

-- ============================================================================
-- 3. Account Position Indexes (for account_service.py queries)
-- ============================================================================

-- Index for account position queries with sync time ordering
CREATE INDEX IF NOT EXISTS idx_account_position_account_synced
ON account_position(account_id, synced_at DESC);

-- Index for position symbol lookups
CREATE INDEX IF NOT EXISTS idx_account_position_symbol_account
ON account_position(tradingsymbol, account_id);

-- ============================================================================
-- 4. Account Order Indexes
-- ============================================================================

-- Composite index for account order queries with status filter
CREATE INDEX IF NOT EXISTS idx_account_order_account_status_time
ON account_order(account_id, status, placed_at DESC NULLS LAST);

-- Index for strategy-linked orders
CREATE INDEX IF NOT EXISTS idx_account_order_strategy_time
ON account_order(strategy_id, placed_at DESC)
WHERE strategy_id IS NOT NULL;

-- ============================================================================
-- 5. TimescaleDB Minute Bars Indexes (for historical and replay queries)
-- ============================================================================

-- Note: Skipping - minute_bars table uses TimescaleDB hypertable with automatic partitioning
-- TimescaleDB handles indexing differently for hypertables

-- ============================================================================
-- 6. Account Holdings Index
-- ============================================================================

-- Index for account holdings queries
CREATE INDEX IF NOT EXISTS idx_account_holding_account_synced
ON account_holding(account_id, synced_at DESC);

-- ============================================================================
-- 7. Account Funds Index
-- ============================================================================

-- Index for funds queries by account and segment
CREATE INDEX IF NOT EXISTS idx_account_funds_account_segment
ON account_funds(account_id, segment, synced_at DESC);

-- ============================================================================
-- 8. Strategy Performance Indexes
-- ============================================================================

-- Index for active strategies
CREATE INDEX IF NOT EXISTS idx_strategy_active_updated
ON strategy(is_active, updated_at DESC)
WHERE is_active = true;

-- Index for strategy snapshots time-series queries
CREATE INDEX IF NOT EXISTS idx_strategy_snapshot_strategy_time
ON strategy_snapshot(strategy_id, snapshot_time DESC);

-- ============================================================================
-- Performance Analysis
-- ============================================================================

-- To analyze index usage after deployment, run:
-- SELECT schemaname, tablename, indexname, idx_scan, idx_tup_read, idx_tup_fetch
-- FROM pg_stat_user_indexes
-- WHERE schemaname = 'public'
-- ORDER BY idx_scan DESC;

-- To find unused indexes:
-- SELECT schemaname, tablename, indexname, idx_scan
-- FROM pg_stat_user_indexes
-- WHERE schemaname = 'public' AND idx_scan = 0
-- ORDER BY pg_relation_size(indexrelid) DESC;

-- ============================================================================
-- Comments for Documentation
-- ============================================================================

COMMENT ON INDEX idx_ml_labels_user_symbol_tf IS 'Composite index for user label queries with symbol and timeframe filtering';
COMMENT ON INDEX idx_fo_strike_moneyness_cover IS 'Covering index for FO moneyness queries to prevent table lookups';
COMMENT ON INDEX idx_account_position_account_synced IS 'Index for account position queries ordered by sync time';
