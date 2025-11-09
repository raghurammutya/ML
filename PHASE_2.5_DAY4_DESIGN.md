# Phase 2.5 Day 4: Payoff Graphs & Greeks - Design Document

**Date**: November 7, 2025
**Status**: Design Phase
**Dependencies**: Day 1 (Database), Day 2 (M2M Worker), Day 3 (Frontend Components)

---

## Overview

Day 4 adds advanced visualization and analytics to the Strategy System:
1. **Payoff Graphs**: Visual representation of strategy P&L across spot price ranges using `opstrat` Python package
2. **Greeks Calculation**: Net Greeks (Delta, Gamma, Theta, Vega) for option strategies
3. **Risk Metrics**: Max profit, max loss, breakeven points for strategies

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        Frontend (React)                          │
│                                                                   │
│  ┌────────────────────┐  ┌────────────────────────────────────┐ │
│  │ StrategyPayoffPanel│  │ StrategyGreeksPanel                │ │
│  │                    │  │                                    │ │
│  │  - Payoff Chart    │  │  - Net Delta, Gamma, Theta, Vega  │ │
│  │  - Max Profit/Loss │  │  - Greeks by instrument           │ │
│  │  - Breakeven Points│  │  - Position sensitivities         │ │
│  └────────────────────┘  └────────────────────────────────────┘ │
│            │                         │                           │
│            └─────────────┬───────────┘                           │
└──────────────────────────┼───────────────────────────────────────┘
                           │
                           ▼ HTTP API
┌─────────────────────────────────────────────────────────────────┐
│                    Backend (FastAPI)                             │
│                                                                   │
│  ┌────────────────────┐  ┌────────────────────────────────────┐ │
│  │ PayoffService      │  │ GreeksService                      │ │
│  │                    │  │                                    │ │
│  │  - Generate payoff │  │  - Calculate net Greeks           │ │
│  │    using opstrat   │  │  - Fetch Greeks from instruments  │ │
│  │  - Calculate risk  │  │  - Position-weighted aggregation  │ │
│  │    metrics         │  │                                    │ │
│  └────────────────────┘  └────────────────────────────────────┘ │
│            │                         │                           │
│            └─────────────┬───────────┘                           │
└──────────────────────────┼───────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    PostgreSQL Database                           │
│                                                                   │
│  - strategy_instruments (with instrument metadata)               │
│  - instruments (Greeks: delta, gamma, theta, vega, iv)           │
│  - strategy_summary_with_greeks (materialized view)              │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. Backend: Payoff Service

### 2.1 Install opstrat

Add to `backend/requirements.txt`:
```
opstrat==0.1.7
```

### 2.2 PayoffService Class

**File**: `backend/app/services/payoff_service.py`

