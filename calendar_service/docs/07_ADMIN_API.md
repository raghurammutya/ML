# Calendar Admin API - Complete Guide

## Overview

The Calendar Admin API provides complete CRUD operations for managing market holidays, special trading sessions, and calendar events without requiring direct database access.

**Version**: 1.0
**Base URL**: `/admin/calendar`
**Authentication**: API Key (X-API-Key header)

---

## 🔐 Authentication

All admin endpoints require API key authentication via the `X-API-Key` header.

### Setting Up API Key

**Development**:
```bash
# Default key (change in production!)
export CALENDAR_ADMIN_API_KEY="change-me-in-production"
```

**Production**:
```bash
# Generate secure key
export CALENDAR_ADMIN_API_KEY="$(openssl rand -hex 32)"
```

### Using API Key

```bash
curl -H "X-API-Key: your-api-key-here" \
  http://localhost:8081/admin/calendar/holidays
```

**Security Notes**:
- ⚠️ NEVER commit API keys to version control
- 🔒 Use environment variables or secrets management
- 🔄 Rotate keys regularly
- 📝 Log all admin API access for audit trail

---

## 📋 Endpoints

### 1. Create Holiday

**POST** `/admin/calendar/holidays`

Create a new holiday or special trading session.

#### Request Body

```json
{
  "calendar": "NSE",
  "date": "2026-11-01",
  "name": "Muhurat Trading (Diwali 2026)",
  "event_type": "special_hours",
  "is_trading_day": true,
  "special_start": "18:15:00",
  "special_end": "19:15:00",
  "category": "special_session",
  "description": "Diwali Muhurat Trading - Special evening session"
}
```

#### Parameters

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| calendar | string | Yes | Calendar code (NSE, BSE, MCX, etc.) |
| date | date | Yes | Event date (YYYY-MM-DD) |
| name | string | Yes | Holiday/event name |
| event_type | string | No | Event type (default: "holiday") |
| is_trading_day | boolean | No | Trading allowed? (default: false) |
| special_start | time | No | Special session start (HH:MM:SS) |
| special_end | time | No | Special session end (HH:MM:SS) |
| category | string | No | Category (default: "market_holiday") |
| description | string | No | Additional description |

#### Event Types

| Type | Description | Example |
|------|-------------|---------|
| `holiday` | Regular market holiday | Republic Day |
| `special_hours` | Special trading session | Muhurat Trading |
| `early_close` | Early market close | Half-day before holiday |
| `extended_hours` | Extended trading hours | Special event |

#### Response

```json
{
  "id": 2035,
  "calendar": "NSE",
  "date": "2026-11-01",
  "name": "Muhurat Trading (Diwali 2026)",
  "event_type": "special_hours",
  "is_trading_day": true,
  "special_start": "18:15:00",
  "special_end": "19:15:00",
  "category": "special_session",
  "description": "Diwali Muhurat Trading - Special evening session",
  "created_at": "2025-11-01 14:21:33.490443+00:00"
}
```

#### Example

```bash
curl -X POST "http://localhost:8081/admin/calendar/holidays" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: change-me-in-production" \
  -d '{
    "calendar": "NSE",
    "date": "2026-11-01",
    "name": "Muhurat Trading (Diwali 2026)",
    "event_type": "special_hours",
    "is_trading_day": true,
    "special_start": "18:15:00",
    "special_end": "19:15:00",
    "category": "special_session",
    "description": "Diwali Muhurat Trading - Special evening session"
  }'
```

---

### 2. Get Holiday by ID

**GET** `/admin/calendar/holidays/{holiday_id}`

Retrieve details of a specific holiday.

#### Example

```bash
curl -H "X-API-Key: change-me-in-production" \
  http://localhost:8081/admin/calendar/holidays/2035
```

#### Response

```json
{
  "id": 2035,
  "calendar": "NSE",
  "date": "2026-11-01",
  "name": "Muhurat Trading (Diwali 2026)",
  "event_type": "special_hours",
  "is_trading_day": true,
  "special_start": "18:15:00",
  "special_end": "19:15:00",
  "category": "special_session",
  "description": "Diwali Muhurat Trading - Special evening session",
  "created_at": "2025-11-01 14:21:33.490443+00:00"
}
```

---

### 3. Update Holiday

**PUT** `/admin/calendar/holidays/{holiday_id}`

Update an existing holiday. Only provided fields will be updated.

#### Request Body

