#!/usr/bin/env python3
"""
Quick Start Guide for StocksBlitz SDK

This script demonstrates the basic usage of the SDK.

Usage:
    python quickstart.py
"""

import sys
sys.path.insert(0, '.')  # Add current directory to path

from stocksblitz import TradingClient

# Configuration
API_URL = "http://localhost:8009"
API_KEY = "sb_30d4d5ea_bbb52c64cc4eb2536fdd7b44861c93e4b30b50c6"


def main():
    print("=" * 70)
    print("StocksBlitz Python SDK - Quick Start")
    print("=" * 70)

    # Step 1: Initialize client
    print("\n1. Initializing client...")
    client = TradingClient(api_url=API_URL, api_key=API_KEY)
    print(f"   ✓ Client created: {client}")

    # Step 2: Create instrument
    print("\n2. Creating instrument...")
    inst = client.Instrument("NIFTY25N0424500PE")
    print(f"   ✓ Instrument: {inst.tradingsymbol}")

    # Step 3: Access market data
    print("\n3. Fetching market data...")
    try:
        ltp = inst.ltp
        volume = inst.volume
        oi = inst.oi
        print(f"   ✓ LTP: {ltp:.2f}")
        print(f"   ✓ Volume: {volume:,}")
        print(f"   ✓ OI: {oi:,}")
    except Exception as e:
        print(f"   ⚠ Error fetching market data: {e}")
        print(f"   (This is normal if backend is not running)")

    # Step 4: Access indicators
    print("\n4. Accessing technical indicators...")
    print("   Note: This requires backend API running with indicator support")
    print("   Example syntax:")
    print("   - inst['5m'].rsi[14]")
    print("   - inst['5m'].sma[20]")
    print("   - inst['5m'].macd[12, 26, 9]")
    print("   - inst['5m'].bbands[20, 2]")

    # Step 5: Create account
    print("\n5. Creating account instance...")
    account = client.Account()
    print(f"   ✓ Account: {account}")

    # Step 6: Access positions (if available)
    print("\n6. Fetching positions...")
    try:
        positions = account.positions
        print(f"   ✓ Found {len(positions)} positions")
        if positions:
            for pos in positions[:3]:  # Show first 3
                print(f"     - {pos.tradingsymbol}: {pos.quantity} @ {pos.average_price:.2f}")
    except Exception as e:
        print(f"   ⚠ Error fetching positions: {e}")

    # Step 7: Access funds
    print("\n7. Fetching funds...")
    try:
        funds = account.funds
        print(f"   ✓ Available Cash: ₹{funds.available_cash:,.2f}")
        print(f"   ✓ Used Margin: ₹{funds.used_margin:,.2f}")
    except Exception as e:
        print(f"   ⚠ Error fetching funds: {e}")

    # Summary
    print("\n" + "=" * 70)
    print("Quick Start Complete!")
    print("=" * 70)
    print("\nNext steps:")
    print("1. Run full examples: python examples.py")
    print("2. Read documentation: cat README.md")
    print("3. Check implementation: cat IMPLEMENTATION.md")
    print("\nFor trading strategies, see examples 8-10 in examples.py")
    print("=" * 70)


if __name__ == "__main__":
    main()
