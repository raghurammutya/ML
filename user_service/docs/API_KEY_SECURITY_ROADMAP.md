# API Key Security Roadmap

**Created:** 2025-11-09
**Owner:** User Service Team
**Status:** APPROVED

---

## Executive Summary

This document outlines the phased approach to API key authentication and security for the trading platform. We balance **speed to market** with **production-grade security** through a three-phase implementation.

**Timeline:**
- **Phase 1 (Sprint 1):** Basic API Keys - Week 1
- **Phase 1.5 (Sprint 1.5):** HMAC Request Signing - Week 2
- **Phase 2 (Sprint 6):** OAuth 2.0 Client Credentials - Week 7-8

**Security Levels:**
- Phase 1: ⭐⭐⭐ Medium (Good for MVP/Beta)
- Phase 1.5: ⭐⭐⭐⭐ High (Production-ready)
- Phase 2: ⭐⭐⭐⭐⭐ Very High (Enterprise-grade)

---

## 🎯 Phase 1: Basic API Keys (Sprint 1)

**Timeline:** Week 1 (Current)
**Security Level:** ⭐⭐⭐ Medium
**Status:** IN PROGRESS

### What We're Building

```python
# User generates API key
POST /v1/api-keys
{
  "name": "Production Bot",
  "scopes": ["read", "trade"],
  "ip_whitelist": ["1.2.3.4"],
  "rate_limit_tier": "standard",
  "expires_in_days": 90
}

Response:
{
  "api_key": "sb_30d4d5ea_bbb52c64cc4eb2536fdd7b44861c93e4b30b50c6",
  "key_prefix": "sb_30d4d5ea",
  "scopes": ["read", "trade"],
  "expires_at": "2026-02-07T..."
}

# Client uses API key
GET /api/instruments/NIFTY50
X-API-Key: sb_30d4d5ea_bbb52c64cc4eb2536fdd7b44861c93e4b30b50c6

# Or
Authorization: Bearer sb_30d4d5ea_bbb52c64cc4eb2536fdd7b44861c93e4b30b50c6
```

### Security Features

1. **SHA-256 Hashing** ✅
   - Secrets hashed in database
   - Full key returned only once at creation
   - Cannot retrieve secret later

2. **Scope-Based Authorization** ✅
   ```python
   Scopes:
   - "read" - View data only
   - "trade" - Place/cancel orders
   - "admin" - Full access
   - "account:manage" - Manage trading accounts
   - "strategy:execute" - Execute strategies
   - "*" - All permissions
   ```

3. **IP Whitelisting** ✅
   ```python
   ip_whitelist: ["1.2.3.4", "5.6.7.8"]
   # Key only works from these IPs
   # null = works from any IP
   ```

4. **Rate Limiting** ✅
   ```python
   Tiers:
   - free: 100 requests/hour
   - standard: 1,000 requests/hour
   - premium: 10,000 requests/hour
   - unlimited: No limit
   ```

5. **Expiration** ✅
   ```python
   expires_in_days: 90  # Max 10 years
   # Key automatically invalid after expiration
   # Recommended: 30-90 days for production
   ```

6. **Revocation** ✅
   ```python
   DELETE /v1/api-keys/{key_id}?reason="Security incident"
   # Immediate revocation
   # Audit trail maintained
   ```

7. **Usage Tracking** ✅
   ```python
   # Every API call logged:
   - Endpoint, method, status code
   - Response time
   - IP address, user agent
   - Timestamp
   # TimescaleDB hypertable for analytics
   ```

### Database Schema

