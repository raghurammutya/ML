#!/usr/bin/env python3
"""
Complete SDK Test - Options, Greeks, Indicators, Account Data
Tests all SDK functionality with mock data during weekends
"""

import sys
sys.path.insert(0, '.')

from stocksblitz import TradingClient
import time
from datetime import datetime

# Configuration
API_URL = "http://localhost:8081"  # Backend URL
API_KEY = "sb_30d4d5ea_bbb52c64cc4eb2536fdd7b44861c93e4b30b50c6"

def print_section(title):
    """Print formatted section header"""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)

def print_result(label, value, success=True):
    """Print formatted result"""
    symbol = "✓" if success else "✗"
    print(f"  {symbol} {label}: {value}")

def print_error(label, error):
    """Print formatted error"""
    print(f"  ✗ {label}: ERROR - {error}")

def test_client_initialization():
    """Test 1: Client Initialization"""
    print_section("Test 1: Client Initialization")

    try:
        client = TradingClient(api_url=API_URL, api_key=API_KEY)
        print_result("Client created", f"{client}")
        print_result("API URL", API_URL)
        print_result("API Key", f"{API_KEY[:20]}...")
        return client
    except Exception as e:
        print_error("Client initialization", e)
        return None

def test_options_data(client):
    """Test 2: Options Data Retrieval"""
    print_section("Test 2: Options Data Retrieval (Mock Feed)")

    if not client:
        print_error("Skipping", "Client not initialized")
        return None

    try:
        # Test NIFTY option
        symbol = "NIFTY25N0724500PE"
        print(f"\n  Testing instrument: {symbol}")

        inst = client.Instrument(symbol)
        print_result("Instrument created", inst.tradingsymbol)

        # Try to get basic data
        try:
            ltp = inst.ltp
            print_result("LTP (Last Traded Price)", f"₹{ltp:.2f}")
        except Exception as e:
            print_error("LTP", e)

        try:
            volume = inst.volume
            print_result("Volume", f"{volume:,}")
        except Exception as e:
            print_error("Volume", e)

        try:
            oi = inst.oi
            print_result("Open Interest", f"{oi:,}")
        except Exception as e:
            print_error("Open Interest", e)

        try:
            bid = inst.bid
            ask = inst.ask
            print_result("Bid", f"₹{bid:.2f}")
            print_result("Ask", f"₹{ask:.2f}")
            print_result("Spread", f"₹{ask - bid:.2f}")
        except Exception as e:
            print_error("Bid/Ask", e)

        return inst

    except Exception as e:
        print_error("Options data", e)
        return None

def test_greeks_data(inst):
    """Test 3: Greeks Data"""
    print_section("Test 3: Greeks Data (Options)")

    if not inst:
        print_error("Skipping", "Instrument not available")
        return

    try:
        print(f"  Fetching Greeks for: {inst.tradingsymbol}")

        # Try to get Greeks
        try:
            greeks = inst.greeks
            if greeks:
                print_result("Delta", f"{greeks.get('delta', 0):.4f}")
                print_result("Gamma", f"{greeks.get('gamma', 0):.4f}")
                print_result("Theta", f"{greeks.get('theta', 0):.4f}")
                print_result("Vega", f"{greeks.get('vega', 0):.4f}")
                print_result("IV (Implied Volatility)", f"{greeks.get('iv', 0):.2%}")
            else:
                print_error("Greeks", "No data returned")
        except AttributeError as e:
            print_error("Greeks", f"Greeks property not available: {e}")
        except Exception as e:
            print_error("Greeks", e)

    except Exception as e:
        print_error("Greeks data", e)

def test_indicators(client):
    """Test 4: Technical Indicators"""
    print_section("Test 4: Technical Indicators")

    if not client:
        print_error("Skipping", "Client not initialized")
        return

    try:
        # Test with NIFTY index
        symbol = "NIFTY 50"
        print(f"\n  Testing indicators for: {symbol}")

        inst = client.Instrument(symbol)
        print_result("Instrument created", inst.tradingsymbol)

        # Test different timeframes
        timeframes = ['1m', '5m', '15m']
        for tf in timeframes:
            print(f"\n  Timeframe: {tf}")
            try:
                tf_data = inst[tf]
                print_result(f"  {tf} data available", "Yes")

                # Try to access indicators
                try:
                    rsi = tf_data.rsi[14]
                    print_result(f"    RSI(14)", f"{rsi:.2f}")
                except Exception as e:
                    print_error(f"    RSI(14)", e)

                try:
                    sma = tf_data.sma[20]
                    print_result(f"    SMA(20)", f"₹{sma:.2f}")
                except Exception as e:
                    print_error(f"    SMA(20)", e)

                try:
                    ema = tf_data.ema[20]
                    print_result(f"    EMA(20)", f"₹{ema:.2f}")
                except Exception as e:
                    print_error(f"    EMA(20)", e)

            except Exception as e:
                print_error(f"  {tf} data", e)

    except Exception as e:
        print_error("Indicators", e)