```python
"""
Strategy Payoff Calculation Service

Uses opstrat library to generate payoff diagrams for option strategies.
"""

import io
import base64
from typing import Dict, List, Optional, Tuple
from decimal import Decimal
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
import opstrat as op


class PayoffService:
    """
    Service for generating payoff diagrams and calculating risk metrics.
    """

    def __init__(self, db_pool):
        self.db = db_pool

    async def generate_payoff_data(
        self,
        strategy_id: int,
        spot_price: Optional[float] = None,
        spot_range: int = 20
    ) -> Dict:
        """
        Generate payoff data for a strategy.

        Args:
            strategy_id: Strategy ID
            spot_price: Current spot price (auto-detect from instruments if None)
            spot_range: Percentage range for spot price variation (default: 20%)

        Returns:
            {
                "spot_price": 23500.0,
                "spot_range": 20,
                "payoff_image": "base64_encoded_png",
                "max_profit": 5000.0,
                "max_loss": -15000.0,
                "breakeven_points": [23350.0, 23650.0],
                "payoff_data": [
                    {"spot": 23000, "pnl": -10000},
                    {"spot": 23100, "pnl": -8000},
                    ...
                ],
                "risk_reward_ratio": 3.0
            }
        """
        async with self.db.acquire() as conn:
            # Fetch strategy instruments
            instruments = await conn.fetch("""
                SELECT
                    tradingsymbol,
                    instrument_type,
                    strike,
                    direction,
                    quantity,
                    entry_price,
                    lot_size,
                    current_price
                FROM strategy_instruments
                WHERE strategy_id = $1
            """, strategy_id)

            if not instruments:
                raise ValueError(f"No instruments found for strategy {strategy_id}")

            # Auto-detect spot price if not provided
            if spot_price is None:
                spot_price = await self._detect_spot_price(conn, instruments)

            # Convert to opstrat format
            op_list = self._convert_to_opstrat_format(instruments)

            # Generate payoff diagram
            payoff_image, payoff_data = self._generate_payoff_diagram(
                op_list, spot_price, spot_range
            )

            # Calculate risk metrics
            risk_metrics = self._calculate_risk_metrics(payoff_data, op_list)

            return {
                "spot_price": spot_price,
                "spot_range": spot_range,
                "payoff_image": payoff_image,
                "payoff_data": payoff_data,
                **risk_metrics
            }

    def _convert_to_opstrat_format(self, instruments: List) -> List[Dict]:
        """
        Convert strategy instruments to opstrat format.

        Args:
            instruments: List of strategy_instruments records

        Returns:
            List of opstrat option dictionaries
        """
        op_list = []

        for inst in instruments:
            # Skip non-options (futures, equity)
            if inst['instrument_type'] not in ('CE', 'PE'):
                continue

            op_dict = {
                'op_type': 'c' if inst['instrument_type'] == 'CE' else 'p',
                'strike': float(inst['strike']),
                'tr_type': 'b' if inst['direction'] == 'BUY' else 's',
                'op_pr': float(inst['entry_price'])
            }
            op_list.append(op_dict)

        return op_list

    def _generate_payoff_diagram(
        self,
        op_list: List[Dict],
        spot_price: float,
        spot_range: int
    ) -> Tuple[str, List[Dict]]:
        """
        Generate payoff diagram using opstrat.

        Args:
            op_list: List of opstrat option dictionaries
            spot_price: Current spot price
            spot_range: Percentage range for spot price variation

        Returns:
            (base64_encoded_png, payoff_data_list)
        """
        # Use opstrat to generate diagram
        fig, ax = plt.subplots(figsize=(12, 7))

        # Call opstrat multi_plotter
        # Note: opstrat doesn't return data, only plots
        # We need to calculate payoff data ourselves
        spot_min = spot_price * (1 - spot_range / 100)
        spot_max = spot_price * (1 + spot_range / 100)
        spot_prices = range(int(spot_min), int(spot_max), int((spot_max - spot_min) / 100))

        payoff_data = []
        for spot in spot_prices:
            pnl = self._calculate_payoff_at_spot(op_list, spot)
            payoff_data.append({"spot": spot, "pnl": round(pnl, 2)})

        # Plot manually (since we need data)
        spots = [d['spot'] for d in payoff_data]
        pnls = [d['pnl'] for d in payoff_data]

        ax.plot(spots, pnls, linewidth=2, color='blue', label='Strategy Payoff')
        ax.axhline(y=0, color='black', linestyle='--', linewidth=1, alpha=0.5)
        ax.axvline(x=spot_price, color='orange', linestyle='--', linewidth=1,
                   alpha=0.7, label=f'Current Spot: {spot_price:.2f}')
        ax.fill_between(spots, 0, pnls, where=[p >= 0 for p in pnls],
                        color='green', alpha=0.3, label='Profit')
        ax.fill_between(spots, 0, pnls, where=[p < 0 for p in pnls],
                        color='red', alpha=0.3, label='Loss')

        ax.set_xlabel('Spot Price at Expiry', fontsize=12)
        ax.set_ylabel('Profit/Loss (₹)', fontsize=12)
        ax.set_title('Strategy Payoff Diagram', fontsize=14, fontweight='bold')
        ax.legend(loc='best')
        ax.grid(True, alpha=0.3)

        # Convert to base64
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=100, bbox_inches='tight')
        buf.seek(0)
        img_base64 = base64.b64encode(buf.read()).decode('utf-8')
        plt.close(fig)

        return img_base64, payoff_data

    def _calculate_payoff_at_spot(self, op_list: List[Dict], spot: float) -> float:
        """
        Calculate strategy payoff at a given spot price.

        Formula:
            For CALL option:
                Long (buy):  max(spot - strike, 0) - premium
                Short (sell): premium - max(spot - strike, 0)
            For PUT option:
                Long (buy):  max(strike - spot, 0) - premium
                Short (sell): premium - max(strike - spot, 0)

        Args:
            op_list: List of opstrat option dictionaries
            spot: Spot price at expiry

        Returns:
            Total payoff (P&L)
        """
        total_pnl = 0.0

        for op in op_list:
            strike = op['strike']
            premium = op['op_pr']
            is_call = (op['op_type'] == 'c')
            is_long = (op['tr_type'] == 'b')

            if is_call:
                intrinsic_value = max(spot - strike, 0)
            else:  # put
                intrinsic_value = max(strike - spot, 0)

            if is_long:
                pnl = intrinsic_value - premium
            else:  # short
                pnl = premium - intrinsic_value

            total_pnl += pnl

        return total_pnl

    def _calculate_risk_metrics(
        self,
        payoff_data: List[Dict],
        op_list: List[Dict]
    ) -> Dict:
        """
        Calculate risk metrics from payoff data.

        Returns:
            {
                "max_profit": float,
                "max_loss": float,
                "breakeven_points": List[float],
                "risk_reward_ratio": float
            }
        """
        pnls = [d['pnl'] for d in payoff_data]
        spots = [d['spot'] for d in payoff_data]

        max_profit = max(pnls)
        max_loss = min(pnls)

        # Find breakeven points (where PnL crosses zero)
        breakeven_points = []
        for i in range(len(pnls) - 1):
            if (pnls[i] <= 0 < pnls[i+1]) or (pnls[i] >= 0 > pnls[i+1]):
                # Linear interpolation
                breakeven = spots[i] + (spots[i+1] - spots[i]) * abs(pnls[i]) / abs(pnls[i+1] - pnls[i])
                breakeven_points.append(round(breakeven, 2))

        # Risk-reward ratio
        risk_reward_ratio = abs(max_profit / max_loss) if max_loss != 0 else float('inf')

        return {
            "max_profit": round(max_profit, 2),
            "max_loss": round(max_loss, 2),
            "breakeven_points": breakeven_points,
            "risk_reward_ratio": round(risk_reward_ratio, 2)
        }

    async def _detect_spot_price(self, conn, instruments: List) -> float:
        """
        Auto-detect spot price from instruments' current_price or underlying.

        Args:
            conn: Database connection
            instruments: List of strategy instruments

        Returns:
            Detected spot price
        """
        # For options, use underlying symbol to get spot price
        underlying_symbols = {
            inst['tradingsymbol'].replace('CE', '').replace('PE', '').replace('FUT', '')[:5]
            for inst in instruments
            if inst['instrument_type'] in ('CE', 'PE')
        }

        if underlying_symbols:
            # Try to get NIFTY or BANKNIFTY current price
            # For now, use a default or fetch from instruments table
            # This should ideally fetch from Redis cache or Ticker Service
            return 23500.0  # Default NIFTY spot (TODO: Fetch real-time)

        # Fallback: Use average current_price
        prices = [float(inst['current_price']) for inst in instruments if inst['current_price']]
        return sum(prices) / len(prices) if prices else 100.0
```

