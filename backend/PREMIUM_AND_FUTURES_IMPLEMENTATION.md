# Premium/Discount & Futures Position Analysis Implementation

## Date: 2025-11-06
## Status: Implementation Plan

---

## Part 1: Options Premium/Discount Metrics (COMPLETED - Computed Expressions)

### Metrics Added to API:

1. **premium_abs** - Absolute premium/discount
   - Formula: `(intrinsic + extrinsic) - model_price`
   - Positive = Trading at premium
   - Negative = Trading at discount

2. **premium_pct** - Percentage premium/discount
   - Formula: `((intrinsic + extrinsic) - model_price) / model_price * 100`
   - Example: +5% means option is 5% overpriced vs Black-Scholes model

### Implementation Locations:

**File**: `/mnt/stocksblitz-data/Quantagro/tradingview-viz/backend/app/routes/fo.py`

**Functions to Update**:
- `moneyness_series()` - Line ~487-518
- `strike_distribution()` - Similar pattern ~line 617+

**SQL Expressions** (to add to column_map):

```python
# For option_side == "both"
"premium_abs": "((COALESCE(call_intrinsic_avg, 0) + COALESCE(call_extrinsic_avg, 0) - COALESCE(call_model_price_avg, 0)) + (COALESCE(put_intrinsic_avg, 0) + COALESCE(put_extrinsic_avg, 0) - COALESCE(put_model_price_avg, 0))) / 2.0",

"premium_pct": "((CASE WHEN COALESCE(call_model_price_avg, 0) > 0 THEN ((COALESCE(call_intrinsic_avg, 0) + COALESCE(call_extrinsic_avg, 0)) - call_model_price_avg) / call_model_price_avg * 100 ELSE 0 END) + (CASE WHEN COALESCE(put_model_price_avg, 0) > 0 THEN ((COALESCE(put_intrinsic_avg, 0) + COALESCE(put_extrinsic_avg, 0)) - put_model_price_avg) / put_model_price_avg * 100 ELSE 0 END)) / 2.0",

# For option_side == "call"
"premium_abs": "(COALESCE(call_intrinsic_avg, 0) + COALESCE(call_extrinsic_avg, 0)) - COALESCE(call_model_price_avg, 0)",

"premium_pct": "CASE WHEN COALESCE(call_model_price_avg, 0) > 0 THEN ((COALESCE(call_intrinsic_avg, 0) + COALESCE(call_extrinsic_avg, 0)) - call_model_price_avg) / call_model_price_avg * 100 ELSE NULL END",

# For option_side == "put"
"premium_abs": "(COALESCE(put_intrinsic_avg, 0) + COALESCE(put_extrinsic_avg, 0)) - COALESCE(put_model_price_avg, 0)",

"premium_pct": "CASE WHEN COALESCE(put_model_price_avg, 0) > 0 THEN ((COALESCE(put_intrinsic_avg, 0) + COALESCE(put_extrinsic_avg, 0)) - put_model_price_avg) / put_model_price_avg * 100 ELSE NULL END",
```

---

## Part 2: Futures Position Analysis

### Position Signals (Computed from Price & OI Movement):

| Signal | Price | OI | Interpretation |
|--------|-------|-----|----------------|
| **Long Buildup** | ↑ | ↑ | Bullish - New longs entering |
| **Short Buildup** | ↓ | ↑ | Bearish - New shorts entering |
| **Long Unwinding** | ↓ | ↓ | Bearish - Longs exiting |
| **Short Unwinding** | ↑ | ↓ | Bullish - Shorts covering |

### Database Schema:

**Table**: `futures_bars`
- Existing columns: time, symbol, contract, expiry, open, high, low, close, volume, open_interest, resolution

**Computed Metrics** (via SQL window functions):

```sql
-- Price change
price_change = close - LAG(close) OVER (PARTITION BY symbol, contract ORDER BY time)
price_change_pct = (close - LAG(close)) / LAG(close) * 100

-- OI change
oi_change = open_interest - LAG(open_interest) OVER (PARTITION BY symbol, contract ORDER BY time)
oi_change_pct = (open_interest - LAG(open_interest)) / LAG(open_interest) * 100

-- Position signal (4-way classification)
position_signal = CASE
    WHEN price_change > 0 AND oi_change > 0 THEN 'LONG_BUILDUP'
    WHEN price_change < 0 AND oi_change > 0 THEN 'SHORT_BUILDUP'
    WHEN price_change < 0 AND oi_change < 0 THEN 'LONG_UNWINDING'
    WHEN price_change > 0 AND oi_change < 0 THEN 'SHORT_UNWINDING'
    ELSE 'NEUTRAL'
END

-- Strength indicator (magnitude of both movements)
signal_strength = ABS(price_change_pct) * ABS(oi_change_pct) / 100
```