```sql
-- API Keys table
CREATE TABLE api_keys (
    api_key_id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(user_id),
    key_prefix VARCHAR(20) UNIQUE,  -- "sb_30d4d5ea"
    key_hash VARCHAR(255),           -- SHA-256 of secret
    name VARCHAR(255),
    scopes JSONB,
    ip_whitelist JSONB,
    rate_limit_tier VARCHAR(50),
    last_used_at TIMESTAMP,
    usage_count BIGINT,
    expires_at TIMESTAMP,
    created_at TIMESTAMP,
    revoked_at TIMESTAMP,
    revoked_reason TEXT
);

-- Usage logs (TimescaleDB hypertable)
CREATE TABLE api_key_usage_logs (
    log_id BIGSERIAL PRIMARY KEY,
    api_key_id BIGINT,
    endpoint VARCHAR(255),
    method VARCHAR(10),
    status_code INTEGER,
    response_time_ms INTEGER,
    ip_address VARCHAR(45),
    timestamp TIMESTAMP
);

SELECT create_hypertable('api_key_usage_logs', 'timestamp');
```

### Key Format

```
Format: sb_{prefix}_{secret}

Example: sb_30d4d5ea_bbb52c64cc4eb2536fdd7b44861c93e4b30b50c6

Components:
- "sb" = StocksBlitz
- "30d4d5ea" = 8-char hex prefix (4 bytes random)
- "bbb5...0c6" = 40-char hex secret (20 bytes random)

Entropy:
- Prefix: 2^32 = 4.3 billion combinations
- Secret: 2^160 = 1.46 × 10^48 combinations
- Total: Cryptographically secure
```

### Security Boundaries

**✅ Protects Against:**
- Brute force attacks (high entropy)
- Unauthorized access (authentication required)
- Privilege escalation (scope enforcement)
- Abuse (rate limiting)
- Long-term compromise (expiration)
- IP-based attacks (IP whitelist)

**❌ Does NOT Protect Against:**
- Key leakage in logs/code (developer responsibility)
- Replay attacks (same key works forever until expired)
- Man-in-the-middle (requires HTTPS enforcement)
- Stolen keys being useful (until revoked/expired)

### Acceptable Use Cases

**✅ Good For:**
- Development and testing
- Internal tools and scripts
- MVP/Beta launch with limited users
- Low-value operations
- Trusted environments

**❌ Not Recommended For (without Phase 1.5):**
- Public production APIs with real money
- Third-party integrations
- Untrusted client applications
- High-value automated trading
- Regulatory compliance requirements (PCI DSS, SOC 2)

### Required Security Practices

**MANDATORY:**
1. **HTTPS Only** - Never use over HTTP
2. **Environment Variables** - Never hardcode in source
3. **Secret Scanning** - Enable GitHub secret scanning
4. **Short Expiration** - Default 30-90 days, max 1 year
5. **Minimal Scopes** - Grant only required permissions
6. **IP Whitelist** - Always specify when possible
7. **Monitoring** - Alert on unusual usage patterns
8. **Rotation** - Rotate every 90 days minimum

**RECOMMENDED:**
9. **Secrets Manager** - Store in AWS Secrets Manager/Vault
10. **Audit Logs** - Review usage logs weekly
11. **Anomaly Detection** - Alert on spikes in usage
12. **Key Inventory** - Maintain spreadsheet of all keys

### Implementation Checklist

- [x] Database migration (api_keys table)
- [x] Database model (ApiKey, ApiKeyUsageLog)
- [ ] Service layer (ApiKeyService)
- [ ] Authentication middleware (verify_api_key)
- [ ] API endpoints (CRUD operations)
- [ ] Schemas (Pydantic models)
- [ ] Unit tests
- [ ] Integration tests
- [ ] SDK compatibility testing
- [ ] Documentation

---

## 🔐 Phase 1.5: HMAC Request Signing (Sprint 1.5)

**Timeline:** Week 2
**Security Level:** ⭐⭐⭐⭐ High
**Status:** PLANNED

### Why HMAC Signing?

**Problem with Phase 1:**
```
Attacker intercepts request:
GET /api/orders
X-API-Key: sb_30d4d5ea_bbb52c64cc4eb2536fdd7b44861c93e4b30b50c6

Attacker can:
1. Replay this exact request (replay attack)
2. Use the key forever (until revoked)
3. Modify the request (if HTTPS is compromised)
```

