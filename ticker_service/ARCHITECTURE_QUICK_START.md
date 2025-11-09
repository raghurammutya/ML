# Ticker Service - Architecture Quick Reference

## Overview at a Glance

**What it does:** Real-time multi-account market data streaming, order execution, and Greeks calculation for options trading.

**Technology Stack:**
- FastAPI (async Python web framework)
- PostgreSQL/TimescaleDB (persistence)
- Redis (pub/sub messaging)
- Kite Connect API (NSE broker integration)
- Prometheus (metrics), Loguru (logging)

**Size:** ~6,000 lines of Python, 66 files

---

## Core Data Flow

```
Kite WebSocket → Validate → Process → Batch → Redis → Clients
                 (Ticks)    (Greeks)  (100ms) (Publish) (Frontend)
```

Three main processes:
1. **Ticker Loop** - Streaming market data from Kite
2. **Order Executor** - Reliable order execution with retries
3. **REST API** - Subscriptions, history, trading account management

---

## Project Structure at a Glance

```
/app
  main.py           ← FastAPI entry point + lifespan management
  generator.py      ← MultiAccountTickerLoop (core streaming)
  config.py         ← 50+ configuration options
  accounts.py       ← Multi-account credential management
  
  /kite/            ← Kite Connect integration
    websocket_pool.py    ← Connection pooling (scales >3000 instruments)
    
  /services/        ← Modular components (Phase 4 refactoring)
    tick_processor.py    ← Validation, routing, enrichment
    tick_batcher.py      ← Batch publishing (10x throughput gain)
    tick_validator.py    ← Pydantic schemas
    tick_refresher.py    ← Daily token refresh
    
  /metrics/         ← Prometheus observability
  
  order_executor.py ← Reliable order execution
  subscription_store.py  ← Database subscriptions
  instrument_registry.py ← Instrument metadata cache
  
  routes_*.py       ← REST API endpoints
```

---

## Key Architectural Decisions

### 1. Multi-Account Streaming
- One ticker_service can manage multiple Kite accounts
- Loadbalances subscriptions across accounts
- Automatic failover on API rate limits
- **Why:** Kite limits to 9,000 instruments per account (3 WS × 3,000 each)

### 2. Tick Batching (10x throughput)
- Groups 100+ ticks over 100ms window
- Single Redis publish instead of per-tick
- Reduces Redis load from 10K publishes/sec → 100 publishes/sec
- **Why:** Redis becomes bottleneck at high volume

### 3. Circuit Breaker Pattern
- Redis failures don't crash streaming
- Gracefully drops messages when Redis down
- Automatic recovery when service restored
- **Why:** Resilience to dependency failures

### 4. Task Queue for Orders
- Orders enqueued with UUID tracking
- Worker polls every 1 second
- Exponential backoff on failures
- Auto-cleanup of old tasks
- **Why:** Durability, retry logic, clear audit trail

### 5. Encrypted Credential Storage
- Kite API secrets stored encrypted in PostgreSQL
- Fernet encryption (symmetric)
- Environment variables for secrets (never hardcoded)
- **Why:** Security compliance

---

## Critical Components to Know

### **main.py** - FastAPI Application
- Initializes all services on startup
- Manages graceful shutdown
- Defines health/metrics endpoints
- PII redaction in logs

### **generator.py** - MultiAccountTickerLoop
- Orchestrates streaming from Kite
- Manages account session leases
- Calculates Greeks for options
- Publishes to Redis
- **Key methods:**
  - `start()` - Boot up streaming
  - `_stream_account()` - Per-account WebSocket listener
  - `_stream_underlying()` - NIFTY/underlying tracking

### **accounts.py** - SessionOrchestrator
- Manages Kite account credentials
- Handles multi-account load balancing
- Enforces rate limits (max 2 concurrent per account)
- **Key class:** `SessionOrchestrator`

### **kite/websocket_pool.py** - Connection Pooling
- Creates multiple WebSocket connections (max 3 per account)
- Distributes subscriptions across connections
- Scales beyond 3,000 instrument limit
- Monitors connection health

