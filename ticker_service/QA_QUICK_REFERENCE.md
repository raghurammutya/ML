# QA QUICK REFERENCE CARD
## Ticker Service Testing - Cheat Sheet

---

## CURRENT STATUS AT A GLANCE

**Overall Coverage**: 11% ❌ (Target: 85%)  
**Total Tests**: 152 tests in 20 files  
**Quality Score**: 42/100  

**Critical Gaps**:
- Order Execution: 0% coverage (242 lines untested)
- WebSocket: 0% coverage (173 lines untested)
- Greeks: 12% coverage (143 lines untested)
- Security: 0 tests

---

## DOCUMENTS DELIVERED

| Document | Pages | Purpose |
|----------|-------|---------|
| QA_EXECUTIVE_SUMMARY.md | 9 | Leadership overview, recommendations |
| QA_COMPREHENSIVE_ASSESSMENT.md | 45 | Detailed analysis, test strategy |
| QA_ACTION_PLAN.md | 32 | Week-by-week implementation guide |
| test_order_executor_TEMPLATE.py | 14 | Ready-to-use test template |

---

## QUICK START (First Day)

```bash
# 1. Setup environment
cd ticker_service
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Run existing tests
pytest

# 3. Check coverage
pytest --cov=app --cov-report=html
open htmlcov/index.html

# 4. Start Week 1 testing
cp tests/unit/test_order_executor_TEMPLATE.py tests/unit/test_order_executor.py
# Edit and implement tests

# 5. Run your new tests
pytest tests/unit/test_order_executor.py -v
```

---

## TEST EXECUTION COMMANDS

```bash
# Run all tests
pytest

# Run by category
pytest -m unit                    # Unit tests only (fast)
pytest -m integration             # Integration tests
pytest -m security                # Security tests
pytest -m load                    # Performance tests
pytest -m "not slow"              # Exclude slow tests

# Run specific file
pytest tests/unit/test_order_executor.py -v

# Run with coverage
pytest --cov=app --cov-report=html
pytest --cov=app/order_executor.py --cov-report=term-missing

# Run in parallel (faster)
pytest -n auto                    # Auto-detect CPU count
pytest -n 4                       # Use 4 workers

# Run with verbose output
pytest -v -s                      # -s shows print statements
pytest --tb=short                 # Short traceback
pytest --log-cli-level=DEBUG      # Show debug logs
```

---

## PRIORITY TESTING SCHEDULE

### Week 1: Order Execution (BLOCKER)
- **File**: `tests/unit/test_order_executor.py`
- **Tests**: 20 tests
- **Effort**: 16 hours
- **Target**: 90% coverage
- **Status**: Use TEMPLATE file to start

### Week 2: WebSocket & Greeks (BLOCKER)
- **Files**: 
  - `tests/integration/test_websocket_lifecycle.py`
  - `tests/unit/test_greeks_calculator_comprehensive.py`
- **Tests**: 40 tests
- **Effort**: 24 hours
- **Target**: 85% WebSocket, 95% Greeks

### Week 3-4: API & Security (HIGH)
- **Files**:
  - `tests/integration/test_api_endpoints_comprehensive.py`
  - `tests/security/test_authentication.py`
  - `tests/security/test_sql_injection.py`
- **Tests**: 50 tests
- **Effort**: 40 hours
- **Target**: 70% overall coverage

### Week 5-8: Completion (MEDIUM)
- Database, Redis, Chaos, Regression
- **Target**: 85% overall coverage

---

## COVERAGE TARGETS BY MODULE

**CRITICAL (95%+ required)**:
- [ ] app/order_executor.py (currently 0%)
- [ ] app/greeks_calculator.py (currently 12%)
- [ ] app/jwt_auth.py (currently 0%)

**HIGH (85%+ required)**:
- [ ] app/generator.py (currently 0%)
- [ ] app/accounts.py (currently 0%)
- [ ] app/routes_orders.py (currently 0%)
- [ ] app/routes_websocket.py (currently 0%)

**GOOD (80%+ required)**:
- [x] app/schema.py (86%) ✓
- [x] app/services/tick_validator.py (92%) ✓
- [x] app/config.py (80%) ✓

---

## TEST WRITING PATTERN

```python
import pytest
from unittest.mock import MagicMock, AsyncMock

@pytest.mark.unit  # or integration, security, load
@pytest.mark.asyncio  # for async tests
async def test_feature_scenario_expected():
    """Test that feature does X when Y happens"""
    # Arrange - Setup test data and mocks
    mock_client = MagicMock()
    mock_client.method = AsyncMock(return_value={"result": "success"})
    
    # Act - Execute the code under test
    result = await execute_function(mock_client)
    
    # Assert - Verify expectations
    assert result.status == "success"
    mock_client.method.assert_called_once()
```

---

## COMMON PYTEST FIXTURES

