# Trade Data Ingestion Pipeline - Design Document

**Version**: 1.0
**Date**: 2025-11-07
**Status**: Design Phase
**Author**: Claude (Ticker Service Team)

---

## Executive Summary

This document outlines the design for a comprehensive Trade Data Ingestion Pipeline that synchronizes trading account data (orders, trades, positions, holdings) from the Kite broker API to the local database for historical tracking, analytics, and strategy backtesting.

**Key Goals**:
1. **Automated Background Sync** - Fetch trading data every 5 minutes
2. **Historical Record** - Store all trades, orders, and positions in TimescaleDB
3. **Multi-Account Support** - Handle multiple trading accounts concurrently
4. **Strategy Attribution** - Tag trades with strategy_id for P&L tracking
5. **Real-Time Analytics** - Enable dashboards and performance metrics

---

## 1. Current State Analysis

### 1.1 Existing Infrastructure ✅

**Database Tables (Already Created)**:
- `trades` - TimescaleDB hypertable for all executed trades
- `orders` - Complete order history with status tracking
- `positions` - Position snapshots with P&L calculation
- `account_order` - Account-specific order cache
- `account_position` - Account-specific position cache
- `trading_account` - Account metadata and configuration

**API Access (Already Implemented)**:
- `KiteClient.trades()` - Fetch all trades for the day
- `KiteClient.orders()` - Fetch all orders for the day
- `KiteClient.positions()` - Fetch current positions (net + day)
- `KiteClient.holdings()` - Fetch long-term holdings

**Backend Endpoints (Already Deployed)**:
- `POST /accounts/{account_id}/sync` - Manual sync trigger
- `GET /accounts/{account_id}/positions` - Fetch positions with fresh flag
- `GET /accounts/{account_id}/orders` - Fetch orders with filters
- `GET /accounts/{account_id}/holdings` - Fetch holdings

### 1.2 Current Gaps ⚠️

**No Automated Background Sync**:
- Data is fetched on-demand via API calls
- No persistent historical record
- Manual intervention required for sync

**No Strategy Attribution**:
- Trades are not tagged with strategy_id
- Cannot calculate per-strategy P&L
- No automated strategy performance tracking

**No Incremental Sync**:
- Full fetch every time (inefficient)
- No delta detection or change tracking
- Duplicate data risk

---

## 2. Architecture Design

### 2.1 System Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                    TRADE DATA INGESTION PIPELINE                 │
└──────────────────────────────────────────────────────────────────┘

┌─────────────────┐
│  Kite Broker    │
│  API (Zerodha)  │
└────────┬────────┘
         │ HTTPS
         │ (Rate Limited: 3 req/sec)
         ↓
┌──────────────────────────────────────────────────────────────────┐
│                  TICKER SERVICE (FastAPI)                        │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  Trade Sync Service (NEW)                                  │ │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐       │ │
│  │  │  Scheduler  │  │ Sync Worker │  │  Persister  │       │ │
│  │  │             │→ │             │→ │             │       │ │
│  │  │  (5 min)    │  │ (Accounts)  │  │ (Database)  │       │ │
│  │  └─────────────┘  └─────────────┘  └─────────────┘       │ │
│  │                                                             │ │
│  │  Sync Workflow:                                            │ │
│  │  1. Fetch trades from Kite API                             │ │
│  │  2. Fetch orders from Kite API                             │ │
│  │  3. Fetch positions from Kite API                          │ │
│  │  4. Transform to database schema                           │ │
│  │  5. Upsert into TimescaleDB                                │ │
│  │  6. Update sync timestamps                                 │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                   │
│  Existing Components:                                            │
│  ├─ KiteClient (API wrapper)                                     │
│  ├─ SessionOrchestrator (multi-account)                          │
│  └─ Rate Limiter (API protection)                                │
└───────────────────────────────┬───────────────────────────────────┘
                                │
                                ↓
