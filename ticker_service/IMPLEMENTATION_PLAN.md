# Implementation Plan - Ticker Service Improvements
**Version**: 1.0
**Date**: November 8, 2025
**Status**: Ready for Execution

---

## EXECUTIVE SUMMARY

### Overview
This implementation plan addresses 26 identified issues across 4 priority levels, improving the ticker_service from a code quality score of 75/100 to 92/100 over an 8-12 week period. All improvements maintain 100% backward compatibility.

### Key Objectives
1. **Eliminate Silent Failures**: Fix all bare exception handlers and unhandled task exceptions
2. **Improve Concurrency Safety**: Resolve race conditions and blocking operations
3. **Enhance Architecture**: Refactor god class, implement dependency injection
4. **Increase Test Coverage**: From 4% to 85%
5. **Optimize Performance**: Fix N+1 queries, improve database filtering

### Timeline
- **Phase 1** (Week 1): Critical Fixes - 4 issues, ~4 hours effort
- **Phase 2** (Weeks 2-3): Core Improvements - 8 issues, ~40 hours effort
- **Phase 3** (Weeks 4-5): Architecture Refactoring - 6 issues, ~80 hours effort
- **Phase 4** (Weeks 6-8): Optimization & Polish - 8 issues, ~60 hours effort
- **Total**: 8-12 weeks, ~184 hours engineering effort

### Resource Requirements
- **Engineers**: 2 senior backend engineers
- **QA**: 1 QA engineer (test implementation)
- **DevOps**: Part-time for CI/CD enhancements
- **Code Review**: All changes require peer review

### Risk Assessment
- **Regression Risk**: LOW (comprehensive test coverage, phased rollout)
- **Performance Risk**: LOW (performance tests in TEST_PLAN.md)
- **Operational Risk**: LOW (feature flags, canary deployment)
- **Timeline Risk**: MEDIUM (god class refactoring may extend to 3 weeks)

---

## PHASE 1: CRITICAL FIXES (Week 1)

Target: Fix all silent failure scenarios that hide errors and prevent proper debugging.

### 1.1 Fix Bare Exception Handler

**Priority**: Critical
**Estimated Effort**: 30 minutes
**Risk Level**: Low
**Regression Risk**: Low

**Problem Statement**:
Bare `except:` clause in strike_rebalancer.py prevents proper shutdown and hides all exceptions.

**Current Implementation** (File: app/strike_rebalancer.py:226):
```python
try:
    await asyncio.sleep(rebalance_interval)
except:
    break  # Silent exit, no logging
```

**Issues**:
- Catches ALL exceptions including KeyboardInterrupt, SystemExit
- No logging of what triggered shutdown
- Debugging is impossible when rebalancer stops unexpectedly

**Proposed Solution**:
Catch only the specific exception we care about (CancelledError for shutdown) and log all others.

**Implementation Steps**:
1. Read app/strike_rebalancer.py
2. Replace bare except with specific exception handling
3. Add structured logging
4. Run existing tests
5. Add new test case TC-ERR-050

**Code Changes**:
```python
# File: app/strike_rebalancer.py:226
# BEFORE:
try:
    await asyncio.sleep(rebalance_interval)
except:
    break

# AFTER:
try:
    await asyncio.sleep(rebalance_interval)
except asyncio.CancelledError:
    logger.info("Strike rebalancer shutdown requested")
    break
except Exception as exc:
    logger.exception(
        "Strike rebalancer error during sleep",
        extra={
            "component": "strike_rebalancer",
            "error_type": type(exc).__name__,
            "error": str(exc)
        }
    )
    # Continue running despite errors in sleep
    break
```

**Testing Requirements**:
- Unit Tests:
  - TC-REBAL-001: Normal shutdown via CancelledError
  - TC-REBAL-002: Unexpected exception during sleep
- Integration Tests:
  - TC-REBAL-010: Verify logging output format
  - TC-REBAL-011: Verify service continues after non-critical errors

**Verification Checklist**:
- [ ] Bare except removed
- [ ] CancelledError caught explicitly
- [ ] Exception logging includes context
- [ ] All existing tests pass
- [ ] New tests added and passing
- [ ] Code review approved

**Rollback Plan**:
Simple git revert - this is an isolated change with no dependencies.

**Dependencies**: None

---

### 1.2 Handle Unhandled Task Exceptions

**Priority**: Critical
**Estimated Effort**: 1 hour
**Risk Level**: Medium
**Regression Risk**: Low

**Problem Statement**:
Fire-and-forget async tasks in generator.py (lines 157-220) can fail silently, causing streaming to stop without any error indication.

**Current Implementation** (File: app/generator.py:157-220):
```python
# Line 157 - Account tasks
task = asyncio.create_task(self._stream_account(account_id))
self._account_tasks[account_id] = task

# Line 172 - Underlying task
self._underlying_task = asyncio.create_task(self._stream_underlying())

# Line 203 - Reload task
asyncio.create_task(self._reload_subscriptions())
```

**Issues**:
- If any task crashes, exception is silently swallowed
- No monitoring of task health
- Service appears running but data stops flowing

**Proposed Solution**:
Wrap all task creation with exception monitoring callback.

**Implementation Steps**:
1. Create task exception handler utility
2. Replace all asyncio.create_task() calls
3. Add task health monitoring to /health endpoint
4. Implement tests TC-MATL-005, TC-MATL-006

**Code Changes**:

