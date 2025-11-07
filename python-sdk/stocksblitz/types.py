"""
Type definitions for StocksBlitz SDK.

Provides type aliases and data models for better type safety.
"""

from typing import Dict, List, Optional, Union, Callable, Any
from datetime import datetime
from dataclasses import dataclass, field
from .enums import (
    AlertType, AlertPriority, EventStatus,
    MessageType, ReminderFrequency, NewsCategory, NewsSentiment
)


# Type aliases
InstrumentSpec = Union[str, 'Instrument']
AlertCallback = Callable[['AlertEvent'], None]
MessageCallback = Callable[['Message'], None]
NewsCallback = Callable[['NewsItem'], None]


@dataclass
class AlertEvent:
    """Alert event data."""
    alert_id: str
    alert_type: AlertType
    priority: AlertPriority
    status: EventStatus
    symbol: Optional[str] = None
    message: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    triggered_at: Optional[datetime] = None
    acknowledged_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.now)

    def acknowledge(self) -> None:
        """Mark alert as acknowledged."""
        self.status = EventStatus.ACKNOWLEDGED
        self.acknowledged_at = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'alert_id': self.alert_id,
            'alert_type': self.alert_type.value,
            'priority': self.priority.value,
            'status': self.status.value,
            'symbol': self.symbol,
            'message': self.message,
            'data': self.data,
            'triggered_at': self.triggered_at.isoformat() if self.triggered_at else None,
            'acknowledged_at': self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            'created_at': self.created_at.isoformat(),
        }


@dataclass
class Message:
    """Message data."""
    message_id: str
    message_type: MessageType
    content: Union[str, bytes, Dict[str, Any]]
    sender: Optional[str] = None
    recipient: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    sent_at: datetime = field(default_factory=datetime.now)
    read_at: Optional[datetime] = None

    def mark_as_read(self) -> None:
        """Mark message as read."""
        self.read_at = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'message_id': self.message_id,
            'message_type': self.message_type.value,
            'content': self.content,
            'sender': self.sender,
            'recipient': self.recipient,
            'metadata': self.metadata,
            'sent_at': self.sent_at.isoformat(),
            'read_at': self.read_at.isoformat() if self.read_at else None,
        }


@dataclass
class Reminder:
    """Reminder/calendar event data."""
    reminder_id: str
    title: str
    description: str = ""
    frequency: ReminderFrequency = ReminderFrequency.ONCE
    scheduled_at: datetime = field(default_factory=datetime.now)
    next_trigger: Optional[datetime] = None
    last_triggered: Optional[datetime] = None
    enabled: bool = True
    callback: Optional[Callable] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def trigger(self) -> None:
        """Trigger the reminder."""
        self.last_triggered = datetime.now()
        if self.callback:
            self.callback(self)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'reminder_id': self.reminder_id,
            'title': self.title,
            'description': self.description,
            'frequency': self.frequency.value,
            'scheduled_at': self.scheduled_at.isoformat(),
            'next_trigger': self.next_trigger.isoformat() if self.next_trigger else None,
            'last_triggered': self.last_triggered.isoformat() if self.last_triggered else None,
            'enabled': self.enabled,
            'metadata': self.metadata,
        }


@dataclass
class NewsItem:
    """News item data."""
    news_id: str
    category: NewsCategory
    title: str
    content: str
    source: str
    sentiment: Optional[NewsSentiment] = None
    sentiment_score: Optional[float] = None  # -1.0 to 1.0
    symbols: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    url: Optional[str] = None
    published_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'news_id': self.news_id,
            'category': self.category.value,
            'title': self.title,
            'content': self.content,
            'source': self.source,
            'sentiment': self.sentiment.value if self.sentiment else None,
            'sentiment_score': self.sentiment_score,
            'symbols': self.symbols,
            'tags': self.tags,
            'url': self.url,
            'published_at': self.published_at.isoformat(),
            'metadata': self.metadata,
        }