┌──────────────────────────────────────────────────────────────────┐
│              TimescaleDB (stocksblitz_unified)                   │
│  ┌────────────────┐  ┌──────────────┐  ┌──────────────────────┐ │
│  │ trades         │  │ orders       │  │ positions            │ │
│  │ (hypertable)   │  │              │  │                      │ │
│  ├────────────────┤  ├──────────────┤  ├──────────────────────┤ │
│  │ time           │  │ order_id     │  │ account_id           │ │
│  │ account_id     │  │ symbol       │  │ tradingsymbol        │ │
│  │ order_id       │  │ status       │  │ quantity             │ │
│  │ symbol         │  │ quantity     │  │ average_price        │ │
│  │ side           │  │ filled_qty   │  │ pnl                  │ │
│  │ quantity       │  │ avg_price    │  │ day_pnl              │ │
│  │ price          │  │ created_at   │  │ synced_at            │ │
│  │ pnl            │  │ executed_at  │  │ strategy_id          │ │
│  │ strategy_id    │  │ strategy_id  │  └──────────────────────┘ │
│  └────────────────┘  └──────────────┘                           │
│                                                                   │
│  Continuous Aggregates (Auto-compute):                          │
│  ├─ daily_pnl_by_strategy                                        │
│  ├─ hourly_trade_volume                                          │
│  └─ account_performance_metrics                                  │
└──────────────────────────────────────────────────────────────────┘
         │
         ↓
