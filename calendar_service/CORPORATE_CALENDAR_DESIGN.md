# Corporate Calendar Integration Design

## Overview

This document outlines the integration of corporate actions into the existing calendar_service. Corporate actions include dividends, bonus issues, stock splits, rights issues, AGM/EGM dates, book closures, and other company-specific events.

## Data Sources

### Primary Sources
- **BSE (Bombay Stock Exchange)**: https://www.bseindia.com/corporates/corporates_act.html
  - Unofficial API: BseIndiaApi (https://github.com/BennyThadikaran/BseIndiaApi)
- **NSE (National Stock Exchange)**: https://www.nseindia.com/companies-listing/corporate-filings-actions
  - Unofficial API: stock-market-india (https://github.com/maanavshah/stock-market-india)

### Data Fetching Strategy
1. Use unofficial APIs for development and testing
2. Schedule daily sync for corporate actions (end of day)
3. Cache results to minimize API calls
4. Provide manual import capability via CSV

## Corporate Action Types

| Type | BSE/NSE Code | Description | Key Dates |
|------|-------------|-------------|-----------|
| **DIVIDEND** | DIV | Cash dividend payment | Ex-date, Record date, Payment date |
| **BONUS** | BON | Bonus share issue | Ex-date, Record date, Ratio |
| **SPLIT** | SPL | Stock split/consolidation | Ex-date, Old FV, New FV, Ratio |
| **RIGHTS** | RIG | Rights issue | Ex-date, Record date, Ratio, Price |
| **AGM** | AGM | Annual General Meeting | Meeting date |
| **EGM** | EGM | Extra-ordinary General Meeting | Meeting date |
| **BOOK_CLOSURE** | BC | Book closure period | Start date, End date, Purpose |
| **BUYBACK** | BUY | Share buyback | Start date, End date, Price |
| **MERGER** | MRG | Merger/Amalgamation | Effective date |
| **DEMERGER** | DMR | Demerger/Spin-off | Effective date |

## Database Schema

### 1. Instruments Table (Symbol Resolution)

```sql
CREATE TABLE instruments (
    id SERIAL PRIMARY KEY,

    -- Symbol identification
    symbol TEXT NOT NULL,              -- Trading symbol (e.g., 'TCS', 'RELIANCE')
    isin TEXT UNIQUE,                  -- International Securities ID

    -- Exchange-specific codes
    nse_symbol TEXT,                   -- NSE trading symbol
    bse_code INTEGER,                  -- BSE scrip code

    -- Company info
    company_name TEXT NOT NULL,
    industry TEXT,
    sector TEXT,

    -- Metadata
    exchange TEXT NOT NULL,            -- 'NSE', 'BSE', 'BOTH'
    instrument_type TEXT DEFAULT 'EQ', -- 'EQ', 'FO', 'DEBT', etc.
    is_active BOOLEAN DEFAULT true,

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Constraints
    UNIQUE(symbol, exchange)
);

CREATE INDEX idx_instruments_symbol ON instruments(symbol);
CREATE INDEX idx_instruments_isin ON instruments(isin);
CREATE INDEX idx_instruments_nse_symbol ON instruments(nse_symbol);
CREATE INDEX idx_instruments_bse_code ON instruments(bse_code);
```

### 2. Corporate Actions Table

```sql
CREATE TABLE corporate_actions (
    id SERIAL PRIMARY KEY,

    -- Link to instrument
    instrument_id INTEGER REFERENCES instruments(id) ON DELETE CASCADE,

    -- Action identification
    action_type TEXT NOT NULL,         -- 'DIVIDEND', 'BONUS', 'SPLIT', etc.
    action_category TEXT DEFAULT 'corporate_action',

    -- Key dates
    ex_date DATE,                      -- Ex-date (most important for trading)
    record_date DATE,                  -- Record date
    announcement_date DATE,            -- When announced
    effective_date DATE,               -- When effective (for mergers, etc.)
    payment_date DATE,                 -- Payment date (for dividends)

    -- Date ranges (for book closure, buyback)
    start_date DATE,
    end_date DATE,

    -- Action-specific data (stored as JSONB for flexibility)
    action_data JSONB DEFAULT '{}',
    -- Examples:
    -- Dividend: {"amount": 10.50, "currency": "INR", "type": "interim|final"}
    -- Bonus: {"ratio": "1:2", "old_shares": 1, "new_shares": 2}
    -- Split: {"old_fv": 10, "new_fv": 2, "ratio": "1:5"}
    -- Rights: {"ratio": "1:3", "price": 150.00, "subscription_start": "2025-01-01", "subscription_end": "2025-01-15"}

    -- Display info
    title TEXT NOT NULL,               -- "Dividend - Rs 10.50 per share"
    description TEXT,
    purpose TEXT,                      -- Purpose of book closure, etc.

    -- Source tracking
    source TEXT NOT NULL,              -- 'BSE', 'NSE', 'manual', 'API'
    source_url TEXT,
    source_id TEXT,                    -- Original ID from source
    verified BOOLEAN DEFAULT false,

    -- Impact
    price_adjustment_factor DECIMAL(10, 6), -- For splits/bonus

    -- Status
    status TEXT DEFAULT 'announced',   -- 'announced', 'upcoming', 'completed', 'cancelled'

    -- Metadata
    notes TEXT,
    metadata JSONB DEFAULT '{}',

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Constraints
    CONSTRAINT valid_action_type CHECK (action_type IN (
        'DIVIDEND', 'BONUS', 'SPLIT', 'RIGHTS', 'AGM', 'EGM',
        'BOOK_CLOSURE', 'BUYBACK', 'MERGER', 'DEMERGER'
    )),
    CONSTRAINT valid_status CHECK (status IN ('announced', 'upcoming', 'completed', 'cancelled'))
);

-- Indexes for performance
CREATE INDEX idx_corporate_actions_instrument ON corporate_actions(instrument_id);
CREATE INDEX idx_corporate_actions_type ON corporate_actions(action_type);
CREATE INDEX idx_corporate_actions_ex_date ON corporate_actions(ex_date);
CREATE INDEX idx_corporate_actions_record_date ON corporate_actions(record_date);
CREATE INDEX idx_corporate_actions_source ON corporate_actions(source);
CREATE INDEX idx_corporate_actions_status ON corporate_actions(status);

-- Composite indexes for common queries
CREATE INDEX idx_corporate_actions_instrument_ex_date ON corporate_actions(instrument_id, ex_date);
CREATE INDEX idx_corporate_actions_type_ex_date ON corporate_actions(action_type, ex_date);
```

### 3. Corporate Actions Cache Table

```sql
CREATE TABLE corporate_actions_cache (
    id SERIAL PRIMARY KEY,

    -- Cache key
    cache_key TEXT UNIQUE NOT NULL,    -- e.g., "symbol:TCS:type:DIVIDEND:from:2025-01-01:to:2025-12-31"

    -- Cached data
    data JSONB NOT NULL,

    -- Cache metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    hit_count INTEGER DEFAULT 0,

    -- Constraints
    CONSTRAINT valid_expiry CHECK (expires_at > created_at)
);

CREATE INDEX idx_corporate_actions_cache_key ON corporate_actions_cache(cache_key);
CREATE INDEX idx_corporate_actions_cache_expiry ON corporate_actions_cache(expires_at);
```

## Symbol/Instrument Conflict Resolution

### Challenge
Same company may have different codes on BSE and NSE:
- TCS: NSE symbol = 'TCS', BSE code = 532540
- Reliance: NSE symbol = 'RELIANCE', BSE code = 500325

### Solution

1. **Use ISIN as primary identifier** (when available)
2. **Maintain mapping table** (instruments table with both NSE and BSE codes)
3. **Merge corporate actions** from both exchanges:
   - If same action (same ISIN, type, ex-date) from both BSE and NSE → merge into one record
   - If conflicting data → prefer NSE data (larger exchange), flag for manual review
   - Store source in metadata for audit trail

### Deduplication Logic

```python
def should_merge_actions(action1, action2):
    """
    Two corporate actions should be merged if they represent the same event
    """
    if action1['instrument_id'] != action2['instrument_id']:
        return False

    if action1['action_type'] != action2['action_type']:
        return False

    # Same ex-date (or within 1 day tolerance for data discrepancies)
    if abs((action1['ex_date'] - action2['ex_date']).days) > 1:
        return False

    return True

def merge_actions(nse_action, bse_action):
    """
    Merge corporate actions from NSE and BSE
    Prefer NSE data, supplement with BSE data where missing
    """
    merged = {**nse_action}  # Start with NSE data

    # Supplement missing fields from BSE
    for field in ['record_date', 'payment_date', 'announcement_date']:
        if not merged.get(field) and bse_action.get(field):
            merged[field] = bse_action[field]

    # Merge action_data
    merged['action_data'] = {**bse_action.get('action_data', {}), **nse_action.get('action_data', {})}

    # Track both sources
    merged['source'] = 'NSE,BSE'
    merged['metadata'] = {
        'nse_source_id': nse_action.get('source_id'),
        'bse_source_id': bse_action.get('source_id'),
        'merged_at': datetime.now().isoformat()
    }

    return merged
```

## API Endpoints

### Public Corporate Actions API

```python
# Get corporate actions for a symbol
GET /calendar/corporate-actions?symbol=TCS&from=2025-01-01&to=2025-12-31&type=DIVIDEND

# Get upcoming corporate actions
GET /calendar/corporate-actions/upcoming?days=30&type=DIVIDEND,BONUS

# Get corporate actions by ex-date
GET /calendar/corporate-actions/by-ex-date?date=2025-06-15

# Get all corporate actions for a date range (all symbols)
GET /calendar/corporate-actions/all?from=2025-01-01&to=2025-01-31

# Get specific corporate action details
GET /calendar/corporate-actions/{id}
```

### Admin API (CRUD Operations)

```python
# Create corporate action
POST /admin/calendar/corporate-actions

# Update corporate action
PUT /admin/calendar/corporate-actions/{id}

# Delete corporate action
DELETE /admin/calendar/corporate-actions/{id}

# Bulk import from CSV
POST /admin/calendar/corporate-actions/bulk-import

# Sync from BSE/NSE
POST /admin/calendar/corporate-actions/sync
```

## Data Fetcher Service

### Architecture

```
corporate_actions_fetcher.py
├── BSEFetcher
│   ├── fetch_corporate_actions(symbol, from_date, to_date)
│   ├── fetch_all_corporate_actions(from_date, to_date)
│   └── parse_bse_action(raw_data)
├── NSEFetcher
│   ├── fetch_corporate_actions(symbol, from_date, to_date)
│   ├── fetch_all_corporate_actions(from_date, to_date)
│   └── parse_nse_action(raw_data)
└── CorporateActionsSync
    ├── sync_from_bse(from_date, to_date)
    ├── sync_from_nse(from_date, to_date)
    ├── deduplicate_actions()
    └── update_database()
```

### Sync Strategy

1. **Daily Sync** (run at 8 PM IST after market close)
   - Fetch corporate actions for next 90 days
   - Update existing records
   - Mark completed actions

2. **Weekly Full Sync** (run on Sunday)
   - Fetch all corporate actions for next 365 days
   - Verify data integrity
   - Clean up old records (>2 years)

3. **On-Demand Sync**
   - Via Admin API endpoint
   - For specific symbol or date range

## Response Models

### CorporateAction Response

```python
{
    "id": 12345,
    "symbol": "TCS",
    "company_name": "Tata Consultancy Services Ltd",
    "isin": "INE467B01029",
    "action_type": "DIVIDEND",
    "title": "Dividend - Rs 10.50 per share",
    "ex_date": "2025-06-15",
    "record_date": "2025-06-16",
    "payment_date": "2025-07-05",
    "action_data": {
        "amount": 10.50,
        "currency": "INR",
        "type": "interim"
    },
    "source": "NSE,BSE",
    "status": "announced",
    "created_at": "2025-01-15T10:30:00Z"
}
```

### Upcoming Actions Summary

```python
{
    "summary": {
        "total_actions": 45,
        "by_type": {
            "DIVIDEND": 30,
            "BONUS": 5,
            "SPLIT": 3,
            "RIGHTS": 2,
            "AGM": 5
        }
    },
    "actions": [
        { /* CorporateAction object */ },
        { /* CorporateAction object */ }
    ]
}
```

## Integration with Existing Calendar Service

### Unified Calendar View

The corporate actions will integrate seamlessly with the existing market calendar:

```python
GET /calendar/status?calendar=NSE&symbol=TCS&date=2025-06-15

Response:
{
    "calendar_code": "NSE",
    "date": "2025-06-15",
    "is_trading_day": true,
    "is_holiday": false,
    "is_weekend": false,
    "current_session": "trading",
    "session_start": "09:15:00",
    "session_end": "15:30:00",

    // NEW: Corporate actions on this date
    "corporate_actions": [
        {
            "symbol": "TCS",
            "action_type": "DIVIDEND",
            "title": "Dividend - Rs 10.50 per share",
            "ex_date": "2025-06-15",
            "is_ex_date": true,
            "action_data": {
                "amount": 10.50,
                "currency": "INR",
                "type": "interim"
            }
        }
    ]
}
```

## Implementation Phases

### Phase 1: Schema & Core Infrastructure
1. Create database migrations (instruments, corporate_actions, cache tables)
2. Populate instruments table with NSE/BSE symbols
3. Create data models and ORM mappings

### Phase 2: Data Fetchers
1. Implement BSE fetcher using BseIndiaApi
2. Implement NSE fetcher (web scraping or unofficial API)
3. Create deduplication and merging logic
4. Add unit tests

### Phase 3: API Endpoints
1. Implement public API endpoints
2. Implement admin API endpoints
3. Add authentication for admin endpoints
4. Create API documentation

### Phase 4: Sync Service
1. Create background sync service
2. Add scheduling (daily/weekly)
3. Implement error handling and retry logic
4. Add monitoring and alerting

### Phase 5: Testing & Documentation
1. Integration tests
2. Performance testing
3. User documentation
4. API reference documentation

## Configuration

### Environment Variables

```bash
# Corporate Actions Configuration
CORPORATE_ACTIONS_ENABLED=true
CORPORATE_ACTIONS_SYNC_HOUR=20  # 8 PM IST

# Data Sources
BSE_API_ENABLED=true
NSE_API_ENABLED=true

# Cache settings
CORPORATE_ACTIONS_CACHE_TTL=3600  # 1 hour

# Sync settings
CORPORATE_ACTIONS_SYNC_DAYS_AHEAD=90
CORPORATE_ACTIONS_RETENTION_DAYS=730  # 2 years
```

## Data Quality & Validation

### Validation Rules

1. **Date Validation**
   - Ex-date must be before or same as record date
   - Record date must be before payment date
   - Start date must be before end date (for book closure)

2. **Data Completeness**
   - Required fields: instrument_id, action_type, title, source
   - At least one key date (ex_date or record_date or announcement_date)

3. **Deduplication**
   - Check for duplicate actions (same instrument, type, ex-date)
   - Merge or flag conflicts

4. **Symbol Resolution**
   - Validate symbol exists in instruments table
   - Handle missing ISIN gracefully
   - Log unresolved symbols for manual review

## Security Considerations

1. **API Key Authentication** for admin endpoints
2. **Rate Limiting** on public endpoints
3. **Input Validation** for all parameters
4. **SQL Injection Prevention** using parameterized queries
5. **Audit Logging** for all data modifications

## Monitoring & Alerts

### Metrics to Track

1. **Sync Status**
   - Last successful sync timestamp
   - Number of actions synced
   - Errors during sync

2. **API Performance**
   - Request count
   - Response time (p50, p95, p99)
   - Error rate

3. **Data Quality**
   - Number of unresolved symbols
   - Number of conflicts/duplicates
   - Number of validation failures

### Alerts

1. **Sync Failure** - Alert if sync fails for > 2 consecutive runs
2. **High Error Rate** - Alert if API error rate > 5%
3. **Data Staleness** - Alert if last sync > 48 hours ago

## Future Enhancements

1. **Calendar Alerts** - Notify users of upcoming corporate actions for their watchlist
2. **Portfolio Impact** - Calculate impact of corporate actions on user portfolio
3. **Historical Adjustments** - Adjust historical prices for splits/bonus
4. **Corporate Actions Calendar UI** - Visual calendar view with corporate actions
5. **Export to iCal/Google Calendar** - Allow users to subscribe to corporate actions calendar
6. **Machine Learning** - Predict stock price movement based on corporate action patterns

---

**Last Updated**: 2025-11-04
**Status**: Design Phase
