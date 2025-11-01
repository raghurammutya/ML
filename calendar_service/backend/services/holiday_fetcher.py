"""
Holiday Calendar Fetcher
Fetches and syncs market holidays from official sources:
- NSE (National Stock Exchange)
- BSE (Bombay Stock Exchange)
- MCX (Multi Commodity Exchange)
- Currency markets

Usage:
    python -m app.services.holiday_fetcher --sync-all
    python -m app.services.holiday_fetcher --calendar NSE --year 2025
"""

import asyncio
import httpx
from datetime import datetime, date
from typing import List, Dict, Optional
import asyncpg
from loguru import logger
import json
from bs4 import BeautifulSoup

from app.database import get_db_pool


class HolidayFetcher:
    """Fetch market holidays from official sources"""

    def __init__(self, db_pool: asyncpg.Pool):
        self.db_pool = db_pool
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json, text/html',
            'Accept-Language': 'en-US,en;q=0.9',
        }

    # =====================================================
    # NSE HOLIDAYS
    # =====================================================

    async def fetch_nse_holidays(self, year: int) -> List[Dict]:
        """
        Fetch NSE holidays from official NSE website

        NSE provides holiday calendar at:
        https://www.nseindia.com/regulations/trading-holidays

        API endpoint (if available):
        https://www.nseindia.com/api/holiday-master?type=trading
        """
        holidays = []

        try:
            # Try API endpoint first
            url = "https://www.nseindia.com/api/holiday-master?type=trading"

            async with httpx.AsyncClient(timeout=30.0) as client:
                # NSE requires visiting homepage first for cookies
                await client.get("https://www.nseindia.com", headers=self.headers)

                # Now fetch holidays
                response = await client.get(url, headers=self.headers)

                if response.status_code == 200:
                    data = response.json()

                    # NSE returns data in format:
                    # {"FO": [{"tradingDate": "01-Jan-2025", "weekDay": "Wednesday", "description": "New Year"}], "CM": [...]}

                    # Extract F&O holidays (includes equity)
                    for segment in ['FO', 'CM']:
                        if segment in data:
                            for holiday_list in data[segment]:
                                if isinstance(holiday_list, dict):
                                    for holiday in holiday_list.get('holidays', []):
                                        try:
                                            holiday_date = datetime.strptime(
                                                holiday['tradingDate'],
                                                '%d-%b-%Y'
                                            ).date()

                                            if holiday_date.year == year:
                                                holidays.append({
                                                    'date': holiday_date,
                                                    'name': holiday.get('description', '').strip(),
                                                    'type': 'market_holiday',
                                                    'segment': segment,
                                                    'source': 'NSE API',
                                                    'verified': True
                                                })
                                        except Exception as e:
                                            logger.warning(f"Failed to parse NSE holiday: {holiday} - {e}")

                    logger.info(f"Fetched {len(holidays)} NSE holidays for {year} from API")
                    return holidays

        except Exception as e:
            logger.warning(f"NSE API fetch failed: {e}, trying fallback")

        # Fallback: Use hardcoded known holidays
        holidays = await self._get_nse_fallback_holidays(year)
        return holidays

    async def _get_nse_fallback_holidays(self, year: int) -> List[Dict]:
        """Fallback: Hardcoded NSE holidays (updated periodically)"""

        # NSE holidays typically include:
        # - National holidays (Republic Day, Independence Day, Gandhi Jayanti)
        # - Religious holidays (Holi, Diwali, etc.)
        # - Market-specific holidays

        known_holidays_2025 = [
            ('2025-01-26', 'Republic Day'),
            ('2025-03-14', 'Holi'),
            ('2025-03-31', 'Id-Ul-Fitr'),
            ('2025-04-10', 'Mahavir Jayanti'),
            ('2025-04-14', 'Dr. Baba Saheb Ambedkar Jayanti'),
            ('2025-04-18', 'Good Friday'),
            ('2025-05-01', 'Maharashtra Day'),
            ('2025-08-15', 'Independence Day'),
            ('2025-08-27', 'Ganesh Chaturthi'),
            ('2025-10-02', 'Mahatma Gandhi Jayanti'),
            ('2025-10-21', 'Dussehra'),
            ('2025-11-01', 'Diwali Laxmi Pujan'),
            ('2025-11-04', 'Diwali Balipratipada'),
            ('2025-11-05', 'Guru Nanak Jayanti'),
            ('2025-12-25', 'Christmas'),
        ]

        known_holidays_2024 = [
            ('2024-01-26', 'Republic Day'),
            ('2024-03-08', 'Maha Shivaratri'),
            ('2024-03-25', 'Holi'),
            ('2024-03-29', 'Good Friday'),
            ('2024-04-11', 'Id-Ul-Fitr'),
            ('2024-04-17', 'Shri Ram Navmi'),
            ('2024-04-21', 'Mahavir Jayanti'),
            ('2024-05-01', 'Maharashtra Day'),
            ('2024-05-23', 'Buddha Pournima'),
            ('2024-06-17', 'Id-Ul-Zuha (Bakri Id)'),
            ('2024-07-17', 'Moharram'),
            ('2024-08-15', 'Independence Day'),
            ('2024-08-26', 'Ganesh Chaturthi'),
            ('2024-10-02', 'Mahatma Gandhi Jayanti'),
            ('2024-10-12', 'Dussehra'),
            ('2024-11-01', 'Diwali Laxmi Pujan'),
            ('2024-11-15', 'Guru Nanak Jayanti'),
            ('2024-12-25', 'Christmas'),
        ]

        known_holidays_2026 = [
            ('2026-01-26', 'Republic Day'),
            ('2026-03-03', 'Holi'),
            ('2026-03-21', 'Id-Ul-Fitr'),
            ('2026-03-30', 'Shri Ram Navmi'),
            ('2026-04-02', 'Mahavir Jayanti'),
            ('2026-04-03', 'Good Friday'),
            ('2026-04-06', 'Dr. Baba Saheb Ambedkar Jayanti'),
            ('2026-05-01', 'Maharashtra Day'),
            ('2026-08-15', 'Independence Day'),
            ('2026-09-16', 'Ganesh Chaturthi'),
            ('2026-10-02', 'Mahatma Gandhi Jayanti'),
            ('2026-10-20', 'Dussehra'),
            ('2026-11-10', 'Diwali Laxmi Pujan'),
            ('2026-12-25', 'Christmas'),
        ]

        all_known = {
            2024: known_holidays_2024,
            2025: known_holidays_2025,
            2026: known_holidays_2026,
        }

        if year not in all_known:
            logger.warning(f"No fallback holidays available for year {year}")
            return []

        holidays = []
        for date_str, name in all_known[year]:
            holidays.append({
                'date': datetime.strptime(date_str, '%Y-%m-%d').date(),
                'name': name,
                'type': 'market_holiday',
                'source': 'Fallback (hardcoded)',
                'verified': False
            })

        logger.info(f"Using {len(holidays)} fallback NSE holidays for {year}")
        return holidays

    # =====================================================
    # BSE HOLIDAYS
    # =====================================================

    async def fetch_bse_holidays(self, year: int) -> List[Dict]:
        """
        Fetch BSE holidays

        BSE usually has the same holidays as NSE for equity segment
        """
        # BSE typically mirrors NSE for most holidays
        # We can fetch from NSE and apply to BSE as well

        nse_holidays = await self.fetch_nse_holidays(year)

        # Convert to BSE format
        bse_holidays = [
            {
                **h,
                'source': f"BSE (mirrored from {h['source']})"
            }
            for h in nse_holidays
        ]

        logger.info(f"Generated {len(bse_holidays)} BSE holidays for {year}")
        return bse_holidays

    # =====================================================
    # MCX HOLIDAYS
    # =====================================================

    async def fetch_mcx_holidays(self, year: int) -> List[Dict]:
        """
        Fetch MCX (commodity) holidays

        MCX has some different holidays than equity markets
        """
        # MCX typically has fewer holidays than equity markets
        # Major holidays only

        major_holidays_2025 = [
            ('2025-01-26', 'Republic Day'),
            ('2025-03-14', 'Holi'),
            ('2025-04-18', 'Good Friday'),
            ('2025-08-15', 'Independence Day'),
            ('2025-10-02', 'Mahatma Gandhi Jayanti'),
            ('2025-11-01', 'Diwali'),
            ('2025-12-25', 'Christmas'),
        ]

        major_holidays_2024 = [
            ('2024-01-26', 'Republic Day'),
            ('2024-03-25', 'Holi'),
            ('2024-03-29', 'Good Friday'),
            ('2024-08-15', 'Independence Day'),
            ('2024-10-02', 'Mahatma Gandhi Jayanti'),
            ('2024-11-01', 'Diwali'),
            ('2024-12-25', 'Christmas'),
        ]

        major_holidays_2026 = [
            ('2026-01-26', 'Republic Day'),
            ('2026-03-03', 'Holi'),
            ('2026-04-03', 'Good Friday'),
            ('2026-08-15', 'Independence Day'),
            ('2026-10-02', 'Mahatma Gandhi Jayanti'),
            ('2026-11-10', 'Diwali'),
            ('2026-12-25', 'Christmas'),
        ]

        all_mcx = {
            2024: major_holidays_2024,
            2025: major_holidays_2025,
            2026: major_holidays_2026,
        }

        if year not in all_mcx:
            return []

        holidays = []
        for date_str, name in all_mcx[year]:
            holidays.append({
                'date': datetime.strptime(date_str, '%Y-%m-%d').date(),
                'name': name,
                'type': 'market_holiday',
                'source': 'MCX (fallback)',
                'verified': False
            })

        logger.info(f"Generated {len(holidays)} MCX holidays for {year}")
        return holidays

    # =====================================================
    # CURRENCY MARKET HOLIDAYS
    # =====================================================

    async def fetch_currency_holidays(self, year: int) -> List[Dict]:
        """
        Fetch currency market holidays

        Currency markets typically follow NSE calendar
        """
        nse_holidays = await self.fetch_nse_holidays(year)

        currency_holidays = [
            {
                **h,
                'source': f"Currency (mirrored from {h['source']})"
            }
            for h in nse_holidays
        ]

        logger.info(f"Generated {len(currency_holidays)} currency market holidays for {year}")
        return currency_holidays

    # =====================================================
    # DATABASE OPERATIONS
    # =====================================================

    async def sync_holidays_to_db(
        self,
        calendar_code: str,
        year: int,
        holidays: List[Dict]
    ) -> int:
        """Sync fetched holidays to database"""

        async with self.db_pool.acquire() as conn:
            # Get calendar type ID
            calendar_id = await conn.fetchval(
                "SELECT id FROM calendar_types WHERE code = $1",
                calendar_code
            )

            if not calendar_id:
                raise ValueError(f"Calendar type {calendar_code} not found")

            inserted = 0
            updated = 0

            for holiday in holidays:
                result = await conn.fetchval("""
                    INSERT INTO calendar_events (
                        calendar_type_id,
                        event_date,
                        event_name,
                        event_type,
                        is_trading_day,
                        category,
                        source,
                        source_url,
                        verified,
                        metadata
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                    ON CONFLICT (calendar_type_id, event_date, event_name)
                    DO UPDATE SET
                        event_type = EXCLUDED.event_type,
                        is_trading_day = EXCLUDED.is_trading_day,
                        category = EXCLUDED.category,
                        source = EXCLUDED.source,
                        verified = EXCLUDED.verified,
                        updated_at = NOW()
                    RETURNING (xmax = 0) AS inserted
                """,
                    calendar_id,
                    holiday['date'],
                    holiday['name'],
                    holiday.get('type', 'holiday'),
                    False,  # is_trading_day
                    holiday.get('category', 'market_holiday'),
                    holiday.get('source', 'Unknown'),
                    holiday.get('source_url'),
                    holiday.get('verified', False),
                    json.dumps(holiday.get('metadata', {}))
                )

                if result:
                    inserted += 1
                else:
                    updated += 1

            logger.info(
                f"Synced {len(holidays)} holidays for {calendar_code} {year}: "
                f"{inserted} inserted, {updated} updated"
            )

            return inserted + updated

    async def sync_all_calendars(self, years: List[int] = None):
        """Sync all calendar types for specified years"""

        if years is None:
            current_year = datetime.now().year
            years = [current_year - 1, current_year, current_year + 1]

        calendar_fetchers = {
            'NSE': self.fetch_nse_holidays,
            'BSE': self.fetch_bse_holidays,
            'MCX': self.fetch_mcx_holidays,
            'NSE_CURRENCY': self.fetch_currency_holidays,
        }

        total_synced = 0

        for calendar_code, fetcher in calendar_fetchers.items():
            logger.info(f"Syncing {calendar_code} holidays...")

            for year in years:
                try:
                    holidays = await fetcher(year)
                    count = await self.sync_holidays_to_db(calendar_code, year, holidays)
                    total_synced += count
                    logger.success(f"✓ {calendar_code} {year}: {count} holidays")

                except Exception as e:
                    logger.error(f"✗ Failed to sync {calendar_code} {year}: {e}")

        logger.success(f"Total holidays synced: {total_synced}")
        return total_synced


