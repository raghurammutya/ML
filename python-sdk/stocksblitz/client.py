"""
Main TradingClient class - entry point for the SDK.
"""

from typing import Optional
from .api import APIClient
from .cache import SimpleCache
from .instrument import Instrument
from .account import Account
from .filter import InstrumentFilter
from .services import AlertService, MessagingService, CalendarService, NewsService


class TradingClient:
    """
    Main client for StocksBlitz trading API.

    This is the primary entry point for using the SDK.

    Example:
        >>> from stocksblitz import TradingClient
        >>> client = TradingClient(
        ...     api_url="http://localhost:8009",
        ...     api_key="sb_XXXXXXXX_YYYYYYYY"
        ... )
        >>> inst = client.Instrument("NIFTY25N0424500PE")
        >>> if inst['5m'].rsi[14] > 70:
        ...     client.Account().sell(inst, quantity=50)
    """

    def __init__(self, api_url: str, api_key: str,
                 cache: Optional[SimpleCache] = None):
        """
        Initialize trading client.

        Args:
            api_url: Base URL of the API (e.g., "http://localhost:8009")
            api_key: API key for authentication
            cache: Optional cache instance (creates new if not provided)

        Example:
            >>> client = TradingClient(
            ...     api_url="http://localhost:8009",
            ...     api_key="sb_30d4d5ea_bbb52c64cc4eb2536fdd7b44861c93e4b30b50c6"
            ... )
        """
        self._cache = cache or SimpleCache(default_ttl=60)
        self._api = APIClient(api_url, api_key, self._cache)

        # Store for easy access
        self.api_url = api_url
        self.api_key = api_key

        # Initialize services
        self._alerts = AlertService(self._api)
        self._messaging = MessagingService(self._api)
        self._calendar = CalendarService(self._api)
        self._news = NewsService(self._api)

    def Instrument(self, spec: str) -> Instrument:
        """
        Create Instrument instance.

        Args:
            spec: Instrument specification

        Returns:
            Instrument object

        Examples:
            >>> inst = client.Instrument("NIFTY25N0424500PE")
            >>> inst = client.Instrument("NSE@NIFTY@Nw+1@Put@OTM2")  # TODO: Not yet implemented
        """
        inst = Instrument(spec, api_client=self._api)
        return inst

    def Account(self, account_id: str = "primary") -> Account:
        """
        Create Account instance.

        Args:
            account_id: Account identifier

        Returns:
            Account object

        Examples:
            >>> account = client.Account()
            >>> account = client.Account("secondary")
        """
        account = Account(account_id, api_client=self._api)
        return account

    def InstrumentFilter(self, pattern: str) -> InstrumentFilter:
        """
        Create InstrumentFilter instance.

        Args:
            pattern: Instrument pattern to filter

        Returns:
            InstrumentFilter object

        Examples:
            >>> filter = client.InstrumentFilter("NSE@NIFTY@Nw@Put")
            >>> results = filter.where(lambda i: i.ltp > 50)
        """
        filter_obj = InstrumentFilter(pattern, api_client=self._api)
        return filter_obj

    @property
    def alerts(self) -> AlertService:
        """
        Access alert service.

        Returns:
            AlertService instance

        Example:
            >>> # Register alert callback
            >>> def on_alert(event):
            ...     print(f"Alert: {event.message}")
            >>> client.alerts.on(AlertType.PRICE, on_alert)
            >>>
            >>> # Raise alert
            >>> client.alerts.raise_alert(
            ...     alert_type=AlertType.PRICE,
            ...     priority=AlertPriority.HIGH,
            ...     symbol="NIFTY50",
            ...     message="Price above 24000"
            ... )
        """
        return self._alerts

    @property
    def messaging(self) -> MessagingService:
        """
        Access messaging service.

        Returns:
            MessagingService instance

        Example:
            >>> # Subscribe to topic
            >>> def on_message(msg):
            ...     print(f"Message: {msg.content}")
            >>> client.messaging.subscribe("trade-signals", on_message)
            >>>
            >>> # Publish message
            >>> client.messaging.publish(
            ...     topic="trade-signals",
            ...     content={"symbol": "NIFTY50", "signal": "BUY"}
            ... )
        """
        return self._messaging

    @property
    def calendar(self) -> CalendarService:
        """
        Access calendar service.

        Returns:
            CalendarService instance

        Example:
            >>> # Set reminder
            >>> reminder_id = client.calendar.set_reminder(
            ...     title="Close positions",
            ...     scheduled_at=datetime(2025, 10, 31, 15, 30),
            ...     callback=lambda r: print("Reminder triggered!")
            ... )
            >>>
            >>> # Start monitoring
            >>> client.calendar.start_monitoring()
        """
        return self._calendar

    @property
    def news(self) -> NewsService:
        """
        Access news service.

        Returns:
            NewsService instance

        Example:
            >>> # Subscribe to news
            >>> def on_news(item):
            ...     if item.sentiment == NewsSentiment.NEGATIVE:
            ...         print(f"Negative news: {item.title}")
            >>> client.news.subscribe(
            ...     callback=on_news,
            ...     category=NewsCategory.MARKET
            ... )
            >>>
            >>> # Get latest news
            >>> items = client.news.get_news(
            ...     symbols=["NIFTY50"],
            ...     limit=10
            ... )
        """
        return self._news

    def clear_cache(self):
        """Clear all cached data."""
        self._cache.clear()

    def __repr__(self) -> str:
        return f"<TradingClient api_url='{self.api_url}'>"
