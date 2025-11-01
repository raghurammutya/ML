# Calendar Service - Quick Start Guide

**TL;DR**: Market calendar with smart LIVE/MOCK mode switching for development and production.

---

## 🚀 30-Second Setup

```bash
# 1. Run migration
cd /mnt/stocksblitz-data/Quantagro/tradingview-viz/backend
PGPASSWORD=stocksblitz123 psql -h localhost -p 5432 -U stocksblitz \
  -d stocksblitz_unified -f migrations/012_create_calendar_service.sql

# 2. Fetch holidays
python -m app.services.holiday_fetcher --sync-all

# 3. Restart backend
docker restart tv-backend

# Done! Calendar API is ready.
```

---

## 💻 Development Mode (Always Mock Data)

**Problem**: Want to develop on weekends/holidays without market being open

**Solution**: Force mock mode

```bash
# In ticker_service/.env or docker-compose.yml
MARKET_MODE=force_mock
```

**Result**: ticker_service always sends mock data, regardless of actual market hours

---

## 🏭 Production Mode (Follow Market Calendar)

**Problem**: Only trade during actual market hours, respect holidays

**Solution**: Auto mode

```bash
# In ticker_service/.env
MARKET_MODE=auto
CALENDAR_CODE=NSE
```

**Result**: ticker_service checks calendar and only goes live during trading hours

---

## 🐍 Python SDK - Common Use Cases

### Use Case 1: Check if market is open before placing order

```python
from stocksblitz_sdk import CalendarClientSync

calendar = CalendarClientSync()

if calendar.is_market_open('NSE'):
    place_order()
else:
    print("Market closed - order queued")
```

---

### Use Case 2: Schedule algo to run only on trading days

```python
import asyncio
from stocksblitz_sdk import CalendarClient

async def run_algo():
    async with CalendarClient() as calendar:
        while True:
            status = await calendar.get_status('NSE')

            if status.current_session == 'trading':
                await execute_strategy()
            else:
                print(f"Waiting... {status.current_session}")

            await asyncio.sleep(60)

asyncio.run(run_algo())
```

---

### Use Case 3: Get next trading day for settlement

```python
from stocksblitz_sdk import CalendarClientSync
from datetime import date

calendar = CalendarClientSync()

# User places order on Friday
order_date = date(2025, 11, 1)  # Friday
settlement_date = calendar.get_next_trading_day('NSE', after_date=order_date)

print(f"Order on {order_date}")
print(f"Settlement on {settlement_date}")  # Monday (skips weekend)
```

---

### Use Case 4: Backtest only on trading days

```python
from stocksblitz_sdk import CalendarClient
from datetime import date

async def backtest():
    async with CalendarClient() as calendar:
        # Get all trading days in Jan 2025
        days = await calendar.get_trading_days(
            'NSE',
            date(2025, 1, 1),
            date(2025, 1, 31)
        )

        trading_days = [d.date for d in days if d.is_trading_day]

        for day in trading_days:
            run_backtest_for_day(day)
```

---

## 🔧 Configuration Modes

| Mode | Use Case | Behavior |
|------|----------|----------|
| `auto` | **Production** | Follows market calendar strictly |
| `force_mock` | **Development** | Always mock data (ignore calendar) |
| `force_live` | **Testing** | Always attempt live connection |
| `off` | **Maintenance** | No streaming at all |

**Set via environment variable**:
```bash
export MARKET_MODE=force_mock  # Development
export MARKET_MODE=auto        # Production
```

---

## 📅 API Quick Reference

### Get current market status

```bash
curl http://localhost:8081/calendar/status?calendar=NSE | jq
```

Response:
```json
{
  "is_trading_day": true,
  "current_session": "trading",
  "session_start": "09:15:00",
  "session_end": "15:30:00",
  "is_holiday": false,
  "is_weekend": false
}
```

---

### Get holidays for a year

```bash
curl "http://localhost:8081/calendar/holidays?calendar=NSE&year=2025" | jq
```

Response:
```json
[
  {
    "date": "2025-01-26",
    "name": "Republic Day",
    "category": "market_holiday"
  },
  {
    "date": "2025-03-14",
    "name": "Holi",
    "category": "market_holiday"
  }
]
```

---

### Get next trading day

```bash
curl http://localhost:8081/calendar/next-trading-day?calendar=NSE | jq
```

Response:
```json
{
  "calendar": "NSE",
  "after_date": "2025-11-01",
  "next_trading_day": "2025-11-03",
  "days_until": 2
}
```

---

## 🎯 Common Scenarios

### Scenario 1: Testing on Weekend

**Want**: Test ticker_service with mock data on Saturday

