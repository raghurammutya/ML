"""
Account, Position, Order, and Funds classes for trading operations.
"""

from typing import TYPE_CHECKING, List, Optional, Union, Dict, Any
from datetime import datetime
from .exceptions import InsufficientFundsError, InvalidOrderError
from .cache import cache_key

if TYPE_CHECKING:
    from .api import APIClient
    from .instrument import Instrument


class Funds:
    """Represents account funds and margin information."""

    def __init__(self, data: Dict[str, Any]):
        """
        Initialize funds.

        Args:
            data: Funds data from API
        """
        self._data = data

    @property
    def available_cash(self) -> float:
        """Available cash for trading."""
        return float(self._data.get("available_cash", 0))

    @property
    def used_margin(self) -> float:
        """Margin currently in use."""
        return float(self._data.get("used_margin", 0))

    @property
    def available_margin(self) -> float:
        """Available margin for trading."""
        return float(self._data.get("available_margin", 0))

    @property
    def total_margin(self) -> float:
        """Total margin (used + available)."""
        return self.used_margin + self.available_margin

    def __repr__(self) -> str:
        return (f"<Funds available_cash={self.available_cash:.2f} "
                f"used_margin={self.used_margin:.2f}>")


class Order:
    """Represents a trading order."""

    def __init__(self, data: Dict[str, Any], api_client: 'APIClient' = None):
        """
        Initialize order.

        Args:
            data: Order data from API
            api_client: API client instance
        """
        self._data = data
        self._api = api_client

    @property
    def order_id(self) -> str:
        """Order ID."""
        return self._data.get("order_id", "")

    @property
    def tradingsymbol(self) -> str:
        """Trading symbol."""
        return self._data.get("tradingsymbol", "")

    @property
    def transaction_type(self) -> str:
        """Transaction type (BUY/SELL)."""
        return self._data.get("transaction_type", "")

    @property
    def quantity(self) -> int:
        """Order quantity."""
        return int(self._data.get("quantity", 0))

    @property
    def price(self) -> float:
        """Order price."""
        return float(self._data.get("price", 0))

    @property
    def order_type(self) -> str:
        """Order type (MARKET/LIMIT/SL/SL-M)."""
        return self._data.get("order_type", "")

    @property
    def status(self) -> str:
        """Order status."""
        return self._data.get("status", "")

    @property
    def filled_quantity(self) -> int:
        """Filled quantity."""
        return int(self._data.get("filled_quantity", 0))

    @property
    def pending_quantity(self) -> int:
        """Pending quantity."""
        return self.quantity - self.filled_quantity

    @property
    def is_complete(self) -> bool:
        """Check if order is complete."""
        return self.status in ["COMPLETE", "FILLED"]

    @property
    def is_pending(self) -> bool:
        """Check if order is pending."""
        return self.status in ["PENDING", "OPEN", "TRIGGER PENDING"]

    @property
    def is_rejected(self) -> bool:
        """Check if order is rejected."""
        return self.status in ["REJECTED", "CANCELLED"]

    def cancel(self) -> bool:
        """
        Cancel order.

        Returns:
            True if cancelled successfully

        Raises:
            InvalidOrderError: If order cannot be cancelled
        """
        if not self.is_pending:
            raise InvalidOrderError(f"Cannot cancel order in status: {self.status}")

        try:
            self._api.delete(
                f"/accounts/primary/orders/{self.order_id}"
            )
            return True
        except Exception as e:
            raise InvalidOrderError(f"Failed to cancel order: {e}")

    def __repr__(self) -> str:
        return (f"<Order {self.order_id} {self.transaction_type} "
                f"{self.tradingsymbol} qty={self.quantity} status={self.status}>")


