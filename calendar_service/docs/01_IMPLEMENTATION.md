# Calendar Service - Complete Implementation Guide

**Date**: November 1, 2025
**Status**: Ready for Implementation

---

## 📋 Overview

This guide implements a comprehensive **Calendar Service** that handles:

✅ **Market Calendars**: NSE, BSE, MCX, Currency markets
✅ **Holiday Tracking**: Automatic sync from official sources
✅ **Trading Hours**: Regular, pre-market, post-market sessions
✅ **Development Mode**: Mock data during development (ignore market hours)
✅ **Production Mode**: Strict calendar adherence
✅ **Python SDK**: Easy integration with any Python code
✅ **Future-Ready**: Supports user calendars, recurring events (when user_service exists)

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────┐
│                 Calendar Service                    │
├─────────────────────────────────────────────────────┤
│                                                     │
│  ┌────────────────┐      ┌──────────────────────┐ │
│  │ PostgreSQL DB  │◄────►│  Calendar API        │ │
│  │                │      │  (FastAPI)           │ │
│  │  Tables:       │      │                      │ │
│  │  - calendar_   │      │  Endpoints:          │ │
│  │    types       │      │  - /status           │ │
│  │  - trading_    │      │  - /holidays         │ │
│  │    sessions    │      │  - /trading-days     │ │
│  │  - calendar_   │      │  - /next-trading-day │ │
│  │    events      │      └──────────────────────┘ │
│  │  - market_     │                ▲              │
│  │    status_cache│                │              │
│  └────────────────┘                │              │
│         ▲                           │              │
│         │                           │              │
│  ┌──────┴───────────┐              │              │
│  │ Holiday Fetcher  │              │              │
│  │                  │              │              │
│  │  - NSE scraper   │              │              │
│  │  - BSE scraper   │              │              │
│  │  - MCX scraper   │              │              │
│  │  - Fallback data │              │              │
│  └──────────────────┘              │              │
└─────────────────────────────────────┼──────────────┘
                                      │
                    ┌─────────────────┴────────────────────┐
                    │                                      │
         ┌──────────▼───────────┐          ┌──────────────▼──────────┐
         │ ticker_service       │          │ Python SDK               │
         │                      │          │ (stocksblitz_sdk)        │
         │ - MarketModeManager  │          │                          │
         │ - Checks calendar    │          │  CalendarClient:         │
         │ - LIVE vs MOCK       │          │  - get_status()          │
         │                      │          │  - get_holidays()        │
         │  Modes:              │          │  - is_market_open()      │
         │  - auto (prod)       │          │  - get_trading_days()    │
         │  - force_mock (dev)  │          │                          │
         │  - force_live (test) │          │  Easy integration in     │
         │  - off (maintenance) │          │  any Python service!     │
         └──────────────────────┘          └──────────────────────────┘
```

---

## 🚀 Step-by-Step Implementation

### Phase 1: Database Setup (15 minutes)

#### Step 1.1: Run Migration

```bash
cd /mnt/stocksblitz-data/Quantagro/tradingview-viz/backend

# Run the migration
PGPASSWORD=stocksblitz123 psql -h localhost -p 5432 -U stocksblitz -d stocksblitz_unified -f migrations/012_create_calendar_service.sql
```

**What this does**:
- Creates `calendar_types` table (NSE, BSE, MCX, etc.)
- Creates `trading_sessions` table (regular trading hours)
- Creates `calendar_events` table (holidays, special days)
- Creates `market_status_cache` table (pre-computed status)
- Pre-populates weekends for 2024-2026
- Creates helper functions

**Verify**:
```sql
-- Check calendar types
SELECT * FROM calendar_types;

-- Check weekends were created
SELECT COUNT(*) FROM calendar_events WHERE category = 'weekend';
-- Should show ~300+ weekend events

-- Check trading sessions
SELECT * FROM trading_sessions;
```

#### Step 1.2: Fetch and Populate Holidays

```bash
cd /mnt/stocksblitz-data/Quantagro/tradingview-viz/backend

