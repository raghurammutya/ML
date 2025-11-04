#!/usr/bin/env python3
"""
Enhanced Tick Monitor with REAL Indicators
Shows actual calculated indicators: OI buildup, PCR trends, Max Pain, Volume spikes
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
USER_SERVICE_URL = "http://localhost:8001"
USERNAME = "sdktest@example.com"
PASSWORD = "TestPass123!"

# Track historical data
history = {
    'oi': defaultdict(list),
    'volume': defaultdict(list),
    'pcr': [],
    'nifty': []
}

def get_backend_snapshot():
    """Get live data from backend"""
    try:
        response = requests.get(f"{API_URL}/monitor/snapshot", timeout=5)
        return response.json()
    except:
        return {}

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

def calculate_max_pain(options_data, spot_price):
    """Calculate Max Pain strike"""
    strikes = {}

    for opt in options_data.values():
        strike = opt.get('strike', 0)
        if strike == 0:
            continue

        if strike not in strikes:
            strikes[strike] = {'ce_oi': 0, 'pe_oi': 0}

        if opt.get('type') == 'CE':
            strikes[strike]['ce_oi'] += opt.get('oi', 0)
        elif opt.get('type') == 'PE':
            strikes[strike]['pe_oi'] += opt.get('oi', 0)

    # Calculate pain at each strike
    pain_by_strike = {}
    for test_strike in strikes.keys():
        total_pain = 0

        for strike, oi_data in strikes.items():
            # Call writers lose if spot > strike
            if test_strike > strike:
                total_pain += oi_data['ce_oi'] * (test_strike - strike)

            # Put writers lose if spot < strike
            if test_strike < strike:
                total_pain += oi_data['pe_oi'] * (strike - test_strike)

        pain_by_strike[test_strike] = total_pain

    if not pain_by_strike:
        return spot_price, 0

    max_pain_strike = min(pain_by_strike.items(), key=lambda x: x[1])
    return max_pain_strike[0], max_pain_strike[1]

def get_atm_strike(spot_price):
    """Get ATM strike (nearest 50 multiple)"""
    return round(spot_price / 50) * 50

def calculate_oi_change(symbol, current_oi):
    """Calculate OI change"""
    hist = history['oi'][symbol]
    if len(hist) < 2:
        return 0, 0

    change = current_oi - hist[-1]
    pct_change = (change / hist[-1] * 100) if hist[-1] > 0 else 0
    return change, pct_change

def calculate_volume_spike(symbol, current_vol):
    """Detect volume spikes"""
    hist = history['volume'][symbol]
    if len(hist) < 5:
        return False, 0

    avg_vol = sum(hist[-5:]) / 5
    if avg_vol == 0:
        return False, 0

    spike_ratio = current_vol / avg_vol
    return spike_ratio > 2.0, spike_ratio

def main():
    print("\n" + "="*80)
    print("StocksBlitz SDK - Monitor with REAL Indicators".center(80))
    print("="*80 + "\n")

    # Authenticate
    print("🔐 Authenticating...")
    client = TradingClient.from_credentials(
        api_url=API_URL,
        user_service_url=USER_SERVICE_URL,
        username=USERNAME,
        password=PASSWORD
    )
    print(f"✓ Authenticated as {USERNAME}\\n")

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

            if not underlying:
                print("⚠ No underlying data available")
                continue

            spot = underlying.get('close', 0)
            atm_strike = get_atm_strike(spot)

            # Calculate indicators
            pcr_data = calculate_pcr(options_data)
            max_pain_strike, _ = calculate_max_pain(options_data, spot)

            # Store history
            history['nifty'].append(spot)
            history['pcr'].append(pcr_data['pcr_oi'])

            # Keep last 20 data points
            if len(history['nifty']) > 20:
                history['nifty'].pop(0)
                history['pcr'].pop(0)

            print(f"\n{'═'*80}")
            print(f"Iteration {iteration} - {datetime.now().strftime('%H:%M:%S')}")
            print(f"{'═'*80}")

            # Show underlying with indicators
            print(f"\n📊 NIFTY 50 Index")
            print(f"{'─'*80}")
            ltp = underlying.get('close', 0)
            open_price = underlying.get('open', 0)
            high = underlying.get('high', 0)
            low = underlying.get('low', 0)
            vol = underlying.get('volume', 0)

            change = ltp - open_price
            change_pct = (change / open_price * 100) if open_price > 0 else 0

            # Price trend
            if len(history['nifty']) >= 5:
                trend = "↗️ UP" if history['nifty'][-1] > history['nifty'][-5] else "↘️ DOWN"
                momentum = ((history['nifty'][-1] - history['nifty'][-5]) / history['nifty'][-5] * 100)
            else:
                trend = "—"
                momentum = 0

            print(f"LTP: ₹{ltp:>10,.2f}  Change: {change:>+8,.2f} ({change_pct:>+6.2f}%)  Trend: {trend} ({momentum:+.2f}%)")
            print(f"O: {open_price:>8,.2f}  H: {high:>8,.2f}  L: {low:>8,.2f}  Vol: {vol:>6,}")
            print(f"ATM Strike: {atm_strike:,.0f}  Max Pain: {max_pain_strike:,.0f}")

            # Market Indicators
            print(f"\n📈 Market Indicators")
            print(f"{'─'*80}")

            # PCR with trend
            pcr_trend = "—"
            if len(history['pcr']) >= 5:
                if history['pcr'][-1] > history['pcr'][-5]:
                    pcr_trend = "↗️ Increasing (Bearish)"
                else:
                    pcr_trend = "↘️ Decreasing (Bullish)"

            print(f"PCR (OI):     {pcr_data['pcr_oi']:>6.3f}  {pcr_trend}")
            print(f"  → Calls OI: {pcr_data['call_oi']:>12,}  Puts OI: {pcr_data['put_oi']:>12,}")
            print(f"\nPCR (Volume): {pcr_data['pcr_vol']:>6.3f}")
            print(f"  → Calls Vol: {pcr_data['call_vol']:>11,}  Puts Vol: {pcr_data['put_vol']:>11,}")

            # Max Pain analysis
            distance_from_max_pain = spot - max_pain_strike
            if abs(distance_from_max_pain) < 50:
                pain_msg = "Near Max Pain (Neutral)"
            elif distance_from_max_pain > 0:
                pain_msg = f"Above Max Pain by {distance_from_max_pain:.0f} (Bullish pressure)"
            else:
                pain_msg = f"Below Max Pain by {abs(distance_from_max_pain):.0f} (Bearish pressure)"

            print(f"\nMax Pain: {max_pain_strike:,.0f}  ({pain_msg})")

            # ATM Options with OI analysis
            print(f"\n🎯 ATM Options (Strike: {atm_strike:,.0f}) - OI Analysis")
            print(f"{'─'*80}")
            print(f"{'Type':<6} {'LTP':>10} {'Volume':>10} {'OI':>12} {'OI Change':>12} {'Signal':<15}")
            print(f"{'─'*80}")

            atm_options = [opt for opt in options_data.values()
                          if opt.get('strike') == atm_strike and opt.get('type') in ['CE', 'PE']]

            for opt in sorted(atm_options, key=lambda x: x.get('type', ''), reverse=True):
                symbol = opt.get('tradingsymbol', '')
                opt_type = opt.get('type', '')
                price = opt.get('price', 0)
                volume = opt.get('volume', 0)
                oi = opt.get('oi', 0)

                # Track OI
                history['oi'][symbol].append(oi)
                if len(history['oi'][symbol]) > 20:
                    history['oi'][symbol].pop(0)

                oi_change, oi_pct = calculate_oi_change(symbol, oi)

                # Interpret signal
                if abs(oi_change) < 1000:
                    signal = "—"
                elif opt_type == 'CE':
                    signal = "🔴 Short Buildup" if oi_change > 0 and price < 0 else "🟢 Long Buildup"
                else:
                    signal = "🔴 Short Buildup" if oi_change > 0 and price < 0 else "🟢 Long Buildup"

                print(f"{opt_type:<6} ₹{price:>9,.2f} {volume:>10,} {oi:>12,} {oi_change:>+11,} {signal:<15}")

            # Options with highest OI buildup
            print(f"\n🔥 Top OI Buildup (Last iteration)")
            print(f"{'─'*80}")
            print(f"{'Symbol':<22} {'Type':<6} {'Strike':>8} {'OI Change':>12} {'Current OI':>12}")
            print(f"{'─'*80}")

            oi_changes = []
            for opt in options_data.values():
                symbol = opt.get('tradingsymbol', '')
                oi = opt.get('oi', 0)

                history['oi'][symbol].append(oi)
                if len(history['oi'][symbol]) > 20:
                    history['oi'][symbol].pop(0)

                oi_change, _ = calculate_oi_change(symbol, oi)

                if abs(oi_change) > 0:
                    oi_changes.append({
                        'symbol': symbol,
                        'type': opt.get('type', ''),
                        'strike': opt.get('strike', 0),
                        'oi_change': oi_change,
                        'oi': oi
                    })

            # Show top 5 by absolute OI change
            oi_changes.sort(key=lambda x: abs(x['oi_change']), reverse=True)
            for item in oi_changes[:5]:
                print(f"{item['symbol']:<22} {item['type']:<6} {item['strike']:>8,.0f} {item['oi_change']:>+11,} {item['oi']:>12,}")

            # Volume spikes
            print(f"\n⚡ Volume Spikes (>2x average)")
            print(f"{'─'*80}")

            spikes = []
            for opt in options_data.values():
                symbol = opt.get('tradingsymbol', '')
                volume = opt.get('volume', 0)

                history['volume'][symbol].append(volume)
                if len(history['volume'][symbol]) > 20:
                    history['volume'][symbol].pop(0)

                is_spike, ratio = calculate_volume_spike(symbol, volume)

                if is_spike:
                    spikes.append({
                        'symbol': symbol,
                        'type': opt.get('type', ''),
                        'strike': opt.get('strike', 0),
                        'volume': volume,
                        'ratio': ratio
                    })

            if spikes:
                print(f"{'Symbol':<22} {'Type':<6} {'Strike':>8} {'Volume':>12} {'Spike':>8}")
                print(f"{'─'*80}")
                spikes.sort(key=lambda x: x['ratio'], reverse=True)
                for item in spikes[:5]:
                    print(f"{item['symbol']:<22} {item['type']:<6} {item['strike']:>8,.0f} {item['volume']:>12,} {item['ratio']:>7.1f}x")
            else:
                print("No significant volume spikes detected")

            print(f"\n{'─'*80}")
            print(f"Refreshing in 5 seconds...")

    except KeyboardInterrupt:
        print(f"\n\n{'='*80}")
        print("Monitor stopped by user".center(80))
        print(f"{'='*80}\n")

if __name__ == "__main__":
    main()
