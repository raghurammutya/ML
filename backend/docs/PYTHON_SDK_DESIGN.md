# Python SDK Design - Smart Order Management

**Created**: 2025-11-09
**Purpose**: Provide clean Python SDK with exceptions, alerts, and event handlers
**Target Users**: Python developers, algorithmic traders, strategy builders

---

## Table of Contents

1. [SDK Architecture](#1-sdk-architecture)
2. [Exception Hierarchy](#2-exception-hierarchy)
3. [Alert System](#3-alert-system)
4. [SDK Usage Examples](#4-sdk-usage-examples)
5. [Event Handlers](#5-event-handlers)
6. [Configuration](#6-configuration)
7. [UI Integration](#7-ui-integration)

---

## 1. SDK Architecture

### 1.1 SDK Structure

```
stocksblitz_sdk/
├── __init__.py
├── client.py                      # Main SDK client
├── exceptions.py                  # All custom exceptions
├── alerts.py                      # Alert system
├── models/
│   ├── __init__.py
│   ├── order.py                   # Order models
│   ├── strategy.py                # Strategy models
│   ├── margin.py                  # Margin models
│   └── execution.py               # Execution analysis models
├── managers/
│   ├── __init__.py
│   ├── order_manager.py           # Order management
│   ├── strategy_manager.py        # Strategy management
│   ├── margin_manager.py          # Margin tracking
│   └── risk_manager.py            # Risk limits
├── analyzers/
│   ├── __init__.py
│   ├── market_depth.py            # Market depth analysis
│   ├── spread_analyzer.py         # Spread analysis
│   └── greeks_analyzer.py         # Greeks analysis
└── events/
    ├── __init__.py
    ├── handlers.py                # Event handlers
    └── listeners.py               # Event listeners
```

### 1.2 Main Client

```python
# stocksblitz_sdk/client.py

from typing import Optional, List, Callable
import asyncio
from .managers import OrderManager, StrategyManager, MarginManager, RiskManager
from .events import EventEmitter
from .exceptions import SDKException

class StocksBlitzClient:
    """
    Main SDK client for StocksBlitz trading platform.

    Usage:
        client = StocksBlitzClient(
            api_url="https://api.stocksblitz.com",
            api_key="your_api_key"
        )

        # Enable auto-housekeeping
        client.enable_auto_housekeeping()

        # Subscribe to alerts
        client.on_alert(lambda alert: print(alert))

        # Create strategy
        strategy = client.strategies.create("My Iron Condor")
    """

    def __init__(
        self,
        api_url: str,
        api_key: str,
        auto_housekeeping: bool = True,
        margin_monitoring: bool = True,
        risk_alerts: bool = True
    ):
        self.api_url = api_url
        self.api_key = api_key

        # Initialize managers
        self.orders = OrderManager(self)
        self.strategies = StrategyManager(self)
        self.margin = MarginManager(self)
        self.risk = RiskManager(self)

        # Event emitter for alerts
        self.events = EventEmitter()

        # Feature flags
        self.auto_housekeeping = auto_housekeeping
        self.margin_monitoring = margin_monitoring
        self.risk_alerts = risk_alerts

        # Start background workers if enabled
        if margin_monitoring:
            self._start_margin_monitor()

        if auto_housekeeping:
            self._start_housekeeping_worker()

    def on_alert(self, handler: Callable):
        """Register alert handler."""
        self.events.on('alert', handler)

    def on_margin_warning(self, handler: Callable):
        """Register margin warning handler."""
        self.events.on('margin_warning', handler)

    def on_risk_breach(self, handler: Callable):
        """Register risk breach handler."""
        self.events.on('risk_breach', handler)

    def on_orphaned_order(self, handler: Callable):
        """Register orphaned order handler."""
        self.events.on('orphaned_order', handler)

    def enable_auto_housekeeping(self):
        """Enable automatic order housekeeping."""
        self.auto_housekeeping = True
        self._start_housekeeping_worker()

    def disable_auto_housekeeping(self):
        """Disable automatic order housekeeping."""
        self.auto_housekeeping = False
```

---

## 2. Exception Hierarchy

### 2.1 Exception Tree

```python
# stocksblitz_sdk/exceptions.py

class SDKException(Exception):
    """Base exception for all SDK errors."""
    def __init__(self, message: str, code: Optional[str] = None, details: Optional[dict] = None):
        self.message = message
        self.code = code
        self.details = details or {}
        super().__init__(self.message)


# ============================================================================
# Order Execution Exceptions
# ============================================================================

class OrderExecutionException(SDKException):
    """Base exception for order execution errors."""
    pass


class WideSpreadException(OrderExecutionException):
    """
    Raised when bid-ask spread exceeds threshold.

    Attributes:
        spread_pct: Spread as percentage
        spread_abs: Absolute spread value
        threshold: Configured threshold
        recommended_action: LIMIT_ORDER, CANCEL, WAIT

    Usage:
        try:
            client.orders.place(order)
        except WideSpreadException as e:
            print(f"Spread {e.spread_pct}% exceeds threshold {e.threshold}%")
            print(f"Recommended: {e.recommended_action}")
            # User can override
            if confirm("Proceed anyway?"):
                client.orders.place(order, force=True)
    """
    def __init__(
        self,
        message: str,
        spread_pct: float,
        spread_abs: float,
        threshold: float,
        recommended_action: str,
        **kwargs
    ):
        super().__init__(message, code="WIDE_SPREAD", **kwargs)
        self.spread_pct = spread_pct
        self.spread_abs = spread_abs
        self.threshold = threshold
        self.recommended_action = recommended_action


class HighMarketImpactException(OrderExecutionException):
    """
    Raised when order would cause high market impact.

    Attributes:
        impact_bps: Market impact in basis points
        impact_cost: Estimated cost in rupees
        threshold_bps: Configured threshold
        recommended_action: SPLIT_ORDER, USE_TWAP, REDUCE_QUANTITY

    Usage:
        try:
            client.orders.place_market(symbol, 500)
        except HighMarketImpactException as e:
            print(f"Impact: {e.impact_bps} bps (₹{e.impact_cost})")
            # Use TWAP instead
            client.orders.place_twap(symbol, 500, duration_minutes=30)
    """
    def __init__(
        self,
        message: str,
        impact_bps: int,
        impact_cost: float,
        threshold_bps: int,
        levels_consumed: int,
        recommended_action: str,
        **kwargs
    ):
        super().__init__(message, code="HIGH_MARKET_IMPACT", **kwargs)
        self.impact_bps = impact_bps
        self.impact_cost = impact_cost
        self.threshold_bps = threshold_bps
        self.levels_consumed = levels_consumed
        self.recommended_action = recommended_action


class InsufficientLiquidityException(OrderExecutionException):
    """
    Raised when order cannot be filled due to insufficient liquidity.

    Attributes:
        requested_quantity: Quantity user wants
        available_quantity: Maximum available in order book
        liquidity_tier: HIGH/MEDIUM/LOW/ILLIQUID

    Usage:
        try:
            client.orders.place(symbol, 1000)
        except InsufficientLiquidityException as e:
            print(f"Only {e.available_quantity} lots available")
            # Reduce quantity
            client.orders.place(symbol, e.available_quantity)
    """
    def __init__(
        self,
        message: str,
        requested_quantity: int,
        available_quantity: int,
        liquidity_tier: str,
        **kwargs
    ):
        super().__init__(message, code="INSUFFICIENT_LIQUIDITY", **kwargs)
        self.requested_quantity = requested_quantity
        self.available_quantity = available_quantity
        self.liquidity_tier = liquidity_tier


# ============================================================================
# Margin Exceptions
# ============================================================================

class MarginException(SDKException):
    """Base exception for margin-related errors."""
    pass


class MarginShortfallException(MarginException):
    """
    Raised when margin requirement exceeds available margin.

    Attributes:
        required_margin: Margin needed
        available_margin: Margin available
        shortfall: Deficit amount
        deadline: Time by which margin must be added

    Usage:
        try:
            client.strategies.add_position(strategy_id, position)
        except MarginShortfallException as e:
            print(f"Shortfall: ₹{e.shortfall}")
            print(f"Deadline: {e.deadline}")
            # Add funds or reduce positions
            client.margin.add_funds(e.shortfall)
    """
    def __init__(
        self,
        message: str,
        required_margin: float,
        available_margin: float,
        shortfall: float,
        deadline: Optional[datetime] = None,
        **kwargs
    ):
        super().__init__(message, code="MARGIN_SHORTFALL", **kwargs)
        self.required_margin = required_margin
        self.available_margin = available_margin
        self.shortfall = shortfall
        self.deadline = deadline


class MarginIncreasedException(MarginException):
    """
    Raised when margin requirement increases significantly.

    Attributes:
        old_margin: Previous margin
        new_margin: New margin
        change_pct: Percentage change
        reason: VIX_INCREASE, EXPIRY_DAY, REGULATORY, etc.

    Usage:
        try:
            # This is raised by background margin monitor
            pass
        except MarginIncreasedException as e:
            print(f"Margin increased {e.change_pct}% due to {e.reason}")
            # Optionally close positions
            if e.change_pct > 20:
                client.strategies.square_off(strategy_id)
    """
    def __init__(
        self,
        message: str,
        old_margin: float,
        new_margin: float,
        change_pct: float,
        reason: str,
        **kwargs
    ):
        super().__init__(message, code="MARGIN_INCREASED", **kwargs)
        self.old_margin = old_margin
        self.new_margin = new_margin
        self.change_pct = change_pct
        self.reason = reason


# ============================================================================
# Risk Exceptions
# ============================================================================

class RiskException(SDKException):
    """Base exception for risk-related errors."""
    pass


class RiskLimitBreachException(RiskException):
    """
    Raised when a risk limit is breached.

    Attributes:
        limit_type: MAX_LOSS_PCT, MAX_MARGIN_UTILIZATION, etc.
        current_value: Current value
        limit_value: Configured limit
        action_taken: STOP_NEW_ORDERS, AUTO_SQUARE_OFF, etc.

    Usage:
        try:
            client.strategies.check_risk_limits(strategy_id)
        except RiskLimitBreachException as e:
            print(f"{e.limit_type} breached: {e.current_value} > {e.limit_value}")
            print(f"Action: {e.action_taken}")
    """
    def __init__(
        self,
        message: str,
        limit_type: str,
        current_value: float,
        limit_value: float,
        action_taken: str,
        **kwargs
    ):
        super().__init__(message, code="RISK_LIMIT_BREACH", **kwargs)
        self.limit_type = limit_type
        self.current_value = current_value
        self.limit_value = limit_value
        self.action_taken = action_taken


class GreeksRiskException(RiskException):
    """
    Raised when Greeks exceed risk thresholds.

    Attributes:
        delta_risk: LOW/MEDIUM/HIGH/EXTREME
        gamma_risk: LOW/MEDIUM/HIGH/EXTREME
        vega_risk: LOW/MEDIUM/HIGH/EXTREME
        net_delta: Net delta value
        net_gamma: Net gamma value
        net_vega: Net vega value
        recommendations: List of suggested actions

    Usage:
        try:
            client.strategies.check_greeks_risk(strategy_id)
        except GreeksRiskException as e:
            if e.delta_risk == 'HIGH':
                print(f"High delta exposure: {e.net_delta}")
                print("Recommendations:", e.recommendations)
    """
    def __init__(
        self,
        message: str,
        delta_risk: str,
        gamma_risk: str,
        vega_risk: str,
        net_delta: float,
        net_gamma: float,
        net_vega: float,
        recommendations: List[str],
        **kwargs
    ):
        super().__init__(message, code="GREEKS_RISK", **kwargs)
        self.delta_risk = delta_risk
        self.gamma_risk = gamma_risk
        self.vega_risk = vega_risk
        self.net_delta = net_delta
        self.net_gamma = net_gamma
        self.net_vega = net_vega
        self.recommendations = recommendations


# ============================================================================
# Housekeeping Exceptions
# ============================================================================

class HousekeepingException(SDKException):
    """Base exception for housekeeping errors."""
    pass


class OrphanedOrdersDetectedException(HousekeepingException):
    """
    Raised when orphaned orders are detected.

    Attributes:
        orphaned_orders: List of orphaned order IDs
        reason: POSITION_CLOSED, EXPIRED_INSTRUMENT, etc.
        auto_cleanup_enabled: Whether auto-cleanup will run

    Usage:
        try:
            # Raised by background housekeeping worker
            pass
        except OrphanedOrdersDetectedException as e:
            print(f"Found {len(e.orphaned_orders)} orphaned orders")
            if not e.auto_cleanup_enabled:
                # Manually cleanup
                for order_id in e.orphaned_orders:
                    client.orders.cancel(order_id)
    """
    def __init__(
        self,
        message: str,
        orphaned_orders: List[int],
        reason: str,
        auto_cleanup_enabled: bool,
        **kwargs
    ):
        super().__init__(message, code="ORPHANED_ORDERS", **kwargs)
        self.orphaned_orders = orphaned_orders
        self.reason = reason
        self.auto_cleanup_enabled = auto_cleanup_enabled


# ============================================================================
# Validation Exceptions
# ============================================================================

class ValidationException(SDKException):
    """Base exception for validation errors."""
    pass


class DuplicateOrderException(ValidationException):
    """
    Raised when duplicate order is detected.

    Attributes:
        original_order_id: ID of original order
        reason: IDEMPOTENCY_KEY, IDENTICAL_ORDER_WITHIN_5_SEC

    Usage:
        try:
            client.orders.place(order)
        except DuplicateOrderException as e:
            print(f"Duplicate of order {e.original_order_id}")
            # Skip or modify order
    """
    def __init__(
        self,
        message: str,
        original_order_id: int,
        reason: str,
        **kwargs
    ):
        super().__init__(message, code="DUPLICATE_ORDER", **kwargs)
        self.original_order_id = original_order_id
        self.reason = reason


class PositionSizeExceedsRecommendationException(ValidationException):
    """
    Raised when position size exceeds liquidity-based recommendation.

    Attributes:
        requested_quantity: What user wants
        recommended_quantity: Safe position size
        liquidity_tier: HIGH/MEDIUM/LOW/ILLIQUID

    Usage:
        try:
            client.strategies.add_position(symbol, 500)
        except PositionSizeExceedsRecommendationException as e:
            print(f"Recommended max: {e.recommended_quantity} lots")
            # User can override
            if confirm("Proceed with {e.requested_quantity}?"):
                client.strategies.add_position(symbol, 500, force=True)
    """
    def __init__(
        self,
        message: str,
        requested_quantity: int,
        recommended_quantity: int,
        liquidity_tier: str,
        **kwargs
    ):
        super().__init__(message, code="POSITION_SIZE_EXCEEDS_REC", **kwargs)
        self.requested_quantity = requested_quantity
        self.recommended_quantity = recommended_quantity
        self.liquidity_tier = liquidity_tier
```

---

## 3. Alert System

### 3.1 Alert Models

```python
# stocksblitz_sdk/alerts.py

from enum import Enum
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from datetime import datetime

class AlertSeverity(Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    URGENT = "urgent"


class AlertType(Enum):
    """Alert types."""
    WIDE_SPREAD = "WIDE_SPREAD"
    HIGH_IMPACT = "HIGH_IMPACT"
    MARGIN_WARNING = "MARGIN_WARNING"
    MARGIN_SHORTFALL = "MARGIN_SHORTFALL"
    RISK_BREACH = "RISK_BREACH"
    ORPHANED_ORDER = "ORPHANED_ORDER"
    GREEKS_RISK = "GREEKS_RISK"
    MARGIN_INCREASED = "MARGIN_INCREASED"
    EXPIRY_DAY_WARNING = "EXPIRY_DAY_WARNING"
    SETTLEMENT_COMPLETE = "SETTLEMENT_COMPLETE"


@dataclass
class Alert:
    """
    Base alert class.

    All alerts have:
    - id: Unique alert ID
    - type: Alert type
    - severity: Severity level
    - title: Short title
    - message: Detailed message
    - data: Additional data (dict)
    - actions: Available actions (list)
    - timestamp: When alert was created
    - expires_at: When alert expires
    """
    id: int
    type: AlertType
    severity: AlertSeverity
    title: str
    message: str
    data: Dict[str, Any]
    actions: List[str]
    timestamp: datetime
    expires_at: Optional[datetime] = None

    def __str__(self):
        return f"[{self.severity.value.upper()}] {self.title}: {self.message}"


@dataclass
class WideSpreadAlert(Alert):
    """Alert for wide bid-ask spread."""
    spread_pct: float
    spread_abs: float
    estimated_slippage: float

    @classmethod
    def create(
        cls,
        spread_pct: float,
        spread_abs: float,
        estimated_slippage: float
    ):
        return cls(
            id=None,  # Set by backend
            type=AlertType.WIDE_SPREAD,
            severity=AlertSeverity.WARNING,
            title="Wide Bid-Ask Spread Detected",
            message=f"Spread is {spread_pct:.2f}% (₹{spread_abs:.2f}). "
                    f"Estimated slippage: ₹{estimated_slippage:.0f}",
            data={
                "spread_pct": spread_pct,
                "spread_abs": spread_abs,
                "estimated_slippage": estimated_slippage
            },
            actions=["PROCEED_MARKET", "USE_LIMIT_ORDER", "CANCEL"],
            timestamp=datetime.now(),
            spread_pct=spread_pct,
            spread_abs=spread_abs,
            estimated_slippage=estimated_slippage
        )


@dataclass
class MarginWarningAlert(Alert):
    """Alert for high margin utilization."""
    utilization_pct: float
    required_margin: float
    available_margin: float

    @classmethod
    def create(
        cls,
        utilization_pct: float,
        required_margin: float,
        available_margin: float
    ):
        severity = (
            AlertSeverity.INFO if utilization_pct < 80
            else AlertSeverity.WARNING if utilization_pct < 90
            else AlertSeverity.CRITICAL
        )

        return cls(
            id=None,
            type=AlertType.MARGIN_WARNING,
            severity=severity,
            title="High Margin Utilization",
            message=f"Margin utilization at {utilization_pct:.1f}%. "
                    f"Consider adding funds or reducing positions.",
            data={
                "utilization_pct": utilization_pct,
                "required_margin": required_margin,
                "available_margin": available_margin
            },
            actions=["ADD_FUNDS", "REDUCE_POSITIONS", "VIEW_DETAILS"],
            timestamp=datetime.now(),
            utilization_pct=utilization_pct,
            required_margin=required_margin,
            available_margin=available_margin
        )


@dataclass
class MarginShortfallAlert(Alert):
    """Alert for margin shortfall."""
    shortfall: float
    deadline: datetime

    @classmethod
    def create(
        cls,
        shortfall: float,
        required_margin: float,
        available_margin: float,
        deadline: datetime
    ):
        return cls(
            id=None,
            type=AlertType.MARGIN_SHORTFALL,
            severity=AlertSeverity.URGENT,
            title="Margin Shortfall",
            message=f"Margin shortfall of ₹{shortfall:,.0f}. "
                    f"Please add funds by {deadline.strftime('%I:%M %p')}.",
            data={
                "shortfall": shortfall,
                "required_margin": required_margin,
                "available_margin": available_margin,
                "deadline": deadline.isoformat()
            },
            actions=["ADD_FUNDS", "SQUARE_OFF_POSITIONS", "REDUCE_POSITIONS"],
            timestamp=datetime.now(),
            expires_at=deadline,
            shortfall=shortfall,
            deadline=deadline
        )


@dataclass
class RiskBreachAlert(Alert):
    """Alert for risk limit breach."""
    limit_type: str
    current_value: float
    limit_value: float
    action_taken: str

    @classmethod
    def create(
        cls,
        limit_type: str,
        current_value: float,
        limit_value: float,
        action_taken: str
    ):
        return cls(
            id=None,
            type=AlertType.RISK_BREACH,
            severity=AlertSeverity.CRITICAL,
            title=f"{limit_type} Limit Breached",
            message=f"{limit_type}: {current_value:.1f} exceeds limit {limit_value:.1f}. "
                    f"Action: {action_taken}",
            data={
                "limit_type": limit_type,
                "current_value": current_value,
                "limit_value": limit_value,
                "action_taken": action_taken
            },
            actions=["VIEW_DETAILS", "ACKNOWLEDGE"],
            timestamp=datetime.now(),
            limit_type=limit_type,
            current_value=current_value,
            limit_value=limit_value,
            action_taken=action_taken
        )
```

### 3.2 Alert Manager

```python
# stocksblitz_sdk/managers/alert_manager.py

class AlertManager:
    """
    Manage alerts and notifications.
    """

    def __init__(self, client):
        self.client = client
        self._handlers = {}

    def subscribe(
        self,
        alert_type: AlertType,
        handler: Callable[[Alert], None]
    ):
        """
        Subscribe to specific alert type.

        Usage:
            def handle_margin_warning(alert: MarginWarningAlert):
                if alert.utilization_pct > 90:
                    # Add funds automatically
                    client.margin.add_funds(10000)

            client.alerts.subscribe(
                AlertType.MARGIN_WARNING,
                handle_margin_warning
            )
        """
        if alert_type not in self._handlers:
            self._handlers[alert_type] = []

        self._handlers[alert_type].append(handler)

    def emit(self, alert: Alert):
        """Emit alert to all registered handlers."""
        handlers = self._handlers.get(alert.type, [])
        for handler in handlers:
            try:
                handler(alert)
            except Exception as e:
                logger.error(f"Alert handler error: {e}")

    async def get_active_alerts(
        self,
        strategy_id: Optional[int] = None
    ) -> List[Alert]:
        """Get all active alerts."""
        # Call backend API
        pass

    async def respond_to_alert(
        self,
        alert_id: int,
        action: str
    ):
        """
        Respond to an alert with chosen action.

        Usage:
            alert = client.alerts.get_active_alerts()[0]
            client.alerts.respond_to_alert(
                alert.id,
                action="USE_LIMIT_ORDER"
            )
        """
        # Call backend API
        pass

    async def dismiss_alert(self, alert_id: int):
        """Mark alert as read/dismissed."""
        # Call backend API
        pass
```

---

## 4. SDK Usage Examples

### 4.1 Order Placement with Exception Handling

```python
# Example 1: Basic order with spread checking

from stocksblitz_sdk import StocksBlitzClient
from stocksblitz_sdk.exceptions import (
    WideSpreadException,
    HighMarketImpactException,
    InsufficientLiquidityException
)

client = StocksBlitzClient(
    api_url="https://api.stocksblitz.com",
    api_key="your_key"
)

try:
    # Place order - SDK automatically checks spread, liquidity, impact
    order = client.orders.place_market(
        instrument_token=12345,
        quantity=100,
        side="BUY"
    )
    print(f"Order placed: {order.id}")

except WideSpreadException as e:
    # Spread too wide - use limit order instead
    print(f"⚠️  {e.message}")
    print(f"Spread: {e.spread_pct}% (threshold: {e.threshold}%)")

    if e.recommended_action == "USE_LIMIT_ORDER":
        # Place limit order at mid-price
        depth = client.orders.get_market_depth(12345)
        mid_price = (depth.best_bid + depth.best_ask) / 2

        order = client.orders.place_limit(
            instrument_token=12345,
            quantity=100,
            side="BUY",
            price=mid_price
        )
        print(f"✅ Limit order placed at ₹{mid_price}")

except HighMarketImpactException as e:
    # High market impact - use TWAP
    print(f"⚠️  {e.message}")
    print(f"Impact: {e.impact_bps} bps (₹{e.impact_cost})")

    if e.recommended_action == "USE_TWAP":
        # Use TWAP over 30 minutes
        order = client.orders.place_twap(
            instrument_token=12345,
            quantity=100,
            side="BUY",
            duration_minutes=30
        )
        print(f"✅ TWAP order initiated")

except InsufficientLiquidityException as e:
    # Not enough liquidity
    print(f"❌ {e.message}")
    print(f"Available: {e.available_quantity} lots")

    # Reduce quantity or cancel
    if e.available_quantity > 0:
        order = client.orders.place_market(
            instrument_token=12345,
            quantity=e.available_quantity,
            side="BUY"
        )
```

### 4.2 Strategy Management with Margin Alerts

```python
# Example 2: Create strategy with margin monitoring

from stocksblitz_sdk.exceptions import MarginShortfallException

client = StocksBlitzClient(api_url="...", api_key="...")

# Subscribe to margin alerts
def handle_margin_alert(alert):
    print(f"📊 Margin Alert: {alert.message}")
    if alert.severity == AlertSeverity.URGENT:
        # Send notification
        send_sms(f"URGENT: {alert.message}")

client.on_margin_warning(handle_margin_alert)

# Create strategy
strategy = client.strategies.create("NIFTY Iron Condor")

try:
    # Add positions
    strategy.add_position(
        tradingsymbol="NIFTY25DEC24500CE",
        quantity=100,
        side="SELL",
        entry_price=150.50
    )

    strategy.add_position(
        tradingsymbol="NIFTY25DEC24700CE",
        quantity=100,
        side="BUY",
        entry_price=80.25
    )

except MarginShortfallException as e:
    print(f"❌ Margin shortfall: ₹{e.shortfall}")
    print(f"Required: ₹{e.required_margin}")
    print(f"Available: ₹{e.available_margin}")
    print(f"Deadline: {e.deadline}")

    # Add funds
    client.margin.add_funds_request(e.shortfall)
```

### 4.3 Risk Monitoring

```python
# Example 3: Monitor Greeks and risk limits

from stocksblitz_sdk.exceptions import (
    GreeksRiskException,
    RiskLimitBreachException
)

# Subscribe to risk alerts
client.on_risk_breach(lambda alert: print(f"🚨 {alert.message}"))

# Enable auto square-off on loss limit
strategy = client.strategies.get(strategy_id=100)
strategy.configure_risk(
    max_loss_pct=10.0,
    auto_square_off_on_loss_limit=True
)

# Check Greeks periodically
try:
    greeks = strategy.get_greeks()
    print(f"Delta: {greeks.net_delta:.3f}")
    print(f"Gamma: {greeks.net_gamma:.5f}")
    print(f"Vega: ₹{greeks.net_vega:.0f}")

except GreeksRiskException as e:
    print(f"⚠️  Greeks Risk Alert")
    print(f"Delta risk: {e.delta_risk} (net delta: {e.net_delta:.3f})")
    print(f"Recommendations: {', '.join(e.recommendations)}")

    # Implement recommendations
    if "Add opposite delta position" in e.recommendations:
        # Add hedging position
        pass
```

### 4.4 Housekeeping Events

```python
# Example 4: Handle orphaned orders

from stocksblitz_sdk.exceptions import OrphanedOrdersDetectedException

# Subscribe to orphaned order events
def handle_orphaned_orders(alert):
    print(f"Found {len(alert.orphaned_orders)} orphaned orders")
    print(f"Reason: {alert.reason}")

    if not alert.auto_cleanup_enabled:
        # Manual cleanup
        for order_id in alert.orphaned_orders:
            print(f"Cancelling order {order_id}")
            client.orders.cancel(order_id)

client.on_orphaned_order(handle_orphaned_orders)

# Enable auto-cleanup
client.enable_auto_housekeeping()

# When position is closed, orphaned SL/Target orders are auto-cancelled
strategy.close_position(position_id=123)
# ✅ Associated SL and Target orders automatically cancelled
```

### 4.5 Pre-Trade Cost Calculation

```python
# Example 5: Calculate costs before placing order

# Get pre-trade cost breakdown
cost_breakdown = client.orders.calculate_costs(
    instrument_token=12345,
    quantity=100,
    side="BUY",
    price=150.50
)

print("📊 Pre-Trade Cost Breakdown:")
print(f"Order Value:      ₹{cost_breakdown.order_value:,.2f}")
print(f"Brokerage:        ₹{cost_breakdown.brokerage:,.2f}")
print(f"STT:              ₹{cost_breakdown.stt:,.2f}")
print(f"Exchange Charges: ₹{cost_breakdown.exchange_charges:,.2f}")
print(f"GST:              ₹{cost_breakdown.gst:,.2f}")
print(f"SEBI Charges:     ₹{cost_breakdown.sebi_charges:,.2f}")
print(f"Stamp Duty:       ₹{cost_breakdown.stamp_duty:,.2f}")
print(f"───────────────────────────────")
print(f"Total Charges:    ₹{cost_breakdown.total_charges:,.2f}")
print(f"Net Cost:         ₹{cost_breakdown.net_cost:,.2f}")

# Get margin requirement
margin = client.margin.calculate_for_order(
    instrument_token=12345,
    quantity=100,
    side="BUY"
)

print(f"\n💰 Margin Required: ₹{margin.total:,.2f}")
print(f"   SPAN:     ₹{margin.span:,.2f}")
print(f"   Exposure: ₹{margin.exposure:,.2f}")
print(f"   Premium:  ₹{margin.premium:,.2f}")

# Confirm before placing
if confirm("Proceed with order?"):
    client.orders.place(...)
```

---

## 5. Event Handlers

### 5.1 Event Types

```python
# stocksblitz_sdk/events/handlers.py

from enum import Enum

class EventType(Enum):
    """SDK event types."""
    # Alerts
    ALERT = "alert"
    MARGIN_WARNING = "margin_warning"
    MARGIN_SHORTFALL = "margin_shortfall"
    RISK_BREACH = "risk_breach"
    ORPHANED_ORDER = "orphaned_order"
    GREEKS_RISK = "greeks_risk"

    # Order events
    ORDER_PLACED = "order_placed"
    ORDER_FILLED = "order_filled"
    ORDER_CANCELLED = "order_cancelled"
    ORDER_REJECTED = "order_rejected"

    # Margin events
    MARGIN_INCREASED = "margin_increased"
    SETTLEMENT_COMPLETE = "settlement_complete"

    # Housekeeping events
    HOUSEKEEPING_COMPLETE = "housekeeping_complete"
    CLEANUP_PERFORMED = "cleanup_performed"


class EventEmitter:
    """Event emitter for SDK events."""

    def __init__(self):
        self._handlers = {}

    def on(self, event_type: str, handler: Callable):
        """Register event handler."""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)

    def emit(self, event_type: str, data: Any):
        """Emit event to all registered handlers."""
        handlers = self._handlers.get(event_type, [])
        for handler in handlers:
            try:
                handler(data)
            except Exception as e:
                logger.error(f"Event handler error for {event_type}: {e}")

    def off(self, event_type: str, handler: Callable):
        """Unregister event handler."""
        if event_type in self._handlers:
            self._handlers[event_type].remove(handler)
```

### 5.2 Usage Example

```python
# Event-driven trading bot

client = StocksBlitzClient(...)

# Register handlers for all events
client.events.on(EventType.ORDER_FILLED.value, lambda order:
    print(f"✅ Order {order.id} filled at ₹{order.average_price}"))

client.events.on(EventType.ORDER_REJECTED.value, lambda order:
    print(f"❌ Order {order.id} rejected: {order.rejection_reason}"))

client.events.on(EventType.MARGIN_WARNING.value, lambda alert:
    send_sms(f"Margin at {alert.utilization_pct}%"))

client.events.on(EventType.RISK_BREACH.value, lambda alert:
    # Auto square-off
    client.strategies.square_off_all())

# Start event loop
client.run()
```

---

## 6. Configuration

### 6.1 SDK Configuration

```python
# stocksblitz_sdk/config.py

@dataclass
class SDKConfig:
    """SDK configuration."""

    # API settings
    api_url: str
    api_key: str
    timeout: int = 30

    # Feature flags
    auto_housekeeping: bool = True
    margin_monitoring: bool = True
    risk_alerts: bool = True

    # Thresholds
    max_spread_pct: float = 0.5          # 0.5% max spread before alert
    max_impact_bps: int = 50             # 50 bps max impact before alert
    min_liquidity_score: int = 50        # Minimum liquidity score (0-100)

    # Risk limits (can be overridden per strategy)
    max_loss_pct: float = 10.0           # 10% max loss
    max_margin_utilization_pct: float = 90.0  # 90% max margin usage

    # Housekeeping settings
    cleanup_orphaned_orders: bool = True
    cleanup_expired_instruments: bool = True
    auto_square_off_mis: bool = True     # Auto square-off MIS at 3:20 PM

    # Margin monitoring
    margin_check_interval_seconds: int = 300  # Check every 5 minutes
    margin_change_alert_threshold_pct: float = 10.0  # Alert if margin changes > 10%

# Usage
config = SDKConfig(
    api_url="https://api.stocksblitz.com",
    api_key="your_key",
    max_spread_pct=0.3,  # More conservative
    max_loss_pct=5.0     # Tighter risk limit
)

client = StocksBlitzClient(config=config)
```

---

## 7. UI Integration

### 7.1 Alert Components (to be implemented in frontend)

All alerts from SDK should be displayed in the UI with proper severity colors and actions.

```typescript
// Alert UI Component (React)

interface AlertProps {
  alert: Alert;
  onAction: (action: string) => void;
  onDismiss: () => void;
}

export const AlertCard: React.FC<AlertProps> = ({ alert, onAction, onDismiss }) => {
  const severityColors = {
    info: 'blue',
    warning: 'yellow',
    critical: 'orange',
    urgent: 'red'
  };

  return (
    <div className={`alert alert-${severityColors[alert.severity]}`}>
      <div className="alert-header">
        <Icon type={alert.type} />
        <h4>{alert.title}</h4>
        <button onClick={onDismiss}>×</button>
      </div>

      <div className="alert-body">
        <p>{alert.message}</p>

        {/* Spread alert details */}
        {alert.type === 'WIDE_SPREAD' && (
          <div className="alert-details">
            <div>Spread: {alert.spread_pct}%</div>
            <div>Estimated Slippage: ₹{alert.estimated_slippage}</div>
          </div>
        )}

        {/* Margin alert details */}
        {alert.type === 'MARGIN_SHORTFALL' && (
          <div className="alert-details">
            <div>Shortfall: ₹{alert.shortfall}</div>
            <div>Deadline: {alert.deadline}</div>
          </div>
        )}
      </div>

      <div className="alert-actions">
        {alert.actions.map(action => (
          <button key={action} onClick={() => onAction(action)}>
            {formatAction(action)}
          </button>
        ))}
      </div>
    </div>
  );
};
```

---

## Summary

This SDK provides:

✅ **Clean Python API** with exception hierarchy
✅ **Alert system** with event handlers
✅ **Type-safe models** using dataclasses
✅ **Event-driven architecture**
✅ **Easy integration** with UI
✅ **Comprehensive error handling**

All features (housekeeping, margin monitoring, risk alerts, etc.) are exposed through:
1. **Exceptions**: For synchronous operations
2. **Alerts**: For asynchronous events
3. **Event handlers**: For background monitoring

The UI can subscribe to SDK events and display alerts in real-time! 🚀