# Sync all calendars for 2024-2026
python -m app.services.holiday_fetcher --sync-all --years "2024,2025,2026"

# OR sync specific calendar
python -m app.services.holiday_fetcher --calendar NSE --year 2025
python -m app.services.holiday_fetcher --calendar BSE --year 2025
python -m app.services.holiday_fetcher --calendar MCX --year 2025
```

**Expected output**:
```
[INFO] Market Mode Manager initialized | mode=auto calendar=NSE
[INFO] Syncing NSE holidays...
[INFO] Fetched 15 NSE holidays for 2024 from API
[INFO] Synced 15 holidays for NSE 2024: 12 inserted, 3 updated
[SUCCESS] ✓ NSE 2024: 15 holidays
[SUCCESS] ✓ NSE 2025: 15 holidays
[SUCCESS] ✓ NSE 2026: 14 holidays
...
[SUCCESS] Total holidays synced: 150
```

**Verify**:
```sql
-- Check holidays
SELECT calendar_code, COUNT(*)
FROM calendar_events ce
JOIN calendar_types ct ON ce.calendar_type_id = ct.id
WHERE category != 'weekend'
GROUP BY calendar_code;

-- See NSE holidays for 2025
SELECT event_date, event_name
FROM calendar_events ce
JOIN calendar_types ct ON ce.calendar_type_id = ct.id
WHERE ct.code = 'NSE'
AND EXTRACT(YEAR FROM event_date) = 2025
AND category != 'weekend'
ORDER BY event_date;
```

---

### Phase 2: Backend API Integration (10 minutes)

#### Step 2.1: Add Calendar Routes to Main App

Edit `backend/app/main.py`:

```python
# Add import
from app.routes import calendar

# Add router (with other routers)
app.include_router(calendar.router)
```

#### Step 2.2: Restart Backend

```bash
# If using Docker
docker restart tv-backend

# OR if running locally
# Stop and restart uvicorn
```

#### Step 2.3: Test Calendar API

```bash
# Check API health
curl http://localhost:8081/health

# Get current market status
curl http://localhost:8081/calendar/status?calendar=NSE | jq

# Get NSE holidays for 2025
curl "http://localhost:8081/calendar/holidays?calendar=NSE&year=2025" | jq

# Get next trading day
curl http://localhost:8081/calendar/next-trading-day?calendar=NSE | jq

# List available calendars
curl http://localhost:8081/calendar/calendars | jq
```

**Expected response** (weekend/holiday):
```json
{
  "calendar_code": "NSE",
  "date": "2025-11-01",
  "is_trading_day": false,
  "is_holiday": false,
  "is_weekend": true,
  "current_session": "closed",
  "holiday_name": null,
  "next_trading_day": "2025-11-03",
  "session_start": null,
  "session_end": null
}
```

**Expected response** (trading day at 10 AM IST):
```json
{
  "calendar_code": "NSE",
  "date": "2025-11-03",
  "is_trading_day": true,
  "is_holiday": false,
  "is_weekend": false,
  "current_session": "trading",
  "holiday_name": null,
  "session_start": "09:15:00",
  "session_end": "15:30:00",
  "pre_market_start": "09:00:00",
  "pre_market_end": "09:08:00",
  "post_market_start": "15:40:00",
  "post_market_end": "16:00:00",
  "next_trading_day": null
}
```

---

### Phase 3: ticker_service Integration (20 minutes)

#### Step 3.1: Update ticker_service Environment

Edit `ticker_service/.env` or `docker-compose.yml`:

```bash
# ticker_service environment variables

# Market mode configuration
# Options: auto, force_mock, force_live, off
MARKET_MODE=auto                     # Production: auto
# MARKET_MODE=force_mock             # Development: always mock
# MARKET_MODE=force_live             # Testing: always live
# MARKET_MODE=off                    # Maintenance: no streaming

# Calendar API
CALENDAR_API_URL=http://backend:8000  # Docker: use service name
# CALENDAR_API_URL=http://localhost:8081  # Local: use localhost