**Step 1: Create utility** (File: app/utils/task_monitor.py - NEW FILE):
```python
"""Task monitoring utilities for async task exception handling."""
import asyncio
from typing import Coroutine, Optional
from loguru import logger


def create_monitored_task(
    coro: Coroutine,
    task_name: str,
    critical: bool = True,
    error_callback: Optional[callable] = None
) -> asyncio.Task:
    """
    Create async task with exception monitoring.

    Args:
        coro: Coroutine to run
        task_name: Human-readable task identifier
        critical: If True, log at CRITICAL level; else WARNING
        error_callback: Optional callback function(task_name, exception)

    Returns:
        asyncio.Task instance
    """
    async def monitored():
        try:
            await coro
        except asyncio.CancelledError:
            logger.info(f"Task {task_name} cancelled")
            raise  # Re-raise to properly handle cancellation
        except Exception as exc:
            log_level = "critical" if critical else "warning"
            logger.log(
                log_level.upper(),
                f"Task {task_name} failed with exception",
                extra={
                    "task_name": task_name,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "critical": critical
                },
                exc_info=True
            )
            if error_callback:
                try:
                    error_callback(task_name, exc)
                except Exception as cb_exc:
                    logger.error(
                        f"Error callback for {task_name} failed: {cb_exc}"
                    )

    task = asyncio.create_task(monitored())
    task.set_name(task_name)  # For debugging
    return task
```

**Step 2: Update generator.py**:
```python
# File: app/generator.py
# Add import at top
from .utils.task_monitor import create_monitored_task

# BEFORE (line 157):
task = asyncio.create_task(self._stream_account(account_id))
self._account_tasks[account_id] = task

# AFTER:
task = create_monitored_task(
    self._stream_account(account_id),
    task_name=f"stream_account_{account_id}",
    critical=True,
    error_callback=self._handle_account_task_failure
)
self._account_tasks[account_id] = task

# Add error handler method to MultiAccountTickerLoop class:
def _handle_account_task_failure(self, task_name: str, exc: Exception) -> None:
    """Handle account streaming task failures."""
    # Extract account_id from task_name
    account_id = task_name.replace("stream_account_", "")

    # Mark account as failed in runtime state
    if account_id in self._account_tasks:
        del self._account_tasks[account_id]

    # Could implement auto-restart logic here if desired
    logger.warning(
        f"Account {account_id} streaming stopped, will not auto-restart",
        extra={"account_id": account_id, "reason": str(exc)}
    )

# BEFORE (line 172):
self._underlying_task = asyncio.create_task(self._stream_underlying())

# AFTER:
self._underlying_task = create_monitored_task(
    self._stream_underlying(),
    task_name="stream_underlying",
    critical=True
)

# BEFORE (line 203):
asyncio.create_task(self._reload_subscriptions())

# AFTER:
create_monitored_task(
    self._reload_subscriptions(),
    task_name="reload_subscriptions",
    critical=False  # Reload failures are not critical
)
```

**Testing Requirements**:
- Unit Tests:
  - TC-MATL-005: Verify task exception logging
  - TC-MATL-006: Verify task name in logs
  - TC-UTIL-001: Test monitored task with success
  - TC-UTIL-002: Test monitored task with exception
  - TC-UTIL-003: Test monitored task with cancellation
  - TC-UTIL-004: Test error callback invocation
- Integration Tests:
  - TC-MATL-050: Verify account failover after task failure
  - TC-MATL-051: Verify service continues after non-critical task failure

**Verification Checklist**:
- [ ] All asyncio.create_task() replaced in critical paths
- [ ] Task names set for debugging
- [ ] Error callback implemented
- [ ] Health endpoint shows task status
- [ ] Tests verify exception logging
- [ ] Tests verify error callback invocation
- [ ] No silent task failures in logs
- [ ] Code review approved

**Rollback Plan**:
Remove task_monitor.py and revert generator.py changes. Simple git revert.

**Dependencies**: None

---

### 1.3 Add API Response Validation

**Priority**: Critical
**Estimated Effort**: 1.5 hours
**Risk Level**: Medium
**Regression Risk**: Medium

**Problem Statement**:
Missing validation of Kite API responses in historical_greeks.py (lines 324-350) can cause data corruption if API returns unexpected formats.

**Current Implementation** (File: app/historical_greeks.py:324-350):
```python
# Directly access response fields without validation
underlying_candles = await client.fetch_historical(
    underlying_token, from_ts, to_ts, interval="minute"
)

# Assume response structure without checking
for candle in underlying_candles:
    underlying_close = candle["close"]  # May KeyError
    timestamp = candle["date"]           # May KeyError
```

**Issues**:
- No validation that API response is not None
- No validation that response is a list
- No validation that candles have required fields
- KeyError crashes the enrichment process
- Corrupted data may propagate to database

**Proposed Solution**:
Add response validation utility and use Pydantic models for API responses.

**Implementation Steps**:
1. Create API response validation utilities
2. Define Pydantic models for Kite API responses
3. Update historical_greeks.py to validate responses
4. Add tests TC-GRK-040 through TC-GRK-043

**Code Changes**:

