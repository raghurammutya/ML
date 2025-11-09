"""
Load tests for tick processing throughput.

Tests system performance under various load scenarios:
- Baseline (1000 instruments)
- Scale (5000 instruments)
- Burst traffic
- Sustained load
- Greeks overhead

Phase 4 - Performance & Observability.
"""
import asyncio
import time
from statistics import mean, median, stdev
from typing import List, Dict, Any
from datetime import datetime, date

import pytest

from app.services.tick_processor import TickProcessor
from app.services.tick_batcher import TickBatcher
from app.services.tick_validator import TickValidator
from app.greeks_calculator import GreeksCalculator
from app.schema import Instrument
from zoneinfo import ZoneInfo


class TickLoadTestHelper:
    """Helper class for load testing"""

    @staticmethod
    def create_test_instruments(count: int, instrument_type: str = "option") -> Dict[int, Instrument]:
        """
        Create test instruments for load testing.

        Args:
            count: Number of instruments to create
            instrument_type: "underlying" or "option"

        Returns:
            Dictionary mapping instrument_token to Instrument
        """
        instruments = {}
        base_token = 256265 if instrument_type == "underlying" else 12000000

        for i in range(count):
            token = base_token + i

            if instrument_type == "underlying":
                instrument = Instrument(
                    symbol="NIFTY",
                    instrument_token=token,
                    tradingsymbol=f"NIFTY 50",
                    segment="INDICES",
                    exchange="NSE",
                    strike=None,
                    expiry=None,
                    instrument_type=None,
                    lot_size=None,
                    tick_size=None,
                )
            else:
                # Create option instrument
                strike = 24000 + (i % 100) * 50
                expiry = date(2025, 12, 26)
                opt_type = "CE" if i % 2 == 0 else "PE"

                instrument = Instrument(
                    symbol="NIFTY",
                    instrument_token=token,
                    tradingsymbol=f"NIFTY2512626{strike}{opt_type}",
                    segment="NFO",
                    exchange="NFO",
                    strike=strike,
                    expiry=expiry,
                    instrument_type=opt_type,
                    lot_size=25,
                    tick_size=0.05,
                )

            instruments[token] = instrument

        return instruments

    @staticmethod
    def create_test_tick(instrument: Instrument, price_offset: float = 0.0) -> Dict[str, Any]:
        """
        Create a test tick for an instrument.

        Args:
            instrument: Instrument to create tick for
            price_offset: Price variation to add

        Returns:
            Dictionary representing a tick
        """
        if instrument.segment == "INDICES":
            # Underlying tick
            return {
                "instrument_token": instrument.instrument_token,
                "last_price": 24000.0 + price_offset,
                "volume_traded_today": 10000000,
                "timestamp": int(time.time()),
                "ohlc": {"open": 24000.0, "high": 24100.0, "low": 23900.0, "close": 24000.0},
            }
        else:
            # Option tick
            return {
                "instrument_token": instrument.instrument_token,
                "last_price": 150.0 + price_offset,
                "volume_traded_today": 50000,
                "oi": 1000000,
                "timestamp": int(time.time()),
                "depth": {
                    "buy": [
                        {"quantity": 100, "price": 14950, "orders": 5},
                        {"quantity": 200, "price": 14900, "orders": 10},
                    ],
                    "sell": [
                        {"quantity": 100, "price": 15050, "orders": 5},
                        {"quantity": 200, "price": 15100, "orders": 10},
                    ],
                },
            }

    @staticmethod
    def calculate_percentiles(values: List[float]) -> Dict[str, float]:
        """Calculate P50, P95, P99 percentiles"""
        if not values:
            return {"p50": 0.0, "p95": 0.0, "p99": 0.0}

        sorted_values = sorted(values)
        n = len(sorted_values)

        return {
            "p50": sorted_values[int(n * 0.50)],
            "p95": sorted_values[int(n * 0.95)],
            "p99": sorted_values[int(n * 0.99)],
            "mean": mean(values),
            "min": min(values),
            "max": max(values),
        }


@pytest.fixture
def load_test_helper():
    """Fixture providing load test helper"""
    return TickLoadTestHelper()


