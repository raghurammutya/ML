"""
Futures market data endpoints with position analysis and rollover metrics.

Provides:
- Position signals (long/short buildup/unwinding)
- Signal strength indicators
- Rollover pressure metrics
"""
from fastapi import APIRouter, Depends, Query, HTTPException
from datetime import datetime, timedelta
from typing import Optional, List
import logging

from ..database import DataManager
from .indicators import get_data_manager
from ..services.futures_analysis import FuturesAnalyzer

router = APIRouter(prefix="/futures", tags=["futures"])
logger = logging.getLogger(__name__)


@router.get("/position-signals")
async def get_position_signals(
    symbol: str = Query(..., description="Underlying symbol (e.g., NIFTY, BANKNIFTY)"),
    resolution: int = Query(1, description="Resolution in minutes (1, 5, 15)"),
    contract: Optional[str] = Query(None, description="Specific contract or leave empty for current month"),
    hours: int = Query(24, description="Hours of historical data"),
    threshold_pct: float = Query(0.1, description="Minimum % change to consider significant"),
    dm: DataManager = Depends(get_data_manager),
):
    """
    Get futures position signals (long/short buildup/unwinding) with signal strength.

    Returns time series with:
    - price_change_pct: Price change percentage
    - oi_change_pct: Open interest change percentage
    - position_signal: LONG_BUILDUP, SHORT_BUILDUP, LONG_UNWINDING, SHORT_UNWINDING, NEUTRAL
    - signal_strength: Magnitude of combined price + OI movement
    - sentiment: BULLISH, BEARISH, or NEUTRAL
    """
    try:
        # Time range
        to_time = datetime.now()
        from_time = to_time - timedelta(hours=hours)

        # SQL query with window functions to compute changes
        query = """
            WITH lagged_data AS (
                SELECT
                    time,
                    contract,
                    expiry,
                    close,
                    open_interest,
                    volume,
                    LAG(close) OVER (PARTITION BY contract ORDER BY time) as prev_close,
                    LAG(open_interest) OVER (PARTITION BY contract ORDER BY time) as prev_oi
                FROM futures_bars
                WHERE symbol = $1
                  AND resolution = $2
                  AND time >= $3
                  AND time <= $4
                  AND ($5::text IS NULL OR contract = $5)
            )
            SELECT
                time,
                contract,
                expiry,
                close,
                open_interest,
                volume,
                close - prev_close as price_change,
                CASE
                    WHEN prev_close > 0
                    THEN (close - prev_close) / prev_close * 100
                    ELSE NULL
                END as price_change_pct,
                open_interest - prev_oi as oi_change,
                CASE
                    WHEN prev_oi > 0
                    THEN (open_interest - prev_oi) / prev_oi * 100
                    ELSE NULL
                END as oi_change_pct
            FROM lagged_data
            ORDER BY time DESC, contract
        """

        analyzer = FuturesAnalyzer()

        async with dm.pool.acquire() as conn:
            rows = await conn.fetch(
                query,
                symbol.upper(),
                resolution,
                from_time,
                to_time,
                contract
            )

        # Process rows and classify signals
        series = []
        for row in rows:
            price_pct = float(row['price_change_pct']) if row['price_change_pct'] is not None else 0.0
            oi_pct = float(row['oi_change_pct']) if row['oi_change_pct'] is not None else 0.0

            # Classify signal
            position_signal = analyzer.classify_position_signal(price_pct, oi_pct, threshold_pct)
            signal_strength = analyzer.compute_signal_strength(price_pct, oi_pct)
            sentiment = analyzer.get_bullish_bearish_indicator(position_signal)

            series.append({
                "timestamp": int(row['time'].timestamp()),
                "contract": row['contract'],
                "expiry": row['expiry'].isoformat(),
                "close": float(row['close']),
                "open_interest": float(row['open_interest']) if row['open_interest'] else None,
                "volume": int(row['volume']) if row['volume'] else None,
                "price_change": float(row['price_change']) if row['price_change'] is not None else None,
                "price_change_pct": price_pct,
                "oi_change": float(row['oi_change']) if row['oi_change'] is not None else None,
                "oi_change_pct": oi_pct,
                "position_signal": position_signal,
                "signal_strength": signal_strength,
                "sentiment": sentiment
            })

        return {
            "status": "ok",
            "symbol": symbol.upper(),
            "resolution": resolution,
            "from_time": int(from_time.timestamp()),
            "to_time": int(to_time.timestamp()),
            "data_points": len(series),
            "series": series
        }

    except Exception as e:
        logger.error(f"Error fetching position signals: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/rollover-metrics")
