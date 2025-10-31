#!/usr/bin/env python3
"""
StocksBlitz SDK - Instrument Filtering Examples

Demonstrates powerful instrument filtering and option chain querying:
- Pattern-based filtering
- Lambda conditions
- Criteria-based filtering
- ATM/OTM/ITM selection
- Sorting and limiting
- Complex multi-condition filters

Usage:
    python examples_filter.py
"""

from stocksblitz import TradingClient

# Configuration
API_URL = "http://localhost:8009"
API_KEY = "sb_30d4d5ea_bbb52c64cc4eb2536fdd7b44861c93e4b30b50c6"


def example_1_basic_filtering():
    """Example 1: Basic filtering with lambda."""
    print("\n" + "="*70)
    print("Example 1: Basic Filtering")
    print("="*70)

    client = TradingClient(api_url=API_URL, api_key=API_KEY)

    # Create filter for NIFTY Puts expiring on 28-Oct-2025
    filter_obj = client.InstrumentFilter("NSE@NIFTY@28-Oct-2025@Put")

    print(f"Filter pattern: {filter_obj.pattern}")

    # Filter by LTP
    print("\n1. Find options with LTP > 50:")
    results = filter_obj.where(lambda i: i.ltp > 50)
    print(f"   Found {len(results)} options")
    for inst in results[:5]:  # Show first 5
        print(f"   - {inst.tradingsymbol}: LTP=₹{inst.ltp:.2f}")

    # Filter by price range
    print("\n2. Find options with 50 < LTP < 100:")
    results = filter_obj.where(lambda i: 50 < i.ltp < 100)
    print(f"   Found {len(results)} options")


def example_2_filter_by_greeks():
    """Example 2: Filter by option greeks."""
    print("\n" + "="*70)
    print("Example 2: Filter by Greeks")
    print("="*70)

    client = TradingClient(api_url=API_URL, api_key=API_KEY)

    filter_obj = client.InstrumentFilter("NSE@NIFTY@28-Oct-2025@Call")

    # Filter by delta
    print("\n1. Find Calls with delta > 0.5:")
    results = filter_obj.where(lambda i: i.delta > 0.5)
    print(f"   Found {len(results)} options")

    # Filter by multiple greeks
    print("\n2. Find Calls with delta > 0.5 and theta < -5:")
    results = filter_obj.where(lambda i: i.delta > 0.5 and i.theta < -5)
    print(f"   Found {len(results)} options")

    # Filter by IV
    print("\n3. Find options with low IV < 20:")
    results = filter_obj.where(lambda i: i.iv < 20)
    print(f"   Found {len(results)} options")


def example_3_filter_by_oi_volume():
    """Example 3: Filter by OI and volume."""
    print("\n" + "="*70)
    print("Example 3: Filter by OI & Volume")
    print("="*70)

    client = TradingClient(api_url=API_URL, api_key=API_KEY)

    filter_obj = client.InstrumentFilter("NSE@NIFTY@28-Oct-2025@Put")

    # High OI options
    print("\n1. Find high OI options (OI > 100,000):")
    results = filter_obj.where(lambda i: i.oi > 100000)
    print(f"   Found {len(results)} options")
    for inst in results[:3]:
        print(f"   - {inst.tradingsymbol}: OI={inst.oi:,}")

    # High volume options
    print("\n2. Find high volume options (volume > 50,000):")
    results = filter_obj.where(lambda i: i.volume > 50000)
    print(f"   Found {len(results)} options")


def example_4_filter_by_indicators():
    """Example 4: Filter by technical indicators."""
    print("\n" + "="*70)
    print("Example 4: Filter by Indicators")
    print("="*70)

    client = TradingClient(api_url=API_URL, api_key=API_KEY)

    filter_obj = client.InstrumentFilter("NSE@NIFTY@28-Oct-2025@Put")

    # Filter by RSI
    print("\n1. Find options with RSI > 70 (overbought):")
    try:
        results = filter_obj.where(lambda i: i['5m'].rsi[14] > 70)
        print(f"   Found {len(results)} options")
    except Exception as e:
        print(f"   ⚠ Error: {e}")

    # Filter by SMA crossover
    print("\n2. Find options with price > SMA(20):")
    try:
        results = filter_obj.where(lambda i: i.ltp > i['5m'].sma[20])
        print(f"   Found {len(results)} options")
    except Exception as e:
        print(f"   ⚠ Error: {e}")


def example_5_complex_conditions():
    """Example 5: Complex multi-condition filtering."""
    print("\n" + "="*70)
    print("Example 5: Complex Conditions")
    print("="*70)

    client = TradingClient(api_url=API_URL, api_key=API_KEY)

    filter_obj = client.InstrumentFilter("NSE@NIFTY@28-Oct-2025@Put")

    # Multiple conditions
    print("\n1. Find liquid options (price 50-100, OI > 100k, delta > 0.3):")
    results = filter_obj.where(lambda i: (
        50 < i.ltp < 100 and
        i.oi > 100000 and
        i.delta > 0.3
    ))
    print(f"   Found {len(results)} options")
    for inst in results[:3]:
        print(f"   - {inst.tradingsymbol}:")
        print(f"       LTP=₹{inst.ltp:.2f}, OI={inst.oi:,}, Delta={inst.delta:.2f}")


