"""
Trading Account Management API Routes

CRUD operations for managing trading accounts dynamically.
Supports creating, reading, updating, and deleting Kite Connect accounts.
"""
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Depends, Query
from loguru import logger

from .auth import verify_api_key
from .account_store import get_account_store
from .api_models import (
    CreateTradingAccountRequest,
    UpdateTradingAccountRequest,
    TradingAccountResponse
)
from .generator import ticker_loop

router = APIRouter(prefix="/trading-accounts", tags=["trading-accounts"])


@router.post("", response_model=TradingAccountResponse, status_code=201, dependencies=[Depends(verify_api_key)])
async def create_trading_account(payload: CreateTradingAccountRequest):
    """
    Create a new trading account.

    Stores credentials securely in the database with encryption.
    After creation, call POST /trading-accounts/reload to activate the account.

    Security Notes:
    - All sensitive fields (api_key, api_secret, password, totp_key, access_token) are encrypted
    - Requires API key authentication
    - Credentials are never logged in plaintext

    Example:
        POST /trading-accounts
        {
            "account_id": "account1",
            "api_key": "your_api_key",
            "api_secret": "your_api_secret",
            "username": "your_username",
            "password": "your_password",
            "totp_key": "your_totp_key",
            "token_dir": "/path/to/tokens"
        }
    """
    try:
        store = get_account_store()

        # Validate account_id format
        if not payload.account_id.replace("_", "").replace("-", "").isalnum():
            raise HTTPException(
                status_code=400,
                detail="account_id must contain only alphanumeric characters, hyphens, and underscores"
            )

        # Create account in database
        account = await store.create(
            account_id=payload.account_id,
            api_key=payload.api_key,
            api_secret=payload.api_secret,
            access_token=payload.access_token,
            username=payload.username,
            password=payload.password,
            totp_key=payload.totp_key,
            token_dir=payload.token_dir,
            metadata=payload.metadata
        )

        logger.info(f"Created trading account: {payload.account_id}")

        return TradingAccountResponse.from_db(account, mask_sensitive=True)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception(f"Failed to create trading account: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create account: {str(e)}")


@router.get("", response_model=List[TradingAccountResponse], dependencies=[Depends(verify_api_key)])
async def list_trading_accounts(
    active_only: bool = Query(True, description="Return only active accounts"),
    mask_sensitive: bool = Query(True, description="Mask sensitive fields in response")
):
    """
    List all trading accounts.

    Args:
        active_only: If True, returns only active accounts (is_active=True)
        mask_sensitive: If True, masks sensitive fields (api_key, passwords, etc.)

    Returns list of trading accounts with masked or full credentials.
    """
    try:
        store = get_account_store()
        accounts = await store.list(active_only=active_only)

        return [
            TradingAccountResponse.from_db(account, mask_sensitive=mask_sensitive)
            for account in accounts
        ]

    except Exception as e:
        logger.exception("Failed to list trading accounts")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{account_id}", response_model=TradingAccountResponse, dependencies=[Depends(verify_api_key)])
