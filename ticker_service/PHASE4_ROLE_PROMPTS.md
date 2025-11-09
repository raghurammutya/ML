# PHASE 4 ROLE-BASED PROMPTS
**Performance & Observability Enhancements**

**Date**: November 8, 2025
**Prerequisites**: Phase 1 (Critical Fixes) + Phase 2 (God Class Part 1) + Phase 3 (Tick Processor) Complete
**Target**: Enhance performance, observability, and reliability of the tick processing pipeline

---

## OVERVIEW

Phase 4 focuses on **performance optimization and observability** for the tick processing system. After successfully extracting services and fixing critical bugs in Phases 1-3, we now optimize for high-throughput production workloads and add comprehensive monitoring.

### Key Focus Areas

1. **Tick Batching** - Batch Redis publishes to reduce overhead
2. **Performance Metrics** - Track latency and throughput per component
3. **Validation Pipeline** - Add tick validation and error handling
4. **Load Testing** - Verify system handles 5000+ instruments
5. **Monitoring Dashboard** - Grafana dashboards for real-time observability

---

## ARCHITECTURAL CONTEXT

### Current State (After Phase 3)
```
TickProcessor (310 lines, 93% coverage)
├── process_ticks() - Per-tick processing
├── publish_underlying_bar() - Immediate Redis publish
├── publish_option_snapshot() - Immediate Redis publish
└── No batching, no metrics, no validation
```

### Target State (After Phase 4)
```
TickProcessor (enhanced)
├── Tick batching (100ms windows)
├── Per-component latency metrics
├── Validation pipeline
├── Error rate tracking
└── Performance monitoring
```

---

## SUCCESS CRITERIA

- ✅ **10x throughput improvement** through batching (target: 10,000 ticks/sec)
- ✅ **< 1ms P99 latency** for tick processing (excluding Redis)
- ✅ **Comprehensive metrics** exposed via Prometheus
- ✅ **Validation** catches malformed ticks before processing
- ✅ **Load tested** with 5000+ instruments at peak traffic
- ✅ **Grafana dashboard** for real-time monitoring
- ✅ **100% backward compatible** - no breaking changes

---

## PROMPT 1: Implement Tick Batching

### Role
You are a senior performance engineer specializing in high-throughput data pipelines and Redis optimization.

### Context
Currently, the TickProcessor publishes each tick to Redis immediately, causing:
- High Redis connection overhead (1 publish per tick)
- Network latency accumulation
- Poor throughput at scale (limited to ~1000 ticks/sec)

For 5000 instruments receiving ticks every second, we need batching.

### Task
Implement batching for Redis publishes to achieve 10x throughput improvement.

### Implementation Steps

1. **Create `app/services/tick_batcher.py`**
   - Batch ticks into time-based windows (100ms default)
   - Separate batches for underlying and options
   - Flush on window expiry or batch size limit
   - Background flusher task

2. **Key Responsibilities**
   ```python
   class TickBatcher:
       """Batches ticks for efficient Redis publishing."""

       def __init__(self, window_ms: int = 100, max_batch_size: int = 1000):
           self._window_ms = window_ms
           self._max_batch_size = max_batch_size
           self._underlying_batch: List[dict] = []
           self._options_batch: List[OptionSnapshot] = []
           self._last_flush = time.time()
           self._flusher_task: Optional[asyncio.Task] = None

       async def add_underlying(self, bar: dict) -> None:
           """Add underlying bar to batch"""

       async def add_option(self, snapshot: OptionSnapshot) -> None:
           """Add option snapshot to batch"""

       async def _flush_batches(self) -> None:
           """Flush all pending batches to Redis"""

       async def _flusher_loop(self) -> None:
           """Background task that flushes batches periodically"""

       async def start(self) -> None:
           """Start background flusher"""

       async def stop(self) -> None:
           """Stop flusher and flush remaining batches"""
   ```

3. **Integration with TickProcessor**
   - Inject TickBatcher into TickProcessor
   - Replace immediate publishes with batch adds:
     ```python
     # BEFORE:
     await publish_underlying_bar(bar)

     # AFTER:
     await self._batcher.add_underlying(bar)
     ```
   - Add flush on shutdown

4. **Configuration**
   ```python
   # app/config.py
   tick_batch_window_ms: int = Field(default=100, description="Tick batch window in milliseconds")
   tick_batch_max_size: int = Field(default=1000, description="Maximum batch size before flush")
   ```

### Testing Requirements

