# Calendar Service

**Status**: ✅ Deployed and Operational
**Deployment Date**: November 1, 2025
**Branch**: feature/nifty-monitor

---

## Overview

The Calendar Service provides market calendar, holiday tracking, and trading hours information for Indian markets (NSE, BSE, MCX, Currency). It enables the trading platform to automatically switch between LIVE and MOCK data modes based on market hours and holidays.

---

## Features

- ✅ **Market Calendars**: NSE, BSE, MCX, NCDEX, Currency markets
- ✅ **Holiday Tracking**: 162 holidays across 4 markets (2024-2026)
- ✅ **Weekend Detection**: Automatic weekend mapping (1,872 events)
- ✅ **Special Sessions**: Support for Muhurat trading and other special hours
- ✅ **Trading Hours**: Pre-market, regular, and post-market sessions
- ✅ **REST API**: 4 endpoints for calendar queries
- ✅ **Python SDK**: Async and sync clients
- ✅ **Market Mode Manager**: Smart LIVE/MOCK switching for ticker_service

---

## Folder Structure

```
calendar_service/
├── README.md                        # This file
├── docs/                            # Documentation
│   ├── 01_IMPLEMENTATION.md         # Technical implementation details
│   ├── 02_DEPLOYMENT.md             # Deployment verification report
│   ├── 03_INTEGRATION_GUIDE.md      # Complete integration guide with examples
│   ├── 04_QUICK_START.md            # Quick reference and common use cases
│   ├── 05_QA.md                     # Questions and answers
│   └── 06_SUMMARY.md                # Architecture overview
├── backend/                         # Backend components
│   ├── migrations/                  # Database migrations
│   │   ├── 012_create_calendar_service.sql    # Schema creation
│   │   └── 013_populate_holidays.sql          # Holiday data
│   ├── routes/                      # API routes
│   │   ├── calendar_simple.py       # ✅ Active (deployed)
│   │   └── calendar.py              # Reference (complex version)
│   └── services/                    # Background services
│       └── holiday_fetcher.py       # Holiday sync service
├── sdk/                             # Python SDK
│   └── calendar.py                  # Calendar client (async + sync)
└── ticker_service/                  # Ticker service integration
    └── market_mode.py               # Market mode manager
```

---

## Quick Start

### 1. Check Market Status (API)

```bash
curl http://localhost:8081/calendar/status?calendar=NSE | jq
```

### 2. Use Python SDK

```python
from stocksblitz_sdk import CalendarClient

async with CalendarClient() as calendar:
    status = await calendar.get_status('NSE')

    if status.is_trading_day:
        print(f"Market open: {status.session_start} - {status.session_end}")
    else:
        print(f"Market closed: {status.holiday_name or 'Weekend'}")
        print(f"Next trading day: {status.next_trading_day}")
```

### 3. Configure Ticker Service

```yaml
# docker-compose.yml
ticker-service:
  environment:
    - MARKET_MODE=force_mock  # Development: always mock
    # or
    - MARKET_MODE=auto        # Production: auto-switch based on calendar
    - CALENDAR_API_URL=http://backend:8000
    - CALENDAR_CODE=NSE
```

---

## Database Schema

### Tables

1. **calendar_types** - Calendar definitions (NSE, BSE, MCX, etc.)
2. **trading_sessions** - Trading hours for each market
3. **calendar_events** - Holidays, weekends, special sessions
4. **market_status_cache** - Cached market status (1-minute TTL)

### Data Statistics

| Item | Count |
|------|-------|
| Calendar Types | 8 |
| Trading Sessions | 4 |
| Weekend Events | 1,872 (2024-2026) |
| NSE Holidays | 47 |
| BSE Holidays | 47 |
| MCX Holidays | 21 |
| Currency Holidays | 47 |
| **Total Events** | **2,034** |

---

## API Endpoints

| Endpoint | Description | Example |
|----------|-------------|---------|
| `GET /calendar/status` | Current market status | `?calendar=NSE` |
| `GET /calendar/holidays` | List holidays | `?calendar=NSE&year=2025` |
| `GET /calendar/next-trading-day` | Next trading day | `?calendar=NSE` |
| `GET /calendar/calendars` | List all calendars | - |

---

## Market Modes

### Development Mode (Current)
```bash
MARKET_MODE=force_mock
```
- Always uses MOCK data
- Works on weekends, holidays, nights
- No Kite API rate limits

### Production Mode
```bash
MARKET_MODE=auto
```
- LIVE data during trading hours (9:15-15:30)
- MOCK data outside trading hours
- Respects holidays and weekends

---

## Integration Status

