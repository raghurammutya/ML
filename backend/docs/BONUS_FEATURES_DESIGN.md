# Bonus Features - Advanced Order Management

**Created**: 2025-11-09
**Status**: Design Proposal
**Related**: Smart Order Management System

---

## Overview

Additional intelligent features to enhance order execution quality and strategy management.

---

## Feature 1: TWAP/ICEBERG Orders for Illiquid Instruments

### Problem
Large orders in illiquid instruments cause significant market impact and poor fill prices.

### Solution: Time-Weighted Average Price (TWAP) Orders

```python
class TWAPOrderExecutor:
    """
    Execute large orders by splitting into smaller chunks over time.

    Use Cases:
    - Large position in illiquid option (e.g., far OTM strikes)
    - Building position gradually to avoid detection
    - Reducing market impact
    """

    async def execute_twap_order(
        self,
        instrument_token: int,
        total_quantity: int,
        side: str,  # BUY/SELL
        duration_minutes: int = 30,
        max_slice_size: Optional[int] = None
    ) -> TWAPOrderExecution:
        """
        Execute TWAP order.

        Args:
            total_quantity: Total lots to buy/sell
            duration_minutes: Time window to spread order (default 30 min)
            max_slice_size: Max lots per slice (default: auto-calculated)

        Algorithm:
            1. Calculate number of slices (e.g., 30 min / 2 min = 15 slices)
            2. Calculate quantity per slice (e.g., 100 lots / 15 = 6-7 lots)
            3. Place orders at regular intervals (every 2 minutes)
            4. Adjust remaining quantity if partial fills occur
            5. Monitor liquidity and pause if spread widens significantly

        Example:
            Order: BUY 100 lots NIFTY 24500 CE
            Duration: 30 minutes
            Slices: 15 (one every 2 minutes)
            Per slice: ~7 lots

            09:15:00 - BUY 7 lots
            09:17:00 - BUY 7 lots
            09:19:00 - BUY 7 lots
            ...
            09:45:00 - BUY 2 lots (final)
        """

        # Calculate slicing parameters
        slice_interval_seconds = 120  # 2 minutes
        num_slices = (duration_minutes * 60) // slice_interval_seconds

        if max_slice_size:
            quantity_per_slice = min(
                total_quantity // num_slices,
                max_slice_size
            )
        else:
            quantity_per_slice = total_quantity // num_slices

        remaining_quantity = total_quantity
        executed_slices = []

        # Execute slices
        for i in range(num_slices):
            if remaining_quantity <= 0:
                break

            # Check market conditions before placing slice
            depth = await self.get_market_depth(instrument_token)
            spread_analysis = self.analyze_spread(depth)

            # If spread too wide, wait for next slice
            if spread_analysis.bid_ask_spread_pct > 1.0:
                logger.warning(f"TWAP: Spread too wide ({spread_analysis.bid_ask_spread_pct}%), skipping slice {i+1}")
                await asyncio.sleep(slice_interval_seconds)
                continue

            # Place slice order
            slice_qty = min(quantity_per_slice, remaining_quantity)
            order = await self._place_limit_order(
                instrument_token,
                slice_qty,
                side,
                limit_price=self._get_smart_limit_price(depth, side)
            )

            executed_slices.append(order)
            remaining_quantity -= slice_qty

            # Wait for next slice interval
            if i < num_slices - 1 and remaining_quantity > 0:
                await asyncio.sleep(slice_interval_seconds)

        # Return execution summary
        total_filled = sum(s.filled_quantity for s in executed_slices)
        avg_fill_price = sum(
            s.filled_quantity * s.average_price for s in executed_slices
        ) / total_filled if total_filled > 0 else Decimal('0')

        return TWAPOrderExecution(
            total_quantity=total_quantity,
            total_filled=total_filled,
            remaining_quantity=total_quantity - total_filled,
            slices_executed=len(executed_slices),
            average_fill_price=avg_fill_price,
            duration_actual_minutes=(
                (executed_slices[-1].placed_at - executed_slices[0].placed_at).seconds // 60
                if executed_slices else 0
            )
        )
```

### ICEBERG Orders (Hidden Quantity)

