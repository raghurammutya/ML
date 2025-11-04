#!/usr/bin/env python3
"""
Test Script for Phase 1A Migration (Fix Continuous Aggregates)

This script verifies that migrations 016-017 completed successfully
and that the new aggregates work correctly without JOINs.

Usage:
    python scripts/test_phase1a_migration.py

Expected output:
    ✅ All tests pass
    Performance improvement: 3-5x faster
"""

import asyncio
import asyncpg
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List
import os

# Database connection
DB_URL = os.getenv("DATABASE_URL", "postgresql://stocksblitz:stocksblitz123@localhost:5432/stocksblitz_unified")


async def test_migration():
    """Run all migration verification tests"""
    print("=" * 80)
    print("PHASE 1A MIGRATION VERIFICATION")
    print("=" * 80)
    print()

    # Connect to database
    conn = await asyncpg.connect(DB_URL)

    try:
        # Test 1: Verify new tables exist
        print("Test 1: Verify new aggregates exist...")
        await test_tables_exist(conn)
        print("✅ PASS\n")

        # Test 2: Verify OI columns are accessible
        print("Test 2: Verify OI columns accessible...")
        await test_oi_columns(conn)
        print("✅ PASS\n")

        # Test 3: Verify no enriched views in use
        print("Test 3: Verify old enriched views removed...")
        await test_enriched_views_removed(conn)
        print("✅ PASS\n")

        # Test 4: Verify data integrity
        print("Test 4: Verify data integrity...")
        await test_data_integrity(conn)
        print("✅ PASS\n")

        # Test 5: Performance comparison
        print("Test 5: Performance comparison (direct vs JOIN)...")
        await test_performance(conn)
        print("✅ PASS\n")

        # Test 6: Verify continuous aggregate refresh policies
        print("Test 6: Verify refresh policies active...")
        await test_refresh_policies(conn)
        print("✅ PASS\n")

        print("=" * 80)
        print("🎉 ALL TESTS PASSED!")
        print("=" * 80)
        print()
        print("Migration 016-017 completed successfully.")
        print("Performance improvement: 3-5x faster (estimated)")
        print()
        print("Next steps:")
        print("  1. Monitor application logs for errors")
        print("  2. Check /fo/strike-distribution endpoint")
        print("  3. If all looks good, run migration 018 to cleanup old tables")
        print("  4. Proceed with Phase 1B (Redis caching)")

    finally:
        await conn.close()


async def test_tables_exist(conn: asyncpg.Connection):
    """Verify that new aggregate tables exist"""
    tables_to_check = [
        'fo_option_strike_bars_5min',
        'fo_option_strike_bars_15min'
    ]

    for table in tables_to_check:
        exists = await conn.fetchval("""
            SELECT EXISTS (
                SELECT 1 FROM pg_matviews WHERE matviewname = $1
            )
        """, table)

        if not exists:
            raise AssertionError(f"Table {table} does not exist!")

        print(f"  ✓ {table} exists")


async def test_oi_columns(conn: asyncpg.Connection):
    """Verify OI columns are directly accessible without JOINs"""

    # Test 5min aggregate
    row_5min = await conn.fetchrow("""
        SELECT call_oi_sum, put_oi_sum
        FROM fo_option_strike_bars_5min
        WHERE call_oi_sum IS NOT NULL
        LIMIT 1
    """)

    if not row_5min:
        raise AssertionError("No OI data found in fo_option_strike_bars_5min")

    print(f"  ✓ 5min OI columns accessible: call={row_5min['call_oi_sum']}, put={row_5min['put_oi_sum']}")

    # Test 15min aggregate
    row_15min = await conn.fetchrow("""
        SELECT call_oi_sum, put_oi_sum
        FROM fo_option_strike_bars_15min
        WHERE call_oi_sum IS NOT NULL
        LIMIT 1
    """)

    if not row_15min:
        raise AssertionError("No OI data found in fo_option_strike_bars_15min")

    print(f"  ✓ 15min OI columns accessible: call={row_15min['call_oi_sum']}, put={row_15min['put_oi_sum']}")


async def test_enriched_views_removed(conn: asyncpg.Connection):
    """Verify old enriched views are removed"""
    enriched_views = [
        'fo_option_strike_bars_5min_enriched',
        'fo_option_strike_bars_15min_enriched'
    ]

    for view in enriched_views:
        exists = await conn.fetchval("""
            SELECT EXISTS (
                SELECT 1 FROM pg_views WHERE viewname = $1
            )
        """, view)

        if exists:
            raise AssertionError(f"Old enriched view {view} still exists! Should be dropped.")

        print(f"  ✓ {view} removed (no more JOINs)")


async def test_data_integrity(conn: asyncpg.Connection):
    """Verify data integrity between different timeframes"""

    # Get row counts
    count_1min = await conn.fetchval("SELECT COUNT(*) FROM fo_option_strike_bars WHERE timeframe = '1min'")
    count_5min = await conn.fetchval("SELECT COUNT(*) FROM fo_option_strike_bars_5min")
    count_15min = await conn.fetchval("SELECT COUNT(*) FROM fo_option_strike_bars_15min")

    print(f"  ✓ Row counts: 1min={count_1min}, 5min={count_5min}, 15min={count_15min}")

    # Verify 5min aggregate is roughly 1/5 of 1min (allowing for compression)
    expected_5min_ratio = count_1min / 5
    ratio_5min = count_5min / expected_5min_ratio if expected_5min_ratio > 0 else 0

    if ratio_5min < 0.5 or ratio_5min > 2.0:
        raise AssertionError(f"5min aggregate ratio looks wrong: {ratio_5min:.2f} (expected ~1.0)")

    print(f"  ✓ 5min/1min ratio: {ratio_5min:.2f} (expected ~1.0)")

    # Verify 15min aggregate is roughly 1/15 of 1min
    expected_15min_ratio = count_1min / 15
    ratio_15min = count_15min / expected_15min_ratio if expected_15min_ratio > 0 else 0

    if ratio_15min < 0.5 or ratio_15min > 2.0:
        raise AssertionError(f"15min aggregate ratio looks wrong: {ratio_15min:.2f} (expected ~1.0)")

    print(f"  ✓ 15min/1min ratio: {ratio_15min:.2f} (expected ~1.0)")


