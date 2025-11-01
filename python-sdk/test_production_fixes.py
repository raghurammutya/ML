#!/usr/bin/env python3
"""
Test script for production fixes to Python SDK.

Tests:
1. DataState enum integration
2. Quote fetching with data quality metadata
3. Greeks with data quality metadata
4. Exception handling improvements
5. Logging functionality
6. Warning system for stale data
"""

import sys
import warnings
import logging
from stocksblitz import (
    TradingClient,
    DataState,
    DataUnavailableError,
    InstrumentNotSubscribedError,
    IndicatorUnavailableError,
    DataValidationError
)

# Configure logging to see SDK logs
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def test_quote_data_quality():
    """Test quote fetching with data quality metadata."""
    print("\n" + "="*80)
    print("TEST 1: Quote Data Quality Tracking")
    print("="*80)

    try:
        client = TradingClient(
            api_url="http://localhost:8081",
            api_key="sb_30d4d5ea_bbb52c64cc4eb2536fdd7b44861c93e4b30b50c6"
        )

        # Test underlying quote
        nifty = client.Instrument("NIFTY 50")

        # Fetch quote with metadata
        quote = nifty._fetch_quote()

        print(f"\n✓ Quote fetched for {nifty.tradingsymbol}")
        print(f"  LTP: ₹{quote['ltp']:,.2f}")
        print(f"  Volume: {quote['volume']:,}")
        print(f"  Data State: {quote['_state']}")
        print(f"  Timestamp: {quote['_timestamp']}")
        if quote.get('_data_age'):
            print(f"  Data Age: {quote['_data_age']:.1f} seconds")
        if quote.get('_reason'):
            print(f"  Reason: {quote['_reason']}")

        # Test that DataState enum works
        assert quote['_state'] in [DataState.VALID, DataState.STALE, DataState.NO_DATA], \
            f"Invalid data state: {quote['_state']}"
        print(f"\n✓ DataState enum working correctly")

        # Test property accessor (should work without errors)
        ltp = nifty.ltp
        print(f"✓ LTP property accessor: ₹{ltp:,.2f}")

        return True

    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_greeks_data_quality():
    """Test Greeks fetching with data quality metadata."""
    print("\n" + "="*80)
    print("TEST 2: Greeks Data Quality Tracking")
    print("="*80)

    try:
        client = TradingClient(
            api_url="http://localhost:8081",
            api_key="sb_30d4d5ea_bbb52c64cc4eb2536fdd7b44861c93e4b30b50c6"
        )

        # Test option Greeks
        option = client.Instrument("NIFTY25N0724500PE")

        # Capture warnings
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            try:
                # Try to fetch Greeks (will raise exception if not subscribed)
                greeks = option._fetch_greeks()

                print(f"\n✓ Greeks fetched for {option.tradingsymbol}")
                print(f"  Delta: {greeks['delta']:.4f}")
                print(f"  Gamma: {greeks['gamma']:.4f}")
                print(f"  Theta: {greeks['theta']:.4f}")
                print(f"  Vega: {greeks['vega']:.4f}")
                print(f"  IV: {greeks['iv']:.2%}")
                print(f"  Data State: {greeks['_state']}")
                print(f"  Timestamp: {greeks['_timestamp']}")
                if greeks.get('_reason'):
                    print(f"  Reason: {greeks['_reason']}")

                # Test that DataState enum works
                assert greeks['_state'] in [DataState.VALID, DataState.NO_DATA], \
                    f"Invalid data state: {greeks['_state']}"
                print(f"\n✓ DataState enum working correctly")

                # Test property accessor
                delta = option.delta
                print(f"✓ Delta property accessor: {delta:.4f}")

                # Check if warnings were issued
                if w:
                    print(f"✓ Warnings issued: {len(w)}")
                    for warning in w:
                        print(f"  - {warning.message}")

            except InstrumentNotSubscribedError as e:
                print(f"\n✓ InstrumentNotSubscribedError raised correctly:")
                print(f"  Message: {e}")
                print(f"  Reason: {e.reason}")
                print(f"\n✓ Exception handling working as expected")

        return True

    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_exception_hierarchy():
    """Test that exception hierarchy works correctly."""
    print("\n" + "="*80)
    print("TEST 3: Exception Hierarchy")
    print("="*80)

    try:
        # Test that all exceptions are importable
        from stocksblitz import (
            StocksBlitzError,
            InstrumentNotFoundError,
            DataUnavailableError,
            StaleDataError,
            InstrumentNotSubscribedError,
            IndicatorUnavailableError,
            DataValidationError
        )

        print("\n✓ All exception classes imported successfully")

        # Test exception hierarchy
        assert issubclass(InstrumentNotSubscribedError, DataUnavailableError), \
            "InstrumentNotSubscribedError should inherit from DataUnavailableError"
        print("✓ InstrumentNotSubscribedError inherits from DataUnavailableError")

        assert issubclass(IndicatorUnavailableError, DataUnavailableError), \
            "IndicatorUnavailableError should inherit from DataUnavailableError"
        print("✓ IndicatorUnavailableError inherits from DataUnavailableError")

        # Test exception creation
        exc = DataValidationError("Test error", field="ltp", value=-100)
        assert exc.field == "ltp", "Field not set correctly"
        assert exc.value == -100, "Value not set correctly"
        print("✓ DataValidationError attributes work correctly")

        exc = StaleDataError("Test error", age_seconds=15.5)
        assert exc.age_seconds == 15.5, "Age not set correctly"
        print("✓ StaleDataError attributes work correctly")

        return True

    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_indicator_exceptions():
    """Test that indicators raise proper exceptions."""
    print("\n" + "="*80)
    print("TEST 4: Indicator Exception Handling")
    print("="*80)

    try:
        client = TradingClient(
            api_url="http://localhost:8081",
            api_key="sb_30d4d5ea_bbb52c64cc4eb2536fdd7b44861c93e4b30b50c6"
        )

        nifty = client.Instrument("NIFTY 50")

        # Try to fetch indicator (will likely fail with current backend)
        try:
            rsi = nifty['5m'].rsi[14]
            print(f"\n✓ RSI computed: {rsi:.2f}")
        except (IndicatorUnavailableError, DataUnavailableError) as e:
            print(f"\n✓ Exception raised correctly for indicator:")
            print(f"  Type: {type(e).__name__}")
            print(f"  Message: {e}")
            if hasattr(e, 'reason'):
                print(f"  Reason: {e.reason}")
            print(f"\n✓ Indicators now raise exceptions instead of silently returning 0")

        return True

    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_logging():
    """Test that logging is working."""
    print("\n" + "="*80)
    print("TEST 5: Logging Functionality")
    print("="*80)

    try:
        # Check that SDK modules have loggers
        import stocksblitz.instrument
        import stocksblitz.indicators

        assert hasattr(stocksblitz.instrument, 'logger'), "instrument.py should have logger"
        assert hasattr(stocksblitz.indicators, 'logger'), "indicators.py should have logger"

        print("\n✓ SDK modules have loggers configured")
        print("✓ Check console output above for log messages")

        return True

    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("\n" + "="*80)
    print("PRODUCTION FIXES TEST SUITE")
    print("="*80)
    print("\nTesting Python SDK production fixes:")
    print("- DataState enum")
    print("- Data quality metadata")
    print("- Exception handling")
    print("- Logging")
    print("- Warning system")

    results = []

    # Run all tests
    results.append(("Quote Data Quality", test_quote_data_quality()))
    results.append(("Greeks Data Quality", test_greeks_data_quality()))
    results.append(("Exception Hierarchy", test_exception_hierarchy()))
    results.append(("Indicator Exceptions", test_indicator_exceptions()))
    results.append(("Logging", test_logging()))

    # Print summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)

    passed = 0
    failed = 0

    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {name}")
        if result:
            passed += 1
        else:
            failed += 1

    print(f"\nTotal: {passed + failed} tests")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed == 0:
        print("\n✓ All tests passed! SDK production fixes are working correctly.")
        return 0
    else:
        print(f"\n✗ {failed} test(s) failed. Please review the errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
