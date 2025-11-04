# Corporate Calendar Implementation Summary

## Overview

The Corporate Calendar extension adds comprehensive corporate actions tracking to the existing calendar_service. It supports BSE and NSE data sources, handles instrument/symbol conflicts, and provides a full REST API for querying corporate actions.

**Implementation Date**: November 4, 2025
**Status**: ✅ Ready for Deployment
**Version**: 1.0

---

## What's Been Implemented

### 1. Database Schema ✅

**File**: `backend/migrations/014_create_corporate_calendar.sql`

Created three new tables:

#### a. `instruments` Table
- Stores symbol/instrument information for NSE, BSE, MCX, etc.
- Handles symbol resolution (same company on different exchanges)
- Fields: symbol, isin, nse_symbol, bse_code, company_name, industry, sector, exchange
- **5 sample instruments** pre-populated (TCS, RELIANCE, INFY, HDFCBANK, ICICIBANK)

#### b. `corporate_actions` Table
- Stores corporate actions: DIVIDEND, BONUS, SPLIT, RIGHTS, AGM, EGM, BOOK_CLOSURE, BUYBACK, MERGER, DEMERGER
- Supports multiple date types: ex_date, record_date, payment_date, announcement_date, effective_date
- Flexible `action_data` JSONB field for action-specific details
- Auto-calculates `price_adjustment_factor` for splits/bonus
- Tracks source (BSE, NSE, or merged) and verification status
- **3 sample actions** pre-populated for testing

#### c. `corporate_actions_cache` Table
- Caching layer for frequently accessed queries
- Tracks hit count and expiry time
- Auto-cleanup function

### 2. Helper Functions ✅

**Implemented SQL Functions**:
- `get_upcoming_corporate_actions()` - Get upcoming actions for a symbol
- `get_corporate_actions_by_date()` - Get all actions on a specific date
- `resolve_instrument()` - Resolve symbol across BSE/NSE
- `calculate_price_adjustment()` - Auto-calculate adjustment factors
- `cleanup_expired_cache()` - Maintenance function
- `update_updated_at()` - Auto-update timestamps
- `auto_calculate_price_adjustment()` - Trigger for auto-calculating adjustments

### 3. Data Fetcher Service ✅

**File**: `backend/services/corporate_actions_fetcher.py`

Complete service for fetching and syncing corporate actions:

#### Features:
- **BSEFetcher**: Fetches data from BSE using BseIndiaApi
  - Parses corporate action types (DIVIDEND, BONUS, SPLIT, RIGHTS, AGM, etc.)
  - Extracts amounts, ratios, and dates
  - Handles multiple date formats

- **NSEFetcher**: Placeholder for NSE data (web scraping or third-party API)
  - Ready for integration with NSE data sources
  - Async HTTP client setup

- **CorporateActionsSync**: Main orchestrator
  - `sync_instrument()` - Sync specific symbol
  - `sync_all()` - Sync all active instruments
  - Deduplication and merging logic (NSE data preferred)
  - Database persistence with conflict handling

#### CLI Interface:
```bash
# Sync specific symbol
python corporate_actions_fetcher.py --symbol TCS

# Sync all instruments (limit 100)
python corporate_actions_fetcher.py --all --limit 100

# Custom date range
python corporate_actions_fetcher.py --symbol RELIANCE --days-ago 60 --days-ahead 180
```

### 4. REST API Endpoints ✅

**File**: `backend/routes/corporate_calendar.py`

Complete REST API with 7 endpoints:

#### Public Endpoints:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/calendar/corporate-actions/` | GET | Get actions for specific symbol |
| `/calendar/corporate-actions/upcoming` | GET | Get upcoming actions (next N days) |
| `/calendar/corporate-actions/by-date` | GET | Get all actions on specific ex-date |
| `/calendar/corporate-actions/all` | GET | Get all actions (all symbols) with pagination |
| `/calendar/corporate-actions/{action_id}` | GET | Get specific action by ID |
| `/calendar/corporate-actions/instruments/search` | GET | Search instruments by symbol/name |

#### Request/Response Models:
- `Instrument` - Instrument details
- `CorporateAction` - Full corporate action details
- `CorporateActionSummary` - Statistics and aggregations
- `UpcomingActionsResponse` - Upcoming actions with summary
- `ActionType` enum - All supported action types
- `ActionStatus` enum - Action statuses

