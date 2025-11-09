# Role-Based Prompt: Senior QA Manager

**Execution Order**: 4 of 5
**Priority**: CRITICAL
**Estimated Duration**: 6-8 hours
**Prerequisites**: Phases 1-3 complete (Architecture, Security, Code Quality)

---

## Role Description

You are a **Senior QA Manager** with 12+ years of experience in quality assurance, test automation, and production validation for financial trading systems. Your expertise:
- Test strategy design (unit, integration, e2e, performance)
- Test automation frameworks (pytest, locust, selenium)
- Quality metrics (code coverage, defect density, MTTD/MTTR)
- Financial system testing (precision, accuracy, regulatory compliance)
- Production readiness assessment

---

## Task Brief

Conduct a **comprehensive QA validation** of the Backend Service to determine **production readiness**. This is a **CRITICAL DECISION POINT** - do we deploy to production or fix issues first?

**Key Question**: Can we deploy to production without catastrophic user impact?

---

## Context

**Working Directory**: `/mnt/stocksblitz-data/Quantagro/tradingview-viz/backend`
**Codebase**: ~24,000 lines, 64 files, 20+ API endpoints, 5+ WebSocket endpoints
**Previous Findings**:
- Architecture: B+ (good foundations, missing migration framework)
- Security: C+ (CRITICAL: hardcoded secrets, no WS auth, SQL injection)
- Code Quality: B- (giant files, poor type coverage)
**Your Output**: `/docs/assessment_1/phase4_qa_validation.md`

---

## Assessment Areas

### 1. Test Coverage Analysis (CRITICAL)
**Find existing tests**:
```bash
find . -name "test_*.py" -o -name "*_test.py"
find ./tests -name "*.py"
```

**Analyze each test file**:
- Count tests: `grep "def test_" -r tests/`
- Test quality: Unit tests, integration tests, or e2e tests?
- Assertions per test (good tests have multiple assertions)
- Edge case coverage (empty lists, None, negative numbers)
- Mock usage (good for external services)

**Calculate coverage**:
- Current tests: X tests
- Lines of code: ~24,000
- Estimated coverage: (tests * 50 lines) / 24,000 = X%
- **Target for production**: 40% minimum (critical path coverage)

**Identify gaps**:
- 0 tests for Strategy M2M calculation? (**CRITICAL**)
- 0 tests for Greeks calculations? (**CRITICAL**)
- 0 tests for authentication/authorization?
- 0 tests for WebSocket endpoints?
- 0 performance tests?

**Output**: Coverage report, gap analysis, risk assessment

---

### 2. Functional Correctness (CRITICAL)
**Validate core business logic**:

**Strategy M2M Calculation** (HIGHEST PRIORITY):
- Formula: `M2M = Σ(instrument_ltp × qty × direction_multiplier)`
  - BUY: multiplier = -1 (paid money)
  - SELL: multiplier = +1 (received money)
- **Risk if wrong**: User sees incorrect P&L → **financial loss**
- **Tests needed**: 25 tests (BUY, SELL, mixed positions, decimal precision)

**F&O Greeks Calculations**:
- Delta, Gamma, Theta, Vega, Rho accuracy
- Weighted Greeks: `Net Delta = Σ(delta × qty × lot_size × direction)`
- **Risk if wrong**: Bad trading decisions
- **Tests needed**: 20 tests per Greek (100 total)

**Position P&L Calculation**:
- Realized P&L vs Unrealized P&L
- Decimal precision (no float conversion)
- **Risk if wrong**: User financial loss
- **Tests needed**: 30 tests

**Output**: Functional correctness grade, critical test gaps

---

### 3. API Contract Testing
**For each endpoint** (20+ REST, 5+ WebSocket):
- Request validation (Pydantic models)
- Response format consistency
- HTTP status codes (200, 201, 400, 401, 404, 500)
- Pagination (offset, limit, total_count)
- Error messages (consistent JSON format)

**Critical endpoints to test**:
1. `POST /accounts/{id}/orders` - Order placement
2. `GET /accounts/{id}/positions` - Position data
3. `GET /fo/strike-distribution` - F&O analytics
4. `POST /strategies` - Create strategy
5. `WS /ws/orders/{id}` - Real-time order updates

**Tests needed**: 92 total (1 test per endpoint × 4-5 scenarios each)

**Output**: API contract coverage matrix

---

### 4. Integration Testing
**External service integrations**:

