#!/usr/bin/env python3
"""
Real-time Data Synchronization Service

This service handles real-time data updates from external sources
and synchronizes them across development and production environments.
"""

import asyncio
import asyncpg
import redis.asyncio as redis
import logging
import json
import aiohttp
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import os
from dataclasses import dataclass, asdict
from enum import Enum
import websockets


class DataSource(Enum):
    WEBSOCKET = "websocket"
    REST_API = "rest_api"
    FILE_UPLOAD = "file_upload"


@dataclass
class OHLCData:
    timestamp: datetime
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    source: str = "external_api"


@dataclass
class MLLabel:
    timestamp: datetime
    symbol: str
    prediction: int  # -1, 0, 1
    confidence: float
    model_version: str
    features: Optional[Dict[str, Any]] = None


class RealTimeDataSync:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.db_pool = None
        self.redis_client = None
        self.running = False
        
        # Data buffers for batch processing
        self.ohlc_buffer: List[OHLCData] = []
        self.ml_buffer: List[MLLabel] = []
        self.buffer_size = config.get('buffer_size', 100)
        self.flush_interval = config.get('flush_interval', 10)  # seconds
        
    async def initialize(self):
        """Initialize database connections and Redis client"""
        try:
            # Create database connection pool
            self.db_pool = await asyncpg.create_pool(
                host=self.config['db_host'],
                port=self.config['db_port'],
                database=self.config['db_name'],
                user=self.config['db_user'],
                password=self.config['db_password'],
                min_size=5,
                max_size=20
            )
            
            # Initialize Redis client
            self.redis_client = redis.from_url(
                self.config['redis_url'],
                password=self.config.get('redis_password')
            )
            
            self.logger.info("Real-time data sync service initialized")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize service: {str(e)}")
            raise
    
    async def start(self):
        """Start the real-time data synchronization service"""
        await self.initialize()
        self.running = True
        
        # Start background tasks
        tasks = [
            asyncio.create_task(self.websocket_listener()),
            asyncio.create_task(self.rest_api_poller()),
            asyncio.create_task(self.buffer_flusher()),
            asyncio.create_task(self.cache_updater())
        ]
        
        try:
            await asyncio.gather(*tasks)
        except Exception as e:
            self.logger.error(f"Service error: {str(e)}")
        finally:
            await self.cleanup()
    
    async def stop(self):
        """Stop the service gracefully"""
        self.running = False
        self.logger.info("Stopping real-time data sync service")
    
    async def cleanup(self):
        """Clean up resources"""
        if self.db_pool:
            await self.db_pool.close()
        if self.redis_client:
            await self.redis_client.close()
    
    async def websocket_listener(self):
        """Listen to WebSocket data feed"""
        if not self.config.get('websocket_url'):
            return
            
        self.logger.info("Starting WebSocket listener")
        
        while self.running:
            try:
                async with websockets.connect(self.config['websocket_url']) as websocket:
                    self.logger.info("Connected to WebSocket feed")
                    
                    async for message in websocket:
                        if not self.running:
                            break
                            
                        data = json.loads(message)
                        await self.process_websocket_data(data)
                        
            except Exception as e:
                self.logger.error(f"WebSocket error: {str(e)}")
                await asyncio.sleep(5)  # Wait before reconnecting
    
    async def rest_api_poller(self):
        """Poll REST API for data updates"""
        if not self.config.get('api_url'):
            return
            
        self.logger.info("Starting REST API poller")
        
        while self.running:
            try:
                async with aiohttp.ClientSession() as session:
                    # Get latest data timestamp from database
                    latest_timestamp = await self.get_latest_timestamp()
                    
                    # Fetch new data from API
                    params = {
                        'since': latest_timestamp.isoformat(),
                        'symbol': 'NIFTY50',
                        'limit': 1000
                    }
                    
                    async with session.get(
                        self.config['api_url'], 
                        params=params,
                        headers={'Authorization': f"Bearer {self.config.get('api_key')}"}
                    ) as response:
                        if response.status == 200:
                            data = await response.json()
                            await self.process_api_data(data)
                        else:
                            self.logger.warning(f"API request failed: {response.status}")
                
                # Wait before next poll
                await asyncio.sleep(self.config.get('poll_interval', 60))
                
            except Exception as e:
                self.logger.error(f"API polling error: {str(e)}")
                await asyncio.sleep(30)
    
    async def process_websocket_data(self, data: Dict[str, Any]):
        """Process incoming WebSocket data"""
        try:
            if data.get('type') == 'ohlc':
                ohlc = OHLCData(
                    timestamp=datetime.fromisoformat(data['timestamp']),
                    symbol=data['symbol'],
                    open=float(data['open']),
                    high=float(data['high']),
                    low=float(data['low']),
                    close=float(data['close']),
                    volume=int(data['volume']),
                    source='websocket'
                )
                self.ohlc_buffer.append(ohlc)
                
            elif data.get('type') == 'ml_prediction':
                ml_label = MLLabel(
                    timestamp=datetime.fromisoformat(data['timestamp']),
                    symbol=data['symbol'],
                    prediction=int(data['prediction']),
                    confidence=float(data['confidence']),
                    model_version=data['model_version'],
                    features=data.get('features')
                )
                self.ml_buffer.append(ml_label)
                
            # Flush buffers if they're full
            if len(self.ohlc_buffer) >= self.buffer_size:
                await self.flush_ohlc_buffer()
            if len(self.ml_buffer) >= self.buffer_size:
                await self.flush_ml_buffer()
                
        except Exception as e:
            self.logger.error(f"Error processing WebSocket data: {str(e)}")
    
    async def process_api_data(self, data: Dict[str, Any]):
        """Process data from REST API"""
        try:
            if 'ohlc_data' in data:
                for item in data['ohlc_data']:
                    ohlc = OHLCData(
                        timestamp=datetime.fromisoformat(item['timestamp']),
                        symbol=item['symbol'],
                        open=float(item['open']),
                        high=float(item['high']),
                        low=float(item['low']),
                        close=float(item['close']),
                        volume=int(item['volume']),
                        source='rest_api'
                    )
                    self.ohlc_buffer.append(ohlc)
            
            if 'ml_predictions' in data:
                for item in data['ml_predictions']:
                    ml_label = MLLabel(
                        timestamp=datetime.fromisoformat(item['timestamp']),
                        symbol=item['symbol'],
                        prediction=int(item['prediction']),
                        confidence=float(item['confidence']),
                        model_version=item['model_version'],
                        features=item.get('features')
                    )
                    self.ml_buffer.append(ml_label)
                    
        except Exception as e:
            self.logger.error(f"Error processing API data: {str(e)}")
    
    async def buffer_flusher(self):
        """Periodically flush data buffers to database"""
        while self.running:
            try:
                await asyncio.sleep(self.flush_interval)
                
                if self.ohlc_buffer:
                    await self.flush_ohlc_buffer()
                if self.ml_buffer:
                    await self.flush_ml_buffer()
                    
            except Exception as e:
                self.logger.error(f"Buffer flushing error: {str(e)}")
    
    async def flush_ohlc_buffer(self):
        """Flush OHLC data buffer to database"""
        if not self.ohlc_buffer:
            return
            
        try:
            async with self.db_pool.acquire() as conn:
                # Prepare data for batch insert
                values = [
                    (
                        item.timestamp,
                        item.open,
                        item.high,
                        item.low,
                        item.close,
                        item.volume
                    )
                    for item in self.ohlc_buffer
                ]
                
                await conn.executemany(
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
                    values
                )
                
                self.logger.info(f"Flushed {len(self.ohlc_buffer)} OHLC records to database")
                
                # Clear buffer
                self.ohlc_buffer.clear()
                
        except Exception as e:
            self.logger.error(f"Error flushing OHLC buffer: {str(e)}")
    
    async def flush_ml_buffer(self):
        """Flush ML labels buffer to database"""
        if not self.ml_buffer:
            return
            
        try:
            async with self.db_pool.acquire() as conn:
                # Prepare data for batch insert
                values = [
                    (
                        item.timestamp,
                        item.symbol,
                        item.prediction,
                        item.confidence,
                        item.model_version,
                        json.dumps(item.features) if item.features else None
                    )
                    for item in self.ml_buffer
                ]
                
                await conn.executemany(
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
                    values
                )
                
                self.logger.info(f"Flushed {len(self.ml_buffer)} ML label records to database")
                
                # Clear buffer
                self.ml_buffer.clear()
                
        except Exception as e:
            self.logger.error(f"Error flushing ML buffer: {str(e)}")
    
    async def cache_updater(self):
        """Update Redis cache with latest data"""
        while self.running:
            try:
                await asyncio.sleep(30)  # Update cache every 30 seconds
                
                # Get latest OHLC data
                async with self.db_pool.acquire() as conn:
                    latest_data = await conn.fetch(
                        """
                        SELECT timestamp, open, high, low, close, volume
                        FROM nifty50_ohlc
                        WHERE timestamp > NOW() - INTERVAL '1 hour'
                        ORDER BY timestamp DESC
                        LIMIT 100
                        """
                    )
                    
                    # Update cache
                    if latest_data:
                        cache_data = [
                            {
                                'timestamp': row['timestamp'].isoformat(),
                                'open': float(row['open']),
                                'high': float(row['high']),
                                'low': float(row['low']),
                                'close': float(row['close']),
                                'volume': row['volume']
                            }
                            for row in latest_data
                        ]
                        
                        await self.redis_client.setex(
                            'latest_ohlc_data',
                            300,  # 5 minutes TTL
                            json.dumps(cache_data)
                        )
                        
                        self.logger.debug("Updated cache with latest OHLC data")
                        
            except Exception as e:
                self.logger.error(f"Cache update error: {str(e)}")
    
    async def get_latest_timestamp(self) -> datetime:
        """Get the latest timestamp from the database"""
        try:
            async with self.db_pool.acquire() as conn:
                result = await conn.fetchval(
                    "SELECT MAX(timestamp) FROM nifty50_ohlc"
                )
                return result or datetime.now() - timedelta(days=1)
        except Exception as e:
            self.logger.error(f"Error getting latest timestamp: {str(e)}")
            return datetime.now() - timedelta(days=1)


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Real-time Data Sync Service')
    parser.add_argument('--config', required=True, help='Configuration file path')
    parser.add_argument('--log-level', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'], 
                       default='INFO', help='Log level')
    
    args = parser.parse_args()
    
    # Set up logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Load configuration
    with open(args.config, 'r') as f:
        config = json.load(f)
    
    # Create and start service
    service = RealTimeDataSync(config)
    
    try:
        asyncio.run(service.start())
    except KeyboardInterrupt:
        logging.info("Service stopped by user")
    except Exception as e:
        logging.error(f"Service failed: {str(e)}")


if __name__ == "__main__":
    main()