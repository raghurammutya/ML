#!/usr/bin/env python3
"""
Comprehensive Data Transformation Pipeline
Transforms 1-minute data from nifty50_ohlc to ml_labeled_data across all timeframes
Supports both batch processing and real-time updates with proper day boundaries
"""

import asyncio
import asyncpg
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional, Tuple
import json
from dataclasses import dataclass
import sys
import os

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class TimeframeConfig:
    """Configuration for each timeframe"""
    name: str
    minutes: int
    batch_size: int  # Number of days to process in each batch
    is_active: bool = True

# Define all supported timeframes with their configurations
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

class DataTransformationPipeline:
    """Main pipeline for data transformation"""
    
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.pool: Optional[asyncpg.Pool] = None
        
    async def connect(self):
        """Initialize database connection pool"""
        try:
            self.pool = await asyncpg.create_pool(
                self.database_url,
                min_size=5,
                max_size=20,
                command_timeout=300  # 5 minutes for large operations
            )
            logger.info("Database connection pool created")
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise
    
    async def close(self):
        """Close database connections"""
        if self.pool:
            await self.pool.close()
            logger.info("Database connections closed")
    
    async def get_data_range(self) -> Tuple[datetime, datetime]:
        """Get the full data range from nifty50_ohlc table"""
        async with self.pool.acquire() as conn:
            result = await conn.fetchrow("""
                SELECT 
                    MIN(time) as min_time,
                    MAX(time) as max_time,
                    COUNT(*) as total_records
                FROM nifty50_ohlc
                WHERE time IS NOT NULL
                  AND open IS NOT NULL 
                  AND high IS NOT NULL 
                  AND low IS NOT NULL 
                  AND close IS NOT NULL
            """)
            
            if result and result['min_time'] and result['max_time']:
                logger.info(f"Source data range: {result['min_time']} to {result['max_time']} ({result['total_records']} records)")
                return result['min_time'], result['max_time']
            else:
                raise ValueError("No valid data found in nifty50_ohlc table")
    
    def get_day_boundaries(self, start_date: datetime, end_date: datetime) -> List[Tuple[datetime, datetime]]:
        """Generate day boundaries ensuring timeframes restart at beginning of each day"""
        boundaries = []
        
        # Convert to timezone-naive UTC timestamps (database expects this format)
        if start_date.tzinfo is not None:
            start_date = start_date.utctimetuple()
            start_date = datetime(*start_date[:6])
        if end_date.tzinfo is not None:
            end_date = end_date.utctimetuple()
            end_date = datetime(*end_date[:6])
            
        current = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        
        while current <= end_date:
            day_start = current
            day_end = current.replace(hour=23, minute=59, second=59, microsecond=999999)
            
            # Don't process future days
            if day_start <= end_date:
                boundaries.append((day_start, min(day_end, end_date)))
            
            current += timedelta(days=1)
        
        return boundaries
    
    async def transform_timeframe_for_day(self, 
                                        conn: asyncpg.Connection,
                                        timeframe: TimeframeConfig, 
                                        day_start: datetime, 
                                        day_end: datetime) -> int:
        """Transform data for a specific timeframe and day"""
        
        if timeframe.name == "1min":
            # For 1min, copy directly from source with minimal transformation
            return await self._copy_1min_data(conn, day_start, day_end)
        else:
            # For other timeframes, aggregate from 1min data
            return await self._aggregate_timeframe_data(conn, timeframe, day_start, day_end)
    
    async def _copy_1min_data(self, conn: asyncpg.Connection, day_start: datetime, day_end: datetime) -> int:
        """Copy 1-minute data directly from nifty50_ohlc with proper formatting"""
        
        # First, calculate technical indicators
        upsert_sql = """
            INSERT INTO ml_labeled_data (
                symbol, timeframe, time, open, high, low, close, volume,
                price_change_pct, body_size_pct, close_position,
                created_at, updated_at, labeling_version
            )
            SELECT 
                'NIFTY' as symbol,
                '1min' as timeframe,
                time,
                open,
                high,
                low,
                close,
                COALESCE(volume, 0) as volume,
                
                -- Technical indicators
                ROUND(((close - open) / NULLIF(open, 0) * 100)::numeric, 4) as price_change_pct,
                ROUND((ABS(close - open) / NULLIF((high - low), 0) * 100)::numeric, 4) as body_size_pct,
                ROUND(((close - low) / NULLIF((high - low), 0))::numeric, 4) as close_position,
                
                NOW() as created_at,
                NOW() as updated_at,
                4 as labeling_version
                
            FROM nifty50_ohlc
            WHERE time >= $1 AND time <= $2
              AND open IS NOT NULL 
              AND high IS NOT NULL 
              AND low IS NOT NULL 
              AND close IS NOT NULL
              AND high >= low  -- Data validation
              AND open > 0 AND close > 0  -- Positive prices
            ORDER BY time
            
            ON CONFLICT (symbol, timeframe, time) 
            DO UPDATE SET
                open = EXCLUDED.open,
                high = EXCLUDED.high,
                low = EXCLUDED.low,
                close = EXCLUDED.close,
                volume = EXCLUDED.volume,
                price_change_pct = EXCLUDED.price_change_pct,
                body_size_pct = EXCLUDED.body_size_pct,
                close_position = EXCLUDED.close_position,
                updated_at = NOW(),
                labeling_version = EXCLUDED.labeling_version
        """
        
        result = await conn.execute(upsert_sql, day_start, day_end)
        count = int(result.split()[-1])
        return count
    
    async def _aggregate_timeframe_data(self, 
                                      conn: asyncpg.Connection,
                                      timeframe: TimeframeConfig, 
                                      day_start: datetime, 
                                      day_end: datetime) -> int:
        """Aggregate data for non-1min timeframes from ml_labeled_data"""
        
        # Calculate the interval for time_bucket
        interval = f"{timeframe.minutes} minutes"
        
        upsert_sql = f"""
            INSERT INTO ml_labeled_data (
                symbol, timeframe, time, open, high, low, close, volume,
                price_change_pct, body_size_pct, close_position,
                created_at, updated_at, labeling_version
            )
            SELECT 
                'NIFTY' as symbol,
                '{timeframe.name}' as timeframe,
                time_bucket(INTERVAL '{interval}', time) as bucket_time,
                
                -- OHLC aggregation
                (array_agg(open ORDER BY time ASC))[1] as open,  -- First open
                MAX(high) as high,
                MIN(low) as low,
                (array_agg(close ORDER BY time DESC))[1] as close, -- Last close
                SUM(volume) as volume,
                
                -- Recalculate technical indicators for aggregated data
                ROUND((((array_agg(close ORDER BY time DESC))[1] - (array_agg(open ORDER BY time ASC))[1]) / 
                       NULLIF((array_agg(open ORDER BY time ASC))[1], 0) * 100)::numeric, 4) as price_change_pct,
                ROUND((ABS((array_agg(close ORDER BY time DESC))[1] - (array_agg(open ORDER BY time ASC))[1]) / 
                       NULLIF((MAX(high) - MIN(low)), 0) * 100)::numeric, 4) as body_size_pct,
                ROUND((((array_agg(close ORDER BY time DESC))[1] - MIN(low)) / 
                       NULLIF((MAX(high) - MIN(low)), 0))::numeric, 4) as close_position,
                
                NOW() as created_at,
                NOW() as updated_at,
                4 as labeling_version
                
            FROM ml_labeled_data
            WHERE timeframe = '1min'
              AND symbol = 'NIFTY'
              AND time >= $1 AND time <= $2
              AND open IS NOT NULL 
              AND high IS NOT NULL 
              AND low IS NOT NULL 
              AND close IS NOT NULL
            GROUP BY bucket_time
            HAVING COUNT(*) > 0  -- Ensure we have data for aggregation
            ORDER BY bucket_time
            
            ON CONFLICT (symbol, timeframe, time) 
            DO UPDATE SET
                open = EXCLUDED.open,
                high = EXCLUDED.high,
                low = EXCLUDED.low,
                close = EXCLUDED.close,
                volume = EXCLUDED.volume,
                price_change_pct = EXCLUDED.price_change_pct,
                body_size_pct = EXCLUDED.body_size_pct,
                close_position = EXCLUDED.close_position,
                updated_at = NOW(),
                labeling_version = EXCLUDED.labeling_version
        """
        
        result = await conn.execute(upsert_sql, day_start, day_end)
        count = int(result.split()[-1])
        return count
    
    async def process_historical_data(self, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None):
        """Process all historical data for all timeframes"""
        logger.info("Starting historical data transformation...")
        
        # Get data range if not specified
        if not start_date or not end_date:
            data_start, data_end = await self.get_data_range()
            start_date = start_date or data_start
            end_date = end_date or data_end
        
        logger.info(f"Processing data from {start_date} to {end_date}")
        
        # Get day boundaries
        day_boundaries = self.get_day_boundaries(start_date, end_date)
        logger.info(f"Processing {len(day_boundaries)} days")
        
        # Process each timeframe
        for timeframe in TIMEFRAMES:
            if not timeframe.is_active:
                continue
                
            logger.info(f"Processing timeframe: {timeframe.name}")
            total_records = 0
            
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    for i, (day_start, day_end) in enumerate(day_boundaries):
                        try:
                            count = await self.transform_timeframe_for_day(conn, timeframe, day_start, day_end)
                            total_records += count
                            
                            if i % 10 == 0:  # Log every 10 days
                                logger.info(f"  {timeframe.name}: Processed {i+1}/{len(day_boundaries)} days, {total_records} records so far")
                                
                        except Exception as e:
                            logger.error(f"Failed to process {timeframe.name} for {day_start.date()}: {e}")
                            # Continue with next day instead of failing entire timeframe
                            continue
            
            logger.info(f"Completed {timeframe.name}: {total_records} total records")
    
    async def process_incremental_update(self, since_datetime: datetime):
        """Process incremental updates for new data since specified datetime"""
        logger.info(f"Processing incremental update since {since_datetime}")
        
        end_time = datetime.now(timezone.utc)
        day_boundaries = self.get_day_boundaries(since_datetime, end_time)
        
        if not day_boundaries:
            logger.info("No new data to process")
            return
        
        logger.info(f"Processing {len(day_boundaries)} days for incremental update")
        
        # Process each timeframe
        for timeframe in TIMEFRAMES:
            if not timeframe.is_active:
                continue
                
            total_records = 0
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    for day_start, day_end in day_boundaries:
                        count = await self.transform_timeframe_for_day(conn, timeframe, day_start, day_end)
                        total_records += count
            
            logger.info(f"Incremental update {timeframe.name}: {total_records} records")
    
    async def get_transformation_stats(self) -> Dict:
        """Get statistics about the transformation"""
        async with self.pool.acquire() as conn:
            stats = {}
            
            # Source data stats
            source_stats = await conn.fetchrow("""
                SELECT 
                    COUNT(*) as total_records,
                    MIN(time) as min_time,
                    MAX(time) as max_time
                FROM nifty50_ohlc
                WHERE open IS NOT NULL AND high IS NOT NULL 
                  AND low IS NOT NULL AND close IS NOT NULL
            """)
            
            stats['source'] = dict(source_stats) if source_stats else {}
            
            # Target data stats by timeframe
            timeframe_stats = await conn.fetch("""
                SELECT 
                    timeframe,
                    COUNT(*) as total_records,
                    MIN(time) as min_time,
                    MAX(time) as max_time,
                    COUNT(DISTINCT DATE(time)) as unique_days
                FROM ml_labeled_data
                WHERE symbol = 'NIFTY'
                GROUP BY timeframe
                ORDER BY 
                    CASE timeframe
                        WHEN '1min' THEN 1
                        WHEN '2min' THEN 2
                        WHEN '3min' THEN 3
                        WHEN '5min' THEN 5
                        WHEN '15min' THEN 15
                        WHEN '30min' THEN 30
                        WHEN '1hour' THEN 60
                        WHEN '1day' THEN 1440
                        ELSE 9999
                    END
            """)
            
            stats['timeframes'] = {row['timeframe']: dict(row) for row in timeframe_stats}
            
            return stats

