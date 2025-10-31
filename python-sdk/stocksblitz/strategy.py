"""
Strategy management for isolated trading within accounts.

A strategy represents a subset of an account's trades, positions, and holdings
with independent P&L tracking and performance metrics.
"""

from typing import Dict, List, Optional, Any
from datetime import datetime
from dataclasses import dataclass, field

from .enums import OrderStatus, PositionType
from .exceptions import APIError


@dataclass
class StrategyMetrics:
    """Strategy performance metrics."""
    total_pnl: float = 0.0
    day_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0

    # Position metrics
    open_positions: int = 0
    total_quantity: int = 0

    # Capital metrics
    capital_deployed: float = 0.0
    margin_used: float = 0.0

    # Trading metrics
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0

    # Risk metrics
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0

    # ROI
    roi: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'total_pnl': self.total_pnl,
            'day_pnl': self.day_pnl,
            'unrealized_pnl': self.unrealized_pnl,
            'realized_pnl': self.realized_pnl,
            'open_positions': self.open_positions,
            'total_quantity': self.total_quantity,
            'capital_deployed': self.capital_deployed,
            'margin_used': self.margin_used,
            'total_trades': self.total_trades,
            'winning_trades': self.winning_trades,
            'losing_trades': self.losing_trades,
            'max_drawdown': self.max_drawdown,
            'sharpe_ratio': self.sharpe_ratio,
            'roi': self.roi,
        }


