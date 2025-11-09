# User Service - Multi-Environment Alignment

**Date:** 2025-11-09
**Status:** ✅ COMPLETE - Aligned with Multi-Environment Architecture
**Sprint:** 1.5 - Environment Configuration

---

## 🎯 Overview

The user_service has been successfully aligned with the multi-environment architecture, using environment-specific PostgreSQL and Redis instances with separate databases per environment.

---

## ✅ Changes Implemented

### 1. Environment-Specific Configuration Files

Created three environment-specific `.env` files:

**Development** (`.env.dev`):
```bash
# Ports
USER_SERVICE_PORT=8011
DATABASE_URL=postgresql://stocksblitz:stocksblitz123@localhost:8003/stocksblitz_unified_dev
REDIS_URL=redis://localhost:8002/0

# Service Discovery
TICKER_SERVICE_URL=http://localhost:8080
BACKEND_SERVICE_URL=http://localhost:8010
ALERT_SERVICE_URL=http://localhost:8012
CALENDAR_SERVICE_URL=http://localhost:8013
```

**Staging** (`.env.staging`):
```bash
# Ports
USER_SERVICE_PORT=8111
DATABASE_URL=postgresql://stocksblitz:stocksblitz123@localhost:8103/stocksblitz_unified_staging
REDIS_URL=redis://localhost:8102/0

# Service Discovery
TICKER_SERVICE_URL=http://localhost:8080
BACKEND_SERVICE_URL=http://localhost:8110
ALERT_SERVICE_URL=http://localhost:8112
CALENDAR_SERVICE_URL=http://localhost:8113
```

**Production** (`.env.production`):
```bash
# Ports
USER_SERVICE_PORT=8211
DATABASE_URL=postgresql://stocksblitz:${PRODUCTION_DB_PASSWORD}@localhost:8203/stocksblitz_unified_production
REDIS_URL=redis://localhost:8202/0

# Service Discovery
TICKER_SERVICE_URL=http://localhost:8080
BACKEND_SERVICE_URL=http://localhost:8210
ALERT_SERVICE_URL=http://localhost:8212
CALENDAR_SERVICE_URL=http://localhost:8213
```

---

### 2. Database Isolation Strategy

**Separate Databases Per Environment:**

| Environment | PostgreSQL Port | Database Name | Purpose |
|-------------|-----------------|---------------|---------|
| **Development** | 8003 | `stocksblitz_unified_dev` | Active development, test users |
| **Staging** | 8103 | `stocksblitz_unified_staging` | Production validation, QA |
| **Production** | 8203 | `stocksblitz_unified_production` | Live user data |

**Benefits:**
- ✅ Complete data isolation between environments
- ✅ Safe schema evolution (test in dev → validate in staging → deploy to prod)
- ✅ Test destructive operations safely in dev/staging
- ✅ Production data remains pristine and secure

---

### 3. Redis Isolation Strategy

**Separate Redis Instances Per Environment:**

| Environment | Redis Port | Database | Purpose |
|-------------|------------|----------|---------|
| **Development** | 8002 | 0 | Sessions, cache, rate limiting |
| **Staging** | 8102 | 0 | Sessions, cache, rate limiting |
| **Production** | 8202 | 0 | Sessions, cache, rate limiting |

---

### 4. Port Allocation

**User Service Ports:**

| Environment | Service Port | Notes |
|-------------|--------------|-------|
| **Development** | 8011 | External access allowed (office/VPN IPs) |
| **Staging** | 8111 | Localhost only, accessed via Nginx |
| **Production** | 8211 | Localhost only, accessed via Nginx |

---

### 5. Configuration Model Updates

Updated `app/core/config.py` to support multi-environment:

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="allow"  # Allow extra environment variables
    )

    # Added fields for multi-environment
    USER_SERVICE_PORT: int = Field(default=8011, env="USER_SERVICE_PORT")
    USER_SERVICE_HOST: str = Field(default="0.0.0.0", env="USER_SERVICE_HOST")
    CALENDAR_SERVICE_URL: str = Field(default="http://calendar_service:8013", env="CALENDAR_SERVICE_URL")