async def main():
    """Main function to run the transformation pipeline"""
    
    # Get database URL from environment
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        logger.error("DATABASE_URL environment variable not set")
        sys.exit(1)
    
    pipeline = DataTransformationPipeline(database_url)
    
    try:
        await pipeline.connect()
        
        # Check command line arguments
        if len(sys.argv) > 1:
            command = sys.argv[1]
            
            if command == "stats":
                # Show transformation statistics
                stats = await pipeline.get_transformation_stats()
                print("\n=== Transformation Statistics ===")
                print(f"Source (nifty50_ohlc): {stats['source']}")
                print("\nTarget (ml_labeled_data):")
                for tf, data in stats['timeframes'].items():
                    print(f"  {tf}: {data}")
                
            elif command == "incremental":
                # Process incremental update (last 24 hours)
                since = datetime.now(timezone.utc) - timedelta(days=1)
                await pipeline.process_incremental_update(since)
                
            elif command == "full":
                # Process all historical data
                await pipeline.process_historical_data()
                
            elif command.startswith("since:"):
                # Process since specific date (format: since:2024-01-01)
                date_str = command.split(":", 1)[1]
                since = datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc)
                await pipeline.process_incremental_update(since)
                
            else:
                print("Usage: python data_transformation_pipeline.py [stats|incremental|full|since:YYYY-MM-DD]")
                sys.exit(1)
        else:
            # Default: show stats
            stats = await pipeline.get_transformation_stats()
            print("=== Current Transformation Status ===")
            print(f"Source records: {stats['source'].get('total_records', 0)}")
            print("Timeframe records:")
            for tf, data in stats['timeframes'].items():
                print(f"  {tf}: {data.get('total_records', 0)}")
            
    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        raise
    finally:
        await pipeline.close()

if __name__ == "__main__":
    asyncio.run(main())