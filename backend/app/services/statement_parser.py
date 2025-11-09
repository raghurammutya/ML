"""
Zerodha Statement Parser Service

Parses Zerodha account statements (Excel/CSV) and categorizes transactions
for margin and funds analysis.

Based on margin-planner categorization logic.
"""

import hashlib
import logging
import re
from datetime import datetime, date
from decimal import Decimal
from typing import Optional, Dict, List, Tuple
from io import BytesIO

import pandas as pd

logger = logging.getLogger(__name__)


class TransactionCategory:
    """Transaction category constants"""
    # Equity categories
    EQUITY_INTRADAY = "equity_intraday"
    EQUITY_DELIVERY_BUY = "equity_delivery_acquisition"
    EQUITY_DELIVERY_SELL = "equity_delivery_sale"

    # F&O categories
    FNO_PREMIUM_PAID = "fno_premium_paid"
    FNO_PREMIUM_RECEIVED = "fno_premium_received"
    FNO_FUTURES_MARGIN = "fno_futures_margin"
    FNO_SETTLEMENT = "fno_settlement"

    # IPO & Corporate actions
    IPO_APPLICATION = "ipo_application"
    DIVIDEND = "dividend_received"

    # Charges & Interest
    INTEREST = "interest_charged"
    CHARGES_TAXES = "charges_taxes"

    # Funds transfer
    FUNDS_IN = "funds_transfer_in"
    FUNDS_OUT = "funds_transfer_out"

    # Other
    OTHER = "other"


class StatementFormat:
    """Zerodha statement format detection"""

    # Known column name variations
    DATE_COLUMNS = ['date', 'trade_date', 'transaction_date', 'Date']
    DESCRIPTION_COLUMNS = ['description', 'narration', 'particulars', 'Description', 'Narration']
    DEBIT_COLUMNS = ['debit', 'debit_amount', 'dr', 'Debit']
    CREDIT_COLUMNS = ['credit', 'credit_amount', 'cr', 'Credit']
    BALANCE_COLUMNS = ['balance', 'closing_balance', 'Balance']
    SYMBOL_COLUMNS = ['symbol', 'tradingsymbol', 'scrip', 'Symbol']

    @staticmethod
    def detect_columns(df: pd.DataFrame) -> Dict[str, str]:
        """
        Detect column names in statement.

        Returns:
            Dict mapping standard names to actual column names
        """
        df_columns_lower = {col.lower(): col for col in df.columns}
        column_map = {}

        # Date column
        for col in StatementFormat.DATE_COLUMNS:
            if col.lower() in df_columns_lower:
                column_map['date'] = df_columns_lower[col.lower()]
                break

        # Description
        for col in StatementFormat.DESCRIPTION_COLUMNS:
            if col.lower() in df_columns_lower:
                column_map['description'] = df_columns_lower[col.lower()]
                break

        # Debit
        for col in StatementFormat.DEBIT_COLUMNS:
            if col.lower() in df_columns_lower:
                column_map['debit'] = df_columns_lower[col.lower()]
                break

        # Credit
        for col in StatementFormat.CREDIT_COLUMNS:
            if col.lower() in df_columns_lower:
                column_map['credit'] = df_columns_lower[col.lower()]
                break

        # Balance
        for col in StatementFormat.BALANCE_COLUMNS:
            if col.lower() in df_columns_lower:
                column_map['balance'] = df_columns_lower[col.lower()]
                break

        # Symbol (optional)
        for col in StatementFormat.SYMBOL_COLUMNS:
            if col.lower() in df_columns_lower:
                column_map['symbol'] = df_columns_lower[col.lower()]
                break

        return column_map


