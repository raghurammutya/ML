"""
Market Mode Manager
Determines whether to use LIVE or MOCK data mode based on:
- Environment configuration (FORCE_MOCK_MODE, FORCE_LIVE_MODE)
- Market calendar (trading hours, holidays)
- Development vs Production environment

This allows:
- Development: Always use mock data (ignore market hours)
- Staging: Use calendar but allow override
- Production: Strict calendar adherence
"""

import os
import httpx
from datetime import datetime, time
from typing import Optional, Literal
from loguru import logger
import pytz

IST = pytz.timezone('Asia/Kolkata')

ModeType = Literal["LIVE", "MOCK", "OFF"]


class MarketModeManager:
    """
    Manages ticker service mode (LIVE vs MOCK)

    Environment Variables:
        MARKET_MODE: 'auto' | 'force_mock' | 'force_live' | 'off'
        CALENDAR_API_URL: Backend calendar API URL (default: http://localhost:8081)
        CALENDAR_CODE: Market calendar to use (default: NSE)

    Modes:
        - auto: Use market calendar to determine (production)
        - force_mock: Always use mock data (development)
        - force_live: Always attempt live connection (testing)
        - off: Don't stream at all (maintenance)
    """

    def __init__(
        self,
        calendar_api_url: str = None,
        calendar_code: str = "NSE"
    ):
        """
        Initialize market mode manager

        Args:
            calendar_api_url: Backend API URL for calendar service
            calendar_code: Market calendar to use (NSE, BSE, MCX)
        """
        # Configuration
        self.mode_config = os.getenv("MARKET_MODE", "auto").lower()
        self.calendar_api_url = (
            calendar_api_url or
            os.getenv("CALENDAR_API_URL", "http://backend:8000")
        ).rstrip('/')
        self.calendar_code = os.getenv("CALENDAR_CODE", calendar_code).upper()

        # State
        self._last_calendar_check: Optional[datetime] = None
        self._cached_status: Optional[dict] = None
        self._cache_duration_seconds = 60  # Cache for 1 minute

        logger.info(
            f"Market Mode Manager initialized | "
            f"mode={self.mode_config} "
            f"calendar={self.calendar_code} "
            f"api={self.calendar_api_url}"
        )

    async def should_use_live_mode(self) -> bool:
        """
        Determine if ticker should use LIVE mode

        Returns:
            True if should connect to live WebSocket
            False if should use mock data or stay off

        Decision Flow:
            1. Check MARKET_MODE environment
            2. If 'auto', check market calendar
            3. Return decision
        """
        mode = await self.get_current_mode()

        if mode == "LIVE":
            return True
        elif mode == "MOCK":
            return False
        else:  # OFF
            return False

    async def get_current_mode(self) -> ModeType:
        """
        Get current recommended mode

        Returns:
            "LIVE" | "MOCK" | "OFF"
        """
        # Check forced modes first
        if self.mode_config == "force_mock":
            logger.debug("Mode: MOCK (forced by MARKET_MODE=force_mock)")
            return "MOCK"

        if self.mode_config == "force_live":
            logger.debug("Mode: LIVE (forced by MARKET_MODE=force_live)")
            return "LIVE"

        if self.mode_config == "off":
            logger.debug("Mode: OFF (forced by MARKET_MODE=off)")
            return "OFF"

        # Auto mode: Check market calendar
        if self.mode_config == "auto":
            is_trading = await self._is_market_trading()

            if is_trading:
                logger.debug("Mode: LIVE (market is trading)")
                return "LIVE"
            else:
                logger.debug("Mode: MOCK (market closed)")
                return "MOCK"

        # Unknown config, default to MOCK for safety
        logger.warning(f"Unknown MARKET_MODE={self.mode_config}, defaulting to MOCK")
        return "MOCK"

    async def _is_market_trading(self) -> bool:
        """
        Check if market is currently in trading session

        Uses calendar API to determine market status
        Falls back to simple time-based check if API unavailable
        """
        # Check cache first
        now = datetime.now(IST)

        if self._cached_status and self._last_calendar_check:
            elapsed = (now - self._last_calendar_check).total_seconds()
            if elapsed < self._cache_duration_seconds:
                return self._cached_status.get('is_trading', False)

        # Fetch from calendar API
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(
                    f"{self.calendar_api_url}/calendar/status",
                    params={"calendar": self.calendar_code}
                )

                if response.status_code == 200:
                    status = response.json()

                    # Update cache
                    self._cached_status = {
                        'is_trading_day': status.get('is_trading_day', False),
                        'is_trading': status.get('current_session') == 'trading',
                        'current_session': status.get('current_session'),
                        'is_holiday': status.get('is_holiday', False),
                        'holiday_name': status.get('holiday_name'),
                    }
                    self._last_calendar_check = now

                    logger.debug(
                        f"Calendar status: "
                        f"trading_day={self._cached_status['is_trading_day']} "
                        f"session={self._cached_status['current_session']} "
                        f"holiday={self._cached_status['holiday_name'] or 'None'}"
                    )

                    return self._cached_status['is_trading']

                else:
                    logger.warning(
                        f"Calendar API returned {response.status_code}, "
                        f"falling back to time-based check"
                    )

        except Exception as e:
            logger.warning(f"Calendar API check failed: {e}, falling back to time-based check")

        # Fallback: Simple time-based check
        return self._simple_market_hours_check(now)

    def _simple_market_hours_check(self, now: datetime) -> bool:
        """
        Fallback: Simple market hours check without calendar API

        Checks:
        - Not a weekend
        - Within trading hours (9:15 AM - 3:30 PM IST)

        Does NOT account for holidays!
        """
        # Check if weekend
        if now.weekday() in [5, 6]:  # Saturday, Sunday
            return False

        # Check trading hours (9:15 AM - 3:30 PM IST)
        trading_start = time(9, 15)
        trading_end = time(15, 30)
        current_time = now.time()

        is_trading_hours = trading_start <= current_time < trading_end

        if is_trading_hours:
            logger.debug(
                f"Fallback check: Trading hours "
                f"(time={current_time.strftime('%H:%M')})"
            )
        else:
            logger.debug(
                f"Fallback check: Outside trading hours "
                f"(time={current_time.strftime('%H:%M')})"
            )

        return is_trading_hours

    async def get_mode_reason(self) -> str:
        """
        Get human-readable reason for current mode

        Returns:
            Explanation string
        """
        mode = await self.get_current_mode()

        if self.mode_config == "force_mock":
            return "Development mode: MARKET_MODE=force_mock"

        if self.mode_config == "force_live":
            return "Testing mode: MARKET_MODE=force_live"

        if self.mode_config == "off":
            return "Maintenance mode: MARKET_MODE=off"

        # Auto mode
        if self._cached_status:
            if self._cached_status.get('is_holiday'):
                return f"Market closed: {self._cached_status.get('holiday_name')}"

            if not self._cached_status.get('is_trading_day'):
                return "Market closed: Weekend"

            session = self._cached_status.get('current_session')
            if session == 'trading':
                return "Market open: Trading session"
            elif session == 'pre-market':
                return "Market closed: Pre-market session"
            elif session == 'post-market':
                return "Market closed: Post-market session"
            else:
                return "Market closed: Outside trading hours"

        return "Auto mode (calendar unavailable, using fallback)"

    def get_config_summary(self) -> dict:
        """
        Get configuration summary for logging/debugging

        Returns:
            Dict with configuration details
        """
        return {
            "market_mode": self.mode_config,
            "calendar_code": self.calendar_code,
            "calendar_api_url": self.calendar_api_url,
            "cache_duration": self._cache_duration_seconds,
        }