async def get_rollover_metrics(
    symbol: str = Query(..., description="Underlying symbol (e.g., NIFTY, BANKNIFTY)"),
    threshold_days: int = Query(5, description="Days before expiry to compute rollover pressure"),
    dm: DataManager = Depends(get_data_manager),
):
    """
    Get rollover metrics showing OI distribution across expiries.

    Returns for each expiry:
    - total_oi: Total open interest in contract
    - total_volume: Total volume traded
    - oi_pct: % of total OI across all expiries
    - days_to_expiry: Days until contract expires
    - rollover_pressure: Urgency score (0-100) indicating need to rollover positions

    High rollover pressure = near expiry + high OI concentration
    """
    try:
        # Get latest data for each contract
        query = """
            WITH latest_data AS (
                SELECT DISTINCT ON (contract)
                    contract,
                    expiry,
                    time,
                    open_interest,
                    volume
                FROM futures_bars
                WHERE symbol = $1
                  AND resolution = 1
                ORDER BY contract, time DESC
            ),
            expiry_totals AS (
                SELECT
                    expiry,
                    SUM(open_interest) as total_oi,
                    SUM(volume) as total_volume,
                    (expiry::date - CURRENT_DATE) as days_to_expiry,
                    COUNT(*) as contract_count
                FROM latest_data
                WHERE open_interest IS NOT NULL
                GROUP BY expiry
            ),
            oi_distribution AS (
                SELECT
                    expiry,
                    total_oi,
                    total_volume,
                    days_to_expiry,
                    contract_count,
                    total_oi / NULLIF(SUM(total_oi) OVER (), 0) * 100 as oi_pct
                FROM expiry_totals
            )
            SELECT
                expiry,
                total_oi,
                total_volume,
                days_to_expiry,
                contract_count,
                oi_pct
            FROM oi_distribution
            ORDER BY expiry;
        """

        analyzer = FuturesAnalyzer()

        async with dm.pool.acquire() as conn:
            rows = await conn.fetch(query, symbol.upper())

        # Compute rollover pressure for each expiry
        expiries = []
        for row in rows:
            days = int(row['days_to_expiry']) if row['days_to_expiry'] is not None else 999
            oi_pct = float(row['oi_pct']) if row['oi_pct'] is not None else 0.0

            rollover_pressure = analyzer.compute_rollover_pressure(
                days_to_expiry=days,
                oi_pct=oi_pct,
                threshold_days=threshold_days
            )

            expiries.append({
                "expiry": row['expiry'].isoformat(),
                "total_oi": float(row['total_oi']) if row['total_oi'] else 0.0,
                "total_volume": int(row['total_volume']) if row['total_volume'] else 0,
                "days_to_expiry": days,
                "contract_count": int(row['contract_count']),
                "oi_pct": oi_pct,
                "rollover_pressure": rollover_pressure,
                "rollover_status": _classify_rollover_status(rollover_pressure, days)
            })

        # Summary stats
        total_oi = sum(e['total_oi'] for e in expiries)
        current_month = next((e for e in expiries if e['days_to_expiry'] >= 0 and e['days_to_expiry'] <= 30), None)

        return {
            "status": "ok",
            "symbol": symbol.upper(),
            "threshold_days": threshold_days,
            "total_oi": total_oi,
            "expiry_count": len(expiries),
            "current_month_expiry": current_month['expiry'] if current_month else None,
            "current_month_oi_pct": current_month['oi_pct'] if current_month else None,
            "current_month_pressure": current_month['rollover_pressure'] if current_month else None,
            "expiries": expiries
        }

    except Exception as e:
        logger.error(f"Error fetching rollover metrics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/summary")
async def get_futures_summary(
    symbol: str = Query(..., description="Underlying symbol"),
    dm: DataManager = Depends(get_data_manager),
):
    """
    Get futures market summary with latest position signal and rollover status.

    Quick snapshot showing:
    - Latest price and OI
    - Current position signal
    - Rollover urgency
    """
    try:
        # Get most recent bar
        query = """
            SELECT DISTINCT ON (contract)
                contract,
                expiry,
                time,
                close,
                open_interest,
                volume
            FROM futures_bars
            WHERE symbol = $1
              AND resolution = 1
            ORDER BY contract, time DESC
        """

        async with dm.pool.acquire() as conn:
            rows = await conn.fetch(query, symbol.upper())

        if not rows:
            raise HTTPException(status_code=404, detail=f"No futures data found for {symbol}")

        # Find current month contract (closest expiry)
        current_contract = min(rows, key=lambda r: r['expiry'])

        return {
            "status": "ok",
            "symbol": symbol.upper(),
            "contract": current_contract['contract'],
            "expiry": current_contract['expiry'].isoformat(),
            "last_update": int(current_contract['time'].timestamp()),
            "close": float(current_contract['close']),
            "open_interest": float(current_contract['open_interest']) if current_contract['open_interest'] else None,
            "volume": int(current_contract['volume']) if current_contract['volume'] else None,
            "active_contracts": len(rows)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching futures summary: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


def _classify_rollover_status(pressure: float, days_to_expiry: int) -> str:
    """
    Classify rollover status based on pressure and days remaining.

    Returns:
        HIGH: Urgent rollover needed
        MEDIUM: Approaching rollover window
        LOW: No immediate rollover needed
        EXPIRED: Contract has expired
    """
    if days_to_expiry < 0:
        return "EXPIRED"
    elif pressure > 30:
        return "HIGH"
    elif pressure > 10:
        return "MEDIUM"
    else:
        return "LOW"
