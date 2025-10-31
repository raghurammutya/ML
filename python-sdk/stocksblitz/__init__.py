"""
StocksBlitz Python SDK

Intuitive Python interface for algorithmic trading with the StocksBlitz platform.

Example:
    >>> from stocksblitz import TradingClient
    >>> client = TradingClient(api_url="http://localhost:8009", api_key="YOUR_API_KEY")
    >>> inst = client.Instrument("NSE@NIFTY@Nw+1@Put@OTM2")
    >>> if inst['5m'].rsi[14] > 70:
    ...     client.Account().sell(inst, quantity=50)
"""

__version__ = "0.1.0"
__author__ = "StocksBlitz"

from .client import TradingClient
from .instrument import Instrument
from .account import Account, Position, Order, Funds
from .filter import InstrumentFilter
from .exceptions import (
    StocksBlitzError,
    InstrumentNotFoundError,
    InsufficientFundsError,
    InvalidOrderError,
    APIError,
    CacheError,
)

__all__ = [
    # Main client
    "TradingClient",

    # Instrument classes
    "Instrument",

    # Account classes
    "Account",
    "Position",
    "Order",
    "Funds",

    # Filtering
    "InstrumentFilter",

    # Exceptions
    "StocksBlitzError",
    "InstrumentNotFoundError",
    "InsufficientFundsError",
    "InvalidOrderError",
    "APIError",
    "CacheError",
]