def test_account_data(client):
    """Test 5: Account Data (Positions, Holdings, Funds)"""
    print_section("Test 5: Account Data")

    if not client:
        print_error("Skipping", "Client not initialized")
        return

    try:
        account = client.Account()
        print_result("Account instance created", f"{account}")

        # Test Positions
        print("\n  A. Positions:")
        try:
            positions = account.positions
            print_result("    Positions count", len(positions))

            if positions:
                print("\n    First 3 positions:")
                for i, pos in enumerate(positions[:3], 1):
                    print(f"    {i}. {pos.tradingsymbol}")
                    print(f"       Quantity: {pos.quantity}")
                    print(f"       Avg Price: ₹{pos.average_price:.2f}")
                    print(f"       LTP: ₹{pos.last_price:.2f}")
                    print(f"       P&L: ₹{pos.pnl:.2f}")
            else:
                print("    No positions found")
        except Exception as e:
            print_error("    Positions", e)

        # Test Holdings
        print("\n  B. Holdings:")
        try:
            holdings = account.holdings
            print_result("    Holdings count", len(holdings))

            if holdings:
                print("\n    First 3 holdings:")
                for i, holding in enumerate(holdings[:3], 1):
                    print(f"    {i}. {holding.tradingsymbol}")
                    print(f"       Quantity: {holding.quantity}")
                    print(f"       Avg Price: ₹{holding.average_price:.2f}")
            else:
                print("    No holdings found")
        except Exception as e:
            print_error("    Holdings", e)

        # Test Funds
        print("\n  C. Funds:")
        try:
            funds = account.funds
            print_result("    Available Cash", f"₹{funds.available_cash:,.2f}")
            print_result("    Used Margin", f"₹{funds.used_margin:,.2f}")
            print_result("    Available Margin", f"₹{funds.available_margin:,.2f}")
            print_result("    Total Margin", f"₹{funds.total:,.2f}")
        except Exception as e:
            print_error("    Funds", e)

        # Test Orders
        print("\n  D. Orders:")
        try:
            orders = account.orders
            print_result("    Orders count", len(orders))

            if orders:
                print("\n    Recent orders:")
                for i, order in enumerate(orders[:5], 1):
                    print(f"    {i}. {order.tradingsymbol} - {order.status}")
            else:
                print("    No orders found")
        except Exception as e:
            print_error("    Orders", e)

    except Exception as e:
        print_error("Account data", e)

def test_option_chain(client):
    """Test 6: Option Chain"""
    print_section("Test 6: Option Chain")

    if not client:
        print_error("Skipping", "Client not initialized")
        return

    try:
        print("  Testing option chain retrieval...")
        print("  (This may not be available in the current SDK version)")

        # This would require an option chain endpoint
        # Placeholder for future implementation

    except Exception as e:
        print_error("Option chain", e)

def test_market_status():
    """Test 7: Market Status (Calendar Service)"""
    print_section("Test 7: Market Status (Calendar Service)")

    import requests

    try:
        response = requests.get(f"{API_URL}/calendar/status?calendar=NSE")
        if response.status_code == 200:
            data = response.json()
            print_result("Market Status API", "✓ Working")
            print_result("Date", data.get('date'))
            print_result("Is Trading Day", data.get('is_trading_day'))
            print_result("Is Holiday", data.get('is_holiday'))
            print_result("Holiday Name", data.get('holiday_name', 'N/A'))
            print_result("Current Session", data.get('current_session'))
            print_result("Next Trading Day", data.get('next_trading_day', 'N/A'))

            if not data.get('is_trading_day'):
                print("\n  ℹ️  Market is closed - SDK should receive MOCK data")
        else:
            print_error("Market Status API", f"Status code: {response.status_code}")
    except Exception as e:
        print_error("Market Status", e)

def test_ticker_service():
    """Test 8: Ticker Service Mock Data"""
    print_section("Test 8: Ticker Service (Mock Data)")

    import requests

    try:
        response = requests.get("http://localhost:8080/health")
        if response.status_code == 200:
            data = response.json()
            print_result("Ticker Service", "✓ Running")
            print_result("Status", data.get('status'))
            print_result("Environment", data.get('environment'))

            ticker_info = data.get('ticker', {})
            print_result("Active Subscriptions", ticker_info.get('active_subscriptions', 0))

            accounts = ticker_info.get('accounts', [])
            if accounts:
                for acc in accounts:
                    print_result(f"Account {acc.get('account_id')}",
                               f"{acc.get('instrument_count')} instruments")
        else:
            print_error("Ticker Service", f"Status code: {response.status_code}")
    except Exception as e:
        print_error("Ticker Service", e)

def main():
    """Run all tests"""
    print("\n" + "=" * 80)
    print("  StocksBlitz Python SDK - Complete Test Suite")
    print("  Testing: Options, Greeks, Indicators, Account Data")
    print(f"  Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    # Run tests
    client = test_client_initialization()
    time.sleep(0.5)

    test_market_status()
    time.sleep(0.5)

    test_ticker_service()
    time.sleep(0.5)

    inst = test_options_data(client)
    time.sleep(0.5)

    test_greeks_data(inst)
    time.sleep(0.5)

    test_indicators(client)
    time.sleep(0.5)

    test_account_data(client)
    time.sleep(0.5)

    test_option_chain(client)

    # Summary
    print("\n" + "=" * 80)
    print("  Test Suite Complete")
    print("=" * 80)
    print("\n  Summary:")
    print("  ✓ Tests completed")
    print("  ℹ️  Weekend/Holiday: Mock data should be flowing")
    print("  ℹ️  Check individual test results above for details")
    print("\n  Next Steps:")
    print("  1. Check logs: docker logs tv-ticker")
    print("  2. Check backend: curl http://localhost:8081/health")
    print("  3. Run examples: python examples.py")
    print("=" * 80 + "\n")

if __name__ == "__main__":
    main()
