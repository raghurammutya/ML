"""
Unit tests for StatementParser and TransactionCategorizer
"""

import pytest
from datetime import datetime, date
from decimal import Decimal
from io import BytesIO
import pandas as pd

from app.services.statement_parser import (
    StatementParser,
    TransactionCategorizer,
    TransactionCategory,
    StatementFormat
)


# ============================================================================
# TransactionCategorizer Tests
# ============================================================================

class TestTransactionCategorizer:
    """Test transaction categorization logic"""

    def test_fno_premium_paid_categorization(self):
        """Test F&O premium paid categorization"""
        desc = "Bought 50 NIFTY24NOV24000CE @ 150"
        debit = Decimal('75000')
        credit = Decimal('0')

        category, is_margin = TransactionCategorizer.categorize(desc, debit, credit)

        assert category == TransactionCategory.FNO_PREMIUM_PAID
        assert is_margin is True  # Premium paid blocks margin

    def test_fno_premium_received_categorization(self):
        """Test F&O premium received categorization"""
        desc = "Sold 50 NIFTY24NOV24000PE @ 120"
        debit = Decimal('0')
        credit = Decimal('60000')

        category, is_margin = TransactionCategorizer.categorize(desc, debit, credit)

        assert category == TransactionCategory.FNO_PREMIUM_RECEIVED
        assert is_margin is False  # Premium received doesn't block margin

    def test_equity_delivery_buy_categorization(self):
        """Test equity delivery buy categorization"""
        desc = "Bought 100 RELIANCE EQ @ 2500"
        debit = Decimal('250000')
        credit = Decimal('0')

        category, is_margin = TransactionCategorizer.categorize(desc, debit, credit)

        assert category == TransactionCategory.EQUITY_DELIVERY_BUY
        assert is_margin is True  # Delivery buy blocks margin

    def test_equity_delivery_sell_categorization(self):
        """Test equity delivery sell categorization"""
        desc = "Sold 100 RELIANCE EQ @ 2600"
        debit = Decimal('0')
        credit = Decimal('260000')

        category, is_margin = TransactionCategorizer.categorize(desc, debit, credit)

        assert category == TransactionCategory.EQUITY_DELIVERY_SELL
        assert is_margin is False  # Delivery sell doesn't block margin

    def test_equity_intraday_categorization(self):
        """Test equity intraday categorization"""
        desc = "Intraday buy TATAMOTORS MIS 50 @ 450"
        debit = Decimal('22500')
        credit = Decimal('0')

        category, is_margin = TransactionCategorizer.categorize(desc, debit, credit)

        assert category == TransactionCategory.EQUITY_INTRADAY
        assert is_margin is True  # Intraday blocks margin

    def test_dividend_categorization(self):
        """Test dividend categorization"""
        desc = "Dividend received from INFY"
        debit = Decimal('0')
        credit = Decimal('5000')

        category, is_margin = TransactionCategorizer.categorize(desc, debit, credit)

        assert category == TransactionCategory.DIVIDEND
        assert is_margin is False

    def test_charges_categorization(self):
        """Test charges and taxes categorization"""
        test_cases = [
            "Brokerage charges",
            "STT charges",
            "Stamp duty",
            "Transaction charges",
            "GST on brokerage",
        ]

        for desc in test_cases:
            category, is_margin = TransactionCategorizer.categorize(
                desc, Decimal('100'), Decimal('0')
            )
            assert category == TransactionCategory.CHARGES_TAXES
            assert is_margin is False

    def test_funds_transfer_in_categorization(self):
        """Test funds transfer in categorization"""
        desc = "UPI credit from SBI"
        debit = Decimal('0')
        credit = Decimal('100000')

        category, is_margin = TransactionCategorizer.categorize(desc, debit, credit)

        assert category == TransactionCategory.FUNDS_IN
        assert is_margin is False

    def test_funds_transfer_out_categorization(self):
        """Test funds transfer out categorization"""
        desc = "Funds withdrawn via NEFT"
        debit = Decimal('50000')
        credit = Decimal('0')

        category, is_margin = TransactionCategorizer.categorize(desc, debit, credit)

        assert category == TransactionCategory.FUNDS_OUT
        assert is_margin is False

    def test_unknown_description_categorization(self):
        """Test unknown description gets categorized as OTHER"""
        desc = "Some random transaction"
        debit = Decimal('1000')
        credit = Decimal('0')

        category, is_margin = TransactionCategorizer.categorize(desc, debit, credit)

        assert category == TransactionCategory.OTHER
        assert is_margin is False

    def test_empty_description_categorization(self):
        """Test empty description handling"""
        category, is_margin = TransactionCategorizer.categorize("", Decimal('0'), Decimal('0'))

        assert category == TransactionCategory.OTHER
        assert is_margin is False


