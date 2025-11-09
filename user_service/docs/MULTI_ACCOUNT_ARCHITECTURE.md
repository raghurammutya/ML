# Multi-Account Architecture

**Date:** 2025-11-09
**Status:** ✅ Phase 1 Complete - Backend Endpoint Ready
**Sprint:** 1.5 - Multi-Account Support

---

## Overview

The StocksBlitz platform now supports multi-account scenarios where a single user can access multiple trading accounts with varying permission levels. This architecture supports:

1. **Personal Accounts** - User owns their own trading account
2. **Family Accounts** - Shared access to family member accounts
3. **Organization Accounts** - Firm accounts with role-based permissions (Sprint 2)

---

## Problem Statement

### The Challenge
A user authenticating with an API key needs to specify **which trading account** they want to operate on, because they may have access to multiple accounts:

```python
# BEFORE: Ambiguous - which account?
client = TradingClient(api_key="sb_xxx")
client.Orders.get_all()  # Which account's orders?

# AFTER: Explicit account selection
client = TradingClient(api_key="sb_xxx", account_id="XJ4540")
client.Orders.get_all()  # XJ4540's orders

# OR: Multi-account access
client.Accounts["ABC123"].Orders.get_all()  # ABC123's orders
```

---

## Architecture Design

### Backend Components

#### 1. New Endpoint: List Accessible Accounts

**Endpoint:** `GET /v1/users/me/accounts`

**Purpose:** Returns all trading accounts accessible to the authenticated user

**Response Schema:**
```json
{
  "user_id": 123,
  "accounts": [
    {
      "account_id": "XJ4540",
      "trading_account_id": 1,
      "broker": "kite",
      "nickname": "My Personal Account",
      "is_primary": true,
      "is_owner": true,
      "permissions": ["view", "trade", "manage"],
      "membership_type": "owner",
      "status": "active",
      "subscription_tier": "connect",
      "market_data_available": true
    },
    {
      "account_id": "ABC123",
      "trading_account_id": 2,
      "broker": "kite",
      "nickname": "Family Account",
      "is_primary": false,
      "is_owner": false,
      "permissions": ["view"],
      "membership_type": "member",
      "status": "active",
      "subscription_tier": "personal",
      "market_data_available": false
    }
  ],
  "primary_account_id": "XJ4540",
  "total_count": 2
}
```

**Implementation:** `app/api/v1/endpoints/users.py:669-785`

#### 2. Account Selection Logic

**Owned Accounts:**
- Full permissions: `["view", "trade", "manage"]`
- `membership_type`: `"owner"`
- Can be set as primary account
- Retrieved via: `TradingAccount.owner_id == user_id`

**Shared Accounts (via Memberships):**
- Variable permissions based on membership
- `membership_type`: `"member"`
- Cannot be primary account
- Retrieved via: `TradingAccountMembership.user_id == user_id`

**Primary Account Selection:**
1. If user has explicitly set a primary account → use it
2. Otherwise, default to first owned account
3. If no owned accounts → first shared account
4. If no accounts → SDK should show error

#### 3. Database Schema (Already Exists)

**trading_accounts table:**
```sql
- trading_account_id (PK)
- owner_id (FK → users.user_id)
- broker_user_id (Kite client ID, e.g., "XJ4540")
- broker (kite, upstox, etc.)
- account_name / nickname
- status (active, suspended, expired, error)
- subscription_tier (unknown, personal, connect, startup)
- market_data_available (boolean)
```

**trading_account_memberships table:**
```sql
- membership_id (PK)
- trading_account_id (FK)
- user_id (FK) -- User granted access
- permissions (JSONB) -- ["view"], ["view", "trade"], etc.
- granted_by (FK → users.user_id)
- status (active, suspended, revoked)
```

---

## SDK Design: Hybrid Approach

### Option Chosen: ✅ Hybrid (Best of Both Worlds)

**Benefits:**
- Simple for single-account users (majority)
- Flexible for multi-account scenarios
- Explicit account selection prevents mistakes
- Natural Python syntax

### SDK Implementation Plan