CALENDAR_CODE=NSE  # Which market calendar to use
```

**For Development** (always mock):
```bash
MARKET_MODE=force_mock
```

**For Production** (use calendar):
```bash
MARKET_MODE=auto
```

#### Step 3.2: Update ticker_service Startup

Edit `ticker_service/app/generator.py`:

Add import at top:
```python
from app.market_mode import MarketModeManager
```

Update `TickerGenerator.__init__`:
```python
class TickerGenerator:
    def __init__(self):
        # ... existing init ...

        # Add market mode manager
        self.market_mode = MarketModeManager(
            calendar_api_url=os.getenv("CALENDAR_API_URL", "http://backend:8000"),
            calendar_code=os.getenv("CALENDAR_CODE", "NSE")
        )
```

Update `_stream_account` method:
```python
async def _stream_account(self, account_id: str) -> None:
    """Main streaming loop for an account"""
    while True:
        try:
            # Check current mode
            mode = await self.market_mode.get_current_mode()
            reason = await self.market_mode.get_mode_reason()

            logger.info(f"Account {account_id}: Mode={mode} | {reason}")

            if mode == "LIVE":
                # Trading hours - use live WebSocket
                logger.info(f"Account {account_id}: Starting LIVE stream")
                await self._run_live_stream(account_id)

            elif mode == "MOCK":
                # Outside hours or development - use mock data
                logger.info(f"Account {account_id}: Starting MOCK stream")
                await self._run_mock_stream(account_id)

            else:  # OFF
                # Maintenance mode - sleep
                logger.info(f"Account {account_id}: Service OFF, sleeping...")
                await asyncio.sleep(60)

        except Exception as exc:
            logger.error(f"Stream error for {account_id}: {exc}")
            await asyncio.sleep(30)
```

#### Step 3.3: Restart ticker_service

```bash
# If using Docker
docker restart tv-ticker

# Check logs
docker logs -f tv-ticker
```

**Expected logs** (weekend, development mode):
```
[INFO] Market Mode Manager initialized | mode=force_mock calendar=NSE api=http://backend:8000
[INFO] Account primary: Mode=MOCK | Development mode: MARKET_MODE=force_mock
[INFO] Account primary: Starting MOCK stream
```

**Expected logs** (trading day, auto mode):
```
[INFO] Market Mode Manager initialized | mode=auto calendar=NSE api=http://backend:8000
[DEBUG] Calendar status: trading_day=True session=trading holiday=None
[INFO] Account primary: Mode=LIVE | Market open: Trading session
[INFO] Account primary: Starting LIVE stream
```

---

### Phase 4: Python SDK Usage (5 minutes)

#### Step 4.1: Install SDK (if not already)

```bash
cd /mnt/stocksblitz-data/Quantagro/tradingview-viz/python-sdk
pip install -e .
```

#### Step 4.2: Use Calendar Client

**Example 1: Check if market is open**

```python
from stocksblitz_sdk import CalendarClient
import asyncio

async def main():
    async with CalendarClient() as calendar:
        # Check current status
        status = await calendar.get_status('NSE')

        print(f"Date: {status.date}")
        print(f"Trading day: {status.is_trading_day}")
        print(f"Current session: {status.current_session}")

        if status.is_trading_day:
            print(f"Trading: {status.session_start} - {status.session_end}")
        elif status.is_holiday:
            print(f"Holiday: {status.holiday_name}")
        elif status.is_weekend:
            print("Weekend")

        if status.next_trading_day:
            print(f"Next trading day: {status.next_trading_day}")

asyncio.run(main())
```

**Example 2: Get holidays**

```python
from stocksblitz_sdk import CalendarClient
import asyncio

async def main():
    async with CalendarClient() as calendar:
        # Get all NSE holidays for 2025
        holidays = await calendar.get_holidays('NSE', year=2025)

        print(f"NSE Holidays 2025: {len(holidays)}")
        for h in holidays:
            print(f"  {h.date.strftime('%d %b %Y')}: {h.name}")

