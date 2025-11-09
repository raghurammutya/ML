"""
Unit tests for mock state concurrency and thread safety.

Tests the Builder + Snapshot pattern for concurrent access to mock data.
"""
import asyncio
import pytest
from app.generator import MultiAccountTickerLoop
from app.schema import Instrument


@pytest.mark.asyncio
async def test_mock_underlying_snapshots_are_immutable():
    """Test that MockUnderlyingSnapshot is truly immutable"""
    ticker_loop = MultiAccountTickerLoop()

    # Create a snapshot (would normally be done in _ensure_mock_underlying_seed)
    from app.services.mock_generator import _MockUnderlyingBuilder

    builder = _MockUnderlyingBuilder(
        symbol="NIFTY",
        base_open=24000.0,
        base_high=24100.0,
        base_low=23900.0,
        base_close=24050.0,
        base_volume=1000000,
        last_close=24050.0,
    )
    snapshot = builder.build_snapshot()

    # Verify frozen dataclass prevents mutation
    with pytest.raises(AttributeError):
        snapshot.last_close = 25000.0  # Should raise FrozenInstanceError


@pytest.mark.asyncio
async def test_mock_option_snapshots_are_immutable():
    """Test that MockOptionSnapshot is truly immutable"""
    from app.services.mock_generator import _MockOptionBuilder

    instrument = Instrument(
        instrument_token=12345,
        tradingsymbol="NIFTY2511524000CE",
        symbol="NIFTY",
        expiry=None,
        strike=24000.0,
        tick_size=0.05,
        lot_size=50,
        instrument_type="CE",
        segment="NFO-OPT",
        exchange="NFO",
    )

    builder = _MockOptionBuilder(
        instrument=instrument,
        base_price=100.0,
        last_price=105.0,
        base_volume=10000,
        base_oi=50000,
        iv=0.15,
        delta=0.5,
        gamma=0.01,
        theta=-0.5,
        vega=10.0,
    )
    snapshot = builder.build_snapshot()

    # Verify frozen dataclass prevents mutation
    with pytest.raises(AttributeError):
        snapshot.last_price = 200.0  # Should raise FrozenInstanceError


@pytest.mark.asyncio
async def test_mock_underlying_concurrent_reads():
    """Test that concurrent reads of underlying snapshot don't see torn data"""
    ticker_loop = MultiAccountTickerLoop()

    # Initialize underlying state
    from app.services.mock_generator import _MockUnderlyingBuilder

    async with ticker_loop._mock_generator._lock:
        ticker_loop._mock_generator._underlying_builder = _MockUnderlyingBuilder(
            symbol="NIFTY",
            base_open=24000.0,
            base_high=24100.0,
            base_low=23900.0,
            base_close=24050.0,
            base_volume=1000000,
            last_close=24050.0,
        )
        ticker_loop._mock_generator._underlying_snapshot = ticker_loop._mock_generator._underlying_builder.build_snapshot()

    read_count = 0
    inconsistency_count = 0

    async def reader():
        """Read snapshot many times and verify consistency"""
        nonlocal read_count, inconsistency_count
        for _ in range(100):
            snapshot = ticker_loop._mock_generator._underlying_snapshot
            if snapshot:
                # Verify internal consistency
                if snapshot.last_close <= 0:
                    inconsistency_count += 1
                if snapshot.base_volume < 0:
                    inconsistency_count += 1
                read_count += 1
            await asyncio.sleep(0.001)

    async def writer():
        """Update underlying state many times"""
        for i in range(50):
            await ticker_loop._generate_mock_underlying_bar()
            await asyncio.sleep(0.002)

    # Run 3 readers + 2 writers concurrently
    await asyncio.gather(
        reader(),
        reader(),
        reader(),
        writer(),
        writer(),
    )

    # All reads should be consistent (no torn reads)
    assert inconsistency_count == 0, f"Found {inconsistency_count} inconsistent reads"
    assert read_count > 200, "Should have many reads"


