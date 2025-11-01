"""
Alert API Routes
REST endpoints for alert management
"""

import logging
from datetime import datetime
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from ..models.alert import (
    AlertCreate,
    AlertUpdate,
    Alert,
    AlertList,
    AlertActionResponse,
)
from ..services.alert_service import AlertService
from ..database import DatabaseManager

logger = logging.getLogger(__name__)

router = APIRouter()


# Dependency: Get database manager
async def get_db_manager(request: Request) -> DatabaseManager:
    """Get database manager from app state."""
    return request.app.state.db_manager


# Dependency: Get alert service
async def get_alert_service(db_manager: DatabaseManager = Depends(get_db_manager)) -> AlertService:
    """Get or create AlertService instance."""
    return AlertService(db_manager)


# Dependency: Get user_id (for now, hardcoded; later from API key)
async def get_current_user_id(request: Request) -> str:
    """
    Get current user ID.
    TODO: Extract from API key authentication.
    For now, return test user.
    """
    # TODO: Implement API key validation
    # api_key = request.headers.get("Authorization", "").replace("Bearer ", "")
    # user_id = await validate_api_key(api_key)
    return "test_user"


# ============================================================================
# Alert CRUD Endpoints
# ============================================================================

@router.post("", response_model=Alert, status_code=201)
async def create_alert(
    alert_data: AlertCreate,
    user_id: str = Depends(get_current_user_id),
    service: AlertService = Depends(get_alert_service),
):
    """
    Create a new alert.

    Example:
    ```json
    {
      "name": "NIFTY 24000 breakout",
      "alert_type": "price",
      "priority": "high",
      "condition_config": {
        "type": "price",
        "symbol": "NIFTY50",
        "operator": "gt",
        "threshold": 24000
      },
      "notification_channels": ["telegram"]
    }
    ```
    """
    try:
        alert = await service.create_alert(user_id, alert_data)
        logger.info(f"Alert created: {alert.alert_id} by user {user_id}")
        return alert
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to create alert: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("", response_model=AlertList)
async def list_alerts(
    status: Optional[str] = Query(None, description="Filter by status"),
    alert_type: Optional[str] = Query(None, description="Filter by alert type"),
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    limit: int = Query(100, ge=1, le=500, description="Max results"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    user_id: str = Depends(get_current_user_id),
    service: AlertService = Depends(get_alert_service),
):
    """
    List alerts for the current user with optional filters.

    Query parameters:
    - status: Filter by status (active, paused, triggered, expired, deleted)
    - alert_type: Filter by type (price, indicator, position, etc.)
    - symbol: Filter by trading symbol
    - limit: Max results (default: 100, max: 500)
    - offset: Pagination offset (default: 0)
    """
    try:
        alerts = await service.list_alerts(
            user_id=user_id,
            status=status,
            alert_type=alert_type,
            symbol=symbol,
            limit=limit,
            offset=offset,
        )

        return AlertList(
            status="success",
            count=len(alerts),
            alerts=alerts,
            page=offset // limit + 1 if limit > 0 else 1,
            page_size=limit,
        )
    except Exception as e:
        logger.error(f"Failed to list alerts: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{alert_id}", response_model=Alert)
async def get_alert(
    alert_id: UUID,
    user_id: str = Depends(get_current_user_id),
    service: AlertService = Depends(get_alert_service),
):
    """
    Get alert by ID.

    Returns alert details if owned by current user.
    """
    try:
        alert = await service.get_alert(alert_id, user_id)

        if not alert:
            raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")

        return alert
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get alert {alert_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/{alert_id}", response_model=Alert)
async def update_alert(
    alert_id: UUID,
    update_data: AlertUpdate,
    user_id: str = Depends(get_current_user_id),
    service: AlertService = Depends(get_alert_service),
):
    """
    Update an existing alert.

    Only fields provided in the request will be updated.

    Example:
    ```json
    {
      "priority": "critical",
      "status": "paused"
    }
    ```
    """
    try:
        alert = await service.update_alert(alert_id, user_id, update_data)

        if not alert:
            raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")

        logger.info(f"Alert updated: {alert_id} by user {user_id}")
        return alert
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update alert {alert_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/{alert_id}", status_code=200)
async def delete_alert(
    alert_id: UUID,
    user_id: str = Depends(get_current_user_id),
    service: AlertService = Depends(get_alert_service),
):
    """
    Delete an alert (soft delete).

    Sets status to 'deleted'. Alert will no longer be evaluated.
    """
    try:
        deleted = await service.delete_alert(alert_id, user_id)

        if not deleted:
            raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")

        logger.info(f"Alert deleted: {alert_id} by user {user_id}")
        return {
            "status": "success",
            "message": f"Alert {alert_id} deleted",
            "alert_id": str(alert_id),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete alert {alert_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================
# Alert Actions
# ============================================================================

@router.post("/{alert_id}/pause", response_model=AlertActionResponse)
async def pause_alert(
    alert_id: UUID,
    user_id: str = Depends(get_current_user_id),
    service: AlertService = Depends(get_alert_service),
):
    """
    Pause an alert.

    Stops evaluation until resumed. Status changes to 'paused'.
    """
    try:
        success = await service.pause_alert(alert_id, user_id)

        if not success:
            raise HTTPException(
                status_code=404,
                detail=f"Alert {alert_id} not found or not active"
            )

        logger.info(f"Alert paused: {alert_id} by user {user_id}")
        return AlertActionResponse(
            status="success",
            alert_id=alert_id,
            action="pause",
            message=f"Alert {alert_id} paused",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to pause alert {alert_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{alert_id}/resume", response_model=AlertActionResponse)
async def resume_alert(
    alert_id: UUID,
    user_id: str = Depends(get_current_user_id),
    service: AlertService = Depends(get_alert_service),
):
    """
    Resume a paused alert.

    Restarts evaluation. Status changes to 'active'.
    """
    try:
        success = await service.resume_alert(alert_id, user_id)

        if not success:
            raise HTTPException(
                status_code=404,
                detail=f"Alert {alert_id} not found or not paused"
            )

        logger.info(f"Alert resumed: {alert_id} by user {user_id}")
        return AlertActionResponse(
            status="success",
            alert_id=alert_id,
            action="resume",
            message=f"Alert {alert_id} resumed",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to resume alert {alert_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: UUID,
    user_id: str = Depends(get_current_user_id),
):
    """
    Acknowledge an alert event.

    Marks the latest event as acknowledged.
    TODO: Implement event acknowledgement logic.
    """
    # TODO: Implement acknowledgement
    return {
        "status": "success",
        "message": "Acknowledgement feature coming soon",
        "alert_id": str(alert_id),
    }


@router.post("/{alert_id}/snooze")
async def snooze_alert(
    alert_id: UUID,
    duration_seconds: int = Query(3600, ge=60, le=86400, description="Snooze duration (60-86400 seconds)"),
    user_id: str = Depends(get_current_user_id),
):
    """
    Snooze an alert for specified duration.

    Temporarily pauses alert evaluation.
    TODO: Implement snooze logic.
    """
    # TODO: Implement snooze
    return {
        "status": "success",
        "message": "Snooze feature coming soon",
        "alert_id": str(alert_id),
        "duration_seconds": duration_seconds,
    }


@router.post("/{alert_id}/test")
async def test_alert(
    alert_id: UUID,
    user_id: str = Depends(get_current_user_id),
    service: AlertService = Depends(get_alert_service),
    request: Request = None,
):
    """
    Test an alert (dry-run evaluation).

    Evaluates the alert condition without triggering notifications.
    Returns evaluation result with current values.
    """
    try:
        alert = await service.get_alert(alert_id, user_id)

        if not alert:
            raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")

        # Get evaluation worker from app state
        evaluation_worker = getattr(request.app.state, "evaluation_worker", None)

        if not evaluation_worker:
            # Worker not available, create temporary evaluator
            from ..services.evaluator import ConditionEvaluator
            evaluator = ConditionEvaluator()
            result = await evaluator.evaluate(alert.condition_config)
            await evaluator.close()
        else:
            # Use worker's evaluator
            result = await evaluation_worker.evaluate_once(alert_id)

        if not result:
            raise HTTPException(status_code=500, detail="Evaluation failed")

        return {
            "status": "success",
            "message": "Alert evaluated (test mode - no notification sent)",
            "alert": {
                "alert_id": str(alert.alert_id),
                "name": alert.name,
                "type": alert.alert_type,
                "priority": alert.priority,
                "condition": alert.condition_config,
            },
            "evaluation": {
                "matched": result.matched,
                "current_value": result.current_value,
                "threshold": result.threshold,
                "details": result.details,
                "error": result.error,
                "evaluated_at": result.evaluated_at.isoformat(),
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to test alert {alert_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================
# Alert Statistics
# ============================================================================

@router.get("/stats/summary")
async def get_alert_stats(
    user_id: str = Depends(get_current_user_id),
    service: AlertService = Depends(get_alert_service),
):
    """
    Get alert statistics for current user.

    Returns:
    - Total alerts
    - Active/paused/triggered counts
    - Total trigger count
    - Last trigger time
    """
    try:
        stats = await service.get_alert_stats(user_id)
        return {
            "status": "success",
            "user_id": user_id,
            **stats,
        }
    except Exception as e:
        logger.error(f"Failed to get alert stats: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")