**Solution: HMAC Signing**
```
Attacker intercepts request:
GET /api/orders
X-API-Key: sb_30d4d5ea
X-Timestamp: 1699564800
X-Signature: a7f3c2d1e5b9...

Attacker CANNOT:
1. Replay (timestamp validation)
2. Modify request (signature breaks)
3. Use key without secret (secret never transmitted)
```

### How It Works

#### Step 1: Client Generates Signature

```python
import hmac
import hashlib
import time

# Components
api_key_id = "sb_30d4d5ea"  # Public prefix
api_key_secret = "bbb52c64cc4eb2536fdd7b44861c93e4b30b50c6"  # Private

# Request details
timestamp = str(int(time.time()))
method = "POST"
path = "/api/orders"
body = '{"symbol":"NIFTY50","qty":50,"side":"BUY"}'

# Create signature payload
payload = f"{timestamp}|{method}|{path}|{body}"

# Calculate HMAC-SHA256 signature
signature = hmac.new(
    api_key_secret.encode('utf-8'),
    payload.encode('utf-8'),
    hashlib.sha256
).hexdigest()

# Send request
headers = {
    "X-API-Key": api_key_id,
    "X-Timestamp": timestamp,
    "X-Signature": signature,
    "Content-Type": "application/json"
}

response = requests.post(
    "https://api.stocksblitz.com/api/orders",
    headers=headers,
    data=body
)
```

#### Step 2: Server Validates Signature

```python
from datetime import datetime, timedelta
import hmac
import hashlib

def validate_hmac_signature(request):
    # Extract headers
    api_key_id = request.headers.get("X-API-Key")
    timestamp = request.headers.get("X-Timestamp")
    signature = request.headers.get("X-Signature")

    if not all([api_key_id, timestamp, signature]):
        raise AuthenticationError("Missing required headers")

    # 1. Validate timestamp (5-minute window)
    request_time = datetime.fromtimestamp(int(timestamp))
    current_time = datetime.utcnow()

    if abs((current_time - request_time).total_seconds()) > 300:
        raise AuthenticationError("Request timestamp too old or too far in future")

    # 2. Lookup API key by ID
    api_key = db.query(ApiKey).filter(
        ApiKey.key_prefix == api_key_id,
        ApiKey.revoked_at.is_(None),
        or_(ApiKey.expires_at.is_(None), ApiKey.expires_at > current_time)
    ).first()

    if not api_key:
        raise AuthenticationError("Invalid API key")

    # 3. Reconstruct signature payload
    method = request.method
    path = request.path
    body = request.body.decode('utf-8') if request.body else ""

    payload = f"{timestamp}|{method}|{path}|{body}"

    # 4. Calculate expected signature using stored secret
    # Note: api_key.key_hash is SHA-256 of secret, we need to store secret separately
    #       OR derive secret from key_hash (not possible with SHA-256)
    #       SOLUTION: Store encrypted secret, decrypt for HMAC

    expected_signature = hmac.new(
        api_key.secret.encode('utf-8'),  # Encrypted secret, decrypted here
        payload.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

    # 5. Compare signatures (constant-time comparison)
    if not hmac.compare_digest(signature, expected_signature):
        raise AuthenticationError("Invalid signature")

    # 6. Check for replay attack (optional: store used signatures with TTL)
    replay_key = f"hmac_signature:{signature}"
    if redis.exists(replay_key):
        raise AuthenticationError("Signature already used (replay attack detected)")

    # Store signature for 5 minutes (prevent replay)
    redis.setex(replay_key, 300, "used")

    return api_key.user
```

### Database Schema Changes

```sql
-- Add encrypted secret storage
ALTER TABLE api_keys ADD COLUMN secret_encrypted TEXT;
-- Store AES-256 encrypted secret (for HMAC signing)
-- Keep key_hash for backward compatibility

-- Add nonce/replay protection tracking (optional)
-- Use Redis instead for better performance
```

### Implementation Changes

**Files to Modify:**

1. **app/models/api_key.py**
   ```python
   class ApiKey(Base):
       # Add field
       secret_encrypted = Column(Text, nullable=True)
   ```