┌──────────────────────────────────────────────────────────────────┐
│                    ANALYTICS & REPORTING                         │
│  ├─ Strategy Performance Dashboard                               │
│  ├─ P&L Attribution by Strategy                                  │
│  ├─ Trade Replay & Backtesting                                   │
│  └─ Risk Metrics (Sharpe, Drawdown, Win Rate)                    │
└──────────────────────────────────────────────────────────────────┘
```

### 2.2 Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│  STEP 1: Scheduled Trigger (Every 5 minutes)                    │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ↓
┌─────────────────────────────────────────────────────────────────┐
│  STEP 2: Multi-Account Fetch (Parallel)                        │
│                                                                  │
│  For each account in ["primary", "secondary", ...]:             │
│    ├─ Fetch trades: await client.trades()                       │
│    ├─ Fetch orders: await client.orders()                       │
│    ├─ Fetch positions: await client.positions()                 │
│    └─ Fetch holdings: await client.holdings()                   │
│                                                                  │
│  Error Handling:                                                │
│    ├─ Retry on network failure (3x with backoff)                │
│    ├─ Skip account on auth failure (log error)                  │
│    └─ Continue with other accounts on partial failure           │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ↓
┌─────────────────────────────────────────────────────────────────┐
│  STEP 3: Data Transformation                                   │
│                                                                  │
│  Transform Kite format → Database schema:                       │
│                                                                  │
│  Trades:                                                         │
│    Kite: {trade_id, order_id, tradingsymbol, exchange, ...}     │
│    DB:   {time, account_id, order_id, symbol, side, quantity,   │
│           price, commission, pnl, strategy_id}                  │
│                                                                  │
│  Orders:                                                         │
│    Kite: {order_id, tradingsymbol, status, quantity, ...}       │
│    DB:   {order_id, symbol, order_type, side, quantity, price,  │
│           filled_quantity, status, created_at, executed_at,     │
│           strategy_id}                                          │
│                                                                  │
│  Positions:                                                      │
│    Kite: {tradingsymbol, product, quantity, pnl, ...}           │
│    DB:   {account_id, tradingsymbol, quantity, average_price,   │
│           unrealized_pnl, realized_pnl, strategy_id}            │
│                                                                  │
│  Strategy Attribution:                                          │
│    ├─ Parse order.tag → extract strategy_id                     │
│    ├─ Match symbol pattern → strategy mapping                   │
│    └─ Default to NULL if no strategy detected                   │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ↓
┌─────────────────────────────────────────────────────────────────┐
│  STEP 4: Incremental Upsert (Conflict Handling)                │
│                                                                  │
│  Trades:                                                         │
│    INSERT INTO trades (time, account_id, order_id, ...)         │
│    VALUES (...)                                                  │
│    ON CONFLICT (time, account_id, order_id) DO UPDATE SET       │
│      pnl = EXCLUDED.pnl,                                         │
│      status = EXCLUDED.status;                                  │
│                                                                  │
│  Orders:                                                         │
│    INSERT INTO orders (order_id, symbol, ...)                   │
│    VALUES (...)                                                  │
│    ON CONFLICT (order_id) DO UPDATE SET                         │
│      status = EXCLUDED.status,                                  │
│      filled_quantity = EXCLUDED.filled_quantity,                │
│      avg_fill_price = EXCLUDED.avg_fill_price,                  │
│      updated_at = NOW();                                        │
│                                                                  │
│  Positions:                                                      │
│    INSERT INTO account_position (account_id, tradingsymbol, ...) │
│    VALUES (...)                                                  │
│    ON CONFLICT (account_id, tradingsymbol, exchange, product)   │
│    DO UPDATE SET                                                │
│      quantity = EXCLUDED.quantity,                              │
│      last_price = EXCLUDED.last_price,                          │
│      pnl = EXCLUDED.pnl,                                         │
│      synced_at = NOW();                                         │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ↓
┌─────────────────────────────────────────────────────────────────┐
│  STEP 5: Update Sync Metadata                                  │
│                                                                  │
│  UPDATE trading_account                                         │
│  SET last_sync_at = NOW(),                                      │
│      trades_count = (SELECT COUNT(*) FROM trades                │
│                      WHERE account_id = $1),                    │
│      orders_count = (SELECT COUNT(*) FROM orders                │
│                      WHERE account_id = $1)                     │
│  WHERE account_id = $1;                                         │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ↓
┌─────────────────────────────────────────────────────────────────┐
│  STEP 6: Publish Metrics & Logs                                │
│                                                                  │
│  ├─ Log sync summary (trades: 15, orders: 8, positions: 3)      │
│  ├─ Emit Prometheus metrics (sync_duration_seconds)             │
│  ├─ Alert on sync failures (Slack/email notification)           │
│  └─ Update sync status in Redis (for health checks)             │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Component Design

### 3.1 Trade Sync Service

**File**: `ticker_service/app/trade_sync.py`

```python
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

from loguru import logger

from .accounts import SessionOrchestrator
from .config import get_settings
from .database import DataManager


@dataclass
class SyncResult:
    """Result of a sync operation"""
    account_id: str
    trades_synced: int
    orders_synced: int
    positions_synced: int
    holdings_synced: int
    duration_ms: int
    success: bool
    error: Optional[str] = None