# =====================================================
# CLI
# =====================================================

async def main():
    import argparse

    parser = argparse.ArgumentParser(description='Fetch and sync market holidays')
    parser.add_argument('--sync-all', action='store_true', help='Sync all calendars')
    parser.add_argument('--calendar', type=str, help='Specific calendar (NSE, BSE, MCX)')
    parser.add_argument('--year', type=int, help='Specific year')
    parser.add_argument('--years', type=str, help='Years to sync (comma-separated)')

    args = parser.parse_args()

    # Get database pool
    db_pool = await get_db_pool()
    fetcher = HolidayFetcher(db_pool)

    try:
        if args.sync_all:
            years = None
            if args.years:
                years = [int(y.strip()) for y in args.years.split(',')]
            elif args.year:
                years = [args.year]

            await fetcher.sync_all_calendars(years)

        elif args.calendar and args.year:
            calendar_fetchers = {
                'NSE': fetcher.fetch_nse_holidays,
                'BSE': fetcher.fetch_bse_holidays,
                'MCX': fetcher.fetch_mcx_holidays,
                'CURRENCY': fetcher.fetch_currency_holidays,
            }

            if args.calendar.upper() not in calendar_fetchers:
                logger.error(f"Unknown calendar: {args.calendar}")
                return

            holidays = await calendar_fetchers[args.calendar.upper()](args.year)
            await fetcher.sync_holidays_to_db(args.calendar.upper(), args.year, holidays)

        else:
            parser.print_help()

    finally:
        await db_pool.close()


if __name__ == '__main__':
    asyncio.run(main())
