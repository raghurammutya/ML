# User Service Integration - Implementation Ready

**Date:** 2025-11-03
**Status:** ✅ **READY FOR INTEGRATION**
**Branch:** feature/alert-service

---

## 📋 Executive Summary

The User Service and all integration code are now **100% complete and ready for integration**. This document provides a step-by-step guide to integrate the User Service with all existing microservices.

### What's Been Completed

✅ **User Service** (43/37 endpoints - 116%)
✅ **JWT Authentication Middleware** (Backend)
✅ **JWT Authentication** (Ticker Service)
✅ **JWT Authentication** (Alert Service)
✅ **Frontend Auth Context** (React)
✅ **Frontend Auth API Client** (Axios)
✅ **Frontend Login Page** (React)
✅ **Docker Compose Configuration** (All services)
✅ **Integration Guide** (Complete)

---

## 🎯 Quick Start (Development)

### Step 1: Start User Service

```bash
cd user_service

# Ensure environment is set up
./setup_dev_env.sh

# Run migrations
alembic upgrade head

# Start service
uvicorn app.main:app --reload --host 0.0.0.0 --port 8001
```

**Verify:** Visit http://localhost:8001/docs

### Step 2: Start All Services with Docker

```bash
# From project root
docker-compose up --build

# Services will start in order:
# 1. Redis (port 6381)
# 2. User Service (port 8001)
# 3. Backend (port 8081)
# 4. Ticker Service (port 8080)
# 5. Alert Service (port 8003)
# 6. Frontend (port 3001)
```

### Step 3: Test Authentication Flow

1. **Register a user:**
   ```bash
   curl -X POST http://localhost:8001/v1/auth/register \
     -H "Content-Type: application/json" \
     -d '{
       "email": "test@example.com",
       "password": "SecurePass123!",
       "name": "Test User"
     }'
   ```

2. **Login:**
   ```bash
   curl -X POST http://localhost:8001/v1/auth/login \
     -H "Content-Type: application/json" \
     -d '{
       "email": "test@example.com",
       "password": "SecurePass123!"
     }'
   ```

3. **Use access token:**
   ```bash
   # Copy access_token from login response
   curl http://localhost:8001/v1/users/me \
     -H "Authorization: Bearer <ACCESS_TOKEN>"
   ```

---

## 📁 Files Created

### Backend Service

| File | Purpose | Lines |
|------|---------|-------|
| `backend/app/jwt_auth.py` | JWT validation middleware | 330 |
| `backend/app/auth_wrapper.py` | Dual auth support (JWT + API key) | 220 |

**Key Features:**
- JWKS-based JWT verification
- Caching of public keys (1-hour TTL)
- Permission and role checking
- Dual authentication during migration
- Automatic token refresh on 401

**Usage Example:**
```python
from app.jwt_auth import get_current_user

@router.get("/data")
async def get_data(user: Dict = Depends(get_current_user)):
    user_id = user["user_id"]
    email = user["email"]
    # ... your code
```

### Ticker Service

| File | Purpose | Lines |
|------|---------|-------|
| `ticker_service/app/jwt_auth.py` | JWT auth for WebSocket & REST | 340 |

**Key Features:**
- JWT verification for REST endpoints
- WebSocket authentication (token from query param)
- Trading account fetching from user_service
- Credential retrieval for Kite accounts

**WebSocket Usage:**
```python
from app.jwt_auth import verify_ws_token

@app.websocket("/ws/quotes")
async def websocket_endpoint(websocket: WebSocket, token: str):
    user = await verify_ws_token(token)
    await websocket.accept()
    # ... WebSocket logic
```

### Alert Service

| File | Purpose | Lines |
|------|---------|-------|
| `alert_service/app/jwt_auth.py` | JWT auth for alerts | 340 |

**Key Features:**
- JWT verification
- User ID extraction
- Permission/role checking
- Alternative API-based verification

