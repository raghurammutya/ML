#!/usr/bin/env python3
"""
StocksBlitz SDK - Strategy Management Examples

Demonstrates strategy isolation and tracking:
- Creating/loading strategies
- Strategy-specific orders and positions
- P&L tracking per strategy
- Performance metrics and ROI
- Multiple strategies on same account

Usage:
    python examples_strategy.py
"""

from stocksblitz import (
    TradingClient,
    StrategyType, StrategyStatus
)
from datetime import datetime

# Configuration
API_URL = "http://localhost:8009"
API_KEY = "sb_30d4d5ea_bbb52c64cc4eb2536fdd7b44861c93e4b30b50c6"


def example_1_create_strategy():
    """Example 1: Create a new strategy."""
    print("\n" + "="*70)
    print("Example 1: Create Strategy")
    print("="*70)

    client = TradingClient(api_url=API_URL, api_key=API_KEY)

    # Create strategy
    strategy = client.Strategy(
        strategy_name="Nifty RSI Mean Reversion",
        strategy_type=StrategyType.MEAN_REVERSION,
        description="Buy when RSI < 30, sell when RSI > 70",
        config={
            "rsi_oversold": 30,
            "rsi_overbought": 70,
            "timeframe": "5m",
            "max_positions": 3
        }
    )

    print(f"✓ Created strategy: {strategy}")
    print(f"  Strategy ID: {strategy.strategy_id}")
    print(f"  Name: {strategy.strategy_name}")

    # Start strategy
    strategy.start()
    print(f"✓ Strategy started")


def example_2_load_existing_strategy():
    """Example 2: Load existing strategy by ID."""
    print("\n" + "="*70)
    print("Example 2: Load Existing Strategy")
    print("="*70)

    client = TradingClient(api_url=API_URL, api_key=API_KEY)

    # Load by ID
    try:
        strategy = client.Strategy(strategy_id=1)
        print(f"✓ Loaded strategy: {strategy}")
        print(f"  Name: {strategy.strategy_name}")
        print(f"  Type: {strategy._strategy_type}")
    except Exception as e:
        print(f"⚠ Strategy not found: {e}")

    # Load or create by name
    strategy = client.Strategy(
        strategy_name="Nifty RSI Mean Reversion",
        strategy_type=StrategyType.MEAN_REVERSION
    )
    print(f"✓ Strategy ready: {strategy}")


def example_3_trading_within_strategy():
    """Example 3: Execute trades within strategy context."""
    print("\n" + "="*70)
    print("Example 3: Trading Within Strategy")
    print("="*70)

    client = TradingClient(api_url=API_URL, api_key=API_KEY)

    # Create strategy
    strategy = client.Strategy(
        strategy_name="Nifty RSI Scalping",
        strategy_type=StrategyType.SCALPING
    )

    print(f"Using strategy: {strategy.strategy_name} (ID: {strategy.strategy_id})")

    # Execute trades within strategy
    inst = client.Instrument("NIFTY25N0424500PE")

    try:
        # Check RSI
        rsi = inst['5m'].rsi[14]
        print(f"\n  Current RSI: {rsi:.2f}")

        # Buy signal
        if rsi < 30:
            print("  → BUY signal (RSI oversold)")
            # order = strategy.buy(inst, quantity=50)
            # print(f"     Order placed: {order.order_id}")
        else:
            print("  → No signal")

    except Exception as e:
        print(f"  ⚠ Error: {e}")

    print(f"\n✓ All orders linked to strategy ID: {strategy.strategy_id}")


