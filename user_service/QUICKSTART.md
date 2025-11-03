# User Service - Quick Start Guide

This guide will help you get the user_service running and test the authentication endpoints.

## Prerequisites

- PostgreSQL 15+ with TimescaleDB extension
- Redis 7+
- Python 3.11+
- Database: `stocksblitz_unified`

## Step 1: Environment Setup

```bash
cd user_service
cp .env.example .env
```

Edit `.env` with your local settings:

```bash
# Database
DATABASE_URL=postgresql://stocksblitz:stocksblitz123@localhost:5432/stocksblitz_unified

# Redis
REDIS_URL=redis://localhost:6379/2

# JWT (will be generated in Step 3)
JWT_SIGNING_KEY_ID=key_2025_11_03_0000

# CORS
CORS_ALLOWED_ORIGINS=["http://localhost:3000","http://localhost:5173"]

# Session
SESSION_COOKIE_NAME=__Secure-refresh_token
SESSION_COOKIE_SECURE=false  # Set to true in production with HTTPS
```

## Step 2: Install Dependencies

```bash
pip install -r requirements.txt
```

## Step 3: Database Setup

### Run Alembic Migrations

```bash
# Apply all migrations
alembic upgrade head
```

This will:
- Create all 10 database tables
- Seed default roles (user, admin, compliance)
- Seed authorization policies
- Create OAuth clients for services

### Setup TimescaleDB Hypertable

```bash
# Connect to database
psql -U stocksblitz -d stocksblitz_unified

# Run TimescaleDB setup script
\i scripts/setup_timescaledb.sql

# Verify hypertable was created
SELECT * FROM timescaledb_information.hypertables WHERE hypertable_name = 'auth_events';

# Exit psql
\q
```

## Step 4: Generate JWT Signing Key

```bash
python scripts/generate_jwt_key.py
```

This will:
- Generate a new RSA-4096 key pair
- Store it in the database
- Output a key_id (e.g., `key_2025_11_03_0000`)

**IMPORTANT**: Copy the key_id to your `.env` file:

```bash
JWT_SIGNING_KEY_ID=key_2025_11_03_0000
```

## Step 5: Start the Service

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8001
```

You should see:

```
Starting user_service v1.0.0
Environment: development
INFO:     Uvicorn running on http://0.0.0.0:8001
```

## Step 6: Verify Service Health

Open your browser or use curl:

```bash
# Health check
curl http://localhost:8001/health

# Root endpoint
curl http://localhost:8001/

# JWKS endpoint (public keys for JWT validation)
curl http://localhost:8001/v1/auth/.well-known/jwks.json
```

## Step 7: Access API Documentation

Open your browser to:

```
http://localhost:8001/docs
```

This will show the interactive Swagger UI with all authentication endpoints.

## Step 8: Test Authentication Flow

### 1. Register a New User

```bash
curl -X POST http://localhost:8001/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "SecurePass123!@#",
    "name": "Test User",
    "timezone": "UTC",
    "locale": "en-US"
  }'
```

Expected response:

```json
{
  "user_id": 1,
  "email": "test@example.com",
  "status": "pending_verification",
  "verification_email_sent": false,
  "created_at": "2025-11-03T..."
}
```

### 2. Login

```bash
curl -X POST http://localhost:8001/v1/auth/login \
  -H "Content-Type: application/json" \
  -c cookies.txt \
  -d '{
    "email": "test@example.com",
    "password": "SecurePass123!@#",
    "persist_session": true
  }'
```

Expected response:

```json
{
  "access_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6ImtleV8yMDI1...",
  "token_type": "Bearer",
  "expires_in": 900,
  "user": {
    "user_id": 1,
    "email": "test@example.com",
    "name": "Test User",
    "roles": ["user"],
    "mfa_enabled": false
  }
}
```

**Note**: The refresh token is set in an HTTP-only cookie (`__Secure-refresh_token`)

### 3. Access Protected Endpoint

```bash
# Get active sessions (requires authentication)
curl http://localhost:8001/v1/auth/sessions \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN_HERE"
```

Expected response:

```json
{
  "sessions": [
    {
      "session_id": "sid_abc123...",
      "device_fingerprint": "...",
      "ip": "127.0.0.1",
      "country": null,
      "created_at": "2025-11-03T...",
      "last_active_at": "2025-11-03T...",
      "current": true
    }
  ],
  "total": 1
}
```

### 4. Refresh Access Token

```bash
curl -X POST http://localhost:8001/v1/auth/refresh \
  -b cookies.txt \
  -c cookies.txt