```python
from stocksblitz import TradingClient

# ========================================
# OPTION 1: Single Account (Simple)
# ========================================
client = TradingClient(
    api_url="http://localhost:8081",
    api_key="sb_xxx_yyy",
    account_id="XJ4540"  # Optional - auto-selects primary if omitted
)

# All operations use XJ4540
client.Orders.get_all()
client.Instrument("NIFTY50")['5m'].close


# ========================================
# OPTION 2: Multi-Account Access
# ========================================
client = TradingClient(
    api_url="http://localhost:8081",
    api_key="sb_xxx_yyy"
    # No account_id - enables multi-account mode
)

# Explicit account selection
client.Accounts["XJ4540"].Orders.place_order(symbol="RELIANCE", qty=10)
client.Accounts["ABC123"].Instrument("NIFTY50")['1d'].close

# List all accessible accounts
for account in client.Accounts.list():
    print(f"{account['account_id']}: {account['nickname']}")

# Switch default account
client.set_default_account("ABC123")
client.Orders.get_all()  # Now uses ABC123


# ========================================
# OPTION 3: Hybrid (Default + Explicit)
# ========================================
client = TradingClient(
    api_url="http://localhost:8081",
    api_key="sb_xxx_yyy",
    account_id="XJ4540"  # Default account
)

# Use default account (XJ4540)
client.Orders.get_all()

# Override for specific account
client.Accounts["ABC123"].Orders.get_all()

# Iterate all accounts
for account in client.Accounts:
    balance = account.get_balance()
    print(f"{account.id}: {balance}")
```

### SDK Classes to Implement

```python
# python-sdk/stocksblitz/client.py

class AccountProxy:
    """Proxy for accessing a specific trading account"""
    def __init__(self, client, account_id):
        self._client = client
        self._account_id = account_id

    @property
    def Orders(self):
        return OrdersAPI(self._client, self._account_id)

    def Instrument(self, symbol):
        return Instrument(self._client, self._account_id, symbol)

    def get_balance(self):
        return self._client._request("GET", f"/v1/accounts/{self._account_id}/balance")


class AccountsCollection:
    """Collection of accessible trading accounts"""
    def __init__(self, client):
        self._client = client
        self._accounts_cache = None

    def __getitem__(self, account_id: str):
        """Get account proxy: client.Accounts["XJ4540"]"""
        return AccountProxy(self._client, account_id)

    def list(self):
        """List all accessible accounts"""
        if self._accounts_cache is None:
            response = self._client._request("GET", "/v1/users/me/accounts")
            self._accounts_cache = response["accounts"]
        return self._accounts_cache

    def __iter__(self):
        """Iterate: for account in client.Accounts:"""
        return iter([AccountProxy(self._client, acc["account_id"]) for acc in self.list()])


class TradingClient:
    def __init__(self, api_url, api_key, account_id=None):
        self.api_url = api_url
        self.api_key = api_key
        self._default_account_id = account_id
        self.Accounts = AccountsCollection(self)

        # Auto-select primary if no account specified
        if account_id is None:
            accounts = self.Accounts.list()
            if accounts:
                primary = next((a for a in accounts if a.get("is_primary")), None)
                self._default_account_id = primary["account_id"] if primary else accounts[0]["account_id"]

    @property
    def Orders(self):
        """Orders API for default account"""
        if not self._default_account_id:
            raise ValueError("No account selected. Use client.Accounts[account_id].Orders")
        return OrdersAPI(self, self._default_account_id)

    def Instrument(self, symbol):
        """Instrument for default account"""
        if not self._default_account_id:
            raise ValueError("No account selected. Use client.Accounts[account_id].Instrument()")
        return Instrument(self, self._default_account_id, symbol)

    def set_default_account(self, account_id):
        """Switch default account"""
        self._default_account_id = account_id
```

---

## Backend API Changes Needed (Future)

### Phase 2: Add account_id Parameter to Endpoints

**Current (BEFORE):**
```
GET /v1/instruments/NIFTY50
GET /v1/orders
POST /v1/orders
```

**Future (AFTER):**
```
GET /v1/accounts/{account_id}/instruments/NIFTY50
GET /v1/accounts/{account_id}/orders
POST /v1/accounts/{account_id}/orders

# Or query parameter:
GET /v1/instruments/NIFTY50?account_id=XJ4540
GET /v1/orders?account_id=XJ4540
```

### Permission Checking Middleware

```python
# app/api/dependencies.py

async def get_current_account(
    account_id: str,
    current_user: User = Depends(get_current_user_flexible),
    db: Session = Depends(get_db)
):
    """
    Verify user has access to specified trading account
    Raises 403 if unauthorized
    """
    # Check ownership
    account = db.query(TradingAccount).filter(
        TradingAccount.trading_account_id == account_id,
        TradingAccount.owner_id == current_user.user_id
    ).first()

    if account:
        return account, ["view", "trade", "manage"]  # Owner has all permissions

    # Check membership
    membership = db.query(TradingAccountMembership).filter(
        TradingAccountMembership.account_id == account_id,
        TradingAccountMembership.user_id == current_user.user_id,
        TradingAccountMembership.status == "active"
    ).first()

    if membership:
        return membership.trading_account, membership.permissions

    raise HTTPException(
        status_code=403,
        detail=f"Access denied to trading account {account_id}"
    )


async def require_account_permission(
    required_permission: str,  # "view", "trade", "manage"
    account: Tuple[TradingAccount, List[str]] = Depends(get_current_account)
):
    """Check if user has specific permission on account"""
    trading_account, permissions = account

    if required_permission not in permissions:
        raise HTTPException(
            status_code=403,
            detail=f"Permission '{required_permission}' required for this operation"
        )

    return trading_account
```