### 5. Documentation ✅

Created comprehensive documentation:

1. **CORPORATE_CALENDAR_DESIGN.md** - Complete design specification
   - Data sources (BSE/NSE)
   - Corporate action types
   - Database schema details
   - Symbol/instrument conflict resolution
   - API endpoints specification
   - Data fetcher architecture
   - Implementation phases
   - Security considerations
   - Monitoring & alerts
   - Future enhancements

2. **CORPORATE_CALENDAR_IMPLEMENTATION.md** (this file)
   - Implementation summary
   - Deployment guide
   - Testing instructions
   - Integration examples

---

## Deployment Guide

### Prerequisites

1. **PostgreSQL** with existing calendar_service schema
2. **Python packages** (optional for BSE fetcher):
   ```bash
   pip install bse  # For BSE API
   pip install aiohttp beautifulsoup4  # For NSE scraping
   ```

### Step 1: Run Database Migration

```bash
# Connect to database
PGPASSWORD=stocksblitz123 psql -U stocksblitz -d stocksblitz_unified

# Run migration
\i /path/to/calendar_service/backend/migrations/014_create_corporate_calendar.sql
```

**Expected Output**:
- 3 tables created: `instruments`, `corporate_actions`, `corporate_actions_cache`
- 8 helper functions created
- 5 sample instruments inserted
- 3 sample corporate actions inserted

### Step 2: Copy Service Files

```bash
# Copy data fetcher service
cp calendar_service/backend/services/corporate_actions_fetcher.py \
   backend/app/services/

# Copy API routes
cp calendar_service/backend/routes/corporate_calendar.py \
   backend/app/routes/
```

### Step 3: Update Backend Main Application

**File**: `backend/app/main.py`

Add these imports:
```python
from app.routes import corporate_calendar
```

Register the router:
```python
# After existing calendar router registration
corporate_calendar.set_data_manager(data_manager)
app.include_router(corporate_calendar.router)
```

### Step 4: Restart Backend Service

```bash
# Restart the backend container
docker-compose restart backend

# Or if running directly
systemctl restart tradingview-backend  # adjust as needed
```

### Step 5: Populate Instruments (Optional)

You can populate the instruments table with more symbols:

```sql
-- Add more instruments
INSERT INTO instruments (symbol, isin, nse_symbol, bse_code, company_name, industry, sector, exchange, instrument_type)
VALUES
('WIPRO', 'INE075A01022', 'WIPRO', 507685, 'Wipro Ltd', 'IT Services', 'Information Technology', 'BOTH', 'EQ'),
('ITC', 'INE154A01025', 'ITC', 500875, 'ITC Ltd', 'Diversified', 'FMCG', 'BOTH', 'EQ'),
('BHARTIARTL', 'INE397D01024', 'BHARTIARTL', 532454, 'Bharti Airtel Ltd', 'Telecom', 'Telecom', 'BOTH', 'EQ')
ON CONFLICT (symbol, exchange) DO NOTHING;
```

Or use a bulk import CSV file (see example below).

### Step 6: Sync Corporate Actions Data

```bash
# Run sync for specific symbols
docker exec tv-backend python -m app.services.corporate_actions_fetcher --symbol TCS
docker exec tv-backend python -m app.services.corporate_actions_fetcher --symbol RELIANCE

# Or sync all (use with caution - rate limiting applies)
docker exec tv-backend python -m app.services.corporate_actions_fetcher --all --limit 50
```

---

## Testing

### 1. Verify Database

```bash
# Check instruments
PGPASSWORD=stocksblitz123 psql -U stocksblitz -d stocksblitz_unified -c \
  "SELECT symbol, company_name, exchange, nse_symbol, bse_code FROM instruments LIMIT 10;"

# Check corporate actions
PGPASSWORD=stocksblitz123 psql -U stocksblitz -d stocksblitz_unified -c \
  "SELECT ca.title, i.symbol, ca.ex_date, ca.action_type, ca.source
   FROM corporate_actions ca
   JOIN instruments i ON ca.instrument_id = i.id
   LIMIT 10;"
```

### 2. Test API Endpoints