asyncio.run(main())
```

**Example 3: Synchronous usage (non-async code)**

```python
from stocksblitz_sdk import CalendarClientSync

# No async/await needed
calendar = CalendarClientSync()

# Check if market is open right now
if calendar.is_market_open('NSE'):
    print("Market is trading - can place orders!")
else:
    print("Market closed")

# Get next trading day
next_day = calendar.get_next_trading_day('NSE')
print(f"Next trading day: {next_day}")
```

**Example 4: Use in existing service**

```python
# In your algo trading service
from stocksblitz_sdk import CalendarClient

class AlgoTradingService:
    def __init__(self):
        self.calendar = CalendarClient()

    async def should_execute_strategy(self):
        """Check if we should execute trading strategy"""

        # Check market status
        status = await self.calendar.get_status('NSE')

        if not status.is_trading_day:
            logger.info(f"Skipping strategy: {status.holiday_name or 'Weekend'}")
            return False

        if status.current_session != 'trading':
            logger.info(f"Skipping strategy: {status.current_session}")
            return False

        # Market is open and trading
        return True

    async def run(self):
        while True:
            if await self.should_execute_strategy():
                await self.execute_trades()
            else:
                # Wait until next trading session
                await asyncio.sleep(60)
```

---

## 🎛️ Configuration Guide

### Development Environment

**Goal**: Always use mock data, ignore market hours

**ticker_service/.env**:
```bash
MARKET_MODE=force_mock
CALENDAR_API_URL=http://localhost:8081
CALENDAR_CODE=NSE
```

**Benefits**:
- Develop anytime (weekends, nights, holidays)
- Consistent mock data for testing
- No Kite API rate limits

---

### Staging Environment

**Goal**: Use calendar but allow override for testing

**ticker_service/.env**:
```bash
MARKET_MODE=auto  # Default: follow calendar
# Override via: docker-compose run -e MARKET_MODE=force_live ticker_service
CALENDAR_API_URL=http://backend:8000
CALENDAR_CODE=NSE
```

**Benefits**:
- Test calendar integration
- Can force live mode for testing
- Matches production behavior

---

### Production Environment

**Goal**: Strict calendar adherence, only trade during market hours

**ticker_service/.env**:
```bash
MARKET_MODE=auto  # MUST be auto in production
CALENDAR_API_URL=http://backend:8000
CALENDAR_CODE=NSE
```

**Benefits**:
- Never trades during holidays
- Respects market hours
- Prevents accidental weekend trades

---

## 📅 Maintenance

### Monthly Holiday Sync (Cron Job)

Create `/etc/cron.monthly/sync-holidays.sh`:

```bash
#!/bin/bash
cd /mnt/stocksblitz-data/Quantagro/tradingview-viz/backend

# Sync next 2 years
YEAR=$(date +%Y)
NEXT_YEAR=$((YEAR + 1))

python -m app.services.holiday_fetcher --sync-all --years "$YEAR,$NEXT_YEAR"
```

Make executable:
```bash
chmod +x /etc/cron.monthly/sync-holidays.sh
```

---

### Manual Holiday Addition

For ad-hoc holidays announced by NSE:

```bash
curl -X POST http://localhost:8081/calendar/holidays \
  -H "Content-Type: application/json" \
  -d '{
    "calendar_code": "NSE",
    "date": "2025-12-31",
    "name": "Special Trading Holiday",
    "category": "market_holiday"
  }'
```

---

### Special Trading Sessions (Muhurat Trading)

For Diwali Muhurat trading (6 PM - 7 PM):

```bash
curl -X POST http://localhost:8081/calendar/holidays \
  -H "Content-Type: application/json" \
  -d '{
    "calendar_code": "NSE",
    "date": "2025-11-01",
    "name": "Diwali Muhurat Trading",
    "category": "special",
    "is_trading_day": true,
    "special_start": "18:00:00",
    "special_end": "19:00:00"
  }'
