# Special Trading Hours - Complete Guide

## Overview

The Calendar Service supports special trading hours for events like:
- 🪔 **Muhurat Trading** (Diwali evening sessions)
- ⏰ **Early Market Close** (half-day sessions)
- 📈 **Extended Hours** (special trading windows)

This feature allows markets to have trading sessions outside regular hours, including on weekends and holidays.

---

## 🎯 Key Concepts

### Regular Trading Hours

```
Monday-Friday
Pre-market: 09:00 - 09:15
Trading:    09:15 - 15:30
Post-market: 15:40 - 16:00
```

### Special Trading Hours

**Muhurat Trading Example**:
```
Sunday (normally closed)
Special session: 18:15 - 19:15
```

**Early Close Example**:
```
Friday (half-day)
Trading: 09:15 - 13:00 (instead of 15:30)
```

---

## 📊 How It Works

### 1. Database Schema

Special hours are stored in the `calendar_events` table:

```sql
CREATE TABLE calendar_events (
    id SERIAL PRIMARY KEY,
    calendar_type_id INTEGER NOT NULL,
    event_date DATE NOT NULL,
    event_name TEXT NOT NULL,
    event_type TEXT DEFAULT 'holiday',  -- ← Key field
    is_trading_day BOOLEAN DEFAULT false,
    special_start TIME,  -- ← Special session start
    special_end TIME,    -- ← Special session end
    category TEXT DEFAULT 'market_holiday',
    ...
);
```

### 2. Event Types

| Event Type | Description | Example |
|------------|-------------|---------|
| `holiday` | Regular market holiday | Republic Day |
| `special_hours` | Complete custom hours | Muhurat Trading (18:15-19:15) |
| `early_close` | Early market close | Christmas Eve (close at 13:00) |
| `extended_hours` | Extended trading | Special event (trade until 17:00) |

### 3. Detection Logic

When checking market status, the API:

1. **Checks for special event** first
   ```sql
   SELECT event_name, special_start, special_end
   FROM calendar_events
   WHERE event_type IN ('special_hours', 'early_close', 'extended_hours')
   AND is_trading_day = true
   ```

2. **If special event found**: Use special hours
3. **Otherwise**: Use regular trading hours

---

## 🪔 Muhurat Trading

### What is Muhurat Trading?

Muhurat Trading is a **special 1-hour evening trading session** held on Diwali, the Hindu festival of lights. It's considered auspicious in Indian culture.

**Characteristics**:
- 📅 Occurs on Diwali day (usually a holiday)
- 🌙 Evening session: 18:15 - 19:15 IST
- ✅ Trading allowed (even on weekend/holiday)
- 💰 Symbolic trades to mark the new Samvat year

### Creating Muhurat Trading Event

#### Using Admin API

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

### Checking Muhurat Trading Status

```bash
curl "http://localhost:8081/calendar/status?calendar=NSE&check_date=2026-11-01"
```

**Response**:
```json
{
  "calendar_code": "NSE",
  "date": "2026-11-01",
  "is_trading_day": true,           // ✅ Trading allowed
  "is_holiday": false,
  "is_weekend": true,                // 🗓️ Sunday
  "current_session": "closed",
  "holiday_name": null,
  "session_start": "18:15:00",      // 🕕 Special hours!
  "session_end": "19:15:00",        // 🕖 Not regular 09:15-15:30
  "next_trading_day": null,
  "is_special_session": true,       // 🎯 Key indicator
  "special_event_name": "Muhurat Trading (Diwali 2026)",
  "event_type": "special_hours"
}
```

### Key Observations

✅ **Trading Day**: Even though it's a Sunday (weekend), `is_trading_day = true`

✅ **Special Hours**: Session is 18:15-19:15, not regular 09:15-15:30

✅ **Event Detection**: `is_special_session = true` clearly marks this as special

✅ **Event Name**: Client can display "Muhurat Trading (Diwali 2026)"

---

## 🕐 Early Market Close

### Use Case

Markets close early before major holidays (e.g., Christmas Eve).

### Example

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

