"""
Corporate Actions Fetcher Service

Fetches corporate actions data from BSE and NSE exchanges.
Handles deduplication and merging of data from both sources.
"""

import asyncio
import logging
from datetime import date, datetime, timedelta
from typing import List, Dict, Optional, Tuple
from decimal import Decimal
import asyncpg

# Third-party imports (optional - install if needed)
try:
    from bse import BSE
    BSE_AVAILABLE = True
except ImportError:
    BSE_AVAILABLE = False
    logging.warning("BseIndiaApi not available. Install with: pip install bse")

# For NSE, we'll use web scraping or a simple HTTP client
import aiohttp
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class CorporateAction:
    """Model for a corporate action"""

    def __init__(self,
                 symbol: str,
                 action_type: str,
                 title: str,
                 ex_date: Optional[date] = None,
                 record_date: Optional[date] = None,
                 payment_date: Optional[date] = None,
                 action_data: Optional[Dict] = None,
                 source: str = 'manual',
                 source_id: Optional[str] = None,
                 **kwargs):
        self.symbol = symbol
        self.action_type = action_type
        self.title = title
        self.ex_date = ex_date
        self.record_date = record_date
        self.payment_date = payment_date
        self.action_data = action_data or {}
        self.source = source
        self.source_id = source_id

        # Optional fields
        self.announcement_date = kwargs.get('announcement_date')
        self.effective_date = kwargs.get('effective_date')
        self.start_date = kwargs.get('start_date')
        self.end_date = kwargs.get('end_date')
        self.description = kwargs.get('description')
        self.purpose = kwargs.get('purpose')
        self.status = kwargs.get('status', 'announced')

    def to_dict(self) -> Dict:
        """Convert to dictionary for database insertion"""
        return {
            'symbol': self.symbol,
            'action_type': self.action_type,
            'title': self.title,
            'ex_date': self.ex_date,
            'record_date': self.record_date,
            'payment_date': self.payment_date,
            'action_data': self.action_data,
            'source': self.source,
            'source_id': self.source_id,
            'announcement_date': self.announcement_date,
            'effective_date': self.effective_date,
            'start_date': self.start_date,
            'end_date': self.end_date,
            'description': self.description,
            'purpose': self.purpose,
            'status': self.status
        }

    def __repr__(self):
        return f"CorporateAction({self.symbol}, {self.action_type}, {self.ex_date})"


