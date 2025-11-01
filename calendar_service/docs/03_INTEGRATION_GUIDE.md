# Calendar Service - Complete Integration Guide

**Date**: November 1, 2025
**Status**: DEPLOYED AND INTEGRATED ✅

---

## 🎯 Overview

The calendar service is now fully integrated into the trading platform. This guide covers:
1. How future holidays are synchronized
2. Special trading sessions (Muhurat)
3. Python SDK usage
4. Docker-compose configuration
5. Development vs Production modes

---

## 1. Future Holiday Synchronization

### Three Synchronization Approaches

#### **Option A: Monthly Cron Job** (Recommended for Production)

Set up automatic monthly sync:

```bash
# Create sync script
sudo nano /etc/cron.monthly/sync-holidays.sh
```

```bash
#!/bin/bash
# Sync holidays for next 2 years
docker exec tv-backend python -m app.services.holiday_fetcher --sync-all --years "2026,2027"
```

```bash
# Make executable
sudo chmod +x /etc/cron.monthly/sync-holidays.sh

# Test manually
sudo /etc/cron.monthly/sync-holidays.sh
```

**When to use**: Production systems that need automatic updates

---

#### **Option B: Manual Admin Endpoint**

Call sync endpoint when needed:

```bash
# Sync specific year
curl -X POST "http://localhost:8081/admin/calendar/sync?year=2026"

# Sync all markets
curl -X POST "http://localhost:8081/admin/calendar/sync-all"
```

**When to use**: Manual control, ad-hoc updates, testing

---

#### **Option C: Background Task** (Future Enhancement)

Add automatic quarterly sync in backend:

```python
# In app/main.py lifespan
async def holiday_sync_task():
    while True:
        await asyncio.sleep(86400 * 90)  # Every 90 days
        await holiday_fetcher.sync_all_markets()
```

**When to use**: Fully automated systems

---

### Current Status

✅ **Holidays populated through 2026**
📅 **Sync required before**: December 2025
🎯 **Recommended**: Set up Option A (cron job) now

---

## 2. Special Trading Sessions (Muhurat Trading)

### Schema Support

The database **fully supports** special trading sessions:

```sql
CREATE TABLE calendar_events (
    event_date DATE,
    event_name TEXT,
    is_trading_day BOOLEAN,      -- true for Muhurat
    special_start TIME,            -- 18:15 for Muhurat
    special_end TIME,              -- 19:15 for Muhurat
    category TEXT                  -- 'special_session'
);
```

### Adding Muhurat Trading for Diwali

#### Method 1: SQL Insert

```sql
-- Muhurat Trading on Diwali 2025
INSERT INTO calendar_events (
    calendar_type_id,
    event_date,
    event_name,
    event_type,
    is_trading_day,
    special_start,
    special_end,
    category,
    source
) VALUES (
    (SELECT id FROM calendar_types WHERE code = 'NSE'),
    '2025-11-01',           -- Diwali day
    'Muhurat Trading',
    'special_hours',
    true,                    -- Market IS open
    '18:15:00',             -- Evening session start
    '19:15:00',             -- Evening session end
    'special_session',
    'NSE Official'
) ON CONFLICT (calendar_type_id, event_date, event_name)
DO UPDATE SET
    is_trading_day = EXCLUDED.is_trading_day,
    special_start = EXCLUDED.special_start,
    special_end = EXCLUDED.special_end;
```

#### Method 2: API Endpoint (When Admin API is Built)

```bash
curl -X POST http://localhost:8081/admin/calendar/special-session \
  -H "Content-Type: application/json" \
  -d '{
    "calendar": "NSE",
    "date": "2025-11-01",
    "name": "Muhurat Trading",
    "start_time": "18:15:00",
    "end_time": "19:15:00"
  }'
```

### API Response for Muhurat Trading

When calling `/calendar/status` on Diwali at 18:30:

```json
{
  "calendar_code": "NSE",
  "date": "2025-11-01",
  "is_trading_day": true,
  "is_holiday": true,
  "is_weekend": true,
  "current_session": "trading",
  "holiday_name": "Muhurat Trading",
  "session_start": "18:15:00",
  "session_end": "19:15:00",
  "next_trading_day": "2025-11-03"
}
```

### Python SDK Usage for Special Sessions

```python
from stocksblitz_sdk import CalendarClient
import asyncio
from datetime import datetime

async def check_muhurat():
    async with CalendarClient() as calendar:
        status = await calendar.get_status('NSE', check_date=date(2025, 11, 1))

        if status.is_trading_day:
            print(f"✅ Special session: {status.holiday_name}")
            print(f"   Trading hours: {status.session_start} - {status.session_end}")

            # Check if we're currently in the session
            now = datetime.now().time()
            if status.session_start <= now <= status.session_end:
                print("   🔴 LIVE - Market is open NOW!")
                await place_muhurat_orders()
            else:
                print(f"   ⏰ Market opens at {status.session_start}")

asyncio.run(check_muhurat())
```

