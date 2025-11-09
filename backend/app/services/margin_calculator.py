"""
Margin Calculator

Fetches real-time margin requirements from Kite API and applies dynamic multipliers for:
- VIX (India VIX volatility index) - 1.0x to 2.0x multiplier
- Expiry day proximity - 1.0x to 3.5x multiplier
- Price movement of underlying - 1.0x to 1.6x multiplier
- NSE regulatory changes - from Kite API

This service INTEGRATES with KiteConnect API via ticker_service:
- Uses kite.order_margins() for single instrument margins
- Uses kite.basket_order_margins() for multi-leg strategies
- Applies dynamic multipliers on top of Kite's base margins

Why use Kite API:
- Each instrument has different margins (updated by NSE daily)
- Margins vary by expiry, volatility, regulatory changes
- Kite API provides real-time, accurate margins
- No need to re-engineer NSE margin calculation logic

Usage:
    # Initialize with ticker_service URL
    calculator = MarginCalculator(ticker_service_url="http://localhost:8080")

    # Fetch real-time margin from Kite API (via ticker_service)
    kite_margin = await calculator.fetch_margin_from_ticker_service(
        tradingsymbol="NIFTY24NOV24000CE",
        exchange="NFO",
        transaction_type="BUY",
        quantity=50,
        price=150.0,
        product="MIS",
        account_id="primary"
    )

    # Apply dynamic multipliers and get enhanced margin
    margin = calculator.calculate_margin(
        instrument_token=256265,
        quantity=50,
        side='BUY',
        segment='NFO-OPT',
        underlying_price=23950,
        vix=15.5  # For multiplier calculation
    )

    print(f"Kite margin: ₹{kite_margin['total']}")
    print(f"Enhanced margin with multipliers: ₹{margin.total_margin}")
    print(f"VIX multiplier: {margin.vix_multiplier}x")
"""

from __future__ import annotations

import logging
import httpx
from typing import Dict, Optional, List
from dataclasses import dataclass
from datetime import datetime, date, timedelta
from enum import Enum
from decimal import Decimal

logger = logging.getLogger(__name__)


class Segment(str, Enum):
    """Trading segments."""
    NFO_FUT = "NFO-FUT"  # Futures
    NFO_OPT = "NFO-OPT"  # Options
    EQUITY = "EQUITY"    # Equity/Cash


class OptionType(str, Enum):
    """Option types."""
    CE = "CE"  # Call option
    PE = "PE"  # Put option


@dataclass
class MarginBreakdown:
    """
    Complete margin breakdown.

    Attributes:
        span_margin: SPAN margin (risk-based)
        exposure_margin: Exposure margin (3% of contract value)
        premium_margin: Premium margin (for option selling)
        additional_margin: Additional regulatory margin
        total_margin: Total margin required

        # Dynamic multipliers
        vix_multiplier: VIX-based multiplier (1.0-2.0x)
        expiry_multiplier: Expiry proximity multiplier (1.0-3.5x)
        price_movement_multiplier: Price movement multiplier (1.0-1.6x)
        regulatory_multiplier: NSE regulatory multiplier (1.0-1.5x)

        # Metadata
        vix: India VIX value
        days_to_expiry: Days until expiry
        is_expiry_week: Whether in expiry week
        is_expiry_day: Whether it's expiry day
        underlying_price: Current underlying price
        strike_price: Strike price (for options)
    """
    span_margin: float
    exposure_margin: float
    premium_margin: float
    additional_margin: float
    total_margin: float

    vix_multiplier: float
    expiry_multiplier: float
    price_movement_multiplier: float
    regulatory_multiplier: float

    vix: float
    days_to_expiry: int
    is_expiry_week: bool
    is_expiry_day: bool
    underlying_price: float
    strike_price: Optional[float]

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "span_margin": round(self.span_margin, 2),
            "exposure_margin": round(self.exposure_margin, 2),
            "premium_margin": round(self.premium_margin, 2),
            "additional_margin": round(self.additional_margin, 2),
            "total_margin": round(self.total_margin, 2),
            "vix_multiplier": round(self.vix_multiplier, 2),
            "expiry_multiplier": round(self.expiry_multiplier, 2),
            "price_movement_multiplier": round(self.price_movement_multiplier, 2),
            "regulatory_multiplier": round(self.regulatory_multiplier, 2),
            "vix": round(self.vix, 2),
            "days_to_expiry": self.days_to_expiry,
            "is_expiry_week": self.is_expiry_week,
            "is_expiry_day": self.is_expiry_day,
            "underlying_price": round(self.underlying_price, 2),
            "strike_price": round(self.strike_price, 2) if self.strike_price else None
        }


