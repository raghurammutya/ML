# User Service - Comprehensive Feature Analysis

**Date:** 2025-11-09
**Analyst:** Claude Code
**Scope:** user_service + Python SDK

---

## Executive Summary

This document provides a detailed analysis of the **user_service** and **Python SDK** against your specific requirements for:
1. Multi-tenant support (organizations, families, individuals)
2. Registration processes
3. Authentication systems
4. Service-to-service authorization
5. Fine-grained permissions
6. API key management for Python SDK users

---

## A) Multi-Tenancy Support: Organizations, Families, Individuals

### ✅ **CURRENT STATE: PARTIAL SUPPORT**

#### What EXISTS:
1. **Individual Users** - ✅ FULLY SUPPORTED
   - Single user accounts with email/password or OAuth
   - Personal trading account management
   - Individual permissions and preferences
   - Location: `app/models/user.py:21-53`

2. **Trading Account Sharing** - ✅ FULLY SUPPORTED
   - Users can share their trading accounts with other users
   - Membership-based access control via `trading_account_memberships` table
   - Fine-grained permissions per membership: `['read', 'trade', 'manage']`
   - Location: `app/models/trading_account.py:75-99`
   - Example: User A can grant User B 'read' access to their trading account

3. **Role-Based Access Control (RBAC)** - ✅ FULLY SUPPORTED
   - Pre-defined roles: admin, trader, viewer, user
   - Multi-role support (users can have multiple roles)
   - Location: `app/models/role.py`

#### What is MISSING:

### ❌ **ORGANIZATIONS (Investment Firms) - NOT IMPLEMENTED**

**Missing Features:**
1. **No `organizations` table**
   - Cannot create investment firms/companies
   - Cannot group multiple users under a single organization
   - Cannot manage organization-level settings

2. **No organization hierarchy**
   - Cannot define departments/teams within organizations
   - Cannot have organization-level administrators
   - Cannot assign users to organizations with org-specific roles

3. **No organization-level trading accounts**
   - Trading accounts are tied to individual users, not organizations
   - Cannot have "company trading accounts" that belong to the organization
   - Cannot manage shared organizational capital

4. **No organization-level permissions**
   - Cannot define "Portfolio Manager", "Risk Officer", "Analyst" roles at org level
   - Cannot restrict access based on organizational hierarchy
   - Current permissions: user-centric, not org-centric

**What SHOULD exist for Investment Firm Support:**

```sql
-- MISSING TABLE: organizations
CREATE TABLE organizations (
    organization_id BIGSERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    type VARCHAR(50) NOT NULL,  -- 'investment_firm', 'family_office', 'proprietary_trading'
    status VARCHAR(50) DEFAULT 'active',
    settings JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- MISSING TABLE: organization_memberships
CREATE TABLE organization_memberships (
    membership_id BIGSERIAL PRIMARY KEY,
    organization_id BIGINT REFERENCES organizations(organization_id),
    user_id BIGINT REFERENCES users(user_id),
    role VARCHAR(50),  -- 'owner', 'admin', 'portfolio_manager', 'analyst', 'trader', 'viewer'
    permissions JSONB DEFAULT '["read"]',
    invited_by BIGINT REFERENCES users(user_id),
    joined_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(organization_id, user_id)
);

-- MISSING: Organization-level trading accounts
ALTER TABLE trading_accounts ADD COLUMN organization_id BIGINT REFERENCES organizations(organization_id);
-- Accounts can be owned by EITHER a user OR an organization
```

**Required Endpoints (NOT IMPLEMENTED):**
- `POST /v1/organizations` - Create organization
- `GET /v1/organizations/{org_id}` - Get organization details
- `PUT /v1/organizations/{org_id}` - Update organization
- `POST /v1/organizations/{org_id}/members` - Add member to org
- `DELETE /v1/organizations/{org_id}/members/{user_id}` - Remove member
- `GET /v1/organizations/{org_id}/members` - List organization members
- `GET /v1/organizations/{org_id}/trading-accounts` - List org trading accounts
- `POST /v1/organizations/{org_id}/roles` - Assign org-level role
- `GET /v1/organizations/{org_id}/permissions` - Get org permissions

---

### ❌ **FAMILIES - NOT IMPLEMENTED**

**Current State:**
- The system can SIMULATE family structures using trading account sharing
- Example: Parent can share trading accounts with children via `trading_account_memberships`
- BUT: No explicit "family" entity or family-specific logic

**What is MISSING:**

