# app/services/indicator_registry.py
"""
Indicator Registry Service

Provides metadata about all available indicators (pandas_ta and custom).
Used by frontend for indicator discovery and parameter configuration.
"""

from typing import Dict, List, Optional, Any
from enum import Enum


class IndicatorCategory(str, Enum):
    """Indicator categories"""
    MOMENTUM = "momentum"
    TREND = "trend"
    VOLATILITY = "volatility"
    VOLUME = "volume"
    OTHER = "other"
    CUSTOM = "custom"


class ParameterType(str, Enum):
    """Parameter data types"""
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    STRING = "string"


class IndicatorParameter:
    """Represents a single indicator parameter"""

    def __init__(
        self,
        name: str,
        type: ParameterType,
        default: Any,
        min_value: Optional[float] = None,
        max_value: Optional[float] = None,
        description: str = "",
        required: bool = True
    ):
        self.name = name
        self.type = type
        self.default = default
        self.min_value = min_value
        self.max_value = max_value
        self.description = description
        self.required = required

    def to_dict(self) -> Dict:
        """Convert to dict for API response"""
        return {
            "name": self.name,
            "type": self.type.value,
            "default": self.default,
            "min": self.min_value,
            "max": self.max_value,
            "description": self.description,
            "required": self.required
        }


class IndicatorDefinition:
    """Represents an indicator definition"""

    def __init__(
        self,
        name: str,
        display_name: str,
        category: IndicatorCategory,
        description: str,
        parameters: List[IndicatorParameter],
        outputs: List[str],
        is_custom: bool = False,
        author: Optional[str] = None,
        created_at: Optional[str] = None
    ):
        self.name = name
        self.display_name = display_name
        self.category = category
        self.description = description
        self.parameters = parameters
        self.outputs = outputs
        self.is_custom = is_custom
        self.author = author
        self.created_at = created_at

    def to_dict(self) -> Dict:
        """Convert to dict for API response"""
        return {
            "name": self.name,
            "display_name": self.display_name,
            "category": self.category.value,
            "description": self.description,
            "parameters": [p.to_dict() for p in self.parameters],
            "outputs": self.outputs,
            "is_custom": self.is_custom,
            "author": self.author,
            "created_at": self.created_at
        }


