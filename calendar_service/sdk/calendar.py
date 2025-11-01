"""
StocksBlitz Calendar SDK Client
Access market calendars, holidays, and trading hours

Usage:
    from stocksblitz_sdk import CalendarClient

    calendar = CalendarClient()

    # Check if market is open
    status = await calendar.get_status('NSE')
    if status.is_trading_day:
        print(f"Market open: {status.session_start} - {status.session_end}")

    # Get holidays
    holidays = await calendar.get_holidays('NSE', year=2025)
    for holiday in holidays:
        print(f"{holiday.date}: {holiday.name}")
"""

import httpx
from datetime import date, time, datetime
from typing import List, Optional
from pydantic import BaseModel
from enum import Enum


class SessionType(str, Enum):
    """Trading session types"""
    PRE_MARKET = "pre-market"
    TRADING = "trading"
    POST_MARKET = "post-market"
    CLOSED = "closed"


class MarketStatus(BaseModel):
    """Market status for a specific calendar and date"""
    calendar_code: str
    date: date
    is_trading_day: bool
    is_holiday: bool
    is_weekend: bool
    current_session: SessionType
    holiday_name: Optional[str] = None

    # Trading hours
    session_start: Optional[time] = None
    session_end: Optional[time] = None
    pre_market_start: Optional[time] = None
    pre_market_end: Optional[time] = None
    post_market_start: Optional[time] = None
    post_market_end: Optional[time] = None

    # Next trading info
    next_trading_day: Optional[date] = None
    time_until_open: Optional[str] = None


class Holiday(BaseModel):
    """Holiday information"""
    date: date
    name: str
    category: str
    calendar_code: str
    is_trading_day: bool = False
    verified: bool = False


class TradingDay(BaseModel):
    """Trading day information"""
    date: date
    is_trading_day: bool
    session_type: str
    trading_start: Optional[time] = None
    trading_end: Optional[time] = None


