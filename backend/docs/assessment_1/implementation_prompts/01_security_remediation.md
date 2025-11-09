# Implementation Prompt: Security Remediation (Week 1 - CRITICAL)

**Priority**: CRITICAL (P0)
**Estimated Duration**: 6-8 days (1 engineer full-time)
**Prerequisites**: Phase 2 Security Audit complete
**Blocking**: Production deployment

---

## Objective

Fix 4 CRITICAL security vulnerabilities (CVSS 9.0+) identified in Phase 2 Security Audit to enable production deployment.

**Critical Blockers**:
1. Hardcoded database credentials in git (CVSS 10.0)
2. No WebSocket authentication (CVSS 9.1)
3. SQL injection vulnerabilities (CVSS 9.8)
4. No rate limiting on trading endpoints (CVSS 9.0)

**Success Criteria**: All 4 CRITICAL vulnerabilities resolved with zero functional regression.

---

## Context

**Working Directory**: `/mnt/stocksblitz-data/Quantagro/tradingview-viz/backend`
**Reference**: `/docs/assessment_1/phase2_security_audit.md`
**Current Security Grade**: C+ (69/100)
**Target Security Grade**: B+ (85/100) minimum for production

**Zero Regression Guarantee**: All fixes must preserve 100% functional parity.

---

## Task 1: Remove Hardcoded Secrets (CVSS 10.0) - Day 1-2

### Current State

**File**: `app/config.py`
**Issue**: Database credentials hardcoded in source code and committed to git

```python
# app/config.py - CURRENT (CRITICAL SECURITY ISSUE)
class Settings(BaseSettings):
    db_password: str = "stocksblitz123"  # ❌ HARDCODED
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "stocksblitz_unified"
    db_user: str = "stocksblitz"

    redis_url: str = "redis://localhost:6379"
    ticker_service_url: str = "http://localhost:8080"
```

**Risk**: Any developer with git access has production database credentials → data breach

### Implementation Steps

**Step 1.1: Install python-dotenv (if not already installed)**
```bash
cd /mnt/stocksblitz-data/Quantagro/tradingview-viz/backend
grep "python-dotenv" requirements.txt || echo "python-dotenv==1.0.0" >> requirements.txt
```

**Step 1.2: Create .env.template**
```bash
cat > .env.template << 'EOF'
# Database Configuration
DB_PASSWORD=your_db_password_here
DB_HOST=localhost
DB_PORT=5432
DB_NAME=stocksblitz_unified
DB_USER=stocksblitz

# Redis Configuration
REDIS_URL=redis://localhost:6379

# External Services
TICKER_SERVICE_URL=http://localhost:8080
USER_SERVICE_URL=http://localhost:8000

# Security
JWT_SECRET_KEY=your_jwt_secret_here
JWT_ALGORITHM=HS256

# Environment
ENVIRONMENT=development
EOF
```

**Step 1.3: Update app/config.py**
```python
# app/config.py - FIXED VERSION
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Literal

class Settings(BaseSettings):
    # Database Configuration
    db_password: str = Field(..., description="Database password")
    db_host: str = Field(default="localhost", description="Database host")
    db_port: int = Field(default=5432, description="Database port")
    db_name: str = Field(default="stocksblitz_unified", description="Database name")
    db_user: str = Field(default="stocksblitz", description="Database user")

    # Redis Configuration
    redis_url: str = Field(default="redis://localhost:6379", description="Redis connection URL")

    # External Services
    ticker_service_url: str = Field(default="http://localhost:8080", description="Ticker service URL")
    user_service_url: str = Field(default="http://localhost:8000", description="User service URL")

    # Security
    jwt_secret_key: str = Field(..., description="JWT secret key for token signing")
    jwt_algorithm: str = Field(default="HS256", description="JWT signing algorithm")

    # Environment
    environment: Literal["development", "staging", "production"] = Field(
        default="development",
        description="Deployment environment"
    )

    @property
    def database_url(self) -> str:
        """Construct database URL from components."""
        return f"postgresql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

settings = Settings()
```

