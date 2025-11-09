"""
Tick processing performance metrics.

Prometheus metrics for monitoring tick processing throughput, latency, and errors.
Phase 4 - Performance & Observability.
"""
from prometheus_client import Counter, Histogram, Gauge

# ============================================================================
# LATENCY METRICS
# ============================================================================

tick_processing_latency_seconds = Histogram(
    "tick_processing_latency_seconds",
    "Time to process a single tick (P50, P95, P99)",
    ["tick_type"],  # underlying or option
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0],
)

greeks_calculation_latency_seconds = Histogram(
    "greeks_calculation_latency_seconds",
    "Time to calculate Greeks for an option",
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5],
)

tick_batch_flush_latency_seconds = Histogram(
    "tick_batch_flush_latency_seconds",
    "Time to flush a batch to Redis",
    ["batch_type"],  # underlying or options
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0],
)

# ============================================================================
# THROUGHPUT METRICS
# ============================================================================

ticks_processed_total = Counter(
    "ticks_processed_total",
    "Total number of ticks processed",
    ["tick_type", "status"],  # success or error
)

ticks_published_total = Counter(
    "ticks_published_total",
    "Total number of ticks published to Redis",
    ["tick_type"],  # underlying or option
)

# ============================================================================
# BATCHING METRICS
# ============================================================================

tick_batch_size = Histogram(
    "tick_batch_size",
    "Number of ticks in each batch",
    ["batch_type"],  # underlying or options
    buckets=[1, 10, 50, 100, 500, 1000, 5000],
)

tick_batches_flushed_total = Counter(
    "tick_batches_flushed_total",
    "Total number of batches flushed",
    ["batch_type"],  # underlying or options
)

tick_batch_fill_rate = Gauge(
    "tick_batch_fill_rate",
    "Current batch fill rate (percentage of max batch size)",
    ["batch_type"],  # underlying or options
)

# ============================================================================
# ERROR METRICS
# ============================================================================

tick_processing_errors_total = Counter(
    "tick_processing_errors_total",
    "Total tick processing errors",
    ["error_type"],  # validation, greeks, publish, etc.
)

tick_validation_errors_total = Counter(
    "tick_validation_errors_total",
    "Total tick validation errors",
    ["validation_type"],  # schema, business_rule, etc.
)

# ============================================================================
# STATE METRICS
# ============================================================================

tick_processor_active_accounts = Gauge(
    "tick_processor_active_accounts",
    "Number of accounts currently processing ticks",
)

tick_processor_underlying_price = Gauge(
    "tick_processor_underlying_price",
    "Current underlying price tracked by processor",
    ["symbol"],  # NIFTY, BANKNIFTY, etc.
)

tick_batch_pending_size = Gauge(
    "tick_batch_pending_size",
    "Number of ticks pending in batch",
    ["batch_type"],  # underlying or options
)

# ============================================================================
# BUSINESS METRICS
# ============================================================================

greeks_calculations_total = Counter(
    "greeks_calculations_total",
    "Total number of Greeks calculations performed",
    ["status"],  # success or error
)

market_depth_updates_total = Counter(
    "market_depth_updates_total",
    "Total number of market depth updates processed",
    ["instrument_type"],  # option, etc.
)

# Note: expired_contracts_filtered_total removed - KiteConnect doesn't send expired contracts

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def record_tick_processing(tick_type: str, latency_seconds: float, success: bool = True):
    """
    Record tick processing metrics.

    Args:
        tick_type: "underlying" or "option"
        latency_seconds: Processing time in seconds
        success: Whether processing succeeded
    """
    tick_processing_latency_seconds.labels(tick_type=tick_type).observe(latency_seconds)
    status = "success" if success else "error"
    ticks_processed_total.labels(tick_type=tick_type, status=status).inc()


def record_greeks_calculation(latency_seconds: float, success: bool = True):
    """
    Record Greeks calculation metrics.

    Args:
        latency_seconds: Calculation time in seconds
        success: Whether calculation succeeded
    """
    greeks_calculation_latency_seconds.observe(latency_seconds)
    status = "success" if success else "error"
    greeks_calculations_total.labels(status=status).inc()


def record_batch_flush(batch_type: str, batch_size: int, latency_seconds: float):
    """
    Record batch flush metrics.

    Args:
        batch_type: "underlying" or "options"
        batch_size: Number of ticks in batch
        latency_seconds: Flush time in seconds
    """
    tick_batch_size.labels(batch_type=batch_type).observe(batch_size)
    tick_batch_flush_latency_seconds.labels(batch_type=batch_type).observe(latency_seconds)
    tick_batches_flushed_total.labels(batch_type=batch_type).inc()


def record_tick_published(tick_type: str):
    """
    Record tick publication.

    Args:
        tick_type: "underlying" or "option"
    """
    ticks_published_total.labels(tick_type=tick_type).inc()


def record_processing_error(error_type: str):
    """
    Record processing error.

    Args:
        error_type: Type of error (validation, greeks, publish, etc.)
    """
    tick_processing_errors_total.labels(error_type=error_type).inc()


def record_validation_error(validation_type: str):
    """
    Record validation error.

    Args:
        validation_type: Type of validation error
    """
    tick_validation_errors_total.labels(validation_type=validation_type).inc()


def update_batch_fill_rate(batch_type: str, fill_rate: float):
    """
    Update batch fill rate gauge.

    Args:
        batch_type: "underlying" or "options"
        fill_rate: Fill rate as percentage (0-100)
    """
    tick_batch_fill_rate.labels(batch_type=batch_type).set(fill_rate)


def update_pending_batch_size(batch_type: str, size: int):
    """
    Update pending batch size gauge.

    Args:
        batch_type: "underlying" or "options"
        size: Number of ticks pending
    """
    tick_batch_pending_size.labels(batch_type=batch_type).set(size)


def update_underlying_price(symbol: str, price: float):
    """
    Update underlying price gauge.

    Args:
        symbol: Underlying symbol (NIFTY, BANKNIFTY, etc.)
        price: Current price
    """
    tick_processor_underlying_price.labels(symbol=symbol).set(price)


def set_active_accounts(count: int):
    """
    Set number of active accounts.

    Args:
        count: Number of active accounts
    """
    tick_processor_active_accounts.set(count)
