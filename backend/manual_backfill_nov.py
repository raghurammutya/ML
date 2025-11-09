#!/usr/bin/env python3
"""
Manual backfill script to fill historical gaps in NIFTY data.
Fills missing data from Nov 1-5, 2025.
"""
import asyncio
import sys
from datetime import datetime, timedelta
from typing import List, Optional
import asyncpg

# Add app to path
sys.path.insert(0, '/app')

from app.config import get_settings
from app.database import DataManager
import httpx

settings = get_settings()


async def fetch_history_from_ticker(
    instrument_token: int,
    from_date: datetime,
    to_date: datetime
) -> List[dict]:
    """Fetch historical data from ticker service."""
    url = f"{settings.ticker_service_url}/history"
    params = {
        "instrument_token": instrument_token,
        "interval": "minute",
        "from_ts": from_date.isoformat() + "Z",
        "to_ts": to_date.isoformat() + "Z",
        "oi": "true"
    }

    print(f"Fetching from ticker service: {url}")
    print(f"  Token: {instrument_token}")
    print(f"  Range: {from_date} to {to_date}")

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        candles = data.get("candles", [])
        print(f"  Received {len(candles)} candles")
        return candles


def parse_candle(candle: dict) -> dict:
    """Parse candle data into row format."""
    return {
        "time": datetime.fromisoformat(candle["date"].replace("+05:30", "")),
        "open": float(candle["open"]),
        "high": float(candle["high"]),
        "low": float(candle["low"]),
        "close": float(candle["close"]),
        "volume": int(candle.get("volume", 0)),
        "oi": int(candle.get("oi", 0))
    }


async def backfill_date_range(
    dm: DataManager,
    symbol: str,
    instrument_token: int,
    start_date: datetime,
    end_date: datetime
):
    """Backfill data for a specific date range."""
    print(f"\n{'='*60}")
    print(f"Backfilling {symbol} from {start_date.date()} to {end_date.date()}")
    print(f"{'='*60}")

    try:
        # Fetch candles from ticker service
        candles = await fetch_history_from_ticker(
            instrument_token,
            start_date,
            end_date
        )

        if not candles:
            print(f"❌ No candles returned for {start_date.date()}")
            return 0

        # Parse candles into rows
        rows = []
        for candle in candles:
            try:
                row = parse_candle(candle)
                row["symbol"] = symbol
                row["resolution"] = "1 minute"
                rows.append(row)
            except Exception as e:
                print(f"⚠️  Failed to parse candle: {e}")
                continue

        if not rows:
            print(f"❌ No valid rows after parsing")
            return 0

        # Insert into database
        print(f"📝 Inserting {len(rows)} rows into minute_bars...")
        await dm.upsert_underlying_bars(rows)
        print(f"✅ Successfully inserted {len(rows)} bars for {start_date.date()}")

        return len(rows)

    except Exception as e:
        print(f"❌ Error backfilling {start_date.date()}: {e}")
        import traceback
        traceback.print_exc()
        return 0


async def main():
    """Main backfill execution."""
    print("🚀 Starting manual backfill for NIFTY Nov 1-5, 2025")
    print("="*60)

    # Create database pool
    db_url = f"postgresql://{settings.db_user}:{settings.db_password}@{settings.db_host}:{settings.db_port}/{settings.db_name}"
    pool = await asyncpg.create_pool(
        db_url,
        min_size=2,
        max_size=5,
        timeout=60,
        command_timeout=30
    )
    print("✅ Database pool created")

    # Initialize DataManager
    dm = DataManager(pool)
    await dm.initialize()
    print("✅ Database connection initialized")

    # NIFTY instrument configuration
    NIFTY_TOKEN = 256265  # NIFTY 50 index token
    NIFTY_SYMBOL = "NIFTY"

    # Define gap date ranges (Nov 1-5, 2025)
    # Trading hours: 9:15 AM - 3:30 PM IST
    gap_dates = [
        datetime(2025, 11, 1, 0, 0, 0),  # Friday
        datetime(2025, 11, 3, 0, 0, 0),  # Sunday (should have no data but we'll try)
        datetime(2025, 11, 4, 0, 0, 0),  # Monday
        datetime(2025, 11, 5, 0, 0, 0),  # Tuesday
    ]

    total_inserted = 0

    for gap_date in gap_dates:
        # Set date range for the full trading day
        start_date = gap_date
        end_date = gap_date + timedelta(days=1) - timedelta(seconds=1)

        inserted = await backfill_date_range(
            dm,
            NIFTY_SYMBOL,
            NIFTY_TOKEN,
            start_date,
            end_date
        )
        total_inserted += inserted

        # Small delay between requests
        await asyncio.sleep(1)

    # Verify the data
    print("\n" + "="*60)
    print(f"✅ Backfill complete! Total bars inserted: {total_inserted}")
    print("="*60)
    print("\n📊 Verifying inserted data...")

    # Check data by date
    async with pool.acquire() as conn:
        result = await conn.fetch("""
            SELECT DATE(time) as date, COUNT(*) as bars
            FROM minute_bars
            WHERE symbol = $1
              AND time >= $2
              AND time < $3
            GROUP BY DATE(time)
            ORDER BY date
        """, NIFTY_SYMBOL, datetime(2025, 11, 1), datetime(2025, 11, 8))

        print("\nNIFTY data by date (Nov 1-7):")
        print("-" * 40)
        for row in result:
            print(f"  {row['date']}: {row['bars']} bars")

    # Close connections
    await dm.close()
    await pool.close()

    print("\n✅ Manual backfill script completed successfully!")


if __name__ == "__main__":
    asyncio.run(main())