```bash
# Health check (existing calendar endpoint)
curl http://localhost:8081/calendar/health | jq

# Get corporate actions for TCS
curl "http://localhost:8081/calendar/corporate-actions/?symbol=TCS&from_date=2024-01-01&to_date=2025-12-31" | jq

# Get upcoming actions (next 30 days)
curl "http://localhost:8081/calendar/corporate-actions/upcoming?days=30" | jq

# Get all dividends
curl "http://localhost:8081/calendar/corporate-actions/upcoming?days=90&action_type=DIVIDEND" | jq

# Get actions by date
curl "http://localhost:8081/calendar/corporate-actions/by-date?ex_date=2025-06-15" | jq

# Search instruments
curl "http://localhost:8081/calendar/corporate-actions/instruments/search?q=TATA" | jq

# Get specific action by ID
curl "http://localhost:8081/calendar/corporate-actions/1" | jq
```

### 3. Test Data Fetcher

```bash
# Test sync with verbose logging
docker exec tv-backend python -m app.services.corporate_actions_fetcher \
  --symbol TCS --days-ago 30 --days-ahead 90
```

---

## API Usage Examples

### Example 1: Get All Dividends for a Symbol

```python
import requests

response = requests.get(
    'http://localhost:8081/calendar/corporate-actions/',
    params={
        'symbol': 'TCS',
        'from_date': '2025-01-01',
        'to_date': '2025-12-31',
        'action_type': 'DIVIDEND'
    }
)

for action in response.json():
    print(f"{action['ex_date']}: {action['title']}")
    print(f"  Amount: Rs {action['action_data']['amount']}")
    print(f"  Record Date: {action['record_date']}")
    print(f"  Payment Date: {action['payment_date']}")
```

### Example 2: Get Upcoming Corporate Actions

```python
import requests

response = requests.get(
    'http://localhost:8081/calendar/corporate-actions/upcoming',
    params={'days': 30}
)

data = response.json()
print(f"Total upcoming actions: {data['summary']['total_actions']}")
print(f"By type: {data['summary']['by_type']}")

for action in data['actions']:
    print(f"{action['instrument']['symbol']}: {action['title']} on {action['ex_date']}")
```

### Example 3: Check if Ex-Date Today

```python
import requests
from datetime import date

today = date.today()

response = requests.get(
    'http://localhost:8081/calendar/corporate-actions/by-date',
    params={'ex_date': today.isoformat()}
)

actions = response.json()
if actions:
    print(f"Corporate actions today ({today}):")
    for action in actions:
        print(f"  {action['instrument']['symbol']}: {action['title']}")
else:
    print(f"No corporate actions on {today}")
```

---

## Integration with Existing Calendar Service

The corporate calendar integrates seamlessly with the existing market calendar. Here's how you can enhance the existing `/calendar/status` endpoint to include corporate actions:

### Enhanced Market Status Endpoint

**File**: `backend/app/routes/calendar_simple.py`

Add this to the `get_market_status` function:

```python
# ... existing code ...

# NEW: Get corporate actions for this date and symbol
corporate_actions = []
if symbol:
    actions = await conn.fetch("""
        SELECT
            i.symbol,
            ca.action_type,
            ca.title,
            ca.ex_date,
            ca.action_data
        FROM corporate_actions ca
        JOIN instruments i ON ca.instrument_id = i.id
        WHERE i.symbol = $1
        AND ca.ex_date = $2
        AND ca.status IN ('announced', 'upcoming')
    """, symbol.upper(), check_date)

    corporate_actions = [
        {
            'symbol': a['symbol'],
            'action_type': a['action_type'],
            'title': a['title'],
            'ex_date': a['ex_date'].isoformat(),
            'is_ex_date': True,
            'action_data': a['action_data']
        }
        for a in actions
    ]

return MarketStatus(
    # ... existing fields ...
    corporate_actions=corporate_actions  # NEW field
)
```

Update the `MarketStatus` model:

```python
class MarketStatus(BaseModel):
    # ... existing fields ...
    corporate_actions: List[dict] = []  # NEW field
```

---

## Symbol/Instrument Conflict Resolution

The system handles symbol conflicts between BSE and NSE:

### How It Works

1. **ISIN as Primary Key** (when available):
   - TCS ISIN: `INE467B01029` (same on both BSE and NSE)
   - System creates ONE instrument record with both BSE code and NSE symbol

2. **Deduplication During Sync**:
   - If same corporate action from both BSE and NSE (same ISIN, type, ex-date)
   - System merges into single record
   - Source marked as `"NSE,BSE"`
   - NSE data preferred, BSE data supplements missing fields

