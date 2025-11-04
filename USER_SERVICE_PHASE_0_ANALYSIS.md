# Phase 0: Service Landscape Analysis for user_service Design

**Document Version:** 1.0
**Date:** 2025-11-03
**Status:** Complete - Ready for Phase 1 Design

---

## Executive Summary

This document provides a comprehensive analysis of the existing microservices architecture for a trading platform to ensure the new `user_service` fits perfectly with **zero overlap and no gaps**. The analysis covers six services: `calendar_service`, `alert_service`, `ticker_service`, `backend` (API gateway), `frontend`, and the planned `user_service`.

**Key Findings:**
- Current architecture has **NO central identity/auth system** - this is the primary gap
- Backend currently handles API keys but no user sessions or OAuth flows
- Alert service has `user_id` fields but no actual user management
- Ticker service manages trading accounts but no user ownership model
- Services share TimescaleDB (`stocksblitz_unified`) and Redis infrastructure
- Redis pub/sub is the primary event bus (no Kafka/RabbitMQ)

**Critical Gap:** The platform currently has no user authentication, session management, or authorization beyond API keys. The `user_service` must fill this gap while integrating cleanly with existing services.

---

## 0.1 Responsibility Matrix (RACI)

**Legend:**
- **R** = Responsible (does the work)
- **A** = Accountable (single decision authority)
- **C** = Consulted (provides input)
- **I** = Informed (kept in the loop)

| Capability | user_service | backend | ticker_service | alert_service | calendar_service | frontend | messaging_service (future) |
|------------|--------------|---------|----------------|---------------|------------------|----------|---------------------------|
| **IDENTITY & AUTH** |
| User registration/login | **R,A** | I | - | - | - | C | - |
| OAuth flows (Google) | **R,A** | I | - | - | - | C | - |
| MFA/TOTP management | **R,A** | - | - | - | - | C | - |
| Session lifecycle | **R,A** | I | - | - | - | I | - |
| Stay-signed-in (refresh tokens) | **R,A** | C | - | - | - | I | - |
| Password reset flows | **R,A** | - | - | - | - | C | - |
| Device/IP risk signals | **R,A** | I | - | I | - | - | I |
| **AUTHORIZATION** |
| Token issuance (JWT/PASETO) | **R,A** | I | I | I | I | I | I |
| Token introspection | **R,A** | C | C | C | C | - | - |
| `/authz/check` PDP | **R,A** | C | C | C | C | - | - |
| Role/policy management | **R,A** | - | - | - | - | - | - |
| Permission grants/revokes | **R,A** | I | I | I | - | - | I |
| **USER PROFILES** |
| Profile CRUD | **R,A** | I | - | - | - | C | - |
| Preferences (watchlists, tz) | **R,A** | I | C | C | - | C | - |
| Default trading account | **R,A** | I | C | - | - | C | - |
| User directory/search | **R,A** | C | - | - | - | C | - |
| **TRADING ACCOUNTS** |
| Account linking (credentials) | **R,A** | - | C | - | - | C | - |
| Credential vault storage | **R,A** | - | - | - | - | - | - |
| Broker profile sync | **R,A** | - | C | - | C | - | - |
| Credential rotation | **R,A** | I | I | - | - | - | I |
| Shared account memberships | **R,A** | - | C | - | - | C | - |
| Trading account permissions | **R,A** | - | C | - | - | - | - |
| **EVENTS & WEBHOOKS** |
| Identity events publishing | **R,A** | I | I | I | I | I | I |
| Webhook delivery infra | **R,A** | - | - | - | - | - | C |
| Event signing/verification | **R,A** | C | - | - | - | - | C |
| **AUDIT & COMPLIANCE** |
| Auth audit logging | **R,A** | I | - | - | - | - | - |
| GDPR export/delete | **R,A** | I | I | I | I | - | I |
| Compliance queries | **R,A** | C | - | - | - | - | - |
| **API KEYS (legacy)** |
| API key management | C | **R,A** | - | - | - | - | - |
| API key auth validation | - | **R,A** | R | R | R | - | - |
| **MARKET DATA** |
| Live ticker subscriptions | - | C | **R,A** | C | - | C | - |
| Historical candles | - | C | **R,A** | - | - | - | - |
| Instrument registry | - | - | **R,A** | - | - | - | - |
| Mock data generation | - | - | **R,A** | - | - | - | - |
| Order execution | - | C | **R,A** | I | - | C | - |
| **INDICATORS & CHARTS** |
| Indicator computation | - | **R,A** | C | C | - | C | - |
| TradingView UDF protocol | - | **R,A** | - | - | - | C | - |
| Chart labels/marks | - | **R,A** | - | - | - | C | - |
| Real-time data aggregation | - | **R,A** | I | - | - | I | - |
| **CALENDAR** |
| Market hours/holidays | - | C | C | - | **R,A** | C | - |
| Trading session mgmt | - | - | C | - | **R,A** | - | - |
| Special hours (Muhurat) | - | - | - | - | **R,A** | - | - |
| Admin calendar updates | - | C | - | - | **R,A** | - | - |
| **ALERTS** |
| Alert condition evaluation | - | C | C | **R,A** | - | C | - |
| Alert CRUD | - | C | - | **R,A** | - | C | - |
| Notification dispatch | - | - | - | **R,A** | - | - | C |
| Telegram bot integration | - | - | - | **R,A** | - | - | C |
| **FRONTEND UI** |
| Monitor dashboard | - | - | - | - | - | **R,A** | - |
| Chart visualization | - | - | - | - | - | **R,A** | - |
| Auth flows/login UI | C | - | - | - | - | **R,A** | - |
| User settings UI | C | - | - | - | - | **R,A** | - |
| **GATEWAY/ROUTING** |
| API gateway/routing | - | **R,A** | - | - | - | - | - |
| WebSocket hubs | - | **R,A** | - | - | - | - | - |
| Request rate limiting | C | **R,A** | R | R | R | - | - |
| CORS handling | - | **R,A** | - | - | - | C | - |

### Key Observations from Matrix

**Clear Gaps (user_service must fill):**
1. No centralized identity management
2. No OAuth/SSO flows
3. No session management beyond API keys
4. No user profile/preferences system
5. No trading account credential management
6. No authorization PDP (policy decision point)
7. No audit logging for auth events

**Current Overlaps to Resolve:**
1. **API Key Auth**: Backend owns current system; user_service should provide JWT/OAuth2 tokens and eventually migrate API keys to a unified model
2. **Trading Account Metadata**: ticker_service has `trading_accounts` table but no user ownership - user_service should own the linking/ownership model
3. **User Context**: alert_service has `user_id` field but no actual user registry - user_service provides this

**Integration Points:**
- All services (R marked) must **consume** user_service tokens for authentication
- All services (C marked) must **call** user_service `/authz/check` for authorization decisions
- Alert, ticker, calendar should **subscribe** to user_service identity events
- Backend remains the API gateway but **delegates** all auth to user_service

---

## 0.2 Ownership Map (Data & API)

### Data Ownership (Single Source of Truth)

