"""
Trading Accounts Service - Sprint 4
Provides proxy layer to ticker_service for trading accounts management.
Caches data in database for historical tracking and aggregation.
"""

import asyncio
import httpx
import logging
import json
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from decimal import Decimal

from ..database import DataManager


logger = logging.getLogger(__name__)


class AccountService:
    """
    Service for trading accounts management.
    Proxies requests to ticker_service and caches in database.
    """

    def __init__(self, dm: DataManager, ticker_url: str):
        """
        Initialize AccountService.

        Args:
            dm: DataManager instance for database operations
            ticker_url: Base URL for ticker_service API (e.g., http://ticker-service:8000)
        """
        self._dm = dm
        self._ticker_url = ticker_url.rstrip("/")
        self._http = httpx.AsyncClient(base_url=self._ticker_url, timeout=30.0)
        logger.info(f"AccountService initialized with ticker_url={ticker_url}")

    async def close(self):
        """Close HTTP client."""
        await self._http.aclose()

    # ============================================================================
    # Trading Accounts Management
    # ============================================================================

    async def list_accounts(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        List all trading accounts with aggregated metrics.

        Args:
            user_id: Optional filter by user_id

        Returns:
            List of accounts with metrics: {
                account_id, account_name, broker, is_active, login_status,
                total_pnl, total_positions, available_margin, last_sync_at
            }
        """
        if not self._dm.pool:
            logger.error("Database pool not available")
            return []

        try:
            # Build query
            query = """
                SELECT
                    ta.account_id,
                    ta.account_name,
                    ta.broker,
                    ta.is_active,
                    ta.login_status,
                    ta.last_login_at,
                    ta.last_sync_at,
                    ta.metadata,
                    COALESCE(SUM(ap.pnl), 0) as total_pnl,
                    COUNT(ap.id) as total_positions,
                    af.available_margin
                FROM trading_account ta
                LEFT JOIN account_position ap ON ta.account_id = ap.account_id
                LEFT JOIN account_funds af ON ta.account_id = af.account_id AND af.segment = 'equity'
            """

            params = []
            if user_id:
                query += " WHERE ta.account_id = $1"
                params.append(user_id)

            query += """
                GROUP BY ta.account_id, ta.account_name, ta.broker, ta.is_active,
                         ta.login_status, ta.last_login_at, ta.last_sync_at, ta.metadata,
                         af.available_margin
                ORDER BY ta.account_name
            """

            async with self._dm.pool.acquire() as conn:
                rows = await conn.fetch(query, *params)

            accounts = []
            for row in rows:
                accounts.append({
                    "account_id": row["account_id"],
                    "account_name": row["account_name"],
                    "broker": row["broker"],
                    "is_active": row["is_active"],
                    "login_status": row["login_status"],
                    "last_login_at": row["last_login_at"].isoformat() if row["last_login_at"] else None,
                    "last_sync_at": row["last_sync_at"].isoformat() if row["last_sync_at"] else None,
                    "total_pnl": float(row["total_pnl"]) if row["total_pnl"] else 0.0,
                    "total_positions": row["total_positions"],
                    "available_margin": float(row["available_margin"]) if row["available_margin"] else 0.0,
                    "metadata": row["metadata"]
                })

            logger.info(f"Retrieved {len(accounts)} accounts")
            return accounts

        except Exception as e:
            logger.error(f"Error listing accounts: {e}", exc_info=True)
            return []

    async def get_account(self, account_id: str) -> Optional[Dict[str, Any]]:
        """
        Get single account details.

        Args:
            account_id: Account identifier (user_id)

        Returns:
            Account details or None if not found
        """
        accounts = await self.list_accounts(user_id=account_id)
        return accounts[0] if accounts else None

    async def sync_account(self, account_id: str) -> Dict[str, Any]:
        """
        Sync account data from ticker_service.
        Fetches positions, holdings, orders, and funds.

        Args:
            account_id: Account identifier (user_id like XJ4540)

        Returns:
            Sync status: {success, synced_at, positions_count, orders_count, holdings_count}
        """
        logger.info(f"Syncing account {account_id}")

        try:
            # Map account_id to ticker_service account_id
            # For now, assume single user with account_id "primary"
            ticker_account_id = "primary"

            # Fetch data from ticker_service in parallel
            responses = await self._fetch_account_data(ticker_account_id)

            # Store in database
            synced_at = datetime.utcnow()
            positions_count = await self._sync_positions(account_id, responses.get("positions", []), synced_at)
            holdings_count = await self._sync_holdings(account_id, responses.get("holdings", []), synced_at)
            orders_count = await self._sync_orders(account_id, responses.get("orders", []), synced_at)
            await self._sync_funds(account_id, responses.get("margins", {}), synced_at)

            # Update account sync timestamp
            await self._update_account_sync(account_id, synced_at)

            logger.info(f"Synced account {account_id}: {positions_count} positions, {holdings_count} holdings, {orders_count} orders")

            return {
                "success": True,
                "synced_at": synced_at.isoformat(),
                "positions_count": positions_count,
                "holdings_count": holdings_count,
                "orders_count": orders_count
            }

        except Exception as e:
            logger.error(f"Error syncing account {account_id}: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }

    async def _fetch_account_data(self, account_id: str) -> Dict[str, Any]:
        """
        Fetch all account data from ticker_service in parallel for performance.

        Args:
            account_id: Account identifier (user_id or account_id)

        Returns:
            Dict with positions, holdings, orders, margins
        """
        try:
            # Fetch in parallel using asyncio.gather for maximum performance
            # This reduces 3 sequential HTTP calls to concurrent execution
            positions_task = self._http.get(f"/portfolio/positions", params={"account_id": account_id})
            holdings_task = self._http.get(f"/portfolio/holdings", params={"account_id": account_id})
            orders_task = self._http.get(f"/orders/", params={"account_id": account_id})

            # Await all requests concurrently
            positions_resp, holdings_resp, orders_resp = await asyncio.gather(
                positions_task,
                holdings_task,
                orders_task,
                return_exceptions=False
            )

            # Parse positions - ticker returns {net: [], day: []}
            positions_data = []
            if positions_resp.status_code == 200:
                pos_json = positions_resp.json()
                # Combine net and day positions
                positions_data = pos_json.get("net", []) + pos_json.get("day", [])

            return {
                "positions": positions_data,
                "holdings": holdings_resp.json() if holdings_resp.status_code == 200 else [],
                "orders": orders_resp.json() if orders_resp.status_code == 200 else [],
                "margins": {}  # Margins endpoint may not be available
            }

        except httpx.HTTPError as e:
            logger.error(f"HTTP error fetching account data: {e}")
            raise
        except Exception as e:
            logger.error(f"Error fetching account data: {e}")
            raise

    async def _sync_positions(self, account_id: str, positions: List[Dict], synced_at: datetime) -> int:
        """Sync positions to database."""
        if not self._dm.pool or not positions:
            return 0

        query = """
            INSERT INTO account_position
                (account_id, tradingsymbol, exchange, instrument_token, product,
                 quantity, average_price, last_price, pnl, day_pnl, synced_at, raw_data)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            ON CONFLICT (account_id, tradingsymbol, exchange, product)
            DO UPDATE SET
                quantity = EXCLUDED.quantity,
                average_price = EXCLUDED.average_price,
                last_price = EXCLUDED.last_price,
                pnl = EXCLUDED.pnl,
                day_pnl = EXCLUDED.day_pnl,
                synced_at = EXCLUDED.synced_at,
                raw_data = EXCLUDED.raw_data,
                updated_at = NOW()
        """

        async with self._dm.pool.acquire() as conn:
            for pos in positions:
                await conn.execute(
                    query,
                    account_id,
                    pos.get("tradingsymbol"),
                    pos.get("exchange"),
                    pos.get("instrument_token"),
                    pos.get("product"),
                    pos.get("quantity", 0),
                    Decimal(str(pos.get("average_price", 0))),
                    Decimal(str(pos.get("last_price", 0))),
                    Decimal(str(pos.get("pnl", 0))),
                    Decimal(str(pos.get("day_pnl", 0))),
                    synced_at,
                    json.dumps(pos)
                )

        return len(positions)

    async def _sync_holdings(self, account_id: str, holdings: List[Dict], synced_at: datetime) -> int:
        """Sync holdings to database."""
        if not self._dm.pool or not holdings:
            return 0

        query = """
            INSERT INTO account_holding
                (account_id, tradingsymbol, exchange, isin, quantity,
                 average_price, last_price, pnl, day_pnl, synced_at, raw_data)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            ON CONFLICT (account_id, tradingsymbol, exchange)
            DO UPDATE SET
                quantity = EXCLUDED.quantity,
                average_price = EXCLUDED.average_price,
                last_price = EXCLUDED.last_price,
                pnl = EXCLUDED.pnl,
                day_pnl = EXCLUDED.day_pnl,
                synced_at = EXCLUDED.synced_at,
                raw_data = EXCLUDED.raw_data,
                updated_at = NOW()
        """

        async with self._dm.pool.acquire() as conn:
            for holding in holdings:
                await conn.execute(
                    query,
                    account_id,
                    holding.get("tradingsymbol"),
                    holding.get("exchange"),
                    holding.get("isin"),
                    holding.get("quantity", 0),
                    Decimal(str(holding.get("average_price", 0))),
                    Decimal(str(holding.get("last_price", 0))),
                    Decimal(str(holding.get("pnl", 0))),
                    Decimal(str(holding.get("day_pnl", 0))),
                    synced_at,
                    json.dumps(holding)
                )

        return len(holdings)

    async def _sync_orders(self, account_id: str, orders: List[Dict], synced_at: datetime) -> int:
        """Sync orders to database."""
        if not self._dm.pool or not orders:
            return 0

        query = """
            INSERT INTO account_order
                (order_id, account_id, tradingsymbol, exchange, instrument_token,
                 transaction_type, order_type, product, quantity, price, trigger_price,
                 status, status_message, filled_quantity, average_price, placed_at, synced_at, raw_data)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18)
            ON CONFLICT (order_id)
            DO UPDATE SET
                status = EXCLUDED.status,
                status_message = EXCLUDED.status_message,
                filled_quantity = EXCLUDED.filled_quantity,
                average_price = EXCLUDED.average_price,
                synced_at = EXCLUDED.synced_at,
                raw_data = EXCLUDED.raw_data,
                updated_at = NOW()
        """

        async with self._dm.pool.acquire() as conn:
            for order in orders:
                # Parse placed_at timestamp
                placed_at = None
                if order.get("order_timestamp"):
                    try:
                        placed_at = datetime.fromisoformat(order["order_timestamp"].replace("Z", "+00:00"))
                    except:
                        placed_at = synced_at

                await conn.execute(
                    query,
                    order.get("order_id"),
                    account_id,
                    order.get("tradingsymbol"),
                    order.get("exchange"),
                    order.get("instrument_token"),
                    order.get("transaction_type"),
                    order.get("order_type"),
                    order.get("product"),
                    order.get("quantity", 0),
                    Decimal(str(order.get("price", 0))) if order.get("price") else None,
                    Decimal(str(order.get("trigger_price", 0))) if order.get("trigger_price") else None,
                    order.get("status"),
                    order.get("status_message"),
                    order.get("filled_quantity", 0),
                    Decimal(str(order.get("average_price", 0))) if order.get("average_price") else None,
                    placed_at,
                    synced_at,
                    json.dumps(order)
                )

        return len(orders)

    async def _sync_funds(self, account_id: str, margins: Dict, synced_at: datetime) -> None:
        """Sync funds/margins to database."""
        if not self._dm.pool or not margins:
            return

        query = """
            INSERT INTO account_funds
                (account_id, segment, available_cash, available_margin, used_margin, net, synced_at, raw_data)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (account_id, segment)
            DO UPDATE SET
                available_cash = EXCLUDED.available_cash,
                available_margin = EXCLUDED.available_margin,
                used_margin = EXCLUDED.used_margin,
                net = EXCLUDED.net,
                synced_at = EXCLUDED.synced_at,
                raw_data = EXCLUDED.raw_data,
                updated_at = NOW()
        """

        async with self._dm.pool.acquire() as conn:
            # Handle both equity and commodity segments
            for segment in ["equity", "commodity"]:
                segment_data = margins.get(segment, {})
                if segment_data:
                    await conn.execute(
                        query,
                        account_id,
                        segment,
                        Decimal(str(segment_data.get("available", {}).get("cash", 0))),
                        Decimal(str(segment_data.get("available", {}).get("live_balance", 0))),
                        Decimal(str(segment_data.get("utilised", {}).get("debits", 0))),
                        Decimal(str(segment_data.get("net", 0))),
                        synced_at,
                        json.dumps(segment_data)
                    )

    async def _update_account_sync(self, account_id: str, synced_at: datetime) -> None:
        """Update account last_sync_at timestamp."""
        if not self._dm.pool:
            return

        query = """
            UPDATE trading_account
            SET last_sync_at = $1, updated_at = NOW()
            WHERE account_id = $2
        """

        async with self._dm.pool.acquire() as conn:
            await conn.execute(query, synced_at, account_id)

    # ============================================================================
    # Positions
    # ============================================================================

    async def get_positions(self, account_id: str, fresh: bool = False) -> List[Dict[str, Any]]:
        """
        Get positions for an account.

        Args:
            account_id: Account identifier
            fresh: If True, fetch fresh data from ticker_service; if False, use cached data

        Returns:
            List of positions
        """
        if fresh:
            # Fetch fresh data and sync
            await self.sync_account(account_id)

        if not self._dm.pool:
            return []

        query = """
            SELECT
                tradingsymbol, exchange, instrument_token, product,
                quantity, average_price, last_price, pnl, day_pnl,
                synced_at, raw_data
            FROM account_position
            WHERE account_id = $1
            ORDER BY synced_at DESC
        """

        async with self._dm.pool.acquire() as conn:
            rows = await conn.fetch(query, account_id)

        positions = []
        for row in rows:
            positions.append({
                "tradingsymbol": row["tradingsymbol"],
                "exchange": row["exchange"],
                "instrument_token": row["instrument_token"],
                "product": row["product"],
                "quantity": row["quantity"],
                "average_price": float(row["average_price"]) if row["average_price"] else 0.0,
                "last_price": float(row["last_price"]) if row["last_price"] else 0.0,
                "pnl": float(row["pnl"]) if row["pnl"] else 0.0,
                "day_pnl": float(row["day_pnl"]) if row["day_pnl"] else 0.0,
                "synced_at": row["synced_at"].isoformat()
            })

        return positions

    # ============================================================================
    # Orders
    # ============================================================================

    async def get_orders(
        self,
        account_id: str,
        status: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get orders for an account.

        Args:
            account_id: Account identifier
            status: Optional filter by status (OPEN, COMPLETE, CANCELLED, etc.)
            limit: Max number of orders to return

        Returns:
            List of orders
        """
        if not self._dm.pool:
            return []

        query = """
            SELECT
                order_id, tradingsymbol, exchange, transaction_type, order_type, product,
                quantity, price, trigger_price, status, status_message,
                filled_quantity, average_price, placed_at, updated_at, raw_data
            FROM account_order
            WHERE account_id = $1
        """

        params = [account_id]
        if status:
            query += " AND status = $2"
            params.append(status)

        query += " ORDER BY placed_at DESC LIMIT $" + str(len(params) + 1)
        params.append(limit)

        async with self._dm.pool.acquire() as conn:
            rows = await conn.fetch(query, *params)

        orders = []
        for row in rows:
            orders.append({
                "order_id": row["order_id"],
                "tradingsymbol": row["tradingsymbol"],
                "exchange": row["exchange"],
                "transaction_type": row["transaction_type"],
                "order_type": row["order_type"],
                "product": row["product"],
                "quantity": row["quantity"],
                "price": float(row["price"]) if row["price"] else None,
                "trigger_price": float(row["trigger_price"]) if row["trigger_price"] else None,
                "status": row["status"],
                "status_message": row["status_message"],
                "filled_quantity": row["filled_quantity"],
                "average_price": float(row["average_price"]) if row["average_price"] else None,
                "placed_at": row["placed_at"].isoformat() if row["placed_at"] else None,
                "updated_at": row["updated_at"].isoformat()
            })

        return orders

    async def place_order(
        self,
        account_id: str,
        tradingsymbol: str,
        exchange: str,
        transaction_type: str,
        quantity: int,
        order_type: str = "MARKET",
        product: str = "MIS",
        price: Optional[float] = None,
        trigger_price: Optional[float] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Place a new order via ticker_service.

        Args:
            account_id: Account identifier (user_id)
            tradingsymbol: Trading symbol
            exchange: Exchange (NSE, NFO, etc.)
            transaction_type: BUY or SELL
            quantity: Order quantity
            order_type: MARKET, LIMIT, SL, SL-M
            product: MIS, NRML, CNC
            price: Limit price (for LIMIT/SL orders)
            trigger_price: Trigger price (for SL/SL-M orders)

        Returns:
            Order result: {success, order_id, message}
        """
        try:
            payload = {
                "user_id": account_id,
                "tradingsymbol": tradingsymbol,
                "exchange": exchange,
                "transaction_type": transaction_type,
                "quantity": quantity,
                "order_type": order_type,
                "product": product,
            }

            if price is not None:
                payload["price"] = price
            if trigger_price is not None:
                payload["trigger_price"] = trigger_price

            # Add any additional parameters
            payload.update(kwargs)

            # Call ticker_service
            response = await self._http.post("/kite/orders", json=payload)
            response.raise_for_status()

            result = response.json()
            order_id = result.get("order_id")

            # Sync orders to update database
            await self.sync_account(account_id)

            logger.info(f"Order placed: {order_id} for account {account_id}")

            return {
                "success": True,
                "order_id": order_id,
                "message": "Order placed successfully"
            }

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error placing order: {e.response.status_code} - {e.response.text}")
            return {
                "success": False,
                "error": f"HTTP {e.response.status_code}: {e.response.text}"
            }
        except Exception as e:
            logger.error(f"Error placing order: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }

    async def place_batch_orders(
        self,
        account_id: str,
        orders: List[Dict[str, Any]],
        rollback_on_failure: bool = True
    ) -> Dict[str, Any]:
        """
        Place multiple orders atomically via ticker_service batch endpoint.

        Args:
            account_id: Account identifier (user_id)
            orders: List of order specifications (each dict contains order parameters)
            rollback_on_failure: If True, cancel all orders if any fails (default: True)

        Returns:
            Batch result: {
                batch_id, success, total_orders, succeeded, failed,
                created_at, completed_at, order_ids (list), errors (list)
            }

        Example:
            orders = [
                {
                    "tradingsymbol": "NIFTY25NOVFUT",
                    "exchange": "NFO",
                    "transaction_type": "BUY",
                    "quantity": 50,
                    "order_type": "MARKET",
                    "product": "NRML"
                },
                {
                    "tradingsymbol": "BANKNIFTY25NOVFUT",
                    "exchange": "NFO",
                    "transaction_type": "SELL",
                    "quantity": 25,
                    "order_type": "LIMIT",
                    "product": "NRML",
                    "price": 45500.0
                }
            ]
        """
        try:
            payload = {
                "orders": orders,
                "account_id": account_id,
                "rollback_on_failure": rollback_on_failure
            }

            logger.info(f"Placing batch of {len(orders)} orders for account {account_id}")

            # Call ticker_service batch orders endpoint
            response = await self._http.post("/advanced/batch-orders", json=payload)
            response.raise_for_status()

            result = response.json()

            # Sync orders to update database with all new orders
            await self.sync_account(account_id)

            batch_id = result.get("batch_id")
            succeeded = result.get("succeeded", 0)
            failed = result.get("failed", 0)

            logger.info(
                f"Batch order completed: batch_id={batch_id}, "
                f"succeeded={succeeded}, failed={failed}"
            )

            return result

        except httpx.HTTPStatusError as e:
            error_detail = e.response.text
            logger.error(
                f"HTTP error placing batch orders: {e.response.status_code} - {error_detail}"
            )
            return {
                "success": False,
                "total_orders": len(orders),
                "succeeded": 0,
                "failed": len(orders),
                "error": f"HTTP {e.response.status_code}: {error_detail}"
            }

        except Exception as e:
            logger.error(f"Error placing batch orders: {e}", exc_info=True)
            return {
                "success": False,
                "total_orders": len(orders),
                "succeeded": 0,
                "failed": len(orders),
                "error": str(e)
            }

    # ============================================================================
    # Holdings
    # ============================================================================

    async def get_holdings(self, account_id: str) -> List[Dict[str, Any]]:
        """Get holdings for an account."""
        if not self._dm.pool:
            return []

        query = """
            SELECT
                tradingsymbol, exchange, isin, quantity,
                average_price, last_price, pnl, day_pnl, synced_at
            FROM account_holding
            WHERE account_id = $1
            ORDER BY synced_at DESC
        """

        async with self._dm.pool.acquire() as conn:
            rows = await conn.fetch(query, account_id)

        holdings = []
        for row in rows:
            holdings.append({
                "tradingsymbol": row["tradingsymbol"],
                "exchange": row["exchange"],
                "isin": row["isin"],
                "quantity": row["quantity"],
                "average_price": float(row["average_price"]) if row["average_price"] else 0.0,
                "last_price": float(row["last_price"]) if row["last_price"] else 0.0,
                "pnl": float(row["pnl"]) if row["pnl"] else 0.0,
                "day_pnl": float(row["day_pnl"]) if row["day_pnl"] else 0.0,
                "synced_at": row["synced_at"].isoformat()
            })

        return holdings

    # ============================================================================
    # Funds/Margins
    # ============================================================================

    async def get_funds(self, account_id: str, segment: str = "equity") -> Optional[Dict[str, Any]]:
        """Get funds/margins for an account."""
        if not self._dm.pool:
            return None

        query = """
            SELECT
                segment, available_cash, available_margin, used_margin, net, synced_at
            FROM account_funds
            WHERE account_id = $1 AND segment = $2
            ORDER BY synced_at DESC
            LIMIT 1
        """

        async with self._dm.pool.acquire() as conn:
            row = await conn.fetchrow(query, account_id, segment)

        if not row:
            return None

        return {
            "segment": row["segment"],
            "available_cash": float(row["available_cash"]) if row["available_cash"] else 0.0,
            "available_margin": float(row["available_margin"]) if row["available_margin"] else 0.0,
            "used_margin": float(row["used_margin"]) if row["used_margin"] else 0.0,
            "net": float(row["net"]) if row["net"] else 0.0,
            "synced_at": row["synced_at"].isoformat()
        }