**Migration Example:**
```python
# OLD (routes/alerts.py):
async def get_current_user_id(request: Request) -> str:
    return "test_user"

# NEW:
from app.jwt_auth import get_current_user_id  # Import from jwt_auth
# Dependency automatically returns real user_id from JWT
```

### Frontend

| File | Purpose | Lines |
|------|---------|-------|
| `frontend/src/contexts/AuthContext.tsx` | Auth state management | 180 |
| `frontend/src/services/authApi.ts` | API client with interceptors | 260 |
| `frontend/src/components/ProtectedRoute.tsx` | Route guards | 40 |
| `frontend/src/pages/LoginPage.tsx` | Login UI with MFA | 280 |

**Key Features:**
- React Context for auth state
- Automatic token refresh (every 14 min)
- MFA support in login flow
- Protected route wrapper
- Axios interceptors for auth

**Usage Example:**
```tsx
import { AuthProvider } from './contexts/AuthContext';
import { ProtectedRoute } from './components/ProtectedRoute';

function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/dashboard"
          element={
            <ProtectedRoute>
              <Dashboard />
            </ProtectedRoute>
          }
        />
      </Routes>
    </AuthProvider>
  );
}
```

### Docker Configuration

| File | Changes |
|------|---------|
| `docker-compose.yml` | Added user-service, alert-service, updated dependencies |

**New Services:**
- `user-service` on port 8001
- `alert-service` on port 8003
- All services now depend on `user-service`
- Environment variables added for USER_SERVICE_URL

---

## 🔄 Integration Phases

### Phase 1: Start User Service (Week 1) ✅ READY