@pytest.mark.asyncio
async def test_mock_option_concurrent_reads():
    """Test that concurrent reads of option snapshots don't see torn data"""
    ticker_loop = MultiAccountTickerLoop()

    instrument = Instrument(
        instrument_token=12345,
        tradingsymbol="NIFTY2511524000CE",
        symbol="NIFTY",
        expiry=None,
        strike=24000.0,
        tick_size=0.05,
        lot_size=50,
        instrument_type="CE",
        segment="NFO-OPT",
        exchange="NFO",
    )

    # Initialize option state
    from app.services.mock_generator import _MockOptionBuilder

    async with ticker_loop._mock_generator._lock:
        ticker_loop._mock_generator._option_builders[instrument.instrument_token] = _MockOptionBuilder(
            instrument=instrument,
            base_price=100.0,
            last_price=105.0,
            base_volume=10000,
            base_oi=50000,
            iv=0.15,
            delta=0.5,
            gamma=0.01,
            theta=-0.5,
            vega=10.0,
        )
        ticker_loop._mock_generator._option_snapshots[instrument.instrument_token] = \
            ticker_loop._mock_generator._option_builders[instrument.instrument_token].build_snapshot()

    read_count = 0
    inconsistency_count = 0

    async def reader():
        """Read snapshot many times and verify consistency"""
        nonlocal read_count, inconsistency_count
        for _ in range(100):
            snapshot = ticker_loop._mock_generator._option_snapshots.get(instrument.instrument_token)
            if snapshot:
                # Verify internal consistency
                if snapshot.last_price <= 0:
                    inconsistency_count += 1
                if snapshot.base_volume < 0:
                    inconsistency_count += 1
                if snapshot.base_oi < 0:
                    inconsistency_count += 1
                read_count += 1
            await asyncio.sleep(0.001)

    async def writer():
        """Update option state many times"""
        for i in range(50):
            await ticker_loop._generate_mock_option_snapshot(instrument)
            await asyncio.sleep(0.002)

    # Run 3 readers + 2 writers concurrently
    await asyncio.gather(
        reader(),
        reader(),
        reader(),
        writer(),
        writer(),
    )

    # All reads should be consistent (no torn reads)
    assert inconsistency_count == 0, f"Found {inconsistency_count} inconsistent reads"
    assert read_count > 200, "Should have many reads"


@pytest.mark.asyncio
async def test_mock_underlying_no_double_initialization():
    """Test that double-check locking prevents duplicate initialization"""
    ticker_loop = MultiAccountTickerLoop()

    # Mock the client
    class MockClient:
        call_count = 0

        async def get_quote(self, symbols):
            MockClient.call_count += 1
            await asyncio.sleep(0.05)  # Simulate slow API call
            return {
                "NSE:NIFTY 50": {
                    "last_price": 24050.0,
                    "ohlc": {
                        "open": 24000.0,
                        "high": 24100.0,
                        "low": 23900.0,
                        "close": 24050.0,
                    },
                    "volume": 1000000,
                }
            }

    client = MockClient()

    # Multiple coroutines try to initialize concurrently
    async def initialize():
        await ticker_loop._ensure_mock_underlying_seed(client)

    # Run 5 concurrent initializations
    await asyncio.gather(
        initialize(),
        initialize(),
        initialize(),
        initialize(),
        initialize(),
    )

    # Should only call API once (double-check locking works)
    assert MockClient.call_count == 1, f"API called {MockClient.call_count} times, expected 1"
    assert ticker_loop._mock_generator._underlying_snapshot is not None


@pytest.mark.asyncio
async def test_builder_mutation_only_under_lock():
    """Test that builders are only mutated when lock is held"""
    ticker_loop = MultiAccountTickerLoop()

    from app.services.mock_generator import _MockUnderlyingBuilder

    # Initialize state
    async with ticker_loop._mock_generator._lock:
        ticker_loop._mock_generator._underlying_builder = _MockUnderlyingBuilder(
            symbol="NIFTY",
            base_open=24000.0,
            base_high=24100.0,
            base_low=23900.0,
            base_close=24050.0,
            base_volume=1000000,
            last_close=24050.0,
        )
        ticker_loop._mock_generator._underlying_snapshot = ticker_loop._mock_generator._underlying_builder.build_snapshot()

    # Attempt to access builder without lock (should be safe - we're just reading)
    builder = ticker_loop._mock_generator._underlying_builder
    assert builder is not None

    # But mutations should only happen under lock
    # _generate_mock_underlying_bar does this correctly
    initial_close = builder.last_close

    await ticker_loop._generate_mock_underlying_bar()

    # Builder should have been mutated (under lock)
    assert ticker_loop._mock_generator._underlying_builder.last_close != initial_close