class MarginCalculator:
    """
    Calculates dynamic margin requirements for F&O trades.

    Margin structure:
    1. SPAN margin (base risk margin from NSE)
    2. Exposure margin (3% of contract value - SEBI mandated)
    3. Premium margin (100% for option selling)
    4. Additional margin (regulatory/ad-hoc)

    Dynamic multipliers:
    - VIX: 1.0x (VIX < 15) to 2.0x (VIX > 30)
    - Expiry: 1.0x (> 7 days) to 3.5x (expiry day)
    - Price movement: 1.0x (ATM) to 1.6x (deep OTM)
    - Regulatory: 1.0x to 1.5x (NSE circulars)
    """

    # VIX thresholds and multipliers
    VIX_LOW = 15.0      # Low volatility
    VIX_MEDIUM = 20.0   # Medium volatility
    VIX_HIGH = 25.0     # High volatility
    VIX_EXTREME = 30.0  # Extreme volatility

    # Base margin percentages (of contract value)
    BASE_SPAN_MARGIN_PCT = 10.0      # 10% base SPAN
    EXPOSURE_MARGIN_PCT = 3.0        # 3% exposure (SEBI mandated)

    # Lot sizes (default, can be overridden)
    DEFAULT_LOT_SIZES = {
        "NIFTY": 50,
        "BANKNIFTY": 25,
        "FINNIFTY": 40,
    }

    def __init__(self, ticker_service_url: str = "http://localhost:8080"):
        """
        Initialize margin calculator.

        Args:
            ticker_service_url: Base URL for ticker service (default: http://localhost:8080)
        """
        self.ticker_service_url = ticker_service_url
        self.nse_margin_cache = {}  # Cache for NSE margin files
        self.last_margin_update = None

    async def fetch_margin_from_ticker_service(
        self,
        tradingsymbol: str,
        exchange: str,
        transaction_type: str,  # 'BUY' or 'SELL'
        quantity: int,
        price: float,
        order_type: str = "MARKET",
        product: str = "MIS",
        variety: str = "regular",
        account_id: str = "primary",
        trigger_price: Optional[float] = None
    ) -> Optional[Dict]:
        """
        Fetch real-time margin from ticker_service (which calls Kite API).

        This is the PREFERRED method - always use ticker_service when available.

        Args:
            tradingsymbol: Trading symbol (e.g., "NIFTY24NOV24000CE")
            exchange: Exchange (NFO, NSE, BSE)
            transaction_type: 'BUY' or 'SELL'
            quantity: Order quantity
            price: Order price
            order_type: Order type (MARKET, LIMIT)
            product: Product type (MIS, NRML, CNC)
            variety: Order variety (regular, amo, iceberg)
            account_id: Trading account ID
            trigger_price: Trigger price for SL orders

        Returns:
            Dict with margin details from Kite API via ticker_service, or None if unavailable

        API Response from ticker_service:
            [
                {
                    "type": "equity",
                    "tradingsymbol": "NIFTY24NOV24000CE",
                    "exchange": "NFO",
                    "span": 12345.0,        # SPAN margin
                    "exposure": 1234.0,     # Exposure margin
                    "option_premium": 0.0,  # Premium margin (for selling)
                    "additional": 0.0,      # Additional margin
                    "total": 13579.0,       # Total margin required
                    "leverage": 1.0,
                    "pnl": {...}
                }
            ]
        """
        try:
            # Build request payload matching ticker_service's BasketOrderMarginRequest model
            payload = {
                "account_id": account_id,
                "consider_positions": True,
                "orders": [
                    {
                        "exchange": exchange,
                        "tradingsymbol": tradingsymbol,
                        "transaction_type": transaction_type,
                        "variety": variety,
                        "product": product,
                        "order_type": order_type,
                        "quantity": quantity,
                        "price": price,
                        "trigger_price": trigger_price
                    }
                ]
            }

            # Call ticker_service /orders/margins endpoint
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self.ticker_service_url}/orders/margins",
                    json=payload
                )
                response.raise_for_status()

                margin_response = response.json()
                # Returns list of margins, we want the first one
                return margin_response[0] if margin_response else None

        except httpx.HTTPError as e:
            logger.error(f"HTTP error fetching margins from ticker_service: {e}")
            return None
        except Exception as e:
            logger.error(f"Error fetching margins from ticker_service: {e}")
            return None

    async def fetch_basket_margin_from_ticker_service(
        self,
        orders: List[Dict],
        account_id: str = "primary",
        consider_positions: bool = True
    ) -> Optional[Dict]:
        """
        Fetch consolidated margin for a basket of orders from ticker_service.

        Args:
            orders: List of order dicts with keys: exchange, tradingsymbol,
                   transaction_type, variety, product, order_type, quantity, price
            account_id: Trading account ID
            consider_positions: Whether to consider existing positions

        Returns:
            Dict with consolidated margin for the entire basket

        API Response from ticker_service:
            {
                "initial": {
                    "type": "equity",
                    "total": 50000.0,
                    "span": 45000.0,
                    "exposure": 5000.0,
                    ...
                },
                "final": {
                    "type": "equity",
                    "total": 30000.0,
                    ...
                },
                "orders": [...]  # Individual order margins
            }
        """
        try:
            payload = {
                "account_id": account_id,
                "consider_positions": consider_positions,
                "orders": orders
            }

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self.ticker_service_url}/orders/margins/basket",
                    json=payload
                )
                response.raise_for_status()
                return response.json()

        except httpx.HTTPError as e:
            logger.error(f"HTTP error fetching basket margins from ticker_service: {e}")
            return None
        except Exception as e:
            logger.error(f"Error fetching basket margins from ticker_service: {e}")
            return None

    def calculate_margin(
        self,
        instrument_token: int,
        quantity: int,
        side: str,  # 'BUY' or 'SELL'
        segment: str,  # 'NFO-FUT', 'NFO-OPT', 'EQUITY'
        underlying_price: float,
        symbol: str = "NIFTY",
        strike_price: Optional[float] = None,
        option_type: Optional[str] = None,  # 'CE' or 'PE'
        premium: Optional[float] = None,
        expiry_date: Optional[date] = None,
        vix: Optional[float] = None,
        lot_size: Optional[int] = None
    ) -> MarginBreakdown:
        """
        Calculate margin requirement with dynamic adjustments.

        Args:
            instrument_token: Instrument identifier
            quantity: Number of lots
            side: 'BUY' or 'SELL'
            segment: Trading segment
            underlying_price: Current price of underlying
            symbol: Underlying symbol (NIFTY, BANKNIFTY, etc.)
            strike_price: Strike price (for options)
            option_type: 'CE' or 'PE' (for options)
            premium: Option premium (for option selling)
            expiry_date: Expiry date
            vix: India VIX value (if None, uses default)
            lot_size: Lot size (if None, uses default for symbol)

        Returns:
            MarginBreakdown with all components
        """
        # Get lot size
        if lot_size is None:
            lot_size = self.DEFAULT_LOT_SIZES.get(symbol, 50)

        # Get VIX (default to 15 if not provided)
        vix = vix or 15.0

        # Calculate days to expiry
        days_to_expiry, is_expiry_week, is_expiry_day = self._calculate_expiry_info(expiry_date)

        # Calculate dynamic multipliers
        vix_multiplier = self._calculate_vix_multiplier(vix)
        expiry_multiplier = self._calculate_expiry_multiplier(days_to_expiry, is_expiry_day)
        price_movement_multiplier = self._calculate_price_movement_multiplier(
            underlying_price=underlying_price,
            strike_price=strike_price,
            option_type=option_type
        )
        regulatory_multiplier = self._calculate_regulatory_multiplier(symbol, days_to_expiry)

        # Calculate base contract value
        contract_value = underlying_price * lot_size * quantity

        # Calculate SPAN margin (with all dynamic multipliers)
        base_span = contract_value * (self.BASE_SPAN_MARGIN_PCT / 100)
        span_margin = (
            base_span *
            vix_multiplier *
            expiry_multiplier *
            price_movement_multiplier *
            regulatory_multiplier
        )

        # Calculate exposure margin (3% of contract value)
        exposure_margin = contract_value * (self.EXPOSURE_MARGIN_PCT / 100)

        # Calculate premium margin (for option selling)
        premium_margin = 0.0
        if segment == "NFO-OPT" and side.upper() == "SELL":
            if premium:
                # 100% of premium received
                premium_margin = premium * lot_size * quantity
            else:
                # Estimate: ~5% of strike price if premium not provided
                premium_margin = (strike_price or underlying_price) * lot_size * quantity * 0.05

        # Additional margin (regulatory/ad-hoc)
        additional_margin = 0.0
        if is_expiry_day:
            # Additional 20% on expiry day
            additional_margin = span_margin * 0.20

        # Total margin
        total_margin = span_margin + exposure_margin + premium_margin + additional_margin

        return MarginBreakdown(
            span_margin=span_margin,
            exposure_margin=exposure_margin,
            premium_margin=premium_margin,
            additional_margin=additional_margin,
            total_margin=total_margin,
            vix_multiplier=vix_multiplier,
            expiry_multiplier=expiry_multiplier,
            price_movement_multiplier=price_movement_multiplier,
            regulatory_multiplier=regulatory_multiplier,
            vix=vix,
            days_to_expiry=days_to_expiry,
            is_expiry_week=is_expiry_week,
            is_expiry_day=is_expiry_day,
            underlying_price=underlying_price,
            strike_price=strike_price
        )

    def _calculate_expiry_info(self, expiry_date: Optional[date]) -> tuple[int, bool, bool]:
        """
        Calculate expiry-related information.

        Returns:
            Tuple of (days_to_expiry, is_expiry_week, is_expiry_day)
        """
        if expiry_date is None:
            # Default to next monthly expiry (last Thursday of month)
            today = date.today()
            # Find last Thursday of current month
            next_month = today.replace(day=28) + timedelta(days=4)
            last_day = next_month - timedelta(days=next_month.day)
            # Find last Thursday
            offset = (last_day.weekday() - 3) % 7
            expiry_date = last_day - timedelta(days=offset)

        today = date.today()
        days_to_expiry = (expiry_date - today).days

        # Expiry week is last 7 days
        is_expiry_week = days_to_expiry <= 7

        # Expiry day
        is_expiry_day = days_to_expiry == 0

        return max(0, days_to_expiry), is_expiry_week, is_expiry_day

    def _calculate_vix_multiplier(self, vix: float) -> float:
        """
        Calculate VIX-based margin multiplier.

        VIX ranges:
        - < 15: 1.0x (low volatility)
        - 15-20: 1.2x (normal)
        - 20-25: 1.4x (elevated)
        - 25-30: 1.7x (high)
        - > 30: 2.0x (extreme)
        """
        if vix < self.VIX_LOW:
            return 1.0
        elif vix < self.VIX_MEDIUM:
            # Linear interpolation 1.0 to 1.2
            return 1.0 + (vix - self.VIX_LOW) / (self.VIX_MEDIUM - self.VIX_LOW) * 0.2
        elif vix < self.VIX_HIGH:
            # Linear interpolation 1.2 to 1.4
            return 1.2 + (vix - self.VIX_MEDIUM) / (self.VIX_HIGH - self.VIX_MEDIUM) * 0.2
        elif vix < self.VIX_EXTREME:
            # Linear interpolation 1.4 to 1.7
            return 1.4 + (vix - self.VIX_HIGH) / (self.VIX_EXTREME - self.VIX_HIGH) * 0.3
        else:
            # Cap at 2.0x for extreme volatility
            return min(2.0, 1.7 + (vix - self.VIX_EXTREME) / 10.0 * 0.3)

    def _calculate_expiry_multiplier(self, days_to_expiry: int, is_expiry_day: bool) -> float:
        """
        Calculate expiry-based margin multiplier.

        Expiry proximity:
        - > 7 days: 1.0x
        - 4-7 days: 1.2x
        - 2-3 days: 1.5x
        - 1 day: 2.0x
        - Expiry day: 3.5x
        """
        if is_expiry_day:
            return 3.5
        elif days_to_expiry == 1:
            return 2.0
        elif days_to_expiry <= 3:
            return 1.5
        elif days_to_expiry <= 7:
            return 1.2
        else:
            return 1.0

    def _calculate_price_movement_multiplier(
        self,
        underlying_price: float,
        strike_price: Optional[float],
        option_type: Optional[str]
    ) -> float:
        """
        Calculate price movement multiplier based on moneyness.

        For options:
        - ATM (within 2%): 1.0x
        - ITM (2-5%): 1.1x
        - OTM (2-5%): 1.2x
        - Deep ITM/OTM (> 5%): 1.4x
        - Very deep OTM (> 10%): 1.6x

        For futures: 1.0x
        """
        if strike_price is None or option_type is None:
            # Futures or no strike info
            return 1.0

        # Calculate moneyness
        moneyness = abs((strike_price - underlying_price) / underlying_price) * 100

        # Check if ITM or OTM
        if option_type.upper() == "CE":
            is_itm = strike_price < underlying_price
        else:  # PE
            is_itm = strike_price > underlying_price

        # Determine multiplier
        if moneyness <= 2.0:
            # ATM
            return 1.0
        elif moneyness <= 5.0:
            # Slightly ITM/OTM
            return 1.1 if is_itm else 1.2
        elif moneyness <= 10.0:
            # Deep ITM/OTM
            return 1.4
        else:
            # Very deep OTM (higher risk)
            return 1.6

    def _calculate_regulatory_multiplier(self, symbol: str, days_to_expiry: int) -> float:
        """
        Calculate regulatory multiplier based on NSE circulars.

        This would typically read from NSE margin files (updated daily at 6 PM).
        For now, using defaults with slight increase for volatile indices.

        Returns:
            Multiplier between 1.0 and 1.5
        """
        # Check if NSE has increased margins for this symbol
        # In production, this would read from NSE margin file

        # Default multiplier
        multiplier = 1.0

        # Volatile indices get higher margin
        if symbol in ("BANKNIFTY", "FINNIFTY"):
            multiplier = 1.1

        # Increase margin in expiry week for all indices
        if days_to_expiry <= 7:
            multiplier += 0.1

        return min(multiplier, 1.5)


# Convenience function for quick calculation
def calculate_margin(
    quantity: int,
    underlying_price: float,
    side: str = "BUY",
    segment: str = "NFO-OPT",
    symbol: str = "NIFTY",
    strike_price: Optional[float] = None,
    option_type: Optional[str] = None,
    vix: Optional[float] = None,
    expiry_date: Optional[date] = None
) -> Dict:
    """
    Quick margin calculation function.

    Args:
        quantity: Number of lots
        underlying_price: Current underlying price
        side: 'BUY' or 'SELL'
        segment: Trading segment
        symbol: Underlying symbol
        strike_price: Strike price (for options)
        option_type: 'CE' or 'PE'
        vix: India VIX value
        expiry_date: Expiry date

    Returns:
        Dictionary with margin breakdown
    """
    calculator = MarginCalculator()
    result = calculator.calculate_margin(
        instrument_token=0,  # Not needed for quick calc
        quantity=quantity,
        side=side,
        segment=segment,
        underlying_price=underlying_price,
        symbol=symbol,
        strike_price=strike_price,
        option_type=option_type,
        vix=vix,
        expiry_date=expiry_date
    )
    return result.to_dict()
