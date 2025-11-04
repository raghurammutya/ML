"""
Main TradingClient class - entry point for the SDK.
"""

from typing import Optional
from pathlib import Path
from .api import APIClient
from .cache import SimpleCache
from .instrument import Instrument
from .account import Account
from .filter import InstrumentFilter
from .strategy import Strategy
from .services import AlertService, MessagingService, CalendarService, NewsService
from .indicator_registry import IndicatorRegistry


class TradingClient:
    """
    Main client for StocksBlitz trading API.

    This is the primary entry point for using the SDK.

    Supports two authentication methods:
    1. API Key (for server-to-server, bots, scripts)
    2. JWT (for user applications with username/password)

    Example (API Key):
        >>> from stocksblitz import TradingClient
        >>> client = TradingClient(
        ...     api_url="http://localhost:8081",
        ...     api_key="sb_30d4d5ea_bbb52c64cc4eb2536fdd7b44861c93e4b30b50c6"
        ... )
        >>> inst = client.Instrument("NIFTY25N0424500PE")
        >>> if inst['5m'].rsi[14] > 70:
        ...     client.Account().sell(inst, quantity=50)

    Example (JWT):
        >>> client = TradingClient.from_credentials(
        ...     api_url="http://localhost:8081",
        ...     user_service_url="http://localhost:8001",
        ...     username="trader@example.com",
        ...     password="my_password"
        ... )
        >>> inst = client.Instrument("NIFTY50")
        >>> inst['5m'].close
    """

    def __init__(
        self,
        api_url: str,
        api_key: Optional[str] = None,
        user_service_url: Optional[str] = None,
        cache: Optional[SimpleCache] = None,
        enable_disk_cache: bool = True,
        cache_dir: Optional[Path] = None,
        cache_ttl: int = 86400
    ):
        """
        Initialize trading client with API key or JWT setup.

        Args:
            api_url: Base URL of the backend API (e.g., "http://localhost:8081")
            api_key: API key for authentication (for server-to-server use)
            user_service_url: User service URL (for JWT authentication)
            cache: Optional cache instance (creates new if not provided)
            enable_disk_cache: Enable persistent disk cache for indicator registry (default: True)
            cache_dir: Custom cache directory for indicator registry (default: ~/.stocksblitz)
            cache_ttl: Cache TTL in seconds for indicator registry (default: 86400 = 24 hours)

        Note:
            For JWT authentication, provide user_service_url and then call login():
                >>> client = TradingClient(
                ...     api_url="http://localhost:8081",
                ...     user_service_url="http://localhost:8001"
                ... )
                >>> client.login("user@example.com", "password")

            Or use the from_credentials() class method for easier JWT setup:
                >>> client = TradingClient.from_credentials(
                ...     api_url="http://localhost:8081",
                ...     user_service_url="http://localhost:8001",
                ...     username="user@example.com",
                ...     password="password"
                ... )
        """
        if not api_key and not user_service_url:
            raise ValueError(
                "Either 'api_key' or 'user_service_url' must be provided. "
                "For API key auth, pass api_key. "
                "For JWT auth, pass user_service_url and call login() or use from_credentials()."
            )

        self._cache = cache or SimpleCache(default_ttl=60)
        self._api = APIClient(api_url, api_key=api_key, user_service_url=user_service_url, cache=self._cache)

        # Store for easy access
        self.api_url = api_url
        self.api_key = api_key
        self.user_service_url = user_service_url

        # Initialize services
        self._alerts = AlertService(self._api)
        self._messaging = MessagingService(self._api)
        self._calendar = CalendarService(self._api)
        self._news = NewsService(self._api)

        # Initialize indicator registry with disk caching
        self._indicators = IndicatorRegistry(
            self._api,
            enable_disk_cache=enable_disk_cache,
            cache_dir=cache_dir,
            cache_ttl=cache_ttl
        )

    @classmethod
    def from_credentials(
        cls,
        api_url: str,
        user_service_url: str,
        username: str,
        password: str,
        persist_session: bool = True,
        cache: Optional[SimpleCache] = None
    ) -> "TradingClient":
        """
        Create TradingClient with username/password authentication (JWT).

        This is the recommended method for user-facing applications.
        It will automatically:
        - Login to user_service
        - Obtain JWT access + refresh tokens
        - Auto-refresh tokens as needed

        Args:
            api_url: Backend API URL (e.g., "http://localhost:8081")
            user_service_url: User service URL (e.g., "http://localhost:8001")
            username: User email/username
            password: User password
            persist_session: If True, obtain refresh token for long-lived session
            cache: Optional cache instance

        Returns:
            Authenticated TradingClient instance

        Raises:
            AuthenticationError: If login fails

        Example:
            >>> from stocksblitz import TradingClient
            >>> client = TradingClient.from_credentials(
            ...     api_url="http://localhost:8081",
            ...     user_service_url="http://localhost:8001",
            ...     username="trader@example.com",
            ...     password="secure_password123"
            ... )
            >>> # Client is now authenticated and ready to use
            >>> inst = client.Instrument("NIFTY50")
            >>> print(inst['5m'].close)
        """
        # Create instance with JWT setup
        instance = cls(
            api_url=api_url,
            user_service_url=user_service_url,
            cache=cache
        )

        # Perform login to get JWT tokens
        instance._api.login(username, password, persist_session=persist_session)

        return instance

    def login(self, username: str, password: str, persist_session: bool = True):
        """
        Login with username/password (for JWT authentication).

        Only needed if you didn't use from_credentials() class method.

        Args:
            username: User email/username
            password: User password
            persist_session: If True, obtain refresh token for long-lived session

        Returns:
            Login response dict

        Raises:
            AuthenticationError: If login fails

        Example:
            >>> client = TradingClient(
            ...     api_url="http://localhost:8081",
            ...     user_service_url="http://localhost:8001"
            ... )
            >>> client.login("user@example.com", "password")
        """
        return self._api.login(username, password, persist_session=persist_session)

    def logout(self):
        """
        Logout and clear authentication tokens.

        For JWT auth, this calls user_service logout endpoint.
        For API key auth, this is a no-op.

        Example:
            >>> client.logout()
        """
        self._api.logout()

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

    def Strategy(
        self,
        strategy_id: Optional[int] = None,
        strategy_name: Optional[str] = None,
        strategy_type: str = "custom",
        **kwargs
    ) -> Strategy:
        """
        Create or load Strategy instance.

        Args:
            strategy_id: Existing strategy ID (loads existing strategy)
            strategy_name: Strategy name (creates new or loads existing)
            strategy_type: Strategy type (default: "custom")
            **kwargs: Additional strategy parameters

        Returns:
            Strategy object

        Examples:
            >>> # Load existing strategy by ID
            >>> strategy = client.Strategy(strategy_id=123)
            >>>
            >>> # Create/load strategy by name
            >>> strategy = client.Strategy(
            ...     strategy_name="My RSI Strategy",
            ...     strategy_type="mean_reversion"
            ... )
            >>>
            >>> # Execute trades within strategy
            >>> with strategy:
            ...     inst = client.Instrument("NIFTY50")
            ...     if inst['5m'].rsi[14] < 30:
            ...         strategy.buy(inst, quantity=50)
            >>>
            >>> # Get strategy metrics
            >>> metrics = strategy.metrics
            >>> print(f"P&L: {metrics.total_pnl}, ROI: {metrics.roi}%")
        """
        strategy = Strategy(
            api_client=self._api,
            strategy_id=strategy_id,
            strategy_name=strategy_name,
            strategy_type=strategy_type,
            **kwargs
        )
        return strategy

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

    @property
    def indicators(self) -> IndicatorRegistry:
        """
        Access indicator registry.

        Returns:
            IndicatorRegistry instance

        Example:
            >>> # List available indicators
            >>> indicators = client.indicators.list_indicators()
            >>> print(f"Total indicators: {len(indicators)}")
            >>>
            >>> # Get indicator by category
            >>> momentum_indicators = client.indicators.list_indicators(category="momentum")
            >>>
            >>> # Validate indicator parameters
            >>> is_valid, error = client.indicators.validate_indicator(
            ...     "RSI",
            ...     {"length": 14, "scalar": 100}
            ... )
            >>>
            >>> # Force refresh after adding custom indicator
            >>> client.indicators.clear_cache()
            >>> client.indicators.fetch_indicators()
        """
        return self._indicators

    def clear_cache(self):
        """Clear all cached data."""
        self._cache.clear()

    def __repr__(self) -> str:
        auth_method = "API Key" if self.api_key else "JWT"
        return f"<TradingClient api_url='{self.api_url}' auth='{auth_method}'>"