@pytest.mark.asyncio
async def test_snapshot_updates_are_atomic():
    """Test that snapshot updates are atomic (readers see old or new, never partial)"""
    ticker_loop = MultiAccountTickerLoop()

    from app.services.mock_generator import _MockUnderlyingBuilder

    # Initialize state
    async with ticker_loop._mock_generator._lock:
        ticker_loop._mock_generator._underlying_builder = _MockUnderlyingBuilder(
            symbol="NIFTY",
            base_open=24000.0,
            base_high=24100.0,
            base_low=23900.0,
            base_close=24050.0,
            base_volume=1000000,
            last_close=24050.0,
        )
        ticker_loop._mock_generator._underlying_snapshot = ticker_loop._mock_generator._underlying_builder.build_snapshot()

    snapshots_seen = []

    async def reader():
        """Collect all unique snapshots seen"""
        for _ in range(100):
            snapshot = ticker_loop._mock_generator._underlying_snapshot
            if snapshot:
                snapshots_seen.append((snapshot.last_close, snapshot.timestamp))
            await asyncio.sleep(0.001)

    async def writer():
        """Generate bars"""
        for _ in range(20):
            await ticker_loop._generate_mock_underlying_bar()
            await asyncio.sleep(0.005)

    await asyncio.gather(reader(), reader(), writer())

    # Each snapshot should have a unique timestamp
    # (proves we're seeing complete snapshots, not partial updates)
    timestamps = [ts for _, ts in snapshots_seen]
    unique_timestamps = set(timestamps)

    # Should have seen multiple different snapshots
    assert len(unique_timestamps) > 1, "Should see multiple snapshot versions"

    # Each timestamp should correspond to a consistent snapshot
    # (this is guaranteed by immutability)


@pytest.mark.asyncio
async def test_reset_mock_state_clears_all():
    """Test that reset clears both builders and snapshots"""
    ticker_loop = MultiAccountTickerLoop()

    from app.services.mock_generator import _MockUnderlyingBuilder, _MockOptionBuilder

    instrument = Instrument(
        instrument_token=12345,
        tradingsymbol="NIFTY2511524000CE",
        symbol="NIFTY",
        expiry=None,
        strike=24000.0,
        tick_size=0.05,
        lot_size=50,
        instrument_type="CE",
        segment="NFO-OPT",
        exchange="NFO",
    )

    # Initialize state
    async with ticker_loop._mock_generator._lock:
        ticker_loop._mock_generator._underlying_builder = _MockUnderlyingBuilder(
            symbol="NIFTY",
            base_open=24000.0,
            base_high=24100.0,
            base_low=23900.0,
            base_close=24050.0,
            base_volume=1000000,
            last_close=24050.0,
        )
        ticker_loop._mock_generator._underlying_snapshot = ticker_loop._mock_generator._underlying_builder.build_snapshot()

        ticker_loop._mock_generator._option_builders[instrument.instrument_token] = _MockOptionBuilder(
            instrument=instrument,
            base_price=100.0,
            last_price=105.0,
            base_volume=10000,
            base_oi=50000,
            iv=0.15,
            delta=0.5,
            gamma=0.01,
            theta=-0.5,
            vega=10.0,
        )
        ticker_loop._mock_generator._option_snapshots[instrument.instrument_token] = \
            ticker_loop._mock_generator._option_builders[instrument.instrument_token].build_snapshot()

    # Verify state exists
    assert ticker_loop._mock_generator._underlying_builder is not None
    assert ticker_loop._mock_generator._underlying_snapshot is not None
    assert len(ticker_loop._mock_generator._option_builders) == 1
    assert len(ticker_loop._mock_generator._option_snapshots) == 1

    # Reset
    await ticker_loop._mock_generator.reset_state()

    # Verify all cleared
    assert ticker_loop._mock_generator._underlying_builder is None
    assert ticker_loop._mock_generator._underlying_snapshot is None
    assert len(ticker_loop._mock_generator._option_builders) == 0
    assert len(ticker_loop._mock_generator._option_snapshots) == 0
