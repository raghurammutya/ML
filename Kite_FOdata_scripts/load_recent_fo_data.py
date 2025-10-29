#!/usr/bin/env python3
"""
Recent F&O Data Loader
Loads available F&O data for the recent period (last few weeks/months)
"""

import os
import sys
import asyncio
import logging
from datetime import datetime, timedelta, time, date
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
from session_manager import SessionOrchestrator

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Database configuration
class RecentFODataLoader:
    def __init__(self, kite_service=None, account_id: Optional[str] = None):
        self.kite_service = kite_service or get_kite_service()
        self.kite = self.kite_service.kite
        self.account_id = account_id or getattr(self.kite_service, "account_id", "default")
        
        if not self.kite_service.is_authenticated():
            raise ValueError("Kite service not authenticated")
        
        self.successful_dates: List[date] = []
        self.failed_dates: List[date] = []
        self.total_records = 0
        
    async def get_nifty_price_for_time(self, target_datetime: datetime) -> Optional[float]:
        """Get Nifty price for specific datetime"""
        conn = await asyncpg.connect(**DB_CONFIG)
        try:
            # Get price closest to target time
            price_data = await conn.fetchrow('''
                SELECT close 
                FROM nifty50_ohlc 
                WHERE time <= $1
                ORDER BY time DESC 
                LIMIT 1
            ''', target_datetime)
            
            return float(price_data['close']) if price_data else None
        finally:
            await conn.close()
    
    @staticmethod
    def is_trading_day(date_obj: datetime) -> bool:
        """Check if given date is a trading day (Monday-Friday, basic check)"""
        return date_obj.weekday() < 5
    
    def is_market_hours(self, dt: datetime) -> bool:
        """Check if datetime is within market hours"""
        return 9 <= dt.hour <= 15
    
    async def get_current_fo_instruments(self) -> Dict[str, List]:
        """Get current F&O instruments grouped by type"""
        logger.info("📥 Loading current F&O instruments...")
        
        instruments = self.kite.instruments('NFO')
        nifty_instruments = [inst for inst in instruments if inst['name'] == 'NIFTY']
        
        futures = [inst for inst in nifty_instruments if inst['instrument_type'] == 'FUT']
        options = [inst for inst in nifty_instruments if inst['instrument_type'] in ['CE', 'PE']]
        
        logger.info(f"✅ Found {len(futures)} futures and {len(options)} options")
        
        return {
            'futures': futures,
            'options': options,
            'all': nifty_instruments
        }
    
    def calculate_atm_strikes(self, spot_price: float) -> List[float]:
        """Calculate relevant strikes around ATM"""
        atm_strike = round(spot_price / 50) * 50
        
        strikes = []
        for i in range(-10, 11):  # ±10 strikes
            strike = atm_strike + (i * 50)
            strikes.append(strike)
        
        return strikes
    
    def filter_instruments_by_strikes(self, instruments: List[Dict], target_strikes: List[float]) -> List[Dict]:
        """Filter option instruments to only include target strikes"""
        filtered = []
        
        for inst in instruments:
            if inst['instrument_type'] == 'FUT':
                # Include all futures
                filtered.append(inst)
            else:
                # For options, extract strike and check if it's in target range
                symbol = inst['tradingsymbol']
                # Extract strike from symbol like NIFTY25OCT25900CE
                import re
                match = re.search(r'(\d{4,5})(CE|PE)$', symbol)
                if match:
                    strike = float(match.group(1))
                    if strike in target_strikes:
                        filtered.append(inst)
        
        return filtered
    
    async def fetch_fo_data_for_period(self, start_time: datetime, end_time: datetime, 
                                     instruments: List[Dict]) -> List[Dict]:
        """Fetch F&O data for specific time period"""
        
        logger.info(f"📊 Fetching F&O data: {start_time.strftime('%Y-%m-%d %H:%M')} to {end_time.strftime('%H:%M')}")
        logger.info(f"   Instruments: {len(instruments)}")
        
        all_data = []
        successful_count = 0
        failed_count = 0
        
        # Process in batches to avoid overwhelming the API
        batch_size = 15
        for i in range(0, len(instruments), batch_size):
            batch = instruments[i:i + batch_size]
            
            logger.info(f"   Processing batch {i//batch_size + 1}/{(len(instruments) + batch_size - 1)//batch_size}")
            
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
                        # Process each candle
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
                                'strike_price': self.extract_strike_from_symbol(inst['tradingsymbol']),
                                'option_type': inst['instrument_type'] if inst['instrument_type'] in ['CE', 'PE'] else None,
                                'instrument_token': inst['instrument_token']
                            }
                            all_data.append(candle_data)
                        
                        successful_count += 1
                        if successful_count % 10 == 0:
                            logger.info(f"     Progress: {successful_count}/{len(instruments)} instruments processed")
                    else:
                        failed_count += 1
                
                except Exception as e:
                    failed_count += 1
                    if "Invalid instrument_token" not in str(e):
                        logger.debug(f"Error fetching {inst.get('tradingsymbol', 'unknown')}: {e}")
                
                # Rate limiting
                await asyncio.sleep(0.05)
            
            # Batch delay
            await asyncio.sleep(0.8)
        
        logger.info(f"   ✅ Completed: {successful_count} success, {failed_count} failed, {len(all_data)} records")
        return all_data
    
    def extract_strike_from_symbol(self, symbol: str) -> Optional[float]:
        """Extract strike price from option symbol"""
        import re
        if 'FUT' in symbol:
            return None
        match = re.search(r'(\d{4,5})(CE|PE)$', symbol)
        return float(match.group(1)) if match else None
    
    async def save_fo_data_batch(self, data: List[Dict]):
        """Save F&O data to database"""
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
            self.total_records += len(records)
            logger.info(f"💾 Saved {len(records)} F&O records to database")
            
        finally:
            await conn.close()
    
    @staticmethod
    def compute_trading_days(days_back: int, start_date: Optional[datetime] = None) -> List[date]:
        current_date = start_date or datetime.now()
        trading_days: List[date] = []
        day_count = 0
        check_date = current_date
        while day_count < days_back:
            if RecentFODataLoader.is_trading_day(check_date):
                trading_days.append(check_date.date())
                day_count += 1
            check_date -= timedelta(days=1)
        trading_days.reverse()
        return trading_days

    async def process_trading_days(self, trading_days: List[date]):
        logger.info(f"🚀 [{self.account_id}] Starting F&O data loading for {len(trading_days)} trading days...")
        try:
            instruments_by_type = await self.get_current_fo_instruments()
            for i, trade_date in enumerate(trading_days):
                try:
                    # Create datetime for market start
                    market_start = datetime.combine(trade_date, time(9, 15))
                    market_end = datetime.combine(trade_date, time(15, 30))
                    
                    # Get Nifty price for ATM calculation
                    nifty_price = await self.get_nifty_price_for_time(market_start)
                    
                    if not nifty_price:
                        logger.warning(f"⚠️ No Nifty price for {trade_date}, skipping")
                        self.failed_dates.append(trade_date)
                        continue
                    
                    # Calculate relevant strikes
                    target_strikes = self.calculate_atm_strikes(nifty_price)
                    atm_strike = round(nifty_price / 50) * 50
                    
                    logger.info(f"📊 [{self.account_id}] Day {i+1}/{len(trading_days)}: {trade_date}")
                    logger.info(f"   Nifty: ₹{nifty_price:,.2f}, ATM: ₹{atm_strike:,.0f}")
                    
                    # Filter instruments to relevant strikes
                    filtered_instruments = self.filter_instruments_by_strikes(
                        instruments_by_type['all'], target_strikes
                    )
                    
                    logger.info(f"   Target instruments: {len(filtered_instruments)}")
                    
                    # Fetch data for the full trading day
                    fo_data = await self.fetch_fo_data_for_period(
                        market_start, market_end, filtered_instruments
                    )
                    
                    # Save data
                    if fo_data:
                        await self.save_fo_data_batch(fo_data)
                        self.successful_dates.append(trade_date)
                        logger.info(f"   ✅ [{self.account_id}] Completed {trade_date}")
                    else:
                        logger.warning(f"   ⚠️ No data for {trade_date}")
                        self.failed_dates.append(trade_date)
                    
                    # Progress update
                    progress = ((i + 1) / len(trading_days)) * 100
                    logger.info(f"📈 [{self.account_id}] Progress: {progress:.1f}%")
                    
                except Exception as e:
                    logger.error(f"❌ [{self.account_id}] Error processing {trade_date}: {e}")
                    self.failed_dates.append(trade_date)
                
                # Rate limiting between days
                await asyncio.sleep(3)
            logger.info(
                f"🎉 [{self.account_id}] Summary -> Success: {len(self.successful_dates)}, "
                f"Failed: {len(self.failed_dates)}, Records: {self.total_records:,}"
            )
        except Exception as e:
            logger.error(f"❌ [{self.account_id}] Error in F&O data loading: {e}")
            raise

    async def load_recent_fo_data(self, days_back: int = 30):
        trading_days = self.compute_trading_days(days_back)
        await self.process_trading_days(trading_days)


