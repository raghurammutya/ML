"""
Instrument, TimeframeProxy, and Candle classes.
"""

from typing import TYPE_CHECKING, Optional, Any, Dict
from datetime import datetime
import logging
from .indicators import IndicatorProxy
from .cache import cache_key
from .exceptions import (
    InstrumentNotFoundError,
    DataUnavailableError,
    DataValidationError,
    InstrumentNotSubscribedError
)
from .enums import DataState

logger = logging.getLogger(__name__)

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
        """
        Fetch OHLCV data for this candle.

        Raises:
            NotImplementedError: For historical candles (offset > 0)
            DataUnavailableError: If data cannot be fetched
        """
        if self._data is not None:
            return self._data

        # Check cache
        key = cache_key("ohlcv", self._symbol, self._timeframe, self._offset)
        cached = self._api.cache.get(key)
        if cached is not None:
            self._data = cached
            return self._data

        logger.info(f"Fetching OHLCV for {self._symbol} {self._timeframe} offset={self._offset}")

        # Fetch from API
        try:
            # For offset=0, we can use current quote from monitor snapshot
            if self._offset == 0:
                # Extract underlying from symbol
                import re
                match = re.match(r'^(NIFTY|BANKNIFTY|FINNIFTY)', self._symbol)
                if match:
                    underlying = match.group(1)
                else:
                    # Direct underlying symbol
                    underlying = self._symbol.replace(" ", "").replace("50", "").upper()
                    if "NIFTY" in underlying:
                        underlying = "NIFTY"

                response = self._api.get(
                    "/monitor/snapshot",
                    params={"underlying": underlying},
                    cache_ttl=5  # Short cache for current quote
                )

                # Extract data from snapshot
                if "underlying" in response and response["underlying"]["symbol"] == underlying:
                    underlying_data = response["underlying"]
                    # TODO: API should return proper OHLC for timeframe
                    # For now using snapshot data which has open/high/low/close for the day
                    self._data = {
                        "open": underlying_data.get("open", underlying_data.get("close", 0)),
                        "high": underlying_data.get("high", underlying_data.get("close", 0)),
                        "low": underlying_data.get("low", underlying_data.get("close", 0)),
                        "close": underlying_data.get("close", 0),
                        "volume": underlying_data.get("volume", 0),
                        "time": datetime.now()
                    }
                elif "options" in response and self._symbol in response["options"]:
                    # Option data
                    option_data = response["options"][self._symbol]
                    self._data = {
                        "open": option_data.get("ltp", 0),  # No OHLC for options yet
                        "high": option_data.get("ltp", 0),
                        "low": option_data.get("ltp", 0),
                        "close": option_data.get("ltp", 0),
                        "volume": option_data.get("volume", 0),
                        "time": datetime.now()
                    }
                else:
                    raise DataUnavailableError(
                        f"OHLCV not available for {self._symbol}",
                        reason="not_in_snapshot"
                    )
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

        except NotImplementedError:
            # Re-raise NotImplementedError
            raise
        except DataUnavailableError:
            # Re-raise our custom exceptions
            raise
        except Exception as e:
            logger.error(f"Failed to fetch OHLCV for {self._symbol}: {e}", exc_info=True)
            raise DataUnavailableError(
                f"Failed to fetch OHLCV for {self._symbol}: {e}",
                reason="api_error"
            )

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
        """
        Fetch current quote data with data quality metadata.

        Returns:
            Dict with quote data and metadata:
            - ltp, volume, oi: Quote values
            - _state: DataState enum indicating data quality
            - _timestamp: When data was fetched
            - _data_age: Age of data in seconds (if available)
            - _reason: Human-readable reason if not VALID

        Raises:
            DataUnavailableError: If data cannot be fetched
            DataValidationError: If data fails validation
        """
        if self._quote_data is not None:
            return self._quote_data

        # Check cache
        key = cache_key("quote", self.tradingsymbol)
        cached = self._api.cache.get(key)
        if cached is not None:
            self._quote_data = cached
            return self._quote_data

        logger.info(f"Fetching quote for {self.tradingsymbol}")

        # Fetch from API using monitor/snapshot
        try:
            # Try to extract underlying symbol
            underlying = self._extract_underlying(self.tradingsymbol)

            # Fetch snapshot
            response = self._api.get(
                "/monitor/snapshot",
                params={"underlying": underlying},
                cache_ttl=5  # 5 second cache for quotes
            )

            fetch_time = datetime.now()

            # Check if this is the underlying itself or an option
            if "underlying" in response and response["underlying"]["symbol"] == underlying:
                # This is the underlying
                underlying_data = response["underlying"]

                # Extract data
                ltp = underlying_data.get("close", 0)
                volume = underlying_data.get("volume", 0)
                data_ts = underlying_data.get("ts")

                # Validate data
                self._validate_quote_data(ltp, volume)

                # Determine data state
                data_state = DataState.VALID
                data_age = None
                reason = None

                if data_ts:
                    data_age = fetch_time.timestamp() - data_ts
                    if data_age > 10:
                        data_state = DataState.STALE
                        reason = f"Data is {data_age:.1f} seconds old"
                        logger.warning(f"Stale data for {self.tradingsymbol}: {reason}")

                self._quote_data = {
                    "ltp": ltp,
                    "open": underlying_data.get("open", 0),
                    "high": underlying_data.get("high", 0),
                    "low": underlying_data.get("low", 0),
                    "volume": volume,
                    "oi": 0,  # Underlying doesn't have OI
                    "_state": data_state,
                    "_timestamp": fetch_time,
                    "_data_age": data_age,
                    "_reason": reason
                }

                logger.info(f"Quote fetched for {self.tradingsymbol}: LTP={ltp}, state={data_state}")

            elif "options" in response and self.tradingsymbol in response["options"]:
                # This is an option in the chain
                option_data = response["options"][self.tradingsymbol]

                ltp = option_data.get("ltp", 0)
                volume = option_data.get("volume", 0)

                # Validate data
                self._validate_quote_data(ltp, volume)

                self._quote_data = {
                    "ltp": ltp,
                    "volume": volume,
                    "oi": option_data.get("oi", 0),
                    "bid": option_data.get("bid", 0),
                    "ask": option_data.get("ask", 0),
                    "_state": DataState.VALID,
                    "_timestamp": fetch_time,
                    "_data_age": None,
                    "_reason": None
                }

                logger.info(f"Option quote fetched for {self.tradingsymbol}: LTP={ltp}")

            else:
                # Option not in snapshot - not subscribed
                logger.warning(f"{self.tradingsymbol} not found in monitor snapshot")
                raise DataUnavailableError(
                    f"Quote not available for {self.tradingsymbol}",
                    reason="not_subscribed"
                )

            return self._quote_data

        except DataUnavailableError:
            # Re-raise our custom exceptions
            raise
        except DataValidationError:
            # Re-raise validation errors
            raise
        except Exception as e:
            logger.error(f"Failed to fetch quote for {self.tradingsymbol}: {e}", exc_info=True)
            raise DataUnavailableError(
                f"Failed to fetch quote for {self.tradingsymbol}: {e}",
                reason="api_error"
            )

    def _validate_quote_data(self, ltp: float, volume: int) -> None:
        """
        Validate quote data for sanity.

        Args:
            ltp: Last traded price
            volume: Volume

        Raises:
            DataValidationError: If data fails validation
        """
        if ltp < 0:
            raise DataValidationError(
                f"Invalid LTP: {ltp} (negative price)",
                field="ltp",
                value=ltp
            )

        if ltp > 1000000:  # Sanity check: price > 10 lakh
            logger.warning(f"Unusually high LTP: {ltp}")

        if volume < 0:
            raise DataValidationError(
                f"Invalid volume: {volume} (negative volume)",
                field="volume",
                value=volume
            )

    def _extract_underlying(self, symbol: str) -> str:
        """
        Extract underlying symbol from option symbol.

        Args:
            symbol: Trading symbol

        Returns:
            Underlying symbol (e.g., "NIFTY", "BANKNIFTY")

        Raises:
            ValueError: If underlying cannot be extracted

        Examples:
            >>> _extract_underlying("NIFTY25N0724500PE")
            'NIFTY'
            >>> _extract_underlying("BANKNIFTY25N07...")
            'BANKNIFTY'
        """
        import re

        # Pattern for option symbols: NIFTY25N0724500PE
        match = re.match(r'^(NIFTY|BANKNIFTY|FINNIFTY)(\d{2}[A-Z]\d{2})', symbol)
        if match:
            return match.group(1)

        # Direct underlying symbols
        normalized = symbol.replace(" ", "").upper()
        known_underlyings = {"NIFTY", "NIFTY50", "BANKNIFTY", "FINNIFTY", "SENSEX"}

        if normalized in known_underlyings:
            # Normalize NIFTY50 -> NIFTY
            return "NIFTY" if "NIFTY" in normalized else normalized

        # Unknown pattern - raise error instead of guessing
        logger.error(f"Cannot extract underlying from '{symbol}'")
        raise ValueError(
            f"Cannot extract underlying from '{symbol}'. "
            f"Please use valid option symbols or direct underlying symbols."
        )

    def _fetch_greeks(self) -> Dict:
        """
        Fetch option Greeks with data quality metadata.

        Returns:
            Dict with Greeks and metadata:
            - delta, gamma, theta, vega, iv: Greek values
            - _state: DataState enum indicating data quality
            - _timestamp: When data was fetched
            - _reason: Human-readable reason if not VALID

        Raises:
            InstrumentNotSubscribedError: If option not in snapshot
            DataUnavailableError: If data cannot be fetched
        """
        if self._greeks_data is not None:
            return self._greeks_data

        # Check cache
        key = cache_key("greeks", self.tradingsymbol)
        cached = self._api.cache.get(key)
        if cached is not None:
            self._greeks_data = cached
            return self._greeks_data

        logger.info(f"Fetching Greeks for {self.tradingsymbol}")

        # Fetch from API using monitor/snapshot
        try:
            underlying = self._extract_underlying(self.tradingsymbol)

            # Fetch snapshot
            response = self._api.get(
                "/monitor/snapshot",
                params={"underlying": underlying},
                cache_ttl=5
            )

            fetch_time = datetime.now()

            # Check if this option is in the chain with Greeks
            if "options" in response and self.tradingsymbol in response["options"]:
                option_data = response["options"][self.tradingsymbol]

                # Extract Greeks
                delta = option_data.get("delta", 0.0)
                gamma = option_data.get("gamma", 0.0)
                theta = option_data.get("theta", 0.0)
                vega = option_data.get("vega", 0.0)
                iv = option_data.get("iv", 0.0)

                # Check if Greeks are actually populated (not all zeros)
                has_greeks = any([delta, gamma, theta, vega, iv])

                if has_greeks:
                    data_state = DataState.VALID
                    reason = None
                    logger.info(f"Greeks fetched for {self.tradingsymbol}: delta={delta:.4f}")
                else:
                    data_state = DataState.NO_DATA
                    reason = "Greeks not computed (option may not be subscribed or not enough data)"
                    logger.warning(f"Greeks unavailable for {self.tradingsymbol}: {reason}")

                self._greeks_data = {
                    "delta": delta,
                    "gamma": gamma,
                    "theta": theta,
                    "vega": vega,
                    "iv": iv,
                    "_state": data_state,
                    "_timestamp": fetch_time,
                    "_reason": reason
                }
            else:
                # Not in snapshot - option not subscribed
                logger.warning(f"{self.tradingsymbol} not found in monitor snapshot for Greeks")

                raise InstrumentNotSubscribedError(
                    f"Greeks not available for {self.tradingsymbol} (option not in monitor snapshot)",
                    reason="not_subscribed"
                )

            # Cache it
            self._api.cache.set(key, self._greeks_data, ttl=5)
            return self._greeks_data

        except InstrumentNotSubscribedError:
            # Re-raise specific exception
            raise
        except DataUnavailableError:
            # Re-raise our custom exceptions
            raise
        except Exception as e:
            logger.error(f"Failed to fetch Greeks for {self.tradingsymbol}: {e}", exc_info=True)
            raise DataUnavailableError(
                f"Failed to fetch Greeks for {self.tradingsymbol}: {e}",
                reason="api_error"
            )

    @property
    def ltp(self) -> float:
        """
        Last traded price.

        Note: Check quote data state before making trading decisions.
        Use inst._fetch_quote()['_state'] to verify data quality.
        """
        quote = self._fetch_quote()

        # Warn on stale data
        if quote.get("_state") == DataState.STALE:
            import warnings
            warnings.warn(
                f"Stale quote data for {self.tradingsymbol}: {quote.get('_reason')}",
                UserWarning,
                stacklevel=2
            )

        return float(quote.get("ltp", 0))

    @property
    def volume(self) -> int:
        """
        Volume.

        Note: Check quote data state before making trading decisions.
        Use inst._fetch_quote()['_state'] to verify data quality.
        """
        quote = self._fetch_quote()

        # Warn on stale data
        if quote.get("_state") == DataState.STALE:
            import warnings
            warnings.warn(
                f"Stale quote data for {self.tradingsymbol}: {quote.get('_reason')}",
                UserWarning,
                stacklevel=2
            )

        return int(quote.get("volume", 0))

    @property
    def oi(self) -> int:
        """
        Open interest.

        Note: Check quote data state before making trading decisions.
        Use inst._fetch_quote()['_state'] to verify data quality.
        """
        quote = self._fetch_quote()

        # Warn on stale data
        if quote.get("_state") == DataState.STALE:
            import warnings
            warnings.warn(
                f"Stale quote data for {self.tradingsymbol}: {quote.get('_reason')}",
                UserWarning,
                stacklevel=2
            )

        return int(quote.get("oi", 0))

    @property
    def bid(self) -> float:
        """Bid price."""
        return float(self._fetch_quote().get("bid", 0))

    @property
    def ask(self) -> float:
        """Ask price."""
        return float(self._fetch_quote().get("ask", 0))

    @property
    def greeks(self) -> Dict:
        """
        Get all Greeks as a dictionary.

        Returns:
            Dict with keys: delta, gamma, theta, vega, iv, _state, _timestamp, _reason

        Example:
            >>> greeks = inst.greeks
            >>> if greeks['_state'] == DataState.VALID:
            ...     print(f"Delta: {greeks['delta']:.4f}, IV: {greeks['iv']:.2%}")
            >>> else:
            ...     print(f"Greeks unavailable: {greeks['_reason']}")

        Note: Always check greeks['_state'] before using Greek values for trading.
        """
        greeks = self._fetch_greeks()

        # Warn on missing/stale Greeks
        if greeks.get("_state") == DataState.NO_DATA:
            import warnings
            warnings.warn(
                f"Greeks not available for {self.tradingsymbol}: {greeks.get('_reason')}",
                UserWarning,
                stacklevel=2
            )

        return greeks

    # Option Greeks (individual properties)
    @property
    def delta(self) -> float:
        """
        Option delta.

        Note: Check inst.greeks['_state'] to verify data quality before trading.
        """
        greeks = self._fetch_greeks()

        # Warn on missing Greeks
        if greeks.get("_state") == DataState.NO_DATA:
            import warnings
            warnings.warn(
                f"Greeks not available for {self.tradingsymbol}: {greeks.get('_reason')}",
                UserWarning,
                stacklevel=2
            )

        return float(greeks.get("delta", 0))

    @property
    def gamma(self) -> float:
        """
        Option gamma.

        Note: Check inst.greeks['_state'] to verify data quality before trading.
        """
        greeks = self._fetch_greeks()

        # Warn on missing Greeks
        if greeks.get("_state") == DataState.NO_DATA:
            import warnings
            warnings.warn(
                f"Greeks not available for {self.tradingsymbol}: {greeks.get('_reason')}",
                UserWarning,
                stacklevel=2
            )

        return float(greeks.get("gamma", 0))

    @property
    def theta(self) -> float:
        """
        Option theta.

        Note: Check inst.greeks['_state'] to verify data quality before trading.
        """
        greeks = self._fetch_greeks()

        # Warn on missing Greeks
        if greeks.get("_state") == DataState.NO_DATA:
            import warnings
            warnings.warn(
                f"Greeks not available for {self.tradingsymbol}: {greeks.get('_reason')}",
                UserWarning,
                stacklevel=2
            )

        return float(greeks.get("theta", 0))

    @property
    def vega(self) -> float:
        """
        Option vega.

        Note: Check inst.greeks['_state'] to verify data quality before trading.
        """
        greeks = self._fetch_greeks()

        # Warn on missing Greeks
        if greeks.get("_state") == DataState.NO_DATA:
            import warnings
            warnings.warn(
                f"Greeks not available for {self.tradingsymbol}: {greeks.get('_reason')}",
                UserWarning,
                stacklevel=2
            )

        return float(greeks.get("vega", 0))

    @property
    def iv(self) -> float:
        """
        Implied volatility.

        Note: Check inst.greeks['_state'] to verify data quality before trading.
        """
        greeks = self._fetch_greeks()

        # Warn on missing Greeks
        if greeks.get("_state") == DataState.NO_DATA:
            import warnings
            warnings.warn(
                f"Greeks not available for {self.tradingsymbol}: {greeks.get('_reason')}",
                UserWarning,
                stacklevel=2
            )

        return float(greeks.get("iv", 0))

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
