# Market Depth Analyzer - Integration Guide

## Overview

The `MarketDepthAnalyzer` computes comprehensive liquidity metrics from market depth data (L2 order book). It helps identify illiquid instruments, detect order flow imbalances, and make informed trading decisions.

## Quick Start

```python
from app.services.market_depth_analyzer import MarketDepthAnalyzer

# Initialize analyzer
analyzer = MarketDepthAnalyzer(include_advanced=True)

# Analyze depth data from a tick
analysis = analyzer.analyze(
    depth_data=tick['depth'],
    last_price=tick['last_price'],
    instrument_token=tick['instrument_token']
)

# Get all metrics as dict
metrics = analysis.to_dict()

# Or get flat dict (all metrics at top level)
flat_metrics = analysis.to_flat_dict()
```

---

## Integration Points

### 1. Ticker Service Integration

Add market depth analysis to real-time ticks:

```python
# In ticker_service/app/generator.py or websocket handler

from market_depth_analyzer import MarketDepthAnalyzer

class TickGenerator:
    def __init__(self):
        self.depth_analyzer = MarketDepthAnalyzer(include_advanced=False)  # Skip advanced for real-time

    def process_tick(self, tick_data):
        """Process incoming tick with depth data."""

        # Only analyze if MODE_FULL (has depth data)
        if tick_data.get('depth'):
            depth_metrics = self.depth_analyzer.analyze(
                depth_data=tick_data['depth'],
                last_price=tick_data['last_price'],
                instrument_token=tick_data['instrument_token']
            )

            # Add essential metrics to tick
            tick_data['liquidity'] = {
                'score': depth_metrics.liquidity.liquidity_score,
                'tier': depth_metrics.liquidity.liquidity_tier,
                'spread_pct': depth_metrics.spread.bid_ask_spread_pct,
                'depth_imbalance_pct': depth_metrics.imbalance.depth_imbalance_pct,
                'book_pressure': depth_metrics.imbalance.book_pressure,
            }

            # Optional: Add flags for filtering
            if depth_metrics.liquidity.illiquidity_flags['wide_spread']:
                tick_data['illiquid_warning'] = True

        return tick_data
```

---

### 2. Backend API Integration

Create endpoint to fetch liquidity metrics:

```python
# In app/routes/fo.py or new routes/liquidity.py

from app.services.market_depth_analyzer import MarketDepthAnalyzer
from fastapi import APIRouter, Query

router = APIRouter(prefix="/liquidity", tags=["liquidity"])

@router.post("/analyze-depth")
async def analyze_market_depth(
    depth_data: dict,
    last_price: float,
    instrument_token: Optional[int] = None,
    include_advanced: bool = False
):
    """
    Analyze market depth and return liquidity metrics.

    Example request:
    {
        "depth_data": {
            "buy": [{"quantity": 100, "price": 25600.00, "orders": 5}, ...],
            "sell": [{"quantity": 150, "price": 25600.50, "orders": 7}, ...]
        },
        "last_price": 25600.25,
        "instrument_token": 256265
    }
    """
    analyzer = MarketDepthAnalyzer(include_advanced=include_advanced)
    analysis = analyzer.analyze(depth_data, last_price, instrument_token)

    return {
        "status": "ok",
        "instrument_token": instrument_token,
        "metrics": analysis.to_dict()
    }


@router.get("/illiquid-instruments")
async def get_illiquid_instruments(
    min_score: float = Query(40.0, description="Minimum liquidity score"),
    max_spread_pct: float = Query(0.5, description="Maximum spread %")
):
    """
    Get list of currently illiquid instruments.

    This would query Redis for latest depth data and filter.
    """
    # Implementation: Query Redis for all instruments with depth data
    # Analyze each and filter by criteria
    pass
```

---

### 3. Database Storage (Optional)

If you want to store liquidity metrics historically:

**Migration: `021_add_liquidity_metrics.sql`**
```sql
-- Add liquidity metrics to fo_option_strike_bars
ALTER TABLE fo_option_strike_bars
ADD COLUMN IF NOT EXISTS liquidity_score DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS liquidity_tier VARCHAR(20),
ADD COLUMN IF NOT EXISTS spread_pct DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS depth_imbalance_pct DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS book_pressure DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS is_illiquid BOOLEAN DEFAULT FALSE;

-- Index for filtering illiquid instruments
CREATE INDEX IF NOT EXISTS idx_fo_strike_illiquid
ON fo_option_strike_bars(is_illiquid, bucket_time)
WHERE is_illiquid = TRUE;
```

**Update database writer:**
```python
# In app/database.py - upsert_fo_strike_rows()

# Add to INSERT columns:
liquidity_score,
liquidity_tier,
spread_pct,
depth_imbalance_pct,
book_pressure,
is_illiquid

# Add to VALUES:
$33, $34, $35, $36, $37, $38

# Extract from row data:
liquidity = row.get("liquidity", {})
records.append((
    # ... existing fields ...
    liquidity.get("score"),
    liquidity.get("tier"),
    liquidity.get("spread_pct"),
    liquidity.get("depth_imbalance_pct"),
    liquidity.get("book_pressure"),
    liquidity.get("score", 100) < 40,  # Mark as illiquid if score < 40
))
```

---

### 4. Frontend Integration

**Recommended Metrics to Send to Frontend:**

```typescript
// frontend/src/types/liquidity.ts

export interface LiquidityMetrics {
  // Essential (always send)
  liquidity_score: number;          // 0-100
  liquidity_tier: 'HIGH' | 'MEDIUM' | 'LOW' | 'ILLIQUID';
  bid_ask_spread_pct: number;       // Spread as %
  depth_imbalance_pct: number;      // Book imbalance
  book_pressure: number;            // -1 to +1

  // Flags (for filtering)
  illiquidity_flags: {
    wide_spread: boolean;
    thin_depth: boolean;
    few_orders: boolean;
    imbalanced_book: boolean;
  };

  // Optional (for advanced users)
  microprice?: number;
  market_impact_cost_100?: number;
}
```

**Display in UI:**

```typescript
// Display liquidity badge
const getLiquidityColor = (tier: string) => {
  switch (tier) {
    case 'HIGH': return 'green';
    case 'MEDIUM': return 'yellow';
    case 'LOW': return 'orange';
    case 'ILLIQUID': return 'red';
  }
};

// Show warning for illiquid instruments
{metrics.liquidity_tier === 'ILLIQUID' && (
  <Alert severity="warning">
    ⚠️ Illiquid instrument - Use limit orders only
  </Alert>
)}

// Order flow indicator
{metrics.book_pressure > 0.15 && (
  <Chip label="🟢 Strong Buy Pressure" color="success" />
)}
{metrics.book_pressure < -0.15 && (
  <Chip label="🔴 Strong Sell Pressure" color="error" />
)}
```

---

## Use Cases

### 1. Filter Illiquid Options Before Trading

```python
# In your trading strategy
if analysis.liquidity.liquidity_score < 40:
    logger.warning(f"Skipping {instrument_token} - Illiquid (score={analysis.liquidity.liquidity_score})")
    return None

if analysis.spread.bid_ask_spread_pct > 1.0:
    logger.warning(f"Wide spread on {instrument_token} - {analysis.spread.bid_ask_spread_pct:.2f}%")
    execution_type = "LIMIT_ONLY"
```

### 2. Detect Order Flow for Entry Timing

```python
# Strong buy pressure = good time to sell
if analysis.imbalance.book_pressure > 0.20:
    print(f"Strong BUY pressure detected - Good time to SELL")
    recommended_action = "SELL"

# Strong sell pressure = good time to buy
elif analysis.imbalance.book_pressure < -0.20:
    print(f"Strong SELL pressure detected - Good time to BUY")
    recommended_action = "BUY"
```

