"""
Order Cleanup Worker

Background worker that listens to position change events and automatically
cleans up orphaned SL/Target orders based on strategy settings.

Usage:
    worker = OrderCleanupWorker(dm, ticker_url, position_tracker)
    await worker.start()
"""

from __future__ import annotations

import logging
import httpx
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
from dataclasses import dataclass

from ..database import DataManager
from ..services.position_tracker import PositionTracker, PositionEvent, PositionEventType

logger = logging.getLogger(__name__)


@dataclass
class StrategySettings:
    """Strategy cleanup settings."""
    strategy_id: int
    auto_cleanup_enabled: bool
    cleanup_sl_on_exit: bool
    cleanup_target_on_exit: bool
    allow_orphaned_orders: bool
    notify_on_orphan_detection: bool


@dataclass
class CleanupAction:
    """Record of a cleanup action."""
    order_id: str
    account_id: str
    tradingsymbol: str
    exchange: str
    order_type: str
    cleanup_reason: str
    cleanup_action: str  # 'cancelled', 'skipped'
    was_auto: bool
    strategy_id: Optional[int]
    position_quantity_before: int
    position_quantity_after: int
    metadata: Dict[str, Any]


class OrderCleanupWorker:
    """
    Automatically cleans up orphaned SL/Target orders when positions close.

    Listens to PositionTracker events and cancels related orders via ticker_service
    based on strategy settings.
    """

    def __init__(
        self,
        dm: DataManager,
        ticker_url: str,
        position_tracker: PositionTracker
    ):
        """
        Initialize OrderCleanupWorker.

        Args:
            dm: DataManager for database operations
            ticker_url: Base URL for ticker_service (e.g., http://localhost:8080)
            position_tracker: PositionTracker to listen to
        """
        self._dm = dm
        self._ticker_url = ticker_url.rstrip("/")
        self._http = httpx.AsyncClient(base_url=self._ticker_url, timeout=30.0)
        self._tracker = position_tracker

        # Register as listener for position closed/reduced events
        self._tracker.register_listener(
            self.on_position_event,
            event_filter=lambda e: e.event_type in [
                PositionEventType.POSITION_CLOSED,
                PositionEventType.POSITION_REDUCED
            ]
        )

        logger.info("OrderCleanupWorker initialized")

    async def close(self):
        """Close HTTP client."""
        await self._http.aclose()

    async def on_position_event(self, event: PositionEvent):
        """
        Handle position change event.

        Args:
            event: PositionEvent (CLOSED or REDUCED)
        """
        logger.info(
            f"Processing cleanup for {event.event_type}: "
            f"{event.tradingsymbol} {event.exchange} {event.product} "
            f"(qty: {event.quantity_before} → {event.quantity_after})"
        )

        try:
            # Find related orders
            orders = await self._find_related_orders(
                account_id=event.account_id,
                tradingsymbol=event.tradingsymbol,
                exchange=event.exchange,
                product=event.product
            )

            if not orders:
                logger.debug(f"No orders found for {event.tradingsymbol}")
                return

            # Filter for SL/Target orders only
            sl_target_orders = [
                o for o in orders
                if o.get("order_type") in ["SL", "SL-M"]
                and o.get("status") in ["PENDING", "OPEN", "TRIGGER PENDING"]
            ]

            if not sl_target_orders:
                logger.debug(f"No active SL/Target orders for {event.tradingsymbol}")
                return

            logger.info(
                f"Found {len(sl_target_orders)} SL/Target orders to process "
                f"for {event.tradingsymbol}"
            )

            # Process each order
            for order in sl_target_orders:
                await self._process_order_cleanup(order, event)

        except Exception as e:
            logger.exception(f"Error processing cleanup for position event: {e}")

    async def _process_order_cleanup(self, order: Dict, event: PositionEvent):
        """
        Process cleanup for a single order.

        Args:
            order: Order dict from database
            event: Position change event
        """
        order_id = order.get("order_id")
        strategy_id = order.get("strategy_id")

        # Get strategy settings
        settings = await self._get_strategy_settings(strategy_id)

        # Check if cleanup enabled
        if not settings.auto_cleanup_enabled:
            logger.info(
                f"Cleanup disabled for order {order_id} (strategy {strategy_id})"
            )
            await self._log_cleanup_action(
                order=order,
                event=event,
                cleanup_action="skipped",
                cleanup_reason="auto_cleanup_disabled",
                was_auto=False
            )
            return

        # Check if should cleanup this order type
        order_type = order.get("order_type")
        if order_type == "SL" and not settings.cleanup_sl_on_exit:
            logger.info(f"SL cleanup disabled for strategy {strategy_id}")
            await self._log_cleanup_action(
                order=order,
                event=event,
                cleanup_action="skipped",
                cleanup_reason="cleanup_sl_on_exit_disabled",
                was_auto=False
            )
            return

        # For position REDUCED (not fully closed), check if order quantity > remaining position
        if event.event_type == PositionEventType.POSITION_REDUCED:
            order_qty = order.get("quantity", 0)
            position_qty_after = event.quantity_after

            if order_qty <= position_qty_after:
                # Order quantity is within remaining position, no action needed
                logger.debug(
                    f"Order {order_id} quantity ({order_qty}) <= "
                    f"remaining position ({position_qty_after}), skipping cleanup"
                )
                return

            # TODO: Could modify order quantity instead of cancelling
            # For now, we cancel to be safe
            logger.info(
                f"Order {order_id} quantity ({order_qty}) > "
                f"remaining position ({position_qty_after}), will cancel"
            )

        # Cancel order via ticker_service
        success = await self._cancel_order(order_id, order.get("account_id"))

        if success:
            cleanup_action = "cancelled"
            cleanup_reason = (
                "position_closed" if event.event_type == PositionEventType.POSITION_CLOSED
                else "position_reduced"
            )
            logger.info(f"Successfully cancelled order {order_id}")
        else:
            cleanup_action = "failed"
            cleanup_reason = "ticker_service_error"
            logger.warning(f"Failed to cancel order {order_id}")

        # Log cleanup action
        await self._log_cleanup_action(
            order=order,
            event=event,
            cleanup_action=cleanup_action,
            cleanup_reason=cleanup_reason,
            was_auto=True
        )

    async def _find_related_orders(
        self,
        account_id: str,
        tradingsymbol: str,
        exchange: str,
        product: str
    ) -> List[Dict]:
        """
        Find orders related to a position.

        Args:
            account_id: Account identifier
            tradingsymbol: Symbol
            exchange: Exchange
            product: Product (MIS, NRML, CNC)

        Returns:
            List of order dicts
        """
        if not self._dm.pool:
            logger.error("Database pool not available")
            return []

        try:
            query = """
                SELECT
                    order_id,
                    account_id,
                    strategy_id,
                    tradingsymbol,
                    exchange,
                    order_type,
                    product,
                    quantity,
                    status,
                    trigger_price,
                    placed_at,
                    updated_at
                FROM account_order
                WHERE account_id = $1
                  AND tradingsymbol = $2
                  AND exchange = $3
                  AND product = $4
                  AND status IN ('PENDING', 'OPEN', 'TRIGGER PENDING')
                ORDER BY placed_at DESC
            """

            async with self._dm.pool.acquire() as conn:
                rows = await conn.fetch(
                    query,
                    account_id,
                    tradingsymbol,
                    exchange,
                    product
                )

            return [dict(row) for row in rows]

        except Exception as e:
            logger.exception(f"Error finding related orders: {e}")
            return []

    async def _get_strategy_settings(
        self,
        strategy_id: Optional[int]
    ) -> StrategySettings:
        """
        Get strategy settings for cleanup behavior.

        Args:
            strategy_id: Strategy ID (None for manual orders)

        Returns:
            StrategySettings object (default settings if not found)
        """
        # Default settings for manual orders (no strategy)
        if strategy_id is None:
            return StrategySettings(
                strategy_id=None,
                auto_cleanup_enabled=False,  # Don't auto-cleanup manual orders
                cleanup_sl_on_exit=False,
                cleanup_target_on_exit=False,
                allow_orphaned_orders=True,
                notify_on_orphan_detection=False
            )

        if not self._dm.pool:
            logger.error("Database pool not available")
            return self._get_default_strategy_settings(strategy_id)

        try:
            query = """
                SELECT
                    strategy_id,
                    auto_cleanup_enabled,
                    cleanup_sl_on_exit,
                    cleanup_target_on_exit,
                    allow_orphaned_orders,
                    notify_on_orphan_detection
                FROM strategy_settings
                WHERE strategy_id = $1
            """

            async with self._dm.pool.acquire() as conn:
                row = await conn.fetchrow(query, strategy_id)

            if row:
                return StrategySettings(**dict(row))
            else:
                # Strategy exists but no settings row, use defaults
                logger.warning(
                    f"No settings found for strategy {strategy_id}, using defaults"
                )
                return self._get_default_strategy_settings(strategy_id)

        except Exception as e:
            logger.exception(f"Error fetching strategy settings: {e}")
            return self._get_default_strategy_settings(strategy_id)

    def _get_default_strategy_settings(self, strategy_id: int) -> StrategySettings:
        """Get default strategy settings."""
        return StrategySettings(
            strategy_id=strategy_id,
            auto_cleanup_enabled=True,
            cleanup_sl_on_exit=True,
            cleanup_target_on_exit=True,
            allow_orphaned_orders=False,
            notify_on_orphan_detection=True
        )

    async def _cancel_order(self, order_id: str, account_id: str) -> bool:
        """
        Cancel order via ticker_service.

        Args:
            order_id: Order ID to cancel
            account_id: Account ID

        Returns:
            True if successful, False otherwise
        """
        try:
            url = f"/orders/cancel"
            payload = {
                "account_id": account_id,
                "order_id": order_id,
                "variety": "regular"
            }

            response = await self._http.post(url, json=payload)

            if response.status_code == 200:
                logger.info(f"Cancelled order {order_id} via ticker_service")
                return True
            else:
                logger.warning(
                    f"Failed to cancel order {order_id}: "
                    f"status={response.status_code}, response={response.text}"
                )
                return False

        except httpx.RequestError as e:
            logger.exception(f"HTTP error cancelling order {order_id}: {e}")
            return False
        except Exception as e:
            logger.exception(f"Error cancelling order {order_id}: {e}")
            return False

    async def _log_cleanup_action(
        self,
        order: Dict,
        event: PositionEvent,
        cleanup_action: str,
        cleanup_reason: str,
        was_auto: bool
    ):
        """
        Log cleanup action to database.

        Args:
            order: Order dict
            event: Position change event
            cleanup_action: 'cancelled', 'skipped', 'failed'
            cleanup_reason: Reason for cleanup
            was_auto: Whether cleanup was automatic
        """
        if not self._dm.pool:
            logger.error("Database pool not available for logging")
            return

        try:
            query = """
                INSERT INTO order_cleanup_log (
                    order_id,
                    account_id,
                    strategy_id,
                    tradingsymbol,
                    exchange,
                    order_type,
                    cleanup_reason,
                    cleanup_action,
                    was_auto,
                    position_quantity_before,
                    position_quantity_after,
                    metadata,
                    cleaned_at
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13
                )
            """

            metadata = {
                "event_type": event.event_type,
                "product": event.product,
                "order_status": order.get("status"),
                "order_quantity": order.get("quantity")
            }

            async with self._dm.pool.acquire() as conn:
                await conn.execute(
                    query,
                    order.get("order_id"),
                    order.get("account_id"),
                    order.get("strategy_id"),
                    order.get("tradingsymbol"),
                    order.get("exchange"),
                    order.get("order_type"),
                    cleanup_reason,
                    cleanup_action,
                    was_auto,
                    event.quantity_before,
                    event.quantity_after,
                    metadata,
                    datetime.now(timezone.utc)
                )

            logger.debug(f"Logged cleanup action for order {order.get('order_id')}")

        except Exception as e:
            logger.exception(f"Error logging cleanup action: {e}")