Create `tests/integration/test_tick_batcher.py`:
- Test batching accumulates ticks
- Test time-based flushing (100ms window)
- Test size-based flushing (max batch size)
- Test graceful shutdown flushes remaining
- Test throughput improvement (benchmark)

### Acceptance Criteria
- [ ] TickBatcher service created (~200 lines)
- [ ] Integrated with TickProcessor
- [ ] Batching tests pass (5+ tests)
- [ ] Throughput improved by 5-10x (benchmarked)
- [ ] No data loss during shutdown
- [ ] Backward compatible (can disable batching)

---

## PROMPT 2: Add Performance Metrics

### Role
You are a senior SRE engineer specializing in observability, metrics, and monitoring systems.

### Context
We have no visibility into tick processing performance:
- No latency tracking per component
- No throughput metrics
- No error rate tracking
- Cannot identify bottlenecks

Need comprehensive Prometheus metrics for production monitoring.

### Task
Add detailed performance metrics to all tick processing components.

### Implementation Steps

1. **Create `app/metrics/tick_metrics.py`**
   - Define Prometheus metrics for tick processing
   - Histogram for latencies (P50, P95, P99)
   - Counter for throughput
   - Gauge for batch sizes
   - Counter for errors

2. **Key Metrics**
   ```python
   from prometheus_client import Histogram, Counter, Gauge

   # Latency metrics (in seconds)
   tick_processing_latency = Histogram(
       "tick_processing_latency_seconds",
       "Time to process a single tick",
       ["tick_type"],  # underlying or option
       buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0]
   )

   # Throughput metrics
   ticks_processed_total = Counter(
       "ticks_processed_total",
       "Total number of ticks processed",
       ["tick_type", "status"]  # success or error
   )

   # Batching metrics
   tick_batch_size = Histogram(
       "tick_batch_size",
       "Number of ticks in each batch",
       ["batch_type"],  # underlying or options
       buckets=[10, 50, 100, 500, 1000, 5000]
   )

   tick_batch_flush_latency = Histogram(
       "tick_batch_flush_latency_seconds",
       "Time to flush a batch to Redis",
       ["batch_type"]
   )

   # Error metrics
   tick_processing_errors_total = Counter(
       "tick_processing_errors_total",
       "Total tick processing errors",
       ["error_type"]  # validation, greeks, publish, etc.
   )

   # Current state
   tick_processor_active_accounts = Gauge(
       "tick_processor_active_accounts",
       "Number of accounts currently processing ticks"
   )
   ```

3. **Instrumentation Points**
   - Instrument TickProcessor.process_ticks()
   - Instrument Greeks calculation
   - Instrument TickBatcher flush operations
   - Instrument Redis publishes
   - Track errors at each stage

4. **Add /metrics Endpoint**
   ```python
   # app/main.py
   from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

   @app.get("/metrics")
   async def metrics():
       """Prometheus metrics endpoint"""
       return Response(
           content=generate_latest(),
           media_type=CONTENT_TYPE_LATEST
       )
   ```

### Testing Requirements

Create `tests/unit/test_tick_metrics.py`:
- Test metrics are incremented correctly
- Test histogram buckets are appropriate
- Test error counters track failures
- Test /metrics endpoint returns valid Prometheus format

### Acceptance Criteria
- [ ] Comprehensive metrics defined (~100 lines)
- [ ] All components instrumented
- [ ] /metrics endpoint added
- [ ] Metrics tests pass (5+ tests)
- [ ] Metrics appear in Prometheus
- [ ] No performance overhead (< 0.1ms per metric)

---

## PROMPT 3: Add Tick Validation Pipeline

### Role
You are a senior backend engineer specializing in data validation and error handling.

### Context
Currently, no validation of incoming tick data:
- Malformed ticks cause processing errors
- Invalid prices can corrupt Greeks calculations
- No schema enforcement
- Errors are only caught during processing

Need a validation layer to catch issues early.

### Task
Implement a tick validation pipeline that validates all incoming ticks before processing.

### Implementation Steps

1. **Create `app/services/tick_validator.py`**
   - Schema validation for ticks
   - Business rule validation
   - Early error detection
   - Validation metrics

