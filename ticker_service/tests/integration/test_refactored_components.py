"""
Integration tests for refactored Phase 2 components.

Verifies MockDataGenerator, SubscriptionReconciler, and HistoricalBootstrapper
work correctly when integrated with MultiAccountTickerLoop.
"""
import asyncio
import pytest
from datetime import datetime, timedelta

from app.generator import MultiAccountTickerLoop
from app.services.mock_generator import MockDataGenerator
from app.services.subscription_reconciler import SubscriptionReconciler
from app.services.historical_bootstrapper import HistoricalBootstrapper
from app.schema import Instrument


@pytest.mark.asyncio
async def test_mock_generator_integration():
    """Test MockDataGenerator integrates correctly with ticker loop"""
    ticker_loop = MultiAccountTickerLoop()

    # Verify mock generator injected
    assert ticker_loop._mock_generator is not None
    assert isinstance(ticker_loop._mock_generator, MockDataGenerator)

    # Verify mock generator has correct configuration
    assert ticker_loop._mock_generator._max_size > 0
    assert ticker_loop._mock_generator._market_tz is not None
    assert ticker_loop._mock_generator._greeks_calculator is not None


@pytest.mark.asyncio
async def test_subscription_reconciler_integration():
    """Test SubscriptionReconciler integrates correctly"""
    ticker_loop = MultiAccountTickerLoop()

    # Verify reconciler injected
    assert ticker_loop._reconciler is not None
    assert isinstance(ticker_loop._reconciler, SubscriptionReconciler)

    # Verify reconciler has correct timezone
    assert ticker_loop._reconciler._market_tz is not None


@pytest.mark.asyncio
async def test_historical_bootstrapper_integration():
    """Test HistoricalBootstrapper integrates correctly"""
    ticker_loop = MultiAccountTickerLoop()

    # Verify bootstrapper injected
    assert ticker_loop._bootstrapper is not None
    assert isinstance(ticker_loop._bootstrapper, HistoricalBootstrapper)

    # Test bootstrap tracking
    assert not ticker_loop._bootstrapper.is_bootstrap_done("test_account")
    ticker_loop._bootstrapper.mark_bootstrap_done("test_account")
    assert ticker_loop._bootstrapper.is_bootstrap_done("test_account")

    # Test reset
    ticker_loop._bootstrapper.reset_bootstrap_state()
    assert not ticker_loop._bootstrapper.is_bootstrap_done("test_account")


@pytest.mark.asyncio
async def test_mock_generator_can_seed_underlying():
    """Test mock generator can seed underlying state"""
    ticker_loop = MultiAccountTickerLoop()

    # Create mock client
    class MockClient:
        async def get_quote(self, symbols):
            return {
                "NSE:NIFTY 50": {
                    "last_price": 24000.0,
                    "ohlc": {
                        "open": 23950.0,
                        "high": 24050.0,
                        "low": 23900.0,
                        "close": 24000.0,
                    },
                    "volume": 1000000,
                }
            }

    client = MockClient()

    # Seed underlying
    await ticker_loop._mock_generator.ensure_underlying_seeded(client)

    # Verify underlying snapshot created
    snapshot = ticker_loop._mock_generator.get_underlying_snapshot()
    assert snapshot is not None
    assert snapshot.last_close == 24000.0
    assert snapshot.base_volume == 1000000


@pytest.mark.asyncio
async def test_mock_generator_can_generate_underlying_bar():
    """Test mock generator can generate underlying bars"""
    ticker_loop = MultiAccountTickerLoop()

    # Create mock client and seed
    class MockClient:
        async def get_quote(self, symbols):
            return {
                "NSE:NIFTY 50": {
                    "last_price": 24000.0,
                    "ohlc": {"open": 24000.0, "high": 24000.0, "low": 24000.0, "close": 24000.0},
                    "volume": 1000000,
                }
            }

    client = MockClient()
    await ticker_loop._mock_generator.ensure_underlying_seeded(client)

    # Generate bar
    bar = await ticker_loop._mock_generator.generate_underlying_bar()

    # Verify bar structure
    assert bar is not None
    assert "symbol" in bar
    assert "open" in bar
    assert "high" in bar
    assert "low" in bar
    assert "close" in bar
    assert "volume" in bar
    assert "ts" in bar


