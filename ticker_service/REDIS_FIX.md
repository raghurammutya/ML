# Redis Connection Fix - Docker Integration

## Issue

Ticker service was publishing to **host Redis** (port 6379) instead of **Docker Redis** (port 6381), preventing backend services from receiving ticks.

## Root Cause

Ticker service runs on the **host** (not in Docker), but backend services run in **Docker containers**. They need to share the same Redis instance.

## Architecture

```
┌─────────────────────────────────────────┐
│ Host Machine                            │
│                                         │
│  Ticker Service (host)                  │
│  └─> Publishes to: 127.0.0.1:6381     │
│       ↓                                 │
│  ┌──────────────────────────────┐      │
│  │ Docker Network               │      │
│  │                              │      │
│  │  Redis Container             │      │
│  │  - Internal: redis:6379      │      │
│  │  - External: 0.0.0.0:6381   │←─────┤
│  │                              │      │
│  │  Backend Container           │      │
│  │  └─> Subscribes: redis:6379 │      │
│  │                              │      │
│  └──────────────────────────────┘      │
└─────────────────────────────────────────┘
```

## Fix Applied

### File: `ticker_service/.env`

**Before:**
```bash
REDIS_URL=redis://:redis123@127.0.0.1:6379/0
```

**After:**
```bash
REDIS_URL=redis://127.0.0.1:6381/0
```

**Changes:**
1. Port: `6379` → `6381` (Docker Redis external port)
2. Auth: Removed `:redis123@` (Docker Redis has no auth)

## Verification

### ✅ Ticker Service Publishing

```bash
$ timeout 3 redis-cli -h 127.0.0.1 -p 6381 PSUBSCRIBE "ticker:nifty:options"
psubscribe
ticker:nifty:options
1
pmessage
ticker:nifty:options
ticker:nifty:options
{"symbol": "NIFTY", "token": 12188674, "tradingsymbol": "NIFTY25N0425100CE", ...}
```

### ✅ Backend Can Subscribe

Backend services use `redis://redis:6379` internally, which Docker resolves to the same Redis container exposed on port 6381.

## Docker Configuration

**From `docker-compose.yml`:**

```yaml
redis:
  image: redis:7-alpine
  ports:
    - "6381:6379"  # External:Internal mapping
  networks:
    - tv-network
  # NO authentication configured

backend:
  environment:
    - REDIS_URL=redis://redis:6379/0  # Internal Docker network
  networks:
    - tv-network
```

## Result

✅ Ticker service publishes to Docker Redis (port 6381)
✅ Backend subscribes from Docker Redis (internal port 6379)
✅ Both services share the same Redis instance
✅ Real-time ticks flowing to backend

## Production Notes

This configuration is correct for the current deployment where:
- Ticker service runs on **host** (direct Python execution)
- Backend services run in **Docker**
- They communicate via Docker Redis exposed on port 6381

If ticker service is moved to Docker in the future, update to:
```bash
REDIS_URL=redis://redis:6379/0  # Use internal Docker network
```
