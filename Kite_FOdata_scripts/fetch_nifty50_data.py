#!/usr/bin/env python3
"""
Script to fetch Nifty50 historical data from Zerodha Kite API
and store it in the stocksblitz_unified database.
"""

import os
import sys
import json
import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any
from pathlib import Path

import asyncpg
from kiteconnect import KiteConnect

# Add backend directory to path for imports
backend_dir = Path(__file__).parent / "backend"
sys.path.append(str(backend_dir))

# Load environment variables from backend/.env
from dotenv import load_dotenv
load_dotenv(backend_dir / ".env")

from config import DB_CONFIG
from kite_accounts import get_kite_service

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Nifty50 instrument token - will be fetched dynamically
NIFTY50_SYMBOL = "NSE:NIFTY 50"

async def create_table_if_not_exists(conn: asyncpg.Connection):
    """Create nifty50_ohlc table if it doesn't exist"""
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS nifty50_ohlc (
        time TIMESTAMP WITHOUT TIME ZONE NOT NULL,
        open DECIMAL(10, 2) NOT NULL,
        high DECIMAL(10, 2) NOT NULL,
        low DECIMAL(10, 2) NOT NULL,
        close DECIMAL(10, 2) NOT NULL,
        volume BIGINT DEFAULT 0,
        symbol VARCHAR(20) DEFAULT 'NIFTY50',
        UNIQUE(time)
    );
    
    CREATE INDEX IF NOT EXISTS idx_nifty50_ohlc_time ON nifty50_ohlc(time);
    """
    await conn.execute(create_table_sql)
    logger.info("Table nifty50_ohlc created or verified")

async def get_last_timestamp(conn: asyncpg.Connection) -> datetime:
    """Get the last timestamp from the database"""
    query = "SELECT MAX(time) FROM nifty50_ohlc"
    result = await conn.fetchval(query)
    
    if result:
        logger.info(f"Last timestamp in database: {result}")
        return result
    else:
        # Default start date if no data exists (timezone-naive)
        start_date = datetime(2025, 7, 25, 9, 15, 0)
        logger.info(f"No existing data, starting from: {start_date}")
        return start_date

async def insert_ohlc_data(conn: asyncpg.Connection, data: List[Dict[str, Any]]):
    """Insert OHLC data into the database"""
    if not data:
        logger.info("No data to insert")
        return
    
    insert_sql = """
    INSERT INTO nifty50_ohlc (time, open, high, low, close, volume, symbol)
    VALUES ($1, $2, $3, $4, $5, $6, $7)
    ON CONFLICT (time) DO UPDATE SET
        open = EXCLUDED.open,
        high = EXCLUDED.high,
        low = EXCLUDED.low,
        close = EXCLUDED.close,
        volume = EXCLUDED.volume,
        symbol = EXCLUDED.symbol
    """
    
    records = []
    for candle in data:
        timestamp = candle['date']
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        elif not isinstance(timestamp, datetime):
            # Convert string or other format to datetime
            if isinstance(timestamp, str):
                timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            else:
                timestamp = datetime.fromisoformat(str(timestamp))
        
        # Convert to timezone-naive for database (remove timezone info)
        if timestamp.tzinfo is not None:
            timestamp = timestamp.replace(tzinfo=None)
        
        records.append((
            timestamp,
            float(candle['open']),
            float(candle['high']),
            float(candle['low']),
            float(candle['close']),
            int(candle.get('volume', 0)),
            'NIFTY50'
        ))
    
    await conn.executemany(insert_sql, records)
    logger.info(f"Inserted/Updated {len(records)} records")

def get_nifty50_instrument_token(kite: KiteConnect) -> int:
    """Get Nifty50 instrument token from instruments list"""
    try:
        instruments = kite.instruments("NSE")
        for instrument in instruments:
            if instrument['name'] == 'NIFTY 50' and instrument['exchange'] == 'NSE':
                logger.info(f"Found Nifty50 instrument token: {instrument['instrument_token']}")
                return instrument['instrument_token']
        
        # Fallback to common token
        logger.warning("Could not find Nifty50 instrument token, using fallback")
        return 256265
        
    except Exception as e:
        logger.error(f"Error getting instrument token: {e}")
        return 256265

def fetch_historical_data(kite: KiteConnect, instrument_token: int, from_date: datetime, to_date: datetime) -> List[Dict[str, Any]]:
    """Fetch historical data from Kite API"""
    try:
        logger.info(f"Fetching data from {from_date} to {to_date}")
        
        # Convert datetime to string format expected by Kite API
        from_date_str = from_date.strftime('%Y-%m-%d %H:%M:%S')
        to_date_str = to_date.strftime('%Y-%m-%d %H:%M:%S')
        
        # Fetch historical data - ONLY 1-minute interval
        historical_data = kite.historical_data(
            instrument_token=instrument_token,
            from_date=from_date_str,
            to_date=to_date_str,
            interval="minute",  # 1-minute data only
            continuous=False,
            oi=False
        )
        
        logger.info(f"Fetched {len(historical_data)} candles from Kite API")
        return historical_data
        
    except Exception as e:
        logger.error(f"Error fetching historical data: {e}")
        return []

async def main():
    """Main function to fetch and store Nifty50 data"""
    try:
        # Initialize Kite service
        logger.info("Initializing Kite service...")
        kite_service = get_kite_service()
        
        # Get authenticated Kite instance  
        kite = kite_service.kite
        if not kite_service.is_authenticated():
            logger.error("Failed to authenticate with Kite API")
            return
        
        logger.info("Successfully authenticated with Kite API")
        
        # Get Nifty50 instrument token
        instrument_token = get_nifty50_instrument_token(kite)
        
        # Connect to database
        logger.info("Connecting to database...")
        conn = await asyncpg.connect(**DB_CONFIG)
        
        try:
            # Create table if needed
            await create_table_if_not_exists(conn)
            
            # Get last timestamp from database
            last_timestamp = await get_last_timestamp(conn)
            
            # Current time (timezone-naive to match database)
            current_time = datetime.now()
            
            # Ensure last_timestamp is timezone-naive for comparison
            if last_timestamp.tzinfo is not None:
                last_timestamp = last_timestamp.replace(tzinfo=None)
            
            # Fetch data in smaller chunks to avoid API limits
            from datetime import timedelta
            chunk_days = 7  # Fetch 7 days at a time for better success rate
            start_date = last_timestamp + timedelta(minutes=1)  # Start from next minute
            
            while start_date < current_time:
                # Calculate end date for this chunk
                end_date = min(
                    start_date + timedelta(days=chunk_days),
                    current_time
                )
                
                logger.info(f"Fetching data chunk: {start_date} to {end_date}")
                
                # Fetch historical data
                historical_data = fetch_historical_data(kite, instrument_token, start_date, end_date)
                
                if historical_data:
                    # Insert data into database
                    await insert_ohlc_data(conn, historical_data)
                    logger.info(f"Successfully processed {len(historical_data)} candles")
                else:
                    logger.warning(f"No data returned for period {start_date} to {end_date}")
                
                # Move to next chunk
                start_date = end_date
                
                # Small delay to avoid rate limiting
                await asyncio.sleep(1)
            
            logger.info("Data fetch and storage completed successfully")
            
        finally:
            await conn.close()
            
    except Exception as e:
        logger.error(f"Error in main function: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())
