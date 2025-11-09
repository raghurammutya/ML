"""
Funds & Statement Management API Endpoints

Endpoints for:
- Uploading Zerodha statements
- Querying transactions
- Category-wise funds breakdown
- Margin utilization analytics
"""

import logging
from datetime import datetime, timezone, date, timedelta
from decimal import Decimal
from typing import Optional, List
from fastapi import APIRouter, File, UploadFile, HTTPException, Depends, Query
from fastapi.responses import JSONResponse

from ..database import DataManager
from ..models.statement import (
    StatementUploadResponse,
    StatementUploadStatus,
    StatementQueryParams,
    TransactionListResponse,
    FundsCategorySummaryResponse,
    CategoryBreakdown,
    MarginUtilizationMetrics,
    MarginTimeseriesResponse,
    DailyMarginTimeseries,
    StatementTransactionDB,
)
from ..services.statement_parser import StatementParser

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/funds", tags=["funds"])

# Module-level data manager instance
_data_manager: Optional[DataManager] = None


def set_data_manager(dm: DataManager):
    """Set the data manager instance."""
    global _data_manager
    _data_manager = dm


async def get_data_manager() -> DataManager:
    """Dependency to get data manager."""
    if _data_manager is None:
        raise HTTPException(status_code=500, detail="Data manager not initialized")
    return _data_manager


# ============================================================================
# File Upload Endpoints
# ============================================================================

@router.post("/upload-statement", response_model=StatementUploadResponse)
async def upload_statement(
    account_id: str = Query(..., description="Trading account ID"),
    file: UploadFile = File(..., description="Statement file (Excel or CSV)"),
    dm: DataManager = Depends(get_data_manager)
) -> StatementUploadResponse:
    """
    Upload and parse Zerodha account statement.

    Supports Excel (.xlsx, .xls) and CSV formats.

    Returns:
        Upload status with parsed transaction summary
    """
    logger.info(f"Uploading statement for account {account_id}: {file.filename}")

    # Validate file format
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    allowed_extensions = ['.xlsx', '.xls', '.csv']
    if not any(file.filename.lower().endswith(ext) for ext in allowed_extensions):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format. Allowed: {', '.join(allowed_extensions)}"
        )

    # Validate file size (max 10MB)
    max_size = 10 * 1024 * 1024  # 10MB
    file_content = await file.read()

    if len(file_content) > max_size:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Max size: {max_size / (1024 * 1024)}MB"
        )

    try:
        # Parse statement
        parser = StatementParser()
        parsed_data = parser.parse_file(file_content, file.filename, account_id)

        metadata = parsed_data['metadata']
        transactions = parsed_data['transactions']
        summary = parsed_data['summary']

        # Check for duplicate upload (same file hash)
        async with dm.pool.acquire() as conn:
            existing = await conn.fetchrow(
                """
                SELECT id, status, uploaded_at
                FROM statement_uploads
                WHERE account_id = $1 AND file_hash = $2
                """,
                account_id,
                metadata['file_hash']
            )

            if existing:
                logger.warning(f"Duplicate upload detected: {metadata['file_hash']}")
                return StatementUploadResponse(
                    upload_id=existing['id'],
                    status='duplicate',
                    message=f"This file was already uploaded on {existing['uploaded_at']}",
                    transactions_parsed=0,
                    errors=[f"Duplicate file uploaded at {existing['uploaded_at']}"]
                )

            # Insert upload record
            upload_id = await conn.fetchval(
                """
                INSERT INTO statement_uploads (
                    account_id, filename, file_size_bytes, file_hash,
                    status, parsed_at,
                    statement_start_date, statement_end_date,
                    total_transactions, total_debits, total_credits,
                    uploaded_at, updated_at, metadata
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                RETURNING id
                """,
                account_id,
                metadata['filename'],
                metadata['file_size_bytes'],
                metadata['file_hash'],
                'completed',
                datetime.now(timezone.utc),
                metadata.get('statement_start_date'),
                metadata.get('statement_end_date'),
                len(transactions),
                Decimal(str(summary['total_debits'])),
                Decimal(str(summary['total_credits'])),
                datetime.now(timezone.utc),
                datetime.now(timezone.utc),
                metadata
            )

            # Insert transactions in batch
            if transactions:
                await _insert_transactions_batch(conn, upload_id, account_id, transactions)

            logger.info(
                f"Successfully parsed {len(transactions)} transactions for account {account_id}"
            )

            return StatementUploadResponse(
                upload_id=upload_id,
                status='completed',
                message=f"Successfully parsed {len(transactions)} transactions",
                summary=summary,
                transactions_parsed=len(transactions),
                errors=[]
            )

    except ValueError as e:
        logger.error(f"Validation error parsing statement: {e}")
        raise HTTPException(status_code=400, detail=str(e))

    except Exception as e:
        logger.exception(f"Error parsing statement: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to parse statement: {str(e)}")


