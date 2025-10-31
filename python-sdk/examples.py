#!/usr/bin/env python3
"""
StocksBlitz SDK Examples

Comprehensive examples demonstrating all features of the SDK.

Usage:
    python examples.py
"""

from stocksblitz import TradingClient
import time


# Configuration
API_URL = "http://localhost:8009"
API_KEY = "sb_30d4d5ea_bbb52c64cc4eb2536fdd7b44861c93e4b30b50c6"


def example_1_basic_usage():
    """Example 1: Basic SDK usage."""
    print("\n" + "="*70)
    print("Example 1: Basic Usage")
    print("="*70)

    # Initialize client
    client = TradingClient(api_url=API_URL, api_key=API_KEY)

    # Create instrument
    inst = client.Instrument("NIFTY25N0424500PE")

    # Access market data
    print(f"Instrument: {inst.tradingsymbol}")
    print(f"LTP: {inst.ltp}")
    print(f"Volume: {inst.volume}")
    print(f"OI: {inst.oi}")


def example_2_technical_indicators():
    """Example 2: Technical indicators."""
    print("\n" + "="*70)
    print("Example 2: Technical Indicators")
    print("="*70)

    client = TradingClient(api_url=API_URL, api_key=API_KEY)
    inst = client.Instrument("NIFTY25N0424500PE")

    # RSI
    rsi = inst['5m'].rsi[14]
    print(f"RSI(14): {rsi:.2f}")

    if rsi > 70:
        print("  → Overbought!")
    elif rsi < 30:
        print("  → Oversold!")

    # Moving Averages
    sma_20 = inst['5m'].sma[20]
    ema_50 = inst['5m'].ema[50]
    print(f"SMA(20): {sma_20:.2f}")
    print(f"EMA(50): {ema_50:.2f}")

    if sma_20 > ema_50:
        print("  → Bullish crossover!")

    # MACD
    macd = inst['5m'].macd[12, 26, 9]
    print(f"MACD: {macd}")

    # Bollinger Bands
    bb = inst['5m'].bbands[20, 2]
    print(f"Bollinger Bands: Upper={bb['upper']:.2f}, "
          f"Middle={bb['middle']:.2f}, Lower={bb['lower']:.2f}")

    # ATR
    atr = inst['5m'].atr[14]
    print(f"ATR(14): {atr:.2f}")


def example_3_multi_timeframe():
    """Example 3: Multi-timeframe analysis."""
    print("\n" + "="*70)
    print("Example 3: Multi-Timeframe Analysis")
    print("="*70)

    client = TradingClient(api_url=API_URL, api_key=API_KEY)
    inst = client.Instrument("NIFTY25N0424500PE")

    # RSI across timeframes
    timeframes = ['1m', '5m', '15m', '1h']
    rsi_values = {}

    for tf in timeframes:
        try:
            rsi = inst[tf].rsi[14]
            rsi_values[tf] = rsi
            print(f"{tf:>4} RSI: {rsi:.2f}")
        except Exception as e:
            print(f"{tf:>4} RSI: Error - {e}")

    # Check trend alignment
    if all(rsi > 60 for rsi in rsi_values.values() if rsi):
        print("\n  → Bullish across all timeframes!")
    elif all(rsi < 40 for rsi in rsi_values.values() if rsi):
        print("\n  → Bearish across all timeframes!")


def example_4_ohlcv_data():
    """Example 4: OHLCV data access."""
    print("\n" + "="*70)
    print("Example 4: OHLCV Data Access")
    print("="*70)

    client = TradingClient(api_url=API_URL, api_key=API_KEY)
    inst = client.Instrument("NIFTY25N0424500PE")

    # Current candle
    candle = inst['5m'][0]
    print(f"Current Candle (5m):")
    print(f"  Open:   {candle.open:.2f}")
    print(f"  High:   {candle.high:.2f}")
    print(f"  Low:    {candle.low:.2f}")
    print(f"  Close:  {candle.close:.2f}")
    print(f"  Volume: {candle.volume}")
    print(f"  Time:   {candle.time}")

    # Check if bullish
    if candle.close > candle.open:
        print("  → Bullish candle")
    else:
        print("  → Bearish candle")

    # Shortcut access
    current_close = inst['5m'].close
    print(f"\nShortcut: inst['5m'].close = {current_close:.2f}")