class Position:
    """Represents an open position."""

    def __init__(self, data: Dict[str, Any], api_client: 'APIClient' = None,
                 account_id: str = "primary"):
        """
        Initialize position.

        Args:
            data: Position data from API
            api_client: API client instance
            account_id: Account ID
        """
        self._data = data
        self._api = api_client
        self._account_id = account_id

    @property
    def tradingsymbol(self) -> str:
        """Trading symbol."""
        return self._data.get("tradingsymbol", "")

    @property
    def quantity(self) -> int:
        """Position quantity (positive for long, negative for short)."""
        return int(self._data.get("quantity", 0))

    @property
    def average_price(self) -> float:
        """Average entry price."""
        return float(self._data.get("average_price", 0))

    @property
    def last_price(self) -> float:
        """Last traded price."""
        return float(self._data.get("last_price", 0))

    @property
    def pnl(self) -> float:
        """Unrealized PnL."""
        return float(self._data.get("unrealized_pnl", 0))

    @property
    def realized_pnl(self) -> float:
        """Realized PnL."""
        return float(self._data.get("realized_pnl", 0))

    @property
    def pnl_percent(self) -> float:
        """PnL as percentage of investment."""
        if self.quantity == 0 or self.average_price == 0:
            return 0.0
        investment = abs(self.quantity) * self.average_price
        return (self.pnl / investment) * 100

    @property
    def is_long(self) -> bool:
        """Check if position is long."""
        return self.quantity > 0

    @property
    def is_short(self) -> bool:
        """Check if position is short."""
        return self.quantity < 0

    def close(self, **kwargs) -> Order:
        """
        Close position by placing reverse order.

        Args:
            **kwargs: Additional order parameters (order_type, etc.)

        Returns:
            Order object

        Examples:
            >>> pos.close()  # Market order
            >>> pos.close(order_type="LIMIT", price=100)
        """
        # Determine side
        side = "SELL" if self.is_long else "BUY"
        qty = abs(self.quantity)

        # Default to MARKET order
        if "order_type" not in kwargs:
            kwargs["order_type"] = "MARKET"

        # Place order
        try:
            response = self._api.post(
                f"/accounts/{self._account_id}/orders",
                json={
                    "tradingsymbol": self.tradingsymbol,
                    "transaction_type": side,
                    "quantity": qty,
                    **kwargs
                }
            )
            return Order(response, self._api)

        except Exception as e:
            raise InvalidOrderError(f"Failed to close position: {e}")

    def history(self, lookback: int = 10) -> List['PositionSnapshot']:
        """
        Get historical snapshots of this position.

        Args:
            lookback: Number of snapshots to retrieve

        Returns:
            List of PositionSnapshot objects
        """
        try:
            # Calculate time range (lookback * 5 minutes assuming 5min snapshots)
            from datetime import timedelta
            to_ts = datetime.now()
            from_ts = to_ts - timedelta(minutes=lookback * 5)

            response = self._api.get(
                f"/accounts/{self._account_id}/positions/history",
                params={
                    "from_ts": from_ts.isoformat(),
                    "to_ts": to_ts.isoformat(),
                    "tradingsymbol": self.tradingsymbol
                },
                cache_ttl=60
            )

            snapshots = response.get("snapshots", [])
            return [PositionSnapshot(s) for s in snapshots]

        except Exception as e:
            raise RuntimeError(f"Failed to fetch position history: {e}")

    def __repr__(self) -> str:
        return (f"<Position {self.tradingsymbol} qty={self.quantity} "
                f"pnl={self.pnl:.2f} ({self.pnl_percent:.2f}%)>")


class PositionSnapshot:
    """Historical snapshot of a position."""

    def __init__(self, data: Dict[str, Any]):
        """Initialize position snapshot."""
        self._data = data

    @property
    def snapshot_time(self) -> datetime:
        """Snapshot timestamp."""
        return datetime.fromisoformat(self._data.get("snapshot_time", ""))

    @property
    def quantity(self) -> int:
        """Quantity at snapshot time."""
        return int(self._data.get("quantity", 0))

    @property
    def average_price(self) -> float:
        """Average price at snapshot time."""
        return float(self._data.get("average_price", 0))

    @property
    def last_price(self) -> float:
        """Last price at snapshot time."""
        return float(self._data.get("last_price", 0))

    @property
    def unrealized_pnl(self) -> float:
        """Unrealized PnL at snapshot time."""
        return float(self._data.get("unrealized_pnl", 0))

    def __repr__(self) -> str:
        return f"<PositionSnapshot time={self.snapshot_time} pnl={self.unrealized_pnl:.2f}>"


