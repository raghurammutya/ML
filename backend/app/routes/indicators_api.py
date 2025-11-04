# app/routes/indicators_api.py
"""
Technical Indicators REST API

Endpoints for subscribing to indicators, querying current/historical values,
and managing subscriptions.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from fastapi import APIRouter, Depends, Query, HTTPException, Request
from pydantic import BaseModel, Field
import pandas as pd

from app.database import DataManager
from app.services.indicator_computer import IndicatorComputer, IndicatorSpec
from app.services.indicator_subscription_manager import IndicatorSubscriptionManager
from app.services.indicator_cache import IndicatorCache
from app.auth import require_api_key, require_api_key_or_jwt, APIKey, UserIdentity
import redis.asyncio as redis

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/indicators", tags=["indicators"])

# Globals
_indicator_computer: Optional[IndicatorComputer] = None
_subscription_manager: Optional[IndicatorSubscriptionManager] = None
_indicator_cache: Optional[IndicatorCache] = None
_redis_client: Optional[redis.Redis] = None


# ========== Dependencies ==========

async def get_indicator_computer(request: Request) -> IndicatorComputer:
    """Get IndicatorComputer instance."""
    global _indicator_computer
    if _indicator_computer is None:
        dm = request.app.state.data_manager
        _indicator_computer = IndicatorComputer(dm)
    return _indicator_computer


async def get_subscription_manager(request: Request) -> IndicatorSubscriptionManager:
    """Get SubscriptionManager instance."""
    global _subscription_manager, _redis_client
    if _subscription_manager is None:
        _redis_client = request.app.state.redis_client
        _subscription_manager = IndicatorSubscriptionManager(_redis_client)
    return _subscription_manager


async def get_indicator_cache(request: Request) -> IndicatorCache:
    """Get IndicatorCache instance."""
    global _indicator_cache, _redis_client
    if _indicator_cache is None:
        _redis_client = request.app.state.redis_client
        _indicator_cache = IndicatorCache(_redis_client)
    return _indicator_cache


# ========== Pydantic Models ==========

class IndicatorParams(BaseModel):
    """Indicator parameters."""
    name: str = Field(..., description="Indicator name (RSI, SMA, MACD, etc.)")
    params: Dict[str, Any] = Field(default={}, description="Indicator parameters")


class SubscribeRequest(BaseModel):
    """Subscribe to indicators request."""
    symbol: str = Field(..., description="Symbol (e.g., NIFTY50)")
    timeframe: str = Field(..., description="Timeframe (1, 5, 15, 60, day)")
    indicators: List[IndicatorParams] = Field(..., description="List of indicators to subscribe")


class UnsubscribeRequest(BaseModel):
    """Unsubscribe from indicators request."""
    symbol: str
    timeframe: str
    indicator_ids: List[str] = Field(..., description="List of indicator IDs to unsubscribe")


class BatchQueryRequest(BaseModel):
    """Batch query request."""
    symbol: str
    queries: List[Dict[str, Any]] = Field(..., description="List of query specs")


# ========== Endpoints ==========

@router.post("/subscribe")
async def subscribe_indicators(
    request: Request,
    body: SubscribeRequest,
    user: UserIdentity = Depends(require_api_key_or_jwt),
    sub_manager: IndicatorSubscriptionManager = Depends(get_subscription_manager),
    computer: IndicatorComputer = Depends(get_indicator_computer),
    cache: IndicatorCache = Depends(get_indicator_cache)
) -> Dict[str, Any]:
    """
    Subscribe to technical indicators for real-time computation.

    **Authentication**: Accepts either API key or JWT token.

    **Example**:
    ```json
    {
      "symbol": "NIFTY50",
      "timeframe": "5min",
      "indicators": [
        {"name": "RSI", "params": {"length": 14}},
        {"name": "SMA", "params": {"length": 20}},
        {"name": "MACD", "params": {"fast": 12, "slow": 26, "signal": 9}}
      ]
    }
    ```

    **Response**:
    - Returns subscription details with unique indicator IDs
    - Indicator IDs format: `RSI_14`, `SMA_20`, `MACD_12_26_9`
    - Use these IDs for querying and unsubscribing
    """
    try:
        # Use key_id for API keys, user_id for JWT
        client_id = str(user.api_key.key_id) if user.api_key else user.user_id

        # Create indicator IDs
        indicator_ids = []
        indicator_specs = []

        for ind in body.indicators:
            ind_id = IndicatorSpec.create_id(ind.name, ind.params)
            indicator_ids.append(ind_id)

            # Parse spec
            spec = IndicatorSpec.parse(ind_id)
            indicator_specs.append(spec)

        # Subscribe in Redis
        result = await sub_manager.subscribe(
            client_id, body.symbol, body.timeframe, indicator_ids
        )

        # Trigger initial computation for newly subscribed indicators
        compute_tasks = []
        for spec in indicator_specs:
            # Check if we need to compute (not in cache)
            cached = await cache.get_latest(body.symbol, body.timeframe, spec["indicator_id"])
            if cached is None:
                # Compute asynchronously
                task = asyncio.create_task(
                    _compute_and_cache(computer, cache, body.symbol, body.timeframe, spec)
                )
                compute_tasks.append(task)

        # Wait for computations (with timeout)
        if compute_tasks:
            await asyncio.wait(compute_tasks, timeout=10)

        return result

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to subscribe: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/unsubscribe")
async def unsubscribe_indicators(
    request: Request,
    body: UnsubscribeRequest,
    user: UserIdentity = Depends(require_api_key_or_jwt),
    sub_manager: IndicatorSubscriptionManager = Depends(get_subscription_manager)
) -> Dict[str, Any]:
    """
    Unsubscribe from indicators.

    **Authentication**: Accepts either API key or JWT token.

    **Example**:
    ```json
    {
      "symbol": "NIFTY50",
      "timeframe": "5min",
      "indicator_ids": ["RSI_14", "SMA_20"]
    }
    ```
    """
    try:
        client_id = str(user.api_key.key_id) if user.api_key else user.user_id

        result = await sub_manager.unsubscribe(
            client_id, body.symbol, body.timeframe, body.indicator_ids
        )

        return result

    except Exception as e:
        logger.error(f"Failed to unsubscribe: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/current")
async def get_current_indicators(
    request: Request,
    symbol: str = Query(..., description="Symbol (e.g., NIFTY50)"),
    timeframe: str = Query(..., description="Timeframe (1, 5, 15, 60, day)"),
    indicators: str = Query(..., description="Comma-separated indicator IDs (e.g., RSI_14,SMA_20)"),
    user: UserIdentity = Depends(require_api_key_or_jwt),
    computer: IndicatorComputer = Depends(get_indicator_computer),
    cache: IndicatorCache = Depends(get_indicator_cache)
) -> Dict[str, Any]:
    """
    Get current indicator values.

    **Authentication**: Accepts either API key or JWT token.

    **Example**:
    ```
    GET /indicators/current?symbol=NIFTY50&timeframe=5&indicators=RSI_14,SMA_20,EMA_50
    ```

    **Response**:
    ```json
    {
      "status": "success",
      "symbol": "NIFTY50",
      "timeframe": "5min",
      "timestamp": 1730369100,
      "candle_time": "2025-10-31T10:05:00Z",
      "indicators": {
        "RSI_14": 64.5,
        "SMA_20": 23100.25,
        "EMA_50": 23050.75
      }
    }
    ```
    """
    try:
        indicator_ids = [ind.strip() for ind in indicators.split(",")]

        # Try cache first (batch get)
        cached_values = await cache.get_latest_batch(symbol, timeframe, indicator_ids)

        # Identify missing values
        missing_ids = [ind_id for ind_id, val in cached_values.items() if val is None]

        # Compute missing values
        if missing_ids:
            missing_specs = [IndicatorSpec.parse(ind_id) for ind_id in missing_ids]

            # Compute in batch (single OHLCV fetch)
            computed = await computer.compute_batch(symbol, timeframe, missing_specs, lookback=100)

            # Extract latest values and cache
            for ind_id, series in computed.items():
                if isinstance(series, pd.DataFrame):
                    # Multi-column indicator (e.g., BBANDS, MACD)
                    latest = series.iloc[-1].to_dict() if len(series) > 0 else {}
                elif isinstance(series, pd.Series):
                    latest = float(series.iloc[-1]) if len(series) > 0 else None
                else:
                    latest = None

                # Cache
                await cache.set_latest(symbol, timeframe, ind_id, latest)
                cached_values[ind_id] = {"value": latest, "timestamp": datetime.now().isoformat()}

        # Build response
        result_indicators = {}
        candle_time = None

        for ind_id in indicator_ids:
            cached = cached_values.get(ind_id)
            if cached:
                result_indicators[ind_id] = cached.get("value")
                if candle_time is None:
                    candle_time = cached.get("candle_time", cached.get("timestamp"))

        return {
            "status": "success",
            "symbol": symbol,
            "timeframe": timeframe,
            "timestamp": int(datetime.now().timestamp()),
            "candle_time": candle_time,
            "indicators": result_indicators
        }

    except Exception as e:
        logger.error(f"Failed to get current indicators: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history")
async def get_indicator_history(
    request: Request,
    symbol: str = Query(..., description="Symbol"),
    timeframe: str = Query(..., description="Timeframe"),
    indicator: str = Query(..., description="Indicator ID (e.g., RSI_14)"),
    lookback: int = Query(20, ge=1, le=1000, description="Number of candles to fetch"),
    user: UserIdentity = Depends(require_api_key_or_jwt),
    computer: IndicatorComputer = Depends(get_indicator_computer),
    cache: IndicatorCache = Depends(get_indicator_cache)
) -> Dict[str, Any]:
    """
    Get historical indicator values (N candles back).

    **Authentication**: Accepts either API key or JWT token.

    **Example**:
    ```
    GET /indicators/history?symbol=NIFTY50&timeframe=5&indicator=RSI_14&lookback=20
    ```

    **Response**:
    ```json
    {
      "status": "success",
      "symbol": "NIFTY50",
      "timeframe": "5min",
      "indicator": "RSI_14",
      "series": [
        {"time": 1730367600, "value": 62.3, "candles_back": 20},
        {"time": 1730367900, "value": 63.1, "candles_back": 19},
        ...
        {"time": 1730369100, "value": 64.5, "candles_back": 0}
      ]
    }
    ```
    """
    try:
        # Parse indicator spec
        spec = IndicatorSpec.parse(indicator)

        # Check cache
        to_ts = datetime.now()
        from_ts = to_ts - timedelta(minutes=_timeframe_to_minutes(timeframe) * lookback * 2)

        cached_series = await cache.get_series(symbol, timeframe, indicator, from_ts, to_ts)

        if cached_series is not None:
            logger.info(f"Serving {indicator} history from cache")
            series = cached_series
        else:
            # Compute
            result = await computer.compute_indicator(symbol, timeframe, spec, lookback=lookback)

            # Convert to series format
            series = []
            if isinstance(result, pd.Series):
                for i, (timestamp, value) in enumerate(result.items()):
                    series.append({
                        "time": int(timestamp.timestamp()),
                        "value": float(value) if pd.notna(value) else None,
                        "candles_back": len(result) - i - 1
                    })
            elif isinstance(result, pd.DataFrame):
                # Multi-column indicator
                for i, (timestamp, row) in enumerate(result.iterrows()):
                    entry = {
                        "time": int(timestamp.timestamp()),
                        "candles_back": len(result) - i - 1
                    }
                    for col in result.columns:
                        entry[col] = float(row[col]) if pd.notna(row[col]) else None
                    series.append(entry)

            # Cache
            await cache.set_series(symbol, timeframe, indicator, from_ts, to_ts, series)

        return {
            "status": "success",
            "symbol": symbol,
            "timeframe": timeframe,
            "indicator": indicator,
            "count": len(series),
            "series": series
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get indicator history: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/at-offset")
async def get_indicator_at_offset(
    request: Request,
    symbol: str = Query(..., description="Symbol"),
    timeframe: str = Query(..., description="Timeframe"),
    indicators: str = Query(..., description="Comma-separated indicator IDs"),
    offset: int = Query(0, ge=0, le=1000, description="Candles back (0=current, 1=one back, etc.)"),
    user: UserIdentity = Depends(require_api_key_or_jwt),
    computer: IndicatorComputer = Depends(get_indicator_computer)
) -> Dict[str, Any]:
    """
    Get indicator values at specific offset (N candles back).

    **Authentication**: Accepts either API key or JWT token.

    **Example**:
    ```
    GET /indicators/at-offset?symbol=NIFTY50&timeframe=5&indicators=RSI_14,SMA_20&offset=5
    ```

    **Response**: Values from 5 candles ago
    ```json
    {
      "status": "success",
      "symbol": "NIFTY50",
      "timeframe": "5min",
      "offset": 5,
      "indicators": {
        "RSI_14": 62.3,
        "SMA_20": 23095.5
      }
    }
    ```
    """
    try:
        indicator_ids = [ind.strip() for ind in indicators.split(",")]

        # Parse specs
        specs = [IndicatorSpec.parse(ind_id) for ind_id in indicator_ids]

        # Compute with lookback = offset + buffer
        results = await computer.compute_batch(symbol, timeframe, specs, lookback=offset + 50)

        # Extract values at offset
        output = {}
        for ind_id, series in results.items():
            if isinstance(series, pd.Series) and len(series) > offset:
                value = series.iloc[-(offset + 1)]  # -1 for current, -2 for 1 back, etc.
                output[ind_id] = float(value) if pd.notna(value) else None
            elif isinstance(series, pd.DataFrame) and len(series) > offset:
                row = series.iloc[-(offset + 1)]
                output[ind_id] = {col: float(row[col]) if pd.notna(row[col]) else None for col in series.columns}
            else:
                output[ind_id] = None

        return {
            "status": "success",
            "symbol": symbol,
            "timeframe": timeframe,
            "offset": offset,
            "indicators": output
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get indicators at offset: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/batch")
async def batch_query(
    request: Request,
    body: BatchQueryRequest,
    user: UserIdentity = Depends(require_api_key_or_jwt),
    computer: IndicatorComputer = Depends(get_indicator_computer)
) -> Dict[str, Any]:
    """
    Batch query multiple indicators/timeframes.

    **Authentication**: Accepts either API key or JWT token.

    **Example**:
    ```json
    {
      "symbol": "NIFTY50",
      "queries": [
        {"timeframe": "1min", "indicator": "RSI_14", "lookback": 10},
        {"timeframe": "5min", "indicator": "RSI_14", "lookback": 20},
        {"timeframe": "15min", "indicator": "SMA_20", "lookback": 10}
      ]
    }
    ```
    """
    try:
        results = []

        # Process each query
        for query in body.queries:
            timeframe = query.get("timeframe")
            indicator = query.get("indicator")
            lookback = query.get("lookback", 20)

            spec = IndicatorSpec.parse(indicator)

            series_data = await computer.compute_indicator(
                body.symbol, timeframe, spec, lookback=lookback
            )

            # Convert to dict format
            series = []
            if isinstance(series_data, pd.Series):
                for timestamp, value in series_data.items():
                    series.append({
                        "time": int(timestamp.timestamp()),
                        "value": float(value) if pd.notna(value) else None
                    })

            results.append({
                "timeframe": timeframe,
                "indicator": indicator,
                "series": series
            })

        return {
            "status": "success",
            "symbol": body.symbol,
            "results": results
        }

    except Exception as e:
        logger.error(f"Failed batch query: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ========== Helper Functions ==========

async def _compute_and_cache(
    computer: IndicatorComputer,
    cache: IndicatorCache,
    symbol: str,
    timeframe: str,
    spec: Dict[str, Any]
):
    """Compute indicator and cache result."""
    try:
        result = await computer.compute_indicator(symbol, timeframe, spec, lookback=100)

        # Extract latest value
        if isinstance(result, pd.Series) and len(result) > 0:
            latest = float(result.iloc[-1])
        elif isinstance(result, pd.DataFrame) and len(result) > 0:
            latest = result.iloc[-1].to_dict()
        else:
            latest = None

        # Cache
        await cache.set_latest(symbol, timeframe, spec["indicator_id"], latest)

        logger.info(f"Computed and cached {spec['indicator_id']} for {symbol} {timeframe}")

    except Exception as e:
        logger.error(f"Failed to compute {spec['indicator_id']}: {e}")


def _timeframe_to_minutes(timeframe: str) -> int:
    """Convert timeframe string to minutes."""
    tf = timeframe.lower().strip()
    if tf in ["1", "1min"]:
        return 1
    elif tf in ["5", "5min"]:
        return 5
    elif tf in ["15", "15min"]:
        return 15
    elif tf in ["60", "60min", "1h"]:
        return 60
    elif tf in ["day", "1d"]:
        return 1440
    else:
        try:
            return int(tf)
        except ValueError:
            return 5


@router.get("/list")
async def list_available_indicators(
    category: Optional[str] = Query(None, description="Filter by category (momentum, trend, volatility, volume, other)"),
    search: Optional[str] = Query(None, description="Search query"),
    include_custom: bool = Query(True, description="Include custom user-defined indicators")
) -> Dict[str, Any]:
    """
    List all available indicators with their parameters and metadata.

    This endpoint is primarily for frontend discovery - it provides all the information
    needed to build dynamic UI for indicator selection and configuration.

    **Example**: Get all indicators
    ```
    GET /indicators/list
    ```

    **Example**: Filter by category
    ```
    GET /indicators/list?category=momentum
    ```

    **Example**: Search
    ```
    GET /indicators/list?search=moving+average
    ```

    **Response**:
    ```json
    {
      "status": "success",
      "total": 41,
      "categories": ["momentum", "trend", "volatility", "volume", "other"],
      "indicators": [
        {
          "name": "RSI",
          "display_name": "Relative Strength Index (RSI)",
          "category": "momentum",
          "description": "Measures the magnitude of recent price changes...",
          "parameters": [
            {
              "name": "length",
              "type": "integer",
              "default": 14,
              "min": 2,
              "max": 100,
              "description": "Period length",
              "required": true
            },
            {
              "name": "scalar",
              "type": "integer",
              "default": 100,
              "min": 1,
              "max": 1000,
              "description": "Scaling factor",
              "required": false
            }
          ],
          "outputs": ["RSI"],
          "is_custom": false
        }
      ]
    }
    ```
    """
    from app.services.indicator_registry import get_indicator_registry, IndicatorCategory

    try:
        registry = get_indicator_registry()

        # Filter by category
        category_filter = None
        if category:
            try:
                category_filter = IndicatorCategory(category.lower())
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid category. Must be one of: {', '.join(registry.get_categories())}"
                )

        # Get indicators
        if search:
            indicators = registry.search(search)
        else:
            indicators = registry.list_all(
                category=category_filter,
                include_custom=include_custom
            )

        # Convert to dict
        indicators_data = [ind.to_dict() for ind in indicators]

        return {
            "status": "success",
            "total": len(indicators_data),
            "categories": registry.get_categories(),
            "indicators": indicators_data
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list indicators: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/definition/{indicator_name}")
async def get_indicator_definition(
    indicator_name: str
) -> Dict[str, Any]:
    """
    Get detailed definition for a specific indicator.

    **Example**:
    ```
    GET /indicators/definition/RSI
    ```

    **Response**:
    ```json
    {
      "status": "success",
      "indicator": {
        "name": "RSI",
        "display_name": "Relative Strength Index (RSI)",
        "category": "momentum",
        "description": "Measures the magnitude of recent price changes...",
        "parameters": [...],
        "outputs": ["RSI"],
        "is_custom": false
      }
    }
    ```
    """
    from app.services.indicator_registry import get_indicator_registry

    try:
        registry = get_indicator_registry()
        indicator = registry.get(indicator_name.upper())

        if not indicator:
            raise HTTPException(
                status_code=404,
                detail=f"Indicator '{indicator_name}' not found"
            )

        return {
            "status": "success",
            "indicator": indicator.to_dict()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get indicator definition: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health_check() -> Dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok", "service": "indicators"}
