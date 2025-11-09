# QA Validation - Claude CLI Prompt

**Role:** Senior QA Manager
**Priority:** HIGH
**Execution Order:** 4 (Run Fourth, After Code Expert Review)
**Estimated Time:** 6-8 hours
**Model:** Claude Sonnet 4.5

---

## Objective

Design and execute a comprehensive QA validation plan to assess test coverage, functional correctness, performance capacity, edge case handling, and production readiness of the ticker_service.

---

## Prerequisites

Before running this prompt, ensure:
- ✅ Architecture, security, and code quality assessments completed
- ✅ You have access to the `/tests` directory
- ✅ You can execute pytest commands via Bash tool
- ✅ You understand identified risks from previous assessments

---

## Prompt

```
You are a SENIOR QA MANAGER conducting comprehensive quality validation of the ticker_service.

CONTEXT:
The ticker_service is a production-critical financial trading system with:
- **Previous Assessments Completed**:
  - Architecture Review: 32 issues identified (5 P0, 8 P1, 12 P2, 7 P3)
  - Security Audit: 23 vulnerabilities found (4 CRITICAL, 8 HIGH, 7 MEDIUM, 4 LOW)
  - Code Quality Review: 17 technical debt items

- **System Criticality**:
  - Handles real money trading (financial risk)
  - Processes 1000+ ticks/second (performance critical)
  - Manages customer trading credentials (security critical)
  - Must maintain 99.9% uptime during market hours (reliability critical)

Your mission is to:
1. Assess current test coverage and quality
2. Execute existing test suites and document results
3. Identify critical testing gaps
4. Validate production readiness
5. Recommend test additions to protect against regressions

VALIDATION SCOPE:

1. TEST COVERAGE ANALYSIS (Priority: CRITICAL)
   - Review all test files in /tests directory
   - Calculate test coverage using pytest-cov
   - Identify modules with <70% coverage
   - Assess test quality (assertions, edge cases)
   - Check for flaky/brittle tests

   Files to review:
   - /tests/unit/* (mocked unit tests)
   - /tests/integration/* (real component tests)
   - /tests/load/* (performance tests)
   - conftest.py (shared fixtures)

   SPECIFIC CHECKS:
   - Run: `pytest --cov=app --cov-report=term-missing --cov-report=html`
   - Count tests: `pytest --collect-only | grep "<Function" | wc -l`
   - Find untested modules: Check coverage report for 0% files
   - Identify test gaps for critical paths (order execution, Greeks calculation)

2. FUNCTIONAL CORRECTNESS VALIDATION (Priority: CRITICAL)
   - Execute full test suite
   - Document pass/fail rates
   - Analyze test failures
   - Validate critical user flows
   - Test error scenarios

   Tests to run:
   - All unit tests: `pytest tests/unit/ -v --tb=short`
   - All integration tests: `pytest tests/integration/ -v --tb=short`
   - Load tests: `pytest tests/load/ -v --tb=short`

   SPECIFIC VALIDATIONS:
   - Order execution: place, modify, cancel, batch operations
   - Subscription management: add, remove, reload
   - WebSocket streaming: connection, authentication, data delivery
   - Historical data: fetch, Greeks enrichment
   - Multi-account failover: automatic retry with different account
   - Strike rebalancer: dynamic subscription updates
   - Token refresher: automatic token refresh

3. PERFORMANCE TESTING (Priority: HIGH)
   - Review load test results
   - Validate tick processing capacity (1000+ ticks/sec target)
   - Measure API endpoint response times
   - Check database query performance
   - Test WebSocket connection scalability
   - Monitor memory usage under load

   Tests to analyze:
   - test_tick_throughput.py (capacity validation)
   - Any stress/load test results

   SPECIFIC BENCHMARKS:
   - Tick processing: P99 latency <100ms
   - API endpoints: P95 latency <500ms
   - WebSocket broadcast: P99 latency <50ms
   - Memory: <2 GB steady state, <10 MB/hour growth
   - Order execution: P95 <1000ms

4. EDGE CASE & ERROR HANDLING (Priority: HIGH)
   - Test network failure scenarios
   - Validate circuit breaker behavior
   - Test retry logic (exponential backoff)
   - Validate invalid input handling
   - Test expired options handling
   - Test market hours transitions (live ↔ mock)
   - Test rate limit behavior

   Scenarios to validate:
   - Redis down → Circuit breaker opens, messages dropped gracefully
   - Postgres down → Graceful degradation, health check reports degraded
   - Kite API down → Failover to backup account
   - Invalid subscription request → Proper error response
   - Expired option tick → Filtered out correctly
   - Mock ↔ Live transition → No data corruption

5. REGRESSION RISK ASSESSMENT (Priority: HIGH)
   - Map identified issues to regression risk levels
   - Assess test protection for each issue
   - Identify high-risk changes needing new tests
   - Recommend regression test additions

   Risk analysis:
   - For each P0/CRITICAL issue: Is there a test protecting against regression?
   - Calculate protection ratio: (Protected issues / Total issues)
   - Identify unprotected high-risk areas

6. INTEGRATION TESTING (Priority: MEDIUM)
   - Test PostgreSQL integration (subscriptions, instruments, accounts)
   - Test Redis pub/sub (tick publishing)
   - Test Kite API integration (mocked and live if possible)
   - Test user_service JWT validation
   - Test WebSocket connections and authentication
   - Test historical data bootstrapping

   Components to validate:
   - subscription_store.py → PostgreSQL
   - redis_client.py → Redis
   - kite/client.py → Kite API
   - jwt_auth.py → User service
   - routes_websocket.py → WebSocket
   - historical_bootstrapper.py → Backfill logic

7. DATA INTEGRITY VALIDATION (Priority: MEDIUM)
   - Validate Greeks calculation accuracy
   - Test symbol normalization correctness
   - Verify subscription reconciliation logic
   - Test order task idempotency
   - Validate mock data state cleanup

   Specific validations:
   - Greeks: Compare calculated values with known benchmarks
   - Symbol normalization: "NIFTY 50" → "NIFTY" consistently
   - Idempotency: Same order submitted twice = same task ID
   - Mock cleanup: Expired options removed within 5 minutes

8. OBSERVABILITY & MONITORING (Priority: MEDIUM)
   - Verify Prometheus metrics exported correctly
   - Test health check endpoint
   - Validate PII sanitization in logs
   - Check error tracking completeness
   - Test dashboard metrics initialization

   Validations:
   - GET /metrics returns valid Prometheus format
   - GET /health returns accurate status
   - Logs do not contain emails, phone numbers, tokens
   - All exceptions logged with context
   - Dashboard metrics populated on startup

ANALYSIS METHOD:

For EACH area:
1. Use `read` to review test files and understand coverage
2. Use `bash` to execute pytest commands and collect results
3. Use `grep` to search for missing test patterns
4. Document gaps with specific file:line references

TEST EXECUTION:

Run the following commands and document results:

```bash
# Install dependencies (if not already installed)
# pip install -r requirements.txt

