"""
Market Depth Analyzer

Computes liquidity metrics, spread analysis, order book imbalance,
and market impact costs from market depth data.

Usage:
    analyzer = MarketDepthAnalyzer()
    metrics = analyzer.analyze(tick['depth'], tick['last_price'])
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class DepthLevel:
    """Single level in the order book."""
    quantity: int
    price: float
    orders: int


@dataclass
class SpreadMetrics:
    """Spread-related metrics."""
    bid_ask_spread_abs: float
    bid_ask_spread_pct: float
    mid_price: float
    weighted_mid_price: float
    best_bid: float
    best_ask: float


@dataclass
class DepthMetrics:
    """Order book depth metrics."""
    total_bid_quantity: int
    total_ask_quantity: int
    total_bid_value: float
    total_ask_value: float
    depth_at_best_bid: int
    depth_at_best_ask: int
    total_orders_bid: int
    total_orders_ask: int
    avg_order_size_bid: float
    avg_order_size_ask: float


@dataclass
class ImbalanceMetrics:
    """Order book imbalance metrics."""
    depth_imbalance_ratio: float
    depth_imbalance_pct: float
    order_imbalance_ratio: float
    volume_imbalance: int
    value_imbalance: float
    book_pressure: float  # Normalized [-1, 1]


@dataclass
class LiquidityMetrics:
    """Liquidity scoring and classification."""
    liquidity_score: float  # 0-100
    liquidity_tier: str  # HIGH/MEDIUM/LOW/ILLIQUID
    illiquidity_flags: Dict[str, bool]


@dataclass
class AdvancedMetrics:
    """Advanced market microstructure metrics."""
    microprice: float
    market_impact_cost_100: float
    market_impact_cost_500: float
    effective_spread_100_pct: float
    depth_concentration_bid: Dict[str, float]
    depth_concentration_ask: Dict[str, float]


@dataclass
class MarketDepthAnalysis:
    """Complete market depth analysis."""
    spread: SpreadMetrics
    depth: DepthMetrics
    imbalance: ImbalanceMetrics
    liquidity: LiquidityMetrics
    advanced: Optional[AdvancedMetrics] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "spread": asdict(self.spread),
            "depth": asdict(self.depth),
            "imbalance": asdict(self.imbalance),
            "liquidity": asdict(self.liquidity),
            "advanced": asdict(self.advanced) if self.advanced else None
        }

    def to_flat_dict(self) -> dict:
        """Convert to flat dictionary (all metrics at top level)."""
        result = {}
        result.update(asdict(self.spread))
        result.update(asdict(self.depth))
        result.update(asdict(self.imbalance))
        result.update(asdict(self.liquidity))
        if self.advanced:
            result.update(asdict(self.advanced))
        return result


class MarketDepthAnalyzer:
    """
    Analyzes market depth data and computes liquidity metrics.

    Computes:
    - Spread metrics (absolute, percentage, mid-price)
    - Depth metrics (quantities, values, order counts)
    - Imbalance metrics (book pressure, flow detection)
    - Liquidity scoring (composite metric 0-100)
    - Advanced metrics (microprice, market impact)
    """

    def __init__(
        self,
        include_advanced: bool = True,
        min_liquid_score: float = 60.0,
        max_spread_pct: float = 0.5
    ):
        """
        Initialize analyzer.

        Args:
            include_advanced: Whether to compute advanced metrics (default: True)
            min_liquid_score: Minimum score for "liquid" classification (default: 60)
            max_spread_pct: Max spread % for liquid instruments (default: 0.5%)
        """
        self.include_advanced = include_advanced
        self.min_liquid_score = min_liquid_score
        self.max_spread_pct = max_spread_pct

    def analyze(
        self,
        depth_data: Dict,
        last_price: float,
        instrument_token: Optional[int] = None
    ) -> MarketDepthAnalysis:
        """
        Analyze market depth and compute all metrics.

        Args:
            depth_data: Market depth dict with 'buy' and 'sell' arrays
            last_price: Last traded price
            instrument_token: Optional instrument identifier for logging

        Returns:
            MarketDepthAnalysis with all computed metrics
        """
        buy_levels = self._parse_depth_levels(depth_data.get("buy", []))
        sell_levels = self._parse_depth_levels(depth_data.get("sell", []))

        if not buy_levels or not sell_levels:
            logger.warning(
                f"Empty depth data for instrument {instrument_token}, "
                f"buy_levels={len(buy_levels)}, sell_levels={len(sell_levels)}"
            )
            return self._empty_analysis(last_price)

        # Compute all metric groups
        spread = self._compute_spread_metrics(buy_levels, sell_levels, last_price)
        depth = self._compute_depth_metrics(buy_levels, sell_levels)
        imbalance = self._compute_imbalance_metrics(depth, spread)
        liquidity = self._compute_liquidity_metrics(spread, depth, imbalance)

        advanced = None
        if self.include_advanced:
            advanced = self._compute_advanced_metrics(buy_levels, sell_levels, spread, depth)

        return MarketDepthAnalysis(
            spread=spread,
            depth=depth,
            imbalance=imbalance,
            liquidity=liquidity,
            advanced=advanced
        )

    def _parse_depth_levels(self, levels: List[Dict]) -> List[DepthLevel]:
        """Parse depth levels from raw data."""
        parsed = []
        for level in levels:
            try:
                parsed.append(DepthLevel(
                    quantity=int(level.get("quantity", 0)),
                    price=float(level.get("price", 0)),
                    orders=int(level.get("orders", 0))
                ))
            except (ValueError, TypeError) as e:
                logger.warning(f"Failed to parse depth level {level}: {e}")
                continue
        return parsed

    def _compute_spread_metrics(
        self,
        buy_levels: List[DepthLevel],
        sell_levels: List[DepthLevel],
        last_price: float
    ) -> SpreadMetrics:
        """Compute spread-related metrics."""
        best_bid = buy_levels[0].price
        best_ask = sell_levels[0].price

        # Basic spread
        spread_abs = best_ask - best_bid
        mid_price = (best_bid + best_ask) / 2.0

        # Spread as percentage of mid price
        spread_pct = (spread_abs / mid_price) * 100.0 if mid_price > 0 else 0.0

        # Weighted mid-price (volume-weighted)
        bid_qty = buy_levels[0].quantity
        ask_qty = sell_levels[0].quantity
        total_qty = bid_qty + ask_qty

        if total_qty > 0:
            weighted_mid = (best_bid * ask_qty + best_ask * bid_qty) / total_qty
        else:
            weighted_mid = mid_price

        return SpreadMetrics(
            bid_ask_spread_abs=round(spread_abs, 2),
            bid_ask_spread_pct=round(spread_pct, 4),
            mid_price=round(mid_price, 2),
            weighted_mid_price=round(weighted_mid, 2),
            best_bid=round(best_bid, 2),
            best_ask=round(best_ask, 2)
        )

    def _compute_depth_metrics(
        self,
        buy_levels: List[DepthLevel],
        sell_levels: List[DepthLevel]
    ) -> DepthMetrics:
        """Compute order book depth metrics."""
        # Total quantities
        total_bid_qty = sum(level.quantity for level in buy_levels)
        total_ask_qty = sum(level.quantity for level in sell_levels)

        # Total values (price * quantity)
        total_bid_value = sum(level.price * level.quantity for level in buy_levels)
        total_ask_value = sum(level.price * level.quantity for level in sell_levels)

        # Depth at best levels
        depth_at_best_bid = buy_levels[0].quantity
        depth_at_best_ask = sell_levels[0].quantity

        # Order counts
        total_orders_bid = sum(level.orders for level in buy_levels)
        total_orders_ask = sum(level.orders for level in sell_levels)

        # Average order sizes
        avg_order_size_bid = total_bid_qty / total_orders_bid if total_orders_bid > 0 else 0
        avg_order_size_ask = total_ask_qty / total_orders_ask if total_orders_ask > 0 else 0

        return DepthMetrics(
            total_bid_quantity=total_bid_qty,
            total_ask_quantity=total_ask_qty,
            total_bid_value=round(total_bid_value, 2),
            total_ask_value=round(total_ask_value, 2),
            depth_at_best_bid=depth_at_best_bid,
            depth_at_best_ask=depth_at_best_ask,
            total_orders_bid=total_orders_bid,
            total_orders_ask=total_orders_ask,
            avg_order_size_bid=round(avg_order_size_bid, 2),
            avg_order_size_ask=round(avg_order_size_ask, 2)
        )

    def _compute_imbalance_metrics(
        self,
        depth: DepthMetrics,
        spread: SpreadMetrics
    ) -> ImbalanceMetrics:
        """Compute order book imbalance metrics."""
        bid_qty = depth.total_bid_quantity
        ask_qty = depth.total_ask_quantity
        bid_orders = depth.total_orders_bid
        ask_orders = depth.total_orders_ask

        # Depth imbalance ratio
        depth_ratio = bid_qty / ask_qty if ask_qty > 0 else 1.0

        # Depth imbalance percentage: (bid - ask) / (bid + ask) * 100
        total_qty = bid_qty + ask_qty
        depth_imbalance_pct = ((bid_qty - ask_qty) / total_qty * 100.0) if total_qty > 0 else 0.0

        # Order imbalance ratio
        order_ratio = bid_orders / ask_orders if ask_orders > 0 else 1.0

        # Volume imbalance (absolute difference)
        volume_imbalance = bid_qty - ask_qty

        # Value imbalance
        value_imbalance = depth.total_bid_value - depth.total_ask_value

        # Book pressure: normalized to [-1, 1]
        # -1 = strong sell pressure, 0 = balanced, +1 = strong buy pressure
        book_pressure = depth_imbalance_pct / 100.0  # Convert to [-1, 1]
        book_pressure = max(-1.0, min(1.0, book_pressure))  # Clamp

        return ImbalanceMetrics(
            depth_imbalance_ratio=round(depth_ratio, 3),
            depth_imbalance_pct=round(depth_imbalance_pct, 2),
            order_imbalance_ratio=round(order_ratio, 3),
            volume_imbalance=volume_imbalance,
            value_imbalance=round(value_imbalance, 2),
            book_pressure=round(book_pressure, 4)
        )

    def _compute_liquidity_metrics(
        self,
        spread: SpreadMetrics,
        depth: DepthMetrics,
        imbalance: ImbalanceMetrics
    ) -> LiquidityMetrics:
        """
        Compute liquidity score and classification.

        Score components (0-100 scale):
        - Spread tightness: 40% weight
        - Total depth: 30% weight
        - Order count: 20% weight
        - Book balance: 10% weight
        """
        # Component 1: Spread tightness (40% weight)
        # Lower spread = higher score
        spread_score = max(0, 100 - min(spread.bid_ask_spread_pct * 200, 100))

        # Component 2: Depth score (30% weight)
        # Normalize total depth (assuming 1000 is very liquid)
        total_depth = depth.total_bid_quantity + depth.total_ask_quantity
        depth_score = min(total_depth / 10, 100)

        # Component 3: Order count score (20% weight)
        # More orders = better liquidity
        total_orders = depth.total_orders_bid + depth.total_orders_ask
        order_score = min(total_orders, 100)

        # Component 4: Book balance score (10% weight)
        # Balanced book = better liquidity
        balance_score = max(0, 100 - abs(imbalance.depth_imbalance_pct) * 2)

        # Weighted composite score
        liquidity_score = (
            spread_score * 0.40 +
            depth_score * 0.30 +
            order_score * 0.20 +
            balance_score * 0.10
        )

        # Classify liquidity tier
        if liquidity_score >= 80:
            tier = "HIGH"
        elif liquidity_score >= 60:
            tier = "MEDIUM"
        elif liquidity_score >= 40:
            tier = "LOW"
        else:
            tier = "ILLIQUID"

        # Illiquidity flags
        flags = {
            "wide_spread": spread.bid_ask_spread_pct > self.max_spread_pct,
            "thin_depth": total_depth < 500,
            "few_orders": total_orders < 50,
            "imbalanced_book": abs(imbalance.depth_imbalance_pct) > 20.0,
            "low_best_depth": min(depth.depth_at_best_bid, depth.depth_at_best_ask) < 50
        }

        return LiquidityMetrics(
            liquidity_score=round(liquidity_score, 2),
            liquidity_tier=tier,
            illiquidity_flags=flags
        )

    def _compute_advanced_metrics(
        self,
        buy_levels: List[DepthLevel],
        sell_levels: List[DepthLevel],
        spread: SpreadMetrics,
        depth: DepthMetrics
    ) -> AdvancedMetrics:
        """Compute advanced microstructure metrics."""
        # Microprice (probability-weighted fair value)
        bid_qty = buy_levels[0].quantity
        ask_qty = sell_levels[0].quantity
        total_qty = bid_qty + ask_qty

        if total_qty > 0:
            microprice = (spread.best_bid * ask_qty + spread.best_ask * bid_qty) / total_qty
        else:
            microprice = spread.mid_price

        # Market impact cost for different sizes
        impact_100 = self._compute_market_impact(buy_levels, sell_levels, 100)
        impact_500 = self._compute_market_impact(buy_levels, sell_levels, 500)

        # Effective spread for 100 units (as percentage)
        effective_spread_100 = (impact_100 / spread.mid_price * 100.0) if spread.mid_price > 0 else 0.0

        # Depth concentration (how much depth is at top levels)
        bid_concentration = self._compute_depth_concentration(buy_levels)
        ask_concentration = self._compute_depth_concentration(sell_levels)

        return AdvancedMetrics(
            microprice=round(microprice, 2),
            market_impact_cost_100=round(impact_100, 2),
            market_impact_cost_500=round(impact_500, 2),
            effective_spread_100_pct=round(effective_spread_100, 4),
            depth_concentration_bid=bid_concentration,
            depth_concentration_ask=ask_concentration
        )

    def _compute_market_impact(
        self,
        buy_levels: List[DepthLevel],
        sell_levels: List[DepthLevel],
        size: int
    ) -> float:
        """
        Compute market impact cost to execute a given size.

        Assumes you're a buyer walking up the sell side (or vice versa).
        Returns the average price slippage cost.
        """
        # To buy, we consume the sell side
        levels = sell_levels
        mid_price = (buy_levels[0].price + sell_levels[0].price) / 2.0

        remaining = size
        total_cost = 0.0

        for level in levels:
            if remaining <= 0:
                break

            qty_at_level = min(remaining, level.quantity)
            total_cost += qty_at_level * level.price
            remaining -= qty_at_level

        if remaining > 0:
            # Not enough depth - use last level price
            total_cost += remaining * levels[-1].price

        avg_execution_price = total_cost / size if size > 0 else mid_price
        impact_cost = avg_execution_price - mid_price

        return impact_cost

    def _compute_depth_concentration(self, levels: List[DepthLevel]) -> Dict[str, float]:
        """
        Compute how concentrated the depth is at top levels.

        Returns percentage of total depth at:
        - Level 1 (best price)
        - Top 3 levels
        - Top 5 levels
        """
        if not levels:
            return {"top1_pct": 0.0, "top3_pct": 0.0, "top5_pct": 0.0}

        total_depth = sum(level.quantity for level in levels)

        if total_depth == 0:
            return {"top1_pct": 0.0, "top3_pct": 0.0, "top5_pct": 0.0}

        top1 = levels[0].quantity
        top3 = sum(level.quantity for level in levels[:3])
        top5 = sum(level.quantity for level in levels[:5])

        return {
            "top1_pct": round((top1 / total_depth) * 100, 2),
            "top3_pct": round((top3 / total_depth) * 100, 2),
            "top5_pct": round((top5 / total_depth) * 100, 2)
        }

    def _empty_analysis(self, last_price: float) -> MarketDepthAnalysis:
        """Return empty/default analysis when depth data is missing."""
        return MarketDepthAnalysis(
            spread=SpreadMetrics(
                bid_ask_spread_abs=0.0,
                bid_ask_spread_pct=0.0,
                mid_price=last_price,
                weighted_mid_price=last_price,
                best_bid=last_price,
                best_ask=last_price
            ),
            depth=DepthMetrics(
                total_bid_quantity=0,
                total_ask_quantity=0,
                total_bid_value=0.0,
                total_ask_value=0.0,
                depth_at_best_bid=0,
                depth_at_best_ask=0,
                total_orders_bid=0,
                total_orders_ask=0,
                avg_order_size_bid=0.0,
                avg_order_size_ask=0.0
            ),
            imbalance=ImbalanceMetrics(
                depth_imbalance_ratio=1.0,
                depth_imbalance_pct=0.0,
                order_imbalance_ratio=1.0,
                volume_imbalance=0,
                value_imbalance=0.0,
                book_pressure=0.0
            ),
            liquidity=LiquidityMetrics(
                liquidity_score=0.0,
                liquidity_tier="ILLIQUID",
                illiquidity_flags={
                    "wide_spread": True,
                    "thin_depth": True,
                    "few_orders": True,
                    "imbalanced_book": False,
                    "low_best_depth": True
                }
            ),
            advanced=None
        )


# Convenience function for quick analysis
def analyze_market_depth(
    depth_data: Dict,
    last_price: float,
    include_advanced: bool = False
) -> Dict:
    """
    Quick analysis function.

    Args:
        depth_data: Market depth dict with 'buy' and 'sell' arrays
        last_price: Last traded price
        include_advanced: Whether to compute advanced metrics

    Returns:
        Dictionary with all metrics
    """
    analyzer = MarketDepthAnalyzer(include_advanced=include_advanced)
    analysis = analyzer.analyze(depth_data, last_price)
    return analysis.to_dict()