### **services/tick_processor.py** - Data Processing
- Validates tick data with Pydantic schemas
- Routes to underlying vs option channels
- Calculates Greeks for options
- Extracts market depth

### **services/tick_batcher.py** - Batched Publishing
- Buffers ticks in memory
- Flushes every 100ms or 1,000 ticks
- Combines into single Redis publish
- Metrics tracking

### **order_executor.py** - Order Management
- Task queue for place/modify/cancel orders
- Retry logic with exponential backoff
- Circuit breaker for Kite API
- Auto-cleanup of old tasks

### **subscription_store.py** - Database Persistence
- CRUD on instrument_subscriptions table
- Load subscriptions on startup
- Validate against instrument registry

### **instrument_registry.py** - Metadata Cache
- Fetches instruments from Kite
- Caches in PostgreSQL + in-memory
- Validates subscription tokens
- Refreshes daily

---

## Configuration (config.py)

**Critical Settings:**
```python
# Kite Connect
KITE_API_KEY              # From https://developers.kite.trade/
KITE_API_SECRET           # From Kite console
KITE_ACCESS_TOKEN         # Generated via token_bootstrap.py

# Database
INSTRUMENT_DB_HOST        # PostgreSQL host
INSTRUMENT_DB_NAME        # Database name
INSTRUMENT_DB_PASSWORD    # Database password

# Redis
REDIS_URL                 # redis://<password>@host:6379/0

# Streaming
TICKER_MODE              # "full" (default), "quote", "ltp"
MAX_INSTRUMENTS_PER_WS   # 3,000 (Kite limit)
MAX_WS_CONNECTIONS      # 3 (Kite hard limit per account)

# Greeks Calculation
OPTION_GREEKS_INTEREST_RATE    # 0.10 (10%, for Black-Scholes)
OPTION_GREEKS_DIVIDEND_YIELD   # 0.0 (default)

# Performance
TICK_BATCH_ENABLED       # true (10x throughput)
TICK_BATCH_WINDOW_MS     # 100 (flush every 100ms)
TICK_BATCH_MAX_SIZE      # 1,000 (max before force flush)
```

---

## Performance Characteristics

### Throughput
- **Current:** 1,000+ ticks/second sustainable
- **With batching:** 10,000+ ticks/second tested
- **Bottleneck:** Redis single connection

### Latency
- **Tick to Redis publish:** <100ms (end-to-end)
- **Order execution:** 1-5 seconds (network dependent)
- **Greeks calculation:** 2-3ms per option

### Memory
- **Baseline:** ~100MB (FastAPI + libraries)
- **Per 1,000 subscriptions:** ~5MB
- **Task queue:** ~200 bytes per order task

### Database
- **Connections:** Pool of 5 (configurable)
- **Write throughput:** ~100 subscriptions/sec
- **Read throughput:** ~1,000 metadata lookups/sec

---

## Data Flows

### Real-Time Tick Processing
```
Kite WebSocket
    ↓ (raw tick dict)
TickValidator (Pydantic)
    ↓ (validated tick)
TickProcessor
    ├→ Extract Greeks (if option)
    ├→ Normalize symbol
    ├→ Extract market depth
    ↓
TickBatcher (accumulate 100ms or 1000 ticks)
    ↓ (batch of snapshots)
RedisPublisher (with circuit breaker)
    ↓
Redis Channel: ticker:nifty:options
Redis Channel: ticker:nifty:underlying
    ↓
Subscribed clients (frontend, mobile)
```

### Subscription Management
```
POST /subscriptions
    ↓
Validate token against instrument registry
    ↓
Store in PostgreSQL
    ↓
Trigger background reload
    ↓
SubscriptionReconciler (load balance across accounts)
    ↓
MultiAccountTickerLoop (update streaming tasks)
    ↓
Kite WebSocket (subscribe to new instruments)
```

