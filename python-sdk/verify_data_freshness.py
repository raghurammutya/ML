#!/usr/bin/env python3
"""
Quick verification script to check if data is fresh during market hours.
"""
import sys
sys.path.insert(0, '/mnt/stocksblitz-data/Quantagro/tradingview-viz/python-sdk')

from stocksblitz import TradingClient
from datetime import datetime
import pytz

print("=" * 80)
print("DATA FRESHNESS VERIFICATION - Market Hours Test")
print("=" * 80)

# Check current time
ist = pytz.timezone('Asia/Kolkata')
now_ist = datetime.now(ist)
print(f"\n📅 Current Time: {now_ist.strftime('%Y-%m-%d %I:%M:%S %p IST')}")

# Market hours check
hour = now_ist.hour
minute = now_ist.minute
is_market_hours = (hour == 9 and minute >= 15) or (10 <= hour < 15) or (hour == 15 and minute <= 30)

if is_market_hours:
    print("✅ Market is OPEN (9:15 AM - 3:30 PM IST)")
else:
    print("⚠️  Market is CLOSED")
    print("   Note: Data may be stale outside market hours (9:15 AM - 3:30 PM IST)")

print("\n" + "-" * 80)
print("Authenticating...")
print("-" * 80)

try:
    client = TradingClient.from_credentials(
        api_url="http://localhost:8081",
        user_service_url="http://localhost:8001",
        username="test_sdk@example.com",
        password="TestSDK123!@#$"
    )
    print("✅ Authentication successful!")

    print("\n" + "-" * 80)
    print("Testing Data Freshness")
    print("-" * 80)

    # Test 1: NIFTY 50 underlying
    print("\n1️⃣  Testing NIFTY 50 underlying...")
    nifty = client.Instrument("NIFTY 50")

    # Access internal quote data to get metadata
    quote_data = nifty._fetch_quote()

    ltp = quote_data.get("ltp")
    data_state = quote_data.get("_state")
    data_age = quote_data.get("_data_age")
    data_ts = quote_data.get("_timestamp")
    reason = quote_data.get("_reason")

    print(f"   LTP: ₹{ltp:,.2f}")
    print(f"   Data State: {data_state}")

    if data_age is not None:
        print(f"   Data Age: {data_age:.1f} seconds")

        if data_age <= 5:
            print(f"   ✅ Data is FRESH (≤5 seconds old)")
        elif data_age <= 10:
            print(f"   ⚠️  Data is slightly old ({data_age:.1f}s) but acceptable")
        else:
            print(f"   ❌ Data is STALE ({data_age:.1f}s old)")
            if reason:
                print(f"   Reason: {reason}")
    else:
        print(f"   ⚠️  Data age not available")

    # Test 2: Check backend snapshot directly
    print("\n2️⃣  Checking backend /monitor/snapshot directly...")
    import requests
    import time

    response = requests.get(
        "http://localhost:8081/monitor/snapshot",
        params={"underlying": "NIFTY"},
        headers={"Authorization": f"Bearer {client._api._token}"}
    )

    if response.status_code == 200:
        snapshot = response.json()
        underlying_data = snapshot.get("underlying", {})

        backend_ltp = underlying_data.get("close")
        backend_ts = underlying_data.get("ts")

        print(f"   Backend LTP: ₹{backend_ltp:,.2f}")

        if backend_ts:
            backend_age = time.time() - backend_ts
            print(f"   Backend Data Age: {backend_age:.1f} seconds")

            if backend_age <= 5:
                print(f"   ✅ Backend data is FRESH")
            else:
                print(f"   ❌ Backend data is STALE ({backend_age:.1f}s old)")
        else:
            print(f"   ⚠️  No timestamp in backend response")
    else:
        print(f"   ❌ Backend request failed: {response.status_code}")

    # Test 3: Check Redis for live ticks
    print("\n3️⃣  Checking Redis for active tick publishing...")
    import redis

    try:
        r = redis.Redis(host='localhost', port=6379, decode_responses=True)

        # Check how many channels are publishing
        pubsub_channels = r.execute_command('PUBSUB CHANNELS', 'ticker:*')
        print(f"   Active ticker channels: {len(pubsub_channels)}")

        if len(pubsub_channels) > 0:
            print(f"   ✅ Ticker service is publishing to {len(pubsub_channels)} channels")

            # Show sample channels
            for channel in list(pubsub_channels)[:5]:
                # Get number of subscribers
                numsub = r.execute_command('PUBSUB NUMSUB', channel)
                if len(numsub) >= 2:
                    channel_name = numsub[0]
                    subscriber_count = numsub[1]
                    print(f"      - {channel_name}: {subscriber_count} subscribers")
        else:
            print(f"   ⚠️  No active ticker channels found")
            print(f"      Ticker service may not be running or publishing")

    except Exception as e:
        print(f"   ⚠️  Could not check Redis: {e}")

    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    if is_market_hours:
        if data_age and data_age <= 10:
            print("✅ Data freshness is GOOD during market hours")
            print("   SDK is receiving fresh data from backend")
        else:
            print("❌ Data is STALE despite market being open")
            print("   This indicates a problem with the data pipeline:")
            print("   1. Check if ticker_service is running and publishing ticks")
            print("   2. Verify backend NiftyMonitorStream is consuming from Redis")
            print("   3. Check Redis channel mismatch between services")
    else:
        print("⚠️  Test run outside market hours")
        print("   Stale data is expected. Re-run between 9:15 AM - 3:30 PM IST")

except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()

print()
