"""
Alert Service - Event-based alert system.

Provides functionality to raise and catch alerts based on price, indicators,
positions, and custom events.
"""

import uuid
import threading
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime
from collections import defaultdict

from ..enums import AlertType, AlertPriority, EventStatus
from ..types import AlertEvent, AlertCallback
from ..exceptions import APIError


class AlertService:
    """
    Event-based alert service.

    Allows users to:
    - Raise alerts based on conditions
    - Register callbacks to catch alerts
    - Query alert history
    - Manage alert lifecycle

    Examples:
        # Create alert service
        alerts = client.alerts

        # Register callback
        def on_price_alert(event: AlertEvent):
            print(f"Price alert: {event.symbol} - {event.message}")
            event.acknowledge()

        alerts.on(AlertType.PRICE, on_price_alert)

        # Raise alert
        alerts.raise_alert(
            alert_type=AlertType.PRICE,
            priority=AlertPriority.HIGH,
            symbol="NIFTY50",
            message="Price above 24000"
        )

        # Create conditional alert
        alerts.create_price_alert(
            symbol="NIFTY50",
            condition=lambda price: price > 24000,
            message="NIFTY above 24000"
        )
    """

    def __init__(self, api_client: 'APIClient'):
        """Initialize alert service."""
        self._api = api_client
        self._alerts: Dict[str, AlertEvent] = {}
        self._callbacks: Dict[AlertType, List[AlertCallback]] = defaultdict(list)
        self._lock = threading.Lock()
        self._monitoring = False
        self._monitor_thread: Optional[threading.Thread] = None

    def raise_alert(
        self,
        alert_type: AlertType,
        priority: AlertPriority = AlertPriority.MEDIUM,
        symbol: Optional[str] = None,
        message: str = "",
        data: Optional[Dict[str, Any]] = None
    ) -> AlertEvent:
        """
        Raise a new alert event.

        Args:
            alert_type: Type of alert
            priority: Alert priority
            symbol: Associated symbol (optional)
            message: Alert message
            data: Additional data

        Returns:
            AlertEvent object

        Example:
            alert = alerts.raise_alert(
                alert_type=AlertType.PRICE,
                priority=AlertPriority.HIGH,
                symbol="NIFTY50",
                message="Price crossed 24000",
                data={"price": 24050, "threshold": 24000}
            )
        """
        alert_id = str(uuid.uuid4())
        event = AlertEvent(
            alert_id=alert_id,
            alert_type=alert_type,
            priority=priority,
            status=EventStatus.TRIGGERED,
            symbol=symbol,
            message=message,
            data=data or {},
            triggered_at=datetime.now()
        )

        with self._lock:
            self._alerts[alert_id] = event

        # Trigger callbacks
        self._trigger_callbacks(event)

        return event

    def on(
        self,
        alert_type: AlertType,
        callback: AlertCallback
    ) -> None:
        """
        Register callback for alert type.

        Args:
            alert_type: Type of alert to listen for
            callback: Callback function (receives AlertEvent)

        Example:
            def my_handler(event: AlertEvent):
                print(f"Alert: {event.message}")
                event.acknowledge()

            alerts.on(AlertType.PRICE, my_handler)
        """
        with self._lock:
            self._callbacks[alert_type].append(callback)

    def off(
        self,
        alert_type: AlertType,
        callback: Optional[AlertCallback] = None
    ) -> None:
        """
        Unregister callback(s) for alert type.

        Args:
            alert_type: Type of alert
            callback: Specific callback to remove (or None to remove all)

        Example:
            alerts.off(AlertType.PRICE)  # Remove all
            alerts.off(AlertType.PRICE, my_handler)  # Remove specific
        """
        with self._lock:
            if callback is None:
                self._callbacks[alert_type].clear()
            else:
                self._callbacks[alert_type].remove(callback)

    def _trigger_callbacks(self, event: AlertEvent) -> None:
        """Trigger all registered callbacks for event type."""
        callbacks = self._callbacks.get(event.alert_type, [])
        for callback in callbacks:
            try:
                callback(event)
            except Exception as e:
                # Log error but don't stop other callbacks
                print(f"Error in alert callback: {e}")

    def create_price_alert(
        self,
        symbol: str,
        condition: Callable[[float], bool],
        message: str = "",
        priority: AlertPriority = AlertPriority.MEDIUM
    ) -> str:
        """
        Create price-based alert (monitors in background).

        Args:
            symbol: Symbol to monitor
            condition: Condition function (receives price, returns bool)
            message: Alert message
            priority: Alert priority

        Returns:
            Alert ID

        Example:
            # Alert when NIFTY > 24000
            alert_id = alerts.create_price_alert(
                symbol="NIFTY50",
                condition=lambda price: price > 24000,
                message="NIFTY crossed 24000"
            )
        """
        # TODO: Implement background monitoring
        # For now, return stub alert ID
        alert_id = str(uuid.uuid4())
        return alert_id

    def create_indicator_alert(
        self,
        symbol: str,
        timeframe: str,
        indicator: str,
        condition: Callable[[float], bool],
        message: str = "",
        priority: AlertPriority = AlertPriority.MEDIUM
    ) -> str:
        """
        Create indicator-based alert.

        Args:
            symbol: Symbol to monitor
            timeframe: Timeframe (e.g., '5m')
            indicator: Indicator name (e.g., 'rsi[14]')
            condition: Condition function
            message: Alert message
            priority: Alert priority

        Returns:
            Alert ID

        Example:
            # Alert when RSI > 70
            alert_id = alerts.create_indicator_alert(
                symbol="NIFTY50",
                timeframe="5m",
                indicator="rsi[14]",
                condition=lambda rsi: rsi > 70,
                message="RSI overbought"
            )
        """
        # TODO: Implement background monitoring
        alert_id = str(uuid.uuid4())
        return alert_id

    def get_alert(self, alert_id: str) -> Optional[AlertEvent]:
        """Get alert by ID."""
        return self._alerts.get(alert_id)

    def get_alerts(
        self,
        alert_type: Optional[AlertType] = None,
        status: Optional[EventStatus] = None,
        priority: Optional[AlertPriority] = None,
        symbol: Optional[str] = None
    ) -> List[AlertEvent]:
        """
        Get alerts with optional filters.

        Args:
            alert_type: Filter by alert type
            status: Filter by status
            priority: Filter by priority
            symbol: Filter by symbol

        Returns:
            List of matching alerts

        Example:
            # Get all triggered high-priority alerts
            alerts_list = alerts.get_alerts(
                status=EventStatus.TRIGGERED,
                priority=AlertPriority.HIGH
            )
        """
        with self._lock:
            results = list(self._alerts.values())

        if alert_type:
            results = [a for a in results if a.alert_type == alert_type]
        if status:
            results = [a for a in results if a.status == status]
        if priority:
            results = [a for a in results if a.priority == priority]
        if symbol:
            results = [a for a in results if a.symbol == symbol]

        return results

    def acknowledge(self, alert_id: str) -> bool:
        """
        Acknowledge an alert.

        Args:
            alert_id: Alert ID

        Returns:
            True if acknowledged, False if not found
        """
        alert = self.get_alert(alert_id)
        if alert:
            alert.acknowledge()
            return True
        return False

    def clear_alerts(
        self,
        alert_type: Optional[AlertType] = None,
        status: Optional[EventStatus] = None
    ) -> int:
        """
        Clear alerts from history.

        Args:
            alert_type: Filter by type
            status: Filter by status

        Returns:
            Number of alerts cleared

        Example:
            # Clear all acknowledged alerts
            count = alerts.clear_alerts(status=EventStatus.ACKNOWLEDGED)
        """
        to_remove = self.get_alerts(alert_type=alert_type, status=status)
        count = 0

        with self._lock:
            for alert in to_remove:
                if alert.alert_id in self._alerts:
                    del self._alerts[alert.alert_id]
                    count += 1

        return count

    def start_monitoring(self) -> None:
        """
        Start background monitoring for conditional alerts.

        Example:
            alerts.start_monitoring()
        """
        if self._monitoring:
            return

        self._monitoring = True
        # TODO: Implement background monitoring thread
        # self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        # self._monitor_thread.start()

    def stop_monitoring(self) -> None:
        """Stop background monitoring."""
        self._monitoring = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)
            self._monitor_thread = None