# =====================================================
# GLOBAL INSTANCE (optional)
# =====================================================

_global_manager: Optional[MarketModeManager] = None


def get_market_mode_manager(
    calendar_api_url: str = None,
    calendar_code: str = "NSE"
) -> MarketModeManager:
    """
    Get or create global market mode manager instance

    Args:
        calendar_api_url: Backend API URL
        calendar_code: Market calendar code

    Returns:
        MarketModeManager instance
    """
    global _global_manager

    if _global_manager is None:
        _global_manager = MarketModeManager(
            calendar_api_url=calendar_api_url,
            calendar_code=calendar_code
        )

    return _global_manager


# =====================================================
# EXAMPLE USAGE
# =====================================================

if __name__ == "__main__":
    import asyncio

    async def main():
        # Example 1: Auto mode (production)
        manager = MarketModeManager()

        mode = await manager.get_current_mode()
        reason = await manager.get_mode_reason()

        print(f"Current mode: {mode}")
        print(f"Reason: {reason}")
        print(f"Config: {manager.get_config_summary()}")

        # Example 2: Check periodically
        print("\nChecking every 10 seconds...")
        for _ in range(3):
            should_stream = await manager.should_use_live_mode()
            print(f"Should stream: {should_stream}")
            await asyncio.sleep(10)

    asyncio.run(main())
