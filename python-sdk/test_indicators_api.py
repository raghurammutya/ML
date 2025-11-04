#!/usr/bin/env python3
"""
Test indicators API directly
"""

import sys
sys.path.insert(0, '/mnt/stocksblitz-data/Quantagro/tradingview-viz/python-sdk')

import requests
import json
from stocksblitz import TradingClient

# Config
API_URL = "http://localhost:8081"
USER_SERVICE_URL = "http://localhost:8001"
USERNAME = "sdktest@example.com"
PASSWORD = "TestPass123!"

def main():
    print("\n" + "="*80)
    print("Testing Indicators API".center(80))
    print("="*80 + "\n")

    # Authenticate
    print("🔐 Authenticating...")
    client = TradingClient.from_credentials(
        api_url=API_URL,
        user_service_url=USER_SERVICE_URL,
        username=USERNAME,
        password=PASSWORD
    )
    access_token = client._api._access_token
    print(f"✓ Authenticated\n")

    # Test 1: Subscribe to indicators
    print("📊 Test 1: Subscribe to indicators")
    print("─"*80)
    try:
        response = requests.post(
            f"{API_URL}/indicators/subscribe",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            },
            json={
                "symbol": "NIFTY50",
                "timeframe": "5min",
                "indicators": [
                    {"name": "RSI", "params": {"length": 14}},
                    {"name": "SMA", "params": {"length": 20}}
                ]
            },
            timeout=10
        )
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}\n")
    except Exception as e:
        print(f"Error: {e}\n")

    # Test 2: Get current indicator values
    print("📊 Test 2: Get current indicator values")
    print("─"*80)
    try:
        response = requests.get(
            f"{API_URL}/indicators/current",
            headers={"Authorization": f"Bearer {access_token}"},
            params={
                "symbol": "NIFTY50",
                "timeframe": "5",
                "indicators": "RSI_14,SMA_20"
            },
            timeout=5
        )
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}\n")
    except Exception as e:
        print(f"Error: {e}\n")

    # Test 3: Get historical series
    print("📊 Test 3: Get historical indicator series")
    print("─"*80)
    try:
        response = requests.get(
            f"{API_URL}/indicators/history",
            headers={"Authorization": f"Bearer {access_token}"},
            params={
                "symbol": "NIFTY50",
                "timeframe": "5",
                "indicator": "RSI_14",
                "lookback": 5
            },
            timeout=5
        )
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}\n")
    except Exception as e:
        print(f"Error: {e}\n")

    # Test 4: Check if OHLCV data exists
    print("📊 Test 4: Check minute_bars data (OHLCV)")
    print("─"*80)
    try:
        # This is an internal check - we'll query the database through backend
        response = requests.get(
            f"{API_URL}/fo/timeseries",
            headers={"Authorization": f"Bearer {access_token}"},
            params={
                "symbol": "NIFTY50FUT",
                "timeframe": "5min",
                "limit": 5
            },
            timeout=5
        )
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"Available: {len(data.get('candles', []))} candles")
            print(f"Response: {json.dumps(data, indent=2)[:500]}...\n")
        else:
            print(f"Response: {response.text}\n")
    except Exception as e:
        print(f"Error: {e}\n")

    print("="*80)
    print("Tests Complete".center(80))
    print("="*80 + "\n")

if __name__ == "__main__":
    main()
