#!/usr/bin/env python3
"""
Test Script for Phase 2 - Dynamic Technical Indicators System

Run this after backend restart to verify all indicator functionality.

Usage:
    python test_indicators.py
"""

import requests
import json
import time
from datetime import datetime

# Configuration
BASE_URL = "http://localhost:8009"
API_KEY = "sb_30d4d5ea_bbb52c64cc4eb2536fdd7b44861c93e4b30b50c6"

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}


def print_test(name: str):
    """Print test banner."""
    print(f"\n{'='*70}")
    print(f"TEST: {name}")
    print(f"{'='*70}")


def print_result(success: bool, message: str):
    """Print test result."""
    status = "✅ PASS" if success else "❌ FAIL"
    print(f"{status}: {message}")


def test_1_subscribe_to_indicators():
    """Test 1: Subscribe to indicators via REST API."""
    print_test("Subscribe to Indicators")

    payload = {
        "symbol": "NIFTY50",
        "timeframe": "5min",
        "indicators": [
            {"name": "RSI", "params": {"length": 14}},
            {"name": "SMA", "params": {"length": 20}},
            {"name": "EMA", "params": {"length": 50}}
        ]
    }

    try:
        response = requests.post(
            f"{BASE_URL}/indicators/subscribe",
            headers=HEADERS,
            json=payload,
            timeout=30
        )

        if response.status_code == 200:
            data = response.json()
            print_result(True, f"Subscribed to {len(data['subscriptions'])} indicators")
            print(f"Client ID: {data['client_id']}")

            for sub in data['subscriptions']:
                print(f"  - {sub['indicator_id']}: subscribers={sub['subscriber_count']}, "
                      f"initial_value={sub.get('initial_value', 'N/A')}")

            return True
        else:
            print_result(False, f"Status {response.status_code}: {response.text}")
            return False

    except Exception as e:
        print_result(False, f"Error: {e}")
        return False


def test_2_get_current_values():
    """Test 2: Get current indicator values."""
    print_test("Get Current Indicator Values")

    params = {
        "symbol": "NIFTY50",
        "timeframe": "5min",
        "indicators": "RSI_14,SMA_20,EMA_50"
    }

    try:
        response = requests.get(
            f"{BASE_URL}/indicators/current",
            headers=HEADERS,
            params=params,
            timeout=30
        )

        if response.status_code == 200:
            data = response.json()
            print_result(True, f"Retrieved {len(data['values'])} indicator values")

            for indicator_id, value_data in data['values'].items():
                cached = "✓ cached" if value_data.get('cached') else "✗ computed"
                print(f"  - {indicator_id}: {value_data['value']:.2f} ({cached})")

            return True
        else:
            print_result(False, f"Status {response.status_code}: {response.text}")
            return False

    except Exception as e:
        print_result(False, f"Error: {e}")
        return False


def test_3_get_historical_values():
    """Test 3: Get historical indicator values."""
    print_test("Get Historical Indicator Values (20 candles back)")

    params = {
        "symbol": "NIFTY50",
        "timeframe": "5",
        "indicator": "RSI_14",
        "lookback": 20
    }

    try:
        response = requests.get(
            f"{BASE_URL}/indicators/history",
            headers=HEADERS,
            params=params,
            timeout=30
        )

        if response.status_code == 200:
            data = response.json()
            series = data['series']
            print_result(True, f"Retrieved {len(series)} historical values")

            if len(series) > 0:
                # Show first and last few values
                print(f"  First value: time={series[0]['time']}, value={series[0]['value']:.2f}, "
                      f"candles_back={series[0]['candles_back']}")
                print(f"  Last value:  time={series[-1]['time']}, value={series[-1]['value']:.2f}, "
                      f"candles_back={series[-1]['candles_back']}")

            return True
        else:
            print_result(False, f"Status {response.status_code}: {response.text}")
            return False

    except Exception as e:
        print_result(False, f"Error: {e}")
        return False


def test_4_get_value_at_offset():
    """Test 4: Get indicator value N candles back."""
    print_test("Get Value at Offset (10 candles back)")

    params = {
        "symbol": "NIFTY50",
        "timeframe": "5",
        "indicators": "RSI_14,SMA_20",
        "offset": 10
    }

    try:
        response = requests.get(
            f"{BASE_URL}/indicators/at-offset",
            headers=HEADERS,
            params=params,
            timeout=30
        )

        if response.status_code == 200:
            data = response.json()
            print_result(True, f"Retrieved values at offset {data['offset']}")
            print(f"  Description: {data['offset_description']}")

            for indicator_id, value_data in data['values'].items():
                print(f"  - {indicator_id}: {value_data['value']:.2f}")

            return True
        else:
            print_result(False, f"Status {response.status_code}: {response.text}")
            return False

    except Exception as e:
        print_result(False, f"Error: {e}")
        return False


