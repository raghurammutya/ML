"""
Option Greeks Calculator

Calculates option Greeks (Delta, Gamma, Theta, Vega, Rho) and Implied Volatility
using the Black-Scholes-Merton model via py-vollib library.

Features:
- Automatic IV calculation from market price
- Greeks calculation (delta, gamma, theta, vega, rho)
- Handles edge cases and errors gracefully
- Returns zero Greeks when calculation fails
"""
from __future__ import annotations

from datetime import datetime, time as dtime
from typing import Dict, Optional, Tuple
from zoneinfo import ZoneInfo

from loguru import logger

try:
    from py_vollib.black_scholes import black_scholes
    from py_vollib.black_scholes.greeks.analytical import delta, gamma, theta, vega, rho
    from py_vollib.black_scholes.implied_volatility import implied_volatility
    VOLLIB_AVAILABLE = True
except ImportError:
    VOLLIB_AVAILABLE = False
    logger.error("py_vollib not available - Greeks calculation will be disabled")


class GreeksCalculator:
    """
    Calculate option Greeks using Black-Scholes-Merton model.
    """

    def __init__(
        self,
        interest_rate: float = 0.10,
        dividend_yield: float = 0.0,
        expiry_time_hour: int = 15,
        expiry_time_minute: int = 30,
        market_timezone: str = "Asia/Kolkata",
    ):
        """
        Initialize Greeks calculator.

        Args:
            interest_rate: Risk-free interest rate (as decimal, e.g., 0.10 for 10%)
            dividend_yield: Dividend yield (as decimal, e.g., 0.02 for 2%)
            expiry_time_hour: Hour of expiry in 24h format (default: 15)
            expiry_time_minute: Minute of expiry (default: 30)
            market_timezone: IANA timezone string (default: Asia/Kolkata)
        """
        self.interest_rate = interest_rate
        self.dividend_yield = dividend_yield
        self.expiry_time = dtime(expiry_time_hour, expiry_time_minute)
        try:
            self.market_tz = ZoneInfo(market_timezone)
        except Exception as e:
            logger.warning(f"Invalid timezone {market_timezone}, using UTC: {e}")
            self.market_tz = ZoneInfo("UTC")

    def calculate_time_to_expiry(self, expiry_date_str: str, current_time: Optional[datetime] = None) -> float:
        """
        Calculate time to expiry in years.

        Args:
            expiry_date_str: Expiry date in format 'YYYY-MM-DD'
            current_time: Current datetime (uses now if not provided)

        Returns:
            Time to expiry in years (fraction)
        """
        try:
            # Parse expiry date
            expiry_date = datetime.strptime(expiry_date_str, "%Y-%m-%d").date()

            # Create expiry datetime at configured time in market timezone
            expiry_datetime = datetime.combine(expiry_date, self.expiry_time)
            expiry_datetime = expiry_datetime.replace(tzinfo=self.market_tz)

            # Get current time
            if current_time is None:
                current_time = datetime.now(self.market_tz)
            elif current_time.tzinfo is None:
                current_time = current_time.replace(tzinfo=self.market_tz)

            # Calculate time difference
            time_diff = expiry_datetime - current_time
            time_to_expiry_seconds = time_diff.total_seconds()

            # Convert to years (365.25 days to account for leap years)
            time_to_expiry_years = time_to_expiry_seconds / (365.25 * 24 * 3600)

            # Ensure non-negative
            return max(0.0, time_to_expiry_years)

        except Exception as e:
            logger.error(f"Error calculating time to expiry: {e}")
            return 0.0

    def calculate_implied_volatility(
        self,
        market_price: float,
        spot_price: float,
        strike_price: float,
        time_to_expiry: float,
        option_type: str,
    ) -> float:
        """
        Calculate implied volatility from market price.

        Args:
            market_price: Current market price of the option
            spot_price: Current price of the underlying
            strike_price: Strike price of the option
            time_to_expiry: Time to expiry in years
            option_type: 'c' for call, 'p' for put

        Returns:
            Implied volatility (as decimal, e.g., 0.20 for 20%)
        """
        if not VOLLIB_AVAILABLE:
            logger.error("GREEKS: py_vollib not available!")
            return 0.0

        try:
            # Input validation
            if market_price <= 0 or spot_price <= 0 or strike_price <= 0:
                logger.debug(f"IV: Invalid inputs price={market_price} spot={spot_price} strike={strike_price}")
                return 0.0

            if time_to_expiry <= 0:
                logger.debug(f"IV: time_to_expiry={time_to_expiry} <= 0")
                return 0.0

            # Normalize option type
            flag = 'c' if option_type.upper() in ('CE', 'CALL', 'C') else 'p'

            # Calculate IV (py-vollib 1.0.1 doesn't support 'q' parameter)
            logger.info(f"IV CALC: price={market_price}, S={spot_price}, K={strike_price}, t={time_to_expiry}, r={self.interest_rate}, flag={flag}")
            iv = implied_volatility(
                price=market_price,
                S=spot_price,
                K=strike_price,
                t=time_to_expiry,
                r=self.interest_rate,
                flag=flag,
            )
            logger.info(f"IV CALC SUCCESS: iv={iv}")

            # Ensure reasonable bounds (0-500%)
            return max(0.0, min(5.0, iv))

        except Exception as e:
            # IV calculation can fail for deep ITM/OTM or edge cases
            logger.info(f"IV calculation failed (price={market_price}, spot={spot_price}, K={strike_price}): {e}")
            return 0.0

    def calculate_greeks(
        self,
        spot_price: float,
        strike_price: float,
        time_to_expiry: float,
        implied_vol: float,
        option_type: str,
    ) -> Dict[str, float]:
        """
        Calculate all option Greeks.

        Args:
            spot_price: Current price of the underlying
            strike_price: Strike price of the option
            time_to_expiry: Time to expiry in years
            implied_vol: Implied volatility (as decimal)
            option_type: 'c' for call, 'p' for put

        Returns:
            Dictionary with keys: delta, gamma, theta, vega, rho
        """
        if not VOLLIB_AVAILABLE:
            return {"delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0, "rho": 0.0}

        try:
            # Input validation
            if spot_price <= 0 or strike_price <= 0 or implied_vol <= 0:
                return {"delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0, "rho": 0.0}

            if time_to_expiry <= 0:
                # At expiry, calculate intrinsic Greeks
                flag = 'c' if option_type.upper() in ('CE', 'CALL', 'C') else 'p'
                intrinsic_delta = 1.0 if (flag == 'c' and spot_price > strike_price) else (
                    -1.0 if (flag == 'p' and spot_price < strike_price) else 0.0
                )
                return {"delta": intrinsic_delta, "gamma": 0.0, "theta": 0.0, "vega": 0.0, "rho": 0.0}

            # Normalize option type
            flag = 'c' if option_type.upper() in ('CE', 'CALL', 'C') else 'p'

            # Calculate Greeks (py-vollib 1.0.1 doesn't support 'q' parameter)
            greeks = {
                "delta": delta(
                    flag=flag,
                    S=spot_price,
                    K=strike_price,
                    t=time_to_expiry,
                    r=self.interest_rate,
                    sigma=implied_vol,
                ),
                "gamma": gamma(
                    flag=flag,
                    S=spot_price,
                    K=strike_price,
                    t=time_to_expiry,
                    r=self.interest_rate,
                    sigma=implied_vol,
                ),
                "theta": theta(
                    flag=flag,
                    S=spot_price,
                    K=strike_price,
                    t=time_to_expiry,
                    r=self.interest_rate,
                    sigma=implied_vol,
                ) / 365.0,  # Convert to daily theta
                "vega": vega(
                    flag=flag,
                    S=spot_price,
                    K=strike_price,
                    t=time_to_expiry,
                    r=self.interest_rate,
                    sigma=implied_vol,
                ) / 100.0,  # Convert to 1% vega
                "rho": rho(
                    flag=flag,
                    S=spot_price,
                    K=strike_price,
                    t=time_to_expiry,
                    r=self.interest_rate,
                    sigma=implied_vol,
                ) / 100.0,  # Convert to 1% rho
            }

            return greeks

        except Exception as e:
            logger.error(f"Error calculating Greeks: {e}")
            return {"delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0, "rho": 0.0}

    def calculate_option_greeks(
        self,
        market_price: float,
        spot_price: float,
        strike_price: float,
        expiry_date: str,
        option_type: str,
        current_time: Optional[datetime] = None,
    ) -> Tuple[float, Dict[str, float]]:
        """
        Complete Greeks calculation workflow.

        Args:
            market_price: Current market price of the option
            spot_price: Current price of the underlying
            strike_price: Strike price of the option
            expiry_date: Expiry date in format 'YYYY-MM-DD'
            option_type: 'CE' or 'PE' (or 'c'/'p')
            current_time: Current datetime (uses now if not provided)

        Returns:
            Tuple of (implied_volatility, greeks_dict)
        """
        # Calculate time to expiry
        logger.info(f"GREEKS DEBUG: expiry_date={expiry_date}, type={type(expiry_date)}")
        time_to_expiry = self.calculate_time_to_expiry(expiry_date, current_time)
        logger.info(f"GREEKS DEBUG: time_to_expiry={time_to_expiry}")

        # Calculate IV from market price
        iv = self.calculate_implied_volatility(
            market_price=market_price,
            spot_price=spot_price,
            strike_price=strike_price,
            time_to_expiry=time_to_expiry,
            option_type=option_type,
        )

        # Calculate Greeks using IV
        greeks = self.calculate_greeks(
            spot_price=spot_price,
            strike_price=strike_price,
            time_to_expiry=time_to_expiry,
            implied_vol=iv,
            option_type=option_type,
        )

        return iv, greeks
