"""
Circuit breaker pattern implementation for fault tolerance.

Protects against cascading failures by temporarily blocking operations
when a dependency (e.g., Redis) is experiencing issues.

State machine:
    CLOSED → (failures reach threshold) → OPEN
    OPEN → (timeout elapsed) → HALF_OPEN
    HALF_OPEN → (success) → CLOSED
    HALF_OPEN → (failure) → OPEN
"""
import asyncio
import enum
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)


class CircuitState(enum.Enum):
    """Circuit breaker states"""
    CLOSED = "closed"           # Normal operation - requests allowed
    OPEN = "open"               # Failing - requests blocked
    HALF_OPEN = "half_open"     # Testing recovery - limited requests allowed


class CircuitBreaker:
    """
    Circuit breaker for protecting against cascading failures.

    When a dependency starts failing, the circuit "opens" to prevent
    further attempts, allowing the system to fail fast and recover gracefully.

    Example:
        >>> breaker = CircuitBreaker(failure_threshold=5, recovery_timeout_seconds=60.0)
        >>> if await breaker.can_execute():
        ...     try:
        ...         result = await risky_operation()
        ...         await breaker.record_success()
        ...     except Exception as exc:
        ...         await breaker.record_failure(exc)
        ...         raise
        ... else:
        ...     logger.warning("Circuit open, skipping operation")
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout_seconds: float = 60.0,
        half_open_max_attempts: int = 3,
        name: str = "circuit_breaker",
    ):
        """
        Initialize circuit breaker.

        Args:
            failure_threshold: Number of failures before circuit opens
            recovery_timeout_seconds: Time to wait before testing recovery
            half_open_max_attempts: Max attempts in HALF_OPEN state
            name: Identifier for logging
        """
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout_seconds
        self._half_open_max_attempts = half_open_max_attempts
        self._name = name

        # State
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: Optional[float] = None
        self._half_open_attempts = 0

        # Thread safety
        self._lock = asyncio.Lock()

        logger.info(
            f"CircuitBreaker '{name}' initialized | "
            f"threshold={failure_threshold} timeout={recovery_timeout_seconds}s"
        )

    async def can_execute(self) -> bool:
        """
        Check if operation can proceed.

        Returns:
            True if operation allowed, False if circuit is open
        """
        async with self._lock:
            if self._state == CircuitState.CLOSED:
                return True

            if self._state == CircuitState.OPEN:
                # Check if recovery timeout has elapsed
                if self._last_failure_time and time.time() - self._last_failure_time >= self._recovery_timeout:
                    logger.info(f"CircuitBreaker '{self._name}' transitioning OPEN → HALF_OPEN (testing recovery)")
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_attempts = 1  # First attempt counted here
                    return True
                else:
                    # Still in OPEN state
                    return False

            if self._state == CircuitState.HALF_OPEN:
                # Allow limited attempts in HALF_OPEN
                if self._half_open_attempts < self._half_open_max_attempts:
                    self._half_open_attempts += 1
                    return True
                else:
                    return False

        return False

    async def record_success(self) -> None:
        """
        Record successful operation.

        If circuit is HALF_OPEN, transition back to CLOSED.
        """
        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                logger.info(f"CircuitBreaker '{self._name}' transitioning HALF_OPEN → CLOSED (recovery successful)")
                self._state = CircuitState.CLOSED
                self._failure_count = 0
                self._half_open_attempts = 0
            elif self._state == CircuitState.CLOSED:
                # Reset failure count on success in CLOSED state
                if self._failure_count > 0:
                    self._failure_count = 0

    async def record_failure(self, error: Optional[Exception] = None) -> None:
        """
        Record failed operation.

        Args:
            error: Optional exception that caused the failure
        """
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()

            if self._state == CircuitState.CLOSED:
                if self._failure_count >= self._failure_threshold:
                    logger.warning(
                        f"CircuitBreaker '{self._name}' transitioning CLOSED → OPEN | "
                        f"failures={self._failure_count}/{self._failure_threshold} error={error}"
                    )
                    self._state = CircuitState.OPEN
                else:
                    logger.debug(
                        f"CircuitBreaker '{self._name}' failure recorded | "
                        f"count={self._failure_count}/{self._failure_threshold}"
                    )

            elif self._state == CircuitState.HALF_OPEN:
                logger.warning(
                    f"CircuitBreaker '{self._name}' transitioning HALF_OPEN → OPEN | "
                    f"recovery failed error={error}"
                )
                self._state = CircuitState.OPEN
                self._half_open_attempts = 0

    def get_state(self) -> CircuitState:
        """Get current circuit state (thread-safe read)"""
        return self._state

    def get_failure_count(self) -> int:
        """Get current failure count (thread-safe read)"""
        return self._failure_count

    async def reset(self) -> None:
        """Manually reset circuit to CLOSED state"""
        async with self._lock:
            logger.info(f"CircuitBreaker '{self._name}' manually reset to CLOSED")
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._half_open_attempts = 0
