#!/usr/bin/env python3
"""
Optimized F&O Data Loader
More efficient loading with reduced instrument count and better performance
"""

import os
import sys
import asyncio
import logging
from datetime import datetime, timedelta, time
from typing import List, Dict, Any, Optional
from pathlib import Path
import asyncpg

# Add backend directory to path
backend_dir = Path(__file__).parent / "backend"
sys.path.append(str(backend_dir))

from dotenv import load_dotenv
load_dotenv(backend_dir / ".env")

from config import DB_CONFIG
from kite_accounts import get_kite_service

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Database configuration
class OptimizedFODataLoader:
    def __init__(self):
        self.kite_service = get_kite_service()
        self.kite = self.kite_service.kite
        
        if not self.kite_service.is_authenticated():
            raise ValueError("Kite service not authenticated")
        
        self.total_records = 0
        
    async def get_existing_dates(self) -> List[str]:
        """Get dates that already have F&O data"""
        conn = await asyncpg.connect(**DB_CONFIG)
        try:
            existing = await conn.fetch('''
                SELECT DISTINCT DATE(time) as trade_date 
                FROM nifty_fo_ohlc 
                ORDER BY trade_date DESC
            ''')
            return [row['trade_date'].strftime('%Y-%m-%d') for row in existing]
        finally:
            await conn.close()
    
    async def get_nifty_price_for_date(self, target_date: datetime) -> Optional[float]:
        """Get Nifty price for specific date"""
        conn = await asyncpg.connect(**DB_CONFIG)
        try:
            price_data = await conn.fetchrow('''
                SELECT close 
                FROM nifty50_ohlc 
                WHERE DATE(time) = DATE($1)
                AND EXTRACT(hour FROM time) BETWEEN 9 AND 15
                ORDER BY time DESC 
                LIMIT 1
            ''', target_date)
            
            return float(price_data['close']) if price_data else None
        finally:
            await conn.close()
    
    def is_trading_day(self, date_obj: datetime) -> bool:
        """Check if given date is a trading day"""
        return date_obj.weekday() < 5  # Monday=0, Friday=4
    
    async def get_high_volume_instruments(self) -> Dict[str, List]:
        """Get only high-volume/OI F&O instruments to reduce load"""
        logger.info("📥 Loading high-volume F&O instruments...")
        
        instruments = self.kite.instruments('NFO')
        nifty_instruments = [inst for inst in instruments if inst['name'] == 'NIFTY']
        
        futures = [inst for inst in nifty_instruments if inst['instrument_type'] == 'FUT']
        
        # For options, we'll be more selective - focus on near ATM strikes
        options = [inst for inst in nifty_instruments if inst['instrument_type'] in ['CE', 'PE']]
        
        logger.info(f"✅ Available: {len(futures)} futures, {len(options)} options")
        
        return {
            'futures': futures,
            'options': options,
            'all': nifty_instruments
        }
    
    def get_focused_strikes(self, spot_price: float, range_size: int = 5) -> List[float]:
        """Get more focused strike range to reduce data volume"""
        atm_strike = round(spot_price / 50) * 50
        
        strikes = []
        for i in range(-range_size, range_size + 1):  # ±5 strikes instead of ±10
            strike = atm_strike + (i * 50)
            strikes.append(strike)
        
        return strikes
    
    def filter_to_focused_instruments(self, instruments: List[Dict], target_strikes: List[float]) -> List[Dict]:
        """Filter to focused instruments only"""
        filtered = []
        
        for inst in instruments:
            if inst['instrument_type'] == 'FUT':
                # Include all futures
                filtered.append(inst)
            else:
                # For options, only include focused strikes
                symbol = inst['tradingsymbol']
                import re
                match = re.search(r'(\d{4,5})(CE|PE)$', symbol)
                if match:
                    strike = float(match.group(1))
                    if strike in target_strikes:
                        filtered.append(inst)
        
        return filtered
    
    async def fetch_day_data_efficient(self, trade_date: datetime, instruments: List[Dict]) -> List[Dict]:
        """More efficient data fetching with larger batches"""
        
        market_start = trade_date.replace(hour=9, minute=15, second=0)
        market_end = trade_date.replace(hour=15, minute=30, second=0)
        
        logger.info(f"📊 Fetching {trade_date.strftime('%Y-%m-%d')}: {len(instruments)} instruments")
        
        all_data = []
        successful_count = 0
        
        # Larger batches for efficiency
        batch_size = 25
        total_batches = (len(instruments) + batch_size - 1) // batch_size
        
        for i in range(0, len(instruments), batch_size):
            batch = instruments[i:i + batch_size]
            batch_num = i // batch_size + 1
            
            logger.info(f"   Batch {batch_num}/{total_batches} ({len(batch)} instruments)")
            
            batch_data = []
            
            for inst in batch:
                try:
                    historical_data = self.kite.historical_data(
                        instrument_token=inst['instrument_token'],
                        from_date=market_start.strftime('%Y-%m-%d %H:%M:%S'),
                        to_date=market_end.strftime('%Y-%m-%d %H:%M:%S'),
                        interval='minute',
                        continuous=False,
                        oi=True
                    )
                    
                    if historical_data:
                        for candle in historical_data:
                            candle_data = {
                                'time': candle['date'],
                                'open': float(candle['open']),
                                'high': float(candle['high']),
                                'low': float(candle['low']),
                                'close': float(candle['close']),
                                'volume': int(candle.get('volume', 0)),
                                'oi': int(candle.get('oi', 0)),
                                'symbol': inst['tradingsymbol'],
                                'instrument_type': inst['instrument_type'],
                                'expiry_date': inst.get('expiry'),
                                'strike_price': self.extract_strike(inst['tradingsymbol']),
                                'option_type': inst['instrument_type'] if inst['instrument_type'] in ['CE', 'PE'] else None,
                                'instrument_token': inst['instrument_token']
                            }
                            batch_data.append(candle_data)
                        
                        successful_count += 1
                
                except Exception as e:
                    if "Invalid instrument_token" not in str(e):
                        logger.debug(f"Error: {inst.get('tradingsymbol', 'unknown')}: {e}")
                
                # Faster rate limiting
                await asyncio.sleep(0.03)
            
            all_data.extend(batch_data)
            
            # Shorter batch delay
            await asyncio.sleep(0.5)
            
            # Progress update
            if batch_num % 5 == 0 or batch_num == total_batches:
                logger.info(f"     Progress: {batch_num}/{total_batches} batches, {len(all_data)} records")
        
        logger.info(f"   ✅ Completed: {successful_count} instruments, {len(all_data)} records")
        return all_data
    
    def extract_strike(self, symbol: str) -> Optional[float]:
        """Extract strike price from symbol"""
        import re
        if 'FUT' in symbol:
            return None
        match = re.search(r'(\d{4,5})(CE|PE)$', symbol)
        return float(match.group(1)) if match else None
    
    async def save_data_batch(self, data: List[Dict], date_str: str):
        """Save data batch efficiently"""
        if not data:
            return
        
        conn = await asyncpg.connect(**DB_CONFIG)
        
        try:
            records = []
            for candle in data:
                timestamp = candle['time']
                if hasattr(timestamp, 'replace'):
                    timestamp = timestamp.replace(tzinfo=None)
                
                records.append((
                    timestamp, candle['open'], candle['high'], candle['low'], candle['close'],
                    candle['volume'], candle['oi'], candle['symbol'], candle['instrument_type'],
                    candle['expiry_date'], candle['strike_price'], candle['option_type'],
                    candle['instrument_token']
                ))
            
            insert_sql = """
                INSERT INTO nifty_fo_ohlc 
                (time, open, high, low, close, volume, oi, symbol, instrument_type, 
                 expiry_date, strike_price, option_type, instrument_token)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                ON CONFLICT (time, instrument_token) DO NOTHING
            """
            
            await conn.executemany(insert_sql, records)
            self.total_records += len(records)
            logger.info(f"💾 Saved {len(records)} records for {date_str}")
            
        finally:
            await conn.close()
    
    async def load_remaining_dates(self, days_back: int = 30):
        """Load F&O data for remaining dates"""
        logger.info(f"🚀 Loading F&O data for remaining dates (up to {days_back} days back)...")
        
        try:
            # Get existing dates
            existing_dates = await self.get_existing_dates()
            logger.info(f"📅 Already have data for {len(existing_dates)} dates")
            
            # Get instruments
            instruments_info = await self.get_high_volume_instruments()
            
            # Generate target dates
            current_date = datetime.now()
            target_dates = []
            
            check_date = current_date
            days_checked = 0
            
            while days_checked < days_back:
                if self.is_trading_day(check_date):
                    date_str = check_date.strftime('%Y-%m-%d')
                    if date_str not in existing_dates:
                        target_dates.append(check_date.date())
                    days_checked += 1
                check_date -= timedelta(days=1)
            
            target_dates.reverse()  # Process chronologically
            
            logger.info(f"📋 Need to load {len(target_dates)} new trading days")
            
            if not target_dates:
                logger.info("✅ All recent dates already loaded!")
                return
            
            # Process each target date
            for i, trade_date in enumerate(target_dates):
                try:
                    trade_datetime = datetime.combine(trade_date, time(9, 15))
                    
                    # Get Nifty price
                    nifty_price = await self.get_nifty_price_for_date(trade_datetime)
                    
                    if not nifty_price:
                        logger.warning(f"⚠️ No Nifty price for {trade_date}, skipping")
                        continue
                    
                    # Calculate focused strikes (smaller range for efficiency)
                    target_strikes = self.get_focused_strikes(nifty_price, range_size=5)
                    atm_strike = round(nifty_price / 50) * 50
                    
                    logger.info(f"📊 Day {i+1}/{len(target_dates)}: {trade_date}")
                    logger.info(f"   Nifty: ₹{nifty_price:,.2f}, ATM: ₹{atm_strike:,.0f}, Strikes: ±5")
                    
                    # Filter to focused instruments
                    focused_instruments = self.filter_to_focused_instruments(
                        instruments_info['all'], target_strikes
                    )
                    
                    logger.info(f"   Focused instruments: {len(focused_instruments)}")
                    
                    # Fetch data
                    fo_data = await self.fetch_day_data_efficient(trade_datetime, focused_instruments)
                    
                    # Save data
                    if fo_data:
                        await self.save_data_batch(fo_data, trade_date.strftime('%Y-%m-%d'))
                        logger.info(f"   ✅ Completed {trade_date}")
                    else:
                        logger.warning(f"   ⚠️ No data for {trade_date}")
                    
                    # Progress
                    progress = ((i + 1) / len(target_dates)) * 100
                    logger.info(f"📈 Progress: {progress:.1f}% | Total records: {self.total_records:,}")
                    
                except Exception as e:
                    logger.error(f"❌ Error processing {trade_date}: {e}")
                
                # Rate limiting
                await asyncio.sleep(2)
            
            logger.info(f"🎉 Optimized F&O loading completed!")
            logger.info(f"   📊 Total new records: {self.total_records:,}")
            
        except Exception as e:
            logger.error(f"❌ Error in optimized loading: {e}")
            raise

async def main():
    """Main execution"""
    try:
        loader = OptimizedFODataLoader()
        await loader.load_remaining_dates(days_back=21)  # Load last 3 weeks
        
    except Exception as e:
        logger.error(f"❌ Error in main: {e}")

if __name__ == "__main__":
    asyncio.run(main())