class BSEFetcher:
    """Fetches corporate actions from BSE"""

    def __init__(self):
        if not BSE_AVAILABLE:
            logger.warning("BSE API not available")

    async def fetch_corporate_actions(self,
                                       symbol: Optional[str] = None,
                                       scrip_code: Optional[int] = None,
                                       from_date: Optional[date] = None,
                                       to_date: Optional[date] = None) -> List[CorporateAction]:
        """
        Fetch corporate actions from BSE

        Args:
            symbol: Stock symbol (e.g., 'TCS')
            scrip_code: BSE scrip code (e.g., 532540 for TCS)
            from_date: Start date
            to_date: End date

        Returns:
            List of CorporateAction objects
        """
        if not BSE_AVAILABLE:
            logger.error("BSE API not available. Install bse package.")
            return []

        try:
            # Use asyncio to run synchronous BSE API in thread
            loop = asyncio.get_event_loop()
            actions = await loop.run_in_executor(
                None,
                self._fetch_bse_actions_sync,
                scrip_code
            )
            return actions
        except Exception as e:
            logger.error(f"Error fetching BSE corporate actions: {e}")
            return []

    def _fetch_bse_actions_sync(self, scrip_code: int) -> List[CorporateAction]:
        """Synchronous BSE fetch (called in thread)"""
        if not BSE_AVAILABLE:
            return []

        actions = []
        try:
            with BSE(download_folder='/tmp') as bse:
                # Fetch corporate actions
                data = bse.actions(scripcode=scrip_code)

                # Parse the response
                for item in data:
                    action = self._parse_bse_action(item, scrip_code)
                    if action:
                        actions.append(action)

        except Exception as e:
            logger.error(f"Error in BSE sync fetch: {e}")

        return actions

    def _parse_bse_action(self, item: Dict, scrip_code: int) -> Optional[CorporateAction]:
        """
        Parse BSE corporate action data

        Expected fields from BSE:
        - EXDATE: Ex-date
        - RECORD_DATE: Record date
        - PURPOSE: Purpose/description
        - BC_START_DATE: Book closure start
        - BC_END_DATE: Book closure end
        - etc.
        """
        try:
            # Extract dates
            ex_date = self._parse_date(item.get('EXDATE'))
            record_date = self._parse_date(item.get('RECORD_DATE'))

            # Determine action type from purpose
            purpose = item.get('PURPOSE', '').upper()
            action_type, title, action_data = self._classify_action(purpose, item)

            # Create CorporateAction
            return CorporateAction(
                symbol=str(scrip_code),  # Will be resolved to actual symbol later
                action_type=action_type,
                title=title,
                ex_date=ex_date,
                record_date=record_date,
                action_data=action_data,
                source='BSE',
                source_id=f"BSE_{scrip_code}_{ex_date or record_date}",
                purpose=purpose,
                start_date=self._parse_date(item.get('BC_START_DATE')),
                end_date=self._parse_date(item.get('BC_END_DATE'))
            )
        except Exception as e:
            logger.error(f"Error parsing BSE action: {e}")
            return None

    def _classify_action(self, purpose: str, item: Dict) -> Tuple[str, str, Dict]:
        """
        Classify corporate action based on purpose

        Returns:
            (action_type, title, action_data)
        """
        purpose_upper = purpose.upper()

        # Dividend
        if 'DIVIDEND' in purpose_upper:
            amount = self._extract_amount(purpose)
            action_type = 'DIVIDEND'
            title = f"Dividend - {purpose}"
            action_data = {
                'amount': amount,
                'currency': 'INR',
                'type': self._determine_dividend_type(purpose)
            }

        # Bonus
        elif 'BONUS' in purpose_upper:
            ratio = self._extract_ratio(purpose)
            action_type = 'BONUS'
            title = f"Bonus Issue - {ratio}"
            action_data = {
                'ratio': ratio,
                'old_shares': ratio.split(':')[0] if ':' in ratio else 1,
                'new_shares': ratio.split(':')[1] if ':' in ratio else 1
            }

        # Split
        elif 'SPLIT' in purpose_upper or 'SUB-DIVISION' in purpose_upper:
            action_type = 'SPLIT'
            title = f"Stock Split - {purpose}"
            action_data = self._extract_split_data(purpose)

        # Rights
        elif 'RIGHTS' in purpose_upper:
            action_type = 'RIGHTS'
            title = f"Rights Issue - {purpose}"
            action_data = {
                'ratio': self._extract_ratio(purpose),
                'price': self._extract_amount(purpose)
            }

        # AGM
        elif 'AGM' in purpose_upper or 'ANNUAL GENERAL MEETING' in purpose_upper:
            action_type = 'AGM'
            title = 'Annual General Meeting'
            action_data = {}

        # EGM
        elif 'EGM' in purpose_upper or 'EXTRAORDINARY GENERAL MEETING' in purpose_upper:
            action_type = 'EGM'
            title = 'Extraordinary General Meeting'
            action_data = {}

        # Book Closure
        elif 'BOOK CLOSURE' in purpose_upper or 'BC' == purpose_upper:
            action_type = 'BOOK_CLOSURE'
            title = f"Book Closure - {purpose}"
            action_data = {}

        # Buyback
        elif 'BUYBACK' in purpose_upper or 'BUY BACK' in purpose_upper:
            action_type = 'BUYBACK'
            title = f"Buyback - {purpose}"
            action_data = {'price': self._extract_amount(purpose)}

        # Default
        else:
            action_type = 'BOOK_CLOSURE'
            title = purpose
            action_data = {}

        return action_type, title, action_data

    def _extract_amount(self, text: str) -> Optional[float]:
        """Extract amount from text (e.g., 'Rs 10.50')"""
        import re
        match = re.search(r'Rs\.?\s*(\d+\.?\d*)', text, re.IGNORECASE)
        if match:
            return float(match.group(1))
        return None

    def _extract_ratio(self, text: str) -> str:
        """Extract ratio from text (e.g., '1:2')"""
        import re
        match = re.search(r'(\d+)\s*:\s*(\d+)', text)
        if match:
            return f"{match.group(1)}:{match.group(2)}"
        return "1:1"

    def _extract_split_data(self, text: str) -> Dict:
        """Extract split data from text"""
        import re
        # Try to find old FV and new FV (e.g., "Rs 10 to Rs 2")
        match = re.search(r'Rs\.?\s*(\d+)\s*to\s*Rs\.?\s*(\d+)', text, re.IGNORECASE)
        if match:
            old_fv = int(match.group(1))
            new_fv = int(match.group(2))
            return {
                'old_fv': old_fv,
                'new_fv': new_fv,
                'ratio': f"1:{old_fv // new_fv if new_fv > 0 else 1}"
            }
        return {'ratio': '1:1'}

    def _determine_dividend_type(self, text: str) -> str:
        """Determine dividend type (interim, final, special)"""
        text_upper = text.upper()
        if 'INTERIM' in text_upper:
            return 'interim'
        elif 'FINAL' in text_upper:
            return 'final'
        elif 'SPECIAL' in text_upper:
            return 'special'
        return 'final'

    def _parse_date(self, date_str: Optional[str]) -> Optional[date]:
        """Parse date string to date object"""
        if not date_str:
            return None

        try:
            # Try multiple date formats
            for fmt in ['%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y', '%Y/%m/%d']:
                try:
                    return datetime.strptime(str(date_str), fmt).date()
                except ValueError:
                    continue
            logger.warning(f"Could not parse date: {date_str}")
            return None
        except Exception as e:
            logger.error(f"Error parsing date {date_str}: {e}")
            return None