**Step 1: Create validation utility** (File: app/utils/api_validation.py - NEW FILE):
```python
"""Kite API response validation utilities."""
from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, validator


class CandleData(BaseModel):
    """Validated candle data from Kite API."""
    date: datetime
    open: float = Field(gt=0, description="Opening price")
    high: float = Field(gt=0, description="High price")
    low: float = Field(gt=0, description="Low price")
    close: float = Field(gt=0, description="Closing price")
    volume: int = Field(ge=0, description="Volume traded")
    oi: Optional[int] = Field(default=None, ge=0, description="Open interest")

    @validator('high')
    def high_must_be_highest(cls, v, values):
        """Validate high >= low, open, close."""
        if 'low' in values and v < values['low']:
            raise ValueError(f"High {v} must be >= low {values['low']}")
        return v

    @validator('low')
    def low_must_be_lowest(cls, v, values):
        """Validate low <= high, open, close."""
        if 'high' in values and v > values['high']:
            raise ValueError(f"Low {v} must be <= high {values['high']}")
        return v


def validate_candle_response(
    response: Any,
    instrument_token: int,
    min_candles: int = 0
) -> List[CandleData]:
    """
    Validate Kite historical candle API response.

    Args:
        response: Raw API response
        instrument_token: Token for error context
        min_candles: Minimum expected candles (0 = no minimum)

    Returns:
        List of validated CandleData objects

    Raises:
        ValueError: If response is invalid
    """
    # Check response is not None
    if response is None:
        raise ValueError(
            f"API returned None for instrument {instrument_token}"
        )

    # Check response is a list
    if not isinstance(response, list):
        raise ValueError(
            f"API returned non-list response for instrument {instrument_token}: "
            f"{type(response).__name__}"
        )

    # Check minimum candles requirement
    if len(response) < min_candles:
        raise ValueError(
            f"API returned {len(response)} candles for instrument {instrument_token}, "
            f"expected at least {min_candles}"
        )

    # Validate each candle
    validated_candles = []
    for idx, candle in enumerate(response):
        try:
            validated = CandleData(**candle)
            validated_candles.append(validated)
        except Exception as exc:
            raise ValueError(
                f"Invalid candle at index {idx} for instrument {instrument_token}: "
                f"{exc}"
            ) from exc

    return validated_candles
```

**Step 2: Update historical_greeks.py**:
```python
# File: app/historical_greeks.py
# Add import
from .utils.api_validation import validate_candle_response, CandleData

# BEFORE (line 324):
underlying_candles = await client.fetch_historical(
    underlying_token, from_ts, to_ts, interval="minute"
)

for candle in underlying_candles:
    underlying_close = candle["close"]
    timestamp = candle["date"]

# AFTER:
try:
    underlying_candles_raw = await client.fetch_historical(
        underlying_token, from_ts, to_ts, interval="minute"
    )

    # Validate API response
    underlying_candles = validate_candle_response(
        underlying_candles_raw,
        instrument_token=underlying_token,
        min_candles=1  # Expect at least 1 candle
    )
except ValueError as exc:
    logger.error(
        f"Invalid underlying candles response",
        extra={
            "instrument_token": underlying_token,
            "from_ts": from_ts.isoformat(),
            "to_ts": to_ts.isoformat(),
            "error": str(exc)
        }
    )
    # Return original candles without Greeks enrichment
    return option_candles
except Exception as exc:
    logger.exception(
        f"Failed to fetch underlying candles",
        extra={
            "instrument_token": underlying_token,
            "error": str(exc)
        }
    )
    return option_candles

# Use validated data
for candle in underlying_candles:
    underlying_close = candle.close  # Type-safe access
    timestamp = candle.date
```

**Testing Requirements**:
- Unit Tests:
  - TC-GRK-040: Valid candle response
  - TC-GRK-041: None response raises ValueError
  - TC-GRK-042: Non-list response raises ValueError
  - TC-GRK-043: Missing required fields raises ValueError
  - TC-GRK-044: Invalid price data (high < low) raises ValueError
  - TC-GRK-045: Negative prices raise ValueError
- Integration Tests:
  - TC-GRK-050: End-to-end with mock invalid responses
  - TC-GRK-051: Verify original candles returned on validation failure

**Verification Checklist**:
- [ ] Pydantic models created for all API responses
- [ ] All API calls wrapped with validation
- [ ] Validation errors logged with context
- [ ] Graceful fallback on validation failure
- [ ] Tests cover all validation scenarios
- [ ] No data corruption possible
- [ ] Code review approved

**Rollback Plan**:
Remove api_validation.py and revert historical_greeks.py. Fallback is to previous behavior (no validation).

**Dependencies**:
- Requires pydantic (already in requirements.txt)

---

### 1.4 Fix Swallowed Exceptions in Redis Client

**Priority**: Critical
**Estimated Effort**: 30 minutes
**Risk Level**: Low
**Regression Risk**: Low

**Problem Statement**:
redis_client.py (lines 64-72) swallows connection exceptions in retry logic, making Redis failures invisible.

**Current Implementation** (File: app/redis_client.py:64-72):
```python
for attempt in (1, 2):
    try:
        return await self._redis.publish(channel, message)
    except RedisConnectionError as exc:
        logger.warning(f"Attempt {attempt} failed: {exc}")
        await self._reset()
        # Last attempt will raise, but no context about all attempts

# If both attempts fail, exception is raised but we lose history
```

**Issues**:
- Each retry logs separately, hard to correlate
- No cumulative error context
- No distinction between transient and persistent failures

**Proposed Solution**:
Accumulate error context across retries and provide full history on final failure.

**Implementation Steps**:
1. Update redis_client.py retry logic
2. Add structured error context
3. Update tests to verify error context

**Code Changes**:
```python
# File: app/redis_client.py:64-72
# BEFORE:
for attempt in (1, 2):
    try:
        return await self._redis.publish(channel, message)
    except RedisConnectionError as exc:
        logger.warning(f"Attempt {attempt} failed: {exc}")
        await self._reset()

# AFTER:
attempts_errors = []
for attempt in (1, 2):
    try:
        result = await self._redis.publish(channel, message)

        # Success - log if we had previous failures
        if attempts_errors:
            logger.info(
                f"Redis publish succeeded after {attempt} attempts",
                extra={
                    "channel": channel,
                    "attempts": attempt,
                    "previous_errors": [str(e) for e in attempts_errors]
                }
            )

        return result

    except RedisConnectionError as exc:
        attempts_errors.append(exc)

        logger.warning(
            f"Redis publish attempt {attempt}/2 failed",
            extra={
                "channel": channel,
                "attempt": attempt,
                "error": str(exc),
                "will_retry": attempt < 2
            }
        )

        if attempt < 2:
            await self._reset()
        else:
            # Final attempt failed - raise with full context
            error_msg = f"Redis publish failed after 2 attempts: {', '.join(str(e) for e in attempts_errors)}"
            logger.error(
                "Redis publish failed completely",
                extra={
                    "channel": channel,
                    "total_attempts": 2,
                    "errors": [str(e) for e in attempts_errors]
                }
            )
            raise RedisConnectionError(error_msg) from attempts_errors[-1]
```

