#!/usr/bin/env python3
"""
Options backfill script with Greeks, IV, and OI.
Processes all strikes for each expiry with real-time progress updates.
"""
import asyncio
import sys
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional
import asyncpg
import httpx

# Add app to path
sys.path.insert(0, '/app')

from app.config import get_settings

settings = get_settings()

# Rate limiting configuration
DELAY_BETWEEN_STRIKES = 1.0  # seconds per strike (to avoid 502 errors)
DELAY_BETWEEN_EXPIRIES = 3.0  # seconds per expiry
REQUEST_TIMEOUT = 60.0


async def fetch_option_history_with_greeks(
    client: httpx.AsyncClient,
    instrument_token: int,
    from_date: datetime,
    to_date: datetime
) -> Optional[List[dict]]:
    """Fetch option history with Greeks from ticker service."""
    url = f"{settings.ticker_service_url}/history"
    params = {
        "instrument_token": instrument_token,
        "interval": "minute",
        "from_ts": from_date.isoformat() + "Z",
        "to_ts": to_date.isoformat() + "Z",
        "oi": "true",
        "greeks": "true"
    }

    try:
        response = await client.get(url, params=params, timeout=REQUEST_TIMEOUT)
        if response.status_code != 200:
            return None
        data = response.json()
        return data.get("candles", [])
    except Exception:
        return None


async def insert_option_strike_bars(
    pool: asyncpg.Pool,
    symbol: str,
    expiry: str,
    strike: float,
    call_candles: List[dict],
    put_candles: List[dict]
) -> int:
    """
    Insert option bars aggregated by strike.
    Combines call and put data into fo_option_strike_bars.
    """
    if not call_candles and not put_candles:
        return 0

    # Create a time-indexed map
    call_map = {datetime.fromisoformat(c["date"].replace("+05:30", "")): c for c in call_candles}
    put_map = {datetime.fromisoformat(c["date"].replace("+05:30", "")): c for c in put_candles}

    all_times = sorted(set(call_map.keys()) | set(put_map.keys()))

    rows = []
    for bucket_time in all_times:
        call_data = call_map.get(bucket_time)
        put_data = put_map.get(bucket_time)

        # Get underlying close from either call or put
        underlying_close = None
        if call_data and "underlying" in call_data:
            underlying_close = call_data["underlying"]
        elif put_data and "underlying" in put_data:
            underlying_close = put_data["underlying"]

        # Extract Greeks and metrics
        call_iv = call_data.get("iv") if call_data else None
        put_iv = put_data.get("iv") if put_data else None
        call_delta = call_data.get("delta") if call_data else None
        put_delta = put_data.get("delta") if put_data else None
        call_gamma = call_data.get("gamma") if call_data else None
        put_gamma = put_data.get("gamma") if put_data else None
        call_theta = call_data.get("theta") if call_data else None
        put_theta = put_data.get("theta") if put_data else None
        call_vega = call_data.get("vega") if call_data else None
        put_vega = put_data.get("vega") if put_data else None
        call_volume = call_data.get("volume", 0) if call_data else 0
        put_volume = put_data.get("volume", 0) if put_data else 0
        call_oi = call_data.get("oi", 0) if call_data else 0
        put_oi = put_data.get("oi", 0) if put_data else 0

        # Additional Greeks if available
        call_rho = call_data.get("rho") if call_data else None
        put_rho = put_data.get("rho") if put_data else None
        call_intrinsic = call_data.get("intrinsic_value") if call_data else None
        put_intrinsic = put_data.get("intrinsic_value") if put_data else None
        call_extrinsic = call_data.get("extrinsic_value") if call_data else None
        put_extrinsic = put_data.get("extrinsic_value") if put_data else None

        rows.append((
            bucket_time.replace(tzinfo=timezone.utc),  # bucket_time
            "1min",  # timeframe
            symbol,
            datetime.fromisoformat(expiry).date(),  # expiry
            strike,
            underlying_close,
            call_iv,
            put_iv,
            call_delta,
            put_delta,
            call_gamma,
            put_gamma,
            call_theta,
            put_theta,
            call_vega,
            put_vega,
            call_volume,
            put_volume,
            1 if call_data else 0,  # call_count
            1 if put_data else 0,   # put_count
            call_oi,
            put_oi,
            call_intrinsic,
            call_extrinsic,
            None,  # call_model_price_avg
            None,  # call_theta_daily_avg
            call_rho,
            put_intrinsic,
            put_extrinsic,
            None,  # put_model_price_avg
            None,  # put_theta_daily_avg
            put_rho
        ))

    if not rows:
        return 0

    async with pool.acquire() as conn:
        await conn.executemany("""
            INSERT INTO fo_option_strike_bars (
                bucket_time, timeframe, symbol, expiry, strike,
                underlying_close,
                call_iv_avg, put_iv_avg,
                call_delta_avg, put_delta_avg,
                call_gamma_avg, put_gamma_avg,
                call_theta_avg, put_theta_avg,
                call_vega_avg, put_vega_avg,
                call_volume, put_volume,
                call_count, put_count,
                call_oi_sum, put_oi_sum,
                call_intrinsic_avg, call_extrinsic_avg, call_model_price_avg,
                call_theta_daily_avg, call_rho_per_1pct_avg,
                put_intrinsic_avg, put_extrinsic_avg, put_model_price_avg,
                put_theta_daily_avg, put_rho_per_1pct_avg
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16,
                    $17, $18, $19, $20, $21, $22, $23, $24, $25, $26, $27, $28, $29, $30, $31, $32)
            ON CONFLICT (bucket_time, timeframe, symbol, expiry, strike) DO UPDATE
            SET underlying_close = EXCLUDED.underlying_close,
                call_iv_avg = EXCLUDED.call_iv_avg,
                put_iv_avg = EXCLUDED.put_iv_avg,
                call_delta_avg = EXCLUDED.call_delta_avg,
                put_delta_avg = EXCLUDED.put_delta_avg,
                call_gamma_avg = EXCLUDED.call_gamma_avg,
                put_gamma_avg = EXCLUDED.put_gamma_avg,
                call_theta_avg = EXCLUDED.call_theta_avg,
                put_theta_avg = EXCLUDED.put_theta_avg,
                call_vega_avg = EXCLUDED.call_vega_avg,
                put_vega_avg = EXCLUDED.put_vega_avg,
                call_volume = EXCLUDED.call_volume,
                put_volume = EXCLUDED.put_volume,
                call_oi_sum = EXCLUDED.call_oi_sum,
                put_oi_sum = EXCLUDED.put_oi_sum
        """, rows)

    return len(rows)