2. **app/services/api_key_service.py**
   ```python
   def generate_api_key():
       # Store both hash (for basic auth) and encrypted secret (for HMAC)
       api_key.key_hash = hash_secret(secret)
       api_key.secret_encrypted = encrypt_secret(secret)  # AES-256

   def decrypt_secret(api_key):
       # Decrypt secret for HMAC validation
       return aes_decrypt(api_key.secret_encrypted)
   ```

3. **app/api/dependencies.py**
   ```python
   async def get_current_user_from_api_key(request: Request):
       # Check if HMAC headers present
       if "X-Signature" in request.headers:
           return await validate_hmac_signature(request)
       else:
           # Fallback to basic API key auth
           return await validate_basic_api_key(request)
   ```

4. **app/utils/hmac_auth.py** (NEW)
   ```python
   def validate_hmac_signature(request):
       # Implementation from above
   ```

5. **Python SDK Update**
   ```python
   # python-sdk/stocksblitz/api.py

   class APIClient:
       def __init__(self, api_key=None, use_hmac=True):
           self.api_key = api_key
           self.use_hmac = use_hmac

           if api_key and use_hmac:
               parts = api_key.split("_")
               self.api_key_id = f"sb_{parts[1]}"
               self.api_key_secret = parts[2]

       def _sign_request(self, method, path, body):
           if not self.use_hmac:
               return {}

           timestamp = str(int(time.time()))
           payload = f"{timestamp}|{method}|{path}|{body or ''}"
           signature = hmac.new(
               self.api_key_secret.encode(),
               payload.encode(),
               hashlib.sha256
           ).hexdigest()

           return {
               "X-API-Key": self.api_key_id,
               "X-Timestamp": timestamp,
               "X-Signature": signature
           }

       def get(self, endpoint):
           headers = self._sign_request("GET", endpoint, None)
           # ... rest of implementation
   ```

### Security Improvements

**✅ NEW Protections:**
- ✅ Replay attack prevention (timestamp + signature storage)
- ✅ Request tampering detection (signature validation)
- ✅ Secret never transmitted (only signature)
- ✅ Time-bound requests (5-minute window)

**✅ Maintains Previous Protections:**
- ✅ Scope enforcement
- ✅ IP whitelisting
- ✅ Rate limiting
- ✅ Expiration
- ✅ Revocation

### Acceptable Use Cases

**✅ Good For:**
- Production APIs with real money
- Public-facing APIs
- Third-party integrations
- Automated trading systems
- Compliance requirements (SOC 2, ISO 27001)

**❌ Still Not Recommended For:**
- PCI DSS Level 1 compliance (need OAuth 2.0)
- Extremely high-security environments (need mTLS)
- Multi-tenant SaaS with complex auth (need OAuth 2.0)

### Migration Plan

**Backward Compatibility:**
```python
# Support both old and new clients
if "X-Signature" in request.headers:
    # New HMAC auth
    user = validate_hmac_signature(request)
else:
    # Old basic auth (deprecated but still works)
    user = validate_basic_api_key(request)

    # Log deprecation warning
    logger.warning(f"API key {key_prefix} using deprecated basic auth")
```

**Deprecation Timeline:**
- Week 2: Launch HMAC support
- Week 3-4: Notify users to upgrade
- Week 5: Mark basic auth as deprecated
- Week 8: Disable basic auth for new keys
- Week 12: Disable basic auth entirely

---

## 🏢 Phase 2: OAuth 2.0 Client Credentials (Sprint 6)

**Timeline:** Week 7-8
**Security Level:** ⭐⭐⭐⭐⭐ Very High
**Status:** PLANNED

### Why OAuth 2.0?

**Industry Standard:**
- Used by Google, Microsoft, GitHub, Stripe, AWS, etc.
- Well-documented, well-understood
- Extensive library support
- Compliance-friendly (PCI DSS, SOC 2, GDPR)

