"""
Mutual Funds API Routes
"""
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from loguru import logger

from .api_models import (
    CancelMFOrderRequest,
    CancelMFSIPRequest,
    ModifyMFSIPRequest,
    PlaceMFOrderRequest,
    PlaceMFSIPRequest,
)
from .generator import ticker_loop

router = APIRouter(prefix="/mf", tags=["mutual_funds"])


# ------------------------------------------------------------------ MF Orders
@router.post("/orders", response_model=Dict[str, str], status_code=201)
async def place_mf_order(payload: PlaceMFOrderRequest) -> Dict[str, str]:
    """
    Place a mutual fund order (purchase or redemption).

    Returns dict with order_id.
    """
    accounts = ticker_loop.list_accounts()
    if payload.account_id not in accounts:
        raise HTTPException(status_code=400, detail=f"Account '{payload.account_id}' not configured")

    try:
        async with ticker_loop.borrow_client(payload.account_id) as client:
            order_id = await client.place_mf_order(
                tradingsymbol=payload.tradingsymbol,
                transaction_type=payload.transaction_type,
                amount=payload.amount,
                quantity=payload.quantity,
                tag=payload.tag,
            )
            return {"order_id": order_id}
    except Exception as exc:
        logger.exception(f"Failed to place MF order for account {payload.account_id}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.delete("/orders", response_model=Dict[str, str])
async def cancel_mf_order(payload: CancelMFOrderRequest) -> Dict[str, str]:
    """
    Cancel a pending mutual fund order.

    Returns dict with order_id.
    """
    accounts = ticker_loop.list_accounts()
    if payload.account_id not in accounts:
        raise HTTPException(status_code=400, detail=f"Account '{payload.account_id}' not configured")

    try:
        async with ticker_loop.borrow_client(payload.account_id) as client:
            order_id = await client.cancel_mf_order(payload.order_id)
            return {"order_id": order_id}
    except Exception as exc:
        logger.exception(f"Failed to cancel MF order for account {payload.account_id}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/orders", response_model=List[Dict[str, Any]])
async def list_mf_orders(
    account_id: str = "primary",
    order_id: str = None
) -> List[Dict[str, Any]]:
    """
    Get all mutual fund orders or details of a specific order.
    """
    accounts = ticker_loop.list_accounts()
    if account_id not in accounts:
        raise HTTPException(status_code=400, detail=f"Account '{account_id}' not configured")

    try:
        async with ticker_loop.borrow_client(account_id) as client:
            return await client.mf_orders(order_id=order_id)
    except Exception as exc:
        logger.exception(f"Failed to fetch MF orders for account {account_id}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ------------------------------------------------------------------ MF SIPs
@router.post("/sips", response_model=Dict[str, str], status_code=201)
async def place_mf_sip(payload: PlaceMFSIPRequest) -> Dict[str, str]:
    """
    Place a mutual fund SIP (Systematic Investment Plan).

    Returns dict with sip_id.
    """
    accounts = ticker_loop.list_accounts()
    if payload.account_id not in accounts:
        raise HTTPException(status_code=400, detail=f"Account '{payload.account_id}' not configured")

    try:
        async with ticker_loop.borrow_client(payload.account_id) as client:
            sip_id = await client.place_mf_sip(
                tradingsymbol=payload.tradingsymbol,
                amount=payload.amount,
                frequency=payload.frequency,
                initial_amount=payload.initial_amount,
                installments=payload.installments,
                installment_day=payload.installment_day,
                tag=payload.tag,
            )
            return {"sip_id": sip_id}
    except Exception as exc:
        logger.exception(f"Failed to place MF SIP for account {payload.account_id}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.put("/sips", response_model=Dict[str, str])
async def modify_mf_sip(payload: ModifyMFSIPRequest) -> Dict[str, str]:
    """
    Modify an active mutual fund SIP.

    Returns dict with sip_id.
    """
    accounts = ticker_loop.list_accounts()
    if payload.account_id not in accounts:
        raise HTTPException(status_code=400, detail=f"Account '{payload.account_id}' not configured")

    try:
        async with ticker_loop.borrow_client(payload.account_id) as client:
            sip_id = await client.modify_mf_sip(
                sip_id=payload.sip_id,
                amount=payload.amount,
                frequency=payload.frequency,
                installments=payload.installments,
                installment_day=payload.installment_day,
                status=payload.status,
            )
            return {"sip_id": sip_id}
    except Exception as exc:
        logger.exception(f"Failed to modify MF SIP for account {payload.account_id}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.delete("/sips", response_model=Dict[str, str])
async def cancel_mf_sip(payload: CancelMFSIPRequest) -> Dict[str, str]:
    """
    Cancel an active mutual fund SIP.

    Returns dict with sip_id.
    """
    accounts = ticker_loop.list_accounts()
    if payload.account_id not in accounts:
        raise HTTPException(status_code=400, detail=f"Account '{payload.account_id}' not configured")

    try:
        async with ticker_loop.borrow_client(payload.account_id) as client:
            sip_id = await client.cancel_mf_sip(payload.sip_id)
            return {"sip_id": sip_id}
    except Exception as exc:
        logger.exception(f"Failed to cancel MF SIP for account {payload.account_id}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/sips", response_model=List[Dict[str, Any]])
async def list_mf_sips(
    account_id: str = "primary",
    sip_id: str = None
) -> List[Dict[str, Any]]:
    """
    Get all mutual fund SIPs or details of a specific SIP.
    """
    accounts = ticker_loop.list_accounts()
    if account_id not in accounts:
        raise HTTPException(status_code=400, detail=f"Account '{account_id}' not configured")

    try:
        async with ticker_loop.borrow_client(account_id) as client:
            return await client.mf_sips(sip_id=sip_id)
    except Exception as exc:
        logger.exception(f"Failed to fetch MF SIPs for account {account_id}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ------------------------------------------------------------------ MF Holdings & Instruments
@router.get("/holdings", response_model=List[Dict[str, Any]])
async def get_mf_holdings(account_id: str = "primary") -> List[Dict[str, Any]]:
    """
    Get mutual fund holdings.
    """
    accounts = ticker_loop.list_accounts()
    if account_id not in accounts:
        raise HTTPException(status_code=400, detail=f"Account '{account_id}' not configured")

    try:
        async with ticker_loop.borrow_client(account_id) as client:
            return await client.mf_holdings()
    except Exception as exc:
        logger.exception(f"Failed to fetch MF holdings for account {account_id}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/instruments", response_model=List[Dict[str, Any]])
async def get_mf_instruments(account_id: str = "primary") -> List[Dict[str, Any]]:
    """
    Get list of all available mutual fund instruments.
    """
    accounts = ticker_loop.list_accounts()
    if account_id not in accounts:
        raise HTTPException(status_code=400, detail=f"Account '{account_id}' not configured")

    try:
        async with ticker_loop.borrow_client(account_id) as client:
            return await client.mf_instruments()
    except Exception as exc:
        logger.exception(f"Failed to fetch MF instruments for account {account_id}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
