"""
Batch Order Execution

Submit multiple orders atomically with rollback on failure.
"""
from __future__ import annotations

import asyncio
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime, timezone
import uuid

from loguru import logger
from .order_executor import TaskStatus


@dataclass
class BatchOrderRequest:
    """Single order in a batch"""
    exchange: str
    tradingsymbol: str
    transaction_type: str
    quantity: int
    product: str
    order_type: str
    variety: str = "regular"
    price: Optional[float] = None
    trigger_price: Optional[float] = None
    validity: str = "DAY"
    tag: Optional[str] = None


@dataclass
class BatchResult:
    """Result of batch order execution"""
    batch_id: str
    success: bool
    total_orders: int
    succeeded: int
    failed: int
    orders: List[Dict[str, Any]]
    created_at: datetime
    completed_at: Optional[datetime] = None
    error: Optional[str] = None


class BatchOrderExecutor:
    """Executes orders in batches with rollback"""

    # Configuration
    MAX_BATCH_SIZE = 20
    ORDER_TIMEOUT = 30.0  # seconds
    TOTAL_TIMEOUT = 600.0  # 10 minutes

    async def _wait_for_task(self, task, timeout: float) -> Optional[Dict[str, Any]]:
        """Wait for task completion with timeout"""
        deadline = asyncio.get_event_loop().time() + timeout

        while asyncio.get_event_loop().time() < deadline:
            if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.DEAD_LETTER):
                if task.status == TaskStatus.COMPLETED:
                    return task.result
                else:
                    # Task failed
                    error_msg = task.last_error or "Task failed without error message"
                    raise RuntimeError(f"Task {task.task_id} failed: {error_msg}")

            await asyncio.sleep(0.1)  # Poll every 100ms

        raise TimeoutError(f"Task {task.task_id} timed out after {timeout}s")

    async def execute_batch(
        self,
        orders: List[BatchOrderRequest],
        account_id: str,
        executor,  # OrderExecutor
        rollback_on_failure: bool = True
    ) -> BatchResult:
        """
        Execute multiple orders atomically.

        If rollback_on_failure=True, cancels all successfully placed orders
        if any order fails.
        """
        # Validate batch size
        if len(orders) > self.MAX_BATCH_SIZE:
            raise ValueError(f"Batch size {len(orders)} exceeds maximum of {self.MAX_BATCH_SIZE}")

        batch_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc)
        batch_start_time = asyncio.get_event_loop().time()

        logger.info(f"Executing batch {batch_id}: {len(orders)} orders for account {account_id}")

        results = []
        successful_order_ids = []

        # Execute orders sequentially
        for idx, order in enumerate(orders):
            # Check total timeout
            elapsed = asyncio.get_event_loop().time() - batch_start_time
            if elapsed > self.TOTAL_TIMEOUT:
                error_msg = f"Batch timeout exceeded ({self.TOTAL_TIMEOUT}s)"
                logger.error(f"Batch {batch_id}: {error_msg}")

                if rollback_on_failure and successful_order_ids:
                    await self._rollback_orders(successful_order_ids, account_id, executor)
                    return BatchResult(
                        batch_id=batch_id,
                        success=False,
                        total_orders=len(orders),
                        succeeded=0,
                        failed=len(orders),
                        orders=results,
                        created_at=created_at,
                        completed_at=datetime.now(timezone.utc),
                        error=f"{error_msg}. Rolled back {len(successful_order_ids)} orders."
                    )

            try:
                # Submit order via executor
                params = {
                    "exchange": order.exchange,
                    "tradingsymbol": order.tradingsymbol,
                    "transaction_type": order.transaction_type,
                    "quantity": order.quantity,
                    "product": order.product,
                    "order_type": order.order_type,
                    "variety": order.variety,
                    "validity": order.validity,
                }

                if order.price:
                    params["price"] = order.price
                if order.trigger_price:
                    params["trigger_price"] = order.trigger_price
                if order.tag:
                    params["tag"] = f"{order.tag}_batch_{batch_id}_{idx}"

                task = await executor.submit_task("place_order", params, account_id)

                # WAIT for completion with timeout
                result = await self._wait_for_task(task, timeout=self.ORDER_TIMEOUT)

                # Extract order_id from result
                order_id = result.get("order_id") if result else None

                if order_id:
                    successful_order_ids.append(order_id)
                    results.append({
                        "index": idx,
                        "task_id": task.task_id,
                        "status": "completed",
                        "order_id": order_id,
                        "order": order.__dict__
                    })
                    logger.debug(f"Batch {batch_id} order {idx} completed: {order_id}")
                else:
                    raise RuntimeError("Order placed but no order_id returned")

            except (RuntimeError, TimeoutError) as e:
                logger.error(f"Batch {batch_id} order {idx} failed: {e}")
                results.append({
                    "index": idx,
                    "status": "failed",
                    "error": str(e),
                    "order": order.__dict__
                })

                # Rollback if configured
                if rollback_on_failure and successful_order_ids:
                    logger.warning(f"Batch {batch_id} rolling back {len(successful_order_ids)} orders")
                    await self._rollback_orders(successful_order_ids, account_id, executor)

                    return BatchResult(
                        batch_id=batch_id,
                        success=False,
                        total_orders=len(orders),
                        succeeded=0,
                        failed=len(orders),
                        orders=results,
                        created_at=created_at,
                        completed_at=datetime.now(timezone.utc),
                        error=f"Order {idx} failed: {e}. Rolled back {len(successful_order_ids)} orders."
                    )

                # If rollback disabled, continue with remaining orders
                if not rollback_on_failure:
                    continue
                else:
                    # Should have already returned above
                    break

        # All orders succeeded (or completed with rollback disabled)
        completed_at = datetime.now(timezone.utc)
        succeeded = len([r for r in results if r.get("status") == "completed"])

        logger.info(f"Batch {batch_id} completed: {succeeded}/{len(orders)} succeeded")

        return BatchResult(
            batch_id=batch_id,
            success=succeeded == len(orders),
            total_orders=len(orders),
            succeeded=succeeded,
            failed=len(orders) - succeeded,
            orders=results,
            created_at=created_at,
            completed_at=completed_at
        )

    async def _rollback_orders(self, order_ids: List[str], account_id: str, executor) -> None:
        """Cancel orders as part of rollback and wait for completion"""
        rollback_tasks = []

        # Submit all cancel tasks
        for order_id in order_ids:
            try:
                params = {
                    "variety": "regular",
                    "order_id": order_id
                }
                task = await executor.submit_task("cancel_order", params, account_id)
                rollback_tasks.append((order_id, task))
            except Exception as e:
                logger.error(f"Failed to submit rollback for order {order_id}: {e}")

        # Wait for all cancellations to complete
        for order_id, task in rollback_tasks:
            try:
                result = await self._wait_for_task(task, timeout=10.0)
                logger.info(f"Successfully rolled back order {order_id}")
            except TimeoutError:
                logger.error(f"Timeout rolling back order {order_id}")
            except RuntimeError as e:
                logger.error(f"Failed to rollback order {order_id}: {e}")


# Global batch executor
batch_executor = BatchOrderExecutor()
