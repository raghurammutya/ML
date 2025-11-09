"""
Integration tests for TickBatcher service.

Verifies tick batching functionality for improved throughput.
"""
import asyncio
import pytest
import time
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch, MagicMock

from app.services.tick_batcher import TickBatcher
from app.schema import Instrument, OptionSnapshot


@pytest.mark.asyncio
async def test_tick_batcher_accumulates_ticks():
    """Test that ticks accumulate in batch"""
    batcher = TickBatcher(window_ms=1000, max_batch_size=10, enabled=True)

    # Add some ticks
    await batcher.add_underlying({"symbol": "NIFTY", "last_price": 24000.0})
    await batcher.add_underlying({"symbol": "NIFTY", "last_price": 24001.0})

    # Check batch size
    assert batcher._underlying_batch ==  [
        {"symbol": "NIFTY", "last_price": 24000.0},
        {"symbol": "NIFTY", "last_price": 24001.0}
    ]
    assert batcher._total_underlying_added == 2


@pytest.mark.asyncio
@patch('app.services.tick_batcher.redis_publisher.publish', new_callable=AsyncMock)
async def test_time_based_flushing(mock_publish):
    """Test that batches flush after time window expires"""
    batcher = TickBatcher(window_ms=100, max_batch_size=1000, enabled=True)
    await batcher.start()

    # Add a tick
    await batcher.add_underlying({"symbol": "NIFTY", "last_price": 24000.0})

    # Wait for window to expire
    await asyncio.sleep(0.15)  # 150ms > 100ms window

    # Batch should be flushed
    assert len(batcher._underlying_batch) == 0
    assert batcher._total_underlying_flushed == 1
    assert mock_publish.called

    await batcher.stop()


@pytest.mark.asyncio
@patch('app.services.tick_batcher.redis_publisher.publish', new_callable=AsyncMock)
async def test_size_based_flushing(mock_publish):
    """Test that batches flush when max size reached"""
    batcher = TickBatcher(window_ms=10000, max_batch_size=5, enabled=True)  # Large window, small batch

    # Add ticks up to max size
    for i in range(5):
        await batcher.add_underlying({"symbol": "NIFTY", "last_price": 24000.0 + i})

    # Batch should be flushed immediately due to size
    assert len(batcher._underlying_batch) == 0
    assert batcher._total_underlying_flushed == 5
    assert mock_publish.call_count == 5


@pytest.mark.asyncio
@patch('app.services.tick_batcher.redis_publisher.publish', new_callable=AsyncMock)
async def test_graceful_shutdown_flushes_remaining(mock_publish):
    """Test that stop() flushes remaining batches"""
    batcher = TickBatcher(window_ms=10000, max_batch_size=1000, enabled=True)
    await batcher.start()

    # Add some ticks (not enough to trigger size flush)
    await batcher.add_underlying({"symbol": "NIFTY", "last_price": 24000.0})
    await batcher.add_underlying({"symbol": "NIFTY", "last_price": 24001.0})

    # Ticks should still be in batch
    assert len(batcher._underlying_batch) == 2

    # Stop should flush
    await batcher.stop()

    # Batch should be empty after stop
    assert len(batcher._underlying_batch) == 0
    assert batcher._total_underlying_flushed == 2
    assert mock_publish.call_count == 2