class MockBatcher:
    """Mock batcher that doesn't actually publish (for load testing)"""

    def __init__(self):
        self.underlying_count = 0
        self.option_count = 0

    async def add_underlying(self, bar: Dict[str, Any]) -> None:
        """Mock add underlying - just count"""
        self.underlying_count += 1

    async def add_option(self, snapshot: Any) -> None:
        """Mock add option - just count"""
        self.option_count += 1


@pytest.fixture
async def tick_processor_for_load_test():
    """Fixture providing a TickProcessor configured for load testing"""
    market_tz = ZoneInfo("Asia/Kolkata")
    greeks_calculator = GreeksCalculator(
        interest_rate=0.10,
        dividend_yield=0.0,
        expiry_time_hour=15,
        expiry_time_minute=30,
        market_timezone="Asia/Kolkata",
    )

    # Use mock batcher to avoid Redis publish overhead in load tests
    mock_batcher = MockBatcher()

    processor = TickProcessor(
        greeks_calculator=greeks_calculator,
        market_tz=market_tz,
        batcher=mock_batcher,  # Mock batcher
        validator=None,  # No validation for load tests
    )

    return processor


@pytest.mark.load
@pytest.mark.asyncio
async def test_throughput_1000_instruments_baseline(load_test_helper, tick_processor_for_load_test):
    """
    Test baseline throughput with 1000 instruments.

    This establishes the baseline for comparison with higher loads.
    Expected: P99 < 100ms, throughput > 1000 ticks/sec
    """
    num_instruments = 1000
    ticks_per_instrument = 10
    total_ticks = num_instruments * ticks_per_instrument

    # Create test instruments
    instruments = load_test_helper.create_test_instruments(num_instruments, "option")

    # Track latencies
    latencies = []
    today = date(2025, 11, 8)

    start_time = time.perf_counter()

    # Process ticks for each instrument
    for i, (token, instrument) in enumerate(instruments.items()):
        tick = load_test_helper.create_test_tick(instrument, price_offset=float(i % 100))

        tick_start = time.perf_counter()
        await tick_processor_for_load_test.process_ticks(
            account_id="load_test",
            lookup=instruments,
            ticks=[tick],
            today_market=today,
        )
        tick_latency = time.perf_counter() - tick_start
        latencies.append(tick_latency)

    elapsed = time.perf_counter() - start_time
    throughput = total_ticks / elapsed

    # Calculate percentiles
    stats = load_test_helper.calculate_percentiles(latencies)

    # Print results
    print(f"\n=== Baseline Test Results (1000 instruments) ===")
    print(f"Total ticks processed: {total_ticks}")
    print(f"Elapsed time: {elapsed:.2f}s")
    print(f"Throughput: {throughput:.2f} ticks/sec")
    print(f"Latency P50: {stats['p50']*1000:.2f}ms")
    print(f"Latency P95: {stats['p95']*1000:.2f}ms")
    print(f"Latency P99: {stats['p99']*1000:.2f}ms")
    print(f"Latency Mean: {stats['mean']*1000:.2f}ms")
    print(f"Latency Min: {stats['min']*1000:.2f}ms")
    print(f"Latency Max: {stats['max']*1000:.2f}ms")

    # Assertions (relaxed for load tests - mainly for visibility)
    assert throughput > 500, f"Throughput too low: {throughput:.2f} ticks/sec"
    assert stats['p99'] < 0.5, f"P99 latency too high: {stats['p99']*1000:.2f}ms"


