# Python SDK - Multi-Account Support Implementation

**Date:** 2025-11-09
**Status:** ✅ COMPLETE
**Sprint:** 1.5 - SDK Enhancement

---

## 🎯 Overview

The Python SDK has been enhanced with multi-account support using a hybrid interface that maintains backward compatibility while enabling explicit multi-account access.

**Key Features:**
- ✅ **Simple single-account usage** (backward compatible): `client.Account().buy(...)`
- ✅ **Explicit multi-account access**: `client.Accounts["XJ4540"].buy(...)`
- ✅ **Account discovery**: `client.Accounts.list()`, iteration, membership testing
- ✅ **Primary account auto-selection**: Automatically identifies and uses primary account
- ✅ **Comprehensive unit tests**: 21 tests covering all functionality

---

## 📁 Files Created/Modified

### New Files:

**`stocksblitz/accounts_collection.py`**
- **Purpose**: Implement `AccountsCollection` and `AccountProxy` classes
- **Key Classes**:
  - `AccountsCollection`: Dict-like collection for managing multiple accounts
  - `AccountProxy`: Proxy that delegates to `Account` for specific account_id

**`tests/test_accounts_collection.py`**
- **Purpose**: Comprehensive unit tests for multi-account functionality
- **Coverage**: 21 tests, 100% passing
- **Test Areas**:
  - AccountProxy delegation
  - Lazy loading
  - Account fetching (JWT and API key modes)
  - Dict-like interface (`[]`, `in`, `len`, iteration)
  - Primary account selection
  - Caching behavior
  - Error handling

**`examples/multi_account_demo.py`**
- **Purpose**: Demo script showing all multi-account usage patterns
- **Examples**:
  - Simple usage (backward compatible)
  - Explicit multi-account access
  - Account discovery
  - Hybrid usage
  - Error handling

### Modified Files:

**`stocksblitz/client.py`**
- Added import for `AccountsCollection`
- Initialized `_accounts_collection` in `__init__()`
- Updated `Account()` method to use primary account by default
- Added `Accounts` property for multi-account access
- Updated docstring with multi-account examples

**`stocksblitz/__init__.py`**
- Added exports for `AccountsCollection` and `AccountProxy`
- Updated `__all__` list

---

## 🏗️ Architecture

### Class Hierarchy

```
TradingClient
  ├── _accounts_collection: AccountsCollection
  │     ├── _accounts: Dict[str, Dict]  (lazy loaded)
  │     ├── _proxies: Dict[str, AccountProxy]  (cached)
  │     └── _primary_account_id: Optional[str]
  │
  └── Account(account_id) -> Account
```

### AccountsCollection Design

**Lazy Loading:**
- Accounts are fetched from API only on first access
- Reduces unnecessary API calls during client initialization
- Cached until explicitly cleared

**Proxy Pattern:**
- `AccountProxy` wraps `Account` with a specific `account_id`
- Provides same interface as `Account` but bound to specific account
- AccountProxy instances are cached for reuse

**Dict-Like Interface:**
```python
# Access by key
account = client.Accounts["XJ4540"]

# Membership test
if "XJ4540" in client.Accounts:
    ...

# Iteration
for account_id in client.Accounts:
    print(account_id)

# Length
total = len(client.Accounts)
```

---

## 🔄 API Integration

### Account Fetching Strategy

**JWT Authentication (user_service):**
```python
# Fetch from user_service /v1/users/me/accounts
GET http://localhost:8011/v1/users/me/accounts
Authorization: Bearer <access_token>

Response:
{
  "accounts": [
    {
      "account_id": "XJ4540",
      "broker": "zerodha",
      "role": "owner",
      "is_primary": true
    },
    {
      "account_id": "AB1234",
      "broker": "zerodha",
      "role": "member",
      "is_primary": false
    }
  ]
}
```