class NSEFetcher:
    """Fetches corporate actions from NSE"""

    BASE_URL = "https://www.nseindia.com"

    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
            'Accept-Language': 'en-US,en;q=0.9',
        }
        self.session = aiohttp.ClientSession(headers=headers)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def fetch_corporate_actions(self,
                                       symbol: Optional[str] = None,
                                       from_date: Optional[date] = None,
                                       to_date: Optional[date] = None) -> List[CorporateAction]:
        """
        Fetch corporate actions from NSE

        Note: NSE API access is restricted. This is a placeholder implementation.
        In production, you may need to:
        1. Use official NSE data subscription
        2. Use third-party data providers (like StockInsights.ai)
        3. Implement web scraping (may violate ToS)
        """
        logger.warning("NSE fetcher not fully implemented. Use manual import or third-party APIs.")
        return []

        # Placeholder for future implementation
        # try:
        #     url = f"{self.BASE_URL}/api/corporate-actions"
        #     params = {
        #         'symbol': symbol,
        #         'from': from_date.isoformat() if from_date else None,
        #         'to': to_date.isoformat() if to_date else None
        #     }
        #     async with self.session.get(url, params=params) as response:
        #         if response.status == 200:
        #             data = await response.json()
        #             return self._parse_nse_response(data)
        # except Exception as e:
        #     logger.error(f"Error fetching NSE corporate actions: {e}")
        #     return []