**Step 1.4: Update .gitignore**
```bash
# Ensure .env is ignored
grep -q "^\.env$" .gitignore || echo ".env" >> .gitignore
```

**Step 1.5: Remove secrets from git history (CRITICAL)**
```bash
# WARNING: This rewrites git history - coordinate with team
git filter-branch --force --index-filter \
  "git rm --cached --ignore-unmatch app/config.py" \
  --prune-empty --tag-name-filter cat -- --all

# Alternative: Use BFG Repo-Cleaner (recommended)
# java -jar bfg.jar --delete-files config.py backend.git
# cd backend.git
# git reflog expire --expire=now --all && git gc --prune=now --aggressive
```

**Step 1.6: Create production secrets**
```bash
# Create .env for production (do NOT commit)
cat > .env << 'EOF'
DB_PASSWORD=REPLACE_WITH_PRODUCTION_PASSWORD
JWT_SECRET_KEY=REPLACE_WITH_PRODUCTION_JWT_SECRET
ENVIRONMENT=production
EOF
```

**Validation**:
- [ ] No hardcoded secrets in `app/config.py`
- [ ] `.env` in `.gitignore`
- [ ] All environment variables loaded from `.env`
- [ ] Application starts successfully with `.env`
- [ ] `git log --all -- app/config.py` shows no secrets

**Effort**: 2 days (includes git history cleanup, testing)

---

## Task 2: Add WebSocket Authentication (CVSS 9.1) - Day 3

### Current State

**File**: `app/routes/fo.py:1850-1900` (WebSocket endpoint)
**Issue**: WebSocket connections accepted without JWT validation

```python
# app/routes/fo.py - CURRENT (CRITICAL SECURITY ISSUE)
@router.websocket("/ws/fo/stream")
async def websocket_fo_stream(websocket: WebSocket):
    await websocket.accept()  # ❌ NO AUTHENTICATION CHECK

    try:
        while True:
            data = await websocket.receive_text()
            # Process real-time F&O data
            await websocket.send_json({"data": data})
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
```

**Risk**: Any user can connect and stream real-time trading data without authentication

### Implementation Steps

**Step 2.1: Create WebSocket authentication dependency**
```python
# app/dependencies.py - NEW FILE
from fastapi import WebSocket, HTTPException, status
from jose import jwt, JWTError
from app.config import settings
import logging

logger = logging.getLogger(__name__)

async def verify_websocket_token(websocket: WebSocket) -> dict:
    """
    Verify JWT token from WebSocket query parameters.

    Args:
        websocket: FastAPI WebSocket connection

    Returns:
        dict: Decoded token payload with user_id, account_id

    Raises:
        WebSocketException: If token is invalid or missing
    """
    # Extract token from query parameter: ws://localhost:8081/ws/fo/stream?token=eyJ...
    token = websocket.query_params.get("token")

    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Missing authentication token")
        raise HTTPException(status_code=401, detail="Missing authentication token")

    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm]
        )

        user_id = payload.get("user_id")
        account_id = payload.get("account_id")

        if not user_id:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid token payload")
            raise HTTPException(status_code=401, detail="Invalid token payload")

        logger.info(f"WebSocket authenticated: user_id={user_id}, account_id={account_id}")
        return payload

    except JWTError as e:
        logger.warning(f"WebSocket JWT validation failed: {e}")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid authentication token")
        raise HTTPException(status_code=401, detail="Invalid authentication token")
```

**Step 2.2: Update WebSocket endpoint in app/routes/fo.py**
```python
# app/routes/fo.py - FIXED VERSION
from app.dependencies import verify_websocket_token

@router.websocket("/ws/fo/stream")
async def websocket_fo_stream(websocket: WebSocket):
    # Step 1: Accept connection (required before reading query params)
    await websocket.accept()

    # Step 2: Verify JWT token
    try:
        token_payload = await verify_websocket_token(websocket)
        user_id = token_payload["user_id"]
        account_id = token_payload.get("account_id")

        logger.info(f"WebSocket authenticated for user_id={user_id}, account_id={account_id}")

    except HTTPException:
        # Token validation failed, connection already closed
        return

    # Step 3: Stream data (only after authentication)
    try:
        while True:
            data = await websocket.receive_text()

            # Multi-tenant isolation: only send data for authenticated account
            filtered_data = filter_by_account(data, account_id)

            await websocket.send_json({"data": filtered_data})

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for user_id={user_id}")
```

