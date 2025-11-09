# Smart Order Management System - Quick Reference

**Date**: 2025-11-09
**Full Design**: [SMART_ORDER_MANAGEMENT_DESIGN.md](./SMART_ORDER_MANAGEMENT_DESIGN.md)

---

## Overview

A comprehensive order management system addressing:
1. ✅ Automated housekeeping (orphaned SL/Target orders)
2. ✅ Market depth-based smart execution
3. ✅ Pre-trade margin & cost calculation
4. ✅ Additional production-ready features

---

## Key Features by Category

### 1. Order Housekeeping

**Problem**: When positions are exited, SL/Target orders remain active

**Solution**: Automatic Order Reconciliation
- Detects orphaned orders within 5 minutes
- Auto-cancels based on user preference
- User override option: `allow_orphaned_orders: true`

**Triggers**:
- Position closed
- Order filled
- Instrument expired
- End-of-day reconciliation
- Manual user trigger

**Configuration** (`strategy_settings` table):
```python
{
  "auto_cleanup_enabled": true,           # Enable auto-cleanup
  "cleanup_sl_on_exit": true,             # Cancel SL on position exit
  "cleanup_target_on_exit": true,         # Cancel Target on exit
  "allow_orphaned_orders": false,         # Strict mode
  "notify_on_orphan_detection": true      # Alert user
}
```

---

### 2. Market Depth-Based Smart Execution

**Problem**: Wide spreads and illiquid instruments cause slippage

**Solution**: Smart Order Execution Engine

**Workflow**:
```
Order Request → Fetch Market Depth → Analyze Spread → Calculate Impact → Decision
```

**Spread Analysis**:
| Spread % | Category | Action |
|----------|----------|--------|
| < 0.2% (options) | Tight | Execute MARKET order |
| 0.2-0.5% | Normal | Execute LIMIT order |
| 0.5-1.0% | Wide | LIMIT order + Alert user |
| > 1.0% | Very Wide | Require user approval |

**Market Impact Calculation**:
- Walks through order book levels
- Calculates weighted average fill price
- Estimates impact in basis points (bps)
- Warns if impact > 50 bps

**Decision Matrix**:
| Spread | Impact (bps) | Liquidity | Action |
|--------|--------------|-----------|--------|
| Tight | 0-10 | HIGH | EXECUTE_MARKET |
| Normal | 10-50 | MEDIUM | EXECUTE_LIMIT |
| Wide | >50 | LOW | ALERT_USER_HIGH_COST |
| Very Wide | * | ILLIQUID | REQUIRE_APPROVAL |

**User Alerts**:
```
⚠️  Wide Bid-Ask Spread Detected
Spread is 0.8% (₹4). Estimated slippage: ₹400
Impact: 45 bps

[ Cancel ]  [ Use LIMIT Order ]  [ Proceed Anyway ]
```

---

### 3. Margin & Brokerage Calculation

**Problem**: Users don't know upfront costs before entering strategy

**Solution**: Pre-Trade Cost Calculator

**Kite Brokerage Rates**:
- Equity Delivery: FREE
- Equity Intraday: 0.03% or ₹20 (whichever lower)
- Futures: 0.03% or ₹20 (whichever lower)
- Options: Flat ₹20 per order

**Tax Breakdown**:
| Tax/Charge | Rate | Applied On |
|------------|------|------------|
| STT (Options Sell) | 0.05% | Premium |
| STT (Futures Sell) | 0.0125% | Turnover |
| Exchange Charges (NFO) | 0.005% | Turnover |
| GST | 18% | Brokerage + Exchange Charges |
| SEBI Charges | ₹10/crore | Turnover |
| Stamp Duty | 0.002% | Buy-side turnover |

**API Endpoint**:
```python
POST /strategies/{id}/calculate-costs

Request:
{
  "instruments": [
    {
      "symbol": "NIFTY25DEC24500CE",
      "quantity": 100,
      "price": 150.50,
      "side": "BUY"
    }
  ]
}

Response:
{
  "total_entry_cost": 125085,
  "total_exit_cost": 124500,
  "breakdown": {
    "order_value": 123450,
    "brokerage": 120,
    "stt": 280,
    "exchange_charges": 40,
    "gst": 29,
    "sebi_charges": 1,
    "stamp_duty": 25,
    "total_charges": 495
  },
  "margin": {
    "required": 45000,
    "available": 60000,
    "remaining": 15000,
    "can_execute": true
  },
  "warnings": []
}
```