1. **No `families` table**
   - Cannot create a "Family Office" entity
   - Cannot group family members together
   - Cannot manage family-level settings (risk limits, inheritance rules, etc.)

2. **No family-specific permissions**
   - Cannot define "Head of Family", "Trustee", "Beneficiary" roles
   - Cannot enforce family-specific access rules (e.g., minors cannot trade)
   - Cannot track family relationships (parent-child, spouse, etc.)

3. **No consolidated family view**
   - Cannot see combined family portfolio
   - Cannot aggregate family P&L
   - Cannot manage family-wide risk limits

**What SHOULD exist for Family Office Support:**

```sql
-- MISSING TABLE: families
CREATE TABLE families (
    family_id BIGSERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    head_of_family_user_id BIGINT REFERENCES users(user_id),
    settings JSONB DEFAULT '{}',  -- risk_limits, notification_prefs, etc.
    created_at TIMESTAMP DEFAULT NOW()
);

-- MISSING TABLE: family_memberships
CREATE TABLE family_memberships (
    membership_id BIGSERIAL PRIMARY KEY,
    family_id BIGINT REFERENCES families(family_id),
    user_id BIGINT REFERENCES users(user_id),
    relationship VARCHAR(50),  -- 'parent', 'child', 'spouse', 'trustee'
    role VARCHAR(50),  -- 'head', 'beneficiary', 'advisor'
    permissions JSONB DEFAULT '["view_own"]',
    can_view_all_accounts BOOLEAN DEFAULT false,
    can_trade_on_behalf BOOLEAN DEFAULT false,
    UNIQUE(family_id, user_id)
);
```

**Required Endpoints (NOT IMPLEMENTED):**
- `POST /v1/families` - Create family
- `GET /v1/families/{family_id}` - Get family details
- `POST /v1/families/{family_id}/members` - Add family member
- `GET /v1/families/{family_id}/members` - List family members
- `GET /v1/families/{family_id}/accounts` - List all family trading accounts
- `GET /v1/families/{family_id}/portfolio` - Consolidated family portfolio
- `POST /v1/families/{family_id}/permissions` - Manage cross-account permissions

---

### ✅ **INDIVIDUALS - FULLY SUPPORTED**

**What EXISTS:**
1. User creates account → Links trading account → Trades ✅
2. User can share their trading account with others (via memberships) ✅
3. User has full control over their accounts ✅

**Locations:**
- Registration: `app/services/auth_service.py:31-120`
- Trading account linking: `app/services/trading_account_service.py`
- Sharing: `app/api/v1/endpoints/trading_accounts.py` (grant/revoke membership)

---

## B) Registration Process

### ✅ **FULLY IMPLEMENTED**

#### 1. **Email/Password Registration** - ✅
- **Endpoint:** `POST /v1/auth/register`
- **Location:** `app/api/v1/endpoints/auth.py:56-130`
- **Service:** `app/services/auth_service.py:31-120`

**Features:**
- Email validation (must be unique)
- Password strength validation:
  - Minimum 12 characters
  - Uppercase, lowercase, numbers, special characters
  - zxcvbn entropy check
  - Cannot contain user's email or name
- Phone number (optional)
- Timezone and locale preferences
- Rate limiting: 5 registrations/hour per IP
- Auto-assigns default 'user' role
- Creates default preferences record
- Publishes `user.registered` event

**Response:**
```json
{
  "user_id": 123,
  "email": "user@example.com",
  "status": "pending_verification",
  "verification_email_sent": true,
  "created_at": "2025-11-09T..."
}
```

#### 2. **Google OAuth Registration** - ✅
- **Endpoint:** `POST /v1/auth/oauth/google`
- **Location:** `app/api/v1/endpoints/auth.py` (OAuth endpoints)
- **Service:** `app/services/oauth_service.py`

**Features:**
- OAuth 2.0 Authorization Code flow
- CSRF protection with state token (10-minute expiry)
- Auto-creates user account if doesn't exist
- Links Google account to user
- No password required for OAuth-only users
- Publishes `user.registered` event for new users

**Flow:**
1. Client calls `POST /v1/auth/oauth/google` → Get authorization URL
2. User authorizes on Google → Google redirects to callback
3. Client calls `POST /v1/auth/oauth/google/callback` → Get JWT tokens

#### 3. **Missing Registration Features**

**✅ Implemented:**
- Email verification status tracking (`email_verified` field exists)
- Phone verification status tracking (`phone_verified` field exists)

