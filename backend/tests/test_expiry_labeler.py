"""
Unit tests for ExpiryLabeler service

Tests expiry classification, label computation, and historical tracking.
"""

import pytest
from datetime import date, timedelta
from typing import Set
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.expiry_labeler import ExpiryLabeler, ExpiryLabel, RelativeLabelPoint


@pytest.fixture
def mock_db_pool():
    """Mock asyncpg database pool"""
    pool = MagicMock()
    return pool


@pytest.fixture
def expiry_labeler(mock_db_pool):
    """Create ExpiryLabeler instance with mocked dependencies"""
    return ExpiryLabeler(db_pool=mock_db_pool, redis_client=None)


class TestExpiryClassification:
    """Test expiry classification logic"""

    def test_weekly_expiry_classification(self, expiry_labeler):
        """Test weekly expiry (Thursday, not last Thursday of month)"""
        # Nov 7, 2024 is a Thursday, not last Thursday of November
        expiry = date(2024, 11, 7)
        is_weekly, is_monthly, is_quarterly = expiry_labeler.classify_expiry(expiry)

        assert is_weekly is True
        assert is_monthly is False
        assert is_quarterly is False

    def test_weekly_expiry_mid_month(self, expiry_labeler):
        """Test another weekly expiry in middle of month"""
        # Nov 14, 2024 is a Thursday (second Thursday)
        expiry = date(2024, 11, 14)
        is_weekly, is_monthly, is_quarterly = expiry_labeler.classify_expiry(expiry)

        assert is_weekly is True
        assert is_monthly is False
        assert is_quarterly is False

    def test_monthly_expiry_classification(self, expiry_labeler):
        """Test monthly expiry (last Thursday of month)"""
        # Nov 28, 2024 is the last Thursday of November
        expiry = date(2024, 11, 28)
        is_weekly, is_monthly, is_quarterly = expiry_labeler.classify_expiry(expiry)

        assert is_weekly is False
        assert is_monthly is True
        assert is_quarterly is False

    def test_quarterly_expiry_classification(self, expiry_labeler):
        """Test quarterly expiry (last Thursday of Mar/Jun/Sep/Dec)"""
        # Dec 26, 2024 is the last Thursday of December (quarterly month)
        expiry = date(2024, 12, 26)
        is_weekly, is_monthly, is_quarterly = expiry_labeler.classify_expiry(expiry)

        assert is_weekly is False
        assert is_monthly is True
        assert is_quarterly is True

    def test_march_quarterly(self, expiry_labeler):
        """Test March quarterly expiry"""
        # Mar 28, 2024 is the last Thursday of March
        expiry = date(2024, 3, 28)
        is_weekly, is_monthly, is_quarterly = expiry_labeler.classify_expiry(expiry)

        assert is_weekly is False
        assert is_monthly is True
        assert is_quarterly is True

    def test_non_thursday_expiry(self, expiry_labeler):
        """Test that non-Thursday dates are not classified as expiries"""
        # Nov 6, 2024 is a Wednesday
        expiry = date(2024, 11, 6)
        is_weekly, is_monthly, is_quarterly = expiry_labeler.classify_expiry(expiry)

        assert is_weekly is False
        assert is_monthly is False
        assert is_quarterly is False

    def test_friday_not_expiry(self, expiry_labeler):
        """Test that Friday is not an expiry"""
        # Nov 8, 2024 is a Friday
        expiry = date(2024, 11, 8)
        is_weekly, is_monthly, is_quarterly = expiry_labeler.classify_expiry(expiry)

        assert is_weekly is False
        assert is_monthly is False
        assert is_quarterly is False

    def test_month_boundary_detection(self, expiry_labeler):
        """Test month boundary detection for monthly expiry"""
        # Oct 31, 2024 is the last Thursday of October
        expiry = date(2024, 10, 31)
        is_weekly, is_monthly, is_quarterly = expiry_labeler.classify_expiry(expiry)

        assert is_weekly is False
        assert is_monthly is True
        assert is_quarterly is False


