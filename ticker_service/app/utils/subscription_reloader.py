"""
Subscription reloader with rate limiting and deduplication.

This module provides utilities for managing subscription reload requests
with rate limiting, deduplication, and debouncing to prevent resource exhaustion.
"""
import asyncio
import logging
import time
from typing import Callable, Coroutine, Optional

logger = logging.getLogger(__name__)


class SubscriptionReloader:
    """
    Manages subscription reload requests with:
    - Rate limiting (max 1 reload at a time)
    - Deduplication (coalesce multiple requests)
    - Debouncing (wait for burst of requests to complete)

    This prevents resource exhaustion from rapid API calls that trigger
    subscription reloads.

    Example:
        >>> async def perform_reload():
        ...     # Actual reload logic
        ...     await reload_from_database()
        >>>
        >>> reloader = SubscriptionReloader(
        ...     reload_fn=perform_reload,
        ...     debounce_seconds=1.0,
        ...     max_reload_frequency_seconds=5.0
        ... )
        >>> await reloader.start()
        >>>
        >>> # Multiple rapid triggers will be coalesced
        >>> reloader.trigger_reload()
        >>> reloader.trigger_reload()
        >>> reloader.trigger_reload()
        >>> # Only 1 reload will execute
    """

    def __init__(
        self,
        reload_fn: Callable[[], Coroutine],
        debounce_seconds: float = 1.0,
        max_reload_frequency_seconds: float = 5.0,
    ):
        """
        Initialize the SubscriptionReloader.

        Args:
            reload_fn: Async function to call when reload triggered
            debounce_seconds: Wait this long after last trigger before reloading
            max_reload_frequency_seconds: Minimum time between reloads
        """
        self._reload_fn = reload_fn
        self._debounce_seconds = debounce_seconds
        self._max_reload_frequency = max_reload_frequency_seconds

        self._reload_semaphore = asyncio.Semaphore(1)  # Only 1 reload at a time
        self._reload_pending = asyncio.Event()
        self._reloader_task: Optional[asyncio.Task] = None
        self._running = False

        self._last_reload_time = 0.0
        self._pending_count = 0

    async def start(self):
        """Start the background reloader loop"""
        if self._running:
            logger.warning("SubscriptionReloader already running")
            return

        self._running = True
        self._reloader_task = asyncio.create_task(self._reloader_loop())
        logger.info("SubscriptionReloader started")

    async def stop(self):
        """Stop the background reloader loop"""
        self._running = False
        self._reload_pending.set()  # Wake up loop

        if self._reloader_task:
            try:
                await self._reloader_task
            except asyncio.CancelledError:
                pass

        logger.info("SubscriptionReloader stopped")

    def trigger_reload(self) -> None:
        """
        Request a subscription reload (non-blocking).

        Multiple rapid triggers will be coalesced into a single reload.
        This method returns immediately.

        Example:
            >>> reloader.trigger_reload()  # Returns immediately
            >>> # Reload happens in background
        """
        self._pending_count += 1
        self._reload_pending.set()
        logger.debug(f"Reload triggered (pending count: {self._pending_count})")

    async def _reloader_loop(self):
        """
        Background loop that processes reload requests.

        This loop:
        1. Waits for reload requests
        2. Debounces (waits for burst to complete)
        3. Enforces rate limiting
        4. Executes reload with semaphore protection
        """
        while self._running:
            try:
                # Wait for reload request
                await self._reload_pending.wait()
                self._reload_pending.clear()

                if not self._running:
                    break

                # Debounce: Wait for burst of requests to complete
                await asyncio.sleep(self._debounce_seconds)

                # Check if minimum reload frequency has elapsed
                elapsed_since_last = time.time() - self._last_reload_time
                if elapsed_since_last < self._max_reload_frequency:
                    wait_time = self._max_reload_frequency - elapsed_since_last
                    logger.debug(f"Rate limiting: waiting {wait_time:.1f}s before reload")
                    await asyncio.sleep(wait_time)

                # Acquire semaphore (ensures only 1 reload at a time)
                async with self._reload_semaphore:
                    pending_count = self._pending_count
                    self._pending_count = 0

                    logger.info(f"Executing subscription reload (coalesced {pending_count} requests)")
                    start_time = time.time()

                    try:
                        await self._reload_fn()
                        duration = time.time() - start_time
                        logger.info(f"Subscription reload completed in {duration:.2f}s")
                    except Exception as exc:
                        logger.exception(f"Subscription reload failed: {exc}")

                    self._last_reload_time = time.time()

            except asyncio.CancelledError:
                logger.info("SubscriptionReloader loop cancelled")
                break
            except Exception as exc:
                logger.exception(f"Unexpected error in reloader loop: {exc}")
                await asyncio.sleep(1.0)  # Prevent tight loop on error
