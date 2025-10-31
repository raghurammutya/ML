from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Dict, Any


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

    def to_payload(self) -> Dict[str, Any]:
        return {
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
