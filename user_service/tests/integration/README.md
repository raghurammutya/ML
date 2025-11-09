# Integration Tests for User Service

This directory contains integration tests that verify end-to-end functionality of the user_service API.

## Prerequisites

1. **User Service Running**:
   ```bash
   cd /home/stocksadmin/Quantagro/tradingview-viz/user_service

   # Development environment
   cp .env.dev .env
   uvicorn app.main:app --host 0.0.0.0 --port 8011 --reload
   ```

2. **Database Available**:
   - PostgreSQL running on port 8003 (dev), 8103 (staging), or 8203 (production)
   - Database created: `stocksblitz_unified_dev`
   - Migrations applied: `alembic upgrade head`

3. **Redis Available**:
   - Redis running on port 8002 (dev), 8102 (staging), or 8202 (production)

4. **Dependencies Installed**:
   ```bash
   pip install pytest httpx
   ```

## Running Integration Tests

### Run All Integration Tests

```bash
cd /home/stocksadmin/Quantagro/tradingview-viz/user_service

# Run all integration tests
pytest tests/integration/ -v

# Run with detailed output
pytest tests/integration/ -vv -s
```

### Run Specific Test Classes

```bash
# Test API key lifecycle
pytest tests/integration/test_api_key_endpoints.py::TestAPIKeyLifecycle -v

# Test scope enforcement
pytest tests/integration/test_api_key_endpoints.py::TestAPIKeyScopeEnforcement -v

# Test rate limiting
pytest tests/integration/test_api_key_endpoints.py::TestAPIKeyRateLimiting -v

# Test error handling
pytest tests/integration/test_api_key_endpoints.py::TestAPIKeyErrorHandling -v
```

### Run Specific Tests

```bash
# Test API key creation
pytest tests/integration/test_api_key_endpoints.py::TestAPIKeyLifecycle::test_02_create_api_key -v

# Test API key authentication
pytest tests/integration/test_api_key_endpoints.py::TestAPIKeyLifecycle::test_04_authenticate_with_api_key -v

# Test API key rotation
pytest tests/integration/test_api_key_endpoints.py::TestAPIKeyLifecycle::test_08_rotate_api_key -v
```

## Test Coverage

### TestAPIKeyLifecycle (10 tests)
Tests the complete API key lifecycle:

1. ✅ `test_01_register_and_login` - User registration for API key tests
2. ✅ `test_02_create_api_key` - API key generation
3. ✅ `test_03_list_api_keys` - List user's API keys
4. ✅ `test_04_authenticate_with_api_key` - Authenticate with Bearer token
5. ✅ `test_05_api_key_with_x_api_key_header` - Authenticate with X-API-Key header
6. ✅ `test_06_get_api_key_details` - Get specific API key metadata
7. ✅ `test_07_update_api_key` - Update API key name and scopes
8. ✅ `test_08_rotate_api_key` - Rotate API key secret
9. ✅ `test_09_revoke_api_key` - Revoke/delete API key
10. ✅ `test_10_create_multiple_api_keys` - Create multiple keys per user

### TestAPIKeyScopeEnforcement (2 tests)
Tests API key scope enforcement:

1. ✅ `test_read_scope_enforcement` - Read-only key permissions
2. ✅ `test_scope_validation` - Scope validation for different keys

### TestAPIKeyRateLimiting (1 test)
Tests rate limiting:

1. ⏭️ `test_api_key_rate_limit` - Rate limit enforcement (skipped, requires config)

### TestAPIKeyErrorHandling (5 tests)
Tests error scenarios:

1. ✅ `test_invalid_api_key_format` - Invalid key format rejection
2. ✅ `test_nonexistent_api_key` - Non-existent key rejection
3. ⏭️ `test_expired_api_key` - Expired key rejection (skipped, requires DB manipulation)
4. ✅ `test_create_api_key_without_auth` - Unauthorized creation attempt
5. ✅ `test_access_other_user_api_key` - Cross-user access prevention

## Configuration

Tests use these default settings:

```python
BASE_URL = "http://localhost:8011"  # Development environment
API_V1 = f"{BASE_URL}/v1"
```

To test against different environments:

**Staging:**
```bash
# Modify BASE_URL in test file or use environment variable
export USER_SERVICE_URL="http://localhost:8111"
pytest tests/integration/test_api_key_endpoints.py -v
```

**Production:**
```bash
export USER_SERVICE_URL="http://localhost:8211"
pytest tests/integration/test_api_key_endpoints.py -v
```

## Expected Output

```bash
$ pytest tests/integration/test_api_key_endpoints.py -v

=================== test session starts ====================
tests/integration/test_api_key_endpoints.py::TestAPIKeyLifecycle::test_01_register_and_login PASSED [ 5%]
tests/integration/test_api_key_endpoints.py::TestAPIKeyLifecycle::test_02_create_api_key PASSED [10%]
tests/integration/test_api_key_endpoints.py::TestAPIKeyLifecycle::test_03_list_api_keys PASSED [15%]
tests/integration/test_api_key_endpoints.py::TestAPIKeyLifecycle::test_04_authenticate_with_api_key PASSED [20%]
tests/integration/test_api_key_endpoints.py::TestAPIKeyLifecycle::test_05_api_key_with_x_api_key_header PASSED [25%]
tests/integration/test_api_key_endpoints.py::TestAPIKeyLifecycle::test_06_get_api_key_details PASSED [30%]
tests/integration/test_api_key_endpoints.py::TestAPIKeyLifecycle::test_07_update_api_key PASSED [35%]
tests/integration/test_api_key_endpoints.py::TestAPIKeyLifecycle::test_08_rotate_api_key PASSED [40%]
tests/integration/test_api_key_endpoints.py::TestAPIKeyLifecycle::test_09_revoke_api_key PASSED [45%]
tests/integration/test_api_key_endpoints.py::TestAPIKeyLifecycle::test_10_create_multiple_api_keys PASSED [50%]
...
=================== 18 passed, 2 skipped in 5.23s ====================
```

## Troubleshooting

### Service Not Responding

```bash
# Check if service is running
curl http://localhost:8011/health

# Check service logs
tail -f /path/to/user_service.log

# Restart service
uvicorn app.main:app --host 0.0.0.0 --port 8011 --reload
```

### Database Connection Errors

```bash
# Check PostgreSQL is running
PGPASSWORD=stocksblitz123 psql -h localhost -p 8003 -U stocksblitz -d stocksblitz_unified_dev -c "SELECT 1;"

# Check database exists
PGPASSWORD=stocksblitz123 psql -h localhost -p 8003 -U stocksblitz -d postgres -c "\l"

# Run migrations
alembic upgrade head
```

### Redis Connection Errors

```bash
# Check Redis is running
redis-cli -p 8002 ping

# Start Redis if needed
redis-server --port 8002 --daemonize yes
```

### Authentication Failures

- Verify JWT signing keys are configured correctly
- Check that `.env` file has correct settings
- Verify `LOCAL_KMS_KEY_PATH` points to valid key file

## Notes

- Tests create temporary users with timestamped emails
- Each test class uses class-scoped fixtures to minimize setup overhead
- Tests are numbered to ensure execution order within lifecycle tests
- Some tests are skipped if they require specific configuration (rate limiting, expiry testing)
- Tests clean up after themselves but may leave test users in the database

## Next Steps

After running integration tests:

1. **SDK Integration Testing**: Test Python SDK with live user_service
2. **Performance Testing**: Measure API key authentication performance
3. **Security Audit**: Verify scope enforcement and access control
4. **Production Readiness**: Test against staging environment before production deployment
