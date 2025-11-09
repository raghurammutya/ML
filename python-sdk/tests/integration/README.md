# Python SDK Integration Tests

Integration tests for the StocksBlitz Python SDK with live services.

## Prerequisites

1. **User Service Running**:
   ```bash
   cd /home/stocksadmin/Quantagro/tradingview-viz/user_service
   cp .env.dev .env
   uvicorn app.main:app --host 0.0.0.0 --port 8011 --reload
   ```

2. **Backend Service Running** (optional):
   ```bash
   cd /home/stocksadmin/Quantagro/tradingview-viz/backend
   cp .env.dev .env
   uvicorn app.main:app --host 0.0.0.0 --port 8010 --reload
   ```

3. **SDK Installed**:
   ```bash
   cd /mnt/stocksblitz-data/Quantagro/tradingview-viz/python-sdk
   pip install -e .
   ```

## Running Tests

### Run All SDK Integration Tests

```bash
cd /mnt/stocksblitz-data/Quantagro/tradingview-viz/python-sdk

# Run all integration tests
pytest tests/integration/ -v

# Run with detailed output
pytest tests/integration/ -vv -s
```

### Run Specific Test Classes

```bash
# Test SDK authentication
pytest tests/integration/test_sdk_with_user_service.py::TestSDKAuthentication -v

# Test SDK API key auth
pytest tests/integration/test_sdk_with_user_service.py::TestSDKAPIKeyAuth -v

# Test SDK multi-account support
pytest tests/integration/test_sdk_with_user_service.py::TestSDKMultiAccount -v

# Test end-to-end workflows
pytest tests/integration/test_sdk_with_user_service.py::TestSDKEndToEnd -v
```

## Test Coverage

### TestSDKAuthentication (4 tests)
Tests SDK authentication with user_service:

1. ✅ `test_01_sdk_jwt_authentication` - JWT authentication with username/password
2. ✅ `test_02_sdk_jwt_authentication_invalid_credentials` - Invalid credentials rejection
3. ✅ `test_03_sdk_login_method` - Manual login() method
4. ✅ `test_04_sdk_logout` - Logout and token cleanup

### TestSDKAPIKeyAuth (2 tests)
Tests SDK API key authentication:

1. ✅ `test_01_sdk_api_key_authentication` - API key setup
2. ✅ `test_02_sdk_api_key_invalid` - Invalid API key handling

### TestSDKMultiAccount (4 tests)
Tests SDK multi-account support:

1. ✅ `test_01_accounts_collection_lazy_loading` - Lazy loading behavior
2. ✅ `test_02_accounts_collection_fetch` - Fetching accounts via SDK
3. ✅ `test_03_primary_account_access` - Primary account auto-selection
4. ✅ `test_04_explicit_account_access` - Explicit account access by ID

### TestSDKEndToEnd (2 tests)
End-to-end workflow tests:

1. ✅ `test_01_full_workflow_with_jwt` - Complete JWT workflow
2. ✅ `test_02_full_workflow_with_api_key` - Complete API key workflow

### TestSDKTokenRefresh (1 test)
Token refresh functionality:

1. ✅ `test_token_refresh` - Automatic token refresh

## Configuration

Tests use these default service URLs:

```python
USER_SERVICE_URL = "http://localhost:8011"  # Development
BACKEND_URL = "http://localhost:8010"       # Development
```

To test against different environments, modify these constants in the test file.

## Expected Output