---

## 3. Backend: Greeks Service

### 3.1 GreeksService Class

**File**: `backend/app/services/greeks_service.py`

```python
"""
Strategy Greeks Calculation Service

Calculates net Greeks (Delta, Gamma, Theta, Vega) for option strategies.
"""

from typing import Dict, List, Optional
from decimal import Decimal


class GreeksService:
    """
    Service for calculating strategy Greeks.
    """

    def __init__(self, db_pool):
        self.db = db_pool

    async def get_strategy_greeks(
        self,
        strategy_id: int,
        include_instrument_greeks: bool = False
    ) -> Dict:
        """
        Get net Greeks for a strategy.

        Args:
            strategy_id: Strategy ID
            include_instrument_greeks: Include per-instrument Greeks breakdown

        Returns:
            {
                "net_delta": 0.12,
                "net_gamma": 0.003,
                "net_theta": -150.5,
                "net_vega": 45.2,
                "avg_iv": 18.5,
                "instrument_greeks": [...]  # If include_instrument_greeks=True
            }
        """
        async with self.db.acquire() as conn:
            # Use the database function we created in migration 024
            result = await conn.fetchrow("""
                SELECT * FROM get_strategy_greeks($1)
            """, strategy_id)

            response = {
                "net_delta": float(result['net_delta']) if result['net_delta'] else 0.0,
                "net_gamma": float(result['net_gamma']) if result['net_gamma'] else 0.0,
                "net_theta": float(result['net_theta']) if result['net_theta'] else 0.0,
                "net_vega": float(result['net_vega']) if result['net_vega'] else 0.0,
                "avg_iv": float(result['avg_iv']) if result['avg_iv'] else 0.0,
            }

            # Include per-instrument breakdown if requested
            if include_instrument_greeks:
                instrument_greeks = await self._get_instrument_greeks(conn, strategy_id)
                response['instrument_greeks'] = instrument_greeks

            return response

    async def _get_instrument_greeks(self, conn, strategy_id: int) -> List[Dict]:
        """
        Get Greeks for each instrument in the strategy.

        Returns:
            List of instrument Greeks with weighted values
        """
        instruments = await conn.fetch("""
            SELECT
                si.tradingsymbol,
                si.instrument_type,
                si.strike,
                si.direction,
                si.quantity,
                si.lot_size,
                i.delta,
                i.gamma,
                i.theta,
                i.vega,
                i.iv
            FROM strategy_instruments si
            LEFT JOIN instruments i ON si.tradingsymbol = i.tradingsymbol
                                    AND si.exchange = i.exchange
            WHERE si.strategy_id = $1
              AND si.instrument_type IN ('CE', 'PE')
        """, strategy_id)

        result = []
        for inst in instruments:
            direction_multiplier = 1 if inst['direction'] == 'BUY' else -1
            position_size = inst['quantity'] * (inst['lot_size'] or 1)

            result.append({
                "tradingsymbol": inst['tradingsymbol'],
                "instrument_type": inst['instrument_type'],
                "strike": float(inst['strike']) if inst['strike'] else None,
                "direction": inst['direction'],
                "quantity": inst['quantity'],
                "lot_size": inst['lot_size'],
                "delta": float(inst['delta']) if inst['delta'] else 0.0,
                "gamma": float(inst['gamma']) if inst['gamma'] else 0.0,
                "theta": float(inst['theta']) if inst['theta'] else 0.0,
                "vega": float(inst['vega']) if inst['vega'] else 0.0,
                "iv": float(inst['iv']) if inst['iv'] else 0.0,
                "weighted_delta": float(inst['delta'] or 0) * direction_multiplier * position_size,
                "weighted_gamma": float(inst['gamma'] or 0) * direction_multiplier * position_size,
                "weighted_theta": float(inst['theta'] or 0) * direction_multiplier * position_size,
                "weighted_vega": float(inst['vega'] or 0) * direction_multiplier * position_size,
            })

        return result
```