**Pre-Trade Confirmation UI**:
```
┌─────────────────────────────────────────────┐
│  Strategy Cost Breakdown                    │
├─────────────────────────────────────────────┤
│  Entry Cost:          ₹ 1,25,085            │
│  Exit Cost (est):     ₹ 1,24,500            │
│                                             │
│  Breakdown:                                 │
│    Order Value:       ₹ 1,23,450            │
│    Brokerage:         ₹     120             │
│    STT:               ₹     280             │
│    GST:               ₹      29             │
│    Other Charges:     ₹      66             │
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
```

---

### 4. Additional Housekeeping Tasks

#### a) End-of-Day Reconciliation
**Runs**: 3:30 PM daily

**Tasks**:
- Reconcile positions with broker
- Match orders with broker order book
- Calculate realized P&L
- Archive completed orders
- Generate EOD reports

#### b) Intraday Auto Square-Off
**Runs**: 3:15-3:25 PM (for MIS positions)

**Timing**:
- 3:15 PM: Warning notification
- 3:20 PM: Start auto square-off
- 3:25 PM: Force square-off remaining

#### c) Expired Instrument Cleanup
**Runs**: 9:00 AM daily

**Actions**:
- Cancel orders for expired instruments
- Archive expired positions
- Update strategy P&L
- Notify users

#### d) Order Aging & Timeout
**Runs**: Every 15 minutes

**Logic**:
- Orders > 1 hour: Notify user
- Orders > 4 hours: Auto-cancel (if configured)
- Orders > 1 day: Archive

#### e) Strategy P&L Snapshot
**Runs**: Every 5 minutes during market hours

**Captures**:
- Current positions
- Open orders
- Realized/Unrealized P&L
- Margin used
- Greeks (F&O)

Used for M2M charts and analytics.

#### f) Risk Limit Monitoring
**Runs**: Real-time

**Limits** (configurable):
```python
{
  "max_loss_per_strategy_pct": 10,      # 10% loss → auto square-off
  "max_loss_per_strategy_abs": 50000,   # ₹50k loss
  "max_position_size_per_instrument": 1000,
  "max_orders_per_minute": 10,
  "max_margin_utilization_pct": 90      # 90% margin usage
}
```

**Actions on breach**:
1. Stop new orders
2. Alert user
3. Auto square-off (if enabled)
4. Log event

#### g) Broker API Health Check
**Runs**: Every 1 minute

**Checks**:
- API reachability
- Token validity
- WebSocket connection
- Order placement latency

**Actions on failure**:
- Retry connection
- Refresh tokens
- Pause order placement
- Alert user

#### h) Data Reconciliation
**Runs**: Hourly

**Compares**:
- Internal positions vs broker positions
- Internal orders vs broker orders

**Detects**:
- Quantity mismatch
- Missing positions
- Phantom positions
- Price discrepancies

#### i) Audit Trail
**Continuous logging**

**Events logged**:
- ORDER_CREATED
- ORDER_PLACED
- ORDER_MODIFIED
- ORDER_CANCELLED
- ORDER_FILLED
- ORDER_REJECTED
- ORDER_EXPIRED

**Retention**: 7 years (compliance)

---

## Database Schema Summary

### New Tables

1. **`strategy_settings`**
   - Housekeeping preferences
   - Smart execution settings
   - Risk limits
   - Margin buffers

2. **`order_execution_analysis`**
   - Pre-execution market depth analysis
   - Spread metrics
   - Market impact estimation
   - Execution recommendations

3. **`order_cost_breakdown`**
   - Brokerage calculation
   - Tax breakdown (STT, GST, etc.)
   - Margin requirements
   - Net cost

4. **`housekeeping_events`**
   - Cleanup actions log
   - Reconciliation results
   - Automated task execution