def example_4_strategy_context_manager():
    """Example 4: Using strategy as context manager."""
    print("\n" + "="*70)
    print("Example 4: Strategy Context Manager")
    print("="*70)

    client = TradingClient(api_url=API_URL, api_key=API_KEY)

    # Use context manager
    with client.Strategy(
        strategy_name="Context Strategy",
        strategy_type=StrategyType.MOMENTUM
    ) as strategy:
        print(f"Entered strategy context: {strategy.strategy_name}")
        print(f"Strategy ID: {strategy.strategy_id}")

        # All orders within this block are linked to strategy
        inst = client.Instrument("BANKNIFTY")

        try:
            ltp = inst.ltp
            print(f"\nBANKNIFTY LTP: {ltp:.2f}")

            # Example trade
            # if some_condition:
            #     strategy.buy(inst, quantity=25)

        except Exception as e:
            print(f"⚠ Error: {e}")

    print("✓ Exited strategy context")


def example_5_strategy_metrics():
    """Example 5: Get strategy performance metrics."""
    print("\n" + "="*70)
    print("Example 5: Strategy Metrics")
    print("="*70)

    client = TradingClient(api_url=API_URL, api_key=API_KEY)

    strategy = client.Strategy(
        strategy_name="Performance Test Strategy",
        strategy_type=StrategyType.DAY_TRADING
    )

    # Get metrics
    metrics = strategy.metrics

    print(f"Strategy: {strategy.strategy_name}")
    print(f"\n📊 Performance Metrics:")
    print(f"  Total P&L:       ₹{metrics.total_pnl:,.2f}")
    print(f"  Realized P&L:    ₹{metrics.realized_pnl:,.2f}")
    print(f"  Unrealized P&L:  ₹{metrics.unrealized_pnl:,.2f}")
    print(f"  Day P&L:         ₹{metrics.day_pnl:,.2f}")
    print(f"\n💼 Position Metrics:")
    print(f"  Open Positions:  {metrics.open_positions}")
    print(f"  Total Quantity:  {metrics.total_quantity}")
    print(f"\n💰 Capital Metrics:")
    print(f"  Capital Deployed:  ₹{metrics.capital_deployed:,.2f}")
    print(f"  Margin Used:       ₹{metrics.margin_used:,.2f}")
    print(f"\n📈 Trading Metrics:")
    print(f"  Total Trades:    {metrics.total_trades}")
    print(f"  Winning Trades:  {metrics.winning_trades}")
    print(f"  Losing Trades:   {metrics.losing_trades}")
    if metrics.total_trades > 0:
        win_rate = (metrics.winning_trades / metrics.total_trades) * 100
        print(f"  Win Rate:        {win_rate:.1f}%")
    print(f"\n📊 Performance:")
    print(f"  ROI:             {metrics.roi:.2f}%")
    print(f"  Max Drawdown:    ₹{metrics.max_drawdown:,.2f}")
    print(f"  Sharpe Ratio:    {metrics.sharpe_ratio:.4f}")


def example_6_strategy_positions_and_orders():
    """Example 6: Get strategy-specific positions and orders."""
    print("\n" + "="*70)
    print("Example 6: Strategy Positions & Orders")
    print("="*70)

    client = TradingClient(api_url=API_URL, api_key=API_KEY)

    strategy = client.Strategy(
        strategy_name="Test Strategy",
        strategy_type=StrategyType.CUSTOM
    )

    # Get strategy positions
    positions = strategy.positions
    print(f"\n📍 Strategy Positions: {len(positions)}")
    for pos in positions[:5]:  # Show first 5
        print(f"  {pos.tradingsymbol}:")
        print(f"    Qty: {pos.quantity}, P&L: ₹{pos.pnl:,.2f} ({pos.pnl_percent:.2f}%)")

    # Get strategy orders
    orders = strategy.orders
    print(f"\n📋 Strategy Orders: {len(orders)}")
    for order in orders[:5]:  # Show first 5
        print(f"  {order.tradingsymbol}:")
        print(f"    {order.transaction_type} {order.quantity} @ {order.order_type}")
        print(f"    Status: {order.status}")

    # Get strategy holdings
    holdings = strategy.holdings
    print(f"\n💎 Strategy Holdings: {len(holdings)}")
    for holding in holdings[:3]:  # Show first 3
        print(f"  {holding['tradingsymbol']}: {holding['quantity']} units")


