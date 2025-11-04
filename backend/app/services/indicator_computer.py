# app/services/indicator_computer.py
"""
Technical Indicator Computer Service

Computes technical indicators using pandas_ta library.
Supports dynamic indicator specification with custom parameters.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
import pandas as pd
import numpy as np

try:
    import pandas_ta as ta
except ImportError:
    ta = None
    logging.warning("pandas_ta not installed. Install with: pip install pandas-ta")

from app.database import DataManager

logger = logging.getLogger("app.services.indicator_computer")


# Indicator parameter mappings (indicator_name -> list of parameter names in order)
INDICATOR_PARAMS = {
    # Momentum Indicators
    "RSI": ["length", "scalar"],
    "STOCH": ["k", "d", "smooth_k"],
    "STOCHRSI": ["length", "rsi_length", "k", "d"],
    "MACD": ["fast", "slow", "signal"],
    "CCI": ["length"],
    "MOM": ["length"],
    "ROC": ["length"],
    "TSI": ["fast", "slow", "signal"],
    "WILLR": ["length"],
    "AO": [],  # No parameters
    "PPO": ["fast", "slow", "signal"],

    # Trend Indicators
    "SMA": ["length"],
    "EMA": ["length"],
    "WMA": ["length"],
    "HMA": ["length"],
    "DEMA": ["length"],
    "TEMA": ["length"],
    "VWMA": ["length"],
    "ZLEMA": ["length"],
    "KAMA": ["length"],
    "MAMA": ["fastlimit", "slowlimit"],
    "T3": ["length"],

    # Volatility Indicators
    "ATR": ["length"],
    "NATR": ["length"],
    "BBANDS": ["length", "std"],
    "KC": ["length", "scalar"],
    "DC": ["length"],

    # Volume Indicators
    "OBV": [],
    "AD": [],
    "ADX": ["length"],
    "VWAP": [],
    "MFI": ["length"],

    # Other Indicators
    "PSAR": ["af", "max_af"],
    "SUPERTREND": ["length", "multiplier"],
    "AROON": ["length"],
    "FISHER": ["length"],
}


class IndicatorSpec:
    """Parse and represent indicator specifications."""

    @staticmethod
    def parse(indicator_id: str) -> Dict[str, Any]:
        """
        Parse indicator ID into name and parameters.

        Examples:
            "RSI_14" -> {"name": "RSI", "params": {"length": 14}}
            "RSI_10_2" -> {"name": "RSI", "params": {"length": 10, "scalar": 2}}
            "MACD_12_26_9" -> {"name": "MACD", "params": {"fast": 12, "slow": 26, "signal": 9}}
            "BBANDS_20_2" -> {"name": "BBANDS", "params": {"length": 20, "std": 2}}

        Args:
            indicator_id: Indicator identifier (e.g., "RSI_14")

        Returns:
            Dict with 'name' and 'params'
        """
        parts = indicator_id.split("_")
        if not parts:
            raise ValueError(f"Invalid indicator ID: {indicator_id}")

        name = parts[0].upper()

        if name not in INDICATOR_PARAMS:
            raise ValueError(f"Unknown indicator: {name}")

        # Get parameter names for this indicator
        param_names = INDICATOR_PARAMS[name]
        param_values = parts[1:]  # Everything after indicator name

        if len(param_values) != len(param_names):
            if param_names:
                raise ValueError(
                    f"Indicator {name} requires {len(param_names)} parameters: "
                    f"{param_names}, got {len(param_values)}: {param_values}"
                )

        # Build params dict
        params = {}
        for i, param_name in enumerate(param_names):
            try:
                # Try to parse as int first, then float
                value = param_values[i]
                if '.' in value:
                    params[param_name] = float(value)
                else:
                    params[param_name] = int(value)
            except (ValueError, IndexError) as e:
                raise ValueError(f"Invalid parameter value for {param_name}: {value}")

        return {
            "name": name,
            "params": params,
            "indicator_id": indicator_id
        }

    @staticmethod
    def create_id(name: str, params: Dict[str, Any]) -> str:
        """
        Create indicator ID from name and parameters.

        Examples:
            create_id("RSI", {"length": 14}) -> "RSI_14"
            create_id("MACD", {"fast": 12, "slow": 26, "signal": 9}) -> "MACD_12_26_9"
        """
        param_names = INDICATOR_PARAMS.get(name.upper(), [])
        param_values = [str(params.get(p, "")) for p in param_names]

        if param_values:
            return f"{name.upper()}_{'_'.join(param_values)}"
        else:
            return name.upper()


class IndicatorComputer:
    """Compute technical indicators using pandas_ta."""

    def __init__(self, data_manager: DataManager):
        self.dm = data_manager

        # pandas_ta is optional - some indicators work without it
        self._has_pandas_ta = (ta is not None)
        if not self._has_pandas_ta:
            logger.warning("pandas_ta not available - some advanced indicators may not work")

    async def compute_indicator(
        self,
        symbol: str,
        timeframe: str,
        indicator_spec: Dict[str, Any],
        lookback: int = 100
    ) -> pd.Series:
        """
        Compute indicator values.

        Args:
            symbol: Symbol (e.g., "NIFTY50")
            timeframe: Timeframe ("1", "5", "15", "60", "day")
            indicator_spec: Parsed indicator spec from IndicatorSpec.parse()
            lookback: Number of candles to fetch (default: 100)

        Returns:
            pd.Series with indicator values (or pd.DataFrame for multi-column indicators)
        """
        # Fetch OHLCV data
        ohlcv = await self._fetch_ohlcv(symbol, timeframe, lookback)

        if ohlcv is None or len(ohlcv) == 0:
            logger.warning(f"No OHLCV data for {symbol} {timeframe}")
            return pd.Series(dtype=float)

        # Convert to DataFrame
        df = pd.DataFrame(ohlcv)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        df = df.set_index('time')

        # Compute indicator
        name = indicator_spec["name"]
        params = indicator_spec["params"]

        try:
            result = self._compute_ta_indicator(df, name, params)
            return result
        except Exception as e:
            logger.error(f"Failed to compute {name} with params {params}: {e}")
            return pd.Series(dtype=float)

    def _compute_ta_indicator(
        self,
        df: pd.DataFrame,
        name: str,
        params: Dict[str, Any]
    ) -> pd.Series:
        """
        Compute indicator using pandas_ta.

        Args:
            df: DataFrame with OHLCV columns
            name: Indicator name
            params: Indicator parameters

        Returns:
            pd.Series or pd.DataFrame with indicator values
        """
        # Momentum Indicators
        if name == "RSI":
            return ta.rsi(df['close'], **params)

        elif name == "STOCH":
            result = ta.stoch(df['high'], df['low'], df['close'], **params)
            # Returns DataFrame with STOCHk and STOCHd
            return result

        elif name == "STOCHRSI":
            result = ta.stochrsi(df['close'], **params)
            return result

        elif name == "MACD":
            result = ta.macd(df['close'], **params)
            # Returns DataFrame with MACD, MACDh, MACDs
            return result

        elif name == "CCI":
            return ta.cci(df['high'], df['low'], df['close'], **params)

        elif name == "MOM":
            return ta.mom(df['close'], **params)

        elif name == "ROC":
            return ta.roc(df['close'], **params)

        elif name == "TSI":
            return ta.tsi(df['close'], **params)

        elif name == "WILLR":
            return ta.willr(df['high'], df['low'], df['close'], **params)

        elif name == "AO":
            return ta.ao(df['high'], df['low'])

        elif name == "PPO":
            return ta.ppo(df['close'], **params)

        # Trend Indicators
        elif name == "SMA":
            return ta.sma(df['close'], **params)

        elif name == "EMA":
            return ta.ema(df['close'], **params)

        elif name == "WMA":
            return ta.wma(df['close'], **params)

        elif name == "HMA":
            return ta.hma(df['close'], **params)

        elif name == "DEMA":
            return ta.dema(df['close'], **params)

        elif name == "TEMA":
            return ta.tema(df['close'], **params)

        elif name == "VWMA":
            return ta.vwma(df['close'], df['volume'], **params)

        elif name == "ZLEMA":
            return ta.zlma(df['close'], **params)

        elif name == "KAMA":
            return ta.kama(df['close'], **params)

        elif name == "T3":
            return ta.t3(df['close'], **params)

        # Volatility Indicators
        elif name == "ATR":
            return ta.atr(df['high'], df['low'], df['close'], **params)

        elif name == "NATR":
            return ta.natr(df['high'], df['low'], df['close'], **params)

        elif name == "BBANDS":
            result = ta.bbands(df['close'], **params)
            # Returns DataFrame with BBL, BBM, BBU, BBB, BBP
            return result

        elif name == "KC":
            result = ta.kc(df['high'], df['low'], df['close'], **params)
            # Returns DataFrame with KCL, KCB, KCU
            return result

        elif name == "DC":
            result = ta.donchian(df['high'], df['low'], **params)
            return result

        # Volume Indicators
        elif name == "OBV":
            return ta.obv(df['close'], df['volume'])

        elif name == "AD":
            return ta.ad(df['high'], df['low'], df['close'], df['volume'])

        elif name == "ADX":
            return ta.adx(df['high'], df['low'], df['close'], **params)

        elif name == "VWAP":
            return ta.vwap(df['high'], df['low'], df['close'], df['volume'])

        elif name == "MFI":
            return ta.mfi(df['high'], df['low'], df['close'], df['volume'], **params)

        # Other Indicators
        elif name == "PSAR":
            return ta.psar(df['high'], df['low'], **params)

        elif name == "SUPERTREND":
            result = ta.supertrend(df['high'], df['low'], df['close'], **params)
            return result

        elif name == "AROON":
            result = ta.aroon(df['high'], df['low'], **params)
            return result

        elif name == "FISHER":
            return ta.fisher(df['high'], df['low'], **params)

        else:
            raise ValueError(f"Unsupported indicator: {name}")

    async def _fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        lookback: int
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Fetch OHLCV data from database.

        Args:
            symbol: Symbol to fetch
            timeframe: Timeframe ("1", "5", "15", "60", "day")
            lookback: Number of candles to fetch

        Returns:
            List of OHLCV dictionaries
        """
        # Convert timeframe to resolution (minutes)
        resolution = self._timeframe_to_minutes(timeframe)

        # Calculate time range
        to_ts = datetime.now()
        from_ts = to_ts - timedelta(minutes=resolution * lookback * 2)  # 2x buffer for gaps

        # Query database
        query = """
            SELECT
                EXTRACT(EPOCH FROM time)::bigint as time,
                open,
                high,
                low,
                close,
                volume
            FROM minute_bars
            WHERE symbol = $1
              AND resolution = $2
              AND time >= $3
              AND time <= $4
            ORDER BY time ASC
            LIMIT $5
        """

        try:
            async with self.dm.pool.acquire() as conn:
                rows = await conn.fetch(
                    query,
                    symbol,
                    resolution,
                    from_ts,
                    to_ts,
                    lookback
                )

                if not rows:
                    logger.warning(f"No OHLCV data found for {symbol} {timeframe}")
                    return None

                return [dict(row) for row in rows]

        except Exception as e:
            logger.error(f"Failed to fetch OHLCV for {symbol}: {e}")
            return None

    def _timeframe_to_minutes(self, timeframe: str) -> int:
        """Convert timeframe string to minutes."""
        timeframe = timeframe.lower().strip()

        # Handle various formats
        if timeframe in ["1", "1min", "1minute"]:
            return 1
        elif timeframe in ["5", "5min", "5minute"]:
            return 5
        elif timeframe in ["15", "15min", "15minute"]:
            return 15
        elif timeframe in ["60", "60min", "60minute", "1h", "1hour"]:
            return 60
        elif timeframe in ["day", "1d", "1day"]:
            return 1440
        else:
            # Try to parse as integer (minutes)
            try:
                return int(timeframe)
            except ValueError:
                logger.warning(f"Unknown timeframe: {timeframe}, defaulting to 5min")
                return 5

    async def compute_batch(
        self,
        symbol: str,
        timeframe: str,
        indicator_specs: List[Dict[str, Any]],
        lookback: int = 100
    ) -> Dict[str, pd.Series]:
        """
        Compute multiple indicators in batch (single OHLCV fetch).

        Args:
            symbol: Symbol
            timeframe: Timeframe
            indicator_specs: List of indicator specs
            lookback: Candles to fetch

        Returns:
            Dict mapping indicator_id -> pd.Series
        """
        # Fetch OHLCV once
        ohlcv = await self._fetch_ohlcv(symbol, timeframe, lookback)

        if ohlcv is None or len(ohlcv) == 0:
            return {}

        df = pd.DataFrame(ohlcv)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        df = df.set_index('time')

        # Compute all indicators
        results = {}
        for spec in indicator_specs:
            try:
                indicator_id = spec["indicator_id"]
                name = spec["name"]
                params = spec["params"]

                result = self._compute_ta_indicator(df, name, params)
                results[indicator_id] = result

            except Exception as e:
                logger.error(f"Failed to compute {spec['indicator_id']}: {e}")
                results[spec["indicator_id"]] = pd.Series(dtype=float)

        return results