2. **Key Responsibilities**
   ```python
   from typing import Dict, Any, Optional, List
   from pydantic import BaseModel, validator

   class TickValidationError(Exception):
       """Raised when tick validation fails"""
       pass

   class UnderlyingTickSchema(BaseModel):
       """Schema for underlying/index ticks"""
       instrument_token: int
       last_price: float
       volume: int
       timestamp: int

       @validator('last_price')
       def validate_price(cls, v):
           if v <= 0:
               raise ValueError("Price must be positive")
           if v > 1000000:  # Sanity check
               raise ValueError("Price unreasonably high")
           return v

   class OptionTickSchema(BaseModel):
       """Schema for option ticks"""
       instrument_token: int
       last_price: float
       volume: int
       oi: int
       timestamp: int

       @validator('last_price')
       def validate_price(cls, v):
           if v < 0:
               raise ValueError("Option price cannot be negative")
           return v

   class TickValidator:
       """Validates incoming tick data"""

       def __init__(self, strict_mode: bool = False):
           self._strict_mode = strict_mode
           self._validation_errors: List[str] = []

       def validate_underlying_tick(self, tick: Dict[str, Any]) -> bool:
           """Validate underlying tick, return True if valid"""

       def validate_option_tick(self, tick: Dict[str, Any]) -> bool:
           """Validate option tick, return True if valid"""

       def validate_batch(self, ticks: List[Dict[str, Any]], instrument_type: str) -> List[Dict[str, Any]]:
           """Validate batch of ticks, return only valid ones"""

       def get_validation_errors(self) -> List[str]:
           """Get list of validation errors"""
   ```

3. **Integration with TickProcessor**
   - Inject TickValidator into TickProcessor
   - Validate ticks before processing:
     ```python
     # In process_ticks()
     valid_ticks = []
     for tick in ticks:
         if self._validator.validate_tick(tick, instrument.segment):
             valid_ticks.append(tick)
         else:
             tick_validation_errors_total.inc()
             logger.warning(f"Invalid tick skipped: {tick}")

     # Process only valid ticks
     for tick in valid_ticks:
         ...
     ```

4. **Configuration**
   ```python
   # app/config.py
   tick_validation_enabled: bool = Field(default=True, description="Enable tick validation")
   tick_validation_strict: bool = Field(default=False, description="Strict validation mode (reject on any error)")
   ```

### Testing Requirements

Create `tests/unit/test_tick_validator.py`:
- Test valid ticks pass validation
- Test invalid prices are rejected
- Test malformed ticks are rejected
- Test batch validation filters invalid ticks
- Test validation error tracking

### Acceptance Criteria
- [ ] TickValidator service created (~150 lines)
- [ ] Pydantic schemas defined for all tick types
- [ ] Integrated with TickProcessor
- [ ] Validation tests pass (8+ tests)
- [ ] Validation metrics tracked
- [ ] Configurable (can disable for testing)

---

## PROMPT 4: Create Load Testing Suite

### Role
You are a senior performance engineer specializing in load testing, capacity planning, and benchmarking.

### Context
System has never been load tested:
- Unknown capacity limits
- Unknown performance at scale
- No baseline metrics
- No regression testing

Need comprehensive load tests to verify 5000+ instrument capacity.

### Task
Create a load testing suite that validates system performance under realistic production loads.

### Implementation Steps

1. **Create `tests/load/test_tick_throughput.py`**
   - Simulate 5000 instruments
   - Generate realistic tick rates
   - Measure throughput and latency
   - Identify bottlenecks

2. **Load Test Scenarios**
   ```python
   import asyncio
   import time
   from statistics import mean, median
   from typing import List

   @pytest.mark.load
   async def test_throughput_1000_instruments():
       """Test throughput with 1000 instruments (baseline)"""
       # Setup: 1000 instruments
       # Generate: 1 tick/sec per instrument for 60 seconds
       # Measure: P50, P95, P99 latency
       # Assert: P99 < 100ms

   @pytest.mark.load
   async def test_throughput_5000_instruments():
       """Test throughput with 5000 instruments (target)"""
       # Setup: 5000 instruments
       # Generate: 1 tick/sec per instrument for 60 seconds
       # Measure: Throughput (ticks/sec)
       # Assert: Throughput > 5000 ticks/sec

   @pytest.mark.load
   async def test_burst_traffic():
       """Test burst traffic handling"""
       # Setup: 1000 instruments
       # Generate: Burst of 10,000 ticks in 1 second
       # Measure: Recovery time, no data loss
       # Assert: All ticks processed within 5 seconds

   @pytest.mark.load
   async def test_sustained_load():
       """Test sustained load over 10 minutes"""
       # Setup: 2000 instruments
       # Generate: 1 tick/sec per instrument for 10 minutes
       # Measure: Memory usage, latency drift
       # Assert: No memory leaks, latency stable

   @pytest.mark.load
   async def test_greeks_calculation_overhead():
       """Test Greeks calculation overhead"""
       # Setup: 1000 option instruments
       # Generate: Ticks requiring Greeks calculation
       # Measure: Latency with vs without Greeks
       # Assert: Greeks add < 5ms per tick
   ```