def example_5_trading_operations():
    """Example 5: Trading operations."""
    print("\n" + "="*70)
    print("Example 5: Trading Operations")
    print("="*70)

    client = TradingClient(api_url=API_URL, api_key=API_KEY)
    account = client.Account()

    # Get funds
    print("Account Funds:")
    try:
        funds = account.funds
        print(f"  Available Cash:   ₹{funds.available_cash:,.2f}")
        print(f"  Used Margin:      ₹{funds.used_margin:,.2f}")
        print(f"  Available Margin: ₹{funds.available_margin:,.2f}")
    except Exception as e:
        print(f"  Error fetching funds: {e}")

    # Get positions
    print("\nPositions:")
    try:
        positions = account.positions
        if positions:
            for pos in positions[:5]:  # First 5 positions
                print(f"  {pos.tradingsymbol}: "
                      f"Qty={pos.quantity}, "
                      f"PnL={pos.pnl:,.2f} ({pos.pnl_percent:.2f}%)")
        else:
            print("  No positions")
    except Exception as e:
        print(f"  Error fetching positions: {e}")

    # Demo order placement (commented out for safety)
    # inst = client.Instrument("NIFTY25N0424500PE")
    # order = account.buy(inst, quantity=50, order_type="MARKET")
    # print(f"\nOrder placed: {order}")


def example_6_position_management():
    """Example 6: Position management."""
    print("\n" + "="*70)
    print("Example 6: Position Management")
    print("="*70)

    client = TradingClient(api_url=API_URL, api_key=API_KEY)
    account = client.Account()

    # Get specific position
    symbol = "NIFTY25N0424500PE"
    pos = account.position(symbol)

    if pos:
        print(f"Position: {pos.tradingsymbol}")
        print(f"  Quantity:     {pos.quantity}")
        print(f"  Avg Price:    {pos.average_price:.2f}")
        print(f"  Last Price:   {pos.last_price:.2f}")
        print(f"  PnL:          {pos.pnl:,.2f}")
        print(f"  PnL %:        {pos.pnl_percent:.2f}%")
        print(f"  Type:         {'Long' if pos.is_long else 'Short'}")

        # Example: Close position with 10% profit (commented for safety)
        # if pos.pnl_percent > 10:
        #     print("\n  Taking profit...")
        #     pos.close()

        # Example: Stop loss at -5% (commented for safety)
        # if pos.pnl_percent < -5:
        #     print("\n  Stop loss triggered...")
        #     pos.close()
    else:
        print(f"No position found for {symbol}")


def example_7_option_greeks():
    """Example 7: Option Greeks."""
    print("\n" + "="*70)
    print("Example 7: Option Greeks")
    print("="*70)

    client = TradingClient(api_url=API_URL, api_key=API_KEY)
    inst = client.Instrument("NIFTY25N0424500PE")

    print(f"Instrument: {inst.tradingsymbol}")
    print(f"  Delta: {inst.delta:.4f}")
    print(f"  Gamma: {inst.gamma:.4f}")
    print(f"  Theta: {inst.theta:.4f}")
    print(f"  Vega:  {inst.vega:.4f}")
    print(f"  IV:    {inst.iv:.2f}%")

    # Greeks-based strategy example
    if inst.delta > 0.5 and inst.theta < -5:
        print("\n  → High delta, high theta decay - consider selling")


