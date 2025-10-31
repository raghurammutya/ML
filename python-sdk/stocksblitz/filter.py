"""
Instrument filtering and option chain querying.

Provides powerful filtering capabilities to find instruments matching patterns
and conditions. Supports both absolute and relative notation.
"""

from typing import TYPE_CHECKING, List, Callable, Dict, Any, Optional
from datetime import datetime, timedelta
from .instrument import Instrument
from .enums import Exchange

if TYPE_CHECKING:
    from .api import APIClient


class InstrumentFilter:
    """
    Filter instruments based on patterns and conditions.

    Pattern Format:
        Exchange@Underlying@Expiry@OptionType[@Strike]

    Examples:
        "NSE@NIFTY@28-Oct-2025@Put"          # Absolute date, all strikes
        "NSE@NIFTY@28-Oct-2025@Put@24500"    # Absolute date and strike
        "NSE@NIFTY@Nw@Put"                   # Next week expiry
        "NSE@NIFTY@Nm@Call"                  # Next month expiry
        "NSE@NIFTY@Nw@Put@ATM"               # At-the-money
        "NSE@NIFTY@Nw@Put@OTM2"              # 2 strikes out-of-the-money
        "NSE@BANKNIFTY@*@Call"               # All expiries

    Usage:
        # Find all NIFTY Puts with LTP > 50
        filter = client.InstrumentFilter("NSE@NIFTY@28-Oct-2025@Put")
        results = filter.where(lambda i: i.ltp > 50)

        # Find options with specific criteria
        results = filter.find(ltp_min=50, ltp_max=100, oi_min=100000)

        # Filter by indicators
        results = filter.where(lambda i: i['5m'].rsi[14] > 70)

        # Chain filters
        results = filter.where(lambda i: i.ltp > 50).where(lambda i: i.delta > 0.3)
    """

    def __init__(self, pattern: str, api_client: 'APIClient' = None):
        """
        Initialize instrument filter.

        Args:
            pattern: Instrument pattern (supports wildcards)
            api_client: API client instance
        """
        self.pattern = pattern
        self._api = api_client
        self._instruments: Optional[List[Instrument]] = None
        self._parsed_pattern = self._parse_pattern(pattern)

    def where(self, condition: Callable[[Instrument], bool]) -> List[Instrument]:
        """
        Filter instruments by custom condition.

        Args:
            condition: Function that takes Instrument and returns bool

        Returns:
            List of matching instruments

        Examples:
            # By price
            >>> filter.where(lambda i: i.ltp > 50)
            >>> filter.where(lambda i: 50 < i.ltp < 100)

            # By greeks
            >>> filter.where(lambda i: i.delta > 0.5 and i.oi > 100000)

            # By indicators
            >>> filter.where(lambda i: i['5m'].rsi[14] > 70)

            # Complex conditions
            >>> filter.where(lambda i: (
            ...     i.ltp > 50 and
            ...     i.delta > 0.3 and
            ...     i.oi > 100000 and
            ...     i['5m'].rsi[14] < 30
            ... ))
        """
        instruments = self._get_instruments()
        results = []

        for inst in instruments:
            try:
                if condition(inst):
                    results.append(inst)
            except Exception as e:
                # Skip instruments that fail condition check
                # (e.g., missing data, API errors)
                continue

        return results

    def find(self, **criteria) -> List[Instrument]:
        """
        Find instruments by simple criteria.

        Args:
            **criteria: Filter criteria with _min/_max suffixes

        Returns:
            List of matching instruments

        Supported Criteria:
            ltp_min, ltp_max: Price range
            oi_min, oi_max: Open interest range
            volume_min, volume_max: Volume range
            delta_min, delta_max: Delta range
            gamma_min, gamma_max: Gamma range
            theta_min, theta_max: Theta range
            vega_min, vega_max: Vega range
            iv_min, iv_max: Implied volatility range

        Examples:
            # Price range
            >>> filter.find(ltp_min=50, ltp_max=100)

            # High OI options
            >>> filter.find(oi_min=100000)

            # Delta range
            >>> filter.find(delta_min=0.3, delta_max=0.7)

            # Multiple criteria
            >>> filter.find(
            ...     ltp_min=50,
            ...     ltp_max=100,
            ...     oi_min=100000,
            ...     delta_min=0.3
            ... )
        """
        instruments = self._get_instruments()
        results = []

        for inst in instruments:
            try:
                if self._matches_criteria(inst, criteria):
                    results.append(inst)
            except Exception:
                continue

        return results

    def order_by(
        self,
        key: str,
        reverse: bool = False
    ) -> List[Instrument]:
        """
        Get instruments ordered by attribute.

        Args:
            key: Attribute to sort by
            reverse: Sort in descending order

        Returns:
            Sorted list of instruments

        Examples:
            # Highest LTP first
            >>> filter.order_by('ltp', reverse=True)

            # Highest OI first
            >>> filter.order_by('oi', reverse=True)

            # Lowest delta first
            >>> filter.order_by('delta')
        """
        instruments = self._get_instruments()

        try:
            return sorted(
                instruments,
                key=lambda i: getattr(i, key, 0),
                reverse=reverse
            )
        except Exception:
            return instruments

    def limit(self, n: int) -> List[Instrument]:
        """
        Get first N instruments.

        Args:
            n: Number of instruments to return

        Returns:
            List of first N instruments

        Example:
            # Top 10 by LTP
            >>> filter.order_by('ltp', reverse=True).limit(10)
        """
        instruments = self._get_instruments()
        return instruments[:n]

    def top(
        self,
        n: int,
        by: str = 'oi',
        ascending: bool = False
    ) -> List[Instrument]:
        """
        Get top N instruments by attribute.

        Args:
            n: Number of instruments
            by: Attribute to sort by
            ascending: Sort ascending (default: descending)

        Returns:
            Top N instruments

        Examples:
            # Top 5 by OI
            >>> filter.top(5, by='oi')

            # Top 10 by volume
            >>> filter.top(10, by='volume')

            # Bottom 5 by LTP
            >>> filter.top(5, by='ltp', ascending=True)
        """
        instruments = self.order_by(by, reverse=not ascending)
        return instruments[:n]

    def atm(self, spot_price: Optional[float] = None) -> Optional[Instrument]:
        """
        Get at-the-money option.

        Args:
            spot_price: Spot price (auto-fetched if not provided)

        Returns:
            ATM instrument or None

        Example:
            >>> filter = client.InstrumentFilter("NSE@NIFTY@Nw@Call")
            >>> atm = filter.atm()
        """
        instruments = self._get_instruments()
        if not instruments:
            return None

        # Get spot price if not provided
        if spot_price is None:
            spot_price = self._get_spot_price()
            if spot_price is None:
                return None

        # Find closest strike to spot
        return min(
            instruments,
            key=lambda i: abs(self._extract_strike(i) - spot_price)
        )

    def otm(self, n: int = 1) -> Optional[Instrument]:
        """
        Get N strikes out-of-the-money.

        Args:
            n: Number of strikes OTM (1 = 1 strike OTM)

        Returns:
            OTM instrument or None

        Example:
            >>> filter = client.InstrumentFilter("NSE@NIFTY@Nw@Put")
            >>> otm2 = filter.otm(2)  # 2 strikes OTM
        """
        instruments = self._get_instruments()
        if not instruments:
            return None

        spot_price = self._get_spot_price()
        if spot_price is None:
            return None

        # Determine option type from pattern
        option_type = self._parsed_pattern.get('option_type', '').upper()

        # Sort by strike
        sorted_insts = sorted(
            instruments,
            key=lambda i: self._extract_strike(i)
        )

        if option_type == 'CALL':
            # OTM Call = strike > spot
            otm_calls = [i for i in sorted_insts if self._extract_strike(i) > spot_price]
            if len(otm_calls) >= n:
                return otm_calls[n - 1]
        elif option_type == 'PUT':
            # OTM Put = strike < spot
            otm_puts = [i for i in sorted_insts if self._extract_strike(i) < spot_price]
            if len(otm_puts) >= n:
                return otm_puts[-(n)]  # From the end

        return None

    def itm(self, n: int = 1) -> Optional[Instrument]:
        """
        Get N strikes in-the-money.

        Args:
            n: Number of strikes ITM

        Returns:
            ITM instrument or None

        Example:
            >>> filter = client.InstrumentFilter("NSE@NIFTY@Nw@Call")
            >>> itm1 = filter.itm(1)  # 1 strike ITM
        """
        instruments = self._get_instruments()
        if not instruments:
            return None

        spot_price = self._get_spot_price()
        if spot_price is None:
            return None

        option_type = self._parsed_pattern.get('option_type', '').upper()
        sorted_insts = sorted(
            instruments,
            key=lambda i: self._extract_strike(i)
        )

        if option_type == 'CALL':
            # ITM Call = strike < spot
            itm_calls = [i for i in sorted_insts if self._extract_strike(i) < spot_price]
            if len(itm_calls) >= n:
                return itm_calls[-(n)]
        elif option_type == 'PUT':
            # ITM Put = strike > spot
            itm_puts = [i for i in sorted_insts if self._extract_strike(i) > spot_price]
            if len(itm_puts) >= n:
                return itm_puts[n - 1]

        return None

    def _get_instruments(self) -> List[Instrument]:
        """Get or fetch instruments matching pattern."""
        if self._instruments is None:
            self._instruments = self._fetch_matching_instruments()
        return self._instruments

    def _fetch_matching_instruments(self) -> List[Instrument]:
        """
        Fetch instruments from backend matching the pattern.

        Returns:
            List of Instrument objects
        """
        if not self._api:
            return []

        try:
            # Build API query from parsed pattern
            params = self._build_api_params()

            # Call option chain API
            # TODO: Replace with actual endpoint
            response = self._api.get("/fo/option-chain", params=params, cache_ttl=10)

            instruments = []
            for data in response.get("data", []):
                symbol = data.get("tradingsymbol")
                if symbol:
                    inst = Instrument(symbol, api_client=self._api)
                    instruments.append(inst)

            return instruments

        except Exception as e:
            # Return empty list if API call fails
            return []

    def _parse_pattern(self, pattern: str) -> Dict[str, str]:
        """
        Parse instrument pattern.

        Pattern: Exchange@Underlying@Expiry@OptionType[@Strike]

        Returns:
            Dict with parsed components
        """
        parts = pattern.split("@")

        parsed = {
            "exchange": parts[0] if len(parts) > 0 else "NSE",
            "underlying": parts[1] if len(parts) > 1 else None,
            "expiry": parts[2] if len(parts) > 2 else None,
            "option_type": parts[3] if len(parts) > 3 else None,
            "strike": parts[4] if len(parts) > 4 else None,
        }

        return parsed

    def _build_api_params(self) -> Dict[str, Any]:
        """Build API parameters from parsed pattern."""
        params = {}

        if self._parsed_pattern.get("underlying"):
            params["underlying"] = self._parsed_pattern["underlying"]

        if self._parsed_pattern.get("expiry"):
            expiry = self._resolve_expiry(self._parsed_pattern["expiry"])
            if expiry:
                params["expiry"] = expiry

        if self._parsed_pattern.get("option_type"):
            params["option_type"] = self._parsed_pattern["option_type"].upper()

        if self._parsed_pattern.get("strike"):
            strike = self._resolve_strike(self._parsed_pattern["strike"])
            if strike:
                params["strike"] = strike

        return params

    def _resolve_expiry(self, expiry_str: str) -> Optional[str]:
        """
        Resolve expiry string to actual date.

        Supports:
            - "Nw" or "1w" = Next week
            - "Nm" or "1m" = Next month
            - "28-Oct-2025" = Absolute date
            - "*" = All expiries

        Returns:
            Resolved expiry string or None
        """
        if expiry_str == "*":
            return None

        if expiry_str in ["Nw", "1w"]:
            # Next week (Thursday)
            today = datetime.now()
            days_ahead = (3 - today.weekday()) % 7  # Thursday = 3
            if days_ahead == 0:
                days_ahead = 7
            next_expiry = today + timedelta(days=days_ahead)
            return next_expiry.strftime("%d-%b-%Y")

        if expiry_str in ["Nm", "1m"]:
            # Next month (last Thursday)
            # Simplified: +30 days
            next_month = datetime.now() + timedelta(days=30)
            return next_month.strftime("%d-%b-%Y")

        # Assume absolute date
        return expiry_str

    def _resolve_strike(self, strike_str: str) -> Optional[float]:
        """
        Resolve strike string.

        Supports:
            - "24500" = Absolute strike
            - "ATM" = At-the-money (requires spot price)
            - "OTM1", "OTM2" = N strikes OTM
            - "ITM1", "ITM2" = N strikes ITM

        Returns:
            Resolved strike or None
        """
        if strike_str.isdigit():
            return float(strike_str)

        # Relative strikes require spot price (handled separately)
        return None

    def _get_spot_price(self) -> Optional[float]:
        """Get spot price for underlying."""
        underlying = self._parsed_pattern.get("underlying")
        if not underlying or not self._api:
            return None

        try:
            # Get spot quote
            response = self._api.get(
                "/fo/quote",
                params={"symbol": underlying},
                cache_ttl=5
            )
            return response.get("ltp")
        except Exception:
            return None

    def _extract_strike(self, inst: Instrument) -> float:
        """Extract strike price from instrument symbol."""
        # Parse from tradingsymbol (e.g., "NIFTY25N0424500PE")
        # Simplified: return 0 if can't parse
        try:
            symbol = inst.tradingsymbol
            # Extract numeric part before CE/PE
            import re
            match = re.search(r'(\d{5,6})(CE|PE)$', symbol)
            if match:
                return float(match.group(1))
        except Exception:
            pass
        return 0.0

    def _matches_criteria(self, inst: Instrument, criteria: Dict[str, Any]) -> bool:
        """
        Check if instrument matches criteria.

        Args:
            inst: Instrument to check
            criteria: Criteria dict with _min/_max suffixes

        Returns:
            True if matches all criteria
        """
        for key, value in criteria.items():
            try:
                if key.endswith("_min"):
                    attr = key[:-4]
                    if getattr(inst, attr, 0) < value:
                        return False

                elif key.endswith("_max"):
                    attr = key[:-4]
                    if getattr(inst, attr, float('inf')) > value:
                        return False

                else:
                    # Exact match
                    if getattr(inst, key, None) != value:
                        return False

            except Exception:
                return False

        return True

    def __repr__(self) -> str:
        return f"<InstrumentFilter pattern='{self.pattern}'>"
