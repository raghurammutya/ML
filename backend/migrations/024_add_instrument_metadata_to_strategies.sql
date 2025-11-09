-- Migration 024: Add Instrument Registry Metadata to Strategy Instruments
-- Phase 2.5: Strategy System Enhancement
--
-- This migration links strategy_instruments to the instrument registry
-- to automatically populate strike, option type, expiry, symbol metadata

-- =============================================================================
-- 1. Add instrument registry columns to strategy_instruments
-- =============================================================================

ALTER TABLE strategy_instruments
ADD COLUMN IF NOT EXISTS instrument_type VARCHAR(10),  -- FUT, CE, PE, EQ
ADD COLUMN IF NOT EXISTS strike NUMERIC(12, 2),
ADD COLUMN IF NOT EXISTS expiry DATE,
ADD COLUMN IF NOT EXISTS underlying_symbol VARCHAR(20),
ADD COLUMN IF NOT EXISTS lot_size INTEGER DEFAULT 1;

CREATE INDEX IF NOT EXISTS idx_strategy_instruments_expiry ON strategy_instruments(expiry) WHERE expiry IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_strategy_instruments_underlying ON strategy_instruments(underlying_symbol) WHERE underlying_symbol IS NOT NULL;

COMMENT ON COLUMN strategy_instruments.instrument_type IS 'Instrument type from registry: FUT, CE, PE, EQ';
COMMENT ON COLUMN strategy_instruments.strike IS 'Strike price for options';
COMMENT ON COLUMN strategy_instruments.expiry IS 'Expiry date for F&O instruments';
COMMENT ON COLUMN strategy_instruments.underlying_symbol IS 'Underlying symbol (e.g., NIFTY, BANKNIFTY)';
COMMENT ON COLUMN strategy_instruments.lot_size IS 'Lot size from instrument registry';


-- =============================================================================
-- 2. Create function to populate instrument metadata from registry
-- =============================================================================

CREATE OR REPLACE FUNCTION populate_instrument_metadata()
RETURNS TRIGGER AS $$
BEGIN
  -- Try to fetch metadata from instrument registry
  SELECT
    CASE
      WHEN i.instrument_type = 'FUTIDX' OR i.instrument_type = 'FUTSTK' THEN 'FUT'
      WHEN i.instrument_type = 'OPTIDX' OR i.instrument_type = 'OPTSTK' THEN
        CASE WHEN i.strike IS NOT NULL AND i.option_type = 'CE' THEN 'CE'
             WHEN i.strike IS NOT NULL AND i.option_type = 'PE' THEN 'PE'
             ELSE 'OPT' END
      ELSE 'EQ'
    END,
    i.strike,
    i.expiry,
    i.name,  -- Underlying symbol like 'NIFTY 50', 'BANKNIFTY'
    i.lot_size
  INTO
    NEW.instrument_type,
    NEW.strike,
    NEW.expiry,
    NEW.underlying_symbol,
    NEW.lot_size
  FROM instruments i
  WHERE i.tradingsymbol = NEW.tradingsymbol
    AND i.exchange = NEW.exchange
  LIMIT 1;

  -- If no match found, set defaults
  IF NEW.instrument_type IS NULL THEN
    NEW.instrument_type := 'EQ';  -- Default to equity
    NEW.lot_size := 1;
  END IF;

  -- Store instrument_token if found
  IF NEW.instrument_token IS NULL THEN
    SELECT instrument_token
    INTO NEW.instrument_token
    FROM instruments
    WHERE tradingsymbol = NEW.tradingsymbol
      AND exchange = NEW.exchange
    LIMIT 1;
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;


-- =============================================================================
-- 3. Create trigger to auto-populate metadata on insert
-- =============================================================================

DROP TRIGGER IF EXISTS trigger_populate_instrument_metadata ON strategy_instruments;
CREATE TRIGGER trigger_populate_instrument_metadata
BEFORE INSERT ON strategy_instruments
FOR EACH ROW
EXECUTE FUNCTION populate_instrument_metadata();