```

---

## 🧪 Testing

### Test 1: Calendar API

```bash
# Test current status
curl http://localhost:8081/calendar/status?calendar=NSE | jq .

# Test specific date (weekend)
curl "http://localhost:8081/calendar/status?calendar=NSE&check_date=2025-11-02" | jq .

# Test specific date (holiday)
curl "http://localhost:8081/calendar/status?calendar=NSE&check_date=2025-01-26" | jq .

# Test specific date (trading day)
curl "http://localhost:8081/calendar/status?calendar=NSE&check_date=2025-11-03" | jq .
```

---

### Test 2: ticker_service Modes

**Test Force Mock** (should always mock):
```bash
docker-compose run -e MARKET_MODE=force_mock ticker_service
# Check logs - should show "Mode=MOCK"
```

**Test Force Live** (should attempt live):
```bash
docker-compose run -e MARKET_MODE=force_live ticker_service
# Check logs - should show "Mode=LIVE"
```

**Test Auto** (should check calendar):
```bash
docker-compose run -e MARKET_MODE=auto ticker_service
# Check logs - should show calendar check and appropriate mode
```

---

### Test 3: Python SDK

Create `test_calendar_sdk.py`:

```python
import asyncio
from stocksblitz_sdk import CalendarClient
from datetime import date

async def test_sdk():
    async with CalendarClient() as calendar:
        # Test 1: Current status
        print("=== Test 1: Current Status ===")
        status = await calendar.get_status('NSE')
        print(f"Trading day: {status.is_trading_day}")
        print(f"Session: {status.current_session}")

        # Test 2: Is market open
        print("\n=== Test 2: Is Market Open ===")
        is_open = await calendar.is_market_open('NSE')
        print(f"Market open: {is_open}")

        # Test 3: Get holidays
        print("\n=== Test 3: Holidays ===")
        holidays = await calendar.get_holidays('NSE', year=2025)
        print(f"Total holidays: {len(holidays)}")
        for h in holidays[:5]:  # Show first 5
            print(f"  {h.date}: {h.name}")

        # Test 4: Trading days
        print("\n=== Test 4: Trading Days ===")
        days = await calendar.get_trading_days(
            'NSE',
            date(2025, 1, 1),
            date(2025, 1, 31)
        )
        trading_count = sum(1 for d in days if d.is_trading_day)
        print(f"Trading days in Jan 2025: {trading_count}")

        # Test 5: Next trading day
        print("\n=== Test 5: Next Trading Day ===")
        next_day = await calendar.get_next_trading_day('NSE')
        print(f"Next trading day: {next_day}")

asyncio.run(test_sdk())
```

Run:
```bash
python test_calendar_sdk.py
```

---

## 🚨 Troubleshooting

### Issue 1: Calendar API not responding

**Symptom**: `ticker_service` logs show "Calendar API check failed"

**Fix**:
```bash
# Check backend is running
curl http://localhost:8081/health

# Check calendar endpoint
curl http://localhost:8081/calendar/status?calendar=NSE

# If 404, ensure routes are added to main.py
# If 500, check database connection
```

---

### Issue 2: No holidays in database

**Symptom**: All days show as trading days

**Fix**:
```bash
# Check if holidays were synced
psql -U stocksblitz -d stocksblitz_unified -c \
  "SELECT COUNT(*) FROM calendar_events WHERE category != 'weekend';"

# If 0, run holiday fetcher
python -m app.services.holiday_fetcher --sync-all
```

---

### Issue 3: ticker_service always in mock mode

**Symptom**: Even during trading hours, ticker uses mock data

**Fix**:
```bash
# Check MARKET_MODE
docker exec tv-ticker env | grep MARKET_MODE
# Should be "auto" for production

# Check calendar API URL
docker exec tv-ticker env | grep CALENDAR_API_URL
# Should point to backend

