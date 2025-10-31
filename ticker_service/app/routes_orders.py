"""
Order Management API Routes with Guaranteed Execution
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from loguru import logger

from .api_models import (
    BasketOrderMarginRequest,
    CancelOrderRequest,
    ExitOrderRequest,
    ModifyOrderRequest,
    OrderMarginRequest,
    OrderResponse,
    OrderTaskResponse,
    PlaceOrderRequest,
)
from .generator import ticker_loop
from .order_executor import OrderTask, TaskStatus, get_executor

router = APIRouter(prefix="/orders", tags=["orders"])


def _task_to_response(task: OrderTask) -> OrderTaskResponse:
    """Convert OrderTask to API response"""
    return OrderTaskResponse(
        task_id=task.task_id,
        idempotency_key=task.idempotency_key,
        operation=task.operation,
        status=task.status.value,
        attempts=task.attempts,
        max_attempts=task.max_attempts,
        created_at=task.created_at,
        updated_at=task.updated_at,
        last_error=task.last_error,
        result=task.result,
        account_id=task.account_id,
    )


@router.post("/place", response_model=OrderResponse, status_code=201)
async def place_order(payload: PlaceOrderRequest) -> OrderResponse:
    """
    Place an order with guaranteed execution.

    This endpoint provides:
    - Idempotency: Duplicate requests within 5-minute window return same order
    - Retry logic: Up to 5 retries with exponential backoff
    - Circuit breaker: Protects against API failures
    - Task tracking: Get order status via /orders/tasks/{task_id}
    """
    # Verify account exists
    accounts = ticker_loop.list_accounts()
    if payload.account_id not in accounts:
        raise HTTPException(status_code=400, detail=f"Account '{payload.account_id}' not configured")

    # Get Kite client for account
    try:
        async with ticker_loop.borrow_client(payload.account_id) as client:
            # Submit to order executor
            executor = get_executor()

            params = {
                "exchange": payload.exchange,
                "tradingsymbol": payload.tradingsymbol,
                "transaction_type": payload.transaction_type,
                "quantity": payload.quantity,
                "product": payload.product,
                "order_type": payload.order_type,
                "variety": payload.variety,
                "validity": payload.validity,
            }

            # Add optional params
            if payload.price is not None:
                params["price"] = payload.price
            if payload.trigger_price is not None:
                params["trigger_price"] = payload.trigger_price
            if payload.disclosed_quantity is not None:
                params["disclosed_quantity"] = payload.disclosed_quantity
            if payload.squareoff is not None:
                params["squareoff"] = payload.squareoff
            if payload.stoploss is not None:
                params["stoploss"] = payload.stoploss
            if payload.trailing_stoploss is not None:
                params["trailing_stoploss"] = payload.trailing_stoploss
            if payload.tag is not None:
                params["tag"] = payload.tag

            task = await executor.submit_task("place_order", params, payload.account_id)

            # If task already completed (idempotency), return result
            if task.status == TaskStatus.COMPLETED and task.result:
                return OrderResponse(
                    order_id=task.result.get("order_id", ""),
                    task_id=task.task_id,
                )

            # Otherwise return task ID for tracking
            return OrderResponse(
                order_id="",  # Will be populated once completed
                task_id=task.task_id,
            )

    except Exception as exc:
        logger.exception(f"Failed to place order for account {payload.account_id}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.put("/modify", response_model=OrderResponse)
async def modify_order(payload: ModifyOrderRequest) -> OrderResponse:
    """
    Modify a pending order with guaranteed execution.
    """
    accounts = ticker_loop.list_accounts()
    if payload.account_id not in accounts:
        raise HTTPException(status_code=400, detail=f"Account '{payload.account_id}' not configured")

    try:
        async with ticker_loop.borrow_client(payload.account_id) as client:
            executor = get_executor()

            params = {
                "variety": payload.variety,
                "order_id": payload.order_id,
            }

            if payload.quantity is not None:
                params["quantity"] = payload.quantity
            if payload.price is not None:
                params["price"] = payload.price
            if payload.order_type is not None:
                params["order_type"] = payload.order_type
            if payload.trigger_price is not None:
                params["trigger_price"] = payload.trigger_price
            if payload.validity is not None:
                params["validity"] = payload.validity
            if payload.disclosed_quantity is not None:
                params["disclosed_quantity"] = payload.disclosed_quantity
            if payload.parent_order_id is not None:
                params["parent_order_id"] = payload.parent_order_id

            task = await executor.submit_task("modify_order", params, payload.account_id)

            if task.status == TaskStatus.COMPLETED and task.result:
                return OrderResponse(
                    order_id=task.result.get("order_id", payload.order_id),
                    task_id=task.task_id,
                )

            return OrderResponse(
                order_id=payload.order_id,
                task_id=task.task_id,
            )

    except Exception as exc:
        logger.exception(f"Failed to modify order for account {payload.account_id}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.delete("/cancel", response_model=OrderResponse)
async def cancel_order(payload: CancelOrderRequest) -> OrderResponse:
    """
    Cancel a pending order with guaranteed execution.
    """
    accounts = ticker_loop.list_accounts()
    if payload.account_id not in accounts:
        raise HTTPException(status_code=400, detail=f"Account '{payload.account_id}' not configured")

    try:
        async with ticker_loop.borrow_client(payload.account_id) as client:
            executor = get_executor()

            params = {
                "variety": payload.variety,
                "order_id": payload.order_id,
            }

            if payload.parent_order_id is not None:
                params["parent_order_id"] = payload.parent_order_id

            task = await executor.submit_task("cancel_order", params, payload.account_id)

            if task.status == TaskStatus.COMPLETED and task.result:
                return OrderResponse(
                    order_id=task.result.get("order_id", payload.order_id),
                    task_id=task.task_id,
                )

            return OrderResponse(
                order_id=payload.order_id,
                task_id=task.task_id,
            )

    except Exception as exc:
        logger.exception(f"Failed to cancel order for account {payload.account_id}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/exit", response_model=OrderResponse)
async def exit_order(payload: ExitOrderRequest) -> OrderResponse:
    """
    Exit a cover order or bracket order with guaranteed execution.
    """
    accounts = ticker_loop.list_accounts()
    if payload.account_id not in accounts:
        raise HTTPException(status_code=400, detail=f"Account '{payload.account_id}' not configured")

    try:
        async with ticker_loop.borrow_client(payload.account_id) as client:
            executor = get_executor()

            params = {
                "variety": payload.variety,
                "order_id": payload.order_id,
            }
            if payload.parent_order_id is not None:
                params["parent_order_id"] = payload.parent_order_id

            task = await executor.submit_task("exit_order", params, payload.account_id)

            # If task already completed (idempotency), return result
            if task.status == TaskStatus.COMPLETED and task.result:
                return OrderResponse(
                    order_id=task.result.get("order_id", ""),
                    task_id=task.task_id,
                )

            # Otherwise return task ID for tracking
            return OrderResponse(
                order_id="",  # Will be populated once completed
                task_id=task.task_id,
            )

    except Exception as exc:
        logger.exception(f"Failed to exit order for account {payload.account_id}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/", response_model=List[Dict[str, Any]])
async def list_orders(account_id: str = "primary") -> List[Dict[str, Any]]:
    """
    Get list of all orders for the day.
    """
    accounts = ticker_loop.list_accounts()
    if account_id not in accounts:
        raise HTTPException(status_code=400, detail=f"Account '{account_id}' not configured")

    try:
        async with ticker_loop.borrow_client(account_id) as client:
            return await client.orders()
    except Exception as exc:
        logger.exception(f"Failed to fetch orders for account {account_id}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{order_id}/history", response_model=List[Dict[str, Any]])
async def get_order_history(order_id: str, account_id: str = "primary") -> List[Dict[str, Any]]:
    """
    Get history/trail of a specific order.
    """
    accounts = ticker_loop.list_accounts()
    if account_id not in accounts:
        raise HTTPException(status_code=400, detail=f"Account '{account_id}' not configured")

    try:
        async with ticker_loop.borrow_client(account_id) as client:
            return await client.order_history(order_id)
    except Exception as exc:
        logger.exception(f"Failed to fetch order history for {order_id}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{order_id}/trades", response_model=List[Dict[str, Any]])
async def get_order_trades(order_id: str, account_id: str = "primary") -> List[Dict[str, Any]]:
    """
    Get list of trades executed for an order.
    """
    accounts = ticker_loop.list_accounts()
    if account_id not in accounts:
        raise HTTPException(status_code=400, detail=f"Account '{account_id}' not configured")

    try:
        async with ticker_loop.borrow_client(account_id) as client:
            return await client.order_trades(order_id)
    except Exception as exc:
        logger.exception(f"Failed to fetch trades for order {order_id}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/trades/all", response_model=List[Dict[str, Any]])
async def list_trades(account_id: str = "primary") -> List[Dict[str, Any]]:
    """
    Get all trades for the day.
    """
    accounts = ticker_loop.list_accounts()
    if account_id not in accounts:
        raise HTTPException(status_code=400, detail=f"Account '{account_id}' not configured")

    try:
        async with ticker_loop.borrow_client(account_id) as client:
            return await client.trades()
    except Exception as exc:
        logger.exception(f"Failed to fetch trades for account {account_id}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/margins", response_model=List[Dict[str, Any]])
async def calculate_order_margins(payload: BasketOrderMarginRequest) -> List[Dict[str, Any]]:
    """
    Calculate margins for a list of orders.
    """
    accounts = ticker_loop.list_accounts()
    if payload.account_id not in accounts:
        raise HTTPException(status_code=400, detail=f"Account '{payload.account_id}' not configured")

    try:
        async with ticker_loop.borrow_client(payload.account_id) as client:
            orders = [order.dict(exclude_none=True) for order in payload.orders]
            return await client.order_margins(orders)
    except Exception as exc:
        logger.exception(f"Failed to calculate order margins for account {payload.account_id}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/margins/basket", response_model=Dict[str, Any])
async def calculate_basket_margins(payload: BasketOrderMarginRequest) -> Dict[str, Any]:
    """
    Calculate total margins required for a basket of orders.
    """
    accounts = ticker_loop.list_accounts()
    if payload.account_id not in accounts:
        raise HTTPException(status_code=400, detail=f"Account '{payload.account_id}' not configured")

    try:
        async with ticker_loop.borrow_client(payload.account_id) as client:
            orders = [order.dict(exclude_none=True) for order in payload.orders]
            return await client.basket_order_margins(orders, payload.consider_positions)
    except Exception as exc:
        logger.exception(f"Failed to calculate basket margins for account {payload.account_id}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/tasks/{task_id}", response_model=OrderTaskResponse)
async def get_order_task(task_id: str) -> OrderTaskResponse:
    """
    Get status of an order task.

    Use this to check the status of orders submitted with guaranteed execution.
    """
    executor = get_executor()
    task = executor.get_task(task_id)

    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    return _task_to_response(task)


@router.get("/tasks", response_model=List[OrderTaskResponse])
async def list_order_tasks(status: Optional[str] = None) -> List[OrderTaskResponse]:
    """
    List all order tasks, optionally filtered by status.

    Valid statuses: pending, running, completed, failed, retrying, dead_letter
    """
    executor = get_executor()

    if status:
        try:
            task_status = TaskStatus(status.lower())
            tasks = executor.get_all_tasks(task_status)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status. Must be one of: {', '.join(s.value for s in TaskStatus)}"
            )
    else:
        tasks = executor.get_all_tasks()

    return [_task_to_response(task) for task in tasks]
