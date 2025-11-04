#!/usr/bin/env python3
"""
Enhanced Tick Monitor - StocksBlitz SDK Complete Testing

Features:
- Authentication (JWT with raghurammutya@gmail.com)
- Instrument discovery with moneyness types
- Real-time tick data (options, underlying, futures)
- All Greeks (delta, gamma, theta, vega, IV)
- OI data and OI change tracking
- Multiple technical indicators (RSI, SMA, EMA, MACD, BB, ATR, ADX)
- Option chain heatmap visualization
- CSV export functionality
"""

import sys
sys.path.insert(0, '/mnt/stocksblitz-data/Quantagro/tradingview-viz/python-sdk')

import time
import csv
from datetime import datetime
from typing import Dict, List, Optional, Any
from collections import defaultdict
from pathlib import Path

from stocksblitz import TradingClient, AuthenticationError, InstrumentNotFoundError
from stocksblitz.enums import DataState


# ==============================================================================
# Configuration
# ==============================================================================

API_URL = "http://localhost:8081"
USER_SERVICE_URL = "http://localhost:8001"
USERNAME = "sdktest@example.com"
PASSWORD = "TestPass123!"  # Test user created for SDK testing

# Export settings
EXPORT_DIR = Path("/tmp/stocksblitz_exports")
EXPORT_DIR.mkdir(exist_ok=True)


# ==============================================================================
# ANSI Color Codes for Terminal Output
# ==============================================================================

class Colors:
    """ANSI color codes for terminal output"""
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    CYAN = '\033[36m'
    YELLOW = '\033[33m'
    MAGENTA = '\033[35m'
    WHITE = '\033[37m'
    GREY = '\033[90m'
    BG_RED = '\033[41m'
    BG_GREEN = '\033[42m'
    BG_YELLOW = '\033[43m'


def print_header(text: str):
    """Print formatted header"""
    print(f"\n{Colors.BOLD}{Colors.HEADER}{'=' * 100}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.HEADER}{text.center(100)}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.HEADER}{'=' * 100}{Colors.ENDC}\n")


def print_section(text: str):
    """Print formatted section"""
    print(f"\n{Colors.BOLD}{Colors.OKBLUE}{'─' * 100}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.OKBLUE}{text}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.OKBLUE}{'─' * 100}{Colors.ENDC}")


def print_success(text: str):
    """Print success message"""
    print(f"{Colors.OKGREEN}✓ {text}{Colors.ENDC}")


def print_error(text: str):
    """Print error message"""
    print(f"{Colors.FAIL}✗ {text}{Colors.ENDC}")


def print_warning(text: str):
    """Print warning message"""
    print(f"{Colors.WARNING}⚠ {text}{Colors.ENDC}")


def print_info(text: str):
    """Print info message"""
    print(f"{Colors.OKCYAN}ℹ {text}{Colors.ENDC}")


# ==============================================================================
# Data Storage for Export
# ==============================================================================

