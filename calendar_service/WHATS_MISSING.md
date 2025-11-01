# Calendar Service - What's Built vs What's Missing

## 🔍 CLARIFICATION

You're right to be confused! The **database schema supports** special hours, but the **API doesn't use it yet**. Here's the breakdown:

---

## 1. ADMIN API - Current State

### ✅ What You HAVE (Read-Only)

```bash
# Get market status
GET /calendar/status?calendar=NSE

# List holidays
GET /calendar/holidays?calendar=NSE&year=2025

# Next trading day
GET /calendar/next-trading-day?calendar=NSE

# List calendars
GET /calendar/calendars
```

### ❌ What's MISSING (Write Operations)

**No way to add/edit holidays without SQL!**

Currently, to add a holiday, you must:
```sql
-- Manually write SQL
INSERT INTO calendar_events (
    calendar_type_id, event_date, event_name,
    is_trading_day, category
) VALUES (
    (SELECT id FROM calendar_types WHERE code = 'NSE'),
    '2026-01-26', 'Republic Day',
    false, 'market_holiday'
);
```

**What Admin API would give you:**
```bash
# Easy API call instead
curl -X POST http://localhost:8081/admin/holidays \
  -H "Content-Type: application/json" \
  -d '{
    "calendar": "NSE",
    "date": "2026-01-26",
    "name": "Republic Day"
  }'
```

---

## 2. SPECIAL HOURS - Current State

### ✅ Database Schema HAS It

```sql
-- Table structure supports special hours:
CREATE TABLE calendar_events (
    event_type TEXT,        -- ✅ 'special_hours'
    special_start TIME,     -- ✅ For Muhurat: 18:15
    special_end TIME,       -- ✅ For Muhurat: 19:15
    ...
);
```

### ❌ API Doesn't CHECK For It

**Current API Query (calendar_simple.py:251-257)**:
```python
# Only gets basic holiday info
holiday = await conn.fetchrow("""
    SELECT event_name, is_trading_day
    FROM calendar_events
    WHERE ct.code = $1 AND ce.event_date = $2
    AND ce.category = 'market_holiday'
""", calendar_code, check_date)

# ❌ Doesn't check event_type
# ❌ Doesn't check special_start/special_end
```

**What's Missing**:
```python
# Should ALSO check for special hours:
special_event = await conn.fetchrow("""
    SELECT event_name, special_start, special_end
    FROM calendar_events
    WHERE ct.code = $1 AND ce.event_date = $2
    AND ce.event_type = 'special_hours'  -- ❌ Not checked!
""", calendar_code, check_date)
```

---

## 📊 SIDE-BY-SIDE COMPARISON

### Example: Diwali Muhurat Trading

**Database CAN Store**:
```sql
INSERT INTO calendar_events (
    calendar_type_id, event_date, event_name, event_type,
    is_trading_day, special_start, special_end
) VALUES (
    (SELECT id FROM calendar_types WHERE code = 'NSE'),
    '2025-11-01', 'Muhurat Trading', 'special_hours',
    true, '18:15:00', '19:15:00'
);
```

**But API Returns**:
```json
{
  "calendar_code": "NSE",
  "date": "2025-11-01",
  "is_trading_day": false,
  "is_holiday": true,
  "holiday_name": "Diwali Laxmi Pujan",
  "session_start": "09:15:00",
  "session_end": "15:30:00"
  // ❌ No special_start/special_end
  // ❌ Shows regular hours instead of 18:15-19:15
}
```

**What It SHOULD Return** (with enhancement):
```json
{
  "calendar_code": "NSE",
  "date": "2025-11-01",
  "is_trading_day": true,
  "is_special_session": true,
  "event_name": "Muhurat Trading",
  "session_start": "18:15:00",  // ✅ Special hours
  "session_end": "19:15:00",    // ✅ Not regular 9:15-15:30
  "current_session": "trading"  // ✅ If checked at 18:30
}
```

---

## 🔧 WHAT NEEDS TO BE BUILT

### 1. Admin API (3 days of work)

**Files to Create**:
- `backend/app/routes/admin_calendar.py` (new file)

**Endpoints to Add**:
```python
@router.post("/admin/holidays")
async def create_holiday(...):
    """Create new holiday/special session"""
    pass

@router.put("/admin/holidays/{id}")
async def update_holiday(...):
    """Update existing holiday"""
    pass

@router.delete("/admin/holidays/{id}")
async def delete_holiday(...):
    """Delete holiday"""
    pass

@router.post("/admin/holidays/bulk-import")
async def bulk_import(file: UploadFile):
    """Import from CSV"""
    pass
```

**Benefits**:
- No SQL needed
- Web UI can manage holidays
- Bulk import capability
- Auto cache invalidation

---

### 2. Special Hours Logic (2 days of work)

**Files to Modify**:
- `backend/app/routes/calendar_simple.py` (update existing)

**Changes Needed**:
```python
# Add to get_market_status():

# Check for special hours event
special_event = await conn.fetchrow("""
    SELECT event_name, event_type, special_start, special_end
    FROM calendar_events ce
    JOIN calendar_types ct ON ce.calendar_type_id = ct.id
    WHERE ct.code = $1 AND ce.event_date = $2
    AND ce.event_type = 'special_hours'
    AND ce.is_trading_day = true
""", calendar_code, check_date)

if special_event:
    # Use special hours instead of regular hours
    session_start = special_event['special_start']
    session_end = special_event['special_end']
    is_special_session = True
else:
    # Use regular trading hours
    session_start = session['trading_start']
    session_end = session['trading_end']
    is_special_session = False
```

**Benefits**:
- Muhurat trading support
- Early market close
- Extended hours
- Uses existing schema!

---

## 📝 CURRENT WORKAROUND

### How to Add Muhurat Trading TODAY (without Admin API)

**Step 1: Insert into database**:
```sql
-- Connect to database
PGPASSWORD=stocksblitz123 psql -U stocksblitz -d stocksblitz_unified

-- Add Muhurat trading
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
    '2025-11-01',
    'Muhurat Trading',
    'special_hours',
    true,
    '18:15:00',
    '19:15:00',
    'special_session',
    'NSE Official'
);
```

**Step 2: API won't use it yet**
- Data is stored ✅
- But `/calendar/status` ignores it ❌
- Need enhancement #4 from roadmap

---

## 🎯 SUMMARY

| Feature | Schema | API | Status |
|---------|--------|-----|--------|
| **Basic holidays** | ✅ | ✅ | Working |
| **Trading hours** | ✅ | ✅ | Working |
| **Special hours storage** | ✅ | ❌ | **Not used** |
| **Special hours detection** | ✅ | ❌ | **Not implemented** |
| **Admin API (create)** | ✅ | ❌ | **Missing** |
| **Admin API (update)** | ✅ | ❌ | **Missing** |
| **Admin API (delete)** | ✅ | ❌ | **Missing** |
| **Bulk import** | ✅ | ❌ | **Missing** |

---

## 💡 RECOMMENDATION

**Immediate (This Week)**:
1. Build Admin API (3 days) - Highest productivity boost
2. Add special hours logic (2 days) - Essential for Indian markets

**Result**:
- No more SQL for holiday management ✅
- Muhurat trading works correctly ✅
- Early market close supported ✅
- Ready for Diwali 2026 ✅

**Total Effort**: 5 days (1 week)

---

**Questions?**
- Schema has it, API doesn't use it yet
- Admin API is completely missing
- Both are quick wins (1 week total)
