"""
Cost Breakdown Calculator

Calculates complete cost breakdown for trades including:
- Brokerage (Zerodha: ₹20 flat for options, 0.03% for futures/equity)
- STT (Securities Transaction Tax - varies by segment and side)
- Exchange charges (NSE/BSE charges)
- GST (18% on brokerage + exchange charges)
- SEBI charges (₹10 per crore turnover)
- Stamp duty (0.002% on buy side for F&O, 0.015% for equity delivery)

Zerodha-specific charges as of 2024:
- Options: ₹20 flat per order
- Futures: 0.03% of turnover
- Equity Intraday: 0.03% of turnover
- Equity Delivery: 0%

Usage:
    calculator = CostBreakdownCalculator()
    cost = calculator.calculate_cost(
        order_value=120000,
        quantity=50,
        price=2400,
        side='BUY',
        segment='NFO-OPT'
    )

    print(f"Total charges: ₹{cost.total_charges}")
    print(f"Net cost: ₹{cost.net_cost}")
"""

from __future__ import annotations

import logging
from typing import Dict, Optional
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class Segment(str, Enum):
    """Trading segments."""
    NFO_FUT = "NFO-FUT"      # Futures
    NFO_OPT = "NFO-OPT"      # Options
    EQUITY_INTRADAY = "EQUITY-INTRADAY"
    EQUITY_DELIVERY = "EQUITY-DELIVERY"


@dataclass
class CostBreakdown:
    """
    Complete cost breakdown for a trade.

    Attributes:
        order_value: Total value of order (price * quantity * lot_size)
        quantity: Number of lots
        price: Price per lot
        side: BUY or SELL
        segment: Trading segment

        # Cost components
        brokerage: Brokerage charges
        stt: Securities Transaction Tax
        exchange_charges: NSE/BSE charges
        gst: 18% GST on brokerage + exchange charges
        sebi_charges: SEBI charges (₹10 per crore)
        stamp_duty: Stamp duty
        total_charges: Sum of all charges
        net_cost: order_value + total_charges (BUY) or order_value - total_charges (SELL)

        # Breakdown details
        turnover: Total turnover for charge calculation
        broker: Broker name (for multi-broker support)
    """
    order_value: float
    quantity: int
    price: float
    side: str
    segment: str

    brokerage: float
    stt: float
    exchange_charges: float
    gst: float
    sebi_charges: float
    stamp_duty: float
    total_charges: float
    net_cost: float

    turnover: float
    broker: str = "zerodha"

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "order_value": round(self.order_value, 2),
            "quantity": self.quantity,
            "price": round(self.price, 2),
            "side": self.side,
            "segment": self.segment,
            "brokerage": round(self.brokerage, 2),
            "stt": round(self.stt, 2),
            "exchange_charges": round(self.exchange_charges, 2),
            "gst": round(self.gst, 2),
            "sebi_charges": round(self.sebi_charges, 2),
            "stamp_duty": round(self.stamp_duty, 2),
            "total_charges": round(self.total_charges, 2),
            "net_cost": round(self.net_cost, 2),
            "turnover": round(self.turnover, 2),
            "broker": self.broker
        }