**API Key Authentication (backend):**
```python
# Fetch from backend /v1/accounts
GET http://localhost:8010/v1/accounts
Authorization: Bearer <api_key>

Response: Same as above
```

### Primary Account Selection Logic

1. **First choice**: Account with `is_primary: true`
2. **Second choice**: Account with `role: "owner"`
3. **Fallback**: First account in list

---

## 💡 Usage Examples

### Example 1: Simple Usage (Backward Compatible)

```python
from stocksblitz import TradingClient

# API key authentication
client = TradingClient(
    api_url="http://localhost:8010",
    api_key="sb_xxx"
)

# Uses primary account automatically
account = client.Account()
positions = account.positions
account.buy("NIFTY50", quantity=50)
```

**Behavior:**
- `client.Account()` automatically uses primary account
- No breaking changes for existing code
- ✅ Fully backward compatible

### Example 2: Explicit Multi-Account Access

```python
from stocksblitz import TradingClient

# JWT authentication
client = TradingClient.from_credentials(
    api_url="http://localhost:8010",
    user_service_url="http://localhost:8011",
    username="trader@example.com",
    password="password123"
)

# List all accounts
for account in client.Accounts.list():
    print(f"{account['account_id']}: {account['broker']}")

# Access specific account
account_xj = client.Accounts["XJ4540"]
account_xj.buy("NIFTY50", quantity=50)

# Access another account
account_ab = client.Accounts["AB1234"]
account_ab.sell("BANKNIFTY", quantity=25)
```

### Example 3: Account Discovery

```python
# Check number of accounts
print(f"Total accounts: {len(client.Accounts)}")

# Iterate over account IDs
for account_id in client.Accounts:
    print(account_id)

# Get primary account
primary = client.Accounts.primary()
print(f"Primary: {primary.account_id}")

# Check account existence
if "XJ4540" in client.Accounts:
    account = client.Accounts["XJ4540"]
```

### Example 4: Hybrid Usage

```python
# Simple for primary
client.Account().buy("NIFTY50", 50)

# Explicit for others
client.Accounts["BACKUP"].sell("BANKNIFTY", 25)

# Conditional multi-account strategy
inst = client.Instrument("NIFTY50")
if inst['5m'].rsi[14] > 70:
    # Sell on primary
    client.Account().sell(inst, 50)

    # Also sell on backup if available
    if "BACKUP" in client.Accounts:
        client.Accounts["BACKUP"].sell(inst, 50)
```

---

## 🧪 Testing

### Unit Test Coverage

**Test File:** `tests/test_accounts_collection.py`

**TestAccountProxy (4 tests):**
- ✅ Creation
- ✅ Delegation to Account (positions, buy)
- ✅ String representation

**TestAccountsCollection (17 tests):**
- ✅ Lazy loading
- ✅ Account fetching (JWT and API key modes)
- ✅ Dict-like interface (`[]`, `in`, `len`, iteration)
- ✅ Account listing
- ✅ Primary account identification
- ✅ Primary account fallback logic
- ✅ Unauthenticated access error
- ✅ Cache management
- ✅ Proxy caching
- ✅ String representation

**Test Results:**
```bash
$ pytest tests/test_accounts_collection.py -v
===================== 21 passed in 0.17s =======================
```

### Running Tests

```bash
cd /mnt/stocksblitz-data/Quantagro/tradingview-viz/python-sdk

# Run multi-account tests
python3 -m pytest tests/test_accounts_collection.py -v

# Run all tests
python3 -m pytest tests/ -v
```

---

## 🔐 Security Considerations

**Authentication Required:**
- Cannot fetch accounts without authentication
- Raises `AuthenticationError` if not authenticated

**Account Access Control:**
- Only returns accounts user has access to
- Backend/user_service enforces access control
- SDK trusts backend's authorization

**Error Handling:**
```python
# Accessing non-existent account
try:
    account = client.Accounts["INVALID"]
except KeyError as e:
    print(f"Account not found: {e}")

# Safe access pattern
if "XJ4540" in client.Accounts:
    account = client.Accounts["XJ4540"]
```

