"""
Performance metrics for tick processing.

Phase 4 - Performance & Observability.
"""
from .tick_metrics import (
    # Latency metrics
    tick_processing_latency_seconds,
    greeks_calculation_latency_seconds,
    tick_batch_flush_latency_seconds,

    # Throughput metrics
    ticks_processed_total,
    ticks_published_total,

    # Batching metrics
    tick_batch_size,
    tick_batches_flushed_total,
    tick_batch_fill_rate,

    # Error metrics
    tick_processing_errors_total,
    tick_validation_errors_total,

    # State metrics
    tick_processor_active_accounts,
    tick_processor_underlying_price,
    tick_batch_pending_size,

    # Business metrics
    greeks_calculations_total,
    market_depth_updates_total,

    # Helper functions
    record_tick_processing,
    record_greeks_calculation,
    record_batch_flush,
    record_tick_published,
    record_processing_error,
    record_validation_error,
    update_batch_fill_rate,
    update_pending_batch_size,
    update_underlying_price,
    set_active_accounts,
)

__all__ = [
    # Latency metrics
    "tick_processing_latency_seconds",
    "greeks_calculation_latency_seconds",
    "tick_batch_flush_latency_seconds",

    # Throughput metrics
    "ticks_processed_total",
    "ticks_published_total",

    # Batching metrics
    "tick_batch_size",
    "tick_batches_flushed_total",
    "tick_batch_fill_rate",

    # Error metrics
    "tick_processing_errors_total",
    "tick_validation_errors_total",

    # State metrics
    "tick_processor_active_accounts",
    "tick_processor_underlying_price",
    "tick_batch_pending_size",

    # Business metrics
    "greeks_calculations_total",
    "market_depth_updates_total",

    # Helper functions
    "record_tick_processing",
    "record_greeks_calculation",
    "record_batch_flush",
    "record_tick_published",
    "record_processing_error",
    "record_validation_error",
    "update_batch_fill_rate",
    "update_pending_batch_size",
    "update_underlying_price",
    "set_active_accounts",
]