```

Expected response:

```json
{
  "access_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6ImtleV8yMDI1...",
  "refresh_token": "[set in cookie]",
  "token_type": "Bearer",
  "expires_in": 900
}
```

**Note**: The old refresh token is automatically rotated, and a new one is set in the cookie.

### 5. Logout

```bash
curl -X POST http://localhost:8001/v1/auth/logout \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN_HERE" \
  -H "Content-Type: application/json" \
  -b cookies.txt \
  -d '{
    "all_devices": false
  }'
```

Expected response:

```json
{
  "message": "Logged out successfully",
  "sessions_revoked": 1
}
```

## Endpoint Summary

### Public Endpoints (No Authentication)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/v1/auth/register` | Register new user |
| POST | `/v1/auth/login` | Login with email/password |
| POST | `/v1/auth/mfa/verify` | Verify MFA code (if MFA enabled) |
| GET | `/v1/auth/.well-known/jwks.json` | Get public keys for JWT validation |

### Protected Endpoints (Require Authentication)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/v1/auth/refresh` | Refresh access token using cookie |
| POST | `/v1/auth/logout` | Logout and invalidate session |
| GET | `/v1/auth/sessions` | List active sessions |

## Token Details

### Access Token (JWT)
- **Lifetime**: 15 minutes
- **Algorithm**: RS256 (RSA signature)
- **Claims**:
  - `sub`: User ID (`user:123`)
  - `sid`: Session ID
  - `roles`: User roles array
  - `acct_ids`: Trading account IDs
  - `mfa`: MFA verification status
  - `exp`: Expiration timestamp
  - `iss`: Issuer (`user_service`)

### Refresh Token
- **Lifetime**: 90 days
- **Storage**: HTTP-only, secure, SameSite=strict cookie
- **Rotation**: Automatically rotated on every use
- **Reuse Detection**: Using an old refresh token triggers security alert and session revocation

## Security Features

✅ **Rate Limiting**
- Login: 5 attempts per 15 minutes
- Register: 5 attempts per hour per IP
- Refresh: 10 attempts per minute

✅ **Password Requirements**
- Minimum 12 characters
- Must contain: uppercase, lowercase, digit, special character
- zxcvbn strength score ≥ 2
- Not in common password list

✅ **Session Security**
- Device fingerprinting (user agent + IP hash)
- IP address tracking
- Session TTL and inactivity timeout
- Anomaly detection (risk scoring)

✅ **Audit Logging**
- All authentication events logged to TimescaleDB
- Events: `login.success`, `login.failed`, `logout`, `token.refreshed`, `refresh.reuse_detected`
- Immutable audit trail with 2-year retention

## Troubleshooting

### Service won't start

**Error**: `JWT signing key not found`
**Solution**: Run `python scripts/generate_jwt_key.py` and update `.env`

**Error**: `Cannot connect to database`
**Solution**: Check DATABASE_URL in `.env` and verify PostgreSQL is running

**Error**: `Cannot connect to Redis`
**Solution**: Check REDIS_URL in `.env` and verify Redis is running

### Database issues

**Error**: `relation "users" does not exist`
**Solution**: Run migrations: `alembic upgrade head`

**Error**: `hypertable does not exist`
**Solution**: Run TimescaleDB setup: `psql -U stocksblitz -d stocksblitz_unified -f scripts/setup_timescaledb.sql`

### Authentication issues

**Error**: `401 Unauthorized`
**Solution**: Check that access token is not expired (15 min lifetime)

**Error**: `429 Rate limit exceeded`
**Solution**: Wait for rate limit window to expire (15 min for login)

**Error**: `Refresh token reuse detected`
**Solution**: This is a security violation - login again to create a new session

## Next Steps

Once you've verified the authentication endpoints work:

1. **Implement Authorization Service** - Policy evaluation engine and `/authz/check` endpoint
2. **Add User Profile Endpoints** - GET/PATCH `/users/me`, preferences management
3. **Implement MFA/TOTP** - Currently accepts any 6-digit code (placeholder)
4. **Add Trading Account Management** - Link broker accounts with encrypted credentials
5. **Setup Event Publishing** - Redis pub/sub for service integration
6. **Add Docker Compose** - Container orchestration for local development

## Documentation

- `README.md` - Project overview
- `IMPLEMENTATION_STATUS.md` - Detailed progress tracker
- `PROGRESS_SUMMARY.md` - Comprehensive implementation summary
- `USER_SERVICE_PHASE_1_DESIGN.md` - Complete architecture and API design

## Support

For issues or questions, check the progress documents or review the inline code documentation (all functions have comprehensive docstrings).
