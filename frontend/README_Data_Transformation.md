It is all# Data Transformation Pipeline

This system transforms 1-minute OHLC data from `nifty50_ohlc` into `ml_labeled_data` across multiple timeframes with proper day boundaries and real-time synchronization.

## Overview

The pipeline ensures that:
- ✅ All 1-minute data from `nifty50_ohlc` is transformed to `ml_labeled_data`
- ✅ Multiple timeframes (1min, 2min, 3min, 5min, 15min, 30min, 1hour, 1day) are supported
- ✅ Timeframes restart at the beginning of each day (proper day boundaries)
- ✅ Real-time and batch updates work with upserts (no duplicates)
- ✅ Technical indicators are calculated automatically
- ✅ Data integrity checks prevent corrupt records

## Current Status

**Source Data:** 997,376 records (2015-01-09 to 2025-10-23)

**Transformed Data:**
- **1min:** 995,502 records (99.8% coverage)
- **2min:** 10,494 records 
- **3min:** 6,977 records
- **5min:** 199,109 records
- **15min:** 66,377 records  
- **30min:** 34,524 records
- **1hour:** 444 records
- **1day:** 292 records

## Usage

### 1. Check Current Status
```bash
DATABASE_URL="postgresql://user:pass@localhost:5432/db" python3 data_transformation_pipeline.py stats
```

### 2. Process Incremental Updates
```bash
# Process last 24 hours
DATABASE_URL="postgresql://user:pass@localhost:5432/db" python3 data_transformation_pipeline.py incremental

# Process since specific date
DATABASE_URL="postgresql://user:pass@localhost:5432/db" python3 data_transformation_pipeline.py since:2025-10-01
```

### 3. Full Historical Transformation
```bash
# Transform ALL historical data
DATABASE_URL="postgresql://user:pass@localhost:5432/db" python3 data_transformation_pipeline.py full
```

### 4. Real-time Sync Service
```bash
# Run continuous sync service (checks every 60 seconds)
DATABASE_URL="postgresql://user:pass@localhost:5432/db" python3 real_time_sync_service.py

# Run single refresh
DATABASE_URL="postgresql://user:pass@localhost:5432/db" python3 real_time_sync_service.py refresh
```

## Key Features

### 1. Day Boundary Logic
- Each timeframe starts fresh at the beginning of each trading day
- Ensures proper aggregation without overnight gaps
- Handles timezone conversion (stored as UTC)

### 2. Technical Indicators
Automatically calculated for each record:
- **Price Change %:** `((close - open) / open) * 100`
- **Body Size %:** `(|close - open| / (high - low)) * 100`
- **Close Position:** `(close - low) / (high - low)`

### 3. Upsert Logic
- Uses `ON CONFLICT (symbol, timeframe, time) DO UPDATE`
- Prevents duplicates while allowing data updates
- Updates `updated_at` timestamp on conflicts

### 4. Data Validation
- Skips records with NULL OHLC values
- Validates positive prices
- Ensures `high >= low`

### 5. Aggregation Method

**1-minute data:** Direct copy from `nifty50_ohlc` with technical calculations

**Other timeframes:** Aggregated from 1-minute `ml_labeled_data`:
```sql
-- Example: 5-minute aggregation
SELECT 
    time_bucket(INTERVAL '5 minutes', time) as bucket_time,
    (array_agg(open ORDER BY time ASC))[1] as open,    -- First open
    MAX(high) as high,                                 -- Highest high
    MIN(low) as low,                                   -- Lowest low
    (array_agg(close ORDER BY time DESC))[1] as close, -- Last close
    SUM(volume) as volume                              -- Total volume
FROM ml_labeled_data
WHERE timeframe = '1min'
GROUP BY bucket_time
```

## Configuration

### Timeframe Settings
```python
TIMEFRAMES = [
    TimeframeConfig("1min", 1, 30),      # 30 days per batch
    TimeframeConfig("2min", 2, 30),      # 30 days per batch  
    TimeframeConfig("3min", 3, 30),      # 30 days per batch
    TimeframeConfig("5min", 5, 30),      # 30 days per batch
    TimeframeConfig("15min", 15, 90),    # 90 days per batch
    TimeframeConfig("30min", 30, 180),   # 180 days per batch
    TimeframeConfig("1hour", 60, 365),   # 365 days per batch
    TimeframeConfig("1day", 1440, 365),  # 365 days per batch
]
```

### Real-time Sync Settings
```python
# Sync interval (seconds)
SYNC_INTERVAL_SECONDS = 60  # Default: 1 minute

# Database connection pool
min_size = 5
max_size = 20
command_timeout = 300  # 5 minutes for large operations
```

## Integration with Backend

### Existing Data Refresh
The pipeline integrates with the existing `data_refresh` task in the backend:

```python
# Enhanced data refresh that includes ml_labeled_data sync
from real_time_sync_service import DataRefreshIntegration

async def enhanced_data_refresh():
    refresh_service = DataRefreshIntegration(database_url)
    await refresh_service.enhanced_data_refresh()
```

### Monitoring
- Logs transformation statistics every refresh
- Tracks record counts and processing times
- Monitors for data quality issues

## Troubleshooting

### Common Issues

1. **Timezone Errors**: Ensure timestamps are timezone-naive (UTC)
2. **Memory Issues**: Use batch processing for large date ranges
3. **TimescaleDB Functions**: Requires `INTERVAL` casting for `time_bucket`
4. **Connection Timeouts**: Increase `command_timeout` for large operations

### Performance Optimization

1. **Batch Size**: Adjust `batch_size` in timeframe configs
2. **Connection Pool**: Tune `min_size`/`max_size` based on load
3. **Indexes**: Ensure proper indexes on `(symbol, timeframe, time)`
4. **Vacuum**: Regular maintenance for optimal query performance

## Data Quality Checks

The pipeline includes several data quality validations:

- ✅ NULL value detection and skipping
- ✅ Price validation (positive values)
- ✅ OHLC relationship validation (high >= low)
- ✅ Duplicate prevention via upserts
- ✅ Technical indicator calculation validation

## Future Enhancements

1. **Label Prediction Integration**: Automatic ML labeling based on price patterns
2. **Additional Technical Indicators**: RSI, MACD, Bollinger Bands
3. **Multiple Symbols**: Extend beyond NIFTY50 to other instruments
4. **Real-time Streaming**: WebSocket integration for live data feeds
5. **Data Compression**: Archive old data using TimescaleDB compression
6. **Alert System**: Notifications for data quality issues or processing failures