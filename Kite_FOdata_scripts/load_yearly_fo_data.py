#!/usr/bin/env python3
"""
1-Year F&O Data Loader
Systematically loads F&O data for the last year with intelligent handling of API limits
"""

import os
import sys
import asyncio
import logging
from datetime import datetime, timedelta, time
from typing import List, Dict, Any, Optional, Tuple
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
class YearlyFODataLoader:
    def __init__(self):
        self.kite_service = get_kite_service()
        self.kite = self.kite_service.kite
        
        if not self.kite_service.is_authenticated():
            raise ValueError("Kite service not authenticated")
        
        self.instruments_cache = {}
        self.strike_step = 50
        self.successful_dates = []
        self.failed_dates = []
        
    async def get_nifty_price_for_date(self, target_date: datetime) -> Optional[float]:
        """Get Nifty price for ATM calculation on specific date"""
        conn = await asyncpg.connect(**DB_CONFIG)
        try:
            # Get price closest to target date (market hours)
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
    
    async def load_fo_instruments(self) -> Dict[str, Dict]:
        """Load and cache current F&O instruments"""
        if self.instruments_cache:
            return self.instruments_cache
        
        logger.info("Loading current F&O instruments for reference...")
        
        try:
            instruments = self.kite.instruments('NFO')
            nifty_instruments = [inst for inst in instruments if inst['name'] == 'NIFTY']
            
            logger.info(f"Found {len(nifty_instruments)} current NIFTY F&O instruments")
            
            # Cache instruments by type for easier access
            self.instruments_cache = {
                'futures': [inst for inst in nifty_instruments if inst['instrument_type'] == 'FUT'],
                'options': [inst for inst in nifty_instruments if inst['instrument_type'] in ['CE', 'PE']],
                'all': nifty_instruments
            }
            
            return self.instruments_cache
            
        except Exception as e:
            logger.error(f"Error loading instruments: {e}")
            raise
    
    async def test_data_availability_range(self) -> Tuple[datetime, datetime]:
        """Test and find the actual data availability range"""
        logger.info("🔍 Testing F&O data availability range...")
        
        instruments = await self.load_fo_instruments()
        test_instrument = instruments['futures'][0] if instruments['futures'] else None
        
        if not test_instrument:
            raise ValueError("No futures instruments available for testing")
        
        current_date = datetime.now()
        available_start = None
        available_end = current_date
        
        # Test different periods to find availability window
        test_periods = [1, 3, 7, 14, 30, 60, 90, 180, 365]  # days back
        
        for days_back in test_periods:
            test_date = current_date - timedelta(days=days_back)
            test_end = test_date + timedelta(hours=1)
            
            try:
                historical_data = self.kite.historical_data(
                    instrument_token=test_instrument['instrument_token'],
                    from_date=test_date.strftime('%Y-%m-%d %H:%M:%S'),
                    to_date=test_end.strftime('%Y-%m-%d %H:%M:%S'),
                    interval='minute',
                    oi=True
                )
                
                if historical_data and len(historical_data) > 0:
                    available_start = test_date
                    logger.info(f"✅ Data available {days_back} days back: {len(historical_data)} candles")
                else:
                    logger.info(f"❌ No data {days_back} days back")
                    break
                    
            except Exception as e:
                logger.info(f"❌ Error {days_back} days back: {str(e)[:50]}...")
                break
        
        if available_start:
            logger.info(f"📊 F&O Data availability window: {available_start.strftime('%Y-%m-%d')} to {available_end.strftime('%Y-%m-%d')}")
            return available_start, available_end
        else:
            logger.warning("⚠️ No historical F&O data available via API")
            return current_date, current_date
    
    def calculate_atm_and_strikes(self, spot_price: float) -> Dict:
        """Calculate ATM and strike range for given spot price"""
        atm_strike = round(spot_price / self.strike_step) * self.strike_step
        
        strike_range = []
        for i in range(-10, 11):  # ±10 strikes
            strike = atm_strike + (i * self.strike_step)
            strike_range.append(strike)
        
        return {
            'atm_strike': atm_strike,
            'strike_range': strike_range,
            'spot_price': spot_price
        }
    
    async def get_target_instruments_for_date(self, target_date: datetime, spot_price: float) -> List[Dict]:
        """Get target F&O instruments for specific date based on spot price"""
        
        instruments = await self.load_fo_instruments()
        strikes_info = self.calculate_atm_and_strikes(spot_price)
        
        target_instruments = []
        
        # Add all available futures (they don't depend on strikes)
        target_instruments.extend(instruments['futures'])
        
        # Add options within strike range
        for inst in instruments['options']:
            # For options, we need to check if the strike is in our range
            # Current API instruments might not have historical strikes, but we'll try
            target_instruments.append(inst)
        
        logger.info(f"Target instruments for {target_date.strftime('%Y-%m-%d')}: {len(target_instruments)} total")
        logger.info(f"  ATM: ₹{strikes_info['atm_strike']}, Range: ₹{strikes_info['strike_range'][0]}-₹{strikes_info['strike_range'][-1]}")
        
        return target_instruments
    
    async def fetch_fo_data_for_date(self, target_date: datetime, instruments: List[Dict]) -> List[Dict]:
        """Fetch F&O data for specific date"""
        
        start_time = target_date.replace(hour=9, minute=15, second=0, microsecond=0)
        end_time = target_date.replace(hour=15, minute=30, second=0, microsecond=0)
        
        logger.info(f"📥 Fetching F&O data for {target_date.strftime('%Y-%m-%d')} ({len(instruments)} instruments)")
        
        all_data = []
        successful_instruments = 0
        failed_instruments = 0
        
        # Process in smaller batches
        batch_size = 10
        for i in range(0, len(instruments), batch_size):
            batch = instruments[i:i + batch_size]
            
            for inst in batch:
                try:
                    historical_data = self.kite.historical_data(
                        instrument_token=inst['instrument_token'],
                        from_date=start_time.strftime('%Y-%m-%d %H:%M:%S'),
                        to_date=end_time.strftime('%Y-%m-%d %H:%M:%S'),
                        interval='minute',
                        continuous=False,
                        oi=True
                    )
                    
                    if historical_data:
                        # Parse instrument info
                        symbol = inst['tradingsymbol']
                        inst_type = inst['instrument_type']
                        
                        for candle in historical_data:
                            candle_data = {
                                'time': candle['date'],
                                'open': float(candle['open']),
                                'high': float(candle['high']),
                                'low': float(candle['low']),
                                'close': float(candle['close']),
                                'volume': int(candle.get('volume', 0)),
                                'oi': int(candle.get('oi', 0)),
                                'symbol': symbol,
                                'instrument_type': inst_type,
                                'expiry_date': inst.get('expiry'),
                                'strike_price': None if inst_type == 'FUT' else self.extract_strike_from_symbol(symbol),
                                'option_type': None if inst_type == 'FUT' else inst_type,
                                'instrument_token': inst['instrument_token']
                            }
                            all_data.append(candle_data)
                        
                        successful_instruments += 1
                        
                    else:
                        failed_instruments += 1
                
                except Exception as e:
                    failed_instruments += 1
                    if "Invalid instrument_token" not in str(e):
                        logger.debug(f"Error fetching {inst.get('tradingsymbol', 'unknown')}: {e}")
                
                # Rate limiting
                await asyncio.sleep(0.05)
            
            # Batch delay
            await asyncio.sleep(0.5)
        
        logger.info(f"  ✅ Success: {successful_instruments}, ❌ Failed: {failed_instruments}, 📊 Records: {len(all_data)}")
        return all_data
    
    def extract_strike_from_symbol(self, symbol: str) -> Optional[float]:
        """Extract strike price from option symbol"""
        import re
        # Match patterns like NIFTY25OCT25900CE -> 25900
        match = re.search(r'(\d{4,5})(CE|PE)$', symbol)
        return float(match.group(1)) if match else None
    
    async def save_fo_data_batch(self, data: List[Dict], date_str: str):
        """Save F&O data batch to database"""
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
                    timestamp,
                    candle['open'],
                    candle['high'],
                    candle['low'],
                    candle['close'],
                    candle['volume'],
                    candle['oi'],
                    candle['symbol'],
                    candle['instrument_type'],
                    candle['expiry_date'],
                    candle['strike_price'],
                    candle['option_type'],
                    candle['instrument_token']
                ))
            
            insert_sql = """
                INSERT INTO nifty_fo_ohlc 
                (time, open, high, low, close, volume, oi, symbol, instrument_type, 
                 expiry_date, strike_price, option_type, instrument_token)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                ON CONFLICT (time, instrument_token) DO UPDATE SET
                    open = EXCLUDED.open,
                    high = EXCLUDED.high,
                    low = EXCLUDED.low,
                    close = EXCLUDED.close,
                    volume = EXCLUDED.volume,
                    oi = EXCLUDED.oi
            """
            
            await conn.executemany(insert_sql, records)
            logger.info(f"💾 Saved {len(records)} F&O records for {date_str}")
            
        finally:
            await conn.close()
    
    async def load_yearly_fo_data(self):
        """Main function to load F&O data for the last year"""
        logger.info("🚀 Starting 1-year F&O data loading process...")
        
        try:
            # Test data availability
            available_start, available_end = await self.test_data_availability_range()
            
            if available_start == available_end:
                logger.error("❌ No historical F&O data available via API")
                return
            
            # Load instruments
            await self.load_fo_instruments()
            
            # Generate date range (working backwards from available_end)
            current_date = available_end.date()
            start_date = max(available_start.date(), current_date - timedelta(days=365))
            
            logger.info(f"📅 Loading F&O data from {start_date} to {current_date}")
            
            total_days = (current_date - start_date).days
            processed_days = 0
            
            # Process day by day
            current_process_date = current_date
            
            while current_process_date >= start_date:
                # Skip weekends
                if current_process_date.weekday() >= 5:
                    current_process_date -= timedelta(days=1)
                    continue
                
                try:
                    # Get Nifty price for this date
                    target_datetime = datetime.combine(current_process_date, time(9, 15))
                    nifty_price = await self.get_nifty_price_for_date(target_datetime)
                    
                    if not nifty_price:
                        logger.warning(f"⚠️ No Nifty price for {current_process_date}, skipping")
                        current_process_date -= timedelta(days=1)
                        continue
                    
                    # Get target instruments for this date
                    target_instruments = await self.get_target_instruments_for_date(target_datetime, nifty_price)
                    
                    # Fetch F&O data
                    fo_data = await self.fetch_fo_data_for_date(target_datetime, target_instruments)
                    
                    # Save data
                    if fo_data:
                        await self.save_fo_data_batch(fo_data, current_process_date.strftime('%Y-%m-%d'))
                        self.successful_dates.append(current_process_date)
                    else:
                        logger.warning(f"⚠️ No F&O data available for {current_process_date}")
                        self.failed_dates.append(current_process_date)
                    
                    processed_days += 1
                    progress = (processed_days / total_days) * 100
                    logger.info(f"📊 Progress: {progress:.1f}% ({processed_days}/{total_days} days)")
                    
                except Exception as e:
                    logger.error(f"❌ Error processing {current_process_date}: {e}")
                    self.failed_dates.append(current_process_date)
                
                current_process_date -= timedelta(days=1)
                
                # Rate limiting between days
                await asyncio.sleep(2)
            
            # Summary
            logger.info(f"🎉 F&O data loading completed!")
            logger.info(f"   ✅ Successful days: {len(self.successful_dates)}")
            logger.info(f"   ❌ Failed days: {len(self.failed_dates)}")
            
            if self.successful_dates:
                logger.info(f"   📅 Date range: {min(self.successful_dates)} to {max(self.successful_dates)}")
            
        except Exception as e:
            logger.error(f"❌ Error in yearly F&O data loading: {e}")
            raise

async def main():
    """Main execution function"""
    try:
        loader = YearlyFODataLoader()
        await loader.load_yearly_fo_data()
        
    except Exception as e:
        logger.error(f"❌ Error in main: {e}")

if __name__ == "__main__":
    asyncio.run(main())
