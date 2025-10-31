"""
Portfolio Management API Routes
"""
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from loguru import logger

from .api_models import ConvertPositionRequest
from .generator import ticker_loop

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.get("/holdings", response_model=List[Dict[str, Any]])
async def get_holdings(account_id: str = "primary") -> List[Dict[str, Any]]:
    """
    Get list of long-term equity holdings.
    """
    accounts = ticker_loop.list_accounts()
    if account_id not in accounts:
        raise HTTPException(status_code=400, detail=f"Account '{account_id}' not configured")

    try:
        async with ticker_loop.borrow_client(account_id) as client:
            return await client.holdings()
    except Exception as exc:
        logger.exception(f"Failed to fetch holdings for account {account_id}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/positions", response_model=Dict[str, Any])
async def get_positions(account_id: str = "primary") -> Dict[str, Any]:
    """
    Get net and day positions.

    Returns dict with 'net' and 'day' keys containing position lists.
    """
    accounts = ticker_loop.list_accounts()
    if account_id not in accounts:
        raise HTTPException(status_code=400, detail=f"Account '{account_id}' not configured")

    try:
        async with ticker_loop.borrow_client(account_id) as client:
            return await client.positions()
    except Exception as exc:
        logger.exception(f"Failed to fetch positions for account {account_id}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.put("/positions/convert", response_model=Dict[str, str])
async def convert_position(payload: ConvertPositionRequest) -> Dict[str, str]:
    """
    Convert position between product types (e.g., MIS to NRML).
    """
    accounts = ticker_loop.list_accounts()
    if payload.account_id not in accounts:
        raise HTTPException(status_code=400, detail=f"Account '{payload.account_id}' not configured")

    try:
        async with ticker_loop.borrow_client(payload.account_id) as client:
            result = await client.convert_position(
                exchange=payload.exchange,
                tradingsymbol=payload.tradingsymbol,
                transaction_type=payload.transaction_type,
                position_type=payload.position_type,
                quantity=payload.quantity,
                old_product=payload.old_product,
                new_product=payload.new_product,
            )
            return {"status": "success" if result else "failed"}
    except Exception as exc:
        logger.exception(f"Failed to convert position for account {payload.account_id}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
