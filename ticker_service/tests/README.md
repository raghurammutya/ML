# Test Suite

Comprehensive test suite for the ticker_service.

## Setup

1. **Install test dependencies:**
   ```bash
   pip install pytest pytest-cov pytest-asyncio httpx
   ```

2. **Set up test environment:**
   ```bash
   cp .env.example .env.test
   # Edit .env.test with test-specific values
   ```

3. **Set up test database (optional for integration tests):**
   ```bash
   createdb stocksblitz_test
   psql stocksblitz_test < migrations/*.sql
   ```

## Running Tests

### Run all tests
```bash
pytest
```

### Run specific test categories
```bash
# Unit tests only (fast, no dependencies)
pytest -m unit

# Integration tests (require database/redis)
pytest -m integration

# End-to-end tests
pytest -m e2e

# Security tests
pytest -m security
```

### Run with coverage
```bash
pytest --cov=app --cov-report=html
# Open htmlcov/index.html in browser
```

### Run specific test file
```bash
pytest tests/unit/test_auth.py
pytest tests/integration/test_api_endpoints.py -v
```

### Run tests in parallel (faster)
```bash
pip install pytest-xdist
pytest -n auto
```

## Test Structure

```
tests/
├── conftest.py              # Shared fixtures and configuration
├── unit/                    # Unit tests (fast, isolated)
│   ├── test_auth.py        # Authentication logic
│   ├── test_config.py      # Configuration validation
│   ├── test_runtime_state.py
│   └── test_batch_orders.py
├── integration/             # Integration tests (external dependencies)
│   ├── test_api_endpoints.py
│   ├── test_database.py
│   └── test_redis.py
└── e2e/                     # End-to-end tests (full system)
    └── test_order_flow.py
```

## Writing Tests

### Unit Test Example

```python
import pytest

@pytest.mark.unit
async def test_my_function():
    \"\"\"Test description\"\"\"
    result = await my_function()
    assert result == expected_value
```

### Integration Test Example

```python
@pytest.mark.integration
def test_api_endpoint(client):
    \"\"\"Test with test client\"\"\"
    response = client.get("/endpoint")
    assert response.status_code == 200
```

### Using Fixtures

```python
@pytest.mark.unit
def test_with_mock(mock_kite_client):
    \"\"\"Use shared fixtures from conftest.py\"\"\"
    result = my_function(mock_kite_client)
    assert result is not None
```

## Coverage Goals

- **Minimum**: 70% overall coverage (enforced by pytest.ini)
- **Target**: 85% coverage
- **Critical paths**: 100% coverage (authentication, order execution, security)

## Continuous Integration

Tests are run automatically on:
- Every commit (pre-commit hook)
- Pull requests (CI pipeline)
- Before deployment

### Pre-commit Hook Setup

```bash
# .git/hooks/pre-commit
#!/bin/bash
pytest -m unit --cov=app --cov-fail-under=70
if [ $? -ne 0 ]; then
    echo "Tests failed. Commit aborted."
    exit 1
fi
```

## Test Data

### Mock Data
- Use fixtures in `conftest.py` for common test data
- Don't commit real credentials or production data
- Use `@pytest.fixture` for reusable test objects

### Test Database
- Use database 15 for Redis tests (see conftest.py)
- Use `stocksblitz_test` database for PostgreSQL
- Tests should clean up after themselves

## Troubleshooting

### Tests hang or timeout
- Check for infinite loops or missing `await`
- Use `pytest -s` to see print statements
- Use `pytest --log-cli-level=DEBUG` for detailed logs

### Import errors
- Ensure ticker_service is in PYTHONPATH
- Run from project root: `cd ticker_service && pytest`

### Fixture not found
- Check that fixture is defined in `conftest.py`
- Ensure you're importing from correct location

### Database connection errors
- Verify test database exists
- Check database credentials in .env.test
- Ensure PostgreSQL is running

## Best Practices

1. **Test one thing per test** - Keep tests focused
2. **Use descriptive names** - `test_api_returns_404_when_not_found`
3. **Arrange-Act-Assert** - Structure tests clearly
4. **Clean up** - Use fixtures with cleanup/teardown
5. **Mock external dependencies** - Don't call real APIs in tests
6. **Test edge cases** - Empty inputs, large inputs, invalid data
7. **Test error paths** - Not just happy paths

## TODO: Additional Tests Needed

High priority tests to add:

- [ ] `tests/unit/test_batch_orders.py` - Batch order rollback logic
- [ ] `tests/unit/test_task_persistence.py` - SQL injection prevention
- [ ] `tests/integration/test_webhooks.py` - SSRF protection
- [ ] `tests/integration/test_websocket.py` - WebSocket authentication
- [ ] `tests/security/test_sql_injection.py` - Security tests
- [ ] `tests/security/test_auth_bypass.py` - Auth vulnerabilities
- [ ] `tests/e2e/test_order_lifecycle.py` - Full order flow

See `TESTING_ROADMAP.md` for complete testing plan.
