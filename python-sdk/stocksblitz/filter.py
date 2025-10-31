"""
Instrument filtering classes.
"""

from typing import TYPE_CHECKING, List, Callable, Dict, Any
from .instrument import Instrument

if TYPE_CHECKING:
    from .api import APIClient


class InstrumentFilter:
    """
    Filter instruments based on criteria.

    Examples:
        >>> filter = InstrumentFilter("NSE@NIFTY@28-Oct-2025@Put")
        >>> results = filter.where(lambda i: i.ltp > 50)
        >>> results = filter.where(lambda i: i['5m'].rsi[14] > 70)
    """

    def __init__(self, pattern: str, api_client: 'APIClient' = None):
        """
        Initialize instrument filter.

        Args:
            pattern: Instrument pattern (e.g., "NSE@NIFTY@Nw@Put")
            api_client: API client instance
        """
        self.pattern = pattern
        self._api = api_client
        self._instruments: List[Instrument] = []

    def where(self, condition: Callable[[Instrument], bool]) -> List[Instrument]:
        """
        Filter instruments by condition.

        Args:
            condition: Function that takes Instrument and returns bool

        Returns:
            List of matching instruments

        Examples:
            >>> filter.where(lambda i: i.ltp > 50)
            >>> filter.where(lambda i: i.delta > 0.5 and i.oi > 100000)
            >>> filter.where(lambda i: i['5m'].rsi[14] > 70)
        """
        instruments = self._fetch_matching_instruments()
        results = []

        for inst in instruments:
            try:
                if condition(inst):
                    results.append(inst)
            except Exception as e:
                # Skip instruments that fail condition check
                continue

        return results

    def find(self, **criteria) -> List[Instrument]:
        """
        Find instruments by criteria.

        Args:
            **criteria: Filter criteria (e.g., ltp_min=50, delta_min=0.3)

        Returns:
            List of matching instruments

        Examples:
            >>> filter.find(ltp_min=50, ltp_max=100)
            >>> filter.find(oi_min=100000, delta_min=0.3)
        """
        instruments = self._fetch_matching_instruments()
        results = []

        for inst in instruments:
            if self._matches_criteria(inst, criteria):
                results.append(inst)

        return results

    def _fetch_matching_instruments(self) -> List[Instrument]:
        """
        Fetch instruments matching the pattern.

        Returns:
            List of Instrument objects
        """
        # For now, this is a placeholder
        # TODO: Implement proper pattern matching and instrument search
        # This would call: GET /fo/option-chain or similar endpoint

        # Placeholder: return empty list
        return []

    def _matches_criteria(self, inst: Instrument, criteria: Dict[str, Any]) -> bool:
        """
        Check if instrument matches criteria.

        Args:
            inst: Instrument to check
            criteria: Criteria dict

        Returns:
            True if matches all criteria
        """
        for key, value in criteria.items():
            if key.endswith("_min"):
                attr = key[:-4]  # Remove "_min"
                if not hasattr(inst, attr):
                    return False
                if getattr(inst, attr) < value:
                    return False

            elif key.endswith("_max"):
                attr = key[:-4]  # Remove "_max"
                if not hasattr(inst, attr):
                    return False
                if getattr(inst, attr) > value:
                    return False

            else:
                # Exact match
                if not hasattr(inst, key):
                    return False
                if getattr(inst, key) != value:
                    return False

        return True

    def __repr__(self) -> str:
        return f"<InstrumentFilter pattern='{self.pattern}'>"