async def get_trading_account(
    account_id: str,
    mask_sensitive: bool = Query(True, description="Mask sensitive fields in response")
):
    """
    Get a specific trading account by ID.

    Args:
        account_id: The account identifier
        mask_sensitive: If True, masks sensitive fields

    Returns account details with optionally masked credentials.
    """
    try:
        store = get_account_store()
        account = await store.get(account_id)

        if not account:
            raise HTTPException(status_code=404, detail=f"Account '{account_id}' not found")

        return TradingAccountResponse.from_db(account, mask_sensitive=mask_sensitive)

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get trading account {account_id}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{account_id}", response_model=TradingAccountResponse, dependencies=[Depends(verify_api_key)])
async def update_trading_account(account_id: str, payload: UpdateTradingAccountRequest):
    """
    Update an existing trading account.

    Only updates fields that are provided (non-None).
    After updating, call POST /trading-accounts/reload to apply changes.

    Security Note:
    - Updated credentials are encrypted before storage
    - Requires API key authentication

    Example:
        PUT /trading-accounts/account1
        {
            "access_token": "new_access_token",
            "is_active": true
        }
    """
    try:
        store = get_account_store()

        # Check if account exists
        existing = await store.get(account_id)
        if not existing:
            raise HTTPException(status_code=404, detail=f"Account '{account_id}' not found")

        # Update account
        account = await store.update(
            account_id=account_id,
            api_key=payload.api_key,
            api_secret=payload.api_secret,
            access_token=payload.access_token,
            username=payload.username,
            password=payload.password,
            totp_key=payload.totp_key,
            token_dir=payload.token_dir,
            is_active=payload.is_active,
            metadata=payload.metadata
        )

        logger.info(f"Updated trading account: {account_id}")

        return TradingAccountResponse.from_db(account, mask_sensitive=True)

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to update trading account {account_id}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{account_id}", dependencies=[Depends(verify_api_key)])
async def delete_trading_account(
    account_id: str,
    hard_delete: bool = Query(False, description="Permanently delete from database (default: soft delete)")
):
    """
    Delete a trading account.

    By default, performs a soft delete (sets is_active=False).
    Use hard_delete=true to permanently remove from database.

    After deletion, call POST /trading-accounts/reload to remove from active sessions.

    Args:
        account_id: The account identifier
        hard_delete: If True, permanently deletes from database. If False, sets is_active=False.

    Returns:
        {"success": true, "account_id": "...", "hard_deleted": false}
    """
    try:
        store = get_account_store()

        # Check if account exists
        existing = await store.get(account_id)
        if not existing:
            raise HTTPException(status_code=404, detail=f"Account '{account_id}' not found")

        # Delete account
        success = await store.delete(account_id, soft_delete=not hard_delete)

        if not success:
            raise HTTPException(status_code=500, detail="Failed to delete account")

        delete_type = "hard deleted" if hard_delete else "soft deleted"
        logger.info(f"Trading account {account_id} {delete_type}")

        return {
            "success": True,
            "account_id": account_id,
            "hard_deleted": hard_delete
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to delete trading account {account_id}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reload", dependencies=[Depends(verify_api_key)])
async def reload_trading_accounts():
    """
    Reload trading accounts from database into active sessions.

    Call this endpoint after:
    - Creating a new trading account
    - Updating account credentials
    - Deleting/deactivating an account

    This will:
    1. Load all active accounts from the database
    2. Re-initialize the SessionOrchestrator with updated accounts
    3. Close connections for removed accounts

    Returns:
        {
            "success": true,
            "accounts_loaded": 3,
            "active_accounts": ["primary", "secondary", "account1"]
        }

    Note: This will briefly interrupt active WebSocket connections and ticker streams.
    """
    try:
        store = get_account_store()

        # Get all active accounts from database
        accounts = await store.list(active_only=True)

        if not accounts:
            raise HTTPException(
                status_code=400,
                detail="No active accounts found in database. At least one active account is required."
            )

        # Reload accounts in ticker_loop
        # Note: This requires implementing reload_accounts() in SessionOrchestrator
        await ticker_loop.reload_accounts(accounts)

        account_ids = [acc["account_id"] for acc in accounts]
        logger.info(f"Reloaded {len(accounts)} trading accounts: {', '.join(account_ids)}")

        return {
            "success": True,
            "accounts_loaded": len(accounts),
            "active_accounts": account_ids
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to reload trading accounts")
        raise HTTPException(status_code=500, detail=f"Failed to reload accounts: {str(e)}")


@router.get("/stats/summary", dependencies=[Depends(verify_api_key)])
async def get_accounts_summary():
    """
    Get summary statistics for trading accounts.

    Returns counts of active, inactive, and total accounts.
    """
    try:
        store = get_account_store()

        total_count = await store.count(active_only=False)
        active_count = await store.count(active_only=True)
        inactive_count = total_count - active_count

        return {
            "total_accounts": total_count,
            "active_accounts": active_count,
            "inactive_accounts": inactive_count
        }

    except Exception as e:
        logger.exception("Failed to get accounts summary")
        raise HTTPException(status_code=500, detail=str(e))