```python
class IcebergOrderExecutor:
    """
    Place large orders with only small portion visible in order book.

    Use Cases:
    - Hide true order size from other traders
    - Reduce market impact
    - Get better average fill price

    Note: Zerodha Kite doesn't natively support iceberg orders,
    so we emulate by placing small visible orders and replenishing.
    """

    async def execute_iceberg_order(
        self,
        instrument_token: int,
        total_quantity: int,
        visible_quantity: int,  # Show only this much in order book
        side: str,
        limit_price: Decimal
    ) -> IcebergOrderExecution:
        """
        Execute iceberg order by showing only visible_quantity at a time.

        Algorithm:
            1. Place order for visible_quantity at limit_price
            2. When filled, immediately place another for visible_quantity
            3. Repeat until total_quantity filled
            4. Update limit_price if market moves

        Example:
            Total: BUY 100 lots
            Visible: 10 lots
            Price: ₹150.00

            Order 1: BUY 10 lots @ ₹150.00 → Filled
            Order 2: BUY 10 lots @ ₹150.00 → Filled
            ...
            Order 10: BUY 10 lots @ ₹150.00 → Filled
        """
        remaining_quantity = total_quantity
        orders_placed = []

        while remaining_quantity > 0:
            # Place visible portion
            current_qty = min(visible_quantity, remaining_quantity)

            # Check if price still valid
            current_price = await self._get_current_price(instrument_token)
            if side == 'BUY' and current_price > limit_price * Decimal('1.01'):
                # Price moved up 1%, adjust limit
                limit_price = current_price * Decimal('1.002')  # 0.2% above current

            order = await self._place_limit_order(
                instrument_token,
                current_qty,
                side,
                limit_price
            )

            orders_placed.append(order)

            # Wait for fill (with timeout)
            filled = await self._wait_for_order_fill(
                order.id,
                timeout_seconds=300  # 5 minutes
            )

            if filled:
                remaining_quantity -= order.filled_quantity
            else:
                # Order not filled, cancel and reassess
                await self._cancel_order(order.id)
                break

        return IcebergOrderExecution(
            total_quantity=total_quantity,
            total_filled=sum(o.filled_quantity for o in orders_placed),
            orders_placed=len(orders_placed),
            average_fill_price=self._calculate_avg_price(orders_placed)
        )
```

---

## Feature 2: Smart Order Splitting

### Problem
Single large order causes high slippage due to walking through multiple price levels.

### Solution: Intelligent Order Splitting

```python
class SmartOrderSplitter:
    """
    Analyze order book and split order optimally to minimize market impact.

    Logic:
    - If order can be filled within best 3 price levels → Single order
    - If order requires 4-6 levels → Split into 2-3 smaller orders
    - If order requires > 6 levels → Use TWAP or reject
    """

    async def analyze_and_split_order(
        self,
        instrument_token: int,
        quantity: int,
        side: str
    ) -> OrderSplitRecommendation:
        """
        Analyze order book and recommend splitting strategy.

        Returns:
            OrderSplitRecommendation with:
            - recommended_strategy: SINGLE, SPLIT, TWAP, REJECT
            - num_splits: How many orders to split into
            - split_quantities: List of quantities per split
            - reasoning: Why this strategy was chosen
        """
        depth = await self.get_market_depth(instrument_token)
        book_side = depth['sell'] if side == 'BUY' else depth['buy']

        # Walk through order book to see how many levels needed
        remaining_qty = quantity
        levels_consumed = 0
        can_fill = True

        for level in book_side:
            if remaining_qty <= 0:
                break

            level_qty = level['quantity']
            if remaining_qty <= level_qty:
                # Can fill completely at this level
                levels_consumed += 1
                break
            else:
                remaining_qty -= level_qty
                levels_consumed += 1

        if remaining_qty > 0:
            # Cannot fill completely with available depth
            can_fill = False

        # Decide strategy based on levels consumed
        if not can_fill:
            return OrderSplitRecommendation(
                recommended_strategy="REJECT",
                reason="INSUFFICIENT_LIQUIDITY",
                alternative="Use TWAP over 30 minutes"
            )

        if levels_consumed <= 3:
            return OrderSplitRecommendation(
                recommended_strategy="SINGLE",
                num_splits=1,
                split_quantities=[quantity],
                reason=f"Can fill within {levels_consumed} levels"
            )

        if levels_consumed <= 6:
            # Split into 2-3 orders
            num_splits = min(3, levels_consumed // 2)
            split_qty = quantity // num_splits

            return OrderSplitRecommendation(
                recommended_strategy="SPLIT",
                num_splits=num_splits,
                split_quantities=[split_qty] * num_splits,
                reason=f"Requires {levels_consumed} levels, splitting reduces impact"
            )

        # More than 6 levels → Use TWAP
        return OrderSplitRecommendation(
            recommended_strategy="TWAP",
            reason=f"Requires {levels_consumed} levels, use TWAP to minimize impact"
        )
```