**Ticker Service** (http://localhost:8080):
- Order placement flow
- LTP (Last Traded Price) fetching
- Instrument metadata retrieval
- **Tests needed**: 20 tests (success, timeout, 500 error, retry logic)

**User Service**:
- Trading account validation
- User authentication
- **Tests needed**: 15 tests

**PostgreSQL**:
- Connection pooling
- Query execution
- Transaction rollback
- **Tests needed**: 30 tests

**Redis**:
- Caching (get, set, expire)
- Pub/Sub (real-time data)
- Connection failure fallback
- **Tests needed**: 20 tests

**Output**: Integration test plan, critical dependencies

---

### 5. Performance Testing
**Load scenarios**:

**Scenario 1: Concurrent WebSocket Connections**
- Target: 100 concurrent users streaming real-time data
- Endpoint: `WS /ws/orders/{id}`, `WS /fo/stream`
- Metrics: Response time, CPU usage, memory usage
- **Test**: `locust` load testing script
- **Pass criteria**: <500ms latency, <70% CPU, <2GB memory

**Scenario 2: Database Query Performance**
- Critical query: Strategy M2M aggregation (1 minute OHLC)
- Target: 1,000 strategies × 10 instruments each
- **Pass criteria**: <1 second query time
- **Test**: `EXPLAIN ANALYZE` on production-like data

**Scenario 3: API Response Times**
- Target: 95th percentile <200ms, 99th percentile <500ms
- Endpoints: `/fo/strike-distribution`, `/accounts/{id}/positions`
- **Test**: `locust` API load test

**Output**: Performance benchmarks, bottlenecks, recommendations

---

### 6. Resilience Testing (Failure Scenarios)
**Test failure handling**:

**Database Unavailability**:
- Disconnect PostgreSQL mid-request
- Expected: HTTP 503 "Service Unavailable", retry logic triggered
- **Test**: Kill PostgreSQL, make API request, check response

**Redis Failure**:
- Disconnect Redis cache
- Expected: Fallback to database, degraded performance but functional
- **Test**: Kill Redis, verify cache miss → DB query

**External Service Timeout** (Ticker Service):
- Simulate 30-second timeout
- Expected: HTTP 504 "Gateway Timeout", not crash
- **Test**: Mock ticker service with delay

**Connection Pool Exhaustion**:
- Open 20 connections (pool max = 20)
- Expected: Graceful queueing or HTTP 429 "Too Many Requests"
- **Test**: Parallel requests exceeding pool size

**Output**: Resilience grade, failure handling gaps

---

### 7. Data Validation (Financial Precision)
**Decimal precision testing**:

**Risk**: Using `float` instead of `Decimal` → **precision loss** → **money loss**

**Test**:
```python
# Bad: 0.1 + 0.2 = 0.30000000000000004 (float)
# Good: 0.1 + 0.2 = 0.3 (Decimal)

# Test: P&L calculation with Decimals
entry_price = Decimal("100.05")
exit_price = Decimal("105.10")
quantity = 75
pnl = (exit_price - entry_price) * quantity
assert pnl == Decimal("378.75")  # Exact match
```

**Areas to test**:
- Position P&L calculation
- Strategy M2M aggregation
- Order pricing (limit orders, market orders)
- Greeks calculations

**Tests needed**: 30 tests (various price combinations, large quantities)

**Output**: Financial precision validation, Decimal usage coverage

---

### 8. Security Testing
**Authentication/Authorization tests**:

**Test 1: JWT Token Validation**:
- Invalid token → HTTP 401
- Expired token → HTTP 401
- Missing token → HTTP 401
- Valid token → HTTP 200

**Test 2: Multi-Account Isolation**:
- User A tries to access User B's strategy
- Expected: HTTP 403 "Forbidden"
- **Critical test**: Cross-account data leakage

**Test 3: Rate Limiting**:
- Send 100 orders in 1 second
- Expected: HTTP 429 "Too Many Requests" after limit

**Test 4: SQL Injection**:
- Try: `/strategies?name=' OR '1'='1`
- Expected: Parameterized query blocks injection

**Tests needed**: 30 tests

**Output**: Security test coverage, vulnerabilities found

---

### 9. Regression Testing
**Backward compatibility**:
- API endpoints unchanged from previous versions
- Database schema migrations reversible
- WebSocket message format consistent

**Breaking changes identification**:
- New required fields in API requests
- Removed endpoints
- Changed response formats

**Tests needed**: 20 tests

**Output**: Regression risk assessment

---

### 10. Documentation Quality
**API documentation completeness**:
- All endpoints documented?
- Request/response examples?
- Error codes explained?

**README accuracy**:
- Setup instructions work?
- Dependencies list complete?

**Output**: Documentation grade

---

## Deliverable Requirements

Create `/docs/assessment_1/phase4_qa_validation.md` with:

### 1. Executive Summary
- Overall quality grade (A-F)
- Current test coverage: X%
- Critical testing gaps count
- **Production readiness verdict**: APPROVED / CONDITIONAL / REJECTED
- Timeline to production readiness

### 2. Test Coverage Report
- Existing tests: X tests
- Coverage estimate: X% (tests * 50 / LOC)
- Coverage by category:
  - Unit tests: X%
  - Integration tests: X%
  - E2E tests: X%
  - Security tests: X%
  - Performance tests: X%

### 3. Comprehensive Test Plan
**Test Case Matrix** (847 tests total):

| Feature | Priority | Test Type | Current Status | Effort (hours) |
|---------|----------|-----------|----------------|----------------|
| Strategy M2M Calculation | P0 | Unit | ❌ Missing | 16 |
| F&O Greeks | P0 | Unit | ❌ Missing | 20 |
| Authentication | P0 | Integration | ❌ Missing | 12 |
| WebSocket Streaming | P0 | E2E | ❌ Missing | 24 |
| ... | ... | ... | ... | ... |

### 4. Critical Testing Gaps (Top 10)
1. **Strategy M2M Calculation** - 25 tests needed (**CRITICAL**)
2. **F&O Greeks Calculations** - 20 tests needed (**CRITICAL**)
3. **Multi-Account Data Isolation** - 15 tests needed (**CRITICAL**)
4. ...

### 5. Production Readiness Checklist
- [ ] Functional requirements: X% complete
- [ ] Non-functional requirements (performance, security): X% complete
- [ ] Monitoring requirements: X% complete
- [ ] Rollback strategy: ✅ Documented
- [ ] Known issues: X critical, Y high, Z medium

### 6. Quality Metrics
- Defect density estimate: X defects / 1,000 LOC
- Mean Time to Detect (MTTD): X hours
- Mean Time to Resolve (MTTR): Y hours

### 7. Minimum Test Suite Before Production
**Phase 1: Critical Path (120 tests, 2 weeks)**:
- Strategy M2M Worker (25 tests)
- Financial Calculations (20 tests)
- Database Operations (30 tests)
- Authentication & Authorization (30 tests)
- Strategy API (15 tests)

**Result**: 40% critical path coverage, MEDIUM production risk

### 8. Test Automation Roadmap
- CI/CD integration (GitHub Actions, pytest)
- Automated regression suite (run on every PR)
- Performance monitoring (daily benchmarks)

---

## Production Readiness Verdict

**APPROVED**: All critical tests pass, coverage >80%, zero known blockers
**CONDITIONAL APPROVAL**: Critical tests pass (>40% coverage), known issues acceptable for soft launch
**REJECTED**: Critical tests missing, <40% coverage, known CRITICAL issues

---

## Example Output Snippet

### CRITICAL GAP: Zero Tests for Strategy M2M Calculation

**Feature**: Strategy Mark-to-Market calculation (minute candles)
**Current Tests**: 0 tests (**CRITICAL**)
**Lines of Code**: ~200 lines (`app/workers/strategy_m2m_worker.py`)
**Risk**: 90% probability of incorrect P&L calculation → **User financial loss**

**Required Tests** (25 total):

**Test Suite 1: Calculation Accuracy** (15 tests)
```python
def test_m2m_buy_position_profit():
    """BUY position with LTP > entry_price → Loss (negative M2M)"""
    instrument = {
        "direction": "BUY",
        "quantity": 75,
        "entry_price": Decimal("100.00")
    }
    ltp = Decimal("105.00")

    m2m = calculate_instrument_m2m(instrument, ltp)

    # BUY: paid 100, now worth 105 → paid 7500, now worth 7875 → -375 loss
    # M2M = (ltp - entry) × qty × -1 (BUY multiplier)
    # M2M = (105 - 100) × 75 × -1 = -375
    assert m2m == Decimal("-375.00")

def test_m2m_sell_position_profit():
    """SELL position with LTP < entry_price → Profit (positive M2M)"""
    instrument = {
        "direction": "SELL",
        "quantity": 50,
        "entry_price": Decimal("200.00")
    }
    ltp = Decimal("180.00")

    m2m = calculate_instrument_m2m(instrument, ltp)

    # SELL: received 200, buy back at 180 → profit 20 per share
    # M2M = (ltp - entry) × qty × +1 (SELL multiplier)
    # M2M = (180 - 200) × 50 × +1 = +1000
    assert m2m == Decimal("1000.00")

# ... 13 more tests (mixed positions, edge cases, decimal precision)
```

**Test Suite 2: OHLC Aggregation** (5 tests)
- Open = first M2M of minute
- High = max M2M of minute
- Low = min M2M of minute
- Close = last M2M of minute

**Test Suite 3: Data Persistence** (5 tests)
- Database insert successful
- Upsert on conflict (timestamp collision)
- Partition routing (monthly partitions)

**Effort**: 16 hours (includes test writing, validation)
**Priority**: **P0 - BLOCKING PRODUCTION**
**Impact**: **CRITICAL - Financial accuracy**

---

## Final Checklist

- [ ] All 10 assessment areas completed
- [ ] Report saved to correct path
- [ ] Test coverage calculated
- [ ] Test case matrix created (847 tests)
- [ ] Critical gaps identified (top 10)
- [ ] Production readiness verdict assigned
- [ ] Minimum test suite defined (120 tests)
- [ ] Effort estimates realistic

---

**Execution Command**:
```bash
cd /mnt/stocksblitz-data/Quantagro/tradingview-viz/backend
# Your QA validation begins here
```

**Expected Output**:
- **Report**: `/docs/assessment_1/phase4_qa_validation.md`
- **Size**: 60-100 KB
- **Duration**: 6-8 hours
- **Next Step**: Phase 5 (Production Release Decision)

---

**END OF PROMPT**