---

## 4. Backend: API Endpoints

### 4.1 Add to `backend/app/routes/strategies.py`

```python
from app.services.payoff_service import PayoffService
from app.services.greeks_service import GreeksService

# Initialize services (at module level)
payoff_service = None
greeks_service = None


@router.on_event("startup")
async def init_services():
    """Initialize services with database pool."""
    global payoff_service, greeks_service
    pool = get_db_pool()
    payoff_service = PayoffService(pool)
    greeks_service = GreeksService(pool)


@router.get(
    "/{strategy_id}/payoff",
    response_model=Dict,
    summary="Get strategy payoff diagram"
)
async def get_strategy_payoff(
    strategy_id: int = Path(..., description="Strategy ID"),
    account_id: str = Query(..., description="Trading account ID"),
    spot_price: Optional[float] = Query(None, description="Current spot price (auto-detect if not provided)"),
    spot_range: int = Query(20, ge=5, le=50, description="Spot price range percentage"),
    jwt_payload: Dict[str, Any] = Depends(verify_jwt_token),
    pool=Depends(get_db_pool)
):
    """
    Generate payoff diagram for a strategy.

    Returns:
        - payoff_image: Base64-encoded PNG image
        - max_profit: Maximum profit at expiry
        - max_loss: Maximum loss at expiry
        - breakeven_points: List of breakeven spot prices
        - payoff_data: List of {spot, pnl} data points
    """
    try:
        await verify_strategy_access(pool, strategy_id, account_id)

        result = await payoff_service.generate_payoff_data(
            strategy_id=strategy_id,
            spot_price=spot_price,
            spot_range=spot_range
        )

        return result

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to generate payoff diagram: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/{strategy_id}/greeks",
    response_model=Dict,
    summary="Get strategy Greeks"
)
async def get_strategy_greeks(
    strategy_id: int = Path(..., description="Strategy ID"),
    account_id: str = Query(..., description="Trading account ID"),
    include_instruments: bool = Query(False, description="Include per-instrument Greeks"),
    jwt_payload: Dict[str, Any] = Depends(verify_jwt_token),
    pool=Depends(get_db_pool)
):
    """
    Get net Greeks for a strategy.

    Returns:
        - net_delta: Net delta (positive = long, negative = short)
        - net_gamma: Net gamma
        - net_theta: Net theta (time decay)
        - net_vega: Net vega (IV sensitivity)
        - avg_iv: Average implied volatility
        - instrument_greeks: (Optional) Per-instrument breakdown
    """
    try:
        await verify_strategy_access(pool, strategy_id, account_id)

        result = await greeks_service.get_strategy_greeks(
            strategy_id=strategy_id,
            include_instrument_greeks=include_instruments
        )

        return result

    except Exception as e:
        logger.error(f"Failed to get strategy Greeks: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
```