```

---

## 🗄️ Database Setup

### Databases Created

```bash
# Development database (port 8003)
PGPASSWORD=stocksblitz123 psql -h localhost -p 8003 -U stocksblitz -d postgres \
  -c "CREATE DATABASE stocksblitz_unified_dev;"
✅ Created

# Staging database (port 8103)
PGPASSWORD=stocksblitz123 psql -h localhost -p 8103 -U stocksblitz -d postgres \
  -c "CREATE DATABASE stocksblitz_unified_staging;"
✅ Created

# Production database (port 8203)
PGPASSWORD=stocksblitz123 psql -h localhost -p 8203 -U stocksblitz -d postgres \
  -c "CREATE DATABASE stocksblitz_unified_production;"
✅ Created
```

### Migrations Applied

All migrations successfully applied to development database:

```bash
$ alembic upgrade head
INFO  [alembic.runtime.migration] Running upgrade  -> 001, Initial schema - create all tables
INFO  [alembic.runtime.migration] Running upgrade 001 -> 002, Seed initial data - roles, policies, service clients
INFO  [alembic.runtime.migration] Running upgrade 002 -> 20251107_0003, Add broker credential columns to trading_accounts
INFO  [alembic.runtime.migration] Running upgrade 20251107_0003 -> 20251108_0004, Add subscription tier tracking to trading accounts
INFO  [alembic.runtime.migration] Running upgrade 20251108_0004 -> 005, Add API keys tables
✅ Complete
```

**Database Schema:**
- ✅ `users` table with authentication
- ✅ `roles` and `policies` tables for authorization
- ✅ `trading_accounts` table with broker credentials
- ✅ `trading_account_memberships` for shared access
- ✅ `api_keys` table with security features
- ✅ `api_key_usage_logs` table for tracking
- ✅ `audit_logs` table for compliance

---

## 🚀 Starting User Service in Each Environment

### Development
```bash
cd /mnt/stocksblitz-data/Quantagro/tradingview-viz/user_service

# Copy dev configuration
cp .env.dev .env

# Start service
uvicorn app.main:app --host 0.0.0.0 --port 8011 --reload

# Verify
curl http://localhost:8011/health
```

### Staging
```bash
cd /mnt/stocksblitz-data/Quantagro/tradingview-viz/user_service

# Copy staging configuration
cp .env.staging .env

# Run migrations (first time only)
alembic upgrade head

# Start service
uvicorn app.main:app --host 127.0.0.1 --port 8111

# Verify
curl http://localhost:8111/health
```

### Production
```bash
cd /mnt/stocksblitz-data/Quantagro/tradingview-viz/user_service

# Copy production configuration
cp .env.production .env

# Run migrations (first time only)
alembic upgrade head

# Start service
uvicorn app.main:app --host 127.0.0.1 --port 8211

# Verify
curl http://localhost:8211/health
```

---

## 🔗 Service Integration

### Backend → User Service Communication

Backend services need to call user_service for authentication and authorization.

**Backend `.env` files should include:**

```bash
# Development (.env.dev)
USER_SERVICE_URL=http://localhost:8011

# Staging (.env.staging)
USER_SERVICE_URL=http://localhost:8111

# Production (.env.production)
USER_SERVICE_URL=http://localhost:8211
```

**Usage in Backend:**
```python
import httpx
from config import settings

async def verify_api_key(api_key: str):
    """Verify API key via user_service"""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{settings.USER_SERVICE_URL}/v1/users/me",
            headers={"X-API-Key": api_key}
        )
        return response.json()
```

---

## 📊 Service Dependency Matrix

### User Service Dependencies

| Dependency | Dev | Staging | Production | Shared? |
|------------|-----|---------|------------|---------|
| **PostgreSQL** | 8003 | 8103 | 8203 | ❌ Isolated |
| **Redis** | 8002 | 8102 | 8202 | ❌ Isolated |
| **Ticker Service** | 8080 | 8080 | 8080 | ✅ Shared |
| **Backend** | 8010 | 8110 | 8210 | ❌ Isolated |
| **Alert Service** | 8012 | 8112 | 8212 | ❌ Isolated |
| **Calendar Service** | 8013 | 8113 | 8213 | ❌ Isolated |

---

## 🔐 Security Configurations

### Development
- `DEBUG=true`
- `SESSION_COOKIE_SECURE=false` (no HTTPS)
- `CORS_ALLOWED_ORIGINS=http://localhost:3000,http://localhost:3001,http://localhost:5173`
- `LOG_LEVEL=DEBUG`
- External access allowed (office/VPN IPs)