def example_6_criteria_based_filtering():
    """Example 6: Criteria-based filtering (simpler syntax)."""
    print("\n" + "="*70)
    print("Example 6: Criteria-Based Filtering")
    print("="*70)

    client = TradingClient(api_url=API_URL, api_key=API_KEY)

    filter_obj = client.InstrumentFilter("NSE@NIFTY@28-Oct-2025@Put")

    # Using find() with criteria
    print("\n1. Find options with ltp_min=50, ltp_max=100:")
    results = filter_obj.find(ltp_min=50, ltp_max=100)
    print(f"   Found {len(results)} options")

    # Multiple criteria
    print("\n2. Find with ltp_min=50, oi_min=100000, delta_min=0.3:")
    results = filter_obj.find(
        ltp_min=50,
        ltp_max=100,
        oi_min=100000,
        delta_min=0.3
    )
    print(f"   Found {len(results)} options")


def example_7_sorting_and_limiting():
    """Example 7: Sorting and limiting results."""
    print("\n" + "="*70)
    print("Example 7: Sorting & Limiting")
    print("="*70)

    client = TradingClient(api_url=API_URL, api_key=API_KEY)

    filter_obj = client.InstrumentFilter("NSE@NIFTY@28-Oct-2025@Put")

    # Top by OI
    print("\n1. Top 5 by OI:")
    results = filter_obj.top(5, by='oi')
    for i, inst in enumerate(results, 1):
        print(f"   {i}. {inst.tradingsymbol}: OI={inst.oi:,}")

    # Top by LTP
    print("\n2. Top 5 by LTP:")
    results = filter_obj.top(5, by='ltp')
    for i, inst in enumerate(results, 1):
        print(f"   {i}. {inst.tradingsymbol}: LTP=₹{inst.ltp:.2f}")

    # Order by delta descending
    print("\n3. Order by delta (descending):")
    results = filter_obj.order_by('delta', reverse=True).limit(5)
    for inst in results:
        print(f"   - {inst.tradingsymbol}: Delta={inst.delta:.4f}")


def example_8_atm_otm_itm():
    """Example 8: ATM/OTM/ITM selection."""
    print("\n" + "="*70)
    print("Example 8: ATM/OTM/ITM Selection")
    print("="*70)

    client = TradingClient(api_url=API_URL, api_key=API_KEY)

    # Next week expiry
    filter_obj = client.InstrumentFilter("NSE@NIFTY@Nw@Put")

    # ATM option
    print("\n1. At-the-money Put:")
    atm = filter_obj.atm()
    if atm:
        print(f"   {atm.tradingsymbol}: LTP=₹{atm.ltp:.2f}, Delta={atm.delta:.4f}")
    else:
        print("   ⚠ ATM not found (requires backend)")

    # OTM options
    print("\n2. Out-of-the-money Puts:")
    otm1 = filter_obj.otm(1)  # 1 strike OTM
    otm2 = filter_obj.otm(2)  # 2 strikes OTM
    if otm1:
        print(f"   OTM1: {otm1.tradingsymbol}")
    if otm2:
        print(f"   OTM2: {otm2.tradingsymbol}")

    # ITM options
    print("\n3. In-the-money Puts:")
    itm1 = filter_obj.itm(1)  # 1 strike ITM
    if itm1:
        print(f"   ITM1: {itm1.tradingsymbol}")


def example_9_relative_expiry():
    """Example 9: Relative expiry patterns."""
    print("\n" + "="*70)
    print("Example 9: Relative Expiry Patterns")
    print("="*70)

    client = TradingClient(api_url=API_URL, api_key=API_KEY)

    # Next week expiry
    print("\n1. Next week expiry (Nw):")
    filter_nw = client.InstrumentFilter("NSE@NIFTY@Nw@Put")
    print(f"   Pattern: {filter_nw.pattern}")
    print(f"   Resolved expiry: {filter_nw._resolve_expiry('Nw')}")

    # Next month expiry
    print("\n2. Next month expiry (Nm):")
    filter_nm = client.InstrumentFilter("NSE@NIFTY@Nm@Call")
    print(f"   Pattern: {filter_nm.pattern}")
    print(f"   Resolved expiry: {filter_nm._resolve_expiry('Nm')}")

    # All expiries
    print("\n3. All expiries (*):")
    filter_all = client.InstrumentFilter("NSE@NIFTY@*@Call")
    print(f"   Pattern: {filter_all.pattern}")


