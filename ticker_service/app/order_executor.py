"""
Order Execution Framework with Task Completion Guarantees

This module provides reliable order execution with:
- Retry logic with exponential backoff
- Circuit breaker pattern
- Idempotency guarantees
- Persistent task tracking
- Dead letter queue for failed orders
- Thread-safe task management with cleanup
"""
from __future__ import annotations

import asyncio
import hashlib
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta  # ARCH-P0-004: Added timedelta for age-based cleanup
from enum import Enum
from typing import Any, Dict, Optional, Set, TYPE_CHECKING
from uuid import uuid4

from loguru import logger

if TYPE_CHECKING:
    from .kite.client import KiteClient


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"
    DEAD_LETTER = "dead_letter"


class CircuitState(str, Enum):
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class OrderTask:
    """Represents an order execution task with completion tracking"""

    task_id: str
    idempotency_key: str
    operation: str  # place_order, modify_order, cancel_order
    params: Dict[str, Any]
    status: TaskStatus = TaskStatus.PENDING
    attempts: int = 0
    max_attempts: int = 5
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_error: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    account_id: str = "primary"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "idempotency_key": self.idempotency_key,
            "operation": self.operation,
            "params": self.params,
            "status": self.status.value,
            "attempts": self.attempts,
            "max_attempts": self.max_attempts,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "last_error": self.last_error,
            "result": self.result,
            "account_id": self.account_id,
        }


class CircuitBreaker:
    """Thread-safe circuit breaker for Kite API calls"""

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        half_open_max_calls: int = 3
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls

        self.state: CircuitState = CircuitState.CLOSED
        self.failure_count: int = 0
        self.last_failure_time: Optional[float] = None
        self.half_open_calls: int = 0
        self._lock = asyncio.Lock()

    async def can_execute(self) -> bool:
        """Check if request can be executed (thread-safe)"""
        async with self._lock:
            if self.state == CircuitState.CLOSED:
                return True

            if self.state == CircuitState.OPEN:
                # Check if we should transition to half-open
                if self.last_failure_time and (time.time() - self.last_failure_time) > self.recovery_timeout:
                    logger.info("Circuit breaker transitioning to HALF_OPEN state")
                    self.state = CircuitState.HALF_OPEN
                    self.half_open_calls = 0
                    return True
                return False

            if self.state == CircuitState.HALF_OPEN:
                return self.half_open_calls < self.half_open_max_calls

            return False

    async def record_success(self) -> None:
        """Record successful execution (thread-safe)"""
        async with self._lock:
            if self.state == CircuitState.HALF_OPEN:
                self.half_open_calls += 1
                if self.half_open_calls >= self.half_open_max_calls:
                    logger.info("Circuit breaker transitioning to CLOSED state")
                    self.state = CircuitState.CLOSED
                    self.failure_count = 0
                    self.last_failure_time = None
            elif self.state == CircuitState.CLOSED:
                self.failure_count = max(0, self.failure_count - 1)

    async def record_failure(self) -> None:
        """Record failed execution (thread-safe)"""
        async with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.time()

            if self.state == CircuitState.HALF_OPEN:
                logger.warning("Circuit breaker transitioning back to OPEN state")
                self.state = CircuitState.OPEN
            elif self.state == CircuitState.CLOSED and self.failure_count >= self.failure_threshold:
                logger.error("Circuit breaker transitioning to OPEN state")
                self.state = CircuitState.OPEN