class CorporateActionsSync:
    """
    Main service for syncing corporate actions from BSE and NSE
    """

    def __init__(self, db_pool: asyncpg.Pool):
        self.db_pool = db_pool
        self.bse_fetcher = BSEFetcher()
        self.nse_fetcher = NSEFetcher()

    async def sync_instrument(self,
                               symbol: str,
                               from_date: Optional[date] = None,
                               to_date: Optional[date] = None) -> Dict:
        """
        Sync corporate actions for a specific instrument

        Args:
            symbol: Stock symbol (e.g., 'TCS')
            from_date: Start date (default: 30 days ago)
            to_date: End date (default: 90 days ahead)

        Returns:
            Dict with sync statistics
        """
        from_date = from_date or (date.today() - timedelta(days=30))
        to_date = to_date or (date.today() + timedelta(days=90))

        logger.info(f"Syncing corporate actions for {symbol} from {from_date} to {to_date}")

        # Resolve instrument
        instrument = await self._resolve_instrument(symbol)
        if not instrument:
            logger.error(f"Instrument not found: {symbol}")
            return {'error': f'Instrument not found: {symbol}'}

        # Fetch from BSE
        bse_actions = []
        if instrument['bse_code']:
            bse_actions = await self.bse_fetcher.fetch_corporate_actions(
                scrip_code=instrument['bse_code'],
                from_date=from_date,
                to_date=to_date
            )

        # Fetch from NSE
        nse_actions = []
        async with self.nse_fetcher as nse:
            if instrument['nse_symbol']:
                nse_actions = await nse.fetch_corporate_actions(
                    symbol=instrument['nse_symbol'],
                    from_date=from_date,
                    to_date=to_date
                )

        # Merge and deduplicate
        merged_actions = self._merge_actions(bse_actions, nse_actions)

        # Save to database
        saved_count = await self._save_actions(instrument['id'], merged_actions)

        return {
            'symbol': symbol,
            'bse_count': len(bse_actions),
            'nse_count': len(nse_actions),
            'merged_count': len(merged_actions),
            'saved_count': saved_count
        }

    async def sync_all(self,
                       from_date: Optional[date] = None,
                       to_date: Optional[date] = None,
                       limit: int = 100) -> Dict:
        """
        Sync corporate actions for all active instruments

        Args:
            from_date: Start date
            to_date: End date
            limit: Max number of instruments to sync

        Returns:
            Dict with overall sync statistics
        """
        from_date = from_date or (date.today() - timedelta(days=30))
        to_date = to_date or (date.today() + timedelta(days=90))

        logger.info(f"Syncing corporate actions for all instruments (limit={limit})")

        # Get all active instruments
        instruments = await self._get_active_instruments(limit)

        total_saved = 0
        errors = []

        for instrument in instruments:
            try:
                result = await self.sync_instrument(
                    instrument['symbol'],
                    from_date,
                    to_date
                )
                if 'error' not in result:
                    total_saved += result.get('saved_count', 0)
                else:
                    errors.append(result)

                # Rate limiting - be nice to APIs
                await asyncio.sleep(1)

            except Exception as e:
                logger.error(f"Error syncing {instrument['symbol']}: {e}")
                errors.append({'symbol': instrument['symbol'], 'error': str(e)})

        return {
            'instruments_processed': len(instruments),
            'total_saved': total_saved,
            'errors': errors
        }

    def _merge_actions(self,
                       bse_actions: List[CorporateAction],
                       nse_actions: List[CorporateAction]) -> List[CorporateAction]:
        """
        Merge and deduplicate corporate actions from BSE and NSE

        Strategy:
        - If same action (same type, ex-date) from both exchanges -> merge
        - Prefer NSE data, supplement with BSE data
        """
        merged = {}

        # Add NSE actions first (they take priority)
        for action in nse_actions:
            key = self._action_key(action)
            merged[key] = action

        # Add BSE actions, merging if duplicate
        for action in bse_actions:
            key = self._action_key(action)

            if key in merged:
                # Merge with existing NSE action
                merged[key] = self._merge_single_action(merged[key], action)
            else:
                # Add new BSE action
                merged[key] = action

        return list(merged.values())

    def _action_key(self, action: CorporateAction) -> str:
        """Generate unique key for action"""
        key_date = action.ex_date or action.record_date or action.announcement_date
        return f"{action.symbol}_{action.action_type}_{key_date}"

    def _merge_single_action(self,
                              nse_action: CorporateAction,
                              bse_action: CorporateAction) -> CorporateAction:
        """
        Merge two actions (NSE preferred)

        Returns merged CorporateAction
        """
        # Start with NSE action
        merged_dict = nse_action.to_dict()

        # Supplement missing fields from BSE
        bse_dict = bse_action.to_dict()
        for field in ['record_date', 'payment_date', 'announcement_date', 'description']:
            if not merged_dict.get(field) and bse_dict.get(field):
                merged_dict[field] = bse_dict[field]

        # Merge action_data
        merged_dict['action_data'] = {
            **bse_dict.get('action_data', {}),
            **merged_dict.get('action_data', {})
        }

        # Update source
        merged_dict['source'] = 'NSE,BSE'

        return CorporateAction(**merged_dict)

    async def _resolve_instrument(self, symbol: str) -> Optional[Dict]:
        """Resolve instrument by symbol"""
        async with self.db_pool.acquire() as conn:
            result = await conn.fetchrow("""
                SELECT id, symbol, company_name, isin, nse_symbol, bse_code
                FROM instruments
                WHERE symbol = $1 OR nse_symbol = $1
                AND is_active = true
                LIMIT 1
            """, symbol.upper())

            return dict(result) if result else None

    async def _get_active_instruments(self, limit: int) -> List[Dict]:
        """Get list of active instruments"""
        async with self.db_pool.acquire() as conn:
            results = await conn.fetch("""
                SELECT id, symbol, company_name, isin, nse_symbol, bse_code
                FROM instruments
                WHERE is_active = true
                AND instrument_type = 'EQ'
                ORDER BY symbol
                LIMIT $1
            """, limit)

            return [dict(r) for r in results]

    async def _save_actions(self,
                             instrument_id: int,
                             actions: List[CorporateAction]) -> int:
        """
        Save corporate actions to database

        Returns:
            Number of actions saved
        """
        saved_count = 0

        async with self.db_pool.acquire() as conn:
            for action in actions:
                try:
                    await conn.execute("""
                        INSERT INTO corporate_actions (
                            instrument_id,
                            action_type,
                            title,
                            ex_date,
                            record_date,
                            payment_date,
                            announcement_date,
                            effective_date,
                            start_date,
                            end_date,
                            action_data,
                            description,
                            purpose,
                            source,
                            source_id,
                            status
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
                        ON CONFLICT (instrument_id, action_type, ex_date, source_id)
                        DO UPDATE SET
                            title = EXCLUDED.title,
                            record_date = EXCLUDED.record_date,
                            payment_date = EXCLUDED.payment_date,
                            action_data = EXCLUDED.action_data,
                            updated_at = NOW()
                    """,
                                      instrument_id,
                                      action.action_type,
                                      action.title,
                                      action.ex_date,
                                      action.record_date,
                                      action.payment_date,
                                      action.announcement_date,
                                      action.effective_date,
                                      action.start_date,
                                      action.end_date,
                                      action.action_data,
                                      action.description,
                                      action.purpose,
                                      action.source,
                                      action.source_id,
                                      action.status
                                      )
                    saved_count += 1

                except Exception as e:
                    logger.error(f"Error saving corporate action: {e}")

        return saved_count


