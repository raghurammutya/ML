#!/usr/bin/env python3
"""
Comprehensive Tick Monitor - StocksBlitz SDK Testing

Tests all SDK functionality:
- Authentication (JWT with raghurammutya@gmail.com)
- Instrument discovery with various moneyness types
- Real-time tick data polling
- Greeks (delta, gamma, theta, vega, IV)
- OI data and OI change tracking
- Indicator outputs
- Formatted display with moneyness labels
"""

import sys
sys.path.insert(0, '/mnt/stocksblitz-data/Quantagro/tradingview-viz/python-sdk')

import time
from datetime import datetime
from typing import Dict, List, Optional
from collections import defaultdict

from stocksblitz import TradingClient, AuthenticationError, InstrumentNotFoundError
from stocksblitz.enums import DataState


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

    # Additional colors
    CYAN = '\033[36m'
    YELLOW = '\033[33m'
    MAGENTA = '\033[35m'
    WHITE = '\033[37m'
    GREY = '\033[90m'


def print_header(text: str):
    """Print formatted header"""
    print(f"\n{Colors.BOLD}{Colors.HEADER}{'=' * 80}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.HEADER}{text.center(80)}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.HEADER}{'=' * 80}{Colors.ENDC}\n")


def print_section(text: str):
    """Print formatted section"""
    print(f"\n{Colors.BOLD}{Colors.OKBLUE}{'─' * 80}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.OKBLUE}{text}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.OKBLUE}{'─' * 80}{Colors.ENDC}")


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
# OI Change Tracker
# ==============================================================================

class OITracker:
    """Track OI changes over time"""

    def __init__(self):
        self.oi_history: Dict[str, List[tuple]] = defaultdict(list)
        self.max_history = 10

    def update(self, symbol: str, oi: int, timestamp: datetime):
        """Update OI for a symbol"""
        history = self.oi_history[symbol]
        history.append((timestamp, oi))

        # Keep only recent history
        if len(history) > self.max_history:
            history.pop(0)

    def get_change(self, symbol: str) -> Optional[int]:
        """Get OI change from first to last"""
        history = self.oi_history.get(symbol, [])
        if len(history) < 2:
            return None

        first_oi = history[0][1]
        last_oi = history[-1][1]
        return last_oi - first_oi

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
    """
    Calculate moneyness label and distance from ATM

    Returns:
        (label, distance) - e.g., ("ATM", 0) or ("OTM2", 100)
    """
    diff = strike - spot

    if option_type.upper() == "CE" or option_type.upper() == "CALL":
        # For calls: ITM when strike < spot
        if abs(diff) < 50:
            return ("ATM", 0)
        elif diff < 0:
            # ITM
            steps = int(abs(diff) / 50)
            return (f"ITM{steps}", abs(diff))
        else:
            # OTM
            steps = int(diff / 50)
            return (f"OTM{steps}", diff)
    else:
        # For puts: ITM when strike > spot
        if abs(diff) < 50:
            return ("ATM", 0)
        elif diff > 0:
            # ITM
            steps = int(diff / 50)
            return (f"ITM{steps}", diff)
        else:
            # OTM
            steps = int(abs(diff) / 50)
            return (f"OTM{steps}", abs(diff))


def extract_option_info(symbol: str) -> Optional[Dict]:
    """
    Extract option information from symbol

    Returns:
        Dict with: underlying, expiry, strike, option_type
    """
    import re

    # Pattern: NIFTY25N0424500PE
    # NIFTY = underlying
    # 25N04 = expiry (year 25, month N=Nov, week 04)
    # 24500 = strike
    # PE = option type

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


# ==============================================================================
# Data Display Functions
# ==============================================================================