| Component | Status | Location |
|-----------|--------|----------|
| Database | ✅ Deployed | PostgreSQL stocksblitz_unified |
| API | ✅ Active | http://localhost:8081/calendar/* |
| Docker-Compose | ✅ Configured | ticker-service environment vars |
| Python SDK | ✅ Ready | stocksblitz_sdk.CalendarClient |
| Documentation | ✅ Complete | calendar_service/docs/ |

---

## Files to Deploy

When deploying, copy these files to their target locations:

### Backend Files
```bash
# Migrations (run once)
backend/migrations/012_create_calendar_service.sql
backend/migrations/013_populate_holidays.sql

# Routes (deployed)
backend/app/routes/calendar_simple.py  → backend/app/routes/

# Services (optional - for holiday sync)
backend/app/services/holiday_fetcher.py → backend/app/services/

# Update main.py
backend/app/main.py  # Add calendar router import
```

### SDK Files
```bash
# Python SDK
sdk/calendar.py → python-sdk/stocksblitz_sdk/calendar.py
```

### Ticker Service Files
```bash
# Market mode manager (optional - for future use)
ticker_service/market_mode.py → ticker_service/app/market_mode.py
```

### Docker Compose
```bash
# Update environment variables
docker-compose.yml  # Add MARKET_MODE, CALENDAR_API_URL, CALENDAR_CODE
```

---

## Testing

### Verify Database
```bash
PGPASSWORD=stocksblitz123 psql -U stocksblitz -d stocksblitz_unified -c \
  "SELECT code, COUNT(*) FROM calendar_types
   JOIN calendar_events ON calendar_type_id = id
   GROUP BY code;"
```

### Verify API
```bash
# All calendars
curl http://localhost:8081/calendar/calendars | jq

# Market status
curl http://localhost:8081/calendar/status?calendar=NSE | jq

# 2025 holidays
curl "http://localhost:8081/calendar/holidays?calendar=NSE&year=2025" | jq length
```

### Verify Ticker Service
```bash
# Check environment
docker exec tv-ticker env | grep -E "MARKET_MODE|CALENDAR"

# Test API access from ticker
docker exec tv-ticker curl -s http://backend:8000/calendar/status?calendar=NSE
```

---

## Maintenance

### Monthly Holiday Sync (Recommended)

```bash
# /etc/cron.monthly/sync-holidays.sh
#!/bin/bash
docker exec tv-backend python -m app.services.holiday_fetcher --sync-all --years "2026,2027"
```

### Add Special Sessions (e.g., Muhurat Trading)

```sql
INSERT INTO calendar_events (
    calendar_type_id,
    event_date,
    event_name,
    is_trading_day,
    special_start,
    special_end,
    category
) VALUES (
    (SELECT id FROM calendar_types WHERE code = 'NSE'),
    '2025-11-01',
    'Muhurat Trading',
    true,
    '18:15:00',
    '19:15:00',
    'special_session'
);
```

---

## Documentation

Start with these guides in order:

1. **04_QUICK_START.md** - Quick examples and common use cases
2. **05_QA.md** - Answers to common questions
3. **03_INTEGRATION_GUIDE.md** - Complete integration guide
4. **01_IMPLEMENTATION.md** - Technical implementation details
5. **02_DEPLOYMENT.md** - Deployment verification
6. **06_SUMMARY.md** - Architecture overview

---

## Production Checklist

Before deploying to production:

- [ ] Verify all migrations run successfully
- [ ] Test all API endpoints
- [ ] Set up monthly cron job for holiday sync
- [ ] Add Muhurat trading dates for upcoming Diwali
- [ ] Switch `MARKET_MODE=auto` in docker-compose.yml
- [ ] Monitor ticker service during first live session
- [ ] Verify mode switching at 9:15 AM and 3:30 PM
- [ ] Test weekend and holiday behavior

---

## Support

**Documentation**: See `docs/` folder
**Branch**: feature/nifty-monitor
**Deployment Date**: November 1, 2025

---

## Quick Reference

### Current Status (Nov 1, 2025)
- **Is Trading Day?**: No (Diwali + Saturday)
- **Holiday**: Diwali Laxmi Pujan
- **Next Trading Day**: Monday, November 3, 2025
- **Mode**: force_mock (Development)

### API Base URL
- **Host Machine**: http://localhost:8081
- **Docker Containers**: http://backend:8000

### Supported Markets
NSE, BSE, MCX, NCDEX, NSE_CURRENCY, BSE_CURRENCY, SYSTEM, USER_DEFAULT

---

**Last Updated**: November 1, 2025
**Status**: ✅ Production Ready