async def _insert_transactions_batch(conn, upload_id: int, account_id: str, transactions: List[dict]):
    """Insert transactions in batch for performance"""
    insert_query = """
        INSERT INTO statement_transactions (
            upload_id, account_id, transaction_date, description,
            tradingsymbol, exchange, instrument_type, segment,
            debit, credit, balance,
            category, is_margin_blocked,
            raw_data, created_at
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
    """

    # Batch insert (PostgreSQL supports multi-row insert efficiently)
    for txn in transactions:
        await conn.execute(
            insert_query,
            upload_id,
            account_id,
            txn['transaction_date'],
            txn['description'],
            txn.get('tradingsymbol'),
            txn.get('exchange'),
            txn.get('instrument_type'),
            txn.get('segment'),
            txn['debit'],
            txn['credit'],
            txn.get('balance'),
            txn['category'],
            txn.get('is_margin_blocked', False),
            txn.get('raw_data'),
            datetime.now(timezone.utc)
        )


# ============================================================================
# Upload Management Endpoints
# ============================================================================

@router.get("/uploads", response_model=List[StatementUploadStatus])
async def list_uploads(
    account_id: str = Query(..., description="Trading account ID"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    dm: DataManager = Depends(get_data_manager)
) -> List[StatementUploadStatus]:
    """List all statement uploads for an account"""
    async with dm.pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT *
            FROM statement_uploads
            WHERE account_id = $1
            ORDER BY uploaded_at DESC
            LIMIT $2 OFFSET $3
            """,
            account_id,
            limit,
            offset
        )

        return [StatementUploadStatus(**dict(row)) for row in rows]


@router.get("/uploads/{upload_id}", response_model=StatementUploadStatus)
async def get_upload_status(
    upload_id: int,
    dm: DataManager = Depends(get_data_manager)
) -> StatementUploadStatus:
    """Get status of a specific upload"""
    async with dm.pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM statement_uploads WHERE id = $1",
            upload_id
        )

        if not row:
            raise HTTPException(status_code=404, detail="Upload not found")

        return StatementUploadStatus(**dict(row))


# ============================================================================
# Transaction Query Endpoints
# ============================================================================

@router.get("/transactions", response_model=TransactionListResponse)
async def get_transactions(
    account_id: str = Query(..., description="Trading account ID"),
    start_date: Optional[date] = Query(None, description="Start date (inclusive)"),
    end_date: Optional[date] = Query(None, description="End date (inclusive)"),
    category: Optional[str] = Query(None, description="Filter by category"),
    segment: Optional[str] = Query(None, description="Filter by segment (equity/fno)"),
    tradingsymbol: Optional[str] = Query(None, description="Filter by symbol"),
    margin_blocked_only: bool = Query(False, description="Only margin-blocking transactions"),
    limit: int = Query(100, ge=1, le=10000),
    offset: int = Query(0, ge=0),
    dm: DataManager = Depends(get_data_manager)
) -> TransactionListResponse:
    """
    Query statement transactions with filters.

    Returns paginated list of transactions.
    """
    # Build query
    query_parts = ["SELECT * FROM statement_transactions WHERE account_id = $1"]
    params = [account_id]
    param_idx = 2

    # Date filters
    if start_date:
        query_parts.append(f"AND transaction_date >= ${param_idx}::timestamptz")
        params.append(start_date)
        param_idx += 1

    if end_date:
        query_parts.append(f"AND transaction_date < (${param_idx}::date + INTERVAL '1 day')::timestamptz")
        params.append(end_date)
        param_idx += 1

    # Category filter
    if category:
        query_parts.append(f"AND category = ${param_idx}")
        params.append(category)
        param_idx += 1

    # Segment filter
    if segment:
        query_parts.append(f"AND segment = ${param_idx}")
        params.append(segment)
        param_idx += 1

    # Symbol filter
    if tradingsymbol:
        query_parts.append(f"AND tradingsymbol = ${param_idx}")
        params.append(tradingsymbol)
        param_idx += 1

    # Margin blocked filter
    if margin_blocked_only:
        query_parts.append("AND is_margin_blocked = TRUE")

    # Count total
    count_query = f"SELECT COUNT(*) FROM statement_transactions WHERE account_id = $1"
    if len(query_parts) > 1:
        count_query = " ".join(query_parts).replace("SELECT *", "SELECT COUNT(*)")

    # Add ordering and pagination
    query_parts.append("ORDER BY transaction_date DESC")
    query_parts.append(f"LIMIT ${param_idx} OFFSET ${param_idx + 1}")
    params.extend([limit, offset])

    query = " ".join(query_parts)

    async with dm.pool.acquire() as conn:
        # Get total count
        total = await conn.fetchval(count_query, *params[:-2])  # Exclude limit/offset

        # Get transactions
        rows = await conn.fetch(query, *params)

        transactions = [StatementTransactionDB(**dict(row)) for row in rows]

        return TransactionListResponse(
            transactions=transactions,
            total=total,
            limit=limit,
            offset=offset,
            filters={
                'account_id': account_id,
                'start_date': start_date,
                'end_date': end_date,
                'category': category,
                'segment': segment,
                'tradingsymbol': tradingsymbol,
                'margin_blocked_only': margin_blocked_only,
            }
        )


# ============================================================================
# Category Summary Endpoints
# ============================================================================

@router.get("/category-summary", response_model=FundsCategorySummaryResponse)
async def get_category_summary(
    account_id: str = Query(..., description="Trading account ID"),
    start_date: Optional[date] = Query(None, description="Start date (default: 30 days ago)"),
    end_date: Optional[date] = Query(None, description="End date (default: today)"),
    dm: DataManager = Depends(get_data_manager)
) -> FundsCategorySummaryResponse:
    """
    Get category-wise funds breakdown for a date range.

    Returns:
        Summary with category breakdown and margin metrics
    """
    # Default date range: last 30 days
    if not end_date:
        end_date = date.today()
    if not start_date:
        start_date = end_date - timedelta(days=30)

    async with dm.pool.acquire() as conn:
        # Use the helper function
        rows = await conn.fetch(
            "SELECT * FROM calculate_funds_category_summary($1, $2, $3)",
            account_id,
            start_date,
            end_date
        )

        # Calculate totals
        total_debits = sum(row['total_debit'] for row in rows)
        total_credits = sum(row['total_credit'] for row in rows)
        net_change = total_credits - total_debits

        # Build category breakdown
        categories = {
            row['category']: CategoryBreakdown(
                category=row['category'],
                count=row['transaction_count'],
                total_debit=float(row['total_debit']),
                total_credit=float(row['total_credit']),
                net=float(row['net_amount'])
            )
            for row in rows
        }

        # Calculate total margin blocked
        margin_result = await conn.fetchrow(
            """
            SELECT COALESCE(SUM(debit), 0) as total_margin_blocked
            FROM statement_transactions
            WHERE account_id = $1
              AND transaction_date >= $2::timestamptz
              AND transaction_date < ($3::date + INTERVAL '1 day')::timestamptz
              AND is_margin_blocked = TRUE
            """,
            account_id,
            start_date,
            end_date
        )

        total_margin_blocked = float(margin_result['total_margin_blocked'])

        # Get top margin consumers
        top_consumers = await conn.fetch(
            """
            SELECT
                tradingsymbol,
                segment,
                category,
                SUM(debit) as total_margin
            FROM statement_transactions
            WHERE account_id = $1
              AND transaction_date >= $2::timestamptz
              AND transaction_date < ($3::date + INTERVAL '1 day')::timestamptz
              AND is_margin_blocked = TRUE
            GROUP BY tradingsymbol, segment, category
            ORDER BY total_margin DESC
            LIMIT 10
            """,
            account_id,
            start_date,
            end_date
        )

        top_margin_consumers = [
            {
                'tradingsymbol': row['tradingsymbol'],
                'segment': row['segment'],
                'category': row['category'],
                'total_margin': float(row['total_margin']),
            }
            for row in top_consumers
        ]

        return FundsCategorySummaryResponse(
            account_id=account_id,
            date_range={'start': start_date, 'end': end_date},
            total_debits=float(total_debits),
            total_credits=float(total_credits),
            net_change=float(net_change),
            total_margin_blocked=total_margin_blocked,
            categories=categories,
            top_margin_consumers=top_margin_consumers
        )


# ============================================================================
# Margin Analytics Endpoints
# ============================================================================

@router.get("/margin-utilization", response_model=MarginUtilizationMetrics)
async def get_margin_utilization(
    account_id: str = Query(..., description="Trading account ID"),
    start_date: Optional[date] = Query(None, description="Start date"),
    end_date: Optional[date] = Query(None, description="End date"),
    dm: DataManager = Depends(get_data_manager)
) -> MarginUtilizationMetrics:
    """
    Get margin utilization metrics.

    Returns:
        Current margin blocked, peak margin, category breakdown
    """
    # Default date range: last 30 days
    if not end_date:
        end_date = date.today()
    if not start_date:
        start_date = end_date - timedelta(days=30)

    async with dm.pool.acquire() as conn:
        # Total margin blocked
        total_margin = await conn.fetchval(
            """
            SELECT COALESCE(SUM(debit), 0)
            FROM statement_transactions
            WHERE account_id = $1
              AND transaction_date >= $2::timestamptz
              AND transaction_date < ($3::date + INTERVAL '1 day')::timestamptz
              AND is_margin_blocked = TRUE
            """,
            account_id,
            start_date,
            end_date
        )

        # Peak margin (daily max)
        peak_result = await conn.fetchrow(
            """
            SELECT
                DATE(transaction_date) as peak_date,
                SUM(debit) as peak_margin
            FROM statement_transactions
            WHERE account_id = $1
              AND transaction_date >= $2::timestamptz
              AND transaction_date < ($3::date + INTERVAL '1 day')::timestamptz
              AND is_margin_blocked = TRUE
            GROUP BY DATE(transaction_date)
            ORDER BY peak_margin DESC
            LIMIT 1
            """,
            account_id,
            start_date,
            end_date
        )

        peak_margin = float(peak_result['peak_margin']) if peak_result else 0
        peak_date = peak_result['peak_date'] if peak_result else None

        # Average daily margin
        days = (end_date - start_date).days + 1
        avg_daily_margin = float(total_margin) / days if days > 0 else 0

        # Margin by category
        category_margins = await conn.fetch(
            """
            SELECT category, SUM(debit) as total_margin
            FROM statement_transactions
            WHERE account_id = $1
              AND transaction_date >= $2::timestamptz
              AND transaction_date < ($3::date + INTERVAL '1 day')::timestamptz
              AND is_margin_blocked = TRUE
            GROUP BY category
            """,
            account_id,
            start_date,
            end_date
        )

        margin_by_category = {
            row['category']: float(row['total_margin'])
            for row in category_margins
        }

        # Margin by segment
        segment_margins = await conn.fetch(
            """
            SELECT segment, SUM(debit) as total_margin
            FROM statement_transactions
            WHERE account_id = $1
              AND transaction_date >= $2::timestamptz
              AND transaction_date < ($3::date + INTERVAL '1 day')::timestamptz
              AND is_margin_blocked = TRUE
              AND segment IS NOT NULL
            GROUP BY segment
            """,
            account_id,
            start_date,
            end_date
        )

        margin_by_segment = {
            row['segment']: float(row['total_margin'])
            for row in segment_margins
        }

        return MarginUtilizationMetrics(
            account_id=account_id,
            date_range={'start': start_date, 'end': end_date},
            total_margin_blocked=float(total_margin),
            available_margin=0,  # TODO: Fetch from account balance
            utilization_percentage=0,  # TODO: Calculate based on account limit
            peak_margin_blocked=peak_margin,
            peak_date=peak_date,
            avg_daily_margin=avg_daily_margin,
            margin_by_category=margin_by_category,
            margin_by_segment=margin_by_segment
        )


@router.get("/margin-timeseries", response_model=MarginTimeseriesResponse)
async def get_margin_timeseries(
    account_id: str = Query(..., description="Trading account ID"),
    start_date: Optional[date] = Query(None, description="Start date"),
    end_date: Optional[date] = Query(None, description="End date"),
    dm: DataManager = Depends(get_data_manager)
) -> MarginTimeseriesResponse:
    """
    Get daily margin utilization timeseries.

    Returns:
        Daily breakdown of margin blocked by category
    """
    # Default date range: last 30 days
    if not end_date:
        end_date = date.today()
    if not start_date:
        start_date = end_date - timedelta(days=30)

    async with dm.pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                DATE(transaction_date) as date,
                SUM(CASE WHEN is_margin_blocked THEN debit ELSE 0 END) as total_margin_blocked,
                SUM(CASE WHEN category = 'equity_intraday' AND is_margin_blocked THEN debit ELSE 0 END) as equity_intraday,
                SUM(CASE WHEN category = 'equity_delivery_acquisition' AND is_margin_blocked THEN debit ELSE 0 END) as equity_delivery,
                SUM(CASE WHEN category = 'fno_premium_paid' AND is_margin_blocked THEN debit ELSE 0 END) as fno_premium,
                SUM(CASE WHEN category = 'fno_futures_margin' AND is_margin_blocked THEN debit ELSE 0 END) as fno_futures,
                SUM(CASE WHEN category = 'ipo_application' AND is_margin_blocked THEN debit ELSE 0 END) as ipo_application
            FROM statement_transactions
            WHERE account_id = $1
              AND transaction_date >= $2::timestamptz
              AND transaction_date < ($3::date + INTERVAL '1 day')::timestamptz
            GROUP BY DATE(transaction_date)
            ORDER BY date
            """,
            account_id,
            start_date,
            end_date
        )

        timeseries = [
            DailyMarginTimeseries(
                date=row['date'],
                total_margin_blocked=float(row['total_margin_blocked']),
                equity_intraday=float(row['equity_intraday']),
                equity_delivery=float(row['equity_delivery']),
                fno_premium=float(row['fno_premium']),
                fno_futures=float(row['fno_futures']),
                ipo_application=float(row['ipo_application'])
            )
            for row in rows
        ]

        return MarginTimeseriesResponse(
            account_id=account_id,
            date_range={'start': start_date, 'end': end_date},
            timeseries=timeseries
        )
