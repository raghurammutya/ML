#!/usr/bin/env python3
"""
Enhanced Tick Monitor with Greeks and Indicators
Shows prices, volume, OI, and option Greeks (IV, Delta, Gamma, Theta, Vega)
"""

import sys
sys.path.insert(0, '/mnt/stocksblitz-data/Quantagro/tradingview-viz/python-sdk')

import time
import requests
from datetime import datetime
from collections import defaultdict

from stocksblitz import TradingClient

# Config
API_URL = "http://localhost:8081"
USER_SERVICE_URL = "http://localhost:8001"
USERNAME = "sdktest@example.com"
PASSWORD = "TestPass123!"

def get_backend_snapshot():
    """Get live data from backend"""
    try:
        response = requests.get(f"{API_URL}/monitor/snapshot", timeout=5)
        return response.json()
    except:
        return {}

def calculate_pcr(options_data, strike=None):
    """Calculate Put-Call Ratio by volume or OI"""
    put_oi = 0
    call_oi = 0
    put_vol = 0
    call_vol = 0

    for opt in options_data.values():
        if strike and opt.get('strike') != strike:
            continue
        if opt.get('type') == 'PE':
            put_oi += opt.get('oi', 0)
            put_vol += opt.get('volume', 0)
        elif opt.get('type') == 'CE':
            call_oi += opt.get('oi', 0)
            call_vol += opt.get('volume', 0)

    pcr_oi = (put_oi / call_oi) if call_oi > 0 else 0
    pcr_vol = (put_vol / call_vol) if call_vol > 0 else 0

    return {
        'pcr_oi': pcr_oi,
        'pcr_vol': pcr_vol,
        'put_oi': put_oi,
        'call_oi': call_oi,
        'put_vol': put_vol,
        'call_vol': call_vol
    }

def get_atm_strike(spot_price):
    """Get ATM strike (nearest 50 multiple)"""
    return round(spot_price / 50) * 50

