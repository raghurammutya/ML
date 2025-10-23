#!/usr/bin/env python3
"""
Real-time Data Synchronization Service
Monitors for new data in nifty50_ohlc and automatically updates ml_labeled_data
Supports both periodic syncing and event-driven updates
"""

import asyncio
import asyncpg
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Set
import os
import json
from data_transformation_pipeline import DataTransformationPipeline, TIMEFRAMES

logger = logging.getLogger(__name__)

class RealTimeSyncService:
    """Service to sync new data from nifty50_ohlc to ml_labeled_data in real-time"""
    
    def __init__(self, database_url: str, sync_interval_seconds: int = 60):
        self.database_url = database_url
        self.sync_interval = sync_interval_seconds
        self.pipeline = DataTransformationPipeline(database_url)
        self.last_sync_time: Optional[datetime] = None
        self.running = False
        
    async def start(self):
        """Start the real-time sync service"""
        logger.info("Starting real-time sync service...")
        
        await self.pipeline.connect()
        self.running = True
        
        # Initialize last sync time
        await self._initialize_last_sync_time()
        
        # Start the sync loop
        while self.running:
            try:
                await self._sync_new_data()
                await asyncio.sleep(self.sync_interval)
            except Exception as e:
                logger.error(f"Sync error: {e}")
                await asyncio.sleep(self.sync_interval)
    
    async def stop(self):
        """Stop the real-time sync service"""
        logger.info("Stopping real-time sync service...")
        self.running = False
        await self.pipeline.close()
    
    async def _initialize_last_sync_time(self):
        """Initialize the last sync time from database or use a recent time"""
        async with self.pipeline.pool.acquire() as conn:
            # Get the latest timestamp from ml_labeled_data
            result = await conn.fetchrow("""
                SELECT MAX(updated_at) as last_update
                FROM ml_labeled_data
                WHERE symbol = 'NIFTY'
            """)
            
            if result and result['last_update']:
                self.last_sync_time = result['last_update']
                logger.info(f"Initialized last sync time from database: {self.last_sync_time}")
            else:
                # If no data exists, start from 24 hours ago
                self.last_sync_time = datetime.now(timezone.utc) - timedelta(hours=24)
                logger.info(f"No existing data found, starting sync from: {self.last_sync_time}")
    
    async def _get_new_source_data_range(self) -> Optional[tuple]:
        """Check for new data in nifty50_ohlc since last sync"""
        async with self.pipeline.pool.acquire() as conn:
            result = await conn.fetchrow("""
                SELECT 
                    MIN(time) as min_time,
                    MAX(time) as max_time,
                    COUNT(*) as count
                FROM nifty50_ohlc
                WHERE time > $1
                  AND open IS NOT NULL 
                  AND high IS NOT NULL 
                  AND low IS NOT NULL 
                  AND close IS NOT NULL
            """, self.last_sync_time)
            
            if result and result['count'] > 0:
                logger.info(f"Found {result['count']} new records from {result['min_time']} to {result['max_time']}")
                return result['min_time'], result['max_time']
            
            return None
    
    async def _sync_new_data(self):
        """Sync new data for all timeframes"""
        new_data_range = await self._get_new_source_data_range()
        
        if not new_data_range:
            logger.debug("No new data to sync")
            return
        
        min_time, max_time = new_data_range
        
        logger.info(f"Syncing new data from {min_time} to {max_time}")
        
        # Update data using the pipeline's incremental update method
        await self.pipeline.process_incremental_update(min_time)
        
        # Update last sync time
        self.last_sync_time = max_time
        
        # Log sync statistics
        await self._log_sync_stats()
    
    async def _log_sync_stats(self):
        """Log statistics about the sync operation"""
        async with self.pipeline.pool.acquire() as conn:
            result = await conn.fetchrow("""
                SELECT 
                    COUNT(*) as total_records,
                    COUNT(CASE WHEN updated_at > NOW() - INTERVAL '1 hour' THEN 1 END) as recent_updates
                FROM ml_labeled_data
                WHERE symbol = 'NIFTY'
            """)
            
            if result:
                logger.info(f"Sync stats: {result['total_records']} total records, {result['recent_updates']} updated in last hour")

class DataRefreshIntegration:
    """Integration with the existing data refresh mechanism in the backend"""
    
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.pipeline = DataTransformationPipeline(database_url)
    
    async def enhanced_data_refresh(self):
        """Enhanced version of the existing data_refresh that includes ml_labeled_data sync"""
        await self.pipeline.connect()
        
        try:
            # Run incremental sync for the last hour
            since_time = datetime.now(timezone.utc) - timedelta(hours=1)
            await self.pipeline.process_incremental_update(since_time)
            
            # Get and log refresh statistics
            stats = await self.pipeline.get_transformation_stats()
            logger.info(f"Data refresh completed. Timeframe record counts: {stats['timeframes']}")
            
        except Exception as e:
            logger.error(f"Enhanced data refresh failed: {e}")
            raise
        finally:
            await self.pipeline.close()

async def run_sync_service():
    """Main function to run the sync service"""
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        logger.error("DATABASE_URL environment variable not set")
        return
    
    # Configure sync interval (default 60 seconds, can be overridden)
    sync_interval = int(os.getenv('SYNC_INTERVAL_SECONDS', '60'))
    
    service = RealTimeSyncService(database_url, sync_interval)
    
    try:
        await service.start()
    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
    finally:
        await service.stop()

async def run_single_refresh():
    """Run a single data refresh operation"""
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        logger.error("DATABASE_URL environment variable not set")
        return
    
    refresh_service = DataRefreshIntegration(database_url)
    await refresh_service.enhanced_data_refresh()

if __name__ == "__main__":
    import sys
    
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    if len(sys.argv) > 1 and sys.argv[1] == "refresh":
        # Run single refresh
        asyncio.run(run_single_refresh())
    else:
        # Run continuous sync service
        asyncio.run(run_sync_service())