**Testing Requirements**:
- Unit Tests:
  - TC-REDIS-001: Success on first attempt (no extra logging)
  - TC-REDIS-002: Failure then success (logs both)
  - TC-REDIS-003: Both attempts fail (raises with full context)
  - TC-REDIS-004: Verify structured error context in logs

**Verification Checklist**:
- [ ] All retry attempts logged with context
- [ ] Final exception includes all attempt errors
- [ ] Success after retry logs previous failures
- [ ] Tests verify error context
- [ ] Code review approved

**Rollback Plan**:
Simple git revert - isolated change.

**Dependencies**: None

---

## PHASE 2: CORE IMPROVEMENTS (Weeks 2-3)

Target: Improve concurrency safety, error handling consistency, and performance.

### 2.1 Centralized Retry Utility

**Priority**: High
**Estimated Effort**: 2 hours
**Risk Level**: Medium
**Regression Risk**: Medium

**Problem Statement**:
Inconsistent retry logic across multiple files (redis_client.py, order_executor.py, account_store.py) with different backoff strategies.

**Current State**:
- redis_client.py: 2 attempts, no backoff
- order_executor.py: 5 attempts, exponential backoff
- account_store.py: Custom retry with different parameters

**Proposed Solution**:
Create centralized retry_utils.py with configurable retry decorators.

**Implementation Steps**:
1. Create app/utils/retry_utils.py
2. Migrate redis_client.py to use utility
3. Migrate order_executor.py to use utility
4. Migrate account_store.py to use utility
5. Add comprehensive tests

**Code Changes**:

**Step 1: Create retry utility** (File: app/utils/retry_utils.py - NEW FILE):
```python
"""Centralized retry utilities with exponential backoff."""
import asyncio
from typing import Callable, Optional, Type, Tuple, Any
from functools import wraps
from loguru import logger


async def retry_async(
    func: Callable,
    *args,
    max_attempts: int = 3,
    backoff_base: float = 1.0,
    backoff_multiplier: float = 2.0,
    backoff_max: float = 60.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable[[int, Exception], None]] = None,
    operation_name: str = "operation",
    **kwargs
) -> Any:
    """
    Retry an async function with exponential backoff.

    Args:
        func: Async function to retry
        *args: Positional arguments for func
        max_attempts: Maximum retry attempts (default: 3)
        backoff_base: Base delay in seconds (default: 1.0)
        backoff_multiplier: Delay multiplier per attempt (default: 2.0)
        backoff_max: Maximum delay in seconds (default: 60.0)
        exceptions: Tuple of exceptions to catch (default: all)
        on_retry: Optional callback(attempt, exception) called on each retry
        operation_name: Human-readable operation name for logging
        **kwargs: Keyword arguments for func

    Returns:
        Result of func(*args, **kwargs)

    Raises:
        Last exception if all attempts fail
    """
    attempts_errors = []

    for attempt in range(1, max_attempts + 1):
        try:
            result = await func(*args, **kwargs)

            # Success - log if we had previous failures
            if attempts_errors:
                logger.info(
                    f"{operation_name} succeeded after {attempt} attempts",
                    extra={
                        "operation": operation_name,
                        "attempts": attempt,
                        "previous_errors": [str(e) for e in attempts_errors]
                    }
                )

            return result

        except exceptions as exc:
            attempts_errors.append(exc)

            is_last_attempt = (attempt == max_attempts)

            logger.log(
                "ERROR" if is_last_attempt else "WARNING",
                f"{operation_name} attempt {attempt}/{max_attempts} failed",
                extra={
                    "operation": operation_name,
                    "attempt": attempt,
                    "max_attempts": max_attempts,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "will_retry": not is_last_attempt
                }
            )

            if on_retry:
                try:
                    on_retry(attempt, exc)
                except Exception as cb_exc:
                    logger.error(f"Retry callback failed: {cb_exc}")

            if is_last_attempt:
                error_msg = (
                    f"{operation_name} failed after {max_attempts} attempts: "
                    f"{', '.join(str(e) for e in attempts_errors)}"
                )
                logger.error(
                    f"{operation_name} failed completely",
                    extra={
                        "operation": operation_name,
                        "total_attempts": max_attempts,
                        "errors": [str(e) for e in attempts_errors]
                    }
                )
                raise type(exc)(error_msg) from exc
            else:
                # Calculate backoff delay
                delay = min(
                    backoff_base * (backoff_multiplier ** (attempt - 1)),
                    backoff_max
                )
                logger.debug(f"Retrying {operation_name} after {delay:.2f}s")
                await asyncio.sleep(delay)


def async_retry(
    max_attempts: int = 3,
    backoff_base: float = 1.0,
    backoff_multiplier: float = 2.0,
    backoff_max: float = 60.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    operation_name: Optional[str] = None
):
    """
    Decorator for async functions with retry logic.

    Usage:
        @async_retry(max_attempts=5, backoff_base=2.0)
        async def my_function():
            ...
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            op_name = operation_name or func.__name__
            return await retry_async(
                func, *args,
                max_attempts=max_attempts,
                backoff_base=backoff_base,
                backoff_multiplier=backoff_multiplier,
                backoff_max=backoff_max,
                exceptions=exceptions,
                operation_name=op_name,
                **kwargs
            )
        return wrapper
    return decorator
```