def main():
    print("\n" + "="*80)
    print("StocksBlitz SDK - Enhanced Monitor with Greeks".center(80))
    print("="*80 + "\n")

    # Authenticate
    print("🔐 Authenticating...")
    client = TradingClient.from_credentials(
        api_url=API_URL,
        user_service_url=USER_SERVICE_URL,
        username=USERNAME,
        password=PASSWORD
    )
    print(f"✓ Authenticated as {USERNAME}\n")

    # Get initial snapshot
    print("📊 Fetching initial data...")
    snapshot = get_backend_snapshot()

    underlying = snapshot.get('underlying')
    options = snapshot.get('options', {})

    print(f"✓ Found {len(options)} instruments")

    if underlying:
        ltp = underlying.get('close', 0)
        print(f"✓ NIFTY @ ₹{ltp:,.2f}\n")

    print("="*80)
    print("Starting live monitor (Press Ctrl+C to stop)".center(80))
    print("="*80 + "\n")

    iteration = 0
    try:
        while True:
            iteration += 1
            time.sleep(5)

            # Get fresh snapshot
            snapshot = get_backend_snapshot()
            underlying = snapshot.get('underlying')
            options_data = snapshot.get('options', {})

            if not underlying:
                print("⚠ No underlying data available")
                continue

            spot = underlying.get('close', 0)
            atm_strike = get_atm_strike(spot)

            print(f"\n{'═'*80}")
            print(f"Iteration {iteration} - {datetime.now().strftime('%H:%M:%S')}")
            print(f"{'═'*80}")

            # Show underlying with OHLC
            print(f"\n📊 NIFTY 50 Index")
            print(f"{'─'*80}")
            ltp = underlying.get('close', 0)
            open_price = underlying.get('open', 0)
            high = underlying.get('high', 0)
            low = underlying.get('low', 0)
            vol = underlying.get('volume', 0)

            change = ltp - open_price
            change_pct = (change / open_price * 100) if open_price > 0 else 0

            print(f"LTP: ₹{ltp:>10,.2f}  ", end="")
            print(f"Change: {change:>+8,.2f} ({change_pct:>+6.2f}%)")
            print(f"O: {open_price:>8,.2f}  H: {high:>8,.2f}  L: {low:>8,.2f}  Vol: {vol:>6,}")
            print(f"ATM Strike: {atm_strike:,.0f}")

            # Calculate overall PCR
            pcr_data = calculate_pcr(options_data)
            print(f"\n📈 Market Indicators")
            print(f"{'─'*80}")
            print(f"PCR (OI):     {pcr_data['pcr_oi']:>6.3f}  ", end="")
            print(f"(Calls: {pcr_data['call_oi']:>12,}, Puts: {pcr_data['put_oi']:>12,})")
            print(f"PCR (Volume): {pcr_data['pcr_vol']:>6.3f}  ", end="")
            print(f"(Calls: {pcr_data['call_vol']:>12,}, Puts: {pcr_data['put_vol']:>12,})")

            # Show ATM options with Greeks
            print(f"\n🎯 ATM Options (Strike: {atm_strike:,.0f}) with Greeks")
            print(f"{'─'*80}")
            print(f"{'Type':<6} {'LTP':>10} {'Volume':>10} {'OI':>12} {'IV':>8} {'Delta':>8} {'Gamma':>8}")
            print(f"{'─'*80}")

            # Get ATM call and put
            atm_options = [opt for opt in options_data.values()
                          if opt.get('strike') == atm_strike and opt.get('type') in ['CE', 'PE']]

            for opt in sorted(atm_options, key=lambda x: x.get('type', ''), reverse=True):
                opt_type = opt.get('type', '')
                price = opt.get('price', 0)
                volume = opt.get('volume', 0)
                oi = opt.get('oi', 0)
                iv = opt.get('iv', 0)
                delta = opt.get('delta', 0)
                gamma = opt.get('gamma', 0)

                print(f"{opt_type:<6} ₹{price:>9,.2f} {volume:>10,} {oi:>12,} ", end="")
                print(f"{iv:>7.2%} {delta:>8.4f} {gamma:>8.6f}")

            # Show strikes around ATM with key Greeks
            print(f"\n📊 Options Chain (±150 from ATM) - Greeks Summary")
            print(f"{'─'*80}")
            print(f"{'Strike':>8} {'CE IV':>8} {'CE Δ':>8} {'CE OI':>12} | {'PE OI':>12} {'PE Δ':>8} {'PE IV':>8}")
            print(f"{'─'*80}")

            strikes_to_show = [atm_strike - 150, atm_strike - 100, atm_strike - 50,
                             atm_strike, atm_strike + 50, atm_strike + 100, atm_strike + 150]

            for strike in strikes_to_show:
                calls = [opt for opt in options_data.values()
                        if opt.get('strike') == strike and opt.get('type') == 'CE']
                puts = [opt for opt in options_data.values()
                       if opt.get('strike') == strike and opt.get('type') == 'PE']

                call = calls[0] if calls else {}
                put = puts[0] if puts else {}

                marker = " ★" if strike == atm_strike else "  "

                print(f"{strike:>8,.0f}{marker} ", end="")
                print(f"{call.get('iv', 0):>7.2%} {call.get('delta', 0):>8.4f} {call.get('oi', 0):>12,} | ", end="")
                print(f"{put.get('oi', 0):>12,} {put.get('delta', 0):>8.4f} {put.get('iv', 0):>7.2%}")

            # Show top movers by volume
            print(f"\n🔥 Top 5 Options by Volume")
            print(f"{'─'*80}")
            print(f"{'Symbol':<22} {'Type':<6} {'Strike':>8} {'LTP':>10} {'Vol':>10} {'IV':>8}")
            print(f"{'─'*80}")

            top_by_volume = sorted(options_data.values(),
                                  key=lambda x: x.get('volume', 0), reverse=True)[:5]

            for opt in top_by_volume:
                symbol = opt.get('tradingsymbol', '')[:22]
                opt_type = opt.get('type', '')
                strike = opt.get('strike', 0)
                price = opt.get('price', 0)
                volume = opt.get('volume', 0)
                iv = opt.get('iv', 0)

                print(f"{symbol:<22} {opt_type:<6} {strike:>8,.0f} ₹{price:>9,.2f} {volume:>10,} {iv:>7.2%}")

            # Show Greeks summary for ATM options
            print(f"\n📉 Greeks Summary - ATM Strike ({atm_strike:,.0f})")
            print(f"{'─'*80}")

            if atm_options:
                for opt in sorted(atm_options, key=lambda x: x.get('type', ''), reverse=True):
                    opt_type = opt.get('type', '')
                    print(f"\n{opt_type} Option:")
                    print(f"  IV (Implied Volatility): {opt.get('iv', 0):>8.2%}")
                    print(f"  Delta (Price Sensitivity): {opt.get('delta', 0):>8.4f}")
                    print(f"  Gamma (Delta Change):      {opt.get('gamma', 0):>8.6f}")
                    print(f"  Theta (Time Decay/day):    {opt.get('theta', 0):>8.4f}")
                    print(f"  Vega (Volatility Impact):  {opt.get('vega', 0):>8.4f}")

            print(f"\n{'─'*80}")
            print(f"Refreshing in 5 seconds...")

    except KeyboardInterrupt:
        print(f"\n\n{'='*80}")
        print("Monitor stopped by user".center(80))
        print(f"{'='*80}\n")

if __name__ == "__main__":
    main()