**Note**: For early close, you typically only need `special_end`. The market will:
- Open at regular time (09:15)
- Close early (13:00 instead of 15:30)

### Status Response

```json
{
  "calendar_code": "NSE",
  "date": "2027-12-24",
  "is_trading_day": true,
  "is_special_session": true,
  "special_event_name": "Christmas Eve - Early Close",
  "event_type": "early_close",
  "session_start": "09:15:00",  // Regular open
  "session_end": "13:00:00"     // Early close
}
```

---

## 📈 Extended Trading Hours

### Use Case

Special events requiring extended trading beyond regular hours.

### Example

```bash
curl -X POST "http://localhost:8081/admin/calendar/holidays" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: change-me-in-production" \
  -d '{
    "calendar": "NSE",
    "date": "2027-03-15",
    "name": "Special Trading Session",
    "event_type": "extended_hours",
    "is_trading_day": true,
    "special_start": "09:15:00",
    "special_end": "17:00:00",
    "category": "special_session",
    "description": "Extended trading for special event"
  }'
```

---

## 🔄 Current Session Detection

The API also determines the **current session** based on time:

### Regular Day (9:15 AM - 3:30 PM)

```bash
# Query at 10:00 AM
curl "http://localhost:8081/calendar/status?calendar=NSE"
```

**Response**:
```json
{
  "current_session": "trading",
  "session_start": "09:15:00",
  "session_end": "15:30:00"
}
```

### Muhurat Trading (6:15 PM - 7:15 PM)

```bash
# Query at 6:30 PM on Diwali
curl "http://localhost:8081/calendar/status?calendar=NSE&check_date=2026-11-01"
```

**Response**:
```json
{
  "current_session": "trading",    // ✅ If checked at 18:30
  "session_start": "18:15:00",
  "session_end": "19:15:00",
  "is_special_session": true
}
```

### Outside Trading Hours

```json
{
  "current_session": "closed"
}
```

---

## 🗓️ Historical Examples

### NSE Muhurat Trading Dates

| Year | Date | Day | Time |
|------|------|-----|------|
| 2024 | Nov 1 | Friday | 18:15-19:15 |
| 2025 | Oct 20 | Monday | 18:15-19:15 |
| 2026 | Nov 8 | Sunday | 18:15-19:15 |
| 2027 | Oct 28 | Thursday | 18:15-19:15 |

### CSV for Bulk Import

```csv
date,name,event_type,is_trading_day,special_start,special_end,category,description
2024-11-01,Muhurat Trading 2024,special_hours,true,18:15,19:15,special_session,Diwali trading
2025-10-20,Muhurat Trading 2025,special_hours,true,18:15,19:15,special_session,Diwali trading
2026-11-08,Muhurat Trading 2026,special_hours,true,18:15,19:15,special_session,Diwali trading
2027-10-28,Muhurat Trading 2027,special_hours,true,18:15,19:15,special_session,Diwali trading
```

---

## 💻 Client Integration

### Detecting Special Sessions

```python
import requests

def is_market_open(calendar="NSE", check_date=None):
    response = requests.get(
        f"http://localhost:8081/calendar/status",
        params={"calendar": calendar, "check_date": check_date}
    )
    status = response.json()

    # Check if trading day
    if not status['is_trading_day']:
        return False, "Market closed"

    # Check for special session
    if status['is_special_session']:
        return True, f"Special session: {status['special_event_name']}"

    # Regular trading
    return True, "Regular trading hours"

# Example usage
is_open, reason = is_market_open(check_date="2026-11-01")
print(f"Market open: {is_open} - {reason}")
# Output: Market open: True - Special session: Muhurat Trading (Diwali 2026)
```

### Display Special Hours in UI

```javascript
async function getMarketStatus(date) {
  const response = await fetch(
    `/calendar/status?calendar=NSE&check_date=${date}`
  );
  const status = await response.json();

  if (status.is_special_session) {
    return {
      type: 'special',
      name: status.special_event_name,
      hours: `${status.session_start} - ${status.session_end}`,
      eventType: status.event_type
    };
  }

  return {
    type: 'regular',
    hours: `${status.session_start} - ${status.session_end}`
  };
}

// Display in UI
const marketInfo = await getMarketStatus('2026-11-01');
if (marketInfo.type === 'special') {
  console.log(`🎉 ${marketInfo.name}`);
  console.log(`⏰ Special hours: ${marketInfo.hours}`);
}
```

