# User Service Integration Guide

**Version:** 1.0
**Date:** 2025-11-03
**Status:** Implementation Plan

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture Changes](#architecture-changes)
3. [Backend Service Integration](#backend-service-integration)
4. [Ticker Service Integration](#ticker-service-integration)
5. [Alert Service Integration](#alert-service-integration)
6. [Frontend Integration](#frontend-integration)
7. [Implementation Phases](#implementation-phases)
8. [Testing Strategy](#testing-strategy)

---

## Overview

The User Service provides centralized authentication and authorization for all microservices. This guide outlines the changes needed in each service to integrate with the User Service.

### Current State
- ❌ Backend: Has API key authentication (different system)
- ❌ Ticker Service: No authentication
- ❌ Alert Service: Basic or no authentication
- ❌ Frontend: No user authentication screens

### Target State
- ✅ All services: JWT-based authentication from User Service
- ✅ Consistent user identity across all services
- ✅ Centralized permission management
- ✅ Session management and MFA support
- ✅ Trading account linking through User Service

---

## Architecture Changes

### Before Integration
```
┌─────────────┐
│  Frontend   │
│             │
└──────┬──────┘
       │
       ▼
┌─────────────┐     ┌──────────────┐
│  Backend    │────▶│  PostgreSQL  │
│  (FastAPI)  │     └──────────────┘
└──────┬──────┘
       │
       ├─────────┐
       │         │
       ▼         ▼
┌──────────┐  ┌──────────┐
│ Ticker   │  │  Alert   │
│ Service  │  │ Service  │
└──────────┘  └──────────┘
```

### After Integration
```
                 ┌─────────────────┐
                 │  User Service   │
                 │  (Port 8001)    │
                 │                 │
                 │  • Auth/Login   │
                 │  • JWT Tokens   │
                 │  • Permissions  │
                 │  • Trading Acc  │
                 └────────┬────────┘
                          │
                          │ JWT Validation
         ┌────────────────┼────────────────┐
         │                │                │
         ▼                ▼                ▼
┌─────────────┐    ┌──────────┐    ┌──────────┐
│  Frontend   │    │  Backend │    │  Ticker  │
│             │    │          │    │  Service │
│  • Login UI │    │  • JWT   │    │  • JWT   │
│  • Profile  │    │  Auth    │    │  Auth    │
└─────────────┘    └──────────┘    └──────────┘
                          │
                          ▼
                   ┌──────────┐
                   │  Alert   │
                   │  Service │
                   │  • JWT   │
                   │  Auth    │
                   └──────────┘
```

---

## Backend Service Integration

### 1. Add JWT Validation Middleware

**File: `backend/app/jwt_auth.py` (NEW)**

```python
"""
JWT Authentication Middleware for Backend Service

Validates JWT tokens from User Service.
"""

import httpx
from typing import Optional
from fastapi import HTTPException, Security, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from functools import lru_cache
import jwt

security = HTTPBearer()

# Cache JWKS for 1 hour
@lru_cache(maxsize=1)
def get_jwks(timestamp: int):
    """Fetch JWKS from user_service (cached)"""
    response = httpx.get("http://localhost:8001/v1/auth/.well-known/jwks.json")
    return response.json()

async def verify_jwt_token(
    credentials: HTTPAuthorizationCredentials = Security(security)
) -> dict:
    """
    Verify JWT token from User Service

    Returns:
        dict: Token payload with user_id, email, roles, etc.
    """
    if not credentials:
        raise HTTPException(status_code=401, detail="Missing authentication token")

    token = credentials.credentials

    try:
        # Get JWKS (cached)
        import time
        timestamp = int(time.time() / 3600)  # Cache for 1 hour
        jwks = get_jwks(timestamp)

        # Verify token
        # Note: Use PyJWT library to verify with JWKS
        payload = jwt.decode(
            token,
            jwks,  # Will need to extract correct key
            algorithms=["RS256"],
            audience="trading_platform",
            issuer="user_service"
        )

        return payload

    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")

async def get_current_user(token_payload: dict = Depends(verify_jwt_token)) -> dict:
    """Get current user from JWT token"""
    return {
        "user_id": token_payload.get("sub"),
        "email": token_payload.get("email"),
        "roles": token_payload.get("roles", []),
        "session_id": token_payload.get("session_id")
    }

async def require_permission(permission: str):
    """Decorator to require specific permission"""
    async def check_permission(user: dict = Depends(get_current_user)):
        # Call user_service to check permission
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "http://localhost:8001/v1/authz/check",
                json={"permission": permission},
                headers={"Authorization": f"Bearer {user['token']}"}
            )

            if response.status_code != 200 or not response.json().get("allowed"):
                raise HTTPException(status_code=403, detail="Permission denied")

        return user

    return check_permission
```

### 2. Update Existing Endpoints

**File: `backend/app/routes/fo.py` (MODIFY)**

```python
from app.jwt_auth import get_current_user, require_permission

# Before (API key auth):
@router.get("/positions")
async def get_positions(api_key: APIKey = Depends(verify_api_key)):
    user_id = api_key.user_id
    # ... rest of code

# After (JWT auth):
@router.get("/positions")
async def get_positions(current_user: dict = Depends(get_current_user)):
    user_id = current_user["user_id"]
    # ... rest of code
```

### 3. Dual Authentication Support (Migration Period)

**File: `backend/app/auth_wrapper.py` (NEW)**

```python
"""
Dual authentication support during migration
Supports both API keys (legacy) and JWT tokens (new)
"""

from fastapi import Depends, HTTPException
from typing import Union
from app.auth import verify_api_key, APIKey
from app.jwt_auth import get_current_user

async def get_user_from_auth(
    api_key: APIKey = Depends(verify_api_key),
    jwt_user: dict = Depends(get_current_user)
) -> dict:
    """
    Accept either API key or JWT token

    During migration period, support both auth methods
    """
    if jwt_user:
        # JWT auth (preferred)
        return {
            "user_id": jwt_user["user_id"],
            "auth_method": "jwt",
            "email": jwt_user["email"]
        }
    elif api_key:
        # API key auth (legacy)
        return {
            "user_id": api_key.user_id,
            "auth_method": "api_key",
            "email": None  # API keys don't have email
        }
    else:
        raise HTTPException(status_code=401, detail="Authentication required")
```

### 4. Required Changes Summary

| File | Change Type | Description |
|------|-------------|-------------|
| `app/jwt_auth.py` | NEW | JWT validation middleware |
| `app/auth_wrapper.py` | NEW | Dual auth support |
| `app/routes/fo.py` | MODIFY | Update to use JWT auth |
| `app/routes/indicator_ws.py` | MODIFY | Add JWT auth to WebSocket |
| `app/main.py` | MODIFY | Add CORS for user_service |
| `requirements.txt` | MODIFY | Add `PyJWT` library |

---

## Ticker Service Integration

### 1. WebSocket Authentication

**File: `ticker_service/app/websocket.py` (MODIFY)**

```python
from fastapi import WebSocket, WebSocketDisconnect
import httpx
import jwt

async def verify_ws_token(token: str) -> dict:
    """Verify JWT token for WebSocket connection"""
    try:
        # Verify with user_service JWKS
        # Similar to backend JWT verification
        payload = jwt.decode(token, ...)
        return payload
    except Exception as e:
        raise ValueError(f"Invalid token: {e}")

@app.websocket("/ws/quotes")
async def websocket_endpoint(websocket: WebSocket, token: str = None):
    """
    WebSocket endpoint with authentication

    Client must send: ws://localhost:8080/ws/quotes?token=JWT_TOKEN
    """
    if not token:
        await websocket.close(code=1008, reason="Missing authentication token")
        return

    try:
        # Verify token
        user = await verify_ws_token(token)
        user_id = user["sub"]

        await websocket.accept()

        # ... rest of WebSocket logic

    except ValueError as e:
        await websocket.close(code=1008, reason=str(e))
```

### 2. Trading Account Verification

**File: `ticker_service/app/kite_manager.py` (MODIFY)**

```python
async def get_user_trading_accounts(user_id: str) -> list:
    """
    Fetch user's trading accounts from user_service

    Returns decrypted Kite credentials for ticker service to use
    """
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"http://localhost:8001/v1/trading-accounts",
            headers={"Authorization": f"Bearer {token}"}
        )

        if response.status_code == 200:
            accounts = response.json()
            # Filter for active Kite accounts
            return [a for a in accounts if a["broker"] == "kite" and a["status"] == "active"]

        return []

async def subscribe_to_symbols(user_id: str, symbols: list):
    """Subscribe to symbols - verify user has linked trading account"""

    # Get user's trading accounts
    accounts = await get_user_trading_accounts(user_id)

    if not accounts:
        raise ValueError("No active trading accounts linked. Please link a Kite account in user profile.")

    # Use first active account
    account = accounts[0]

    # Get decrypted credentials from user_service
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"http://localhost:8001/v1/internal/trading-accounts/{account['account_id']}/credentials",
            headers={"X-Service-Token": "TICKER_SERVICE_SECRET"}  # Service-to-service auth
        )

        if response.status_code == 200:
            credentials = response.json()
            api_key = credentials["api_key"]
            api_secret = credentials["api_secret"]

            # Initialize Kite connection with credentials
            # ... rest of logic
```

### 3. Required Changes Summary

| File | Change Type | Description |
|------|-------------|-------------|
| `app/websocket.py` | MODIFY | Add JWT auth to WebSocket |
| `app/kite_manager.py` | MODIFY | Fetch credentials from user_service |
| `app/jwt_auth.py` | NEW | JWT verification utility |
| `requirements.txt` | MODIFY | Add `PyJWT` library |

---

## Alert Service Integration

### 1. Add JWT Authentication

**File: `alert_service/app/auth.py` (NEW)**

```python
"""JWT authentication for Alert Service"""

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer
import httpx

security = HTTPBearer()

async def get_current_user(credentials = Depends(security)) -> dict:
    """Verify JWT token with user_service"""
    token = credentials.credentials

    # Verify token with user_service
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "http://localhost:8001/v1/users/me",
            headers={"Authorization": f"Bearer {token}"}
        )

        if response.status_code == 200:
            return response.json()
        else:
            raise HTTPException(status_code=401, detail="Invalid token")
```

### 2. Update Alert Endpoints

**File: `alert_service/app/routes/alerts.py` (MODIFY)**

```python
from app.auth import get_current_user

@router.post("/alerts")
async def create_alert(
    alert: AlertCreate,
    current_user: dict = Depends(get_current_user)
):
    """Create alert - associate with current user"""
    alert_data = alert.dict()
    alert_data["user_id"] = current_user["user_id"]

    # ... rest of logic

@router.get("/alerts")
async def list_alerts(current_user: dict = Depends(get_current_user)):
    """List alerts for current user only"""
    user_id = current_user["user_id"]

    # Filter alerts by user_id
    # ... rest of logic
```

### 3. Required Changes Summary

| File | Change Type | Description |
|------|-------------|-------------|
| `app/auth.py` | NEW | JWT authentication |
| `app/routes/alerts.py` | MODIFY | Add user_id to alerts |
| `app/database.py` | MODIFY | Add user_id column to alerts table |

---

## Frontend Integration

### 1. New Screens Required

#### A. Authentication Screens

**1. Login Page (`/login`)**

```tsx
// frontend/src/pages/LoginPage.tsx

import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

export function LoginPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [mfaRequired, setMfaRequired] = useState(false);
  const [mfaCode, setMfaCode] = useState('');
  const [sessionToken, setSessionToken] = useState('');
  const { login, verifyMfa } = useAuth();
  const navigate = useNavigate();

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();

    try {
      const response = await login(email, password);

      if (response.status === 'mfa_required') {
        setMfaRequired(true);
        setSessionToken(response.session_token);
      } else {
        // Login successful
        navigate('/');
      }
    } catch (error) {
      alert('Login failed: ' + error.message);
    }
  };

  const handleMfaVerify = async (e: React.FormEvent) => {
    e.preventDefault();

    try {
      await verifyMfa(sessionToken, mfaCode);
      navigate('/');
    } catch (error) {
      alert('MFA verification failed: ' + error.message);
    }
  };

  if (mfaRequired) {
    return (
      <div className="login-container">
        <h1>Two-Factor Authentication</h1>
        <form onSubmit={handleMfaVerify}>
          <input
            type="text"
            placeholder="Enter 6-digit code"
            value={mfaCode}
            onChange={(e) => setMfaCode(e.target.value)}
            maxLength={6}
          />
          <button type="submit">Verify</button>
        </form>
      </div>
    );
  }

  return (
    <div className="login-container">
      <h1>Login to Quantagro</h1>
      <form onSubmit={handleLogin}>
        <input
          type="email"
          placeholder="Email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <input
          type="password"
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <button type="submit">Login</button>
      </form>
      <a href="/register">Don't have an account? Register</a>
      <a href="/forgot-password">Forgot password?</a>
    </div>
  );
}
```

**2. Registration Page (`/register`)**

```tsx
// frontend/src/pages/RegisterPage.tsx

import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { authApi } from '../services/authApi';

export function RegisterPage() {
  const [formData, setFormData] = useState({
    email: '',
    password: '',
    confirmPassword: '',
    name: '',
    phone: ''
  });
  const navigate = useNavigate();

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();

    if (formData.password !== formData.confirmPassword) {
      alert('Passwords do not match');
      return;
    }

    try {
      await authApi.register({
        email: formData.email,
        password: formData.password,
        name: formData.name,
        phone: formData.phone
      });

      alert('Registration successful! Please login.');
      navigate('/login');
    } catch (error) {
      alert('Registration failed: ' + error.message);
    }
  };

  return (
    <div className="register-container">
      <h1>Create Account</h1>
      <form onSubmit={handleRegister}>
        <input
          type="text"
          placeholder="Full Name"
          value={formData.name}
          onChange={(e) => setFormData({...formData, name: e.target.value})}
        />
        <input
          type="email"
          placeholder="Email"
          value={formData.email}
          onChange={(e) => setFormData({...formData, email: e.target.value})}
        />
        <input
          type="tel"
          placeholder="Phone (optional)"
          value={formData.phone}
          onChange={(e) => setFormData({...formData, phone: e.target.value})}
        />
        <input
          type="password"
          placeholder="Password (min 12 chars)"
          value={formData.password}
          onChange={(e) => setFormData({...formData, password: e.target.value})}
        />
        <input
          type="password"
          placeholder="Confirm Password"
          value={formData.confirmPassword}
          onChange={(e) => setFormData({...formData, confirmPassword: e.target.value})}
        />
        <button type="submit">Register</button>
      </form>
      <a href="/login">Already have an account? Login</a>
    </div>
  );
}
```

**3. Profile Page (`/profile`)**

```tsx
// frontend/src/pages/ProfilePage.tsx

import { useEffect, useState } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { userApi } from '../services/userApi';

export function ProfilePage() {
  const { user } = useAuth();
  const [profile, setProfile] = useState(null);
  const [editing, setEditing] = useState(false);

  useEffect(() => {
    loadProfile();
  }, []);

  const loadProfile = async () => {
    const data = await userApi.getCurrentUser();
    setProfile(data);
  };

  return (
    <div className="profile-container">
      <h1>My Profile</h1>

      <div className="profile-section">
        <h2>Basic Information</h2>
        <p><strong>Name:</strong> {profile?.name}</p>
        <p><strong>Email:</strong> {profile?.email}</p>
        <p><strong>Phone:</strong> {profile?.phone || 'Not set'}</p>
        <button onClick={() => setEditing(true)}>Edit Profile</button>
      </div>

      <div className="profile-section">
        <h2>Security</h2>
        <p><strong>MFA:</strong> {profile?.mfa_enabled ? 'Enabled' : 'Disabled'}</p>
        <a href="/security">Manage Security Settings</a>
      </div>

      <div className="profile-section">
        <h2>Trading Accounts</h2>
        <a href="/trading-accounts">Manage Trading Accounts</a>
      </div>

      <div className="profile-section">
        <h2>Activity</h2>
        <a href="/audit">View Audit Log</a>
      </div>
    </div>
  );
}
```

**4. Trading Accounts Page (`/trading-accounts`)**

```tsx
// frontend/src/pages/TradingAccountsPage.tsx

import { useEffect, useState } from 'react';
import { tradingAccountApi } from '../services/tradingAccountApi';

export function TradingAccountsPage() {
  const [accounts, setAccounts] = useState([]);
  const [showLinkForm, setShowLinkForm] = useState(false);

  useEffect(() => {
    loadAccounts();
  }, []);

  const loadAccounts = async () => {
    const data = await tradingAccountApi.listAccounts();
    setAccounts(data);
  };

  const handleLinkAccount = async (formData) => {
    try {
      await tradingAccountApi.linkAccount({
        broker: 'kite',
        user_id_broker: formData.userId,
        api_key: formData.apiKey,
        api_secret: formData.apiSecret
      });

      alert('Trading account linked successfully!');
      loadAccounts();
      setShowLinkForm(false);
    } catch (error) {
      alert('Failed to link account: ' + error.message);
    }
  };

  return (
    <div className="trading-accounts-container">
      <h1>Trading Accounts</h1>

      <button onClick={() => setShowLinkForm(true)}>
        Link New Account
      </button>

      {accounts.length === 0 ? (
        <p>No trading accounts linked. Link a Kite Connect account to start trading.</p>
      ) : (
        <div className="accounts-list">
          {accounts.map(account => (
            <div key={account.account_id} className="account-card">
              <h3>{account.broker} - {account.user_id_broker}</h3>
              <p>Status: {account.status}</p>
              <p>Linked: {new Date(account.created_at).toLocaleDateString()}</p>
              <button onClick={() => verifyAccount(account.account_id)}>
                Verify Account
              </button>
            </div>
          ))}
        </div>
      )}

      {showLinkForm && (
        <LinkAccountForm
          onSubmit={handleLinkAccount}
          onCancel={() => setShowLinkForm(false)}
        />
      )}
    </div>
  );
}
```

**5. Security Settings Page (`/security`)**

```tsx
// frontend/src/pages/SecurityPage.tsx

import { useState, useEffect } from 'react';
import { mfaApi } from '../services/mfaApi';

export function SecurityPage() {
  const [mfaEnabled, setMfaEnabled] = useState(false);
  const [showQrCode, setShowQrCode] = useState(false);
  const [qrCodeUri, setQrCodeUri] = useState('');
  const [backupCodes, setBackupCodes] = useState([]);

  useEffect(() => {
    checkMfaStatus();
  }, []);

  const checkMfaStatus = async () => {
    const user = await userApi.getCurrentUser();
    setMfaEnabled(user.mfa_enabled);
  };

  const handleEnableMfa = async () => {
    // Setup TOTP
    const setup = await mfaApi.setupTotp();
    setQrCodeUri(setup.qr_code_uri);
    setShowQrCode(true);
  };

  const handleVerifyAndEnable = async (code: string) => {
    try {
      const result = await mfaApi.enableTotp(code);
      setBackupCodes(result.backup_codes);
      setMfaEnabled(true);
      setShowQrCode(false);
      alert('MFA enabled successfully! Save your backup codes.');
    } catch (error) {
      alert('Invalid code. Please try again.');
    }
  };

  return (
    <div className="security-container">
      <h1>Security Settings</h1>

      <div className="security-section">
        <h2>Two-Factor Authentication</h2>
        {mfaEnabled ? (
          <div>
            <p>✅ MFA is enabled</p>
            <button onClick={handleDisableMfa}>Disable MFA</button>
            <button onClick={handleRegenerateBackupCodes}>
              Regenerate Backup Codes
            </button>
          </div>
        ) : (
          <div>
            <p>⚠️ MFA is not enabled. Enable it for better security.</p>
            <button onClick={handleEnableMfa}>Enable MFA</button>
          </div>
        )}
      </div>

      {showQrCode && (
        <div className="qr-code-modal">
          <h3>Scan QR Code with Google Authenticator</h3>
          <img src={qrCodeUri} alt="QR Code" />
          <p>Or enter this code manually: {qrCodeUri.split('=')[1]}</p>
          <input
            type="text"
            placeholder="Enter 6-digit code"
            onBlur={(e) => handleVerifyAndEnable(e.target.value)}
          />
        </div>
      )}

      {backupCodes.length > 0 && (
        <div className="backup-codes">
          <h3>⚠️ Save These Backup Codes</h3>
          <p>Store these codes safely. Each can be used once if you lose your device.</p>
          {backupCodes.map(code => <p key={code}>{code}</p>)}
          <button onClick={() => setBackupCodes([])}>I've saved them</button>
        </div>
      )}

      <div className="security-section">
        <h2>Change Password</h2>
        <button onClick={() => navigate('/change-password')}>
          Change Password
        </button>
      </div>

      <div className="security-section">
        <h2>Active Sessions</h2>
        <a href="/sessions">View Active Sessions</a>
      </div>
    </div>
  );
}
```

### 2. Authentication Context/Provider

**File: `frontend/src/contexts/AuthContext.tsx` (NEW)**

```tsx
import React, { createContext, useContext, useState, useEffect } from 'react';
import { authApi } from '../services/authApi';

interface User {
  user_id: number;
  email: string;
  name: string;
  roles: string[];
}

interface AuthContextType {
  user: User | null;
  accessToken: string | null;
  login: (email: string, password: string) => Promise<any>;
  logout: () => Promise<void>;
  verifyMfa: (sessionToken: string, code: string) => Promise<void>;
  refreshToken: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType>(null!);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [accessToken, setAccessToken] = useState<string | null>(null);

  useEffect(() => {
    // Check if user is already logged in
    checkAuth();

    // Set up token refresh timer
    const interval = setInterval(refreshToken, 14 * 60 * 1000); // Refresh every 14 minutes

    return () => clearInterval(interval);
  }, []);

  const checkAuth = async () => {
    try {
      const response = await authApi.getCurrentUser();
      setUser(response);
    } catch (error) {
      // Not logged in
      setUser(null);
    }
  };

  const login = async (email: string, password: string) => {
    const response = await authApi.login(email, password);

    if (response.status === 'mfa_required') {
      return response;
    }

    setAccessToken(response.access_token);
    setUser(response.user);

    return response;
  };

  const verifyMfa = async (sessionToken: string, code: string) => {
    const response = await authApi.verifyMfa(sessionToken, code);

    setAccessToken(response.access_token);
    setUser(response.user);
  };

  const logout = async () => {
    await authApi.logout();
    setAccessToken(null);
    setUser(null);
  };

  const refreshToken = async () => {
    try {
      const response = await authApi.refreshToken();
      setAccessToken(response.access_token);
    } catch (error) {
      // Refresh failed - logout
      logout();
    }
  };

  return (
    <AuthContext.Provider value={{ user, accessToken, login, logout, verifyMfa, refreshToken }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
```

### 3. API Service Layer

**File: `frontend/src/services/authApi.ts` (NEW)**

```typescript
import axios from 'axios';

const API_BASE_URL = 'http://localhost:8001/v1';

// Create axios instance with interceptors
const apiClient = axios.create({
  baseURL: API_BASE_URL,
  withCredentials: true  // For refresh token cookie
});

// Add access token to requests
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Handle token refresh on 401
apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status === 401 && !error.config._retry) {
      error.config._retry = true;

      try {
        const response = await authApi.refreshToken();
        localStorage.setItem('access_token', response.access_token);

        error.config.headers.Authorization = `Bearer ${response.access_token}`;
        return apiClient(error.config);
      } catch (refreshError) {
        // Refresh failed - redirect to login
        window.location.href = '/login';
        return Promise.reject(refreshError);
      }
    }

    return Promise.reject(error);
  }
);

export const authApi = {
  register: async (data: any) => {
    const response = await apiClient.post('/auth/register', data);
    return response.data;
  },

  login: async (email: string, password: string) => {
    const response = await apiClient.post('/auth/login', {
      email,
      password,
      persist_session: true
    });

    if (response.data.access_token) {
      localStorage.setItem('access_token', response.data.access_token);
    }

    return response.data;
  },

  verifyMfa: async (sessionToken: string, code: string) => {
    const response = await apiClient.post('/auth/mfa/verify', {
      session_token: sessionToken,
      code
    });

    localStorage.setItem('access_token', response.data.access_token);
    return response.data;
  },

  logout: async () => {
    await apiClient.post('/auth/logout', { all_devices: false });
    localStorage.removeItem('access_token');
  },

  refreshToken: async () => {
    const response = await apiClient.post('/auth/refresh');
    return response.data;
  },

  getCurrentUser: async () => {
    const response = await apiClient.get('/users/me');
    return response.data;
  }
};

export default apiClient;
```

### 4. Protected Routes

**File: `frontend/src/components/ProtectedRoute.tsx` (NEW)**

```tsx
import { Navigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

export function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
}
```

### 5. Update App Routing

**File: `frontend/src/App.tsx` (MODIFY)**

```tsx
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { AuthProvider } from './contexts/AuthContext';
import { ProtectedRoute } from './components/ProtectedRoute';
import { LoginPage } from './pages/LoginPage';
import { RegisterPage } from './pages/RegisterPage';
import { ProfilePage } from './pages/ProfilePage';
import { TradingAccountsPage } from './pages/TradingAccountsPage';
import { SecurityPage } from './pages/SecurityPage';
import { MonitorPage } from './pages/MonitorPage';

export function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          {/* Public routes */}
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/forgot-password" element={<ForgotPasswordPage />} />

          {/* Protected routes */}
          <Route
            path="/"
            element={
              <ProtectedRoute>
                <MonitorPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/profile"
            element={
              <ProtectedRoute>
                <ProfilePage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/trading-accounts"
            element={
              <ProtectedRoute>
                <TradingAccountsPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/security"
            element={
              <ProtectedRoute>
                <SecurityPage />
              </ProtectedRoute>
            }
          />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
```

### 6. Update Existing API Calls

**All existing API calls in frontend need to be updated to use authenticated client**

```tsx
// Before:
const response = await fetch('http://localhost:8081/api/positions');

// After:
import apiClient from '../services/authApi';
const response = await apiClient.get('http://localhost:8081/api/positions');
```

### 7. Required Frontend Changes Summary

| Component | Type | Description |
|-----------|------|-------------|
| `LoginPage.tsx` | NEW | User login |
| `RegisterPage.tsx` | NEW | User registration |
| `ProfilePage.tsx` | NEW | User profile |
| `TradingAccountsPage.tsx` | NEW | Trading accounts |
| `SecurityPage.tsx` | NEW | MFA & security |
| `ForgotPasswordPage.tsx` | NEW | Password reset |
| `AuditLogPage.tsx` | NEW | View audit events |
| `SessionsPage.tsx` | NEW | Active sessions |
| `AuthContext.tsx` | NEW | Auth state management |
| `ProtectedRoute.tsx` | NEW | Route guards |
| `authApi.ts` | NEW | API client with auth |
| `App.tsx` | MODIFY | Add routes |
| `MonitorPage.tsx` | MODIFY | Use authenticated API |
| All API calls | MODIFY | Add Authorization header |

---

## Implementation Phases

### Phase 1: User Service Startup (Week 1)
- [x] User Service implemented
- [x] User Service tested
- [x] User Service deployed
- [ ] Start user_service: `uvicorn app.main:app --port 8001`
- [ ] Run migrations: `alembic upgrade head`
- [ ] Test basic endpoints via Swagger UI

### Phase 2: Backend Integration (Week 2)
- [ ] Add JWT validation middleware
- [ ] Update authentication in endpoints
- [ ] Add dual auth support (API key + JWT)
- [ ] Test backend with JWT tokens
- [ ] Deploy backend changes

### Phase 3: Frontend Authentication (Week 2-3)
- [ ] Create authentication screens
- [ ] Implement AuthContext
- [ ] Add protected routes
- [ ] Test login/logout flow
- [ ] Deploy frontend changes

### Phase 4: Trading Accounts (Week 3)
- [ ] Create trading accounts screen
- [ ] Link Kite accounts through user_service
- [ ] Update ticker_service to fetch credentials
- [ ] Test end-to-end trading flow

### Phase 5: Advanced Features (Week 4)
- [ ] MFA/TOTP setup screens
- [ ] Password reset flow
- [ ] Audit log viewer
- [ ] Session management
- [ ] Profile management

### Phase 6: Testing & Polish (Week 5)
- [ ] Integration testing
- [ ] Security audit
- [ ] Performance testing
- [ ] UI/UX polish
- [ ] Documentation

---

## Testing Strategy

### Unit Tests
- User Service: `pytest tests/`
- Backend: Test JWT validation
- Frontend: Test components with React Testing Library

### Integration Tests
- Full authentication flow
- Trading account linking
- Cross-service communication
- WebSocket authentication

### Manual Testing Checklist
- [ ] Register new user
- [ ] Login with email/password
- [ ] Enable MFA/TOTP
- [ ] Login with MFA
- [ ] Link trading account
- [ ] Subscribe to ticker data
- [ ] Create alert
- [ ] View audit log
- [ ] Change password
- [ ] Logout from all devices

---

## Security Considerations

### JWT Tokens
- ✅ RS256 signature algorithm
- ✅ 15-minute access token expiry
- ✅ Refresh token rotation
- ✅ Reuse detection
- ✅ JWKS endpoint for validation

### Session Management
- ✅ HTTP-only cookies for refresh tokens
- ✅ SameSite=strict in production
- ✅ Device fingerprinting
- ✅ Session revocation

### Password Security
- ✅ bcrypt (cost factor 12)
- ✅ Minimum 12 characters
- ✅ Complexity requirements
- ✅ Password reset flow

### Trading Account Credentials
- ✅ Encrypted at rest with KMS
- ✅ Never logged or cached
- ✅ Service-to-service authentication
- ✅ Automatic credential rotation

---

## Next Steps

1. **Review this document** - Ensure all stakeholders understand the integration plan
2. **Prioritize phases** - Decide which phase to tackle first
3. **Allocate resources** - Assign developers to each service
4. **Set up dev environment** - Start user_service locally
5. **Begin Phase 1** - Get user_service running and tested

---

**Questions? Contact the development team or refer to:**
- User Service README: `/user_service/README.md`
- User Service API Docs: `http://localhost:8001/docs`
- Test Report: `/user_service/TEST_REPORT.md`

---

**Document Version:** 1.0
**Last Updated:** 2025-11-03
**Status:** Ready for Implementation
