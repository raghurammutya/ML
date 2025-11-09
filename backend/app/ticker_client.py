from __future__ import annotations

from typing import Any, Dict, Optional
import logging

import httpx

try:
    from aiobreaker import CircuitBreaker, CircuitBreakerError
    CIRCUIT_BREAKER_AVAILABLE = True
except ImportError:
    CIRCUIT_BREAKER_AVAILABLE = False
    CircuitBreaker = None
    CircuitBreakerError = Exception

logger = logging.getLogger(__name__)


class TickerServiceError(RuntimeError):
    """Raised when the ticker service returns an error response."""


class TickerServiceClient:
    """
    Thin async HTTP client for the ticker microservice.
    """

    def __init__(self, base_url: str, timeout: float = 10.0, enable_circuit_breaker: bool = True) -> None:
        self._client = httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=timeout)

        # Initialize circuit breaker
        if enable_circuit_breaker and CIRCUIT_BREAKER_AVAILABLE:
            self._breaker = CircuitBreaker(
                fail_max=5,  # Open circuit after 5 failures
                timeout_duration=60,  # Keep circuit open for 60 seconds
                name="ticker_service_breaker"
            )
            logger.info("Circuit breaker enabled for ticker service")
        else:
            self._breaker = None
            if enable_circuit_breaker and not CIRCUIT_BREAKER_AVAILABLE:
                logger.warning("Circuit breaker requested but aiobreaker not available")

    async def _call_with_breaker(self, func, *args, **kwargs):
        """Wrapper to call functions with circuit breaker protection."""
        if self._breaker:
            try:
                return await self._breaker.call_async(func, *args, **kwargs)
            except CircuitBreakerError:
                logger.error("Circuit breaker is OPEN - ticker service calls are being blocked")
                raise TickerServiceError("Ticker service is unavailable (circuit breaker open)")
        else:
            return await func(*args, **kwargs)

    async def close(self) -> None:
        await self._client.aclose()

    async def health(self) -> Dict[str, Any]:
        async def _health():
            resp = await self._client.get("/health")
            if resp.status_code >= 400:
                raise TickerServiceError(f"Ticker /health error: {resp.status_code}")
            return resp.json()
        return await self._call_with_breaker(_health)

    async def subscribe(
        self,
        instrument_token: int,
        requested_mode: str = "FULL",
        account_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload = {
            "instrument_token": int(instrument_token),
            "requested_mode": requested_mode,
        }
        if account_id:
            payload["account_id"] = account_id
        resp = await self._client.post("/subscriptions", json=payload)
        if resp.status_code >= 400:
            detail = resp.text
            raise TickerServiceError(
                f"Ticker subscribe failed for {instrument_token}: {resp.status_code} {detail}"
            )
        return resp.json()

    async def unsubscribe(self, instrument_token: int) -> None:
        resp = await self._client.delete(f"/subscriptions/{int(instrument_token)}")
        if resp.status_code not in (200, 202, 204, 404):
            detail = resp.text
            raise TickerServiceError(
                f"Ticker unsubscribe failed for {instrument_token}: {resp.status_code} {detail}"
            )

    async def list_subscriptions(self, status: Optional[str] = None) -> Dict[str, Any]:
        params = {"status": status} if status else None
        resp = await self._client.get("/subscriptions", params=params)
        if resp.status_code >= 400:
            raise TickerServiceError(f"Ticker list subscriptions error: {resp.status_code}")
        return resp.json()

    async def history(self, **params: Any) -> Dict[str, Any]:
        async def _history():
            resp = await self._client.get("/history", params=params)
            if resp.status_code >= 400:
                raise TickerServiceError(f"Ticker history error: {resp.status_code}")
            return resp.json()
        return await self._call_with_breaker(_history)
