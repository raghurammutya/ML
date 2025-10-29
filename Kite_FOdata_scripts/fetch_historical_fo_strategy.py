#!/usr/bin/env python3
"""
Historical F&O Data Strategy
Adapts to API limitations and provides historical F&O analysis capabilities
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta, date
from typing import Dict, List, Optional, Tuple
import asyncio
import asyncpg

# Add backend directory to path
backend_dir = Path(__file__).parent / "backend"
sys.path.append(str(backend_dir))

from dotenv import load_dotenv
load_dotenv(backend_dir / ".env")

from config import DB_CONFIG
from kite_accounts import get_kite_service

class HistoricalFOStrategy:
    
    def __init__(self):
        self.kite_service = get_kite_service()
        self.kite = self.kite_service.kite
        
        # API data availability periods (discovered through testing)
        self.api_limits = {
            'futures': timedelta(days=30),    # Last ~30 days
            'options': timedelta(days=30),    # Last ~30 days  
            'reliable_period': timedelta(days=7)  # Most reliable data
        }
        
    async def get_historical_nifty_price(self, target_date: datetime) -> Optional[float]:
        """Get historical Nifty price for ATM calculation"""
        
        conn = await asyncpg.connect(**DB_CONFIG)
        
        # Get price closest to target date
        price_data = await conn.fetchrow('''
            SELECT close 
            FROM nifty50_ohlc 
            WHERE time <= $1
            ORDER BY time DESC 
            LIMIT 1
        ''', target_date)
        
        await conn.close()
        return float(price_data['close']) if price_data else None
    
    def calculate_historical_strikes(self, spot_price: float, target_date: datetime) -> Dict:
        """Calculate what strikes would have been relevant for historical date"""
        
        # ATM calculation
        atm_strike = round(spot_price / 50) * 50
        
        # Strike range (±10 strikes)
        strike_range = []
        for i in range(-10, 11):
            strike = atm_strike + (i * 50)
            strike_range.append(strike)
        
        return {
            'atm_strike': atm_strike,
            'strike_range': strike_range,
            'spot_price': spot_price,
            'target_date': target_date
        }
    
    def estimate_historical_expiries(self, target_date: datetime) -> List[date]:
        """Estimate what expiries would have been available on target date"""
        
        # Nifty F&O expiries are typically last Thursday of each month
        # Plus weekly expiries in current month
        
        def get_last_thursday(year: int, month: int) -> date:
            """Get last Thursday of given month"""
            # Start from last day of month and work backwards
            if month == 12:
                last_day = date(year + 1, 1, 1) - timedelta(days=1)
            else:
                last_day = date(year, month + 1, 1) - timedelta(days=1)
            
            # Find last Thursday (weekday 3)
            while last_day.weekday() != 3:  # Thursday = 3
                last_day -= timedelta(days=1)
            
            return last_day
        
        expiries = []
        target_date_obj = target_date.date()
        
        # Get expiries for next 3-4 months from target date
        for month_offset in range(4):
            year = target_date_obj.year
            month = target_date_obj.month + month_offset
            
            # Handle year rollover
            while month > 12:
                month -= 12
                year += 1
            
            expiry = get_last_thursday(year, month)
            if expiry > target_date_obj:  # Only future expiries
                expiries.append(expiry)
        
        return sorted(expiries)
    
    def generate_historical_fo_symbols(self, strikes_info: Dict, expiries: List[date]) -> List[Dict]:
        """Generate what F&O symbols would have existed for historical date"""
        
        target_year = strikes_info['target_date'].year
        symbols = []
        
        # Generate futures for each expiry
        for expiry in expiries:
            month_abbr = expiry.strftime('%b').upper()
            year_suffix = str(expiry.year)[-2:]
            
            # Historical symbol format (estimated)
            fut_symbol = f"NIFTY{year_suffix}{month_abbr}FUT"
            
            symbols.append({
                'symbol': fut_symbol,
                'instrument_type': 'FUT',
                'expiry_date': expiry,
                'strike_price': None,
                'option_type': None,
                'estimated': True  # Flag to indicate this is estimated
            })
        
        # Generate options for each strike and expiry
        for expiry in expiries:
            month_abbr = expiry.strftime('%b').upper()
            year_suffix = str(expiry.year)[-2:]
            
            for strike in strikes_info['strike_range']:
                for option_type in ['CE', 'PE']:
                    # Historical symbol format (estimated)
                    opt_symbol = f"NIFTY{year_suffix}{month_abbr}{int(strike)}{option_type}"
                    
                    symbols.append({
                        'symbol': opt_symbol,
                        'instrument_type': 'OPT',
                        'expiry_date': expiry,
                        'strike_price': strike,
                        'option_type': option_type,
                        'estimated': True
                    })
        
        return symbols
    
    def assess_data_availability(self, target_date: datetime) -> Dict:
        """Assess what data can actually be fetched for target date"""
        
        current_date = datetime.now()
        time_diff = current_date - target_date
        
        # Determine data availability
        if time_diff <= self.api_limits['reliable_period']:
            availability = 'high'
            confidence = 0.9
            method = 'direct_api'
        elif time_diff <= self.api_limits['futures']:
            availability = 'medium' 
            confidence = 0.6
            method = 'limited_api'
        else:
            availability = 'low'
            confidence = 0.2
            method = 'estimation_only'
        
        return {
            'availability': availability,
            'confidence': confidence,
            'method': method,
            'time_diff_days': time_diff.days,
            'recommended_action': self._get_recommendation(availability)
        }
    
    def _get_recommendation(self, availability: str) -> str:
        """Get recommendation based on data availability"""
        
        recommendations = {
            'high': 'Fetch real F&O data via API',
            'medium': 'Fetch available data, supplement with estimates',
            'low': 'Use Nifty spot price + theoretical F&O modeling'
        }
        
        return recommendations.get(availability, 'Unknown')
    
    async def create_historical_fo_analysis(self, target_date: datetime) -> Dict:
        """Create comprehensive historical F&O analysis for target date"""
        
        print(f"🔍 Creating historical F&O analysis for {target_date.strftime('%Y-%m-%d')}")
        
        # Get historical Nifty price
        spot_price = await self.get_historical_nifty_price(target_date)
        if not spot_price:
            return {'error': 'No historical Nifty data available for target date'}
        
        # Calculate strikes
        strikes_info = self.calculate_historical_strikes(spot_price, target_date)
        
        # Estimate expiries
        expiries = self.estimate_historical_expiries(target_date)
        
        # Generate symbols
        estimated_symbols = self.generate_historical_fo_symbols(strikes_info, expiries)
        
        # Assess data availability
        availability = self.assess_data_availability(target_date)
        
        return {
            'target_date': target_date,
            'nifty_spot_price': spot_price,
            'atm_strike': strikes_info['atm_strike'],
            'strike_range': strikes_info['strike_range'],
            'estimated_expiries': expiries,
            'estimated_symbols_count': len(estimated_symbols),
            'futures_count': len([s for s in estimated_symbols if s['instrument_type'] == 'FUT']),
            'options_count': len([s for s in estimated_symbols if s['instrument_type'] == 'OPT']),
            'data_availability': availability,
            'estimated_symbols': estimated_symbols[:20]  # Show first 20 as sample
        }

async def test_historical_analysis():
    """Test the historical F&O analysis for different dates"""
    
    strategy = HistoricalFOStrategy()
    
    test_dates = [
        datetime(2016, 1, 1, 9, 15, 0),   # Very old - Jan 2016
        datetime(2020, 3, 15, 9, 15, 0),  # COVID crash period
        datetime(2024, 1, 1, 9, 15, 0),   # Recent but not current
        datetime.now() - timedelta(days=7)  # Last week - should have real data
    ]
    
    for test_date in test_dates:
        print(f"\n{'='*60}")
        print(f"📊 HISTORICAL F&O ANALYSIS: {test_date.strftime('%Y-%m-%d')}")
        print('='*60)
        
        analysis = await strategy.create_historical_fo_analysis(test_date)
        
        if 'error' in analysis:
            print(f"❌ {analysis['error']}")
            continue
        
        print(f"💰 Nifty Spot Price: ₹{analysis['nifty_spot_price']:,.2f}")
        print(f"🎯 ATM Strike: ₹{analysis['atm_strike']:,.0f}")
        print(f"📊 Strike Range: ₹{analysis['strike_range'][0]:,.0f} to ₹{analysis['strike_range'][-1]:,.0f}")
        print(f"📅 Estimated Expiries: {len(analysis['estimated_expiries'])} expiries")
        print(f"📈 Estimated Instruments: {analysis['estimated_symbols_count']} total")
        print(f"   • Futures: {analysis['futures_count']}")
        print(f"   • Options: {analysis['options_count']}")
        
        availability = analysis['data_availability']
        print(f"\n🔍 Data Availability: {availability['availability'].upper()}")
        print(f"   • Confidence: {availability['confidence']*100:.0f}%")
        print(f"   • Method: {availability['method']}")
        print(f"   • Recommendation: {availability['recommended_action']}")
        
        print(f"\n📋 Sample Estimated Symbols:")
        for symbol in analysis['estimated_symbols'][:10]:
            if symbol['instrument_type'] == 'FUT':
                print(f"   • {symbol['symbol']} (Futures)")
            else:
                print(f"   • {symbol['symbol']} (₹{symbol['strike_price']} {symbol['option_type']})")

if __name__ == "__main__":
    asyncio.run(test_historical_analysis())
