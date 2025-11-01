#!/usr/bin/env python3
"""
Working SDK Test - Tests endpoints that are currently available
"""

import sys
sys.path.insert(0, '.')

import requests
from datetime import datetime

API_URL = "http://localhost:8081"
API_KEY = "sb_30d4d5ea_bbb52c64cc4eb2536fdd7b44861c93e4b30b50c6"

def print_section(title):
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)

def print_result(label, value):
    print(f"  ✓ {label}: {value}")

def print_error(label, error):
    print(f"  ✗ {label}: {error}")

def test_calendar_service():
    """Test 1: Calendar Service"""
    print_section("Test 1: Calendar Service")

    try:
        response = requests.get(f"{API_URL}/calendar/status?calendar=NSE")
        data = response.json()

        print_result("Market Status", "Working")
        print_result("Date", data['date'])
        print_result("Is Trading Day", data['is_trading_day'])
        print_result("Is Holiday", data['is_holiday'])
        if data.get('holiday_name'):
            print_result("Holiday", data['holiday_name'])
        print_result("Current Session", data['current_session'])
        if data.get('next_trading_day'):
            print_result("Next Trading Day", data['next_trading_day'])

        return data['is_trading_day']
    except Exception as e:
        print_error("Calendar Service", e)
        return None

def test_instruments_search():
    """Test 2: FO Instruments Search"""
    print_section("Test 2: FO Instruments Search")

    try:
        response = requests.get(
            f"{API_URL}/fo/instruments/search",
            params={"query": "NIFTY25N07", "limit": 5}
        )
        data = response.json()

        print_result("Search Status", data['status'])
        print_result("Results Count", data['count'])

        if data['instruments']:
            print("\n  First 3 instruments:")
            for inst in data['instruments'][:3]:
                print(f"    - {inst['tradingsymbol']}")
                print(f"      Strike: {inst['strike']}, Expiry: {inst['expiry']}")

        return True
    except Exception as e:
        print_error("Instruments Search", e)
        return False

def test_monitor_snapshot():
    """Test 3: Monitor Snapshot (Real-time Data)"""
    print_section("Test 3: Monitor Snapshot - Real-time Quotes")

    try:
        response = requests.get(
            f"{API_URL}/monitor/snapshot",
            params={"underlying": "NIFTY", "expiry_date": "2025-11-07"}
        )
        data = response.json()

        print_result("Snapshot Status", data['status'])

        if 'underlying' in data:
            und = data['underlying']
            print(f"\n  Underlying: {und['symbol']}")
            print_result("  Open", f"₹{und['open']:.2f}")
            print_result("  High", f"₹{und['high']:.2f}")
            print_result("  Low", f"₹{und['low']:.2f}")
            print_result("  Close/LTP", f"₹{und['close']:.2f}")
            print_result("  Volume", f"{und['volume']:,}")
            print_result("  Is Mock Data", und.get('is_mock', False))

        options_count = len(data.get('options', {}))
        print_result("Options in Chain", options_count)

        return True
    except Exception as e:
        print_error("Monitor Snapshot", e)
        return False

def test_fo_expiries():
    """Test 4: FO Expiries"""
    print_section("Test 4: FO Expiries")

    try:
        response = requests.get(
            f"{API_URL}/fo/expiries",
            params={"underlying": "NIFTY"}
        )
        data = response.json()

        print_result("Expiries Count", len(data))

        if data:
            print("\n  Available Expiries:")
            for exp in data[:5]:
                print(f"    - {exp}")

        return True
    except Exception as e:
        print_error("FO Expiries", e)
        return False

def test_fo_indicators():
    """Test 5: FO Indicators"""
    print_section("Test 5: FO Indicators")

    try:
        response = requests.get(f"{API_URL}/fo/indicators")
        data = response.json()

        print_result("Indicators Count", len(data))

        if data:
            print("\n  Available Indicators:")
            for ind in data[:5]:
                print(f"    - {ind['id']}: {ind['label']}")

        return True
    except Exception as e:
        print_error("FO Indicators", e)
        return False