def example_7_multiple_strategies():
    """Example 7: Multiple strategies on same account."""
    print("\n" + "="*70)
    print("Example 7: Multiple Strategies")
    print("="*70)

    client = TradingClient(api_url=API_URL, api_key=API_KEY)

    # Strategy 1: Mean Reversion
    strategy1 = client.Strategy(
        strategy_name="NIFTY Mean Reversion",
        strategy_type=StrategyType.MEAN_REVERSION
    )
    print(f"✓ Strategy 1: {strategy1.strategy_name} (ID: {strategy1.strategy_id})")

    # Strategy 2: Momentum
    strategy2 = client.Strategy(
        strategy_name="BANKNIFTY Momentum",
        strategy_type=StrategyType.MOMENTUM
    )
    print(f"✓ Strategy 2: {strategy2.strategy_name} (ID: {strategy2.strategy_id})")

    # Strategy 3: Scalping
    strategy3 = client.Strategy(
        strategy_name="Intraday Scalping",
        strategy_type=StrategyType.SCALPING
    )
    print(f"✓ Strategy 3: {strategy3.strategy_name} (ID: {strategy3.strategy_id})")

    print("\nAll strategies running on same account with isolated tracking!")

    # Compare performance
    print("\n📊 Performance Comparison:")
    for strat in [strategy1, strategy2, strategy3]:
        metrics = strat.metrics
        print(f"\n  {strat.strategy_name}:")
        print(f"    P&L: ₹{metrics.total_pnl:,.2f}")
        print(f"    ROI: {metrics.roi:.2f}%")
        print(f"    Trades: {metrics.total_trades}")


def example_8_strategy_lifecycle():
    """Example 8: Strategy lifecycle management."""
    print("\n" + "="*70)
    print("Example 8: Strategy Lifecycle")
    print("="*70)

    client = TradingClient(api_url=API_URL, api_key=API_KEY)

    strategy = client.Strategy(
        strategy_name="Lifecycle Test Strategy",
        strategy_type=StrategyType.DAY_TRADING
    )

    print(f"Created: {strategy.strategy_name}")

    # Start strategy
    print("\n1. Starting strategy...")
    try:
        strategy.start()
        print("   ✓ Strategy active")
    except Exception as e:
        print(f"   ⚠ {e}")

    # Pause strategy
    print("\n2. Pausing strategy...")
    try:
        strategy.pause()
        print("   ✓ Strategy paused")
    except Exception as e:
        print(f"   ⚠ {e}")

    # Resume strategy
    print("\n3. Resuming strategy...")
    try:
        strategy.resume()
        print("   ✓ Strategy resumed")
    except Exception as e:
        print(f"   ⚠ {e}")

    # Stop strategy
    print("\n4. Stopping strategy...")
    try:
        strategy.stop()
        print("   ✓ Strategy stopped")
    except Exception as e:
        print(f"   ⚠ {e}")


def example_9_strategy_snapshots():
    """Example 9: Strategy historical snapshots."""
    print("\n" + "="*70)
    print("Example 9: Strategy Snapshots")
    print("="*70)

    client = TradingClient(api_url=API_URL, api_key=API_KEY)

    strategy = client.Strategy(
        strategy_name="Snapshot Test Strategy",
        strategy_type=StrategyType.SWING_TRADING
    )

    # Get historical snapshots
    print(f"Strategy: {strategy.strategy_name}\n")
    try:
        snapshots = strategy.get_snapshots(limit=10)
        print(f"📸 Historical Snapshots: {len(snapshots)}")

        for snapshot in snapshots[:5]:  # Show first 5
            print(f"\n  Time: {snapshot.get('snapshot_time')}")
            print(f"    P&L: ₹{snapshot.get('total_pnl', 0):,.2f}")
            print(f"    Positions: {snapshot.get('open_positions', 0)}")
            print(f"    Trades: {snapshot.get('total_trades', 0)}")
    except Exception as e:
        print(f"⚠ Error fetching snapshots: {e}")