# Force live mode for testing
docker-compose run -e MARKET_MODE=force_live ticker_service
```

---

### Issue 4: Weekends not detected

**Symptom**: Saturday/Sunday show as trading days

**Fix**:
```bash
# Check weekends were created
psql -U stocksblitz -d stocksblitz_unified -c \
  "SELECT COUNT(*) FROM calendar_events WHERE category = 'weekend';"

# If 0, run function manually
psql -U stocksblitz -d stocksblitz_unified -c \
  "SELECT populate_weekends('NSE', 2025);"
```

---

## 📊 Monitoring

### Dashboard Metrics (Future)

Recommended metrics to track:

- **Mode switches**: LIVE ↔ MOCK transitions
- **Calendar API latency**: Response time of `/calendar/status`
- **Holiday sync status**: Last sync time, success/failure
- **Mode override events**: When `force_` modes are used

---

### Logging

**ticker_service** logs to watch:

```
✅ GOOD:
[INFO] Market Mode Manager initialized | mode=auto calendar=NSE
[DEBUG] Calendar status: trading_day=True session=trading
[INFO] Account primary: Mode=LIVE | Market open: Trading session

❌ WARNING:
[WARNING] Calendar API check failed: ... falling back to time-based check
[WARNING] Unknown MARKET_MODE=xyz, defaulting to MOCK

🚨 ERROR:
[ERROR] Calendar API returned 500
```

---

## 🔮 Future Enhancements

### Phase 5: User Calendars (When user_service exists)

```sql
-- Add user events
INSERT INTO calendar_events (
    calendar_type_id,
    event_date,
    event_name,
    event_type,
    user_id,  -- ← Reference to user_service
    category
) VALUES (
    (SELECT id FROM calendar_types WHERE code = 'USER_DEFAULT'),
    '2025-12-25',
    'My Trading Block',
    'one_time',
    123,  -- User ID
    'user_event'
);
```

### Phase 6: Recurring Events

```python
# Add weekly recurring event
await calendar_api.add_event({
    'event_name': 'Weekly Strategy Review',
    'recurrence_rule': 'WEEKLY:FRI',  # Every Friday
    'event_type': 'recurring'
})
```

---

## ✅ Verification Checklist

After implementation, verify:

- [ ] Migration ran successfully
- [ ] Calendar types created (NSE, BSE, MCX, etc.)
- [ ] Weekends populated for 2024-2026
- [ ] Holidays fetched and synced
- [ ] Calendar API endpoints working
- [ ] ticker_service integrated with MarketModeManager
- [ ] Development mode works (force_mock)
- [ ] Production mode works (auto)
- [ ] Python SDK installed and working
- [ ] Next trading day calculation correct
- [ ] Holiday detection working
- [ ] Weekend detection working

---

## 📚 Summary

### What We Built

1. **Database**: 4 tables for calendars, sessions, events, cache
2. **Holiday Fetcher**: Auto-sync from NSE/BSE/MCX + fallback data
3. **Calendar API**: 6 endpoints for status, holidays, trading days
4. **Market Mode Manager**: Smart LIVE/MOCK switching
5. **Python SDK**: Easy integration for any service
6. **Configuration**: Dev/Staging/Prod modes

### Key Files

- `backend/migrations/012_create_calendar_service.sql` - Database schema
- `backend/app/services/holiday_fetcher.py` - Holiday sync
- `backend/app/routes/calendar.py` - API endpoints
- `ticker_service/app/market_mode.py` - Mode manager
- `python-sdk/stocksblitz_sdk/calendar.py` - SDK client

### Environment Variables

| Variable | Values | Use Case |
|----------|--------|----------|
| `MARKET_MODE` | `auto` | Production (default) |
| | `force_mock` | Development (always mock) |
| | `force_live` | Testing (always live) |
| | `off` | Maintenance (no stream) |
| `CALENDAR_API_URL` | `http://backend:8000` | Docker |
| | `http://localhost:8081` | Local |
| `CALENDAR_CODE` | `NSE`, `BSE`, `MCX` | Market to follow |

---

**Ready to implement!** 🚀

Start with Phase 1 (Database Setup) and proceed sequentially.