---

## 5. Frontend: StrategyPayoffPanel Component

### 5.1 Component Specification

**File**: `frontend/src/components/tradingDashboard/StrategyPayoffPanel.tsx`

**Purpose**: Display payoff diagram and risk metrics for selected strategy

**Features**:
- Payoff diagram image (from API)
- Max profit, max loss display
- Breakeven points highlighted
- Risk-reward ratio badge
- Spot price adjustment slider

**Design**:
```
┌─────────────────────────────────────────────────────────────┐
│ Strategy Payoff Analysis                                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   ┌─────────────────────────────────────────────────────┐ │
│   │                                                     │ │
│   │         Payoff Diagram (PNG Image)                 │ │
│   │                                                     │ │
│   │   [Profit/Loss curve with green/red shading]      │ │
│   │                                                     │ │
│   └─────────────────────────────────────────────────────┘ │
│                                                             │
│   Spot Price: [─────⬤─────────] 23500                     │
│               22000         25000                          │
│                                                             │
│   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │
│   │ Max Profit   │  │ Max Loss     │  │ Risk:Reward  │   │
│   │ ₹ 5,000      │  │ ₹ -15,000    │  │ 1 : 3        │   │
│   └──────────────┘  └──────────────┘  └──────────────┘   │
│                                                             │
│   Breakeven Points: 23,350 • 23,650                        │
│                                                             │
│   [Refresh Payoff]                                         │
└─────────────────────────────────────────────────────────────┘
```

### 5.2 TypeScript Interface

```typescript
interface PayoffData {
  spot_price: number;
  spot_range: number;
  payoff_image: string;  // base64 PNG
  max_profit: number;
  max_loss: number;
  breakeven_points: number[];
  risk_reward_ratio: number;
  payoff_data: Array<{ spot: number; pnl: number }>;
}
```

### 5.3 Service Function

**File**: `frontend/src/services/strategies.ts`

```typescript
export async function getStrategyPayoff(
  strategyId: number,
  accountId: string,
  spotPrice?: number,
  spotRange: number = 20
): Promise<PayoffData> {
  const params = new URLSearchParams({
    account_id: accountId,
    spot_range: spotRange.toString(),
  });
  if (spotPrice !== undefined) {
    params.append('spot_price', spotPrice.toString());
  }

  const response = await fetch(
    `${API_BASE}/strategies/${strategyId}/payoff?${params}`,
    {
      headers: {
        Authorization: `Bearer ${getToken()}`,
      },
    }
  );

  if (!response.ok) {
    throw new Error('Failed to fetch payoff data');
  }

  return response.json();
}
```

---

## 6. Frontend: StrategyGreeksPanel Component

### 6.1 Component Specification

**File**: `frontend/src/components/tradingDashboard/StrategyGreeksPanel.tsx`

**Purpose**: Display net Greeks and position sensitivities

