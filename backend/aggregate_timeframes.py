#!/usr/bin/env python3
"""
Aggregate 1-minute NIFTY data to multiple timeframes.
Creates 5min, 15min, 30min, 1hour, and 1day bars from 1min data.
"""

import asyncio
import asyncpg
from datetime import datetime
import os

# Database connection
DATABASE_URL = os.getenv("POSTGRES_URL", "postgresql://stocksblitz:stocksblitz123@localhost:5432/stocksblitz_unified_prod")

# Timeframe configurations: (target_timeframe, minutes_interval)
TIMEFRAMES = [
    ('2min', 2),
    ('3min', 3),
    ('5min', 5),
    ('15min', 15),
    ('30min', 30),
    ('1hour', 60),
]

# Date range
START_DATE = datetime(2025, 10, 24)
END_DATE = datetime(2025, 11, 8)


async def aggregate_timeframe(pool: asyncpg.Pool, timeframe: str, minutes: int):
    """Aggregate 1-minute data to specified timeframe"""

    print(f"\n{'='*60}")
    print(f"Aggregating to {timeframe} ({minutes} minutes)")
    print(f"{'='*60}")

    # SQL query to aggregate 1-minute bars
    # Groups by time buckets and creates OHLC bars
    aggregate_query = f"""
    INSERT INTO ml_labeled_data (
        symbol, timeframe, time, open, high, low, close, volume, created_at, updated_at
    )
    SELECT
        'NIFTY' as symbol,
        '{timeframe}' as timeframe,
        -- Round down to {minutes}-minute intervals
        date_trunc('hour', time) +
        (FLOOR(EXTRACT(MINUTE FROM time) / {minutes}) * {minutes} || ' minutes')::interval AS bar_time,
        -- First open in the period
        (array_agg(open ORDER BY time ASC))[1] as open,
        -- Highest high
        MAX(high) as high,
        -- Lowest low
        MIN(low) as low,
        -- Last close in the period
        (array_agg(close ORDER BY time DESC))[1] as close,
        -- Sum of volume
        SUM(volume) as volume,
        NOW() as created_at,
        NOW() as updated_at
    FROM ml_labeled_data
    WHERE symbol = 'NIFTY'
        AND timeframe = '1min'
        AND time >= $1::timestamp
        AND time <= $2::timestamp
    GROUP BY bar_time
    ORDER BY bar_time
    ON CONFLICT (symbol, timeframe, time) DO UPDATE SET
        open = EXCLUDED.open,
        high = EXCLUDED.high,
        low = EXCLUDED.low,
        close = EXCLUDED.close,
        volume = EXCLUDED.volume,
        updated_at = NOW()
    """

    async with pool.acquire() as conn:
        result = await conn.execute(
            aggregate_query,
            START_DATE,
            END_DATE
        )

        # Extract count from result (format: "INSERT 0 123")
        count = int(result.split()[-1]) if result else 0
        print(f"  Aggregated {count} {timeframe} bars")

        # Verify the aggregation
        verify_query = """
        SELECT
            COUNT(*) as bars,
            MIN(time) as first,
            MAX(time) as last,
            MIN(low) as lowest,
            MAX(high) as highest
        FROM ml_labeled_data
        WHERE symbol = 'NIFTY'
            AND timeframe = $1
            AND time >= $2
            AND time <= $3
        """

        row = await conn.fetchrow(verify_query, timeframe, START_DATE, END_DATE)

        print(f"  Verification:")
        print(f"    Total bars: {row['bars']}")
        print(f"    First bar: {row['first']}")
        print(f"    Last bar: {row['last']}")
        print(f"    Range: {row['lowest']:.2f} - {row['highest']:.2f}")