def example_10_complete_strategy():
    """Example 10: Complete strategy implementation."""
    print("\n" + "="*70)
    print("Example 10: Complete Strategy Implementation")
    print("="*70)

    client = TradingClient(api_url=API_URL, api_key=API_KEY)

    # Configuration
    RSI_OVERSOLD = 30
    RSI_OVERBOUGHT = 70
    STOP_LOSS_PCT = -2.0
    TAKE_PROFIT_PCT = 5.0

    with client.Strategy(
        strategy_name="Complete RSI Strategy",
        strategy_type=StrategyType.MEAN_REVERSION,
        config={
            "rsi_oversold": RSI_OVERSOLD,
            "rsi_overbought": RSI_OVERBOUGHT,
            "stop_loss": STOP_LOSS_PCT,
            "take_profit": TAKE_PROFIT_PCT
        }
    ) as strategy:
        print(f"Running: {strategy.strategy_name}")
        print(f"Strategy ID: {strategy.strategy_id}\n")

        inst = client.Instrument("NIFTY25N0424500PE")

        try:
            # Get indicator
            rsi = inst['5m'].rsi[14]
            ltp = inst.ltp
            print(f"NIFTY PE:")
            print(f"  LTP: {ltp:.2f}")
            print(f"  RSI: {rsi:.2f}")

            # Check existing position
            positions = strategy.positions
            has_position = len(positions) > 0

            if has_position:
                pos = positions[0]
                print(f"\nExisting Position:")
                print(f"  Qty: {pos.quantity}")
                print(f"  P&L: ₹{pos.pnl:,.2f} ({pos.pnl_percent:.2f}%)")

                # Exit conditions
                if rsi > RSI_OVERBOUGHT:
                    print("\n  → EXIT: RSI overbought")
                    # pos.close()

                elif pos.pnl_percent < STOP_LOSS_PCT:
                    print(f"\n  → STOP LOSS: P&L {pos.pnl_percent:.2f}%")
                    # pos.close()

                elif pos.pnl_percent > TAKE_PROFIT_PCT:
                    print(f"\n  → TAKE PROFIT: P&L {pos.pnl_percent:.2f}%")
                    # pos.close()

            else:
                print("\nNo existing position")

                # Entry condition
                if rsi < RSI_OVERSOLD:
                    print(f"\n  → ENTRY: RSI oversold ({rsi:.2f})")
                    # strategy.buy(inst, quantity=50)

        except Exception as e:
            print(f"\n⚠ Error: {e}")

        # Show final metrics
        print(f"\n📊 Strategy Metrics:")
        metrics = strategy.metrics
        print(f"  Total P&L: ₹{metrics.total_pnl:,.2f}")
        print(f"  ROI: {metrics.roi:.2f}%")
        print(f"  Trades: {metrics.total_trades}")


def main():
    """Run all strategy examples."""
    print("\n" + "#"*70)
    print("# StocksBlitz SDK - Strategy Management Examples")
    print("#"*70)

    examples = [
        example_1_create_strategy,
        example_2_load_existing_strategy,
        example_3_trading_within_strategy,
        example_4_strategy_context_manager,
        example_5_strategy_metrics,
        example_6_strategy_positions_and_orders,
        example_7_multiple_strategies,
        example_8_strategy_lifecycle,
        example_9_strategy_snapshots,
        example_10_complete_strategy,
    ]

    for example in examples:
        try:
            example()
            import time
            time.sleep(1)
        except Exception as e:
            print(f"\n  ❌ Error in {example.__name__}: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "="*70)
    print("All strategy examples completed!")
    print("="*70)
    print("\nKey Features:")
    print("  ✓ Strategy isolation (orders, positions, P&L)")
    print("  ✓ Multiple strategies per account")
    print("  ✓ Automatic order-strategy linking")
    print("  ✓ Performance metrics (P&L, ROI, Sharpe, etc.)")
    print("  ✓ Historical snapshots")
    print("  ✓ Context manager support")
    print("="*70)


if __name__ == "__main__":
    main()
