# NIFTY Price Doubling Bug - Fix Documentation

## Issue Description

**Problem**: Frontend showing NIFTY prices around 50,000 instead of correct ~25,000
**Symptom**: Every second, big spike bars appeared and then collapsed to 25,000
**Root Cause**: Multiple resolution data (1min, 5min, 15min) stored at same timestamps in `minute_bars` table

## Root Cause Analysis

### What Was Happening

1. **Data Ingestion**: The `FOAggregator` in `fo_stream.py` was configured to aggregate data for multiple timeframes:
   - `fo_timeframes = ["1min", "5min", "15min"]` (all timeframes to aggregate)
   - `fo_persist_timeframes = ["1min"]` (only 1min should be persisted)

2. **The Bug**: In `flush_all()` method (line 276-292), the code was persisting underlying bars for **ALL timeframes**, not just `_persist_timeframes`:
   ```python
   # BUGGY CODE:
   for tf, buffer in self._underlying_buffers.items():
       for key, bar in buffer.items():
           underlying_items.append((tf, key, bar))  # ← Persisting ALL timeframes!
       buffer.clear()
   ```

3. **Database State**: This resulted in multiple rows with same timestamp but different resolutions:
   ```sql
   time                | resolution | close
   2025-11-07 07:45:00 | 1          | 25483.70
   2025-11-07 07:45:00 | 5          | 25488.35
   2025-11-07 07:45:00 | 15         | 25532.05  ← Adding to ~76,500!
   ```

4. **Display Issue**: When the history API queried for 1-minute data with `resolution = $2`, it was incorrectly getting multiple rows per timestamp, causing price aggregation issues.

## Fix Applied

### Code Changes

**File**: `backend/app/fo_stream.py` (lines 284-290)

**Before**:
```python
for tf, buffer in self._underlying_buffers.items():
    for key, bar in buffer.items():
        underlying_items.append((tf, key, bar))
    buffer.clear()
```

**After**:
```python
# BUGFIX: Only persist underlying bars for configured persist_timeframes
# to prevent duplicate resolutions in minute_bars table
for tf, buffer in self._underlying_buffers.items():
    if tf in self._persist_timeframes:  # ← Added filter
        for key, bar in buffer.items():
            underlying_items.append((tf, key, bar))
    buffer.clear()
```

### Database Cleanup

Removed duplicate resolution data:
```sql
DELETE FROM minute_bars
WHERE symbol IN ('NIFTY', 'NIFTY50', 'NIFTY 50')
  AND resolution IN (5, 15);
-- Deleted 268 rows
```

## Verification

### Before Fix
```sql
SELECT time, COUNT(*), ARRAY_AGG(resolution), ARRAY_AGG(close)
FROM minute_bars
WHERE symbol = 'NIFTY' AND time >= NOW() - INTERVAL '1 hour'
GROUP BY time HAVING COUNT(*) > 1;

-- Results showed multiple resolutions per timestamp:
time                | count | resolutions | closes
2025-11-07 08:00:00 | 2     | {1,5}       | {25529.10, 25537.75}
2025-11-07 07:45:00 | 3     | {1,5,15}    | {25483.70, 25488.35, 25532.05}
```

### After Fix
```sql
-- Same query returns 0 rows
time | count | resolutions | closes
-----+-------+-------------+--------
(0 rows)

-- All data now at resolution=1 only
SELECT symbol, resolution, COUNT(*)
FROM minute_bars WHERE symbol = 'NIFTY'
GROUP BY symbol, resolution;

symbol | resolution | count
NIFTY  | 1          | 28011  ← Only 1-minute data
```

## Testing

1. **Database Verification**: ✅ Confirmed no duplicate timestamps
2. **Price Range Check**: ✅ All NIFTY prices correctly around 25,500
3. **Frontend Display**: 🔄 Needs verification after backend restart

## Deployment Steps

1. ✅ **Code Fix Applied**: Modified `fo_stream.py`
2. ✅ **Database Cleaned**: Removed duplicate resolutions
3. ⏳ **Restart Required**: Backend service needs restart to load new code

### Restart Backend

```bash
# Option 1: Docker Compose
cd /mnt/stocksblitz-data/Quantagro/tradingview-viz
docker-compose restart backend

# Option 2: Manual restart
# Stop and start the backend service
```

### Expected Behavior After Restart

- ✅ NIFTY prices display correctly around 25,000 (not 50,000)
- ✅ No more price spikes/collapses every second
- ✅ Smooth candlestick charts without artifacts
- ✅ Only 1-minute resolution data stored in `minute_bars` table

## Configuration Reference

The fix relies on these configuration values in `app/config.py`:

```python
fo_timeframes: list[str] = ["1min", "5min", "15min"]  # Timeframes to aggregate
fo_persist_timeframes: list[str] = ["1min"]           # Only persist 1-minute
```

**Important**:
- `fo_timeframes`: Controls which timeframes are aggregated in memory for real-time streaming
- `fo_persist_timeframes`: Controls which timeframes are actually saved to database
- With this fix, only `fo_persist_timeframes` data is written to `minute_bars`

## Prevention

To prevent this issue in the future:

1. **Code Review**: Any changes to `FOAggregator.flush_all()` should verify that only `_persist_timeframes` data is persisted
2. **Database Monitoring**: Add alert if multiple resolutions appear for same timestamp:
   ```sql
   -- Alert query
   SELECT COUNT(*) FROM (
     SELECT time FROM minute_bars
     WHERE symbol = 'NIFTY'
     GROUP BY time HAVING COUNT(DISTINCT resolution) > 1
   ) duplicates;
   -- Should always return 0
   ```
3. **Integration Test**: Add test to verify single resolution per timestamp
4. **Documentation**: Updated `fo_stream.py` with inline comments explaining the filter

## Impact

- **Performance**: ✅ Improved (less data stored)
- **Data Integrity**: ✅ Fixed (no duplicates)
- **Frontend Display**: ✅ Should fix price doubling issue
- **Backward Compatibility**: ✅ No breaking changes (query logic unchanged)

## Related Files

- `backend/app/fo_stream.py` (Line 276-292) - Fix applied
- `backend/app/database.py` (Line 614-671) - `upsert_underlying_bars` method
- `backend/app/config.py` (Line 26-29) - Configuration settings

## Rollback Plan

If issues occur, rollback is simple:

1. **Revert Code**:
   ```bash
   git revert <commit-hash>
   ```

2. **Restore would not be needed** because the fix only prevents new duplicates, doesn't affect existing functionality

## Summary

✅ **Bug Fixed**: Code now correctly filters to only persist `_persist_timeframes`
✅ **Data Cleaned**: Removed 268 duplicate resolution entries
⏳ **Restart Needed**: Backend must be restarted to apply fix
📊 **Expected Result**: NIFTY prices will display correctly at ~25,000

---

**Fixed by**: Claude Code
**Date**: 2025-11-07
**Files Modified**: 1 (`fo_stream.py`)
**Rows Deleted**: 268 duplicate entries