| Domain Object | Source of Truth | Cache Allowed | Cache TTL | Update Mechanism |
|---------------|-----------------|---------------|-----------|------------------|
| **IDENTITY** |
| User (id, email, phone) | **user_service** PG | backend (short), frontend (memory) | 5 min (backend), session (frontend) | Event: `user.updated` |
| Session | **user_service** Redis | frontend (memory) | Session lifetime | Session create/refresh |
| Access Token | **user_service** issued | All services (validate only) | Token exp (5-15 min) | Introspection or local JWT validation |
| Refresh Token | **user_service** Redis | None (never cached) | 30-90 days rotating | Rotation on use |
| Password Hash | **user_service** PG | Never | N/A | User action only |
| MFA Seed/Backup Codes | **user_service** vault/KMS | Never | N/A | User action only |
| **AUTHORIZATION** |
| Role/Policy | **user_service** PG | All services (decision cache) | 1-5 min | Event: `permission.updated` |
| Permission Grant | **user_service** PG | backend, services (decision cache) | 1-5 min | Event: `permission.granted/revoked` |
| Token Claims | **user_service** issued | Services (extract from token) | Token lifetime | Token refresh |
| **PROFILES** |
| User Profile | **user_service** PG | backend | 5 min | Event: `user.profile.updated` |
| Preferences (watchlists) | **user_service** PG | ticker_service, backend | 5 min | Event: `user.preferences.updated` |
| Timezone/Locale | **user_service** PG | backend, frontend | Session | Event: `user.preferences.updated` |
| Default Trading Acct | **user_service** PG | frontend | Session | Event: `user.preferences.updated` |
| **TRADING ACCOUNTS** |
| TradingAccount Link | **user_service** PG | ticker_service (metadata only) | 15 min | Event: `trading_account.linked` |
| Membership (sharing) | **user_service** PG | ticker_service | 5 min | Event: `trading_account.membership.*` |
| Credentials (api_key/secret) | **user_service** vault/KMS | Never | N/A | Never exposed; used internally |
| TOTP Seed | **user_service** vault/KMS | Never | N/A | Never exposed; used internally |
| Broker Profile Snapshot | **user_service** PG (synced) | ticker_service, calendar | 1 hour | Event: `trading_account.profile.synced` |
| **AUDIT** |
| Auth Event Log | **user_service** TimescaleDB | Never | N/A | Write-only append |
| Security Anomaly | **user_service** TimescaleDB | alert_service (read for alerting) | N/A | Event: `session.anomaly` |
| **API KEYS (legacy)** |
| API Key Registry | **backend** PG | backend (in-memory) | Application lifetime | Direct DB update |
| API Key Hash | **backend** PG | Never | N/A | Direct DB update |
| **MARKET DATA** |
| Instrument Registry | **ticker_service** PG | backend, alert_service | 1 day | Daily refresh |
| Subscription State | **ticker_service** PG | backend | 1 min | Event: `subscription.*` |
| Live Tick | **ticker_service** Redis pub | backend, alert_service | Ephemeral | Real-time stream |
| Historical Candles | **ticker_service** (fetch) → **backend** PG | backend | Immutable | Backfill process |
| Order Task | **ticker_service** PG | None | N/A | Task queue |
| **INDICATORS** |
| Computed Indicator | **backend** PG | backend (Redis) | 1-5 min | On-demand compute |
| Label/Mark | **backend** PG | frontend | Session | Direct API |
| **CALENDAR** |
| Holiday/Session | **calendar_service** PG | ticker_service, backend | 1 day | Admin API update |
| Market Status | **calendar_service** PG | backend, ticker_service | 1 min | Computed on demand |
| **ALERTS** |
| Alert Definition | **alert_service** PG | None | N/A | Direct API |
| Alert Event History | **alert_service** TimescaleDB | None | N/A | Write-only append |
| Notification Preference | **alert_service** PG | alert_service (memory) | 5 min | Direct API |

### API Ownership Matrix

| API Endpoint Pattern | Owner | Consumers | Auth Required | Authorization Method |
|----------------------|-------|-----------|---------------|---------------------|
| **AUTHENTICATION** |
| `/auth/register` | user_service | frontend | No | N/A (public) |
| `/auth/login` | user_service | frontend | No | Credentials in body |
| `/auth/google` | user_service | frontend | No | OAuth2 code flow |
| `/auth/mfa/*` | user_service | frontend | Session (partial) | Session token (pre-MFA) |
| `/auth/refresh` | user_service | frontend, backend | Yes | Refresh token (HttpOnly cookie) |
| `/auth/logout` | user_service | frontend | Yes | Access token |
| `/auth/sessions` | user_service | frontend | Yes | Access token + subject match |
| `/auth/password/*` | user_service | frontend | Varies | Magic link or access token |
| **AUTHORIZATION** |
| `/authz/check` | user_service | All services | Yes | Service account token or user token |
| `/authz/policies` | user_service | Admin UI | Yes | Admin role required |
| `/authz/evaluate` | user_service | backend | Yes | Service account token |
| **TOKENS & KEYS** |
| `/oauth/token` | user_service | frontend, services | Varies | OAuth2 client credentials or refresh |
| `/oauth/introspect` | user_service | All services | Yes | Service account token |
| `/jwks.json` | user_service | All services | No | N/A (public key endpoint) |
| `/keys/rotate` | user_service | Admin | Yes | Admin role + MFA |
| **USERS & PROFILES** |
| `/users/me` | user_service | frontend, backend | Yes | Access token |
| `/users/{id}` | user_service | backend, services | Yes | Token + authz check |
| `/users/{id}/preferences` | user_service | frontend, backend | Yes | Token + subject match or admin |
| `/users/search` | user_service | frontend, backend | Yes | Token + directory:read permission |
| `/users/{id}/deactivate` | user_service | Admin UI | Yes | Admin role + audit log |
| **TRADING ACCOUNTS** |
| `/trading-accounts` | user_service | frontend, ticker_service | Yes | Token + account ownership |
| `/trading-accounts/{id}/link` | user_service | frontend | Yes | Token + account ownership + MFA |
| `/trading-accounts/{id}/rotate-credentials` | user_service | Admin, frontend | Yes | Token + account ownership + MFA |
| `/trading-accounts/{id}/profile/sync` | user_service | Scheduled job | Yes | Service account token |
| `/trading-accounts/{id}/memberships` | user_service | frontend, ticker_service | Yes | Token + account ownership |
| `/trading-accounts/{id}/permissions/check` | user_service | ticker_service | Yes | Service account token |
| **DIRECTORY** |
| `/directory/users` | user_service | backend, frontend | Yes | Token + directory:read |
| `/directory/memberships` | user_service | ticker_service | Yes | Service account token |
| **AUDIT** |
| `/audit/events` | user_service | Admin, compliance | Yes | Admin or compliance role |
| `/audit/export` | user_service | Compliance | Yes | Compliance role + audit log |
| **WEBHOOKS** |
| `/events/webhooks` | user_service | - | Yes | Admin role |
| **API KEYS (legacy - backend)** |
| `/api-keys` | backend | frontend | Yes | API key or token |
| **MARKET DATA (ticker_service)** |
| `/subscriptions` | ticker_service | backend | Yes | API key or service token |
| `/history` | ticker_service | backend | Yes | API key or service token |
| `/orders` | ticker_service | backend | Yes | API key or service token (with trading_account check) |
| **INDICATORS (backend)** |
| `/indicators/*` | backend | frontend | Yes | API key or token |
| `/marks`, `/labels` | backend | frontend | Yes | API key or token (with user context) |
| **F&O DATA (backend)** |
| `/fo/stream` | backend | frontend | Yes | API key or token (WebSocket) |
| **CALENDAR (calendar_service via backend)** |
| `/calendar/*` | calendar_service | frontend, ticker, backend | No | Public (read); API key (admin write) |
| **ALERTS (alert_service)** |
| `/alerts` | alert_service | frontend | Yes | Token (with user_id extraction) |
| `/notifications/preferences` | alert_service | frontend | Yes | Token (with user_id extraction) |