# ============================================================================
# StatementFormat Tests
# ============================================================================

class TestStatementFormat:
    """Test statement format detection"""

    def test_detect_standard_columns(self):
        """Test detection of standard column names"""
        df = pd.DataFrame({
            'Date': ['2024-01-01'],
            'Description': ['Test'],
            'Debit': [1000],
            'Credit': [0],
            'Balance': [5000]
        })

        column_map = StatementFormat.detect_columns(df)

        assert column_map['date'] == 'Date'
        assert column_map['description'] == 'Description'
        assert column_map['debit'] == 'Debit'
        assert column_map['credit'] == 'Credit'
        assert column_map['balance'] == 'Balance'

    def test_detect_lowercase_columns(self):
        """Test detection of lowercase column names"""
        df = pd.DataFrame({
            'date': ['2024-01-01'],
            'narration': ['Test'],
            'dr': [1000],
            'cr': [0],
            'closing_balance': [5000]
        })

        column_map = StatementFormat.detect_columns(df)

        assert column_map['date'] == 'date'
        assert column_map['description'] == 'narration'
        assert column_map['debit'] == 'dr'
        assert column_map['credit'] == 'cr'
        assert column_map['balance'] == 'closing_balance'

    def test_detect_alternate_column_names(self):
        """Test detection of alternate column names"""
        df = pd.DataFrame({
            'trade_date': ['2024-01-01'],
            'particulars': ['Test'],
            'debit_amount': [1000],
            'credit_amount': [0]
        })

        column_map = StatementFormat.detect_columns(df)

        assert 'date' in column_map
        assert 'description' in column_map
        assert 'debit' in column_map
        assert 'credit' in column_map


# ============================================================================
# StatementParser Tests
# ============================================================================

