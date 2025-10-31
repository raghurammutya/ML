from fastapi import APIRouter, HTTPException, Query, Depends
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import logging
import asyncpg

from ..database import DataManager, _normalize_symbol, _normalize_timeframe
from .indicators import get_data_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/replay", tags=["replay"])


@router.get("/window")
async def get_replay_window(
    underlying: str = Query(..., description="Underlying symbol (e.g., NIFTY)"),
    timeframe: str = Query("1min", description="Timeframe (1min, 5min, etc.)"),
    start: str = Query(..., description="Start time (ISO format)"),
    end: str = Query(..., description="End time (ISO format)"),
    expiries: str = Query(..., description="Comma-separated expiry dates"),
    strikes: Optional[str] = Query(None, description="Comma-separated strikes"),
    panels: str = Query(..., description="Comma-separated panel IDs"),
    data_manager: DataManager = Depends(get_data_manager)
):
    """
    Fetch historical window for replay mode.
    Returns aligned time-series data for main chart and all requested panels.
    """
    try:
        # Parse parameters
        start_time = datetime.fromisoformat(start.replace('Z', '+00:00'))
        end_time = datetime.fromisoformat(end.replace('Z', '+00:00'))
        expiry_list = expiries.split(',')
        strike_list = [int(s) for s in strikes.split(',')] if strikes else None
        panel_list = panels.split(',')

        normalized_tf = _normalize_timeframe(timeframe)
        symbol_db = _normalize_symbol(underlying)

        # Use shared pool from DataManager (no pool leak!)
        if not data_manager.pool:
            raise HTTPException(status_code=500, detail="Database connection unavailable")

        async with data_manager.pool.acquire() as conn:
            # Fetch price series (underlying candles)
            price_query = """
                SELECT
                    bucket_time,
                    open,
                    high,
                    low,
                    close,
                    volume
                FROM underlying_bars
                WHERE symbol = $1
                    AND timeframe = $2
                    AND bucket_time >= $3
                    AND bucket_time <= $4
                ORDER BY bucket_time
            """

            price_rows = await conn.fetch(
                price_query,
                symbol_db,
                normalized_tf,
                start_time,
                end_time
            )

            # Fetch panel data for each requested panel
            panels_data: Dict[str, Any] = {}

            for panel_id in panel_list:
                # Determine what data to fetch based on panel type
                if panel_id in ['call_iv', 'put_iv', 'call_delta', 'put_delta',
                               'call_gamma', 'put_gamma', 'call_theta', 'put_theta',
                               'call_vega', 'put_vega']:
                    # Greek panels - fetch from fo_option_strike_bars
                    metric = panel_id.split('_')[1]  # iv, delta, etc.
                    side = 'call' if 'call' in panel_id else 'put'

                    panel_query = f"""
                        SELECT
                            bucket_time,
                            strike,
                            expiry,
                            {side}_{metric}_avg as value
                        FROM fo_option_strike_bars
                        WHERE symbol = $1
                            AND timeframe = $2
                            AND bucket_time >= $3
                            AND bucket_time <= $4
                            AND expiry = ANY($5)
                        ORDER BY bucket_time, strike
                    """

                    panel_rows = await conn.fetch(
                        panel_query,
                        symbol_db,
                        normalized_tf,
                        start_time,
                        end_time,
                        expiry_list
                    )

                    # Group by expiry
                    series_by_expiry: Dict[str, List[Dict]] = {}
                    for row in panel_rows:
                        expiry_key = row['expiry'].isoformat()
                        if expiry_key not in series_by_expiry:
                            series_by_expiry[expiry_key] = []

                        series_by_expiry[expiry_key].append({
                            'time': row['bucket_time'].isoformat() + 'Z',
                            'value': float(row['value']) if row['value'] else 0.0,
                            'strike': int(row['strike'])
                        })

                    panels_data[panel_id] = {
                        'series': [
                            {
                                'expiry': exp,
                                'points': points
                            }
                            for exp, points in series_by_expiry.items()
                        ]
                    }

                elif panel_id == 'pcr':
                    # PCR panel - compute from OI data if available
                    # For now, return empty as OI data is not fully implemented
                    panels_data[panel_id] = {'series': []}

                else:
                    # Unknown panel type
                    panels_data[panel_id] = {'series': []}

        # Format response
        timestamps = [row['bucket_time'].isoformat() + 'Z' for row in price_rows]
        candles = [
            {
                'o': float(row['open']) if row['open'] else 0.0,
                'h': float(row['high']) if row['high'] else 0.0,
                'l': float(row['low']) if row['low'] else 0.0,
                'c': float(row['close']) if row['close'] else 0.0,
                'v': int(row['volume']) if row['volume'] else 0
            }
            for row in price_rows
        ]

        response = {
            'status': 'ok',
            'underlying': symbol_db,
            'timeframe': normalized_tf,
            'range': {
                'start': timestamps[0] if timestamps else start,
                'end': timestamps[-1] if timestamps else end
            },
            'timestamps': timestamps,
            'priceSeries': {
                'timestamps': timestamps,
                'candles': candles
            },
            'panels': panels_data
        }

        logger.info(f"Replay window: {len(timestamps)} timestamps for {symbol_db}")
        return response

    except Exception as e:
        logger.error(f"Error in replay window: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
