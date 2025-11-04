# Phase 1: user_service Implementation Design

**Document Version:** 1.0
**Date:** 2025-11-03
**Status:** Design Complete - Ready for Implementation
**Based On:** USER_SERVICE_PHASE_0_ANALYSIS.md

---

## Executive Summary

This document provides the complete implementation design for the `user_service` microservice. Based on the Phase 0 analysis, this service will be the **central identity, authentication, and authorization provider** for the trading platform.

**Service Responsibilities:**
- User identity lifecycle (registration, verification, deactivation)
- Authentication (email/password, OAuth, MFA)
- Session management (access tokens, refresh tokens, stay-signed-in)
- Authorization (RBAC + ABAC policy decision point)
- Trading account credential management (vault/KMS integration)
- User profiles and preferences
- Audit logging for compliance (GDPR/DPDP)
- Event publishing for service integration

**Technology Stack:**
- **Language:** Python 3.11+
- **Framework:** FastAPI 0.104+
- **Database:** PostgreSQL 15+ (via TimescaleDB)
- **Cache/Sessions:** Redis 7+
- **Token Format:** JWT (RS256)
- **Encryption:** AWS KMS or HashiCorp Vault (configurable)
- **Event Bus:** Redis Pub/Sub
- **Deployment:** Docker + Docker Compose

---

## Table of Contents

