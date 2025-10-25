from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Dict, Any


@dataclass
class Instrument:
    symbol: str
    instrument_token: int
    strike: float | None = None
    expiry: str | None = None
    instrument_type: Literal['EQ', 'CE', 'PE'] = 'EQ'


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

    def to_payload(self) -> Dict[str, Any]:
        return {
            "symbol": self.instrument.symbol,
            "token": self.instrument.instrument_token,
            "strike": self.instrument.strike,
            "expiry": self.instrument.expiry,
            "type": self.instrument.instrument_type,
            "price": self.last_price,
            "volume": self.volume,
            "iv": self.iv,
            "delta": self.delta,
            "gamma": self.gamma,
            "theta": self.theta,
            "vega": self.vega,
            "ts": self.timestamp,
        }