---

## 3. Python SDK - How It Works

### Architecture

```
┌─────────────────┐
│  Python Script  │
│   (Your Code)   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐     HTTP Request
│ CalendarClient  │────────────────────┐
│   (SDK Layer)   │                    │
└─────────────────┘                    ▼
                              ┌──────────────────┐
                              │   Backend API    │
                              │ /calendar/status │
                              └────────┬─────────┘
                                       │
                                       ▼
                              ┌──────────────────┐
                              │   PostgreSQL     │
                              │  calendar_events │
                              └──────────────────┘
```

**Key Point**: SDK uses REST API - no direct database access needed!

### Installation

```bash
# Install from local SDK
cd /mnt/stocksblitz-data/Quantagro/tradingview-viz/python-sdk
pip install -e .
```

### Configuration

```python
# Default (uses localhost:8081)
from stocksblitz_sdk import CalendarClient
calendar = CalendarClient()

# Custom backend URL
calendar = CalendarClient(base_url="http://backend:8000")

# For production
calendar = CalendarClient(base_url="https://api.stocksblitz.com")
```

---

## 4. Python SDK Usage Examples

### Example 1: Trading Bot with Market Hours Check

```python
from stocksblitz_sdk import CalendarClient
import asyncio
import logging

logger = logging.getLogger(__name__)

async def trading_bot():
    """Trading bot that respects market hours"""
    async with CalendarClient() as calendar:
        while True:
            try:
                # Check market status
                status = await calendar.get_status('NSE')

                if status.is_trading_day and status.current_session == "trading":
                    logger.info(f"✅ Market OPEN - Current session: {status.current_session}")
                    logger.info(f"   Trading until: {status.session_end}")

                    # Execute trading logic
                    await place_orders()
                    await monitor_positions()

                elif status.current_session == "pre-market":
                    logger.info(f"⏰ Pre-market session")
                    await prepare_orders()

                else:
                    reason = status.holiday_name or "Outside trading hours"
                    logger.info(f"❌ Market CLOSED - {reason}")
                    logger.info(f"   Next trading day: {status.next_trading_day}")

                    # Use mock data or sleep
                    await use_mock_data()

                # Check every 60 seconds
                await asyncio.sleep(60)

            except Exception as e:
                logger.error(f"Error checking market status: {e}")
                await asyncio.sleep(60)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(trading_bot())
```

### Example 2: Backtest Only on Trading Days

```python
from stocksblitz_sdk import CalendarClientSync
from datetime import date, timedelta

def run_backtest(start_date: date, end_date: date):
    """Backtest that excludes weekends and holidays"""
    calendar = CalendarClientSync()

    # Get all holidays in range
    holidays = calendar.get_holidays('NSE', year=start_date.year)
    holiday_dates = {h.date for h in holidays}

    # If multi-year backtest, get holidays for all years
    if end_date.year > start_date.year:
        for year in range(start_date.year + 1, end_date.year + 1):
            year_holidays = calendar.get_holidays('NSE', year=year)
            holiday_dates.update(h.date for h in year_holidays)

    # Iterate through date range
    current = start_date
    trading_days = []

    while current <= end_date:
        # Check if trading day
        if current.weekday() < 5 and current not in holiday_dates:
            trading_days.append(current)
        current += timedelta(days=1)

    print(f"Backtest period: {start_date} to {end_date}")
    print(f"Total days: {(end_date - start_date).days}")
    print(f"Trading days: {len(trading_days)}")
    print(f"Holidays excluded: {len(holiday_dates)}")

    # Run backtest on trading days only
    for day in trading_days:
        run_strategy_for_day(day)

# Run backtest
run_backtest(date(2024, 1, 1), date(2024, 12, 31))
```

### Example 3: Smart Scheduler

```python
from stocksblitz_sdk import CalendarClient
import asyncio
from datetime import datetime

async def market_data_collector():
    """Collect live data only during market hours"""
    async with CalendarClient() as calendar:
        while True:
            # Quick check: is market open RIGHT NOW?
            is_open = await calendar.is_market_open('NSE')

            if is_open:
                print(f"[{datetime.now()}] 🔴 Market OPEN - Collecting live data")
                await collect_live_greeks()
                await collect_option_chain()
                await update_positions()
                interval = 10  # Fast updates during market hours

            else:
                # Get detailed status to know why market is closed
                status = await calendar.get_status('NSE')
                print(f"[{datetime.now()}] ⚫ Market CLOSED - {status.holiday_name or 'Non-trading hours'}")

                # Use cached data
                await use_cached_data()
                interval = 300  # Slow checks when market is closed

            await asyncio.sleep(interval)

asyncio.run(market_data_collector())
```

