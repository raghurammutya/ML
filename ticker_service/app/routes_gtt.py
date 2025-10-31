"""
GTT (Good Till Triggered) API Routes
"""
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from loguru import logger

from .api_models import DeleteGTTRequest, GTTTriggerRangeRequest, ModifyGTTRequest, PlaceGTTRequest
from .generator import ticker_loop

router = APIRouter(prefix="/gtt", tags=["gtt"])


@router.post("/", response_model=Dict[str, int], status_code=201)
async def place_gtt(payload: PlaceGTTRequest) -> Dict[str, int]:
    """
    Place a GTT (Good Till Triggered) order.

    Returns dict with gtt_id.
    """
    accounts = ticker_loop.list_accounts()
    if payload.account_id not in accounts:
        raise HTTPException(status_code=400, detail=f"Account '{payload.account_id}' not configured")

    try:
        async with ticker_loop.borrow_client(payload.account_id) as client:
            orders = [order.dict() for order in payload.orders]
            gtt_id = await client.place_gtt(
                trigger_type=payload.trigger_type,
                tradingsymbol=payload.tradingsymbol,
                exchange=payload.exchange,
                trigger_values=payload.trigger_values,
                last_price=payload.last_price,
                orders=orders,
            )
            return {"gtt_id": gtt_id}
    except Exception as exc:
        logger.exception(f"Failed to place GTT for account {payload.account_id}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{gtt_id}", response_model=Dict[str, Any])
async def get_gtt(gtt_id: int, account_id: str = "primary") -> Dict[str, Any]:
    """
    Get details of a specific GTT.
    """
    accounts = ticker_loop.list_accounts()
    if account_id not in accounts:
        raise HTTPException(status_code=400, detail=f"Account '{account_id}' not configured")

    try:
        async with ticker_loop.borrow_client(account_id) as client:
            return await client.get_gtt(gtt_id)
    except Exception as exc:
        logger.exception(f"Failed to fetch GTT {gtt_id} for account {account_id}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/", response_model=List[Dict[str, Any]])
async def list_gtts(account_id: str = "primary") -> List[Dict[str, Any]]:
    """
    Get list of all active GTTs.
    """
    accounts = ticker_loop.list_accounts()
    if account_id not in accounts:
        raise HTTPException(status_code=400, detail=f"Account '{account_id}' not configured")

    try:
        async with ticker_loop.borrow_client(account_id) as client:
            return await client.get_gtts()
    except Exception as exc:
        logger.exception(f"Failed to fetch GTTs for account {account_id}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.put("/", response_model=Dict[str, int])
async def modify_gtt(payload: ModifyGTTRequest) -> Dict[str, int]:
    """
    Modify a GTT order.

    Returns dict with gtt_id.
    """
    accounts = ticker_loop.list_accounts()
    if payload.account_id not in accounts:
        raise HTTPException(status_code=400, detail=f"Account '{payload.account_id}' not configured")

    try:
        async with ticker_loop.borrow_client(payload.account_id) as client:
            orders = [order.dict() for order in payload.orders]
            gtt_id = await client.modify_gtt(
                gtt_id=payload.gtt_id,
                trigger_type=payload.trigger_type,
                tradingsymbol=payload.tradingsymbol,
                exchange=payload.exchange,
                trigger_values=payload.trigger_values,
                last_price=payload.last_price,
                orders=orders,
            )
            return {"gtt_id": gtt_id}
    except Exception as exc:
        logger.exception(f"Failed to modify GTT for account {payload.account_id}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.delete("/", response_model=Dict[str, int])
async def delete_gtt(payload: DeleteGTTRequest) -> Dict[str, int]:
    """
    Cancel a GTT order.

    Returns dict with gtt_id.
    """
    accounts = ticker_loop.list_accounts()
    if payload.account_id not in accounts:
        raise HTTPException(status_code=400, detail=f"Account '{payload.account_id}' not configured")

    try:
        async with ticker_loop.borrow_client(payload.account_id) as client:
            gtt_id = await client.delete_gtt(payload.gtt_id)
            return {"gtt_id": gtt_id}
    except Exception as exc:
        logger.exception(f"Failed to delete GTT for account {payload.account_id}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/trigger-range", response_model=Dict[str, Any])
async def get_trigger_range(payload: GTTTriggerRangeRequest) -> Dict[str, Any]:
    """
    Get trigger range for GTT orders for a specific instrument.

    Returns price range within which GTT triggers can be placed.
    """
    accounts = ticker_loop.list_accounts()
    if payload.account_id not in accounts:
        raise HTTPException(status_code=400, detail=f"Account '{payload.account_id}' not configured")

    try:
        async with ticker_loop.borrow_client(payload.account_id) as client:
            return await client.gtt_trigger_range(
                transaction_type=payload.transaction_type,
                exchange=payload.exchange,
                tradingsymbol=payload.tradingsymbol,
            )
    except Exception as exc:
        logger.exception(f"Failed to fetch GTT trigger range for account {payload.account_id}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
