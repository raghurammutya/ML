"""
SDK Exceptions

Custom exception hierarchy for StocksBlitz SDK.
All exceptions provide structured error information for programmatic handling.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from decimal import Decimal


class SDKException(Exception):
    """Base exception for all SDK errors."""

    def __init__(
        self,
        message: str,
        code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.code = code or self.__class__.__name__.replace('Exception', '').upper()
        self.details = details or {}
        super().__init__(self.message)

    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for JSON serialization."""
        return {
            'error': self.__class__.__name__,
            'code': self.code,
            'message': self.message,
            'details': self.details
        }


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
        spread_pct (float): Spread as percentage
        spread_abs (float): Absolute spread value
        threshold (float): Configured threshold
        recommended_action (str): LIMIT_ORDER, CANCEL, WAIT

    Example:
        try:
            client.orders.place_market(symbol, 100)
        except WideSpreadException as e:
            print(f"Spread {e.spread_pct}% exceeds {e.threshold}%")
            # Use limit order instead
            client.orders.place_limit(symbol, 100, e.recommended_limit_price)
    """

    def __init__(
        self,
        message: str,
        spread_pct: float,
        spread_abs: float,
        threshold: float,
        recommended_action: str,
        recommended_limit_price: Optional[Decimal] = None,
        **kwargs
    ):
        super().__init__(message, code="WIDE_SPREAD", **kwargs)
        self.spread_pct = spread_pct
        self.spread_abs = spread_abs
        self.threshold = threshold
        self.recommended_action = recommended_action
        self.recommended_limit_price = recommended_limit_price
        self.details.update({
            'spread_pct': spread_pct,
            'spread_abs': spread_abs,
            'threshold': threshold,
            'recommended_action': recommended_action
        })


class HighMarketImpactException(OrderExecutionException):
    """
    Raised when order would cause high market impact.

    Attributes:
        impact_bps (int): Market impact in basis points
        impact_cost (float): Estimated cost in rupees
        threshold_bps (int): Configured threshold
        levels_consumed (int): Number of price levels consumed
        recommended_action (str): SPLIT_ORDER, USE_TWAP, REDUCE_QUANTITY

    Example:
        try:
            client.orders.place_market(symbol, 500)
        except HighMarketImpactException as e:
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
        self.details.update({
            'impact_bps': impact_bps,
            'impact_cost': impact_cost,
            'threshold_bps': threshold_bps,
            'levels_consumed': levels_consumed,
            'recommended_action': recommended_action
        })


class InsufficientLiquidityException(OrderExecutionException):
    """
    Raised when order cannot be filled due to insufficient liquidity.

    Attributes:
        requested_quantity (int): Quantity user wants
        available_quantity (int): Maximum available in order book
        liquidity_tier (str): HIGH/MEDIUM/LOW/ILLIQUID

    Example:
        try:
            client.orders.place(symbol, 1000)
        except InsufficientLiquidityException as e:
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
        self.details.update({
            'requested_quantity': requested_quantity,
            'available_quantity': available_quantity,
            'liquidity_tier': liquidity_tier
        })


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
        required_margin (float): Margin needed
        available_margin (float): Margin available
        shortfall (float): Deficit amount
        deadline (datetime): Time by which margin must be added

    Example:
        try:
            client.strategies.add_position(strategy_id, position)
        except MarginShortfallException as e:
            print(f"Shortfall: ₹{e.shortfall}")
            # Add funds
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
        self.details.update({
            'required_margin': required_margin,
            'available_margin': available_margin,
            'shortfall': shortfall,
            'deadline': deadline.isoformat() if deadline else None
        })


class MarginIncreasedException(MarginException):
    """
    Raised when margin requirement increases significantly.

    Attributes:
        old_margin (float): Previous margin
        new_margin (float): New margin
        change_pct (float): Percentage change
        reason (str): VIX_INCREASE, EXPIRY_DAY, REGULATORY, etc.

    Example:
        try:
            # Raised by background margin monitor
            pass
        except MarginIncreasedException as e:
            print(f"Margin increased {e.change_pct}% due to {e.reason}")
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
        self.details.update({
            'old_margin': old_margin,
            'new_margin': new_margin,
            'change_pct': change_pct,
            'reason': reason
        })


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
        limit_type (str): MAX_LOSS_PCT, MAX_MARGIN_UTILIZATION, etc.
        current_value (float): Current value
        limit_value (float): Configured limit
        action_taken (str): STOP_NEW_ORDERS, AUTO_SQUARE_OFF, etc.

    Example:
        try:
            client.strategies.check_risk_limits(strategy_id)
        except RiskLimitBreachException as e:
            print(f"{e.limit_type} breached: {e.current_value} > {e.limit_value}")
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
        self.details.update({
            'limit_type': limit_type,
            'current_value': current_value,
            'limit_value': limit_value,
            'action_taken': action_taken
        })


class GreeksRiskException(RiskException):
    """
    Raised when Greeks exceed risk thresholds.

    Attributes:
        delta_risk (str): LOW/MEDIUM/HIGH/EXTREME
        gamma_risk (str): LOW/MEDIUM/HIGH/EXTREME
        vega_risk (str): LOW/MEDIUM/HIGH/EXTREME
        net_delta (float): Net delta value
        net_gamma (float): Net gamma value
        net_vega (float): Net vega value
        recommendations (list): Suggested actions

    Example:
        try:
            client.strategies.check_greeks_risk(strategy_id)
        except GreeksRiskException as e:
            if e.delta_risk == 'HIGH':
                print(f"High delta: {e.net_delta}")
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
        self.details.update({
            'delta_risk': delta_risk,
            'gamma_risk': gamma_risk,
            'vega_risk': vega_risk,
            'net_delta': net_delta,
            'net_gamma': net_gamma,
            'net_vega': net_vega,
            'recommendations': recommendations
        })


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
        orphaned_orders (list): List of orphaned order IDs
        reason (str): POSITION_CLOSED, EXPIRED_INSTRUMENT, etc.
        auto_cleanup_enabled (bool): Whether auto-cleanup will run

    Example:
        try:
            # Raised by background housekeeping worker
            pass
        except OrphanedOrdersDetectedException as e:
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
        self.details.update({
            'orphaned_orders': orphaned_orders,
            'reason': reason,
            'auto_cleanup_enabled': auto_cleanup_enabled
        })


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
        original_order_id (int): ID of original order
        reason (str): IDEMPOTENCY_KEY, IDENTICAL_ORDER_WITHIN_5_SEC

    Example:
        try:
            client.orders.place(order)
        except DuplicateOrderException as e:
            print(f"Duplicate of order {e.original_order_id}")
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
        self.details.update({
            'original_order_id': original_order_id,
            'reason': reason
        })


class PositionSizeExceedsRecommendationException(ValidationException):
    """
    Raised when position size exceeds liquidity-based recommendation.

    Attributes:
        requested_quantity (int): What user wants
        recommended_quantity (int): Safe position size
        liquidity_tier (str): HIGH/MEDIUM/LOW/ILLIQUID

    Example:
        try:
            client.strategies.add_position(symbol, 500)
        except PositionSizeExceedsRecommendationException as e:
            print(f"Recommended max: {e.recommended_quantity} lots")
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
        self.details.update({
            'requested_quantity': requested_quantity,
            'recommended_quantity': recommended_quantity,
            'liquidity_tier': liquidity_tier
        })
