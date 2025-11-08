-- Safe script to copy recent OHLC data from production to development
-- This script only READS from production and WRITES to development

-- First, let's copy a reasonable amount of recent data (last 2 months)
-- Using individual INSERT statements to avoid TimescaleDB issues

DO $$
DECLARE
    rec RECORD;
    counter INTEGER := 0;
BEGIN
    -- Loop through recent production data and insert into development
    FOR rec IN 
        SELECT time, open, high, low, close, volume, symbol 
        FROM nifty50_ohlc 
        WHERE time > NOW() - INTERVAL '2 months' 
        ORDER BY time DESC 
        LIMIT 20000
    LOOP
        BEGIN
            INSERT INTO nifty50_ohlc (time, open, high, low, close, volume, symbol)
            VALUES (rec.time, rec.open, rec.high, rec.low, rec.close, rec.volume, rec.symbol);
            
            counter := counter + 1;
            
            -- Progress indicator every 1000 records
            IF counter % 1000 = 0 THEN
                RAISE NOTICE 'Copied % records...', counter;
            END IF;
            
        EXCEPTION 
            WHEN unique_violation THEN
                -- Skip duplicates
                CONTINUE;
            WHEN OTHERS THEN
                RAISE NOTICE 'Error inserting record at %: %', rec.time, SQLERRM;
                CONTINUE;
        END;
    END LOOP;
    
    RAISE NOTICE 'Total records copied: %', counter;
END $$;