def example_8_mean_reversion_strategy():
    """Example 8: Complete mean reversion strategy."""
    print("\n" + "="*70)
    print("Example 8: Mean Reversion Strategy (Demo)")
    print("="*70)

    client = TradingClient(api_url=API_URL, api_key=API_KEY)
    inst = client.Instrument("NIFTY25N0424500PE")
    account = client.Account()

    # Strategy parameters
    RSI_OVERSOLD = 30
    RSI_OVERBOUGHT = 70
    STOP_LOSS_PCT = -5
    TAKE_PROFIT_PCT = 10

    # Get current RSI
    try:
        rsi = inst['5m'].rsi[14]
        print(f"Current RSI: {rsi:.2f}")

        # Check existing position
        pos = account.position(inst)

        if pos:
            print(f"Existing position: PnL={pos.pnl_percent:.2f}%")

            # Exit conditions
            if rsi > RSI_OVERBOUGHT:
                print("  → EXIT SIGNAL: RSI overbought")
                # pos.close()  # Commented for safety

            elif pos.pnl_percent < STOP_LOSS_PCT:
                print(f"  → STOP LOSS: PnL={pos.pnl_percent:.2f}%")
                # pos.close()  # Commented for safety

            elif pos.pnl_percent > TAKE_PROFIT_PCT:
                print(f"  → TAKE PROFIT: PnL={pos.pnl_percent:.2f}%")
                # pos.close()  # Commented for safety

        else:
            print("No existing position")

            # Entry condition
            if rsi < RSI_OVERSOLD:
                print("  → ENTRY SIGNAL: RSI oversold")
                # account.buy(inst, quantity=50)  # Commented for safety

    except Exception as e:
        print(f"Error: {e}")


def example_9_breakout_strategy():
    """Example 9: Breakout strategy."""
    print("\n" + "="*70)
    print("Example 9: Breakout Strategy (Demo)")
    print("="*70)

    client = TradingClient(api_url=API_URL, api_key=API_KEY)
    inst = client.Instrument("NIFTY25N0424500PE")

    try:
        # Get current price and recent highs
        current_price = inst.ltp

        # Calculate 20-period high using indicator lookback
        # Note: This is a simplified example
        high_20 = inst['15m'].high  # Current high
        print(f"Current Price: {current_price:.2f}")
        print(f"20-period High: {high_20:.2f}")

        # Breakout condition
        if current_price > high_20:
            print("  → BREAKOUT SIGNAL!")
            print("  → Consider BUY")

        # ATR-based stop loss
        atr = inst['15m'].atr[14]
        stop_loss = current_price - (2 * atr)
        print(f"\nSuggested stop loss: {stop_loss:.2f} (2x ATR)")

    except Exception as e:
        print(f"Error: {e}")


def example_10_portfolio_management():
    """Example 10: Portfolio management."""
    print("\n" + "="*70)
    print("Example 10: Portfolio Management")
    print("="*70)

    client = TradingClient(api_url=API_URL, api_key=API_KEY)
    account = client.Account()

    try:
        positions = account.positions

        if positions:
            print(f"Total Positions: {len(positions)}\n")

            # Calculate portfolio metrics
            total_pnl = sum(pos.pnl for pos in positions)
            total_investment = sum(
                abs(pos.quantity) * pos.average_price
                for pos in positions
            )
            portfolio_pnl_pct = (total_pnl / total_investment * 100) if total_investment > 0 else 0

            print(f"Portfolio Metrics:")
            print(f"  Total PnL:     ₹{total_pnl:,.2f}")
            print(f"  Investment:    ₹{total_investment:,.2f}")
            print(f"  PnL %:         {portfolio_pnl_pct:.2f}%")

            # Winners and losers
            winners = [p for p in positions if p.pnl > 0]
            losers = [p for p in positions if p.pnl < 0]

            print(f"\n  Winners: {len(winners)}")
            print(f"  Losers:  {len(losers)}")

            # Risk management
            if len(positions) > 5:
                print("\n  ⚠ Warning: More than 5 positions - consider reducing")

        else:
            print("No positions")

    except Exception as e:
        print(f"Error: {e}")


def main():
    """Run all examples."""
    print("\n" + "#"*70)
    print("# StocksBlitz SDK - Comprehensive Examples")
    print("#"*70)

    examples = [
        example_1_basic_usage,
        example_2_technical_indicators,
        example_3_multi_timeframe,
        example_4_ohlcv_data,
        example_5_trading_operations,
        example_6_position_management,
        example_7_option_greeks,
        example_8_mean_reversion_strategy,
        example_9_breakout_strategy,
        example_10_portfolio_management,
    ]

    for example in examples:
        try:
            example()
            time.sleep(1)  # Brief pause between examples
        except Exception as e:
            print(f"\n  ❌ Error in {example.__name__}: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "="*70)
    print("All examples completed!")
    print("="*70)


if __name__ == "__main__":
    main()
