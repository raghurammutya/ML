"""
Custom exceptions for StocksBlitz SDK.
"""


class StocksBlitzError(Exception):
    """Base exception for all StocksBlitz SDK errors."""
    pass


class InstrumentNotFoundError(StocksBlitzError):
    """Raised when an instrument cannot be found."""
    pass


class InsufficientFundsError(StocksBlitzError):
    """Raised when account has insufficient funds for an operation."""
    pass


class InvalidOrderError(StocksBlitzError):
    """Raised when an order is invalid."""
    pass


class APIError(StocksBlitzError):
    """Raised when an API call fails."""

    def __init__(self, message: str, status_code: int = None, response: dict = None):
        super().__init__(message)
        self.status_code = status_code
        self.response = response


class CacheError(StocksBlitzError):
    """Raised when a cache operation fails."""
    pass


class ValidationError(StocksBlitzError):
    """Raised when input validation fails."""
    pass


class TimeoutError(StocksBlitzError):
    """Raised when an operation times out."""
    pass


class DataUnavailableError(StocksBlitzError):
    """Raised when data is unavailable (not an error, but no data exists)."""

    def __init__(self, message: str, reason: str = None):
        super().__init__(message)
        self.reason = reason


class StaleDataError(StocksBlitzError):
    """Raised when data is stale and shouldn't be used for trading."""

    def __init__(self, message: str, age_seconds: float = None):
        super().__init__(message)
        self.age_seconds = age_seconds


class InstrumentNotSubscribedError(DataUnavailableError):
    """Raised when instrument is not subscribed in ticker service."""
    pass


class IndicatorUnavailableError(DataUnavailableError):
    """Raised when an indicator is unavailable."""
    pass


class DataValidationError(StocksBlitzError):
    """Raised when data validation fails (e.g., negative prices)."""

    def __init__(self, message: str, field: str = None, value: any = None):
        super().__init__(message)
        self.field = field
        self.value = value
