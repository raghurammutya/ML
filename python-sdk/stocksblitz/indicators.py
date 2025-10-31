"""
Indicator proxy classes for lazy evaluation.
"""

from typing import Any, Union, Tuple, Dict, TYPE_CHECKING
from .cache import cache_key

if TYPE_CHECKING:
    from .api import APIClient


# Indicator parameter mappings
INDICATOR_PARAMS = {
    "RSI": ["length", "scalar"],
    "SMA": ["length"],
    "EMA": ["length"],
    "WMA": ["length"],
    "HMA": ["length"],
    "MACD": ["fast", "slow", "signal"],
    "BBANDS": ["length", "std"],
    "ATR": ["length"],
    "STOCH": ["k", "d", "smooth_k"],
    "ADX": ["length"],
    "CCI": ["length"],
    "MOM": ["length"],
    "ROC": ["length"],
    "VWAP": [],
    "OBV": [],
}


class IndicatorProxy:
    """
    Lazy evaluation proxy for technical indicators.

    Supports both indexing and call syntax:
    - candle.rsi[14]
    - candle.rsi(14)
    - candle.macd[12, 26, 9]
    - candle.macd(12, 26, 9)
    """

    def __init__(self, api_client: 'APIClient', symbol: str, timeframe: str,
                 offset: int, indicator_name: str):
        """
        Initialize indicator proxy.

        Args:
            api_client: API client instance
            symbol: Trading symbol
            timeframe: Timeframe (e.g., "5min")
            offset: Candles back from current (0 = current)
            indicator_name: Indicator name (e.g., "rsi", "sma")
        """
        self._api = api_client
        self._symbol = symbol
        self._timeframe = timeframe
        self._offset = offset
        self._indicator_name = indicator_name.upper()

    def __getitem__(self, params: Union[int, Tuple, slice]) -> Union[float, Dict]:
        """
        Access indicator with parameters using indexing.

        Args:
            params: Single param (int), multiple params (tuple), or dict

        Returns:
            Indicator value(s)

        Examples:
            >>> candle.rsi[14]
            62.5
            >>> candle.macd[12, 26, 9]
            {'macd': 1.5, 'signal': 1.2, 'histogram': 0.3}
        """
        if isinstance(params, int):
            params = (params,)
        elif not isinstance(params, tuple):
            params = (params,)

        return self._compute_indicator(params)

    def __call__(self, *args, **kwargs) -> Union[float, Dict]:
        """
        Access indicator with parameters using call syntax.

        Args:
            *args: Positional parameters
            **kwargs: Keyword parameters

        Returns:
            Indicator value(s)

        Examples:
            >>> candle.rsi(14)
            62.5
            >>> candle.macd(fast=12, slow=26, signal=9)
            {'macd': 1.5, 'signal': 1.2, 'histogram': 0.3}
        """
        if kwargs:
            return self._compute_indicator_with_kwargs(kwargs)
        return self._compute_indicator(args)

    def _compute_indicator(self, params: Tuple) -> Union[float, Dict]:
        """
        Compute indicator value by calling API.

        Args:
            params: Parameter values

        Returns:
            Indicator value(s)
        """
        # Build indicator ID
        indicator_id = self._build_indicator_id(params)

        # Check cache first
        key = cache_key("indicator", self._symbol, self._timeframe,
                        self._offset, indicator_id)
        cached = self._api.cache.get(key)
        if cached is not None:
            return cached

        # Call API
        try:
            response = self._api.get(
                "/indicators/at-offset",
                params={
                    "symbol": self._symbol,
                    "timeframe": self._timeframe,
                    "indicators": indicator_id,
                    "offset": self._offset
                },
                cache_ttl=60  # Cache for 60 seconds
            )

            # Extract value
            if "values" in response and indicator_id in response["values"]:
                value_data = response["values"][indicator_id]
                value = value_data.get("value")

                # Cache the value
                self._api.cache.set(key, value, ttl=60)

                return value
            else:
                raise ValueError(f"Indicator {indicator_id} not found in response")

        except Exception as e:
            raise RuntimeError(f"Failed to compute {indicator_id}: {e}")

    def _compute_indicator_with_kwargs(self, kwargs: Dict) -> Union[float, Dict]:
        """
        Compute indicator with keyword arguments.

        Args:
            kwargs: Keyword arguments for parameters

        Returns:
            Indicator value(s)
        """
        # Convert kwargs to ordered params based on INDICATOR_PARAMS
        param_names = INDICATOR_PARAMS.get(self._indicator_name, [])
        params = tuple(kwargs.get(name) for name in param_names)

        return self._compute_indicator(params)

    def _build_indicator_id(self, params: Tuple) -> str:
        """
        Build indicator ID from parameters.

        Args:
            params: Parameter values

        Returns:
            Indicator ID (e.g., "RSI_14", "MACD_12_26_9")

        Examples:
            >>> _build_indicator_id(("RSI", (14,)))
            'RSI_14'
            >>> _build_indicator_id(("MACD", (12, 26, 9)))
            'MACD_12_26_9'
        """
        if not params:
            return self._indicator_name

        param_str = "_".join(str(p) for p in params)
        return f"{self._indicator_name}_{param_str}"