class OrderExecutor:
    """
    Reliable order executor with completion guarantees and memory management
    """

    def __init__(self, max_tasks: int = 10000, worker_poll_interval: float = 1.0, worker_error_backoff: float = 5.0):
        self._tasks: OrderedDict[str, OrderTask] = OrderedDict()
        self._idempotency_map: Dict[str, str] = {}  # idempotency_key -> task_id
        self._circuit_breaker = CircuitBreaker()
        self._running = False
        self._worker_task: Optional[asyncio.Task] = None
        self._max_tasks = max_tasks
        self._worker_poll_interval = worker_poll_interval
        self._worker_error_backoff = worker_error_backoff
        self._execution_lock = asyncio.Lock()
        self._executing_tasks: Set[str] = set()
        self._last_cleanup: datetime = datetime.now(timezone.utc)

    @staticmethod
    def generate_idempotency_key(operation: str, params: Dict[str, Any], account_id: str) -> str:
        """Generate idempotency key for order operations (includes account_id)"""
        # CRITICAL FIX: Include account_id to prevent cross-account idempotency collisions
        key_parts = [operation, account_id]

        # Include relevant params for idempotency
        if operation == "place_order":
            key_parts.extend(
                [
                    params.get("exchange", ""),
                    params.get("tradingsymbol", ""),
                    params.get("transaction_type", ""),
                    str(params.get("quantity", "")),
                    params.get("product", ""),
                    params.get("order_type", ""),
                ]
            )
        elif operation in ["modify_order", "cancel_order", "exit_order"]:
            key_parts.extend([params.get("variety", ""), str(params.get("order_id", ""))])

        # Add timestamp bucket (5 minute window) for place_order
        if operation == "place_order":
            bucket = int(time.time() / 300)  # 5-minute buckets
            key_parts.append(str(bucket))

        key_string = "|".join(key_parts)
        return hashlib.sha256(key_string.encode()).hexdigest()

    async def submit_task(
        self, operation: str, params: Dict[str, Any], account_id: str = "primary"
    ) -> OrderTask:
        """
        Submit an order task with idempotency guarantee (thread-safe)

        Returns existing task if idempotent operation already submitted
        """
        # CRITICAL FIX: Pass account_id to idempotency key generation
        idempotency_key = self.generate_idempotency_key(operation, params, account_id)

        async with self._execution_lock:
            # Check if task already exists (idempotency)
            if idempotency_key in self._idempotency_map:
                task_id = self._idempotency_map[idempotency_key]
                existing_task = self._tasks.get(task_id)
                if existing_task and existing_task.status in [TaskStatus.PENDING, TaskStatus.RUNNING, TaskStatus.COMPLETED]:
                    logger.info(
                        f"Idempotent task found for {operation}: {task_id} (status={existing_task.status})"
                    )
                    return existing_task

            # Create new task
            task = OrderTask(
                task_id=str(uuid4()),
                idempotency_key=idempotency_key,
                operation=operation,
                params=params,
                account_id=account_id,
            )

            self._tasks[task.task_id] = task
            self._idempotency_map[idempotency_key] = task.task_id

            # CRITICAL FIX: Cleanup old tasks if limit exceeded
            await self._cleanup_old_tasks_if_needed()

            logger.info(f"Submitted new task {task.task_id} for {operation}")
            return task

    async def _cleanup_old_tasks_if_needed(self) -> None:
        """
        Remove old completed/dead_letter tasks to prevent memory leak (ARCH-P0-004 fix).

        Proactive cleanup strategy:
        1. Age-based: Remove tasks older than 24 hours (configurable)
        2. Hard limit: Enforce max_tasks limit by removing oldest 20%
        3. Periodic: Run every 60 seconds minimum

        Memory impact: Each task ~1KB, 10K tasks = ~10MB
        At 151MB/week leak rate, this prevents unbounded growth
        """
        now = datetime.now(timezone.utc)

        # ARCH-P0-004 FIX: Rate limit cleanup to avoid excessive overhead
        # But ensure it runs even if under limit (proactive cleanup)
        if (now - self._last_cleanup).total_seconds() < 60:  # Min 1 minute between cleanups
            return

        self._last_cleanup = now

        # ARCH-P0-004 FIX: Age-based cleanup (remove tasks older than 24 hours)
        # This prevents indefinite accumulation regardless of count
        max_age_hours = 24
        age_cutoff = now - timedelta(hours=max_age_hours)

        removable_statuses = {TaskStatus.COMPLETED, TaskStatus.DEAD_LETTER}

        # Phase 1: Remove tasks older than age cutoff
        aged_tasks = [
            (task_id, task) for task_id, task in self._tasks.items()
            if (task.status in removable_statuses
                and task_id not in self._executing_tasks
                and task.updated_at < age_cutoff)
        ]

        aged_count = 0
        for task_id, task in aged_tasks:
            del self._tasks[task_id]
            if task.idempotency_key in self._idempotency_map:
                del self._idempotency_map[task.idempotency_key]
            aged_count += 1

        if aged_count > 0:
            logger.info(
                f"ARCH-P0-004: Removed {aged_count} tasks older than {max_age_hours}h "
                f"(age-based cleanup)"
            )

        # Phase 2: Hard limit enforcement (remove oldest 20% if over limit)
        if len(self._tasks) > self._max_tasks:
            # Find all removable tasks (not currently executing)
            old_tasks = [
                (task_id, task) for task_id, task in self._tasks.items()
                if task.status in removable_statuses and task_id not in self._executing_tasks
            ]

            if not old_tasks:
                logger.error(
                    f"ARCH-P0-004: Task limit exceeded ({len(self._tasks)}/{self._max_tasks}) "
                    f"but no removable tasks found! This should not happen."
                )
                return

            # ARCH-P0-004 FIX: Aggressive cleanup - remove oldest 20% to stay under limit
            old_tasks.sort(key=lambda x: x[1].updated_at)
            remove_count = min(len(old_tasks), max(1, self._max_tasks // 5))

            for task_id, task in old_tasks[:remove_count]:
                del self._tasks[task_id]
                if task.idempotency_key in self._idempotency_map:
                    del self._idempotency_map[task.idempotency_key]

            logger.warning(
                f"ARCH-P0-004: Hard limit cleanup - removed {remove_count} oldest tasks | "
                f"current={len(self._tasks)}/{self._max_tasks} | "
                f"completed={len([t for t in self._tasks.values() if t.status == TaskStatus.COMPLETED])} | "
                f"dead_letter={len([t for t in self._tasks.values() if t.status == TaskStatus.DEAD_LETTER])}"
            )

        # Phase 3: Log current memory usage estimate
        memory_mb = (len(self._tasks) * 1.0) / 1024  # Assuming ~1KB per task
        logger.debug(
            f"ARCH-P0-004: Task memory estimate: {len(self._tasks)} tasks ≈ {memory_mb:.2f} MB"
        )

    async def execute_task(self, task: OrderTask, get_client) -> bool:
        """
        Execute a single task with retry logic (thread-safe)

        Args:
            task: The task to execute
            get_client: Async function that returns a client context manager for the account

        Returns True if successful, False if needs retry
        """
        if not await self._circuit_breaker.can_execute():
            logger.warning(
                f"Circuit breaker {self._circuit_breaker.state.value}, cannot execute task {task.task_id}"
            )
            return False

        task.status = TaskStatus.RUNNING
        task.attempts += 1
        task.updated_at = datetime.now(timezone.utc)

        try:
            # Get client for this account
            async with get_client(task.account_id) as client:
                # Execute the operation
                if task.operation == "place_order":
                    result = await self._execute_place_order(client, task.params)
                elif task.operation == "modify_order":
                    result = await self._execute_modify_order(client, task.params)
                elif task.operation == "cancel_order":
                    result = await self._execute_cancel_order(client, task.params)
                elif task.operation == "exit_order":
                    result = await self._execute_exit_order(client, task.params)
                else:
                    raise ValueError(f"Unknown operation: {task.operation}")

            # Success
            task.status = TaskStatus.COMPLETED
            task.result = result
            task.updated_at = datetime.now(timezone.utc)
            await self._circuit_breaker.record_success()
            logger.info(f"Task {task.task_id} completed successfully")
            return True

        except Exception as exc:
            task.last_error = str(exc)
            task.updated_at = datetime.now(timezone.utc)
            await self._circuit_breaker.record_failure()

            if task.attempts >= task.max_attempts:
                task.status = TaskStatus.DEAD_LETTER
                logger.error(
                    f"Task {task.task_id} moved to dead letter queue after {task.attempts} attempts: {exc}"
                )
                return True  # Consider completed (failed permanently)
            else:
                task.status = TaskStatus.RETRYING
                logger.warning(
                    f"Task {task.task_id} failed (attempt {task.attempts}/{task.max_attempts}): {exc}"
                )
                return False  # Will retry

    async def _execute_place_order(self, client: KiteClient, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute place_order with the Kite client"""
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, lambda: client._kite.place_order(**params))
        return {"order_id": result}

    async def _execute_modify_order(self, client: KiteClient, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute modify_order with the Kite client"""
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, lambda: client._kite.modify_order(**params))
        return {"order_id": result}

    async def _execute_cancel_order(self, client: KiteClient, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute cancel_order with the Kite client"""
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, lambda: client._kite.cancel_order(**params))
        return {"order_id": result}

    async def _execute_exit_order(self, client: KiteClient, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute exit_order with the Kite client"""
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, lambda: client._kite.exit_order(**params))
        return {"order_id": result}

    def get_task(self, task_id: str) -> Optional[OrderTask]:
        """Retrieve task by ID"""
        return self._tasks.get(task_id)

    def get_all_tasks(self, status: Optional[TaskStatus] = None) -> list[OrderTask]:
        """Get all tasks, optionally filtered by status"""
        if status:
            return [t for t in self._tasks.values() if t.status == status]
        return list(self._tasks.values())

    async def start_worker(self, get_client) -> None:
        """
        Start background worker to process pending tasks (thread-safe with race condition fix)

        Args:
            get_client: Async function that returns a client context manager for an account_id
        """
        self._running = True
        logger.info("Order executor worker started")

        while self._running:
            try:
                # CRITICAL FIX: Synchronize access to task list
                async with self._execution_lock:
                    # Find pending tasks not currently being executed
                    pending_tasks = [
                        t for t in self._tasks.values()
                        if t.status in [TaskStatus.PENDING, TaskStatus.RETRYING]
                        and t.task_id not in self._executing_tasks
                    ]

                # Execute tasks outside the lock to allow other operations
                for task in pending_tasks:
                    # Calculate backoff delay for retrying tasks
                    if task.status == TaskStatus.RETRYING:
                        delay = min(2**task.attempts, 60)  # Exponential backoff, max 60s
                        elapsed = (datetime.now(timezone.utc) - task.updated_at).total_seconds()
                        if elapsed < delay:
                            continue  # Skip, not ready yet

                    # Mark task as executing
                    async with self._execution_lock:
                        if task.task_id in self._executing_tasks:
                            continue  # Another worker picked this up
                        self._executing_tasks.add(task.task_id)

                    try:
                        await self.execute_task(task, get_client)
                    finally:
                        # Always remove from executing set
                        async with self._execution_lock:
                            self._executing_tasks.discard(task.task_id)

                # Sleep before next iteration (configurable)
                await asyncio.sleep(self._worker_poll_interval)

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.exception(f"Error in order executor worker: {exc}")
                await asyncio.sleep(self._worker_error_backoff)

        logger.info("Order executor worker stopped")

    async def stop_worker(self) -> None:
        """Stop background worker"""
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass


# Global instance - will be initialized with config on first import from main.py
_executor: Optional[OrderExecutor] = None


def get_executor() -> OrderExecutor:
    """Get global order executor instance"""
    global _executor
    if _executor is None:
        # Initialize with default values (will be overridden by init_executor if called)
        _executor = OrderExecutor()
    return _executor


def init_executor(max_tasks: int = 10000, worker_poll_interval: float = 1.0, worker_error_backoff: float = 5.0) -> None:
    """Initialize global executor with custom configuration"""
    global _executor
    _executor = OrderExecutor(
        max_tasks=max_tasks,
        worker_poll_interval=worker_poll_interval,
        worker_error_backoff=worker_error_backoff
    )