---

## Feature 3: Historical Slippage Analysis

### Problem
Users don't know typical slippage for an instrument, leading to poor execution expectations.

### Solution: Slippage Tracking & Analytics

```python
class SlippageAnalyzer:
    """
    Track and analyze historical slippage for instruments.

    Metrics:
    - Average slippage per instrument
    - Slippage by time of day (morning, afternoon, last hour)
    - Slippage by order size
    - Slippage on expiry day vs normal days
    """

    async def record_order_slippage(
        self,
        order_id: int,
        expected_price: Decimal,
        actual_fill_price: Decimal,
        quantity: int,
        instrument_token: int,
        timestamp: datetime
    ):
        """
        Record slippage for an executed order.
        """
        slippage_abs = abs(actual_fill_price - expected_price)
        slippage_pct = (slippage_abs / expected_price) * 100
        slippage_cost = slippage_abs * quantity

        await self._save_slippage_record({
            "order_id": order_id,
            "instrument_token": instrument_token,
            "expected_price": expected_price,
            "actual_price": actual_fill_price,
            "slippage_abs": slippage_abs,
            "slippage_pct": slippage_pct,
            "slippage_cost": slippage_cost,
            "quantity": quantity,
            "timestamp": timestamp,
            "hour_of_day": timestamp.hour,
            "is_expiry_day": self._is_expiry_day(timestamp)
        })

    async def get_slippage_stats(
        self,
        instrument_token: int,
        days: int = 30
    ) -> SlippageStatistics:
        """
        Get historical slippage statistics for instrument.

        Returns:
            SlippageStatistics with:
            - avg_slippage_pct: Average slippage (%)
            - median_slippage_pct: Median slippage
            - p95_slippage_pct: 95th percentile (worst case)
            - slippage_by_hour: Dict of avg slippage by hour
            - slippage_by_size: Dict of avg slippage by order size bucket
            - expiry_day_slippage: Avg slippage on expiry days
        """
        records = await self._fetch_slippage_records(
            instrument_token,
            days
        )

        return SlippageStatistics(
            avg_slippage_pct=statistics.mean(r.slippage_pct for r in records),
            median_slippage_pct=statistics.median(r.slippage_pct for r in records),
            p95_slippage_pct=self._percentile(
                [r.slippage_pct for r in records],
                0.95
            ),
            slippage_by_hour=self._group_by_hour(records),
            slippage_by_size=self._group_by_size(records),
            expiry_day_slippage=self._calculate_expiry_day_slippage(records)
        )
```

### UI Display

```
Instrument: NIFTY 24500 CE

Historical Slippage (Last 30 Days):
┌────────────────────────────────────┐
│ Average Slippage:      0.15%       │
│ Median:                0.10%       │
│ Worst Case (95%ile):   0.35%       │
│                                    │
│ By Time of Day:                    │
│   9:15-10:00 AM:      0.20%        │
│   10:00-12:00 PM:     0.12%        │
│   12:00-3:00 PM:      0.13%        │
│   3:00-3:30 PM:       0.25%        │
│                                    │
│ By Order Size:                     │
│   1-20 lots:          0.10%        │
│   21-50 lots:         0.15%        │
│   51-100 lots:        0.25%        │
│   > 100 lots:         0.40%        │
│                                    │
│ Expiry Day:           0.45%        │
│ Normal Days:          0.12%        │
└────────────────────────────────────┘
```

---

## Feature 4: Liquidity-Based Position Sizing

### Problem
Users enter large positions in illiquid instruments without understanding risk.

### Solution: Smart Position Size Recommendations