### Rollover Metrics:

**Computed across expiries for same underlying**:

```sql
-- OI distribution by expiry
WITH expiry_oi AS (
    SELECT
        symbol,
        expiry,
        SUM(open_interest) as total_oi,
        SUM(volume) as total_volume
    FROM futures_bars
    WHERE time = CURRENT_TIMESTAMP
    GROUP BY symbol, expiry
)
SELECT
    symbol,
    expiry,
    total_oi,
    total_oi / SUM(total_oi) OVER (PARTITION BY symbol) * 100 as oi_pct,
    EXTRACT(DAY FROM expiry - CURRENT_DATE) as days_to_expiry,
    -- Rollover pressure (high when near expiry with high OI)
    CASE
        WHEN EXTRACT(DAY FROM expiry - CURRENT_DATE) <= 5 THEN
            total_oi / GREATEST(SUM(total_oi) OVER (PARTITION BY symbol), 1) * 100
        ELSE 0
    END as rollover_pressure
FROM expiry_oi
ORDER BY symbol, expiry;
```

---

## Implementation Files:

### 1. Create Futures Analysis Utility

**File**: `/mnt/stocksblitz-data/Quantagro/tradingview-viz/backend/app/services/futures_analysis.py`

```python
"""
Futures Position Analysis & Rollover Metrics
"""
from typing import Optional, Dict, List
from datetime import datetime, date

class FuturesAnalyzer:
    """Analyzes futures position signals and rollover metrics."""

    @staticmethod
    def classify_position_signal(
        price_change: float,
        oi_change: float,
        threshold_pct: float = 0.1
    ) -> str:
        """
        Classify position signal based on price and OI changes.

        Args:
            price_change: Price change percentage
            oi_change: Open interest change percentage
            threshold_pct: Minimum % change to consider significant (default 0.1%)

        Returns:
            Position signal: LONG_BUILDUP, SHORT_BUILDUP, LONG_UNWINDING, SHORT_UNWINDING, NEUTRAL
        """
        if abs(price_change) < threshold_pct and abs(oi_change) < threshold_pct:
            return "NEUTRAL"

        if price_change > 0 and oi_change > 0:
            return "LONG_BUILDUP"
        elif price_change < 0 and oi_change > 0:
            return "SHORT_BUILDUP"
        elif price_change < 0 and oi_change < 0:
            return "LONG_UNWINDING"
        elif price_change > 0 and oi_change < 0:
            return "SHORT_UNWINDING"
        else:
            return "NEUTRAL"

    @staticmethod
    def compute_signal_strength(price_change_pct: float, oi_change_pct: float) -> float:
        """
        Compute signal strength as product of price and OI change magnitudes.

        Returns:
            Strength value (0-100+). Higher = stronger signal.
        """
        return abs(price_change_pct) * abs(oi_change_pct) / 100

    @staticmethod
    def compute_rollover_pressure(
        days_to_expiry: int,
        oi_pct: float,
        threshold_days: int = 5
    ) -> float:
        """
        Compute rollover pressure based on days to expiry and OI concentration.

        Args:
            days_to_expiry: Days until contract expiry
            oi_pct: Percentage of total OI in this contract
            threshold_days: Days before expiry to start computing pressure

        Returns:
            Rollover pressure (0-100). Higher = more urgent to roll.
        """
        if days_to_expiry > threshold_days:
            return 0.0

        # Pressure increases exponentially as expiry approaches
        time_factor = (threshold_days - days_to_expiry) / threshold_days
        return oi_pct * (time_factor ** 2)
```

### 2. Create Futures API Endpoint

**File**: `/mnt/stocksblitz-data/Quantagro/tradingview-viz/backend/app/routes/futures.py` (new file)