**Enterprise Requirements:**
- Multi-tenant support
- Fine-grained scopes
- Token lifecycle management
- Delegation and impersonation
- Third-party app authorization

### How It Works

#### OAuth 2.0 Client Credentials Flow

```
Client                                    Server
  |                                         |
  |-- POST /oauth/token ------------------>|
  |   grant_type=client_credentials        |
  |   client_id=my_app                     |
  |   client_secret=secret123              |
  |   scope=read trade                     |
  |                                         |
  |<-- 200 OK ---------------------------- |
  |   {                                     |
  |     "access_token": "eyJhbGc...",      |
  |     "token_type": "Bearer",            |
  |     "expires_in": 3600,                |
  |     "scope": "read trade"              |
  |   }                                     |
  |                                         |
  |-- GET /api/orders -------------------->|
  |   Authorization: Bearer eyJhbGc...     |
  |                                         |
  |<-- 200 OK ----------------------------- |
  |   [orders...]                           |
  |                                         |
  |                                         |
  [Access token expires after 1 hour]      |
  |                                         |
  |-- POST /oauth/token ------------------>|
  |   grant_type=client_credentials        |
  |   (Request new token)                  |
  |                                         |
```

### Implementation

#### Database Schema

```sql
-- OAuth clients table
CREATE TABLE oauth_clients (
    client_id VARCHAR(100) PRIMARY KEY,
    client_secret_hash VARCHAR(255),
    user_id BIGINT REFERENCES users(user_id),
    name VARCHAR(255),
    description TEXT,
    scopes JSONB,
    redirect_uris JSONB,  -- For future authorization code flow
    grant_types JSONB DEFAULT '["client_credentials"]',
    created_at TIMESTAMP,
    revoked_at TIMESTAMP
);

-- OAuth tokens table (short-lived)
CREATE TABLE oauth_access_tokens (
    token_id VARCHAR(50) PRIMARY KEY,
    client_id VARCHAR(100) REFERENCES oauth_clients(client_id),
    user_id BIGINT REFERENCES users(user_id),
    token_hash VARCHAR(255),  -- SHA-256 of token
    scopes JSONB,
    expires_at TIMESTAMP,
    created_at TIMESTAMP,
    revoked_at TIMESTAMP
);

-- Index for cleanup
CREATE INDEX idx_oauth_tokens_expires ON oauth_access_tokens(expires_at);
```

#### Endpoints

**1. Token Endpoint**

```python
@router.post("/oauth/token")
async def token(
    grant_type: str = Form(...),
    client_id: str = Form(...),
    client_secret: str = Form(...),
    scope: str = Form(None)
):
    """
    OAuth 2.0 Token Endpoint

    Supports:
    - grant_type=client_credentials (service-to-service)
    - grant_type=refresh_token (future)
    """
    if grant_type != "client_credentials":
        raise HTTPException(400, "unsupported_grant_type")

    # Validate client credentials
    client = db.query(OAuthClient).filter(
        OAuthClient.client_id == client_id,
        OAuthClient.revoked_at.is_(None)
    ).first()

    if not client:
        raise HTTPException(401, "invalid_client")

    # Verify client secret
    secret_hash = hashlib.sha256(client_secret.encode()).hexdigest()
    if not hmac.compare_digest(secret_hash, client.client_secret_hash):
        raise HTTPException(401, "invalid_client")

    # Validate scopes
    requested_scopes = scope.split() if scope else ["read"]
    if not all(s in client.scopes for s in requested_scopes):
        raise HTTPException(400, "invalid_scope")

    # Generate access token (JWT)
    access_token = jwt.encode({
        "sub": str(client.user_id),
        "client_id": client_id,
        "scope": requested_scopes,
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,  # 1 hour
        "jti": str(uuid.uuid4())  # Token ID
    }, private_key, algorithm="RS256")

    # Store token (for revocation)
    token_record = OAuthAccessToken(
        token_id=access_token["jti"],
        client_id=client_id,
        user_id=client.user_id,
        token_hash=hashlib.sha256(access_token.encode()).hexdigest(),
        scopes=requested_scopes,
        expires_at=datetime.utcnow() + timedelta(hours=1)
    )
    db.add(token_record)
    db.commit()

    return {
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": 3600,
        "scope": " ".join(requested_scopes)
    }
```