```python
class LiquidityBasedPositionSizer:
    """
    Recommend position size based on liquidity metrics.

    Rules:
    - High liquidity (tier 1): Up to 10% of visible depth
    - Medium liquidity (tier 2): Up to 5% of visible depth
    - Low liquidity (tier 3): Up to 2% of visible depth
    - Illiquid: Warn user, suggest max 1-2 lots
    """

    async def recommend_position_size(
        self,
        instrument_token: int,
        desired_quantity: int
    ) -> PositionSizeRecommendation:
        """
        Analyze liquidity and recommend safe position size.

        Returns:
            PositionSizeRecommendation with:
            - max_recommended_quantity: Safe position size
            - liquidity_tier: HIGH/MEDIUM/LOW/ILLIQUID
            - reasoning: Why this size was recommended
            - warnings: List of warnings if desired > recommended
        """
        # Get market depth
        depth = await self.get_market_depth(instrument_token)
        liquidity_analysis = self.analyze_liquidity(depth)

        # Calculate visible depth
        total_bid_depth = sum(level['quantity'] for level in depth['buy'][:5])
        total_ask_depth = sum(level['quantity'] for level in depth['sell'][:5])
        total_depth = (total_bid_depth + total_ask_depth) // 2

        # Determine max safe position size
        if liquidity_analysis.tier == "HIGH":
            max_safe = int(total_depth * 0.10)  # 10% of depth
        elif liquidity_analysis.tier == "MEDIUM":
            max_safe = int(total_depth * 0.05)  # 5% of depth
        elif liquidity_analysis.tier == "LOW":
            max_safe = int(total_depth * 0.02)  # 2% of depth
        else:  # ILLIQUID
            max_safe = 2  # Max 2 lots

        warnings = []
        if desired_quantity > max_safe:
            warnings.append(
                f"Desired quantity ({desired_quantity}) exceeds safe limit ({max_safe})"
            )
            warnings.append(
                f"Consider using TWAP or reducing position size"
            )

        return PositionSizeRecommendation(
            desired_quantity=desired_quantity,
            max_recommended_quantity=max_safe,
            liquidity_tier=liquidity_analysis.tier,
            total_visible_depth=total_depth,
            reasoning=f"Liquidity tier: {liquidity_analysis.tier}, visible depth: {total_depth} lots",
            warnings=warnings
        )
```

---

## Feature 5: Greeks-Based Risk Alerts

### Problem
Users don't understand Greeks risk when building multi-leg option strategies.

### Solution: Real-Time Greeks Monitoring & Alerts

```python
class GreeksRiskMonitor:
    """
    Monitor strategy Greeks and alert on excessive exposure.

    Greeks Monitored:
    - Delta: Directional risk (target: -0.2 to +0.2 for neutral strategies)
    - Gamma: Acceleration risk (high gamma = large delta swings)
    - Vega: Volatility risk (high vega = sensitive to VIX changes)
    - Theta: Time decay (positive theta = earning time decay)
    """

    RISK_THRESHOLDS = {
        "delta": {
            "low": 0.1,      # < 0.1 delta: low directional risk
            "medium": 0.3,   # < 0.3: moderate risk
            "high": 0.5,     # < 0.5: high risk
            "extreme": 1.0   # >= 0.5: extreme risk
        },
        "gamma": {
            "low": 0.01,
            "medium": 0.03,
            "high": 0.05,
            "extreme": 0.1
        },
        "vega": {
            "low": 100,      # Vega in ₹
            "medium": 500,
            "high": 1000,
            "extreme": 2000
        }
    }

    async def monitor_strategy_greeks(
        self,
        strategy_id: int
    ) -> GreeksRiskAlert:
        """
        Calculate strategy Greeks and check risk thresholds.

        Returns:
            GreeksRiskAlert with:
            - delta: Net delta exposure
            - gamma: Net gamma exposure
            - vega: Net vega exposure
            - theta: Net theta (daily decay)
            - risk_level: LOW/MEDIUM/HIGH/EXTREME
            - warnings: List of specific risks
            - recommendations: Suggested adjustments
        """
        # Get all positions in strategy
        positions = await self._get_strategy_positions(strategy_id)

        # Calculate net Greeks
        net_delta = sum(p.delta * p.quantity for p in positions)
        net_gamma = sum(p.gamma * p.quantity for p in positions)
        net_vega = sum(p.vega * p.quantity for p in positions)
        net_theta = sum(p.theta * p.quantity for p in positions)

        # Determine risk levels
        delta_risk = self._assess_greek_risk(abs(net_delta), self.RISK_THRESHOLDS['delta'])
        gamma_risk = self._assess_greek_risk(abs(net_gamma), self.RISK_THRESHOLDS['gamma'])
        vega_risk = self._assess_greek_risk(abs(net_vega), self.RISK_THRESHOLDS['vega'])

        overall_risk = max([delta_risk, gamma_risk, vega_risk])

        # Generate warnings
        warnings = []
        if delta_risk == "HIGH":
            warnings.append(f"High delta exposure ({net_delta:.2f}). Strategy is directional.")
        if gamma_risk == "HIGH":
            warnings.append(f"High gamma ({net_gamma:.4f}). Delta will change rapidly.")
        if vega_risk == "HIGH":
            warnings.append(f"High vega (₹{net_vega:.0f}). Sensitive to VIX changes.")

        # Generate recommendations
        recommendations = []
        if abs(net_delta) > 0.3:
            recommendations.append("Add opposite delta position to neutralize")
        if abs(net_gamma) > 0.05:
            recommendations.append("Consider reducing gamma by closing far OTM options")

        return GreeksRiskAlert(
            strategy_id=strategy_id,
            delta=net_delta,
            gamma=net_gamma,
            vega=net_vega,
            theta=net_theta,
            delta_risk=delta_risk,
            gamma_risk=gamma_risk,
            vega_risk=vega_risk,
            overall_risk=overall_risk,
            warnings=warnings,
            recommendations=recommendations
        )
```