### Critical "Never Do This" Rules

1. **Never store passwords or MFA seeds outside user_service vault/KMS**
   - No other service may store, hash, or validate passwords
   - No plaintext credentials in logs, database, or cache

2. **Never cache refresh tokens**
   - Only user_service Redis may store refresh token families
   - Services must never inspect or store refresh tokens

3. **Never implement auth logic in other services**
   - Token validation via `/oauth/introspect` or local JWT signature verification only
   - Authorization decisions via `/authz/check` only
   - No custom auth middleware beyond token extraction

4. **Never expose broker credentials**
   - Trading account credentials remain in user_service vault
   - ticker_service receives credentials only in-flight during order execution (via internal RPC)
   - No credentials in API responses (return only masked metadata)

5. **Never mutate identity data outside user_service**
   - Only user_service may create/update/delete users, roles, permissions
   - Other services may only cache with strict TTL and event-driven invalidation

6. **Never bypass audit logging**
   - All auth events (login, logout, permission changes) must be logged by user_service
   - Audit logs are immutable and retained per compliance policy

---

## 0.3 Integration Playbooks (Sequence Narratives)

### Playbook 1: User Login with Stay-Signed-In

**Scenario:** User logs in via frontend with "Remember Me" checked.

**Sequence:**
1. **Frontend → user_service**: `POST /auth/login`
   - Body: `{"email": "user@example.com", "password": "***", "persist_session": true, "device_fingerprint": "abc123"}`
   - Frontend includes device fingerprint (browser + IP hash)

2. **user_service Internal**:
   - Validate email/password against hashed credential in PG
   - Check rate limits (5 failed attempts → 15-min lockout)
   - Check if MFA required (user has TOTP enabled)
   - If MFA required, return `{"status": "mfa_required", "session_token": "temp_abc", "methods": ["totp"]}`

3. **Frontend → user_service** (if MFA required): `POST /auth/mfa/verify`
   - Body: `{"session_token": "temp_abc", "code": "123456"}`
   - user_service validates TOTP against seed in vault

4. **user_service Internal** (MFA passed):
   - Create session in Redis with:
     - `sid`: unique session ID
     - `user_id`, `device_fingerprint`, `ip`, `created_at`, `last_active_at`
     - TTL: 90 days (absolute max), 14 days inactivity window
   - Generate **refresh token family**:
     - Create `refresh_token_jti` (unique ID)
     - Store in Redis: `refresh_family:{jti}` → `{user_id, sid, parent_jti: null, issued_at, rotates_on_use: true}`
     - TTL: 90 days
   - Issue **access token** (JWT/PASETO):
     - Claims: `{sub: user_id, sid, scp: ["read", "trade"], roles: ["user"], acct_ids: [1,2], mfa: true, iat, exp: 15min, ver: 1}`
   - Issue **refresh token** as HttpOnly cookie:
     - Name: `__Secure-refresh_token`
     - Value: signed JWT with `{jti, sub, sid, exp: 90d}`
     - Flags: `HttpOnly, Secure, SameSite=Strict`

5. **user_service → Frontend**:
   - Response: `{"access_token": "eyJ...", "token_type": "Bearer", "expires_in": 900}`
   - Set-Cookie header with refresh token

6. **user_service → Event Bus** (Redis pub):
   - Publish: `user.session.created` → `{user_id, sid, device_fingerprint, ip, timestamp}`
   - alert_service listens and checks for anomalies (e.g., login from new country)

7. **Frontend**:
   - Store access token in memory (React state, not localStorage)
   - Use access token in `Authorization: Bearer <token>` header for all API calls
   - On access token expiry (15 min), automatically refresh

**Error Handling:**
- Invalid credentials → 401, increment rate limit counter
- MFA code invalid → 401, allow 3 attempts before invalidating session_token
- Device fingerprint mismatch on existing session → security event, require re-auth

**Idempotency:**
- Login is not idempotent (creates new session each time)
- If user already has active session, create new session (allow multiple devices)

**Rate Limits:**
- 5 login attempts per email per 15 minutes
- 3 MFA verification attempts per session_token

---

### Playbook 2: Token Refresh (Stay-Signed-In)

**Scenario:** Frontend's access token expires (15 min). Frontend automatically refreshes.

**Sequence:**
1. **Frontend → user_service**: `POST /auth/refresh`
   - Cookie: `__Secure-refresh_token=eyJ...` (sent automatically)
   - No body required

2. **user_service Internal**:
   - Extract refresh token from cookie
   - Validate JWT signature and expiration
   - Extract claims: `{jti, sub, sid, exp}`
   - Lookup `refresh_family:{jti}` in Redis
   - **Reuse Detection Check**:
     - If `refresh_family:{jti}` has `rotated_to` field → SECURITY VIOLATION
       - Invalidate entire family (all descendant tokens)
       - Revoke session `sid`
       - Log security event: `session.refresh_reuse_detected`
       - Return 401 (user must re-login)
     - If not found → token expired or invalid → 401
   - If valid and not reused:
     - Mark current token as rotated: `refresh_family:{jti}.rotated_to = new_jti`
     - Create new refresh token:
       - `new_jti` = generate UUID
       - `refresh_family:{new_jti}` → `{user_id: sub, sid, parent_jti: jti, issued_at, rotates_on_use: true}`
       - TTL: original expiration (not extended)
     - Update session `last_active_at` in Redis
     - Issue new access token (same claims structure, new `iat`, `exp`)
     - Issue new refresh token JWT

3. **user_service → Frontend**:
   - Response: `{"access_token": "eyJ...", "token_type": "Bearer", "expires_in": 900}`
   - Set-Cookie header with **new** refresh token (rotated)

4. **user_service → Event Bus** (Redis pub):
   - Publish: `user.session.refreshed` → `{user_id, sid, old_jti, new_jti, timestamp}`

5. **Frontend**:
   - Replace access token in memory
   - Continue making API calls

**Error Handling:**
- Refresh token expired → 401, redirect to login
- Refresh token reuse detected → 401, revoke session, force re-login, notify user via email
- Session invalidated (user logged out elsewhere) → 401, redirect to login