```json
{
  "description": "Updated description",
  "special_end": "19:30:00"
}
```

#### Parameters

All fields from create are optional. Only include fields you want to update.

#### Example

```bash
curl -X PUT "http://localhost:8081/admin/calendar/holidays/2035" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: change-me-in-production" \
  -d '{
    "description": "Diwali Muhurat Trading - Updated description"
  }'
```

#### Response

Returns updated holiday object (same format as GET).

---

### 4. Delete Holiday

**DELETE** `/admin/calendar/holidays/{holiday_id}`

Delete a holiday from the calendar.

#### Example

```bash
curl -X DELETE \
  -H "X-API-Key: change-me-in-production" \
  http://localhost:8081/admin/calendar/holidays/2035
```

#### Response

```json
{
  "status": "deleted",
  "holiday": "Muhurat Trading (Diwali 2026)",
  "date": "2026-11-01"
}
```

---

### 5. Bulk Import Holidays

**POST** `/admin/calendar/holidays/bulk-import?calendar=NSE`

Import multiple holidays from a CSV file.

#### CSV Format

```csv
date,name,event_type,is_trading_day,special_start,special_end,category,description
2027-01-26,Republic Day,holiday,false,,,market_holiday,National holiday
2027-11-07,Muhurat Trading 2027,special_hours,true,18:15,19:15,special_session,Diwali trading
```

#### CSV Columns

| Column | Required | Description | Example |
|--------|----------|-------------|---------|
| date | Yes | Event date | 2027-01-26 |
| name | Yes | Event name | Republic Day |
| event_type | No | Type of event | holiday, special_hours |
| is_trading_day | No | Trading allowed | true, false |
| special_start | No | Start time | 18:15 |
| special_end | No | End time | 19:15 |
| category | No | Category | market_holiday |
| description | No | Description | National holiday |

#### Example

```bash
curl -X POST \
  "http://localhost:8081/admin/calendar/holidays/bulk-import?calendar=NSE" \
  -H "X-API-Key: change-me-in-production" \
  -F "file=@holidays_2027.csv"
```

#### Response

```json
{
  "status": "completed",
  "calendar": "NSE",
  "imported": 14,
  "updated": 0,
  "failed": 0,
  "errors": []
}
```

**Features**:
- ✅ Upsert logic: Updates existing holidays, creates new ones
- ✅ Atomic: All succeed or all fail per row
- ✅ Error reporting: First 10 errors returned
- ✅ Conflict resolution: Uses (calendar, date, name) as unique key

---

## 🎯 Common Use Cases

### 1. Adding Regular Holiday

```bash
curl -X POST "http://localhost:8081/admin/calendar/holidays" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: change-me-in-production" \
  -d '{
    "calendar": "NSE",
    "date": "2027-01-26",
    "name": "Republic Day",
    "category": "market_holiday",
    "description": "National holiday"
  }'
```

### 2. Adding Muhurat Trading (Special Hours)

```bash
curl -X POST "http://localhost:8081/admin/calendar/holidays" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: change-me-in-production" \
  -d '{
    "calendar": "NSE",
    "date": "2027-11-07",
    "name": "Muhurat Trading 2027",
    "event_type": "special_hours",
    "is_trading_day": true,
    "special_start": "18:15:00",
    "special_end": "19:15:00",
    "category": "special_session",
    "description": "Diwali special evening trading"
  }'
```

### 3. Early Market Close

```bash
curl -X POST "http://localhost:8081/admin/calendar/holidays" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: change-me-in-production" \
  -d '{
    "calendar": "NSE",
    "date": "2027-12-24",
    "name": "Christmas Eve - Early Close",
    "event_type": "early_close",
    "is_trading_day": true,
    "special_end": "13:00:00",
    "category": "early_close",
    "description": "Half-day trading before Christmas"
  }'
```

### 4. Bulk Import Year's Holidays

```bash
# Create CSV file
cat > holidays_2027.csv << EOF
date,name,event_type,is_trading_day,special_start,special_end,category,description
2027-01-26,Republic Day,holiday,false,,,market_holiday,National holiday
2027-03-11,Mahashivratri,holiday,false,,,market_holiday,Religious holiday
2027-11-07,Muhurat Trading 2027,special_hours,true,18:15,19:15,special_session,Diwali trading
EOF

# Import
curl -X POST \
  "http://localhost:8081/admin/calendar/holidays/bulk-import?calendar=NSE" \
  -H "X-API-Key: change-me-in-production" \
  -F "file=@holidays_2027.csv"
```

