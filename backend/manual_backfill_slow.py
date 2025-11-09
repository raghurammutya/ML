#!/usr/bin/env python3
"""
Rate-limited manual backfill script with real-time progress updates.
Goes SLOW to avoid 502 errors.
"""
import asyncio
import sys
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import asyncpg
import httpx

# Add app to path
sys.path.insert(0, '/app')

from app.config import get_settings

settings = get_settings()

# Rate limiting configuration
DELAY_BETWEEN_INSTRUMENTS = 2.0  # seconds
DELAY_BETWEEN_STRIKES = 0.5  # seconds
REQUEST_TIMEOUT = 60.0

async def fetch_history(
    client: httpx.AsyncClient,
    instrument_token: int,
    from_date: datetime,
    to_date: datetime,
    include_greeks: bool = False
) -> Optional[List[dict]]:
    """Fetch historical data with error handling."""
    url = f"{settings.ticker_service_url}/history"
    params = {
        "instrument_token": instrument_token,
        "interval": "minute",
        "from_ts": from_date.isoformat() + "Z",
        "to_ts": to_date.isoformat() + "Z",
        "oi": "true"
    }
    if include_greeks:
        params["greeks"] = "true"

    try:
        response = await client.get(url, params=params, timeout=REQUEST_TIMEOUT)
        if response.status_code != 200:
            print(f"    ⚠️  HTTP {response.status_code}")
            return None

        data = response.json()
        candles = data.get("candles", [])
        return candles
    except Exception as e:
        print(f"    ❌ Error: {str(e)[:80]}")
        return None


async def insert_underlying_bars(pool: asyncpg.Pool, symbol: str, candles: List[dict]) -> int:
    """Insert underlying bars into minute_bars table."""
    if not candles:
        return 0

    rows = []
    for candle in candles:
        rows.append({
            "time": datetime.fromisoformat(candle["date"].replace("+05:30", "")),
            "symbol": symbol,
            "open": float(candle["open"]),
            "high": float(candle["high"]),
            "low": float(candle["low"]),
            "close": float(candle["close"]),
            "volume": int(candle.get("volume", 0)),
            "resolution": 1  # 1 minute
        })

    async with pool.acquire() as conn:
        await conn.executemany("""
            INSERT INTO minute_bars (time, symbol, open, high, low, close, volume, resolution)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (symbol, time, resolution) DO UPDATE
            SET open = EXCLUDED.open,
                high = EXCLUDED.high,
                low = EXCLUDED.low,
                close = EXCLUDED.close,
                volume = EXCLUDED.volume
        """, [(r["time"], r["symbol"], r["open"], r["high"], r["low"], r["close"], r["volume"], r["resolution"]) for r in rows])

    return len(rows)


async def insert_futures_bars(pool: asyncpg.Pool, symbol: str, contract: str, expiry: Optional[str], candles: List[dict]) -> int:
    """Insert futures bars into futures_bars table."""
    if not candles:
        return 0

    expiry_date = datetime.fromisoformat(expiry).date() if expiry else None
    rows = []
    for candle in candles:
        rows.append((
            datetime.fromisoformat(candle["date"].replace("+05:30", "")),
            symbol,
            contract,
            float(candle["open"]),
            float(candle["high"]),
            float(candle["low"]),
            float(candle["close"]),
            int(candle.get("volume", 0)),
            int(candle.get("oi", 0)),
            expiry_date,
            1  # resolution
        ))

    async with pool.acquire() as conn:
        await conn.executemany("""
            INSERT INTO futures_bars (time, symbol, contract, open, high, low, close, volume, open_interest, expiry, resolution)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            ON CONFLICT (time, symbol, contract, resolution) DO UPDATE
            SET open = EXCLUDED.open,
                high = EXCLUDED.high,
                low = EXCLUDED.low,
                close = EXCLUDED.close,
                volume = EXCLUDED.volume,
                open_interest = EXCLUDED.open_interest
        """, rows)

    return len(rows)


