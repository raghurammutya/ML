"""
StocksBlitz Python SDK

Intuitive Python interface for algorithmic trading with advanced services
for alerts, messaging, calendar, and news.

Example:
    >>> from stocksblitz import TradingClient, AlertType, AlertPriority
    >>> client = TradingClient(api_url="http://localhost:8009", api_key="YOUR_API_KEY")
    >>> inst = client.Instrument("NIFTY25N0424500PE")
    >>>
    >>> # Trading
    >>> if inst['5m'].rsi[14] > 70:
    ...     client.Account().sell(inst, quantity=50)
    >>>
    >>> # Alerts
    >>> def on_alert(event):
    ...     print(f"Alert: {event.message}")
    >>> client.alerts.on(AlertType.PRICE, on_alert)
"""

__version__ = "0.2.0"
__author__ = "StocksBlitz"

from .client import TradingClient
from .instrument import Instrument
from .account import Account, Position, Order, Funds
from .accounts_collection import AccountsCollection, AccountProxy
from .filter import InstrumentFilter
from .strategy import Strategy, StrategyMetrics

# Services
from .services import AlertService, MessagingService, CalendarService, NewsService

# Enums
from .enums import (
    DataState,
    Exchange,
    TransactionType,
    OrderType,
    ProductType,
    Validity,
    OrderStatus,
    PositionType,
    Timeframe,
    AlertType,
    AlertPriority,
    MessageType,
    ReminderFrequency,
    NewsCategory,
    NewsSentiment,
    EventStatus,
    StrategyType,
    StrategyStatus,
)

# Types
from .types import (
    AlertEvent,
    Message,
    Reminder,
    NewsItem,
    OrderRequest,
    QuoteData,
    GreeksData,
)

# Exceptions
from .exceptions import (
    StocksBlitzError,
    InstrumentNotFoundError,
    InsufficientFundsError,
    InvalidOrderError,
    APIError,
    AuthenticationError,
    CacheError,
    DataUnavailableError,
    StaleDataError,
    InstrumentNotSubscribedError,
    IndicatorUnavailableError,
    DataValidationError,
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
    "AccountsCollection",
    "AccountProxy",

    # Filtering
    "InstrumentFilter",

    # Strategy
    "Strategy",
    "StrategyMetrics",

    # Services
    "AlertService",
    "MessagingService",
    "CalendarService",
    "NewsService",

    # Enums
    "DataState",
    "Exchange",
    "TransactionType",
    "OrderType",
    "ProductType",
    "Validity",
    "OrderStatus",
    "PositionType",
    "Timeframe",
    "AlertType",
    "AlertPriority",
    "MessageType",
    "ReminderFrequency",
    "NewsCategory",
    "NewsSentiment",
    "EventStatus",
    "StrategyType",
    "StrategyStatus",

    # Types
    "AlertEvent",
    "Message",
    "Reminder",
    "NewsItem",
    "OrderRequest",
    "QuoteData",
    "GreeksData",

    # Exceptions
    "StocksBlitzError",
    "InstrumentNotFoundError",
    "InsufficientFundsError",
    "InvalidOrderError",
    "APIError",
    "AuthenticationError",
    "CacheError",
    "DataUnavailableError",
    "StaleDataError",
    "InstrumentNotSubscribedError",
    "IndicatorUnavailableError",
    "DataValidationError",
]
