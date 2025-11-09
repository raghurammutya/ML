"""
Position Tracker Service

Tracks position state changes and detects position closures, reductions, and openings.
Emits events for downstream consumers (e.g., order cleanup worker).

Usage:
    tracker = PositionTracker()
    tracker.register_listener(cleanup_worker.on_position_event)
    await tracker.on_position_update(account_id, positions)
"""

from __future__ import annotations

import logging
from typing import Dict, List, Callable, Optional, Any
from dataclasses import dataclass
from enum import Enum
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class PositionEventType(str, Enum):
    """Types of position change events."""
    POSITION_OPENED = "POSITION_OPENED"      # New position created
    POSITION_INCREASED = "POSITION_INCREASED"  # Position quantity increased
    POSITION_REDUCED = "POSITION_REDUCED"    # Position quantity decreased
    POSITION_CLOSED = "POSITION_CLOSED"      # Position fully closed (quantity → 0)
    POSITION_UPDATED = "POSITION_UPDATED"    # Price/PnL update only


@dataclass
class Position:
    """Position data snapshot."""
    account_id: str
    tradingsymbol: str
    exchange: str
    product: str  # MIS, NRML, CNC
    quantity: int
    average_price: float
    last_price: float
    pnl: float
    day_pnl: float
    synced_at: datetime


@dataclass
class PositionEvent:
    """
    Position change event.

    Attributes:
        event_type: Type of position change
        account_id: Account identifier
        tradingsymbol: Instrument symbol
        exchange: Exchange (NSE, NFO, etc.)
        product: Product type (MIS, NRML, CNC)

        # State changes
        quantity_before: Position quantity before change
        quantity_after: Position quantity after change
        quantity_delta: Change in quantity (positive = increase, negative = decrease)

        # Position data
        current_position: Current position snapshot (None if closed)
        previous_position: Previous position snapshot (None if opened)

        # Metadata
        timestamp: Event timestamp
        metadata: Additional context
    """
    event_type: PositionEventType
    account_id: str
    tradingsymbol: str
    exchange: str
    product: str

    quantity_before: int
    quantity_after: int
    quantity_delta: int

    current_position: Optional[Position]
    previous_position: Optional[Position]

    timestamp: datetime
    metadata: Dict[str, Any]

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "event_type": self.event_type,
            "account_id": self.account_id,
            "tradingsymbol": self.tradingsymbol,
            "exchange": self.exchange,
            "product": self.product,
            "quantity_before": self.quantity_before,
            "quantity_after": self.quantity_after,
            "quantity_delta": self.quantity_delta,
            "current_position": self.current_position.__dict__ if self.current_position else None,
            "previous_position": self.previous_position.__dict__ if self.previous_position else None,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata
        }