class TransactionCategorizer:
    """
    Categorizes transactions based on description patterns.

    Based on Zerodha statement patterns.
    """

    # Regex patterns for categorization
    # NOTE: Order matters! More specific patterns should come first
    PATTERNS = {
        # Equity patterns (check before F&O to avoid false matches)
        TransactionCategory.EQUITY_INTRADAY: [
            r'intraday',
            r'mis.*?(buy|sell)',
            r'squareoff',
        ],
        TransactionCategory.EQUITY_DELIVERY_BUY: [
            r'bought.*?\s+\w+\s+EQ\b',  # "Bought RELIANCE EQ"
            r'purchase.*?equity',
            r'buy.*?cnc',
        ],
        TransactionCategory.EQUITY_DELIVERY_SELL: [
            r'sold.*?\s+\w+\s+EQ\b',  # "Sold RELIANCE EQ"
            r'sale.*?equity',
            r'sell.*?cnc',
        ],

        # F&O patterns (after equity to avoid "bought X EQ" matching "bought X CE")
        TransactionCategory.FNO_PREMIUM_PAID: [
            r'bought.*?(CE|PE)\b',  # "Bought X CE" (not "Bought X EQ")
            r'purchase.*?option',
            r'buy.*?(call|put)',
        ],
        TransactionCategory.FNO_PREMIUM_RECEIVED: [
            r'sold.*?(CE|PE)\b',  # "Sold X PE" (not "Sold X EQ")
            r'sale.*?option',
            r'sell.*?(call|put)',
        ],
        TransactionCategory.FNO_FUTURES_MARGIN: [
            r'bought.*?FUT\b',
            r'sold.*?FUT\b',
            r'futures.*?(buy|sell)',
        ],
        TransactionCategory.FNO_SETTLEMENT: [
            r'settlement',
            r'expiry.*?settled',
            r'delivery.*?obligation',
        ],

        # IPO & Corporate
        TransactionCategory.IPO_APPLICATION: [
            r'ipo.*?application',
            r'public.*?issue',
        ],
        TransactionCategory.DIVIDEND: [
            r'dividend',
            r'interim.*?dividend',
        ],

        # Charges
        TransactionCategory.INTEREST: [
            r'interest.*?charged',
            r'debit.*?interest',
        ],
        TransactionCategory.CHARGES_TAXES: [
            r'brokerage',
            r'stt',
            r'stamp.*?duty',
            r'transaction.*?charges',
            r'gst',
            r'sebi.*?charges',
            r'exchange.*?charges',
        ],

        # Funds transfer
        TransactionCategory.FUNDS_IN: [
            r'funds.*?added',
            r'payment.*?received',
            r'upi.*?credit',
            r'neft.*?credit',
            r'imps.*?credit',
        ],
        TransactionCategory.FUNDS_OUT: [
            r'funds.*?withdrawn',
            r'payment.*?transferred',
            r'upi.*?debit',
            r'neft.*?debit',
            r'imps.*?debit',
        ],
    }

    @classmethod
    def categorize(cls, description: str, debit: Decimal, credit: Decimal) -> Tuple[str, bool]:
        """
        Categorize transaction based on description.

        Args:
            description: Transaction description
            debit: Debit amount
            credit: Credit amount

        Returns:
            Tuple of (category, is_margin_blocked)
        """
        if not description:
            return TransactionCategory.OTHER, False

        desc_lower = description.lower()

        # Check each category pattern
        for category, patterns in cls.PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, desc_lower, re.IGNORECASE):
                    is_margin_blocked = cls._is_margin_blocking(category, debit, credit)
                    return category, is_margin_blocked

        # Default
        return TransactionCategory.OTHER, False

    @staticmethod
    def _is_margin_blocking(category: str, debit: Decimal, credit: Decimal) -> bool:
        """
        Determine if transaction blocks margin.

        Margin-blocking categories:
        - Equity delivery buy (blocks full amount)
        - FNO premium paid (blocks premium)
        - Equity intraday (blocks turnover)
        - IPO application (blocks amount)
        """
        margin_blocking_categories = {
            TransactionCategory.EQUITY_DELIVERY_BUY,
            TransactionCategory.FNO_PREMIUM_PAID,
            TransactionCategory.EQUITY_INTRADAY,
            TransactionCategory.IPO_APPLICATION,
        }

        return category in margin_blocking_categories and debit > 0


