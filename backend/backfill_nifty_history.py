#!/usr/bin/env python3
"""
Backfill NIFTY historical data from ticker_service to ml_labeled_data table.
Fetches 1-minute data from Oct 24, 2025 to Nov 8, 2025.
"""

import asyncio
import asyncpg
import httpx
from datetime import datetime, timedelta
import os

# Database connection
DATABASE_URL = os.getenv("POSTGRES_URL", "postgresql://stocksblitz:stocksblitz123@localhost:5432/stocksblitz_unified_prod")

# Ticker service endpoint
TICKER_SERVICE_URL = "http://localhost:8080/history"

# NIFTY50 instrument token
NIFTY_TOKEN = 256265

# Date range to backfill
START_DATE = datetime(2025, 10, 24)
END_DATE = datetime(2025, 11, 8)


async def fetch_history(from_date: datetime, to_date: datetime) -> dict:
    """Fetch historical data from ticker_service"""
    params = {
        "instrument_token": NIFTY_TOKEN,
        "from_ts": from_date.isoformat(),
        "to_ts": to_date.isoformat(),
        "interval": "minute"
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.get(TICKER_SERVICE_URL, params=params)
        response.raise_for_status()
        return response.json()


async def insert_candles(pool: asyncpg.Pool, candles: list, symbol: str = "NIFTY"):
    """Insert candles into ml_labeled_data table"""
    if not candles:
        print("  No candles to insert")
        return 0

    # Prepare insert query
    insert_query = """
        INSERT INTO ml_labeled_data (
            symbol, timeframe, time, open, high, low, close, volume, created_at, updated_at
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW(), NOW())
        ON CONFLICT (symbol, timeframe, time) DO NOTHING
    """

    inserted = 0
    async with pool.acquire() as conn:
        for candle in candles:
            # Parse ISO timestamp with timezone
            ts_str = candle['date']
            # Remove timezone offset for naive timestamp storage
            if '+' in ts_str:
                ts_str = ts_str.split('+')[0]
            ts = datetime.fromisoformat(ts_str)

            try:
                await conn.execute(
                    insert_query,
                    symbol,
                    '1min',
                    ts,
                    float(candle['open']),
                    float(candle['high']),
                    float(candle['low']),
                    float(candle['close']),
                    int(candle['volume'])
                )
                inserted += 1
            except Exception as e:
                print(f"  Error inserting candle at {ts}: {e}")

    return inserted


async def backfill_data():
    """Main backfill function"""
    print(f"Starting backfill from {START_DATE.date()} to {END_DATE.date()}")
    print(f"Database: {DATABASE_URL.split('@')[1]}")
    print(f"Ticker service: {TICKER_SERVICE_URL}")
    print()

    # Connect to database
    pool = await asyncpg.create_pool(DATABASE_URL)

    total_inserted = 0
    total_days = (END_DATE - START_DATE).days + 1

    # Fetch data day by day to avoid timeouts
    current_date = START_DATE
    day_num = 0

    while current_date <= END_DATE:
        day_num += 1
        from_date = current_date.replace(hour=0, minute=0, second=0)
        to_date = current_date.replace(hour=23, minute=59, second=59)

        print(f"[{day_num}/{total_days}] Fetching {current_date.date()}...")

        try:
            # Fetch data from ticker service
            data = await fetch_history(from_date, to_date)
            candles = data.get('candles', [])

            print(f"  Retrieved {len(candles)} candles")

            # Insert into database
            inserted = await insert_candles(pool, candles)
            total_inserted += inserted

            print(f"  Inserted {inserted} candles")

            # Small delay to avoid rate limiting
            await asyncio.sleep(0.5)

        except httpx.HTTPError as e:
            print(f"  HTTP error: {e}")
        except Exception as e:
            print(f"  Error: {e}")

        # Move to next day
        current_date += timedelta(days=1)
        print()

    # Close pool
    await pool.close()

    print(f"\nBackfill complete!")
    print(f"Total candles inserted: {total_inserted}")

    # Verify data
    print("\nVerifying data...")
    pool = await asyncpg.create_pool(DATABASE_URL)
    async with pool.acquire() as conn:
        count = await conn.fetchval("""
            SELECT COUNT(*) FROM ml_labeled_data
            WHERE symbol = 'NIFTY'
              AND timeframe = '1min'
              AND time >= $1
              AND time <= $2
        """, START_DATE, END_DATE)
        print(f"Total 1-minute bars in database: {count}")

    await pool.close()


if __name__ == "__main__":
    asyncio.run(backfill_data())