def test_5_batch_query():
    """Test 5: Batch query multiple indicators/timeframes."""
    print_test("Batch Query (Multi-Timeframe RSI)")

    payload = {
        "symbol": "NIFTY50",
        "queries": [
            {"timeframe": "1min", "indicator": "RSI_14", "lookback": 10},
            {"timeframe": "5min", "indicator": "RSI_14", "lookback": 10},
            {"timeframe": "15min", "indicator": "RSI_14", "lookback": 10}
        ]
    }

    try:
        response = requests.post(
            f"{BASE_URL}/indicators/batch",
            headers=HEADERS,
            json=payload,
            timeout=30
        )

        if response.status_code == 200:
            data = response.json()
            print_result(True, f"Retrieved {len(data['results'])} timeframe results")

            for result in data['results']:
                tf = result['timeframe']
                ind_id = result['indicator_id']
                series = result['series']
                if len(series) > 0:
                    latest_value = series[-1]['value']
                    print(f"  - {tf} {ind_id}: {latest_value:.2f} (latest)")

            return True
        else:
            print_result(False, f"Status {response.status_code}: {response.text}")
            return False

    except Exception as e:
        print_result(False, f"Error: {e}")
        return False


def test_6_unsubscribe():
    """Test 6: Unsubscribe from indicators."""
    print_test("Unsubscribe from Indicators")

    payload = {
        "symbol": "NIFTY50",
        "timeframe": "5min",
        "indicators": ["RSI_14", "SMA_20"]
    }

    try:
        response = requests.post(
            f"{BASE_URL}/indicators/unsubscribe",
            headers=HEADERS,
            json=payload,
            timeout=30
        )

        if response.status_code == 200:
            data = response.json()
            print_result(True, f"Unsubscribed from {len(data['unsubscribed'])} indicators")

            for unsub in data['unsubscribed']:
                print(f"  - {unsub['indicator_id']}: remaining subscribers={unsub['subscriber_count']}")

            return True
        else:
            print_result(False, f"Status {response.status_code}: {response.text}")
            return False

    except Exception as e:
        print_result(False, f"Error: {e}")
        return False


def test_7_websocket_info():
    """Test 7: Print WebSocket connection info."""
    print_test("WebSocket Connection Info")

    ws_url = f"ws://localhost:8009/indicators/stream?api_key={API_KEY}"

    print(f"WebSocket URL: {ws_url}")
    print("\nTo test WebSocket streaming, use this Python code:\n")

    example_code = f"""
import asyncio
import websockets
import json

async def test_ws():
    uri = "{ws_url}"
    async with websockets.connect(uri) as websocket:
        # Wait for welcome
        welcome = await websocket.recv()
        print("Welcome:", json.loads(welcome))

        # Subscribe
        subscribe_msg = {{
            "action": "subscribe",
            "symbol": "NIFTY50",
            "timeframe": "5min",
            "indicators": [
                {{"name": "RSI", "params": {{"length": 14}}}},
                {{"name": "SMA", "params": {{"length": 20}}}}
            ]
        }}
        await websocket.send(json.dumps(subscribe_msg))

        # Listen
        for i in range(3):
            msg = await websocket.recv()
            print(json.loads(msg))

asyncio.run(test_ws())
"""

    print(example_code)
    print_result(True, "WebSocket info displayed (manual test required)")
    return True


def main():
    """Run all tests."""
    print(f"\n{'#'*70}")
    print("# Phase 2 - Technical Indicators System Test Suite")
    print(f"# Base URL: {BASE_URL}")
    print(f"# Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'#'*70}")

    results = []

    # Run tests
    results.append(("Subscribe to Indicators", test_1_subscribe_to_indicators()))
    time.sleep(1)

    results.append(("Get Current Values", test_2_get_current_values()))
    time.sleep(1)

    results.append(("Get Historical Values", test_3_get_historical_values()))
    time.sleep(1)

    results.append(("Get Value at Offset", test_4_get_value_at_offset()))
    time.sleep(1)

    results.append(("Batch Query", test_5_batch_query()))
    time.sleep(1)

    results.append(("Unsubscribe", test_6_unsubscribe()))
    time.sleep(1)

    results.append(("WebSocket Info", test_7_websocket_info()))

    # Summary
    print(f"\n{'='*70}")
    print("TEST SUMMARY")
    print(f"{'='*70}")

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {name}")

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 All tests passed! Phase 2 is fully operational.")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. Check logs for errors.")
        return 1


if __name__ == "__main__":
    exit(main())