3. **Performance Benchmarks**
   ```python
   class TickProcessorBenchmark:
       """Benchmark TickProcessor performance"""

       async def benchmark_tick_processing(self, num_ticks: int) -> dict:
           """Benchmark processing N ticks"""
           start = time.perf_counter()

           # Process ticks
           await process_n_ticks(num_ticks)

           elapsed = time.perf_counter() - start
           throughput = num_ticks / elapsed

           return {
               "ticks_processed": num_ticks,
               "elapsed_seconds": elapsed,
               "throughput_ticks_per_sec": throughput,
               "latency_per_tick_ms": (elapsed / num_ticks) * 1000,
           }
   ```

4. **Load Test Runner**
   ```bash
   # tests/load/run_load_tests.sh
   #!/bin/bash

   echo "Running load tests..."
   pytest tests/load/ -v -m load --tb=short

   echo "Generating performance report..."
   python tests/load/generate_report.py
   ```

### Testing Requirements

Create load test suite:
- Baseline test (1000 instruments)
- Scale test (5000 instruments)
- Burst test (10,000 ticks/sec)
- Sustained test (10 minutes)
- Regression test (compare vs baseline)

### Acceptance Criteria
- [ ] Load test suite created (5+ scenarios)
- [ ] Tests run successfully
- [ ] Performance baselines documented
- [ ] Bottlenecks identified and documented
- [ ] System handles 5000+ instruments
- [ ] P99 latency < 100ms at target load

---

## PROMPT 5: Create Monitoring Dashboard

### Role
You are a senior SRE engineer specializing in Grafana dashboards, alerting, and production monitoring.

### Context
No production monitoring exists:
- No real-time visibility
- No alerting on anomalies
- No historical trends
- Cannot diagnose issues quickly

Need Grafana dashboards for ops team.

### Task
Create comprehensive Grafana dashboards for tick processing monitoring.

### Implementation Steps

1. **Create `monitoring/grafana/tick-processing-dashboard.json`**
   - Dashboard configuration for Grafana
   - Panels for all key metrics
   - Alerting rules
   - Production-ready

2. **Dashboard Panels**
   ```
   Dashboard: Tick Processing

   Row 1: Overview
   - [Panel] Tick Throughput (ticks/sec)
   - [Panel] Active Accounts
   - [Panel] Error Rate (errors/sec)
   - [Panel] System Health (OK/Warning/Critical)

   Row 2: Latency
   - [Panel] Tick Processing Latency (P50, P95, P99)
   - [Panel] Batch Flush Latency
   - [Panel] Greeks Calculation Latency
   - [Panel] End-to-End Latency

   Row 3: Batching
   - [Panel] Batch Size Distribution
   - [Panel] Batches Flushed per Second
   - [Panel] Batch Fill Rate (%)
   - [Panel] Pending Batch Size

   Row 4: Errors
   - [Panel] Validation Errors
   - [Panel] Processing Errors
   - [Panel] Redis Errors
   - [Panel] Error Rate by Type

   Row 5: Business Metrics
   - [Panel] Underlying Ticks Processed
   - [Panel] Option Ticks Processed
   - [Panel] Greeks Calculations per Second
   - [Panel] Market Depth Updates
   ```

3. **Alerting Rules**
   ```yaml
   # monitoring/alerts/tick-processing-alerts.yml

   groups:
     - name: tick_processing
       interval: 30s
       rules:
         - alert: HighTickProcessingLatency
           expr: tick_processing_latency_seconds{quantile="0.99"} > 0.1
           for: 5m
           labels:
             severity: warning
           annotations:
             summary: "High P99 tick processing latency"
             description: "P99 latency is {{ $value }}s (threshold: 0.1s)"

         - alert: HighErrorRate
           expr: rate(tick_processing_errors_total[5m]) > 10
           for: 2m
           labels:
             severity: critical
           annotations:
             summary: "High tick processing error rate"
             description: "Error rate: {{ $value }}/sec"

         - alert: LowThroughput
           expr: rate(ticks_processed_total[1m]) < 100
           for: 5m
           labels:
             severity: warning
           annotations:
             summary: "Low tick processing throughput"
             description: "Throughput: {{ $value }} ticks/sec (expected > 1000)"

         - alert: NoTicksProcessed
           expr: increase(ticks_processed_total[5m]) == 0
           for: 5m
           labels:
             severity: critical
           annotations:
             summary: "No ticks being processed"
             description: "Tick processing may be stalled"
   ```

