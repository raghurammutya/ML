"""
Condition Models
Defines structured condition configurations for different alert types
"""

from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field


class PriceCondition(BaseModel):
    """Price-based alert condition."""

    type: Literal["price"] = "price"
    symbol: str = Field(..., description="Trading symbol (e.g., NIFTY50)")
    operator: Literal["gt", "gte", "lt", "lte", "eq", "between"] = Field(
        ..., description="Comparison operator"
    )
    threshold: float = Field(..., description="Price threshold")
    min_threshold: Optional[float] = Field(None, description="Min threshold for 'between' operator")
    max_threshold: Optional[float] = Field(None, description="Max threshold for 'between' operator")
    comparison: Literal["last_price", "bid", "ask", "vwap"] = Field(
        default="last_price", description="Price field to compare"
    )


class IndicatorCondition(BaseModel):
    """Technical indicator alert condition."""

    type: Literal["indicator"] = "indicator"
    symbol: str = Field(..., description="Trading symbol")
    indicator: str = Field(..., description="Indicator name (rsi, macd, sma, ema, etc.)")
    timeframe: str = Field(default="5min", description="Timeframe (1min, 5min, 15min, 1hour, 1day)")
    operator: Literal["gt", "gte", "lt", "lte", "eq", "between", "crossover", "crossunder"] = Field(
        ..., description="Comparison operator"
    )
    threshold: Optional[float] = Field(None, description="Threshold value")
    lookback_periods: int = Field(default=14, ge=1, description="Lookback period for indicator")
    parameters: Optional[Dict[str, Any]] = Field(None, description="Indicator-specific parameters")


class PositionCondition(BaseModel):
    """Position-based alert condition."""

    type: Literal["position"] = "position"
    metric: Literal["pnl", "day_pnl", "quantity", "pnl_percentage"] = Field(
        ..., description="Position metric to monitor"
    )
    operator: Literal["gt", "gte", "lt", "lte", "eq", "between"] = Field(
        ..., description="Comparison operator"
    )
    threshold: float = Field(..., description="Threshold value")
    symbol: Optional[str] = Field(None, description="Specific symbol (or all positions if None)")
    product: Optional[str] = Field(None, description="Product type (MIS, NRML, CNC)")


class GreekCondition(BaseModel):
    """Option Greeks alert condition."""

    type: Literal["greek"] = "greek"
    greek: Literal["delta", "gamma", "theta", "vega"] = Field(..., description="Greek to monitor")
    operator: Literal["gt", "gte", "lt", "lte", "eq", "between"] = Field(
        ..., description="Comparison operator"
    )
    threshold: Optional[float] = Field(None, description="Threshold value")
    min_threshold: Optional[float] = Field(None, description="Min threshold for 'between'")
    max_threshold: Optional[float] = Field(None, description="Max threshold for 'between'")
    position_type: Optional[Literal["long_call", "short_call", "long_put", "short_put"]] = Field(
        None, description="Position type filter"
    )
    symbol: Optional[str] = Field(None, description="Specific option symbol")


class TimeCondition(BaseModel):
    """Time-based reminder condition."""

    type: Literal["time"] = "time"
    schedule: Literal["cron", "once", "daily", "weekly"] = Field(
        ..., description="Schedule type"
    )
    expression: Optional[str] = Field(None, description="Cron expression (for schedule=cron)")
    time: Optional[str] = Field(None, description="Time in HH:MM format (for daily/weekly)")
    date: Optional[str] = Field(None, description="Date in YYYY-MM-DD format (for once)")
    weekday: Optional[int] = Field(None, ge=0, le=6, description="Day of week 0=Monday (for weekly)")
    timezone: str = Field(default="Asia/Kolkata", description="Timezone for schedule")
    message: str = Field(..., description="Reminder message")


class CompositeCondition(BaseModel):
    """Composite condition (AND/OR logic)."""

    type: Literal["composite"] = "composite"
    operator: Literal["and", "or"] = Field(..., description="Logical operator")
    conditions: List[Dict[str, Any]] = Field(
        ..., min_length=2, description="List of sub-conditions"
    )


class CustomScriptCondition(BaseModel):
    """Custom Python script condition (advanced users)."""

    type: Literal["script"] = "script"
    language: Literal["python"] = Field(default="python", description="Script language")
    script: str = Field(..., description="Python expression or script")
    timeout_seconds: int = Field(default=5, ge=1, le=30, description="Execution timeout")
    context_variables: Optional[Dict[str, Any]] = Field(
        None, description="Variables available in script context"
    )


# Union type for all condition types
ConditionType = (
    PriceCondition
    | IndicatorCondition
    | PositionCondition
    | GreekCondition
    | TimeCondition
    | CompositeCondition
    | CustomScriptCondition
)