class StatementParser:
    """
    Parses Zerodha account statements.

    Supports Excel (.xlsx, .xls) and CSV formats.
    """

    def __init__(self):
        self.categorizer = TransactionCategorizer()

    def parse_file(
        self,
        file_content: bytes,
        filename: str,
        account_id: str
    ) -> Dict:
        """
        Parse statement file and return structured data.

        Args:
            file_content: Raw file bytes
            filename: Original filename
            account_id: Trading account ID

        Returns:
            Dict with:
            - transactions: List of parsed transactions
            - summary: Summary statistics
            - metadata: File metadata (hash, size, etc.)

        Raises:
            ValueError: If file format is invalid
        """
        # Calculate file hash for deduplication
        file_hash = hashlib.sha256(file_content).hexdigest()

        # Read file into DataFrame
        df = self._read_file(file_content, filename)

        if df.empty:
            raise ValueError("No valid transactions found")

        # Detect column mapping
        column_map = StatementFormat.detect_columns(df)

        if 'date' not in column_map or 'description' not in column_map:
            raise ValueError(
                "Could not detect required columns (date, description). "
                f"Available columns: {list(df.columns)}"
            )

        # Parse transactions
        transactions = self._parse_transactions(df, column_map)

        if not transactions:
            raise ValueError("No valid transactions found in statement")

        # Calculate summary
        summary = self._calculate_summary(transactions)

        # Extract statement period
        dates = [t['transaction_date'] for t in transactions if t.get('transaction_date')]
        statement_start = min(dates) if dates else None
        statement_end = max(dates) if dates else None

        return {
            'transactions': transactions,
            'summary': summary,
            'metadata': {
                'filename': filename,
                'file_hash': file_hash,
                'file_size_bytes': len(file_content),
                'account_id': account_id,
                'statement_start_date': statement_start,
                'statement_end_date': statement_end,
                'total_rows': len(df),
                'parsed_rows': len(transactions),
            }
        }

    def _read_file(self, file_content: bytes, filename: str) -> pd.DataFrame:
        """Read file into pandas DataFrame"""
        try:
            file_obj = BytesIO(file_content)

            if filename.endswith('.csv'):
                df = pd.read_csv(file_obj)
            elif filename.endswith(('.xlsx', '.xls')):
                df = pd.read_excel(file_obj, engine='openpyxl' if filename.endswith('.xlsx') else None)
            else:
                raise ValueError(f"Unsupported file format: {filename}")

            return df

        except Exception as e:
            logger.error(f"Error reading file {filename}: {e}")
            raise ValueError(f"Failed to read file: {str(e)}")

    def _parse_transactions(
        self,
        df: pd.DataFrame,
        column_map: Dict[str, str]
    ) -> List[Dict]:
        """Parse DataFrame rows into transaction dicts"""
        transactions = []

        for idx, row in df.iterrows():
            try:
                # Extract date
                date_str = row[column_map['date']]
                if pd.isna(date_str):
                    continue

                transaction_date = self._parse_date(date_str)
                if not transaction_date:
                    logger.warning(f"Could not parse date: {date_str}")
                    continue

                # Extract description
                description = str(row[column_map['description']]) if not pd.isna(row[column_map['description']]) else ''

                # Extract amounts
                debit = self._parse_decimal(row.get(column_map.get('debit'), 0))
                credit = self._parse_decimal(row.get(column_map.get('credit'), 0))
                balance = self._parse_decimal(row.get(column_map.get('balance'), 0))

                # Extract symbol if available
                tradingsymbol = None
                if 'symbol' in column_map:
                    tradingsymbol = str(row[column_map['symbol']]) if not pd.isna(row[column_map['symbol']]) else None

                # Categorize
                category, is_margin_blocked = self.categorizer.categorize(description, debit, credit)

                # Extract instrument details from description
                instrument_info = self._extract_instrument_info(description, tradingsymbol)

                transaction = {
                    'transaction_date': transaction_date,
                    'description': description,
                    'debit': debit,
                    'credit': credit,
                    'balance': balance,
                    'category': category,
                    'is_margin_blocked': is_margin_blocked,
                    'tradingsymbol': instrument_info.get('tradingsymbol'),
                    'exchange': instrument_info.get('exchange'),
                    'instrument_type': instrument_info.get('instrument_type'),
                    'segment': instrument_info.get('segment'),
                    'raw_data': row.to_dict(),
                }

                transactions.append(transaction)

            except Exception as e:
                logger.warning(f"Error parsing row {idx}: {e}")
                continue

        return transactions

    @staticmethod
    def _parse_date(date_val) -> Optional[datetime]:
        """Parse date from various formats"""
        if isinstance(date_val, (datetime, date)):
            return datetime.combine(date_val, datetime.min.time()) if isinstance(date_val, date) else date_val

        if isinstance(date_val, str):
            # Try common formats
            formats = [
                '%Y-%m-%d',
                '%d-%m-%Y',
                '%d/%m/%Y',
                '%d-%b-%Y',
                '%d %b %Y',
                '%Y/%m/%d',
            ]

            for fmt in formats:
                try:
                    return datetime.strptime(date_val, fmt)
                except ValueError:
                    continue

        return None

    @staticmethod
    def _parse_decimal(value) -> Decimal:
        """Parse decimal from various formats"""
        if pd.isna(value):
            return Decimal('0')

        if isinstance(value, (int, float)):
            return Decimal(str(value))

        if isinstance(value, str):
            # Remove currency symbols, commas
            cleaned = value.replace('₹', '').replace(',', '').strip()
            try:
                return Decimal(cleaned) if cleaned else Decimal('0')
            except:
                return Decimal('0')

        return Decimal('0')

    @staticmethod
    def _extract_instrument_info(description: str, tradingsymbol: Optional[str] = None) -> Dict:
        """
        Extract instrument details from description.

        Returns:
            Dict with tradingsymbol, exchange, instrument_type, segment
        """
        info = {
            'tradingsymbol': tradingsymbol,
            'exchange': None,
            'instrument_type': None,
            'segment': None,
        }

        if not description:
            return info

        desc_upper = description.upper()

        # Extract symbol if not provided
        if not tradingsymbol:
            # Try to find symbol pattern (e.g., "RELIANCE", "NIFTY24NOV24000CE")
            symbol_match = re.search(r'\b([A-Z][A-Z0-9]+)\b', desc_upper)
            if symbol_match:
                info['tradingsymbol'] = symbol_match.group(1)

        # Detect exchange
        if 'NSE' in desc_upper:
            info['exchange'] = 'NSE'
        elif 'BSE' in desc_upper:
            info['exchange'] = 'BSE'
        elif 'NFO' in desc_upper:
            info['exchange'] = 'NFO'
        elif 'MCX' in desc_upper:
            info['exchange'] = 'MCX'

        # Detect instrument type
        # Check for CE/PE at end of symbol (NIFTY24NOV24000CE) or as word with EQ coming later
        # Priority: EQ first to avoid matching "CE" in "RELIANCE"
        if re.search(r'\bEQ(\b|\s|@)', desc_upper) or 'EQUITY' in desc_upper:
            info['instrument_type'] = 'EQ'
            info['segment'] = 'equity'
            info['exchange'] = info['exchange'] or 'NSE'
        elif re.search(r'\d+CE(\b|\s|@)', desc_upper) or re.search(r'\sCE(\b|\s|@)', desc_upper):
            # Match CE after digits (NIFTY24NOV24000CE) or as separate word ( CE @)
            info['instrument_type'] = 'CE'
            info['segment'] = 'fno'
            info['exchange'] = info['exchange'] or 'NFO'
        elif re.search(r'\d+PE(\b|\s|@)', desc_upper) or re.search(r'\sPE(\b|\s|@)', desc_upper):
            # Match PE after digits (BANKNIFTY24DEC48000PE) or as separate word ( PE @)
            info['instrument_type'] = 'PE'
            info['segment'] = 'fno'
            info['exchange'] = info['exchange'] or 'NFO'
        elif re.search(r'FUT(\b|\s|@)', desc_upper):
            info['instrument_type'] = 'FUT'
            info['segment'] = 'fno'
            info['exchange'] = info['exchange'] or 'NFO'

        return info

    @staticmethod
    def _calculate_summary(transactions: List[Dict]) -> Dict:
        """Calculate summary statistics"""
        total_debits = sum(t['debit'] for t in transactions)
        total_credits = sum(t['credit'] for t in transactions)

        # Category-wise breakdown
        category_summary = {}
        for txn in transactions:
            cat = txn['category']
            if cat not in category_summary:
                category_summary[cat] = {
                    'count': 0,
                    'total_debit': Decimal('0'),
                    'total_credit': Decimal('0'),
                }
            category_summary[cat]['count'] += 1
            category_summary[cat]['total_debit'] += txn['debit']
            category_summary[cat]['total_credit'] += txn['credit']

        # Margin blocked
        total_margin_blocked = sum(
            t['debit'] for t in transactions if t.get('is_margin_blocked')
        )

        return {
            'total_transactions': len(transactions),
            'total_debits': float(total_debits),
            'total_credits': float(total_credits),
            'net_change': float(total_credits - total_debits),
            'total_margin_blocked': float(total_margin_blocked),
            'category_breakdown': {
                cat: {
                    'count': data['count'],
                    'total_debit': float(data['total_debit']),
                    'total_credit': float(data['total_credit']),
                    'net': float(data['total_credit'] - data['total_debit']),
                }
                for cat, data in category_summary.items()
            },
        }
