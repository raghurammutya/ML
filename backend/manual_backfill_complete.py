#!/usr/bin/env python3
"""
Comprehensive manual backfill script for NIFTY.
Backfills:
1. Underlying index (minute_bars)
2. Futures contracts (futures_bars)
3. Options (fo_option_strike_bars) with Greeks, OI, IV for all strikes and expiries
"""
import asyncio
import sys
from datetime import datetime, timedelta
from typing import List, Dict
import asyncpg

# Add app to path
sys.path.insert(0, '/app')

from app.config import get_settings
from app.database import DataManager
from app.backfill import BackfillManager
from app.ticker_client import TickerServiceClient

settings = get_settings()


async def main():
    """Main comprehensive backfill execution."""
    print("🚀 Starting COMPREHENSIVE manual backfill for NIFTY")
    print("   Including: Underlying + Futures + Options (with Greeks, OI, IV)")
    print("="*70)

    # Create database pool
    db_url = f"postgresql://{settings.db_user}:{settings.db_password}@{settings.db_host}:{settings.db_port}/{settings.db_name}"
    pool = await asyncpg.create_pool(
        db_url,
        min_size=5,
        max_size=10,
        timeout=60,
        command_timeout=60
    )
    print("✅ Database pool created")

    # Initialize DataManager
    dm = DataManager(pool)
    await dm.initialize()
    print("✅ DataManager initialized")

    # Initialize TickerServiceClient
    ticker_client = TickerServiceClient(settings.ticker_service_url)
    print("✅ TickerServiceClient initialized")

    # Initialize BackfillManager (uses same logic as production)
    backfill_manager = BackfillManager(dm, ticker_client)
    print("✅ BackfillManager initialized")

    # Get metadata for NIFTY (underlying, futures, options)
    print("\n📋 Fetching NIFTY metadata (futures, options, strikes, expiries)...")
    metadata = await dm.get_nifty_monitor_metadata(
        settings.monitor_default_symbol,
        expiry_limit=6  # Get 6 expiries
    )

    if not metadata:
        print("❌ Failed to fetch metadata")
        await pool.close()
        return

    underlying_info = metadata.get("underlying")
    futures_info = metadata.get("futures", [])
    options_info = metadata.get("options", [])

    print(f"   Underlying: {underlying_info.get('tradingsymbol') if underlying_info else 'N/A'}")
    print(f"   Futures: {len(futures_info)} contracts")
    print(f"   Options: {len(options_info)} expiries")

    # Define date ranges to backfill (Nov 3-4)
    backfill_ranges = [
        {
            "start": datetime(2025, 11, 3, 0, 0, 0),
            "end": datetime(2025, 11, 3, 23, 59, 59),
            "label": "Nov 3 (Sunday)"
        },
        {
            "start": datetime(2025, 11, 4, 0, 0, 0),
            "end": datetime(2025, 11, 4, 23, 59, 59),
            "label": "Nov 4 (Monday)"
        }
    ]

    total_stats = {
        "underlying_bars": 0,
        "futures_bars": 0,
        "options_bars": 0
    }

    for date_range in backfill_ranges:
        print(f"\n{'='*70}")
        print(f"📅 Backfilling {date_range['label']}")
        print(f"   Range: {date_range['start']} to {date_range['end']}")
        print(f"{'='*70}")

        start_time = date_range["start"]
        end_time = date_range["end"]

        # 1. Backfill Underlying
        print(f"\n1️⃣  Backfilling UNDERLYING index...")
        try:
            if underlying_info:
                # Use backfill manager's internal method
                await backfill_manager._do_backfill_ohlc(
                    underlying_info.get("tradingsymbol") or "NIFTY",
                    underlying_info.get("instrument_token"),
                    start_time,
                    end_time
                )
                # Count what was inserted
                async with pool.acquire() as conn:
                    count = await conn.fetchval("""
                        SELECT COUNT(*) FROM minute_bars
                        WHERE symbol = $1
                          AND time >= $2
                          AND time < $3
                    """, "NIFTY", start_time, end_time + timedelta(days=1))
                    print(f"   ✅ Underlying: {count} bars")
                    total_stats["underlying_bars"] += count
        except Exception as e:
            print(f"   ❌ Underlying backfill error: {e}")

        # 2. Backfill Futures
        print(f"\n2️⃣  Backfilling FUTURES contracts...")
        futures_count = 0
        for i, fut in enumerate(futures_info[:3], 1):  # First 3 futures
            try:
                contract = fut.get("tradingsymbol")
                print(f"   [{i}/{min(3, len(futures_info))}] {contract}...", end=" ")

                await backfill_manager._do_backfill_future(
                    "NIFTY",
                    contract,
                    fut.get("instrument_token"),
                    fut.get("expiry"),
                    start_time,
                    end_time
                )

                async with pool.acquire() as conn:
                    count = await conn.fetchval("""
                        SELECT COUNT(*) FROM futures_bars
                        WHERE symbol = $1
                          AND contract = $2
                          AND time >= $3
                          AND time < $4
                    """, "NIFTY", contract, start_time, end_time + timedelta(days=1))
                    print(f"{count} bars")
                    futures_count += count
            except Exception as e:
                print(f"ERROR: {e}")

        print(f"   ✅ Futures total: {futures_count} bars")
        total_stats["futures_bars"] += futures_count

        # 3. Backfill Options (with Greeks, OI, IV)
        print(f"\n3️⃣  Backfilling OPTIONS (with Greeks, OI, IV)...")
        options_count = 0
        for i, exp in enumerate(options_info[:6], 1):  # First 6 expiries
            try:
                expiry_date = exp.get("expiry")
                strikes = exp.get("strikes", [])
                print(f"   [{i}/{min(6, len(options_info))}] Expiry {expiry_date}: {len(strikes)} strikes...", end=" ")

                # This method handles both calls and puts, with Greeks
                await backfill_manager._backfill_option_expiry(
                    "NIFTY",
                    exp,
                    start_time,
                    end_time
                )

                async with pool.acquire() as conn:
                    count = await conn.fetchval("""
                        SELECT COUNT(*) FROM fo_option_strike_bars
                        WHERE symbol = $1
                          AND expiry = $2
                          AND bucket_time >= $3
                          AND bucket_time < $4
                    """, "NIFTY", expiry_date, start_time, end_time + timedelta(days=1))
                    print(f"{count} bars")
                    options_count += count

                # Small delay to avoid overloading ticker service
                await asyncio.sleep(0.5)

            except Exception as e:
                print(f"ERROR: {e}")

        print(f"   ✅ Options total: {options_count} bars")
        total_stats["options_bars"] += options_count

    # Final Summary
    print(f"\n{'='*70}")
    print("✅ COMPREHENSIVE BACKFILL COMPLETE!")
    print(f"{'='*70}")
    print(f"📊 Total Stats:")
    print(f"   Underlying: {total_stats['underlying_bars']} bars")
    print(f"   Futures:    {total_stats['futures_bars']} bars")
    print(f"   Options:    {total_stats['options_bars']} bars (with Greeks, OI, IV)")
    print(f"   TOTAL:      {sum(total_stats.values())} bars")

    # Verification
    print(f"\n🔍 Verification Query:")
    async with pool.acquire() as conn:
        # Check underlying
        underlying_result = await conn.fetch("""
            SELECT DATE(time) as date, COUNT(*) as bars
            FROM minute_bars
            WHERE symbol = 'NIFTY'
              AND DATE(time) IN ('2025-11-03', '2025-11-04')
            GROUP BY DATE(time)
            ORDER BY date
        """)

        # Check futures
        futures_result = await conn.fetch("""
            SELECT DATE(time) as date, COUNT(*) as bars, COUNT(DISTINCT contract) as contracts
            FROM futures_bars
            WHERE symbol = 'NIFTY'
              AND DATE(time) IN ('2025-11-03', '2025-11-04')
            GROUP BY DATE(time)
            ORDER BY date
        """)

        # Check options
        options_result = await conn.fetch("""
            SELECT
                DATE(bucket_time) as date,
                COUNT(*) as bars,
                COUNT(DISTINCT expiry) as expiries,
                COUNT(DISTINCT strike) as strikes
            FROM fo_option_strike_bars
            WHERE symbol = 'NIFTY'
              AND DATE(bucket_time) IN ('2025-11-03', '2025-11-04')
            GROUP BY DATE(bucket_time)
            ORDER BY date
        """)

    print("\n   Underlying (minute_bars):")
    for row in underlying_result:
        print(f"     {row['date']}: {row['bars']} bars")

    print("\n   Futures (futures_bars):")
    for row in futures_result:
        print(f"     {row['date']}: {row['bars']} bars across {row['contracts']} contracts")

    print("\n   Options (fo_option_strike_bars):")
    for row in options_result:
        print(f"     {row['date']}: {row['bars']} bars ({row['expiries']} expiries, {row['strikes']} strikes)")

    # Close connections
    await dm.close()
    await pool.close()

    print(f"\n✅ Script completed successfully!")


if __name__ == "__main__":
    asyncio.run(main())
