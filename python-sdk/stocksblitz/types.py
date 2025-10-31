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
    """Option greeks data."""
    symbol: str
    delta: float
    gamma: float
    theta: float
    vega: float
    iv: float  # Implied Volatility
    timestamp: datetime = field(default_factory=datetime.now)