---

## 🧪 Testing Special Hours

### Test Setup

```bash
# 1. Create Muhurat trading event
curl -X POST "http://localhost:8081/admin/calendar/holidays" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: change-me-in-production" \
  -d '{
    "calendar": "NSE",
    "date": "2026-11-01",
    "name": "Muhurat Trading Test",
    "event_type": "special_hours",
    "is_trading_day": true,
    "special_start": "18:15:00",
    "special_end": "19:15:00",
    "category": "special_session"
  }'
```

### Verification Checklist

✅ **Test 1**: Verify event created
```bash
curl "http://localhost:8081/calendar/status?calendar=NSE&check_date=2026-11-01"
# Expect: is_special_session = true
```

✅ **Test 2**: Check special hours
```bash
# session_start should be 18:15:00, not 09:15:00
# session_end should be 19:15:00, not 15:30:00
```

✅ **Test 3**: Trading day on weekend
```bash
# is_trading_day should be true even if is_weekend = true
```

✅ **Test 4**: Event name displayed
```bash
# special_event_name should be "Muhurat Trading Test"
# event_type should be "special_hours"
```

---

## 🎓 Best Practices

### 1. Naming Conventions

```bash
# ✅ Good: Descriptive with year
"Muhurat Trading (Diwali 2026)"
"Christmas Eve - Early Close 2027"

# ❌ Bad: Generic names
"Special Session"
"Holiday"
```

### 2. Time Format

```bash
# ✅ Good: Full HH:MM:SS format
"special_start": "18:15:00"

# ⚠️ Also works: HH:MM (adds :00 automatically)
"special_start": "18:15"
```

### 3. Category Selection

| Event Type | Recommended Category |
|------------|---------------------|
| special_hours | `special_session` |
| early_close | `early_close` |
| extended_hours | `extended_hours` |
| holiday | `market_holiday` |

### 4. Validation

```python
def validate_special_hours(event):
    if event['event_type'] == 'special_hours':
        # Both start and end required
        assert event.get('special_start'), "Missing special_start"
        assert event.get('special_end'), "Missing special_end"

    if event['event_type'] == 'early_close':
        # Only end required
        assert event.get('special_end'), "Missing special_end"

    # Trading day must be true for special hours
    if event['event_type'] in ['special_hours', 'early_close', 'extended_hours']:
        assert event['is_trading_day'], "is_trading_day must be true"
```

---

## 📚 Reference

### API Fields Summary

| Field | Type | Purpose | Example |
|-------|------|---------|---------|
| `event_type` | string | Type of special event | `special_hours` |
| `is_trading_day` | boolean | Allow trading? | `true` |
| `special_start` | time | Custom start time | `18:15:00` |
| `special_end` | time | Custom end time | `19:15:00` |
| `is_special_session` | boolean | (Output) Special session? | `true` |
| `special_event_name` | string | (Output) Event name | `Muhurat Trading` |

### Trading Session Types

```
Regular Day:
  Pre-market:  09:00 - 09:15
  Trading:     09:15 - 15:30
  Post-market: 15:40 - 16:00

Special Hours (Muhurat):
  Trading:     18:15 - 19:15

Early Close:
  Trading:     09:15 - 13:00

Extended Hours:
  Trading:     09:15 - 17:00
```

---

## 🔗 Related Documentation

- [Admin API Guide](07_ADMIN_API.md) - Creating special hours events
- [Integration Guide](03_INTEGRATION_GUIDE.md) - Using the calendar API
- [Quick Start](04_QUICK_START.md) - Getting started
- [QA Guide](05_QA.md) - Common questions

---

**Version**: 1.0
**Last Updated**: 2025-11-01
**Production Status**: ✅ Ready
