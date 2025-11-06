"""
Expiry Labeling Service

Computes relative expiry labels for F&O instruments.
Handles classification of expiries as weekly/monthly/quarterly
and generates labels like "NWeek+1", "NMonth+0", etc.

Usage:
    labeler = ExpiryLabeler(db_pool)
    labels = await labeler.compute_labels("NIFTY", date.today())
    for label in labels:
        print(f"{label.expiry}: {label.relative_label} (rank: {label.relative_rank})")
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, asdict
from datetime import date, timedelta
from typing import Dict, List, Optional, Set, Tuple

import asyncpg
import redis.asyncio as redis

logger = logging.getLogger(__name__)


@dataclass
class ExpiryLabel:
    """
    Relative label information for a specific expiry date.
    """
    expiry: date
    is_weekly: bool
    is_monthly: bool
    is_quarterly: bool
    relative_label: str  # e.g., "NWeek+1", "NMonth+0"
    relative_rank: int   # 1, 2, 3... for weeklies; 0 for monthly
    days_to_expiry: int  # Days from as_of_date to expiry

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        d = asdict(self)
        d['expiry'] = self.expiry.isoformat()
        return d

    @classmethod
    def from_dict(cls, data: dict) -> ExpiryLabel:
        """Create from dictionary"""
        data = data.copy()
        data['expiry'] = date.fromisoformat(data['expiry'])
        return cls(**data)


@dataclass
class RelativeLabelPoint:
    """Relative label for a specific date (historical tracking)"""
    time: date
    label: str

    def to_dict(self) -> dict:
        return {
            "time": self.time.isoformat(),
            "label": self.label
        }


class ExpiryLabeler:
    """
    Compute relative expiry labels for FO instruments.
    Uses market holidays to determine business days.

    Labeling scheme:
    - Weekly expiries: NWeek+1, NWeek+2, NWeek+3, ...
    - Monthly expiries: NMonth+0, NMonth+1, NMonth+2, ...
    - Rank: 1+ for weeklies (nearest=1), 0 for monthly

    Classification rules:
    - Weekly: Any Thursday that's not the last Thursday of month
    - Monthly: Last Thursday of month
    - Quarterly: Last Thursday of Mar/Jun/Sep/Dec
    """

    def __init__(self, db_pool: asyncpg.Pool, redis_client: Optional[redis.Redis] = None):
        self.db_pool = db_pool
        self.redis = redis_client
        self._holiday_cache: Dict[int, Set[date]] = {}  # year -> set of holiday dates
        self._label_cache: Dict[str, List[ExpiryLabel]] = {}  # "{symbol}:{date}" -> labels

    async def get_holidays(self, year: int) -> Set[date]:
        """
        Fetch NSE holidays for a given year from calendar_events table.
        Results are cached in memory per year.
        """
        if year in self._holiday_cache:
            return self._holiday_cache[year]

        query = """
            SELECT ce.event_date::DATE as holiday_date
            FROM calendar_events ce
            JOIN calendar_types ct ON ce.calendar_type_id = ct.id
            WHERE ct.code = 'NSE'
              AND ce.event_type = 'holiday'
              AND ce.is_trading_day = false
              AND EXTRACT(YEAR FROM ce.event_date) = $1
        """

        try:
            async with self.db_pool.acquire() as conn:
                rows = await conn.fetch(query, year)

            holidays = {row['holiday_date'] for row in rows}
            self._holiday_cache[year] = holidays
            logger.debug(f"Loaded {len(holidays)} NSE holidays for {year}")
            return holidays

        except Exception as e:
            logger.warning(f"Failed to fetch holidays for {year}: {e}. Using empty set.")
            return set()

    def is_business_day(self, d: date, holidays: Set[date]) -> bool:
        """
        Check if a date is a business day.
        Business day = Monday-Friday AND not a market holiday.
        """
        # 0=Monday, 6=Sunday
        is_weekday = d.weekday() < 5
        is_not_holiday = d not in holidays
        return is_weekday and is_not_holiday

    def get_next_business_day(self, d: date, holidays: Set[date]) -> date:
        """Get the next business day after a given date (not including the date itself)"""
        candidate = d + timedelta(days=1)  # Start from next day
        max_iterations = 30  # Safety limit
        iterations = 0

        while not self.is_business_day(candidate, holidays) and iterations < max_iterations:
            candidate += timedelta(days=1)
            iterations += 1

        if iterations >= max_iterations:
            logger.error(f"Could not find business day after {d} within 30 days")

        return candidate

    def count_business_days(self, start: date, end: date, holidays: Set[date]) -> int:
        """Count business days between start and end (inclusive)"""
        if start > end:
            return 0

        count = 0
        current = start

        while current <= end:
            if self.is_business_day(current, holidays):
                count += 1
            current += timedelta(days=1)

        return count

    def classify_expiry(self, expiry: date) -> Tuple[bool, bool, bool]:
        """
        Classify expiry as weekly/monthly/quarterly.

        Rules (NSE F&O):
        - Weekly: Every Thursday (excluding last Thursday of month)
        - Monthly: Last Thursday of each month
        - Quarterly: Last Thursday of Mar/Jun/Sep/Dec

        Returns:
            (is_weekly, is_monthly, is_quarterly)
        """
        # Check if Thursday (NSE expiries are on Thursdays)
        # weekday: 0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri, 5=Sat, 6=Sun
        if expiry.weekday() != 3:
            # Not a Thursday - not a valid expiry
            return (False, False, False)

        # Check if last Thursday of the month
        # Strategy: Add 7 days and check if month changes
        next_week = expiry + timedelta(days=7)
        is_last_thursday = (next_week.month != expiry.month)

        if is_last_thursday:
            # This is a monthly expiry
            is_quarterly = expiry.month in [3, 6, 9, 12]
            return (False, True, is_quarterly)
        else:
            # This is a weekly expiry
            return (True, False, False)

    async def get_all_expiries(
        self,
        symbol: str,
        min_date: Optional[date] = None,
        max_date: Optional[date] = None
    ) -> List[date]:
        """
        Get all distinct expiries for a symbol from fo_option_strike_bars.

        Args:
            symbol: Underlying symbol (NIFTY, BANKNIFTY, etc.)
            min_date: Minimum expiry date (default: today)
            max_date: Maximum expiry date (optional)
        """
        from ..database import _normalize_symbol

        symbol_norm = _normalize_symbol(symbol)
        min_date = min_date or date.today()

        if max_date:
            query = """
                SELECT DISTINCT expiry
                FROM fo_option_strike_bars
                WHERE symbol = $1
                  AND expiry >= $2
                  AND expiry <= $3
                ORDER BY expiry
            """
            params = [symbol_norm, min_date, max_date]
        else:
            query = """
                SELECT DISTINCT expiry
                FROM fo_option_strike_bars
                WHERE symbol = $1
                  AND expiry >= $2
                ORDER BY expiry
            """
            params = [symbol_norm, min_date]

        try:
            async with self.db_pool.acquire() as conn:
                rows = await conn.fetch(query, *params)

            expiries = [row['expiry'] for row in rows]
            logger.debug(f"Found {len(expiries)} expiries for {symbol} from {min_date}")
            return expiries

        except Exception as e:
            logger.error(f"Failed to fetch expiries for {symbol}: {e}")
            return []

    async def compute_labels(
        self,
        symbol: str,
        as_of_date: Optional[date] = None,
        use_cache: bool = True
    ) -> List[ExpiryLabel]:
        """
        Compute relative labels for all expiries of a symbol as of a specific date.

        Labels:
        - Weekly expiries: "NWeek+1" (nearest), "NWeek+2", "NWeek+3", ...
        - Monthly expiries: "NMonth+0" (current month), "NMonth+1", "NMonth+2", ...

        Ranking:
        - Weekly expiries: 1, 2, 3, ... (ascending by date)
        - Monthly expiries: 0 (special rank to distinguish from weeklies)

        Args:
            symbol: Underlying symbol
            as_of_date: Reference date for "today" (default: actual today)
            use_cache: Whether to use Redis cache (default: True)

        Returns:
            List of ExpiryLabel sorted by expiry date
        """
        as_of_date = as_of_date or date.today()
        cache_key = f"{symbol}:{as_of_date.isoformat()}"

        # Check cache first
        if use_cache and cache_key in self._label_cache:
            logger.debug(f"Using in-memory cache for {cache_key}")
            return self._label_cache[cache_key]

        if use_cache and self.redis:
            cached = await self._get_from_redis_cache(cache_key)
            if cached:
                self._label_cache[cache_key] = cached
                return cached

        # Compute fresh labels
        expiries = await self.get_all_expiries(symbol, min_date=as_of_date)

        if not expiries:
            logger.warning(f"No expiries found for {symbol} from {as_of_date}")
            return []

        # Get holidays for relevant years
        years = {as_of_date.year, expiries[0].year, expiries[-1].year}
        holidays_map = {}
        for year in years:
            holidays_map[year] = await self.get_holidays(year)

        def get_holidays_for_date(d: date) -> Set[date]:
            return holidays_map.get(d.year, set())

        # Classify and label each expiry
        labels: List[ExpiryLabel] = []
        weekly_count = 0
        monthly_count = 0

        for expiry in expiries:
            is_weekly, is_monthly, is_quarterly = self.classify_expiry(expiry)

            # Determine label and rank
            if is_weekly:
                weekly_count += 1
                relative_label = f"NWeek+{weekly_count}"
                relative_rank = weekly_count
            elif is_monthly:
                relative_label = f"NMonth+{monthly_count}"
                relative_rank = 0  # Monthly gets special rank 0
                monthly_count += 1
            else:
                # Not a valid expiry (not Thursday)
                logger.warning(f"Skipping invalid expiry {expiry} for {symbol} (not Thursday)")
                continue

            # Calculate days to expiry
            holidays = get_holidays_for_date(as_of_date)
            days_to_expiry = (expiry - as_of_date).days

            label = ExpiryLabel(
                expiry=expiry,
                is_weekly=is_weekly,
                is_monthly=is_monthly,
                is_quarterly=is_quarterly,
                relative_label=relative_label,
                relative_rank=relative_rank,
                days_to_expiry=days_to_expiry
            )
            labels.append(label)

        # Cache results
        self._label_cache[cache_key] = labels

        if use_cache and self.redis:
            await self._save_to_redis_cache(cache_key, labels)

        logger.info(
            f"Computed {len(labels)} labels for {symbol} as of {as_of_date}: "
            f"{weekly_count} weekly, {monthly_count} monthly"
        )

        return labels

    async def compute_historical_labels(
        self,
        symbol: str,
        expiry: date,
        backfill_days: int = 30
    ) -> List[RelativeLabelPoint]:
        """
        Compute what the relative label would have been for this expiry
        on every business day in the past N days.

        This is used for historical charting - so the frontend can display
        the correct label for each timestamp in the past.

        Example:
        - On 2024-11-01, the 2024-11-07 expiry was "NWeek+2"
        - On 2024-11-04, it became "NWeek+1"
        - On 2024-11-05, it's still "NWeek+1"

        Args:
            symbol: Underlying symbol
            expiry: The specific expiry to track
            backfill_days: Number of days to look back

        Returns:
            List of RelativeLabelPoint with (date, label) pairs for each business day
        """
        end_date = date.today()
        start_date = end_date - timedelta(days=backfill_days)

        # Get holidays for the backfill period
        years = {start_date.year, end_date.year}
        holidays_map = {}
        for year in years:
            holidays_map[year] = await self.get_holidays(year)

        def get_holidays_for_date(d: date) -> Set[date]:
            return holidays_map.get(d.year, set())

        historical: List[RelativeLabelPoint] = []
        current = start_date

        while current <= end_date:
            holidays = get_holidays_for_date(current)

            if self.is_business_day(current, holidays):
                # Compute labels as of this date
                labels = await self.compute_labels(symbol, as_of_date=current, use_cache=False)

                # Find the label for our target expiry
                for lbl in labels:
                    if lbl.expiry == expiry:
                        historical.append(
                            RelativeLabelPoint(time=current, label=lbl.relative_label)
                        )
                        break

            current += timedelta(days=1)

        logger.info(
            f"Computed {len(historical)} historical labels for {symbol} "
            f"expiry {expiry} over {backfill_days} days"
        )

        return historical

    def get_label_map(self, labels: List[ExpiryLabel]) -> Dict[date, Tuple[str, int]]:
        """
        Convert list of ExpiryLabel to a lookup map.

        Returns:
            Dictionary mapping expiry -> (relative_label, relative_rank)
        """
        return {
            lbl.expiry: (lbl.relative_label, lbl.relative_rank)
            for lbl in labels
        }

    async def _get_from_redis_cache(self, cache_key: str) -> Optional[List[ExpiryLabel]]:
        """Get labels from Redis cache"""
        if not self.redis:
            return None

        try:
            redis_key = f"expiry_labels:{cache_key}"
            cached_data = await self.redis.get(redis_key)

            if cached_data:
                data = json.loads(cached_data)
                labels = [ExpiryLabel.from_dict(item) for item in data]
                logger.debug(f"Redis cache hit for {cache_key}")
                return labels

        except Exception as e:
            logger.warning(f"Failed to get from Redis cache: {e}")

        return None

    async def _save_to_redis_cache(self, cache_key: str, labels: List[ExpiryLabel]):
        """Save labels to Redis cache with 24-hour TTL"""
        if not self.redis:
            return

        try:
            redis_key = f"expiry_labels:{cache_key}"
            data = [lbl.to_dict() for lbl in labels]

            # Cache for 24 hours
            await self.redis.setex(
                redis_key,
                86400,  # 24 hours
                json.dumps(data)
            )
            logger.debug(f"Saved to Redis cache: {cache_key}")

        except Exception as e:
            logger.warning(f"Failed to save to Redis cache: {e}")

    def clear_cache(self, symbol: Optional[str] = None):
        """
        Clear in-memory cache.

        Args:
            symbol: If provided, only clear cache for this symbol.
                   If None, clear entire cache.
        """
        if symbol:
            # Clear only entries for this symbol
            keys_to_remove = [k for k in self._label_cache.keys() if k.startswith(f"{symbol}:")]
            for key in keys_to_remove:
                del self._label_cache[key]
            logger.info(f"Cleared cache for symbol: {symbol}")
        else:
            # Clear entire cache
            self._label_cache.clear()
            logger.info("Cleared entire label cache")
