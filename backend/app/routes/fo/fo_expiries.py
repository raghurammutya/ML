"""
F&O Expiries API endpoints.
"""
import logging
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from ...config import get_settings
from ...database import DataManager, _normalize_symbol
from ..indicators import get_data_manager

router = APIRouter()
settings = get_settings()
logger = logging.getLogger(__name__)


@router.get("/expiries")
async def list_expiries(
    symbol: str = Query(settings.monitor_default_symbol),
    dm: DataManager = Depends(get_data_manager),
):
    """
    List all available expiries for a symbol.

    Returns basic list of expiry dates without metadata.
    For enhanced metadata with relative labels, use /expiries-v2.
    """
    symbol_db = _normalize_symbol(symbol)
    expiries = await dm.list_fo_expiries(symbol_db)
    return {
        "status": "ok",
        "symbol": symbol_db,
        "expiries": [exp.isoformat() for exp in expiries],
    }


async def _resolve_relative_expiries(
    dm: DataManager,
    symbol: str,
    relative_labels: List[str],
    as_of_date: Optional[date] = None
) -> Dict[str, date]:
    """
    Resolve relative expiry labels (NWeek+0, NMonth+1, etc.) to actual expiry dates.

    Args:
        dm: DataManager instance
        symbol: Underlying symbol
        relative_labels: List of relative labels to resolve
        as_of_date: Date to compute labels relative to (defaults to today)

    Returns:
        Dictionary mapping relative_label -> expiry_date
    """
    from app.services.expiry_labeler import ExpiryLabeler

    if not as_of_date:
        as_of_date = date.today()

    # Get all expiries for the symbol
    all_expiries = await dm.list_fo_expiries(symbol)
    if not all_expiries:
        return {}

    # Initialize expiry labeler and compute labels
    labeler = ExpiryLabeler(dm.pool)

    try:
        # Compute labels for all expiries as of the given date
        expiry_labels = await labeler.compute_labels(symbol, as_of_date)

        # Map relative labels to expiry dates
        label_to_expiry = {}
        for label_info in expiry_labels:
            if label_info.relative_label in relative_labels:
                label_to_expiry[label_info.relative_label] = label_info.expiry

        return label_to_expiry
    except Exception as e:
        logger.warning(f"Failed to resolve relative expiries: {e}")
        # Fallback: Simple mapping based on position
        # Filter future expiries
        future_expiries = [exp for exp in all_expiries if exp >= as_of_date]
        future_expiries.sort()

        label_to_expiry = {}

        # Map NWeek+0, NWeek+1, etc.
        for i, label in enumerate(relative_labels):
            if label.startswith("NWeek+") and i < len(future_expiries):
                label_to_expiry[label] = future_expiries[i]
            elif label == "NMonth+0" and future_expiries:
                # Find the first monthly expiry (last Thursday of month)
                for exp in future_expiries:
                    # Check if it's last Thursday of month (rough check)
                    days_in_month = (exp.replace(day=28) + timedelta(days=4)).day
                    if exp.day > days_in_month - 7 and exp.weekday() == 3:  # Thursday
                        label_to_expiry[label] = exp
                        break

        return label_to_expiry


@router.get("/expiries-v2")
async def get_expiries_v2(
    symbol: str = Query(..., description="Underlying symbol (NIFTY, BANKNIFTY, etc.)"),
    backfill_days: int = Query(30, description="Days of historical labels to compute"),
    dm: DataManager = Depends(get_data_manager)
):
    """
    Get all expiries with relative labels and metadata.

    Returns:
    - is_weekly, is_monthly, is_quarterly flags
    - relative_label_today (e.g., "NWeek+1", "NMonth+0")
    - relative_label_timestamp (historical labels for each business day)

    Example:
    ```
    GET /fo/expiries-v2?symbol=NIFTY&backfill_days=30
    ```

    Response:
    ```json
    {
      "symbol": "NIFTY",
      "as_of_date": "2024-11-05",
      "expiries": [
        {
          "date": "2024-11-07",
          "is_weekly": true,
          "is_monthly": false,
          "relative_label_today": "NWeek+1",
          "relative_rank": 1,
          "relative_label_timestamp": [
            {"time": "2024-11-01", "label": "NWeek+2"},
            {"time": "2024-11-04", "label": "NWeek+1"}
          ]
        }
      ]
    }
    ```
    """
    from app.services.expiry_labeler import ExpiryLabeler

    symbol_norm = _normalize_symbol(symbol)
    as_of_date = date.today()

    # Get expiry metadata from database (pre-computed or on-the-fly)
    metadata_list = await dm.get_expiry_metadata(symbol_norm, as_of_date)

    if not metadata_list:
        raise HTTPException(status_code=404, detail=f"No expiries found for {symbol}")

    # Initialize labeler for historical computation
    labeler = ExpiryLabeler(dm.pool)

    expiries = []
    for meta in metadata_list:
        # Compute historical labels for this expiry
        historical = await labeler.compute_historical_labels(
            symbol_norm,
            meta['expiry'],
            backfill_days=backfill_days
        )

        expiries.append({
            "date": meta['expiry'].isoformat(),
            "is_weekly": meta['is_weekly'],
            "is_monthly": meta['is_monthly'],
            "is_quarterly": meta['is_quarterly'],
            "days_to_expiry": meta['days_to_expiry'],
            "relative_label_today": meta['relative_label'],
            "relative_rank": meta['relative_rank'],
            "relative_label_timestamp": [point.to_dict() for point in historical]
        })

    return {
        "symbol": symbol_norm,
        "as_of_date": as_of_date.isoformat(),
        "expiries": expiries
    }