**Step 2.3: Update all WebSocket endpoints**

Apply same authentication pattern to:
- `WS /ws/orders/{account_id}`
- `WS /ws/positions/{account_id}`
- `WS /ws/strategies/{strategy_id}`

**Step 2.4: Update frontend WebSocket client**
```typescript
// frontend/src/services/websocket.ts - EXAMPLE
const token = localStorage.getItem("access_token");
const ws = new WebSocket(`ws://localhost:8081/ws/fo/stream?token=${token}`);

ws.onopen = () => {
  console.log("WebSocket connected and authenticated");
};

ws.onerror = (error) => {
  console.error("WebSocket authentication failed:", error);
};
```

**Validation**:
- [ ] WebSocket connection without token rejected (1008 status code)
- [ ] WebSocket connection with invalid token rejected
- [ ] WebSocket connection with valid token accepted
- [ ] Multi-account isolation enforced (User A cannot see User B's data)
- [ ] All 5+ WebSocket endpoints updated

**Effort**: 1 day (includes frontend updates, testing)

---

## Task 3: Fix SQL Injection Vulnerabilities (CVSS 9.8) - Day 4-5

### Current State

**File**: `app/routes/strategies.py:385-409`
**Issue**: Dynamic SQL query building with user input → SQL injection

```python
# app/routes/strategies.py - CURRENT (CRITICAL SECURITY ISSUE)
@router.get("/strategies")
async def get_strategies(
    user_id: int,
    sort_by: str = "created_at",  # ❌ USER INPUT
    order: str = "DESC"            # ❌ USER INPUT
):
    # VULNERABLE: User input directly interpolated into SQL
    query = f"""
        SELECT * FROM strategies
        WHERE user_id = {user_id}
        ORDER BY {sort_by} {order}
    """

    results = await db.fetch(query)
    return results
```

**Attack Vector**:
```bash
# Attacker sends: sort_by=id; DROP TABLE strategies; --
# Resulting query:
SELECT * FROM strategies WHERE user_id = 123 ORDER BY id; DROP TABLE strategies; -- DESC
```

### Implementation Steps

**Step 3.1: Create SQL injection safe utilities**
```python
# app/database.py - ADD UTILITIES
from typing import Literal

# Whitelist of allowed sort columns (prevents SQL injection)
ALLOWED_STRATEGY_SORT_COLUMNS = {
    "created_at", "updated_at", "name", "status", "total_m2m"
}

ALLOWED_SORT_ORDER = {"ASC", "DESC"}

def validate_sort_params(
    sort_by: str,
    order: str,
    allowed_columns: set[str]
) -> tuple[str, str]:
    """
    Validate and sanitize sort parameters to prevent SQL injection.

    Args:
        sort_by: Column name to sort by
        order: Sort order (ASC or DESC)
        allowed_columns: Set of allowed column names

    Returns:
        tuple: (validated_column, validated_order)

    Raises:
        HTTPException: If parameters are invalid
    """
    if sort_by not in allowed_columns:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid sort_by parameter. Allowed: {', '.join(allowed_columns)}"
        )

    order_upper = order.upper()
    if order_upper not in ALLOWED_SORT_ORDER:
        raise HTTPException(
            status_code=400,
            detail="Invalid order parameter. Allowed: ASC, DESC"
        )

    return sort_by, order_upper
```

**Step 3.2: Fix app/routes/strategies.py**
```python
# app/routes/strategies.py - FIXED VERSION
from app.database import validate_sort_params, ALLOWED_STRATEGY_SORT_COLUMNS