class CalendarClient:
    """
    Calendar Service Client

    Provides access to market calendars, holidays, and trading hours.

    Example:
        >>> calendar = CalendarClient()
        >>> status = await calendar.get_status('NSE')
        >>> if status.is_trading_day:
        ...     print("Market is open!")
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8081",
        timeout: float = 30.0
    ):
        """
        Initialize calendar client

        Args:
            base_url: Backend API base URL
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client"""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout
            )
        return self._client

    async def close(self):
        """Close HTTP client"""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    # =====================================================
    # MARKET STATUS
    # =====================================================

    async def get_status(
        self,
        calendar: str = "NSE",
        check_date: Optional[date] = None
    ) -> MarketStatus:
        """
        Get current market status

        Args:
            calendar: Calendar code (NSE, BSE, MCX, etc.)
            check_date: Date to check (default: today)

        Returns:
            Market status including trading hours and current session

        Example:
            >>> status = await calendar.get_status('NSE')
            >>> if status.current_session == SessionType.TRADING:
            ...     print("Market is trading now!")
        """
        client = await self._get_client()

        params = {"calendar": calendar.upper()}
        if check_date:
            params["check_date"] = check_date.isoformat()

        response = await client.get("/calendar/status", params=params)
        response.raise_for_status()

        return MarketStatus(**response.json())

    async def is_market_open(
        self,
        calendar: str = "NSE",
        session_types: List[SessionType] = None
    ) -> bool:
        """
        Check if market is currently open

        Args:
            calendar: Calendar code
            session_types: Which sessions count as "open"
                          (default: [TRADING] only)

        Returns:
            True if market is open in specified session types

        Example:
            >>> if await calendar.is_market_open('NSE'):
            ...     print("Can place orders!")
        """
        if session_types is None:
            session_types = [SessionType.TRADING]

        status = await self.get_status(calendar)
        return status.current_session in session_types

    async def is_trading_day(
        self,
        calendar: str = "NSE",
        check_date: Optional[date] = None
    ) -> bool:
        """
        Check if a date is a trading day

        Args:
            calendar: Calendar code
            check_date: Date to check (default: today)

        Returns:
            True if market is open for trading on this date

        Example:
            >>> if await calendar.is_trading_day('NSE', date(2025, 11, 1)):
            ...     print("Market open on Nov 1")
        """
        status = await self.get_status(calendar, check_date)
        return status.is_trading_day

    # =====================================================
    # HOLIDAYS
    # =====================================================

    async def get_holidays(
        self,
        calendar: str = "NSE",
        year: Optional[int] = None,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None
    ) -> List[Holiday]:
        """
        Get list of market holidays

        Args:
            calendar: Calendar code
            year: Year to get holidays for (default: current year)
            from_date: Alternative: start of date range
            to_date: Alternative: end of date range

        Returns:
            List of holidays

        Example:
            >>> holidays = await calendar.get_holidays('NSE', year=2025)
            >>> for h in holidays:
            ...     print(f"{h.date}: {h.name}")
        """
        client = await self._get_client()

        params = {"calendar": calendar.upper()}

        if from_date and to_date:
            params["from_date"] = from_date.isoformat()
            params["to_date"] = to_date.isoformat()
        else:
            params["year"] = year or datetime.now().year

        response = await client.get("/calendar/holidays", params=params)
        response.raise_for_status()

        return [Holiday(**h) for h in response.json()]

    async def is_holiday(
        self,
        calendar: str = "NSE",
        check_date: Optional[date] = None
    ) -> bool:
        """
        Check if a date is a holiday

        Args:
            calendar: Calendar code
            check_date: Date to check (default: today)

        Returns:
            True if date is a market holiday

        Example:
            >>> if await calendar.is_holiday('NSE', date(2025, 1, 26)):
            ...     print("Republic Day - market closed")
        """
        status = await self.get_status(calendar, check_date)
        return status.is_holiday

    # =====================================================
    # TRADING DAYS
    # =====================================================

    async def get_trading_days(
        self,
        calendar: str = "NSE",
        from_date: date = None,
        to_date: date = None
    ) -> List[TradingDay]:
        """
        Get list of trading days in a date range

        Useful for backtesting and analysis.

        Args:
            calendar: Calendar code
            from_date: Start date
            to_date: End date

        Returns:
            List of trading day information

        Example:
            >>> days = await calendar.get_trading_days(
            ...     'NSE',
            ...     date(2025, 1, 1),
            ...     date(2025, 1, 31)
            ... )
            >>> trading_days = [d for d in days if d.is_trading_day]
            >>> print(f"Trading days in Jan: {len(trading_days)}")
        """
        client = await self._get_client()

        if not from_date:
            from_date = date.today()
        if not to_date:
            to_date = from_date

        params = {
            "calendar": calendar.upper(),
            "from_date": from_date.isoformat(),
            "to_date": to_date.isoformat()
        }

        response = await client.get("/calendar/trading-days", params=params)
        response.raise_for_status()

        return [TradingDay(**d) for d in response.json()]

    async def get_next_trading_day(
        self,
        calendar: str = "NSE",
        after_date: Optional[date] = None
    ) -> date:
        """
        Get next trading day after a given date

        Args:
            calendar: Calendar code
            after_date: Date to search after (default: today)

        Returns:
            Next trading day

        Example:
            >>> next_day = await calendar.get_next_trading_day('NSE')
            >>> print(f"Next trading day: {next_day}")
        """
        client = await self._get_client()

        params = {"calendar": calendar.upper()}
        if after_date:
            params["after_date"] = after_date.isoformat()

        response = await client.get("/calendar/next-trading-day", params=params)
        response.raise_for_status()

        data = response.json()
        return datetime.fromisoformat(data['next_trading_day']).date()

    # =====================================================
    # AVAILABLE CALENDARS
    # =====================================================

    async def list_calendars(self) -> List[dict]:
        """
        Get list of available calendar types

        Returns:
            List of calendar information

        Example:
            >>> calendars = await calendar.list_calendars()
            >>> for cal in calendars:
            ...     print(f"{cal['code']}: {cal['name']}")
        """
        client = await self._get_client()

        response = await client.get("/calendar/calendars")
        response.raise_for_status()

        return response.json()


# =====================================================
# SYNCHRONOUS WRAPPER (for non-async code)
# =====================================================

class CalendarClientSync:
    """
    Synchronous wrapper for CalendarClient

    For use in non-async code. Uses asyncio.run() internally.

    Example:
        >>> calendar = CalendarClientSync()
        >>> status = calendar.get_status('NSE')
        >>> if status.is_trading_day:
        ...     print("Market open!")
    """

    def __init__(self, base_url: str = "http://localhost:8081"):
        self._async_client = CalendarClient(base_url)

    def get_status(
        self,
        calendar: str = "NSE",
        check_date: Optional[date] = None
    ) -> MarketStatus:
        """Synchronous version of get_status"""
        import asyncio
        return asyncio.run(self._async_client.get_status(calendar, check_date))

    def is_market_open(self, calendar: str = "NSE") -> bool:
        """Synchronous version of is_market_open"""
        import asyncio
        return asyncio.run(self._async_client.is_market_open(calendar))

    def is_trading_day(
        self,
        calendar: str = "NSE",
        check_date: Optional[date] = None
    ) -> bool:
        """Synchronous version of is_trading_day"""
        import asyncio
        return asyncio.run(self._async_client.is_trading_day(calendar, check_date))

    def get_holidays(
        self,
        calendar: str = "NSE",
        year: Optional[int] = None
    ) -> List[Holiday]:
        """Synchronous version of get_holidays"""
        import asyncio
        return asyncio.run(self._async_client.get_holidays(calendar, year))

    def get_next_trading_day(
        self,
        calendar: str = "NSE",
        after_date: Optional[date] = None
    ) -> date:
        """Synchronous version of get_next_trading_day"""
        import asyncio
        return asyncio.run(self._async_client.get_next_trading_day(calendar, after_date))