### Staging
- `DEBUG=false`
- `SESSION_COOKIE_SECURE=true` (HTTPS enforced)
- `SESSION_COOKIE_SAMESITE=strict`
- `CORS_ALLOWED_ORIGINS=http://localhost:3002` (limited)
- `LOG_LEVEL=INFO`
- `LOG_FORMAT=json`
- Localhost only, accessed via Nginx

### Production
- `DEBUG=false`
- `SESSION_COOKIE_SECURE=true` (HTTPS enforced)
- `SESSION_COOKIE_SAMESITE=strict`
- `CORS_ALLOWED_ORIGINS=https://app.stocksblitz.com,https://stocksblitz.com`
- `LOG_LEVEL=WARNING`
- `LOG_FORMAT=json`
- `SENTRY_DSN` configured
- Localhost only, accessed via Nginx
- Stricter rate limits (3 login attempts vs 5)
- Password requirements (14 chars min vs 12)

---

## 📁 Files Created/Modified

### Created Files:
- `.env.dev` - Development environment configuration
- `.env.staging` - Staging environment configuration
- `.env.production` - Production environment configuration
- `docs/MULTI_ENVIRONMENT_ALIGNMENT.md` - This file

### Modified Files:
- `app/core/config.py` - Added USER_SERVICE_PORT, USER_SERVICE_HOST, CALENDAR_SERVICE_URL, extra="allow"
- `.env` - Updated to use development configuration

### Databases Created:
- `stocksblitz_unified_dev` on port 8003
- `stocksblitz_unified_staging` on port 8103
- `stocksblitz_unified_production` on port 8203

---

## ✅ Verification Checklist

**Configuration:**
- [x] `.env.dev` created with port 8003, 8002
- [x] `.env.staging` created with port 8103, 8102
- [x] `.env.production` created with port 8203, 8202
- [x] Settings model updated with new fields
- [x] `extra="allow"` added to model config

**Databases:**
- [x] Development database created
- [x] Staging database created
- [x] Production database created
- [x] Migrations run successfully on dev

**Integration:**
- [x] Service ports aligned (8011, 8111, 8211)
- [x] Service discovery URLs configured
- [x] Ticker service shared across all envs (8080)

**Documentation:**
- [x] Multi-environment alignment documented
- [x] Startup procedures documented
- [x] Integration points documented

---

## 🎯 Next Steps

1. **Run migrations on staging and production** (when ready):
   ```bash
   # Staging
   cp .env.staging .env
   alembic upgrade head

   # Production
   cp .env.production .env
   alembic upgrade head
   ```

2. **Start user_service in all environments:**
   ```bash
   # Dev
   uvicorn app.main:app --host 0.0.0.0 --port 8011 --reload &

   # Staging
   uvicorn app.main:app --host 127.0.0.1 --port 8111 &

   # Production
   uvicorn app.main:app --host 127.0.0.1 --port 8211 &
   ```

3. **Update backend to use USER_SERVICE_URL**

4. **Test cross-service communication:**
   - Backend → User Service authentication
   - Backend → User Service account access
   - API key verification flow

---

## 📞 Coordination with Other Services

**Message for Backend Team:**

The user_service is now available on environment-specific ports:
- Dev: `http://localhost:8011`
- Staging: `http://localhost:8111`
- Production: `http://localhost:8211`

**Key Endpoints:**
- `GET /v1/users/me` - Get current user profile
- `GET /v1/users/me/accounts` - List accessible trading accounts (new!)
- `POST /v1/api-keys` - Generate API key
- `GET /v1/api-keys` - List user's API keys

**Authentication Methods:**
1. JWT Bearer token in `Authorization` header
2. API key in `X-API-Key` header

---

**END OF MULTI-ENVIRONMENT ALIGNMENT DOCUMENT**
