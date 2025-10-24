#!/usr/bin/env python3
"""
Data Migration Script for TradingView ML Visualization System

This script handles data migration between environments:
- Production -> Staging (subset of data)
- Production -> Development (sample data)
- Backup creation and restoration
"""

import asyncio
import asyncpg
import redis.asyncio as redis
import logging
import argparse
from datetime import datetime, timedelta
from typing import Optional
import os
from dataclasses import dataclass


@dataclass
class DatabaseConfig:
    host: str
    port: int
    database: str
    username: str
    password: str


@dataclass
class MigrationConfig:
    source: DatabaseConfig
    target: DatabaseConfig
    redis_url: str
    days_to_migrate: int = 90
    batch_size: int = 10000


class DataMigrator:
    def __init__(self, config: MigrationConfig):
        self.config = config
        self.logger = logging.getLogger(__name__)
        
    async def connect_databases(self):
        """Establish connections to source and target databases"""
        self.source_conn = await asyncpg.connect(
            host=self.config.source.host,
            port=self.config.source.port,
            database=self.config.source.database,
            user=self.config.source.username,
            password=self.config.source.password
        )
        
        self.target_conn = await asyncpg.connect(
            host=self.config.target.host,
            port=self.config.target.port,
            database=self.config.target.database,
            user=self.config.target.username,
            password=self.config.target.password
        )
        
        self.redis_conn = redis.from_url(self.config.redis_url)
        
    async def close_connections(self):
        """Close all database connections"""
        await self.source_conn.close()
        await self.target_conn.close()
        await self.redis_conn.close()
        
    async def migrate_ohlc_data(self, start_date: datetime, end_date: datetime):
        """Migrate OHLC data from source to target"""
        self.logger.info(f"Migrating OHLC data from {start_date} to {end_date}")
        
        # Get total count for progress tracking
        count_query = """
        SELECT COUNT(*) FROM nifty50_ohlc 
        WHERE timestamp BETWEEN $1 AND $2
        """
        total_records = await self.source_conn.fetchval(count_query, start_date, end_date)
        self.logger.info(f"Total records to migrate: {total_records}")
        
        # Clear existing data in target for the date range
        await self.target_conn.execute(
            "DELETE FROM nifty50_ohlc WHERE timestamp BETWEEN $1 AND $2",
            start_date, end_date
        )
        
        # Migrate data in batches
        offset = 0
        migrated = 0
        
        while offset < total_records:
            query = """
            SELECT timestamp, open, high, low, close, volume
            FROM nifty50_ohlc 
            WHERE timestamp BETWEEN $1 AND $2
            ORDER BY timestamp
            LIMIT $3 OFFSET $4
            """
            
            rows = await self.source_conn.fetch(
                query, start_date, end_date, self.config.batch_size, offset
            )
            
            if not rows:
                break
                
            # Insert batch into target
            await self.target_conn.executemany(
                """
                INSERT INTO nifty50_ohlc (timestamp, open, high, low, close, volume)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (timestamp) DO UPDATE SET
                    open = EXCLUDED.open,
                    high = EXCLUDED.high,
                    low = EXCLUDED.low,
                    close = EXCLUDED.close,
                    volume = EXCLUDED.volume,
                    updated_at = NOW()
                """,
                rows
            )
            
            migrated += len(rows)
            offset += self.config.batch_size
            
            progress = (migrated / total_records) * 100
            self.logger.info(f"Progress: {progress:.1f}% ({migrated}/{total_records})")
            
        self.logger.info(f"OHLC data migration completed: {migrated} records")
        
    async def migrate_ml_labels(self, start_date: datetime, end_date: datetime):
        """Migrate ML labels from source to target"""
        self.logger.info(f"Migrating ML labels from {start_date} to {end_date}")
        
        # Get total count
        count_query = """
        SELECT COUNT(*) FROM ml_labeled_data 
        WHERE timestamp BETWEEN $1 AND $2
        """
        total_records = await self.source_conn.fetchval(count_query, start_date, end_date)
        self.logger.info(f"Total ML labels to migrate: {total_records}")
        
        # Clear existing data
        await self.target_conn.execute(
            "DELETE FROM ml_labeled_data WHERE timestamp BETWEEN $1 AND $2",
            start_date, end_date
        )
        
        # Migrate in batches
        offset = 0
        migrated = 0
        
        while offset < total_records:
            query = """
            SELECT timestamp, symbol, prediction, confidence, model_version, features
            FROM ml_labeled_data 
            WHERE timestamp BETWEEN $1 AND $2
            ORDER BY timestamp
            LIMIT $3 OFFSET $4
            """
            
            rows = await self.source_conn.fetch(
                query, start_date, end_date, self.config.batch_size, offset
            )
            
            if not rows:
                break
                
            await self.target_conn.executemany(
                """
                INSERT INTO ml_labeled_data (timestamp, symbol, prediction, confidence, model_version, features)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (timestamp, symbol) DO UPDATE SET
                    prediction = EXCLUDED.prediction,
                    confidence = EXCLUDED.confidence,
                    model_version = EXCLUDED.model_version,
                    features = EXCLUDED.features,
                    updated_at = NOW()
                """,
                rows
            )
            
            migrated += len(rows)
            offset += self.config.batch_size
            
            progress = (migrated / total_records) * 100
            self.logger.info(f"Progress: {progress:.1f}% ({migrated}/{total_records})")
            
        self.logger.info(f"ML labels migration completed: {migrated} records")
        
    async def refresh_continuous_aggregates(self):
        """Refresh continuous aggregates after data migration"""
        self.logger.info("Refreshing continuous aggregates...")
        
        aggregates = ['nifty50_5min', 'nifty50_15min', 'nifty50_daily']
        
        for aggregate in aggregates:
            self.logger.info(f"Refreshing {aggregate}...")
            await self.target_conn.execute(f"CALL refresh_continuous_aggregate('{aggregate}', NULL, NULL)")
            
        self.logger.info("Continuous aggregates refreshed")
        
    async def clear_cache(self):
        """Clear Redis cache after migration"""
        self.logger.info("Clearing Redis cache...")
        await self.redis_conn.flushdb()
        self.logger.info("Redis cache cleared")
        
    async def create_backup(self, backup_path: str):
        """Create a backup of the target database"""
        self.logger.info(f"Creating backup at {backup_path}")
        
        # This would use pg_dump in a real implementation
        # For now, we'll just log the action
        self.logger.info("Backup creation would happen here using pg_dump")
        
    async def run_migration(self, environment: str):
        """Run the full migration process"""
        try:
            await self.connect_databases()
            
            # Calculate date range based on environment
            end_date = datetime.now()
            if environment == 'dev':
                start_date = end_date - timedelta(days=30)  # 1 month for dev
            elif environment == 'staging':
                start_date = end_date - timedelta(days=90)  # 3 months for staging
            else:
                start_date = end_date - timedelta(days=self.config.days_to_migrate)
                
            self.logger.info(f"Starting migration for {environment} environment")
            self.logger.info(f"Date range: {start_date} to {end_date}")
            
            # Run migrations
            await self.migrate_ohlc_data(start_date, end_date)
            await self.migrate_ml_labels(start_date, end_date)
            await self.refresh_continuous_aggregates()
            await self.clear_cache()
            
            self.logger.info("Migration completed successfully")
            
        except Exception as e:
            self.logger.error(f"Migration failed: {str(e)}")
            raise
        finally:
            await self.close_connections()