@pytest.mark.asyncio
async def test_mock_generator_can_seed_options():
    """Test mock generator can seed option state"""
    ticker_loop = MultiAccountTickerLoop()

    # Create mock client
    class MockClient:
        async def fetch_historical(self, **kwargs):
            return [{"close": 100.0, "volume": 1000, "oi": 5000}]

        async def get_last_price(self, symbol):
            return 100.0

    client = MockClient()

    # Create test instrument
    future_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
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

    # Seed options
    await ticker_loop._mock_generator.ensure_options_seeded(client, [instrument])

    # Verify option state created
    assert ticker_loop._mock_generator.get_state_size() == 1


@pytest.mark.asyncio
async def test_mock_generator_can_generate_option_snapshot():
    """Test mock generator can generate option snapshots"""
    ticker_loop = MultiAccountTickerLoop()

    # Create mock client and seed
    class MockClient:
        async def fetch_historical(self, **kwargs):
            return [{"close": 100.0, "volume": 1000, "oi": 5000}]

        async def get_last_price(self, symbol):
            return 100.0

    client = MockClient()

    future_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
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

    await ticker_loop._mock_generator.ensure_options_seeded(client, [instrument])

    # Generate snapshot
    snapshot = await ticker_loop._mock_generator.generate_option_snapshot(instrument)

    # Verify snapshot structure
    assert snapshot is not None
    assert snapshot.instrument == instrument
    assert snapshot.last_price > 0
    assert snapshot.volume >= 0
    assert snapshot.oi >= 0
    assert snapshot.depth is not None
    assert len(snapshot.depth.buy) == 5
    assert len(snapshot.depth.sell) == 5


@pytest.mark.asyncio
async def test_subscription_reconciler_can_build_assignments_with_empty_plan():
    """Test subscription reconciler can handle empty plan"""
    ticker_loop = MultiAccountTickerLoop()

    # Build assignments with empty plan
    assignments = await ticker_loop._reconciler.build_assignments([], ["account1", "account2"])

    # Should return empty dict when no plan items
    assert assignments == {}


@pytest.mark.asyncio
async def test_subscription_reconciler_can_build_assignments():
    """Test subscription reconciler can build assignments"""
    ticker_loop = MultiAccountTickerLoop()

    # Build assignments with empty plan and no accounts
    assignments = await ticker_loop._reconciler.build_assignments([], [])

    # Should return empty dict
    assert assignments == {}


@pytest.mark.asyncio
async def test_historical_bootstrapper_state_management():
    """Test historical bootstrapper state management"""
    ticker_loop = MultiAccountTickerLoop()

    # Initially not bootstrapped
    assert not ticker_loop._bootstrapper.is_bootstrap_done("account1")
    assert not ticker_loop._bootstrapper.is_bootstrap_done("account2")

    # Mark account1 as done
    ticker_loop._bootstrapper.mark_bootstrap_done("account1")
    assert ticker_loop._bootstrapper.is_bootstrap_done("account1")
    assert not ticker_loop._bootstrapper.is_bootstrap_done("account2")

    # Mark account2 as done
    ticker_loop._bootstrapper.mark_bootstrap_done("account2")
    assert ticker_loop._bootstrapper.is_bootstrap_done("account1")
    assert ticker_loop._bootstrapper.is_bootstrap_done("account2")

    # Reset all
    ticker_loop._bootstrapper.reset_bootstrap_state()
    assert not ticker_loop._bootstrapper.is_bootstrap_done("account1")
    assert not ticker_loop._bootstrapper.is_bootstrap_done("account2")