async def main():
    """Main execution with rate limiting."""
    print("🐢 Starting SLOW, rate-limited comprehensive backfill")
    print(f"   Delays: {DELAY_BETWEEN_INSTRUMENTS}s between instruments, {DELAY_BETWEEN_STRIKES}s between strikes")
    print("="*80)

    # Create database pool
    db_url = f"postgresql://{settings.db_user}:{settings.db_password}@{settings.db_host}:{settings.db_port}/{settings.db_name}"
    pool = await asyncpg.create_pool(db_url, min_size=2, max_size=5)
    print("✅ Database pool created")

    # Create HTTP client
    client = httpx.AsyncClient(timeout=REQUEST_TIMEOUT)
    print("✅ HTTP client created")

    # Define backfill dates
    dates_to_backfill = [
        ("2025-11-03", "Nov 3 (Sunday)"),
        ("2025-11-04", "Nov 4 (Monday)")
    ]

    # Hardcoded instruments (from metadata)
    underlying = {"token": 256265, "symbol": "NIFTY", "name": "NIFTY 50"}
    futures = [
        {"token": 9485826, "symbol": "NIFTY", "contract": "NIFTY25NOVFUT", "expiry": "2025-11-25"},
        {"token": 12683010, "symbol": "NIFTY", "contract": "NIFTY25DECFUT", "expiry": "2025-12-30"},
        {"token": 12602626, "symbol": "NIFTY", "contract": "NIFTY26JANFUT", "expiry": "2026-01-27"}
    ]

    total_stats = {"underlying": 0, "futures": 0, "options": 0}

    for date_str, date_label in dates_to_backfill:
        print(f"\n{'='*80}")
        print(f"📅 {date_label} ({date_str})")
        print(f"{'='*80}")

        from_date = datetime.fromisoformat(f"{date_str}T00:00:00")
        to_date = datetime.fromisoformat(f"{date_str}T23:59:59")

        # 1. Backfill Underlying
        print(f"\n1️⃣  UNDERLYING: {underlying['name']}")
        print(f"   Token: {underlying['token']}, Fetching...", end=" ", flush=True)
        candles = await fetch_history(client, underlying["token"], from_date, to_date)
        if candles:
            inserted = await insert_underlying_bars(pool, underlying["symbol"], candles)
            total_stats["underlying"] += inserted
            print(f"✅ {inserted} bars | {candles[0]['date']} to {candles[-1]['date']}")
        else:
            print("❌ No data")

        await asyncio.sleep(DELAY_BETWEEN_INSTRUMENTS)

        # 2. Backfill Futures
        print(f"\n2️⃣  FUTURES: {len(futures)} contracts")
        for i, fut in enumerate(futures, 1):
            print(f"   [{i}/{len(futures)}] {fut['contract']} (exp {fut['expiry']})")
            print(f"       Token: {fut['token']}, Fetching...", end=" ", flush=True)
            candles = await fetch_history(client, fut["token"], from_date, to_date, include_greeks=True)
            if candles:
                inserted = await insert_futures_bars(pool, fut["symbol"], fut["contract"], fut["expiry"], candles)
                total_stats["futures"] += inserted
                print(f"✅ {inserted} bars | Min: {candles[0]['date']} | Max: {candles[-1]['date']}")
            else:
                print("❌ No data")

            await asyncio.sleep(DELAY_BETWEEN_INSTRUMENTS)

        # 3. Options backfill skipped for now due to complexity
        # Would need to iterate through all strikes for each expiry
        print(f"\n3️⃣  OPTIONS: Skipped (requires strike-by-strike processing)")

    # Final summary
    print(f"\n{'='*80}")
    print("✅ BACKFILL COMPLETE")
    print(f"{'='*80}")
    print(f"📊 Total Inserted:")
    print(f"   Underlying: {total_stats['underlying']} bars")
    print(f"   Futures:    {total_stats['futures']} bars")
    print(f"   Options:    {total_stats['options']} bars")
    print(f"   TOTAL:      {sum(total_stats.values())} bars")

    # Verification queries
    print(f"\n🔍 Database Verification:")
    async with pool.acquire() as conn:
        # Underlying
        result = await conn.fetch("""
            SELECT DATE(time) as date, COUNT(*) as bars
            FROM minute_bars WHERE symbol = 'NIFTY' AND DATE(time) IN ('2025-11-03', '2025-11-04')
            GROUP BY DATE(time) ORDER BY date
        """)
        print("\n   Underlying (minute_bars):")
        for row in result:
            print(f"     {row['date']}: {row['bars']} bars")

        # Futures
        result = await conn.fetch("""
            SELECT contract, DATE(time) as date, COUNT(*) as bars, MIN(time) as first, MAX(time) as last
            FROM futures_bars WHERE symbol = 'NIFTY' AND DATE(time) IN ('2025-11-03', '2025-11-04')
            GROUP BY contract, DATE(time) ORDER BY date, contract
        """)
        print("\n   Futures (futures_bars):")
        for row in result:
            print(f"     {row['contract']} | {row['date']}: {row['bars']} bars | {row['first']} to {row['last']}")

    await client.aclose()
    await pool.close()
    print("\n✅ Script completed successfully!\n")


if __name__ == "__main__":
    asyncio.run(main())