def main():
    parser = argparse.ArgumentParser(description='Data Migration Tool')
    parser.add_argument('--environment', choices=['dev', 'staging', 'prod'], required=True,
                       help='Target environment')
    parser.add_argument('--source-host', required=True, help='Source database host')
    parser.add_argument('--source-db', required=True, help='Source database name')
    parser.add_argument('--source-user', required=True, help='Source database user')
    parser.add_argument('--source-password', required=True, help='Source database password')
    parser.add_argument('--target-host', required=True, help='Target database host')
    parser.add_argument('--target-db', required=True, help='Target database name')
    parser.add_argument('--target-user', required=True, help='Target database user')
    parser.add_argument('--target-password', required=True, help='Target database password')
    parser.add_argument('--redis-url', required=True, help='Redis connection URL')
    parser.add_argument('--days', type=int, default=90, help='Number of days to migrate')
    parser.add_argument('--batch-size', type=int, default=10000, help='Batch size for migration')
    parser.add_argument('--log-level', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'], 
                       default='INFO', help='Log level')
    
    args = parser.parse_args()
    
    # Set up logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Create configuration
    source_config = DatabaseConfig(
        host=args.source_host,
        port=5432,
        database=args.source_db,
        username=args.source_user,
        password=args.source_password
    )
    
    target_config = DatabaseConfig(
        host=args.target_host,
        port=5432,
        database=args.target_db,
        username=args.target_user,
        password=args.target_password
    )
    
    migration_config = MigrationConfig(
        source=source_config,
        target=target_config,
        redis_url=args.redis_url,
        days_to_migrate=args.days,
        batch_size=args.batch_size
    )
    
    # Run migration
    migrator = DataMigrator(migration_config)
    asyncio.run(migrator.run_migration(args.environment))


if __name__ == "__main__":
    main()