class TradeSyncService:
    """
    Background service for syncing trade data from Kite to database.

    Features:
    - Periodic sync every 5 minutes
    - Multi-account support with parallel fetching
    - Incremental updates with conflict resolution
    - Strategy attribution from order tags
    - Error handling and retry logic
    """

    def __init__(
        self,
        orchestrator: SessionOrchestrator,
        data_manager: DataManager,
        sync_interval_seconds: int = 300,
    ):
        self.orchestrator = orchestrator
        self.dm = data_manager
        self.sync_interval = sync_interval_seconds
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()

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

        self._running = False
        self._stop_event.set()

        if self._task:
            await self._task
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

                logger.info(
                    f"Sync completed: {len(results)} accounts | "
                    f"trades={total_trades} orders={total_orders} positions={total_positions}"
                )

            except Exception as exc:
                logger.exception(f"Sync loop error: {exc}")

            # Wait for next sync interval
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self.sync_interval
                )
            except asyncio.TimeoutError:
                continue

    async def sync_all_accounts(self) -> List[SyncResult]:
        """Sync all configured accounts in parallel"""
        accounts = self.orchestrator.list_accounts()

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
                    holdings_synced=0,
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

        try:
            async with self.orchestrator.borrow(account_id) as client:
                # Fetch data from Kite API
                trades_data = await client.trades()
                orders_data = await client.orders()
                positions_data = await client.positions()
                holdings_data = await client.holdings()

                # Store in database
                trades_count = await self._store_trades(account_id, trades_data)
                orders_count = await self._store_orders(account_id, orders_data)
                positions_count = await self._store_positions(account_id, positions_data)
                holdings_count = await self._store_holdings(account_id, holdings_data)

                duration_ms = int((asyncio.get_event_loop().time() - start_time) * 1000)

                return SyncResult(
                    account_id=account_id,
                    trades_synced=trades_count,
                    orders_synced=orders_count,
                    positions_synced=positions_count,
                    holdings_synced=holdings_count,
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
                holdings_synced=0,
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
            return 0

        # Transform Kite format to database schema
        records = []
        for trade in trades_data:
            record = {
                "time": self._parse_timestamp(trade.get("fill_timestamp")),
                "account_id": account_id,
                "order_id": str(trade.get("order_id")),
                "symbol": trade.get("tradingsymbol"),
                "side": "BUY" if trade.get("transaction_type") == "BUY" else "SELL",
                "quantity": int(trade.get("quantity", 0)),
                "price": float(trade.get("average_price", 0)),
                "commission": 0.0,  # Calculate from exchange_order_id if needed
                "status": "FILLED",
                "broker": "zerodha",
                "strategy_id": self._extract_strategy_id(trade),
                "pnl": 0.0  # Will be calculated later
            }
            records.append(record)

        # Upsert into database
        await self.dm.upsert_trades(records)
        return len(records)

    async def _store_orders(
        self,
        account_id: str,
        orders_data: List[Dict[str, Any]]
    ) -> int:
        """Transform and store orders in database"""
        if not orders_data:
            return 0

        records = []
        for order in orders_data:
            record = {
                "order_id": str(order.get("order_id")),
                "symbol": order.get("tradingsymbol"),
                "order_type": order.get("order_type"),
                "side": order.get("transaction_type"),
                "quantity": int(order.get("quantity", 0)),
                "price": float(order.get("price", 0)) if order.get("price") else None,
                "filled_quantity": int(order.get("filled_quantity", 0)),
                "status": order.get("status"),
                "created_at": self._parse_timestamp(order.get("order_timestamp")),
                "executed_at": self._parse_timestamp(order.get("exchange_timestamp")),
                "avg_fill_price": float(order.get("average_price", 0)) if order.get("average_price") else None,
                "strategy_id": self._extract_strategy_id(order),
                "metadata": order  # Store full raw data
            }
            records.append(record)

        await self.dm.upsert_orders(records)
        return len(records)

    async def _store_positions(
        self,
        account_id: str,
        positions_data: Dict[str, List[Dict[str, Any]]]
    ) -> int:
        """Transform and store positions in database"""
        # Positions come as {"net": [...], "day": [...]}
        net_positions = positions_data.get("net", [])

        if not net_positions:
            return 0

        records = []
        for pos in net_positions:
            record = {
                "account_id": account_id,
                "tradingsymbol": pos.get("tradingsymbol"),
                "exchange": pos.get("exchange"),
                "product": pos.get("product"),
                "quantity": int(pos.get("quantity", 0)),
                "average_price": float(pos.get("average_price", 0)),
                "last_price": float(pos.get("last_price", 0)),
                "pnl": float(pos.get("pnl", 0)),
                "day_pnl": float(pos.get("m2m", 0)),
                "synced_at": datetime.now(timezone.utc),
                "strategy_id": None,  # TODO: Infer from holdings or tags
                "raw_data": pos
            }
            records.append(record)

        await self.dm.upsert_positions(records)
        return len(records)

    async def _store_holdings(
        self,
        account_id: str,
        holdings_data: List[Dict[str, Any]]
    ) -> int:
        """Transform and store holdings in database"""
        # Holdings are delivery positions
        # Can store in positions table with product="CNC"
        if not holdings_data:
            return 0

        # Implementation similar to _store_positions
        return len(holdings_data)

    def _parse_timestamp(self, ts_str: Optional[str]) -> Optional[datetime]:
        """Parse Kite timestamp to datetime"""
        if not ts_str:
            return None
        # Kite format: "2025-11-07 09:15:30"
        try:
            return datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        except:
            return None

    def _extract_strategy_id(self, order_or_trade: Dict[str, Any]) -> Optional[str]:
        """Extract strategy_id from order tag"""
        tag = order_or_trade.get("tag", "")

        # Expected tag format: "strategy_123" or "strat:123"
        if not tag:
            return None

        # Parse tag
        if tag.startswith("strategy_"):
            return tag.replace("strategy_", "")
        elif ":" in tag:
            parts = tag.split(":")
            if len(parts) == 2:
                return parts[1]

        return None
```

---

## 4. Database Schema Enhancements

### 4.1 New Continuous Aggregates

```sql
-- Daily P&L by Strategy
CREATE MATERIALIZED VIEW daily_pnl_by_strategy
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 day', time) AS day,
    strategy_id,
    account_id,
    COUNT(*) AS trade_count,
    SUM(pnl) AS total_pnl,
    AVG(pnl) AS avg_pnl,
    STDDEV(pnl) AS pnl_volatility,
    SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) AS winning_trades,
    SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) AS losing_trades