class DataExporter:
    """Collect and export data to CSV"""

    def __init__(self, export_dir: Path):
        self.export_dir = export_dir
        self.underlying_data: List[Dict] = []
        self.options_data: List[Dict] = []
        self.futures_data: List[Dict] = []
        self.greeks_data: List[Dict] = []
        self.indicators_data: List[Dict] = []

    def add_underlying_tick(self, timestamp: datetime, symbol: str, data: Dict):
        """Add underlying tick data"""
        self.underlying_data.append({
            'timestamp': timestamp,
            'symbol': symbol,
            **data
        })

    def add_option_tick(self, timestamp: datetime, symbol: str, data: Dict):
        """Add option tick data"""
        self.options_data.append({
            'timestamp': timestamp,
            'symbol': symbol,
            **data
        })

    def add_futures_tick(self, timestamp: datetime, symbol: str, data: Dict):
        """Add futures tick data"""
        self.futures_data.append({
            'timestamp': timestamp,
            'symbol': symbol,
            **data
        })

    def add_greeks(self, timestamp: datetime, symbol: str, greeks: Dict):
        """Add Greeks data"""
        self.greeks_data.append({
            'timestamp': timestamp,
            'symbol': symbol,
            **greeks
        })

    def add_indicators(self, timestamp: datetime, symbol: str, timeframe: str, indicators: Dict):
        """Add technical indicators data"""
        self.indicators_data.append({
            'timestamp': timestamp,
            'symbol': symbol,
            'timeframe': timeframe,
            **indicators
        })

    def export_all(self, session_id: str):
        """Export all collected data to CSV files"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        # Export underlying data
        if self.underlying_data:
            filepath = self.export_dir / f"underlying_{session_id}_{timestamp}.csv"
            self._export_to_csv(filepath, self.underlying_data)
            print_success(f"Exported underlying data: {filepath}")

        # Export options data
        if self.options_data:
            filepath = self.export_dir / f"options_{session_id}_{timestamp}.csv"
            self._export_to_csv(filepath, self.options_data)
            print_success(f"Exported options data: {filepath}")

        # Export futures data
        if self.futures_data:
            filepath = self.export_dir / f"futures_{session_id}_{timestamp}.csv"
            self._export_to_csv(filepath, self.futures_data)
            print_success(f"Exported futures data: {filepath}")

        # Export Greeks data
        if self.greeks_data:
            filepath = self.export_dir / f"greeks_{session_id}_{timestamp}.csv"
            self._export_to_csv(filepath, self.greeks_data)
            print_success(f"Exported Greeks data: {filepath}")

        # Export indicators data
        if self.indicators_data:
            filepath = self.export_dir / f"indicators_{session_id}_{timestamp}.csv"
            self._export_to_csv(filepath, self.indicators_data)
            print_success(f"Exported indicators data: {filepath}")

    def _export_to_csv(self, filepath: Path, data: List[Dict]):
        """Export data to CSV file"""
        if not data:
            return

        with open(filepath, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=data[0].keys())
            writer.writeheader()
            writer.writerows(data)


# ==============================================================================
# OI Change Tracker
# ==============================================================================

class OITracker:
    """Track OI changes over time"""

    def __init__(self):
        self.oi_history: Dict[str, List[tuple]] = defaultdict(list)
        self.max_history = 20

    def update(self, symbol: str, oi: int, timestamp: datetime):
        """Update OI for a symbol"""
        history = self.oi_history[symbol]
        history.append((timestamp, oi))

        if len(history) > self.max_history:
            history.pop(0)

    def get_change(self, symbol: str) -> Optional[int]:
        """Get OI change from first to last"""
        history = self.oi_history.get(symbol, [])
        if len(history) < 2:
            return None
        return history[-1][1] - history[0][1]

    def get_percentage_change(self, symbol: str) -> Optional[float]:
        """Get OI percentage change"""
        history = self.oi_history.get(symbol, [])
        if len(history) < 2:
            return None

        first_oi = history[0][1]
        last_oi = history[-1][1]
        if first_oi == 0:
            return None
        return ((last_oi - first_oi) / first_oi) * 100


# ==============================================================================
# Moneyness Calculator
# ==============================================================================

def calculate_moneyness(strike: float, spot: float, option_type: str) -> tuple:
    """Calculate moneyness label and distance from ATM"""
    diff = strike - spot

    if option_type.upper() in ("CE", "CALL"):
        if abs(diff) < 50:
            return ("ATM", 0)
        elif diff < 0:
            steps = int(abs(diff) / 50)
            return (f"ITM{steps}", abs(diff))
        else:
            steps = int(diff / 50)
            return (f"OTM{steps}", diff)
    else:
        if abs(diff) < 50:
            return ("ATM", 0)
        elif diff > 0:
            steps = int(diff / 50)
            return (f"ITM{steps}", diff)
        else:
            steps = int(abs(diff) / 50)
            return (f"OTM{steps}", abs(diff))


def extract_option_info(symbol: str) -> Optional[Dict]:
    """Extract option information from symbol"""
    import re
    pattern = r'^(NIFTY|BANKNIFTY|FINNIFTY)(\d{2}[A-Z]\d{2})(\d+)(CE|PE)$'
    match = re.match(pattern, symbol)
    if not match:
        return None
    return {
        'underlying': match.group(1),
        'expiry_code': match.group(2),
        'strike': float(match.group(3)),
        'option_type': match.group(4)
    }


def extract_futures_info(symbol: str) -> Optional[Dict]:
    """Extract futures information from symbol"""
    import re
    # Pattern: NIFTY25OCTFUT
    pattern = r'^(NIFTY|BANKNIFTY|FINNIFTY)(\d{2}[A-Z]{3})FUT$'
    match = re.match(pattern, symbol)
    if not match:
        return None
    return {
        'underlying': match.group(1),
        'expiry_code': match.group(2)
    }


# ==============================================================================
# Technical Indicators Display
# ==============================================================================

def get_all_indicators(inst, timeframe: str = '5m') -> Dict:
    """Get all available technical indicators for an instrument"""
    indicators = {}

    try:
        tf = inst[timeframe]

        # Trend indicators
        try:
            indicators['rsi_14'] = tf.rsi[14]
        except:
            pass

        try:
            indicators['sma_20'] = tf.sma[20]
        except:
            pass

        try:
            indicators['sma_50'] = tf.sma[50]
        except:
            pass

        try:
            indicators['ema_12'] = tf.ema[12]
        except:
            pass

        try:
            indicators['ema_26'] = tf.ema[26]
        except:
            pass

        # MACD
        try:
            macd = tf.macd[12, 26, 9]
            if isinstance(macd, dict):
                indicators['macd'] = macd.get('macd', 0)
                indicators['macd_signal'] = macd.get('signal', 0)
                indicators['macd_histogram'] = macd.get('histogram', 0)
        except:
            pass

        # Bollinger Bands
        try:
            bb = tf.bb[20, 2]
            if isinstance(bb, dict):
                indicators['bb_upper'] = bb.get('upper', 0)
                indicators['bb_middle'] = bb.get('middle', 0)
                indicators['bb_lower'] = bb.get('lower', 0)
        except:
            pass

        # Volatility indicators
        try:
            indicators['atr_14'] = tf.atr[14]
        except:
            pass

        # Trend strength
        try:
            indicators['adx_14'] = tf.adx[14]
        except:
            pass

    except Exception as e:
        pass

    return indicators


def display_indicators(indicators: Dict):
    """Display technical indicators in formatted way"""
    if not indicators:
        return

    print(f"  {Colors.CYAN}Indicators (5m):{Colors.ENDC}")

    # Oscillators
    if 'rsi_14' in indicators:
        rsi = indicators['rsi_14']
        rsi_color = Colors.FAIL if rsi > 70 else (Colors.OKGREEN if rsi < 30 else Colors.GREY)
        print(f"    RSI(14): {rsi_color}{rsi:.2f}{Colors.ENDC}", end="  ")

    # Moving Averages
    if 'sma_20' in indicators:
        print(f"SMA(20): {Colors.GREY}{indicators['sma_20']:.2f}{Colors.ENDC}", end="  ")
    if 'ema_12' in indicators:
        print(f"EMA(12): {Colors.GREY}{indicators['ema_12']:.2f}{Colors.ENDC}", end="  ")

    print()  # New line

    # MACD
    if 'macd' in indicators:
        macd_color = Colors.OKGREEN if indicators.get('macd_histogram', 0) > 0 else Colors.FAIL
        print(f"    MACD: {macd_color}{indicators['macd']:.2f}{Colors.ENDC}", end="  ")
        print(f"Signal: {Colors.GREY}{indicators.get('macd_signal', 0):.2f}{Colors.ENDC}", end="  ")
        print(f"Hist: {macd_color}{indicators.get('macd_histogram', 0):.2f}{Colors.ENDC}")

    # Bollinger Bands
    if 'bb_upper' in indicators:
        print(f"    BB: Upper: {Colors.GREY}{indicators['bb_upper']:.2f}{Colors.ENDC}", end="  ")
        print(f"Mid: {Colors.GREY}{indicators.get('bb_middle', 0):.2f}{Colors.ENDC}", end="  ")
        print(f"Lower: {Colors.GREY}{indicators.get('bb_lower', 0):.2f}{Colors.ENDC}")

    # Volatility & Trend
    if 'atr_14' in indicators:
        print(f"    ATR(14): {Colors.GREY}{indicators['atr_14']:.2f}{Colors.ENDC}", end="  ")
    if 'adx_14' in indicators:
        adx = indicators['adx_14']
        adx_color = Colors.OKGREEN if adx > 25 else Colors.GREY
        print(f"ADX(14): {adx_color}{adx:.2f}{Colors.ENDC}")


# ==============================================================================
# Display Functions
# ==============================================================================

def display_underlying_data(client: TradingClient, symbol: str, exporter: DataExporter):
    """Display underlying (NIFTY spot) data"""
    print_section(f"📊 Underlying: {symbol}")

    try:
        inst = client.Instrument(symbol)
        ltp = inst.ltp
        volume = inst.volume

        # Get OHLC
        try:
            candle = inst['1m']
            open_price = candle.open
            high = candle.high
            low = candle.low
            close = candle.close
            change = close - open_price
            change_pct = (change / open_price * 100) if open_price > 0 else 0

            print(f"{Colors.BOLD}LTP:{Colors.ENDC} {Colors.OKGREEN if change >= 0 else Colors.FAIL}{ltp:,.2f}{Colors.ENDC} "
                  f"({Colors.OKGREEN if change >= 0 else Colors.FAIL}{change:+.2f} / {change_pct:+.2f}%{Colors.ENDC})")
            print(f"{Colors.GREY}O: {open_price:,.2f}  H: {high:,.2f}  L: {low:,.2f}  C: {close:,.2f}  Vol: {volume:,}{Colors.ENDC}")

            # Export data
            exporter.add_underlying_tick(datetime.now(), symbol, {
                'ltp': ltp, 'open': open_price, 'high': high,
                'low': low, 'close': close, 'volume': volume,
                'change': change, 'change_pct': change_pct
            })

        except:
            print(f"{Colors.BOLD}LTP:{Colors.ENDC} {ltp:,.2f}  Vol: {volume:,}")

        # Get all indicators
        indicators = get_all_indicators(inst, '5m')
        display_indicators(indicators)

        if indicators:
            exporter.add_indicators(datetime.now(), symbol, '5m', indicators)

    except Exception as e:
        print_error(f"Error fetching {symbol}: {e}")


def display_option_tick(client: TradingClient, symbol: str, oi_tracker: OITracker,
                       spot_price: float, exporter: DataExporter):
    """Display option tick data with all details"""
    try:
        inst = client.Instrument(symbol)
        opt_info = extract_option_info(symbol)
        if not opt_info:
            return

        moneyness_label, distance = calculate_moneyness(
            opt_info['strike'], spot_price, opt_info['option_type']
        )

        # Get quote data
        ltp = inst.ltp
        volume = inst.volume
        oi = inst.oi
        bid = inst.bid
        ask = inst.ask

        # Update OI tracker
        oi_tracker.update(symbol, oi, datetime.now())
        oi_change = oi_tracker.get_change(symbol)
        oi_pct_change = oi_tracker.get_percentage_change(symbol)

        # Get Greeks
        greeks = inst.greeks
        greeks_valid = greeks.get('_state') == DataState.VALID
        delta = greeks.get('delta', 0) if greeks_valid else 0
        gamma = greeks.get('gamma', 0) if greeks_valid else 0
        theta = greeks.get('theta', 0) if greeks_valid else 0
        vega = greeks.get('vega', 0) if greeks_valid else 0
        iv = greeks.get('iv', 0) if greeks_valid else 0

        # Export data
        exporter.add_option_tick(datetime.now(), symbol, {
            'strike': opt_info['strike'],
            'option_type': opt_info['option_type'],
            'moneyness': moneyness_label,
            'ltp': ltp, 'bid': bid, 'ask': ask,
            'volume': volume, 'oi': oi,
            'oi_change': oi_change or 0,
            'oi_pct_change': oi_pct_change or 0
        })

        if greeks_valid:
            exporter.add_greeks(datetime.now(), symbol, {
                'delta': delta, 'gamma': gamma, 'theta': theta,
                'vega': vega, 'iv': iv
            })

        # Display
        opt_color = Colors.OKGREEN if opt_info['option_type'] == 'CE' else Colors.FAIL
        print(f"\n{opt_color}{Colors.BOLD}{symbol}{Colors.ENDC} "
              f"{Colors.YELLOW}[{moneyness_label}]{Colors.ENDC} "
              f"{Colors.GREY}(Strike: {opt_info['strike']:.0f}){Colors.ENDC}")

        print(f"  {Colors.BOLD}LTP:{Colors.ENDC} {ltp:.2f}  "
              f"{Colors.GREY}Bid: {bid:.2f}  Ask: {ask:.2f}{Colors.ENDC}")

        oi_color = Colors.OKGREEN if (oi_change or 0) >= 0 else Colors.FAIL
        oi_change_str = f" ({oi_color}{oi_change:+,}{Colors.ENDC}" if oi_change else ""
        oi_pct_str = f", {oi_color}{oi_pct_change:+.1f}%{Colors.ENDC})" if oi_pct_change is not None and oi_change else ")"

        print(f"  {Colors.CYAN}Vol:{Colors.ENDC} {volume:,}  "
              f"{Colors.CYAN}OI:{Colors.ENDC} {oi:,}{oi_change_str}{oi_pct_str if oi_change else ''}")

        if greeks_valid:
            print(f"  {Colors.MAGENTA}Greeks:{Colors.ENDC} "
                  f"Δ: {delta:.4f}  γ: {gamma:.4f}  θ: {theta:.4f}  ν: {vega:.4f}  IV: {iv:.2%}")

        # Get indicators
        indicators = get_all_indicators(inst, '5m')
        if indicators:
            display_indicators(indicators)
            exporter.add_indicators(datetime.now(), symbol, '5m', indicators)

    except InstrumentNotFoundError:
        pass
    except Exception as e:
        pass


def display_futures_tick(client: TradingClient, symbol: str, oi_tracker: OITracker, exporter: DataExporter):
    """Display futures tick data"""
    try:
        inst = client.Instrument(symbol)
        fut_info = extract_futures_info(symbol)
        if not fut_info:
            return

        # Get quote data
        ltp = inst.ltp
        volume = inst.volume
        oi = inst.oi
        bid = inst.bid
        ask = inst.ask

        # Update OI tracker
        oi_tracker.update(symbol, oi, datetime.now())
        oi_change = oi_tracker.get_change(symbol)
        oi_pct_change = oi_tracker.get_percentage_change(symbol)

        # Get OHLC
        try:
            candle = inst['1m']
            open_price = candle.open
            high = candle.high
            low = candle.low
            close = candle.close
            change = close - open_price
            change_pct = (change / open_price * 100) if open_price > 0 else 0

            # Export data
            exporter.add_futures_tick(datetime.now(), symbol, {
                'underlying': fut_info['underlying'],
                'expiry_code': fut_info['expiry_code'],
                'ltp': ltp, 'bid': bid, 'ask': ask,
                'open': open_price, 'high': high, 'low': low, 'close': close,
                'volume': volume, 'oi': oi,
                'oi_change': oi_change or 0,
                'oi_pct_change': oi_pct_change or 0,
                'change': change, 'change_pct': change_pct
            })

            print(f"\n{Colors.BOLD}{Colors.CYAN}{symbol}{Colors.ENDC} {Colors.GREY}(Futures){Colors.ENDC}")
            print(f"  {Colors.BOLD}LTP:{Colors.ENDC} {Colors.OKGREEN if change >= 0 else Colors.FAIL}{ltp:,.2f}{Colors.ENDC} "
                  f"({Colors.OKGREEN if change >= 0 else Colors.FAIL}{change:+.2f} / {change_pct:+.2f}%{Colors.ENDC})")
            print(f"  {Colors.GREY}O: {open_price:,.2f}  H: {high:,.2f}  L: {low:,.2f}  C: {close:,.2f}{Colors.ENDC}")

        except:
            print(f"\n{Colors.BOLD}{Colors.CYAN}{symbol}{Colors.ENDC} {Colors.GREY}(Futures){Colors.ENDC}")
            print(f"  {Colors.BOLD}LTP:{Colors.ENDC} {ltp:,.2f}  {Colors.GREY}Bid: {bid:.2f}  Ask: {ask:.2f}{Colors.ENDC}")

        oi_color = Colors.OKGREEN if (oi_change or 0) >= 0 else Colors.FAIL
        oi_change_str = f" ({oi_color}{oi_change:+,}{Colors.ENDC}" if oi_change else ""
        oi_pct_str = f", {oi_color}{oi_pct_change:+.1f}%{Colors.ENDC})" if oi_pct_change is not None and oi_change else ")"

        print(f"  {Colors.CYAN}Vol:{Colors.ENDC} {volume:,}  "
              f"{Colors.CYAN}OI:{Colors.ENDC} {oi:,}{oi_change_str}{oi_pct_str if oi_change else ''}")

        # Get indicators
        indicators = get_all_indicators(inst, '5m')
        if indicators:
            display_indicators(indicators)
            exporter.add_indicators(datetime.now(), symbol, '5m', indicators)

    except Exception as e:
        pass


# ==============================================================================
# Option Chain Heatmap
# ==============================================================================

def display_option_chain_heatmap(client: TradingClient, spot_price: float, strike_range: List[float]):
    """Display option chain as a heatmap"""
    print_section("🔥 Option Chain Heatmap (OI Intensity)")

    # Header
    print(f"\n{'Strike':<10} {'Call OI':>15} {'':>5} {'Put OI':>15} {'PCR':>10}")
    print(f"{'-'*10} {'-'*15:>15} {'-'*5:>5} {'-'*15:>15} {'-'*10:>10}")

    for strike in strike_range:
        try:
            # Get call option
            call_symbol = f"NIFTY25N04{int(strike)}CE"
            put_symbol = f"NIFTY25N04{int(strike)}PE"

            call_oi = 0
            put_oi = 0

            try:
                call_inst = client.Instrument(call_symbol)
                call_oi = call_inst.oi
            except:
                pass

            try:
                put_inst = client.Instrument(put_symbol)
                put_oi = put_inst.oi
            except:
                pass

            pcr = (put_oi / call_oi) if call_oi > 0 else 0

            # Color code based on max OI
            max_oi = max(call_oi, put_oi)
            if max_oi > 5000000:
                intensity = Colors.BG_RED
            elif max_oi > 2000000:
                intensity = Colors.BG_YELLOW
            elif max_oi > 1000000:
                intensity = Colors.BG_GREEN
            else:
                intensity = ""

            # Highlight ATM
            if abs(strike - spot_price) < 50:
                strike_str = f"{Colors.YELLOW}{Colors.BOLD}{strike:,.0f} ★{Colors.ENDC}"
            else:
                strike_str = f"{strike:,.0f}"

            call_bar = '█' * min(int(call_oi / 500000), 15)
            put_bar = '█' * min(int(put_oi / 500000), 15)

            print(f"{strike_str:<18} {call_oi:>15,} {Colors.OKGREEN}{call_bar:<15}{Colors.ENDC} "
                  f"{Colors.FAIL}{put_bar:>15}{Colors.ENDC} {put_oi:>15,} {pcr:>10.2f}")

        except Exception as e:
            pass


# ==============================================================================
# Continuous Tick Monitor
# ==============================================================================

def run_tick_monitor(client: TradingClient, duration_seconds: int = 300):
    """Run continuous tick monitor with all features"""
    print_header("ENHANCED TICK MONITOR")

    print_info(f"Monitoring for {duration_seconds} seconds...")
    print_info(f"Export directory: {EXPORT_DIR}")
    print_info("Press Ctrl+C to stop and export data")

    # Initialize
    oi_tracker = OITracker()
    session_id = datetime.now().strftime('%Y%m%d_%H%M%S')
    exporter = DataExporter(EXPORT_DIR)

    underlying_symbol = "NIFTY 50"

    # Get spot price
    try:
        nifty = client.Instrument(underlying_symbol)
        spot_price = nifty.ltp
    except:
        spot_price = 25680

    atm_strike = round(spot_price / 50) * 50

    # Define instruments to monitor
    monitored_options = [
        f"NIFTY25N04{int(atm_strike - 150)}CE",
        f"NIFTY25N04{int(atm_strike - 100)}CE",
        f"NIFTY25N04{int(atm_strike - 50)}CE",
        f"NIFTY25N04{int(atm_strike)}CE",
        f"NIFTY25N04{int(atm_strike + 50)}CE",
        f"NIFTY25N04{int(atm_strike + 100)}CE",
        f"NIFTY25N04{int(atm_strike + 150)}CE",
        f"NIFTY25N04{int(atm_strike - 150)}PE",
        f"NIFTY25N04{int(atm_strike - 100)}PE",
        f"NIFTY25N04{int(atm_strike - 50)}PE",
        f"NIFTY25N04{int(atm_strike)}PE",
        f"NIFTY25N04{int(atm_strike + 50)}PE",
        f"NIFTY25N04{int(atm_strike + 100)}PE",
        f"NIFTY25N04{int(atm_strike + 150)}PE",
    ]

    # Futures to monitor
    monitored_futures = ["NIFTY25NOVFUT", "NIFTY25DECFUT"]

    start_time = time.time()
    iteration = 0

    try:
        while time.time() - start_time < duration_seconds:
            iteration += 1

            # Clear screen
            print("\033[2J\033[H")
            print_header(f"LIVE TICK MONITOR - Iteration {iteration}")
            print(f"{Colors.GREY}Session: {session_id}{Colors.ENDC}")
            print(f"{Colors.GREY}Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{Colors.ENDC}")
            print(f"{Colors.GREY}Elapsed: {int(time.time() - start_time)}s / {duration_seconds}s{Colors.ENDC}")

            # Display underlying
            display_underlying_data(client, underlying_symbol, exporter)

            # Update spot price
            try:
                nifty = client.Instrument(underlying_symbol)
                spot_price = nifty.ltp
            except:
                pass

            # Display futures
            print_section("📈 FUTURES")
            for symbol in monitored_futures:
                display_futures_tick(client, symbol, oi_tracker, exporter)

            # Display call options
            print_section("📞 CALL Options")
            for symbol in monitored_options:
                if "CE" in symbol:
                    display_option_tick(client, symbol, oi_tracker, spot_price, exporter)

            # Display put options
            print_section("📉 PUT Options")
            for symbol in monitored_options:
                if "PE" in symbol:
                    display_option_tick(client, symbol, oi_tracker, spot_price, exporter)

            # Display option chain heatmap every 3rd iteration
            if iteration % 3 == 0:
                strike_range = [atm_strike + (i * 50) for i in range(-5, 6)]
                display_option_chain_heatmap(client, spot_price, strike_range)

            print(f"\n{Colors.GREY}Refreshing in 5 seconds... (Data points collected: {len(exporter.underlying_data)}){Colors.ENDC}")
            time.sleep(5)

    except KeyboardInterrupt:
        print(f"\n\n{Colors.WARNING}Monitor stopped by user{Colors.ENDC}")
    finally:
        print_section("Exporting Collected Data")
        exporter.export_all(session_id)
        print_success(f"Session {session_id} complete!")


# ==============================================================================
# Main Function
# ==============================================================================

def main():
    """Main function"""
    print_header("StocksBlitz SDK - Enhanced Tick Monitor")

    print_info(f"API URL: {API_URL}")
    print_info(f"User Service URL: {USER_SERVICE_URL}")
    print_info(f"Username: {USERNAME}")

    # Authenticate
    print_section("Authentication")

    try:
        client = TradingClient.from_credentials(
            api_url=API_URL,
            user_service_url=USER_SERVICE_URL,
            username=USERNAME,
            password=PASSWORD,
            persist_session=True
        )
        print_success(f"Authenticated as {USERNAME}")
    except AuthenticationError as e:
        print_error(f"Authentication failed: {e}")
        print_warning("Trying alternate password...")

        # Try asking user for password
        try:
            import getpass
            alt_password = getpass.getpass("Enter password for raghurammutya@gmail.com: ")
            client = TradingClient.from_credentials(
                api_url=API_URL,
                user_service_url=USER_SERVICE_URL,
                username=USERNAME,
                password=alt_password,
                persist_session=True
            )
            print_success(f"Authenticated successfully!")
        except Exception as e2:
            print_error(f"Authentication failed: {e2}")
            return 1
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        return 1

    # Run monitor
    print("\n")
    print_info("Starting enhanced tick monitor in 3 seconds...")
    time.sleep(3)

    try:
        run_tick_monitor(client, duration_seconds=300)
    except Exception as e:
        print_error(f"Error in tick monitor: {e}")
        import traceback
        traceback.print_exc()
        return 1

    print_success("Monitor completed successfully!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
