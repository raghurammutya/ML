"""
Integration tests for mock state cleanup.

Tests that expired options are removed automatically.
"""
import asyncio
import pytest
from datetime import datetime, timedelta
from app.generator import MultiAccountTickerLoop
from app.services.mock_generator import _MockOptionBuilder
from app.schema import Instrument


@pytest.mark.asyncio
async def test_expired_cleanup_removes_old_options():
    """Test that expired options are removed by cleanup"""
    ticker_loop = MultiAccountTickerLoop()

    # Create an expired instrument (yesterday)
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    expired_inst = Instrument(
        instrument_token=12345,
        tradingsymbol="NIFTY2511424000CE",
        symbol="NIFTY",
        expiry=yesterday,
        strike=24000.0,
        tick_size=0.05,
        lot_size=50,
        instrument_type="CE",
        segment="NFO-OPT",
        exchange="NFO",
    )

    # Create a valid instrument (next month)
    future_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
    valid_inst = Instrument(
        instrument_token=67890,
        tradingsymbol="NIFTY2512424000CE",
        symbol="NIFTY",
        expiry=future_date,
        strike=24000.0,
        tick_size=0.05,
        lot_size=50,
        instrument_type="CE",
        segment="NFO-OPT",
        exchange="NFO",
    )

    # Manually add to mock state (simulating they were seeded earlier)
    async with ticker_loop._mock_generator._lock:
        # Add expired
        ticker_loop._mock_generator._option_builders[expired_inst.instrument_token] = _MockOptionBuilder(
            instrument=expired_inst,
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
        ticker_loop._mock_generator._option_snapshots[expired_inst.instrument_token] = \
            ticker_loop._mock_generator._option_builders[expired_inst.instrument_token].build_snapshot()

        # Add valid
        ticker_loop._mock_generator._option_builders[valid_inst.instrument_token] = _MockOptionBuilder(
            instrument=valid_inst,
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
        ticker_loop._mock_generator._option_snapshots[valid_inst.instrument_token] = \
            ticker_loop._mock_generator._option_builders[valid_inst.instrument_token].build_snapshot()

    # Verify both present
    assert 12345 in ticker_loop._mock_generator._option_snapshots
    assert 67890 in ticker_loop._mock_generator._option_snapshots
    assert len(ticker_loop._mock_generator._option_snapshots) == 2

    # Run cleanup
    await ticker_loop._mock_generator.cleanup_expired()

    # Expired should be removed, valid should remain
    assert 12345 not in ticker_loop._mock_generator._option_snapshots
    assert 67890 in ticker_loop._mock_generator._option_snapshots
    assert len(ticker_loop._mock_generator._option_snapshots) == 1


@pytest.mark.asyncio
async def test_cleanup_handles_invalid_expiry_format():
    """Test that cleanup gracefully handles invalid expiry formats"""
    ticker_loop = MultiAccountTickerLoop()

    # Create instrument with invalid expiry format
    invalid_inst = Instrument(
        instrument_token=11111,
        tradingsymbol="NIFTY2511424000CE",
        symbol="NIFTY",
        expiry="invalid-date",  # Invalid format
        strike=24000.0,
        tick_size=0.05,
        lot_size=50,
        instrument_type="CE",
        segment="NFO-OPT",
        exchange="NFO",
    )

    # Manually add to mock state
    async with ticker_loop._mock_generator._lock:
        ticker_loop._mock_generator._option_builders[invalid_inst.instrument_token] = _MockOptionBuilder(
            instrument=invalid_inst,
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
        ticker_loop._mock_generator._option_snapshots[invalid_inst.instrument_token] = \
            ticker_loop._mock_generator._option_builders[invalid_inst.instrument_token].build_snapshot()

    # Run cleanup - should not crash
    await ticker_loop._mock_generator.cleanup_expired()

    # Invalid expiry should be kept (not considered expired)
    assert 11111 in ticker_loop._mock_generator._option_snapshots


@pytest.mark.asyncio
async def test_cleanup_with_no_expiry():
    """Test cleanup handles instruments with no expiry field"""
    ticker_loop = MultiAccountTickerLoop()

    # Create instrument with None expiry
    no_expiry_inst = Instrument(
        instrument_token=22222,
        tradingsymbol="NIFTY",
        symbol="NIFTY",
        expiry=None,  # No expiry
        strike=None,
        tick_size=0.05,
        lot_size=75,
        instrument_type="EQ",
        segment="NSE",
        exchange="NSE",
    )

    # Manually add to mock state
    async with ticker_loop._mock_generator._lock:
        ticker_loop._mock_generator._option_builders[no_expiry_inst.instrument_token] = _MockOptionBuilder(
            instrument=no_expiry_inst,
            base_price=24000.0,
            last_price=24050.0,
            base_volume=1000000,
            base_oi=0,
            iv=0.0,
            delta=1.0,
            gamma=0.0,
            theta=0.0,
            vega=0.0,
        )
        ticker_loop._mock_generator._option_snapshots[no_expiry_inst.instrument_token] = \
            ticker_loop._mock_generator._option_builders[no_expiry_inst.instrument_token].build_snapshot()

    # Run cleanup
    await ticker_loop._mock_generator.cleanup_expired()

    # No expiry instruments should be kept
    assert 22222 in ticker_loop._mock_generator._option_snapshots


@pytest.mark.asyncio
async def test_cleanup_internal_vs_public():
    """Test both internal (lock held) and public (acquires lock) cleanup methods"""
    ticker_loop = MultiAccountTickerLoop()

    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    expired_inst = Instrument(
        instrument_token=33333,
        tradingsymbol="NIFTY2511424000CE",
        symbol="NIFTY",
        expiry=yesterday,
        strike=24000.0,
        tick_size=0.05,
        lot_size=50,
        instrument_type="CE",
        segment="NFO-OPT",
        exchange="NFO",
    )

    # Test internal cleanup (lock already held)
    async with ticker_loop._mock_generator._lock:
        ticker_loop._mock_generator._option_builders[expired_inst.instrument_token] = _MockOptionBuilder(
            instrument=expired_inst,
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
        ticker_loop._mock_generator._option_snapshots[expired_inst.instrument_token] = \
            ticker_loop._mock_generator._option_builders[expired_inst.instrument_token].build_snapshot()

        assert 33333 in ticker_loop._mock_generator._option_snapshots

        # Call internal cleanup
        await ticker_loop._mock_generator.cleanup_expired_internal()

        assert 33333 not in ticker_loop._mock_generator._option_snapshots

    # Test public cleanup (acquires lock)
    async with ticker_loop._mock_generator._lock:
        ticker_loop._mock_generator._option_builders[expired_inst.instrument_token] = _MockOptionBuilder(
            instrument=expired_inst,
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
        ticker_loop._mock_generator._option_snapshots[expired_inst.instrument_token] = \
            ticker_loop._mock_generator._option_builders[expired_inst.instrument_token].build_snapshot()

    assert 33333 in ticker_loop._mock_generator._option_snapshots

    # Call public cleanup (from outside lock)
    await ticker_loop._mock_generator.cleanup_expired()

    assert 33333 not in ticker_loop._mock_generator._option_snapshots


@pytest.mark.asyncio
async def test_cleanup_during_seed_operation():
    """Test that cleanup is called during seed operations"""
    ticker_loop = MultiAccountTickerLoop()
    ticker_loop._mock_state_max_size = 100

    class MockClient:
        async def fetch_historical(self, **kwargs):
            return [{"close": 100.0, "volume": 1000, "oi": 5000}]

        async def get_last_price(self, symbol):
            return 100.0

    client = MockClient()

    # Add expired instrument first
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    expired_inst = Instrument(
        instrument_token=44444,
        tradingsymbol="NIFTY2511424000CE",
        symbol="NIFTY",
        expiry=yesterday,
        strike=24000.0,
        tick_size=0.05,
        lot_size=50,
        instrument_type="CE",
        segment="NFO-OPT",
        exchange="NFO",
    )

    async with ticker_loop._mock_generator._lock:
        ticker_loop._mock_generator._option_builders[expired_inst.instrument_token] = _MockOptionBuilder(
            instrument=expired_inst,
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
        ticker_loop._mock_generator._option_snapshots[expired_inst.instrument_token] = \
            ticker_loop._mock_generator._option_builders[expired_inst.instrument_token].build_snapshot()

    assert 44444 in ticker_loop._mock_generator._option_snapshots

    # Now seed a new valid instrument - should trigger cleanup
    future_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
    new_inst = Instrument(
        instrument_token=55555,
        tradingsymbol="NIFTY2512424000CE",
        symbol="NIFTY",
        expiry=future_date,
        strike=24000.0,
        tick_size=0.05,
        lot_size=50,
        instrument_type="CE",
        segment="NFO-OPT",
        exchange="NFO",
    )

    await ticker_loop._ensure_mock_option_seed(client, [new_inst])

    # Expired should be cleaned up automatically
    assert 44444 not in ticker_loop._mock_generator._option_snapshots
    # New should be present
    assert 55555 in ticker_loop._mock_generator._option_snapshots
