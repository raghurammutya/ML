"""
Basic tests for StocksBlitz SDK.

Run with: pytest tests/
"""

import pytest
from stocksblitz import TradingClient
from stocksblitz.exceptions import APIError


@pytest.fixture
def client():
    """Create client fixture."""
    return TradingClient(
        api_url="http://localhost:8009",
        api_key="test_api_key"
    )


def test_client_creation(client):
    """Test client initialization."""
    assert client is not None
    assert client.api_url == "http://localhost:8009"
    assert client.api_key == "test_api_key"


def test_instrument_creation(client):
    """Test instrument creation."""
    inst = client.Instrument("NIFTY25N0424500PE")
    assert inst is not None
    assert inst.tradingsymbol == "NIFTY25N0424500PE"


def test_account_creation(client):
    """Test account creation."""
    account = client.Account()
    assert account is not None
    assert account.account_id == "primary"


def test_timeframe_proxy(client):
    """Test timeframe proxy."""
    inst = client.Instrument("NIFTY25N0424500PE")
    tf = inst['5m']
    assert tf is not None


def test_candle_creation(client):
    """Test candle creation."""
    inst = client.Instrument("NIFTY25N0424500PE")
    candle = inst['5m'][0]
    assert candle is not None


# Add more tests for actual API calls when backend is running
# def test_fetch_ltp(client):
#     """Test fetching LTP."""
#     inst = client.Instrument("NIFTY25N0424500PE")
#     ltp = inst.ltp
#     assert isinstance(ltp, float)
#     assert ltp > 0
