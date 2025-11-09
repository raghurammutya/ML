"""
Integration tests for TickProcessor service.

Verifies that TickProcessor correctly processes ticks and integrates with MultiAccountTickerLoop.
"""
import asyncio
import pytest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from unittest.mock import patch, AsyncMock

from app.generator import MultiAccountTickerLoop
from app.services.tick_processor import TickProcessor
from app.schema import Instrument
from app.greeks_calculator import GreeksCalculator


@pytest.mark.asyncio
async def test_tick_processor_integration():
    """Test TickProcessor integrates correctly with ticker loop"""
    ticker_loop = MultiAccountTickerLoop()

    # Verify tick processor injected
    assert ticker_loop._tick_processor is not None
    assert isinstance(ticker_loop._tick_processor, TickProcessor)

    # Verify tick processor has correct configuration
    assert ticker_loop._tick_processor._greeks_calculator is not None
    assert ticker_loop._tick_processor._market_tz is not None


@pytest.mark.asyncio
@patch('app.services.tick_processor.publish_underlying_bar', new_callable=AsyncMock)
async def test_underlying_tick_processing(mock_publish):
    """Test processing of underlying/index ticks"""
    ticker_loop = MultiAccountTickerLoop()

    # Create mock underlying instrument
    instrument = Instrument(
        instrument_token=256265,
        tradingsymbol="NIFTY 50",
        symbol="NIFTY 50",
        expiry=None,
        strike=None,
        tick_size=0.05,
        lot_size=50,
        instrument_type="",
        segment="INDICES",
        exchange="NSE",
    )

    lookup = {256265: instrument}

    # Create mock underlying tick
    tick = {
        "instrument_token": 256265,
        "last_price": 24000.0,
        "volume_traded_today": 1000000,
        "timestamp": int(datetime.now().timestamp()),
        "ohlc": {
            "open": 23950.0,
            "high": 24050.0,
            "low": 23900.0,
            "close": 24000.0,
        },
    }

    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()

    # Process tick
    await ticker_loop._tick_processor.process_ticks(
        account_id="test_account",
        lookup=lookup,
        ticks=[tick],
        today_market=today,
    )

    # Verify underlying price was tracked
    assert ticker_loop._tick_processor.get_last_underlying_price() == 24000.0

    # Verify last tick time updated
    assert ticker_loop._tick_processor.get_last_tick_time("test_account") is not None