@router.get("/strategies")
async def get_strategies(
    user_id: int,
    sort_by: str = "created_at",
    order: str = "DESC"
):
    # Validate and sanitize user input
    safe_sort_by, safe_order = validate_sort_params(
        sort_by,
        order,
        ALLOWED_STRATEGY_SORT_COLUMNS
    )

    # Use parameterized query (SQL injection safe)
    query = f"""
        SELECT * FROM strategies
        WHERE user_id = $1
        ORDER BY {safe_sort_by} {safe_order}
    """

    # $1 placeholder prevents SQL injection for user_id
    results = await db.fetch(query, user_id)
    return results
```

**Step 3.3: Audit all dynamic queries**

Search for vulnerable patterns:
```bash
cd /mnt/stocksblitz-data/Quantagro/tradingview-viz/backend
grep -rn "f\"SELECT" app/ --include="*.py"
grep -rn "f'SELECT" app/ --include="*.py"
grep -rn '%.format(' app/ --include="*.py"
```

**Fix all instances** using parameterized queries (`$1`, `$2`, etc.) and whitelisting.

**Step 3.4: Add SQL injection tests**
```python
# tests/security/test_sql_injection.py - NEW FILE
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_sql_injection_in_sort_by():
    """Test that SQL injection in sort_by parameter is blocked."""

    # Attempt SQL injection
    response = client.get(
        "/strategies",
        params={
            "user_id": 1,
            "sort_by": "id; DROP TABLE strategies; --",
            "order": "DESC"
        }
    )

    # Should return 400 Bad Request, not 200
    assert response.status_code == 400
    assert "Invalid sort_by parameter" in response.json()["detail"]

def test_sql_injection_in_order():
    """Test that SQL injection in order parameter is blocked."""

    response = client.get(
        "/strategies",
        params={
            "user_id": 1,
            "sort_by": "created_at",
            "order": "DESC; DROP TABLE strategies; --"
        }
    )

    assert response.status_code == 400
    assert "Invalid order parameter" in response.json()["detail"]

def test_parameterized_query_prevents_injection():
    """Test that user_id parameter is SQL injection safe."""

    # Attempt injection via user_id
    response = client.get(
        "/strategies",
        params={
            "user_id": "1 OR 1=1",  # Classic SQL injection attempt
            "sort_by": "created_at",
            "order": "DESC"
        }
    )

    # FastAPI type validation should reject non-integer user_id
    assert response.status_code == 422  # Validation error
```

**Validation**:
- [ ] All dynamic queries use parameterized queries (`$1`, `$2`, etc.)
- [ ] All user-controlled column names use whitelist validation
- [ ] All user-controlled sort orders use whitelist validation
- [ ] SQL injection tests pass (3+ tests)
- [ ] No `f"SELECT {user_input}"` patterns in codebase

**Effort**: 2 days (includes full audit, testing)

---

## Task 4: Add Rate Limiting (CVSS 9.0) - Day 6

### Current State

**File**: `app/routes/fo.py`, `app/main.py`
**Issue**: No rate limiting on order placement endpoints → margin exhaustion attack

**Attack Vector**:
- Attacker places 1,000 orders in 1 second
- Each order consumes margin: ₹50,000 × 1,000 = ₹5 crore margin exhausted
- User cannot place legitimate orders
- Potential financial loss if orders executed

### Implementation Steps

**Step 4.1: Install slowapi**
```bash
pip install slowapi==0.1.9
echo "slowapi==0.1.9" >> requirements.txt
```

**Step 4.2: Configure rate limiting in app/main.py**
```python
# app/main.py - ADD RATE LIMITING
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Initialize rate limiter
limiter = Limiter(
    key_func=get_remote_address,  # Rate limit by IP address
    default_limits=["100/minute"]  # Global default: 100 requests/minute
)

app = FastAPI(title="Backend API", version="1.0.0")

# Add rate limit exception handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
```

**Step 4.3: Add rate limiting to trading endpoints**
```python
# app/routes/fo.py - ADD RATE LIMITING
from slowapi import Limiter
from slowapi.util import get_remote_address
from app.main import limiter