---

## Feature 6: Correlation Analysis for Multi-Leg Strategies

### Problem
Users build multi-leg strategies without understanding correlation between legs.

### Solution: Position Correlation Analysis

```python
class PositionCorrelationAnalyzer:
    """
    Analyze correlation between positions in a strategy.

    Use Cases:
    - Iron Condor: Ensure call spread and put spread are balanced
    - Calendar Spread: Understand near-month vs far-month correlation
    - Multi-asset strategies: Correlate NIFTY and BANKNIFTY positions
    """

    async def analyze_strategy_correlation(
        self,
        strategy_id: int
    ) -> CorrelationAnalysis:
        """
        Analyze correlation between positions.

        Returns:
            CorrelationAnalysis with:
            - correlation_matrix: Position-to-position correlations
            - hedging_effectiveness: How well positions hedge each other
            - concentration_risk: Are positions too correlated?
            - diversification_score: 0-100 (100 = well diversified)
        """
        positions = await self._get_strategy_positions(strategy_id)

        # Calculate price correlations (last 30 days)
        correlation_matrix = await self._calculate_correlation_matrix(positions)

        # Assess hedging effectiveness
        # If positions are negatively correlated → good hedge
        # If positions are positively correlated → concentration risk
        hedging_score = self._calculate_hedging_effectiveness(correlation_matrix)

        # Check for concentration risk
        concentration_warnings = []
        for i, pos1 in enumerate(positions):
            for j, pos2 in enumerate(positions):
                if i >= j:
                    continue

                corr = correlation_matrix[i][j]
                if corr > 0.8:
                    # High positive correlation = redundant positions
                    concentration_warnings.append(
                        f"{pos1.tradingsymbol} and {pos2.tradingsymbol} "
                        f"are highly correlated ({corr:.2f})"
                    )

        return CorrelationAnalysis(
            correlation_matrix=correlation_matrix,
            hedging_effectiveness=hedging_score,
            concentration_warnings=concentration_warnings,
            diversification_score=self._calculate_diversification_score(correlation_matrix)
        )
```

---

## Feature 7: Order Replay Protection

### Problem
Network issues or user errors can cause duplicate orders to be placed.

### Solution: Idempotency & Replay Protection