@pytest.mark.asyncio
async def test_all_services_reset_independently():
    """Test all services can be reset independently"""
    ticker_loop = MultiAccountTickerLoop()

    # Seed some state
    ticker_loop._bootstrapper.mark_bootstrap_done("test_account")

    # Create mock client and seed mock state
    class MockClient:
        async def get_quote(self, symbols):
            return {
                "NSE:NIFTY 50": {
                    "last_price": 24000.0,
                    "ohlc": {"open": 24000.0, "high": 24000.0, "low": 24000.0, "close": 24000.0},
                    "volume": 1000000,
                }
            }

    client = MockClient()
    await ticker_loop._mock_generator.ensure_underlying_seeded(client)

    # Verify state exists
    assert ticker_loop._bootstrapper.is_bootstrap_done("test_account")
    assert ticker_loop._mock_generator.get_underlying_snapshot() is not None

    # Reset services independently
    await ticker_loop._mock_generator.reset_state()
    ticker_loop._bootstrapper.reset_bootstrap_state()

    # Verify all state reset
    assert not ticker_loop._bootstrapper.is_bootstrap_done("test_account")
    assert ticker_loop._mock_generator.get_underlying_snapshot() is None


@pytest.mark.asyncio
async def test_services_work_together_for_mock_data_flow():
    """Test complete mock data flow through all services"""
    ticker_loop = MultiAccountTickerLoop()

    # 1. Mock generator seeds underlying
    class MockClient:
        async def get_quote(self, symbols):
            return {
                "NSE:NIFTY 50": {
                    "last_price": 24000.0,
                    "ohlc": {"open": 24000.0, "high": 24000.0, "low": 24000.0, "close": 24000.0},
                    "volume": 1000000,
                }
            }

        async def fetch_historical(self, **kwargs):
            return [{"close": 100.0, "volume": 1000, "oi": 5000}]

        async def get_last_price(self, symbol):
            return 100.0

    client = MockClient()
    await ticker_loop._mock_generator.ensure_underlying_seeded(client)

    # 2. Mock generator seeds options
    future_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
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

    await ticker_loop._mock_generator.ensure_options_seeded(client, [instrument])

    # 3. Generate underlying bar
    underlying_bar = await ticker_loop._mock_generator.generate_underlying_bar()
    assert underlying_bar is not None
    assert underlying_bar["close"] > 0

    # 4. Generate option snapshot
    option_snapshot = await ticker_loop._mock_generator.generate_option_snapshot(instrument)
    assert option_snapshot is not None
    assert option_snapshot.last_price > 0

    # 5. Verify bootstrap tracking (simulating account stream)
    account_id = "test_account"
    assert not ticker_loop._bootstrapper.is_bootstrap_done(account_id)
    ticker_loop._bootstrapper.mark_bootstrap_done(account_id)
    assert ticker_loop._bootstrapper.is_bootstrap_done(account_id)

    # 6. Complete flow - all services working together
    assert ticker_loop._mock_generator.get_state_size() == 1
    assert ticker_loop._bootstrapper.is_bootstrap_done(account_id)


@pytest.mark.asyncio
async def test_dependency_injection_allows_custom_mock_generator():
    """Test that custom MockDataGenerator can be injected"""
    from app.greeks_calculator import GreeksCalculator
    from zoneinfo import ZoneInfo

    # Create custom mock generator
    custom_mock_gen = MockDataGenerator(
        greeks_calculator=GreeksCalculator(),
        market_tz=ZoneInfo("Asia/Kolkata"),
        max_size=1000,  # Custom max size
    )

    # Inject into ticker loop
    ticker_loop = MultiAccountTickerLoop(mock_generator=custom_mock_gen)

    # Verify our custom instance was used
    assert ticker_loop._mock_generator is custom_mock_gen
    assert ticker_loop._mock_generator._max_size == 1000