-- =============================================================================
-- 4. Backfill metadata for existing strategy instruments
-- =============================================================================

-- Update existing records with metadata from instrument registry
UPDATE strategy_instruments si
SET
  instrument_type = CASE
    WHEN i.instrument_type = 'FUTIDX' OR i.instrument_type = 'FUTSTK' THEN 'FUT'
    WHEN i.instrument_type = 'OPTIDX' OR i.instrument_type = 'OPTSTK' THEN
      CASE WHEN i.strike IS NOT NULL AND i.option_type = 'CE' THEN 'CE'
           WHEN i.strike IS NOT NULL AND i.option_type = 'PE' THEN 'PE'
           ELSE 'OPT' END
    ELSE 'EQ'
  END,
  strike = i.strike,
  expiry = i.expiry,
  underlying_symbol = i.name,
  lot_size = i.lot_size,
  instrument_token = i.instrument_token
FROM instruments i
WHERE si.tradingsymbol = i.tradingsymbol
  AND si.exchange = i.exchange
  AND si.instrument_type IS NULL;


-- =============================================================================
-- 5. Create view for enriched strategy instruments
-- =============================================================================

CREATE OR REPLACE VIEW strategy_instruments_enriched AS
SELECT
  si.id,
  si.strategy_id,
  si.tradingsymbol,
  si.exchange,
  si.instrument_token,
  si.instrument_type,
  si.strike,
  si.expiry,
  si.underlying_symbol,
  si.lot_size,
  si.direction,
  si.quantity,
  si.entry_price,
  si.current_price,
  si.current_pnl,
  si.added_at,
  si.notes,

  -- Calculated fields
  (si.quantity * si.lot_size) as total_quantity,
  (si.entry_price * si.quantity * si.lot_size) as entry_value,
  (si.current_price * si.quantity * si.lot_size) as current_value,

  -- Greeks (from instruments table for options)
  i.delta,
  i.gamma,
  i.theta,
  i.vega,
  i.iv as implied_volatility,

  -- Additional instrument info
  i.last_price as registry_last_price,
  i.tick_size,
  i.segment

FROM strategy_instruments si
LEFT JOIN instruments i ON si.tradingsymbol = i.tradingsymbol AND si.exchange = i.exchange;

COMMENT ON VIEW strategy_instruments_enriched IS 'Strategy instruments with full metadata from instrument registry including Greeks';


-- =============================================================================
-- 6. Create function to calculate strategy Greeks
-- =============================================================================

CREATE OR REPLACE FUNCTION get_strategy_greeks(p_strategy_id INTEGER)
RETURNS TABLE (
  net_delta NUMERIC,
  net_gamma NUMERIC,
  net_theta NUMERIC,
  net_vega NUMERIC,
  avg_iv NUMERIC
) AS $$
BEGIN
  RETURN QUERY
  SELECT
    SUM(
      CASE
        WHEN si.direction = 'BUY' THEN si.quantity * si.lot_size * i.delta
        WHEN si.direction = 'SELL' THEN -1 * si.quantity * si.lot_size * i.delta
        ELSE 0
      END
    ) as net_delta,
    SUM(
      CASE
        WHEN si.direction = 'BUY' THEN si.quantity * si.lot_size * i.gamma
        WHEN si.direction = 'SELL' THEN -1 * si.quantity * si.lot_size * i.gamma
        ELSE 0
      END
    ) as net_gamma,
    SUM(
      CASE
        WHEN si.direction = 'BUY' THEN si.quantity * si.lot_size * i.theta
        WHEN si.direction = 'SELL' THEN -1 * si.quantity * si.lot_size * i.theta
        ELSE 0
      END
    ) as net_theta,
    SUM(
      CASE
        WHEN si.direction = 'BUY' THEN si.quantity * si.lot_size * i.vega
        WHEN si.direction = 'SELL' THEN -1 * si.quantity * si.lot_size * i.vega
        ELSE 0
      END
    ) as net_vega,
    AVG(i.iv) as avg_iv
  FROM strategy_instruments si
  LEFT JOIN instruments i ON si.tradingsymbol = i.tradingsymbol AND si.exchange = i.exchange
  WHERE si.strategy_id = p_strategy_id
    AND si.instrument_type IN ('CE', 'PE')  -- Only for options
  GROUP BY si.strategy_id;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION get_strategy_greeks IS 'Calculate net Greeks for a strategy (weighted by direction: BUY +ve, SELL -ve)';


