"""
StocksBlitz SDK

Python SDK for smart order management, margin tracking, and risk management.
"""

from .exceptions import (
    SDKException,
    OrderExecutionException,
    WideSpreadException,
    HighMarketImpactException,
    InsufficientLiquidityException,
    MarginException,
    MarginShortfallException,
    MarginIncreasedException,
    RiskException,
    RiskLimitBreachException,
    GreeksRiskException,
    HousekeepingException,
    OrphanedOrdersDetectedException,
    ValidationException,
    DuplicateOrderException,
    PositionSizeExceedsRecommendationException,
)

__all__ = [
    # Base
    'SDKException',
    # Order Execution
    'OrderExecutionException',
    'WideSpreadException',
    'HighMarketImpactException',
    'InsufficientLiquidityException',
    # Margin
    'MarginException',
    'MarginShortfallException',
    'MarginIncreasedException',
    # Risk
    'RiskException',
    'RiskLimitBreachException',
    'GreeksRiskException',
    # Housekeeping
    'HousekeepingException',
    'OrphanedOrdersDetectedException',
    # Validation
    'ValidationException',
    'DuplicateOrderException',
    'PositionSizeExceedsRecommendationException',
]

__version__ = '1.0.0'