async def main():
    """Main options backfill execution."""
    print("📊 Starting OPTIONS backfill with Greeks, IV, and OI")
    print(f"   Delays: {DELAY_BETWEEN_STRIKES}s per strike, {DELAY_BETWEEN_EXPIRIES}s per expiry")
    print("="*80)

    # Create database pool
    db_url = f"postgresql://{settings.db_user}:{settings.db_password}@{settings.db_host}:{settings.db_port}/{settings.db_name}"
    pool = await asyncpg.create_pool(db_url, min_size=2, max_size=5)
    client = httpx.AsyncClient(timeout=REQUEST_TIMEOUT)
    print("✅ Database pool and HTTP client created\n")

    # Fetch active NIFTY options from subscriptions
    print("📋 Fetching active NIFTY options subscriptions...")
    response = await client.get(f"{settings.ticker_service_url}/subscriptions", params={"status": "active"})
    subscriptions = response.json()

    # Group by expiry
    options_by_expiry = {}
    for sub in subscriptions:
        if sub.get("segment") != "NFO-OPT":
            continue
        symbol = sub["tradingsymbol"]
        if not symbol.startswith("NIFTY25N"):
            continue

        # Parse expiry and strike from symbol (e.g., NIFTY25N1125350CE)
        # Format: NIFTY25N + {month}{day}{strike}{CE/PE}
        # Index 8 onwards: "1125350CE" = month(11) + day(25) + strike(350) + type(CE)
        after_n = symbol[8:]  # "1125350CE"

        # Extract month (2 digits) and day (2 digits)
        month = int(after_n[:2])   # "11"
        day = int(after_n[2:4])    # "25"
        expiry_date = f"2025-{month:02d}-{day:02d}"

        # Rest is strike + option type
        strike_and_type = after_n[4:]  # "350CE"
        strike_str = strike_and_type[:-2]  # "350"
        strike = float(strike_str)  # Strike value

        option_type = symbol[-2:]  # "CE" or "PE"

        if expiry_date not in options_by_expiry:
            options_by_expiry[expiry_date] = {}

        if strike not in options_by_expiry[expiry_date]:
            options_by_expiry[expiry_date][strike] = {}

        options_by_expiry[expiry_date][strike][option_type] = sub

    print(f"✅ Found {len(options_by_expiry)} expiries\n")

    # Backfill dates
    dates_to_backfill = [
        ("2025-11-03", "Nov 3"),
        ("2025-11-04", "Nov 4")
    ]

    total_bars = 0
    total_strikes = 0

    for date_str, date_label in dates_to_backfill:
        print(f"{'='*80}")
        print(f"📅 {date_label} ({date_str})")
        print(f"{'='*80}\n")

        from_date = datetime.fromisoformat(f"{date_str}T00:00:00")
        to_date = datetime.fromisoformat(f"{date_str}T23:59:59")

        # Process first 3 expiries only (to avoid very long runtime)
        for exp_idx, (expiry, strikes) in enumerate(sorted(options_by_expiry.items())[:3], 1):
            print(f"⏰ Expiry {exp_idx}/3: {expiry} ({len(strikes)} strikes)")

            for strike_idx, (strike, options) in enumerate(sorted(strikes.items()), 1):
                call_token = options.get("CE", {}).get("instrument_token")
                put_token = options.get("PE", {}).get("instrument_token")

                if not call_token and not put_token:
                    continue

                print(f"   [{strike_idx:3d}/{len(strikes)}] Strike {strike:7.2f}: ", end="", flush=True)

                # Fetch call data
                call_candles = []
                if call_token:
                    call_candles = await fetch_option_history_with_greeks(client, call_token, from_date, to_date)
                    if not call_candles:
                        call_candles = []

                # Fetch put data
                put_candles = []
                if put_token:
                    put_candles = await fetch_option_history_with_greeks(client, put_token, from_date, to_date)
                    if not put_candles:
                        put_candles = []

                # Insert combined data
                if call_candles or put_candles:
                    bars_inserted = await insert_option_strike_bars(
                        pool, "NIFTY", expiry, strike, call_candles, put_candles
                    )
                    total_bars += bars_inserted
                    total_strikes += 1
                    print(f"✅ {bars_inserted:3d} bars (C:{len(call_candles)} P:{len(put_candles)})")
                else:
                    print("❌ No data")

                await asyncio.sleep(DELAY_BETWEEN_STRIKES)

            print(f"   ✅ Expiry {expiry} complete\n")
            await asyncio.sleep(DELAY_BETWEEN_EXPIRIES)

    # Final summary
    print(f"\n{'='*80}")
    print("✅ OPTIONS BACKFILL COMPLETE")
    print(f"{'='*80}")
    print(f"📊 Total: {total_bars} bars across {total_strikes} strikes")

    # Verification
    print(f"\n🔍 Database Verification:")
    async with pool.acquire() as conn:
        result = await conn.fetch("""
            SELECT
                expiry,
                DATE(bucket_time) as date,
                COUNT(*) as bars,
                COUNT(DISTINCT strike) as strikes,
                SUM(CASE WHEN call_iv_avg IS NOT NULL THEN 1 ELSE 0 END) as with_call_greeks,
                SUM(CASE WHEN put_iv_avg IS NOT NULL THEN 1 ELSE 0 END) as with_put_greeks
            FROM fo_option_strike_bars
            WHERE symbol = 'NIFTY'
              AND DATE(bucket_time) IN ('2025-11-03', '2025-11-04')
            GROUP BY expiry, DATE(bucket_time)
            ORDER BY date, expiry
        """)

        print("\n   Options (fo_option_strike_bars):")
        for row in result:
            print(f"     {row['date']} | Exp:{row['expiry']} | {row['bars']} bars | "
                  f"{row['strikes']} strikes | Greeks: C={row['with_call_greeks']} P={row['with_put_greeks']}")

    await client.aclose()
    await pool.close()
    print("\n✅ Script completed successfully!\n")


if __name__ == "__main__":
    asyncio.run(main())