### Order Execution
```
POST /orders/place
    ↓
Create OrderTask(uuid, idempotency_key)
    ↓
Enqueue in OrderExecutor.tasks
    ↓
OrderExecutor.start_worker() (polls every 1s)
    ├→ Check status == PENDING
    ├→ Borrow Kite client
    ├→ Execute operation
    ├→ Record success/failure
    ├→ Exponential backoff on error
    ↓
After 5 attempts: mark DEAD_LETTER
    ↓
Publish to WebSocket for client updates
```

---

## Security Model

### Authentication
1. **API Key** (X-API-Key header)
   - Required for REST endpoints (except health)
   - 32+ character random string
   - Enforced in production only

2. **JWT Tokens** (Bearer token)
   - From user_service
   - Validates signature with cached JWKS
   - For sensitive endpoints + WebSocket

3. **Credential Encryption**
   - Fernet (symmetric) for stored secrets
   - Environment variables for dynamic secrets
   - Never logged or exposed in errors

### Input Validation
- Pydantic schemas for all requests
- Range checks (price, volume, quantities)
- Token validation against instrument registry
- PII redaction in logs (email, phone, API keys)

### Production Enforcement
- MUST enable API key in production
- MUST use strong encryption keys
- MUST rotate secrets every 90 days
- MUST use environment-specific config

---

## Observability

### Logging
- **Console:** Real-time Docker logs (INFO level)
- **File:** Persistent logs with rotation (DEBUG level)
- **Rotation:** 100MB per file, 7-day retention
- **Format:** Timestamp | Level | Module:Function:Line - Message

### Metrics
- **Endpoint:** `GET /metrics` (Prometheus format)
- **Key metrics:**
  - `http_requests_total` - API requests
  - `order_requests_completed` - Order execution
  - `websocket_pool_connections` - Active connections
  - `redis_publish_failures` - Redis health
  - `circuit_breaker_state` - Fault tolerance

### Health Check
- **Endpoint:** `GET /health`
- **Includes:** Redis, PostgreSQL, Instrument Registry
- **Status:** "ok", "degraded", or critical details

---

## Known Bottlenecks & Mitigations

| Bottleneck | Impact | Mitigation | Status |
|------------|--------|-----------|--------|
| Single Redis connection | 10K publishes/sec limit | Tick batching | Implemented |
| Greeks CPU cost | 2-3ms per option × 1000/sec | Vectorization | TODO |
| WebSocket limit (3 per account) | Max 9K instruments | Connection pool + load balancing | Implemented |
| DB connection pool (5 max) | Query queueing under load | Monitor + tune pool size | Needs monitoring |
| OrderExecutor task memory | Unbounded growth | Auto-cleanup of old tasks | Implemented |

---

## Deployment Checklist

- [ ] PostgreSQL database created and initialized
- [ ] Redis instance available and accessible
- [ ] Kite API credentials obtained from developers.kite.trade
- [ ] Kite access tokens generated via token_bootstrap.py
- [ ] API key generated and set in .env
- [ ] Database encryption key generated and set
- [ ] .env file created with all required variables
- [ ] Docker image built
- [ ] Container health check verified
- [ ] Metrics endpoint accessible
- [ ] Health endpoint returns 200
- [ ] Log rotation working

---

## Common Tasks

### Add a New Subscription
```bash
curl -X POST http://localhost:8080/subscriptions \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_API_KEY" \
  -d '{
    "instrument_token": 20535810,
    "requested_mode": "FULL",
    "account_id": "primary"
  }'
```

### Fetch Historical Data
```bash
curl "http://localhost:8080/history?instrument_token=20535810&from_ts=2025-10-28T09:30:00Z&to_ts=2025-10-28T10:00:00Z&interval=minute&oi=true"
```

### Check Service Health
```bash
curl http://localhost:8080/health | jq .
```

### View Prometheus Metrics
```bash
curl http://localhost:8080/metrics
```

### Generate Kite Access Token
```bash
cd ticker_service
source .venv/bin/activate
python app/kite/token_bootstrap.py
```

---

## References

- **Full Architecture:** See ARCHITECTURE_OVERVIEW.md (1,179 lines)
- **README:** Quick start guide
- **Dockerfile:** Container configuration
- **requirements.txt:** Dependencies (26 packages)
- **Code:** 66 files, 6,000 lines of Python