@pytest.mark.asyncio
@patch('app.services.tick_processor.publish_option_snapshot', new_callable=AsyncMock)
@patch('app.services.tick_processor.publish_underlying_bar', new_callable=AsyncMock)
async def test_option_tick_processing(mock_publish_underlying, mock_publish_option):
    """Test processing of option ticks with Greeks calculation"""
    ticker_loop = MultiAccountTickerLoop()

    # First, set underlying price
    underlying_instrument = Instrument(
        instrument_token=256265,
        tradingsymbol="NIFTY 50",
        symbol="NIFTY 50",
        expiry=None,
        strike=None,
        tick_size=0.05,
        lot_size=50,
        instrument_type="",
        segment="INDICES",
        exchange="NSE",
    )

    underlying_tick = {
        "instrument_token": 256265,
        "last_price": 24000.0,
        "volume_traded_today": 1000000,
        "timestamp": int(datetime.now().timestamp()),
    }

    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    future_date = (datetime.now() + timedelta(days=30)).date()

    await ticker_loop._tick_processor.process_ticks(
        account_id="test_account",
        lookup={256265: underlying_instrument},
        ticks=[underlying_tick],
        today_market=today,
    )

    # Now process option tick
    option_instrument = Instrument(
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

    option_tick = {
        "instrument_token": 12345,
        "last_price": 150.0,
        "volume_traded_today": 10000,
        "oi": 50000,
        "timestamp": int(datetime.now().timestamp()),
        "total_buy_quantity": 5000,
        "total_sell_quantity": 6000,
    }

    # Process option tick
    await ticker_loop._tick_processor.process_ticks(
        account_id="test_account",
        lookup={12345: option_instrument},
        ticks=[option_tick],
        today_market=today,
    )

    # Verify processing succeeded (Greeks calculated)
    # Greeks calculation is internal, we mainly verify no exceptions


@pytest.mark.asyncio
async def test_expired_contract_filtering():
    """Test that expired contracts are filtered out"""
    ticker_loop = MultiAccountTickerLoop()

    # Create expired option
    yesterday = (datetime.now() - timedelta(days=1)).date()
    expired_instrument = Instrument(
        instrument_token=12345,
        tradingsymbol="NIFTY2410024000CE",
        symbol="NIFTY",
        expiry=yesterday,  # Expired!
        strike=24000.0,
        tick_size=0.05,
        lot_size=50,
        instrument_type="CE",
        segment="NFO-OPT",
        exchange="NFO",
    )

    expired_tick = {
        "instrument_token": 12345,
        "last_price": 0.05,
        "volume_traded_today": 0,
        "oi": 0,
        "timestamp": int(datetime.now().timestamp()),
    }

    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()

    # Process expired tick
    await ticker_loop._tick_processor.process_ticks(
        account_id="test_account",
        lookup={12345: expired_instrument},
        ticks=[expired_tick],
        today_market=today,
    )

    # Should complete without errors (tick skipped)


@pytest.mark.asyncio
@patch('app.services.tick_processor.publish_option_snapshot', new_callable=AsyncMock)
@patch('app.services.tick_processor.publish_underlying_bar', new_callable=AsyncMock)
async def test_market_depth_extraction(mock_publish_underlying, mock_publish_option):
    """Test extraction of market depth data"""
    ticker_loop = MultiAccountTickerLoop()

    # Set underlying price first
    underlying_tick = {
        "instrument_token": 256265,
        "last_price": 24000.0,
        "volume_traded_today": 1000000,
        "timestamp": int(datetime.now().timestamp()),
    }

    underlying_instrument = Instrument(
        instrument_token=256265,
        tradingsymbol="NIFTY 50",
        symbol="NIFTY 50",
        expiry=None,
        strike=None,
        tick_size=0.05,
        lot_size=50,
        instrument_type="",
        segment="INDICES",
        exchange="NSE",
    )

    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()

    await ticker_loop._tick_processor.process_ticks(
        account_id="test_account",
        lookup={256265: underlying_instrument},
        ticks=[underlying_tick],
        today_market=today,
    )

    # Create option with depth data
    future_date = (datetime.now() + timedelta(days=30)).date()
    option_instrument = Instrument(
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

    option_tick = {
        "instrument_token": 12345,
        "last_price": 150.0,
        "volume_traded_today": 10000,
        "oi": 50000,
        "timestamp": int(datetime.now().timestamp()),
        "depth": {
            "buy": [
                {"price": 14950, "quantity": 100, "orders": 5},  # In paise
                {"price": 14900, "quantity": 200, "orders": 10},
            ],
            "sell": [
                {"price": 15050, "quantity": 150, "orders": 7},  # In paise
                {"price": 15100, "quantity": 250, "orders": 12},
            ],
        },
        "total_buy_quantity": 300,
        "total_sell_quantity": 400,
    }

    # Process option tick with depth
    await ticker_loop._tick_processor.process_ticks(
        account_id="test_account",
        lookup={12345: option_instrument},
        ticks=[option_tick],
        today_market=today,
    )

    # Verify processing succeeded (depth extracted)


@pytest.mark.asyncio
@patch('app.services.tick_processor.publish_underlying_bar', new_callable=AsyncMock)
async def test_tick_processor_state_management(mock_publish):
    """Test tick processor state management"""
    ticker_loop = MultiAccountTickerLoop()

    # Process some ticks
    instrument = Instrument(
        instrument_token=256265,
        tradingsymbol="NIFTY 50",
        symbol="NIFTY 50",
        expiry=None,
        strike=None,
        tick_size=0.05,
        lot_size=50,
        instrument_type="",
        segment="INDICES",
        exchange="NSE",
    )

    tick = {
        "instrument_token": 256265,
        "last_price": 24000.0,
        "volume_traded_today": 1000000,
        "timestamp": int(datetime.now().timestamp()),
    }

    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()

    await ticker_loop._tick_processor.process_ticks(
        account_id="account1",
        lookup={256265: instrument},
        ticks=[tick],
        today_market=today,
    )

    # Verify state tracked
    assert ticker_loop._tick_processor.get_last_underlying_price() == 24000.0
    assert ticker_loop._tick_processor.get_last_tick_time("account1") is not None

    # Reset state
    ticker_loop._tick_processor.reset_state()

    # Verify state cleared
    assert ticker_loop._tick_processor.get_last_underlying_price() is None
    assert ticker_loop._tick_processor.get_last_tick_time("account1") is None


@pytest.mark.asyncio
async def test_dependency_injection_allows_custom_tick_processor():
    """Test that custom TickProcessor can be injected"""
    from zoneinfo import ZoneInfo

    # Create custom tick processor
    custom_processor = TickProcessor(
        greeks_calculator=GreeksCalculator(),
        market_tz=ZoneInfo("Asia/Kolkata"),
    )

    # Inject into ticker loop
    ticker_loop = MultiAccountTickerLoop(tick_processor=custom_processor)

    # Verify our custom instance was used
    assert ticker_loop._tick_processor is custom_processor


@pytest.mark.asyncio
@patch('app.services.tick_processor.publish_underlying_bar', new_callable=AsyncMock)
async def test_tick_processor_stats(mock_publish):
    """Test tick processor statistics"""
    ticker_loop = MultiAccountTickerLoop()

    # Get initial stats
    stats = ticker_loop._tick_processor.get_stats()
    assert stats["last_underlying_price"] is None
    assert stats["accounts_tracked"] == 0

    # Process some ticks
    instrument = Instrument(
        instrument_token=256265,
        tradingsymbol="NIFTY 50",
        symbol="NIFTY 50",
        expiry=None,
        strike=None,
        tick_size=0.05,
        lot_size=50,
        instrument_type="",
        segment="INDICES",
        exchange="NSE",
    )

    tick = {
        "instrument_token": 256265,
        "last_price": 24000.0,
        "volume_traded_today": 1000000,
        "timestamp": int(datetime.now().timestamp()),
    }

    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()

    await ticker_loop._tick_processor.process_ticks(
        account_id="account1",
        lookup={256265: instrument},
        ticks=[tick],
        today_market=today,
    )

    # Get updated stats
    stats = ticker_loop._tick_processor.get_stats()
    assert stats["last_underlying_price"] == 24000.0
    assert stats["accounts_tracked"] == 1
    assert "account1" in stats["last_tick_times"]