class TestStatementParser:
    """Test statement parsing functionality"""

    @pytest.fixture
    def parser(self):
        """Create parser instance"""
        return StatementParser()

    @pytest.fixture
    def sample_csv_content(self):
        """Create sample CSV content"""
        csv_data = """Date,Description,Debit,Credit,Balance
2024-01-01,Bought 50 NIFTY24JAN24000CE @ 150,75000,0,425000
2024-01-01,Sold 50 NIFTY24JAN24000PE @ 120,0,60000,485000
2024-01-02,Bought 100 RELIANCE EQ @ 2500,250000,0,235000
2024-01-03,Dividend received from INFY,0,5000,240000
2024-01-04,Brokerage charges,500,0,239500
"""
        return csv_data.encode('utf-8')

    @pytest.fixture
    def sample_excel_content(self):
        """Create sample Excel content"""
        df = pd.DataFrame({
            'Date': ['2024-01-01', '2024-01-02', '2024-01-03'],
            'Description': [
                'Bought 50 NIFTY24JAN24000CE @ 150',
                'Bought 100 RELIANCE EQ @ 2500',
                'Dividend received from INFY'
            ],
            'Debit': [75000, 250000, 0],
            'Credit': [0, 0, 5000],
            'Balance': [425000, 175000, 180000]
        })

        buffer = BytesIO()
        df.to_excel(buffer, index=False, engine='openpyxl')
        buffer.seek(0)
        return buffer.read()

    def test_parse_csv_file(self, parser, sample_csv_content):
        """Test parsing CSV file"""
        result = parser.parse_file(sample_csv_content, 'statement.csv', 'account_1')

        assert 'transactions' in result
        assert 'summary' in result
        assert 'metadata' in result

        # Check metadata
        assert result['metadata']['filename'] == 'statement.csv'
        assert result['metadata']['account_id'] == 'account_1'
        assert result['metadata']['file_hash'] is not None
        assert result['metadata']['parsed_rows'] == 5

        # Check transactions
        transactions = result['transactions']
        assert len(transactions) == 5

        # Verify first transaction (FNO premium paid)
        txn1 = transactions[0]
        assert txn1['category'] == TransactionCategory.FNO_PREMIUM_PAID
        assert txn1['is_margin_blocked'] is True
        assert txn1['debit'] == Decimal('75000')

        # Verify dividend transaction
        dividend_txn = [t for t in transactions if t['category'] == TransactionCategory.DIVIDEND][0]
        assert dividend_txn['credit'] == Decimal('5000')
        assert dividend_txn['is_margin_blocked'] is False

    def test_parse_excel_file(self, parser, sample_excel_content):
        """Test parsing Excel file"""
        result = parser.parse_file(sample_excel_content, 'statement.xlsx', 'account_1')

        assert 'transactions' in result
        assert len(result['transactions']) == 3

        # Verify categorization
        categories = [t['category'] for t in result['transactions']]
        assert TransactionCategory.FNO_PREMIUM_PAID in categories
        assert TransactionCategory.EQUITY_DELIVERY_BUY in categories
        assert TransactionCategory.DIVIDEND in categories

    def test_parse_empty_file_raises_error(self, parser):
        """Test parsing empty file raises error"""
        empty_csv = b"Date,Description,Debit,Credit,Balance\n"

        with pytest.raises(ValueError, match="No valid transactions found"):
            parser.parse_file(empty_csv, 'empty.csv', 'account_1')

    def test_parse_invalid_format_raises_error(self, parser):
        """Test parsing invalid format raises error"""
        with pytest.raises(ValueError, match="Unsupported file format"):
            parser.parse_file(b"some text", 'file.txt', 'account_1')

    def test_parse_missing_columns_raises_error(self, parser):
        """Test parsing file with missing required columns"""
        csv_data = b"Col1,Col2\n1,2\n"

        with pytest.raises(ValueError, match="Could not detect required columns"):
            parser.parse_file(csv_data, 'invalid.csv', 'account_1')

    def test_date_parsing_multiple_formats(self, parser):
        """Test parsing multiple date formats"""
        date_formats = [
            '2024-01-01',
            '01-01-2024',
            '01/01/2024',
            '01-Jan-2024',
            '01 Jan 2024',
        ]

        for date_str in date_formats:
            parsed = parser._parse_date(date_str)
            assert parsed is not None
            assert parsed.year == 2024
            assert parsed.month == 1
            assert parsed.day == 1

    def test_decimal_parsing_various_formats(self, parser):
        """Test parsing decimal values in various formats"""
        test_cases = [
            ('1000', Decimal('1000')),
            ('1,000', Decimal('1000')),
            ('₹1,000', Decimal('1000')),
            (1000.50, Decimal('1000.50')),
            ('', Decimal('0')),
            (None, Decimal('0')),
        ]

        for value, expected in test_cases:
            result = parser._parse_decimal(value)
            assert result == expected

    def test_instrument_info_extraction(self, parser):
        """Test extracting instrument info from description"""
        test_cases = [
            {
                'description': 'Bought 50 NIFTY24NOV24000CE @ 150 NFO',
                'expected': {
                    'instrument_type': 'CE',
                    'exchange': 'NFO',
                    'segment': 'fno',
                }
            },
            {
                'description': 'Sold 100 BANKNIFTY24DEC48000PE @ 450',
                'expected': {
                    'instrument_type': 'PE',
                    'segment': 'fno',
                }
            },
            {
                'description': 'Bought 100 RELIANCE EQ @ 2500 NSE',
                'expected': {
                    'instrument_type': 'EQ',
                    'exchange': 'NSE',
                    'segment': 'equity',
                }
            },
            {
                'description': 'Dividend received',
                'expected': {
                    'instrument_type': None,
                    'exchange': None,
                    'segment': None,
                }
            },
        ]

        for case in test_cases:
            info = parser._extract_instrument_info(case['description'])
            for key, expected_value in case['expected'].items():
                assert info[key] == expected_value

    def test_summary_calculation(self, parser, sample_csv_content):
        """Test summary statistics calculation"""
        result = parser.parse_file(sample_csv_content, 'statement.csv', 'account_1')
        summary = result['summary']

        # Check totals
        assert summary['total_transactions'] == 5
        assert summary['total_debits'] > 0
        assert summary['total_credits'] > 0
        assert summary['net_change'] == summary['total_credits'] - summary['total_debits']

        # Check category breakdown exists
        assert 'category_breakdown' in summary
        assert len(summary['category_breakdown']) > 0

        # Check margin blocked
        assert summary['total_margin_blocked'] > 0

    def test_file_hash_consistency(self, parser, sample_csv_content):
        """Test file hash is consistent for same content"""
        result1 = parser.parse_file(sample_csv_content, 'file1.csv', 'account_1')
        result2 = parser.parse_file(sample_csv_content, 'file2.csv', 'account_1')

        # Same content should produce same hash (for deduplication)
        assert result1['metadata']['file_hash'] == result2['metadata']['file_hash']

    def test_statement_period_detection(self, parser, sample_csv_content):
        """Test statement period detection from transactions"""
        result = parser.parse_file(sample_csv_content, 'statement.csv', 'account_1')
        metadata = result['metadata']

        # Should detect start and end dates
        assert metadata['statement_start_date'] is not None
        assert metadata['statement_end_date'] is not None
        assert metadata['statement_start_date'] <= metadata['statement_end_date']


