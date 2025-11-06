"""
Test Market Depth Analyzer

Demonstrates the MarketDepthAnalyzer with sample data.
"""

import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.market_depth_analyzer import MarketDepthAnalyzer


def test_liquid_instrument():
    """Test with liquid instrument (tight spread, good depth)."""
    print("\n" + "="*80)
    print("TEST 1: Liquid NIFTY Future")
    print("="*80)

    depth_data = {
        "buy": [
            {"quantity": 750, "price": 25600.00, "orders": 15},
            {"quantity": 1500, "price": 25599.50, "orders": 25},
            {"quantity": 2000, "price": 25599.00, "orders": 35},
            {"quantity": 1000, "price": 25598.50, "orders": 18},
            {"quantity": 1250, "price": 25598.00, "orders": 22}
        ],
        "sell": [
            {"quantity": 1000, "price": 25600.50, "orders": 18},
            {"quantity": 1750, "price": 25601.00, "orders": 28},
            {"quantity": 1500, "price": 25601.50, "orders": 24},
            {"quantity": 2000, "price": 25602.00, "orders": 32},
            {"quantity": 1250, "price": 25602.50, "orders": 20}
        ]
    }

    analyzer = MarketDepthAnalyzer(include_advanced=True)
    analysis = analyzer.analyze(depth_data, last_price=25600.25)

    print_analysis(analysis)


def test_illiquid_option():
    """Test with illiquid option (wide spread, thin depth)."""
    print("\n" + "="*80)
    print("TEST 2: Illiquid OTM Option")
    print("="*80)

    depth_data = {
        "buy": [
            {"quantity": 25, "price": 45.00, "orders": 1},
            {"quantity": 50, "price": 44.50, "orders": 2},
            {"quantity": 75, "price": 44.00, "orders": 3},
            {"quantity": 25, "price": 43.50, "orders": 1},
            {"quantity": 50, "price": 43.00, "orders": 2}
        ],
        "sell": [
            {"quantity": 50, "price": 46.50, "orders": 2},
            {"quantity": 75, "price": 47.00, "orders": 3},
            {"quantity": 50, "price": 47.50, "orders": 2},
            {"quantity": 100, "price": 48.00, "orders": 4},
            {"quantity": 50, "price": 48.50, "orders": 2}
        ]
    }

    analyzer = MarketDepthAnalyzer(include_advanced=True)
    analysis = analyzer.analyze(depth_data, last_price=45.75)

    print_analysis(analysis)


def test_imbalanced_book():
    """Test with strong buy pressure (imbalanced book)."""
    print("\n" + "="*80)
    print("TEST 3: Imbalanced Book - Strong Buy Pressure")
    print("="*80)

    depth_data = {
        "buy": [
            {"quantity": 2000, "price": 25600.00, "orders": 40},
            {"quantity": 3000, "price": 25599.50, "orders": 55},
            {"quantity": 2500, "price": 25599.00, "orders": 48},
            {"quantity": 2000, "price": 25598.50, "orders": 38},
            {"quantity": 1500, "price": 25598.00, "orders": 28}
        ],
        "sell": [
            {"quantity": 500, "price": 25600.50, "orders": 10},
            {"quantity": 750, "price": 25601.00, "orders": 14},
            {"quantity": 600, "price": 25601.50, "orders": 11},
            {"quantity": 800, "price": 25602.00, "orders": 15},
            {"quantity": 500, "price": 25602.50, "orders": 9}
        ]
    }

    analyzer = MarketDepthAnalyzer(include_advanced=True)
    analysis = analyzer.analyze(depth_data, last_price=25600.25)

    print_analysis(analysis)