```bash
# Set force_mock mode
docker-compose run -e MARKET_MODE=force_mock ticker_service

# ticker_service will send mock data regardless of it being weekend
```

---

### Scenario 2: Production - Never Trade on Holidays

**Want**: Ensure system never trades on NSE holidays

```bash
# Set auto mode (in production .env)
MARKET_MODE=auto
CALENDAR_CODE=NSE

# System will check calendar and stay in mock/off mode during holidays
```

---

### Scenario 3: Add Unscheduled Holiday

**Want**: NSE announces sudden holiday tomorrow

```bash
curl -X POST http://localhost:8081/calendar/holidays \
  -H "Content-Type: application/json" \
  -d '{
    "calendar_code": "NSE",
    "date": "2025-11-05",
    "name": "Emergency Holiday",
    "category": "market_holiday"
  }'

# ticker_service will immediately pick up the new holiday
```

---

### Scenario 4: Muhurat Trading (Special Hours)

**Want**: Handle Diwali Muhurat trading (6 PM - 7 PM)

```bash
curl -X POST http://localhost:8081/calendar/holidays \
  -H "Content-Type: application/json" \
  -d '{
    "calendar_code": "NSE",
    "date": "2025-11-01",
    "name": "Diwali Muhurat Trading",
    "is_trading_day": true,
    "special_start": "18:00:00",
    "special_end": "19:00:00"
  }'

# ticker_service will switch to LIVE mode only during 6-7 PM
```

---

## 🔍 Debugging

### Check what mode ticker_service is in

```bash
# View ticker_service logs
docker logs tv-ticker | grep "Mode="

# You should see:
# [INFO] Account primary: Mode=LIVE | Market open: Trading session
# OR
# [INFO] Account primary: Mode=MOCK | Market closed: Weekend
```

---

### Verify calendar API is working

```bash
# Test from inside ticker_service container
docker exec tv-ticker curl http://backend:8000/calendar/status?calendar=NSE

# Should return JSON with market status
```

---

### Check if holidays are in database

```bash
PGPASSWORD=stocksblitz123 psql -h localhost -p 5432 -U stocksblitz \
  -d stocksblitz_unified -c \
  "SELECT event_date, event_name FROM calendar_events
   WHERE EXTRACT(YEAR FROM event_date) = 2025
   AND category != 'weekend'
   ORDER BY event_date;"
```

---

## 📊 Monitoring

### Key Metrics to Watch

1. **Mode Switches**: How often LIVE ↔ MOCK transitions happen
2. **Calendar API Latency**: Response time of `/calendar/status`
3. **Holiday Coverage**: Are all known holidays in database?

### Log Patterns

✅ **Good**:
```
[INFO] Calendar status: trading_day=True session=trading
[INFO] Account primary: Mode=LIVE | Market open: Trading session
```

⚠️ **Warning**:
```
[WARNING] Calendar API check failed, falling back to time-based check
```

🚨 **Error**:
```
[ERROR] Calendar API returned 500
```

---

## 🆘 Quick Fixes

### Issue: Always mock mode even during trading hours

```bash
# Check environment
docker exec tv-ticker env | grep MARKET_MODE

# Should be 'auto', if 'force_mock' change it:
# Edit docker-compose.yml or .env
# Restart: docker restart tv-ticker
```

---

### Issue: No holidays in database

```bash
# Re-sync holidays
cd /mnt/stocksblitz-data/Quantagro/tradingview-viz/backend
python -m app.services.holiday_fetcher --sync-all
```

---

### Issue: Calendar API not responding

```bash
# Check backend is running
curl http://localhost:8081/health

# Check calendar endpoint specifically
curl http://localhost:8081/calendar/status?calendar=NSE

# Restart backend if needed
docker restart tv-backend
```

---

## 📚 Related Files

- **Full Guide**: `CALENDAR_SERVICE_IMPLEMENTATION.md`
- **Migration**: `backend/migrations/012_create_calendar_service.sql`
- **Holiday Fetcher**: `backend/app/services/holiday_fetcher.py`
- **Calendar API**: `backend/app/routes/calendar.py`
- **Market Mode Manager**: `ticker_service/app/market_mode.py`
- **Python SDK**: `python-sdk/stocksblitz_sdk/calendar.py`

---

## 🎓 Next Steps

1. ✅ Run migration
2. ✅ Sync holidays
3. ✅ Restart backend
4. ✅ Configure ticker_service mode
5. ✅ Test with Python SDK
6. ✅ Monitor logs

**That's it!** You now have a production-ready calendar service.

---

**Need help?** See `CALENDAR_SERVICE_IMPLEMENTATION.md` for detailed documentation.