### 3. Dynamic Execution Strategy

```python
def get_execution_strategy(analysis: MarketDepthAnalysis):
    """Determine optimal execution based on liquidity."""

    if analysis.liquidity.liquidity_score >= 70 and analysis.spread.bid_ask_spread_pct < 0.3:
        return "MARKET_ORDER"  # Liquid enough for market orders

    elif analysis.liquidity.liquidity_score >= 50:
        return "LIMIT_AT_MID"  # Use limit at mid-price

    elif analysis.liquidity.liquidity_score >= 30:
        return "LIMIT_AT_BEST"  # Patient limit at best bid/ask

    else:
        return "AVOID"  # Too illiquid
```

### 4. Market Impact Cost Estimation

```python
# Estimate cost before placing large order
if order_size > 100:
    if order_size <= 500:
        estimated_cost = analysis.advanced.market_impact_cost_500
    else:
        # Extrapolate
        estimated_cost = analysis.advanced.market_impact_cost_500 * (order_size / 500)

    print(f"Estimated market impact for {order_size} units: ₹{estimated_cost:.2f}")

    # Adjust strategy if impact too high
    if estimated_cost / analysis.spread.mid_price > 0.01:  # > 1% impact
        print("High market impact - Consider splitting order")
```

---

## Performance Notes

- **Real-time Analysis**: ~0.1ms per instrument (without advanced metrics)
- **With Advanced Metrics**: ~0.3ms per instrument
- **Memory**: ~1KB per analysis result

**Recommendation:**
- In ticker service: Use `include_advanced=False` for real-time
- In API endpoints: Use `include_advanced=True` on-demand
- Cache results for 1-2 seconds if analyzing same instrument repeatedly

---

## API Response Example

```json
{
  "status": "ok",
  "instrument_token": 256265,
  "metrics": {
    "spread": {
      "bid_ask_spread_abs": 0.50,
      "bid_ask_spread_pct": 0.0020,
      "mid_price": 25600.25,
      "weighted_mid_price": 25600.21,
      "best_bid": 25600.00,
      "best_ask": 25600.50
    },
    "depth": {
      "total_bid_quantity": 6500,
      "total_ask_quantity": 7500,
      "depth_at_best_bid": 750,
      "depth_at_best_ask": 1000,
      "total_orders_bid": 115,
      "total_orders_ask": 122
    },
    "imbalance": {
      "depth_imbalance_pct": -7.14,
      "book_pressure": -0.0714,
      "volume_imbalance": -1000
    },
    "liquidity": {
      "liquidity_score": 98.41,
      "liquidity_tier": "HIGH",
      "illiquidity_flags": {
        "wide_spread": false,
        "thin_depth": false,
        "few_orders": false,
        "imbalanced_book": false
      }
    }
  }
}
```

---

## Testing

Run the test suite:
```bash
python3 tests/test_market_depth_analyzer.py
```

Test with your own data:
```python
from app.services.market_depth_analyzer import analyze_market_depth

# Quick analysis
metrics = analyze_market_depth(
    depth_data=your_tick['depth'],
    last_price=your_tick['last_price'],
    include_advanced=True
)

print(f"Liquidity Score: {metrics['liquidity']['liquidity_score']}")
print(f"Tier: {metrics['liquidity']['liquidity_tier']}")
```

---

## Summary

The `MarketDepthAnalyzer` provides:

✅ **Spread Analysis** - Identify wide spreads and fair value
✅ **Depth Metrics** - Understand available liquidity
✅ **Imbalance Detection** - Detect buy/sell pressure
✅ **Liquidity Scoring** - Classify instruments as liquid/illiquid
✅ **Market Impact** - Estimate execution costs
✅ **Trading Signals** - Guide execution strategy

**Key Benefits:**
- Avoid illiquid instruments automatically
- Optimize order execution strategy
- Detect order flow for better timing
- Estimate transaction costs before trading