@pytest.mark.asyncio
@patch('app.services.tick_batcher.redis_publisher.publish', new_callable=AsyncMock)
async def test_option_batching(mock_publish):
    """Test option snapshot batching"""
    batcher = TickBatcher(window_ms=100, max_batch_size=10, enabled=True)
    await batcher.start()

    # Create option snapshot
    future_date = (datetime.now() + timedelta(days=30)).date()
    instrument = Instrument(
        instrument_token=12345,
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

    snapshot = OptionSnapshot(
        instrument=instrument,
        last_price=150.0,
        volume=10000,
        oi=50000,
        iv=0.2,
        delta=0.5,
        gamma=0.01,
        theta=-5.0,
        vega=10.0,
        timestamp=int(time.time()),
        depth=None,
        total_buy_quantity=5000,
        total_sell_quantity=6000,
    )

    # Add option snapshot
    await batcher.add_option(snapshot)

    # Wait for flush (longer wait to ensure flush completes)
    await asyncio.sleep(0.25)

    # Should be flushed
    assert len(batcher._options_batch) == 0
    assert batcher._total_options_flushed == 1
    assert mock_publish.called

    await batcher.stop()


@pytest.mark.asyncio
@patch('app.services.tick_batcher.redis_publisher.publish', new_callable=AsyncMock)
async def test_disabled_batching_publishes_immediately(mock_publish):
    """Test that disabled batching publishes immediately"""
    batcher = TickBatcher(window_ms=100, max_batch_size=10, enabled=False)

    # Add a tick
    await batcher.add_underlying({"symbol": "NIFTY", "last_price": 24000.0})

    # Should publish immediately (not batched)
    assert mock_publish.called
    assert len(batcher._underlying_batch) == 0
    assert batcher._total_underlying_added == 0  # Not tracked when disabled


@pytest.mark.asyncio
async def test_batcher_stats():
    """Test batcher statistics"""
    batcher = TickBatcher(window_ms=100, max_batch_size=10, enabled=True)

    # Add some ticks
    await batcher.add_underlying({"symbol": "NIFTY", "last_price": 24000.0})
    await batcher.add_underlying({"symbol": "NIFTY", "last_price": 24001.0})

    # Get stats
    stats = batcher.get_stats()

    assert stats["enabled"] is True
    assert stats["window_ms"] == 100
    assert stats["max_batch_size"] == 10
    assert stats["underlying_batch_size"] == 2
    assert stats["options_batch_size"] == 0
    assert stats["total_underlying_added"] == 2
    assert stats["total_options_added"] == 0


@pytest.mark.asyncio
async def test_batch_fill_rate():
    """Test batch fill rate calculation"""
    batcher = TickBatcher(window_ms=100, max_batch_size=10, enabled=True)

    # Add 5 ticks (50% of max)
    for i in range(5):
        await batcher.add_underlying({"symbol": "NIFTY", "last_price": 24000.0 + i})

    # Get fill rate
    fill_rate = batcher.get_batch_fill_rate()

    assert fill_rate["underlying_fill_rate"] == 50.0
    assert fill_rate["options_fill_rate"] == 0.0


@pytest.mark.asyncio
@patch('app.services.tick_batcher.redis_publisher.publish', new_callable=AsyncMock)
async def test_mixed_underlying_and_options(mock_publish):
    """Test batching both underlying and options together"""
    batcher = TickBatcher(window_ms=100, max_batch_size=10, enabled=True)
    await batcher.start()

    # Add underlying
    await batcher.add_underlying({"symbol": "NIFTY", "last_price": 24000.0})

    # Add option
    future_date = (datetime.now() + timedelta(days=30)).date()
    instrument = Instrument(
        instrument_token=12345,
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

    snapshot = OptionSnapshot(
        instrument=instrument,
        last_price=150.0,
        volume=10000,
        oi=50000,
        iv=0.2,
        delta=0.5,
        gamma=0.01,
        theta=-5.0,
        vega=10.0,
        timestamp=int(time.time()),
        depth=None,
        total_buy_quantity=5000,
        total_sell_quantity=6000,
    )

    await batcher.add_option(snapshot)

    # Wait for flush (longer wait to ensure flush completes)
    await asyncio.sleep(0.25)

    # Both should be flushed
    assert len(batcher._underlying_batch) == 0
    assert len(batcher._options_batch) == 0
    assert batcher._total_underlying_flushed == 1
    assert batcher._total_options_flushed == 1

    await batcher.stop()