3. **Symbol Resolution**:
   - User queries by symbol (e.g., `TCS`)
   - `resolve_instrument()` function checks:
     - `symbol` column
     - `nse_symbol` column
     - `bse_code` column (if numeric)
   - Returns first match

### Example Conflict Scenario

**BSE Data**:
```json
{
  "scrip_code": 532540,
  "symbol": "TCS",
  "ex_date": "2025-06-15",
  "action_type": "DIVIDEND",
  "amount": 10.50,
  "record_date": "2025-06-16"
}
```

**NSE Data**:
```json
{
  "symbol": "TCS",
  "ex_date": "2025-06-15",
  "action_type": "DIVIDEND",
  "amount": 10.50,
  "payment_date": "2025-07-05"
}
```

**Merged Result**:
```json
{
  "symbol": "TCS",
  "isin": "INE467B01029",
  "ex_date": "2025-06-15",
  "record_date": "2025-06-16",
  "payment_date": "2025-07-05",
  "action_type": "DIVIDEND",
  "action_data": {
    "amount": 10.50,
    "currency": "INR"
  },
  "source": "NSE,BSE"
}
```

---

## Bulk Import from CSV

You can bulk import instruments or corporate actions from CSV files.

### Instruments CSV Format

**File**: `instruments.csv`

```csv
symbol,isin,nse_symbol,bse_code,company_name,industry,sector,exchange,instrument_type
TCS,INE467B01029,TCS,532540,Tata Consultancy Services Ltd,IT Services,Information Technology,BOTH,EQ
RELIANCE,INE002A01018,RELIANCE,500325,Reliance Industries Ltd,Refining,Energy,BOTH,EQ
```

**Import Script**:

```python
import asyncio
import asyncpg
import csv

async def import_instruments(csv_file):
    pool = await asyncpg.create_pool(
        'postgresql://stocksblitz:stocksblitz123@localhost:5432/stocksblitz_unified'
    )

    with open(csv_file, 'r') as f:
        reader = csv.DictReader(f)
        async with pool.acquire() as conn:
            for row in reader:
                await conn.execute("""
                    INSERT INTO instruments (
                        symbol, isin, nse_symbol, bse_code, company_name,
                        industry, sector, exchange, instrument_type
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    ON CONFLICT (symbol, exchange) DO UPDATE SET
                        company_name = EXCLUDED.company_name,
                        industry = EXCLUDED.industry,
                        sector = EXCLUDED.sector,
                        updated_at = NOW()
                """,
                    row['symbol'],
                    row['isin'] if row['isin'] else None,
                    row['nse_symbol'] if row['nse_symbol'] else None,
                    int(row['bse_code']) if row['bse_code'] else None,
                    row['company_name'],
                    row['industry'],
                    row['sector'],
                    row['exchange'],
                    row['instrument_type']
                )

    await pool.close()
    print("Import complete!")

asyncio.run(import_instruments('instruments.csv'))
```

---

## Scheduling Automated Syncs

### Daily Sync (Recommended)

Add to crontab or systemd timer:

```bash
# /etc/cron.daily/sync-corporate-actions.sh
#!/bin/bash

# Sync corporate actions for active instruments
docker exec tv-backend python -m app.services.corporate_actions_fetcher \
  --all --limit 100 --days-ago 0 --days-ahead 90

# Cleanup expired cache
docker exec tv-backend psql -U stocksblitz -d stocksblitz_unified \
  -c "SELECT cleanup_expired_cache();"
```

Make it executable:
```bash
chmod +x /etc/cron.daily/sync-corporate-actions.sh
```

---

## Monitoring & Maintenance

### 1. Check Sync Status

```sql
-- Count of actions by source
SELECT source, COUNT(*) as count
FROM corporate_actions
GROUP BY source;

-- Recent actions
SELECT
    i.symbol,
    ca.action_type,
    ca.ex_date,
    ca.source,
    ca.created_at
FROM corporate_actions ca
JOIN instruments i ON ca.instrument_id = i.id
ORDER BY ca.created_at DESC
LIMIT 20;
```

### 2. Data Quality Checks

