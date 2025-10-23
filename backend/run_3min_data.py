#!/usr/bin/env python3
"""Create 3-minute data by aggregating 1-minute data"""

import asyncio
import asyncpg
import os

async def create_3min_data():
    # Database configuration
    db_config = {
        'host': os.getenv('DB_HOST', 'localhost'),
        'port': int(os.getenv('DB_PORT', '5432')),
        'database': os.getenv('DB_NAME', 'stocksblitz_unified'),
        'user': os.getenv('DB_USER', 'stocksblitz'),
        'password': os.getenv('DB_PASSWORD', 'stocksblitz123')
    }
    
    try:
        # Connect to database
        conn = await asyncpg.connect(**db_config)
        print(f"Connected to database {db_config['database']}")
        
        # First check if we have 1min data to aggregate
        check_query = """
            SELECT COUNT(*) as count
            FROM ml_labeled_data
            WHERE symbol = 'NIFTY'
            AND timeframe = '1min'
            AND time >= to_timestamp(1729500000)
            AND time < to_timestamp(1729540000)
            AND open IS NOT NULL
            AND high IS NOT NULL
            AND low IS NOT NULL
            AND close IS NOT NULL
        """
        
        count = await conn.fetchval(check_query)
        print(f"Found {count} valid 1-minute records to aggregate")
        
        if count == 0:
            print("No valid 1-minute data found to aggregate")
            await conn.close()
            return
        
        # Create 3-minute data using standard aggregation (no TimescaleDB dependency)
        create_query = """
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
            WITH grouped_data AS (
                SELECT 
                    symbol,
                    -- Group into 3-minute buckets
                    timestamp 'epoch' + interval '1 second' * (EXTRACT(EPOCH FROM time)::integer / 180 * 180) as bucket_time,
                    time,
                    open,
                    high,
                    low,
                    close,
                    volume,
                    ROW_NUMBER() OVER (PARTITION BY symbol, EXTRACT(EPOCH FROM time)::integer / 180 ORDER BY time) as rn_first,
                    ROW_NUMBER() OVER (PARTITION BY symbol, EXTRACT(EPOCH FROM time)::integer / 180 ORDER BY time DESC) as rn_last
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
            )
            SELECT 
                symbol,
                '3min' as timeframe,
                bucket_time as time,
                MAX(CASE WHEN rn_first = 1 THEN open END) as open,
                MAX(high) as high,
                MIN(low) as low,
                MAX(CASE WHEN rn_last = 1 THEN close END) as close,
                SUM(volume) as volume,
                NOW() as created_at
            FROM grouped_data
            GROUP BY symbol, bucket_time
            ORDER BY bucket_time
            ON CONFLICT (symbol, timeframe, time) DO NOTHING
        """
        
        result = await conn.execute(create_query)
        print(f"Created 3-minute data: {result}")
        
        # Verify the results
        verify_query = """
            SELECT COUNT(*) as count, timeframe 
            FROM ml_labeled_data 
            WHERE symbol = 'NIFTY' 
            AND time >= to_timestamp(1729500000) 
            AND time < to_timestamp(1729540000)
            GROUP BY timeframe
            ORDER BY timeframe
        """
        
        results = await conn.fetch(verify_query)
        print("\nData count by timeframe:")
        for row in results:
            print(f"  {row['timeframe']}: {row['count']} records")
        
        # Show sample 3min data
        sample_query = """
            SELECT time, open, high, low, close, volume
            FROM ml_labeled_data
            WHERE symbol = 'NIFTY'
            AND timeframe = '3min'
            ORDER BY time
            LIMIT 5
        """
        
        samples = await conn.fetch(sample_query)
        print("\nSample 3-minute data:")
        for row in samples:
            print(f"  {row['time']}: O={row['open']:.2f} H={row['high']:.2f} L={row['low']:.2f} C={row['close']:.2f} V={row['volume']}")
        
        await conn.close()
        print("\n3-minute data creation completed successfully!")
        
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    asyncio.run(create_3min_data())