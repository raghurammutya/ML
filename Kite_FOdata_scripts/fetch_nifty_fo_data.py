#!/usr/bin/env python3
"""
Smart Nifty F&O Data Fetcher
Efficiently fetches Futures and Options data with intelligent strike selection
"""

import os
import sys
import json
import asyncio
import logging
import re
from datetime import datetime, timedelta, date
from typing import List, Dict, Any, Optional, Tuple
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

class NiftyFODataFetcher:
    def __init__(self):
        self.kite_service = get_kite_service()
        self.kite = self.kite_service.kite
        
        if not self.kite_service.is_authenticated():
            raise ValueError("Kite service not authenticated")
        
        self.instruments_cache = {}
        self.strike_step = 50  # Nifty strikes are in multiples of 50
        
    def parse_nifty_symbol(self, symbol: str) -> Optional[Dict]:
        """Parse Nifty F&O symbols into components"""
        
        # Futures: NIFTY25OCTFUT, NIFTY25NOVFUT  
        if symbol.endswith('FUT'):
            match = re.match(r'NIFTY(\d{2})([A-Z]{3})FUT', symbol)
            if match:
                year = int('20' + match.group(1))
                month = match.group(2)
                return {
                    'instrument_type': 'FUT',
                    'expiry_year': year,
                    'expiry_month': month,
                    'strike_price': None,
                    'option_type': None
                }
        
        # Options: NIFTY25OCT25850CE, NIFTY25NOV26000PE
        # Fixed regex to handle 5-digit strikes properly
        elif symbol.endswith('CE') or symbol.endswith('PE'):
            # Handle 4-5 digit strikes: 9500, 25850, etc.
            match = re.match(r'NIFTY(\d{2})([A-Z]{3})(\d{4,5})(CE|PE)', symbol)
            if match:
                year = int('20' + match.group(1))
                month = match.group(2)
                strike = float(match.group(3))
                option_type = match.group(4)
                return {
                    'instrument_type': 'OPT',
                    'expiry_year': year,
                    'expiry_month': month,
                    'strike_price': strike,
                    'option_type': option_type
                }
        
        return None
    
    def get_month_number(self, month_str: str) -> int:
        """Convert month abbreviation to number"""
        months = {
            'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
            'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12
        }
        return months.get(month_str, 0)
    
    def calculate_atm_strike(self, spot_price: float) -> float:
        """Calculate ATM strike price rounded to nearest step"""
        return round(spot_price / self.strike_step) * self.strike_step
    
    def get_strike_range(self, atm_strike: float, range_size: int = 10) -> List[float]:
        """Get strike range around ATM (±range_size strikes)"""
        strikes = []
        for i in range(-range_size, range_size + 1):
            strike = atm_strike + (i * self.strike_step)
            strikes.append(strike)
        return strikes
    
    async def load_fo_instruments(self) -> Dict[str, Dict]:
        """Load and cache F&O instruments with parsing"""
        if self.instruments_cache:
            return self.instruments_cache
        
        logger.info("Loading F&O instruments...")
        
        try:
            # Get all NFO instruments
            instruments = self.kite.instruments('NFO')
            nifty_instruments = [inst for inst in instruments if inst['name'] == 'NIFTY']
            
            logger.info(f"Found {len(nifty_instruments)} NIFTY F&O instruments")
            
            # Parse and cache instruments
            for inst in nifty_instruments:
                symbol = inst['tradingsymbol']
                parsed = self.parse_nifty_symbol(symbol)
                
                if parsed:
                    # Calculate expiry date
                    expiry_year = parsed['expiry_year']
                    expiry_month = self.get_month_number(parsed['expiry_month'])
                    
                    # Use the exchange expiry date if available, otherwise estimate
                    if inst.get('expiry'):
                        if isinstance(inst['expiry'], str):
                            expiry_date = datetime.strptime(inst['expiry'], '%Y-%m-%d').date()
                        else:
                            expiry_date = inst['expiry']  # Already a date object
                    else:
                        # Estimate last Thursday of the month
                        expiry_date = date(expiry_year, expiry_month, 1)
                    
                    self.instruments_cache[symbol] = {
                        'instrument_token': inst['instrument_token'],
                        'symbol': symbol,
                        'instrument_type': parsed['instrument_type'],
                        'expiry_date': expiry_date,
                        'strike_price': parsed['strike_price'],
                        'option_type': parsed['option_type'],
                        'lot_size': inst.get('lot_size', 25),
                        'tick_size': inst.get('tick_size', 0.05)
                    }
            
            logger.info(f"Cached {len(self.instruments_cache)} parsed instruments")
            return self.instruments_cache
            
        except Exception as e:
            logger.error(f"Error loading instruments: {e}")
            raise
    
    async def get_target_instruments(self, spot_price: float, target_date: date = None) -> List[Dict]:
        """Get list of instruments to fetch based on ATM calculation"""
        
        if target_date is None:
            target_date = date.today()
        
        instruments = await self.load_fo_instruments()
        
        # Calculate ATM and strike range
        atm_strike = self.calculate_atm_strike(spot_price)
        strike_range = self.get_strike_range(atm_strike, 10)  # ±10 strikes
        
        target_instruments = []
        
        # Get active expiries for target date
        active_expiries = set()
        for inst_data in instruments.values():
            if inst_data['expiry_date'] >= target_date:
                active_expiries.add(inst_data['expiry_date'])
        
        active_expiries = sorted(list(active_expiries))[:4]  # Limit to 4 nearest expiries
        
        logger.info(f"ATM: ₹{atm_strike}, Strike range: ₹{strike_range[0]}-₹{strike_range[-1]}")
        logger.info(f"Active expiries: {len(active_expiries)}")
        
        # Add Futures for all active expiries
        for inst_data in instruments.values():
            if (inst_data['instrument_type'] == 'FUT' and 
                inst_data['expiry_date'] in active_expiries):
                target_instruments.append(inst_data)
        
        # Add Options for strike range across all active expiries
        for inst_data in instruments.values():
            if (inst_data['instrument_type'] == 'OPT' and 
                inst_data['expiry_date'] in active_expiries and
                inst_data['strike_price'] in strike_range):
                target_instruments.append(inst_data)
        
        logger.info(f"Target instruments: {len(target_instruments)} (Futures: {len([i for i in target_instruments if i['instrument_type'] == 'FUT'])}, Options: {len([i for i in target_instruments if i['instrument_type'] == 'OPT'])})")
        
        return target_instruments
    
    async def fetch_historical_data_batch(self, instruments: List[Dict], 
                                        from_date: datetime, to_date: datetime) -> List[Dict]:
        """Fetch historical data for multiple instruments efficiently"""
        
        all_data = []
        batch_size = 20  # Process in smaller batches to avoid rate limiting
        
        for i in range(0, len(instruments), batch_size):
            batch = instruments[i:i + batch_size]
            logger.info(f"Processing batch {i//batch_size + 1}/{(len(instruments) + batch_size - 1)//batch_size}")
            
            batch_data = []
            for inst in batch:
                try:
                    historical_data = self.kite.historical_data(
                        instrument_token=inst['instrument_token'],
                        from_date=from_date.strftime('%Y-%m-%d %H:%M:%S'),
                        to_date=to_date.strftime('%Y-%m-%d %H:%M:%S'),
                        interval="minute",  # 1-minute data only
                        continuous=False,
                        oi=True  # Include Open Interest - CRITICAL for F&O
                    )
                    
                    # Add instrument metadata to each candle
                    for candle in historical_data:
                        candle_data = {
                            'time': candle['date'],
                            'open': float(candle['open']),
                            'high': float(candle['high']),
                            'low': float(candle['low']),
                            'close': float(candle['close']),
                            'volume': int(candle.get('volume', 0)),
                            'oi': int(candle.get('oi', 0)),  # Open Interest
                            'symbol': inst['symbol'],
                            'instrument_type': inst['instrument_type'],
                            'expiry_date': inst['expiry_date'],
                            'strike_price': inst['strike_price'],
                            'option_type': inst['option_type'],
                            'instrument_token': inst['instrument_token']
                        }
                        batch_data.append(candle_data)
                    
                    logger.info(f"  {inst['symbol']}: {len(historical_data)} candles")
                    
                except Exception as e:
                    logger.error(f"Error fetching {inst['symbol']}: {e}")
                
                # Small delay to avoid rate limiting
                await asyncio.sleep(0.1)
            
            all_data.extend(batch_data)
            
            # Longer delay between batches
            if i + batch_size < len(instruments):
                await asyncio.sleep(1)
        
        return all_data
    
    async def save_fo_data(self, data: List[Dict]):
        """Save F&O data to database"""
        if not data:
            logger.info("No data to save")
            return
        
        conn = await asyncpg.connect(**DB_CONFIG)
        
        try:
            # Prepare records for insertion
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
            
            # Insert data
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
            logger.info(f"Saved {len(records)} F&O records to database")
            
        finally:
            await conn.close()

async def main():
    """Main function for F&O data fetching"""
    try:
        fetcher = NiftyFODataFetcher()
        
        # Get current Nifty price for ATM calculation
        nifty_quote = fetcher.kite.quote('NSE:NIFTY 50')
        current_price = list(nifty_quote.values())[0]['last_price']
        
        logger.info(f"Current Nifty: ₹{current_price}")
        
        # Test with small date range first
        test_date = datetime.now().replace(hour=9, minute=15, second=0, microsecond=0)
        end_date = test_date + timedelta(hours=1)  # 1 hour of data for testing
        
        logger.info(f"Fetching F&O data from {test_date} to {end_date}")
        
        # Get target instruments based on current price
        target_instruments = await fetcher.get_target_instruments(current_price)
        
        # Fetch data for target instruments
        fo_data = await fetcher.fetch_historical_data_batch(
            target_instruments, test_date, end_date
        )
        
        # Save to database
        await fetcher.save_fo_data(fo_data)
        
        logger.info("F&O data fetch completed successfully")
        
    except Exception as e:
        logger.error(f"Error in main function: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())