**❌ NOT Implemented:**
- Email verification flow (no send verification email, no verify endpoint)
- SMS/phone verification flow
- Invitation-based registration (for organizations/families)
- Self-service password recovery during registration (only post-login)
- Organization/family association during registration

---

## C) Authentication Systems

### ✅ **FULLY IMPLEMENTED**

#### 1. **Email/Password Authentication** - ✅
- **Endpoint:** `POST /v1/auth/login`
- **Location:** `app/services/auth_service.py:122-208`

**Features:**
- bcrypt password hashing (cost factor 12)
- Device fingerprinting for session tracking
- Multi-device session support
- IP address and country tracking
- Rate limiting: 5 attempts/15 minutes per IP
- MFA challenge if enabled
- Persistent sessions (optional, 90-day refresh token)
- Publishes `user.login` event

**Response:**
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "Bearer",
  "expires_in": 900,
  "user": {...},
  "mfa_required": false
}
```

#### 2. **JWT Tokens (RS256)** - ✅
- **Service:** `app/services/jwt_service.py`

**Features:**
- RS256 asymmetric signing (public/private key pair)
- Access token: 15-minute TTL
- Refresh token: 90-day TTL
- Token rotation on refresh (prevents reuse)
- Reuse detection (revokes all sessions if violated)
- JWK Set (JWKS) endpoint for verification: `GET /v1/auth/.well-known/jwks.json`
- Session tracking in Redis

**Token Claims:**
```json
{
  "sub": "123",  // user_id
  "email": "user@example.com",
  "name": "John Doe",
  "roles": ["user", "trader"],
  "session_id": "uuid",
  "iat": 1699564800,
  "exp": 1699565700
}
```

#### 3. **MFA/TOTP (Two-Factor Authentication)** - ✅
- **Endpoints:** `POST /v1/mfa/setup`, `POST /v1/mfa/verify-setup`, `POST /v1/auth/mfa/verify`
- **Service:** `app/services/mfa_service.py`

**Features:**
- TOTP (RFC 6238) with 30-second time step
- QR code generation for Google Authenticator
- 6-digit codes
- 10 single-use backup codes
- Backup code regeneration
- MFA challenge during login
- Rate limiting: 5 attempts/15 minutes

**MFA Setup Flow:**
1. `POST /v1/mfa/setup` → Get secret + QR code
2. `POST /v1/mfa/verify-setup` → Verify first code → Enable MFA
3. Next login → `POST /v1/auth/login` → Returns `mfa_required: true`
4. `POST /v1/auth/mfa/verify` → Complete login with TOTP code

#### 4. **Google OAuth 2.0** - ✅
- **Service:** `app/services/oauth_service.py`

**Features:**
- Authorization Code flow with PKCE-style state token
- CSRF protection
- Auto-creates or links user account
- Supports OAuth-only users (no password)
- Publishes `oauth.linked` event

#### 5. **Session Management** - ✅
- **Endpoints:** `GET /v1/auth/sessions`, `POST /v1/auth/logout`

**Features:**
- Multi-device session tracking
- Device fingerprinting
- IP and country tracking
- Last active timestamp
- Session revocation (single device or all devices)
- 14-day inactivity timeout
- Redis-backed session storage

**Session Storage:**
- Key: `session:{session_id}`
- Value: `{user_id, device_fingerprint, ip, country, last_active, refresh_token_family}`

#### 6. **Password Reset** - ✅
- **Endpoints:** `POST /v1/auth/password/reset-request`, `POST /v1/auth/password/reset`
- **Service:** `app/services/password_reset_service.py`

**Features:**
- Secure 256-bit token generation
- 30-minute token expiry
- Single-use tokens
- Always returns success (security: don't leak if email exists)
- Password strength validation on reset
- Publishes `password.reset_completed` event

#### 7. **Rate Limiting** - ✅
- **Implementation:** `app/core/redis_client.py`

**Limits:**
- Login: 5 attempts / 15 minutes (per IP)
- Registration: 5 attempts / 1 hour (per IP)
- Token refresh: 10 attempts / 1 minute
- Password reset: 5 attempts / 1 hour
- MFA: 5 attempts / 15 minutes

---

### ❌ **MISSING AUTHENTICATION FEATURES**

1. **API Keys for User Authentication** - NOT IMPLEMENTED
   - No `api_keys` table
   - No API key generation endpoint
   - No API key-based authentication middleware
   - Python SDK expects API keys but backend doesn't provide them

2. **Email Verification**
   - Fields exist (`email_verified`) but no flow implemented
   - No email sending integration
   - No verification token/link generation

3. **Phone/SMS Verification**
   - Fields exist (`phone_verified`) but no flow implemented
   - No SMS integration

4. **Social Login (beyond Google)**
   - Only Google OAuth is implemented
   - Missing: GitHub, Microsoft, LinkedIn, etc.

5. **Passwordless Login**
   - No magic link authentication
   - No WebAuthn/FIDO2 support

---

## D) Service-to-Service Authorization

### ✅ **PARTIALLY IMPLEMENTED**

#### What EXISTS:

1. **Policy Decision Point (PDP)** - ✅ FULLY IMPLEMENTED
   - **Endpoint:** `POST /v1/authz/check`
   - **Service:** `app/services/authz_service.py`
   - **Location:** `app/api/v1/endpoints/authz.py:40-91`

**Features:**
- Centralized authorization service
- RBAC + ABAC (Role-Based + Attribute-Based Access Control)
- Pattern matching with wildcards (`user:*`, `trade:*`, etc.)
- Redis-backed permission caching (60-second TTL)
- <5ms cached, <20ms uncached
- DENY overrides ALLOW (fail-secure)
- Default deny if no policies match

**Request:**
```json
{
  "subject": "user:123",
  "action": "trade:place_order",
  "resource": "trading_account:456",
  "context": {"ip": "1.2.3.4"}
}
```

**Response:**
```json
{
  "allowed": true,
  "decision": "allow",
  "matched_policy": "allow_account_owner_to_trade"
}
```

2. **JWKS Endpoint for JWT Verification** - ✅ FULLY IMPLEMENTED
   - **Endpoint:** `GET /v1/auth/.well-known/jwks.json`
   - **Location:** `app/api/v1/endpoints/auth.py`

**Features:**
- Public endpoint (no auth required)
- Returns RS256 public keys in JWK format
- Other services can verify JWTs independently
- Used by API Gateway, backend services, etc.

**Response:**
```json
{
  "keys": [
    {
      "kty": "RSA",
      "use": "sig",
      "kid": "default",
      "alg": "RS256",
      "n": "...",
      "e": "AQAB"
    }
  ]
}
```

3. **Trading Account Ownership & Membership Checks** - ✅ FULLY IMPLEMENTED
   - Built into authorization service
   - Location: `app/services/authz_service.py:96-135`

**Logic:**
- Owner has full access (read, trade, manage)
- Members have permissions based on `trading_account_memberships.permissions`
- Non-members are denied by default

---

#### What is MISSING:

### ❌ **API Keys for Service-to-Service Auth - NOT IMPLEMENTED**

**Current State:**
- Python SDK has API key support (`TradingClient(api_key="sb_...")`)
- Backend does NOT have API key authentication
- No `api_keys` table
- No API key middleware

**What SHOULD exist:**

```sql
-- MISSING TABLE: api_keys
CREATE TABLE api_keys (
    api_key_id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(user_id),
    organization_id BIGINT REFERENCES organizations(organization_id),  -- optional
    key_prefix VARCHAR(20) NOT NULL,  -- 'sb_30d4d5ea'
    key_hash VARCHAR(255) NOT NULL,  -- SHA-256 hash of full key
    name VARCHAR(255) NOT NULL,  -- 'Production Bot', 'Dev Testing'
    scopes JSONB DEFAULT '["read"]',  -- ['read', 'trade', 'admin']
    ip_whitelist JSONB,  -- ['1.2.3.4', '5.6.7.8'] or null (any IP)
    rate_limit_tier VARCHAR(50) DEFAULT 'standard',  -- 'standard', 'premium', 'unlimited'
    last_used_at TIMESTAMP,
    expires_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    revoked_at TIMESTAMP,
    UNIQUE(key_prefix)
);