---

## ⚠️ Error Handling

### Invalid Calendar

```json
{
  "detail": "Calendar 'INVALID' not found. Valid calendars: BSE, MCX, NCDEX, NSE, NSE_CURRENCY"
}
```

### Duplicate Holiday

```json
{
  "detail": "Holiday 'Republic Day' already exists for 2027-01-26"
}
```

### Missing Special Hours

```json
{
  "detail": [
    {
      "loc": ["body", "special_start"],
      "msg": "special_start and special_end required for special_hours events",
      "type": "value_error"
    }
  ]
}
```

### Unauthorized

```json
{
  "detail": "Invalid API key"
}
```

---

## 🔍 Audit Trail

All admin operations are logged:

```json
{
  "time": "2025-11-01 14:21:33.490443",
  "level": "INFO",
  "logger": "app.routes.admin_calendar",
  "message": "Holiday created: Muhurat Trading (Diwali 2026) on 2026-11-01 for NSE (type: special_hours)"
}
```

**Logged Events**:
- Holiday created
- Holiday updated
- Holiday deleted
- Bulk import completed
- Failed API key attempts

---

## 🚀 Best Practices

### 1. API Key Security

```bash
# ❌ DON'T: Hard-code API keys
curl -H "X-API-Key: my-secret-key" ...

# ✅ DO: Use environment variables
export CALENDAR_ADMIN_API_KEY="$(openssl rand -hex 32)"
curl -H "X-API-Key: $CALENDAR_ADMIN_API_KEY" ...
```

### 2. Bulk Import vs Individual

- **Use bulk import** for: Initial setup, yearly updates, multiple holidays
- **Use individual POST** for: Single holiday, immediate needs, one-off changes

### 3. Testing Before Production

```bash
# 1. Test on development first
curl -X POST "http://localhost:8081/admin/calendar/holidays" ...

# 2. Verify with GET
curl "http://localhost:8081/calendar/status?check_date=2027-11-07"

# 3. Rollback if needed
curl -X DELETE "http://localhost:8081/admin/calendar/holidays/2035"
```

### 4. Validation

```bash
# Validate CSV before import
python3 << EOF
import csv
with open('holidays_2027.csv') as f:
    reader = csv.DictReader(f)
    for i, row in enumerate(reader, start=2):
        # Check required fields
        assert row['date'], f"Row {i}: Missing date"
        assert row['name'], f"Row {i}: Missing name"
        print(f"Row {i}: ✓ {row['name']}")
EOF
```

---

## 📊 Integration Examples

### Python

```python
import requests

API_KEY = "change-me-in-production"
BASE_URL = "http://localhost:8081/admin/calendar"

def create_holiday(calendar, date, name, **kwargs):
    response = requests.post(
        f"{BASE_URL}/holidays",
        headers={"X-API-Key": API_KEY},
        json={
            "calendar": calendar,
            "date": date,
            "name": name,
            **kwargs
        }
    )
    return response.json()

# Create Muhurat trading
result = create_holiday(
    calendar="NSE",
    date="2027-11-07",
    name="Muhurat Trading 2027",
    event_type="special_hours",
    is_trading_day=True,
    special_start="18:15:00",
    special_end="19:15:00",
    category="special_session"
)

print(f"Created holiday ID: {result['id']}")
```

### Shell Script

```bash
#!/bin/bash
# bulk_add_holidays.sh

API_KEY="change-me-in-production"
BASE_URL="http://localhost:8081/admin/calendar"

# Add multiple holidays
for holiday in \
  "2027-01-26|Republic Day" \
  "2027-08-15|Independence Day" \
  "2027-10-02|Gandhi Jayanti"
do
  IFS='|' read -r date name <<< "$holiday"
  curl -X POST "$BASE_URL/holidays" \
    -H "Content-Type: application/json" \
    -H "X-API-Key: $API_KEY" \
    -d "{\"calendar\":\"NSE\",\"date\":\"$date\",\"name\":\"$name\"}"
  echo ""
done
```

---

## 🔗 See Also

- [Calendar API Guide](03_INTEGRATION_GUIDE.md) - Using the calendar API
- [Special Hours Support](08_SPECIAL_HOURS.md) - Muhurat trading documentation
- [Deployment Guide](02_DEPLOYMENT.md) - Production deployment
- [Quick Start](04_QUICK_START.md) - Getting started

---

**Version**: 1.0
**Last Updated**: 2025-11-01
