"""
Enumerations for StocksBlitz SDK.

Provides type-safe constants for orders, transactions, and other operations.
"""

from enum import Enum


class Exchange(str, Enum):
    """Supported exchanges."""
    NSE = "NSE"
    BSE = "BSE"
    NFO = "NFO"  # NSE Futures & Options
    BFO = "BFO"  # BSE Futures & Options
    CDS = "CDS"  # Currency Derivatives
    MCX = "MCX"  # Commodity Exchange


class TransactionType(str, Enum):
    """Order transaction type."""
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    """Order type."""
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    SL = "SL"  # Stop Loss
    SL_M = "SL-M"  # Stop Loss Market


class ProductType(str, Enum):
    """Product type for orders."""
    CNC = "CNC"  # Cash and Carry (Delivery)
    MIS = "MIS"  # Margin Intraday Square-off
    NRML = "NRML"  # Normal (Overnight positions)


class Validity(str, Enum):
    """Order validity."""
    DAY = "DAY"
    IOC = "IOC"  # Immediate or Cancel
    TTL = "TTL"  # Time to Live


class OrderStatus(str, Enum):
    """Order status."""
    PENDING = "PENDING"
    OPEN = "OPEN"
    COMPLETE = "COMPLETE"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    MODIFIED = "MODIFIED"


class PositionType(str, Enum):
    """Position type."""
    LONG = "LONG"
    SHORT = "SHORT"


class Timeframe(str, Enum):
    """Supported timeframes."""
    MINUTE_1 = "1min"
    MINUTE_5 = "5min"
    MINUTE_15 = "15min"
    MINUTE_30 = "30min"
    HOUR_1 = "1hour"
    DAY_1 = "1day"

    @classmethod
    def normalize(cls, tf: str) -> str:
        """
        Normalize timeframe string to standard format.

        Examples:
            '1m' -> '1min'
            '5m' -> '5min'
            '1h' -> '1hour'
            '1d' -> '1day'
        """
        mapping = {
            '1m': cls.MINUTE_1.value,
            '5m': cls.MINUTE_5.value,
            '15m': cls.MINUTE_15.value,
            '30m': cls.MINUTE_30.value,
            '1h': cls.HOUR_1.value,
            '1d': cls.DAY_1.value,
        }
        return mapping.get(tf, tf)


class AlertType(str, Enum):
    """Alert types."""
    PRICE = "PRICE"  # Price-based alert
    INDICATOR = "INDICATOR"  # Indicator-based alert
    POSITION = "POSITION"  # Position-based alert
    ACCOUNT = "ACCOUNT"  # Account-based alert
    CUSTOM = "CUSTOM"  # Custom event


class AlertPriority(str, Enum):
    """Alert priority levels."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class MessageType(str, Enum):
    """Message types."""
    TEXT = "TEXT"
    JSON = "JSON"
    BINARY = "BINARY"


class ReminderFrequency(str, Enum):
    """Reminder frequency."""
    ONCE = "ONCE"
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"
    CUSTOM = "CUSTOM"


class NewsCategory(str, Enum):
    """News categories."""
    MARKET = "MARKET"
    EARNINGS = "EARNINGS"
    ECONOMIC = "ECONOMIC"
    CORPORATE = "CORPORATE"
    REGULATORY = "REGULATORY"
    GLOBAL = "GLOBAL"
    SECTOR = "SECTOR"


class NewsSentiment(str, Enum):
    """News sentiment."""
    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    NEUTRAL = "NEUTRAL"
    MIXED = "MIXED"


class EventStatus(str, Enum):
    """Event status."""
    PENDING = "PENDING"
    TRIGGERED = "TRIGGERED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    EXPIRED = "EXPIRED"
