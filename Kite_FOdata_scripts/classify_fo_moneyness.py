#!/usr/bin/env python3
"""
F&O Moneyness Classification System
Dynamically classifies each F&O record as ITM/OTM/ATM based on minute-by-minute Nifty50 spot price
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import asyncpg

from config import DB_CONFIG

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class FOMoneynessClassifier:
    def __init__(self):
        self.strike_step = 50  # Nifty strikes are in multiples of 50
        self.processed_records = 0
        
    def calculate_moneyness(self, strike_price: Optional[float], spot_price: float, 
                          option_type: Optional[str], instrument_type: str) -> Dict:
        """
        Calculate moneyness classification for an F&O instrument
        
        Args:
            strike_price: Option strike price (None for futures)
            spot_price: Current Nifty spot price
            option_type: 'CE' or 'PE' for options (None for futures)
            instrument_type: 'FUT', 'CE', or 'PE'
            
        Returns:
            Dict with moneyness, position, and label
        """
        
        # Futures don't have moneyness classification
        if instrument_type == 'FUT' or strike_price is None:
            return {
                'moneyness': 'N/A',
                'moneyness_position': 0,
                'moneyness_label': 'FUTURES'
            }
        
        # Calculate ATM strike (nearest 50)
        atm_strike = round(spot_price / self.strike_step) * self.strike_step
        
        # Calculate distance from ATM
        strike_distance = abs(strike_price - atm_strike)
        position_steps = int(strike_distance / self.strike_step)
        
        # Determine moneyness based on option type
        if strike_price == atm_strike:
            # At-the-money
            moneyness = 'ATM'
            position = 0
            label = 'ATM'
            
        elif option_type == 'CE':  # Call options
            if strike_price < spot_price:
                # Call is in-the-money
                moneyness = 'ITM'
                position = position_steps
                label = f'ITM {position}' if position > 0 else 'ATM'
            else:
                # Call is out-of-the-money
                moneyness = 'OTM'
                position = position_steps
                label = f'OTM {position}' if position > 0 else 'ATM'
                
        elif option_type == 'PE':  # Put options
            if strike_price > spot_price:
                # Put is in-the-money
                moneyness = 'ITM'
                position = position_steps
                label = f'ITM {position}' if position > 0 else 'ATM'
            else:
                # Put is out-of-the-money
                moneyness = 'OTM'
                position = position_steps
                label = f'OTM {position}' if position > 0 else 'ATM'
        else:
            # Unknown option type
            moneyness = 'UNKNOWN'
            position = 0
            label = 'UNKNOWN'
        
        return {
            'moneyness': moneyness,
            'moneyness_position': position,
            'moneyness_label': label
        }
    
    async def get_fo_data_summary(self) -> Dict:
        """Get summary of F&O data that needs classification"""
        conn = await asyncpg.connect(**DB_CONFIG)
        
        try:
            # Get total records and date range
            summary = await conn.fetchrow('''
                SELECT 
                    COUNT(*) as total_records,
                    MIN(time) as earliest_time,
                    MAX(time) as latest_time,
                    COUNT(DISTINCT DATE(time)) as trading_days,
                    COUNT(CASE WHEN moneyness IS NULL THEN 1 END) as unclassified_records
                FROM nifty_fo_ohlc
            ''')
            
            return dict(summary)
            
        finally:
            await conn.close()
    
    async def classify_fo_data_batch(self, start_time: datetime, end_time: datetime) -> int:
        """
        Classify F&O data for a specific time period
        
        Returns:
            Number of records processed
        """
        conn = await asyncpg.connect(**DB_CONFIG)
        
        try:
            logger.info(f"Processing F&O data from {start_time} to {end_time}")
            
            # Get F&O data and corresponding spot prices for the time period
            fo_data = await conn.fetch('''
                SELECT 
                    fo.time,
                    fo.symbol,
                    fo.instrument_type,
                    fo.strike_price,
                    fo.option_type,
                    fo.instrument_token,
                    spot.close as spot_price
                FROM nifty_fo_ohlc fo
                JOIN nifty50_ohlc spot ON fo.time = spot.time
                WHERE fo.time >= $1 AND fo.time <= $2
                AND fo.moneyness IS NULL
                ORDER BY fo.time, fo.symbol
            ''', start_time, end_time)
            
            if not fo_data:
                logger.info("No unclassified F&O data found for this period")
                return 0
            
            logger.info(f"Found {len(fo_data)} F&O records to classify")
            
            # Process records and calculate moneyness
            update_records = []
            
            for record in fo_data:
                moneyness_info = self.calculate_moneyness(
                    strike_price=record['strike_price'],
                    spot_price=float(record['spot_price']),
                    option_type=record['option_type'],
                    instrument_type=record['instrument_type']
                )
                
                update_records.append((
                    moneyness_info['moneyness'],
                    moneyness_info['moneyness_position'],
                    moneyness_info['moneyness_label'],
                    float(record['spot_price']),
                    record['time'],
                    record['instrument_token']
                ))
            
            # Batch update the records
            if update_records:
                update_sql = '''
                    UPDATE nifty_fo_ohlc 
                    SET 
                        moneyness = $1,
                        moneyness_position = $2,
                        moneyness_label = $3,
                        spot_price = $4
                    WHERE time = $5 AND instrument_token = $6
                '''
                
                await conn.executemany(update_sql, update_records)
                
                logger.info(f"Successfully classified {len(update_records)} F&O records")
                return len(update_records)
            
            return 0
            
        finally:
            await conn.close()
    
    async def classify_all_fo_data(self, batch_hours: int = 6):
        """
        Classify all F&O data in batches
        
        Args:
            batch_hours: Process data in chunks of this many hours
        """
        
        logger.info("🚀 Starting F&O moneyness classification...")
        
        try:
            # Get data summary
            summary = await self.get_fo_data_summary()
            
            logger.info(f"📊 F&O Data Summary:")
            logger.info(f"   Total records: {summary['total_records']:,}")
            logger.info(f"   Date range: {summary['earliest_time']} to {summary['latest_time']}")
            logger.info(f"   Trading days: {summary['trading_days']}")
            logger.info(f"   Unclassified records: {summary['unclassified_records']:,}")
            
            if summary['unclassified_records'] == 0:
                logger.info("✅ All F&O data already classified!")
                return
            
            # Process data in time-based batches
            current_time = summary['earliest_time']
            end_time = summary['latest_time']
            batch_delta = timedelta(hours=batch_hours)
            
            total_processed = 0
            batch_count = 0
            
            while current_time < end_time:
                batch_end = min(current_time + batch_delta, end_time)
                batch_count += 1
                
                # Process this batch
                batch_processed = await self.classify_fo_data_batch(current_time, batch_end)
                total_processed += batch_processed
                
                # Progress update
                progress = ((current_time - summary['earliest_time']).total_seconds() / 
                          (end_time - summary['earliest_time']).total_seconds()) * 100
                
                logger.info(f"📈 Batch {batch_count} completed: {batch_processed:,} records | "
                          f"Progress: {progress:.1f}% | Total: {total_processed:,}")
                
                current_time = batch_end
                
                # Small delay to avoid overwhelming the database
                await asyncio.sleep(0.5)
            
            logger.info(f"🎉 Moneyness classification completed!")
            logger.info(f"   Total records classified: {total_processed:,}")
            
            # Generate classification summary
            await self.generate_classification_summary()
            
        except Exception as e:
            logger.error(f"❌ Error in classification: {e}")
            raise
    
    async def generate_classification_summary(self):
        """Generate summary statistics of the classification results"""
        
        conn = await asyncpg.connect(**DB_CONFIG)
        
        try:
            logger.info("📊 Generating classification summary...")
            
            # Overall moneyness distribution
            moneyness_dist = await conn.fetch('''
                SELECT 
                    moneyness,
                    COUNT(*) as record_count,
                    COUNT(DISTINCT symbol) as unique_symbols,
                    ROUND(AVG(oi), 0) as avg_oi
                FROM nifty_fo_ohlc 
                WHERE moneyness IS NOT NULL
                GROUP BY moneyness 
                ORDER BY record_count DESC
            ''')
            
            # Position distribution for options
            position_dist = await conn.fetch('''
                SELECT 
                    moneyness_label,
                    COUNT(*) as record_count,
                    ROUND(AVG(oi), 0) as avg_oi
                FROM nifty_fo_ohlc 
                WHERE moneyness IN ('ITM', 'OTM', 'ATM')
                AND moneyness_position <= 5
                GROUP BY moneyness_label 
                ORDER BY 
                    CASE WHEN moneyness_label = 'ATM' THEN 0
                         WHEN moneyness_label LIKE 'ITM%' THEN 1 
                         ELSE 2 END,
                    moneyness_position
            ''')
            
            # Recent day analysis
            recent_analysis = await conn.fetch('''
                SELECT 
                    DATE(time) as trade_date,
                    moneyness,
                    COUNT(*) as records,
                    ROUND(AVG(spot_price), 2) as avg_spot_price
                FROM nifty_fo_ohlc 
                WHERE time >= (SELECT MAX(time) - INTERVAL '3 days' FROM nifty_fo_ohlc)
                AND moneyness IS NOT NULL
                GROUP BY DATE(time), moneyness
                ORDER BY trade_date DESC, moneyness
            ''')
            
            print("\n🎯 MONEYNESS CLASSIFICATION SUMMARY")
            print("="*60)
            
            print("\n📈 Overall Moneyness Distribution:")
            for row in moneyness_dist:
                print(f"   {row['moneyness']:<8}: {row['record_count']:>8,} records | "
                      f"{row['unique_symbols']:>3} symbols | Avg OI: {row['avg_oi']:>10,}")
            
            print("\n🎲 Position Distribution (Top positions):")
            for row in position_dist[:15]:
                print(f"   {row['moneyness_label']:<8}: {row['record_count']:>8,} records | "
                      f"Avg OI: {row['avg_oi']:>10,}")
            
            print("\n📅 Recent Days Analysis:")
            for row in recent_analysis:
                print(f"   {row['trade_date']} {row['moneyness']:<8}: {row['records']:>6,} records | "
                      f"Avg Spot: ₹{row['avg_spot_price']:>8}")
            
            print("\n✅ Moneyness classification system is now operational!")
            print("🔍 Available for: ITM/OTM analysis, Greeks calculation, Strategy optimization")
            
        finally:
            await conn.close()

async def main():
    """Main execution function"""
    try:
        classifier = FOMoneynessClassifier()
        await classifier.classify_all_fo_data(batch_hours=6)
        
    except Exception as e:
        logger.error(f"❌ Error in main: {e}")

if __name__ == "__main__":
    asyncio.run(main())