FROM trades
WHERE strategy_id IS NOT NULL
GROUP BY 1, 2, 3;

-- Hourly Trade Volume
CREATE MATERIALIZED VIEW hourly_trade_volume
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', time) AS hour,
    account_id,
    symbol,
    side,
    COUNT(*) AS trade_count,
    SUM(quantity) AS total_quantity,
    SUM(quantity * price) AS total_value
FROM trades
GROUP BY 1, 2, 3, 4;

-- Account Performance Metrics
CREATE MATERIALIZED VIEW account_performance_metrics
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 day', time) AS day,
    account_id,
    COUNT(DISTINCT symbol) AS unique_symbols_traded,
    COUNT(*) AS total_trades,
    SUM(pnl) AS daily_pnl,
    AVG(pnl) AS avg_pnl_per_trade,
    MAX(pnl) AS max_win,
    MIN(pnl) AS max_loss,
    SUM(ABS(pnl)) AS total_pnl_abs
FROM trades
GROUP BY 1, 2;
```

### 4.2 Indexes for Performance

```sql
-- Trades table optimizations
CREATE INDEX idx_trades_strategy_time
ON trades(strategy_id, time DESC)
WHERE strategy_id IS NOT NULL;

CREATE INDEX idx_trades_symbol_time
ON trades(symbol, time DESC);

-- Orders table optimizations
CREATE INDEX idx_orders_strategy_status
ON orders(strategy_id, status)
WHERE strategy_id IS NOT NULL;

CREATE INDEX idx_orders_created_status
ON orders(created_at DESC, status);
```

---

## 5. API Enhancements

### 5.1 New Endpoints

```python
# Manual sync trigger
POST /sync/trades/{account_id}
POST /sync/orders/{account_id}
POST /sync/positions/{account_id}
POST /sync/all/{account_id}

# Sync status
GET /sync/status
GET /sync/history?account_id={id}&limit=10

# Strategy analytics
GET /analytics/strategy/{strategy_id}/pnl?from=2025-11-01&to=2025-11-07
GET /analytics/strategy/{strategy_id}/trades?limit=100

