"""
Condition Evaluator Service
Evaluates alert conditions by fetching market data and comparing against thresholds
"""

import logging
from datetime import datetime
from typing import Dict, Any, Optional
import httpx

from ..config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class EvaluationResult:
    """Result of condition evaluation."""

    def __init__(
        self,
        matched: bool,
        current_value: Optional[float] = None,
        threshold: Optional[float] = None,
        details: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ):
        self.matched = matched
        self.current_value = current_value
        self.threshold = threshold
        self.details = details or {}
        self.error = error
        self.evaluated_at = datetime.utcnow()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "matched": self.matched,
            "current_value": self.current_value,
            "threshold": self.threshold,
            "details": self.details,
            "error": self.error,
            "evaluated_at": self.evaluated_at.isoformat(),
        }


class ConditionEvaluator:
    """
    Evaluates alert conditions by fetching market data.

    Supports:
    - Price conditions (LTP from ticker_service)
    - Indicator conditions (RSI, MACD, etc. from backend)
    - Position conditions (P&L, exposure from backend)
    - Greek conditions (delta, gamma, etc. from backend)
    - Time conditions (market hours, time-based)
    - Composite conditions (AND/OR logic)
    """

    def __init__(
        self,
        ticker_service_url: Optional[str] = None,
        backend_url: Optional[str] = None,
        timeout_seconds: float = 5.0,
    ):
        self.ticker_service_url = ticker_service_url or settings.ticker_service_url
        self.backend_url = backend_url or settings.backend_url
        self.timeout = timeout_seconds
        self.client = httpx.AsyncClient(timeout=self.timeout)

    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()

    async def evaluate(self, condition_config: Dict[str, Any]) -> EvaluationResult:
        """
        Evaluate a condition based on its type.

        Args:
            condition_config: Condition configuration (JSONB from database)

        Returns:
            EvaluationResult with matched status and details
        """
        condition_type = condition_config.get("type", "")

        try:
            if condition_type == "price":
                return await self.evaluate_price(condition_config)
            elif condition_type == "indicator":
                return await self.evaluate_indicator(condition_config)
            elif condition_type == "position":
                return await self.evaluate_position(condition_config)
            elif condition_type == "greek":
                return await self.evaluate_greek(condition_config)
            elif condition_type == "time":
                return await self.evaluate_time(condition_config)
            elif condition_type == "composite":
                return await self.evaluate_composite(condition_config)
            elif condition_type == "custom":
                return await self.evaluate_custom(condition_config)
            else:
                return EvaluationResult(
                    matched=False,
                    error=f"Unknown condition type: {condition_type}"
                )

        except Exception as e:
            logger.error(f"Error evaluating condition {condition_type}: {e}", exc_info=True)
            return EvaluationResult(
                matched=False,
                error=f"Evaluation error: {str(e)}"
            )

    async def evaluate_price(self, config: Dict[str, Any]) -> EvaluationResult:
        """
        Evaluate price condition.

        Fetches LTP from ticker_service and compares against threshold.

        Config format:
        {
            "type": "price",
            "symbol": "NIFTY50",
            "operator": "gt",  # gt, gte, lt, lte, eq, between
            "threshold": 24000,
            "comparison": "last_price"  # last_price, bid, ask, close
        }
        """
        symbol = config.get("symbol", "")
        operator = config.get("operator", "gt")
        threshold = float(config.get("threshold", 0))
        comparison = config.get("comparison", "last_price")

        if not symbol:
            return EvaluationResult(matched=False, error="Symbol is required")

        # Fetch price from ticker_service
        try:
            # Try live LTP endpoint first
            response = await self.client.get(
                f"{self.ticker_service_url}/live/{symbol}"
            )

            if response.status_code == 200:
                data = response.json()
                current_price = data.get("last_price") or data.get("ltp")
            else:
                # Fallback: try quotes endpoint
                response = await self.client.get(
                    f"{self.ticker_service_url}/quotes/{symbol}"
                )
                if response.status_code != 200:
                    return EvaluationResult(
                        matched=False,
                        error=f"Failed to fetch price for {symbol}: {response.status_code}"
                    )
                data = response.json()
                current_price = data.get("last_price")

            if current_price is None:
                return EvaluationResult(
                    matched=False,
                    error=f"No price data for {symbol}"
                )

            current_price = float(current_price)

            # Compare using operator
            matched = self._compare_values(current_price, operator, threshold)

            return EvaluationResult(
                matched=matched,
                current_value=current_price,
                threshold=threshold,
                details={
                    "symbol": symbol,
                    "operator": operator,
                    "comparison": comparison,
                }
            )

        except httpx.RequestError as e:
            logger.error(f"Network error fetching price for {symbol}: {e}")
            return EvaluationResult(
                matched=False,
                error=f"Network error: {str(e)}"
            )

    async def evaluate_indicator(self, config: Dict[str, Any]) -> EvaluationResult:
        """
        Evaluate indicator condition.

        Fetches technical indicators from backend.

        Config format:
        {
            "type": "indicator",
            "symbol": "NIFTY50",
            "indicator": "rsi",
            "timeframe": "5min",
            "operator": "gt",
            "threshold": 70,
            "lookback_periods": 14
        }
        """
        symbol = config.get("symbol", "")
        indicator = config.get("indicator", "").lower()
        timeframe = config.get("timeframe", "5min")
        operator = config.get("operator", "gt")
        threshold = float(config.get("threshold", 0))
        lookback = config.get("lookback_periods", 14)

        if not symbol or not indicator:
            return EvaluationResult(
                matched=False,
                error="Symbol and indicator are required"
            )

        try:
            # Fetch indicator from backend
            # Assuming backend has endpoint: /api/indicators/{symbol}/{indicator}
            response = await self.client.get(
                f"{self.backend_url}/api/indicators/{symbol}/{indicator}",
                params={
                    "timeframe": timeframe,
                    "lookback": lookback,
                }
            )

            if response.status_code != 200:
                return EvaluationResult(
                    matched=False,
                    error=f"Failed to fetch {indicator} for {symbol}: {response.status_code}"
                )

            data = response.json()
            current_value = data.get("value") or data.get(indicator)

            if current_value is None:
                return EvaluationResult(
                    matched=False,
                    error=f"No {indicator} data for {symbol}"
                )

            current_value = float(current_value)

            # Compare using operator
            matched = self._compare_values(current_value, operator, threshold)

            return EvaluationResult(
                matched=matched,
                current_value=current_value,
                threshold=threshold,
                details={
                    "symbol": symbol,
                    "indicator": indicator,
                    "timeframe": timeframe,
                    "operator": operator,
                }
            )

        except httpx.RequestError as e:
            logger.error(f"Network error fetching {indicator} for {symbol}: {e}")
            return EvaluationResult(
                matched=False,
                error=f"Network error: {str(e)}"
            )

    async def evaluate_position(self, config: Dict[str, Any]) -> EvaluationResult:
        """
        Evaluate position condition.

        Fetches position data from backend (P&L, exposure, etc.).

        Config format:
        {
            "type": "position",
            "metric": "pnl",  # pnl, exposure, quantity
            "operator": "lt",
            "threshold": -5000,
            "symbol": "NIFTY50",  # optional, for specific position
            "account_id": "kite_primary"  # optional
        }
        """
        metric = config.get("metric", "pnl")
        operator = config.get("operator", "lt")
        threshold = float(config.get("threshold", 0))
        symbol = config.get("symbol")
        account_id = config.get("account_id")

        try:
            # Fetch positions from backend
            params = {}
            if account_id:
                params["account_id"] = account_id

            response = await self.client.get(
                f"{self.backend_url}/api/positions",
                params=params
            )

            if response.status_code != 200:
                return EvaluationResult(
                    matched=False,
                    error=f"Failed to fetch positions: {response.status_code}"
                )

            data = response.json()
            positions = data.get("positions", [])

            # Filter by symbol if specified
            if symbol:
                positions = [p for p in positions if p.get("symbol") == symbol]

            # Calculate metric
            if metric == "pnl":
                current_value = sum(float(p.get("pnl", 0)) for p in positions)
            elif metric == "exposure":
                current_value = sum(float(p.get("exposure", 0)) for p in positions)
            elif metric == "quantity":
                current_value = sum(float(p.get("quantity", 0)) for p in positions)
            else:
                return EvaluationResult(
                    matched=False,
                    error=f"Unknown metric: {metric}"
                )

            # Compare using operator
            matched = self._compare_values(current_value, operator, threshold)

            return EvaluationResult(
                matched=matched,
                current_value=current_value,
                threshold=threshold,
                details={
                    "metric": metric,
                    "operator": operator,
                    "symbol": symbol,
                    "position_count": len(positions),
                }
            )

        except httpx.RequestError as e:
            logger.error(f"Network error fetching positions: {e}")
            return EvaluationResult(
                matched=False,
                error=f"Network error: {str(e)}"
            )

    async def evaluate_greek(self, config: Dict[str, Any]) -> EvaluationResult:
        """
        Evaluate greek condition (delta, gamma, theta, vega).

        Config format:
        {
            "type": "greek",
            "symbol": "NIFTY50",
            "greek": "delta",
            "operator": "gt",
            "threshold": 0.5
        }
        """
        symbol = config.get("symbol", "")
        greek = config.get("greek", "").lower()
        operator = config.get("operator", "gt")
        threshold = float(config.get("threshold", 0))

        if not symbol or not greek:
            return EvaluationResult(
                matched=False,
                error="Symbol and greek are required"
            )

        try:
            # Fetch greeks from backend
            response = await self.client.get(
                f"{self.backend_url}/api/greeks/{symbol}"
            )

            if response.status_code != 200:
                return EvaluationResult(
                    matched=False,
                    error=f"Failed to fetch greeks for {symbol}: {response.status_code}"
                )

            data = response.json()
            current_value = data.get(greek)

            if current_value is None:
                return EvaluationResult(
                    matched=False,
                    error=f"No {greek} data for {symbol}"
                )

            current_value = float(current_value)

            # Compare using operator
            matched = self._compare_values(current_value, operator, threshold)

            return EvaluationResult(
                matched=matched,
                current_value=current_value,
                threshold=threshold,
                details={
                    "symbol": symbol,
                    "greek": greek,
                    "operator": operator,
                }
            )

        except httpx.RequestError as e:
            logger.error(f"Network error fetching greeks for {symbol}: {e}")
            return EvaluationResult(
                matched=False,
                error=f"Network error: {str(e)}"
            )

    async def evaluate_time(self, config: Dict[str, Any]) -> EvaluationResult:
        """
        Evaluate time-based condition.

        Config format:
        {
            "type": "time",
            "condition": "market_hours",  # market_hours, time_range, day_of_week
            "timezone": "Asia/Kolkata"
        }
        """
        condition = config.get("condition", "market_hours")

        # For now, simple implementation
        # TODO: Integrate with calendar_service for proper market hours

        from datetime import datetime
        import pytz

        tz = pytz.timezone(config.get("timezone", "Asia/Kolkata"))
        now = datetime.now(tz)

        if condition == "market_hours":
            # NSE market hours: 9:15 AM - 3:30 PM IST
            market_open = now.replace(hour=9, minute=15, second=0)
            market_close = now.replace(hour=15, minute=30, second=0)
            matched = market_open <= now <= market_close

            return EvaluationResult(
                matched=matched,
                details={
                    "condition": condition,
                    "current_time": now.isoformat(),
                    "market_open": market_open.isoformat(),
                    "market_close": market_close.isoformat(),
                }
            )

        elif condition == "time_range":
            start_time = config.get("start_time", "09:15")
            end_time = config.get("end_time", "15:30")

            start_hour, start_min = map(int, start_time.split(":"))
            end_hour, end_min = map(int, end_time.split(":"))

            start = now.replace(hour=start_hour, minute=start_min, second=0)
            end = now.replace(hour=end_hour, minute=end_min, second=0)

            matched = start <= now <= end

            return EvaluationResult(
                matched=matched,
                details={
                    "condition": condition,
                    "current_time": now.isoformat(),
                    "start_time": start.isoformat(),
                    "end_time": end.isoformat(),
                }
            )

        elif condition == "day_of_week":
            allowed_days = config.get("days", ["monday", "tuesday", "wednesday", "thursday", "friday"])
            current_day = now.strftime("%A").lower()
            matched = current_day in [d.lower() for d in allowed_days]

            return EvaluationResult(
                matched=matched,
                details={
                    "condition": condition,
                    "current_day": current_day,
                    "allowed_days": allowed_days,
                }
            )

        else:
            return EvaluationResult(
                matched=False,
                error=f"Unknown time condition: {condition}"
            )

    async def evaluate_composite(self, config: Dict[str, Any]) -> EvaluationResult:
        """
        Evaluate composite condition (AND/OR logic).

        Config format:
        {
            "type": "composite",
            "operator": "and",  # and, or
            "conditions": [
                {"type": "price", ...},
                {"type": "indicator", ...}
            ]
        }
        """
        operator = config.get("operator", "and").lower()
        conditions = config.get("conditions", [])

        if not conditions:
            return EvaluationResult(
                matched=False,
                error="Composite condition requires at least one sub-condition"
            )

        results = []
        for sub_condition in conditions:
            result = await self.evaluate(sub_condition)
            results.append(result)

        # Apply AND/OR logic
        if operator == "and":
            matched = all(r.matched for r in results)
        elif operator == "or":
            matched = any(r.matched for r in results)
        else:
            return EvaluationResult(
                matched=False,
                error=f"Unknown composite operator: {operator}"
            )

        return EvaluationResult(
            matched=matched,
            details={
                "operator": operator,
                "sub_results": [r.to_dict() for r in results],
                "total_conditions": len(conditions),
                "matched_conditions": sum(1 for r in results if r.matched),
            }
        )

    async def evaluate_custom(self, config: Dict[str, Any]) -> EvaluationResult:
        """
        Evaluate custom condition.

        For now, returns False (not implemented).
        Future: Could support Python expressions or custom scripts.
        """
        return EvaluationResult(
            matched=False,
            error="Custom conditions not yet implemented"
        )

    def _compare_values(
        self,
        current: float,
        operator: str,
        threshold: float,
        threshold_max: Optional[float] = None
    ) -> bool:
        """
        Compare current value against threshold using operator.

        Supports: gt, gte, lt, lte, eq, between
        """
        if operator == "gt":
            return current > threshold
        elif operator == "gte":
            return current >= threshold
        elif operator == "lt":
            return current < threshold
        elif operator == "lte":
            return current <= threshold
        elif operator == "eq":
            # Use tolerance for float comparison
            tolerance = abs(threshold) * 0.001 if threshold != 0 else 0.001
            return abs(current - threshold) <= tolerance
        elif operator == "between":
            if threshold_max is None:
                logger.warning("'between' operator requires threshold_max")
                return False
            return threshold <= current <= threshold_max
        else:
            logger.warning(f"Unknown operator: {operator}")
            return False
