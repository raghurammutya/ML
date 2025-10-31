"""
User & Account API Routes
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from loguru import logger

from .generator import ticker_loop

router = APIRouter(prefix="/account", tags=["account"])


@router.get("/s", response_model=List[Dict[str, Any]])
async def list_accounts(include_profile: bool = True) -> List[Dict[str, Any]]:
    """
    List all configured trading accounts.

    Args:
        include_profile: If True, fetches full profile for each account. If False, returns only account IDs.

    Returns:
        List of account objects with account_id and optionally full profile details.

    Example response with include_profile=True:
    [
        {
            "account_id": "primary",
            "user_id": "XJ4540",
            "user_name": "John Doe",
            "broker": "ZERODHA",
            "exchanges": ["NSE", "NFO", ...],
            ...
        }
    ]

    Example response with include_profile=False:
    [
        {"account_id": "primary"},
        {"account_id": "secondary"}
    ]
    """
    try:
        account_ids = ticker_loop.list_accounts()

        if not include_profile:
            return [{"account_id": acc_id} for acc_id in account_ids]

        # Fetch profile for each account
        accounts_with_profiles = []
        for account_id in account_ids:
            try:
                async with ticker_loop.borrow_client(account_id) as client:
                    profile = await client.profile()
                    profile["account_id"] = account_id  # Add account_id to profile
                    accounts_with_profiles.append(profile)
            except Exception as exc:
                logger.error(f"Failed to fetch profile for account {account_id}: {exc}")
                # Include account in list even if profile fetch fails
                accounts_with_profiles.append({
                    "account_id": account_id,
                    "error": str(exc),
                    "profile_available": False
                })

        return accounts_with_profiles

    except Exception as exc:
        logger.exception("Failed to list accounts")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/profile", response_model=Dict[str, Any])
async def get_profile(account_id: str = "primary") -> Dict[str, Any]:
    """
    Get user profile details including enabled products, exchanges, and broker info.
    """
    accounts = ticker_loop.list_accounts()
    if account_id not in accounts:
        raise HTTPException(status_code=400, detail=f"Account '{account_id}' not configured")

    try:
        async with ticker_loop.borrow_client(account_id) as client:
            return await client.profile()
    except Exception as exc:
        logger.exception(f"Failed to fetch profile for account {account_id}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/margins", response_model=Dict[str, Any])
async def get_margins(
    account_id: str = "primary",
    segment: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get account margins and cash balances.

    Args:
        account_id: Account ID
        segment: Optional segment filter ("equity" or "commodity")

    Returns dict with margin details including available margins, used margins, and collateral.
    """
    accounts = ticker_loop.list_accounts()
    if account_id not in accounts:
        raise HTTPException(status_code=400, detail=f"Account '{account_id}' not configured")

    if segment and segment.lower() not in ("equity", "commodity"):
        raise HTTPException(
            status_code=400,
            detail="segment must be 'equity' or 'commodity'"
        )

    try:
        async with ticker_loop.borrow_client(account_id) as client:
            return await client.margins(segment=segment)
    except Exception as exc:
        logger.exception(f"Failed to fetch margins for account {account_id}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