# ============================================================================
# Integration Tests
# ============================================================================

class TestParserIntegration:
    """Integration tests for complete parsing workflow"""

    def test_complete_parsing_workflow(self):
        """Test complete workflow from file to categorized transactions"""
        # Create realistic statement
        df = pd.DataFrame({
            'Date': [
                '2024-11-01',
                '2024-11-01',
                '2024-11-02',
                '2024-11-02',
                '2024-11-03',
                '2024-11-04',
                '2024-11-05',
            ],
            'Description': [
                'Bought 50 NIFTY24NOV24000CE @ 150',
                'Sold 50 NIFTY24NOV24500PE @ 100',
                'Bought 100 RELIANCE EQ @ 2500',
                'Intraday buy TATAMOTORS MIS 50 @ 450',
                'Dividend received from INFY',
                'Brokerage charges',
                'UPI credit from SBI',
            ],
            'Debit': [75000, 0, 250000, 22500, 0, 500, 0],
            'Credit': [0, 50000, 0, 0, 5000, 0, 100000],
            'Balance': [425000, 475000, 225000, 202500, 207500, 207000, 307000],
        })

        buffer = BytesIO()
        df.to_excel(buffer, index=False, engine='openpyxl')
        content = buffer.getvalue()

        parser = StatementParser()
        result = parser.parse_file(content, 'monthly_statement.xlsx', 'test_account')

        # Verify all transactions parsed
        assert len(result['transactions']) == 7

        # Verify categories
        categories = [t['category'] for t in result['transactions']]
        assert TransactionCategory.FNO_PREMIUM_PAID in categories
        assert TransactionCategory.FNO_PREMIUM_RECEIVED in categories
        assert TransactionCategory.EQUITY_DELIVERY_BUY in categories
        assert TransactionCategory.EQUITY_INTRADAY in categories
        assert TransactionCategory.DIVIDEND in categories
        assert TransactionCategory.CHARGES_TAXES in categories
        assert TransactionCategory.FUNDS_IN in categories

        # Verify margin blocking
        margin_blocked_txns = [t for t in result['transactions'] if t['is_margin_blocked']]
        assert len(margin_blocked_txns) == 3  # FNO premium paid, delivery buy, intraday

        # Verify summary
        summary = result['summary']
        assert summary['total_transactions'] == 7
        assert summary['total_margin_blocked'] == 75000 + 250000 + 22500  # Premium + Delivery + Intraday

        # Verify category breakdown
        breakdown = summary['category_breakdown']
        assert TransactionCategory.FNO_PREMIUM_PAID in breakdown
        assert breakdown[TransactionCategory.FNO_PREMIUM_PAID]['count'] == 1
        assert breakdown[TransactionCategory.FNO_PREMIUM_PAID]['total_debit'] == 75000