@router.post("/accounts/{account_id}/orders")
@limiter.limit("10/minute")  # ✅ Max 10 orders per minute per IP
async def place_order(
    request: Request,  # Required for slowapi
    account_id: int,
    order: OrderRequest
):
    """
    Place a new order.

    Rate Limit: 10 orders/minute per account
    """
    # Validate account ownership
    # ... existing code ...

    # Place order via ticker service
    result = await ticker_service.place_order(account_id, order)
    return result

@router.delete("/accounts/{account_id}/orders/{order_id}")
@limiter.limit("20/minute")  # ✅ Max 20 cancellations per minute
async def cancel_order(
    request: Request,
    account_id: int,
    order_id: str
):
    """
    Cancel an existing order.

    Rate Limit: 20 cancellations/minute per account
    """
    result = await ticker_service.cancel_order(account_id, order_id)
    return result
```

**Step 4.4: Add account-based rate limiting (more secure)**
```python
# app/dependencies.py - ADD ACCOUNT-BASED RATE LIMITING
from slowapi.util import get_remote_address

def get_account_identifier(request: Request) -> str:
    """
    Get unique identifier for rate limiting.

    Combines account_id + IP to prevent:
    1. Single account abuse from one IP
    2. Single IP targeting multiple accounts
    """
    account_id = request.path_params.get("account_id", "unknown")
    ip_address = get_remote_address(request)

    return f"{account_id}:{ip_address}"

# app/main.py - UPDATE LIMITER
limiter = Limiter(
    key_func=get_account_identifier,  # Rate limit by account+IP
    default_limits=["100/minute"]
)
```

**Step 4.5: Add rate limiting tests**
```python
# tests/security/test_rate_limiting.py - NEW FILE
import pytest
from fastapi.testclient import TestClient
from app.main import app
import time

client = TestClient(app)

def test_order_rate_limit_enforced():
    """Test that order placement is rate limited to 10/minute."""

    # Attempt to place 15 orders rapidly
    for i in range(15):
        response = client.post(
            "/accounts/123/orders",
            json={
                "tradingsymbol": "NIFTY2550024000CE",
                "quantity": 50,
                "price": 100.0,
                "order_type": "LIMIT"
            }
        )

        if i < 10:
            # First 10 orders should succeed
            assert response.status_code == 200
        else:
            # Orders 11-15 should be rate limited
            assert response.status_code == 429  # Too Many Requests
            assert "Rate limit exceeded" in response.json()["detail"]

def test_rate_limit_reset_after_window():
    """Test that rate limit resets after 1 minute."""

    # Place 10 orders (hit limit)
    for _ in range(10):
        client.post("/accounts/123/orders", json={...})

    # 11th order should fail
    response = client.post("/accounts/123/orders", json={...})
    assert response.status_code == 429

    # Wait 61 seconds
    time.sleep(61)

    # 12th order should succeed (rate limit reset)
    response = client.post("/accounts/123/orders", json={...})
    assert response.status_code == 200
```

**Validation**:
- [ ] Rate limiting enabled globally (100 req/min default)
- [ ] Order placement limited to 10/minute per account
- [ ] Order cancellation limited to 20/minute per account
- [ ] HTTP 429 returned when limit exceeded
- [ ] Rate limit tests pass (2+ tests)
- [ ] Rate limit headers present: `X-RateLimit-Limit`, `X-RateLimit-Remaining`

**Effort**: 1 day (includes testing)

---

## Task 5: Security Testing & Validation - Day 7-8

### Test Suite Requirements

**5.1: Create security test suite**
```python
# tests/security/test_authentication.py - NEW FILE
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_jwt_token_required():
    """Test that endpoints require valid JWT token."""

    # Attempt to access protected endpoint without token
    response = client.get("/strategies")
    assert response.status_code == 401
    assert "Missing authentication token" in response.json()["detail"]

def test_invalid_jwt_token_rejected():
    """Test that invalid JWT tokens are rejected."""

    response = client.get(
        "/strategies",
        headers={"Authorization": "Bearer invalid_token_12345"}
    )
    assert response.status_code == 401
    assert "Invalid authentication token" in response.json()["detail"]