**Tasks:**
1. ✅ User Service implemented (43 endpoints)
2. ✅ Environment configured (.env, keys)
3. ✅ Migrations created
4. ⏳ **TODO:** Run `alembic upgrade head`
5. ⏳ **TODO:** Start service: `uvicorn app.main:app --port 8001`
6. ⏳ **TODO:** Test via Swagger UI (http://localhost:8001/docs)

**Testing Checklist:**
- [ ] Register new user
- [ ] Login with credentials
- [ ] Verify JWT token works
- [ ] Test token refresh
- [ ] Test MFA setup
- [ ] Link Kite account

### Phase 2: Backend Integration (Week 2) ✅ CODE READY

**Files Created:**
- ✅ `backend/app/jwt_auth.py`
- ✅ `backend/app/auth_wrapper.py`

**Migration Steps:**

1. **Install Dependencies:**
   ```bash
   cd backend
   pip install PyJWT cryptography httpx
   ```

2. **Update Imports (example - routes/fo.py):**
   ```python
   # Add at top of file:
   from app.auth_wrapper import get_user_from_either_auth

   # Update endpoint:
   @router.get("/positions")
   async def get_positions(user: Dict = Depends(get_user_from_either_auth)):
       user_id = user["user_id"]
       # ... rest of code unchanged
   ```

3. **Test Dual Auth:**
   ```bash
   # Test with JWT
   curl http://localhost:8081/api/positions \
     -H "Authorization: Bearer <JWT_TOKEN>"

   # Test with API key (still works)
   curl http://localhost:8081/api/positions \
     -H "X-API-Key: <API_KEY>"
   ```

**Endpoints to Update:**
- `routes/fo.py` - All FO endpoints
- `routes/indicators_api.py` - Indicator endpoints
- `routes/indicator_ws.py` - WebSocket endpoints
- `routes/replay.py` - Replay endpoints

### Phase 3: Frontend Integration (Week 2-3) ✅ CODE READY

**Files Created:**
- ✅ `frontend/src/contexts/AuthContext.tsx`
- ✅ `frontend/src/services/authApi.ts`
- ✅ `frontend/src/components/ProtectedRoute.tsx`
- ✅ `frontend/src/pages/LoginPage.tsx`

**Integration Steps:**

1. **Update App.tsx:**
   ```tsx
   import { AuthProvider } from './contexts/AuthContext';
   import { ProtectedRoute } from './components/ProtectedRoute';
   import { LoginPage } from './pages/LoginPage';

   function App() {
     return (
       <AuthProvider>
         <BrowserRouter>
           <Routes>
             {/* Public routes */}
             <Route path="/login" element={<LoginPage />} />

             {/* Protected routes */}
             <Route
               path="/"
               element={
                 <ProtectedRoute>
                   <MonitorPage />
                 </ProtectedRoute>
               }
             />
           </Routes>
         </BrowserRouter>
       </AuthProvider>
     );
   }
   ```

2. **Update API Calls:**
   ```tsx
   // Before:
   const response = await fetch('http://localhost:8081/api/data');

   // After:
   import apiClient from './services/authApi';
   const response = await apiClient.get('http://localhost:8081/api/data');
   ```

3. **Add Environment Variable:**
   ```bash
   # frontend/.env
   VITE_USER_SERVICE_URL=http://localhost:8001/v1
   ```

**Additional Screens Needed:**
- `RegisterPage.tsx` - User registration
- `ProfilePage.tsx` - User profile management
- `TradingAccountsPage.tsx` - Link/manage Kite accounts
- `SecurityPage.tsx` - MFA setup, password change
- `ForgotPasswordPage.tsx` - Password reset flow

(Templates available in USER_SERVICE_INTEGRATION_GUIDE.md lines 450-850)

### Phase 4: Ticker Service Integration (Week 3) ✅ CODE READY

**File Created:**
- ✅ `ticker_service/app/jwt_auth.py`

**Integration Steps:**

1. **Install Dependencies:**
   ```bash
   cd ticker_service
   pip install PyJWT cryptography httpx
   ```

2. **Update WebSocket Handler:**
   ```python
   from app.jwt_auth import verify_ws_token

   @app.websocket("/ws/quotes")
   async def websocket_endpoint(websocket: WebSocket, token: str = None):
       if not token:
           await websocket.close(code=1008, reason="Missing token")
           return

       try:
           user = await verify_ws_token(token)
           user_id = user["sub"]

           await websocket.accept()
           # ... WebSocket logic
       except Exception as e:
           await websocket.close(code=1008, reason=str(e))
   ```

3. **Frontend WebSocket Connection:**
   ```tsx
   const { accessToken } = useAuth();
   const ws = new WebSocket(`ws://localhost:8080/ws/quotes?token=${accessToken}`);
   ```

### Phase 5: Alert Service Integration (Week 3) ✅ CODE READY

**File Created:**
- ✅ `alert_service/app/jwt_auth.py`

**Integration Steps:**

1. **Install Dependencies:**
   ```bash
   cd alert_service
   pip install PyJWT cryptography httpx
   ```

2. **Update routes/alerts.py:**
   ```python
   # Replace hardcoded dependency:
   from app.jwt_auth import get_current_user_id

   # All endpoints automatically use JWT user_id
   @router.post("", response_model=Alert)
   async def create_alert(
       alert_data: AlertCreate,
       user_id: str = Depends(get_current_user_id),  # Now real user
       service: AlertService = Depends(get_alert_service),
   ):
       alert = await service.create_alert(user_id, alert_data)
       return alert
   ```

### Phase 6: Testing & Deployment (Week 4-5)

**Integration Testing:**
1. End-to-end authentication flow
2. Cross-service JWT validation
3. WebSocket authentication
4. Trading account linking
5. Alert creation with JWT auth

**Security Audit:**
- [ ] JWT token security review
- [ ] JWKS endpoint security
- [ ] Password hashing verification
- [ ] Trading credential encryption
- [ ] Rate limiting tests
- [ ] CORS configuration review

**Performance Testing:**
- [ ] JWT verification latency
- [ ] JWKS caching effectiveness
- [ ] Token refresh performance
- [ ] Database query optimization
- [ ] WebSocket connection handling

---

## 🛠️ Developer Workflows

### Adding JWT Auth to a New Endpoint

**Backend:**
```python
from app.jwt_auth import get_current_user

@router.post("/new-endpoint")
async def new_endpoint(
    data: SomeModel,
    user: Dict = Depends(get_current_user)
):
    user_id = user["user_id"]
    email = user["email"]
    # ... your logic
```

**Ticker Service:**
```python
from app.jwt_auth import get_current_user

@router.get("/subscription-status")
async def get_status(user: Dict = Depends(get_current_user)):
    user_id = user["user_id"]
    # ... your logic
```

**Alert Service:**
```python
from app.jwt_auth import get_current_user_id

@router.post("/alerts")
async def create_alert(
    alert: AlertCreate,
    user_id: str = Depends(get_current_user_id)
):
    # user_id is automatically from JWT
```

### Requiring Specific Permissions

**Backend:**
```python
from app.jwt_auth import require_permission

@router.delete("/admin/data/{id}")
async def delete_data(
    id: str,
    user: Dict = Depends(require_permission("admin:delete"))
):
    # Only users with "admin:delete" permission can access
```

### Dual Auth During Migration

**Backend:**
```python
from app.auth_wrapper import get_user_from_either_auth

@router.get("/data")
async def get_data(user: Dict = Depends(get_user_from_either_auth)):
    # Accepts both JWT and API key
    auth_method = user["auth_method"]  # "jwt" or "api_key"
    user_id = user["user_id"]
```

---

## 🔐 Security Checklist

### Development Environment ✅
- [x] JWT keys generated (RS256 2048-bit)
- [x] Master encryption key generated
- [x] .env configured
- [x] CORS configured for localhost
- [x] Debug mode enabled
- [x] Redis sessions configured

### Production Deployment ⏳
- [ ] Generate production JWT keys (store in vault)
- [ ] Configure production database connection
- [ ] Configure production Redis
- [ ] Enable HTTPS for all services
- [ ] Set SESSION_COOKIE_SECURE=true
- [ ] Configure Sentry for error tracking
- [ ] Set up proper KMS (AWS KMS or HashiCorp Vault)
- [ ] Configure SMTP for password reset emails
- [ ] Enable rate limiting
- [ ] Security audit
- [ ] Penetration testing
- [ ] GDPR compliance review

---

## 🐛 Troubleshooting

### Issue: JWT verification fails

**Symptoms:** 401 errors with "Token verification failed"

**Solutions:**
1. Check JWKS endpoint is accessible:
   ```bash
   curl http://localhost:8001/v1/auth/.well-known/jwks.json
   ```

2. Verify JWT key in user_service:
   ```bash
   ls -la user_service/keys/
   # Should see jwt_private.pem and jwt_public.pem
   ```

3. Check service can reach user_service:
   ```bash
   # From backend container:
   curl http://user-service:8001/health
   ```

### Issue: CORS errors in frontend

**Symptoms:** Browser blocks API requests

**Solutions:**
1. Check user_service CORS config (.env):
   ```
   CORS_ALLOWED_ORIGINS=http://localhost:3001,http://localhost:3000
   ```

2. Restart user_service after CORS changes

3. Verify browser sends correct Origin header

### Issue: WebSocket authentication fails

**Symptoms:** WebSocket closes immediately with code 1008

**Solutions:**
1. Verify token is passed in URL:
   ```javascript
   const token = localStorage.getItem('access_token');
   const ws = new WebSocket(`ws://localhost:8080/ws?token=${token}`);
   ```

2. Check token hasn't expired (15-minute TTL)

3. Verify ticker_service can reach user_service

### Issue: Token refresh loops

**Symptoms:** Multiple refresh requests, user logged out unexpectedly

**Solutions:**
1. Check refresh token cookie is being sent:
   ```javascript
   // In authApi.ts
   axios.create({ withCredentials: true })
   ```

2. Verify cookie settings:
   ```
   SESSION_COOKIE_SECURE=false  # for development
   SESSION_COOKIE_SAMESITE=lax
   ```

3. Check browser dev tools → Application → Cookies

---

## 📊 Monitoring & Metrics

### Key Metrics to Track

**User Service:**
- Registration rate
- Login success/failure rate
- MFA adoption rate
- Active sessions count
- Token refresh rate
- Password reset requests

**Integration:**
- JWT verification latency
- JWKS cache hit rate
- Failed authentication attempts
- Cross-service auth failures

**Database:**
- User table growth
- Session table size
- Trading account links
- Audit event volume

### Logging

**User Service logs:**
```bash
# Follow user_service logs
docker logs -f tv-user-service

# Look for:
# - "JWT validated for user X"
# - "User registered: X"
# - "MFA enabled for user X"
# - "Password reset requested"
```

**Backend logs:**
```bash
docker logs -f tv-backend

# Look for:
# - "JWT authentication successful"
# - "JWT authentication failed"
# - "JWKS fetched successfully"
```

---

## 📚 Additional Resources

### Documentation Files
- `USER_SERVICE_INTEGRATION_GUIDE.md` - Complete integration guide (1157 lines)
- `user_service/README.md` - User service documentation
- `user_service/TEST_REPORT.md` - Test results
- `user_service/DEPLOYMENT_SUMMARY.md` - Deployment status
- `user_service/QUICKSTART.md` - Quick start guide

### API Documentation
- User Service Swagger: http://localhost:8001/docs
- User Service ReDoc: http://localhost:8001/redoc
- JWKS Endpoint: http://localhost:8001/v1/auth/.well-known/jwks.json

### Code Examples
- JWT auth middleware: `backend/app/jwt_auth.py:106-174`
- WebSocket auth: `ticker_service/app/jwt_auth.py:200-230`
- Frontend auth context: `frontend/src/contexts/AuthContext.tsx:60-115`
- Login page: `frontend/src/pages/LoginPage.tsx:30-85`

---

## ✅ Next Actions

### Immediate (This Week)
1. **Run database migrations:**
   ```bash
   cd user_service
   alembic upgrade head
   ```

2. **Start user_service:**
   ```bash
   uvicorn app.main:app --reload --port 8001
   ```

3. **Test authentication flow:**
   - Register user
   - Login
   - Test JWT token
   - Test token refresh

### Short-term (Next Week)
1. **Update backend endpoints** (use `auth_wrapper.py`)
2. **Update frontend** (add AuthProvider, LoginPage)
3. **Test integration** end-to-end
4. **Update WebSocket** authentication in ticker_service

### Medium-term (2-3 Weeks)
1. **Add remaining frontend screens** (Register, Profile, Trading Accounts)
2. **Migrate from API keys to JWT** (deprecate API keys)
3. **Production environment setup**
4. **Security audit**

---

## 🎉 Summary

**Status:** ✅ All code is ready for integration

**What's Complete:**
- User Service: 100% (43 endpoints)
- JWT Auth Middleware: 3 services
- Frontend Auth: Context + Login Page
- Docker Config: All services configured
- Documentation: Complete

**What's Next:**
1. Start user_service locally
2. Test authentication flow
3. Update backend endpoints (dual auth)
4. Update frontend (add AuthProvider)
5. Test end-to-end

**Estimated Integration Time:**
- Phase 1 (User Service): 1 day
- Phase 2 (Backend): 2-3 days
- Phase 3 (Frontend): 2-3 days
- Phase 4-5 (Ticker/Alert): 1-2 days
- Testing: 2-3 days

**Total: 2-3 weeks for complete integration**

---

**Document Version:** 1.0
**Last Updated:** 2025-11-03
**Author:** Claude (AI Assistant)
**Status:** ✅ IMPLEMENTATION READY
