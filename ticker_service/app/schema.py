from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Dict, Any, List, Optional


@dataclass
class DepthLevel:
    """Single level of market depth (bid or ask)."""
    quantity: int
    price: float
    orders: int


@dataclass
class MarketDepth:
    """Market depth with buy (bid) and sell (ask) levels."""
    buy: List[DepthLevel]  # Bids (up to 5 levels, sorted descending by price)
    sell: List[DepthLevel]  # Asks (up to 5 levels, sorted ascending by price)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "buy": [
                {"quantity": level.quantity, "price": level.price, "orders": level.orders}
                for level in self.buy
            ],
            "sell": [
                {"quantity": level.quantity, "price": level.price, "orders": level.orders}
                for level in self.sell
            ]
        }


@dataclass
class Instrument:
    symbol: str
    instrument_token: int
    tradingsymbol: str | None = None
    segment: str | None = None
    exchange: str | None = None
    strike: float | None = None
    expiry: str | None = None
    instrument_type: Literal["EQ", "CE", "PE"] = "EQ"
    lot_size: int | None = None
    tick_size: float | None = None


@dataclass
class OptionSnapshot:
    instrument: Instrument
    last_price: float
    volume: int
    iv: float
    delta: float
    gamma: float
    theta: float
    vega: float
    timestamp: int
    oi: int | None = None
    is_mock: bool = False
    # Market depth fields
    depth: Optional[MarketDepth] = None
    total_buy_quantity: int = 0
    total_sell_quantity: int = 0

    def to_payload(self) -> Dict[str, Any]:
        payload = {
            "symbol": self.instrument.symbol,
            "token": self.instrument.instrument_token,
            "tradingsymbol": self.instrument.tradingsymbol,
            "segment": self.instrument.segment,
            "exchange": self.instrument.exchange,
            "strike": self.instrument.strike,
            "expiry": self.instrument.expiry,
            "type": self.instrument.instrument_type,
            "lot_size": self.instrument.lot_size,
            "tick_size": self.instrument.tick_size,
            "price": self.last_price,
            "volume": self.volume,
            "oi": self.oi,
            "iv": self.iv,
            "delta": self.delta,
            "gamma": self.gamma,
            "theta": self.theta,
            "vega": self.vega,
            "ts": self.timestamp,
            "is_mock": self.is_mock,
        }

        # Add market depth if available
        if self.depth:
            payload["depth"] = self.depth.to_dict()
            payload["total_buy_quantity"] = self.total_buy_quantity
            payload["total_sell_quantity"] = self.total_sell_quantity

        return payload