# Run all tests with coverage
pytest --cov=app --cov-report=term-missing --cov-report=html --cov-fail-under=0 -v --tb=short > test_results.txt 2>&1

# Run unit tests only
pytest tests/unit/ -v --tb=short

# Run integration tests only
pytest tests/integration/ -v --tb=short

# Run load tests
pytest tests/load/ -v --tb=short

# Count tests by type
find tests/unit -name "test_*.py" | wc -l
find tests/integration -name "test_*.py" | wc -l
find tests/load -name "test_*.py" | wc -l

# Calculate coverage percentage
pytest --cov=app --cov-report=term | grep "TOTAL"
```

DELIVERABLE FORMAT:

Create `/docs/assessment_2/04_qa_validation_report.md` containing:

## Executive Summary
- **Overall Quality Grade**: A/B/C/D/F
- **Test Coverage**: XX% (vs. 70% target)
- **Test Pass Rate**: XX% (passed/total)
- **Critical Gaps**: X gaps identified
- **Production Readiness**: READY / NOT READY / CONDITIONAL

## Test Coverage Analysis

### Coverage by Module

| Module | Statements | Missing | Coverage | Status |
|--------|------------|---------|----------|--------|
| app/main.py | 500 | 150 | 70% | ✅ |
| app/generator.py | 400 | 250 | 37% | ❌ |
| app/order_executor.py | 300 | 30 | 90% | ✅ |
| ... | ... | ... | ... | ... |
| **TOTAL** | **X,XXX** | **X,XXX** | **XX%** | **✅/❌** |

### Critical Modules (<70% Coverage)

1. **generator.py**: 37% coverage (250/400 statements missing)
   - Missing: Mock state transitions, historical bootstrapping
   - Risk: CRITICAL (core streaming logic)
   - Recommendation: Add 15 test cases (effort: 2 days)

2. [Continue for all <70% modules]

## Test Execution Results

```
=========================== Test Summary ===========================
Total Tests:     XXX
Passed:          XXX (XX%)
Failed:          XX (XX%)
Errors:          XX (XX%)
Skipped:         XX (XX%)
Duration:        XX.XX seconds
================================================================
```

### Failed Tests Analysis

#### test_order_executor.py::test_idempotency_collision
**Status**: FAILED
**Error**: AssertionError: Expected task_id to match, got different ID
**Root Cause**: [Analysis of why test failed]
**Impact**: HIGH (idempotency not working)
**Recommendation**: [Fix required]

[Continue for all failed tests]

## Performance Test Results

| Test | Target | Actual | Status | Notes |
|------|--------|--------|--------|-------|
| Tick throughput | 1000/sec | 1250/sec | ✅ PASS | Exceeds target by 25% |
| API latency (P95) | <500ms | 380ms | ✅ PASS | Good headroom |
| Memory under load | <2 GB | 1.8 GB | ✅ PASS | Steady state |
| WebSocket P99 | <50ms | 42ms | ✅ PASS | Good performance |

## Gap Analysis

### Critical Testing Gaps

#### GAP-001: Order Execution Not Fully Tested
**Module**: order_executor.py (90% coverage but critical paths missing)
**Missing Tests**:
- Multi-account failover scenario
- Circuit breaker state transitions
- Task cleanup on memory limit
- Dead letter queue handling

**Risk**: CRITICAL (financial transactions)
**Recommendation**: Add test cases (code provided below)
**Effort**: 1 day

```python
# Recommended test case
async def test_order_execution_with_failover():
    """Test order execution fails over to backup account when primary fails"""
    # Test implementation...