**Idempotency:**
- Refresh is **NOT** idempotent due to rotation
- Retry logic must include backoff and single in-flight refresh request

**Rate Limits:**
- 10 refresh requests per session per minute (prevents tight loops)

**Absolute Limits:**
- Session max lifetime: 90 days (even with refresh)
- Inactivity timeout: 14 days (no refresh → session expires)

---

### Playbook 3: Authorize Trading Action

**Scenario:** User attempts to place order via ticker_service. ticker_service validates permission.

**Sequence:**
1. **Frontend → backend**: `POST /orders`
   - Header: `Authorization: Bearer eyJ...`
   - Body: `{"trading_account_id": 123, "symbol": "NIFTY25300CE", "quantity": 50, "order_type": "LIMIT", "price": 125.0}`

2. **backend → ticker_service**: Forward request (internal)
   - Header: `Authorization: Bearer eyJ...` (pass through)
   - Body: same

3. **ticker_service Internal**:
   - Extract access token from header
   - Decode JWT claims (or call `/oauth/introspect` if opaque token):
     - Extract: `{sub: user_id, acct_ids: [1,2,3]}`
   - Check if `trading_account_id: 123` is in `acct_ids`
     - If not → Call user_service for explicit check

4. **ticker_service → user_service**: `POST /authz/check`
   - Body: `{"subject": "user_id", "action": "trade:place_order", "resource": "trading_account:123"}`
   - Header: `Authorization: Bearer <service_token>` (ticker_service's own service account token)

5. **user_service Internal**:
   - Lookup user's permissions for `trading_account:123`
   - Check:
     - User is owner OR member of shared account
     - Account has `can_trade: true` permission
     - Account is active (not deactivated)
     - No temporary suspension
   - Cache decision in Redis: `authz_decision:{user_id}:{acct:123}:trade:place_order` → `allow` (TTL: 1 min)
   - Return decision

6. **user_service → ticker_service**:
   - Response: `{"decision": "allow", "reason": "user is owner", "ttl": 60}`

7. **ticker_service Internal**:
   - Cache decision locally (1 min TTL)
   - Proceed with order placement
   - Call Kite API with trading account credentials (fetched from user_service internal RPC)

8. **ticker_service → Kite API**: Place order
   - Use credentials from user_service (never stored in ticker_service)

9. **ticker_service → user_service** (internal RPC): `POST /internal/trading-accounts/{id}/credentials`
   - Header: `Authorization: Bearer <service_token>`
   - Response: `{"api_key": "...", "api_secret": "...", "access_token": "..."}` (in-flight only, never cached)

10. **ticker_service → backend → Frontend**:
    - Response: `{"order_id": "abc", "status": "PENDING", ...}`

**Error Handling:**
- Token invalid → 401
- Authorization denied → 403 with reason: "insufficient permissions"
- Trading account not found → 404
- Kite API error → 502 with retry guidance

**Caching Strategy:**
- user_service caches authz decisions (1-5 min TTL)
- ticker_service caches authz decisions (1 min TTL)
- On permission change event (`permission.revoked`), invalidate cache immediately

**Rate Limits:**
- `/authz/check`: 1000 req/sec per service
- Credential fetch: 10 req/sec per trading account (credentials cached for 1 hour in user_service memory)

---

### Playbook 4: Link Trading Account

**Scenario:** User links a new Kite account to the platform.

**Sequence:**
1. **Frontend → user_service**: `POST /trading-accounts/link`
   - Header: `Authorization: Bearer eyJ...`
   - Body: `{"broker": "kite", "api_key": "...", "api_secret": "...", "totp_seed": "...", "username": "...", "password": "...", "nickname": "My Kite Account"}`
   - Frontend enforces MFA before allowing this action

2. **user_service Internal**:
   - Validate access token and extract `user_id`
   - Require MFA: Check token claims for `mfa: true` or enforce step-up auth
   - Create record in `trading_accounts` table:
     - `id`: auto-increment
     - `user_id`: from token
     - `broker`: "kite"
     - `nickname`: "My Kite Account"
     - `status`: "pending_verification"
     - `created_at`, `updated_at`
   - Store credentials in vault/KMS:
     - Use envelope encryption: per-account data key encrypted with master KMS key
     - Store: `{trading_account_id: 123, credentials: {api_key, api_secret, totp_seed, username, password_hash}, encrypted_with: "data_key_abc"}`
   - Generate data key: `data_key_abc` → Encrypt with KMS → Store wrapped key in DB

3. **user_service → Kite API** (connectivity test):
   - Attempt login using stored credentials
   - If TOTP required, generate code from `totp_seed`
   - Validate API key/secret
   - Fetch user profile: name, email, broker_user_id

4. **user_service Internal** (if validation succeeds):
   - Update `trading_accounts.status` → "active"
   - Store broker profile snapshot:
     - `{broker_user_id, broker_email, broker_name, linked_at}`
   - Issue access token for this account (optional for future multi-account flows)

5. **user_service → Event Bus** (Redis pub):
   - Publish: `trading_account.linked` → `{user_id, trading_account_id, broker, nickname, broker_profile: {name, email}, timestamp}`
   - ticker_service listens and updates its account registry
   - calendar_service listens and may annotate holidays with account-specific info

6. **user_service → Frontend**:
   - Response: `{"trading_account_id": 123, "status": "active", "nickname": "My Kite Account", "broker_profile": {"name": "John Doe"}}`

**Error Handling:**
- Invalid credentials → 400, status remains "pending_verification"
- Kite API timeout → 504, retry with exponential backoff (3 attempts)
- Duplicate account (same broker_user_id) → 409 conflict

**Security:**
- Credentials never returned in API responses (only masked: `api_key: "abc***xyz"`)
- Audit log: `trading_account.linked` event with IP, device, timestamp
- Rate limit: 5 linking attempts per user per hour

**Idempotency:**
- Include `Idempotency-Key: <UUID>` header
- user_service checks if account with same key was recently created → return existing

---

### Playbook 5: Broker Profile Sync (Scheduled)

**Scenario:** Periodic background job refreshes broker profiles for all active trading accounts.

**Sequence:**
1. **Scheduler (cron)** → user_service: `POST /admin/trading-accounts/sync-profiles`
   - Header: `Authorization: Bearer <admin_service_token>`
   - Body: `{"batch_size": 100}` (optional)

2. **user_service Internal**:
   - Query all active trading accounts with `last_sync < (now - 24h)` (1-day TTL)
   - Batch process: 100 accounts per run
   - For each account:
     - Fetch credentials from vault
     - Call Kite API: `GET /user/profile`
     - Compare with stored snapshot
     - If changed:
       - Update broker profile snapshot
       - Emit `trading_account.profile.synced` event

3. **user_service → Kite API** (per account):
   - Login with stored credentials (handle TOTP)
   - `GET /api/user/profile` → `{user_id, name, email, ...}`

4. **user_service Internal**:
   - Update `trading_accounts` table:
     - `broker_profile_snapshot` → new JSON
     - `last_synced_at` → now
   - Log: `trading_account.profile.synced` audit event

5. **user_service → Event Bus** (Redis pub):
   - Publish: `trading_account.profile.synced` → `{trading_account_id, user_id, broker_profile: {name, email, broker_user_id}, timestamp}`

6. **calendar_service** (event listener):
   - Receives event
   - Annotates calendar events with broker identity (e.g., "Diwali Muhurat Trading - available for Kite account 'My Kite Account'")
   - No secrets stored

7. **ticker_service** (event listener):
   - Receives event
   - Updates account metadata cache (name, status)
   - No credentials stored

**Error Handling:**
- Kite API rate limit (429) → exponential backoff, retry later
- Login failure (invalid credentials) → mark account `status: "credentials_expired"`, emit `trading_account.credentials.invalid`, notify user
- Network timeout → retry next sync cycle

**Idempotency:**
- Sync job is idempotent (safe to re-run)
- Use `last_synced_at` timestamp to prevent duplicate syncs

**Rate Limits:**
- 10 Kite API calls/sec (respecting broker limits)
- Batch processing to avoid overwhelming Kite API

**Observability:**
- Metrics: `sync_success_total`, `sync_failed_total`, `sync_duration_seconds`
- Alerts: >10% sync failures

---

### Playbook 6: Update User Preferences (Watchlist)

**Scenario:** User updates their default watchlist for NIFTY options.

**Sequence:**
1. **Frontend → user_service**: `PUT /users/me/preferences`
   - Header: `Authorization: Bearer eyJ...`
   - Body: `{"watchlist": {"nifty_options": ["NIFTY25300CE", "NIFTY25300PE", "NIFTY25350CE"]}, "default_trading_account_id": 123}`

2. **user_service Internal**:
   - Validate access token, extract `user_id`
   - Validate payload:
     - `watchlist`: JSON object
     - `default_trading_account_id`: must be owned by user
   - Update `user_preferences` table:
     - `user_id`, `watchlist`, `default_trading_account_id`, `updated_at`

3. **user_service → Event Bus** (Redis pub):
   - Publish: `user.preferences.updated` → `{user_id, preferences: {watchlist, default_trading_account_id}, timestamp}`

4. **ticker_service** (event listener):
   - Receives event
   - Invalidate cached preferences for `user_id`
   - On next user request, apply new watchlist (e.g., prioritize subscriptions for watchlist symbols)

5. **user_service → Frontend**:
   - Response: `{"preferences": {...}, "updated_at": "2025-11-03T10:00:00Z"}`

**Error Handling:**
- `default_trading_account_id` not owned by user → 403
- Invalid JSON schema → 400

**Caching:**
- user_service caches preferences in Redis (5 min TTL)
- ticker_service caches preferences (5 min TTL, invalidated on event)

**Idempotency:**
- Include `If-Match: <etag>` header for optimistic concurrency control
- user_service returns `ETag` in response

---

### Playbook 7: Security Alert on Anomaly

**Scenario:** user_service detects login from a new country, triggers alert.

**Sequence:**
1. **user_service** (during login flow):
   - Detect login from IP in new country (user previously logged in from India, now from US)
   - Create security event in `auth_events` table:
     - `event_type`: "login.new_country"
     - `user_id`, `ip`, `country`, `device_fingerprint`
   - Risk score: HIGH (threshold exceeded)

2. **user_service → Event Bus** (Redis pub):
   - Publish: `session.anomaly` → `{user_id, event_type: "login.new_country", risk_score: "high", ip, country, timestamp}`

3. **alert_service** (event listener):
   - Receives event
   - Check if user has security alert enabled (query `notification_preferences`)
   - If enabled:
     - Create alert: "Unusual login detected from United States"
     - Dispatch notification via Telegram

4. **alert_service → Telegram Bot API**:
   - Send message: "🚨 Security Alert: Login from new location (US). Was this you? If not, secure your account immediately."

5. **alert_service → user_service** (optional callback):
   - Report notification delivery status

6. **user_service Internal**:
   - Update `auth_events.notification_sent` → true

**Error Handling:**
- Telegram API failure → retry with exponential backoff (3 attempts)
- If all retries fail → log error, notify via fallback channel (email)

**Rate Limits:**
- Max 1 security alert per user per 15 minutes (prevent spam)

---

### Playbook 8: Calendar Annotation with Broker Identity

**Scenario:** calendar_service receives `trading_account.profile.synced` event and enriches calendar data.

**Sequence:**
1. **user_service → Event Bus**: Publish `trading_account.profile.synced` (from Playbook 5)

2. **calendar_service** (event listener):
   - Receives event: `{trading_account_id: 123, user_id: 456, broker_profile: {name: "John Doe"}, timestamp}`
   - Query calendar events for next 7 days
   - Annotate events with account context:
     - "Diwali Muhurat Trading (15:30-16:30) - Available for John Doe's Kite account"
   - Store annotation in `calendar_event_annotations` table:
     - `calendar_event_id`, `trading_account_id`, `annotation_text`, `created_at`

3. **Frontend → calendar_service** (via backend): `GET /calendar/events?trading_account_id=123`
   - Response includes annotations

**Security:**
- No credentials stored in calendar_service
- Only public profile data (name, nickname) used

**Data Flow:**
```
user_service (profile sync)
  → Event Bus
  → calendar_service (annotate)
  → frontend (display)
```

---

### Playbook 9: Deactivate User (GDPR/DPDP)

**Scenario:** Admin deactivates a user account, triggering cleanup across all services.

**Sequence:**
1. **Admin UI → user_service**: `POST /users/{user_id}/deactivate`
   - Header: `Authorization: Bearer <admin_token>`
   - Body: `{"reason": "user_request", "gdpr_export": true}`

2. **user_service Internal**:
   - Validate admin permissions
   - If `gdpr_export: true`:
     - Generate export of all user data (profile, preferences, audit logs, trading accounts metadata - NOT credentials)
     - Store export in S3/object storage
     - Return export URL (time-limited signed URL)
   - Update `users.status` → "deactivated"
   - Revoke all active sessions (delete from Redis)
   - Revoke all refresh tokens (delete families from Redis)
   - Mark all trading accounts as "deactivated"
   - Schedule data deletion (if required by policy): 30-day grace period

3. **user_service → Event Bus** (Redis pub):
   - Publish: `user.deactivated` → `{user_id, reason, timestamp}`

4. **All Services** (event listeners):
   - **ticker_service**: Remove cached user data, cancel any pending orders for user's trading accounts
   - **alert_service**: Delete user's alerts (or mark inactive), clear notification preferences
   - **backend**: Invalidate cached user data, revoke API keys
   - **calendar_service**: Remove user-specific annotations

5. **user_service → Admin UI**:
   - Response: `{"status": "deactivated", "export_url": "https://...", "data_deletion_scheduled": "2025-12-03"}`

**Error Handling:**
- User has pending orders → 409 conflict, require order cancellation first
- Export generation fails → retry async, notify admin when ready

**Audit:**
- Log `user.deactivated` event with admin user_id, reason, IP

**GDPR Compliance:**
- Pseudonymize data instead of hard delete (replace PII with hashed IDs)
- Retain audit logs (required for compliance) but redact PII
- Provide data export in machine-readable format (JSON)

---

## 0.4 Anti-Redundancy & Gap-Prevention Rules

### Anti-Redundancy Rules (Eliminate Duplication)

**Rule 1: Single Auth Source**
- ✅ **ONLY** user_service issues access tokens, refresh tokens, and validates credentials
- ❌ backend, ticker_service, alert_service, calendar_service **NEVER** implement login/password logic
- ❌ No service may store password hashes, MFA seeds, or refresh tokens except user_service

**Rule 2: Single AuthZ Decision Point**
- ✅ **ONLY** user_service evaluates authorization via `/authz/check`
- ❌ Other services may cache decisions (short TTL) but must defer to user_service for source of truth
- ❌ No service may implement custom permission checks (e.g., "is user admin?")

**Rule 3: Single User Registry**
- ✅ **ONLY** user_service stores user profiles, preferences, roles
- ❌ Other services may reference `user_id` but must fetch user data from user_service
- ❌ No "shadow" user tables (e.g., `alert_service.users`)

**Rule 4: Single Credential Vault**
- ✅ **ONLY** user_service stores trading account credentials (api_key, api_secret, TOTP, passwords)
- ❌ ticker_service receives credentials only in-flight via internal RPC (never cached or logged)
- ❌ No credentials in API responses, logs, or error messages

**Rule 5: Single Session Store**
- ✅ **ONLY** user_service manages sessions (creation, refresh, revocation)
- ❌ backend may validate tokens but must not create or refresh sessions
- ❌ No "pseudo-sessions" in other services (e.g., ticker_service storing user state)

**Rule 6: API Keys are Legacy, Not Primary**
- ✅ backend continues to manage **existing** API keys for backward compatibility
- ✅ user_service issues **new** auth via OAuth2/JWT tokens
- 🔄 **Migration Path**: Eventually migrate API keys to user_service-issued service tokens

### Gap-Prevention Rules (Ensure Coverage)

**Gap 1: User Identity Lifecycle**
- ✅ user_service owns: registration, email verification, login, logout, password reset, account deactivation
- ✅ No gaps: All identity states (pending, active, suspended, deactivated) managed

**Gap 2: MFA & Passwordless**
- ✅ user_service owns: TOTP, SMS OTP, magic links, WebAuthn (future)
- ✅ No gaps: All auth methods centrally managed

**Gap 3: OAuth & SSO**
- ✅ user_service owns: Google OAuth, future SAML/OIDC providers
- ✅ No gaps: External identity federation

**Gap 4: Trading Account Ownership**
- ✅ user_service owns: account linking, membership (sharing), permissions
- ✅ ticker_service implements: order execution, subscription management
- ✅ Clear boundary: user_service = "who can use account", ticker_service = "how to use account"

**Gap 5: Preferences**
- ✅ user_service owns: watchlists, timezone, default account, UI preferences
- ✅ ticker_service, alert_service **consume** preferences via events
- ✅ No gaps: All user settings in one place

**Gap 6: Audit & Compliance**
- ✅ user_service owns: auth audit logs (login, logout, permission changes)
- ✅ ticker_service owns: trading audit logs (orders, trades)
- ✅ alert_service owns: notification delivery logs
- ✅ No gaps: Comprehensive audit trail

**Gap 7: Event-Driven Sync**
- ✅ user_service publishes: `user.*`, `session.*`, `trading_account.*`, `permission.*`
- ✅ All services subscribe to relevant events
- ✅ No gaps: Services stay in sync via events, not polling

### Checklist for Every New Feature

Before implementing any new feature, confirm:

1. **Source of Truth**:
   - [ ] Which service owns this data?
   - [ ] Is there an existing SoT or does this create a new one?
   - [ ] Can this data be derived/cached instead of stored?

2. **API Owner**:
   - [ ] Which service exposes the endpoint?
   - [ ] Is there an existing endpoint that should be extended?
   - [ ] Does this duplicate an existing API?

3. **Event Producer**:
   - [ ] Should this state change emit an event?
   - [ ] What is the event schema and versioning?
   - [ ] Who are the consumers?

4. **Consumer Set**:
   - [ ] Which services need to react to this event?
   - [ ] Can consumers handle event loss/delay?
   - [ ] Are there ordering guarantees required?

5. **Cache TTLs**:
   - [ ] Can this data be cached?
   - [ ] What is the acceptable staleness?
   - [ ] How is cache invalidated (TTL, event, manual)?

6. **"Not My Job" Entries**:
   - [ ] What should this service explicitly **NOT** do?
   - [ ] Are there boundaries that might be blurred?
   - [ ] Document the "why" for each exclusion

---

## 0.5 SLAs/SLOs per Interface

### Service-Level Objectives (SLOs)

| Service | Endpoint Pattern | P50 Latency | P95 Latency | P99 Latency | Availability | Error Budget |
|---------|------------------|-------------|-------------|-------------|--------------|--------------|
| **user_service** |
| | `/auth/login` | <100ms | <250ms | <500ms | 99.9% | 0.1% (43 min/month) |
| | `/auth/refresh` | <50ms | <100ms | <200ms | 99.9% | 0.1% |
| | `/authz/check` | <20ms | <50ms | <100ms | 99.95% | 0.05% (cache-backed) |
| | `/oauth/introspect` | <30ms | <80ms | <150ms | 99.9% | 0.1% |
| | `/users/*` (CRUD) | <100ms | <200ms | <400ms | 99.9% | 0.1% |
| | `/trading-accounts/*/link` | <2s | <5s | <10s | 99.5% | 0.5% (external API) |
| | `/trading-accounts/*/profile/sync` | <2s | <5s | <10s | 99.5% | 0.5% (external API) |
| | `/audit/events` | <200ms | <500ms | <1s | 99.9% | 0.1% |
| **ticker_service** |
| | `/subscriptions` | <100ms | <200ms | <400ms | 99.9% | 0.1% |
| | `/history` | <500ms | <2s | <5s | 99.5% | 0.5% (external API) |
| | `/orders` (place) | <500ms | <1s | <3s | 99.9% | 0.1% (critical path) |
| **backend** |
| | `/fo/stream` (WebSocket) | <100ms | <200ms | <500ms | 99.9% | 0.1% |
| | `/indicators/*` | <200ms | <500ms | <1s | 99.5% | 0.5% (compute) |
| **alert_service** |
| | `/alerts` (CRUD) | <100ms | <200ms | <400ms | 99.9% | 0.1% |
| | Evaluation latency | <5s | <15s | <30s | 99.5% | 0.5% (background) |
| **calendar_service** |
| | `/calendar/status` | <10ms | <30ms | <50ms | 99.95% | 0.05% (cached) |
| | `/calendar/holidays` | <50ms | <100ms | <200ms | 99.9% | 0.1% |

### External Dependencies SLAs

| External Service | SLA | Fallback Strategy |
|-----------------|-----|-------------------|
| **Kite API** | No SLA (best-effort) | Cache last known state; mock data; circuit breaker |
| **Google OAuth** | 99.9% (Google-provided) | Fallback to email/password; retry with backoff |
| **Telegram Bot API** | 99% (Telegram-provided) | Queue notifications; retry; fallback to email |
| **PostgreSQL/TimescaleDB** | 99.95% (self-hosted) | Read replicas; connection pooling; circuit breaker |
| **Redis** | 99.95% (self-hosted) | Fallback to DB for critical paths; tolerate cache misses |

### Backoff & Retry Policies

**user_service → Kite API** (trading account linking/sync):
- Retry: 3 attempts
- Backoff: Exponential (1s, 2s, 4s)
- Circuit Breaker: Open after 5 consecutive failures, half-open after 30s
- Timeout: 10s per request

**ticker_service → user_service** (`/authz/check`):
- Retry: 2 attempts (fast fail)
- Backoff: Linear (100ms, 200ms)
- Circuit Breaker: Open after 10 failures in 1 min, half-open after 10s
- Timeout: 5s per request
- Fallback: Use cached decision (with warning log)

**alert_service → Telegram Bot API**:
- Retry: 3 attempts
- Backoff: Exponential (2s, 4s, 8s)
- Circuit Breaker: Open after 10 failures, half-open after 60s
- Timeout: 10s per request
- Fallback: Queue for later delivery; notify via email

**Backend → ticker_service** (`/subscriptions`):
- Retry: 3 attempts
- Backoff: Exponential (500ms, 1s, 2s)
- Circuit Breaker: Open after 5 failures, half-open after 15s
- Timeout: 30s per request
- Fallback: Return cached subscription state

### Rate Limits (Service-to-Service)

| Caller | Callee | Endpoint | Limit | Scope |
|--------|--------|----------|-------|-------|
| All services | user_service | `/authz/check` | 1000 req/sec | Per service (keyed by service_token) |
| All services | user_service | `/oauth/introspect` | 500 req/sec | Per service |
| ticker_service | user_service | `/trading-accounts/*/credentials` (internal) | 10 req/sec | Per trading account |
| Backend | ticker_service | `/subscriptions` | 100 req/sec | Global (backend aggregates) |
| alert_service | ticker_service | `/history` | 50 req/sec | Per alert (evaluation) |
| Frontend | backend | All endpoints | 100 req/sec | Per user (via API key or token) |

### Fallback Strategies

**user_service `/authz/check` unavailable**:
- Fallback: Use cached decision (1-5 min TTL)
- If no cache: DENY by default (fail-secure)
- Log: Warning with circuit breaker status

**user_service `/oauth/introspect` unavailable**:
- Fallback: Validate JWT locally (signature + exp check)
- Risk: No revocation check (acceptable for short TTL tokens)
- Alert: On prolonged unavailability

**Kite API unavailable** (order placement):
- Fallback: Queue order in ticker_service, retry when Kite recovers
- UI: Show "Order queued, will execute when market opens"
- Alert: Notify user if order delayed >5 min

**Redis unavailable** (cache miss):
- Fallback: Query TimescaleDB directly
- Performance: Slower but functional
- Alert: On prolonged Redis outage

---

## 0.6 Change Management & Versioning

### API Versioning Strategy

**Approach:** URL-based versioning for major breaking changes; additive changes without version bump.

**Rules:**
1. **Major Version** (breaking change): `/v1/auth/login` → `/v2/auth/login`
   - Examples: Remove field, change field type, change behavior
   - Support N-1 version for 6 months deprecation period

2. **Minor Version** (additive change): No version bump
   - Examples: Add optional field, add new endpoint
   - Backward compatible

3. **Deprecation Policy**:
   - Announce: 3 months in advance
   - Header: `Sunset: Sat, 01 Jun 2025 00:00:00 GMT` (RFC 8594)
   - Docs: Publish migration guide
   - Support: N-1 version for 6 months

**Example:**
- `POST /v1/auth/login` → Returns `{token, expires_in}`
- `POST /v2/auth/login` → Returns `{access_token, refresh_token, expires_in, user: {...}}`
- v1 deprecated 2025-06-01, EOL 2025-12-01

### Event Versioning

**Approach:** Event type suffix with version (`user.created@v1`, `user.created@v2`).

**Rules:**
1. **Additive Changes** (backward compatible):
   - Add new field → Same version
   - Consumers ignore unknown fields

2. **Breaking Changes**:
   - Publish new event type: `user.created@v2`
   - Continue publishing `@v1` for 6 months
   - Consumers migrate at their pace

3. **Schema Registry**:
   - Store event schemas in JSON Schema format
   - Validate events before publishing
   - Consumers fetch schema from `/events/schemas/{event_type}`

**Example:**
```json
// v1
{"type": "user.created@v1", "user_id": 123, "email": "user@example.com"}

// v2 (added name field)
{"type": "user.created@v2", "user_id": 123, "email": "user@example.com", "name": "John Doe"}
```

Consumers:
- Legacy consumers subscribe to `user.created@v1` (6 months)
- New consumers subscribe to `user.created@v2`

### Database Schema Migrations

**Approach:** Expand-contract pattern for zero-downtime.

**Steps:**
1. **Expand**: Add new column (nullable), deploy code that writes to both old and new
2. **Migrate**: Backfill data from old to new column
3. **Contract**: Deploy code that reads from new column only, drop old column

**Example:** Rename `trading_accounts.api_key` → `trading_accounts.broker_api_key`
1. Expand: `ALTER TABLE trading_accounts ADD COLUMN broker_api_key TEXT;`
2. Code: Write to both `api_key` and `broker_api_key`
3. Migrate: `UPDATE trading_accounts SET broker_api_key = api_key WHERE broker_api_key IS NULL;`
4. Contract: Deploy code reading only `broker_api_key`, then `ALTER TABLE trading_accounts DROP COLUMN api_key;`

### Service Contract Governance

**Contract-First Development:**
1. **Define** OpenAPI spec (REST) or AsyncAPI spec (events) **before** implementation
2. **Review** spec with consumers (API review meeting)
3. **Publish** spec to contract registry (e.g., Swagger UI, Redocly)
4. **Generate** client SDKs from spec
5. **Test** with contract tests (Pact, Spring Cloud Contract)

**Ownership:**
- Each service owns its OpenAPI spec (e.g., `user_service/openapi.yaml`)
- Specs versioned in Git
- Breaking changes require approval from architect

**Tooling:**
- OpenAPI validation: `openapi-spec-validator`
- Breaking change detection: `oasdiff`
- Client generation: `openapi-generator`

### Architecture Decision Records (ADRs)

**Purpose:** Document key architectural decisions with context and consequences.

**Format:** Markdown files in `/docs/adr/` directory.

**Template:**
```markdown
# ADR-001: Use JWT for Access Tokens

## Status
Accepted

## Context
Need to choose token format for user_service. Options: JWT, PASETO, opaque tokens.

## Decision
Use JWT (RS256) for access tokens because:
- Stateless validation (no DB lookup)
- Standard format (IETF RFC 7519)
- Library support (PyJWT, jose)

## Consequences
Positive:
- Fast validation (local signature check)
- Scalable (no central token store)

Negative:
- Cannot revoke before expiry (mitigate with short TTL + refresh)
- Token size larger than opaque (mitigate with selective claims)

## Alternatives Considered
- PASETO: More secure defaults but less ecosystem support
- Opaque: Requires introspection endpoint (latency/load)
```

**Index:** Maintain `docs/adr/README.md` with list of all ADRs.

### Boundary Decision ADRs (Required for user_service)

**ADR-010:** user_service Owns All Auth (Status: Accepted)
- **Context:** No existing auth system; need central identity provider
- **Decision:** user_service is single source of truth for identity, auth, authz
- **Boundary:** Other services delegate all auth to user_service

**ADR-011:** Credential Storage in Vault/KMS (Status: Accepted)
- **Context:** Trading account credentials must be encrypted at rest
- **Decision:** Use envelope encryption (per-account data keys + KMS master key)
- **Boundary:** Only user_service accesses vault; credentials never leave service

**ADR-012:** Refresh Token Rotation (Status: Accepted)
- **Context:** Need secure "stay signed in" without long-lived access tokens
- **Decision:** Implement refresh token families with rotation and reuse detection
- **Boundary:** user_service manages rotation; frontend never inspects refresh tokens

**ADR-013:** Authorization Model (RBAC + ABAC) (Status: Proposed)
- **Context:** Need flexible permission model for trading accounts (shared access, per-account roles)
- **Decision:** Hybrid RBAC (global roles) + ABAC (resource-level attributes)
- **Boundary:** user_service evaluates policies; services cache decisions

**ADR-014:** Event Bus = Redis Pub/Sub (Status: Accepted)
- **Context:** Existing infrastructure uses Redis; no Kafka/RabbitMQ
- **Decision:** Use Redis pub/sub for events (at-most-once delivery)
- **Boundary:** user_service publishes; consumers handle duplicates/loss via idempotency

**ADR-015:** API Keys as Legacy (Status: Accepted)
- **Context:** Backend has existing API key system; need migration path
- **Decision:** Keep API keys in backend for backward compat; new auth via user_service OAuth2/JWT
- **Boundary:** Backend API keys for machine clients only; user_service tokens for user auth

---

## Phase 0 Deliverables Summary

### Artifacts Produced

1. ✅ **Responsibility Matrix (0.1)**: RACI table mapping 50+ capabilities across 7 services
2. ✅ **Ownership Map (0.2)**:
   - Data ownership table (40+ domain objects)
   - API ownership table (50+ endpoint patterns)
   - "Never Do This" rules (6 critical boundaries)
3. ✅ **Integration Playbooks (0.3)**:
   - 9 detailed sequence narratives covering:
     - Login with stay-signed-in
     - Token refresh with rotation
     - Trading action authorization
     - Trading account linking
     - Broker profile sync
     - User preferences update
     - Security alert flow
     - Calendar annotation
     - User deactivation (GDPR)
4. ✅ **Anti-Redundancy & Gap-Prevention Rules (0.4)**:
   - 6 anti-redundancy rules
   - 7 gap-prevention rules
   - Feature checklist (6 validation steps)
5. ✅ **SLAs/SLOs per Interface (0.5)**:
   - Latency targets for 25+ endpoints
   - Availability targets per service
   - Backoff/retry policies for 5 integration patterns
   - Rate limits (service-to-service)
   - Fallback strategies
6. ✅ **Change Management & Versioning (0.6)**:
   - API versioning strategy (URL-based)
   - Event versioning strategy (type@version)
   - Database migration pattern (expand-contract)
   - Contract-first governance
   - ADR framework with 6 boundary decision examples

### Key Insights for Phase 1

**Critical Gaps Identified:**
- **NO** central identity/auth system → user_service is **essential**
- **NO** session management beyond API keys → user_service must provide robust session lifecycle
- **NO** OAuth/SSO → user_service must implement Google OAuth (and future providers)
- **NO** trading account credential management → user_service must own vault/KMS integration
- **NO** authorization PDP → user_service must provide `/authz/check` with caching

**Integration Points Defined:**
- user_service publishes 10+ event types (identity, session, trading account, permission)
- All services consume events via Redis pub/sub
- All services call `/authz/check` for authorization (with local caching)
- ticker_service receives trading account credentials via internal RPC only
- Backend remains API gateway but delegates all auth to user_service

**Boundaries Enforced:**
- user_service = identity, auth, authz, credentials, profiles, audit
- ticker_service = market data, subscriptions, orders, broker API integration
- alert_service = condition evaluation, notifications
- calendar_service = market hours, holidays
- backend = API gateway, data aggregation, WebSocket hubs, indicators
- frontend = UI only (no business logic)

**Technology Decisions:**
- Shared TimescaleDB (`stocksblitz_unified`)
- Shared Redis (user_service uses different DB number for isolation)
- JWT (RS256) for access tokens
- HttpOnly cookies for refresh tokens
- Envelope encryption (KMS) for credentials
- Redis pub/sub for events (at-most-once delivery)

---

## Next Steps (Phase 1 Preview)

With Phase 0 complete, Phase 1 will design the `user_service` implementation details:

1. **Detailed API Specifications** (OpenAPI):
   - 40+ endpoints with request/response schemas
   - Error codes, status codes, pagination
   - Rate limiting headers, idempotency keys

2. **Data Models** (PostgreSQL schemas):
   - `users`, `sessions`, `refresh_token_families`, `roles`, `policies`, `permissions`
   - `trading_accounts`, `trading_account_memberships`, `credential_vault_refs`
   - `auth_events` (TimescaleDB hypertable)
   - Indexes, constraints, partitioning

3. **Event Schemas** (AsyncAPI):
   - JSON schemas for all 10+ event types
   - Versioning, delivery guarantees, retry semantics

4. **Security Architecture**:
   - KMS integration (AWS KMS, HashiCorp Vault, or local)
   - Envelope encryption implementation
   - Token signing key rotation
   - Threat model (STRIDE)

5. **Infrastructure Configuration**:
   - Docker Compose integration
   - Environment variables (50+ config parameters)
   - TimescaleDB extensions, hypertables, retention policies
   - Redis keyspace design

6. **Observability**:
   - Prometheus metrics (20+ custom metrics)
   - Structured logging (auth events, errors, performance)
   - Health check endpoints
   - Alerting rules

7. **Deployment & Rollout**:
   - Staging → canary → production
   - Feature flags for OAuth providers
   - Migration plan (seed admin user, backfill broker profiles)
   - Zero-downtime deployment strategy

---

**Phase 0 Status: ✅ COMPLETE**

This analysis provides the foundation for user_service design with guaranteed:
- **Zero overlap**: No redundant auth/identity logic in other services
- **No gaps**: All identity, auth, authz, credential, audit capabilities covered
- **Clear contracts**: API ownership, data ownership, event flows defined
- **Pragmatic SLAs**: Latency, availability, retry policies realistic for trading platform

**Ready for Phase 1 design.**

---

*End of Phase 0 Analysis Document*
