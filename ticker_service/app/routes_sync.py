"""
Trade Sync API Routes

Manual trigger endpoints for trade data synchronization.
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Dict, Any, Optional
from loguru import logger

from .trade_sync import TradeSyncService, SyncResult

router = APIRouter(prefix="/sync", tags=["sync"])

# Global reference to sync service (will be set during startup)
_sync_service: Optional[TradeSyncService] = None


def set_sync_service(service: TradeSyncService) -> None:
    """Set the global sync service instance"""
    global _sync_service
    _sync_service = service


def get_sync_service() -> TradeSyncService:
    """Get the sync service dependency"""
    if _sync_service is None:
        raise HTTPException(
            status_code=503,
            detail="Trade sync service not available"
        )
    return _sync_service


class SyncResponse(BaseModel):
    """Response model for sync operations"""
    account_id: str
    trades_synced: int
    orders_synced: int
    positions_synced: int
    duration_ms: int
    success: bool
    error: Optional[str] = None


@router.post("/accounts/{account_id}", response_model=SyncResponse)
async def sync_account(
    account_id: str,
    service: TradeSyncService = Depends(get_sync_service)
) -> SyncResponse:
    """
    Manually trigger sync for a specific account.

    This fetches the latest trades, orders, and positions from Kite API
    and stores them in the database.

    Args:
        account_id: Account ID to sync (e.g., "primary")

    Returns:
        Sync result with counts and duration
    """
    logger.info(f"Manual sync triggered for account: {account_id}")

    try:
        result = await service.sync_account(account_id)

        return SyncResponse(
            account_id=result.account_id,
            trades_synced=result.trades_synced,
            orders_synced=result.orders_synced,
            positions_synced=result.positions_synced,
            duration_ms=result.duration_ms,
            success=result.success,
            error=result.error
        )
    except Exception as e:
        logger.exception(f"Manual sync failed for account {account_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/all", response_model=Dict[str, Any])
async def sync_all_accounts(
    service: TradeSyncService = Depends(get_sync_service)
) -> Dict[str, Any]:
    """
    Manually trigger sync for all configured accounts.

    Returns:
        Summary of sync results for all accounts
    """
    logger.info("Manual sync triggered for all accounts")

    try:
        results = await service.sync_all_accounts()

        return {
            "total_accounts": len(results),
            "successful": sum(1 for r in results if r.success),
            "failed": sum(1 for r in results if not r.success),
            "total_trades": sum(r.trades_synced for r in results),
            "total_orders": sum(r.orders_synced for r in results),
            "total_positions": sum(r.positions_synced for r in results),
            "results": [
                SyncResponse(
                    account_id=r.account_id,
                    trades_synced=r.trades_synced,
                    orders_synced=r.orders_synced,
                    positions_synced=r.positions_synced,
                    duration_ms=r.duration_ms,
                    success=r.success,
                    error=r.error
                )
                for r in results
            ]
        }
    except Exception as e:
        logger.exception(f"Manual sync failed for all accounts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def get_sync_status(
    service: TradeSyncService = Depends(get_sync_service)
) -> Dict[str, Any]:
    """
    Get the status of the trade sync service.

    Returns:
        Service status and configuration
    """
    return {
        "running": service._running,
        "sync_interval_seconds": service.sync_interval,
        "configured_accounts": service.orchestrator.list_accounts()
    }