class PositionTracker:
    """
    Tracks position state changes and emits events.

    Maintains a snapshot of positions and compares incoming updates
    to detect openings, closures, and quantity changes.
    """

    def __init__(self):
        """Initialize position tracker."""
        # State: {account_id: {position_key: Position}}
        self._positions: Dict[str, Dict[str, Position]] = {}

        # Event listeners: [(callback_func, filter_func)]
        self._listeners: List[tuple[Callable, Optional[Callable]]] = []

        logger.info("PositionTracker initialized")

    def register_listener(
        self,
        callback: Callable[[PositionEvent], None],
        event_filter: Optional[Callable[[PositionEvent], bool]] = None
    ):
        """
        Register a listener for position events.

        Args:
            callback: Async function to call with PositionEvent
            event_filter: Optional filter function (returns True to include event)

        Example:
            def my_filter(event):
                return event.event_type == PositionEventType.POSITION_CLOSED

            tracker.register_listener(my_handler, my_filter)
        """
        self._listeners.append((callback, event_filter))
        callback_name = getattr(callback, '__name__', str(callback))
        logger.info(f"Registered position event listener: {callback_name}")

    async def on_position_update(self, account_id: str, positions: List[Dict]):
        """
        Process position update from ticker_service.

        Args:
            account_id: Account identifier
            positions: List of position dicts from ticker_service

        This method:
        1. Compares new positions with stored snapshot
        2. Detects changes (opened, closed, increased, reduced)
        3. Emits events to registered listeners
        4. Updates snapshot
        """
        logger.debug(f"Processing position update for account {account_id}: {len(positions)} positions")

        # Get current snapshot for this account
        current_snapshot = self._positions.get(account_id, {})

        # Build new snapshot
        new_snapshot = {}
        for pos_dict in positions:
            position = self._dict_to_position(account_id, pos_dict)
            position_key = self._get_position_key(position)
            new_snapshot[position_key] = position

        # Detect changes
        events = self._detect_changes(account_id, current_snapshot, new_snapshot)

        # Emit events
        for event in events:
            await self._emit_event(event)

        # Update snapshot
        self._positions[account_id] = new_snapshot

        logger.debug(f"Position update complete for {account_id}: {len(events)} events emitted")

    def _detect_changes(
        self,
        account_id: str,
        old_snapshot: Dict[str, Position],
        new_snapshot: Dict[str, Position]
    ) -> List[PositionEvent]:
        """
        Detect position changes between snapshots.

        Returns:
            List of PositionEvent objects
        """
        events = []

        # Keys in old but not in new = CLOSED
        closed_keys = set(old_snapshot.keys()) - set(new_snapshot.keys())
        for key in closed_keys:
            old_pos = old_snapshot[key]
            event = PositionEvent(
                event_type=PositionEventType.POSITION_CLOSED,
                account_id=account_id,
                tradingsymbol=old_pos.tradingsymbol,
                exchange=old_pos.exchange,
                product=old_pos.product,
                quantity_before=old_pos.quantity,
                quantity_after=0,
                quantity_delta=-old_pos.quantity,
                current_position=None,
                previous_position=old_pos,
                timestamp=datetime.now(timezone.utc),
                metadata={"reason": "position_not_in_update"}
            )
            events.append(event)
            logger.info(
                f"Position CLOSED: {old_pos.tradingsymbol} {old_pos.exchange} "
                f"{old_pos.product} (qty: {old_pos.quantity} → 0)"
            )

        # Keys in new but not in old = OPENED
        opened_keys = set(new_snapshot.keys()) - set(old_snapshot.keys())
        for key in opened_keys:
            new_pos = new_snapshot[key]
            event = PositionEvent(
                event_type=PositionEventType.POSITION_OPENED,
                account_id=account_id,
                tradingsymbol=new_pos.tradingsymbol,
                exchange=new_pos.exchange,
                product=new_pos.product,
                quantity_before=0,
                quantity_after=new_pos.quantity,
                quantity_delta=new_pos.quantity,
                current_position=new_pos,
                previous_position=None,
                timestamp=datetime.now(timezone.utc),
                metadata={"reason": "new_position_in_update"}
            )
            events.append(event)
            logger.info(
                f"Position OPENED: {new_pos.tradingsymbol} {new_pos.exchange} "
                f"{new_pos.product} (qty: 0 → {new_pos.quantity})"
            )

        # Keys in both = check for changes
        common_keys = set(old_snapshot.keys()) & set(new_snapshot.keys())
        for key in common_keys:
            old_pos = old_snapshot[key]
            new_pos = new_snapshot[key]

            # Check quantity change
            qty_delta = new_pos.quantity - old_pos.quantity

            if qty_delta > 0:
                # Position increased
                event = PositionEvent(
                    event_type=PositionEventType.POSITION_INCREASED,
                    account_id=account_id,
                    tradingsymbol=new_pos.tradingsymbol,
                    exchange=new_pos.exchange,
                    product=new_pos.product,
                    quantity_before=old_pos.quantity,
                    quantity_after=new_pos.quantity,
                    quantity_delta=qty_delta,
                    current_position=new_pos,
                    previous_position=old_pos,
                    timestamp=datetime.now(timezone.utc),
                    metadata={"reason": "quantity_increased"}
                )
                events.append(event)
                logger.info(
                    f"Position INCREASED: {new_pos.tradingsymbol} {new_pos.exchange} "
                    f"{new_pos.product} (qty: {old_pos.quantity} → {new_pos.quantity})"
                )

            elif qty_delta < 0:
                # Position reduced
                event = PositionEvent(
                    event_type=PositionEventType.POSITION_REDUCED,
                    account_id=account_id,
                    tradingsymbol=new_pos.tradingsymbol,
                    exchange=new_pos.exchange,
                    product=new_pos.product,
                    quantity_before=old_pos.quantity,
                    quantity_after=new_pos.quantity,
                    quantity_delta=qty_delta,
                    current_position=new_pos,
                    previous_position=old_pos,
                    timestamp=datetime.now(timezone.utc),
                    metadata={"reason": "quantity_reduced"}
                )
                events.append(event)
                logger.info(
                    f"Position REDUCED: {new_pos.tradingsymbol} {new_pos.exchange} "
                    f"{new_pos.product} (qty: {old_pos.quantity} → {new_pos.quantity})"
                )

            else:
                # Quantity unchanged, check if price/PnL changed significantly
                # (Only emit if price changed by > 0.1% or PnL changed)
                price_change_pct = abs(new_pos.last_price - old_pos.last_price) / old_pos.last_price * 100
                pnl_changed = new_pos.pnl != old_pos.pnl

                if price_change_pct > 0.1 or pnl_changed:
                    event = PositionEvent(
                        event_type=PositionEventType.POSITION_UPDATED,
                        account_id=account_id,
                        tradingsymbol=new_pos.tradingsymbol,
                        exchange=new_pos.exchange,
                        product=new_pos.product,
                        quantity_before=old_pos.quantity,
                        quantity_after=new_pos.quantity,
                        quantity_delta=0,
                        current_position=new_pos,
                        previous_position=old_pos,
                        timestamp=datetime.now(timezone.utc),
                        metadata={
                            "reason": "price_pnl_update",
                            "price_change_pct": round(price_change_pct, 2)
                        }
                    )
                    events.append(event)
                    logger.debug(
                        f"Position UPDATED: {new_pos.tradingsymbol} {new_pos.exchange} "
                        f"(price: {old_pos.last_price} → {new_pos.last_price}, "
                        f"pnl: {old_pos.pnl} → {new_pos.pnl})"
                    )

        return events

    async def _emit_event(self, event: PositionEvent):
        """
        Emit event to all registered listeners.

        Args:
            event: PositionEvent to emit
        """
        for callback, event_filter in self._listeners:
            # Apply filter if provided
            if event_filter and not event_filter(event):
                continue

            try:
                # Call listener (may be async)
                if hasattr(callback, '__call__'):
                    result = callback(event)
                    # Await if async
                    if hasattr(result, '__await__'):
                        await result
            except Exception as e:
                logger.exception(
                    f"Error in position event listener {callback.__name__}: {e}"
                )

    def _dict_to_position(self, account_id: str, pos_dict: Dict) -> Position:
        """Convert position dict from ticker_service to Position object."""
        return Position(
            account_id=account_id,
            tradingsymbol=pos_dict.get("tradingsymbol", ""),
            exchange=pos_dict.get("exchange", ""),
            product=pos_dict.get("product", ""),
            quantity=pos_dict.get("quantity", 0),
            average_price=pos_dict.get("average_price", 0.0),
            last_price=pos_dict.get("last_price", 0.0),
            pnl=pos_dict.get("pnl", 0.0),
            day_pnl=pos_dict.get("day_pnl", 0.0),
            synced_at=datetime.now(timezone.utc)
        )

    def _get_position_key(self, position: Position) -> str:
        """Get unique key for position (tradingsymbol + exchange + product)."""
        return f"{position.tradingsymbol}:{position.exchange}:{position.product}"

    def get_current_positions(self, account_id: str) -> Dict[str, Position]:
        """
        Get current position snapshot for an account.

        Args:
            account_id: Account identifier

        Returns:
            Dictionary of {position_key: Position}
        """
        return self._positions.get(account_id, {}).copy()

    def clear_positions(self, account_id: Optional[str] = None):
        """
        Clear position snapshots.

        Args:
            account_id: If provided, clear only this account. Otherwise clear all.
        """
        if account_id:
            self._positions.pop(account_id, None)
            logger.info(f"Cleared position snapshot for account: {account_id}")
        else:
            self._positions.clear()
            logger.info("Cleared all position snapshots")