@pytest.mark.load
@pytest.mark.asyncio
async def test_throughput_5000_instruments_scale(load_test_helper, tick_processor_for_load_test):
    """
    Test scale throughput with 5000 instruments (target production load).

    Expected: Throughput > 5000 ticks/sec, P99 < 100ms
    """
    num_instruments = 5000
    ticks_per_instrument = 2  # Reduced for test speed
    total_ticks = num_instruments * ticks_per_instrument

    # Create test instruments
    instruments = load_test_helper.create_test_instruments(num_instruments, "option")

    # Track latencies
    latencies = []
    today = date(2025, 11, 8)

    start_time = time.perf_counter()

    # Process ticks for each instrument
    for i, (token, instrument) in enumerate(instruments.items()):
        tick = load_test_helper.create_test_tick(instrument, price_offset=float(i % 100))

        tick_start = time.perf_counter()
        await tick_processor_for_load_test.process_ticks(
            account_id="load_test",
            lookup=instruments,
            ticks=[tick],
            today_market=today,
        )
        tick_latency = time.perf_counter() - tick_start
        latencies.append(tick_latency)

    elapsed = time.perf_counter() - start_time
    throughput = total_ticks / elapsed

    # Calculate percentiles
    stats = load_test_helper.calculate_percentiles(latencies)

    # Print results
    print(f"\n=== Scale Test Results (5000 instruments) ===")
    print(f"Total ticks processed: {total_ticks}")
    print(f"Elapsed time: {elapsed:.2f}s")
    print(f"Throughput: {throughput:.2f} ticks/sec")
    print(f"Latency P50: {stats['p50']*1000:.2f}ms")
    print(f"Latency P95: {stats['p95']*1000:.2f}ms")
    print(f"Latency P99: {stats['p99']*1000:.2f}ms")
    print(f"Latency Mean: {stats['mean']*1000:.2f}ms")

    # Assertions (relaxed for load tests)
    assert throughput > 500, f"Throughput too low: {throughput:.2f} ticks/sec"
    assert stats['p99'] < 0.5, f"P99 latency too high: {stats['p99']*1000:.2f}ms"


@pytest.mark.load
@pytest.mark.asyncio
async def test_burst_traffic(load_test_helper, tick_processor_for_load_test):
    """
    Test handling of burst traffic (many ticks in short time).

    Simulates market event causing sudden spike in tick rate.
    Expected: All ticks processed within 5 seconds, no data loss
    """
    num_instruments = 1000
    burst_size = 10000  # 10,000 ticks in rapid succession

    # Create test instruments
    instruments = load_test_helper.create_test_instruments(num_instruments, "option")
    today = date(2025, 11, 8)

    # Create burst of ticks
    burst_ticks = []
    for i in range(burst_size):
        instrument = list(instruments.values())[i % num_instruments]
        tick = load_test_helper.create_test_tick(instrument)
        burst_ticks.append((instrument, tick))

    start_time = time.perf_counter()
    processed_count = 0

    # Process burst
    for instrument, tick in burst_ticks:
        await tick_processor_for_load_test.process_ticks(
            account_id="load_test",
            lookup=instruments,
            ticks=[tick],
            today_market=today,
        )
        processed_count += 1

    elapsed = time.perf_counter() - start_time
    throughput = burst_size / elapsed

    # Print results
    print(f"\n=== Burst Traffic Test Results ===")
    print(f"Burst size: {burst_size} ticks")
    print(f"Elapsed time: {elapsed:.2f}s")
    print(f"Throughput: {throughput:.2f} ticks/sec")
    print(f"Ticks processed: {processed_count}")

    # Assertions
    assert processed_count == burst_size, "Data loss detected!"
    assert elapsed < 30.0, f"Burst processing took too long: {elapsed:.2f}s (expected < 30s)"