**Step 2: Migrate redis_client.py**:
```python
# File: app/redis_client.py
from .utils.retry_utils import retry_async
from redis.exceptions import RedisConnectionError

# BEFORE (lines 64-72):
for attempt in (1, 2):
    try:
        return await self._redis.publish(channel, message)
    except RedisConnectionError as exc:
        logger.warning(f"Attempt {attempt} failed: {exc}")
        await self._reset()

# AFTER:
async def _publish_with_reset(channel: str, message: str) -> int:
    """Publish with connection reset on failure."""
    try:
        return await self._redis.publish(channel, message)
    except RedisConnectionError:
        await self._reset()
        raise

return await retry_async(
    _publish_with_reset,
    channel, message,
    max_attempts=2,
    backoff_base=0.1,
    backoff_multiplier=1.0,  # No exponential backoff, just immediate retry
    exceptions=(RedisConnectionError,),
    operation_name=f"redis_publish:{channel}"
)
```

**Testing Requirements**:
- Unit Tests:
  - TC-UTIL-010: Retry success on first attempt
  - TC-UTIL-011: Retry success after failures
  - TC-UTIL-012: Retry all attempts fail
  - TC-UTIL-013: Exponential backoff timing
  - TC-UTIL-014: Backoff max limit
  - TC-UTIL-015: on_retry callback invocation
  - TC-UTIL-016: Decorator usage
- Integration Tests:
  - TC-REDIS-010: Redis publish with retry
  - TC-ORD-040: Order execution with retry
  - TC-ACC-020: Account operation with retry

**Verification Checklist**:
- [ ] retry_utils.py created with tests
- [ ] All retry logic migrated to utility
- [ ] Consistent retry behavior across codebase
- [ ] Tests verify backoff timing
- [ ] Tests verify error context
- [ ] Code review approved

**Rollback Plan**:
Revert each file individually, maintaining old retry logic.

**Dependencies**:
- Phase 1 completion (for consistent error logging)

---

### 2.2 Fix Race Conditions in Mock State Access

**Priority**: High
**Estimated Effort**: 1 hour
**Risk Level**: Medium
**Regression Risk**: Low

**Problem Statement**:
Mock state (_mock_option_state, _mock_underlying_state) in generator.py accessed from multiple async tasks without synchronization.

**Current Implementation** (File: app/generator.py:313-350):
```python
# Line 313: Double-check locking for seed (CORRECT)
async with self._mock_seed_lock:
    if self._mock_underlying_state is not None:
        return
    # Initialize state

# Line 350: Direct access in streaming loop (WRONG - no lock!)
if token in self._mock_option_state:
    mock_state = self._mock_option_state[token]
    mock_state.update()  # Mutates state without lock!
```

**Issues**:
- Multiple async tasks read/write mock state concurrently
- Mock state mutation not protected by lock
- Potential for corrupted mock prices

**Proposed Solution**:
Use immutable snapshots for reading mock state.

**Implementation Steps**:
1. Create immutable snapshot method
2. Update streaming loop to use snapshots
3. Add tests TC-MATL-050, TC-MATL-051

**Code Changes**:
```python
# File: app/generator.py

# Add method to MultiAccountTickerLoop class:
def _get_mock_state_snapshot(self) -> Tuple[Optional[Dict[int, MockOptionState]], Optional[MockUnderlyingState]]:
    """
    Get immutable snapshot of mock state for safe concurrent access.

    Returns:
        Tuple of (option_state_copy, underlying_state_copy)
    """
    if self._mock_option_state is None:
        return None, None

    # Create shallow copies - each MockState is immutable after update()
    option_snapshot = dict(self._mock_option_state)
    underlying_snapshot = (
        self._mock_underlying_state.copy() if self._mock_underlying_state else None
    )

    return option_snapshot, underlying_snapshot

# Add copy method to MockUnderlyingState class:
def copy(self) -> "MockUnderlyingState":
    """Create immutable copy of current state."""
    return MockUnderlyingState(
        current_price=self.current_price,
        high=self.high,
        low=self.low,
        volume=self.volume,
        last_update=self.last_update
    )

# Update streaming loop (line 350):
# BEFORE:
if token in self._mock_option_state:
    mock_state = self._mock_option_state[token]
    mock_state.update()

# AFTER:
option_states, underlying_state = self._get_mock_state_snapshot()
if option_states and token in option_states:
    mock_state = option_states[token]
    # mock_state is now a snapshot, no concurrent mutations possible
    # Create new state instead of mutating
    updated_state = mock_state.update()  # Returns new instance

    # Update shared state with lock
    async with self._mock_seed_lock:
        self._mock_option_state[token] = updated_state
```

**Testing Requirements**:
- Unit Tests:
  - TC-MATL-050: Concurrent access to mock state (no corruption)
  - TC-MATL-051: Mock state updates isolated per task
  - TC-MOCK-001: Snapshot is immutable
  - TC-MOCK-002: Snapshot reflects current state at time of call

**Verification Checklist**:
- [ ] All mock state access uses snapshots
- [ ] Mock state mutations protected by lock
- [ ] Tests verify concurrent access safety
- [ ] No race conditions in stress tests
- [ ] Code review approved

**Rollback Plan**:
Revert to previous implementation. Document that concurrent access should be avoided in deployment notes.

