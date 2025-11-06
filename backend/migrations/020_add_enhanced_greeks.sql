-- Migration 020: Add Enhanced Greeks Columns
-- Adds intrinsic, extrinsic, model_price, theta_daily, and rho_per_1pct to fo_option_strike_bars

-- Add call option enhanced Greek columns
ALTER TABLE fo_option_strike_bars
ADD COLUMN IF NOT EXISTS call_intrinsic_avg DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS call_extrinsic_avg DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS call_model_price_avg DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS call_theta_daily_avg DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS call_rho_per_1pct_avg DOUBLE PRECISION;

-- Add put option enhanced Greek columns
ALTER TABLE fo_option_strike_bars
ADD COLUMN IF NOT EXISTS put_intrinsic_avg DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS put_extrinsic_avg DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS put_model_price_avg DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS put_theta_daily_avg DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS put_rho_per_1pct_avg DOUBLE PRECISION;

-- Add comments for documentation
COMMENT ON COLUMN fo_option_strike_bars.call_intrinsic_avg IS 'Call option intrinsic value: max(S-K, 0)';
COMMENT ON COLUMN fo_option_strike_bars.call_extrinsic_avg IS 'Call option extrinsic (time) value: option_price - intrinsic';
COMMENT ON COLUMN fo_option_strike_bars.call_model_price_avg IS 'Call option Black-Scholes theoretical price';
COMMENT ON COLUMN fo_option_strike_bars.call_theta_daily_avg IS 'Call option theta per day (daily decay)';
COMMENT ON COLUMN fo_option_strike_bars.call_rho_per_1pct_avg IS 'Call option rho per 1% rate change';

COMMENT ON COLUMN fo_option_strike_bars.put_intrinsic_avg IS 'Put option intrinsic value: max(K-S, 0)';
COMMENT ON COLUMN fo_option_strike_bars.put_extrinsic_avg IS 'Put option extrinsic (time) value: option_price - intrinsic';
COMMENT ON COLUMN fo_option_strike_bars.put_model_price_avg IS 'Put option Black-Scholes theoretical price';
COMMENT ON COLUMN fo_option_strike_bars.put_theta_daily_avg IS 'Put option theta per day (daily decay)';
COMMENT ON COLUMN fo_option_strike_bars.put_rho_per_1pct_avg IS 'Put option rho per 1% rate change';