class TestBusinessDayCalculations:
    """Test business day and holiday handling"""

    def test_weekday_is_business_day(self, expiry_labeler):
        """Test that weekdays (Mon-Fri) are business days when not holidays"""
        # Nov 5, 2024 is a Tuesday
        tuesday = date(2024, 11, 5)
        holidays: Set[date] = set()

        assert expiry_labeler.is_business_day(tuesday, holidays) is True

    def test_saturday_not_business_day(self, expiry_labeler):
        """Test that Saturday is not a business day"""
        # Nov 9, 2024 is a Saturday
        saturday = date(2024, 11, 9)
        holidays: Set[date] = set()

        assert expiry_labeler.is_business_day(saturday, holidays) is False

    def test_sunday_not_business_day(self, expiry_labeler):
        """Test that Sunday is not a business day"""
        # Nov 10, 2024 is a Sunday
        sunday = date(2024, 11, 10)
        holidays: Set[date] = set()

        assert expiry_labeler.is_business_day(sunday, holidays) is False

    def test_holiday_not_business_day(self, expiry_labeler):
        """Test that holidays are not business days even on weekdays"""
        # Nov 5, 2024 is a Tuesday, but mark it as a holiday
        tuesday = date(2024, 11, 5)
        holidays = {tuesday}

        assert expiry_labeler.is_business_day(tuesday, holidays) is False

    def test_get_next_business_day_from_friday(self, expiry_labeler):
        """Test getting next business day from Friday"""
        # Nov 8, 2024 is a Friday
        friday = date(2024, 11, 8)
        holidays: Set[date] = set()

        # Next business day should be Monday, Nov 11
        next_bd = expiry_labeler.get_next_business_day(friday, holidays)
        assert next_bd == date(2024, 11, 11)

    def test_get_next_business_day_skip_holiday(self, expiry_labeler):
        """Test skipping holiday when finding next business day"""
        # Nov 7, 2024 is a Thursday
        thursday = date(2024, 11, 7)
        # Mark Nov 8 (Fri) as holiday
        holidays = {date(2024, 11, 8)}

        # Next business day should be Monday, Nov 11 (skip Sat, Sun, and Friday holiday)
        next_bd = expiry_labeler.get_next_business_day(thursday, holidays)
        assert next_bd == date(2024, 11, 11)

    def test_count_business_days_one_week(self, expiry_labeler):
        """Test counting business days in a normal week"""
        # Nov 4-8, 2024 (Mon-Fri)
        start = date(2024, 11, 4)
        end = date(2024, 11, 8)
        holidays: Set[date] = set()

        count = expiry_labeler.count_business_days(start, end, holidays)
        assert count == 5  # Mon, Tue, Wed, Thu, Fri

    def test_count_business_days_with_weekend(self, expiry_labeler):
        """Test counting business days across weekend"""
        # Nov 4-11, 2024 (Mon-Mon, spans weekend)
        start = date(2024, 11, 4)
        end = date(2024, 11, 11)
        holidays: Set[date] = set()

        count = expiry_labeler.count_business_days(start, end, holidays)
        assert count == 6  # Two weeks = 6 business days (Mon-Fri + Mon)

    def test_count_business_days_with_holiday(self, expiry_labeler):
        """Test counting business days with a holiday"""
        # Nov 4-8, 2024 (Mon-Fri), but Nov 5 is a holiday
        start = date(2024, 11, 4)
        end = date(2024, 11, 8)
        holidays = {date(2024, 11, 5)}

        count = expiry_labeler.count_business_days(start, end, holidays)
        assert count == 4  # Mon, Wed, Thu, Fri (skip Tue holiday)