**2. Client Management Endpoints**

```python
# Create OAuth client
POST /v1/oauth/clients
{
  "name": "Production Trading Bot",
  "scopes": ["read", "trade"],
  "grant_types": ["client_credentials"]
}

Response:
{
  "client_id": "sb_client_30d4d5ea",
  "client_secret": "cs_bbb52c64cc4eb2536fdd7b44861c93e4b30b50c6",
  "name": "Production Trading Bot",
  "scopes": ["read", "trade"]
}

# List clients
GET /v1/oauth/clients

# Revoke client
DELETE /v1/oauth/clients/{client_id}

# Rotate client secret
POST /v1/oauth/clients/{client_id}/rotate-secret
```

**3. Token Revocation**

```python
@router.post("/oauth/revoke")
async def revoke_token(
    token: str = Form(...),
    token_type_hint: str = Form(None)
):
    """
    OAuth 2.0 Token Revocation (RFC 7009)
    """
    # Hash token
    token_hash = hashlib.sha256(token.encode()).hexdigest()

    # Find and revoke
    token_record = db.query(OAuthAccessToken).filter(
        OAuthAccessToken.token_hash == token_hash
    ).first()

    if token_record:
        token_record.revoked_at = datetime.utcnow()
        db.commit()

    # Always return 200 (don't leak info)
    return {"status": "ok"}
```

#### SDK Integration

```python
# Python SDK
from stocksblitz import TradingClient

# Option 1: Automatic token management
client = TradingClient.from_oauth(
    api_url="https://api.stocksblitz.com",
    token_url="https://auth.stocksblitz.com/oauth/token",
    client_id="sb_client_30d4d5ea",
    client_secret="cs_bbb52c64..."
)

# SDK automatically:
# 1. Exchanges credentials for access token
# 2. Includes token in requests
# 3. Refreshes token when expired

# Option 2: Manual token management
client = TradingClient(
    api_url="https://api.stocksblitz.com",
    access_token="eyJhbGc..."
)
```

### Security Features

**✅ Short-Lived Tokens:**
```python
Access Token: 1 hour (configurable: 15min - 24hr)
- If stolen, only valid for 1 hour
- Must re-authenticate after expiry
- No long-lived credentials in flight
```

**✅ Scope Granularity:**
```python
Scopes can be hierarchical:
- "read" - Read all resources
- "read:orders" - Read orders only
- "read:positions" - Read positions only
- "trade" - Execute trades
- "trade:options" - Trade options only
- "admin" - Full access
```

**✅ Token Revocation:**
```python
# Revoke specific token
POST /oauth/revoke
token=eyJhbGc...

# Revoke all tokens for client
DELETE /v1/oauth/clients/{client_id}

# Token blacklist in Redis
- Store revoked token JTIs
- Check on every request
- Expire after token TTL
```

**✅ Audit Trail:**
```python
# Every token issuance logged
{
  "event": "oauth.token.issued",
  "client_id": "sb_client_30d4d5ea",
  "user_id": 123,
  "scopes": ["read", "trade"],
  "ip": "1.2.3.4",
  "timestamp": "2025-11-09T..."
}

# Every token usage logged
{
  "event": "oauth.token.used",
  "token_id": "jti_abc123",
  "endpoint": "/api/orders",
  "ip": "1.2.3.4",
  "timestamp": "2025-11-09T..."
}
```

### Advanced Features

**1. Token Introspection (RFC 7662)**

```python
POST /oauth/introspect
token=eyJhbGc...

Response:
{
  "active": true,
  "scope": "read trade",
  "client_id": "sb_client_30d4d5ea",
  "username": "user@example.com",
  "exp": 1699568400
}
```

**2. Dynamic Client Registration (RFC 7591)**

