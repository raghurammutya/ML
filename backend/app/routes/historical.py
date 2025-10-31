from fastapi import APIRouter, HTTPException, Query, Depends
from typing import List, Optional
import asyncio
import logging
from datetime import datetime, timedelta, date
import asyncpg

from ..database import DataManager
from .indicators import get_data_manager

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/historical/series")
async def get_historical_series(
    underlying: str = Query(..., description="Underlying symbol (e.g., NIFTY)"),
    strike: Optional[int] = Query(None, description="Strike price for options"),
    bucket: Optional[str] = Query(None, description="Moneyness bucket (ATM, OTM1, ITM1, etc.)"),
    expiry: Optional[str] = Query(None, description="Expiry date (YYYY-MM-DD)"),
    timeframe: str = Query("1min", description="Timeframe (1min, 5min, 15min, etc.)"),
    start: Optional[str] = Query(None, description="Start time (ISO format)"),
    end: Optional[str] = Query(None, description="End time (ISO format)"),
    data_manager: DataManager = Depends(get_data_manager)
):
    """
    Fetch historical series data for popup charts.
    Returns timestamps, candles, and metrics for the specified instrument.
    """

    try:
        # Parse time range
        if start:
            start_time = datetime.fromisoformat(start.replace('Z', '+00:00'))
        else:
            start_time = datetime.utcnow() - timedelta(hours=6)

        if end:
            end_time = datetime.fromisoformat(end.replace('Z', '+00:00'))
        else:
            end_time = datetime.utcnow()

        # Use shared pool from DataManager (no pool leak!)
        if not data_manager.pool:
            raise HTTPException(status_code=500, detail="Database connection unavailable")

        async with data_manager.pool.acquire() as conn:
            # Handle strike-based queries (vertical panels)
            if strike and expiry:
                # Query option candles and metrics for specific strike
                option_query = """
                    SELECT
                        bucket_time,
                        underlying_close as close,
                        call_iv_avg as iv,
                        call_delta_avg as delta,
                        call_gamma_avg as gamma,
                        call_theta_avg as theta,
                        call_vega_avg as vega,
                        call_volume as volume
                    FROM fo_option_strike_bars
                    WHERE symbol = $1
                        AND strike = $2
                        AND expiry = $3
                        AND timeframe = $4
                        AND bucket_time >= $5
                        AND bucket_time <= $6
                    ORDER BY bucket_time
                """

                # Convert expiry string to date object
                try:
                    expiry_date = date.fromisoformat(expiry) if expiry else None
                except (ValueError, AttributeError):
                    raise HTTPException(status_code=400, detail=f"Invalid expiry format: {expiry}")

                rows = await conn.fetch(
                    option_query,
                    underlying.upper(),
                    strike,
                    expiry_date,
                    timeframe,
                    start_time,
                    end_time
                )

            else:
                # For now, return empty data for non-strike queries
                # In future, implement bucket-based and underlying-only queries
                rows = []

        # Format response
        timestamps = []
        candles = []
        metrics = []

        for row in rows:
            timestamp = row['bucket_time'].isoformat() + 'Z'
            timestamps.append(timestamp)

            # For options, we don't have OHLC, so use close price
            close_price = float(row['close']) if row['close'] else 0.0
            candle = {
                'o': close_price,
                'h': close_price,
                'l': close_price,
                'c': close_price,
                'v': int(row['volume']) if row['volume'] else 0
            }
            candles.append(candle)

            # Add metrics if option data
            if strike and expiry:
                metric = {
                    'iv': float(row['iv']) if row['iv'] else 0.0,
                    'delta': float(row['delta']) if row['delta'] else 0.0,
                    'gamma': float(row['gamma']) if row['gamma'] else 0.0,
                    'theta': float(row['theta']) if row['theta'] else 0.0,
                    'vega': float(row['vega']) if row['vega'] else 0.0,
                    'premium': 0.0,  # Not available in aggregated table
                    'oi': 0,  # Not available in aggregated table
                    'oi_delta': 0,  # Not available in aggregated table
                    'bid': 0.0,  # Not available in aggregated table
                    'ask': 0.0,  # Not available in aggregated table
                    'last': 0.0  # Not available in aggregated table
                }
                metrics.append(metric)

        response = {
            'timestamps': timestamps,
            'candles': candles
        }

        # Only include metrics for option data
        if metrics:
            response['metrics'] = metrics

        context = f"{underlying}"
        if strike:
            context += f" strike {strike}"
        elif bucket:
            context += f" {bucket} bucket"
        if expiry:
            context += f" {expiry}"

        logger.info(f"Fetched {len(timestamps)} data points for {context}")
        return response

    except Exception as e:
        logger.error(f"Error in historical series: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