class IndicatorRegistry:
    """
    Central registry for all available indicators.
    Provides metadata for frontend consumption.
    """

    def __init__(self):
        self._indicators: Dict[str, IndicatorDefinition] = {}
        self._initialize_builtin_indicators()

    def _initialize_builtin_indicators(self):
        """Initialize pandas_ta indicators with metadata"""

        # ==================== MOMENTUM INDICATORS ====================

        self.register(IndicatorDefinition(
            name="RSI",
            display_name="Relative Strength Index (RSI)",
            category=IndicatorCategory.MOMENTUM,
            description="Measures the magnitude of recent price changes to evaluate overbought or oversold conditions",
            parameters=[
                IndicatorParameter("length", ParameterType.INTEGER, 14, 2, 100, "Period length"),
                IndicatorParameter("scalar", ParameterType.INTEGER, 100, 1, 1000, "Scaling factor", required=False)
            ],
            outputs=["RSI"]
        ))

        self.register(IndicatorDefinition(
            name="MACD",
            display_name="Moving Average Convergence Divergence (MACD)",
            category=IndicatorCategory.MOMENTUM,
            description="Shows the relationship between two moving averages of prices",
            parameters=[
                IndicatorParameter("fast", ParameterType.INTEGER, 12, 2, 50, "Fast period"),
                IndicatorParameter("slow", ParameterType.INTEGER, 26, 2, 100, "Slow period"),
                IndicatorParameter("signal", ParameterType.INTEGER, 9, 2, 50, "Signal line period")
            ],
            outputs=["MACD", "MACDh", "MACDs"]
        ))

        self.register(IndicatorDefinition(
            name="STOCH",
            display_name="Stochastic Oscillator",
            category=IndicatorCategory.MOMENTUM,
            description="Compares closing price to price range over a given period",
            parameters=[
                IndicatorParameter("k", ParameterType.INTEGER, 14, 1, 100, "%K period"),
                IndicatorParameter("d", ParameterType.INTEGER, 3, 1, 50, "%D period"),
                IndicatorParameter("smooth_k", ParameterType.INTEGER, 3, 1, 50, "Smoothing for %K")
            ],
            outputs=["STOCHk", "STOCHd"]
        ))

        self.register(IndicatorDefinition(
            name="STOCHRSI",
            display_name="Stochastic RSI",
            category=IndicatorCategory.MOMENTUM,
            description="Stochastic oscillator applied to RSI values",
            parameters=[
                IndicatorParameter("length", ParameterType.INTEGER, 14, 2, 100, "RSI length"),
                IndicatorParameter("rsi_length", ParameterType.INTEGER, 14, 2, 100, "Stochastic length"),
                IndicatorParameter("k", ParameterType.INTEGER, 3, 1, 50, "%K smoothing"),
                IndicatorParameter("d", ParameterType.INTEGER, 3, 1, 50, "%D smoothing")
            ],
            outputs=["STOCHRSIk", "STOCHRSId"]
        ))

        self.register(IndicatorDefinition(
            name="CCI",
            display_name="Commodity Channel Index (CCI)",
            category=IndicatorCategory.MOMENTUM,
            description="Measures current price level relative to average price level",
            parameters=[
                IndicatorParameter("length", ParameterType.INTEGER, 20, 2, 100, "Period length")
            ],
            outputs=["CCI"]
        ))

        self.register(IndicatorDefinition(
            name="MOM",
            display_name="Momentum",
            category=IndicatorCategory.MOMENTUM,
            description="Measures the rate of change in price",
            parameters=[
                IndicatorParameter("length", ParameterType.INTEGER, 10, 1, 100, "Period length")
            ],
            outputs=["MOM"]
        ))

        self.register(IndicatorDefinition(
            name="ROC",
            display_name="Rate of Change (ROC)",
            category=IndicatorCategory.MOMENTUM,
            description="Percentage change in price over a specified period",
            parameters=[
                IndicatorParameter("length", ParameterType.INTEGER, 12, 1, 100, "Period length")
            ],
            outputs=["ROC"]
        ))

        self.register(IndicatorDefinition(
            name="TSI",
            display_name="True Strength Index (TSI)",
            category=IndicatorCategory.MOMENTUM,
            description="Shows both trend direction and overbought/oversold conditions",
            parameters=[
                IndicatorParameter("fast", ParameterType.INTEGER, 13, 1, 50, "Fast period"),
                IndicatorParameter("slow", ParameterType.INTEGER, 25, 1, 100, "Slow period"),
                IndicatorParameter("signal", ParameterType.INTEGER, 13, 1, 50, "Signal line")
            ],
            outputs=["TSI", "TSIs"]
        ))

        self.register(IndicatorDefinition(
            name="WILLR",
            display_name="Williams %R",
            category=IndicatorCategory.MOMENTUM,
            description="Momentum indicator measuring overbought/oversold levels",
            parameters=[
                IndicatorParameter("length", ParameterType.INTEGER, 14, 2, 100, "Period length")
            ],
            outputs=["WILLR"]
        ))

        self.register(IndicatorDefinition(
            name="AO",
            display_name="Awesome Oscillator",
            category=IndicatorCategory.MOMENTUM,
            description="Measures market momentum using median price",
            parameters=[],
            outputs=["AO"]
        ))

        self.register(IndicatorDefinition(
            name="PPO",
            display_name="Percentage Price Oscillator (PPO)",
            category=IndicatorCategory.MOMENTUM,
            description="MACD indicator in percentage form",
            parameters=[
                IndicatorParameter("fast", ParameterType.INTEGER, 12, 2, 50, "Fast period"),
                IndicatorParameter("slow", ParameterType.INTEGER, 26, 2, 100, "Slow period"),
                IndicatorParameter("signal", ParameterType.INTEGER, 9, 2, 50, "Signal line")
            ],
            outputs=["PPO", "PPOh", "PPOs"]
        ))

        # ==================== TREND INDICATORS ====================

        self.register(IndicatorDefinition(
            name="SMA",
            display_name="Simple Moving Average (SMA)",
            category=IndicatorCategory.TREND,
            description="Average price over a specified number of periods",
            parameters=[
                IndicatorParameter("length", ParameterType.INTEGER, 20, 2, 500, "Period length")
            ],
            outputs=["SMA"]
        ))

        self.register(IndicatorDefinition(
            name="EMA",
            display_name="Exponential Moving Average (EMA)",
            category=IndicatorCategory.TREND,
            description="Weighted moving average giving more weight to recent prices",
            parameters=[
                IndicatorParameter("length", ParameterType.INTEGER, 20, 2, 500, "Period length")
            ],
            outputs=["EMA"]
        ))

        self.register(IndicatorDefinition(
            name="WMA",
            display_name="Weighted Moving Average (WMA)",
            category=IndicatorCategory.TREND,
            description="Moving average with linear weights",
            parameters=[
                IndicatorParameter("length", ParameterType.INTEGER, 20, 2, 500, "Period length")
            ],
            outputs=["WMA"]
        ))

        self.register(IndicatorDefinition(
            name="HMA",
            display_name="Hull Moving Average (HMA)",
            category=IndicatorCategory.TREND,
            description="Moving average that reduces lag and improves smoothing",
            parameters=[
                IndicatorParameter("length", ParameterType.INTEGER, 20, 2, 200, "Period length")
            ],
            outputs=["HMA"]
        ))

        self.register(IndicatorDefinition(
            name="DEMA",
            display_name="Double Exponential Moving Average (DEMA)",
            category=IndicatorCategory.TREND,
            description="EMA of EMA to reduce lag",
            parameters=[
                IndicatorParameter("length", ParameterType.INTEGER, 20, 2, 200, "Period length")
            ],
            outputs=["DEMA"]
        ))

        self.register(IndicatorDefinition(
            name="TEMA",
            display_name="Triple Exponential Moving Average (TEMA)",
            category=IndicatorCategory.TREND,
            description="EMA of EMA of EMA to further reduce lag",
            parameters=[
                IndicatorParameter("length", ParameterType.INTEGER, 20, 2, 200, "Period length")
            ],
            outputs=["TEMA"]
        ))

        self.register(IndicatorDefinition(
            name="VWMA",
            display_name="Volume Weighted Moving Average (VWMA)",
            category=IndicatorCategory.TREND,
            description="Moving average weighted by volume",
            parameters=[
                IndicatorParameter("length", ParameterType.INTEGER, 20, 2, 200, "Period length")
            ],
            outputs=["VWMA"]
        ))

        self.register(IndicatorDefinition(
            name="ZLEMA",
            display_name="Zero Lag Exponential Moving Average (ZLEMA)",
            category=IndicatorCategory.TREND,
            description="EMA with reduced lag",
            parameters=[
                IndicatorParameter("length", ParameterType.INTEGER, 20, 2, 200, "Period length")
            ],
            outputs=["ZLEMA"]
        ))

        self.register(IndicatorDefinition(
            name="KAMA",
            display_name="Kaufman Adaptive Moving Average (KAMA)",
            category=IndicatorCategory.TREND,
            description="Adaptive moving average that adjusts to volatility",
            parameters=[
                IndicatorParameter("length", ParameterType.INTEGER, 10, 2, 100, "Period length")
            ],
            outputs=["KAMA"]
        ))

        self.register(IndicatorDefinition(
            name="MAMA",
            display_name="MESA Adaptive Moving Average (MAMA)",
            category=IndicatorCategory.TREND,
            description="Adaptive moving average using Hilbert Transform",
            parameters=[
                IndicatorParameter("fastlimit", ParameterType.FLOAT, 0.5, 0.01, 1.0, "Fast limit"),
                IndicatorParameter("slowlimit", ParameterType.FLOAT, 0.05, 0.01, 1.0, "Slow limit")
            ],
            outputs=["MAMA", "FAMA"]
        ))

        self.register(IndicatorDefinition(
            name="T3",
            display_name="T3 Moving Average",
            category=IndicatorCategory.TREND,
            description="Triple smoothed exponential moving average",
            parameters=[
                IndicatorParameter("length", ParameterType.INTEGER, 5, 2, 100, "Period length")
            ],
            outputs=["T3"]
        ))

        # ==================== VOLATILITY INDICATORS ====================

        self.register(IndicatorDefinition(
            name="ATR",
            display_name="Average True Range (ATR)",
            category=IndicatorCategory.VOLATILITY,
            description="Measures market volatility using true range",
            parameters=[
                IndicatorParameter("length", ParameterType.INTEGER, 14, 1, 100, "Period length")
            ],
            outputs=["ATR"]
        ))

        self.register(IndicatorDefinition(
            name="NATR",
            display_name="Normalized Average True Range (NATR)",
            category=IndicatorCategory.VOLATILITY,
            description="ATR normalized as percentage of price",
            parameters=[
                IndicatorParameter("length", ParameterType.INTEGER, 14, 1, 100, "Period length")
            ],
            outputs=["NATR"]
        ))

        self.register(IndicatorDefinition(
            name="BBANDS",
            display_name="Bollinger Bands",
            category=IndicatorCategory.VOLATILITY,
            description="Price channel based on standard deviation",
            parameters=[
                IndicatorParameter("length", ParameterType.INTEGER, 20, 2, 100, "Period length"),
                IndicatorParameter("std", ParameterType.FLOAT, 2.0, 0.5, 5.0, "Standard deviations")
            ],
            outputs=["BBL", "BBM", "BBU", "BBB", "BBP"]
        ))

        self.register(IndicatorDefinition(
            name="KC",
            display_name="Keltner Channels",
            category=IndicatorCategory.VOLATILITY,
            description="Price channel based on ATR",
            parameters=[
                IndicatorParameter("length", ParameterType.INTEGER, 20, 2, 100, "Period length"),
                IndicatorParameter("scalar", ParameterType.FLOAT, 2.0, 0.5, 5.0, "ATR multiplier")
            ],
            outputs=["KCL", "KCB", "KCU"]
        ))

        self.register(IndicatorDefinition(
            name="DC",
            display_name="Donchian Channels",
            category=IndicatorCategory.VOLATILITY,
            description="Price channel based on highest high and lowest low",
            parameters=[
                IndicatorParameter("length", ParameterType.INTEGER, 20, 2, 100, "Period length")
            ],
            outputs=["DCL", "DCM", "DCU"]
        ))

        # ==================== VOLUME INDICATORS ====================

        self.register(IndicatorDefinition(
            name="OBV",
            display_name="On Balance Volume (OBV)",
            category=IndicatorCategory.VOLUME,
            description="Cumulative volume indicator based on price direction",
            parameters=[],
            outputs=["OBV"]
        ))

        self.register(IndicatorDefinition(
            name="AD",
            display_name="Accumulation/Distribution",
            category=IndicatorCategory.VOLUME,
            description="Volume indicator based on price and volume",
            parameters=[],
            outputs=["AD"]
        ))

        self.register(IndicatorDefinition(
            name="ADX",
            display_name="Average Directional Index (ADX)",
            category=IndicatorCategory.VOLUME,
            description="Measures trend strength (not direction)",
            parameters=[
                IndicatorParameter("length", ParameterType.INTEGER, 14, 2, 100, "Period length")
            ],
            outputs=["ADX"]
        ))

        self.register(IndicatorDefinition(
            name="VWAP",
            display_name="Volume Weighted Average Price (VWAP)",
            category=IndicatorCategory.VOLUME,
            description="Average price weighted by volume",
            parameters=[],
            outputs=["VWAP"]
        ))

        self.register(IndicatorDefinition(
            name="MFI",
            display_name="Money Flow Index (MFI)",
            category=IndicatorCategory.VOLUME,
            description="Volume-weighted RSI",
            parameters=[
                IndicatorParameter("length", ParameterType.INTEGER, 14, 2, 100, "Period length")
            ],
            outputs=["MFI"]
        ))

        # ==================== OTHER INDICATORS ====================

        self.register(IndicatorDefinition(
            name="PSAR",
            display_name="Parabolic SAR",
            category=IndicatorCategory.OTHER,
            description="Stop and reverse indicator for trend following",
            parameters=[
                IndicatorParameter("af", ParameterType.FLOAT, 0.02, 0.01, 0.5, "Acceleration factor"),
                IndicatorParameter("max_af", ParameterType.FLOAT, 0.2, 0.05, 1.0, "Maximum acceleration")
            ],
            outputs=["PSARl", "PSARs", "PSARaf", "PSARr"]
        ))

        self.register(IndicatorDefinition(
            name="SUPERTREND",
            display_name="SuperTrend",
            category=IndicatorCategory.OTHER,
            description="Trend following indicator based on ATR",
            parameters=[
                IndicatorParameter("length", ParameterType.INTEGER, 10, 1, 50, "ATR period"),
                IndicatorParameter("multiplier", ParameterType.FLOAT, 3.0, 0.5, 10.0, "ATR multiplier")
            ],
            outputs=["SUPERT", "SUPERTd", "SUPERTl", "SUPERTs"]
        ))

        self.register(IndicatorDefinition(
            name="AROON",
            display_name="Aroon Indicator",
            category=IndicatorCategory.OTHER,
            description="Identifies trend changes and strength",
            parameters=[
                IndicatorParameter("length", ParameterType.INTEGER, 25, 2, 100, "Period length")
            ],
            outputs=["AROOND", "AROONU", "AROONOSC"]
        ))

        self.register(IndicatorDefinition(
            name="FISHER",
            display_name="Fisher Transform",
            category=IndicatorCategory.OTHER,
            description="Converts price to Gaussian distribution for clearer signals",
            parameters=[
                IndicatorParameter("length", ParameterType.INTEGER, 9, 2, 50, "Period length")
            ],
            outputs=["FISHER", "FISHERs"]
        ))

    def register(self, indicator: IndicatorDefinition):
        """Register an indicator"""
        self._indicators[indicator.name] = indicator

    def get(self, name: str) -> Optional[IndicatorDefinition]:
        """Get indicator by name"""
        return self._indicators.get(name)

    def list_all(
        self,
        category: Optional[IndicatorCategory] = None,
        include_custom: bool = True
    ) -> List[IndicatorDefinition]:
        """
        List all indicators, optionally filtered by category.

        Args:
            category: Filter by category (None = all categories)
            include_custom: Include custom user-defined indicators

        Returns:
            List of indicator definitions
        """
        indicators = list(self._indicators.values())

        if category:
            indicators = [ind for ind in indicators if ind.category == category]

        if not include_custom:
            indicators = [ind for ind in indicators if not ind.is_custom]

        return indicators

    def get_categories(self) -> List[str]:
        """Get list of all categories"""
        return [cat.value for cat in IndicatorCategory]

    def search(self, query: str) -> List[IndicatorDefinition]:
        """
        Search indicators by name or description.

        Args:
            query: Search query string

        Returns:
            List of matching indicators
        """
        query_lower = query.lower()
        results = []

        for indicator in self._indicators.values():
            if (query_lower in indicator.name.lower() or
                query_lower in indicator.display_name.lower() or
                query_lower in indicator.description.lower()):
                results.append(indicator)

        return results


# Global singleton instance
_registry: Optional[IndicatorRegistry] = None


def get_indicator_registry() -> IndicatorRegistry:
    """Get global indicator registry instance"""
    global _registry
    if _registry is None:
        _registry = IndicatorRegistry()
    return _registry