```python
class OrderReplayProtection:
    """
    Prevent duplicate orders from being placed.

    Protection mechanisms:
    1. Idempotency keys (order_ref)
    2. Rate limiting (max 1 order per second for same instrument)
    3. Duplicate detection (same symbol, quantity, side within 5 seconds)
    """

    async def validate_order_not_duplicate(
        self,
        instrument_token: int,
        quantity: int,
        side: str,
        idempotency_key: Optional[str] = None
    ) -> OrderValidation:
        """
        Check if order is a duplicate.

        Returns:
            OrderValidation with:
            - is_duplicate: bool
            - reason: Why it's considered duplicate
            - original_order_id: If duplicate, ID of original order
        """

        # Check 1: Idempotency key
        if idempotency_key:
            existing = await self._check_idempotency_key(idempotency_key)
            if existing:
                return OrderValidation(
                    is_duplicate=True,
                    reason="IDEMPOTENCY_KEY_ALREADY_USED",
                    original_order_id=existing.id
                )

        # Check 2: Recent identical orders (within 5 seconds)
        recent_orders = await self._get_recent_orders(
            instrument_token,
            seconds=5
        )

        for order in recent_orders:
            if (
                order.quantity == quantity and
                order.side == side and
                order.status in ['PENDING', 'OPEN', 'FILLED']
            ):
                return OrderValidation(
                    is_duplicate=True,
                    reason="IDENTICAL_ORDER_WITHIN_5_SECONDS",
                    original_order_id=order.id
                )

        return OrderValidation(
            is_duplicate=False,
            reason=None,
            original_order_id=None
        )
```

---

## Database Schema Extensions

```sql
-- Slippage tracking
CREATE TABLE order_slippage_history (
    id BIGSERIAL PRIMARY KEY,
    order_id BIGINT REFERENCES orders(id),
    instrument_token BIGINT NOT NULL,

    expected_price DECIMAL(20, 8),
    actual_fill_price DECIMAL(20, 8),
    slippage_abs DECIMAL(20, 8),
    slippage_pct DECIMAL(10, 4),
    slippage_cost DECIMAL(20, 2),

    quantity INTEGER,
    hour_of_day INTEGER,
    is_expiry_day BOOLEAN,

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_slippage_instrument ON order_slippage_history(instrument_token);
CREATE INDEX idx_slippage_created ON order_slippage_history(created_at);

-- TWAP/ICEBERG order tracking
CREATE TABLE advanced_order_executions (
    id BIGSERIAL PRIMARY KEY,
    parent_order_id BIGINT,  -- Logical parent order
    execution_type VARCHAR(20),  -- TWAP, ICEBERG, SPLIT

    total_quantity INTEGER,
    total_filled INTEGER,
    avg_fill_price DECIMAL(20, 8),

    child_orders JSONB,  -- Array of child order IDs
    execution_params JSONB,  -- TWAP duration, iceberg visible qty, etc.

    status VARCHAR(20),  -- IN_PROGRESS, COMPLETED, CANCELLED
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Greeks risk snapshots
CREATE TABLE strategy_greeks_snapshots (
    id BIGSERIAL PRIMARY KEY,
    strategy_id BIGINT REFERENCES strategies(id),

    net_delta DECIMAL(20, 8),
    net_gamma DECIMAL(20, 8),
    net_vega DECIMAL(20, 8),
    net_theta DECIMAL(20, 8),

    delta_risk VARCHAR(20),  -- LOW, MEDIUM, HIGH, EXTREME
    gamma_risk VARCHAR(20),
    vega_risk VARCHAR(20),
    overall_risk VARCHAR(20),

    warnings JSONB,
    recommendations JSONB,

    snapshot_timestamp TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_greeks_snapshots_strategy ON strategy_greeks_snapshots(strategy_id);
```

---

## Implementation Priority

### MVP (Must Have)
1. ✅ **Smart Order Splitting** - High impact, low complexity
2. ✅ **Order Replay Protection** - Critical for reliability
3. ✅ **Historical Slippage Analysis** - Builds trust with users

### Phase 2 (Nice to Have)
4. ✅ **TWAP Orders** - Advanced feature for sophisticated users
5. ✅ **Liquidity-Based Position Sizing** - Good risk management

### Phase 3 (Advanced)
6. ✅ **Greeks-Based Risk Alerts** - For options traders
7. ✅ **Correlation Analysis** - For complex strategies

---

## Success Metrics

**Execution Quality**:
- ✅ 30% reduction in slippage with smart splitting
- ✅ Zero duplicate orders (replay protection)
- ✅ 50% reduction in market impact for large orders (TWAP)

**Risk Management**:
- ✅ 80% of users see position sizing recommendations
- ✅ Greeks alerts triggered for 90% of high-risk strategies
- ✅ Correlation warnings prevent 50% of overexposed positions

---

These bonus features significantly enhance the trading experience and risk management capabilities! 🚀