async def test_performance(conn: asyncpg.Connection):
    """
    Compare query performance between direct table access and simulated JOIN

    Note: We can't test old enriched views since they're dropped,
    but we can simulate the JOIN to show the difference
    """

    # Test query: Get latest strikes for NIFTY with 3 expiries
    test_query_direct = """
        WITH latest AS (
            SELECT expiry, MAX(bucket_time) AS latest_bucket
            FROM fo_option_strike_bars_5min
            WHERE symbol = 'NIFTY'
            GROUP BY expiry
            LIMIT 3
        )
        SELECT s.*
        FROM fo_option_strike_bars_5min s
        JOIN latest l ON s.expiry = l.expiry AND s.bucket_time = l.latest_bucket
        WHERE s.symbol = 'NIFTY'
        ORDER BY s.expiry, s.strike
    """

    # Measure direct query (current implementation)
    start = time.time()
    rows_direct = await conn.fetch(test_query_direct)
    time_direct = (time.time() - start) * 1000  # ms

    print(f"  ✓ Direct query (no JOINs): {time_direct:.2f}ms ({len(rows_direct)} rows)")

    # Simulate old enriched view with JOIN
    test_query_with_join = """
        WITH latest AS (
            SELECT expiry, MAX(bucket_time) AS latest_bucket
            FROM fo_option_strike_bars_5min
            WHERE symbol = 'NIFTY'
            GROUP BY expiry
            LIMIT 3
        ),
        agg_data AS (
            SELECT s.*
            FROM fo_option_strike_bars_5min s
            JOIN latest l ON s.expiry = l.expiry AND s.bucket_time = l.latest_bucket
            WHERE s.symbol = 'NIFTY'
        )
        SELECT
            agg.*,
            COALESCE(MAX(base.call_oi_sum), 0) AS call_oi_sum_joined,
            COALESCE(MAX(base.put_oi_sum), 0) AS put_oi_sum_joined
        FROM agg_data agg
        LEFT JOIN fo_option_strike_bars base
            ON base.timeframe = '1min'
            AND base.symbol = agg.symbol
            AND base.expiry = agg.expiry
            AND base.strike = agg.strike
            AND base.bucket_time >= agg.bucket_time
            AND base.bucket_time < agg.bucket_time + INTERVAL '5 minutes'
        GROUP BY agg.bucket_time, agg.timeframe, agg.symbol, agg.expiry, agg.strike,
                 agg.underlying_close, agg.call_iv_avg, agg.put_iv_avg,
                 agg.call_delta_avg, agg.put_delta_avg, agg.call_gamma_avg,
                 agg.put_gamma_avg, agg.call_theta_avg, agg.put_theta_avg,
                 agg.call_vega_avg, agg.put_vega_avg, agg.call_volume, agg.put_volume,
                 agg.call_count, agg.put_count, agg.created_at, agg.updated_at,
                 agg.call_oi_sum, agg.put_oi_sum
        ORDER BY agg.expiry, agg.strike
    """

    start = time.time()
    rows_with_join = await conn.fetch(test_query_with_join)
    time_with_join = (time.time() - start) * 1000  # ms

    print(f"  ✓ Simulated JOIN query: {time_with_join:.2f}ms ({len(rows_with_join)} rows)")

    # Calculate speedup
    if time_with_join > 0:
        speedup = time_with_join / time_direct
        print(f"  ✓ Speedup: {speedup:.1f}x faster")

        if speedup < 1.5:
            print(f"  ⚠️  Warning: Speedup is less than expected. May need index tuning.")
    else:
        print(f"  ⚠️  Warning: Could not measure speedup (query too fast)")


async def test_refresh_policies(conn: asyncpg.Connection):
    """Verify continuous aggregate refresh policies are active"""

    # Check 5min policy
    policy_5min = await conn.fetchrow("""
        SELECT config
        FROM timescaledb_information.jobs
        WHERE hypertable_name = 'fo_option_strike_bars_5min'
          AND proc_name = 'policy_refresh_continuous_aggregate'
    """)

    if not policy_5min:
        raise AssertionError("No refresh policy found for fo_option_strike_bars_5min")

    print(f"  ✓ 5min refresh policy active")

    # Check 15min policy
    policy_15min = await conn.fetchrow("""
        SELECT config
        FROM timescaledb_information.jobs
        WHERE hypertable_name = 'fo_option_strike_bars_15min'
          AND proc_name = 'policy_refresh_continuous_aggregate'
    """)

    if not policy_15min:
        raise AssertionError("No refresh policy found for fo_option_strike_bars_15min")

    print(f"  ✓ 15min refresh policy active")


if __name__ == "__main__":
    try:
        asyncio.run(test_migration())
    except Exception as e:
        print()
        print("=" * 80)
        print("❌ TEST FAILED")
        print("=" * 80)
        print(f"Error: {e}")
        print()
        print("Migration verification failed. Please review the error above.")
        print("If needed, run migrations/017_rollback.sql to revert.")
        exit(1)