### Example 4: Pre-Market Preparation

```python
from stocksblitz_sdk import CalendarClient
import asyncio
from datetime import datetime, time

async def pre_market_setup():
    """Run setup tasks before market opens"""
    async with CalendarClient() as calendar:
        # Get today's market status
        status = await calendar.get_status('NSE')

        if not status.is_trading_day:
            print(f"Market closed today: {status.holiday_name or 'Weekend'}")
            print(f"Next trading day: {status.next_trading_day}")
            return

        # Calculate time until market opens
        now = datetime.now().time()
        market_open = status.session_start  # e.g., 09:15:00

        if now < market_open:
            # We're before market hours
            print(f"Pre-market preparation")
            print(f"Market opens at: {market_open}")

            # Run preparation tasks
            await load_instruments()
            await fetch_overnight_data()
            await calculate_indicators()
            await generate_signals()

            # Wait until market opens
            wait_seconds = (datetime.combine(datetime.today(), market_open) -
                           datetime.combine(datetime.today(), now)).seconds
            print(f"Waiting {wait_seconds} seconds until market opens...")
            await asyncio.sleep(wait_seconds)

            # Market is now open
            await start_trading()

asyncio.run(pre_market_setup())
```

### Example 5: Synchronous Usage (Non-Async Scripts)

```python
from stocksblitz_sdk import CalendarClientSync

# For scripts that don't use async/await
def check_market_before_order():
    calendar = CalendarClientSync()

    # Simple check
    if calendar.is_market_open('NSE'):
        place_order()
    else:
        print("Market closed - order queued for next session")
        queue_order()

# For scheduled jobs (cron, etc.)
def daily_report():
    calendar = CalendarClientSync()
    status = calendar.get_status('NSE')

    print(f"Market Status: {status.current_session}")
    print(f"Is Trading Day: {status.is_trading_day}")

    if not status.is_trading_day:
        print(f"Holiday: {status.holiday_name}")
        print(f"Next Trading Day: {status.next_trading_day}")
```

---

## 5. Docker-Compose Integration

### ✅ NOW ADDED TO DOCKER-COMPOSE

Updated `docker-compose.yml` with calendar service environment variables:

```yaml
ticker-service:
  environment:
    # Calendar service integration
    - MARKET_MODE=force_mock          # Development mode
    - CALENDAR_API_URL=http://backend:8000
    - CALENDAR_CODE=NSE
```

### Market Mode Configuration

#### **Development Mode** (Current)
```yaml
- MARKET_MODE=force_mock
```
- Always uses MOCK data
- Works on weekends, holidays, nights
- Safe for testing anytime
- No Kite API rate limits

#### **Production Mode** (Switch When Ready)
```yaml
- MARKET_MODE=auto
```
- Automatically switches LIVE/MOCK based on calendar
- During trading hours (9:15-15:30): Uses LIVE data
- Outside trading hours: Uses MOCK data
- Respects holidays and weekends

#### **Force Live Mode** (Testing Only)
```yaml
- MARKET_MODE=force_live
```
- Always uses LIVE data
- Ignores calendar
- Use only for testing Kite API connectivity

#### **Disabled Mode**
```yaml
- MARKET_MODE=off
```
- Ticker service won't fetch any data
- Calendar not consulted

### Restart Ticker Service to Apply

```bash
# After changing docker-compose.yml
docker-compose restart ticker-service

# Verify calendar integration
docker logs tv-ticker | grep -i calendar
docker logs tv-ticker | grep -i "market.*mode"
```

### Expected Log Output

**Development mode (force_mock)**:
```
[INFO] Market mode: force_mock
[INFO] Calendar service: http://backend:8000
[INFO] Calendar code: NSE
[INFO] Account primary: Mode=MOCK | Development mode enabled
```

**Production mode during market hours (auto)**:
```
[INFO] Market mode: auto
[INFO] Checking calendar API...
[INFO] Calendar status: is_trading_day=true, current_session=trading
[INFO] Account primary: Mode=LIVE | Market open, using live data
```

**Production mode after hours (auto)**:
```
[INFO] Market mode: auto
[INFO] Checking calendar API...
[INFO] Calendar status: is_trading_day=true, current_session=closed
[INFO] Account primary: Mode=MOCK | Market closed, using mock data
```

---

## 6. Testing Calendar Integration

### Test 1: Verify Calendar API

```bash
# Check market status
curl http://localhost:8081/calendar/status?calendar=NSE | jq

# Expected output (Nov 1, 2025 - Diwali):
# {
#   "is_trading_day": false,
#   "is_holiday": true,
#   "holiday_name": "Diwali Laxmi Pujan",
#   "next_trading_day": "2025-11-03"
# }
```