4. **Deployment**
   ```bash
   # monitoring/deploy.sh
   #!/bin/bash

   # Import Grafana dashboard
   curl -X POST \
     -H "Content-Type: application/json" \
     -d @grafana/tick-processing-dashboard.json \
     http://grafana:3000/api/dashboards/db

   # Configure Prometheus alerts
   kubectl apply -f alerts/tick-processing-alerts.yml
   ```

### Testing Requirements

Create monitoring validation:
- Verify all metrics appear in dashboard
- Test alert firing thresholds
- Validate query performance
- Check dashboard loads in < 2 seconds

### Acceptance Criteria
- [ ] Grafana dashboard created with 15+ panels
- [ ] Alerting rules defined (4+ alerts)
- [ ] Dashboard imports successfully
- [ ] All metrics visible
- [ ] Alerts fire correctly in test
- [ ] Documentation for ops team

---

## IMPLEMENTATION SEQUENCE

### Week 1: Performance
- **Days 1-2**: PROMPT 1 (Tick Batching) - 6-8 hours
- **Days 3-4**: PROMPT 2 (Performance Metrics) - 4-6 hours

### Week 2: Validation & Testing
- **Day 5**: PROMPT 3 (Validation Pipeline) - 4-5 hours
- **Days 6-7**: PROMPT 4 (Load Testing) - 8-10 hours

### Week 3: Observability
- **Days 8-9**: PROMPT 5 (Monitoring Dashboard) - 4-6 hours
- **Day 10**: Integration testing and documentation - 4 hours

**Total Estimated Effort**: 30-39 hours

---

## DEPENDENCIES

### Prerequisites
- ✅ Phase 1 Complete (Critical Fixes)
- ✅ Phase 2 Complete (God Class Part 1)
- ✅ Phase 3 Complete (Tick Processor)
- ✅ All 79 tests passing
- ✅ Redis available for testing
- ☐ Prometheus available for metrics
- ☐ Grafana available for dashboards

### External Dependencies
- Prometheus (metrics collection)
- Grafana (dashboards)
- Redis (tick publishing)
- pytest-benchmark (performance testing)

---

## SUCCESS METRICS

### Performance Targets
- **Throughput**: > 10,000 ticks/sec (10x improvement)
- **Latency P99**: < 100ms (excluding Redis)
- **Latency P50**: < 10ms
- **Batch efficiency**: > 80% batch fill rate
- **Error rate**: < 0.1% of ticks

### Observability Targets
- **Metrics coverage**: 20+ metrics exposed
- **Dashboard panels**: 15+ panels
- **Alerts defined**: 4+ production alerts
- **Alert accuracy**: < 5% false positives

### Quality Targets
- **Test coverage**: > 85% for new code
- **Load tests**: 5+ scenarios
- **Validation coverage**: 100% of tick fields
- **Documentation**: Complete ops runbook

---

## ROLLBACK STRATEGY

Each prompt can be rolled back independently:

1. **If PROMPT 1 fails**: Disable batching, revert to immediate publish
2. **If PROMPT 2 fails**: Remove metrics instrumentation
3. **If PROMPT 3 fails**: Disable validation, log warnings only
4. **If PROMPT 4 fails**: Skip load tests (no production impact)
5. **If PROMPT 5 fails**: Use basic Prometheus metrics

All rollbacks maintain Phase 1+2+3 functionality.

---

## MONITORING & VALIDATION

### Success Validation
- **Performance**: Load tests show 10x throughput improvement
- **Reliability**: Error rate < 0.1% under load
- **Observability**: All metrics visible in Grafana
- **Capacity**: System handles 5000+ instruments
- **Stability**: No degradation over 10-minute sustained load

### Red Flags (Stop Implementation)
- ❌ Performance regression > 10%
- ❌ Memory leaks detected
- ❌ Error rate > 1% under normal load
- ❌ P99 latency > 500ms
- ❌ Data loss during batching

---

## CONCLUSION

Phase 4 transforms the tick processing system from **functional** to **production-grade** by adding:
- **Performance**: 10x throughput via batching
- **Observability**: Comprehensive metrics and dashboards
- **Reliability**: Validation pipeline and error handling
- **Confidence**: Load testing validates capacity

After Phase 4, the system will be **truly production-ready** for high-scale deployments.

---

**Document Version**: 1.0
**Author**: Claude Code (Sonnet 4.5)
**Date**: November 8, 2025
**Status**: READY FOR IMPLEMENTATION