-- =============================================================================
-- 7. Create materialized view for strategy summary with Greeks
-- =============================================================================

CREATE MATERIALIZED VIEW IF NOT EXISTS strategy_summary_with_greeks AS
SELECT
  s.strategy_id,
  s.strategy_name,
  s.trading_account_id,
  s.status,
  s.is_default,
  s.total_pnl,
  s.current_m2m,

  -- Instrument counts by type
  COUNT(DISTINCT si.id) as total_instruments,
  COUNT(DISTINCT si.id) FILTER (WHERE si.instrument_type = 'CE') as ce_count,
  COUNT(DISTINCT si.id) FILTER (WHERE si.instrument_type = 'PE') as pe_count,
  COUNT(DISTINCT si.id) FILTER (WHERE si.instrument_type = 'FUT') as fut_count,

  -- Expiry distribution
  json_agg(DISTINCT si.expiry ORDER BY si.expiry) FILTER (WHERE si.expiry IS NOT NULL) as expiries,

  -- Greeks (will be NULL if no options)
  g.net_delta,
  g.net_gamma,
  g.net_theta,
  g.net_vega,
  g.avg_iv

FROM strategy s
LEFT JOIN strategy_instruments si ON s.strategy_id = si.strategy_id
LEFT JOIN LATERAL get_strategy_greeks(s.strategy_id) g ON TRUE
WHERE s.status = 'active'
GROUP BY s.strategy_id, s.strategy_name, s.trading_account_id, s.status,
         s.is_default, s.total_pnl, s.current_m2m, g.net_delta, g.net_gamma,
         g.net_theta, g.net_vega, g.avg_iv;

CREATE UNIQUE INDEX IF NOT EXISTS idx_strategy_summary_greeks_id ON strategy_summary_with_greeks(strategy_id);

COMMENT ON MATERIALIZED VIEW strategy_summary_with_greeks IS 'Strategy summary with instrument counts, expiries, and net Greeks (refresh periodically)';

-- Refresh the view
REFRESH MATERIALIZED VIEW strategy_summary_with_greeks;


-- =============================================================================
-- 8. Comments and documentation
-- =============================================================================

COMMENT ON COLUMN strategy_instruments.instrument_type IS 'FUT, CE, PE, EQ - auto-populated from instruments table';
COMMENT ON COLUMN strategy_instruments.strike IS 'Strike price for options - from instruments.strike';
COMMENT ON COLUMN strategy_instruments.expiry IS 'Expiry date - from instruments.expiry';
COMMENT ON COLUMN strategy_instruments.underlying_symbol IS 'Underlying like NIFTY, BANKNIFTY - from instruments.name';
COMMENT ON COLUMN strategy_instruments.lot_size IS 'Lot size from instruments.lot_size (default 1 for equity)';


-- =============================================================================
-- Verification
-- =============================================================================

DO $$
DECLARE
  col_count INTEGER;
BEGIN
  SELECT COUNT(*) INTO col_count
  FROM information_schema.columns
  WHERE table_name = 'strategy_instruments'
  AND column_name IN ('instrument_type', 'strike', 'expiry', 'underlying_symbol', 'lot_size');

  IF col_count = 5 THEN
    RAISE NOTICE 'Migration 024 completed successfully. Instrument metadata columns added.';
  ELSE
    RAISE EXCEPTION 'Migration 024 failed. Expected 5 new columns, found %', col_count;
  END IF;
END $$;