```python
# Allow third-party apps to register
POST /oauth/register
{
  "client_name": "Third Party App",
  "redirect_uris": ["https://app.example.com/callback"],
  "grant_types": ["authorization_code"],
  "scope": "read"
}

# Returns client_id and client_secret
```

**3. JWT Token Structure**

```json
{
  "header": {
    "alg": "RS256",
    "typ": "JWT",
    "kid": "default"
  },
  "payload": {
    "sub": "123",
    "client_id": "sb_client_30d4d5ea",
    "scope": ["read", "trade"],
    "iat": 1699564800,
    "exp": 1699568400,
    "jti": "token_abc123",
    "iss": "https://auth.stocksblitz.com",
    "aud": "https://api.stocksblitz.com"
  },
  "signature": "..."
}
```

### Migration from Phase 1.5

**Dual Support:**

```python
# Support both API keys and OAuth tokens
async def authenticate(request: Request):
    auth_header = request.headers.get("Authorization", "")

    if auth_header.startswith("Bearer eyJ"):
        # OAuth 2.0 JWT token
        return validate_oauth_token(auth_header)

    elif auth_header.startswith("Bearer sb_"):
        # API key (Phase 1)
        return validate_api_key(auth_header)

    elif "X-API-Key" in request.headers:
        # API key with HMAC (Phase 1.5)
        return validate_hmac_api_key(request)

    else:
        raise HTTPException(401, "Authentication required")
```

**Deprecation Timeline:**
- Week 7-8: Launch OAuth 2.0
- Week 9-12: Run dual mode (OAuth + API keys)
- Week 13: Deprecate API keys for new integrations
- Week 16: Encourage migration of existing API keys
- Week 20: Optional: Disable API keys entirely

### Compliance Benefits

**PCI DSS 4.0:**
- ✅ Short-lived credentials
- ✅ Cryptographic authentication
- ✅ Auditability
- ✅ Revocation capabilities

**SOC 2:**
- ✅ Access control
- ✅ Logging and monitoring
- ✅ Encryption in transit and at rest
- ✅ Incident response (revocation)

**GDPR:**
- ✅ Data minimization (scoped access)
- ✅ Right to revoke (token/client revocation)
- ✅ Audit trail (compliance reporting)

---

## 📊 Comparison Matrix

| Feature | Phase 1 (Basic) | Phase 1.5 (HMAC) | Phase 2 (OAuth) |
|---------|----------------|------------------|-----------------|
| **Security Level** | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| **Implementation Time** | 1 week | +1 day | +1 week |
| **Complexity** | Low | Medium | High |
| **Replay Protection** | ❌ | ✅ | ✅ |
| **Token Expiry** | 90 days | 90 days | 1 hour |
| **Secret in Transit** | ✅ (risky) | ❌ | ❌ |
| **Industry Standard** | ❌ | Partial | ✅ |
| **Compliance Ready** | ❌ | Partial | ✅ |
| **Third-Party Support** | Limited | Limited | Extensive |
| **Multi-Tenant** | ❌ | ❌ | ✅ |
| **Fine-Grained Scopes** | Basic | Basic | Advanced |
| **Automatic Rotation** | ❌ | ❌ | ✅ |
| **Library Support** | Custom | Custom | Extensive |

---

## 🚀 Rollout Strategy

### Week 1: Phase 1 (Sprint 1)
```
Monday-Wednesday: Implementation
- Database migration
- Service layer
- API endpoints
- Authentication middleware

Thursday: Testing
- Unit tests
- Integration tests
- SDK compatibility

Friday: Documentation & Deploy
- Update docs
- Deploy to dev environment
- Manual testing
```

### Week 2: Phase 1.5 (Sprint 1.5)
```
Monday: Planning & Design
- Review HMAC implementation
- Design secret encryption strategy
- Plan SDK changes

Tuesday-Wednesday: Implementation
- Update database schema
- Implement HMAC validation
- Update SDK with signing

Thursday: Testing
- Test HMAC flow
- Test backward compatibility
- Performance testing

Friday: Deploy & Migration
- Deploy to production
- Notify users of new auth method
- Provide migration guide
```