```

#### GAP-002: WebSocket Authentication Not Tested
**Module**: routes_websocket.py (0% coverage)
**Missing Tests**:
- JWT token validation on connection
- Token expiration handling
- Unauthorized connection rejection

**Risk**: HIGH (security vulnerability)
**Recommendation**: Add security test suite (code provided)
**Effort**: 4 hours

[Continue for all critical gaps]

## Regression Risk Matrix

Map all previously identified issues to test coverage:

| Issue ID | Issue | Risk | Test Coverage | Protected? |
|----------|-------|------|---------------|------------|
| ARCH-P0-001 | WebSocket deadlock | CRITICAL | 0% | ❌ NO |
| SEC-CRITICAL-001 | API key timing attack | CRITICAL | 0% | ❌ NO |
| CODE-P1-001 | God class complexity | HIGH | 37% | ⚠️ PARTIAL |

**Summary**:
- CRITICAL issues: X total, Y protected (Z%)
- HIGH issues: X total, Y protected (Z%)
- MEDIUM issues: X total, Y protected (Z%)

## Production Readiness Checklist

| Category | Requirement | Status | Notes |
|----------|-------------|--------|-------|
| **Functional Validation** |
| Core functionality | All critical flows tested | ✅/❌ | [Details] |
| Error handling | All error paths tested | ✅/❌ | [Details] |
| Edge cases | Boundary conditions tested | ✅/❌ | [Details] |
| **Performance Validation** |
| Load testing | 1000+ ticks/sec sustained | ✅/❌ | [Results] |
| API latency | P95 <500ms | ✅/❌ | [Results] |
| Memory | No leaks detected | ✅/❌ | [Results] |
| **Security Validation** |
| Authentication | All auth flows tested | ✅/❌ | [Details] |
| Authorization | Permission checks tested | ✅/❌ | [Details] |
| Input validation | Injection tests passed | ✅/❌ | [Details] |
| **Monitoring Validation** |
| Metrics | Prometheus metrics validated | ✅/❌ | [Details] |
| Health checks | /health endpoint tested | ✅/❌ | [Details] |
| Logging | PII sanitization verified | ✅/❌ | [Details] |
| **Documentation** |
| API docs | All endpoints documented | ✅/❌ | [Details] |
| Runbook | Operational procedures | ✅/❌ | [Details] |
| Test docs | Test coverage documented | ✅/❌ | [Details] |

**OVERALL**: ✅ PRODUCTION READY / ❌ NOT READY / ⚠️ CONDITIONAL

## Recommendations

### Immediate Actions (Block Production)
1. Fix all failing tests (XX failures)
2. Achieve 70% minimum coverage (currently XX%)
3. Add security test suite (0 security tests currently)
4. Test order execution failover (0% coverage)

**Estimated Effort**: X days

### Short-Term (Pre-Production)
1. Add WebSocket authentication tests
2. Test circuit breaker state transitions
3. Validate Greeks calculation accuracy
4. Test market hours transitions

**Estimated Effort**: Y days

### Medium-Term (Post-Production)
1. Increase coverage to 85%
2. Add chaos engineering tests
3. Implement automated performance regression testing

**Estimated Effort**: Z days

## Testing Roadmap

**Week 1: Critical Gaps**
- Fix failing tests (8 hours)
- Order execution tests (16 hours)
- Security test suite (24 hours)

**Weeks 2-3: Coverage Improvement**
- WebSocket tests (16 hours)
- Integration tests (24 hours)
- Edge case tests (16 hours)

**Weeks 4-6: Comprehensive Validation**
- Performance testing (16 hours)
- Chaos engineering (24 hours)
- Documentation (8 hours)

**Total Effort**: ~200 hours (5 weeks, 2 QA engineers)

CRITICAL CONSTRAINTS:

1. ⚠️ **ACTUAL EXECUTION**: Run real tests, don't just analyze
2. 🔍 **EVIDENCE-BASED**: Document actual pass/fail results
3. 📊 **COVERAGE METRICS**: Calculate real coverage percentages
4. 🎯 **SPECIFIC GAPS**: Identify exact missing test cases
5. ⏱️ **EFFORT ESTIMATES**: Provide realistic time to close gaps

QUALITY DEFINITIONS:

- **A (Excellent)**: >85% coverage, 100% pass rate, all critical paths tested
- **B (Good)**: 70-85% coverage, >95% pass rate, most critical paths tested
- **C (Acceptable)**: 50-70% coverage, >90% pass rate, some gaps in critical paths
- **D (Poor)**: 30-50% coverage, >80% pass rate, many gaps in critical paths
- **F (Failing)**: <30% coverage, <80% pass rate, critical paths untested

OUTPUT REQUIREMENTS:

- Actual test execution results (pass/fail counts)
- Real coverage percentages from pytest-cov
- Specific test cases recommended (with code examples)
- Gap analysis with file:line references
- Regression risk matrix for all identified issues
- Prioritized testing roadmap with effort estimates

BEGIN VALIDATION NOW.

Use all available tools (bash, read, grep) to execute tests and conduct thorough QA validation.
```

---

## Expected Output

A comprehensive QA validation report (~150-200 KB) with:
- Executive summary with quality grade
- Real test coverage data (from pytest-cov)
- Test execution results (actual pass/fail counts)
- Performance test results
- Critical gap analysis with test recommendations
- Regression risk matrix
- Production readiness checklist
- Testing roadmap with effort estimates

---

## Success Criteria

✅ Real tests executed via pytest
✅ Coverage data from pytest-cov included
✅ All test failures analyzed with root cause
✅ Specific test cases recommended with code examples
✅ Regression risk matrix for all issues
✅ Production readiness assessment (READY/NOT READY/CONDITIONAL)
✅ Testing roadmap with timeline and effort

---

## Next Steps

After completion:
1. Fix all failing tests
2. Implement recommended test cases
3. Re-run coverage analysis to validate improvements
4. Proceed to **05_release_decision.md** (Production Release Review)