def print_analysis(analysis):
    """Pretty print analysis results."""
    print("\n📊 SPREAD METRICS:")
    print(f"  Bid-Ask Spread:     ₹{analysis.spread.bid_ask_spread_abs:.2f} ({analysis.spread.bid_ask_spread_pct:.4f}%)")
    print(f"  Mid Price:          ₹{analysis.spread.mid_price:.2f}")
    print(f"  Weighted Mid:       ₹{analysis.spread.weighted_mid_price:.2f}")
    print(f"  Best Bid/Ask:       ₹{analysis.spread.best_bid:.2f} / ₹{analysis.spread.best_ask:.2f}")

    print("\n📈 DEPTH METRICS:")
    print(f"  Total Bid Quantity: {analysis.depth.total_bid_quantity:,}")
    print(f"  Total Ask Quantity: {analysis.depth.total_ask_quantity:,}")
    print(f"  Depth at Best:      {analysis.depth.depth_at_best_bid} / {analysis.depth.depth_at_best_ask}")
    print(f"  Total Orders:       {analysis.depth.total_orders_bid} / {analysis.depth.total_orders_ask}")
    print(f"  Avg Order Size:     {analysis.depth.avg_order_size_bid:.0f} / {analysis.depth.avg_order_size_ask:.0f}")

    print("\n⚖️  IMBALANCE METRICS:")
    print(f"  Depth Imbalance:    {analysis.imbalance.depth_imbalance_pct:+.2f}%")
    print(f"  Book Pressure:      {analysis.imbalance.book_pressure:+.4f}")
    print(f"  Volume Imbalance:   {analysis.imbalance.volume_imbalance:+,}")

    if analysis.imbalance.book_pressure > 0.15:
        print(f"  → 🟢 Strong BUY pressure")
    elif analysis.imbalance.book_pressure < -0.15:
        print(f"  → 🔴 Strong SELL pressure")
    else:
        print(f"  → ⚪ Balanced book")

    print("\n💧 LIQUIDITY METRICS:")
    print(f"  Liquidity Score:    {analysis.liquidity.liquidity_score:.2f}/100")
    print(f"  Liquidity Tier:     {analysis.liquidity.liquidity_tier}")

    print(f"\n  Illiquidity Flags:")
    for flag, value in analysis.liquidity.illiquidity_flags.items():
        status = "⚠️ " if value else "✅"
        print(f"    {status} {flag}: {value}")

    if analysis.advanced:
        print("\n🔬 ADVANCED METRICS:")
        print(f"  Microprice:         ₹{analysis.advanced.microprice:.2f}")
        print(f"  Market Impact:")
        print(f"    - 100 units:      ₹{analysis.advanced.market_impact_cost_100:.2f}")
        print(f"    - 500 units:      ₹{analysis.advanced.market_impact_cost_500:.2f}")
        print(f"  Effective Spread:   {analysis.advanced.effective_spread_100_pct:.4f}%")
        print(f"\n  Depth Concentration:")
        print(f"    Bid - Top 1: {analysis.advanced.depth_concentration_bid['top1_pct']:.1f}%")
        print(f"    Bid - Top 3: {analysis.advanced.depth_concentration_bid['top3_pct']:.1f}%")
        print(f"    Ask - Top 1: {analysis.advanced.depth_concentration_ask['top1_pct']:.1f}%")
        print(f"    Ask - Top 3: {analysis.advanced.depth_concentration_ask['top3_pct']:.1f}%")

    print("\n" + "─"*80)

    # Trading recommendations
    print("\n💡 TRADING RECOMMENDATIONS:")

    if analysis.liquidity.liquidity_score >= 70:
        print("  ✅ LIQUID - Market orders acceptable")
    elif analysis.liquidity.liquidity_score >= 50:
        print("  ⚠️  MEDIUM - Use limit orders at mid-price")
    else:
        print("  ❌ ILLIQUID - Avoid or use passive limits only")

    if analysis.spread.bid_ask_spread_pct > 0.5:
        print("  ⚠️  Wide spread - Consider limit orders")

    if abs(analysis.imbalance.book_pressure) > 0.20:
        direction = "BUY" if analysis.imbalance.book_pressure < 0 else "SELL"
        print(f"  💎 Strong pressure favors {direction} side - Good entry opportunity")


if __name__ == "__main__":
    print("\n🧪 Market Depth Analyzer - Test Suite")

    test_liquid_instrument()
    test_illiquid_option()
    test_imbalanced_book()

    print("\n✅ All tests completed!\n")