```bash
$ pytest tests/integration/test_sdk_with_user_service.py -v

=================== test session starts ====================
tests/integration/test_sdk_with_user_service.py::TestSDKAuthentication::test_01_sdk_jwt_authentication PASSED [ 7%]
tests/integration/test_sdk_with_user_service.py::TestSDKAuthentication::test_02_sdk_jwt_authentication_invalid_credentials PASSED [14%]
tests/integration/test_sdk_with_user_service.py::TestSDKAuthentication::test_03_sdk_login_method PASSED [21%]
tests/integration/test_sdk_with_user_service.py::TestSDKAuthentication::test_04_sdk_logout PASSED [28%]
tests/integration/test_sdk_with_user_service.py::TestSDKAPIKeyAuth::test_01_sdk_api_key_authentication PASSED [35%]
tests/integration/test_sdk_with_user_service.py::TestSDKAPIKeyAuth::test_02_sdk_api_key_invalid PASSED [42%]
tests/integration/test_sdk_with_user_service.py::TestSDKMultiAccount::test_01_accounts_collection_lazy_loading PASSED [50%]
tests/integration/test_sdk_with_user_service.py::TestSDKMultiAccount::test_02_accounts_collection_fetch PASSED [57%]
tests/integration/test_sdk_with_user_service.py::TestSDKMultiAccount::test_03_primary_account_access PASSED [64%]
tests/integration/test_sdk_with_user_service.py::TestSDKMultiAccount::test_04_explicit_account_access PASSED [71%]
tests/integration/test_sdk_with_user_service.py::TestSDKEndToEnd::test_01_full_workflow_with_jwt PASSED [78%]
tests/integration/test_sdk_with_user_service.py::TestSDKEndToEnd::test_02_full_workflow_with_api_key PASSED [85%]
tests/integration/test_sdk_with_user_service.py::TestSDKTokenRefresh::test_token_refresh PASSED [92%]
=================== 13 passed in 8.45s ====================
```

## Example Usage Demonstrated

These integration tests demonstrate real-world SDK usage:

### JWT Authentication

```python
from stocksblitz import TradingClient

# Simple authentication
client = TradingClient.from_credentials(
    api_url="http://localhost:8010",
    user_service_url="http://localhost:8011",
    username="trader@example.com",
    password="password123"
)

# Client is now authenticated and ready to use
```

### API Key Authentication

```python
from stocksblitz import TradingClient

# API key authentication
client = TradingClient(
    api_url="http://localhost:8010",
    api_key="sb_12345678_abc..."
)

# Use client for automated trading, bots, etc.
```

### Multi-Account Access

```python
# List accessible accounts
accounts = client.Accounts.list()
for account in accounts:
    print(f"{account['account_id']}: {account['broker']}")

# Access specific account
client.Accounts["XJ4540"].buy("NIFTY50", quantity=50)

# Or use primary account
client.Account().buy("NIFTY50", quantity=50)
```

## Troubleshooting

### SDK Import Errors

```bash
# Make sure SDK is installed in development mode
cd /mnt/stocksblitz-data/Quantagro/tradingview-viz/python-sdk
pip install -e .

# Verify installation
python -c "import stocksblitz; print(stocksblitz.__version__)"
```

### Service Connection Errors

```bash
# Check user_service
curl http://localhost:8011/health

# Check backend
curl http://localhost:8010/health

# Restart services if needed
```

### Authentication Failures

- Verify user_service .env has correct JWT settings
- Check that KMS keys are properly configured
- Ensure database migrations are up to date

### Multi-Account Tests Skipped

Some tests may be skipped if the backend doesn't implement multi-account endpoints yet:

```
SKIPPED [1] tests/integration/test_sdk_with_user_service.py:123: Multi-account endpoint not implemented yet
```

This is expected during development. Tests will pass once backend endpoints are implemented.

## Notes

- Tests create temporary users with timestamped emails
- Each test class uses class-scoped fixtures for efficiency
- Tests are numbered to ensure execution order
- Some tests gracefully handle missing backend functionality
- Tests verify SDK behavior, not backend business logic

## Next Steps

1. ✅ SDK unit tests (already done)
2. ✅ SDK integration tests (these tests)
3. ⏭️ Backend integration (when backend multi-account endpoints are ready)
4. ⏭️ Performance testing
5. ⏭️ Production deployment