class TestLabelComputation:
    """Test expiry label computation"""

    @pytest.mark.asyncio
    async def test_compute_labels_basic(self, expiry_labeler):
        """Test basic label computation with multiple expiries"""
        # Mock database to return 3 expiries
        expiries = [
            date(2024, 11, 7),   # Weekly
            date(2024, 11, 14),  # Weekly
            date(2024, 11, 28),  # Monthly
        ]

        async def mock_get_all_expiries(symbol, min_date=None, max_date=None):
            return expiries

        expiry_labeler.get_all_expiries = mock_get_all_expiries

        # Mock holidays
        async def mock_get_holidays(year):
            return set()

        expiry_labeler.get_holidays = mock_get_holidays

        # Compute labels as of Nov 5, 2024
        labels = await expiry_labeler.compute_labels("NIFTY", as_of_date=date(2024, 11, 5))

        assert len(labels) == 3

        # First weekly expiry
        assert labels[0].expiry == date(2024, 11, 7)
        assert labels[0].relative_label == "NWeek+1"
        assert labels[0].relative_rank == 1
        assert labels[0].is_weekly is True
        assert labels[0].is_monthly is False

        # Second weekly expiry
        assert labels[1].expiry == date(2024, 11, 14)
        assert labels[1].relative_label == "NWeek+2"
        assert labels[1].relative_rank == 2
        assert labels[1].is_weekly is True

        # Monthly expiry
        assert labels[2].expiry == date(2024, 11, 28)
        assert labels[2].relative_label == "NMonth+0"
        assert labels[2].relative_rank == 0
        assert labels[2].is_weekly is False
        assert labels[2].is_monthly is True

    @pytest.mark.asyncio
    async def test_compute_labels_with_quarterly(self, expiry_labeler):
        """Test label computation with quarterly expiry"""
        expiries = [
            date(2024, 12, 5),   # Weekly
            date(2024, 12, 12),  # Weekly
            date(2024, 12, 19),  # Weekly
            date(2024, 12, 26),  # Monthly + Quarterly
        ]

        async def mock_get_all_expiries(symbol, min_date=None, max_date=None):
            return expiries

        expiry_labeler.get_all_expiries = mock_get_all_expiries

        async def mock_get_holidays(year):
            return set()

        expiry_labeler.get_holidays = mock_get_holidays

        labels = await expiry_labeler.compute_labels("NIFTY", as_of_date=date(2024, 12, 1))

        assert len(labels) == 4

        # Quarterly expiry
        quarterly_label = labels[3]
        assert quarterly_label.expiry == date(2024, 12, 26)
        assert quarterly_label.is_monthly is True
        assert quarterly_label.is_quarterly is True
        assert quarterly_label.relative_label == "NMonth+0"
        assert quarterly_label.relative_rank == 0

    @pytest.mark.asyncio
    async def test_compute_labels_multiple_monthlies(self, expiry_labeler):
        """Test label computation with multiple monthly expiries"""
        expiries = [
            date(2024, 11, 7),   # Weekly
            date(2024, 11, 28),  # Monthly (NMonth+0)
            date(2024, 12, 26),  # Monthly (NMonth+1)
        ]

        async def mock_get_all_expiries(symbol, min_date=None, max_date=None):
            return expiries

        expiry_labeler.get_all_expiries = mock_get_all_expiries

        async def mock_get_holidays(year):
            return set()

        expiry_labeler.get_holidays = mock_get_holidays

        labels = await expiry_labeler.compute_labels("NIFTY", as_of_date=date(2024, 11, 5))

        # Find the monthly expiries
        monthlies = [lbl for lbl in labels if lbl.is_monthly]
        assert len(monthlies) == 2

        assert monthlies[0].relative_label == "NMonth+0"
        assert monthlies[1].relative_label == "NMonth+1"

    @pytest.mark.asyncio
    async def test_days_to_expiry_calculation(self, expiry_labeler):
        """Test that days_to_expiry is calculated correctly"""
        expiries = [date(2024, 11, 7)]

        async def mock_get_all_expiries(symbol, min_date=None, max_date=None):
            return expiries

        expiry_labeler.get_all_expiries = mock_get_all_expiries

        async def mock_get_holidays(year):
            return set()

        expiry_labeler.get_holidays = mock_get_holidays

        # As of Nov 5, 2024, Nov 7 is 2 days away
        labels = await expiry_labeler.compute_labels("NIFTY", as_of_date=date(2024, 11, 5))

        assert labels[0].days_to_expiry == 2


class TestHistoricalLabels:
    """Test historical label computation"""

    @pytest.mark.asyncio
    async def test_compute_historical_labels(self, expiry_labeler):
        """Test that historical labels change correctly over time"""
        target_expiry = date(2024, 11, 7)

        # Mock holidays
        async def mock_get_holidays(year):
            return set()

        expiry_labeler.get_holidays = mock_get_holidays

        # Mock compute_labels to return different labels based on as_of_date
        original_compute = expiry_labeler.compute_labels

        async def mock_compute_labels(symbol, as_of_date=None, use_cache=False):
            # Simulate label changing based on date
            if as_of_date <= date(2024, 10, 31):
                # Far in advance: NWeek+2
                return [ExpiryLabel(
                    expiry=target_expiry,
                    is_weekly=True,
                    is_monthly=False,
                    is_quarterly=False,
                    relative_label="NWeek+2",
                    relative_rank=2,
                    days_to_expiry=(target_expiry - as_of_date).days
                )]
            else:
                # Closer: NWeek+1
                return [ExpiryLabel(
                    expiry=target_expiry,
                    is_weekly=True,
                    is_monthly=False,
                    is_quarterly=False,
                    relative_label="NWeek+1",
                    relative_rank=1,
                    days_to_expiry=(target_expiry - as_of_date).days
                )]

        expiry_labeler.compute_labels = mock_compute_labels

        # Compute historical labels for 10 days back from Nov 5
        historical = await expiry_labeler.compute_historical_labels(
            "NIFTY",
            target_expiry,
            backfill_days=10
        )

        # Should have multiple entries
        assert len(historical) > 0

        # All entries should be RelativeLabelPoint
        for point in historical:
            assert isinstance(point, RelativeLabelPoint)
            assert point.label in ["NWeek+1", "NWeek+2"]


