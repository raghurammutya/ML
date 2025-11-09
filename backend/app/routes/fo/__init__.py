"""
F&O Routes Module.

This module provides comprehensive F&O (Futures & Options) analytics endpoints:
- Indicators: Available F&O indicators registry
- Instruments: Advanced instrument search and filtering
- Expiries: Expiry management with relative labels (NWeek+0, NMonth+0, etc.)
- Moneyness: Time-series analysis grouped by moneyness buckets
- Strikes: Strike distribution and historical analysis
- WebSockets: Real-time data streaming with expiry labels

The module is organized into focused sub-modules for better maintainability.
"""
from fastapi import APIRouter
from ...realtime import RealTimeHub

# Import sub-routers
from .fo_indicators import router as indicators_router
from .fo_instruments import router as instruments_router
from .fo_expiries import router as expiries_router
from .fo_moneyness import router as moneyness_router
from .fo_strikes import router as strikes_router
from .fo_websockets import router as websockets_router, set_realtime_hub

# Create main router with prefix and tags
router = APIRouter(prefix="/fo", tags=["fo"])

# Include all sub-routers
router.include_router(indicators_router)
router.include_router(instruments_router)
router.include_router(expiries_router)
router.include_router(moneyness_router)
router.include_router(strikes_router)
router.include_router(websockets_router)

# Re-export set_realtime_hub for main.py
__all__ = ["router", "set_realtime_hub"]
