"""
Task monitoring and exception handling utilities.

This module provides utilities for monitoring asyncio tasks and handling
unhandled exceptions to prevent silent failures in background tasks.
"""
import asyncio
import logging
from typing import Callable, Coroutine, Any, Optional

logger = logging.getLogger(__name__)


class TaskMonitor:
    """
    Monitors asyncio tasks and logs unhandled exceptions.

    This class provides a global exception handler for asyncio tasks to ensure
    that no task fails silently. It also provides utilities to create monitored
    tasks with custom error callbacks.

    Example:
        >>> monitor = TaskMonitor(asyncio.get_running_loop())
        >>> task = monitor.create_monitored_task(
        ...     my_coroutine(),
        ...     task_name="my_background_task",
        ...     on_error=lambda exc: logger.error(f"Task failed: {exc}")
        ... )
    """

    def __init__(self, loop: Optional[asyncio.AbstractEventLoop] = None):
        """
        Initialize the TaskMonitor.

        Args:
            loop: The event loop to monitor. If None, uses the running loop.
        """
        self._loop = loop or asyncio.get_running_loop()
        self._setup_exception_handler()

    def _setup_exception_handler(self):
        """Set up global exception handler for unhandled task exceptions"""
        def exception_handler(loop: asyncio.AbstractEventLoop, context: dict):
            exc = context.get("exception")
            task = context.get("task")
            message = context.get("message", "Unhandled exception in task")

            logger.critical(
                f"Unhandled asyncio exception: {message}",
                exc_info=exc,
                extra={
                    "task": str(task),
                    "task_name": task.get_name() if task else None,
                    "context": context,
                },
            )

            # Optional: Add alerting here (PagerDuty, Slack, etc.)
            # This is where you'd integrate with your alerting system
            # Example:
            # await self._send_alert(message, exc, task)

        self._loop.set_exception_handler(exception_handler)
        logger.info("Global task exception handler registered")

    @staticmethod
    async def monitored_task(
        coro: Coroutine,
        task_name: str,
        on_error: Optional[Callable[[Exception], Any]] = None,
    ) -> None:
        """
        Wrap a coroutine with exception handling.

        This method wraps a coroutine to catch and log all exceptions,
        preventing silent task failures.

        Args:
            coro: The coroutine to execute
            task_name: Human-readable name for logging
            on_error: Optional callback when task fails. Can be sync or async.

        Returns:
            None (exceptions are logged, not raised)
        """
        try:
            await coro
        except asyncio.CancelledError:
            logger.info(f"Task '{task_name}' was cancelled")
            raise  # Re-raise to properly propagate cancellation
        except Exception as exc:
            logger.critical(
                f"Task '{task_name}' failed with exception",
                exc_info=True,
                extra={"task_name": task_name, "error": str(exc)},
            )

            if on_error:
                try:
                    result = on_error(exc)
                    # Handle both sync and async callbacks
                    if asyncio.iscoroutine(result):
                        await result
                except Exception as callback_exc:
                    logger.exception(
                        f"Error callback for '{task_name}' failed: {callback_exc}"
                    )

            # Don't re-raise - let the task die gracefully
            # The exception has been logged and the callback has been called

    def create_monitored_task(
        self,
        coro: Coroutine,
        task_name: str,
        on_error: Optional[Callable[[Exception], Any]] = None,
    ) -> asyncio.Task:
        """
        Create a task with automatic exception monitoring.

        This is the preferred way to create background tasks in the application.
        All exceptions will be logged and the optional error callback will be invoked.

        Args:
            coro: The coroutine to execute
            task_name: Human-readable name for logging and debugging
            on_error: Optional callback when task fails. Can be sync or async.

        Returns:
            asyncio.Task with monitoring wrapper

        Example:
            >>> monitor = TaskMonitor()
            >>> task = monitor.create_monitored_task(
            ...     stream_data(),
            ...     task_name="data_stream",
            ...     on_error=lambda exc: alert_ops_team(exc)
            ... )
        """
        wrapped_coro = self.monitored_task(coro, task_name, on_error)
        task = self._loop.create_task(wrapped_coro)
        task.set_name(task_name)
        return task