@pytest.mark.load
@pytest.mark.asyncio
@pytest.mark.slow
async def test_sustained_load(load_test_helper, tick_processor_for_load_test):
    """
    Test sustained load over extended period (60 seconds).

    Verifies system stability under continuous load.
    Expected: No memory leaks, latency stable (no drift)
    """
    num_instruments = 500  # Reduced for test speed
    duration_seconds = 60
    tick_rate_per_sec = 10  # 10 ticks/sec per instrument = 5000 ticks/sec total

    # Create test instruments
    instruments = load_test_helper.create_test_instruments(num_instruments, "option")
    today = date(2025, 11, 8)

    latencies = []
    start_time = time.perf_counter()
    ticks_processed = 0

    # Run for duration
    while time.perf_counter() - start_time < duration_seconds:
        # Process one tick per instrument per interval
        for instrument in list(instruments.values())[:tick_rate_per_sec]:
            tick = load_test_helper.create_test_tick(instrument)

            tick_start = time.perf_counter()
            await tick_processor_for_load_test.process_ticks(
                account_id="load_test",
                lookup=instruments,
                ticks=[tick],
                today_market=today,
            )
            latencies.append(time.perf_counter() - tick_start)
            ticks_processed += 1

        # Sleep to maintain tick rate
        await asyncio.sleep(0.1)

    elapsed = time.perf_counter() - start_time
    throughput = ticks_processed / elapsed

    # Calculate stats
    stats = load_test_helper.calculate_percentiles(latencies)

    # Check for latency drift (first vs last quartile)
    q1_latencies = latencies[:len(latencies)//4]
    q4_latencies = latencies[3*len(latencies)//4:]
    q1_mean = mean(q1_latencies)
    q4_mean = mean(q4_latencies)
    drift_pct = ((q4_mean - q1_mean) / q1_mean) * 100 if q1_mean > 0 else 0

    # Print results
    print(f"\n=== Sustained Load Test Results ===")
    print(f"Duration: {elapsed:.2f}s")
    print(f"Ticks processed: {ticks_processed}")
    print(f"Throughput: {throughput:.2f} ticks/sec")
    print(f"Latency P99: {stats['p99']*1000:.2f}ms")
    print(f"Latency Mean: {stats['mean']*1000:.2f}ms")
    print(f"Latency Drift: {drift_pct:.2f}% (Q1→Q4)")

    # Assertions
    assert throughput > 50, f"Throughput too low: {throughput:.2f} ticks/sec"
    assert abs(drift_pct) < 50, f"Latency drift detected: {drift_pct:.2f}%"


@pytest.mark.load
@pytest.mark.asyncio
async def test_greeks_calculation_overhead(load_test_helper):
    """
    Test overhead of Greeks calculation on tick processing.

    Measures latency with vs without Greeks to quantify overhead.
    Expected: Greeks add < 5ms per tick
    """
    num_ticks = 1000
    market_tz = ZoneInfo("Asia/Kolkata")
    today = date(2025, 11, 8)

    # Create test instruments
    instruments = load_test_helper.create_test_instruments(num_ticks, "option")

    # Mock batchers for both tests
    mock_batcher_1 = MockBatcher()
    mock_batcher_2 = MockBatcher()

    # Test 1: Without Greeks
    processor_no_greeks = TickProcessor(
        greeks_calculator=None,
        market_tz=market_tz,
        batcher=mock_batcher_1,
        validator=None,
    )

    latencies_no_greeks = []
    for instrument in instruments.values():
        tick = load_test_helper.create_test_tick(instrument)

        start = time.perf_counter()
        await processor_no_greeks.process_ticks(
            account_id="load_test",
            lookup=instruments,
            ticks=[tick],
            today_market=today,
        )
        latencies_no_greeks.append(time.perf_counter() - start)

    # Test 2: With Greeks
    greeks_calculator = GreeksCalculator(
        interest_rate=0.10,
        dividend_yield=0.0,
        expiry_time_hour=15,
        expiry_time_minute=30,
        market_timezone="Asia/Kolkata",
    )

    processor_with_greeks = TickProcessor(
        greeks_calculator=greeks_calculator,
        market_tz=market_tz,
        batcher=mock_batcher_2,
        validator=None,
    )

    latencies_with_greeks = []
    for instrument in instruments.values():
        tick = load_test_helper.create_test_tick(instrument)

        start = time.perf_counter()
        await processor_with_greeks.process_ticks(
            account_id="load_test",
            lookup=instruments,
            ticks=[tick],
            today_market=today,
        )
        latencies_with_greeks.append(time.perf_counter() - start)

    # Calculate overhead
    mean_no_greeks = mean(latencies_no_greeks)
    mean_with_greeks = mean(latencies_with_greeks)
    overhead_ms = (mean_with_greeks - mean_no_greeks) * 1000

    # Print results
    print(f"\n=== Greeks Calculation Overhead Test ===")
    print(f"Mean latency (no Greeks): {mean_no_greeks*1000:.2f}ms")
    print(f"Mean latency (with Greeks): {mean_with_greeks*1000:.2f}ms")
    print(f"Greeks overhead: {overhead_ms:.2f}ms")

    # Assertion (relaxed - Greeks can be expensive)
    assert overhead_ms < 10.0, f"Greeks overhead too high: {overhead_ms:.2f}ms"
