#!/usr/bin/env python3
"""
Test script for new SDK features - enhanced Greeks, market depth, liquidity, futures metrics.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from stocksblitz import TradingClient
from stocksblitz.types import GreeksData, MarketDepth, LiquidityMetrics, FuturesPosition, RolloverMetrics
import json


def test_enhanced_greeks():
    """Test enhanced Greeks properties."""
    print("\n=== Testing Enhanced Greeks ===")
    
    # Create client
    client = TradingClient(
        api_url="http://localhost:8081",
        api_key="sb_test_key"  # Use a test key
    )
    
    # Create option instrument
    inst = client.Instrument("NIFTY25N0724500PE")
    
    try:
        # Test all new Greek properties
        print(f"Symbol: {inst.tradingsymbol}")
        print(f"LTP: {inst.ltp}")
        
        # Standard Greeks
        print(f"\nStandard Greeks:")
        print(f"  Delta: {inst.delta:.4f}")
        print(f"  Gamma: {inst.gamma:.4f}")
        print(f"  Theta: {inst.theta:.4f}")
        print(f"  Vega: {inst.vega:.4f}")
        print(f"  IV: {inst.iv:.2%}")
        
        # Enhanced Greeks
        print(f"\nEnhanced Greeks:")
        print(f"  Rho: {inst.rho:.4f}")
        print(f"  Intrinsic Value: {inst.intrinsic_value:.2f}")
        print(f"  Extrinsic Value: {inst.extrinsic_value:.2f}")
        print(f"  Model Price: {inst.model_price:.2f}")
        print(f"  Theta Daily: {inst.theta_daily:.4f}")
        print(f"  Premium %: {inst.premium_pct:.2f}%" if inst.premium_pct else "  Premium %: N/A")
        
        # Get all Greeks as dict
        greeks = inst.greeks
        print(f"\nGreeks State: {greeks.get('_state')}")
        
    except Exception as e:
        print(f"Error testing Greeks: {e}")


def test_market_depth():
    """Test market depth property."""
    print("\n\n=== Testing Market Depth ===")
    
    client = TradingClient(
        api_url="http://localhost:8081",
        api_key="sb_test_key"
    )
    
    inst = client.Instrument("NIFTY25N0724500PE")
    
    try:
        depth = inst.market_depth
        if depth:
            print(f"Market Depth for {inst.tradingsymbol}:")
            print(f"  Total Buy Quantity: {depth.get('total_buy_quantity')}")
            print(f"  Total Sell Quantity: {depth.get('total_sell_quantity')}")
            print(f"  Spread %: {depth.get('spread_pct', 0):.2f}%")
            print(f"  Microprice: {depth.get('microprice')}")
            print(f"  Book Pressure: {depth.get('book_pressure', 0):.2f}")
            
            if 'buy_levels' in depth and depth['buy_levels']:
                print(f"\n  Best Bid: {depth['buy_levels'][0]['price']} x {depth['buy_levels'][0]['quantity']}")
            if 'sell_levels' in depth and depth['sell_levels']:
                print(f"  Best Ask: {depth['sell_levels'][0]['price']} x {depth['sell_levels'][0]['quantity']}")
        else:
            print("Market depth not available")
            
    except Exception as e:
        print(f"Error testing market depth: {e}")


def test_liquidity_metrics():
    """Test liquidity metrics property."""
    print("\n\n=== Testing Liquidity Metrics ===")
    
    client = TradingClient(
        api_url="http://localhost:8081",
        api_key="sb_test_key"
    )
    
    inst = client.Instrument("NIFTY25N0724500PE")
    
    try:
        liquidity = inst.liquidity_metrics
        if liquidity:
            print(f"Liquidity Metrics for {inst.tradingsymbol}:")
            print(f"  Score: {liquidity.get('score', 0):.1f}/100")
            print(f"  Tier: {liquidity.get('tier')}")
            print(f"  Is Illiquid: {liquidity.get('is_illiquid', False)}")
            print(f"  Avg Spread %: {liquidity.get('spread_pct_avg', 0):.2f}%")
            print(f"  Max Spread %: {liquidity.get('spread_pct_max', 0):.2f}%")
            print(f"  Market Impact (100 units): {liquidity.get('market_impact_100', 0):.2f}")
        else:
            print("Liquidity metrics not available")
            
    except Exception as e:
        print(f"Error testing liquidity: {e}")


def test_futures_signals():
    """Test futures position signals."""
    print("\n\n=== Testing Futures Position Signals ===")
    
    client = TradingClient(
        api_url="http://localhost:8081",
        api_key="sb_test_key"
    )
    
    # Test with futures instrument
    inst = client.Instrument("NIFTY25NOVFUT")
    
    try:
        signal = inst.position_signal
        if signal:
            print(f"Position Signal for {inst.tradingsymbol}:")
            print(f"  Signal: {signal.get('signal')}")
            print(f"  Sentiment: {signal.get('sentiment')}")
            print(f"  Strength: {signal.get('strength', 0):.1f}")
            print(f"  Price Change %: {signal.get('price_change_pct', 0):.2f}%")
            print(f"  OI Change %: {signal.get('oi_change_pct', 0):.2f}%")
        else:
            print("Position signal not available (may not be a futures instrument)")
            
    except Exception as e:
        print(f"Error testing futures signals: {e}")


def test_rollover_metrics():
    """Test futures rollover metrics."""
    print("\n\n=== Testing Rollover Metrics ===")
    
    client = TradingClient(
        api_url="http://localhost:8081",
        api_key="sb_test_key"
    )
    
    inst = client.Instrument("NIFTY25NOVFUT")
    
    try:
        rollover = inst.rollover_metrics
        if rollover:
            print(f"Rollover Metrics for {inst.tradingsymbol}:")
            print(f"  Pressure: {rollover.get('pressure', 0):.1f}/100")
            print(f"  OI %: {rollover.get('oi_pct', 0):.1f}%")
            print(f"  Days to Expiry: {rollover.get('days_to_expiry')}")
            print(f"  Status: {rollover.get('status')}")
            print(f"  Recommended Target: {rollover.get('recommended_target', 'None')}")
        else:
            print("Rollover metrics not available")
            
    except Exception as e:
        print(f"Error testing rollover metrics: {e}")


def test_fo_client_methods():
    """Test new FO-specific client methods."""
    print("\n\n=== Testing FO Client Methods ===")
    
    client = TradingClient(
        api_url="http://localhost:8081", 
        api_key="sb_test_key"
    )
    
    try:
        # Test strike distribution
        print("\n1. Strike Distribution:")
        distribution = client.get_fo_strike_distribution(
            symbol="NIFTY",
            expiry="2025-11-28",
            indicators=["RSI:14", "SMA:20"]
        )
        print(f"   Got {len(distribution.get('strikes', []))} strikes")
        
        # Test expiry metrics
        print("\n2. Expiry Metrics:")
        metrics = client.get_fo_expiry_metrics("NIFTY")
        if 'expiries' in metrics:
            for expiry in metrics['expiries'][:3]:  # Show first 3
                print(f"   {expiry.get('expiry')}: OI={expiry.get('oi_pct', 0):.1f}%, Pressure={expiry.get('rollover_pressure', 0):.0f}")
        
        # Test futures position signals
        print("\n3. Futures Position Signals:")
        signals = client.get_futures_position_signals("NIFTY")
        print(f"   Signal: {signals.get('signal')}, Sentiment: {signals.get('sentiment')}")
        
        # Test option liquidity metrics
        print("\n4. Option Liquidity Metrics:")
        liquidity = client.get_option_liquidity_metrics(
            symbol="NIFTY",
            strike=24500,
            expiry="2025-11-28"
        )
        print(f"   Liquidity Score: {liquidity.get('score', 0):.0f}, Tier: {liquidity.get('tier')}")
        
    except Exception as e:
        print(f"Error testing FO client methods: {e}")


def test_data_models():
    """Test that data models are properly defined."""
    print("\n\n=== Testing Data Models ===")
    
    # Test GreeksData
    greeks = GreeksData(
        symbol="TEST",
        delta=0.5,
        gamma=0.02,
        theta=-0.05,
        vega=0.1,
        iv=0.25,
        rho=0.03,
        intrinsic_value=100,
        extrinsic_value=50,
        model_price=150,
        theta_daily=-0.0001,
        premium_pct=2.5
    )
    print(f"GreeksData created: rho={greeks.rho}, intrinsic={greeks.intrinsic_value}")
    
    # Test other models
    print("MarketDepth model imported successfully")
    print("LiquidityMetrics model imported successfully")
    print("FuturesPosition model imported successfully")
    print("RolloverMetrics model imported successfully")


if __name__ == "__main__":
    print("Testing new SDK features...")
    print("=" * 60)
    
    # Run all tests
    test_enhanced_greeks()
    test_market_depth()
    test_liquidity_metrics()
    test_futures_signals()
    test_rollover_metrics()
    test_fo_client_methods()
    test_data_models()
    
    print("\n" + "=" * 60)
    print("Testing complete!")