# CLI interface for manual sync
async def main():
    import argparse
    import os

    parser = argparse.ArgumentParser(description='Sync corporate actions from BSE/NSE')
    parser.add_argument('--symbol', help='Specific symbol to sync')
    parser.add_argument('--all', action='store_true', help='Sync all instruments')
    parser.add_argument('--limit', type=int, default=100, help='Max instruments to sync (default: 100)')
    parser.add_argument('--days-ago', type=int, default=30, help='Start date (days ago)')
    parser.add_argument('--days-ahead', type=int, default=90, help='End date (days ahead)')

    args = parser.parse_args()

    # Database connection
    db_url = os.getenv('DATABASE_URL', 'postgresql://stocksblitz:stocksblitz123@localhost:5432/stocksblitz_unified')
    pool = await asyncpg.create_pool(db_url)

    try:
        syncer = CorporateActionsSync(pool)

        from_date = date.today() - timedelta(days=args.days_ago)
        to_date = date.today() + timedelta(days=args.days_ahead)

        if args.symbol:
            result = await syncer.sync_instrument(args.symbol, from_date, to_date)
            print(f"Sync result: {result}")
        elif args.all:
            result = await syncer.sync_all(from_date, to_date, args.limit)
            print(f"Sync result: {result}")
        else:
            print("Please specify --symbol or --all")

    finally:
        await pool.close()


if __name__ == '__main__':
    asyncio.run(main())