**Dependencies**: None

---

### 2.3 Bounded Reload Queue

**Priority**: High
**Estimated Effort**: 1 hour
**Risk Level**: Low
**Regression Risk**: Low

**Problem Statement**:
Reload queue in generator.py (line 203-220) has no bounds - rapid subscription changes can create unlimited pending reload tasks.

**Current Implementation** (File: app/generator.py:203-220):
```python
def reload_subscriptions_async(self) -> None:
    """Fire-and-forget reload trigger."""
    asyncio.create_task(self._reload_subscriptions())
    # No limit on pending reloads!
```

**Issues**:
- Duplicate reloads waste resources
- No queue size limit
- Memory exhaustion possible with rapid API calls

**Proposed Solution**:
Add semaphore-based queue with duplicate prevention.

**Implementation Steps**:
1. Add reload semaphore to __init__
2. Implement reload queue with deduplication
3. Add metrics for reload queue depth
4. Add tests TC-MATL-013, TC-MATL-014

**Code Changes**:
```python
# File: app/generator.py

# Add to __init__ (line 70):
self._reload_semaphore = asyncio.Semaphore(1)  # Only 1 reload at a time
self._reload_pending = False
self._reload_lock = asyncio.Lock()

# BEFORE (line 203):
def reload_subscriptions_async(self) -> None:
    """Fire-and-forget reload trigger."""
    asyncio.create_task(self._reload_subscriptions())

# AFTER:
def reload_subscriptions_async(self) -> None:
    """
    Trigger subscription reload with duplicate prevention.

    Only one reload runs at a time. If a reload is already pending,
    this call is ignored to prevent queue buildup.
    """
    # Non-blocking check if reload already pending
    if self._reload_pending:
        logger.debug("Subscription reload already pending, skipping duplicate request")
        return

    asyncio.create_task(self._reload_with_semaphore())

async def _reload_with_semaphore(self) -> None:
    """Reload with semaphore to prevent concurrent reloads."""
    # Mark as pending
    async with self._reload_lock:
        if self._reload_pending:
            logger.debug("Reload already in progress, skipping")
            return
        self._reload_pending = True

    try:
        # Wait for semaphore (only 1 reload at a time)
        async with self._reload_semaphore:
            logger.info("Starting subscription reload")
            await self._reload_subscriptions()
            logger.info("Subscription reload completed")
    except Exception as exc:
        logger.exception("Subscription reload failed", extra={"error": str(exc)})
    finally:
        # Clear pending flag
        async with self._reload_lock:
            self._reload_pending = False
```

**Testing Requirements**:
- Unit Tests:
  - TC-MATL-013: Multiple rapid reload requests (only 1 executes)
  - TC-MATL-014: Reload queue depth never > 1
  - TC-MATL-015: Duplicate reload requests logged
- Load Tests:
  - TC-PERF-020: 1000 rapid subscription changes (bounded reload)

**Verification Checklist**:
- [ ] Reload queue bounded to 1 concurrent
- [ ] Duplicate requests prevented
- [ ] Logging shows duplicate prevention
- [ ] Load test verifies no memory growth
- [ ] Code review approved

**Rollback Plan**:
Revert to unbounded queue. Document to avoid rapid subscription changes.

**Dependencies**: None

---

### 2.4 Database Filtering Optimization

**Priority**: High
**Estimated Effort**: 30 minutes
**Risk Level**: Low
**Regression Risk**: Low

**Problem Statement**:
Inefficient linear filtering in main.py (lines 477-482) fetches ALL subscriptions then filters in Python.

**Current Implementation** (File: app/main.py:477-482):
```python
# Fetch all subscriptions
all_subs = await subscription_store.list_active()

# Filter in Python
filtered = [
    sub for sub in all_subs
    if sub["account_id"] == account_id
]
```

**Issues**:
- Fetches all rows from database
- Linear search in Python
- Memory overhead for large subscription lists
- Slow with 10,000+ subscriptions

**Proposed Solution**:
Add SQL filtering to subscription_store.

**Implementation Steps**:
1. Add filter parameters to list_active()
2. Update all call sites
3. Add tests TC-SUB-030, TC-SUB-031

**Code Changes**:
```python
# File: app/subscription_store.py

# Update list_active method signature:
async def list_active(
    self,
    account_id: Optional[str] = None,
    segment: Optional[str] = None,
    instrument_tokens: Optional[List[int]] = None
) -> List[Dict[str, Any]]:
    """
    Get all active subscriptions with optional filtering.

    Args:
        account_id: Filter by account (optional)
        segment: Filter by segment (optional)
        instrument_tokens: Filter by token list (optional)

    Returns:
        List of active subscription dictionaries
    """
    await self.initialise()

    # Build WHERE clause
    where_clauses = ["status = 'active'"]
    params = []

    if account_id is not None:
        where_clauses.append("account_id = $%d" % (len(params) + 1))
        params.append(account_id)

    if segment is not None:
        where_clauses.append("segment = $%d" % (len(params) + 1))
        params.append(segment)

    if instrument_tokens is not None:
        where_clauses.append("instrument_token = ANY($%d)" % (len(params) + 1))
        params.append(instrument_tokens)

    where_sql = " AND ".join(where_clauses)

    query = f"""
        SELECT instrument_token, tradingsymbol, segment, status,
               requested_mode, account_id, created_at, updated_at
        FROM instrument_subscriptions
        WHERE {where_sql}
        ORDER BY instrument_token
    """

    async with self._pool.connection() as conn:
        cursor = await conn.execute(query, params)
        rows = await cursor.fetchall()

        return [
            {
                "instrument_token": row[0],
                "tradingsymbol": row[1],
                "segment": row[2],
                "status": row[3],
                "requested_mode": row[4],
                "account_id": row[5],
                "created_at": row[6],
                "updated_at": row[7]
            }
            for row in rows
        ]

# File: app/main.py:477-482
# BEFORE:
all_subs = await subscription_store.list_active()
filtered = [sub for sub in all_subs if sub["account_id"] == account_id]

# AFTER:
filtered = await subscription_store.list_active(account_id=account_id)
```