-- MISSING TABLE: api_key_usage
CREATE TABLE api_key_usage (
    usage_id BIGSERIAL PRIMARY KEY,
    api_key_id BIGINT REFERENCES api_keys(api_key_id),
    endpoint VARCHAR(255),
    method VARCHAR(10),
    status_code INTEGER,
    response_time_ms INTEGER,
    timestamp TIMESTAMP DEFAULT NOW()
);
```

**Required Endpoints (NOT IMPLEMENTED):**
- `POST /v1/api-keys` - Create API key
- `GET /v1/api-keys` - List user's API keys
- `DELETE /v1/api-keys/{key_id}` - Revoke API key
- `PUT /v1/api-keys/{key_id}/rotate` - Rotate API key

**Required Middleware (NOT IMPLEMENTED):**
- `api_key_auth()` dependency in `app/api/dependencies.py`
- Extract API key from `Authorization: Bearer sb_...` or `X-API-Key: sb_...` header
- Validate key hash
- Check IP whitelist
- Check expiry
- Check scopes
- Rate limit by key

---

### ❌ **OAuth Client Credentials Flow - PARTIALLY IMPLEMENTED**

**Current State:**
- `oauth_clients` table exists (for client_id/client_secret storage)
- Location: `app/models/oauth.py`
- NO endpoint to issue client credentials tokens
- NO client credentials authentication flow

**What is MISSING:**
- `POST /v1/oauth/token` endpoint with `grant_type=client_credentials`
- Client authentication via `client_id` + `client_secret`
- Scope-based access control for service accounts

---

## E) Fine-Grained Permissions

### ✅ **FULLY IMPLEMENTED**

#### 1. **RBAC (Role-Based Access Control)** - ✅
- **Model:** `app/models/role.py`
- **Tables:** `roles`, `user_roles`

**Pre-defined Roles:**
- `admin` - Full system access
- `trader` - Trading permissions
- `viewer` - Read-only access
- `user` - Default user role

**Features:**
- Multi-role support (users can have multiple roles)
- Role assignment by admins
- Role-based policy evaluation

#### 2. **ABAC (Attribute-Based Access Control)** - ✅
- **Model:** `app/models/policy.py`
- **Service:** `app/services/authz_service.py`

**Policy Structure:**
```json
{
  "name": "allow_account_owner_to_trade",
  "effect": "allow",
  "subjects": ["user:*"],
  "actions": ["trade:*"],
  "resources": ["trading_account:*"],
  "conditions": {"owner": true},
  "priority": 10,
  "enabled": true
}
```

**Features:**
- Pattern matching with wildcards
- Condition-based evaluation (owner, ip, time, etc.)
- Priority-based conflict resolution
- DENY overrides ALLOW
- Redis caching for performance

**Example Policies:**
1. **Owner can manage their account:**
   - Subject: `user:*`
   - Action: `account:*`
   - Resource: `trading_account:*`
   - Condition: `owner = true`

2. **Members with 'trade' permission can trade:**
   - Subject: `user:*`
   - Action: `trade:place_order`
   - Resource: `trading_account:*`
   - Condition: `membership.permissions contains 'trade'`

3. **Admins can do anything:**
   - Subject: `role:admin`
   - Action: `*`
   - Resource: `*`

#### 3. **Trading Account Memberships** - ✅
- **Model:** `app/models/trading_account.py:75-99`
- **Table:** `trading_account_memberships`

**Permissions Array:**
- `['read']` - View account details, positions, orders
- `['read', 'trade']` - View + place orders
- `['read', 'trade', 'manage']` - View + trade + modify account settings

**Features:**
- Granular per-account permissions
- Granted by account owner
- Revocable (soft delete with `revoked_at`)
- Audit trail (granted_by, granted_at)

#### 4. **Permission Caching** - ✅
- **Implementation:** `app/services/authz_service.py`
- **Cache:** Redis with 60-second TTL

**Performance:**
- Cached check: <5ms
- Uncached check: <20ms
- Cache key: `authz:{subject}:{action}:{resource}`

---

#### What is MISSING:

### ❌ **Granular Action Permissions**

**Current State:**
- Actions are string-based: `trade:place_order`, `account:view`
- No formal action registry
- No documentation of available actions

**What SHOULD exist:**
- Formal action definitions in code or database
- Action categories and hierarchies
- Action documentation endpoint

### ❌ **Resource-Level Attributes**

**Current State:**
- Policies can match resources by pattern: `trading_account:*`
- No resource attribute evaluation (e.g., account.status, account.balance)

**What SHOULD exist:**
- Dynamic resource attribute loading
- Context-aware evaluation (e.g., "deny if account.balance < 0")

### ❌ **Time-Based Permissions**

**Current State:**
- No time-based policy evaluation
- Cannot restrict access to trading hours, weekdays, etc.

**What SHOULD exist:**
- Condition: `time.hour >= 9 && time.hour < 16` (market hours)
- Condition: `time.weekday in [1,2,3,4,5]` (weekdays only)

### ❌ **IP-Based Permissions**

**Current State:**
- IP is tracked in sessions and audit events
- NOT evaluated in authorization policies

**What SHOULD exist:**
- Condition: `ip in ['1.2.3.4', '5.6.7.8']` (whitelist)
- Condition: `ip.country = 'US'` (geo-restriction)

---

## F) API Keys for Python SDK Users

### ❌ **NOT IMPLEMENTED**

#### Current State:

**Python SDK:**
- Supports API key authentication: `TradingClient(api_key="sb_...")`
- Location: `python-sdk/stocksblitz/client.py:48-91`
- Example: `python-sdk/examples/api_key_auth_example.py`

**Backend (user_service):**
- **NO API key support**
- No `api_keys` table
- No API key generation endpoint
- No API key authentication middleware

**Gap:**
- SDK expects API keys but backend doesn't issue them
- Users cannot use API key authentication
- Must use JWT (username/password) authentication

---

#### What is MISSING:

### 1. **API Key Generation**

**Required Endpoint:**
```http
POST /v1/api-keys
Content-Type: application/json
Authorization: Bearer <jwt_access_token>

