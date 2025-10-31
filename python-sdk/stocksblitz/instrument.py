"""
Instrument, TimeframeProxy, and Candle classes.
"""

from typing import TYPE_CHECKING, Optional, Any, Dict
from datetime import datetime
from .indicators import IndicatorProxy
from .cache import cache_key
from .exceptions import InstrumentNotFoundError

if TYPE_CHECKING:
    from .api import APIClient


class Candle:
    """
    Represents a single OHLCV candle with indicator access.
    """

    def __init__(self, api_client: 'APIClient', symbol: str,
                 timeframe: str, offset: int = 0):
        """
        Initialize candle.

        Args:
            api_client: API client instance
            symbol: Trading symbol
            timeframe: Timeframe (e.g., "5min", "1h")
            offset: Candles back from current (0 = current)
        """
        self._api = api_client
        self._symbol = symbol
        self._timeframe = timeframe
        self._offset = offset
        self._data: Optional[Dict] = None

    def _get_ohlcv(self) -> Dict:
        """Fetch OHLCV data for this candle."""
        if self._data is not None:
            return self._data

        # Check cache
        key = cache_key("ohlcv", self._symbol, self._timeframe, self._offset)
        cached = self._api.cache.get(key)
        if cached is not None:
            self._data = cached
            return self._data

        # Fetch from API
        try:
            # For offset=0, we can use current quote
            if self._offset == 0:
                response = self._api.get(
                    f"/fo/quote",
                    params={"symbol": self._symbol},
                    cache_ttl=5  # Short cache for current quote
                )
                # TODO: API should return OHLC, for now using LTP
                self._data = {
                    "open": response.get("open", response.get("ltp")),
                    "high": response.get("high", response.get("ltp")),
                    "low": response.get("low", response.get("ltp")),
                    "close": response.get("ltp"),
                    "volume": response.get("volume", 0),
                    "time": datetime.now()
                }
            else:
                # For historical candles, use historical endpoint
                # TODO: Implement proper historical candle fetching
                # For now, this is a placeholder
                raise NotImplementedError(
                    "Historical candle fetching not yet implemented. "
                    "Use current candle (offset=0) for now."
                )

            # Cache it
            self._api.cache.set(key, self._data, ttl=60)
            return self._data

        except Exception as e:
            raise RuntimeError(f"Failed to fetch OHLCV for {self._symbol}: {e}")

    @property
    def open(self) -> float:
        """Open price."""
        return float(self._get_ohlcv()["open"])

    @property
    def high(self) -> float:
        """High price."""
        return float(self._get_ohlcv()["high"])

    @property
    def low(self) -> float:
        """Low price."""
        return float(self._get_ohlcv()["low"])

    @property
    def close(self) -> float:
        """Close price."""
        return float(self._get_ohlcv()["close"])

    @property
    def volume(self) -> int:
        """Volume."""
        return int(self._get_ohlcv()["volume"])

    @property
    def time(self) -> datetime:
        """Candle timestamp."""
        return self._get_ohlcv()["time"]

    def __getattr__(self, name: str) -> IndicatorProxy:
        """
        Access indicators as attributes.

        Args:
            name: Indicator name (e.g., "rsi", "sma", "macd")

        Returns:
            IndicatorProxy for lazy evaluation

        Examples:
            >>> candle.rsi[14]
            >>> candle.sma[20]
            >>> candle.macd[12, 26, 9]
        """
        # Avoid infinite recursion for private attributes
        if name.startswith("_"):
            raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

        return IndicatorProxy(
            self._api,
            self._symbol,
            self._timeframe,
            self._offset,
            name
        )

    def __repr__(self) -> str:
        return f"<Candle {self._symbol} {self._timeframe} offset={self._offset}>"


class TimeframeProxy:
    """
    Proxy for accessing timeframe-specific data.
    """

    def __init__(self, instrument: 'Instrument', timeframe: str):
        """
        Initialize timeframe proxy.

        Args:
            instrument: Parent instrument
            timeframe: Timeframe (e.g., "5m", "1h", "1d")
        """
        self._instrument = instrument
        self._timeframe = self._normalize_timeframe(timeframe)

    def __getitem__(self, offset: int) -> Candle:
        """
        Access candle N candles back.

        Args:
            offset: Number of candles back (0 = current)

        Returns:
            Candle instance

        Examples:
            >>> inst['5m'][0]  # Current candle
            >>> inst['5m'][3]  # 3 candles ago
        """
        return Candle(
            self._instrument._api,
            self._instrument.tradingsymbol,
            self._timeframe,
            offset
        )

    def __getattr__(self, name: str) -> Any:
        """
        Access current candle properties directly.

        Args:
            name: Property/indicator name

        Returns:
            Property value from current candle

        Examples:
            >>> inst['5m'].close  # Same as inst['5m'][0].close
            >>> inst['5m'].rsi[14]  # Same as inst['5m'][0].rsi[14]
        """
        # Avoid infinite recursion
        if name.startswith("_"):
            raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

        # Delegate to current candle (offset=0)
        return getattr(self[0], name)

    @staticmethod
    def _normalize_timeframe(tf: str) -> str:
        """
        Convert shorthand timeframe to full format.

        Args:
            tf: Timeframe (e.g., "5m", "1h", "1d")

        Returns:
            Normalized timeframe (e.g., "5min", "60min", "day")
        """
        mapping = {
            "1m": "1min",
            "5m": "5min",
            "15m": "15min",
            "30m": "30min",
            "1h": "60min",
            "1d": "day",
        }
        return mapping.get(tf.lower(), tf)

    def __repr__(self) -> str:
        return f"<TimeframeProxy {self._instrument.tradingsymbol} {self._timeframe}>"