**Design**:
```
┌─────────────────────────────────────────────────────────────┐
│ Strategy Greeks                                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   Net Position Greeks                                       │
│   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │
│   │ Delta        │  │ Gamma        │  │ Theta        │   │
│   │ +0.12        │  │ +0.003       │  │ -150.50      │   │
│   │ Directional  │  │ Convexity    │  │ Time Decay   │   │
│   └──────────────┘  └──────────────┘  └──────────────┘   │
│                                                             │
│   ┌──────────────┐  ┌──────────────┐                      │
│   │ Vega         │  │ Avg IV       │                      │
│   │ +45.20       │  │ 18.5%        │                      │
│   │ IV Sensitivity│  │ Volatility   │                      │
│   └──────────────┘  └──────────────┘                      │
│                                                             │
│   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│                                                             │
│   Instrument Breakdown                 [Show Details ▼]    │
│                                                             │
│   ┌─────────────────────────────────────────────────────┐ │
│   │ Symbol           Delta  Gamma  Theta  Vega   IV    │ │
│   ├─────────────────────────────────────────────────────┤ │
│   │ NIFTY 23400 CE   +0.65  0.005  -50    +20   17.2% │ │
│   │ NIFTY 23500 CE   -0.55  0.004  +45    -18   18.1% │ │
│   │ ...                                                  │ │
│   └─────────────────────────────────────────────────────┘ │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 6.2 TypeScript Interface

```typescript
interface GreeksData {
  net_delta: number;
  net_gamma: number;
  net_theta: number;
  net_vega: number;
  avg_iv: number;
  instrument_greeks?: Array<{
    tradingsymbol: string;
    instrument_type: string;
    strike: number;
    direction: 'BUY' | 'SELL';
    quantity: number;
    lot_size: number;
    delta: number;
    gamma: number;
    theta: number;
    vega: number;
    iv: number;
    weighted_delta: number;
    weighted_gamma: number;
    weighted_theta: number;
    weighted_vega: number;
  }>;
}
```

---

## 7. Implementation Plan

### Phase 1: Backend Setup (2-3 hours)
1. Install opstrat: `pip install opstrat==0.1.7`
2. Create `backend/app/services/payoff_service.py`
3. Create `backend/app/services/greeks_service.py`
4. Add API endpoints to `backend/app/routes/strategies.py`
5. Test endpoints with Postman/curl

### Phase 2: Frontend Components (2-3 hours)
6. Create `StrategyPayoffPanel.tsx` component
7. Create `StrategyGreeksPanel.tsx` component
8. Add service functions to `frontend/src/services/strategies.ts`
9. Integrate into `TradingDashboard.tsx`

### Phase 3: Testing & Polish (1-2 hours)
10. Test with Iron Condor test strategy
11. Verify Greeks calculations
12. Add loading states and error handling
13. Style improvements

**Total Estimated Time**: 5-8 hours (1 day)

---

## 8. Database Considerations

### Greeks Data Source

The Greeks are already available in the database:

**From migration 024** (`backend/migrations/024_add_instrument_metadata_to_strategies.sql`):

```sql
-- Function already exists
CREATE OR REPLACE FUNCTION get_strategy_greeks(p_strategy_id INTEGER)
RETURNS TABLE (
  net_delta NUMERIC,
  net_gamma NUMERIC,
  net_theta NUMERIC,
  net_vega NUMERIC,
  avg_iv NUMERIC
) AS $$
BEGIN
  RETURN QUERY
  SELECT
    SUM(
      CASE
        WHEN si.direction = 'BUY' THEN si.quantity * si.lot_size * i.delta
        WHEN si.direction = 'SELL' THEN -1 * si.quantity * si.lot_size * i.delta
        ELSE 0
      END
    ) as net_delta,
    -- ... (gamma, theta, vega similar)
  FROM strategy_instruments si
  LEFT JOIN instruments i ON si.tradingsymbol = i.tradingsymbol
                          AND si.exchange = i.exchange
  WHERE si.strategy_id = p_strategy_id
    AND si.instrument_type IN ('CE', 'PE')
  GROUP BY si.strategy_id;
END;
$$ LANGUAGE plpgsql;
```

**No new migrations needed!** The database is already ready for Day 4.

---

## 9. Testing Strategy

### Backend Testing

**Test Payoff Endpoint**:
```bash
curl -X GET "http://localhost:8081/strategies/2/payoff?account_id=acc123&spot_range=20" \
  -H "Authorization: Bearer $TOKEN"
```

**Expected Response**:
```json
{
  "spot_price": 23500.0,
  "spot_range": 20,
  "payoff_image": "iVBORw0KGgoAAAANSUhEUgAA...",
  "max_profit": 5000.0,
  "max_loss": -15000.0,
  "breakeven_points": [23350.0, 23650.0],
  "risk_reward_ratio": 3.0,
  "payoff_data": [
    {"spot": 22000, "pnl": -10000},
    {"spot": 22100, "pnl": -8500},
    ...
  ]
}
```

**Test Greeks Endpoint**:
```bash
curl -X GET "http://localhost:8081/strategies/2/greeks?account_id=acc123&include_instruments=true" \
  -H "Authorization: Bearer $TOKEN"
