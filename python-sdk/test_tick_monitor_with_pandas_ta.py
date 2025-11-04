#!/usr/bin/env python3
"""
Enhanced Tick Monitor with pandas_ta Technical Indicators
Shows RSI, MACD, Bollinger Bands, ATR, and other technical indicators
"""

import sys
sys.path.insert(0, '/mnt/stocksblitz-data/Quantagro/tradingview-viz/python-sdk')

import time
import requests
from datetime import datetime
from collections import defaultdict

from stocksblitz import TradingClient

# Config
API_URL = "http://localhost:8081"
INDICATOR_URL = "http://localhost:8081"  # Indicators are on the backend service
USER_SERVICE_URL = "http://localhost:8001"
USERNAME = "sdktest@example.com"
PASSWORD = "TestPass123!"

def get_backend_snapshot():
    """Get live data from backend"""
    try:
        response = requests.get(f"{API_URL}/monitor/snapshot", timeout=5)
        return response.json()
    except:
        return {}

def subscribe_indicators(access_token, symbol, timeframe):
    """Subscribe to technical indicators"""
    try:
        response = requests.post(
            f"{INDICATOR_URL}/indicators/subscribe",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            },
            json={
                "symbol": symbol,
                "timeframe": timeframe,
                "indicators": [
                    {"name": "RSI", "params": {"length": 14}},
                    {"name": "MACD", "params": {"fast": 12, "slow": 26, "signal": 9}},
                    {"name": "BBANDS", "params": {"length": 20, "std": 2}},
                    {"name": "ATR", "params": {"length": 14}},
                    {"name": "SMA", "params": {"length": 20}},
                    {"name": "SMA", "params": {"length": 50}},
                    {"name": "EMA", "params": {"length": 12}},
                    {"name": "EMA", "params": {"length": 26}},
                    {"name": "ADX", "params": {"length": 14}},
                    {"name": "OBV", "params": {}}
                ]
            },
            timeout=10
        )
        return response.json()
    except Exception as e:
        print(f"Error subscribing to indicators: {e}")
        return None

def get_indicators(access_token, symbol, timeframe):
    """Get current indicator values"""
    indicators = "RSI_14,MACD_12_26_9,BBANDS_20_2,ATR_14,SMA_20,SMA_50,EMA_12,EMA_26,ADX_14,OBV"
    try:
        response = requests.get(
            f"{INDICATOR_URL}/indicators/current",
            headers={"Authorization": f"Bearer {access_token}"},
            params={
                "symbol": symbol,
                "timeframe": timeframe,
                "indicators": indicators
            },
            timeout=5
        )
        if response.status_code == 200:
            return response.json()
        else:
            return None
    except Exception as e:
        return None

def calculate_pcr(options_data):
    """Calculate Put-Call Ratio by OI and Volume"""
    put_oi = 0
    call_oi = 0
    put_vol = 0
    call_vol = 0

    for opt in options_data.values():
        if opt.get('type') == 'PE':
            put_oi += opt.get('oi', 0)
            put_vol += opt.get('volume', 0)
        elif opt.get('type') == 'CE':
            call_oi += opt.get('oi', 0)
            call_vol += opt.get('volume', 0)

    pcr_oi = (put_oi / call_oi) if call_oi > 0 else 0
    pcr_vol = (put_vol / call_vol) if call_vol > 0 else 0

    return {
        'pcr_oi': pcr_oi,
        'pcr_vol': pcr_vol,
        'put_oi': put_oi,
        'call_oi': call_oi,
        'put_vol': put_vol,
        'call_vol': call_vol
    }

def get_atm_strike(spot_price):
    """Get ATM strike (nearest 50 multiple)"""
    return round(spot_price / 50) * 50

def interpret_rsi(rsi):
    """Interpret RSI value"""
    if rsi >= 70:
        return "🔴 Overbought"
    elif rsi <= 30:
        return "🟢 Oversold"
    elif rsi > 50:
        return "↗️ Bullish"
    else:
        return "↘️ Bearish"

def interpret_macd(macd_value, macd_signal):
    """Interpret MACD"""
    if macd_value > macd_signal:
        return "🟢 Bullish Cross"
    else:
        return "🔴 Bearish Cross"

def interpret_bb_position(price, bb_lower, bb_middle, bb_upper):
    """Interpret Bollinger Bands position"""
    if price >= bb_upper:
        return "🔴 Above Upper Band"
    elif price <= bb_lower:
        return "🟢 Below Lower Band"
    elif price > bb_middle:
        return "↗️ Above Middle"
    else:
        return "↘️ Below Middle"

