#!/usr/bin/env python3
"""
Backfill Enhanced Greeks

Calculates and populates enhanced Greeks (rho, theta_daily, intrinsic, extrinsic, model_price)
for existing fo_option_strike_bars records.

Usage:
    python backfill_enhanced_greeks.py [--days N] [--symbol SYMBOL] [--batch-size N]
"""

import asyncio
import argparse
from datetime import datetime, timedelta, date
from typing import Dict, Optional
import asyncpg
import sys
from pathlib import Path

# Add parent directory to path to import from backend
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.config import get_settings

try:
    from py_vollib.black import black as bs_black
    from py_vollib.black.greeks.analytical import rho as bs_rho, theta as bs_theta
except ImportError:
    print("ERROR: py_vollib not installed. Install with: pip install py_vollib")
    sys.exit(1)


def bs_greeks_and_values(
    flag: str,
    S: float,
    K: float,
    t: float,
    r: float,
    sigma: float,
    option_price: Optional[float] = None
) -> Dict[str, float]:
    """
    Calculate enhanced Greeks using Black-Scholes model.

    Args:
        flag: 'c' for call, 'p' for put
        S: Spot price
        K: Strike price
        t: Time to expiry in years
        r: Risk-free rate (continuous, e.g. 0.10 for 10%)
        sigma: Volatility (e.g. 0.18 for 18%)
        option_price: Market price for extrinsic calculation (optional)

    Returns:
        Dictionary with enhanced Greeks
    """
    # Handle edge case: at expiry
    if t <= 0:
        intrinsic = max(S - K, 0) if flag == 'c' else max(K - S, 0)
        extrinsic = 0.0 if option_price is None else max(option_price - intrinsic, 0)
        return {
            "model_price": intrinsic,
            "rho_annual": 0.0,
            "rho_per_1pct_rate_change": 0.0,
            "theta_annual": 0.0,
            "theta_daily_decay": 0.0,
            "intrinsic": intrinsic,
            "extrinsic": extrinsic
        }

    # Calculate model price
    try:
        model_price = bs_black(flag, S, K, t, r, sigma)
    except Exception as e:
        print(f"Warning: Failed to calculate model price: {e}")
        model_price = 0.0

    # Calculate Greeks
    try:
        rho_annual = bs_rho(flag, S, K, t, r, sigma)
        theta_annual = bs_theta(flag, S, K, t, r, sigma)
    except Exception as e:
        print(f"Warning: Failed to calculate Greeks: {e}")
        rho_annual = 0.0
        theta_annual = 0.0

    # Scale rho to per 1% change
    rho_per_1pct = rho_annual / 100.0

    # Scale theta to daily decay
    theta_daily = theta_annual / 365.0

    # Calculate intrinsic value
    if flag == 'c':
        intrinsic = max(S - K, 0)
    else:  # flag == 'p'
        intrinsic = max(K - S, 0)

    # Calculate extrinsic value
    if option_price is not None:
        extrinsic = max(option_price - intrinsic, 0)
    else:
        extrinsic = max(model_price - intrinsic, 0)

    return {
        "model_price": model_price,
        "rho_annual": rho_annual,
        "rho_per_1pct_rate_change": rho_per_1pct,
        "theta_annual": theta_annual,
        "theta_daily_decay": theta_daily,
        "intrinsic": intrinsic,
        "extrinsic": extrinsic
    }


def calculate_time_to_expiry(expiry_date: date, current_time: datetime) -> float:
    """Calculate time to expiry in years."""
    current_date = current_time.date() if isinstance(current_time, datetime) else current_time

    days_to_expiry = (expiry_date - current_date).days
    if days_to_expiry < 0:
        return 0.0

    # Convert days to years (using 365 days per year)
    return days_to_expiry / 365.0