{
  "name": "Production Trading Bot",
  "scopes": ["read", "trade"],
  "expires_in_days": 365,
  "ip_whitelist": ["1.2.3.4"]
}

Response:
{
  "api_key_id": 123,
  "api_key": "sb_30d4d5ea_bbb52c64cc4eb2536fdd7b44861c93e4b30b50c6",
  "key_prefix": "sb_30d4d5ea",
  "name": "Production Trading Bot",
  "scopes": ["read", "trade"],
  "created_at": "2025-11-09T...",
  "expires_at": "2026-11-09T..."
}
```

**Security:**
- Return full key ONCE (cannot retrieve later)
- Store SHA-256 hash in database
- Key format: `sb_{8_char_prefix}_{40_char_secret}`

### 2. **API Key Authentication Middleware**

**Required Implementation:**
```python
# app/api/dependencies.py

async def get_current_user_from_api_key(
    api_key: str = Header(None, alias="X-API-Key"),
    authorization: str = Header(None)
) -> User:
    """
    Authenticate user via API key.

    Supports:
    - X-API-Key: sb_30d4d5ea_bbb52c64...
    - Authorization: Bearer sb_30d4d5ea_bbb52c64...
    """
    # Extract API key from header
    if api_key:
        key = api_key
    elif authorization and authorization.startswith("Bearer sb_"):
        key = authorization.replace("Bearer ", "")
    else:
        raise HTTPException(401, "API key required")

    # Parse key (prefix + secret)
    prefix, secret = parse_api_key(key)

    # Lookup by prefix
    api_key_record = db.query(ApiKey).filter(
        ApiKey.key_prefix == prefix,
        ApiKey.revoked_at.is_(None),
        ApiKey.expires_at > datetime.utcnow()
    ).first()

    if not api_key_record:
        raise HTTPException(401, "Invalid API key")

    # Verify secret hash
    secret_hash = hashlib.sha256(secret.encode()).hexdigest()
    if secret_hash != api_key_record.key_hash:
        raise HTTPException(401, "Invalid API key")

    # Check IP whitelist
    if api_key_record.ip_whitelist:
        if client_ip not in api_key_record.ip_whitelist:
            raise HTTPException(403, "IP not whitelisted")

    # Update last_used_at
    api_key_record.last_used_at = datetime.utcnow()
    db.commit()

    # Return user
    return api_key_record.user