def test_expired_jwt_token_rejected():
    """Test that expired JWT tokens are rejected."""

    # Create expired token (issued 2 hours ago, expires in 1 hour)
    expired_token = create_test_token(exp_hours=-1)

    response = client.get(
        "/strategies",
        headers={"Authorization": f"Bearer {expired_token}"}
    )
    assert response.status_code == 401
    assert "Token expired" in response.json()["detail"]

def test_multi_account_isolation():
    """Test that User A cannot access User B's data."""

    # User A's token (account_id=123)
    token_a = create_test_token(user_id=1, account_id=123)

    # Attempt to access User B's strategies (account_id=456)
    response = client.get(
        "/strategies?account_id=456",
        headers={"Authorization": f"Bearer {token_a}"}
    )

    # Should return 403 Forbidden (not 200)
    assert response.status_code == 403
    assert "Access denied" in response.json()["detail"]
```

**5.2: Run security audit tools**
```bash
# Install security audit tools
pip install bandit safety

# Run Bandit (Python security linter)
bandit -r app/ -f json -o security_audit_bandit.json

# Run Safety (dependency vulnerability scanner)
safety check --json > security_audit_safety.json

# Review results
cat security_audit_bandit.json | jq '.results[] | select(.issue_severity=="HIGH" or .issue_severity=="MEDIUM")'
```

**5.3: Manual penetration testing checklist**
- [ ] Attempt SQL injection on all query parameters
- [ ] Attempt XSS on all text inputs
- [ ] Attempt CSRF on all POST endpoints
- [ ] Attempt directory traversal on file paths
- [ ] Attempt command injection on system calls
- [ ] Attempt JWT tampering (modify payload)
- [ ] Attempt brute force on rate limited endpoints

**Validation**:
- [ ] All security tests pass (15+ tests)
- [ ] Bandit reports zero HIGH/CRITICAL issues
- [ ] Safety reports zero vulnerable dependencies
- [ ] Manual penetration tests pass

**Effort**: 2 days (includes manual testing, reporting)

---

## Final Checklist

### Security Fixes
- [ ] **Task 1**: Hardcoded secrets removed from git
- [ ] **Task 2**: WebSocket authentication implemented
- [ ] **Task 3**: SQL injection vulnerabilities fixed
- [ ] **Task 4**: Rate limiting implemented
- [ ] **Task 5**: Security testing complete

### Zero Regression Validation
- [ ] All existing API endpoints functional
- [ ] All existing tests pass
- [ ] No breaking changes to API contracts
- [ ] Frontend WebSocket clients updated
- [ ] Database queries return same results

### Documentation
- [ ] `.env.template` created with all required variables
- [ ] Security fixes documented in CHANGELOG.md
- [ ] API documentation updated (rate limits, authentication)
- [ ] Deployment guide updated (environment variables)

### Deployment Preparation
- [ ] Production `.env` configured (secrets manager)
- [ ] Environment variables validated
- [ ] Security headers configured (HSTS, CSP, X-Frame-Options)
- [ ] CORS configuration reviewed
- [ ] SSL/TLS certificates verified

---

## Success Metrics

**Before (Phase 2 Security Audit)**:
- Security Grade: C+ (69/100)
- CRITICAL vulnerabilities: 4
- OWASP Top 10 compliance: 40%

**After (Target)**:
- Security Grade: B+ (85/100)
- CRITICAL vulnerabilities: 0
- OWASP Top 10 compliance: 80%+

---

## Next Steps

After completing this security remediation:

1. **Week 2-3**: Execute Implementation Prompt 02 (Critical Testing - 120 tests)
2. **Week 4+**: Consider Implementation Prompt 03 (Strategy System) if pursuing full production path
3. **Continuous**: Run security audits monthly (Bandit, Safety, OWASP ZAP)

---

**Estimated Effort**: 6-8 days (1 engineer full-time)
**Priority**: P0 - BLOCKING PRODUCTION
**Impact**: CRITICAL - Enables production deployment

---

**Last Updated**: 2025-11-09
**Owner**: Security Team
**Next Review**: After implementation complete
