# app/routes/indicators.py
"""
Technical indicators API endpoints for TradingView charts.
Provides Central Pivot Range (CPR) and extensible framework for other indicators.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from fastapi import APIRouter, Query, HTTPException, Depends
from pydantic import BaseModel

from ..database import DataManager, _normalize_symbol, _normalize_timeframe, _as_epoch_seconds

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/indicators", tags=["indicators"])

# CPR Models
class CPRPoint(BaseModel):
    """Central Pivot Range point"""
    time: int  # Unix timestamp (start of trading day)
    pivot: float      # Central Pivot (P)
    bc: float         # Bottom Central (BC) 
    tc: float         # Top Central (TC)
    r1: float         # Resistance 1
    r2: float         # Resistance 2
    r3: float         # Resistance 3
    s1: float         # Support 1
    s2: float         # Support 2
    s3: float         # Support 3
    prev_high: float  # Previous day high
    prev_close: float # Previous day close

class CPRResponse(BaseModel):
    """CPR indicator response"""
    status: str = "ok"
    data: List[CPRPoint] = []
    symbol: str
    timeframe: str
    from_time: int
    to_time: int

class IndicatorSettings(BaseModel):
    """Indicator display settings"""
    enabled: bool = True
    pivot_color: str = "#FFEB3B"      # Yellow
    bc_color: str = "#FF5722"         # Red
    tc_color: str = "#4CAF50"         # Green
    resistance_color: str = "#2196F3" # Blue
    support_color: str = "#FF9800"    # Orange
    line_width: int = 1
    line_style: str = "solid"  # solid, dashed, dotted

def calculate_cpr(high: float, low: float, close: float) -> Dict[str, float]:
    """
    Calculate Central Pivot Range levels from previous day's HLC.
    
    CPR Formula:
    - Pivot (P) = (H + L + C) / 3
    - Bottom Central (BC) = (H + L) / 2  
    - Top Central (TC) = (P - BC) + P = 2*P - BC
    - Resistance 1 (R1) = 2*P - L
    - Resistance 2 (R2) = P + (H - L)
    - Resistance 3 (R3) = H + 2*(P - L)
    - Support 1 (S1) = 2*P - H
    - Support 2 (S2) = P - (H - L)
    - Support 3 (S3) = L - 2*(H - P)
    """
    pivot = (high + low + close) / 3
    bc = (high + low) / 2
    tc = (2 * pivot) - bc
    
    r1 = (2 * pivot) - low
    r2 = pivot + (high - low)
    r3 = high + 2 * (pivot - low)
    
    s1 = (2 * pivot) - high
    s2 = pivot - (high - low)
    s3 = low - 2 * (high - pivot)
    
    return {
        "pivot": round(pivot, 2),
        "bc": round(bc, 2),
        "tc": round(tc, 2),
        "r1": round(r1, 2),
        "r2": round(r2, 2),
        "r3": round(r3, 2),
        "s1": round(s1, 2),
        "s2": round(s2, 2),
        "s3": round(s3, 2),
        "prev_high": round(high, 2),
        "prev_close": round(close, 2)
    }

async def get_cpr_data(
    data_manager: DataManager,
    symbol: str,
    from_timestamp: int,
    to_timestamp: int,
    resolution: str
) -> List[CPRPoint]:
    """
    Generate CPR data for the given time range.
    CPR values are calculated from previous day's HLC and remain constant throughout the trading day.
    Returns one CPR point per trading day.
    """
    normalized_symbol = _normalize_symbol(symbol)
    from_ts, to_ts = _as_epoch_seconds(from_timestamp, to_timestamp)
    
    logger.info(f"Calculating CPR for {normalized_symbol} from {from_ts} to {to_ts}")
    
    # Get daily OHLC data to calculate CPR
    # We need to get data from earlier to have previous day's HLC for first day
    extended_from = from_ts - (24 * 3600 * 10)  # 10 days before to ensure we have enough data
    
    try:
        # Always get daily bars for CPR calculation regardless of requested resolution
        daily_history = await data_manager.get_history(
            normalized_symbol, extended_from, to_ts, "1D"
        )
        
        if not daily_history or daily_history.get("s") != "ok":
            logger.warning(f"No daily data for CPR calculation: {daily_history}")
            return []
        
        daily_bars = []
        times = daily_history.get("t", [])
        opens = daily_history.get("o", [])
        highs = daily_history.get("h", [])
        lows = daily_history.get("l", [])
        closes = daily_history.get("c", [])
        
        for i in range(len(times)):
            daily_bars.append({
                "time": times[i],
                "open": opens[i],
                "high": highs[i],
                "low": lows[i],
                "close": closes[i]
            })
        
        # Generate CPR points - one per trading day
        cpr_points = []
        
        for i in range(1, len(daily_bars)):  # Start from index 1 to have previous day
            prev_day = daily_bars[i-1]
            current_day = daily_bars[i]
            
            # Skip if current day is before our requested range
            if current_day["time"] < from_ts:
                continue
                
            # Calculate CPR from previous day's HLC
            cpr_levels = calculate_cpr(
                prev_day["high"],
                prev_day["low"], 
                prev_day["close"]
            )
            
            # Create CPR point for current day (using current day's timestamp as start of trading day)
            cpr_point = CPRPoint(
                time=current_day["time"],  # Start of current trading day
                pivot=cpr_levels["pivot"],
                bc=cpr_levels["bc"],
                tc=cpr_levels["tc"],
                r1=cpr_levels["r1"],
                r2=cpr_levels["r2"],
                r3=cpr_levels["r3"],
                s1=cpr_levels["s1"],
                s2=cpr_levels["s2"],
                s3=cpr_levels["s3"],
                prev_high=cpr_levels["prev_high"],
                prev_close=cpr_levels["prev_close"]
            )
            
            cpr_points.append(cpr_point)
        
        logger.info(f"Generated {len(cpr_points)} CPR points for trading days")
        return cpr_points
        
    except Exception as e:
        logger.error(f"Error calculating CPR: {e}")
        raise HTTPException(status_code=500, detail=f"CPR calculation failed: {str(e)}")

# Global data manager reference (set by main.py)
_data_manager: Optional[DataManager] = None

def set_data_manager(dm: DataManager):
    """Set the data manager instance from main.py"""
    global _data_manager
    _data_manager = dm

async def get_data_manager() -> DataManager:
    """Get the data manager instance"""
    if not _data_manager:
        raise HTTPException(status_code=503, detail="Data manager not available")
    return _data_manager

@router.get("/cpr", response_model=CPRResponse)
async def get_cpr_indicator(
    symbol: str = Query("NIFTY50", description="Symbol to get CPR for"),
    from_timestamp: int = Query(..., alias="from", description="Start timestamp"),
    to_timestamp: int = Query(..., alias="to", description="End timestamp"),
    resolution: str = Query("1D", description="Timeframe resolution"),
    data_manager: DataManager = Depends(get_data_manager)
):
    """
    Get Central Pivot Range (CPR) indicator data.
    
    CPR is calculated using the previous day's High, Low, and Close:
    - Pivot (P) = (H + L + C) / 3
    - Bottom Central (BC) = (H + L) / 2
    - Top Central (TC) = 2*P - BC
    - R1/R2 = Resistance levels
    - S1/S2 = Support levels
    """
    try:
        cpr_data = await get_cpr_data(
            data_manager, symbol, from_timestamp, to_timestamp, resolution
        )
        
        return CPRResponse(
            status="ok",
            data=cpr_data,
            symbol=symbol,
            timeframe=resolution,
            from_time=from_timestamp,
            to_time=to_timestamp
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"CPR endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/available")
async def get_available_indicators():
    """Get list of available technical indicators"""
    return {
        "indicators": [
            {
                "id": "cpr",
                "name": "Central Pivot Range",
                "description": "Daily pivot points with support and resistance levels",
                "settings": {
                    "pivot_color": "#FFEB3B",
                    "bc_color": "#FF5722", 
                    "tc_color": "#4CAF50",
                    "resistance_color": "#2196F3",
                    "support_color": "#FF9800",
                    "line_width": 1,
                    "line_style": "solid"
                }
            }
        ]
    }