#!/usr/bin/env python3
"""
Simple Tick Monitor - Clean version focusing on core tick data
Works with live and mock data from backend
"""

import sys
sys.path.insert(0, '/mnt/stocksblitz-data/Quantagro/tradingview-viz/python-sdk')

import time
import requests
from datetime import datetime

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

def main():
    print("\n" + "="*80)
    print("StocksBlitz SDK - Simple Tick Monitor".center(80))
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
        print(f"✓ NIFTY: {underlying.get('symbol')} @ ₹{ltp:,.2f}")
    
    # Get some sample options (top 10 by volume)
    opt_list = list(options.values())
    opt_list.sort(key=lambda x: x.get('volume', 0), reverse=True)
    sample_options = [opt['tradingsymbol'] for opt in opt_list[:10] if 'NIFTY25N04' in opt['tradingsymbol']]
    
    print(f"✓ Monitoring {len(sample_options)} top options by volume\n")
    
    print("="*80)
    print("Starting live monitor (Press Ctrl+C to stop)".center(80))
    print("="*80 + "\n")
    
    iteration = 0
    try:
        while True:
            iteration += 1
            time.sleep(3)
            
            # Get fresh snapshot
            snapshot = get_backend_snapshot()
            underlying = snapshot.get('underlying')
            options_data = snapshot.get('options', {})
            
            print(f"\n{'─'*80}")
            print(f"Iteration {iteration} - {datetime.now().strftime('%H:%M:%S')}")
            print(f"{'─'*80}")
            
            # Show underlying
            if underlying:
                ltp = underlying.get('close', 0)
                vol = underlying.get('volume', 0)
                open_price = underlying.get('open', 0)
                high = underlying.get('high', 0)
                low = underlying.get('low', 0)
                print(f"\n📊 {underlying.get('symbol', 'NIFTY')}: ₹{ltp:,.2f}  O:{open_price:,.2f}  H:{high:,.2f}  L:{low:,.2f}  Vol:{vol:,}")
            
            # Show top options
            print(f"\n📈 Top Options (by Volume):\n")
            print(f"{'Symbol':<20} {'Type':<6} {'Strike':<8} {'LTP':<10} {'Volume':<12} {'OI':<12}")
            print("─" * 80)
            
            for opt_symbol in sample_options[:5]:
                token = None
                for tok, opt in options_data.items():
                    if opt.get('tradingsymbol') == opt_symbol:
                        token = tok
                        break
                
                if token:
                    opt = options_data[token]
                    symbol = opt.get('tradingsymbol', '')
                    opt_type = opt.get('type', '')
                    strike = opt.get('strike', 0)
                    price = opt.get('price', 0)
                    volume = opt.get('volume', 0)
                    oi = opt.get('oi', 0)
                    
                    print(f"{symbol:<20} {opt_type:<6} {strike:<8.0f} ₹{price:<9.2f} {volume:<12,} {oi:<12,}")
            
            # Show futures
            futures = [(tok, opt) for tok, opt in options_data.items() if opt.get('type') == 'FUT']
            if futures:
                print(f"\n📊 Futures:\n")
                for tok, fut in futures[:2]:
                    symbol = fut.get('tradingsymbol', '')
                    price = fut.get('price', 0)
                    volume = fut.get('volume', 0)
                    oi = fut.get('oi', 0)
                    print(f"  {symbol:<20} ₹{price:>10,.2f}  Vol: {volume:>8,}  OI: {oi:>10,}")
            
    except KeyboardInterrupt:
        print(f"\n\n{'='*80}")
        print("Monitor stopped by user".center(80))
        print(f"{'='*80}\n")

if __name__ == "__main__":
    main()