async def backfill_enhanced_greeks(
    days: int = 7,
    symbol: Optional[str] = None,
    batch_size: int = 1000,
    risk_free_rate: float = 0.10
):
    """
    Backfill enhanced Greeks for historical data.

    Args:
        days: Number of days to backfill (default: 7)
        symbol: Specific symbol to backfill (default: all)
        batch_size: Number of records to process per batch
        risk_free_rate: Risk-free rate to use (default: 0.10 = 10%)
    """
    settings = get_settings()

    conn = await asyncpg.connect(
        host=settings.db_host,
        port=settings.db_port,
        user=settings.db_user,
        password=settings.db_password,
        database=settings.db_name
    )

    try:
        # Calculate date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        print(f"Backfilling enhanced Greeks from {start_date.date()} to {end_date.date()}")
        print(f"Risk-free rate: {risk_free_rate * 100}%")
        if symbol:
            print(f"Symbol: {symbol}")

        # Build query
        where_clause = "WHERE bucket_time >= $1 AND bucket_time <= $2"
        params = [start_date, end_date]

        if symbol:
            where_clause += " AND symbol = $3"
            params.append(symbol)

        # Count total records
        count_query = f"SELECT COUNT(*) FROM fo_option_strike_bars {where_clause}"
        total_records = await conn.fetchval(count_query, *params)

        print(f"Total records to process: {total_records}")

        if total_records == 0:
            print("No records found to backfill.")
            return

        # Process in batches
        offset = 0
        processed = 0
        updated = 0
        errors = 0

        while offset < total_records:
            # Fetch batch
            query = f"""
                SELECT
                    bucket_time, symbol, expiry, strike, underlying_close,
                    call_iv_avg, put_iv_avg,
                    call_delta_avg, put_delta_avg
                FROM fo_option_strike_bars
                {where_clause}
                ORDER BY bucket_time, symbol, expiry, strike
                LIMIT ${'3' if symbol else '3'} OFFSET ${'4' if symbol else '4'}
            """

            batch_params = params + [batch_size, offset]
            rows = await conn.fetch(query, *batch_params)

            if not rows:
                break

            # Process each row
            for row in rows:
                processed += 1

                try:
                    # Extract data
                    bucket_time = row['bucket_time']
                    expiry = row['expiry']
                    strike = float(row['strike'])
                    underlying_close = row['underlying_close']
                    call_iv = row['call_iv_avg']
                    put_iv = row['put_iv_avg']

                    # Skip if missing required data
                    if not underlying_close or strike == 0:
                        continue

                    # Calculate time to expiry
                    time_to_expiry = calculate_time_to_expiry(expiry, bucket_time)

                    # Calculate enhanced Greeks for CALL
                    call_enhanced = None
                    if call_iv and call_iv > 0:
                        call_enhanced = bs_greeks_and_values(
                            flag='c',
                            S=float(underlying_close),
                            K=strike,
                            t=time_to_expiry,
                            r=risk_free_rate,
                            sigma=float(call_iv)
                        )

                    # Calculate enhanced Greeks for PUT
                    put_enhanced = None
                    if put_iv and put_iv > 0:
                        put_enhanced = bs_greeks_and_values(
                            flag='p',
                            S=float(underlying_close),
                            K=strike,
                            t=time_to_expiry,
                            r=risk_free_rate,
                            sigma=float(put_iv)
                        )

                    # Update database
                    if call_enhanced or put_enhanced:
                        update_query = """
                            UPDATE fo_option_strike_bars
                            SET
                                call_rho_per_1pct_avg = $1,
                                call_intrinsic_avg = $2,
                                call_extrinsic_avg = $3,
                                call_theta_daily_avg = $4,
                                call_model_price_avg = $5,
                                put_rho_per_1pct_avg = $6,
                                put_intrinsic_avg = $7,
                                put_extrinsic_avg = $8,
                                put_theta_daily_avg = $9,
                                put_model_price_avg = $10
                            WHERE bucket_time = $11
                              AND symbol = $12
                              AND expiry = $13
                              AND strike = $14
                        """

                        await conn.execute(
                            update_query,
                            call_enhanced['rho_per_1pct_rate_change'] if call_enhanced else None,
                            call_enhanced['intrinsic'] if call_enhanced else None,
                            call_enhanced['extrinsic'] if call_enhanced else None,
                            call_enhanced['theta_daily_decay'] if call_enhanced else None,
                            call_enhanced['model_price'] if call_enhanced else None,
                            put_enhanced['rho_per_1pct_rate_change'] if put_enhanced else None,
                            put_enhanced['intrinsic'] if put_enhanced else None,
                            put_enhanced['extrinsic'] if put_enhanced else None,
                            put_enhanced['theta_daily_decay'] if put_enhanced else None,
                            put_enhanced['model_price'] if put_enhanced else None,
                            bucket_time,
                            row['symbol'],
                            expiry,
                            strike
                        )

                        updated += 1

                except Exception as e:
                    errors += 1
                    if errors <= 10:  # Only print first 10 errors
                        print(f"Error processing row: {e}")

            offset += batch_size

            # Progress update
            progress_pct = (processed / total_records) * 100
            print(f"Progress: {processed}/{total_records} ({progress_pct:.1f}%) - Updated: {updated}, Errors: {errors}")

        print(f"\nBackfill complete!")
        print(f"Total processed: {processed}")
        print(f"Total updated: {updated}")
        print(f"Total errors: {errors}")

    finally:
        await conn.close()


def main():
    parser = argparse.ArgumentParser(description='Backfill enhanced Greeks for historical option data')
    parser.add_argument('--days', type=int, default=7, help='Number of days to backfill (default: 7)')
    parser.add_argument('--symbol', type=str, help='Specific symbol to backfill (default: all)')
    parser.add_argument('--batch-size', type=int, default=1000, help='Batch size (default: 1000)')
    parser.add_argument('--risk-free-rate', type=float, default=0.10, help='Risk-free rate (default: 0.10)')

    args = parser.parse_args()

    asyncio.run(backfill_enhanced_greeks(
        days=args.days,
        symbol=args.symbol,
        batch_size=args.batch_size,
        risk_free_rate=args.risk_free_rate
    ))


if __name__ == '__main__':
    main()