```

### 3. **API Key Management Endpoints**

**Required:**
- `GET /v1/api-keys` - List user's API keys (without secrets)
- `DELETE /v1/api-keys/{key_id}` - Revoke API key
- `PUT /v1/api-keys/{key_id}` - Update name, scopes, IP whitelist
- `POST /v1/api-keys/{key_id}/rotate` - Generate new key, revoke old

### 4. **API Key Scopes**

**Scope Examples:**
- `read` - Read-only access (GET endpoints)
- `trade` - Place/cancel orders
- `admin` - Full access
- `account:manage` - Manage trading accounts
- `strategy:execute` - Execute strategies

**Enforcement:**
```python
# In endpoint dependencies
def require_scope(scope: str):
    def dependency(api_key: ApiKey = Depends(get_current_api_key)):
        if scope not in api_key.scopes:
            raise HTTPException(403, f"Scope '{scope}' required")
        return api_key
    return dependency

# Usage
@router.post("/orders")
async def place_order(
    api_key: ApiKey = Depends(require_scope("trade"))
):
    ...
```

### 5. **Rate Limiting by API Key**

**Implementation:**
```python
# Different rate limits per tier
RATE_LIMITS = {
    "free": (100, 3600),       # 100 requests/hour
    "standard": (1000, 3600),  # 1000 requests/hour
    "premium": (10000, 3600),  # 10000 requests/hour
    "unlimited": None          # No limit
}