---

## 🚀 Migration Guide

### For Existing Code (No Changes Needed)

Existing code continues to work without modification:

```python
# Before multi-account support
client = TradingClient(api_url=..., api_key=...)
account = client.Account()
account.buy("NIFTY50", 50)

# Still works! (uses primary account)
```

### For New Multi-Account Code

To leverage multi-account support:

```python
# New: Access specific accounts
client.Accounts["XJ4540"].buy("NIFTY50", 50)
client.Accounts["AB1234"].sell("BANKNIFTY", 25)

# New: Discover accounts
for account_id in client.Accounts:
    print(f"{account_id}: {client.Accounts[account_id].funds}")
```

---

## 📊 Performance Considerations

**Lazy Loading:**
- Accounts fetched only on first access
- Reduces client initialization time
- Cached after first fetch

**Proxy Caching:**
- `AccountProxy` instances cached
- Accessing same account twice returns same instance
- No redundant object creation

**API Call Optimization:**
- Single API call fetches all accounts
- Results cached with 60-second TTL
- Manual cache clear available: `client.Accounts.clear_cache()`

---

## 🔄 Integration with Backend/User Service

### Backend Requirements

**Endpoint:** `GET /v1/users/me/accounts`

**Authentication:** JWT Bearer token or API key

**Response Format:**
```json
{
  "accounts": [
    {
      "account_id": "XJ4540",
      "broker": "zerodha",
      "broker_client_id": "XJ4540",
      "role": "owner",
      "is_primary": true,
      "created_at": "2025-11-01T10:00:00Z"
    }
  ]
}
```

**Required Fields:**
- `account_id` (string): Unique account identifier
- `broker` (string): Broker name
- `role` (string): User's role (owner/member)
- `is_primary` (boolean): Primary account flag

### User Service Integration

The SDK works seamlessly with the user_service multi-account implementation:

1. **User logs in** → SDK obtains JWT
2. **SDK fetches accounts** → `GET /v1/users/me/accounts`
3. **User service returns** → All accessible accounts
4. **SDK caches** → Accounts stored in `AccountsCollection`
5. **User accesses account** → `client.Accounts["XJ4540"]` returns `AccountProxy`

---

## ✅ Verification Checklist

**Implementation:**
- [x] `AccountsCollection` class created
- [x] `AccountProxy` class created
- [x] TradingClient integration
- [x] Lazy loading implemented
- [x] Primary account auto-selection
- [x] Dict-like interface ([], in, len, iteration)
- [x] JWT authentication support
- [x] API key authentication support

**Testing:**
- [x] Unit tests written (21 tests)
- [x] All tests passing
- [x] Error handling tested
- [x] Caching behavior tested
- [x] Mock-based testing

**Documentation:**
- [x] Multi-account implementation doc
- [x] Usage examples
- [x] Demo script
- [x] Docstrings updated
- [x] Migration guide

**Backward Compatibility:**
- [x] Existing code works unchanged
- [x] `client.Account()` uses primary
- [x] No breaking changes

---

## 🎯 Next Steps

1. **Integration Testing**: Test with live backend and user_service
2. **End-to-End Testing**: Full workflow from login to multi-account trading
3. **Performance Testing**: Measure lazy loading and caching performance
4. **Documentation**: Update main README with multi-account examples
5. **Sprint 2**: Implement Organizations support

---

## 📞 Related Documentation

- **User Service Multi-Environment Alignment**: `user_service/docs/MULTI_ENVIRONMENT_ALIGNMENT.md`
- **Backend Multi-Account API**: `backend/docs/MULTI_ACCOUNT_API.md`
- **SDK Main README**: `python-sdk/README.md`

---

**END OF MULTI-ACCOUNT IMPLEMENTATION DOCUMENT**
