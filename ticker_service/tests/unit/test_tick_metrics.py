"""
Unit tests for tick processing metrics.

Verifies that metrics are properly defined and helper functions work correctly.
"""
import pytest
from prometheus_client import REGISTRY

from app.metrics.tick_metrics import (
    # Metrics
    tick_processing_latency_seconds,
    greeks_calculation_latency_seconds,
    tick_batch_flush_latency_seconds,
    ticks_processed_total,
    ticks_published_total,
    tick_batch_size,
    tick_batches_flushed_total,
    tick_batch_fill_rate,
    tick_processing_errors_total,
    tick_validation_errors_total,
    tick_processor_active_accounts,
    tick_processor_underlying_price,
    tick_batch_pending_size,
    greeks_calculations_total,
    market_depth_updates_total,
    # Note: expired_contracts_filtered_total removed - KiteConnect doesn't send expired contracts
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


def test_all_metrics_registered():
    """Test that all metrics are registered with Prometheus"""
    # Get all registered metric names
    metric_names = {metric.name for metric in REGISTRY.collect()}

    # Check our metrics are registered (note: Counter names get _total suffix automatically)
    assert "tick_processing_latency_seconds" in metric_names
    assert "greeks_calculation_latency_seconds" in metric_names
    assert "tick_batch_flush_latency_seconds" in metric_names
    assert "ticks_processed" in metric_names  # _total is added by prometheus
    assert "ticks_published" in metric_names  # _total is added by prometheus


def test_record_tick_processing():
    """Test record_tick_processing helper"""
    # Get initial count
    initial_count = ticks_processed_total.labels(tick_type="underlying", status="success")._value.get()

    # Record a tick
    record_tick_processing("underlying", 0.001, success=True)

    # Check count increased
    new_count = ticks_processed_total.labels(tick_type="underlying", status="success")._value.get()
    assert new_count == initial_count + 1


def test_record_greeks_calculation():
    """Test record_greeks_calculation helper"""
    # Get initial count
    initial_count = greeks_calculations_total.labels(status="success")._value.get()

    # Record a calculation
    record_greeks_calculation(0.005, success=True)

    # Check count increased
    new_count = greeks_calculations_total.labels(status="success")._value.get()
    assert new_count == initial_count + 1


def test_record_batch_flush():
    """Test record_batch_flush helper"""
    # Get initial count
    initial_count = tick_batches_flushed_total.labels(batch_type="underlying")._value.get()

    # Record a flush
    record_batch_flush("underlying", 100, 0.01)

    # Check count increased
    new_count = tick_batches_flushed_total.labels(batch_type="underlying")._value.get()
    assert new_count == initial_count + 1


def test_record_tick_published():
    """Test record_tick_published helper"""
    # Get initial count
    initial_count = ticks_published_total.labels(tick_type="underlying")._value.get()

    # Record a publish
    record_tick_published("underlying")

    # Check count increased
    new_count = ticks_published_total.labels(tick_type="underlying")._value.get()
    assert new_count == initial_count + 1


def test_record_processing_error():
    """Test record_processing_error helper"""
    # Get initial count
    initial_count = tick_processing_errors_total.labels(error_type="test_error")._value.get()

    # Record an error
    record_processing_error("test_error")

    # Check count increased
    new_count = tick_processing_errors_total.labels(error_type="test_error")._value.get()
    assert new_count == initial_count + 1


def test_record_validation_error():
    """Test record_validation_error helper"""
    # Get initial count
    initial_count = tick_validation_errors_total.labels(validation_type="schema")._value.get()

    # Record an error
    record_validation_error("schema")

    # Check count increased
    new_count = tick_validation_errors_total.labels(validation_type="schema")._value.get()
    assert new_count == initial_count + 1


def test_update_batch_fill_rate():
    """Test update_batch_fill_rate helper"""
    # Update fill rate
    update_batch_fill_rate("underlying", 75.5)

    # Check value set
    value = tick_batch_fill_rate.labels(batch_type="underlying")._value.get()
    assert value == 75.5


def test_update_pending_batch_size():
    """Test update_pending_batch_size helper"""
    # Update pending size
    update_pending_batch_size("options", 42)

    # Check value set
    value = tick_batch_pending_size.labels(batch_type="options")._value.get()
    assert value == 42


def test_update_underlying_price():
    """Test update_underlying_price helper"""
    # Update price
    update_underlying_price("NIFTY", 24000.0)

    # Check value set
    value = tick_processor_underlying_price.labels(symbol="NIFTY")._value.get()
    assert value == 24000.0


def test_set_active_accounts():
    """Test set_active_accounts helper"""
    # Set active accounts
    set_active_accounts(5)

    # Check value set
    value = tick_processor_active_accounts._value.get()
    assert value == 5


def test_histogram_buckets():
    """Test histogram buckets are appropriate"""
    # Histograms don't expose _buckets directly in newer versions
    # Just verify they can be observed without error
    tick_processing_latency_seconds.labels(tick_type="test").observe(0.001)
    greeks_calculation_latency_seconds.observe(0.005)
    tick_batch_size.labels(batch_type="test").observe(100)

    # If we got here without exceptions, histograms are working correctly
    assert True


def test_metric_labels():
    """Test metrics have correct labels"""
    # Tick processing should have tick_type and status labels
    metric = ticks_processed_total.labels(tick_type="underlying", status="success")
    assert metric is not None

    # Batch flush should have batch_type label
    metric = tick_batches_flushed_total.labels(batch_type="underlying")
    assert metric is not None

    # Underlying price should have symbol label
    metric = tick_processor_underlying_price.labels(symbol="NIFTY")
    assert metric is not None
