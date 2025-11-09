"""
Trade Data Sync Service

Automatically syncs trading data (trades, orders, positions) from Kite API
to the local database for historical tracking and analytics.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

from loguru import logger
import asyncpg

from .accounts import SessionOrchestrator
from .config import get_settings

settings = get_settings()


@dataclass
class SyncResult:
    """Result of a sync operation"""
    account_id: str
    trades_synced: int
    orders_synced: int
    positions_synced: int
    duration_ms: int
    success: bool
    error: Optional[str] = None


class TradeSyncService:
    """
    Background service for syncing trade data from Kite to database.

    Features:
    - Periodic sync every 5 minutes (configurable)
    - Multi-account support with parallel fetching
    - Incremental updates with conflict resolution
    - Strategy attribution from order tags
    - Error handling and retry logic
    """

    def __init__(
        self,
        orchestrator: SessionOrchestrator,
        db_pool: asyncpg.Pool,
        sync_interval_seconds: int = 300,
    ):
        self.orchestrator = orchestrator
        self.db_pool = db_pool
        self.sync_interval = sync_interval_seconds
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
        logger.info(f"TradeSyncService initialized (interval={sync_interval_seconds}s)")

    async def start(self) -> None:
        """Start the background sync service"""
        if self._running:
            logger.warning("Trade sync service already running")
            return

        self._running = True
        self._stop_event.clear()
        self._task = asyncio.create_task(self._sync_loop())
        logger.info(f"Trade sync service started (interval={self.sync_interval}s)")

    async def stop(self) -> None:
        """Stop the background sync service"""
        if not self._running:
            return

        logger.info("Stopping trade sync service...")
        self._running = False
        self._stop_event.set()

        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=10.0)
            except asyncio.TimeoutError:
                logger.warning("Trade sync service did not stop gracefully, cancelling task")
                self._task.cancel()
            self._task = None

        logger.info("Trade sync service stopped")

    async def _sync_loop(self) -> None:
        """Main sync loop - runs periodically"""
        while not self._stop_event.is_set():
            try:
                # Run sync for all accounts
                results = await self.sync_all_accounts()

                # Log summary
                total_trades = sum(r.trades_synced for r in results)
                total_orders = sum(r.orders_synced for r in results)
                total_positions = sum(r.positions_synced for r in results)
                successful = sum(1 for r in results if r.success)

                logger.info(
                    f"Sync completed: {successful}/{len(results)} accounts successful | "
                    f"trades={total_trades} orders={total_orders} positions={total_positions}"
                )

            except Exception as exc:
                logger.exception(f"Sync loop error: {exc}")

            # Wait for next sync interval or stop signal
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self.sync_interval
                )
            except asyncio.TimeoutError:
                # Timeout is expected - continue to next iteration
                continue

    async def sync_all_accounts(self) -> List[SyncResult]:
        """Sync all configured accounts in parallel"""
        accounts = self.orchestrator.list_accounts()

        if not accounts:
            logger.warning("No accounts configured for sync")
            return []

        logger.info(f"Starting sync for {len(accounts)} accounts: {accounts}")

        # Create sync tasks for each account
        tasks = [
            self.sync_account(account_id)
            for account_id in accounts
        ]

        # Execute in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Handle exceptions
        sync_results = []
        for account_id, result in zip(accounts, results):
            if isinstance(result, Exception):
                logger.error(f"Sync failed for {account_id}: {result}")
                sync_results.append(SyncResult(
                    account_id=account_id,
                    trades_synced=0,
                    orders_synced=0,
                    positions_synced=0,
                    duration_ms=0,
                    success=False,
                    error=str(result)
                ))
            else:
                sync_results.append(result)

        return sync_results

    async def sync_account(self, account_id: str) -> SyncResult:
        """Sync a single account"""
        start_time = asyncio.get_event_loop().time()
        logger.info(f"Starting sync for account: {account_id}")

        try:
            async with self.orchestrator.borrow(account_id) as client:
                await client.ensure_session()

                # Fetch data from Kite API
                logger.debug(f"Fetching trades for {account_id}")
                trades_data = await client.trades()

                logger.debug(f"Fetching orders for {account_id}")
                orders_data = await client.orders()

                logger.debug(f"Fetching positions for {account_id}")
                positions_data = await client.positions()

                logger.info(
                    f"Fetched data for {account_id}: "
                    f"{len(trades_data)} trades, {len(orders_data)} orders, "
                    f"{len(positions_data.get('net', []))} positions"
                )

                # Store in database
                trades_count = await self._store_trades(account_id, trades_data)
                orders_count = await self._store_orders(account_id, orders_data)
                positions_count = await self._store_positions(account_id, positions_data)

                duration_ms = int((asyncio.get_event_loop().time() - start_time) * 1000)

                logger.info(
                    f"Sync completed for {account_id} in {duration_ms}ms: "
                    f"trades={trades_count}, orders={orders_count}, positions={positions_count}"
                )

                return SyncResult(
                    account_id=account_id,
                    trades_synced=trades_count,
                    orders_synced=orders_count,
                    positions_synced=positions_count,
                    duration_ms=duration_ms,
                    success=True
                )

        except Exception as exc:
            duration_ms = int((asyncio.get_event_loop().time() - start_time) * 1000)
            logger.exception(f"Failed to sync account {account_id}: {exc}")

            return SyncResult(
                account_id=account_id,
                trades_synced=0,
                orders_synced=0,
                positions_synced=0,
                duration_ms=duration_ms,
                success=False,
                error=str(exc)
            )

    async def _store_trades(
        self,
        account_id: str,
        trades_data: List[Dict[str, Any]]
    ) -> int:
        """Transform and store trades in database"""
        if not trades_data:
            logger.debug(f"No trades to sync for {account_id}")
            return 0

        # Transform Kite format to database schema
        records = []
        for trade in trades_data:
            try:
                # Parse timestamp
                fill_timestamp = self._parse_timestamp(trade.get("fill_timestamp"))
                if not fill_timestamp:
                    logger.warning(f"Skipping trade with invalid timestamp: {trade}")
                    continue

                record = (
                    fill_timestamp,  # time
                    account_id,  # account_id
                    str(trade.get("order_id", "")),  # order_id
                    trade.get("tradingsymbol", ""),  # symbol
                    "BUY" if trade.get("transaction_type") == "BUY" else "SELL",  # side
                    int(trade.get("quantity", 0)),  # quantity
                    float(trade.get("average_price", 0)),  # price
                    0.0,  # commission (calculate later if needed)
                    "FILLED",  # status
                    "zerodha",  # broker
                    self._extract_strategy_id(trade),  # strategy_id
                    0.0  # pnl (calculate later)
                )
                records.append(record)
            except Exception as e:
                logger.error(f"Error transforming trade {trade}: {e}")
                continue

        if not records:
            return 0

        # Upsert into database
        sql = """
            INSERT INTO trades (
                time, account_id, order_id, symbol, side, quantity,
                price, commission, status, broker, strategy_id, pnl
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            ON CONFLICT (time, account_id, order_id) DO UPDATE SET
                quantity = EXCLUDED.quantity,
                price = EXCLUDED.price,
                status = EXCLUDED.status,
                pnl = EXCLUDED.pnl
        """

        async with self.db_pool.acquire() as conn:
            await conn.executemany(sql, records)

        logger.info(f"Stored {len(records)} trades for {account_id}")
        return len(records)

    async def _store_orders(
        self,
        account_id: str,
        orders_data: List[Dict[str, Any]]
    ) -> int:
        """Transform and store orders in database"""
        if not orders_data:
            logger.debug(f"No orders to sync for {account_id}")
            return 0

        records = []
        for order in orders_data:
            try:
                order_id = str(order.get("order_id", ""))
                if not order_id:
                    continue

                created_at = self._parse_timestamp(order.get("order_timestamp"))
                executed_at = self._parse_timestamp(order.get("exchange_timestamp"))

                record = (
                    order_id,  # order_id
                    order.get("tradingsymbol", ""),  # symbol
                    order.get("order_type", ""),  # order_type
                    order.get("transaction_type", ""),  # side
                    int(order.get("quantity", 0)),  # quantity
                    float(order.get("price", 0)) if order.get("price") else None,  # price
                    int(order.get("filled_quantity", 0)),  # filled_quantity
                    order.get("status", ""),  # status
                    created_at,  # created_at
                    executed_at,  # executed_at
                    float(order.get("average_price", 0)) if order.get("average_price") else None,  # avg_fill_price
                    self._extract_strategy_id(order),  # strategy_id (from order tag)
                )
                records.append(record)
            except Exception as e:
                logger.error(f"Error transforming order {order}: {e}")
                continue

        if not records:
            return 0

        # Upsert into orders table
        sql = """
            INSERT INTO orders (
                order_id, symbol, order_type, side, quantity, price,
                filled_quantity, status, created_at, executed_at,
                avg_fill_price, metadata
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12::jsonb)
            ON CONFLICT (id) DO NOTHING
        """

        # For orders table, we need to handle the id conflict differently
        # Since order_id might not be the primary key, let's use account_order table instead
        sql_account_order = """
            INSERT INTO account_order (
                order_id, account_id, tradingsymbol, exchange, transaction_type,
                order_type, product, quantity, price, trigger_price,
                status, status_message, filled_quantity, average_price,
                placed_at, updated_at, strategy_id, raw_data
            )
            VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, NOW(), $16, $17::jsonb
            )
            ON CONFLICT (order_id) DO UPDATE SET
                status = EXCLUDED.status,
                status_message = EXCLUDED.status_message,
                filled_quantity = EXCLUDED.filled_quantity,
                average_price = EXCLUDED.average_price,
                updated_at = NOW(),
                synced_at = NOW()
        """

        account_order_records = []
        for order in orders_data:
            try:
                order_id = str(order.get("order_id", ""))
                if not order_id:
                    continue

                placed_at = self._parse_timestamp(order.get("order_timestamp"))

                record = (
                    order_id,  # order_id
                    account_id,  # account_id
                    order.get("tradingsymbol", ""),  # tradingsymbol
                    order.get("exchange", ""),  # exchange
                    order.get("transaction_type", ""),  # transaction_type
                    order.get("order_type", ""),  # order_type
                    order.get("product", ""),  # product
                    int(order.get("quantity", 0)),  # quantity
                    float(order.get("price", 0)) if order.get("price") else None,  # price
                    float(order.get("trigger_price", 0)) if order.get("trigger_price") else None,  # trigger_price
                    order.get("status", ""),  # status
                    order.get("status_message", ""),  # status_message
                    int(order.get("filled_quantity", 0)),  # filled_quantity
                    float(order.get("average_price", 0)) if order.get("average_price") else None,  # average_price
                    placed_at,  # placed_at
                    self._extract_strategy_id(order),  # strategy_id
                    order,  # raw_data (full order as JSON)
                )
                account_order_records.append(record)
            except Exception as e:
                logger.error(f"Error preparing account_order record {order}: {e}")
                continue

        if not account_order_records:
            return 0

        async with self.db_pool.acquire() as conn:
            await conn.executemany(sql_account_order, account_order_records)

        logger.info(f"Stored {len(account_order_records)} orders for {account_id}")
        return len(account_order_records)

    async def _store_positions(
        self,
        account_id: str,
        positions_data: Dict[str, List[Dict[str, Any]]]
    ) -> int:
        """Transform and store positions in database"""
        # Positions come as {"net": [...], "day": [...]}
        net_positions = positions_data.get("net", [])

        if not net_positions:
            logger.debug(f"No positions to sync for {account_id}")
            return 0

        records = []
        for pos in net_positions:
            try:
                record = (
                    account_id,  # account_id
                    pos.get("tradingsymbol", ""),  # tradingsymbol
                    pos.get("exchange", ""),  # exchange
                    pos.get("product", ""),  # product
                    int(pos.get("quantity", 0)),  # quantity
                    float(pos.get("average_price", 0)),  # average_price
                    float(pos.get("last_price", 0)),  # last_price
                    float(pos.get("pnl", 0)),  # pnl
                    float(pos.get("m2m", 0)),  # day_pnl
                    pos,  # raw_data (full position as JSON)
                )
                records.append(record)
            except Exception as e:
                logger.error(f"Error transforming position {pos}: {e}")
                continue

        if not records:
            return 0

        # Upsert into account_position table
        sql = """
            INSERT INTO account_position (
                account_id, tradingsymbol, exchange, product, quantity,
                average_price, last_price, pnl, day_pnl, raw_data, synced_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb, NOW())
            ON CONFLICT (account_id, tradingsymbol, exchange, product) DO UPDATE SET
                quantity = EXCLUDED.quantity,
                average_price = EXCLUDED.average_price,
                last_price = EXCLUDED.last_price,
                pnl = EXCLUDED.pnl,
                day_pnl = EXCLUDED.day_pnl,
                raw_data = EXCLUDED.raw_data,
                synced_at = NOW(),
                updated_at = NOW()
        """

        async with self.db_pool.acquire() as conn:
            await conn.executemany(sql, records)

        logger.info(f"Stored {len(records)} positions for {account_id}")
        return len(records)

    def _parse_timestamp(self, ts_str: Optional[str]) -> Optional[datetime]:
        """Parse Kite timestamp to datetime"""
        if not ts_str:
            return None

        # Kite format: "2025-11-07 09:15:30"
        try:
            return datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        except Exception as e:
            logger.debug(f"Failed to parse timestamp '{ts_str}': {e}")
            return None

    def _extract_strategy_id(self, order_or_trade: Dict[str, Any]) -> Optional[str]:
        """Extract strategy_id from order tag"""
        tag = order_or_trade.get("tag", "")

        if not tag:
            return None

        # Expected tag formats:
        # - "strategy_123"
        # - "strat:123"
        # - "s123"
        if tag.startswith("strategy_"):
            return tag.replace("strategy_", "")
        elif ":" in tag:
            parts = tag.split(":")
            if len(parts) == 2:
                return parts[1]
        elif tag.startswith("s") and tag[1:].isdigit():
            return tag[1:]

        # If tag doesn't match expected format, return None
        return None