---

## Migration Strategy

### Phase 1: ✅ COMPLETE (Current Sprint 1.5)
- [x] Add `GET /v1/users/me/accounts` endpoint
- [x] Return both owned and shared accounts
- [x] Include permissions, primary flag, subscription tier
- [x] SDK-friendly response format

### Phase 2: Backward-Compatible Account Parameters (Week 2)
- [ ] Add optional `account_id` parameter to existing endpoints
- [ ] Default to primary account if not provided
- [ ] Update middleware to fetch account context
- [ ] Add permission checking

### Phase 3: SDK Implementation (Week 2-3)
- [ ] Implement `AccountsCollection` class
- [ ] Implement `AccountProxy` class
- [ ] Update `TradingClient` constructor
- [ ] Add auto-selection of primary account
- [ ] Write SDK tests for multi-account scenarios

### Phase 4: Deprecation (Week 4+)
- [ ] Warn users to specify `account_id`
- [ ] Eventually make `account_id` required
- [ ] Remove default account fallback

---

## Testing Plan

### Unit Tests
```python
def test_list_accessible_accounts_owner():
    """User with owned accounts sees them with full permissions"""
    pass

def test_list_accessible_accounts_member():
    """User with membership sees limited permissions"""
    pass

def test_list_accessible_accounts_mixed():
    """User with both owned and shared accounts sees all"""
    pass

def test_primary_account_selection():
    """Primary account is correctly identified"""
    pass
```

### Integration Tests
```python
def test_sdk_single_account_mode():
    """SDK works with single account_id specified"""
    client = TradingClient(api_key="...", account_id="XJ4540")
    orders = client.Orders.get_all()
    assert all(order.account_id == "XJ4540" for order in orders)

def test_sdk_multi_account_mode():
    """SDK can access multiple accounts"""
    client = TradingClient(api_key="...")
    account1_orders = client.Accounts["XJ4540"].Orders.get_all()
    account2_orders = client.Accounts["ABC123"].Orders.get_all()
    assert account1_orders != account2_orders
```

---

## Security Considerations

### Permission Enforcement
1. **Always verify account access** before returning data
2. **Check specific permissions** (view, trade, manage) for each operation
3. **Audit log all account switches** for compliance
4. **Rate limit per account** (not just per user)

### Edge Cases
1. **Account revocation:** What happens if membership revoked mid-session?
   - Solution: Check permissions on every request, not just at login
2. **Account deletion:** Owner deletes account while member is using it
   - Solution: Return 404 with clear message, SDK should handle gracefully
3. **Permission changes:** Owner downgrades member from "trade" to "view"
   - Solution: Validate permissions on every request

---

## Files Modified

### Created
- `docs/MULTI_ACCOUNT_ARCHITECTURE.md` (this file)

### Modified
- `app/schemas/trading_account.py` - Added `AccessibleAccountInfo` and `ListAccessibleAccountsResponse`
- `app/api/v1/endpoints/users.py` - Added `GET /me/accounts` endpoint

---

## Next Steps

1. ✅ **Backend endpoint created** - `/v1/users/me/accounts`
2. ⏳ **Update Python SDK** - Implement hybrid approach
3. ⏳ **Add account_id to backend APIs** - Instrument, Orders, etc.
4. ⏳ **Write integration tests** - Test multi-account scenarios
5. ⏳ **Update documentation** - API docs, SDK usage examples

---

## Example Usage Scenarios

### Scenario 1: Individual Trader
```python
client = TradingClient(api_key="sb_xxx", account_id="XJ4540")
# Simple - just like before
client.Orders.place_order(symbol="RELIANCE", qty=10)
```

### Scenario 2: Family Account Manager
```python
client = TradingClient(api_key="sb_xxx")

# Trade on my account
client.Accounts["XJ4540"].Orders.place_order(symbol="RELIANCE", qty=10)

# Check father's account (read-only)
balance = client.Accounts["FATHER_ACC"].get_balance()

# Monitor son's account
positions = client.Accounts["SON_ACC"].Positions.get_all()
```

### Scenario 3: Investment Firm
```python
client = TradingClient(api_key="sb_xxx")

# Iterate all managed accounts
for account in client.Accounts:
    pnl = account.get_pnl()
    print(f"{account.nickname}: {pnl}")

    # Close all positions if loss > threshold
    if pnl < -10000:
        account.Positions.close_all()
```

---

**END OF MULTI-ACCOUNT ARCHITECTURE DOCUMENT**