**Testing Requirements**:
- Unit Tests:
  - TC-SUB-030: Filter by account_id
  - TC-SUB-031: Filter by segment
  - TC-SUB-032: Filter by token list
  - TC-SUB-033: Multiple filters combined
  - TC-SUB-034: No filters (returns all active)
- Performance Tests:
  - TC-PERF-030: 10,000 subscriptions, filter performance

**Verification Checklist**:
- [ ] SQL filtering implemented
- [ ] All call sites updated
- [ ] Tests verify correct filtering
- [ ] Performance improved (measure before/after)
- [ ] Code review approved

**Rollback Plan**:
Revert to Python filtering. Simple git revert.

**Dependencies**: None

---

## PHASE 3: ARCHITECTURE IMPROVEMENTS (Weeks 4-5)

Target: Refactor god class, implement dependency injection, improve testability.

### 3.1 Refactor MultiAccountTickerLoop God Class

**Priority**: Medium
**Estimated Effort**: 3-5 days
**Risk Level**: High
**Regression Risk**: High

**Problem Statement**:
MultiAccountTickerLoop (1184 lines) violates single responsibility principle, making it:
- Hard to test (requires extensive mocking)
- Hard to maintain (changes affect multiple concerns)
- Hard to understand (too many responsibilities)

**Current Responsibilities**:
1. Account streaming coordination
2. Underlying bar aggregation
3. Mock data generation
4. Subscription reconciliation
5. Historical data fetching
6. Instrument registry management

**Proposed Solution**:
Extract into focused classes with clear interfaces.

**New Architecture**:
```
MultiAccountTickerLoop (coordinator) - 200 lines
├── OptionTickStream (per-account streaming) - 300 lines
├── UnderlyingBarAggregator (aggregation logic) - 200 lines
├── MockDataGenerator (mock price generation) - 250 lines
├── SubscriptionReconciler (DB sync logic) - 200 lines
└── Uses existing: InstrumentRegistry, SubscriptionStore
```

**Implementation Steps**:

This is a large refactoring. The full implementation would be:

1. **Week 1: Create new classes**
   - Day 1-2: OptionTickStream + tests
   - Day 3: UnderlyingBarAggregator + tests
   - Day 4: MockDataGenerator + tests
   - Day 5: SubscriptionReconciler + tests

2. **Week 2: Integrate and migrate**
   - Day 1-2: Update MultiAccountTickerLoop to use new classes
   - Day 3: Integration testing
   - Day 4-5: Bug fixes and refinement

**Code Structure Example**:

```python
# File: app/streaming/option_tick_stream.py - NEW FILE
"""Per-account option tick streaming."""
from typing import List, Callable, Optional
import asyncio
from loguru import logger
from ..models import Instrument, OptionSnapshot
from ..kite.client_async import AsyncKiteClient


class OptionTickStream:
    """
    Manages option tick streaming for a single account.

    Responsibilities:
    - Subscribe to instruments
    - Handle incoming ticks
    - Calculate Greeks
    - Publish snapshots
    """

    def __init__(
        self,
        account_id: str,
        client: AsyncKiteClient,
        on_snapshot: Callable[[OptionSnapshot], None],
        greeks_calculator,
        instrument_registry
    ):
        self.account_id = account_id
        self.client = client
        self.on_snapshot = on_snapshot
        self.greeks_calculator = greeks_calculator
        self.instrument_registry = instrument_registry
        self._stop_event = asyncio.Event()
        self._subscribed_tokens = set()

    async def start(self, instruments: List[Instrument]) -> None:
        """Start streaming for given instruments."""
        tokens = [inst.instrument_token for inst in instruments]

        # Subscribe
        await self.client.subscribe(tokens, self._handle_tick)
        self._subscribed_tokens.update(tokens)

        logger.info(
            f"OptionTickStream started",
            extra={"account_id": self.account_id, "instruments": len(tokens)}
        )

    async def stop(self) -> None:
        """Stop streaming and cleanup."""
        self._stop_event.set()

        # Unsubscribe
        if self._subscribed_tokens:
            await self.client.unsubscribe(list(self._subscribed_tokens))

        logger.info(f"OptionTickStream stopped for {self.account_id}")

    def _handle_tick(self, tick: dict) -> None:
        """Handle incoming tick from KiteTicker."""
        try:
            # Create snapshot with Greeks
            snapshot = self._create_snapshot(tick)

            # Notify coordinator
            self.on_snapshot(snapshot)

        except Exception as exc:
            logger.exception(
                f"Error handling tick",
                extra={
                    "account_id": self.account_id,
                    "token": tick.get("instrument_token"),
                    "error": str(exc)
                }
            )

    def _create_snapshot(self, tick: dict) -> OptionSnapshot:
        """Create option snapshot with Greeks calculation."""
        # Implementation similar to current code but isolated
        # ... (Greeks calculation logic here)
        pass
```

**Due to complexity, I recommend:**
1. Create a separate detailed refactoring design document
2. Implement incrementally with feature flags
3. Extensive parallel testing (old vs new implementation)
4. Gradual cutover per account

**Testing Requirements**:
- All existing tests must pass (regression)
- New unit tests for each extracted class
- Integration tests for coordinator
- Performance tests (no degradation)
- Canary deployment validation