async def aggregate_daily(pool: asyncpg.Pool):
    """Aggregate to daily timeframe (1day)"""

    print(f"\n{'='*60}")
    print(f"Aggregating to 1day")
    print(f"{'='*60}")

    # For daily, we group by date
    aggregate_query = """
    INSERT INTO ml_labeled_data (
        symbol, timeframe, time, open, high, low, close, volume, created_at, updated_at
    )
    SELECT
        'NIFTY' as symbol,
        '1day' as timeframe,
        DATE(time) as bar_date,
        (array_agg(open ORDER BY time ASC))[1] as open,
        MAX(high) as high,
        MIN(low) as low,
        (array_agg(close ORDER BY time DESC))[1] as close,
        SUM(volume) as volume,
        NOW() as created_at,
        NOW() as updated_at
    FROM ml_labeled_data
    WHERE symbol = 'NIFTY'
        AND timeframe = '1min'
        AND time >= $1::timestamp
        AND time <= $2::timestamp
    GROUP BY DATE(time)
    ORDER BY DATE(time)
    ON CONFLICT (symbol, timeframe, time) DO UPDATE SET
        open = EXCLUDED.open,
        high = EXCLUDED.high,
        low = EXCLUDED.low,
        close = EXCLUDED.close,
        volume = EXCLUDED.volume,
        updated_at = NOW()
    """

    async with pool.acquire() as conn:
        result = await conn.execute(aggregate_query, START_DATE, END_DATE)
        count = int(result.split()[-1]) if result else 0
        print(f"  Aggregated {count} daily bars")

        # Verify
        verify_query = """
        SELECT
            COUNT(*) as bars,
            MIN(time) as first,
            MAX(time) as last
        FROM ml_labeled_data
        WHERE symbol = 'NIFTY'
            AND timeframe = '1day'
            AND time >= $1
            AND time <= $2
        """

        row = await conn.fetchrow(verify_query, START_DATE, END_DATE)
        print(f"  Verification:")
        print(f"    Total bars: {row['bars']}")
        print(f"    First date: {row['first']}")
        print(f"    Last date: {row['last']}")


async def main():
    """Main aggregation function"""

    print(f"\nStarting timeframe aggregation")
    print(f"Date range: {START_DATE.date()} to {END_DATE.date()}")
    print(f"Database: {DATABASE_URL.split('@')[1]}")

    # Connect to database
    pool = await asyncpg.create_pool(DATABASE_URL)

    # Check how much 1-minute data we have
    async with pool.acquire() as conn:
        count_1min = await conn.fetchval("""
            SELECT COUNT(*) FROM ml_labeled_data
            WHERE symbol = 'NIFTY'
                AND timeframe = '1min'
                AND time >= $1
                AND time <= $2
        """, START_DATE, END_DATE)

    print(f"Source data: {count_1min} 1-minute bars\n")

    if count_1min == 0:
        print("ERROR: No 1-minute data found! Please run backfill_nifty_history.py first.")
        await pool.close()
        return

    # Aggregate to each timeframe
    for timeframe, minutes in TIMEFRAMES:
        try:
            await aggregate_timeframe(pool, timeframe, minutes)
        except Exception as e:
            print(f"  ERROR: {e}")

    # Aggregate daily separately (different logic)
    try:
        await aggregate_daily(pool)
    except Exception as e:
        print(f"  ERROR: {e}")

    # Final summary
    print(f"\n{'='*60}")
    print("AGGREGATION COMPLETE - Summary")
    print(f"{'='*60}\n")

    async with pool.acquire() as conn:
        for tf, _ in TIMEFRAMES + [('1day', None)]:
            count = await conn.fetchval("""
                SELECT COUNT(*) FROM ml_labeled_data
                WHERE symbol = 'NIFTY'
                    AND timeframe = $1
                    AND time >= $2
                    AND time <= $3
            """, tf, START_DATE, END_DATE)
            print(f"  {tf:8s}: {count:5d} bars")

    await pool.close()
    print("\nDone!")


if __name__ == "__main__":
    asyncio.run(main())
