# Liquidity Metrics - Aggregation Strategy

## Overview

This document explains how tick-level market depth metrics are aggregated to higher timeframes (1min, 5min, 15min, etc.) and stored in `fo_option_strike_bars`.

---

## Aggregation Functions by Metric Type

### 1. Liquidity Score
**Source**: `liquidity_score` (0-100, computed per tick)

**Aggregations**:
- `liquidity_score_avg` = **Average** of all tick scores in the bar period
- `liquidity_score_min` = **Minimum** score (worst case scenario)

**Rationale**: Average gives overall liquidity quality, minimum identifies worst moments.

**Example**:
```
Ticks: [98.5, 97.2, 95.8, 92.3, 96.1]
liquidity_score_avg = 95.98
liquidity_score_min = 92.3
```

---

### 2. Liquidity Tier
**Source**: `liquidity_tier` (HIGH/MEDIUM/LOW/ILLIQUID, computed per tick)

**Aggregation**:
- `liquidity_tier` = **Most Frequent** tier during the bar period (mode)

**Rationale**: Represents the dominant liquidity condition.

**Example**:
```
Ticks: [HIGH, HIGH, MEDIUM, HIGH, HIGH]
liquidity_tier = "HIGH"  (appears 4/5 times)
```

**Implementation**:
```python
from collections import Counter
tiers = [tick['liquidity']['tier'] for tick in ticks]
liquidity_tier = Counter(tiers).most_common(1)[0][0]
```

---

### 3. Spread Metrics
**Source**: `bid_ask_spread_abs`, `bid_ask_spread_pct` (computed per tick)

**Aggregations**:
- `spread_abs_avg` = **Average** absolute spread
- `spread_pct_avg` = **Average** percentage spread
- `spread_pct_max` = **Maximum** percentage spread (worst case)

**Rationale**: Average spread for cost estimation, max spread to identify spikes.

**Example**:
```
Ticks (spread_pct): [0.02%, 0.025%, 0.018%, 0.035%, 0.022%]
spread_pct_avg = 0.024%
spread_pct_max = 0.035%
```

---

### 4. Depth Imbalance
**Source**: `depth_imbalance_pct`, `book_pressure` (computed per tick)

**Aggregations**:
- `depth_imbalance_pct_avg` = **Average** imbalance percentage
- `book_pressure_avg` = **Average** book pressure

**Rationale**: Average imbalance shows prevailing order flow direction.

**Example**:
```
Ticks (book_pressure): [+0.15, +0.20, +0.12, +0.18, +0.22]
book_pressure_avg = +0.174  (strong buy pressure)
```

---

### 5. Depth Quantities
**Source**: `total_bid_quantity`, `total_ask_quantity` (from depth data)

**Aggregations**:
- `total_bid_quantity_avg` = **Average** total bid quantity
- `total_ask_quantity_avg` = **Average** total ask quantity

**Rationale**: Average depth available during the bar period.

**Example**:
```
Ticks (bid_qty): [6500, 7200, 6800, 7000, 6900]
total_bid_quantity_avg = 6880
```

---

### 6. Illiquid Detection
**Source**: Computed from `liquidity_score` per tick

**Aggregations**:
- `illiquid_tick_count` = **Count** of ticks where `liquidity_score < 40`
- `total_tick_count` = **Count** of all ticks in the bar period
- `is_illiquid` = **Boolean** - TRUE if `illiquid_tick_count / total_tick_count > 0.5`

**Rationale**: If >50% of ticks were illiquid, mark the entire bar as illiquid.

**Example**:
```
Ticks (scores): [35, 38, 42, 36, 39, 41, 37, 45, 34, 40]
illiquid_tick_count = 6  (scores < 40)
total_tick_count = 10
is_illiquid = TRUE  (6/10 = 60% > 50%)
```

---

## Implementation in Database Writer

### Location: `app/database.py` - `upsert_fo_strike_rows()`

The aggregation happens **before** writing to the database. Here's the logic:

```python
def aggregate_liquidity_metrics(ticks: List[dict]) -> dict:
    """
    Aggregate tick-level liquidity metrics to bar-level metrics.

    Args:
        ticks: List of tick dictionaries with 'liquidity' key

    Returns:
        Dictionary with aggregated metrics
    """
    from collections import Counter

    if not ticks:
        return {}

    # Extract liquidity data from ticks
    liquidity_scores = []
    liquidity_tiers = []
    spread_abs_values = []
    spread_pct_values = []
    depth_imbalance_values = []
    book_pressure_values = []
    bid_qty_values = []
    ask_qty_values = []
    depth_at_best_bid_values = []
    depth_at_best_ask_values = []

    illiquid_count = 0
    total_count = 0

    for tick in ticks:
        liq = tick.get('liquidity', {})

        if liq:
            total_count += 1

            # Liquidity score
            score = liq.get('score')
            if score is not None:
                liquidity_scores.append(score)
                if score < 40:
                    illiquid_count += 1

            # Tier
            tier = liq.get('tier')
            if tier:
                liquidity_tiers.append(tier)

            # Spread
            spread_pct = liq.get('spread_pct')
            if spread_pct is not None:
                spread_pct_values.append(spread_pct)

            spread_abs = liq.get('spread_abs')
            if spread_abs is not None:
                spread_abs_values.append(spread_abs)

            # Imbalance
            depth_imb = liq.get('depth_imbalance_pct')
            if depth_imb is not None:
                depth_imbalance_values.append(depth_imb)

            book_press = liq.get('book_pressure')
            if book_press is not None:
                book_pressure_values.append(book_press)

            # Depth quantities
            bid_qty = liq.get('total_bid_quantity')
            if bid_qty is not None:
                bid_qty_values.append(bid_qty)

            ask_qty = liq.get('total_ask_quantity')
            if ask_qty is not None:
                ask_qty_values.append(ask_qty)

            depth_bid = liq.get('depth_at_best_bid')
            if depth_bid is not None:
                depth_at_best_bid_values.append(depth_bid)

            depth_ask = liq.get('depth_at_best_ask')
            if depth_ask is not None:
                depth_at_best_ask_values.append(depth_ask)

    # Compute aggregations
    result = {}

    if liquidity_scores:
        result['liquidity_score_avg'] = sum(liquidity_scores) / len(liquidity_scores)
        result['liquidity_score_min'] = min(liquidity_scores)

    if liquidity_tiers:
        result['liquidity_tier'] = Counter(liquidity_tiers).most_common(1)[0][0]

    if spread_abs_values:
        result['spread_abs_avg'] = sum(spread_abs_values) / len(spread_abs_values)

    if spread_pct_values:
        result['spread_pct_avg'] = sum(spread_pct_values) / len(spread_pct_values)
        result['spread_pct_max'] = max(spread_pct_values)

    if depth_imbalance_values:
        result['depth_imbalance_pct_avg'] = sum(depth_imbalance_values) / len(depth_imbalance_values)

    if book_pressure_values:
        result['book_pressure_avg'] = sum(book_pressure_values) / len(book_pressure_values)

    if bid_qty_values:
        result['total_bid_quantity_avg'] = int(sum(bid_qty_values) / len(bid_qty_values))

    if ask_qty_values:
        result['total_ask_quantity_avg'] = int(sum(ask_qty_values) / len(ask_qty_values))

    if depth_at_best_bid_values:
        result['depth_at_best_bid_avg'] = int(sum(depth_at_best_bid_values) / len(depth_at_best_bid_values))

    if depth_at_best_ask_values:
        result['depth_at_best_ask_avg'] = int(sum(depth_at_best_ask_values) / len(depth_at_best_ask_values))

    # Illiquid detection
    if total_count > 0:
        result['illiquid_tick_count'] = illiquid_count
        result['total_tick_count'] = total_count
        result['is_illiquid'] = (illiquid_count / total_count) > 0.5

    return result
```

---

## When Aggregation Happens

### Ticker Service → Backend Flow

1. **Ticker Service** computes liquidity metrics for each tick
2. **Backend** receives ticks via WebSocket
3. **Backend** buffers ticks in memory (Redis or in-process)
4. **Every 1 minute** (or configured interval):
   - Aggregate all buffered ticks using `aggregate_liquidity_metrics()`
   - Write aggregated metrics to `fo_option_strike_bars`
   - Clear buffer

### Higher Timeframe Aggregation (5min, 15min, etc.)

For higher timeframes, we **re-aggregate from 1-minute bars**:

```sql
-- Example: Aggregate 1min bars to 5min bars
SELECT
    -- Time bucket (5min)
    date_trunc('hour', bucket_time) +
    INTERVAL '5 min' * FLOOR(EXTRACT(MINUTE FROM bucket_time) / 5) AS bucket_5min,

    symbol,
    expiry,
    strike,

    -- Re-aggregate liquidity metrics
    AVG(liquidity_score_avg) AS liquidity_score_avg,
    MIN(liquidity_score_min) AS liquidity_score_min,  -- Worst case across all 1min bars

    AVG(spread_pct_avg) AS spread_pct_avg,
    MAX(spread_pct_max) AS spread_pct_max,  -- Worst spread

    AVG(depth_imbalance_pct_avg) AS depth_imbalance_pct_avg,
    AVG(book_pressure_avg) AS book_pressure_avg,

    -- Illiquid detection for 5min bar
    SUM(illiquid_tick_count) AS illiquid_tick_count,
    SUM(total_tick_count) AS total_tick_count,
    (SUM(illiquid_tick_count)::float / SUM(total_tick_count)) > 0.5 AS is_illiquid,

    -- Liquidity tier (most common across 5 1min bars)
    MODE() WITHIN GROUP (ORDER BY liquidity_tier) AS liquidity_tier

FROM fo_option_strike_bars
WHERE timeframe = '1min'
  AND bucket_time >= NOW() - INTERVAL '1 day'
GROUP BY bucket_5min, symbol, expiry, strike
ORDER BY bucket_5min DESC;
```

**Key Principles**:
- **MIN** for worst-case metrics (liquidity_score_min, spread_pct_max)
- **AVG** for typical metrics (spread_pct_avg, book_pressure_avg)
- **SUM** then ratio for illiquid detection
- **MODE** for categorical (liquidity_tier)

---

## Query Examples

### 1. Find Illiquid Instruments in Last Hour
```sql
SELECT
    symbol,
    expiry,
    strike,
    liquidity_score_avg,
    liquidity_tier,
    spread_pct_avg,
    is_illiquid
FROM fo_option_strike_bars
WHERE bucket_time >= NOW() - INTERVAL '1 hour'
  AND is_illiquid = TRUE
ORDER BY liquidity_score_avg ASC
LIMIT 20;
```

### 2. Track Spread Widening Over Time
```sql
SELECT
    bucket_time,
    symbol,
    strike,
    spread_pct_avg,
    spread_pct_max
FROM fo_option_strike_bars
WHERE symbol = 'NIFTY'
  AND expiry = '2025-11-12'
  AND strike = 25600
  AND bucket_time >= NOW() - INTERVAL '1 day'
ORDER BY bucket_time ASC;
```

### 3. Identify Strong Order Flow
```sql
SELECT
    bucket_time,
    symbol,
    strike,
    book_pressure_avg,
    depth_imbalance_pct_avg
FROM fo_option_strike_bars
WHERE symbol = 'NIFTY'
  AND bucket_time >= NOW() - INTERVAL '30 minutes'
  AND ABS(book_pressure_avg) > 0.20  -- Strong pressure
ORDER BY ABS(book_pressure_avg) DESC;
```

---

## Performance Considerations

### Storage Impact
- **Per row overhead**: ~120 bytes (12 new columns × ~10 bytes avg)
- **Daily volume**: ~500K strikes × 375 bars × 120 bytes = ~22.5 GB/day
- **With compression**: ~5-8 GB/day (PostgreSQL TOAST compression)

### Optimization
1. **Partial Indexes**: Only index illiquid instruments (see migration 021)
2. **Partitioning**: Partition by bucket_time (monthly partitions)
3. **Retention Policy**: Archive data older than 90 days to cold storage

---

## Summary

| Metric | Aggregation | Use Case |
|--------|-------------|----------|
| `liquidity_score_avg` | AVG | Overall liquidity quality |
| `liquidity_score_min` | MIN | Worst-case scenario |
| `liquidity_tier` | MODE | Dominant condition |
| `spread_pct_avg` | AVG | Execution cost estimate |
| `spread_pct_max` | MAX | Identify spread spikes |
| `book_pressure_avg` | AVG | Order flow direction |
| `is_illiquid` | >50% rule | Filter illiquid periods |

**Next Steps**:
1. Apply migration 021
2. Update `app/database.py` with aggregation logic
3. Test with live data
4. Create monitoring dashboard for illiquid instruments
