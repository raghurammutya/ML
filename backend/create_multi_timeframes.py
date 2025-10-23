#!/usr/bin/env python3
"""Create 2min, 1hour and 1day data by aggregating from existing data"""

import asyncio
import asyncpg
import os

async def create_multi_timeframes():
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
        
        # Create 2-minute data
        print("\nCreating 2-minute data...")
        create_2min = """
            INSERT INTO ml_labeled_data (
                symbol, timeframe, time, open, high, low, close, volume, created_at
            )
            WITH grouped_data AS (
                SELECT 
                    symbol,
                    timestamp 'epoch' + interval '1 second' * (EXTRACT(EPOCH FROM time)::integer / 120 * 120) as bucket_time,
                    time, open, high, low, close, volume,
                    ROW_NUMBER() OVER (PARTITION BY symbol, EXTRACT(EPOCH FROM time)::integer / 120 ORDER BY time) as rn_first,
                    ROW_NUMBER() OVER (PARTITION BY symbol, EXTRACT(EPOCH FROM time)::integer / 120 ORDER BY time DESC) as rn_last
                FROM ml_labeled_data
                WHERE 
                    symbol = 'NIFTY' AND timeframe = '1min'
                    AND time >= to_timestamp(1729500000) AND time < to_timestamp(1729540000)
                    AND open IS NOT NULL AND high IS NOT NULL AND low IS NOT NULL AND close IS NOT NULL
            )
            SELECT 
                symbol, '2min' as timeframe, bucket_time as time,
                MAX(CASE WHEN rn_first = 1 THEN open END) as open,
                MAX(high) as high, MIN(low) as low,
                MAX(CASE WHEN rn_last = 1 THEN close END) as close,
                SUM(volume) as volume, NOW() as created_at
            FROM grouped_data
            GROUP BY symbol, bucket_time
            ORDER BY bucket_time
            ON CONFLICT (symbol, timeframe, time) DO NOTHING
        """
        result = await conn.execute(create_2min)
        print(f"Created 2-minute data: {result}")
        
        # Create 1-hour data
        print("\nCreating 1-hour data...")
        create_1hour = """
            INSERT INTO ml_labeled_data (
                symbol, timeframe, time, open, high, low, close, volume, created_at
            )
            WITH grouped_data AS (
                SELECT 
                    symbol,
                    timestamp 'epoch' + interval '1 second' * (EXTRACT(EPOCH FROM time)::integer / 3600 * 3600) as bucket_time,
                    time, open, high, low, close, volume,
                    ROW_NUMBER() OVER (PARTITION BY symbol, EXTRACT(EPOCH FROM time)::integer / 3600 ORDER BY time) as rn_first,
                    ROW_NUMBER() OVER (PARTITION BY symbol, EXTRACT(EPOCH FROM time)::integer / 3600 ORDER BY time DESC) as rn_last
                FROM ml_labeled_data
                WHERE 
                    symbol = 'NIFTY' AND timeframe IN ('5min', '15min')
                    AND time >= to_timestamp(1729000000) AND time < to_timestamp(1730000000)
                    AND open IS NOT NULL AND high IS NOT NULL AND low IS NOT NULL AND close IS NOT NULL
            )
            SELECT 
                symbol, '1hour' as timeframe, bucket_time as time,
                MAX(CASE WHEN rn_first = 1 THEN open END) as open,
                MAX(high) as high, MIN(low) as low,
                MAX(CASE WHEN rn_last = 1 THEN close END) as close,
                SUM(volume) as volume, NOW() as created_at
            FROM grouped_data
            GROUP BY symbol, bucket_time
            ORDER BY bucket_time
            ON CONFLICT (symbol, timeframe, time) DO NOTHING
        """
        result = await conn.execute(create_1hour)
        print(f"Created 1-hour data: {result}")
        
        # Create 1-day data
        print("\nCreating 1-day data...")
        create_1day = """
            INSERT INTO ml_labeled_data (
                symbol, timeframe, time, open, high, low, close, volume, created_at
            )
            WITH grouped_data AS (
                SELECT 
                    symbol,
                    date_trunc('day', time) as bucket_time,
                    time, open, high, low, close, volume,
                    ROW_NUMBER() OVER (PARTITION BY symbol, date_trunc('day', time) ORDER BY time) as rn_first,
                    ROW_NUMBER() OVER (PARTITION BY symbol, date_trunc('day', time) ORDER BY time DESC) as rn_last
                FROM ml_labeled_data
                WHERE 
                    symbol = 'NIFTY' AND timeframe = '30min'
                    AND time >= to_timestamp(1700000000) AND time < to_timestamp(1730000000)
                    AND open IS NOT NULL AND high IS NOT NULL AND low IS NOT NULL AND close IS NOT NULL
            )
            SELECT 
                symbol, '1day' as timeframe, bucket_time as time,
                MAX(CASE WHEN rn_first = 1 THEN open END) as open,
                MAX(high) as high, MIN(low) as low,
                MAX(CASE WHEN rn_last = 1 THEN close END) as close,
                SUM(volume) as volume, NOW() as created_at
            FROM grouped_data
            GROUP BY symbol, bucket_time
            ORDER BY bucket_time
            ON CONFLICT (symbol, timeframe, time) DO NOTHING
        """
        result = await conn.execute(create_1day)
        print(f"Created 1-day data: {result}")
        
        # Verify the results
        print("\n\nVerifying data counts:")
        verify_query = """
            SELECT timeframe, COUNT(*) as count,
                   MIN(time) as earliest, MAX(time) as latest
            FROM ml_labeled_data 
            WHERE symbol = 'NIFTY' 
            GROUP BY timeframe
            ORDER BY 
                CASE timeframe
                    WHEN '1min' THEN 1
                    WHEN '2min' THEN 2
                    WHEN '3min' THEN 3
                    WHEN '5min' THEN 5
                    WHEN '15min' THEN 15
                    WHEN '30min' THEN 30
                    WHEN '1hour' THEN 60
                    WHEN '1day' THEN 1440
                    ELSE 9999
                END
        """
        
        results = await conn.fetch(verify_query)
        for row in results:
            print(f"  {row['timeframe']:8s}: {row['count']:6d} records from {row['earliest']} to {row['latest']}")
        
        await conn.close()
        print("\nMulti-timeframe data creation completed successfully!")
        
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    asyncio.run(create_multi_timeframes())