```python
# Available in tests/conftest.py

@pytest.fixture
def async_client():
    """AsyncClient for API testing"""
    
@pytest.fixture
def client():
    """Synchronous TestClient"""
    
@pytest.fixture
def mock_kite_client():
    """Mocked KiteConnect client"""
    
@pytest.fixture
def mock_redis():
    """Mocked Redis client"""
    
@pytest.fixture
def sample_order_task():
    """Sample OrderTask for testing"""
```

---

## QUALITY GATES (CI/CD)

**Before Merge**:
- [x] All tests passing
- [x] Coverage >= 85% (will be enforced)
- [x] No security findings
- [x] Code review approved

**Test Execution Time**:
- Unit tests: < 5 minutes
- Full suite: < 15 minutes

---

## CRITICAL TEST SCENARIOS

### Order Execution Must Test:
1. Successful order placement
2. Network error retry (exponential backoff)
3. Max retries exceeded → Dead letter queue
4. Idempotency (same request twice)
5. Circuit breaker opens after failures
6. Circuit breaker rejects when open
7. Circuit breaker recovery (HALF_OPEN → CLOSED)
8. Concurrent order execution
9. Invalid params handling
10. Task timeout

### WebSocket Must Test:
1. Connect with valid auth token
2. Connect without auth (rejected)
3. Receive tick data after subscribe
4. Subscribe to multiple instruments
5. Unsubscribe handling
6. Disconnect cleanup
7. Reconnect with state resume
8. Max connections limit
9. Message rate limiting
10. Concurrent clients

### Greeks Must Test:
1. Black-Scholes call option (ATM, ITM, OTM)
2. Black-Scholes put option (ATM, ITM, OTM)
3. Delta calculation accuracy
4. Gamma calculation (highest at ATM)
5. Theta time decay
6. Vega volatility sensitivity
7. Put-call parity validation
8. Edge cases (zero volatility, negative time)
9. Deep ITM/OTM behavior
10. Performance (<1ms per calculation)

---

## TROUBLESHOOTING

**Tests hanging?**
```bash
pytest --timeout=30  # Kill tests after 30s
```

**Import errors?**
```bash
export PYTHONPATH="${PYTHONPATH}:/path/to/ticker_service"
```

**Database connection errors?**
```bash
# Check test database exists
psql -l | grep stocksblitz_test

# Create if missing
createdb stocksblitz_test
```

**Redis connection errors?**
```bash
# Use test database (15)
export REDIS_URL="redis://localhost:6379/15"
```

**Coverage report not updating?**
```bash
# Clear cache
rm -rf .pytest_cache htmlcov .coverage
pytest --cov=app --cov-report=html
```

---

## SECURITY TEST EXAMPLES

```python
@pytest.mark.security
async def test_sql_injection_prevention(async_client):
    """Test SQL injection is prevented"""
    malicious = "'; DROP TABLE subscriptions; --"
    response = await async_client.get(f"/subscriptions?symbol={malicious}")
    assert response.status_code in [200, 400]
    # Verify table still exists
    assert table_exists("subscriptions")

@pytest.mark.security
async def test_auth_required(async_client):
    """Test authentication is required"""
    response = await async_client.post("/orders/regular", json={})
    assert response.status_code == 401
```

---

## PERFORMANCE TEST EXAMPLES

```python
@pytest.mark.load
async def test_throughput_1000_instruments():
    """Test tick processing throughput"""
    start = time.perf_counter()
    
    for i in range(1000):
        await process_tick(create_test_tick(i))
    
    elapsed = time.perf_counter() - start
    throughput = 1000 / elapsed
    
    assert throughput > 1000  # >1000 ticks/sec
    print(f"Throughput: {throughput:.2f} ticks/sec")
```

---

## HELPFUL RESOURCES

**Documentation**:
- Pytest docs: https://docs.pytest.org/
- Coverage.py: https://coverage.readthedocs.io/
- FastAPI testing: https://fastapi.tiangolo.com/tutorial/testing/

**Tools**:
- Bandit (security): https://bandit.readthedocs.io/
- pytest-asyncio: https://pytest-asyncio.readthedocs.io/
- pytest-cov: https://pytest-cov.readthedocs.io/

**Internal Docs**:
- tests/README.md - Test suite documentation
- QA_COMPREHENSIVE_ASSESSMENT.md - Full QA report
- QA_ACTION_PLAN.md - Implementation guide

---

## CONTACT & ESCALATION

**Questions?**
- Review QA_COMPREHENSIVE_ASSESSMENT.md
- Check tests/README.md
- Ask in #qa-testing Slack channel

**Blockers?**
- Escalate to QA Lead
- Tag in sprint standup
- Create ticket in Jira

---

**Last Updated**: November 8, 2025  
**Version**: 1.0  
**Status**: Active  

---
