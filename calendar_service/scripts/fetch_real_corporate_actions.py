#!/usr/bin/env python3
"""
Fetch real corporate actions data from NSE and populate database
"""

import asyncio
import asyncpg
import requests
from datetime import datetime, date
import re
import sys
import json

# Database configuration
import os

# Use environment variable or detect from POSTGRES_URL
postgres_url = os.getenv('POSTGRES_URL', '')
if postgres_url:
    # Parse from POSTGRES_URL (format: postgresql://user:pass@host:port/dbname)
    import re
    match = re.search(r'postgresql://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)', postgres_url)
    if match:
        DB_CONFIG = {
            'user': match.group(1),
            'password': match.group(2),
            'host': match.group(3),
            'port': int(match.group(4)),
            'database': match.group(5)
        }
    else:
        DB_CONFIG = {
            'host': 'localhost',
            'port': 5432,
            'database': 'stocksblitz_unified',
            'user': 'stocksblitz',
            'password': 'stocksblitz123'
        }
else:
    # Default config
    DB_CONFIG = {
        'host': 'localhost',
        'port': 5432,
        'database': 'stocksblitz_unified',
        'user': 'stocksblitz',
        'password': 'stocksblitz123'
    }


class NSERealDataFetcher:
    """Fetch real corporate actions from NSE"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
            'Accept-Language': 'en-US,en;q=0.9'
        })

    def fetch_nse_corporate_actions(self):
        """Fetch corporate actions from NSE"""
        try:
            # First visit homepage to get cookies
            self.session.get('https://www.nseindia.com', timeout=10)

            # Get corporate actions
            url = "https://www.nseindia.com/api/corporates-corporateActions?index=equities"
            response = self.session.get(url, timeout=10)

            if response.status_code == 200:
                data = response.json()
                print(f"✓ Fetched {len(data)} corporate actions from NSE")
                return data
            else:
                print(f"✗ NSE returned status: {response.status_code}")
                return []

        except Exception as e:
            print(f"✗ Error fetching from NSE: {e}")
            return []

    def parse_nse_action(self, item):
        """Parse NSE corporate action item"""
        symbol = item.get('symbol', '').strip()
        subject = item.get('subject', '').strip()
        company_name = item.get('comp', '').strip()
        isin = item.get('isin', '').strip()

        # Parse dates
        ex_date = self._parse_date(item.get('exDate'))
        record_date = self._parse_date(item.get('recDate'))

        # Classify action type
        action_type, title, action_data = self._classify_nse_action(subject)

        return {
            'symbol': symbol,
            'company_name': company_name,
            'isin': isin,
            'action_type': action_type,
            'title': title,
            'ex_date': ex_date,
            'record_date': record_date,
            'action_data': action_data,
            'source': 'NSE',
            'source_id': f"NSE_{symbol}_{ex_date or record_date}_{action_type}",
            'description': subject
        }

    def _parse_date(self, date_str):
        """Parse NSE date format (DD-MMM-YYYY)"""
        if not date_str or date_str == '-':
            return None

        try:
            # Format: "04-Nov-2025"
            return datetime.strptime(date_str, "%d-%b-%Y").date()
        except:
            return None

    def _classify_nse_action(self, subject):
        """Classify NSE corporate action"""
        subject_upper = subject.upper()

        # Dividend
        if 'DIVIDEND' in subject_upper:
            amount = self._extract_amount(subject)
            div_type = 'interim' if 'INTERIM' in subject_upper else 'final'
            if 'SPECIAL' in subject_upper:
                div_type = 'special'

            return (
                'DIVIDEND',
                subject,
                {
                    'amount': amount,
                    'currency': 'INR',
                    'type': div_type
                }
            )

        # Bonus
        elif 'BONUS' in subject_upper:
            ratio = self._extract_ratio(subject)
            return (
                'BONUS',
                subject,
                {
                    'ratio': ratio
                }
            )

        # Split
        elif 'SPLIT' in subject_upper or 'SUB-DIVISION' in subject_upper:
            return (
                'SPLIT',
                subject,
                self._extract_split_data(subject)
            )

        # Rights
        elif 'RIGHTS' in subject_upper:
            return (
                'RIGHTS',
                subject,
                {
                    'ratio': self._extract_ratio(subject),
                    'price': self._extract_amount(subject)
                }
            )

        # AGM/EGM
        elif 'AGM' in subject_upper or 'ANNUAL GENERAL MEETING' in subject_upper:
            return ('AGM', 'Annual General Meeting', {})

        elif 'EGM' in subject_upper or 'EXTRAORDINARY' in subject_upper:
            return ('EGM', 'Extraordinary General Meeting', {})

        # Buyback
        elif 'BUYBACK' in subject_upper or 'BUY BACK' in subject_upper:
            return (
                'BUYBACK',
                subject,
                {'price': self._extract_amount(subject)}
            )

        # Distribution (for InvITs/REITs)
        elif 'DISTRIBUTION' in subject_upper:
            return (
                'DIVIDEND',
                subject,
                {
                    'amount': self._extract_amount(subject),
                    'currency': 'INR',
                    'type': 'distribution'
                }
            )

        # Default: Book Closure
        else:
            return ('BOOK_CLOSURE', subject, {})

    def _extract_amount(self, text):
        """Extract amount from text"""
        # Look for patterns like "Rs 3.75", "Rs. 10.50", "Rs.10"
        match = re.search(r'Rs\.?\s*(\d+\.?\d*)', text, re.IGNORECASE)
        if match:
            return float(match.group(1))
        return None

    def _extract_ratio(self, text):
        """Extract ratio from text (e.g., '1:2')"""
        match = re.search(r'(\d+)\s*:\s*(\d+)', text)
        if match:
            return f"{match.group(1)}:{match.group(2)}"
        return "1:1"

    def _extract_split_data(self, text):
        """Extract split data"""
        match = re.search(r'Rs\.?\s*(\d+)\s*(?:to|into)\s*Rs\.?\s*(\d+)', text, re.IGNORECASE)
        if match:
            old_fv = int(match.group(1))
            new_fv = int(match.group(2))
            return {
                'old_fv': old_fv,
                'new_fv': new_fv,
                'ratio': f"1:{old_fv // new_fv if new_fv > 0 else 1}"
            }
        return {'ratio': '1:1'}


async def populate_database(actions_data):
    """Populate database with fetched data"""

    pool = await asyncpg.create_pool(**DB_CONFIG)

    try:
        instruments_added = 0
        actions_added = 0
        actions_updated = 0

        async with pool.acquire() as conn:
            for action in actions_data:
                try:
                    # First, ensure instrument exists
                    # Use existing instruments table structure
                    instrument_key = f"NSE:{action['symbol']}"

                    instrument_id = await conn.fetchval("""
                        INSERT INTO instruments (
                            instrument_key, symbol, exchange, asset_type, name,
                            isin, nse_symbol, company_name, is_active
                        ) VALUES ($1, $2, 'NSE', 'EQ', $3, $4, $5, $6, true)
                        ON CONFLICT (instrument_key)
                        DO UPDATE SET
                            isin = COALESCE(EXCLUDED.isin, instruments.isin),
                            nse_symbol = COALESCE(EXCLUDED.nse_symbol, instruments.nse_symbol),
                            company_name = EXCLUDED.company_name,
                            name = COALESCE(instruments.name, EXCLUDED.name),
                            updated_at = NOW()
                        RETURNING id
                    """,
                        instrument_key,
                        action['symbol'],
                        action['company_name'],
                        action['isin'] if action['isin'] else None,
                        action['symbol'],
                        action['company_name']
                    )

                    if instrument_id:
                        instruments_added += 1

                    # Get instrument_id if not returned (in case of conflict)
                    if not instrument_id:
                        instrument_id = await conn.fetchval("""
                            SELECT id FROM instruments
                            WHERE instrument_key = $1 OR (symbol = $2 AND exchange = 'NSE')
                        """, instrument_key, action['symbol'])

                    if not instrument_id:
                        print(f"  ✗ Could not resolve instrument for {action['symbol']}")
                        continue

                    # Insert corporate action
                    # Convert action_data dict to JSON string
                    action_data_json = json.dumps(action['action_data']) if action['action_data'] else '{}'

                    # UPSERT: Keep old records intact, update if needed, add new ones
                    result = await conn.fetchrow("""
                        INSERT INTO corporate_actions (
                            instrument_id,
                            action_type,
                            title,
                            ex_date,
                            record_date,
                            payment_date,
                            action_data,
                            description,
                            source,
                            source_id,
                            status
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8, $9, $10, $11)
                        ON CONFLICT (source_id) WHERE source_id IS NOT NULL
                        DO UPDATE SET
                            title = EXCLUDED.title,
                            record_date = COALESCE(EXCLUDED.record_date, corporate_actions.record_date),
                            payment_date = COALESCE(EXCLUDED.payment_date, corporate_actions.payment_date),
                            action_data = EXCLUDED.action_data,
                            description = COALESCE(EXCLUDED.description, corporate_actions.description),
                            status = CASE
                                WHEN corporate_actions.status = 'completed' THEN 'completed'
                                ELSE EXCLUDED.status
                            END,
                            updated_at = NOW()
                        RETURNING id,
                                  (xmax = 0) AS inserted  -- True if inserted, False if updated
                    """,
                        instrument_id,
                        action['action_type'],
                        action['title'],
                        action['ex_date'],
                        action['record_date'],
                        action.get('payment_date'),
                        action_data_json,
                        action['description'],
                        action['source'],
                        action['source_id'],
                        'announced'
                    )

                    if result:
                        if result['inserted']:
                            actions_added += 1
                            print(f"  ✓ NEW: {action['symbol']}: {action['title'][:60]}... (ex: {action['ex_date']})")
                        else:
                            actions_updated += 1
                            print(f"  ✓ UPD: {action['symbol']}: {action['title'][:60]}... (ex: {action['ex_date']})")

                except Exception as e:
                    print(f"  ✗ Error processing {action.get('symbol', 'unknown')}: {e}")

        print(f"\n{'='*60}")
        print(f"Summary:")
        print(f"  Instruments added/updated: {instruments_added}")
        print(f"  Corporate actions added: {actions_added}")
        print(f"  Corporate actions updated: {actions_updated}")
        print(f"{'='*60}")

    finally:
        await pool.close()


async def main():
    print("Fetching real corporate actions data from NSE...")
    print("="*60)

    fetcher = NSERealDataFetcher()

    # Fetch from NSE
    nse_data = fetcher.fetch_nse_corporate_actions()

    if not nse_data:
        print("No data fetched. Exiting.")
        return 1

    # Parse all actions
    print(f"\nParsing {len(nse_data)} actions...")
    parsed_actions = []
    for item in nse_data:
        try:
            parsed = fetcher.parse_nse_action(item)
            parsed_actions.append(parsed)
        except Exception as e:
            print(f"  ✗ Error parsing action: {e}")

    print(f"Successfully parsed {len(parsed_actions)} actions")

    # Populate database
    print(f"\nPopulating database...")
    await populate_database(parsed_actions)

    print("\n✓ Done! Real corporate actions data has been loaded.")
    return 0


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