def main():
    print("\n" + "="*80)
    print("StocksBlitz SDK - Monitor with pandas_ta Indicators".center(80))
    print("="*80 + "\n")

    # Authenticate
    print("🔐 Authenticating...")
    client = TradingClient.from_credentials(
        api_url=API_URL,
        user_service_url=USER_SERVICE_URL,
        username=USERNAME,
        password=PASSWORD
    )
    # Get JWT access token (stored in internal API client)
    access_token = client._api._access_token
    print(f"✓ Authenticated as {USERNAME}\n")

    # Subscribe to indicators
    print("📊 Subscribing to technical indicators...")
    sub_result = subscribe_indicators(access_token, "NIFTY50", "5min")
    if sub_result:
        print(f"✓ Subscribed to indicators: {sub_result.get('status', 'unknown')}\n")
    else:
        print("⚠️  Could not subscribe to indicators (continuing anyway)\n")

    print("="*80)
    print("Starting live monitor (Press Ctrl+C to stop)".center(80))
    print("="*80 + "\n")

    iteration = 0
    try:
        while True:
            iteration += 1
            time.sleep(5)

            # Get fresh snapshot
            snapshot = get_backend_snapshot()
            underlying = snapshot.get('underlying')
            options_data = snapshot.get('options', {})

            # Get technical indicators
            indicators = get_indicators(access_token, "NIFTY50", "5")

            if not underlying:
                print("⚠ No underlying data available")
                continue

            spot = underlying.get('close', 0)
            atm_strike = get_atm_strike(spot)

            # Calculate PCR
            pcr_data = calculate_pcr(options_data)

            print(f"\n{'═'*80}")
            print(f"Iteration {iteration} - {datetime.now().strftime('%H:%M:%S')}")
            print(f"{'═'*80}")

            # Show underlying
            print(f"\n📊 NIFTY 50 Index")
            print(f"{'─'*80}")
            ltp = underlying.get('close', 0)
            open_price = underlying.get('open', 0)
            high = underlying.get('high', 0)
            low = underlying.get('low', 0)
            vol = underlying.get('volume', 0)

            change = ltp - open_price
            change_pct = (change / open_price * 100) if open_price > 0 else 0

            print(f"LTP: ₹{ltp:>10,.2f}  Change: {change:>+8,.2f} ({change_pct:>+6.2f}%)")
            print(f"O: {open_price:>8,.2f}  H: {high:>8,.2f}  L: {low:>8,.2f}  Vol: {vol:>6,}")
            print(f"ATM Strike: {atm_strike:,.0f}")

            # Show Technical Indicators
            if indicators and indicators.get('status') == 'success':
                ind_data = indicators.get('indicators', {})

                print(f"\n📈 Technical Indicators (5min timeframe)")
                print(f"{'─'*80}")

                # RSI
                rsi = ind_data.get('RSI_14')
                if rsi:
                    rsi_signal = interpret_rsi(rsi)
                    print(f"RSI(14):        {rsi:>7.2f}  {rsi_signal}")

                # MACD
                macd = ind_data.get('MACD_12_26_9', {})
                if isinstance(macd, dict):
                    macd_line = macd.get('MACD', 0)
                    macd_signal = macd.get('MACDs', 0)
                    macd_hist = macd.get('MACDh', 0)
                    macd_interp = interpret_macd(macd_line, macd_signal)
                    print(f"MACD:           {macd_line:>7.2f}  Signal: {macd_signal:>7.2f}  Hist: {macd_hist:>+7.2f}  {macd_interp}")

                # Bollinger Bands
                bbands = ind_data.get('BBANDS_20_2', {})
                if isinstance(bbands, dict):
                    bb_lower = bbands.get('BBL_20_2.0', 0)
                    bb_middle = bbands.get('BBM_20_2.0', 0)
                    bb_upper = bbands.get('BBU_20_2.0', 0)
                    bb_width = bbands.get('BBB_20_2.0', 0)

                    if bb_middle > 0:
                        bb_signal = interpret_bb_position(ltp, bb_lower, bb_middle, bb_upper)
                        print(f"BB(20,2):       Lower: {bb_lower:>8,.2f}  Mid: {bb_middle:>8,.2f}  Upper: {bb_upper:>8,.2f}")
                        print(f"                Width: {bb_width:>7.4f}  {bb_signal}")

                # ATR (Volatility)
                atr = ind_data.get('ATR_14')
                if atr:
                    atr_pct = (atr / ltp * 100) if ltp > 0 else 0
                    volatility = "High" if atr_pct > 2 else "Medium" if atr_pct > 1 else "Low"
                    print(f"ATR(14):        {atr:>7.2f}  ({atr_pct:.2f}% of price) - {volatility} Volatility")

                # Moving Averages
                sma20 = ind_data.get('SMA_20')
                sma50 = ind_data.get('SMA_50')
                ema12 = ind_data.get('EMA_12')
                ema26 = ind_data.get('EMA_26')

                if sma20 and sma50:
                    ma_trend = "🟢 Bullish" if sma20 > sma50 else "🔴 Bearish"
                    print(f"SMA(20):        {sma20:>8,.2f}  SMA(50): {sma50:>8,.2f}  {ma_trend}")

                if ema12 and ema26:
                    ema_trend = "🟢 Bullish" if ema12 > ema26 else "🔴 Bearish"
                    print(f"EMA(12):        {ema12:>8,.2f}  EMA(26): {ema26:>8,.2f}  {ema_trend}")

                # Price vs MA
                if sma20:
                    price_vs_ma = ((ltp - sma20) / sma20 * 100) if sma20 > 0 else 0
                    position = "Above" if price_vs_ma > 0 else "Below"
                    print(f"Price vs SMA20: {position} by {abs(price_vs_ma):.2f}%")

                # ADX (Trend Strength)
                adx = ind_data.get('ADX_14')
                if adx:
                    strength = "Strong" if adx > 25 else "Weak" if adx < 20 else "Moderate"
                    print(f"ADX(14):        {adx:>7.2f}  Trend Strength: {strength}")

                # OBV (Volume)
                obv = ind_data.get('OBV')
                if obv:
                    print(f"OBV:            {obv:>12,.0f}")

            else:
                print(f"\n⚠️  Technical indicators not available")
                if indicators:
                    print(f"Status: {indicators.get('status', 'unknown')}")

            # Market Indicators (PCR, OI)
            print(f"\n📊 Options Market Indicators")
            print(f"{'─'*80}")
            print(f"PCR (OI):       {pcr_data['pcr_oi']:>6.3f}  (Calls: {pcr_data['call_oi']:>12,}, Puts: {pcr_data['put_oi']:>12,})")
            print(f"PCR (Volume):   {pcr_data['pcr_vol']:>6.3f}  (Calls: {pcr_data['call_vol']:>12,}, Puts: {pcr_data['put_vol']:>12,})")

            # ATM Options
            print(f"\n🎯 ATM Options (Strike: {atm_strike:,.0f})")
            print(f"{'─'*80}")
            print(f"{'Type':<6} {'LTP':>10} {'Volume':>10} {'OI':>12}")
            print(f"{'─'*80}")

            atm_options = [opt for opt in options_data.values()
                          if opt.get('strike') == atm_strike and opt.get('type') in ['CE', 'PE']]

            for opt in sorted(atm_options, key=lambda x: x.get('type', ''), reverse=True)[:5]:
                opt_type = opt.get('type', '')
                price = opt.get('price', 0)
                volume = opt.get('volume', 0)
                oi = opt.get('oi', 0)

                print(f"{opt_type:<6} ₹{price:>9,.2f} {volume:>10,} {oi:>12,}")

            # Top movers by volume
            print(f"\n🔥 Top 5 Options by Volume")
            print(f"{'─'*80}")
            print(f"{'Symbol':<22} {'Type':<6} {'Strike':>8} {'LTP':>10} {'Volume':>10}")
            print(f"{'─'*80}")

            top_by_volume = sorted(options_data.values(),
                                  key=lambda x: x.get('volume', 0), reverse=True)[:5]

            for opt in top_by_volume:
                symbol = opt.get('tradingsymbol', '')[:22]
                opt_type = opt.get('type', '')
                strike = opt.get('strike', 0)
                price = opt.get('price', 0)
                volume = opt.get('volume', 0)

                print(f"{symbol:<22} {opt_type:<6} {strike:>8,.0f} ₹{price:>9,.2f} {volume:>10,}")

            print(f"\n{'─'*80}")
            print(f"Refreshing in 5 seconds...")

    except KeyboardInterrupt:
        print(f"\n\n{'='*80}")
        print("Monitor stopped by user".center(80))
        print(f"{'='*80}\n")

if __name__ == "__main__":
    main()