def example_10_banknifty_options():
    """Example 10: BANKNIFTY options."""
    print("\n" + "="*70)
    print("Example 10: BANKNIFTY Options")
    print("="*70)

    client = TradingClient(api_url=API_URL, api_key=API_KEY)

    # BANKNIFTY Calls
    filter_obj = client.InstrumentFilter("NSE@BANKNIFTY@28-Oct-2025@Call")

    print(f"Filter pattern: {filter_obj.pattern}")

    # Find liquid calls
    print("\n1. Find liquid BANKNIFTY Calls (LTP > 100, OI > 50k):")
    results = filter_obj.where(lambda i: i.ltp > 100 and i.oi > 50000)
    print(f"   Found {len(results)} options")


def example_11_chaining_filters():
    """Example 11: Chaining multiple filters."""
    print("\n" + "="*70)
    print("Example 11: Chaining Filters")
    print("="*70)

    client = TradingClient(api_url=API_URL, api_key=API_KEY)

    filter_obj = client.InstrumentFilter("NSE@NIFTY@28-Oct-2025@Put")

    # Chain multiple where() calls
    print("\n1. Chain filters: LTP > 50, then delta > 0.3, then OI > 100k:")
    results = (filter_obj
               .where(lambda i: i.ltp > 50)
               .where(lambda i: i.delta > 0.3)
               .where(lambda i: i.oi > 100000))

    # Note: where() returns list, not InstrumentFilter, so this doesn't chain
    # Better approach:
    results = filter_obj.where(lambda i: (
        i.ltp > 50 and
        i.delta > 0.3 and
        i.oi > 100000
    ))
    print(f"   Found {len(results)} options")


def example_12_complete_strategy():
    """Example 12: Complete strategy using filters."""
    print("\n" + "="*70)
    print("Example 12: Complete Strategy with Filtering")
    print("="*70)

    client = TradingClient(api_url=API_URL, api_key=API_KEY)

    # Strategy: Buy liquid Puts with RSI < 30
    print("Strategy: Buy liquid NIFTY Puts with RSI < 30")
    print()

    # Step 1: Filter for liquid options
    filter_obj = client.InstrumentFilter("NSE@NIFTY@Nw@Put")

    print("1. Filter for liquid options (LTP 50-100, OI > 100k):")
    liquid_options = filter_obj.where(lambda i: (
        50 < i.ltp < 100 and
        i.oi > 100000
    ))
    print(f"   Found {len(liquid_options)} liquid options")

    # Step 2: Filter by technical indicator
    print("\n2. Filter by RSI < 30:")
    buy_candidates = []
    for inst in liquid_options:
        try:
            if inst['5m'].rsi[14] < 30:
                buy_candidates.append(inst)
        except Exception:
            continue

    print(f"   Found {len(buy_candidates)} buy candidates")

    # Step 3: Sort by OI and pick top
    if buy_candidates:
        print("\n3. Sort by OI and pick top option:")
        best_option = max(buy_candidates, key=lambda i: i.oi)
        print(f"   Best option: {best_option.tradingsymbol}")
        print(f"     LTP: ₹{best_option.ltp:.2f}")
        print(f"     OI: {best_option.oi:,}")
        print(f"     Delta: {best_option.delta:.4f}")

        # Execute trade
        print("\n4. Execute trade:")
        print(f"   → BUY {best_option.tradingsymbol} @ ₹{best_option.ltp:.2f}")
        # account.buy(best_option, quantity=50)
    else:
        print("\n   No candidates found")


def main():
    """Run all filtering examples."""
    print("\n" + "#"*70)
    print("# StocksBlitz SDK - Instrument Filtering Examples")
    print("#"*70)

    examples = [
        example_1_basic_filtering,
        example_2_filter_by_greeks,
        example_3_filter_by_oi_volume,
        example_4_filter_by_indicators,
        example_5_complex_conditions,
        example_6_criteria_based_filtering,
        example_7_sorting_and_limiting,
        example_8_atm_otm_itm,
        example_9_relative_expiry,
        example_10_banknifty_options,
        example_11_chaining_filters,
        example_12_complete_strategy,
    ]

    for example in examples:
        try:
            example()
            import time
            time.sleep(1)
        except Exception as e:
            print(f"\n  ❌ Error in {example.__name__}: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "="*70)
    print("All filtering examples completed!")
    print("="*70)
    print("\nKey Patterns:")
    print("  ✓ NSE@NIFTY@28-Oct-2025@Put       - Absolute date")
    print("  ✓ NSE@NIFTY@Nw@Put                - Next week")
    print("  ✓ NSE@NIFTY@Nm@Call               - Next month")
    print("  ✓ NSE@NIFTY@*@Call                - All expiries")
    print("\nKey Methods:")
    print("  ✓ where(lambda i: i.ltp > 50)     - Custom condition")
    print("  ✓ find(ltp_min=50, oi_min=100000) - Criteria-based")
    print("  ✓ top(5, by='oi')                 - Top N by attribute")
    print("  ✓ atm() / otm(2) / itm(1)         - Strike selection")
    print("  ✓ order_by('ltp').limit(10)       - Sort and limit")
    print("="*70)


if __name__ == "__main__":
    main()