### Week 7-8: Phase 2 (Sprint 6)
```
Week 7:
Monday-Tuesday: OAuth Server Setup
- Implement token endpoint
- Implement client management
- Database schema

Wednesday-Thursday: Token Validation
- JWT validation
- Scope enforcement
- Token revocation

Friday: Testing
- Unit tests
- Integration tests

Week 8:
Monday-Tuesday: SDK Integration
- Automatic token exchange
- Token refresh logic
- Error handling

Wednesday: Advanced Features
- Token introspection
- Dynamic registration (optional)

Thursday: Testing & Documentation
- End-to-end tests
- API documentation
- Migration guide

Friday: Deploy
- Production deployment
- User notification
- Support preparation
```

---

## 📋 Success Metrics

### Phase 1 Metrics
```
✅ API key generation: <100ms
✅ API key validation: <10ms
✅ Rate limiting accuracy: 100%
✅ IP whitelist accuracy: 100%
✅ Zero plaintext secrets in database
✅ SDK compatibility: 100%
```

### Phase 1.5 Metrics
```
✅ HMAC validation: <15ms
✅ Replay attack prevention: 100%
✅ Timestamp validation: ±5 minutes
✅ Backward compatibility: 100%
✅ Zero HMAC signature collisions
```

### Phase 2 Metrics
```
✅ Token issuance: <50ms
✅ Token validation: <10ms (cached)
✅ Token TTL: 1 hour (configurable)
✅ Revocation propagation: <5 seconds
✅ Compliance: PCI DSS, SOC 2, GDPR
```

---

## 🔒 Security Checklist

### Before Production Launch

**Phase 1:**
- [ ] HTTPS enforced on all endpoints
- [ ] GitHub secret scanning enabled
- [ ] Secrets never in logs or error messages
- [ ] Default expiration: 90 days
- [ ] Default scopes: minimal (read-only)
- [ ] IP whitelist encouraged in docs
- [ ] Rate limiting tested under load
- [ ] Monitoring and alerting configured

**Phase 1.5:**
- [ ] HMAC signature entropy validated
- [ ] Timestamp window tested (5 minutes)
- [ ] Replay protection Redis tested
- [ ] Secret encryption key rotated
- [ ] Backward compatibility tested
- [ ] SDK updated and tested
- [ ] Migration guide published

**Phase 2:**
- [ ] OAuth server security audit completed
- [ ] Token signing keys rotated
- [ ] Scope hierarchy documented
- [ ] Token revocation tested
- [ ] Compliance requirements met
- [ ] Third-party integration tested
- [ ] Incident response plan documented

---

## 📞 Support & Resources

### Documentation
- Phase 1: `docs/api_keys_basic.md`
- Phase 1.5: `docs/api_keys_hmac.md`
- Phase 2: `docs/oauth2_guide.md`

### Migration Guides
- Phase 1 → 1.5: `docs/migrations/phase1_to_phase1.5.md`
- Phase 1.5 → 2: `docs/migrations/phase1.5_to_phase2.md`

### Security Contacts
- Security issues: security@stocksblitz.com
- API questions: api-support@stocksblitz.com

### External Resources
- OWASP API Security: https://owasp.org/www-project-api-security/
- OAuth 2.0 RFC: https://tools.ietf.org/html/rfc6749
- JWT Best Practices: https://tools.ietf.org/html/rfc8725

---

## ✅ Approval & Sign-Off

**Approved By:** User Service Team
**Date:** 2025-11-09
**Review Date:** After Phase 1 completion

**Decisions:**
1. ✅ Proceed with Phase 1 (Basic API Keys) immediately
2. ✅ Implement Phase 1.5 (HMAC) in Week 2
3. ✅ Plan Phase 2 (OAuth 2.0) for Week 7-8
4. ✅ Maintain backward compatibility during transitions
5. ✅ Prioritize security without sacrificing development velocity

---

**END OF DOCUMENT**