async def run_distributed_recent_loader(days_back: int = 30, orchestrator: Optional[SessionOrchestrator] = None):
    orchestrator = orchestrator or SessionOrchestrator()
    trading_days = RecentFODataLoader.compute_trading_days(days_back)
    assignments = orchestrator.distribute(trading_days)
    logger.info(f"🤝 Distributing {len(trading_days)} days across accounts: {list(assignments.keys())}")

    async def worker(account_id: str, days: List[date]):
        async with orchestrator.borrow(account_id) as service:
            loader = RecentFODataLoader(kite_service=service, account_id=account_id)
            await loader.process_trading_days(days)

    tasks = [asyncio.create_task(worker(account_id, days)) for account_id, days in assignments.items()]
    if tasks:
        await asyncio.gather(*tasks)


async def main():
    """Main execution function"""
    try:
        distributed = os.getenv("KITE_DISTRIBUTED", "0") == "1"
        days_back = int(os.getenv("FO_DAYS_BACK", "14"))
        if distributed:
            orchestrator = SessionOrchestrator()
            await run_distributed_recent_loader(days_back=days_back, orchestrator=orchestrator)
        else:
            loader = RecentFODataLoader()
            await loader.load_recent_fo_data(days_back=days_back)
    except Exception as e:
        logger.error(f"❌ Error in main: {e}")

if __name__ == "__main__":
    asyncio.run(main())