5. **`user_alerts`**
   - Spread warnings
   - Impact alerts
   - Margin warnings
   - Risk limit breaches

### Modified Tables

**`orders`** table additions:
- `pre_execution_analysis_id`
- `cost_breakdown_id`
- `is_orphaned`
- `orphaned_reason`
- `parent_position_id`

**`strategies`** table additions:
- `total_brokerage_paid`
- `total_taxes_paid`
- `total_margin_blocked`
- `risk_status`
- `last_housekeeping_run`

---

## API Endpoints Summary

### Housekeeping
```
POST   /strategies/{id}/reconcile-orders
POST   /strategies/{id}/cleanup-orphaned-orders
GET    /strategies/{id}/orphaned-orders
PUT    /strategies/{id}/settings
```

### Smart Execution
```
POST   /orders/analyze-execution
POST   /orders/validate-spread
POST   /orders/estimate-impact
```

### Margin Calculation
```
POST   /strategies/{id}/calculate-margin
POST   /orders/calculate-costs
GET    /accounts/{id}/available-margin
```

### Alerts
```
GET    /users/{id}/alerts
POST   /alerts/{id}/respond
PUT    /alerts/{id}/mark-read
```

### Admin/Housekeeping
```
POST   /admin/housekeeping/eod
POST   /admin/housekeeping/reconcile-all
GET    /admin/housekeeping/logs
```

---

## Implementation Roadmap

| Phase | Duration | Features |
|-------|----------|----------|
| **Phase 1: Foundation** | Week 1-2 | Database schema, base classes |
| **Phase 2: Order Housekeeping** | Week 3-4 | Orphan detection, auto-cleanup, EOD tasks |
| **Phase 3: Smart Execution** | Week 5-6 | Market depth integration, alerts |
| **Phase 4: Margin Calculation** | Week 7-8 | Kite API, cost calculator |
| **Phase 5: Additional Housekeeping** | Week 9-10 | Square-off, reconciliation, risk limits |
| **Phase 6: Testing** | Week 11-12 | Unit, integration, load testing |
| **Phase 7: Deployment** | Week 13 | Documentation, staging, production |

**Total**: ~13 weeks (3 months)

---

## Configuration Examples

### Conservative Strategy
```json
{
  "auto_cleanup_enabled": true,
  "cleanup_sl_on_exit": true,
  "max_order_spread_pct": 0.3,
  "min_liquidity_score": 70,
  "require_user_approval_high_impact": true,
  "max_market_impact_bps": 30,
  "margin_buffer_pct": 20.0,
  "max_loss_per_strategy_pct": 5.0,
  "auto_square_off_on_loss_limit": true
}
```

### Aggressive Strategy
```json
{
  "auto_cleanup_enabled": false,
  "allow_orphaned_orders": true,
  "max_order_spread_pct": 1.0,
  "min_liquidity_score": 40,
  "require_user_approval_high_impact": false,
  "margin_buffer_pct": 5.0,
  "max_loss_per_strategy_pct": 15.0
}
```

---

## Success Metrics

**Execution Quality**:
- ✅ Average slippage < 0.2% for liquid instruments
- ✅ 95%+ orders executed at expected price or better
- ✅ User alert response rate > 80%

**Housekeeping Efficiency**:
- ✅ Orphaned orders detected within 5 minutes
- ✅ 100% expired instruments cleaned up next day
- ✅ Zero position-order discrepancies at EOD

**Cost Transparency**:
- ✅ 100% orders have pre-execution cost breakdown
- ✅ Margin calculation accuracy > 99.5%

**Risk Management**:
- ✅ Risk breaches detected < 1 second
- ✅ Auto square-off within 30 seconds
- ✅ Zero manual intervention for routine tasks

---

## Next Steps

1. **Review & Prioritize**: Identify MVP features vs. nice-to-have
2. **Database Setup**: Create schema (Phase 1)
3. **Kite Sandbox**: Set up test environment
4. **Phase 2 Start**: Begin order housekeeping implementation

---

**Full Technical Specification**: See [SMART_ORDER_MANAGEMENT_DESIGN.md](./SMART_ORDER_MANAGEMENT_DESIGN.md)