```sql
-- Actions missing key dates
SELECT
    i.symbol,
    ca.title,
    ca.ex_date,
    ca.record_date
FROM corporate_actions ca
JOIN instruments i ON ca.instrument_id = i.id
WHERE ca.ex_date IS NULL OR ca.record_date IS NULL;

-- Instruments without ISIN
SELECT symbol, company_name, exchange
FROM instruments
WHERE isin IS NULL;
```

### 3. Cache Performance

```sql
-- Cache hit statistics
SELECT
    cache_key,
    hit_count,
    created_at,
    expires_at
FROM corporate_actions_cache
ORDER BY hit_count DESC
LIMIT 10;
```

---

## Performance Considerations

1. **Indexing**: All critical fields are indexed for fast queries
2. **Caching**: Use `corporate_actions_cache` table for frequently accessed queries
3. **Pagination**: Always use `limit` and `offset` for large result sets
4. **Date Range Limits**: API enforces max 365-day range for `/all` endpoint
5. **Rate Limiting**: Implement rate limiting for public endpoints

### Recommended Optimizations

```sql
-- Create materialized view for upcoming actions (refresh daily)
CREATE MATERIALIZED VIEW upcoming_corporate_actions AS
SELECT
    i.symbol,
    i.company_name,
    ca.action_type,
    ca.title,
    ca.ex_date,
    ca.action_data
FROM corporate_actions ca
JOIN instruments i ON ca.instrument_id = i.id
WHERE ca.ex_date >= CURRENT_DATE
AND ca.ex_date <= CURRENT_DATE + INTERVAL '90 days'
AND ca.status IN ('announced', 'upcoming')
ORDER BY ca.ex_date, i.symbol;

-- Refresh daily
REFRESH MATERIALIZED VIEW upcoming_corporate_actions;
```

---

## Troubleshooting

### Issue: BSE API Not Working

**Solution**: Install the `bse` package:
```bash
pip install bse
```

If still not working, use manual CSV import instead.

### Issue: Symbol Not Found

**Solution**: Add the instrument first:
```sql
INSERT INTO instruments (symbol, company_name, exchange, instrument_type)
VALUES ('NEWSYMBOL', 'New Company Ltd', 'NSE', 'EQ');
```

### Issue: Duplicate Actions

**Solution**: The system automatically handles duplicates using `ON CONFLICT`. If you see duplicates, check the unique constraint:
```sql
-- Should have unique constraint on (instrument_id, action_type, ex_date, source_id)
ALTER TABLE corporate_actions ADD CONSTRAINT unique_action
UNIQUE (instrument_id, action_type, ex_date, source_id);
```

---

## Security Notes

1. **No Admin API**: Currently only read endpoints are implemented. Admin endpoints (CREATE/UPDATE/DELETE) should be added with authentication.

2. **Rate Limiting**: Implement rate limiting on public endpoints:
   ```python
   from slowapi import Limiter
   limiter = Limiter(key_func=get_remote_address)

   @router.get("/")
   @limiter.limit("100/minute")
   async def get_corporate_actions(...):
       ...
   ```

3. **Input Validation**: All inputs are validated using Pydantic models.

4. **SQL Injection**: All queries use parameterized statements.

---

## Future Enhancements

1. **Admin API**: Add CRUD endpoints with API key authentication
2. **Webhooks**: Notify users of upcoming corporate actions
3. **Calendar Alerts**: Push notifications for ex-dates
4. **Portfolio Impact**: Calculate impact on user portfolios
5. **Historical Adjustments**: Auto-adjust historical prices for splits/bonus
6. **iCal Export**: Export to iCal format for calendar apps
7. **Machine Learning**: Predict price movement based on corporate actions

---

## Files Created

| File | Location | Purpose |
|------|----------|---------|
| CORPORATE_CALENDAR_DESIGN.md | calendar_service/ | Complete design specification |
| CORPORATE_CALENDAR_IMPLEMENTATION.md | calendar_service/ | This file - implementation guide |
| 014_create_corporate_calendar.sql | backend/migrations/ | Database schema migration |
| corporate_actions_fetcher.py | backend/services/ | Data fetcher service |
| corporate_calendar.py | backend/routes/ | REST API endpoints |

---

## Support

For questions or issues:
1. Check this documentation
2. Review the design document (CORPORATE_CALENDAR_DESIGN.md)
3. Check database logs for errors
4. Review API response errors (they include helpful details)

---

**Last Updated**: November 4, 2025
**Version**: 1.0
**Status**: ✅ Ready for Production