class Instrument:
    """
    Represents a tradable instrument.

    Supports multiple notation formats:
    - Relative: "NSE@NIFTY@Nw+1@Put@OTM2"
    - Absolute: "NSE@NIFTY@28-Oct-2025@Put@24500"
    - Direct symbol: "NIFTY25N0424500PE"
    """

    def __init__(self, spec: str, api_client: 'APIClient' = None):
        """
        Initialize instrument.

        Args:
            spec: Instrument specification
            api_client: API client instance (set by TradingClient)

        Examples:
            >>> inst = Instrument("NSE@NIFTY@Nw+1@Put@OTM2")
            >>> inst = Instrument("NSE@NIFTY@28-Oct-2025@Put@24500")
            >>> inst = Instrument("NIFTY25N0424500PE")
        """
        self.spec = spec
        self._api = api_client
        self._tradingsymbol: Optional[str] = None
        self._quote_data: Optional[Dict] = None
        self._greeks_data: Optional[Dict] = None

        # Parse spec to get tradingsymbol
        self._resolve_tradingsymbol()

    def _resolve_tradingsymbol(self):
        """
        Resolve spec to actual tradingsymbol.

        For now, we assume spec is already a tradingsymbol.
        TODO: Implement proper parsing of relative/absolute formats.
        """
        # Simple case: spec is already a tradingsymbol
        if "@" not in self.spec:
            self._tradingsymbol = self.spec
        else:
            # TODO: Parse complex spec and resolve to tradingsymbol
            # For now, raise NotImplementedError
            raise NotImplementedError(
                "Complex instrument notation (NSE@NIFTY@...) not yet implemented. "
                "Use direct tradingsymbol for now (e.g., 'NIFTY25N0424500PE')"
            )

    @property
    def tradingsymbol(self) -> str:
        """Get trading symbol."""
        if self._tradingsymbol is None:
            raise InstrumentNotFoundError(f"Could not resolve instrument: {self.spec}")
        return self._tradingsymbol

    def _fetch_quote(self) -> Dict:
        """Fetch current quote data."""
        if self._quote_data is not None:
            return self._quote_data

        # Check cache
        key = cache_key("quote", self.tradingsymbol)
        cached = self._api.cache.get(key)
        if cached is not None:
            self._quote_data = cached
            return self._quote_data

        # Fetch from API
        try:
            self._quote_data = self._api.get(
                "/fo/quote",
                params={"symbol": self.tradingsymbol},
                cache_ttl=5  # 5 second cache for quotes
            )
            return self._quote_data

        except Exception as e:
            raise RuntimeError(f"Failed to fetch quote for {self.tradingsymbol}: {e}")

    def _fetch_greeks(self) -> Dict:
        """Fetch option Greeks."""
        if self._greeks_data is not None:
            return self._greeks_data

        # Check cache
        key = cache_key("greeks", self.tradingsymbol)
        cached = self._api.cache.get(key)
        if cached is not None:
            self._greeks_data = cached
            return self._greeks_data

        # Fetch from API
        try:
            # TODO: Implement Greeks API endpoint
            # For now, return placeholder
            self._greeks_data = {
                "delta": 0.0,
                "gamma": 0.0,
                "theta": 0.0,
                "vega": 0.0,
                "iv": 0.0
            }
            return self._greeks_data

        except Exception as e:
            raise RuntimeError(f"Failed to fetch Greeks for {self.tradingsymbol}: {e}")

    @property
    def ltp(self) -> float:
        """Last traded price."""
        return float(self._fetch_quote().get("ltp", 0))

    @property
    def volume(self) -> int:
        """Volume."""
        return int(self._fetch_quote().get("volume", 0))

    @property
    def oi(self) -> int:
        """Open interest."""
        return int(self._fetch_quote().get("oi", 0))

    # Option Greeks
    @property
    def delta(self) -> float:
        """Option delta."""
        return float(self._fetch_greeks().get("delta", 0))

    @property
    def gamma(self) -> float:
        """Option gamma."""
        return float(self._fetch_greeks().get("gamma", 0))

    @property
    def theta(self) -> float:
        """Option theta."""
        return float(self._fetch_greeks().get("theta", 0))

    @property
    def vega(self) -> float:
        """Option vega."""
        return float(self._fetch_greeks().get("vega", 0))

    @property
    def iv(self) -> float:
        """Implied volatility."""
        return float(self._fetch_greeks().get("iv", 0))

    def __getitem__(self, timeframe: str) -> TimeframeProxy:
        """
        Access timeframe-specific data.

        Args:
            timeframe: Timeframe (e.g., "5m", "1h", "1d")

        Returns:
            TimeframeProxy instance

        Examples:
            >>> inst['5m']
            >>> inst['1h']
        """
        return TimeframeProxy(self, timeframe)

    def __repr__(self) -> str:
        return f"<Instrument {self.tradingsymbol}>"

    def __str__(self) -> str:
        return self.tradingsymbol