class CostBreakdownCalculator:
    """
    Calculates complete cost breakdown for trades.

    Zerodha brokerage structure:
    - Options: ₹20 flat per order
    - Futures: 0.03% of turnover
    - Equity Intraday: 0.03% of turnover
    - Equity Delivery: ₹0 (free)

    Tax structure:
    - STT: Varies by segment (0.05% options sell, 0.0125% futures sell, etc.)
    - Exchange charges: ~0.005% for NFO
    - GST: 18% on (brokerage + exchange charges)
    - SEBI charges: ₹10 per crore turnover
    - Stamp duty: 0.002% on buy side (F&O), 0.015% on buy side (equity delivery)
    """

    # Brokerage rates (Zerodha)
    BROKERAGE_OPTIONS_FLAT = 20.0  # ₹20 flat
    BROKERAGE_FUTURES_PCT = 0.03   # 0.03% of turnover
    BROKERAGE_EQUITY_INTRADAY_PCT = 0.03
    BROKERAGE_EQUITY_DELIVERY_PCT = 0.0  # Free

    # STT rates (% of turnover)
    STT_OPTIONS_SELL = 0.05      # 0.05% on sell side
    STT_FUTURES_SELL = 0.0125    # 0.0125% on sell side
    STT_EQUITY_DELIVERY_BUY = 0.1  # 0.1% on both sides
    STT_EQUITY_INTRADAY = 0.025  # 0.025% on sell side

    # Exchange charges (% of turnover)
    EXCHANGE_CHARGES_NFO = 0.005   # ~0.005% for F&O
    EXCHANGE_CHARGES_EQUITY = 0.00345  # ~0.00345% for equity

    # GST
    GST_RATE = 18.0  # 18% on brokerage + exchange charges

    # SEBI charges
    SEBI_CHARGES_PER_CRORE = 10.0  # ₹10 per crore

    # Stamp duty (% of turnover)
    STAMP_DUTY_FO_BUY = 0.002      # 0.002% on buy side
    STAMP_DUTY_EQUITY_BUY = 0.015  # 0.015% on buy side (delivery)

    def calculate_cost(
        self,
        order_value: float,
        quantity: int,
        price: float,
        side: str,  # 'BUY' or 'SELL'
        segment: str,  # 'NFO-OPT', 'NFO-FUT', 'EQUITY-INTRADAY', 'EQUITY-DELIVERY'
        broker: str = "zerodha"
    ) -> CostBreakdown:
        """
        Calculate complete cost breakdown.

        Args:
            order_value: Total order value (price * quantity * lot_size)
            quantity: Number of lots
            price: Price per lot
            side: 'BUY' or 'SELL'
            segment: Trading segment
            broker: Broker name (default: zerodha)

        Returns:
            CostBreakdown with all cost components
        """
        turnover = order_value

        # Calculate brokerage
        brokerage = self._calculate_brokerage(turnover, segment)

        # Calculate STT
        stt = self._calculate_stt(turnover, side, segment)

        # Calculate exchange charges
        exchange_charges = self._calculate_exchange_charges(turnover, segment)

        # Calculate GST (18% on brokerage + exchange charges)
        gst = (brokerage + exchange_charges) * (self.GST_RATE / 100)

        # Calculate SEBI charges (₹10 per crore)
        sebi_charges = (turnover / 10000000) * self.SEBI_CHARGES_PER_CRORE

        # Calculate stamp duty (only on buy side)
        stamp_duty = self._calculate_stamp_duty(turnover, side, segment)

        # Total charges
        total_charges = brokerage + stt + exchange_charges + gst + sebi_charges + stamp_duty

        # Net cost (add charges for BUY, subtract for SELL)
        if side.upper() == "BUY":
            net_cost = order_value + total_charges
        else:  # SELL
            net_cost = order_value - total_charges

        return CostBreakdown(
            order_value=order_value,
            quantity=quantity,
            price=price,
            side=side,
            segment=segment,
            brokerage=brokerage,
            stt=stt,
            exchange_charges=exchange_charges,
            gst=gst,
            sebi_charges=sebi_charges,
            stamp_duty=stamp_duty,
            total_charges=total_charges,
            net_cost=net_cost,
            turnover=turnover,
            broker=broker
        )

    def _calculate_brokerage(self, turnover: float, segment: str) -> float:
        """Calculate brokerage based on segment."""
        if segment == "NFO-OPT":
            # ₹20 flat for options
            return self.BROKERAGE_OPTIONS_FLAT
        elif segment == "NFO-FUT":
            # 0.03% of turnover, capped at ₹20
            brokerage = turnover * (self.BROKERAGE_FUTURES_PCT / 100)
            return min(brokerage, 20.0)
        elif segment == "EQUITY-INTRADAY":
            # 0.03% of turnover, capped at ₹20
            brokerage = turnover * (self.BROKERAGE_EQUITY_INTRADAY_PCT / 100)
            return min(brokerage, 20.0)
        elif segment == "EQUITY-DELIVERY":
            # Free
            return 0.0
        else:
            # Default to ₹20
            return 20.0

    def _calculate_stt(self, turnover: float, side: str, segment: str) -> float:
        """Calculate Securities Transaction Tax."""
        if segment == "NFO-OPT":
            # 0.05% on sell side only
            if side.upper() == "SELL":
                return turnover * (self.STT_OPTIONS_SELL / 100)
            else:
                return 0.0
        elif segment == "NFO-FUT":
            # 0.0125% on sell side only
            if side.upper() == "SELL":
                return turnover * (self.STT_FUTURES_SELL / 100)
            else:
                return 0.0
        elif segment == "EQUITY-DELIVERY":
            # 0.1% on both buy and sell
            return turnover * (self.STT_EQUITY_DELIVERY_BUY / 100)
        elif segment == "EQUITY-INTRADAY":
            # 0.025% on sell side only
            if side.upper() == "SELL":
                return turnover * (self.STT_EQUITY_INTRADAY / 100)
            else:
                return 0.0
        else:
            return 0.0

    def _calculate_exchange_charges(self, turnover: float, segment: str) -> float:
        """Calculate exchange charges."""
        if segment in ("NFO-OPT", "NFO-FUT"):
            # ~0.005% for F&O
            return turnover * (self.EXCHANGE_CHARGES_NFO / 100)
        else:  # Equity
            # ~0.00345% for equity
            return turnover * (self.EXCHANGE_CHARGES_EQUITY / 100)

    def _calculate_stamp_duty(self, turnover: float, side: str, segment: str) -> float:
        """Calculate stamp duty (only on buy side)."""
        if side.upper() != "BUY":
            return 0.0

        if segment in ("NFO-OPT", "NFO-FUT"):
            # 0.002% on buy side for F&O
            return turnover * (self.STAMP_DUTY_FO_BUY / 100)
        elif segment == "EQUITY-DELIVERY":
            # 0.015% on buy side for equity delivery
            return turnover * (self.STAMP_DUTY_EQUITY_BUY / 100)
        elif segment == "EQUITY-INTRADAY":
            # 0.002% on buy side for intraday
            return turnover * (self.STAMP_DUTY_FO_BUY / 100)
        else:
            return 0.0


# Convenience function for quick calculation
def calculate_trade_cost(
    order_value: float,
    quantity: int,
    price: float,
    side: str,
    segment: str = "NFO-OPT",
    broker: str = "zerodha"
) -> Dict:
    """
    Quick cost calculation function.

    Args:
        order_value: Total order value
        quantity: Number of lots
        price: Price per lot
        side: 'BUY' or 'SELL'
        segment: Trading segment
        broker: Broker name

    Returns:
        Dictionary with cost breakdown
    """
    calculator = CostBreakdownCalculator()
    result = calculator.calculate_cost(
        order_value=order_value,
        quantity=quantity,
        price=price,
        side=side,
        segment=segment,
        broker=broker
    )
    return result.to_dict()