```

**Expected Response**:
```json
{
  "net_delta": 0.12,
  "net_gamma": 0.003,
  "net_theta": -150.5,
  "net_vega": 45.2,
  "avg_iv": 18.5,
  "instrument_greeks": [
    {
      "tradingsymbol": "NIFTY25N1123400CE",
      "instrument_type": "CE",
      "strike": 23400.0,
      "direction": "BUY",
      "quantity": 1,
      "lot_size": 75,
      "delta": 0.65,
      "gamma": 0.005,
      "theta": -50.0,
      "vega": 20.0,
      "iv": 17.2,
      "weighted_delta": 48.75,
      "weighted_gamma": 0.375,
      "weighted_theta": -3750.0,
      "weighted_vega": 1500.0
    }
  ]
}
```

### Frontend Testing

1. **Payoff Panel**:
   - Select strategy with options
   - Verify payoff diagram loads
   - Adjust spot price slider
   - Check max profit/loss values
   - Verify breakeven points displayed

2. **Greeks Panel**:
   - Verify net Greeks displayed correctly
   - Toggle instrument breakdown
   - Check weighted Greeks calculation
   - Verify color coding (positive/negative)

---

## 10. Key Design Decisions

### 1. Why opstrat?
- **Mature library**: Well-maintained, 0.1.7 stable release
- **Simple API**: Easy to integrate with our data model
- **Visualization**: Handles complex multi-leg strategies
- **No need to build from scratch**: Saves development time

### 2. Image vs. Data?
- **Initial**: Return base64-encoded PNG image (simple, works everywhere)
- **Future Enhancement**: Can return raw payoff_data for custom charting (Recharts, D3)

### 3. Real-time Greeks vs. Static?
- **Current**: Fetch Greeks from `instruments` table (updated by ticker service)
- **Future**: Real-time Greeks streaming via WebSocket

### 4. Spot Price Detection
- **Auto-detect**: Try to infer from underlying symbol
- **Manual Override**: Allow user to adjust via slider
- **Default**: Use sensible default (23500 for NIFTY)

---

## 11. Success Criteria

- [ ] Backend: PayoffService implemented with opstrat
- [ ] Backend: GreeksService implemented using database function
- [ ] Backend: API endpoints added and tested
- [ ] Frontend: StrategyPayoffPanel displays diagram correctly
- [ ] Frontend: StrategyGreeksPanel shows net Greeks
- [ ] Frontend: Spot price slider updates payoff diagram
- [ ] Frontend: Instrument Greeks breakdown toggleable
- [ ] Testing: Works with Iron Condor test strategy (strategy_id=2)
- [ ] Testing: Max profit, max loss, breakeven points calculated correctly
- [ ] Testing: Net Greeks match manual calculation

---

## 12. Phase 2.5 Progress

**Day 1**: ✅ Database & Backend APIs (Complete)
**Day 2**: ✅ M2M Calculation Engine (Complete)
**Day 3**: ⏸️ Frontend Components (Pending - Design Ready)
**Day 4**: 📝 Payoff Graphs & Greeks (Design Complete - Ready to Implement)
**Day 5**: 📋 Polish & Testing (Planned)

**Overall Progress**: 40% complete (2 of 5 days implemented)

---

## 13. Next Steps

Once Day 4 design is approved:

1. **Implement Backend**:
   - Install opstrat
   - Create PayoffService
   - Create GreeksService
   - Add API endpoints
   - Test with curl/Postman

2. **Implement Frontend**:
   - Build StrategyPayoffPanel
   - Build StrategyGreeksPanel
   - Integrate with dashboard

3. **Test End-to-End**:
   - Use test Iron Condor strategy (strategy_id=2)
   - Verify payoff diagram accuracy
   - Verify Greeks calculations
   - Polish UI/UX

---

## 14. Optional Enhancements (Future)

1. **Interactive Payoff Chart**: Use Recharts instead of static PNG
2. **Greeks Timeline**: Historical Greeks tracking over time
3. **What-If Analysis**: Adjust volatility, time to expiry
4. **Strategy Comparison**: Compare multiple strategies side-by-side
5. **Risk Alerts**: Notify when Greeks exceed thresholds
6. **Custom Payoff Overlays**: Show payoff at different dates before expiry

---

## Ready for Day 4 Implementation! 🚀

The design is complete and ready for implementation. Day 4 will add powerful analytics and visualization to the Strategy System using the industry-standard opstrat library.