class TestCaching:
    """Test caching functionality"""

    @pytest.mark.asyncio
    async def test_in_memory_cache(self, expiry_labeler):
        """Test that in-memory cache works"""
        expiries = [date(2024, 11, 7)]

        async def mock_get_all_expiries(symbol, min_date=None, max_date=None):
            return expiries

        expiry_labeler.get_all_expiries = mock_get_all_expiries

        async def mock_get_holidays(year):
            return set()

        expiry_labeler.get_holidays = mock_get_holidays

        # First call - should compute
        labels1 = await expiry_labeler.compute_labels("NIFTY", as_of_date=date(2024, 11, 5))

        # Second call - should use cache
        labels2 = await expiry_labeler.compute_labels("NIFTY", as_of_date=date(2024, 11, 5))

        # Should be same object (from cache)
        assert labels1 is labels2

    def test_clear_cache_all(self, expiry_labeler):
        """Test clearing entire cache"""
        expiry_labeler._label_cache = {
            "NIFTY:2024-11-05": [],
            "BANKNIFTY:2024-11-05": []
        }

        expiry_labeler.clear_cache()

        assert len(expiry_labeler._label_cache) == 0

    def test_clear_cache_symbol(self, expiry_labeler):
        """Test clearing cache for specific symbol"""
        expiry_labeler._label_cache = {
            "NIFTY:2024-11-05": [],
            "NIFTY:2024-11-06": [],
            "BANKNIFTY:2024-11-05": []
        }

        expiry_labeler.clear_cache(symbol="NIFTY")

        assert "NIFTY:2024-11-05" not in expiry_labeler._label_cache
        assert "NIFTY:2024-11-06" not in expiry_labeler._label_cache
        assert "BANKNIFTY:2024-11-05" in expiry_labeler._label_cache


class TestLabelMap:
    """Test get_label_map utility"""

    def test_get_label_map(self, expiry_labeler):
        """Test converting labels to lookup map"""
        labels = [
            ExpiryLabel(
                expiry=date(2024, 11, 7),
                is_weekly=True,
                is_monthly=False,
                is_quarterly=False,
                relative_label="NWeek+1",
                relative_rank=1,
                days_to_expiry=2
            ),
            ExpiryLabel(
                expiry=date(2024, 11, 28),
                is_weekly=False,
                is_monthly=True,
                is_quarterly=False,
                relative_label="NMonth+0",
                relative_rank=0,
                days_to_expiry=23
            )
        ]

        label_map = expiry_labeler.get_label_map(labels)

        assert label_map[date(2024, 11, 7)] == ("NWeek+1", 1)
        assert label_map[date(2024, 11, 28)] == ("NMonth+0", 0)


class TestExpiryLabelSerialization:
    """Test ExpiryLabel serialization/deserialization"""

    def test_to_dict(self):
        """Test converting ExpiryLabel to dictionary"""
        label = ExpiryLabel(
            expiry=date(2024, 11, 7),
            is_weekly=True,
            is_monthly=False,
            is_quarterly=False,
            relative_label="NWeek+1",
            relative_rank=1,
            days_to_expiry=2
        )

        d = label.to_dict()

        assert d['expiry'] == "2024-11-07"
        assert d['is_weekly'] is True
        assert d['relative_label'] == "NWeek+1"
        assert d['relative_rank'] == 1

    def test_from_dict(self):
        """Test creating ExpiryLabel from dictionary"""
        data = {
            'expiry': "2024-11-07",
            'is_weekly': True,
            'is_monthly': False,
            'is_quarterly': False,
            'relative_label': "NWeek+1",
            'relative_rank': 1,
            'days_to_expiry': 2
        }

        label = ExpiryLabel.from_dict(data)

        assert label.expiry == date(2024, 11, 7)
        assert label.is_weekly is True
        assert label.relative_label == "NWeek+1"
        assert label.relative_rank == 1

    def test_round_trip_serialization(self):
        """Test that to_dict -> from_dict preserves data"""
        original = ExpiryLabel(
            expiry=date(2024, 11, 7),
            is_weekly=True,
            is_monthly=False,
            is_quarterly=False,
            relative_label="NWeek+1",
            relative_rank=1,
            days_to_expiry=2
        )

        d = original.to_dict()
        restored = ExpiryLabel.from_dict(d)

        assert restored.expiry == original.expiry
        assert restored.is_weekly == original.is_weekly
        assert restored.relative_label == original.relative_label
        assert restored.relative_rank == original.relative_rank