class Account:
    """Trading account operations."""

    def __init__(self, account_id: str = "primary", api_client: 'APIClient' = None):
        """
        Initialize account.

        Args:
            account_id: Account identifier
            api_client: API client instance
        """
        self.account_id = account_id
        self._api = api_client
        self._positions_cache = None
        self._funds_cache = None

    @property
    def positions(self) -> List[Position]:
        """
        Get all positions.

        Returns:
            List of Position objects
        """
        # Check cache
        key = cache_key("positions", self.account_id)
        cached = self._api.cache.get(key)
        if cached is not None:
            return [Position(p, self._api, self.account_id) for p in cached]

        # Fetch from API
        try:
            response = self._api.get(
                f"/accounts/{self.account_id}/positions",
                cache_ttl=5  # 5 second cache
            )

            positions_data = response.get("data", [])
            self._api.cache.set(key, positions_data, ttl=5)

            return [Position(p, self._api, self.account_id) for p in positions_data]

        except Exception as e:
            raise RuntimeError(f"Failed to fetch positions: {e}")

    @property
    def holdings(self) -> List[Dict]:
        """Get all holdings."""
        try:
            response = self._api.get(
                f"/accounts/{self.account_id}/holdings",
                cache_ttl=30
            )
            return response.get("data", [])
        except Exception as e:
            raise RuntimeError(f"Failed to fetch holdings: {e}")

    @property
    def orders(self) -> List[Order]:
        """Get all orders."""
        try:
            response = self._api.get(
                f"/accounts/{self.account_id}/orders",
                cache_ttl=5
            )
            return [Order(o, self._api) for o in response.get("data", [])]
        except Exception as e:
            raise RuntimeError(f"Failed to fetch orders: {e}")

    @property
    def funds(self) -> Funds:
        """Get available funds."""
        # Check cache
        key = cache_key("funds", self.account_id)
        cached = self._api.cache.get(key)
        if cached is not None:
            return Funds(cached)

        # Fetch from API
        try:
            response = self._api.get(
                f"/accounts/{self.account_id}/funds",
                cache_ttl=10
            )

            funds_data = response.get("data", {})
            self._api.cache.set(key, funds_data, ttl=10)

            return Funds(funds_data)

        except Exception as e:
            raise RuntimeError(f"Failed to fetch funds: {e}")

    def position(self, instrument: Union[str, 'Instrument']) -> Optional[Position]:
        """
        Get position for specific instrument.

        Args:
            instrument: Trading symbol or Instrument object

        Returns:
            Position object or None if not found
        """
        from .instrument import Instrument

        symbol = instrument.tradingsymbol if isinstance(instrument, Instrument) else instrument
        positions = self.positions

        for pos in positions:
            if pos.tradingsymbol == symbol:
                return pos

        return None

    def buy(self, instrument: Union[str, 'Instrument'], quantity: int, **kwargs) -> Order:
        """
        Place buy order.

        Args:
            instrument: Trading symbol or Instrument object
            quantity: Order quantity
            **kwargs: Additional order parameters

        Returns:
            Order object

        Examples:
            >>> account.buy("NIFTY25N0424500PE", 50)
            >>> account.buy(inst, 50, order_type="LIMIT", price=100)
        """
        return self._place_order("BUY", instrument, quantity, **kwargs)

    def sell(self, instrument: Union[str, 'Instrument'], quantity: int, **kwargs) -> Order:
        """
        Place sell order.

        Args:
            instrument: Trading symbol or Instrument object
            quantity: Order quantity
            **kwargs: Additional order parameters

        Returns:
            Order object
        """
        return self._place_order("SELL", instrument, quantity, **kwargs)

    def _place_order(self, side: str, instrument: Union[str, 'Instrument'],
                     quantity: int, **kwargs) -> Order:
        """
        Internal method to place order.

        Args:
            side: BUY or SELL
            instrument: Trading symbol or Instrument object
            quantity: Order quantity
            **kwargs: Additional parameters

        Returns:
            Order object
        """
        from .instrument import Instrument

        symbol = instrument.tradingsymbol if isinstance(instrument, Instrument) else instrument

        # Default order type
        if "order_type" not in kwargs:
            kwargs["order_type"] = "MARKET"

        # Build order payload
        order_data = {
            "tradingsymbol": symbol,
            "transaction_type": side,
            "quantity": quantity,
            **kwargs
        }

        # Place order
        try:
            response = self._api.post(
                f"/accounts/{self.account_id}/orders",
                json=order_data
            )
            return Order(response, self._api)

        except Exception as e:
            raise InvalidOrderError(f"Failed to place order: {e}")

    def __repr__(self) -> str:
        return f"<Account {self.account_id}>"