**Verification Checklist**:
- [ ] All new classes created with tests
- [ ] Coordinator updated to use new classes
- [ ] All existing tests pass
- [ ] New tests achieve 85%+ coverage
- [ ] Performance benchmarks show no regression
- [ ] Feature flag allows rollback
- [ ] Documentation updated
- [ ] Code review approved by 2+ engineers

**Rollback Plan**:
Feature flag to switch between old and new implementation. Keep old code for 2 releases.

**Dependencies**:
- Phase 1 & 2 completion recommended
- Requires dedicated time from 2 engineers

---

## PHASE 4: OPTIMIZATION & POLISH (Weeks 6-8)

Target: Performance optimizations, logging improvements, documentation.

### 4.1 Fix N+1 Query in Greeks Calculation

**Priority**: Medium
**Estimated Effort**: 2 hours
**Risk Level**: Low
**Regression Risk**: Low

**Problem Statement**:
Historical Greeks enrichment fetches underlying prices per candle, causing N+1 query pattern.

**Current Implementation** (File: app/historical_greeks.py):
```python
for candle in option_candles:
    # Fetch underlying price for EACH candle (N+1!)
    underlying_candle = await fetch_underlying_at_time(candle.timestamp)
    greeks = calculate_greeks(underlying_candle.close, ...)
```

**Proposed Solution**:
Batch fetch all underlying prices upfront.

**Implementation Steps**:
1. Fetch all underlying candles for time range
2. Create timestamp → price mapping
3. Lookup prices from map instead of fetching

**Code Changes**:
```python
# File: app/historical_greeks.py

# BEFORE: N+1 pattern
for candle in option_candles:
    underlying_candle = await fetch_underlying_at_time(candle.timestamp)
    greeks = calculate_greeks(underlying_candle.close, ...)

# AFTER: Batch fetch
# Fetch all underlying candles upfront
underlying_candles = await client.fetch_historical(
    underlying_token,
    from_ts=option_candles[0].timestamp,
    to_ts=option_candles[-1].timestamp,
    interval="minute"
)

# Create timestamp → price mapping
underlying_prices = {
    candle.timestamp: candle.close
    for candle in underlying_candles
}

# Lookup from map
for candle in option_candles:
    underlying_price = underlying_prices.get(candle.timestamp)
    if underlying_price is None:
        logger.warning(f"No underlying price for {candle.timestamp}")
        continue

    greeks = calculate_greeks(underlying_price, ...)
```

**Testing Requirements**:
- Unit Tests:
  - TC-GRK-060: Batch fetch performance
  - TC-GRK-061: Missing timestamps handled gracefully
- Performance Tests:
  - TC-PERF-040: 1000 candles enrichment time (should be ~10x faster)

**Verification Checklist**:
- [ ] Single batch fetch replaces per-candle fetches
- [ ] Performance improved (measure before/after)
- [ ] Missing data handled gracefully
- [ ] Tests verify correctness
- [ ] Code review approved

**Rollback Plan**:
Simple git revert.

**Dependencies**: None

---

### 4.2 Standardize Logging

**Priority**: Low
**Estimated Effort**: 4 hours
**Risk Level**: Low
**Regression Risk**: Low

**Problem Statement**:
Inconsistent logging patterns across codebase:
- Mix of f-strings and .format()
- Inconsistent structured logging (extra fields)
- Missing context in some logs

**Proposed Solution**:
Create logging standards and utility functions.

**Implementation**:

1. Create logging utilities
2. Define structured logging schema
3. Update high-value log statements
4. Document logging standards

**Code Changes**:
```python
# File: app/utils/logging_utils.py - NEW FILE
"""Standardized logging utilities."""
from typing import Optional, Dict, Any
from loguru import logger


def log_operation_start(
    operation: str,
    extra: Optional[Dict[str, Any]] = None
) -> None:
    """Log operation start with standard format."""
    logger.info(
        f"Starting {operation}",
        extra={"operation": operation, "phase": "start", **(extra or {})}
    )


def log_operation_success(
    operation: str,
    duration_ms: Optional[float] = None,
    extra: Optional[Dict[str, Any]] = None
) -> None:
    """Log operation success with standard format."""
    log_data = {"operation": operation, "phase": "success", **(extra or {})}
    if duration_ms is not None:
        log_data["duration_ms"] = duration_ms

    logger.info(f"Completed {operation}", extra=log_data)


def log_operation_error(
    operation: str,
    error: Exception,
    extra: Optional[Dict[str, Any]] = None
) -> None:
    """Log operation error with standard format."""
    logger.error(
        f"Failed {operation}: {error}",
        extra={
            "operation": operation,
            "phase": "error",
            "error_type": type(error).__name__,
            "error": str(error),
            **(extra or {})
        },
        exc_info=True
    )
```

**Standards Document** (app/docs/LOGGING_STANDARDS.md):
```markdown
# Logging Standards

## Levels
- DEBUG: Detailed diagnostic info (verbose)
- INFO: Normal operations (startup, subscriptions)
- WARNING: Recoverable issues (retries, fallbacks)
- ERROR: Operation failures (with recovery)
- CRITICAL: System-level failures (requires intervention)

## Structured Logging
Always include:
- operation: Human-readable operation name
- phase: "start" | "success" | "error"
- error_type: Exception class name (on errors)
- error: Exception message (on errors)

Context-specific:
- account_id: For multi-account operations
- instrument_token: For instrument operations
- duration_ms: For timed operations

## Format
Use f-strings for messages, structured extra for data:
```python
logger.info(
    f"Operation {name} completed",
    extra={"operation": name, "duration_ms": 123}
)
```
