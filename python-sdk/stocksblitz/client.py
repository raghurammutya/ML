"""
Main TradingClient class - entry point for the SDK.
"""

from typing import Optional
from .api import APIClient
from .cache import SimpleCache
from .instrument import Instrument
from .account import Account
from .filter import InstrumentFilter


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

    def clear_cache(self):
        """Clear all cached data."""
        self._cache.clear()

    def __repr__(self) -> str:
        return f"<TradingClient api_url='{self.api_url}'>"