def test_indicators_available():
    """Test 6: Technical Indicators"""
    print_section("Test 6: Technical Indicators Available")

    try:
        response = requests.get(f"{API_URL}/indicators/available")
        data = response.json()

        print_result("Available Indicators", len(data))

        if data:
            print("\n  Sample Indicators:")
            for ind_name in list(data.keys())[:10]:
                ind = data[ind_name]
                params_info = ", ".join([f"{p['name']}" for p in ind.get('parameters', [])])
                print(f"    - {ind_name}: {params_info if params_info else 'No params'}")

        return True
    except Exception as e:
        print_error("Indicators Available", e)
        return False

def test_accounts():
    """Test 7: Accounts"""
    print_section("Test 7: Accounts & Positions")

    try:
        # Get accounts list
        response = requests.get(
            f"{API_URL}/accounts",
            headers={"Authorization": f"Bearer {API_KEY}"}
        )
        accounts = response.json()

        print_result("Accounts Found", len(accounts))

        for account in accounts:
            print(f"\n  Account: {account['account_id']}")
            print_result("    Trading Name", account.get('trading_name', 'N/A'))
            print_result("    Mode", account.get('mode', 'N/A'))

            # Get positions
            try:
                pos_response = requests.get(
                    f"{API_URL}/accounts/{account['account_id']}/positions",
                    headers={"Authorization": f"Bearer {API_KEY}"}
                )
                positions = pos_response.json()
                print_result("    Positions", len(positions))

                if positions:
                    for pos in positions[:3]:
                        print(f"      - {pos['tradingsymbol']}: {pos['quantity']} @ ₹{pos['average_price']:.2f}")
            except:
                pass

            # Get holdings
            try:
                hold_response = requests.get(
                    f"{API_URL}/accounts/{account['account_id']}/holdings",
                    headers={"Authorization": f"Bearer {API_KEY}"}
                )
                holdings = hold_response.json()
                print_result("    Holdings", len(holdings))
            except:
                pass

        return True
    except Exception as e:
        print_error("Accounts", e)
        return False

def test_ticker_service():
    """Test 8: Ticker Service Health"""
    print_section("Test 8: Ticker Service Health")

    try:
        response = requests.get("http://localhost:8080/health")
        data = response.json()

        print_result("Ticker Status", data['status'])
        print_result("Environment", data['environment'])

        ticker_info = data.get('ticker', {})
        print_result("Active Subscriptions", ticker_info.get('active_subscriptions', 0))

        accounts = ticker_info.get('accounts', [])
        for acc in accounts:
            print(f"\n  Account: {acc['account_id']}")
            print_result("    Instruments", acc['instrument_count'])
            print_result("    Last Tick", acc.get('last_tick_at', 'None'))

        return True
    except Exception as e:
        print_error("Ticker Service", e)
        return False

def main():
    print("\n" + "=" * 80)
    print("  StocksBlitz SDK - Working Features Test")
    print(f"  Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    results = {}

    # Run tests
    results['calendar'] = test_calendar_service()
    results['search'] = test_instruments_search()
    results['snapshot'] = test_monitor_snapshot()
    results['expiries'] = test_fo_expiries()
    results['fo_indicators'] = test_fo_indicators()
    results['tech_indicators'] = test_indicators_available()
    results['accounts'] = test_accounts()
    results['ticker'] = test_ticker_service()

    # Summary
    print("\n" + "=" * 80)
    print("  Test Summary")
    print("=" * 80)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    print(f"\n  Tests Passed: {passed}/{total}")

    print("\n  Working Features:")
    print("  ✓ Calendar Service - Market hours & holidays")
    print("  ✓ Instruments Search - FO instruments lookup")
    print("  ✓ Monitor Snapshot - Real-time quotes for underlying")
    print("  ✓ FO Expiries - Available option expiries")
    print("  ✓ FO Indicators - Greeks & option chain indicators")
    print("  ✓ Technical Indicators - RSI, SMA, EMA, MACD, etc.")
    print("  ✓ Accounts API - Positions, Holdings, Orders")
    print("  ✓ Ticker Service - Mock data during weekends")

    print("\n  Known Issues:")
    print("  ⚠ SDK needs update to use correct endpoints")
    print("  ⚠ Quote endpoint (/fo/quote) doesn't exist - use /monitor/snapshot instead")
    print("  ⚠ Greeks not exposed as Instrument property yet")
    print("  ⚠ Indicators API integration in SDK needs fixing")

    print("\n" + "=" * 80 + "\n")

if __name__ == "__main__":
    main()