```python
"""
Futures market data endpoints with position analysis and rollover metrics.
"""
from fastapi import APIRouter, Depends, Query
from datetime import datetime, timedelta
from typing import Optional, List

from ..data_manager import DataManager, get_data_manager
from ..services.futures_analysis import FuturesAnalyzer

router = APIRouter(prefix="/futures", tags=["futures"])

@router.get("/position-signals")
async def get_position_signals(
    symbol: str = Query(..., description="Underlying symbol (e.g., NIFTY, BANKNIFTY)"),
    timeframe: str = Query("1min", description="Timeframe (1min, 5min, 15min)"),
    contract: Optional[str] = Query(None, description="Specific contract or current month"),
    hours: int = Query(6, description="Hours of historical data"),
    dm: DataManager = Depends(get_data_manager),
):
    """
    Get futures position signals (long/short buildup/unwinding) across timeframes.

    Returns time series with:
    - price_change_pct
    - oi_change_pct
    - position_signal
    - signal_strength
    """
    # SQL query with window functions to compute changes
    query = """
        SELECT
            time,
            contract,
            expiry,
            close,
            open_interest,
            volume,
            -- Price change
            close - LAG(close) OVER w as price_change,
            (close - LAG(close)) / NULLIF(LAG(close), 0) * 100 as price_change_pct,
            -- OI change
            open_interest - LAG(open_interest) OVER w as oi_change,
            (open_interest - LAG(open_interest)) / NULLIF(LAG(open_interest), 0) * 100 as oi_change_pct
        FROM futures_bars
        WHERE symbol = $1
          AND resolution = $2
          AND time >= $3
          AND ($4::text IS NULL OR contract = $4)
        WINDOW w AS (PARTITION BY contract ORDER BY time)
        ORDER BY time DESC, contract
    """

    # Execute query...
    # Classify signals using FuturesAnalyzer
    # Return formatted response


@router.get("/rollover-metrics")
async def get_rollover_metrics(
    symbol: str = Query(...),
    dm: DataManager = Depends(get_data_manager),
):
    """
    Get rollover metrics showing OI distribution across expiries.

    Returns:
    - OI by expiry
    - % distribution
    - Days to expiry
    - Rollover pressure score
    """
    query = """
        WITH latest_data AS (
            SELECT DISTINCT ON (contract)
                contract,
                expiry,
                time,
                open_interest,
                volume
            FROM futures_bars
            WHERE symbol = $1
              AND resolution = 1
            ORDER BY contract, time DESC
        ),
        expiry_totals AS (
            SELECT
                expiry,
                SUM(open_interest) as total_oi,
                SUM(volume) as total_volume,
                EXTRACT(DAY FROM expiry - CURRENT_DATE)::int as days_to_expiry
            FROM latest_data
            GROUP BY expiry
        )
        SELECT
            expiry,
            total_oi,
            total_volume,
            days_to_expiry,
            total_oi / NULLIF(SUM(total_oi) OVER (), 0) * 100 as oi_pct,
            -- Rollover pressure
            CASE
                WHEN days_to_expiry <= 5 THEN
                    (total_oi / NULLIF(SUM(total_oi) OVER (), 0) * 100) *
                    POWER((5 - days_to_expiry) / 5.0, 2)
                ELSE 0
            END as rollover_pressure
        FROM expiry_totals
        ORDER BY expiry;
    """
    # Execute and return...
```

### 3. Register Futures Router

**File**: `/mnt/stocksblitz-data/Quantagro/tradingview-viz/backend/app/main.py`

Add:
```python
from .routes import futures

app.include_router(futures.router)
```

---

## Testing:

### 1. Test Premium/Discount Metrics:
```bash
curl "http://localhost:8081/fo/moneyness-series?symbol=NIFTY50&timeframe=5min&indicator=premium_pct&hours=6"
```

### 2. Test Futures Position Signals:
```bash
curl "http://localhost:8081/futures/position-signals?symbol=NIFTY&timeframe=5min&hours=24"
```

### 3. Test Rollover Metrics:
```bash
curl "http://localhost:8081/futures/rollover-metrics?symbol=NIFTY"
```

---

## Next Steps:

1. ✅ Add premium/discount to options column_map (computed SQL expressions)
2. ⏳ Create futures_analysis.py utility
3. ⏳ Create futures.py API router
4. ⏳ Register router in main.py
5. ⏳ Test all endpoints
6. ⏳ Update frontend to display new metrics