### Test 2: Verify Ticker Service Integration

```bash
# Check ticker service logs for calendar status
docker logs tv-ticker 2>&1 | tail -n 50 | grep -i "market\|calendar\|mode"
```

### Test 3: Test Python SDK

```bash
cd /mnt/stocksblitz-data/Quantagro/tradingview-viz/python-sdk

# Create test script
cat > test_calendar.py << 'EOF'
from stocksblitz_sdk import CalendarClient
import asyncio

async def test():
    async with CalendarClient(base_url="http://localhost:8081") as cal:
        status = await cal.get_status('NSE')
        print(f"Trading day: {status.is_trading_day}")
        print(f"Current session: {status.current_session}")
        print(f"Next trading day: {status.next_trading_day}")

asyncio.run(test())
EOF

# Run test
python test_calendar.py
```

---

## 7. Production Deployment Checklist

When moving to production:

- [ ] **Switch MARKET_MODE to `auto`** in docker-compose.yml
- [ ] **Set up monthly cron job** for holiday synchronization
- [ ] **Add Muhurat trading dates** for upcoming Diwali
- [ ] **Test calendar API** from production servers
- [ ] **Update Python SDK base_url** in production scripts
- [ ] **Monitor ticker service logs** during first market session
- [ ] **Verify mode switching** at 9:15 AM (should go LIVE)
- [ ] **Verify mode switching** at 3:30 PM (should go MOCK)
- [ ] **Test weekend behavior** (should use MOCK)
- [ ] **Test holiday behavior** (should use MOCK)

---

## 8. Troubleshooting

### Calendar API Returns 503

**Symptom**: `{"detail": "Data manager not available"}`

**Fix**: Ensure backend is fully started:
```bash
docker logs tv-backend | grep "initialized successfully"
```

### Ticker Service Still Using Old Mock Logic

**Symptom**: Ticker doesn't check calendar

**Fix**: Ensure environment variables are set:
```bash
docker exec tv-ticker env | grep -E "MARKET_MODE|CALENDAR"
```

### Python SDK Connection Refused

**Symptom**: `ConnectionError: Connection refused`

**Fix**: Check base_url is correct:
```python
# Inside Docker containers
CalendarClient(base_url="http://backend:8000")

# From host machine
CalendarClient(base_url="http://localhost:8081")
```

---

## 9. Quick Reference

### Calendar API Endpoints

| Endpoint | Purpose | Example |
|----------|---------|---------|
| `GET /calendar/status` | Current market status | `curl "http://localhost:8081/calendar/status?calendar=NSE"` |
| `GET /calendar/holidays` | List holidays | `curl "http://localhost:8081/calendar/holidays?calendar=NSE&year=2025"` |
| `GET /calendar/next-trading-day` | Next trading day | `curl "http://localhost:8081/calendar/next-trading-day?calendar=NSE"` |
| `GET /calendar/calendars` | List all calendars | `curl "http://localhost:8081/calendar/calendars"` |

### Python SDK Quick Reference

```python
# Async version
from stocksblitz_sdk import CalendarClient
async with CalendarClient() as cal:
    status = await cal.get_status('NSE')
    is_open = await cal.is_market_open('NSE')
    holidays = await cal.get_holidays('NSE', year=2025)
    next_day = await cal.get_next_trading_day('NSE')

# Sync version
from stocksblitz_sdk import CalendarClientSync
cal = CalendarClientSync()
status = cal.get_status('NSE')
is_open = cal.is_market_open('NSE')
```

### Market Modes

| Mode | Behavior | Use Case |
|------|----------|----------|
| `force_mock` | Always MOCK | Development, testing, weekend work |
| `auto` | LIVE during market hours, MOCK otherwise | Production |
| `force_live` | Always LIVE | Testing Kite API |
| `off` | No data fetching | Debugging |

---

## 🎉 Summary

✅ **Calendar service deployed and integrated**
✅ **Docker-compose configured with MARKET_MODE**
✅ **Python SDK ready to use**
✅ **Special sessions (Muhurat) fully supported**
✅ **Holiday sync mechanism designed**
✅ **REST API working and tested**

**Current Mode**: Development (`force_mock`) - works anytime
**Next Step**: Set up monthly cron job for holiday sync before 2026
**Production Ready**: Switch to `auto` mode when deploying

---

**Questions?** Check the other documentation:
- `CALENDAR_SERVICE_IMPLEMENTATION.md` - Technical details
- `CALENDAR_DEPLOYMENT_COMPLETE.md` - Deployment verification
- `CALENDAR_QUICK_START.md` - Quick examples