# Check rate limit
rate_limit_key = f"ratelimit:apikey:{api_key_id}"
allowed, remaining = redis.check_rate_limit(
    rate_limit_key,
    RATE_LIMITS[api_key.rate_limit_tier][0],
    RATE_LIMITS[api_key.rate_limit_tier][1]
)
```

---

## G) Other Functionality in Current Codebase

### Additional Features (Beyond Your Questions):

#### 1. **Audit Trail & Compliance** - ✅
- **Endpoint:** `GET /v1/audit/events`
- **Model:** `app/models/auth_event.py`
- **Table:** `auth_events` (TimescaleDB hypertable)

**Features:**
- Complete event logging for all user actions
- Event types: login, logout, password_change, mfa_enabled, trading_account_linked, etc.
- Queryable with filters (user_id, event_type, date range)
- JSON/CSV export
- 24-hour retention for exports

**Use Cases:**
- Compliance audits
- Security investigations
- User activity tracking

#### 2. **Event Publishing (Event-Driven Architecture)** - ✅
- **Service:** `app/services/event_service.py`
- **Transport:** Redis Pub/Sub

**16 Event Types:**
- `user.registered`, `user.login`, `user.logout`, `user.updated`, `user.deleted`
- `password.changed`, `password.reset_completed`
- `session.created`, `session.revoked`
- `mfa.enabled`, `mfa.disabled`
- `trading_account.linked`, `trading_account.unlinked`, `trading_account.credentials_updated`
- `permission.granted`, `permission.revoked`

**Channels:**
- `events:user_service:*`

**Use Cases:**
- Other microservices subscribe to user events
- Example: Order service subscribes to `trading_account.linked` to enable trading
- Example: Notification service subscribes to `user.login` for security alerts

#### 3. **Credential Encryption (KMS)** - ✅
- **Service:** `app/services/kms_service.py`
- **Algorithm:** Envelope encryption

**Features:**
- Master key encryption (KMS)
- Data key encryption (AES-256)
- Supports: Local, AWS KMS, HashiCorp Vault
- Used for: Trading account credentials, TOTP secrets

**Encryption Flow:**
1. Generate data key (AES-256)
2. Encrypt credentials with data key
3. Encrypt data key with KMS master key
4. Store encrypted credentials + wrapped data key

#### 4. **Subscription Tier Detection (Zerodha)** - ✅
- **Service:** `app/services/subscription_tier_detector.py`

**Features:**
- Detects KiteConnect subscription tier
- Tiers: Personal (free), Connect (paid), Startup (free with benefits)
- Determines market data availability
- Auto-updates on trading account sync

**Use Cases:**
- Restrict market data access based on subscription
- Upsell users to paid tier

#### 5. **User Preferences** - ✅
- **Endpoint:** `GET /v1/users/preferences`, `PUT /v1/users/preferences`
- **Model:** `app/models/preference.py`

**Features:**
- JSONB preferences (flexible schema)
- Default trading account selection
- Theme, notification, display preferences

#### 6. **Health Checks** - ✅
- **Endpoint:** `GET /health`

**Features:**
- Database connectivity check
- Redis connectivity check
- Returns overall status

---

## H) Missing Functionality / Feature Gaps

### Critical Missing Features:

#### 1. **API Keys for SDK Users** - ❌ HIGHEST PRIORITY
- **Impact:** SDK users cannot use API key authentication
- **Effort:** Medium (3-5 days)
- **Components:**
  - `api_keys` table
  - API key generation endpoint
  - Authentication middleware
  - Management endpoints (list, revoke, rotate)
  - Scope enforcement
  - Rate limiting by key

#### 2. **Organizations (Investment Firms)** - ❌ HIGH PRIORITY
- **Impact:** Cannot support multi-user investment firms
- **Effort:** High (7-10 days)
- **Components:**
  - `organizations` table
  - `organization_memberships` table
  - Organization CRUD endpoints
  - Member management endpoints
  - Organization-level trading accounts
  - Organization-level permissions
  - Consolidated organization portfolio view

#### 3. **Families (Family Offices)** - ❌ HIGH PRIORITY
- **Impact:** Cannot support family office use case
- **Effort:** High (7-10 days)
- **Components:**
  - `families` table
  - `family_memberships` table
  - Family CRUD endpoints
  - Relationship tracking (parent, child, etc.)
  - Cross-account permissions
  - Consolidated family portfolio view
  - Family-level risk limits

#### 4. **Email Verification** - ❌ MEDIUM PRIORITY
- **Impact:** Security concern, cannot verify email ownership
- **Effort:** Medium (2-3 days)
- **Components:**
  - Email service integration (SendGrid, SES, etc.)
  - Verification token generation
  - `POST /v1/auth/email/verify` endpoint
  - `POST /v1/auth/email/resend-verification` endpoint

#### 5. **Invitation System** - ❌ MEDIUM PRIORITY
- **Impact:** Cannot invite users to organizations/families
- **Effort:** Medium (3-4 days)
- **Components:**
  - `invitations` table
  - `POST /v1/organizations/{org_id}/invite` endpoint
  - `POST /v1/families/{family_id}/invite` endpoint
  - `POST /v1/invitations/{token}/accept` endpoint
  - Email invitations

#### 6. **Admin Dashboard Endpoints** - ❌ LOW PRIORITY
- **Impact:** No admin UI capabilities
- **Effort:** Medium (4-5 days)
- **Components:**
  - User management (list, search, suspend, delete)
  - Organization management
  - System health metrics
  - Audit log viewer

#### 7. **WebAuthn/Passwordless Auth** - ❌ LOW PRIORITY
- **Impact:** Nice-to-have for UX
- **Effort:** High (5-7 days)
- **Components:**
  - WebAuthn registration
  - WebAuthn authentication
  - FIDO2 credential storage

---

## Summary: Requirements Checklist

| Requirement | Status | Notes |
|-------------|--------|-------|
| **a) Multi-Tenancy** | | |
| - Organizations (1 org, multi-user, shared accounts) | ❌ | NOT IMPLEMENTED |
| - Families (multi-user, shared accounts) | ❌ | NOT IMPLEMENTED (can simulate with memberships) |
| - Individuals | ✅ | FULLY SUPPORTED |
| - Varying responsibilities/permissions | ✅ | FULLY SUPPORTED (via memberships + policies) |
| **b) Registration** | | |
| - Email/password registration | ✅ | FULLY IMPLEMENTED |
| - OAuth registration (Google) | ✅ | FULLY IMPLEMENTED |
| - Email verification | ❌ | Fields exist, flow NOT implemented |
| **c) Authentication** | | |
| - Email/password login | ✅ | FULLY IMPLEMENTED |
| - JWT tokens (access + refresh) | ✅ | FULLY IMPLEMENTED |
| - MFA/TOTP | ✅ | FULLY IMPLEMENTED |
| - OAuth (Google) | ✅ | FULLY IMPLEMENTED |
| - Password reset | ✅ | FULLY IMPLEMENTED |
| - Session management | ✅ | FULLY IMPLEMENTED |
| - API keys | ❌ | NOT IMPLEMENTED |
| **d) Service Authorization** | | |
| - Centralized PDP (authz check) | ✅ | FULLY IMPLEMENTED |
| - JWKS endpoint for JWT verification | ✅ | FULLY IMPLEMENTED |
| - Policy-based access control | ✅ | FULLY IMPLEMENTED |
| **e) Fine-Grained Permissions** | | |
| - RBAC (roles) | ✅ | FULLY IMPLEMENTED |
| - ABAC (policies) | ✅ | FULLY IMPLEMENTED |
| - Trading account memberships | ✅ | FULLY IMPLEMENTED |
| - Permission caching | ✅ | FULLY IMPLEMENTED |
| **f) API Keys for SDK** | | |
| - API key generation | ❌ | NOT IMPLEMENTED |
| - API key authentication | ❌ | NOT IMPLEMENTED |
| - Scope enforcement | ❌ | NOT IMPLEMENTED |
| - Rate limiting by key | ❌ | NOT IMPLEMENTED |

---

## Recommendations

### Phase 1: API Keys (Immediate Priority)
- Implement API key management system
- Enable SDK users to authenticate without credentials
- Timeline: 1 week

### Phase 2: Organizations (High Priority)
- Add organization multi-tenancy
- Support investment firms with multiple traders
- Timeline: 2 weeks

### Phase 3: Families (High Priority)
- Add family office support
- Enable cross-account permissions within families
- Timeline: 2 weeks

### Phase 4: Email Verification (Security)
- Implement email verification flow
- Integrate email service
- Timeline: 1 week

### Phase 5: Invitations (Enhancement)
- Add invitation system for orgs/families
- Timeline: 1 week

---

**End of Analysis**
