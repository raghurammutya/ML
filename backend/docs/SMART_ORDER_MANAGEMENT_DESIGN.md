# Smart Order Management System - Design Document

**Created**: 2025-11-09
**Status**: Design Proposal
**Related**: Strategy System Enhancement

---

## Executive Summary

This document outlines a comprehensive smart order management system that includes:
1. **Automated housekeeping** for orphaned orders/positions
2. **Market depth-based smart execution** with spread analysis
3. **Pre-trade margin and cost calculation** (Kite-specific initially)
4. **Risk alerts and user notifications**
5. **Additional housekeeping tasks** for production-ready trading

---

## Table of Contents

1. [Order Housekeeping System](#1-order-housekeeping-system)
2. [Market Depth-Based Smart Execution](#2-market-depth-based-smart-execution)
3. [Margin & Brokerage Calculation](#3-margin--brokerage-calculation)
4. [Additional Housekeeping Tasks](#4-additional-housekeeping-tasks)
5. [Database Schema Changes](#5-database-schema-changes)
6. [API Design](#6-api-design)
7. [Implementation Roadmap](#7-implementation-roadmap)

---

## 1. Order Housekeeping System

### 1.1 Problem Statement

When positions are exited, associated SL (Stop Loss) and Target orders become orphaned and need cleanup:
- **Orphaned SL orders**: Position closed but SL order still active
- **Orphaned Target orders**: Position closed but Target order still active
- **Partially filled positions**: Orders need adjustment based on actual filled quantity
- **Expired options**: Orders for expired instruments still active

### 1.2 Proposed Solution: Automatic Order Reconciliation

```python
# Core housekeeping logic
class OrderHousekeeping:
    """
    Automatic order cleanup and reconciliation.

    Runs periodically (every 5 minutes) and on position change events.
    """

    async def reconcile_strategy_orders(self, strategy_id: int, user_override: bool = False):
        """
        Reconcile all orders for a strategy against current positions.

        Args:
            strategy_id: Strategy to reconcile
            user_override: If True, skip cleanup (user wants to keep orders)

        Actions:
            1. Fetch all active orders for strategy
            2. Fetch all current positions for strategy
            3. Identify orphaned orders (no matching position)
            4. Cancel or archive orphaned orders (unless user_override)
            5. Log all actions to strategy_events table
        """

    async def detect_orphaned_orders(self, strategy_id: int) -> List[OrphanedOrder]:
        """
        Detect orders that no longer have matching positions.

        Returns:
            List of OrphanedOrder objects with:
            - order_id
            - reason (POSITION_CLOSED, EXPIRED_INSTRUMENT, QUANTITY_MISMATCH)
            - recommended_action (CANCEL, REDUCE_QUANTITY, KEEP)
        """

    async def auto_cancel_orphaned_orders(self, orphaned_orders: List[OrphanedOrder]):
        """
        Automatically cancel orphaned orders.

        Workflow:
            1. Check user preference (auto_cleanup_enabled in strategy_settings)
            2. If enabled: Cancel orders via broker API
            3. If disabled: Create notification/alert for user
            4. Log action to order_events table
        """
```

### 1.3 Configuration Options

```python
# New table: strategy_settings
CREATE TABLE strategy_settings (
    strategy_id BIGINT PRIMARY KEY REFERENCES strategies(id),

    -- Housekeeping settings
    auto_cleanup_enabled BOOLEAN DEFAULT TRUE,
    cleanup_sl_on_exit BOOLEAN DEFAULT TRUE,
    cleanup_target_on_exit BOOLEAN DEFAULT TRUE,
    cleanup_expired_instruments BOOLEAN DEFAULT TRUE,

    -- Order management
    allow_orphaned_orders BOOLEAN DEFAULT FALSE,
    notify_on_orphan_detection BOOLEAN DEFAULT TRUE,

    -- Risk management
    max_order_spread_pct DECIMAL(10, 4) DEFAULT 0.5,  -- 0.5% max spread
    min_liquidity_score INTEGER DEFAULT 50,  -- 0-100 scale
    require_user_approval_high_impact BOOLEAN DEFAULT TRUE,

    -- Margin management
    margin_buffer_pct DECIMAL(10, 4) DEFAULT 10.0,  -- 10% safety buffer
    check_margin_before_order BOOLEAN DEFAULT TRUE,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

### 1.4 Housekeeping Triggers

```python
# Event-driven housekeeping
HOUSEKEEPING_TRIGGERS = {
    "POSITION_CLOSED": reconcile_strategy_orders,
    "POSITION_FULLY_EXITED": auto_cancel_associated_orders,
    "ORDER_FILLED": update_related_orders,
    "ORDER_REJECTED": notify_and_log,
    "INSTRUMENT_EXPIRED": cancel_expired_instrument_orders,
    "END_OF_DAY": reconcile_all_strategies,
    "MANUAL_TRIGGER": user_initiated_cleanup
}
```

---

## 2. Market Depth-Based Smart Execution

### 2.1 Problem Statement

- **Wide spreads**: High bid-ask spreads lead to significant slippage
- **Illiquid instruments**: Limited depth causes market impact
- **User needs guidance**: Should we proceed with wide spread or alert user?

### 2.2 Proposed Solution: Smart Order Execution Engine

```python
class SmartOrderExecutor:
    """
    Intelligent order execution using market depth analysis.
    """

    async def validate_order_execution(
        self,
        instrument_token: int,
        order_side: str,  # BUY or SELL
        quantity: int,
        order_type: str,  # MARKET, LIMIT, SL
        limit_price: Optional[Decimal] = None
    ) -> OrderExecutionPlan:
        """
        Analyze market depth and create execution plan.

        Returns:
            OrderExecutionPlan with:
            - is_executable: bool
            - warnings: List[str]
            - estimated_slippage: Decimal
            - estimated_cost: Decimal
            - recommended_action: EXECUTE | ALERT_USER | REJECT
            - alternative_strategies: List[str]
        """

        # 1. Fetch current market depth
        depth = await self.get_market_depth(instrument_token)

        # 2. Analyze spread
        spread_analysis = self.analyze_spread(depth)

        # 3. Calculate market impact
        impact = self.calculate_market_impact(depth, order_side, quantity)

        # 4. Determine execution strategy
        return self.create_execution_plan(spread_analysis, impact, order_type)
```

### 2.3 Spread Analysis Logic

```python
@dataclass
class SpreadAnalysis:
    bid_ask_spread_abs: Decimal
    bid_ask_spread_pct: Decimal
    is_wide_spread: bool  # > 0.5% for options, > 0.05% for futures
    liquidity_tier: str  # HIGH, MEDIUM, LOW, ILLIQUID
    recommended_order_type: str  # MARKET, LIMIT, ICEBERG

class SpreadAnalyzer:
    # Spread thresholds (configurable per instrument type)
    SPREAD_THRESHOLDS = {
        "options": {
            "tight": 0.2,      # < 0.2% = tight spread
            "normal": 0.5,     # < 0.5% = normal spread
            "wide": 1.0,       # < 1.0% = wide spread
            "very_wide": 2.0   # >= 2.0% = very wide spread
        },
        "futures": {
            "tight": 0.02,
            "normal": 0.05,
            "wide": 0.1,
            "very_wide": 0.2
        }
    }

    def analyze_spread(self, depth: dict, instrument_type: str) -> SpreadAnalysis:
        """
        Analyze bid-ask spread and determine if order should proceed.

        Logic:
            - Tight/Normal: Execute immediately (MARKET order OK)
            - Wide: Use LIMIT order at mid-price or slightly better
            - Very Wide: Alert user, suggest LIMIT order or wait
        """
        best_bid = depth['buy'][0]['price']
        best_ask = depth['sell'][0]['price']
        mid_price = (best_bid + best_ask) / 2

        spread_abs = best_ask - best_bid
        spread_pct = (spread_abs / mid_price) * 100

        thresholds = self.SPREAD_THRESHOLDS[instrument_type]

        if spread_pct < thresholds['tight']:
            return SpreadAnalysis(
                spread_abs, spread_pct, False, "HIGH",
                recommended_order_type="MARKET"
            )
        elif spread_pct < thresholds['normal']:
            return SpreadAnalysis(
                spread_abs, spread_pct, False, "MEDIUM",
                recommended_order_type="LIMIT"
            )
        elif spread_pct < thresholds['wide']:
            return SpreadAnalysis(
                spread_abs, spread_pct, True, "LOW",
                recommended_order_type="LIMIT"
            )
        else:  # Very wide spread
            return SpreadAnalysis(
                spread_abs, spread_pct, True, "ILLIQUID",
                recommended_order_type="LIMIT_WITH_ALERT"
            )
```

### 2.4 Market Impact Calculation

```python
class MarketImpactCalculator:
    """
    Calculate estimated market impact for order execution.
    """

    def calculate_impact(
        self,
        depth: dict,
        side: str,
        quantity: int
    ) -> MarketImpact:
        """
        Calculate how much price will move when executing order.

        Algorithm:
            1. Walk through order book levels
            2. Sum quantity until order is filled
            3. Calculate weighted average fill price
            4. Compare to mid-price to get impact

        Returns:
            MarketImpact with:
            - estimated_fill_price: Decimal
            - impact_bps: int (basis points)
            - impact_cost: Decimal (absolute cost)
            - can_fill_completely: bool
            - levels_consumed: int
        """

        book_side = depth['sell'] if side == 'BUY' else depth['buy']
        remaining_qty = quantity
        total_cost = Decimal('0')
        levels_consumed = 0

        for level in book_side:
            if remaining_qty <= 0:
                break

            level_qty = level['quantity']
            level_price = Decimal(str(level['price']))

            fill_qty = min(remaining_qty, level_qty)
            total_cost += fill_qty * level_price
            remaining_qty -= fill_qty
            levels_consumed += 1

        if remaining_qty > 0:
            # Order cannot be filled completely
            return MarketImpact(
                estimated_fill_price=None,
                impact_bps=9999,  # Indicates partial fill
                impact_cost=None,
                can_fill_completely=False,
                levels_consumed=levels_consumed,
                warning="INSUFFICIENT_LIQUIDITY"
            )

        avg_fill_price = total_cost / quantity
        mid_price = (depth['buy'][0]['price'] + depth['sell'][0]['price']) / 2
        impact_pct = abs((avg_fill_price - mid_price) / mid_price) * 100
        impact_bps = int(impact_pct * 100)

        return MarketImpact(
            estimated_fill_price=avg_fill_price,
            impact_bps=impact_bps,
            impact_cost=abs(avg_fill_price - mid_price) * quantity,
            can_fill_completely=True,
            levels_consumed=levels_consumed
        )
```

### 2.5 Execution Decision Matrix

```python
# Decision matrix for order execution
EXECUTION_RULES = {
    # (spread_category, impact_bps, liquidity_tier) -> action

    # Tight spread, low impact -> Execute
    ("tight", 0-10, "HIGH"): "EXECUTE_MARKET",
    ("tight", 0-10, "MEDIUM"): "EXECUTE_MARKET",

    # Normal spread, moderate impact -> Execute with limit
    ("normal", 10-50, "MEDIUM"): "EXECUTE_LIMIT",
    ("normal", 10-50, "LOW"): "EXECUTE_LIMIT_ALERT",

    # Wide spread -> Alert user
    ("wide", ">50", "LOW"): "ALERT_USER_HIGH_COST",
    ("wide", ">50", "ILLIQUID"): "REJECT_SUGGEST_ALTERNATIVES",

    # Very wide spread -> Require user approval
    ("very_wide", "*", "*"): "REQUIRE_USER_APPROVAL",

    # Insufficient liquidity -> Suggest alternative
    ("*", "*", "ILLIQUID"): "SUGGEST_ICEBERG_OR_TWAP"
}
```

### 2.6 User Alerts and Notifications

```python
class OrderExecutionAlert:
    """Alert types for order execution."""

    WARNING_TYPES = {
        "WIDE_SPREAD": {
            "title": "Wide Bid-Ask Spread Detected",
            "message": "Spread is {spread_pct}% ({spread_abs}). Estimated slippage: ₹{slippage}",
            "severity": "warning",
            "actions": ["PROCEED_MARKET", "USE_LIMIT_ORDER", "CANCEL"]
        },

        "HIGH_IMPACT": {
            "title": "High Market Impact",
            "message": "Order will consume {levels} price levels. Impact: {impact_bps} bps (₹{impact_cost})",
            "severity": "warning",
            "actions": ["PROCEED", "SPLIT_ORDER", "CANCEL"]
        },

        "ILLIQUID_INSTRUMENT": {
            "title": "Low Liquidity Warning",
            "message": "Instrument has low liquidity (tier: {tier}). Cannot fill {unfilled_qty} lots.",
            "severity": "error",
            "actions": ["USE_LIMIT_ORDER", "REDUCE_QUANTITY", "CANCEL"]
        },

        "POTENTIAL_LOSS": {
            "title": "Potential Monetary Loss Alert",
            "message": "Estimated total cost: ₹{total_cost} (impact: ₹{impact_cost}). Proceed?",
            "severity": "critical",
            "actions": ["APPROVE", "CANCEL"]
        }
    }
```

---

## 3. Margin & Brokerage Calculation

### 3.1 Problem Statement

Users need upfront visibility into:
- **Margin required** before entering a strategy
- **Brokerage charges** (per order, per lot)
- **Taxes**: GST (CGST + SGST), STT, stamp duty
- **Total cost** to enter and exit a position

### 3.2 Proposed Solution: Pre-Trade Cost Calculator

```python
class KiteMarginCalculator:
    """
    Calculate margin and costs for Zerodha Kite orders.

    Uses Kite's margin API and brokerage schedule.
    """

    # Zerodha brokerage rates (as of 2024)
    BROKERAGE_RATES = {
        "equity_delivery": {
            "brokerage_pct": 0,  # Free
        },
        "equity_intraday": {
            "brokerage_pct": 0.03,  # 0.03% or ₹20, whichever is lower
            "max_per_order": 20
        },
        "futures": {
            "brokerage_pct": 0.03,  # 0.03% or ₹20, whichever is lower
            "max_per_order": 20
        },
        "options": {
            "brokerage_flat": 20,  # Flat ₹20 per order
        }
    }

    # Tax rates (as per Indian regulations)
    TAX_RATES = {
        "stt_equity_delivery_buy": 0.0,      # No STT on buy
        "stt_equity_delivery_sell": 0.1,     # 0.1% on sell
        "stt_equity_intraday": 0.025,        # 0.025% on sell
        "stt_futures": 0.0125,                # 0.0125% on sell
        "stt_options_buy": 0.0,               # No STT on buy
        "stt_options_sell": 0.05,             # 0.05% on premium (sell)

        "exchange_charges_nse": 0.00325,     # 0.00325% (NSE)
        "exchange_charges_nfo": 0.005,       # 0.005% (NFO)

        "gst": 0.18,                          # 18% on brokerage + transaction charges

        "sebi_charges": 0.0001,               # ₹10 per crore
        "stamp_duty": 0.002,                  # 0.002% on buy side (equity)
        "stamp_duty_fo": 0.002,               # 0.002% on buy side (F&O)
    }

    async def calculate_margin_required(
        self,
        orders: List[OrderRequest]
    ) -> MarginBreakdown:
        """
        Calculate total margin required for a basket of orders.

        Uses Kite's margin calculator API:
        POST https://api.kite.trade/margins/orders

        Returns:
            MarginBreakdown with:
            - total_margin: Decimal
            - span_margin: Decimal
            - exposure_margin: Decimal
            - premium_margin: Decimal (for options writing)
            - additional_margin: Decimal
            - available_margin: Decimal
            - margin_shortfall: Decimal (if any)
            - can_place_order: bool
        """

        # Call Kite margin API
        response = await self.kite_client.post(
            "/margins/orders",
            json=[order.to_kite_format() for order in orders]
        )

        total_margin = Decimal(str(response['total']))
        available = await self.get_available_margin()

        return MarginBreakdown(
            total_margin=total_margin,
            span_margin=Decimal(str(response['span'])),
            exposure_margin=Decimal(str(response['exposure'])),
            premium_margin=Decimal(str(response.get('premium', 0))),
            additional_margin=Decimal(str(response.get('additional', 0))),
            available_margin=available,
            margin_shortfall=max(Decimal('0'), total_margin - available),
            can_place_order=total_margin <= available
        )

    def calculate_order_costs(
        self,
        order: OrderRequest,
        segment: str  # "equity", "futures", "options"
    ) -> OrderCostBreakdown:
        """
        Calculate complete cost breakdown for a single order.

        Returns:
            OrderCostBreakdown with:
            - order_value: Decimal
            - brokerage: Decimal
            - stt: Decimal
            - exchange_charges: Decimal
            - gst: Decimal
            - sebi_charges: Decimal
            - stamp_duty: Decimal
            - total_charges: Decimal
            - net_cost: Decimal (order_value + total_charges for buy)
        """

        order_value = order.quantity * order.price

        # 1. Brokerage
        brokerage = self._calculate_brokerage(order, segment)

        # 2. STT
        stt = self._calculate_stt(order, segment)

        # 3. Exchange charges
        exchange_charges = self._calculate_exchange_charges(order, segment)

        # 4. GST (18% on brokerage + exchange charges)
        gst_base = brokerage + exchange_charges
        gst = gst_base * Decimal(str(self.TAX_RATES['gst']))

        # 5. SEBI charges (₹10 per crore)
        sebi_charges = order_value * Decimal(str(self.TAX_RATES['sebi_charges']))

        # 6. Stamp duty (on buy side only)
        stamp_duty = Decimal('0')
        if order.side == 'BUY':
            rate = self.TAX_RATES['stamp_duty_fo'] if segment in ['futures', 'options'] else self.TAX_RATES['stamp_duty']
            stamp_duty = order_value * Decimal(str(rate))

        total_charges = brokerage + stt + exchange_charges + gst + sebi_charges + stamp_duty

        return OrderCostBreakdown(
            order_value=order_value,
            brokerage=brokerage,
            stt=stt,
            exchange_charges=exchange_charges,
            gst=gst,
            sebi_charges=sebi_charges,
            stamp_duty=stamp_duty,
            total_charges=total_charges,
            net_cost=order_value + total_charges if order.side == 'BUY' else order_value - total_charges
        )

    def _calculate_brokerage(self, order: OrderRequest, segment: str) -> Decimal:
        """Calculate brokerage based on segment."""
        if segment == "options":
            return Decimal(str(self.BROKERAGE_RATES['options']['brokerage_flat']))

        # For equity/futures: 0.03% or ₹20, whichever is lower
        order_value = order.quantity * order.price
        pct_brokerage = order_value * Decimal(str(self.BROKERAGE_RATES[segment]['brokerage_pct'])) / 100

        return min(pct_brokerage, Decimal(str(self.BROKERAGE_RATES[segment]['max_per_order'])))

    def _calculate_stt(self, order: OrderRequest, segment: str) -> Decimal:
        """Calculate STT based on segment and side."""
        if segment == "options":
            if order.side == 'SELL':
                # 0.05% on premium for sell
                return order.quantity * order.price * Decimal(str(self.TAX_RATES['stt_options_sell']))
            return Decimal('0')

        if segment == "futures":
            if order.side == 'SELL':
                return order.quantity * order.price * Decimal(str(self.TAX_RATES['stt_futures']))
            return Decimal('0')

        # Equity
        if order.side == 'SELL':
            rate = self.TAX_RATES['stt_equity_delivery_sell']  # or intraday based on product type
            return order.quantity * order.price * Decimal(str(rate))

        return Decimal('0')
```

### 3.3 Strategy-Level Cost Calculator

```python
class StrategyMarginCalculator:
    """
    Calculate total margin and costs for an entire strategy.
    """

    async def calculate_strategy_costs(
        self,
        strategy_id: int,
        new_instruments: List[InstrumentRequest] = []
    ) -> StrategyCostSummary:
        """
        Calculate complete cost breakdown for strategy.

        Includes:
        - Existing positions/orders
        - New instruments to be added
        - Entry costs
        - Exit costs (estimated)
        - Total margin required
        - Available vs required comparison

        Returns:
            StrategyCostSummary with:
            - total_entry_cost: Decimal
            - total_exit_cost: Decimal (estimated)
            - total_brokerage: Decimal
            - total_taxes: Decimal
            - net_margin_required: Decimal
            - available_margin: Decimal
            - can_execute: bool
            - warnings: List[str]
        """

        # Get existing instruments in strategy
        existing = await self.get_strategy_instruments(strategy_id)

        # Combine existing + new
        all_instruments = existing + new_instruments

        # Convert to order requests
        entry_orders = self._convert_to_orders(all_instruments, "ENTRY")
        exit_orders = self._convert_to_orders(all_instruments, "EXIT")

        # Calculate margin
        margin = await self.margin_calculator.calculate_margin_required(entry_orders)

        # Calculate costs
        entry_costs = sum([
            self.margin_calculator.calculate_order_costs(order, order.segment)
            for order in entry_orders
        ])

        exit_costs = sum([
            self.margin_calculator.calculate_order_costs(order, order.segment)
            for order in exit_orders
        ])

        total_brokerage = entry_costs.brokerage + exit_costs.brokerage
        total_taxes = (entry_costs.total_charges - entry_costs.brokerage) + \
                      (exit_costs.total_charges - exit_costs.brokerage)

        return StrategyCostSummary(
            total_entry_cost=entry_costs.net_cost,
            total_exit_cost=exit_costs.net_cost,
            total_brokerage=total_brokerage,
            total_taxes=total_taxes,
            net_margin_required=margin.total_margin,
            available_margin=margin.available_margin,
            can_execute=margin.can_place_order,
            warnings=self._generate_warnings(margin, entry_costs)
        )
```

### 3.4 Pre-Trade Confirmation UI

```python
# API endpoint for pre-trade cost display
@router.post("/strategies/{strategy_id}/calculate-costs")
async def calculate_strategy_costs(
    strategy_id: int,
    instruments: List[AddInstrumentRequest],
    pool = Depends(get_db_pool)
) -> StrategyCostSummary:
    """
    Calculate and return complete cost breakdown before adding instruments.

    Frontend displays:
    ┌─────────────────────────────────────────────┐
    │  Strategy Cost Breakdown                    │
    ├─────────────────────────────────────────────┤
    │  Entry Cost:          ₹ 1,25,000            │
    │  Exit Cost (est):     ₹ 1,24,500            │
    │                                             │
    │  Breakdown:                                 │
    │    Order Value:       ₹ 1,23,450            │
    │    Brokerage:         ₹     120             │
    │    STT:               ₹     280             │
    │    Exchange Charges:  ₹      40             │
    │    GST:               ₹      29             │
    │    SEBI Charges:      ₹       1             │
    │    Stamp Duty:        ₹      25             │
    │  ─────────────────────────────              │
    │    Total Charges:     ₹     495             │
    │                                             │
    │  Margin Required:     ₹  45,000             │
    │  Available Margin:    ₹  60,000             │
    │  ─────────────────────────────              │
    │  Remaining Margin:    ₹  15,000 ✅          │
    │                                             │
    │  [ Cancel ]  [ Proceed with Orders ]        │
    └─────────────────────────────────────────────┘
    """
    calculator = StrategyMarginCalculator()
    return await calculator.calculate_strategy_costs(strategy_id, instruments)
```

---

## 4. Additional Housekeeping Tasks

### 4.1 End-of-Day Reconciliation

```python
class EODReconciliation:
    """End-of-day housekeeping tasks."""

    async def run_eod_tasks(self):
        """
        Run at market close (3:30 PM IST).

        Tasks:
        1. Reconcile all positions with broker
        2. Match orders with broker order book
        3. Update realized P&L for closed positions
        4. Archive filled/cancelled orders
        5. Check for discrepancies
        6. Generate EOD reports
        7. Reset intraday counters
        """

        await self.reconcile_positions_with_broker()
        await self.match_orders_with_broker()
        await self.calculate_realized_pnl()
        await self.archive_completed_orders()
        await self.check_discrepancies()
        await self.generate_eod_reports()
        await self.reset_intraday_metrics()
```

### 4.2 Position Squaring-Off (Intraday)

```python
class IntradaySquareOff:
    """Auto square-off for MIS/NRML positions."""

    async def auto_square_off_mis_positions(self):
        """
        Auto square-off MIS positions before market close.

        Timing:
        - 3:15 PM: Send warning notification
        - 3:20 PM: Start auto square-off
        - 3:25 PM: Force square-off remaining positions

        Actions:
        1. Fetch all open MIS positions
        2. Calculate exit orders
        3. Place market orders
        4. Monitor fills
        5. Retry failed orders
        6. Log all actions
        """
```

### 4.3 Expired Instrument Cleanup

```python
class ExpiredInstrumentCleanup:
    """Cleanup orders/positions for expired instruments."""

    async def cleanup_expired_instruments(self):
        """
        Run daily at 9:00 AM.

        Tasks:
        1. Identify instruments expiring today
        2. Cancel all pending orders for expired instruments
        3. Archive expired positions (options expired worthless)
        4. Update strategy P&L
        5. Notify users of expired instruments
        """

        expired_today = await self.get_instruments_expiring_today()

        for instrument in expired_today:
            await self.cancel_orders_for_instrument(instrument)
            await self.archive_expired_positions(instrument)
            await self.update_strategy_pnl(instrument)
            await self.notify_user(instrument)
```

### 4.4 Order Aging and Timeout

```python
class OrderTimeoutManager:
    """Manage stale and aging orders."""

    async def check_aging_orders(self):
        """
        Run every 15 minutes.

        Logic:
        - Open orders > 1 hour: Send notification
        - Open orders > 4 hours: Cancel automatically (if configured)
        - Pending orders > 1 day: Archive
        """

        aging_orders = await self.get_aging_orders(threshold_minutes=60)

        for order in aging_orders:
            if order.age_minutes > 240:  # 4 hours
                if order.strategy_settings.auto_cancel_stale_orders:
                    await self.cancel_order(order.id)
            else:
                await self.notify_user_stale_order(order)
```

### 4.5 Strategy P&L Snapshot

```python
class StrategySnapshotManager:
    """Periodic snapshots of strategy state."""

    async def capture_strategy_snapshot(self, strategy_id: int):
        """
        Capture point-in-time snapshot.

        Frequency: Every 5 minutes during market hours

        Snapshot includes:
        - Current positions
        - Open orders
        - Realized P&L
        - Unrealized P&L
        - Margin used
        - Greeks (if F&O strategy)
        - Timestamp

        Used for:
        - M2M chart generation
        - Performance analytics
        - Audit trail
        """
```

### 4.6 Risk Limit Monitoring

```python
class RiskLimitMonitor:
    """Monitor and enforce risk limits."""

    RISK_LIMITS = {
        "max_loss_per_strategy_pct": 10,  # 10% loss -> auto square-off
        "max_loss_per_strategy_abs": 50000,  # ₹50,000 loss
        "max_position_size_per_instrument": 1000,  # Max 1000 lots
        "max_orders_per_minute": 10,  # Rate limiting
        "max_margin_utilization_pct": 90,  # 90% margin usage
    }

    async def check_risk_limits(self, strategy_id: int):
        """
        Check if strategy has breached any risk limits.

        Actions on breach:
        1. Stop new orders
        2. Send alert to user
        3. Auto square-off (if configured)
        4. Log event
        """
```

### 4.7 Broker API Health Check

```python
class BrokerHealthMonitor:
    """Monitor broker API connectivity and health."""

    async def check_broker_health(self):
        """
        Run every 1 minute.

        Checks:
        1. API reachability
        2. Token validity
        3. Rate limit status
        4. WebSocket connection
        5. Order placement latency

        Actions on failure:
        1. Retry connection
        2. Refresh tokens
        3. Pause order placement
        4. Alert user
        """
```

### 4.8 Data Reconciliation

```python
class DataReconciliationService:
    """Reconcile internal data with broker."""

    async def reconcile_positions(self):
        """
        Compare our position records with broker's position book.

        Discrepancies to detect:
        - Quantity mismatch
        - Missing positions
        - Phantom positions (we have, broker doesn't)
        - Average price discrepancy

        Actions:
        1. Log discrepancies
        2. Attempt auto-fix (if safe)
        3. Alert user for manual review
        """

    async def reconcile_orders(self):
        """
        Match our order records with broker's order book.

        Check:
        - Order status sync
        - Fill price accuracy
        - Timestamp alignment
        """
```

### 4.9 Audit Trail Generation

```python
class AuditTrailGenerator:
    """Generate comprehensive audit trails."""

    async def log_order_event(
        self,
        order_id: int,
        event_type: str,
        details: dict,
        user_id: Optional[str] = None
    ):
        """
        Log every order lifecycle event.

        Events:
        - ORDER_CREATED
        - ORDER_PLACED
        - ORDER_MODIFIED
        - ORDER_CANCELLED
        - ORDER_FILLED
        - ORDER_REJECTED
        - ORDER_EXPIRED

        Table: order_events
        Retention: 7 years (compliance)
        """
```

### 4.10 Performance Metrics Calculation

```python
class PerformanceMetricsCalculator:
    """Calculate strategy performance metrics."""

    async def calculate_daily_metrics(self, strategy_id: int):
        """
        Run at EOD.

        Metrics:
        - Daily P&L
        - Cumulative P&L
        - Win rate
        - Sharpe ratio
        - Max drawdown
        - ROI
        - Total trades
        - Winning/Losing trades

        Store in: strategy_performance_daily
        """
```

---

## 5. Database Schema Changes

### 5.1 New Tables

```sql
-- Strategy settings for housekeeping and risk management
CREATE TABLE strategy_settings (
    strategy_id BIGINT PRIMARY KEY REFERENCES strategies(id),

    -- Housekeeping
    auto_cleanup_enabled BOOLEAN DEFAULT TRUE,
    cleanup_sl_on_exit BOOLEAN DEFAULT TRUE,
    cleanup_target_on_exit BOOLEAN DEFAULT TRUE,
    cleanup_expired_instruments BOOLEAN DEFAULT TRUE,
    allow_orphaned_orders BOOLEAN DEFAULT FALSE,
    notify_on_orphan_detection BOOLEAN DEFAULT TRUE,
    auto_cancel_stale_orders BOOLEAN DEFAULT FALSE,
    stale_order_threshold_hours INTEGER DEFAULT 4,

    -- Smart execution
    max_order_spread_pct DECIMAL(10, 4) DEFAULT 0.5,
    min_liquidity_score INTEGER DEFAULT 50,
    require_user_approval_high_impact BOOLEAN DEFAULT TRUE,
    max_market_impact_bps INTEGER DEFAULT 50,

    -- Margin management
    margin_buffer_pct DECIMAL(10, 4) DEFAULT 10.0,
    check_margin_before_order BOOLEAN DEFAULT TRUE,

    -- Risk limits
    max_loss_per_strategy_pct DECIMAL(10, 4) DEFAULT 10.0,
    max_loss_per_strategy_abs DECIMAL(20, 2),
    max_position_size_per_instrument INTEGER,
    max_orders_per_minute INTEGER DEFAULT 10,
    max_margin_utilization_pct DECIMAL(10, 4) DEFAULT 90.0,
    auto_square_off_on_loss_limit BOOLEAN DEFAULT FALSE,

    -- Intraday
    is_intraday_strategy BOOLEAN DEFAULT FALSE,
    auto_square_off_time TIME DEFAULT '15:20:00',
    send_square_off_warning BOOLEAN DEFAULT TRUE,
    square_off_warning_time TIME DEFAULT '15:15:00',

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Order execution analysis
CREATE TABLE order_execution_analysis (
    id BIGSERIAL PRIMARY KEY,
    order_id BIGINT REFERENCES orders(id),
    strategy_id BIGINT REFERENCES strategies(id),

    -- Pre-execution analysis
    analyzed_at TIMESTAMPTZ DEFAULT NOW(),
    bid_ask_spread_abs DECIMAL(20, 8),
    bid_ask_spread_pct DECIMAL(10, 4),
    liquidity_tier VARCHAR(20),  -- HIGH, MEDIUM, LOW, ILLIQUID
    liquidity_score INTEGER,

    -- Market impact
    estimated_fill_price DECIMAL(20, 8),
    market_impact_bps INTEGER,
    market_impact_cost DECIMAL(20, 2),
    levels_to_consume INTEGER,
    can_fill_completely BOOLEAN,

    -- Execution decision
    recommended_action VARCHAR(50),  -- EXECUTE, ALERT_USER, REJECT
    recommended_order_type VARCHAR(20),  -- MARKET, LIMIT, ICEBERG
    warnings JSONB,

    -- Actual execution (filled later)
    actual_fill_price DECIMAL(20, 8),
    actual_slippage DECIMAL(20, 8),
    execution_quality_score INTEGER,  -- 0-100

    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_order_exec_analysis_order_id ON order_execution_analysis(order_id);
CREATE INDEX idx_order_exec_analysis_strategy_id ON order_execution_analysis(strategy_id);

-- Margin and cost calculations
CREATE TABLE order_cost_breakdown (
    id BIGSERIAL PRIMARY KEY,
    order_id BIGINT REFERENCES orders(id),
    strategy_id BIGINT REFERENCES strategies(id),

    -- Order details
    order_value DECIMAL(20, 2),
    quantity INTEGER,
    price DECIMAL(20, 8),
    side VARCHAR(10),  -- BUY, SELL
    segment VARCHAR(20),  -- equity, futures, options

    -- Cost breakdown
    brokerage DECIMAL(20, 2),
    stt DECIMAL(20, 2),
    exchange_charges DECIMAL(20, 2),
    gst DECIMAL(20, 2),
    sebi_charges DECIMAL(20, 2),
    stamp_duty DECIMAL(20, 2),
    total_charges DECIMAL(20, 2),
    net_cost DECIMAL(20, 2),

    -- Margin (if applicable)
    margin_required DECIMAL(20, 2),
    span_margin DECIMAL(20, 2),
    exposure_margin DECIMAL(20, 2),
    premium_margin DECIMAL(20, 2),

    calculated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_order_cost_order_id ON order_cost_breakdown(order_id);
CREATE INDEX idx_order_cost_strategy_id ON order_cost_breakdown(strategy_id);

-- Housekeeping event log
CREATE TABLE housekeeping_events (
    id BIGSERIAL PRIMARY KEY,
    event_type VARCHAR(50) NOT NULL,  -- ORDER_CLEANUP, POSITION_RECONCILIATION, EOD_TASKS
    strategy_id BIGINT REFERENCES strategies(id),
    order_id BIGINT REFERENCES orders(id),

    event_details JSONB,
    action_taken VARCHAR(100),
    status VARCHAR(20),  -- SUCCESS, FAILED, PARTIAL
    error_message TEXT,

    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_housekeeping_events_type ON housekeeping_events(event_type);
CREATE INDEX idx_housekeeping_events_strategy ON housekeeping_events(strategy_id);
CREATE INDEX idx_housekeeping_events_created_at ON housekeeping_events(created_at);

-- User alerts and notifications
CREATE TABLE user_alerts (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id),
    strategy_id BIGINT REFERENCES strategies(id),
    order_id BIGINT REFERENCES orders(id),

    alert_type VARCHAR(50) NOT NULL,  -- WIDE_SPREAD, HIGH_IMPACT, MARGIN_SHORTFALL
    severity VARCHAR(20) DEFAULT 'info',  -- info, warning, error, critical
    title VARCHAR(200),
    message TEXT,

    -- Alert data
    alert_data JSONB,

    -- User actions available
    available_actions JSONB,  -- ["PROCEED", "CANCEL", "MODIFY"]

    -- User response
    is_read BOOLEAN DEFAULT FALSE,
    user_action VARCHAR(50),  -- Action taken by user
    responded_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ
);
CREATE INDEX idx_user_alerts_user_id ON user_alerts(user_id);
CREATE INDEX idx_user_alerts_strategy_id ON user_alerts(strategy_id);
CREATE INDEX idx_user_alerts_is_read ON user_alerts(is_read);
CREATE INDEX idx_user_alerts_created_at ON user_alerts(created_at);
```

### 5.2 Schema Modifications

```sql
-- Add columns to existing orders table
ALTER TABLE orders ADD COLUMN IF NOT EXISTS
    pre_execution_analysis_id BIGINT REFERENCES order_execution_analysis(id);

ALTER TABLE orders ADD COLUMN IF NOT EXISTS
    cost_breakdown_id BIGINT REFERENCES order_cost_breakdown(id);

ALTER TABLE orders ADD COLUMN IF NOT EXISTS
    is_orphaned BOOLEAN DEFAULT FALSE;

ALTER TABLE orders ADD COLUMN IF NOT EXISTS
    orphaned_reason VARCHAR(100);

ALTER TABLE orders ADD COLUMN IF NOT EXISTS
    parent_position_id BIGINT REFERENCES positions(id);

-- Add columns to strategies table
ALTER TABLE strategies ADD COLUMN IF NOT EXISTS
    total_brokerage_paid DECIMAL(20, 2) DEFAULT 0;

ALTER TABLE strategies ADD COLUMN IF NOT EXISTS
    total_taxes_paid DECIMAL(20, 2) DEFAULT 0;

ALTER TABLE strategies ADD COLUMN IF NOT EXISTS
    total_margin_blocked DECIMAL(20, 2) DEFAULT 0;

ALTER TABLE strategies ADD COLUMN IF NOT EXISTS
    risk_status VARCHAR(20) DEFAULT 'normal';  -- normal, warning, critical

ALTER TABLE strategies ADD COLUMN IF NOT EXISTS
    last_housekeeping_run TIMESTAMPTZ;
```

---

## 6. API Design

### 6.1 Order Management Endpoints

```python
# Housekeeping
POST   /strategies/{id}/reconcile-orders
POST   /strategies/{id}/cleanup-orphaned-orders
GET    /strategies/{id}/orphaned-orders
PUT    /strategies/{id}/settings  # Update strategy settings

# Smart execution
POST   /orders/analyze-execution  # Pre-execution analysis
POST   /orders/validate-spread    # Check spread before placing order
POST   /orders/estimate-impact    # Estimate market impact

# Margin calculation
POST   /strategies/{id}/calculate-margin  # Calculate margin for basket
POST   /orders/calculate-costs            # Calculate costs for single order
GET    /accounts/{id}/available-margin    # Get available margin

# Alerts
GET    /users/{id}/alerts                 # Get user alerts
POST   /alerts/{id}/respond                # Respond to alert
PUT    /alerts/{id}/mark-read             # Mark alert as read

# Housekeeping tasks
POST   /admin/housekeeping/eod            # Trigger EOD tasks
POST   /admin/housekeeping/reconcile-all  # Reconcile all strategies
GET    /admin/housekeeping/logs           # Get housekeeping logs
```

### 6.2 WebSocket Events

```python
# Real-time alerts to frontend
WS_EVENTS = {
    "ORDER_ALERT": {
        "type": "order_alert",
        "alert_type": "WIDE_SPREAD",
        "order_id": 12345,
        "data": {...},
        "actions": ["PROCEED", "CANCEL"]
    },

    "MARGIN_WARNING": {
        "type": "margin_warning",
        "strategy_id": 100,
        "available": 15000,
        "required": 18000,
        "shortfall": 3000
    },

    "ORPHANED_ORDER_DETECTED": {
        "type": "orphaned_order",
        "order_id": 12346,
        "reason": "POSITION_CLOSED",
        "recommended_action": "CANCEL"
    },

    "RISK_LIMIT_BREACH": {
        "type": "risk_breach",
        "strategy_id": 100,
        "limit_type": "MAX_LOSS_PCT",
        "current_loss_pct": 12.5,
        "limit": 10.0,
        "action_taken": "STOP_NEW_ORDERS"
    }
}
```

---

## 7. Implementation Roadmap

### Phase 1: Foundation (Week 1-2)
- [ ] Create database schema (new tables + migrations)
- [ ] Implement `strategy_settings` table and CRUD APIs
- [ ] Implement basic housekeeping event logging
- [ ] Create base classes: `OrderHousekeeping`, `SmartOrderExecutor`

### Phase 2: Order Housekeeping (Week 3-4)
- [ ] Implement orphaned order detection logic
- [ ] Implement auto-cleanup with user override
- [ ] Create housekeeping triggers (position_closed, order_filled, etc.)
- [ ] Implement EOD reconciliation
- [ ] Add expired instrument cleanup

### Phase 3: Smart Execution (Week 5-6)
- [ ] Integrate market depth analyzer with order execution
- [ ] Implement spread analysis and decision matrix
- [ ] Implement market impact calculator
- [ ] Create user alert system (DB + WebSocket)
- [ ] Build execution validation API

### Phase 4: Margin & Cost Calculation (Week 7-8)
- [ ] Integrate Kite margin API
- [ ] Implement brokerage calculator
- [ ] Implement tax calculator (STT, GST, stamp duty)
- [ ] Create strategy-level cost calculator
- [ ] Build pre-trade confirmation UI/API

### Phase 5: Additional Housekeeping (Week 9-10)
- [ ] Implement intraday auto square-off
- [ ] Implement order aging and timeout
- [ ] Implement strategy snapshot manager
- [ ] Implement risk limit monitoring
- [ ] Implement broker health monitoring
- [ ] Implement data reconciliation service

### Phase 6: Testing & Optimization (Week 11-12)
- [ ] Unit tests for all calculators
- [ ] Integration tests with mock Kite API
- [ ] End-to-end testing with real broker (test environment)
- [ ] Performance optimization
- [ ] Load testing (100+ concurrent strategies)

### Phase 7: Documentation & Deployment (Week 13)
- [ ] API documentation
- [ ] User guide for housekeeping features
- [ ] Admin guide for configuration
- [ ] Deployment to staging
- [ ] Production rollout

---

## 8. Configuration Examples

### 8.1 Conservative Strategy Settings

```json
{
  "auto_cleanup_enabled": true,
  "cleanup_sl_on_exit": true,
  "cleanup_target_on_exit": true,
  "max_order_spread_pct": 0.3,
  "min_liquidity_score": 70,
  "require_user_approval_high_impact": true,
  "max_market_impact_bps": 30,
  "margin_buffer_pct": 20.0,
  "max_loss_per_strategy_pct": 5.0,
  "auto_square_off_on_loss_limit": true
}
```

### 8.2 Aggressive Strategy Settings

```json
{
  "auto_cleanup_enabled": false,
  "allow_orphaned_orders": true,
  "max_order_spread_pct": 1.0,
  "min_liquidity_score": 40,
  "require_user_approval_high_impact": false,
  "max_market_impact_bps": 100,
  "margin_buffer_pct": 5.0,
  "max_loss_per_strategy_pct": 15.0,
  "auto_square_off_on_loss_limit": false
}
```

---

## 9. Example Workflows

### 9.1 Workflow: Adding Instrument to Strategy with Smart Checks

```
User Action: Add NIFTY 24500 CE to Strategy
                    ↓
        ┌───────────────────────────┐
        │ 1. Calculate Margin       │
        │    - Call Kite margin API │
        │    - Check available funds│
        └───────────┬───────────────┘
                    ↓
        ┌───────────────────────────┐
        │ 2. Calculate Costs        │
        │    - Brokerage: ₹20       │
        │    - STT, GST, etc.       │
        │    - Total: ₹85           │
        └───────────┬───────────────┘
                    ↓
        ┌───────────────────────────┐
        │ 3. Analyze Market Depth   │
        │    - Spread: 0.8% (wide)  │
        │    - Impact: 45 bps       │
        └───────────┬───────────────┘
                    ↓
                Decision
                    ↓
        ┌───────────────────────────┐
        │ 4. Show Confirmation      │
        │    ⚠️  Wide spread detected│
        │    Entry: ₹1,25,085       │
        │    Impact: ₹450           │
        │    Margin: ₹45,000 ✅     │
        │    [Cancel] [Proceed]     │
        └───────────┬───────────────┘
                    ↓
            User Approves
                    ↓
        ┌───────────────────────────┐
        │ 5. Place Order            │
        │    - Use LIMIT order      │
        │    - Price: mid-price     │
        └───────────┬───────────────┘
                    ↓
        ┌───────────────────────────┐
        │ 6. Log Analysis           │
        │    - Save to order_       │
        │      execution_analysis   │
        │    - Save to order_cost_  │
        │      breakdown            │
        └───────────────────────────┘
```

### 9.2 Workflow: Position Exit with Auto Cleanup

```
Position Closed: NIFTY 24500 CE (100 lots sold)
                    ↓
        ┌───────────────────────────┐
        │ 1. Trigger Housekeeping   │
        │    Event: POSITION_CLOSED │
        └───────────┬───────────────┘
                    ↓
        ┌───────────────────────────┐
        │ 2. Detect Orphaned Orders │
        │    - SL order: 24300      │
        │    - Target: 24700        │
        └───────────┬───────────────┘
                    ↓
        ┌───────────────────────────┐
        │ 3. Check User Preference  │
        │    auto_cleanup_enabled:  │
        │    TRUE                   │
        └───────────┬───────────────┘
                    ↓
        ┌───────────────────────────┐
        │ 4. Cancel SL & Target     │
        │    - Call broker API      │
        │    - Update order status  │
        └───────────┬───────────────┘
                    ↓
        ┌───────────────────────────┐
        │ 5. Notify User            │
        │    "2 orders auto-        │
        │     cancelled (position   │
        │     closed)"              │
        └───────────┬───────────────┘
                    ↓
        ┌───────────────────────────┐
        │ 6. Log Event              │
        │    housekeeping_events    │
        └───────────────────────────┘
```

---

## 10. Success Metrics

**Order Execution Quality**:
- Average slippage < 0.2% for liquid instruments
- 95%+ orders executed at expected price or better
- User alert response rate > 80%

**Housekeeping Efficiency**:
- Orphaned orders detected within 5 minutes
- 100% expired instruments cleaned up by next trading day
- Zero position-order discrepancies at EOD

**Cost Transparency**:
- 100% orders have pre-execution cost breakdown
- Margin calculation accuracy > 99.5%
- User awareness of costs before trade execution

**Risk Management**:
- Risk limit breaches detected in < 1 second
- Auto square-off executed within 30 seconds of trigger
- Zero manual intervention needed for routine housekeeping

---

## Conclusion

This comprehensive system provides:
✅ **Automated housekeeping** with user control
✅ **Smart execution** using market depth
✅ **Complete cost transparency** before trading
✅ **Proactive risk management**
✅ **Production-grade reliability**

**Recommended Next Steps**:
1. Review and approve design
2. Prioritize features (MVP vs. nice-to-have)
3. Begin Phase 1 implementation (database schema)
4. Set up test environment with Kite sandbox API