def display_underlying_data(client: TradingClient, symbol: str):
    """Display underlying (NIFTY spot) data"""
    print_section(f"📊 Underlying: {symbol}")

    try:
        inst = client.Instrument(symbol)

        # Get quote data
        ltp = inst.ltp
        volume = inst.volume

        # Try to get OHLC if available
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
            print(f"{Colors.GREY}O: {open_price:,.2f}  H: {high:,.2f}  L: {low:,.2f}  C: {close:,.2f}{Colors.ENDC}")
        except:
            print(f"{Colors.BOLD}LTP:{Colors.ENDC} {ltp:,.2f}")

        print(f"{Colors.GREY}Volume: {volume:,}{Colors.ENDC}")

        # Try to get indicators
        try:
            rsi = inst['5m'].rsi[14]
            print(f"{Colors.CYAN}RSI(14, 5m): {rsi:.2f}{Colors.ENDC}")
        except:
            pass

    except Exception as e:
        print_error(f"Error fetching {symbol}: {e}")


def display_option_tick(client: TradingClient, symbol: str, oi_tracker: OITracker, spot_price: float):
    """Display option tick data with all details"""

    try:
        inst = client.Instrument(symbol)

        # Extract option info
        opt_info = extract_option_info(symbol)
        if not opt_info:
            print_warning(f"Cannot parse symbol: {symbol}")
            return

        # Calculate moneyness
        moneyness_label, distance = calculate_moneyness(
            opt_info['strike'],
            spot_price,
            opt_info['option_type']
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

        # Color coding for option type
        opt_color = Colors.OKGREEN if opt_info['option_type'] == 'CE' else Colors.FAIL

        # Print symbol with moneyness
        print(f"\n{opt_color}{Colors.BOLD}{symbol}{Colors.ENDC} "
              f"{Colors.YELLOW}[{moneyness_label}]{Colors.ENDC} "
              f"{Colors.GREY}(Strike: {opt_info['strike']:.0f}){Colors.ENDC}")

        # Price data
        print(f"  {Colors.BOLD}LTP:{Colors.ENDC} {ltp:.2f}  "
              f"{Colors.GREY}Bid: {bid:.2f}  Ask: {ask:.2f}{Colors.ENDC}")

        # Volume and OI
        oi_color = Colors.OKGREEN if (oi_change or 0) >= 0 else Colors.FAIL
        oi_change_str = f" ({oi_color}{oi_change:+,}{Colors.ENDC}" if oi_change else ""
        oi_pct_str = f", {oi_color}{oi_pct_change:+.1f}%{Colors.ENDC})" if oi_pct_change is not None and oi_change else ")"

        print(f"  {Colors.CYAN}Vol:{Colors.ENDC} {volume:,}  "
              f"{Colors.CYAN}OI:{Colors.ENDC} {oi:,}{oi_change_str}{oi_pct_str if oi_change else ''}")

        # Greeks
        if greeks_valid:
            print(f"  {Colors.MAGENTA}Greeks:{Colors.ENDC} "
                  f"Δ: {delta:.4f}  γ: {gamma:.4f}  θ: {theta:.4f}  ν: {vega:.4f}  "
                  f"IV: {iv:.2%}")
        else:
            print(f"  {Colors.GREY}Greeks: {greeks.get('_reason', 'N/A')}{Colors.ENDC}")

        # Try to get indicators
        try:
            rsi = inst['5m'].rsi[14]
            print(f"  {Colors.CYAN}RSI(14, 5m):{Colors.ENDC} {rsi:.2f}")
        except:
            pass

    except InstrumentNotFoundError:
        print_warning(f"{symbol}: Not found in current snapshot")
    except Exception as e:
        print_error(f"Error fetching {symbol}: {e}")


def display_expiry_summary(client: TradingClient, underlying: str, spot_price: float):
    """Display summary across expiries"""
    print_section(f"📅 Expiry Summary - {underlying}")

    # This would use the monitor API to get aggregated data
    # For now, we'll show a simplified version

    try:
        # Get monitor snapshot
        response = client._api.get(f"/monitor/snapshot", params={"underlying": underlying})

        if "expiries" in response:
            expiries = response["expiries"]

            print(f"{'Expiry':<15} {'Total Call OI':>15} {'Total Put OI':>15} {'PCR':>10} {'Max Pain':>12}")
            print(f"{'-'*15} {'-'*15:>15} {'-'*15:>15} {'-'*10:>10} {'-'*12:>12}")

            for exp in expiries[:5]:  # Show first 5 expiries
                expiry_date = exp.get('expiry', 'N/A')
                total_call_oi = exp.get('total_call_oi', 0)
                total_put_oi = exp.get('total_put_oi', 0)
                pcr = (total_put_oi / total_call_oi) if total_call_oi > 0 else 0
                max_pain = exp.get('max_pain_strike', 0)

                print(f"{expiry_date:<15} {total_call_oi:>15,} {total_put_oi:>15,} "
                      f"{pcr:>10.2f} {max_pain:>12,.0f}")
    except Exception as e:
        print_warning(f"Could not fetch expiry summary: {e}")


# ==============================================================================
# Instrument Discovery Testing
# ==============================================================================

def test_instrument_discovery(client: TradingClient):
    """Test instrument discovery with various moneyness types"""
    print_header("INSTRUMENT DISCOVERY - Moneyness Testing")

    print_info("Testing different moneyness patterns...")

    # Get current NIFTY price first
    try:
        nifty = client.Instrument("NIFTY 50")
        spot_price = nifty.ltp
        print_success(f"NIFTY Spot Price: {spot_price:,.2f}")
    except Exception as e:
        print_error(f"Could not fetch NIFTY price: {e}")
        spot_price = 25680  # Fallback

    # Calculate ATM strike (rounded to nearest 50)
    atm_strike = round(spot_price / 50) * 50

    print(f"\n{Colors.BOLD}ATM Strike (calculated):{Colors.ENDC} {atm_strike:.0f}")

    # Define test strikes for different moneyness
    test_cases = [
        ("ATM Call", atm_strike, "CE", "ATM"),
        ("ATM Put", atm_strike, "PE", "ATM"),
        ("OTM1 Call", atm_strike + 50, "CE", "OTM1"),
        ("OTM2 Call", atm_strike + 100, "CE", "OTM2"),
        ("OTM3 Call", atm_strike + 150, "CE", "OTM3"),
        ("OTM1 Put", atm_strike - 50, "PE", "OTM1"),
        ("OTM2 Put", atm_strike - 100, "PE", "OTM2"),
        ("ITM1 Call", atm_strike - 50, "CE", "ITM1"),
        ("ITM2 Call", atm_strike - 100, "CE", "ITM2"),
        ("ITM1 Put", atm_strike + 50, "PE", "ITM1"),
        ("ITM2 Put", atm_strike + 100, "PE", "ITM2"),
    ]

    print(f"\n{Colors.BOLD}Moneyness Test Cases:{Colors.ENDC}\n")
    print(f"{'Label':<15} {'Strike':>10} {'Type':>6} {'Expected':>10} {'Symbol':<25}")
    print(f"{'-'*15} {'-'*10:>10} {'-'*6:>6} {'-'*10:>10} {'-'*25}")

    for label, strike, opt_type, expected_money in test_cases:
        # Try to construct symbol (using weekly expiry)
        # Format: NIFTY25N0424500PE
        # This is a simplified version - actual implementation would need proper expiry lookup
        symbol = f"NIFTY25N04{int(strike)}{opt_type}"

        moneyness_label, distance = calculate_moneyness(strike, spot_price, opt_type)

        match = "✓" if moneyness_label == expected_money else "✗"
        color = Colors.OKGREEN if moneyness_label == expected_money else Colors.FAIL

        print(f"{label:<15} {strike:>10,.0f} {opt_type:>6} {expected_money:>10} {symbol:<25} "
              f"{color}{match} {moneyness_label}{Colors.ENDC}")


# ==============================================================================
# Continuous Tick Monitor
# ==============================================================================

def run_tick_monitor(client: TradingClient, duration_seconds: int = 300):
    """
    Run continuous tick monitor

    Args:
        client: Authenticated TradingClient
        duration_seconds: How long to run (default: 5 minutes)
    """
    print_header("CONTINUOUS TICK MONITOR")

    print_info(f"Monitoring for {duration_seconds} seconds...")
    print_info("Press Ctrl+C to stop early")

    # Initialize OI tracker
    oi_tracker = OITracker()

    # Define instruments to monitor
    underlying_symbol = "NIFTY 50"

    # Get current spot price
    try:
        nifty = client.Instrument(underlying_symbol)
        spot_price = nifty.ltp
    except:
        spot_price = 25680  # Fallback

    # Calculate ATM and nearby strikes
    atm_strike = round(spot_price / 50) * 50

    # Monitor these options
    monitored_options = [
        f"NIFTY25N04{int(atm_strike - 100)}CE",  # ITM2 Call
        f"NIFTY25N04{int(atm_strike - 50)}CE",   # ITM1 Call
        f"NIFTY25N04{int(atm_strike)}CE",        # ATM Call
        f"NIFTY25N04{int(atm_strike + 50)}CE",   # OTM1 Call
        f"NIFTY25N04{int(atm_strike + 100)}CE",  # OTM2 Call
        f"NIFTY25N04{int(atm_strike - 100)}PE",  # OTM2 Put
        f"NIFTY25N04{int(atm_strike - 50)}PE",   # OTM1 Put
        f"NIFTY25N04{int(atm_strike)}PE",        # ATM Put
        f"NIFTY25N04{int(atm_strike + 50)}PE",   # ITM1 Put
        f"NIFTY25N04{int(atm_strike + 100)}PE",  # ITM2 Put
    ]

    start_time = time.time()
    iteration = 0

    try:
        while time.time() - start_time < duration_seconds:
            iteration += 1

            # Clear screen and show header
            print("\033[2J\033[H")  # Clear screen
            print_header(f"LIVE TICK MONITOR - Iteration {iteration}")
            print(f"{Colors.GREY}Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{Colors.ENDC}")
            print(f"{Colors.GREY}Elapsed: {int(time.time() - start_time)}s / {duration_seconds}s{Colors.ENDC}")

            # Display underlying
            display_underlying_data(client, underlying_symbol)

            # Update spot price
            try:
                nifty = client.Instrument(underlying_symbol)
                spot_price = nifty.ltp
            except:
                pass

            # Display options
            print_section("📈 CALL Options")
            for symbol in monitored_options:
                if "CE" in symbol:
                    display_option_tick(client, symbol, oi_tracker, spot_price)

            print_section("📉 PUT Options")
            for symbol in monitored_options:
                if "PE" in symbol:
                    display_option_tick(client, symbol, oi_tracker, spot_price)

            # Display expiry summary
            # display_expiry_summary(client, "NIFTY", spot_price)

            # Wait before next iteration
            print(f"\n{Colors.GREY}Refreshing in 5 seconds...{Colors.ENDC}")
            time.sleep(5)

    except KeyboardInterrupt:
        print(f"\n\n{Colors.WARNING}Monitor stopped by user{Colors.ENDC}")


# ==============================================================================
# Main Function
# ==============================================================================

def main():
    """Main function"""
    print_header("StocksBlitz SDK - Comprehensive Tick Monitor")

    # Configuration
    API_URL = "http://localhost:8081"
    USER_SERVICE_URL = "http://localhost:8001"
    USERNAME = "raghurammutya@gmail.com"
    PASSWORD = "password123"  # You'll need to provide the actual password

    print_info("Initializing StocksBlitz client...")
    print_info(f"API URL: {API_URL}")
    print_info(f"User Service URL: {USER_SERVICE_URL}")
    print_info(f"Username: {USERNAME}")

    # Step 1: Authenticate
    print_section("Step 1: Authentication")

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
        print_warning("Please check your credentials and try again")
        return 1
    except Exception as e:
        print_error(f"Unexpected error during authentication: {e}")
        return 1

    # Step 2: Test Instrument Discovery
    print("\n")
    test_instrument_discovery(client)

    # Step 3: Run Continuous Monitor
    print("\n")
    print_info("Starting continuous tick monitor in 3 seconds...")
    time.sleep(3)

    try:
        run_tick_monitor(client, duration_seconds=300)  # Run for 5 minutes
    except Exception as e:
        print_error(f"Error in tick monitor: {e}")
        import traceback
        traceback.print_exc()
        return 1

    print_success("Monitor completed successfully!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