1. [API Specifications](#1-api-specifications)
2. [Data Models](#2-data-models)
3. [Event Schemas](#3-event-schemas)
4. [Security Architecture](#4-security-architecture)
5. [Infrastructure Configuration](#5-infrastructure-configuration)
6. [Observability](#6-observability)
7. [Deployment & Rollout](#7-deployment--rollout)
8. [Testing Strategy](#8-testing-strategy)
9. [Migration Plan](#9-migration-plan)

---

## 1. API Specifications

### 1.1 API Design Principles

- **RESTful:** HTTP verbs (GET, POST, PUT, DELETE, PATCH)
- **Versioning:** URL-based (`/v1/auth/login`)
- **Idempotency:** `Idempotency-Key` header for mutations
- **Rate Limiting:** `X-RateLimit-*` headers
- **Pagination:** Cursor-based with `?cursor=` and `?limit=`
- **Errors:** RFC 7807 Problem Details format

### 1.2 Authentication Endpoints

#### POST /v1/auth/register

**Description:** Register a new user account

**Request:**
```json
{
  "email": "user@example.com",
  "password": "SecurePass123!",
  "name": "John Doe",
  "phone": "+919876543210",
  "timezone": "Asia/Kolkata",
  "locale": "en-IN"
}
```

**Response:** `201 Created`
```json
{
  "user_id": 123,
  "email": "user@example.com",
  "status": "pending_verification",
  "verification_email_sent": true,
  "created_at": "2025-11-03T10:00:00Z"
}
```

**Errors:**
- `400` - Invalid email/password format
- `409` - Email already registered
- `429` - Rate limit exceeded (5 registrations per IP per hour)

**Rate Limits:** 5 req/hour per IP

---

#### POST /v1/auth/login

**Description:** Authenticate user with email/password

**Request:**
```json
{
  "email": "user@example.com",
  "password": "SecurePass123!",
  "persist_session": true,
  "device_fingerprint": "abc123def456"
}
```

**Response:** `200 OK` (MFA not required)
```json
{
  "access_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "Bearer",
  "expires_in": 900,
  "user": {
    "user_id": 123,
    "email": "user@example.com",
    "name": "John Doe",
    "roles": ["user"],
    "mfa_enabled": false
  }
}
```

**Response:** `200 OK` (MFA required)
```json
{
  "status": "mfa_required",
  "session_token": "temp_abc123",
  "methods": ["totp"],
  "message": "MFA verification required"
}
```

**Errors:**
- `401` - Invalid credentials
- `423` - Account locked (too many failed attempts)
- `429` - Rate limit exceeded (5 attempts per email per 15 min)

**Rate Limits:** 5 req/15min per email

**Set-Cookie:** `__Secure-refresh_token` (if `persist_session: true`)

---

#### POST /v1/auth/mfa/verify

**Description:** Verify TOTP code after initial login

**Request:**
```json
{
  "session_token": "temp_abc123",
  "code": "123456"
}
```

**Response:** `200 OK`
```json
{
  "access_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "Bearer",
  "expires_in": 900,
  "user": {
    "user_id": 123,
    "email": "user@example.com",
    "name": "John Doe",
    "roles": ["user"],
    "mfa_enabled": true
  }
}
```

**Errors:**
- `401` - Invalid code or session_token
- `429` - Too many attempts (3 per session_token)

**Rate Limits:** 3 req/session_token

**Set-Cookie:** `__Secure-refresh_token`

---

#### POST /v1/auth/refresh

**Description:** Refresh access token using refresh token

**Request:** Empty body (refresh token in cookie)

**Response:** `200 OK`
```json
{
  "access_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "Bearer",
  "expires_in": 900
}
```

**Errors:**
- `401` - Invalid or expired refresh token
- `401` - Refresh token reuse detected (security violation)
- `429` - Too many refresh requests (10 per session per min)

**Rate Limits:** 10 req/min per session

**Set-Cookie:** `__Secure-refresh_token` (new rotated token)

---

#### POST /v1/auth/logout

**Description:** Invalidate current session

**Headers:** `Authorization: Bearer <access_token>`

**Request:**
```json
{
  "all_devices": false
}
```

**Response:** `200 OK`
```json
{
  "message": "Logged out successfully",
  "sessions_revoked": 1
}
```

**Errors:**
- `401` - Invalid or expired token

---

#### GET /v1/auth/sessions

**Description:** List all active sessions for current user

**Headers:** `Authorization: Bearer <access_token>`

**Response:** `200 OK`
```json
{
  "sessions": [
    {
      "session_id": "sid_abc123",
      "device_fingerprint": "abc123",
      "ip": "203.0.113.1",
      "country": "IN",
      "created_at": "2025-11-01T10:00:00Z",
      "last_active_at": "2025-11-03T10:00:00Z",
      "current": true
    }
  ],
  "total": 1
}
```

---

#### POST /v1/auth/password/reset-request

**Description:** Request password reset email

**Request:**
```json
{
  "email": "user@example.com"
}
```

**Response:** `200 OK` (always, even if email doesn't exist)
```json
{
  "message": "If this email is registered, you will receive a password reset link."
}
```

**Rate Limits:** 3 req/hour per email

---

#### POST /v1/auth/password/reset

**Description:** Reset password with magic link token

**Request:**
```json
{
  "token": "reset_token_abc123",
  "new_password": "NewSecurePass123!"
}
```

**Response:** `200 OK`
```json
{
  "message": "Password reset successfully",
  "sessions_revoked": 5
}
```

**Errors:**
- `400` - Invalid or expired token
- `400` - Weak password

---

#### POST /v1/auth/google

**Description:** Initiate Google OAuth flow

**Request:**
```json
{
  "redirect_uri": "https://app.example.com/auth/callback"
}
```

**Response:** `200 OK`
```json
{
  "authorization_url": "https://accounts.google.com/o/oauth2/v2/auth?...",
  "state": "state_abc123"
}
```

---

#### POST /v1/auth/google/callback

**Description:** Complete Google OAuth flow

**Request:**
```json
{
  "code": "oauth_code_abc123",
  "state": "state_abc123"
}
```

**Response:** `200 OK`
```json
{
  "access_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "Bearer",
  "expires_in": 900,
  "user": {
    "user_id": 123,
    "email": "user@example.com",
    "name": "John Doe",
    "oauth_provider": "google"
  }
}
```

**Errors:**
- `400` - Invalid code or state

**Set-Cookie:** `__Secure-refresh_token`

---

### 1.3 Authorization Endpoints

#### POST /v1/authz/check

**Description:** Policy decision point for authorization

**Headers:** `Authorization: Bearer <service_token>`

**Request:**
```json
{
  "subject": "user:123",
  "action": "trade:place_order",
  "resource": "trading_account:456",
  "context": {
    "ip": "203.0.113.1",
    "time": "2025-11-03T10:00:00Z"
  }
}
```

**Response:** `200 OK`
```json
{
  "decision": "allow",
  "reason": "user is owner of trading_account:456",
  "ttl": 60,
  "evaluated_at": "2025-11-03T10:00:00Z"
}
```

**Errors:**
- `401` - Invalid service token
- `403` - Access denied

**Rate Limits:** 1000 req/sec per service

---

#### GET /v1/authz/policies

**Description:** List authorization policies (admin only)

**Headers:** `Authorization: Bearer <admin_token>`

**Response:** `200 OK`
```json
{
  "policies": [
    {
      "policy_id": "pol_001",
      "name": "Trading Account Owner Can Trade",
      "effect": "allow",
      "subjects": ["user:*"],
      "actions": ["trade:*"],
      "resources": ["trading_account:*"],
      "conditions": {
        "owner": true
      }
    }
  ],
  "total": 1
}
```

---

### 1.4 OAuth 2.0 Endpoints

#### POST /v1/oauth/token

**Description:** OAuth 2.0 token endpoint

**Request (client_credentials):**
```json
{
  "grant_type": "client_credentials",
  "client_id": "service_ticker",
  "client_secret": "secret_xyz",
  "scope": "authz:check"
}
```

**Response:** `200 OK`
```json
{
  "access_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "Bearer",
  "expires_in": 3600,
  "scope": "authz:check"
}
```

---

#### POST /v1/oauth/introspect

**Description:** Introspect access token

**Headers:** `Authorization: Bearer <service_token>`

**Request:**
```json
{
  "token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

**Response:** `200 OK`
```json
{
  "active": true,
  "sub": "user:123",
  "sid": "sid_abc123",
  "scp": ["read", "trade"],
  "roles": ["user"],
  "acct_ids": [1, 2, 3],
  "mfa": true,
  "exp": 1730635200,
  "iat": 1730634300
}
```

**Rate Limits:** 500 req/sec per service

---

#### GET /v1/.well-known/jwks.json

**Description:** JSON Web Key Set (public keys for JWT validation)

**Response:** `200 OK`
```json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "key_2025_11_03",
      "use": "sig",
      "alg": "RS256",
      "n": "0vx7agoebGcQSuuPiLJXZptN9nndrQmbXEps2aiAFbWhM78LhWx...",
      "e": "AQAB"
    }
  ]
}
```

---

### 1.5 User & Profile Endpoints

#### GET /v1/users/me

**Description:** Get current user profile

**Headers:** `Authorization: Bearer <access_token>`

**Response:** `200 OK`
```json
{
  "user_id": 123,
  "email": "user@example.com",
  "name": "John Doe",
  "phone": "+919876543210",
  "timezone": "Asia/Kolkata",
  "locale": "en-IN",
  "roles": ["user"],
  "mfa_enabled": true,
  "email_verified": true,
  "status": "active",
  "created_at": "2025-11-01T10:00:00Z",
  "updated_at": "2025-11-03T10:00:00Z"
}
```

---

#### PATCH /v1/users/me

**Description:** Update current user profile

**Headers:** `Authorization: Bearer <access_token>`

**Request:**
```json
{
  "name": "John Smith",
  "timezone": "America/New_York",
  "locale": "en-US"
}
```

**Response:** `200 OK`
```json
{
  "user_id": 123,
  "email": "user@example.com",
  "name": "John Smith",
  "timezone": "America/New_York",
  "locale": "en-US",
  "updated_at": "2025-11-03T10:05:00Z"
}
```

---

#### GET /v1/users/{user_id}

**Description:** Get user by ID (admin or self)

**Headers:** `Authorization: Bearer <access_token>`

**Response:** `200 OK` (same as /users/me)

**Errors:**
- `403` - Not authorized to view this user
- `404` - User not found

---

#### GET /v1/users/me/preferences

**Description:** Get user preferences

**Headers:** `Authorization: Bearer <access_token>`

**Response:** `200 OK`
```json
{
  "user_id": 123,
  "preferences": {
    "watchlist": {
      "nifty_options": ["NIFTY25300CE", "NIFTY25300PE"]
    },
    "default_trading_account_id": 456,
    "theme": "dark",
    "notifications": {
      "email": true,
      "telegram": true
    }
  },
  "updated_at": "2025-11-03T10:00:00Z"
}
```

---

#### PUT /v1/users/me/preferences

**Description:** Update user preferences

**Headers:** `Authorization: Bearer <access_token>`

**Request:**
```json
{
  "preferences": {
    "watchlist": {
      "nifty_options": ["NIFTY25350CE"]
    },
    "default_trading_account_id": 789
  }
}
```

**Response:** `200 OK`
```json
{
  "user_id": 123,
  "preferences": {
    "watchlist": {
      "nifty_options": ["NIFTY25350CE"]
    },
    "default_trading_account_id": 789
  },
  "updated_at": "2025-11-03T10:05:00Z"
}
```

**Errors:**
- `403` - default_trading_account_id not owned by user

---

#### POST /v1/users/{user_id}/deactivate

**Description:** Deactivate user account (admin only)

**Headers:** `Authorization: Bearer <admin_token>`

**Request:**
```json
{
  "reason": "user_request",
  "gdpr_export": true
}
```

**Response:** `200 OK`
```json
{
  "user_id": 123,
  "status": "deactivated",
  "export_url": "https://exports.example.com/user_123.json?sig=...",
  "data_deletion_scheduled": "2025-12-03T10:00:00Z",
  "sessions_revoked": 3
}
```

---

### 1.6 MFA Management Endpoints

#### POST /v1/mfa/totp/enroll

**Description:** Enroll TOTP authenticator

**Headers:** `Authorization: Bearer <access_token>`

**Response:** `200 OK`
```json
{
  "secret": "JBSWY3DPEHPK3PXP",
  "qr_code_url": "data:image/png;base64,iVBORw0KGgo...",
  "backup_codes": [
    "12345678",
    "87654321",
    "11111111"
  ]
}
```

---

#### POST /v1/mfa/totp/confirm

**Description:** Confirm TOTP enrollment

**Headers:** `Authorization: Bearer <access_token>`

**Request:**
```json
{
  "code": "123456"
}
```

**Response:** `200 OK`
```json
{
  "mfa_enabled": true,
  "methods": ["totp"]
}
```

**Errors:**
- `400` - Invalid code

---

#### DELETE /v1/mfa/totp

**Description:** Disable TOTP (requires password confirmation)

**Headers:** `Authorization: Bearer <access_token>`

**Request:**
```json
{
  "password": "SecurePass123!"
}
```

**Response:** `200 OK`
```json
{
  "mfa_enabled": false,
  "methods": []
}
```

---

### 1.7 Trading Account Endpoints

#### GET /v1/trading-accounts

**Description:** List user's trading accounts

**Headers:** `Authorization: Bearer <access_token>`

**Response:** `200 OK`
```json
{
  "trading_accounts": [
    {
      "trading_account_id": 456,
      "broker": "kite",
      "nickname": "My Kite Account",
      "status": "active",
      "ownership": "owner",
      "broker_profile": {
        "name": "John Doe",
        "email": "user@example.com",
        "broker_user_id": "ABC123"
      },
      "credentials_masked": {
        "api_key": "abc***xyz"
      },
      "linked_at": "2025-11-01T10:00:00Z",
      "last_synced_at": "2025-11-03T09:00:00Z"
    }
  ],
  "total": 1
}
```

---

#### POST /v1/trading-accounts/link

**Description:** Link a new trading account

**Headers:**
- `Authorization: Bearer <access_token>`
- `Idempotency-Key: uuid-abc-123`

**Request:**
```json
{
  "broker": "kite",
  "nickname": "My Kite Account",
  "credentials": {
    "api_key": "your_kite_api_key",
    "api_secret": "your_kite_api_secret",
    "totp_seed": "JBSWY3DPEHPK3PXP",
    "username": "AB1234",
    "password": "your_password"
  }
}
```

**Response:** `201 Created`
```json
{
  "trading_account_id": 456,
  "broker": "kite",
  "nickname": "My Kite Account",
  "status": "active",
  "broker_profile": {
    "name": "John Doe",
    "email": "user@example.com",
    "broker_user_id": "ABC123"
  },
  "linked_at": "2025-11-03T10:00:00Z"
}
```

**Errors:**
- `400` - Invalid credentials
- `403` - MFA required (token must have mfa: true claim)
- `409` - Account already linked
- `504` - Broker API timeout

**Rate Limits:** 5 req/hour per user

---

#### POST /v1/trading-accounts/{account_id}/rotate-credentials

**Description:** Rotate trading account credentials

**Headers:** `Authorization: Bearer <access_token>`

**Request:**
```json
{
  "new_credentials": {
    "api_key": "new_kite_api_key",
    "api_secret": "new_kite_api_secret"
  }
}
```

**Response:** `200 OK`
```json
{
  "trading_account_id": 456,
  "status": "active",
  "credentials_rotated_at": "2025-11-03T10:00:00Z"
}
```

**Errors:**
- `403` - MFA required

---

#### POST /v1/trading-accounts/{account_id}/memberships

**Description:** Share trading account with another user

**Headers:** `Authorization: Bearer <access_token>`

**Request:**
```json
{
  "member_user_id": 789,
  "permissions": ["read", "trade"]
}
```

**Response:** `201 Created`
```json
{
  "membership_id": 101,
  "trading_account_id": 456,
  "member_user_id": 789,
  "permissions": ["read", "trade"],
  "granted_at": "2025-11-03T10:00:00Z"
}
```

**Errors:**
- `403` - Must be account owner
- `404` - User not found

---

#### DELETE /v1/trading-accounts/{account_id}/memberships/{membership_id}

**Description:** Revoke shared access

**Headers:** `Authorization: Bearer <access_token>`

**Response:** `204 No Content`

---

#### GET /v1/trading-accounts/{account_id}/permissions/check

**Description:** Check permissions for trading account (service-to-service)

**Headers:** `Authorization: Bearer <service_token>`

**Query:** `?user_id=123&action=trade:place_order`

**Response:** `200 OK`
```json
{
  "allowed": true,
  "ownership": "owner",
  "permissions": ["read", "trade"]
}
```

---

### 1.8 Internal Service Endpoints (Not Public)

#### POST /v1/internal/trading-accounts/{account_id}/credentials

**Description:** Fetch decrypted credentials (ticker_service only)

**Headers:** `Authorization: Bearer <service_token>`

**Response:** `200 OK`
```json
{
  "trading_account_id": 456,
  "broker": "kite",
  "credentials": {
    "api_key": "your_kite_api_key",
    "api_secret": "your_kite_api_secret",
    "totp_seed": "JBSWY3DPEHPK3PXP",
    "access_token": "live_kite_session_token"
  },
  "fetched_at": "2025-11-03T10:00:00Z"
}
```

**Security:**
- Only accessible from ticker_service IP range
- mTLS required
- Rate limited: 10 req/sec per account
- Never logged

---

### 1.9 Admin & Audit Endpoints

#### GET /v1/audit/events

**Description:** Query audit logs (admin or compliance role)

**Headers:** `Authorization: Bearer <admin_token>`

**Query:** `?user_id=123&event_type=login&from=2025-11-01&to=2025-11-03&limit=100`

**Response:** `200 OK`
```json
{
  "events": [
    {
      "event_id": "evt_abc123",
      "user_id": 123,
      "event_type": "login.success",
      "ip": "203.0.113.1",
      "country": "IN",
      "device_fingerprint": "abc123",
      "timestamp": "2025-11-03T10:00:00Z",
      "metadata": {
        "mfa_used": true
      }
    }
  ],
  "cursor": "cursor_next_page",
  "has_more": true
}
```

---

#### POST /v1/audit/export

**Description:** Export audit logs for compliance (GDPR)

**Headers:** `Authorization: Bearer <compliance_token>`

**Request:**
```json
{
  "user_id": 123,
  "format": "json",
  "include_pii": false
}
```

**Response:** `200 OK`
```json
{
  "export_url": "https://exports.example.com/audit_user_123.json?sig=...",
  "expires_at": "2025-11-04T10:00:00Z"
}
```

---

#### POST /v1/admin/trading-accounts/sync-profiles

**Description:** Sync all broker profiles (scheduled job)

**Headers:** `Authorization: Bearer <admin_service_token>`

**Request:**
```json
{
  "batch_size": 100,
  "force": false
}
```

**Response:** `200 OK`
```json
{
  "accounts_synced": 95,
  "accounts_failed": 5,
  "duration_seconds": 120,
  "next_cursor": "cursor_abc"
}
```

---

### 1.10 Health & Metadata Endpoints

#### GET /health

**Description:** Health check

**Response:** `200 OK`
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "checks": {
    "database": "healthy",
    "redis": "healthy",
    "kms": "healthy"
  }
}
```

---

#### GET /metrics

**Description:** Prometheus metrics

**Response:** `200 OK` (text/plain)
```
# HELP user_service_requests_total Total requests
# TYPE user_service_requests_total counter
user_service_requests_total{method="POST",endpoint="/v1/auth/login",status="200"} 12345
```

---

### 1.11 Error Response Format

All errors follow RFC 7807 Problem Details:

```json
{
  "type": "https://docs.example.com/errors/invalid-credentials",
  "title": "Invalid Credentials",
  "status": 401,
  "detail": "The provided email or password is incorrect.",
  "instance": "/v1/auth/login",
  "trace_id": "abc123def456"
}
```

---

## 2. Data Models

### 2.1 PostgreSQL Schema

#### Table: users

```sql
CREATE TABLE users (
    user_id BIGSERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    email_verified BOOLEAN DEFAULT FALSE,
    password_hash VARCHAR(255),  -- bcrypt, NULL for OAuth-only users
    name VARCHAR(255) NOT NULL,
    phone VARCHAR(20),
    phone_verified BOOLEAN DEFAULT FALSE,
    timezone VARCHAR(50) DEFAULT 'UTC',
    locale VARCHAR(10) DEFAULT 'en-US',
    status VARCHAR(50) DEFAULT 'pending_verification' CHECK (status IN ('pending_verification', 'active', 'suspended', 'deactivated')),
    mfa_enabled BOOLEAN DEFAULT FALSE,
    oauth_provider VARCHAR(50),  -- 'google', 'github', NULL for email
    oauth_subject VARCHAR(255),  -- Google user ID
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    deactivated_at TIMESTAMPTZ,
    last_login_at TIMESTAMPTZ
);

CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_status ON users(status);
CREATE INDEX idx_users_oauth ON users(oauth_provider, oauth_subject) WHERE oauth_provider IS NOT NULL;
```

---

#### Table: user_preferences

```sql
CREATE TABLE user_preferences (
    preference_id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    preferences JSONB NOT NULL DEFAULT '{}'::jsonb,
    default_trading_account_id BIGINT,  -- FK added later
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id)
);

CREATE INDEX idx_user_preferences_user_id ON user_preferences(user_id);
CREATE INDEX idx_user_preferences_jsonb ON user_preferences USING GIN(preferences);
```

---

#### Table: sessions

```sql
-- Stored in Redis, not PostgreSQL
-- Redis key: session:{sid}
-- Redis value (JSON):
{
  "user_id": 123,
  "device_fingerprint": "abc123",
  "ip": "203.0.113.1",
  "country": "IN",
  "created_at": "2025-11-03T10:00:00Z",
  "last_active_at": "2025-11-03T10:15:00Z"
}
-- Redis TTL: 90 days (absolute max) or 14 days inactivity
```

---

#### Table: refresh_token_families

```sql
-- Stored in Redis, not PostgreSQL
-- Redis key: refresh_family:{jti}
-- Redis value (JSON):
{
  "user_id": 123,
  "sid": "sid_abc123",
  "parent_jti": null,
  "rotated_to": null,  -- Set when rotated
  "issued_at": "2025-11-03T10:00:00Z"
}
-- Redis TTL: 90 days
```

---

#### Table: roles

```sql
CREATE TABLE roles (
    role_id SERIAL PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL,  -- 'user', 'admin', 'compliance'
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO roles (name, description) VALUES
    ('user', 'Standard user role'),
    ('admin', 'Administrator with full access'),
    ('compliance', 'Compliance officer with audit access');
```

---

#### Table: user_roles

```sql
CREATE TABLE user_roles (
    user_role_id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    role_id INT NOT NULL REFERENCES roles(role_id) ON DELETE CASCADE,
    granted_at TIMESTAMPTZ DEFAULT NOW(),
    granted_by BIGINT REFERENCES users(user_id),
    UNIQUE(user_id, role_id)
);

CREATE INDEX idx_user_roles_user_id ON user_roles(user_id);
```

---

#### Table: policies

```sql
CREATE TABLE policies (
    policy_id SERIAL PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL,
    effect VARCHAR(10) CHECK (effect IN ('allow', 'deny')) DEFAULT 'allow',
    subjects JSONB NOT NULL,  -- ['user:*', 'role:admin']
    actions JSONB NOT NULL,   -- ['trade:*', 'read:account']
    resources JSONB NOT NULL, -- ['trading_account:*']
    conditions JSONB DEFAULT '{}'::jsonb,  -- {"owner": true, "account_active": true}
    priority INT DEFAULT 0,
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_policies_enabled ON policies(enabled);
```

**Example policy:**
```json
{
  "name": "Trading Account Owner Can Trade",
  "effect": "allow",
  "subjects": ["user:*"],
  "actions": ["trade:place_order", "trade:cancel_order"],
  "resources": ["trading_account:*"],
  "conditions": {
    "owner": true,
    "account_status": "active"
  },
  "priority": 100
}
```

---

#### Table: trading_accounts

```sql
CREATE TABLE trading_accounts (
    trading_account_id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    broker VARCHAR(50) NOT NULL,  -- 'kite', 'zerodha', etc.
    nickname VARCHAR(255) NOT NULL,
    status VARCHAR(50) DEFAULT 'pending_verification' CHECK (status IN ('pending_verification', 'active', 'credentials_expired', 'deactivated')),
    broker_profile_snapshot JSONB,  -- {name, email, broker_user_id}
    credential_vault_ref VARCHAR(255) NOT NULL,  -- Reference to KMS/Vault
    data_key_wrapped TEXT NOT NULL,  -- Encrypted data key (envelope encryption)
    linked_at TIMESTAMPTZ DEFAULT NOW(),
    last_synced_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_trading_accounts_user_id ON trading_accounts(user_id);
CREATE INDEX idx_trading_accounts_status ON trading_accounts(status);
CREATE UNIQUE INDEX idx_trading_accounts_broker_user ON trading_accounts(broker, (broker_profile_snapshot->>'broker_user_id')) WHERE status = 'active';
```

---

#### Table: trading_account_memberships

```sql
CREATE TABLE trading_account_memberships (
    membership_id BIGSERIAL PRIMARY KEY,
    trading_account_id BIGINT NOT NULL REFERENCES trading_accounts(trading_account_id) ON DELETE CASCADE,
    member_user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    permissions JSONB NOT NULL DEFAULT '["read"]'::jsonb,  -- ['read', 'trade']
    granted_by BIGINT NOT NULL REFERENCES users(user_id),
    granted_at TIMESTAMPTZ DEFAULT NOW(),
    revoked_at TIMESTAMPTZ,
    UNIQUE(trading_account_id, member_user_id)
);

CREATE INDEX idx_memberships_account ON trading_account_memberships(trading_account_id);
CREATE INDEX idx_memberships_member ON trading_account_memberships(member_user_id);
```

---

#### Table: mfa_totp

```sql
CREATE TABLE mfa_totp (
    totp_id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    secret_encrypted TEXT NOT NULL,  -- Encrypted TOTP seed
    backup_codes_encrypted JSONB NOT NULL,  -- Encrypted backup codes
    verified BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    verified_at TIMESTAMPTZ,
    UNIQUE(user_id)
);
```

---

#### Table: auth_events (TimescaleDB Hypertable)

```sql
CREATE TABLE auth_events (
    event_id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id BIGINT REFERENCES users(user_id) ON DELETE SET NULL,
    event_type VARCHAR(100) NOT NULL,  -- 'login.success', 'login.failed', 'logout', 'mfa.verified', etc.
    ip INET,
    country VARCHAR(2),
    device_fingerprint VARCHAR(255),
    session_id VARCHAR(255),
    metadata JSONB,
    risk_score VARCHAR(20),  -- 'low', 'medium', 'high'
    timestamp TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    notification_sent BOOLEAN DEFAULT FALSE
);

-- Convert to hypertable
SELECT create_hypertable('auth_events', 'timestamp', chunk_time_interval => INTERVAL '7 days');

-- Indexes
CREATE INDEX idx_auth_events_user_id ON auth_events(user_id, timestamp DESC);
CREATE INDEX idx_auth_events_type ON auth_events(event_type, timestamp DESC);
CREATE INDEX idx_auth_events_session ON auth_events(session_id, timestamp DESC);
CREATE INDEX idx_auth_events_risk ON auth_events(risk_score) WHERE risk_score = 'high';

-- Retention policy (keep 2 years)
SELECT add_retention_policy('auth_events', INTERVAL '2 years');
```

---

#### Table: oauth_clients (Service Accounts)

```sql
CREATE TABLE oauth_clients (
    client_id VARCHAR(100) PRIMARY KEY,
    client_secret_hash VARCHAR(255) NOT NULL,  -- bcrypt
    name VARCHAR(255) NOT NULL,  -- 'ticker_service', 'alert_service'
    scopes JSONB NOT NULL DEFAULT '["authz:check"]'::jsonb,
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_used_at TIMESTAMPTZ
);

INSERT INTO oauth_clients (client_id, client_secret_hash, name, scopes) VALUES
    ('service_ticker', '$2b$12$...', 'Ticker Service', '["authz:check", "credentials:read"]'),
    ('service_alert', '$2b$12$...', 'Alert Service', '["authz:check"]'),
    ('service_backend', '$2b$12$...', 'Backend Service', '["authz:check"]');
```

---

#### Table: jwt_signing_keys

```sql
CREATE TABLE jwt_signing_keys (
    key_id VARCHAR(50) PRIMARY KEY,  -- 'key_2025_11_03'
    public_key TEXT NOT NULL,        -- PEM format
    private_key_encrypted TEXT NOT NULL,  -- Encrypted with KMS
    algorithm VARCHAR(10) DEFAULT 'RS256',
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    rotated_at TIMESTAMPTZ
);

-- Only one active key at a time
CREATE UNIQUE INDEX idx_jwt_keys_active ON jwt_signing_keys(active) WHERE active = TRUE;
```

---

### 2.2 Redis Schema

#### Sessions
```
Key: session:{sid}
Type: Hash
TTL: 90 days (absolute) or 14 days since last_active_at
Fields:
  user_id: 123
  device_fingerprint: abc123
  ip: 203.0.113.1
  country: IN
  created_at: 2025-11-03T10:00:00Z
  last_active_at: 2025-11-03T10:15:00Z
```

#### Refresh Token Families
```
Key: refresh_family:{jti}
Type: Hash
TTL: 90 days
Fields:
  user_id: 123
  sid: sid_abc123
  parent_jti: (null or parent jti)
  rotated_to: (null or new jti)
  issued_at: 2025-11-03T10:00:00Z
```

#### Authorization Decision Cache
```
Key: authz_decision:{user_id}:{resource}:{action}
Type: String
Value: allow | deny
TTL: 60 seconds
```

#### Rate Limiting
```
Key: ratelimit:{endpoint}:{identifier}
Type: String
Value: request count
TTL: varies (e.g., 900s for 15 min window)
```

#### Password Reset Tokens
```
Key: password_reset:{token}
Type: Hash
TTL: 1 hour
Fields:
  user_id: 123
  created_at: 2025-11-03T10:00:00Z
```

#### OAuth State (CSRF protection)
```
Key: oauth_state:{state}
Type: String
Value: redirect_uri
TTL: 10 minutes
```

---

## 3. Event Schemas

### 3.1 Event Publishing Architecture

**Event Bus:** Redis Pub/Sub
**Format:** JSON
**Versioning:** `event_type@version` (e.g., `user.created@v1`)
**Delivery:** At-most-once (consumers must handle duplicates via idempotency)

---

### 3.2 Event Types

#### user.created@v1

```json
{
  "event_id": "evt_abc123",
  "event_type": "user.created@v1",
  "timestamp": "2025-11-03T10:00:00Z",
  "payload": {
    "user_id": 123,
    "email": "user@example.com",
    "name": "John Doe",
    "status": "pending_verification",
    "oauth_provider": null
  }
}
```

**Channel:** `user_service.user.created`

---

#### user.updated@v1

```json
{
  "event_id": "evt_abc124",
  "event_type": "user.updated@v1",
  "timestamp": "2025-11-03T10:05:00Z",
  "payload": {
    "user_id": 123,
    "changes": {
      "name": "John Smith",
      "timezone": "America/New_York"
    }
  }
}
```

**Channel:** `user_service.user.updated`

---

#### user.deactivated@v1

```json
{
  "event_id": "evt_abc125",
  "event_type": "user.deactivated@v1",
  "timestamp": "2025-11-03T10:10:00Z",
  "payload": {
    "user_id": 123,
    "reason": "user_request",
    "deactivated_by": 999,
    "gdpr_export_url": "https://exports.example.com/user_123.json"
  }
}
```

**Channel:** `user_service.user.deactivated`

**Consumers:** ticker_service, alert_service, backend, calendar_service

---

#### user.session.created@v1

```json
{
  "event_id": "evt_abc126",
  "event_type": "user.session.created@v1",
  "timestamp": "2025-11-03T10:00:00Z",
  "payload": {
    "user_id": 123,
    "session_id": "sid_abc123",
    "device_fingerprint": "abc123",
    "ip": "203.0.113.1",
    "country": "IN",
    "mfa_used": true
  }
}
```

**Channel:** `user_service.session.created`

**Consumers:** alert_service (for anomaly detection)

---

#### user.session.anomaly@v1

```json
{
  "event_id": "evt_abc127",
  "event_type": "user.session.anomaly@v1",
  "timestamp": "2025-11-03T10:00:00Z",
  "payload": {
    "user_id": 123,
    "session_id": "sid_abc123",
    "anomaly_type": "login.new_country",
    "risk_score": "high",
    "ip": "203.0.113.1",
    "country": "US",
    "previous_country": "IN"
  }
}
```

**Channel:** `user_service.session.anomaly`

**Consumers:** alert_service

---

#### user.preferences.updated@v1

```json
{
  "event_id": "evt_abc128",
  "event_type": "user.preferences.updated@v1",
  "timestamp": "2025-11-03T10:05:00Z",
  "payload": {
    "user_id": 123,
    "preferences": {
      "watchlist": {
        "nifty_options": ["NIFTY25350CE"]
      },
      "default_trading_account_id": 789
    }
  }
}
```

**Channel:** `user_service.preferences.updated`

**Consumers:** ticker_service, backend

---

#### trading_account.linked@v1

```json
{
  "event_id": "evt_abc129",
  "event_type": "trading_account.linked@v1",
  "timestamp": "2025-11-03T10:00:00Z",
  "payload": {
    "trading_account_id": 456,
    "user_id": 123,
    "broker": "kite",
    "nickname": "My Kite Account",
    "broker_profile": {
      "name": "John Doe",
      "email": "user@example.com",
      "broker_user_id": "ABC123"
    }
  }
}
```

**Channel:** `user_service.trading_account.linked`

**Consumers:** ticker_service, calendar_service

---

#### trading_account.profile.synced@v1

```json
{
  "event_id": "evt_abc130",
  "event_type": "trading_account.profile.synced@v1",
  "timestamp": "2025-11-03T09:00:00Z",
  "payload": {
    "trading_account_id": 456,
    "user_id": 123,
    "broker_profile": {
      "name": "John Doe",
      "email": "user@example.com",
      "broker_user_id": "ABC123"
    }
  }
}
```

**Channel:** `user_service.trading_account.synced`

**Consumers:** ticker_service, calendar_service

---

#### trading_account.credentials.invalid@v1

```json
{
  "event_id": "evt_abc131",
  "event_type": "trading_account.credentials.invalid@v1",
  "timestamp": "2025-11-03T09:00:00Z",
  "payload": {
    "trading_account_id": 456,
    "user_id": 123,
    "broker": "kite",
    "error": "login_failed"
  }
}
```

**Channel:** `user_service.trading_account.credentials_invalid`

**Consumers:** alert_service (notify user)

---

#### trading_account.membership.granted@v1

```json
{
  "event_id": "evt_abc132",
  "event_type": "trading_account.membership.granted@v1",
  "timestamp": "2025-11-03T10:00:00Z",
  "payload": {
    "membership_id": 101,
    "trading_account_id": 456,
    "owner_user_id": 123,
    "member_user_id": 789,
    "permissions": ["read", "trade"]
  }
}
```

**Channel:** `user_service.trading_account.membership_granted`

**Consumers:** ticker_service

---

#### permission.updated@v1

```json
{
  "event_id": "evt_abc133",
  "event_type": "permission.updated@v1",
  "timestamp": "2025-11-03T10:00:00Z",
  "payload": {
    "user_id": 123,
    "resource": "trading_account:456",
    "permissions_added": ["trade"],
    "permissions_removed": []
  }
}
```

**Channel:** `user_service.permission.updated`

**Consumers:** All services (invalidate authz cache)

---

### 3.3 Event Schema Validation

All events conform to this schema:

```json
{
  "event_id": "string (UUID)",
  "event_type": "string (type@version)",
  "timestamp": "string (ISO 8601)",
  "payload": "object (type-specific)"
}
```

Consumers must:
1. Validate `event_id` uniqueness (idempotency)
2. Parse `event_type` and version
3. Validate `payload` against JSON schema
4. Handle missing fields gracefully

---

## 4. Security Architecture

### 4.1 Credential Storage (Envelope Encryption)

**Strategy:** Envelope encryption with KMS
**Providers:** AWS KMS, HashiCorp Vault, or local (configurable)

**Flow:**
1. **Generate Data Key:**
   - For each trading account, generate unique 256-bit AES data key
   - Encrypt data key with KMS master key → `data_key_wrapped`

2. **Encrypt Credentials:**
   - Encrypt trading account credentials (api_key, api_secret, totp_seed, password) with data key using AES-256-GCM
   - Store `credential_vault_ref` (encrypted blob) and `data_key_wrapped` in DB

3. **Decrypt Credentials:**
   - Fetch `data_key_wrapped` from DB
   - Decrypt with KMS → plaintext data key
   - Decrypt credentials with data key
   - **Never cache plaintext credentials** (fetch on-demand)

**KMS Master Key Rotation:**
- Rotate master key annually
- Re-wrap all data keys (background job, zero downtime)

---

### 4.2 JWT Token Design

**Access Token:**
- **Format:** JWT (RS256)
- **TTL:** 15 minutes
- **Claims:**
  ```json
  {
    "iss": "https://user-service.example.com",
    "sub": "user:123",
    "aud": ["api.example.com"],
    "exp": 1730635200,
    "iat": 1730634300,
    "sid": "sid_abc123",
    "scp": ["read", "trade"],
    "roles": ["user"],
    "acct_ids": [456, 789],
    "mfa": true,
    "ver": 1
  }
  ```

**Refresh Token:**
- **Format:** JWT (RS256) or opaque token
- **TTL:** 90 days (rotating)
- **Storage:** HttpOnly, Secure, SameSite=Strict cookie
- **Claims:**
  ```json
  {
    "jti": "refresh_jti_abc123",
    "sub": "user:123",
    "sid": "sid_abc123",
    "exp": 1738411200,
    "iat": 1730635200
  }
  ```

**Service Token (OAuth 2.0 Client Credentials):**
- **Format:** JWT (RS256)
- **TTL:** 1 hour
- **Claims:**
  ```json
  {
    "iss": "https://user-service.example.com",
    "sub": "service:ticker",
    "aud": ["user-service.example.com"],
    "exp": 1730638800,
    "iat": 1730635200,
    "scp": ["authz:check", "credentials:read"],
    "ver": 1
  }
  ```

---

### 4.3 JWT Signing Key Management

**Key Rotation:**
- Generate new RSA-4096 key pair every 90 days
- Old keys retained for 180 days (for token validation)
- Active key marked in `jwt_signing_keys` table

**Private Key Storage:**
- Private key encrypted with KMS
- Decrypted only at service startup (cached in memory)

**Public Key Distribution:**
- Published at `/v1/.well-known/jwks.json`
- All services fetch JWKS on startup (cached for 1 hour, auto-refresh)

---

### 4.4 Password Policy

**Requirements:**
- Minimum 12 characters
- At least 1 uppercase, 1 lowercase, 1 digit, 1 special character
- Not in common password list (rockyou.txt)
- Not same as email prefix

**Hashing:**
- Algorithm: bcrypt
- Cost factor: 12 (2^12 iterations)

---

### 4.5 MFA (TOTP)

**TOTP Secret Storage:**
- Encrypted with KMS (same as trading account credentials)
- Stored in `mfa_totp.secret_encrypted`

**Backup Codes:**
- Generate 10 single-use codes
- Hashed with bcrypt
- Stored in `mfa_totp.backup_codes_encrypted`

**Time Window:**
- 30-second window (standard TOTP)
- Allow ±1 window for clock drift

---

### 4.6 Rate Limiting

**Algorithm:** Token bucket
**Storage:** Redis (per endpoint + identifier)

**Limits:**
- `/v1/auth/login`: 5 req/15min per email
- `/v1/auth/register`: 5 req/hour per IP
- `/v1/auth/refresh`: 10 req/min per session
- `/v1/authz/check`: 1000 req/sec per service
- `/v1/oauth/introspect`: 500 req/sec per service

**Headers:**
```
X-RateLimit-Limit: 5
X-RateLimit-Remaining: 3
X-RateLimit-Reset: 1730635200
```

---

### 4.7 CORS & CSP

**CORS:**
```python
ALLOWED_ORIGINS = [
    "https://app.example.com",
    "https://monitor.example.com"
]
ALLOW_CREDENTIALS = True
ALLOWED_METHODS = ["GET", "POST", "PUT", "DELETE", "PATCH"]
ALLOWED_HEADERS = ["Authorization", "Content-Type", "Idempotency-Key"]
```

**CSP (Content-Security-Policy):**
```
default-src 'self'; script-src 'self'; connect-src 'self' https://api.example.com
```

---

### 4.8 Threat Model (STRIDE)

| Threat | Mitigation |
|--------|------------|
| **Spoofing** | JWT signature validation, MFA, device fingerprinting |
| **Tampering** | HTTPS/TLS, JWT signature, database constraints |
| **Repudiation** | Audit logging (auth_events), immutable logs |
| **Information Disclosure** | Encryption at rest (KMS), TLS in transit, no credentials in logs |
| **Denial of Service** | Rate limiting, circuit breakers, autoscaling |
| **Elevation of Privilege** | RBAC + ABAC, `/authz/check` PDP, least privilege |

---

## 5. Infrastructure Configuration

### 5.1 Docker Compose Integration

**Service Name:** `user_service`

```yaml
version: '3.8'

services:
  user_service:
    build:
      context: ./user_service
      dockerfile: Dockerfile
    container_name: user_service
    ports:
      - "8001:8000"
    environment:
      - DATABASE_URL=postgresql://stocksblitz:stocksblitz123@timescaledb:5432/stocksblitz_unified
      - REDIS_URL=redis://redis:6379/2
      - KMS_PROVIDER=local  # or 'aws', 'vault'
      - KMS_MASTER_KEY_ID=local_master_key
      - JWT_SIGNING_KEY_ID=key_2025_11_03
      - LOG_LEVEL=INFO
      - ENVIRONMENT=development
    depends_on:
      - timescaledb
      - redis
    volumes:
      - ./user_service:/app
      - user_service_keys:/app/keys  # For local KMS
    networks:
      - stocksblitz_network
    restart: unless-stopped

volumes:
  user_service_keys:

networks:
  stocksblitz_network:
    external: true
```

---

### 5.2 Environment Variables (50+ config parameters)

**Database:**
```bash
DATABASE_URL=postgresql://user:pass@host:5432/db
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=10
DATABASE_POOL_TIMEOUT=30
```

**Redis:**
```bash
REDIS_URL=redis://host:6379/2
REDIS_POOL_SIZE=50
REDIS_SESSION_TTL_DAYS=90
REDIS_SESSION_INACTIVITY_DAYS=14
```

**JWT:**
```bash
JWT_SIGNING_KEY_ID=key_2025_11_03
JWT_ACCESS_TOKEN_TTL_MINUTES=15
JWT_REFRESH_TOKEN_TTL_DAYS=90
JWT_ALGORITHM=RS256
JWT_ISSUER=https://user-service.example.com
JWT_AUDIENCE=api.example.com
```

**KMS/Encryption:**
```bash
KMS_PROVIDER=aws  # or 'vault', 'local'
KMS_MASTER_KEY_ID=arn:aws:kms:us-east-1:123456789:key/abc
KMS_REGION=us-east-1
VAULT_URL=https://vault.example.com
VAULT_TOKEN=hvs.abc123
LOCAL_KMS_KEY_PATH=/app/keys/master.key
```

**OAuth Providers:**
```bash
GOOGLE_OAUTH_CLIENT_ID=abc123.apps.googleusercontent.com
GOOGLE_OAUTH_CLIENT_SECRET=secret_xyz
GOOGLE_OAUTH_REDIRECT_URI=https://app.example.com/auth/google/callback
```

**Email (for password reset):**
```bash
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=noreply@example.com
SMTP_PASSWORD=secret
SMTP_FROM=noreply@example.com
```

**Rate Limiting:**
```bash
RATELIMIT_LOGIN_ATTEMPTS=5
RATELIMIT_LOGIN_WINDOW_MINUTES=15
RATELIMIT_REGISTER_ATTEMPTS=5
RATELIMIT_REGISTER_WINDOW_HOURS=1
RATELIMIT_REFRESH_ATTEMPTS=10
RATELIMIT_REFRESH_WINDOW_MINUTES=1
```

**Security:**
```bash
PASSWORD_MIN_LENGTH=12
PASSWORD_BCRYPT_COST=12
MFA_TOTP_WINDOW_SECONDS=30
SESSION_COOKIE_NAME=__Secure-refresh_token
SESSION_COOKIE_SECURE=true
SESSION_COOKIE_HTTPONLY=true
SESSION_COOKIE_SAMESITE=Strict
```

**CORS:**
```bash
CORS_ALLOWED_ORIGINS=https://app.example.com,https://monitor.example.com
CORS_ALLOW_CREDENTIALS=true
```

**Logging & Observability:**
```bash
LOG_LEVEL=INFO  # DEBUG, INFO, WARNING, ERROR
LOG_FORMAT=json  # or 'text'
SENTRY_DSN=https://...@sentry.io/123
PROMETHEUS_PORT=9090
```

**Feature Flags:**
```bash
FEATURE_GOOGLE_OAUTH=true
FEATURE_MFA_TOTP=true
FEATURE_SHARED_ACCOUNTS=true
```

**External APIs:**
```bash
KITE_API_BASE_URL=https://api.kite.trade
KITE_API_TIMEOUT_SECONDS=10
KITE_API_MAX_RETRIES=3
```

**Service Discovery:**
```bash
TICKER_SERVICE_URL=http://ticker_service:8002
ALERT_SERVICE_URL=http://alert_service:8003
BACKEND_SERVICE_URL=http://backend:8000
```

---

### 5.3 TimescaleDB Setup

**Hypertables:**
```sql
-- auth_events (already defined in 2.1)
SELECT create_hypertable('auth_events', 'timestamp', chunk_time_interval => INTERVAL '7 days');
SELECT add_retention_policy('auth_events', INTERVAL '2 years');
```

**Continuous Aggregates (Optional):**
```sql
-- Daily login count per user
CREATE MATERIALIZED VIEW auth_events_daily
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 day', timestamp) AS day,
    user_id,
    COUNT(*) FILTER (WHERE event_type = 'login.success') AS login_count,
    COUNT(*) FILTER (WHERE event_type = 'login.failed') AS failed_login_count
FROM auth_events
GROUP BY day, user_id
WITH NO DATA;

SELECT add_continuous_aggregate_policy('auth_events_daily',
    start_offset => INTERVAL '3 days',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour');
```

---

### 5.4 Redis Keyspace Design

**Database Numbers:**
- DB 0: Backend (default)
- DB 1: Ticker Service
- **DB 2: User Service** ← Use this
- DB 3: Alert Service

**Key Prefixes:**
- `session:{sid}` - User sessions
- `refresh_family:{jti}` - Refresh token families
- `authz_decision:{user_id}:{resource}:{action}` - Authz cache
- `ratelimit:{endpoint}:{identifier}` - Rate limit counters
- `password_reset:{token}` - Password reset tokens
- `oauth_state:{state}` - OAuth CSRF state

**Memory Optimization:**
- Use Redis hashes for sessions (more efficient)
- Set TTLs on all keys
- Enable eviction policy: `allkeys-lru`

---

## 6. Observability

### 6.1 Prometheus Metrics

**Custom Metrics (20+):**

```python
# Authentication metrics
user_service_auth_requests_total = Counter(
    'user_service_auth_requests_total',
    'Total authentication requests',
    ['method', 'endpoint', 'status']
)

user_service_auth_latency_seconds = Histogram(
    'user_service_auth_latency_seconds',
    'Authentication request latency',
    ['endpoint']
)

user_service_login_failures_total = Counter(
    'user_service_login_failures_total',
    'Total login failures',
    ['reason']  # 'invalid_credentials', 'account_locked', 'rate_limited'
)

user_service_mfa_verifications_total = Counter(
    'user_service_mfa_verifications_total',
    'Total MFA verifications',
    ['status']  # 'success', 'failed'
)

# Session metrics
user_service_sessions_active = Gauge(
    'user_service_sessions_active',
    'Number of active sessions'
)

user_service_refresh_token_rotations_total = Counter(
    'user_service_refresh_token_rotations_total',
    'Total refresh token rotations',
    ['status']  # 'success', 'reuse_detected'
)

# Authorization metrics
user_service_authz_check_requests_total = Counter(
    'user_service_authz_check_requests_total',
    'Total authz check requests',
    ['decision']  # 'allow', 'deny'
)

user_service_authz_check_latency_seconds = Histogram(
    'user_service_authz_check_latency_seconds',
    'Authz check latency'
)

user_service_authz_cache_hits_total = Counter(
    'user_service_authz_cache_hits_total',
    'Authz cache hits'
)

# Trading account metrics
user_service_trading_accounts_total = Gauge(
    'user_service_trading_accounts_total',
    'Total trading accounts',
    ['broker', 'status']
)

user_service_trading_account_sync_duration_seconds = Histogram(
    'user_service_trading_account_sync_duration_seconds',
    'Trading account profile sync duration'
)

user_service_trading_account_sync_failures_total = Counter(
    'user_service_trading_account_sync_failures_total',
    'Trading account profile sync failures',
    ['broker', 'reason']
)

# Credential vault metrics
user_service_kms_decrypt_requests_total = Counter(
    'user_service_kms_decrypt_requests_total',
    'KMS decrypt requests',
    ['status']
)

user_service_kms_decrypt_latency_seconds = Histogram(
    'user_service_kms_decrypt_latency_seconds',
    'KMS decrypt latency'
)

# Security metrics
user_service_security_anomalies_total = Counter(
    'user_service_security_anomalies_total',
    'Security anomalies detected',
    ['type', 'risk_score']
)

user_service_rate_limit_exceeded_total = Counter(
    'user_service_rate_limit_exceeded_total',
    'Rate limit exceeded count',
    ['endpoint']
)

# Database metrics
user_service_db_query_duration_seconds = Histogram(
    'user_service_db_query_duration_seconds',
    'Database query duration',
    ['query_type']
)

user_service_db_connection_pool_size = Gauge(
    'user_service_db_connection_pool_size',
    'Database connection pool size'
)

# Redis metrics
user_service_redis_command_duration_seconds = Histogram(
    'user_service_redis_command_duration_seconds',
    'Redis command duration',
    ['command']
)
```

---

### 6.2 Structured Logging

**Format:** JSON (for log aggregation)

**Log Levels:**
- DEBUG: Detailed flow (dev only)
- INFO: Request/response, normal operations
- WARNING: Recoverable errors, degraded performance
- ERROR: Unrecoverable errors
- CRITICAL: Service down

**Log Structure:**
```json
{
  "timestamp": "2025-11-03T10:00:00.123Z",
  "level": "INFO",
  "logger": "user_service.auth",
  "message": "User login successful",
  "user_id": 123,
  "email": "user@example.com",
  "ip": "203.0.113.1",
  "session_id": "sid_abc123",
  "mfa_used": true,
  "duration_ms": 45,
  "trace_id": "abc123def456"
}
```

**Sensitive Data Masking:**
- NEVER log passwords, tokens, credentials
- Mask email: `u***r@example.com`
- Mask IP last octet: `203.0.113.xxx`

---

### 6.3 Health Check Endpoints

#### GET /health

**Checks:**
1. Database connectivity (SELECT 1)
2. Redis connectivity (PING)
3. KMS connectivity (encrypt/decrypt test)

**Response:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "checks": {
    "database": {
      "status": "healthy",
      "latency_ms": 5
    },
    "redis": {
      "status": "healthy",
      "latency_ms": 2
    },
    "kms": {
      "status": "healthy",
      "latency_ms": 120
    }
  },
  "timestamp": "2025-11-03T10:00:00Z"
}
```

**Degraded State:**
```json
{
  "status": "degraded",
  "checks": {
    "database": "healthy",
    "redis": "healthy",
    "kms": "unhealthy"
  }
}
```

---

### 6.4 Alerting Rules

**Prometheus Alerts:**

```yaml
groups:
  - name: user_service_alerts
    rules:
      - alert: HighLoginFailureRate
        expr: rate(user_service_login_failures_total[5m]) > 10
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High login failure rate detected"

      - alert: RefreshTokenReuseDetected
        expr: user_service_refresh_token_rotations_total{status="reuse_detected"} > 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Refresh token reuse detected (security incident)"

      - alert: AuthzCheckLatencyHigh
        expr: histogram_quantile(0.95, user_service_authz_check_latency_seconds) > 0.1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Authz check P95 latency > 100ms"

      - alert: TradingAccountSyncFailures
        expr: rate(user_service_trading_account_sync_failures_total[15m]) > 0.1
        for: 15m
        labels:
          severity: warning
        annotations:
          summary: "High trading account sync failure rate"

      - alert: KMSDecryptFailures
        expr: rate(user_service_kms_decrypt_requests_total{status="error"}[5m]) > 0.05
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "KMS decrypt failures detected"

      - alert: DatabaseConnectionPoolExhausted
        expr: user_service_db_connection_pool_size >= 20
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Database connection pool exhausted"
```

---

## 7. Deployment & Rollout

### 7.1 Deployment Strategy

**Phases:**
1. **Staging Deployment** (Day 0)
   - Deploy to staging environment
   - Run integration tests
   - Validate with test users

2. **Production Canary** (Day 1)
   - Deploy to 10% of production traffic
   - Monitor error rates, latency
   - Rollback if error rate > 1%

3. **Production Full Rollout** (Day 2-3)
   - Gradually increase to 50%, then 100%
   - Monitor for 24 hours
   - Enable all features

---

### 7.2 Feature Flags

**Google OAuth:**
```python
if settings.FEATURE_GOOGLE_OAUTH:
    app.include_router(oauth_router)
```

**MFA:**
```python
if settings.FEATURE_MFA_TOTP:
    app.include_router(mfa_router)
```

**Shared Accounts:**
```python
if settings.FEATURE_SHARED_ACCOUNTS:
    app.include_router(memberships_router)
```

---

### 7.3 Migration Plan

**Step 1: Database Schema Creation**
```bash
# Run migrations
docker exec -it user_service python -m alembic upgrade head

# Verify tables
docker exec -it timescaledb psql -U stocksblitz -d stocksblitz_unified -c "\dt"
```

**Step 2: Seed Admin User**
```sql
INSERT INTO users (email, password_hash, name, status, created_at) VALUES
  ('admin@example.com', '$2b$12$...', 'Admin User', 'active', NOW());

INSERT INTO user_roles (user_id, role_id) VALUES
  (1, (SELECT role_id FROM roles WHERE name = 'admin'));
```

**Step 3: Generate JWT Signing Key**
```bash
docker exec -it user_service python -m scripts.generate_jwt_key
```

**Step 4: Backfill Trading Accounts** (if migrating from existing system)
```sql
-- Map existing ticker_service trading_accounts to user_service
INSERT INTO trading_accounts (user_id, broker, nickname, status, credential_vault_ref, data_key_wrapped, linked_at)
SELECT ... FROM ticker_service.trading_accounts;
```

**Step 5: Enable Service-to-Service Auth**
```bash
# Generate service tokens
docker exec -it user_service python -m scripts.create_service_client \
  --client_id service_ticker \
  --name "Ticker Service" \
  --scopes authz:check,credentials:read
```

---

### 7.4 Zero-Downtime Deployment

**Strategy:** Blue-Green Deployment

**Steps:**
1. Deploy new version (green) alongside old version (blue)
2. Health check green version
3. Switch traffic from blue to green (load balancer)
4. Monitor for 10 minutes
5. If stable, decommission blue; else rollback

**Database Migrations:**
- Use expand-contract pattern (as defined in Phase 0)
- Never drop columns in same deployment as code change

---

### 7.5 Rollback Plan

**Trigger:** Error rate > 1% or P95 latency > 500ms

**Steps:**
1. Switch load balancer back to blue version
2. Investigate issue in logs
3. Fix in green version
4. Re-deploy

**Database Rollback:**
- Keep old schema compatible for N-1 version
- Use Alembic downgrade if needed

---

## 8. Testing Strategy

### 8.1 Unit Tests

**Coverage Target:** 90%

**Focus Areas:**
- Password hashing/validation
- JWT signing/verification
- Refresh token rotation logic
- Authorization policy evaluation
- Envelope encryption/decryption

**Example:**
```python
def test_login_success(client, db_session):
    user = create_test_user(email="test@example.com", password="SecurePass123!")
    response = client.post("/v1/auth/login", json={
        "email": "test@example.com",
        "password": "SecurePass123!"
    })
    assert response.status_code == 200
    assert "access_token" in response.json()
```

---

### 8.2 Integration Tests

**Focus Areas:**
- Database transactions
- Redis session lifecycle
- KMS encryption/decryption
- Event publishing to Redis pub/sub

**Example:**
```python
def test_trading_account_link_with_kite_api(client, db_session, mock_kite_api):
    mock_kite_api.return_value = {"user_id": "ABC123", "name": "John Doe"}
    response = client.post("/v1/trading-accounts/link", json={
        "broker": "kite",
        "credentials": {...}
    })
    assert response.status_code == 201
    assert mock_kite_api.called
```

---

### 8.3 Contract Tests (Pact)

**Consumer:** ticker_service
**Provider:** user_service

**Contract:** `/v1/authz/check` returns `{decision: "allow"}` when user owns account

---

### 8.4 Load Tests (Locust)

**Scenarios:**
- 1000 concurrent logins
- 10000 authz checks/sec
- 100 trading account links/min

**Acceptance Criteria:**
- P95 latency < 200ms for authz checks
- No errors under normal load

---

## 9. Migration Plan

### 9.1 From Backend API Keys to User Service Tokens

**Phase 1: Dual Support** (Months 1-3)
- Backend validates both API keys and user_service tokens
- New users get tokens only
- Existing users continue with API keys

**Phase 2: Migration** (Months 4-6)
- Email existing users: "Upgrade to new auth"
- Provide migration guide
- Deprecation warnings in API responses

**Phase 3: Sunset** (Month 7)
- Disable API key validation
- All traffic uses user_service tokens

---

### 9.2 Trading Account Credential Migration

**Current State:** ticker_service stores credentials (if applicable)

**Migration:**
1. Export credentials from ticker_service
2. Encrypt with user_service KMS
3. Store in user_service `trading_accounts` table
4. Update ticker_service to call user_service internal API for credentials
5. Delete credentials from ticker_service

---

## Appendix: ADRs

### ADR-001: Use JWT (RS256) for Access Tokens

**Status:** Accepted

**Context:** Need stateless token validation with cryptographic signatures.

**Decision:** Use JWT with RS256 (RSA-2048 signatures) for access tokens.

**Consequences:**
- ✅ Stateless validation (no DB lookup)
- ✅ Services can validate locally via JWKS
- ❌ Cannot revoke before expiry (mitigated with 15-min TTL)
- ❌ Larger token size vs opaque tokens

---

### ADR-002: Refresh Token Rotation with Reuse Detection

**Status:** Accepted

**Context:** Need secure "stay signed in" without long-lived access tokens.

**Decision:** Implement refresh token families with automatic rotation on each use and reuse detection.

**Consequences:**
- ✅ Detects stolen refresh tokens
- ✅ Limits blast radius of compromise
- ❌ Complexity in client-side retry logic

---

### ADR-003: Envelope Encryption with KMS

**Status:** Accepted

**Context:** Must encrypt trading account credentials at rest.

**Decision:** Use envelope encryption with per-account data keys and KMS master key.

**Consequences:**
- ✅ Secure key management (rotate master key without re-encrypting all data)
- ✅ Compliance with SOC 2, PCI-DSS
- ❌ Dependency on KMS availability

---

### ADR-004: Redis Pub/Sub for Events (Not Kafka)

**Status:** Accepted

**Context:** Existing infrastructure uses Redis; no Kafka.

**Decision:** Use Redis pub/sub for event bus.

**Consequences:**
- ✅ Leverage existing infrastructure
- ✅ Simple, low-latency
- ❌ At-most-once delivery (no durability)
- Mitigation: Consumers implement idempotency

---

### ADR-005: RBAC + ABAC Hybrid Authorization

**Status:** Accepted

**Context:** Need global roles (admin) and resource-level permissions (trading account ownership).

**Decision:** Implement hybrid RBAC (roles like "admin") + ABAC (attributes like "owner of account").

**Consequences:**
- ✅ Flexible permission model
- ✅ Supports shared trading accounts
- ❌ More complex policy evaluation (mitigated with caching)

---

## Summary

This Phase 1 design provides a complete blueprint for implementing `user_service`:

✅ **40+ API endpoints** with detailed specs
✅ **10+ database tables** with indexes and constraints
✅ **10+ event schemas** for service integration
✅ **Security architecture** (KMS, JWT, MFA, rate limiting)
✅ **Infrastructure config** (Docker, env vars, Redis keyspace)
✅ **Observability** (20+ metrics, structured logging, health checks)
✅ **Deployment strategy** (canary, feature flags, zero-downtime)

**Next Steps:**
1. Review and approve this design
2. Create GitHub issues for each component
3. Implement in order: Core auth → Trading accounts → MFA → Admin
4. Deploy to staging → canary → production

**Estimated Implementation Time:** 6-8 weeks with 2-3 engineers

---

*End of Phase 1 Design Document*
