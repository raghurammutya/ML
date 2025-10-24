-- SQL to create 3-minute data by aggregating from 1-minute data
-- This aggregates 1min data into 3min bars

INSERT INTO ml_labeled_data (
    symbol,
    timeframe,
    time,
    open,
    high,
    low,
    close,
    volume,
    created_at
)
SELECT 
    symbol,
    '3min' as timeframe,
    time_bucket('3 minutes', time) as time,
    first(open, time) as open,
    MAX(high) as high,
    MIN(low) as low,
    last(close, time) as close,
    SUM(volume) as volume,
    NOW() as created_at
FROM ml_labeled_data
WHERE 
    symbol = 'NIFTY'
    AND timeframe = '1min'
    AND time >= to_timestamp(1729500000)
    AND time < to_timestamp(1729540000)
    AND open IS NOT NULL
    AND high IS NOT NULL
    AND low IS NOT NULL
    AND close IS NOT NULL
GROUP BY symbol, time_bucket('3 minutes', time)
ORDER BY time
ON CONFLICT (symbol, timeframe, time) DO NOTHING;

-- Check the results
SELECT COUNT(*), timeframe 
FROM ml_labeled_data 
WHERE symbol = 'NIFTY' 
AND time >= to_timestamp(1729500000) 
AND time < to_timestamp(1729540000)
GROUP BY timeframe;