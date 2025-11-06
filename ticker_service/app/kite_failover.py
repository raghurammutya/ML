"""
Kite API Failover Mechanism

Provides automatic account failover when Kite API limits are reached:
- Rate limiting (429 Too Many Requests)
- Subscription limits exceeded
- API quota exhausted

Usage:
    async with borrow_with_failover(orchestrator, operation="subscription") as client:
        await client.subscribe([123, 456])
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, AsyncGenerator, Optional

from loguru import logger

if TYPE_CHECKING:
    from .accounts import SessionOrchestrator
    from .kite.client import KiteClient


# Kite API error patterns indicating limits/rate limiting
RATE_LIMIT_INDICATORS = [
    "too many requests",
    "rate limit",
    "429",
    "quota exceeded",
    "subscription limit",
    "maximum subscriptions",
    "throttled",
    "too many subscriptions",
]


def is_kite_limit_error(error: Exception) -> bool:
    """
    Detect if an error is due to Kite API limits/rate limiting.

    Args:
        error: Exception from Kite API call

    Returns:
        True if error indicates API limit reached, False otherwise
    """
    error_str = str(error).lower()
    error_type = type(error).__name__.lower()

    # Check error message for limit indicators
    for indicator in RATE_LIMIT_INDICATORS:
        if indicator in error_str or indicator in error_type:
            return True

    # Check for HTTP 429 status code
    if hasattr(error, 'code') and error.code == 429:
        return True

    # Check for HTTPError with 429 status
    if hasattr(error, 'response'):
        response = error.response
        if hasattr(response, 'status_code') and response.status_code == 429:
            return True

    return False


@asynccontextmanager
async def borrow_with_failover(
    orchestrator: "SessionOrchestrator",
    operation: str = "api_call",
    preferred_account: Optional[str] = None,
    max_retries: Optional[int] = None
) -> AsyncGenerator["KiteClient", None]:
    """
    Borrow a Kite client with automatic failover on API limits.

    If the API call fails due to rate limits or subscription limits,
    automatically retries with the next available account.

    Args:
        orchestrator: SessionOrchestrator managing accounts
        operation: Description of operation (for logging)
        preferred_account: Preferred account to try first
        max_retries: Maximum accounts to try (None = try all accounts once)

    Yields:
        KiteClient instance

    Example:
        async with borrow_with_failover(orchestrator, "subscription") as client:
            await client.subscribe([12192002])

    Raises:
        Exception: If all accounts fail or error is not limit-related
    """
    accounts = orchestrator.list_accounts()
    max_attempts = max_retries or len(accounts)

    # If preferred account specified, try it first
    if preferred_account and preferred_account in accounts:
        try_accounts = [preferred_account] + [a for a in accounts if a != preferred_account]
    else:
        try_accounts = accounts

    last_error: Optional[Exception] = None

    for attempt, account_id in enumerate(try_accounts[:max_attempts], 1):
        try:
            logger.debug(
                f"Attempting {operation} with account {account_id} (attempt {attempt}/{max_attempts})"
            )

            async with orchestrator.borrow(account_id) as client:
                # Yield the client - the caller will use it
                # If it succeeds, we're done
                # If it fails, we catch below and try next account
                yield client
                return  # Success - exit

        except Exception as error:
            last_error = error

            # Check if this is a Kite API limit error
            if is_kite_limit_error(error):
                logger.warning(
                    f"{operation} failed for account {account_id}: {error}. "
                    f"Attempting failover to next account..."
                )

                # If this is the last account, log and re-raise
                if attempt >= max_attempts or attempt >= len(try_accounts):
                    if len(accounts) == 1:
                        logger.error(
                            f"{operation} failed: Only 1 account available and it has reached limits. "
                            f"Error: {error}"
                        )
                    else:
                        logger.error(
                            f"{operation} failed: All {len(accounts)} accounts have reached limits. "
                            f"Last error: {error}"
                        )
                    raise

                # Try next account
                continue
            else:
                # Not a limit error - re-raise immediately
                logger.error(f"{operation} failed for account {account_id}: {error}")
                raise

    # Should never reach here, but just in case
    if last_error:
        raise last_error
    raise RuntimeError(f"{operation} failed: No accounts available")


async def execute_with_failover(
    orchestrator: "SessionOrchestrator",
    operation_func,
    operation_name: str = "api_call",
    preferred_account: Optional[str] = None,
    max_retries: Optional[int] = None,
    **kwargs
):
    """
    Execute an operation with automatic account failover.

    Convenience function for operations that don't need context manager.

    Args:
        orchestrator: SessionOrchestrator managing accounts
        operation_func: Async function that takes (client, **kwargs)
        operation_name: Description for logging
        preferred_account: Preferred account to try first
        max_retries: Maximum accounts to try
        **kwargs: Additional args passed to operation_func

    Returns:
        Result from operation_func

    Example:
        result = await execute_with_failover(
            orchestrator,
            lambda client, **kw: client.historical_data(**kw),
            operation_name="history_fetch",
            instrument_token=123,
            from_date="2025-01-01",
            to_date="2025-01-31",
            interval="day"
        )
    """
    async with borrow_with_failover(
        orchestrator,
        operation_name,
        preferred_account,
        max_retries
    ) as client:
        return await operation_func(client, **kwargs)