class Strategy:
    """
    Strategy represents an isolated trading strategy within an account.

    A strategy tracks its own subset of:
    - Orders (linked via strategy_id)
    - Positions (filtered by strategy orders)
    - Holdings (filtered by strategy orders)
    - P&L and performance metrics

    Usage:
        # Create/load strategy
        strategy = client.Strategy(
            strategy_name="Nifty RSI Mean Reversion",
            strategy_type="mean_reversion"
        )

        # Execute trades within strategy context
        with strategy:
            inst = client.Instrument("NIFTY50")
            if inst['5m'].rsi[14] < 30:
                strategy.buy(inst, quantity=50)

        # Get strategy metrics
        metrics = strategy.metrics
        print(f"Strategy P&L: {metrics.total_pnl}")
        print(f"ROI: {metrics.roi}%")
    """

    def __init__(
        self,
        api_client: 'APIClient',
        strategy_id: Optional[int] = None,
        strategy_name: Optional[str] = None,
        strategy_type: str = "custom",
        description: str = "",
        account_ids: Optional[List[str]] = None,
        config: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize strategy.

        Args:
            api_client: API client instance
            strategy_id: Existing strategy ID (loads existing)
            strategy_name: Strategy name (for new strategy)
            strategy_type: Strategy type
            description: Strategy description
            account_ids: List of account IDs
            config: Strategy configuration dict
        """
        self._api = api_client
        self._strategy_id = strategy_id
        self._strategy_name = strategy_name
        self._strategy_type = strategy_type
        self._description = description
        self._account_ids = account_ids or ["primary"]
        self._config = config or {}

        self._data: Optional[Dict[str, Any]] = None
        self._metrics: Optional[StrategyMetrics] = None

        # Active strategy context
        self._is_active_context = False

        # Load existing or create new
        if strategy_id:
            self._load_strategy()
        elif strategy_name:
            self._create_or_get_strategy()

    @property
    def strategy_id(self) -> Optional[int]:
        """Get strategy ID."""
        return self._strategy_id

    @property
    def strategy_name(self) -> str:
        """Get strategy name."""
        return self._strategy_name or "Unnamed Strategy"

    @property
    def metrics(self) -> StrategyMetrics:
        """Get strategy performance metrics."""
        if self._metrics is None:
            self._metrics = self._fetch_metrics()
        return self._metrics

    @property
    def positions(self) -> List['Position']:
        """Get strategy-specific positions."""
        from .account import Position

        # Get strategy orders to filter positions
        orders = self.orders
        symbols = set(order.tradingsymbol for order in orders)

        # Get all account positions
        account_id = self._account_ids[0]
        response = self._api.get(f"/accounts/{account_id}/positions", cache_ttl=5)
        all_positions = response.get("data", [])

        # Filter to strategy symbols
        strategy_positions = [
            Position(pos, self._api, account_id)
            for pos in all_positions
            if pos.get("tradingsymbol") in symbols
        ]

        return strategy_positions

    @property
    def orders(self) -> List['Order']:
        """Get strategy-specific orders."""
        from .account import Order

        if not self._strategy_id:
            return []

        # Fetch orders filtered by strategy_id
        account_id = self._account_ids[0]
        response = self._api.get(
            f"/accounts/{account_id}/orders",
            params={"strategy_id": self._strategy_id},
            cache_ttl=2
        )

        return [Order(order, self._api) for order in response.get("data", [])]

    @property
    def holdings(self) -> List[Dict[str, Any]]:
        """Get strategy-specific holdings."""
        # Similar to positions, filter by strategy order symbols
        orders = self.orders
        symbols = set(order.tradingsymbol for order in orders)

        account_id = self._account_ids[0]
        response = self._api.get(f"/accounts/{account_id}/holdings", cache_ttl=10)
        all_holdings = response.get("data", [])

        return [
            holding for holding in all_holdings
            if holding.get("tradingsymbol") in symbols
        ]

    def buy(
        self,
        instrument: 'Instrument',
        quantity: int,
        **kwargs
    ) -> 'Order':
        """
        Place buy order within this strategy.

        Args:
            instrument: Instrument to buy
            quantity: Quantity to buy
            **kwargs: Additional order parameters

        Returns:
            Order object
        """
        return self._place_order("BUY", instrument, quantity, **kwargs)

    def sell(
        self,
        instrument: 'Instrument',
        quantity: int,
        **kwargs
    ) -> 'Order':
        """
        Place sell order within this strategy.

        Args:
            instrument: Instrument to sell
            quantity: Quantity to sell
            **kwargs: Additional order parameters

        Returns:
            Order object
        """
        return self._place_order("SELL", instrument, quantity, **kwargs)

    def _place_order(
        self,
        transaction_type: str,
        instrument: Any,
        quantity: int,
        **kwargs
    ) -> 'Order':
        """Place order and associate with strategy."""
        from .account import Order

        # Ensure strategy exists
        if not self._strategy_id:
            self._create_or_get_strategy()

        # Get symbol
        if hasattr(instrument, 'tradingsymbol'):
            symbol = instrument.tradingsymbol
        else:
            symbol = str(instrument)

        # Build order payload
        order_data = {
            "tradingsymbol": symbol,
            "transaction_type": transaction_type,
            "quantity": quantity,
            "strategy_id": self._strategy_id,  # Link to strategy
            **kwargs
        }

        # Place order
        account_id = self._account_ids[0]
        response = self._api.post(
            f"/accounts/{account_id}/orders",
            json=order_data
        )

        # Invalidate metrics cache
        self._metrics = None

        return Order(response, self._api)

    def _load_strategy(self) -> None:
        """Load existing strategy from database."""
        try:
            response = self._api.get(f"/strategies/{self._strategy_id}")
            self._data = response

            # Update fields
            self._strategy_name = self._data.get("strategy_name")
            self._strategy_type = self._data.get("strategy_type")
            self._description = self._data.get("description", "")
            self._account_ids = self._data.get("account_ids", ["primary"])
            self._config = self._data.get("config", {})

        except APIError as e:
            raise ValueError(f"Failed to load strategy {self._strategy_id}: {e}")

    def _create_or_get_strategy(self) -> None:
        """Create new strategy or get existing by name."""
        # Try to find existing strategy by name
        try:
            response = self._api.get(
                "/strategies",
                params={"strategy_name": self._strategy_name}
            )
            strategies = response.get("data", [])

            if strategies:
                # Found existing - use it
                self._data = strategies[0]
                self._strategy_id = self._data["strategy_id"]
                self._strategy_type = self._data.get("strategy_type", self._strategy_type)
                return
        except APIError:
            pass  # Strategy doesn't exist, create it

        # Create new strategy
        payload = {
            "strategy_name": self._strategy_name,
            "strategy_type": self._strategy_type,
            "description": self._description,
            "account_ids": self._account_ids,
            "config": self._config,
            "status": "active",
            "is_active": True
        }

        try:
            response = self._api.post("/strategies", json=payload)
            self._data = response
            self._strategy_id = self._data["strategy_id"]
        except APIError as e:
            raise ValueError(f"Failed to create strategy: {e}")

    def _fetch_metrics(self) -> StrategyMetrics:
        """Fetch strategy performance metrics."""
        if not self._strategy_id:
            return StrategyMetrics()

        try:
            # Get latest snapshot
            response = self._api.get(
                f"/strategies/{self._strategy_id}/metrics",
                cache_ttl=5
            )

            return StrategyMetrics(
                total_pnl=response.get("total_pnl", 0.0),
                day_pnl=response.get("day_pnl", 0.0),
                unrealized_pnl=response.get("unrealized_pnl", 0.0),
                realized_pnl=response.get("realized_pnl", 0.0),
                open_positions=response.get("open_positions", 0),
                total_quantity=response.get("total_quantity", 0),
                capital_deployed=response.get("capital_deployed", 0.0),
                margin_used=response.get("margin_used", 0.0),
                total_trades=response.get("total_trades", 0),
                winning_trades=response.get("winning_trades", 0),
                losing_trades=response.get("losing_trades", 0),
                max_drawdown=response.get("max_drawdown", 0.0),
                sharpe_ratio=response.get("sharpe_ratio", 0.0),
                roi=response.get("roi", 0.0),
            )
        except APIError:
            # Fallback: calculate from orders/positions
            return self._calculate_metrics()

    def _calculate_metrics(self) -> StrategyMetrics:
        """Calculate metrics from strategy data."""
        metrics = StrategyMetrics()

        # Get positions and orders
        positions = self.positions
        orders = self.orders

        # Calculate from positions
        metrics.open_positions = len(positions)
        metrics.total_quantity = sum(abs(pos.quantity) for pos in positions)
        metrics.unrealized_pnl = sum(pos.pnl for pos in positions)

        # Calculate from orders
        completed_orders = [o for o in orders if o.status == OrderStatus.COMPLETE]
        metrics.total_trades = len(completed_orders)

        # Calculate capital deployed
        for pos in positions:
            metrics.capital_deployed += abs(pos.quantity) * pos.average_price

        # Calculate realized P&L from completed round trips
        # (Simplified - assumes all completed orders are round trips)
        buy_orders = [o for o in completed_orders if o.transaction_type == "BUY"]
        sell_orders = [o for o in completed_orders if o.transaction_type == "SELL"]

        if buy_orders and sell_orders:
            buy_value = sum(o.filled_quantity * o.average_price for o in buy_orders)
            sell_value = sum(o.filled_quantity * o.average_price for o in sell_orders)
            metrics.realized_pnl = sell_value - buy_value

        # Total P&L
        metrics.total_pnl = metrics.realized_pnl + metrics.unrealized_pnl

        # ROI
        if metrics.capital_deployed > 0:
            metrics.roi = (metrics.total_pnl / metrics.capital_deployed) * 100

        # Winning/losing trades (simplified)
        for pos in positions:
            if pos.pnl > 0:
                metrics.winning_trades += 1
            elif pos.pnl < 0:
                metrics.losing_trades += 1

        return metrics

    def start(self) -> None:
        """Start/activate strategy."""
        if not self._strategy_id:
            self._create_or_get_strategy()

        self._api.post(f"/strategies/{self._strategy_id}/start")
        self._data["status"] = "active"
        self._data["is_active"] = True

    def stop(self) -> None:
        """Stop/deactivate strategy."""
        if self._strategy_id:
            self._api.post(f"/strategies/{self._strategy_id}/stop")
            if self._data:
                self._data["status"] = "stopped"
                self._data["is_active"] = False

    def pause(self) -> None:
        """Pause strategy."""
        if self._strategy_id:
            self._api.post(f"/strategies/{self._strategy_id}/pause")
            if self._data:
                self._data["status"] = "paused"

    def resume(self) -> None:
        """Resume paused strategy."""
        if self._strategy_id:
            self._api.post(f"/strategies/{self._strategy_id}/resume")
            if self._data:
                self._data["status"] = "active"

    def get_snapshots(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get historical strategy snapshots.

        Args:
            start_time: Start time
            end_time: End time
            limit: Maximum snapshots to return

        Returns:
            List of snapshot dictionaries
        """
        if not self._strategy_id:
            return []

        params = {"limit": limit}
        if start_time:
            params["start_time"] = start_time.isoformat()
        if end_time:
            params["end_time"] = end_time.isoformat()

        response = self._api.get(
            f"/strategies/{self._strategy_id}/snapshots",
            params=params
        )

        return response.get("data", [])

    def __enter__(self):
        """Enter strategy context."""
        self._is_active_context = True
        if not self._strategy_id:
            self._create_or_get_strategy()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit strategy context."""
        self._is_active_context = False
        # Refresh metrics on exit
        self._metrics = None
        return False

    def __repr__(self) -> str:
        if self._strategy_id:
            return f"<Strategy id={self._strategy_id} name='{self.strategy_name}'>"
        else:
            return f"<Strategy name='{self.strategy_name}' (not created)>"
