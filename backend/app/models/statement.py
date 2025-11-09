"""
Pydantic models for statement parsing and funds categorization.
"""

from datetime import datetime, date
from decimal import Decimal
from typing import Optional, Dict, List
from pydantic import BaseModel, Field, validator


# ============================================================================
# Transaction Models
# ============================================================================

class StatementTransaction(BaseModel):
    """Individual transaction from statement"""
    transaction_date: datetime
    description: str
    debit: Decimal = Decimal('0')
    credit: Decimal = Decimal('0')
    balance: Optional[Decimal] = None
    category: str
    is_margin_blocked: bool = False
    tradingsymbol: Optional[str] = None
    exchange: Optional[str] = None
    instrument_type: Optional[str] = None
    segment: Optional[str] = None
    raw_data: Optional[Dict] = None

    class Config:
        json_encoders = {
            Decimal: lambda v: float(v),
            datetime: lambda v: v.isoformat(),
        }


class StatementTransactionDB(StatementTransaction):
    """Transaction with database fields"""
    id: int
    upload_id: int
    account_id: str
    quantity: Optional[int] = None
    price: Optional[Decimal] = None
    transaction_type: Optional[str] = None
    subcategory: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ============================================================================
# Upload Models
# ============================================================================

class StatementUploadCreate(BaseModel):
    """Request to create statement upload"""
    account_id: str
    uploaded_by: Optional[str] = None


class StatementUploadStatus(BaseModel):
    """Statement upload status"""
    id: int
    account_id: str
    filename: str
    file_size_bytes: int
    file_hash: str
    status: str  # pending, processing, completed, failed
    parsed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    statement_start_date: Optional[date] = None
    statement_end_date: Optional[date] = None
    total_transactions: int = 0
    total_debits: Decimal = Decimal('0')
    total_credits: Decimal = Decimal('0')
    uploaded_at: datetime
    updated_at: datetime
    metadata: Optional[Dict] = None

    class Config:
        from_attributes = True
        json_encoders = {
            Decimal: lambda v: float(v),
            datetime: lambda v: v.isoformat(),
            date: lambda v: v.isoformat(),
        }


class StatementUploadResponse(BaseModel):
    """Response after uploading statement"""
    upload_id: int
    status: str
    message: str
    summary: Optional[Dict] = None
    transactions_parsed: int = 0
    errors: List[str] = []


# ============================================================================
# Category Summary Models
# ============================================================================

class CategoryBreakdown(BaseModel):
    """Breakdown for a single category"""
    category: str
    count: int
    total_debit: float
    total_credit: float
    net: float


class FundsCategorySummary(BaseModel):
    """Category-wise funds summary"""
    account_id: str
    start_date: date
    end_date: date

    # Equity categories
    equity_intraday: Decimal = Decimal('0')
    equity_delivery_acquisition: Decimal = Decimal('0')
    equity_delivery_sale: Decimal = Decimal('0')

    # F&O categories
    fno_premium_paid: Decimal = Decimal('0')
    fno_premium_received: Decimal = Decimal('0')
    fno_futures_margin: Decimal = Decimal('0')
    fno_settlement: Decimal = Decimal('0')

    # Other categories
    ipo_application: Decimal = Decimal('0')
    dividend_received: Decimal = Decimal('0')
    interest_charged: Decimal = Decimal('0')
    charges_taxes: Decimal = Decimal('0')
    funds_transfer_in: Decimal = Decimal('0')
    funds_transfer_out: Decimal = Decimal('0')
    other: Decimal = Decimal('0')

    # Margin metrics
    total_margin_blocked: Decimal = Decimal('0')
    peak_margin_blocked: Decimal = Decimal('0')
    avg_daily_margin: Decimal = Decimal('0')

    calculated_at: datetime

    class Config:
        from_attributes = True
        json_encoders = {
            Decimal: lambda v: float(v),
            datetime: lambda v: v.isoformat(),
            date: lambda v: v.isoformat(),
        }


class FundsCategorySummaryResponse(BaseModel):
    """Response for category summary query"""
    account_id: str
    date_range: Dict[str, date]
    total_debits: float
    total_credits: float
    net_change: float
    total_margin_blocked: float

    # Category breakdown
    categories: Dict[str, CategoryBreakdown]

    # Top margin consumers
    top_margin_consumers: List[Dict]

    class Config:
        json_encoders = {
            date: lambda v: v.isoformat(),
        }


# ============================================================================
# Query Models
# ============================================================================

class StatementQueryParams(BaseModel):
    """Query parameters for transactions"""
    account_id: str
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    category: Optional[str] = None
    segment: Optional[str] = None
    tradingsymbol: Optional[str] = None
    min_amount: Optional[Decimal] = None
    max_amount: Optional[Decimal] = None
    margin_blocked_only: bool = False
    limit: int = Field(default=100, ge=1, le=10000)
    offset: int = Field(default=0, ge=0)

    @validator('end_date')
    def end_date_after_start(cls, v, values):
        """Validate end_date is after start_date"""
        if v and values.get('start_date') and v < values['start_date']:
            raise ValueError('end_date must be after start_date')
        return v


class TransactionListResponse(BaseModel):
    """Response for transaction list query"""
    transactions: List[StatementTransactionDB]
    total: int
    limit: int
    offset: int
    filters: Dict


# ============================================================================
# Analytics Models
# ============================================================================

class MarginUtilizationMetrics(BaseModel):
    """Margin utilization metrics"""
    account_id: str
    date_range: Dict[str, date]

    # Current state
    total_margin_blocked: float
    available_margin: float
    utilization_percentage: float

    # Historical
    peak_margin_blocked: float
    peak_date: Optional[date] = None
    avg_daily_margin: float

    # By category
    margin_by_category: Dict[str, float]

    # By segment
    margin_by_segment: Dict[str, float]

    class Config:
        json_encoders = {
            date: lambda v: v.isoformat(),
        }


class DailyMarginTimeseries(BaseModel):
    """Daily margin blocked timeseries"""
    date: date
    total_margin_blocked: float
    equity_intraday: float
    equity_delivery: float
    fno_premium: float
    fno_futures: float
    ipo_application: float

    class Config:
        json_encoders = {
            date: lambda v: v.isoformat(),
        }


class MarginTimeseriesResponse(BaseModel):
    """Response for margin timeseries query"""
    account_id: str
    date_range: Dict[str, date]
    timeseries: List[DailyMarginTimeseries]

    class Config:
        json_encoders = {
            date: lambda v: v.isoformat(),
        }


# ============================================================================
# Validation Models
# ============================================================================

class FileValidationResult(BaseModel):
    """Result of file validation"""
    is_valid: bool
    errors: List[str] = []
    warnings: List[str] = []
    metadata: Optional[Dict] = None


class StatementPreview(BaseModel):
    """Preview of statement before parsing"""
    filename: str
    file_size_bytes: int
    estimated_transactions: int
    date_range: Optional[Dict[str, date]] = None
    columns_detected: Dict[str, str]
    sample_rows: List[Dict]

    class Config:
        json_encoders = {
            date: lambda v: v.isoformat(),
        }