@dataclass
class OrderRequest:
    """Order request data."""
    tradingsymbol: str
    transaction_type: str  # BUY/SELL
    quantity: int
    order_type: str = "MARKET"
    product: str = "MIS"
    price: Optional[float] = None
    trigger_price: Optional[float] = None
    validity: str = "DAY"
    disclosed_quantity: int = 0
    tag: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API."""
        data = {
            'tradingsymbol': self.tradingsymbol,
            'transaction_type': self.transaction_type,
            'quantity': self.quantity,
            'order_type': self.order_type,
            'product': self.product,
            'validity': self.validity,
            'disclosed_quantity': self.disclosed_quantity,
        }
        if self.price is not None:
            data['price'] = self.price
        if self.trigger_price is not None:
            data['trigger_price'] = self.trigger_price
        if self.tag:
            data['tag'] = self.tag
        return data


@dataclass
class QuoteData:
    """Market quote data."""
    symbol: str
    ltp: float
    volume: int
    oi: int
    bid: Optional[float] = None
    ask: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    open: Optional[float] = None
    close: Optional[float] = None
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class GreeksData:
    """Option greeks data with enhanced metrics."""
    symbol: str
    delta: float
    gamma: float
    theta: float
    vega: float
    iv: float  # Implied Volatility
    # Enhanced Greeks
    rho: float = 0.0  # Sensitivity to 1% interest rate change
    intrinsic_value: float = 0.0  # max(S-K, 0) for calls, max(K-S, 0) for puts
    extrinsic_value: float = 0.0  # Time value (option_price - intrinsic_value)
    model_price: float = 0.0  # Black-Scholes theoretical price
    theta_daily: float = 0.0  # Daily theta decay (annual theta / 365)
    # Premium metrics (computed)
    premium_abs: Optional[float] = None  # Absolute premium/discount vs model price
    premium_pct: Optional[float] = None  # Percentage premium/discount
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class DepthLevel:
    """Single level in order book."""
    quantity: int
    price: float
    orders: int


@dataclass
class MarketDepth:
    """Market depth data with microstructure metrics."""
    buy_levels: List[DepthLevel]
    sell_levels: List[DepthLevel]
    total_buy_quantity: int
    total_sell_quantity: int
    microprice: Optional[float] = None  # Volume-weighted fair value
    spread_abs: Optional[float] = None  # Absolute bid-ask spread
    spread_pct: Optional[float] = None  # Spread as % of mid-price
    imbalance_pct: Optional[float] = None  # Order book imbalance %
    book_pressure: Optional[float] = None  # Normalized buy/sell pressure (-1 to 1)


@dataclass
class LiquidityMetrics:
    """Liquidity metrics for instruments."""
    score: float  # 0-100 composite liquidity score
    tier: str  # HIGH/MEDIUM/LOW/ILLIQUID
    is_illiquid: bool  # True if illiquid for >50% of period
    spread_pct_avg: Optional[float] = None  # Average spread %
    spread_pct_max: Optional[float] = None  # Maximum spread % (worst case)
    depth_at_best_bid: Optional[int] = None  # Average depth at best bid
    depth_at_best_ask: Optional[int] = None  # Average depth at best ask
    market_impact_100: Optional[float] = None  # Expected slippage for 100-unit order
    illiquid_tick_count: Optional[int] = None  # Number of ticks with low liquidity
    total_tick_count: Optional[int] = None  # Total ticks in period


@dataclass
class FuturesPosition:
    """Futures position signal analysis."""
    symbol: str
    signal: str  # LONG_BUILDUP, SHORT_BUILDUP, LONG_UNWINDING, SHORT_UNWINDING
    strength: float  # Magnitude of combined price + OI movement (0-100+)
    sentiment: str  # BULLISH, BEARISH, or NEUTRAL
    price_change_pct: float
    oi_change_pct: float
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class RolloverMetrics:
    """Futures rollover analysis."""
    symbol: str
    expiry: str
    pressure: float  # Urgency score (0-100) for rolling positions
    oi_pct: float  # % of total OI across all expiries
    days_to_expiry: int
    status: str  # HIGH, MEDIUM, LOW, or EXPIRED
    recommended_target: Optional[str] = None  # Suggested expiry to roll into
    timestamp: datetime = field(default_factory=datetime.now)
