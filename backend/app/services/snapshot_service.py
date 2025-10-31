# app/services/snapshot_service.py
"""
Account Snapshot Service

Periodically snapshots positions, holdings, and funds data for historical analysis.
Snapshots are stored in TimescaleDB hypertables for efficient time-series queries.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

import asyncpg

from app.database import DataManager
from app.services.account_service import AccountService

logger = logging.getLogger("app.services.snapshot_service")


class AccountSnapshotService:
    """Service to take periodic snapshots of account state."""

    def __init__(self, data_manager: DataManager, account_service: AccountService):
        self.dm = data_manager
        self.account_service = account_service
        self.is_running = False
        self.snapshot_task: Optional[asyncio.Task] = None

    async def start(self, interval_seconds: int = 300):
        """
        Start the snapshot service.

        Args:
            interval_seconds: Interval between snapshots (default: 300 = 5 minutes)
        """
        if self.is_running:
            logger.warning("Snapshot service already running")
            return

        self.is_running = True
        self.snapshot_task = asyncio.create_task(
            self._snapshot_loop(interval_seconds)
        )
        logger.info(f"Account snapshot service started (interval: {interval_seconds}s)")

    async def stop(self):
        """Stop the snapshot service."""
        if not self.is_running:
            return

        self.is_running = False
        if self.snapshot_task:
            self.snapshot_task.cancel()
            try:
                await self.snapshot_task
            except asyncio.CancelledError:
                pass

        logger.info("Account snapshot service stopped")

    async def _snapshot_loop(self, interval_seconds: int):
        """Background loop to take snapshots periodically."""
        while self.is_running:
            try:
                # Get all active trading accounts
                accounts = await self._get_active_accounts()

                for account in accounts:
                    account_id = account['account_id']
                    try:
                        await self.snapshot_account(account_id)
                    except Exception as e:
                        logger.error(f"Failed to snapshot account {account_id}: {e}")

                # Wait for next interval
                await asyncio.sleep(interval_seconds)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in snapshot loop: {e}")
                await asyncio.sleep(60)  # Wait 1 minute before retrying

    async def _get_active_accounts(self) -> List[Dict[str, Any]]:
        """Get list of active trading accounts."""
        try:
            async with self.dm.pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT account_id, account_name, is_active
                    FROM trading_account
                    WHERE is_active = true
                """)
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to fetch active accounts: {e}")
            return []

    async def snapshot_account(self, account_id: str):
        """
        Take complete snapshot of account state.

        Args:
            account_id: Trading account ID
        """
        snapshot_time = datetime.now(timezone.utc)

        try:
            # Fetch current state from ticker_service via AccountService
            positions = await self.account_service.get_positions(account_id)
            holdings = await self.account_service.get_holdings(account_id)
            funds = await self.account_service.get_funds(account_id)

            # Store snapshots
            async with self.dm.pool.acquire() as conn:
                async with conn.transaction():
                    # Snapshot positions
                    if positions and 'data' in positions:
                        await self._store_position_snapshots(
                            conn, account_id, snapshot_time, positions['data']
                        )

                    # Snapshot holdings
                    if holdings and 'data' in holdings:
                        await self._store_holdings_snapshots(
                            conn, account_id, snapshot_time, holdings['data']
                        )

                    # Snapshot funds
                    if funds and 'data' in funds:
                        await self._store_funds_snapshots(
                            conn, account_id, snapshot_time, funds['data']
                        )

            logger.info(f"Snapshot completed for account {account_id} at {snapshot_time}")

        except Exception as e:
            logger.error(f"Failed to snapshot account {account_id}: {e}")
            raise

    async def _store_position_snapshots(
        self,
        conn: asyncpg.Connection,
        account_id: str,
        snapshot_time: datetime,
        positions: List[Dict[str, Any]]
    ):
        """Store position snapshots."""
        if not positions:
            return

        insert_query = """
            INSERT INTO position_snapshots (
                snapshot_time, account_id, tradingsymbol, exchange,
                product_type, quantity, average_price, last_price,
                market_value, unrealized_pnl, realized_pnl, margin_used,
                side, strike_price, expiry_date, option_type, snapshot_data
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17)
            ON CONFLICT (snapshot_time, account_id, tradingsymbol)
            DO UPDATE SET
                quantity = EXCLUDED.quantity,
                last_price = EXCLUDED.last_price,
                unrealized_pnl = EXCLUDED.unrealized_pnl,
                snapshot_data = EXCLUDED.snapshot_data
        """

        records = []
        for pos in positions:
            try:
                records.append((
                    snapshot_time,
                    account_id,
                    pos.get('tradingsymbol'),
                    pos.get('exchange'),
                    pos.get('product'),
                    float(pos.get('quantity', 0)),
                    float(pos.get('average_price', 0) or pos.get('avg_price', 0)),
                    float(pos.get('last_price', 0)),
                    float(pos.get('market_value', 0)),
                    float(pos.get('unrealized_pnl', 0) or pos.get('pnl', 0)),
                    float(pos.get('realized_pnl', 0)),
                    float(pos.get('margin_used', 0)),
                    pos.get('side', 'long'),
                    float(pos.get('strike_price', 0)) if pos.get('strike_price') else None,
                    pos.get('expiry_date'),
                    pos.get('option_type'),
                    json.dumps(pos)  # Store full position data
                ))
            except (ValueError, TypeError) as e:
                logger.warning(f"Skipping position {pos.get('tradingsymbol')}: {e}")
                continue

        if records:
            await conn.executemany(insert_query, records)
            logger.debug(f"Stored {len(records)} position snapshots for {account_id}")

    async def _store_holdings_snapshots(
        self,
        conn: asyncpg.Connection,
        account_id: str,
        snapshot_time: datetime,
        holdings: List[Dict[str, Any]]
    ):
        """Store holdings snapshots."""
        if not holdings:
            return

        insert_query = """
            INSERT INTO holdings_snapshots (
                snapshot_time, account_id, tradingsymbol, exchange,
                quantity, average_price, current_price, market_value,
                pnl, day_change, day_change_percent, holding_type, snapshot_data
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
            ON CONFLICT (snapshot_time, account_id, tradingsymbol)
            DO UPDATE SET
                current_price = EXCLUDED.current_price,
                market_value = EXCLUDED.market_value,
                pnl = EXCLUDED.pnl,
                snapshot_data = EXCLUDED.snapshot_data
        """

        records = []
        for holding in holdings:
            try:
                records.append((
                    snapshot_time,
                    account_id,
                    holding.get('tradingsymbol'),
                    holding.get('exchange'),
                    float(holding.get('quantity', 0)),
                    float(holding.get('average_price', 0)),
                    float(holding.get('current_price', 0) or holding.get('last_price', 0)),
                    float(holding.get('market_value', 0)),
                    float(holding.get('pnl', 0)),
                    float(holding.get('day_change', 0)),
                    float(holding.get('day_change_percent', 0)),
                    holding.get('holding_type', 'equity'),
                    json.dumps(holding)
                ))
            except (ValueError, TypeError) as e:
                logger.warning(f"Skipping holding {holding.get('tradingsymbol')}: {e}")
                continue

        if records:
            await conn.executemany(insert_query, records)
            logger.debug(f"Stored {len(records)} holdings snapshots for {account_id}")

    async def _store_funds_snapshots(
        self,
        conn: asyncpg.Connection,
        account_id: str,
        snapshot_time: datetime,
        funds: Dict[str, Any]
    ):
        """Store funds snapshots."""
        if not funds:
            return

        # Funds data is typically keyed by segment
        # Handle both single segment and multiple segments
        segments_data = []

        if isinstance(funds, dict):
            if 'equity' in funds or 'commodity' in funds:
                # Multiple segments
                for segment, data in funds.items():
                    segments_data.append((segment, data))
            else:
                # Single segment (assume equity)
                segments_data.append(('equity', funds))

        insert_query = """
            INSERT INTO funds_snapshots (
                snapshot_time, account_id, segment,
                available_cash, available_margin, used_margin, net,
                collateral, opening_balance, payin, payout,
                realized_pnl, unrealized_pnl, snapshot_data
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
            ON CONFLICT (snapshot_time, account_id, segment)
            DO UPDATE SET
                available_cash = EXCLUDED.available_cash,
                available_margin = EXCLUDED.available_margin,
                used_margin = EXCLUDED.used_margin,
                snapshot_data = EXCLUDED.snapshot_data
        """

        records = []
        for segment, data in segments_data:
            try:
                records.append((
                    snapshot_time,
                    account_id,
                    segment,
                    float(data.get('available_cash', 0) or data.get('available', {}).get('cash', 0)),
                    float(data.get('available_margin', 0) or data.get('available', {}).get('intraday_payin', 0)),
                    float(data.get('used_margin', 0) or data.get('utilised', {}).get('debits', 0)),
                    float(data.get('net', 0)),
                    float(data.get('collateral', 0)),
                    float(data.get('opening_balance', 0)),
                    float(data.get('payin', 0)),
                    float(data.get('payout', 0)),
                    float(data.get('realized_pnl', 0)),
                    float(data.get('unrealized_pnl', 0)),
                    json.dumps(data)
                ))
            except (ValueError, TypeError) as e:
                logger.warning(f"Skipping funds snapshot for segment {segment}: {e}")
                continue

        if records:
            await conn.executemany(insert_query, records)
            logger.debug(f"Stored {len(records)} funds snapshots for {account_id}")

    # ========== Query Methods for Historical Data ==========

    async def get_positions_at_time(
        self,
        account_id: str,
        timestamp: datetime
    ) -> List[Dict[str, Any]]:
        """
        Get position snapshot at specific time.

        Args:
            account_id: Trading account ID
            timestamp: Target timestamp

        Returns:
            List of positions at that time
        """
        async with self.dm.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM get_positions_at_time($1, $2)",
                account_id,
                timestamp
            )
            return [dict(row) for row in rows]

    async def get_positions_history(
        self,
        account_id: str,
        from_ts: datetime,
        to_ts: datetime,
        tradingsymbol: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get position history within time range.

        Args:
            account_id: Trading account ID
            from_ts: Start time
            to_ts: End time
            tradingsymbol: Optional filter by symbol

        Returns:
            List of position snapshots
        """
        query = """
            SELECT *
            FROM position_snapshots
            WHERE account_id = $1
              AND snapshot_time >= $2
              AND snapshot_time <= $3
        """
        params = [account_id, from_ts, to_ts]

        if tradingsymbol:
            query += " AND tradingsymbol = $4"
            params.append(tradingsymbol)

        query += " ORDER BY snapshot_time DESC"

        async with self.dm.pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
            return [dict(row) for row in rows]

    async def get_funds_at_time(
        self,
        account_id: str,
        timestamp: datetime,
        segment: str = 'equity'
    ) -> Optional[Dict[str, Any]]:
        """
        Get funds snapshot at specific time.

        Args:
            account_id: Trading account ID
            timestamp: Target timestamp
            segment: Segment ('equity', 'commodity', etc.)

        Returns:
            Funds data at that time
        """
        async with self.dm.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM get_funds_at_time($1, $2, $3)",
                account_id,
                segment,
                timestamp
            )
            return dict(row) if row else None

    async def get_funds_history(
        self,
        account_id: str,
        from_ts: datetime,
        to_ts: datetime,
        segment: str = 'equity'
    ) -> List[Dict[str, Any]]:
        """
        Get funds history within time range.

        Args:
            account_id: Trading account ID
            from_ts: Start time
            to_ts: End time
            segment: Segment filter

        Returns:
            List of funds snapshots
        """
        query = """
            SELECT *
            FROM funds_snapshots
            WHERE account_id = $1
              AND segment = $2
              AND snapshot_time >= $3
              AND snapshot_time <= $4
            ORDER BY snapshot_time DESC
        """

        async with self.dm.pool.acquire() as conn:
            rows = await conn.fetch(query, account_id, segment, from_ts, to_ts)
            return [dict(row) for row in rows]