# Account performance
GET /analytics/account/{account_id}/performance?period=7d
GET /analytics/account/{account_id}/trade-distribution
```

---

## 6. Monitoring & Observability

### 6.1 Metrics (Prometheus)

```python
# Sync metrics
trade_sync_duration_seconds{account_id, status}
trade_sync_trades_count{account_id}
trade_sync_orders_count{account_id}
trade_sync_errors_total{account_id, error_type}

# Data quality metrics
trade_data_freshness_seconds{account_id}
trade_data_missing_strategy_id_total
trade_data_duplicate_count{table}
```

### 6.2 Logging

```python
# Structured logs
logger.info("Trade sync completed", extra={
    "account_id": "primary",
    "trades_synced": 15,
    "orders_synced": 8,
    "duration_ms": 2340,
    "success": True
})

# Error tracking
logger.error("Trade sync failed", extra={
    "account_id": "secondary",
    "error": "Authentication failed",
    "retry_count": 3
})
```

---

## 7. Implementation Plan

### Phase 1: Core Sync Service (Week 1)
- [ ] Implement `TradeSyncService` class
- [ ] Add database methods (`upsert_trades`, `upsert_orders`, etc.)
- [ ] Create background task scheduler
- [ ] Add manual sync endpoints
- [ ] Write unit tests

### Phase 2: Strategy Attribution (Week 2)
- [ ] Implement strategy_id extraction from tags
- [ ] Add symbol pattern matching
- [ ] Create strategy management UI
- [ ] Backfill existing trades with strategy_id

### Phase 3: Analytics & Dashboards (Week 3)
- [ ] Create continuous aggregates
- [ ] Build strategy P&L API
- [ ] Implement performance metrics
- [ ] Add frontend dashboards

### Phase 4: Production Deployment (Week 4)
- [ ] Load testing and optimization
- [ ] Monitoring and alerting setup
- [ ] Documentation and runbooks
- [ ] Production rollout

---

## 8. Testing Strategy

### 8.1 Unit Tests
- Test data transformation (Kite → DB schema)
- Test strategy_id extraction
- Test conflict resolution (upserts)
- Test error handling and retries

### 8.2 Integration Tests
- Test full sync workflow
- Test multi-account parallel sync
- Test database consistency
- Test API endpoints

### 8.3 Performance Tests
- Measure sync duration for 1000+ trades
- Test database write throughput
- Validate query performance on aggregates

---

## 9. Deployment Checklist

- [ ] Create database migrations
- [ ] Update environment variables
- [ ] Configure sync interval
- [ ] Set up monitoring dashboards
- [ ] Create runbook for troubleshooting
- [ ] Train team on new features
- [ ] Document API endpoints
- [ ] Perform dry-run on staging

---

## 10. Future Enhancements

1. **Real-Time WebSocket Sync** - Subscribe to Kite postback webhooks
2. **Trade Reconciliation** - Compare broker vs. local records
3. **Cost Basis Tracking** - FIFO/LIFO for tax reporting
4. **Trade Replay** - Step-through historical trades
5. **Strategy Backtesting** - Simulate strategies on historical data
6. **Risk Limits** - Real-time position monitoring and alerts
7. **Multi-Broker Support** - Extend to other brokers (Upstox, Angel One)

---

## Appendix A: Database Schema Reference

See existing schemas:
- `trades` - /mnt/stocksblitz-data/Quantagro/tradingview-viz/backend/migrations/
- `orders` - /mnt/stocksblitz-data/Quantagro/tradingview-viz/backend/migrations/
- `positions` - /mnt/stocksblitz-data/Quantagro/tradingview-viz/backend/migrations/

## Appendix B: API Reference

See:
- `/mnt/stocksblitz-data/Quantagro/tradingview-viz/backend/API_REFERENCE.md`
- `/mnt/stocksblitz-data/Quantagro/tradingview-viz/backend/KITECONNECT_BACKEND_IMPLEMENTATION.md`

---

**End of Design Document**
