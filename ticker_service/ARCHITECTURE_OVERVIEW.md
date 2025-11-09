# Ticker Service - Comprehensive Architecture Overview

**Document Status:** Detailed Technical Analysis (Very Thorough)
**Repository:** ticker_service (feature/nifty-monitor branch)
**Total Code:** ~6,022 lines of Python across 66 files
**Directory Size:** 2.0 MB (excluding .venv and logs)
**Dependencies:** FastAPI, Redis, PostgreSQL/TimescaleDB, Kite Connect API

---

## 1. OVERALL ARCHITECTURE

### High-Level Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                     FastAPI Application                         │
│  (main.py: Lifespan manager + REST API endpoints)               │
└──────────────────┬──────────────────────────────────────────────┘
                   │
        ┌──────────┴──────────┐
        │                     │
┌───────▼────────────┐  ┌────▼──────────────────┐
│ MultiAccountTicker │  │  REST API Routes      │
│ Loop (generator.py)│  │  - orders             │
│                    │  │  - portfolio          │
│ Manages:          │  │  - accounts           │
│ - Streaming ticks │  │  - subscriptions      │
│ - Greeks calc     │  │  - historical         │
│ - Data publishing │  │  - WebSocket          │
└────────┬──────────┘  └────▬──────────────────┘
         │                  │
         └──────────────┬───┘
                        │
      ┌─────────────────┼─────────────────┐
      │                 │                 │
┌─────▼──────┐  ┌──────▼──────┐  ┌──────▼──────────┐
│  Kite      │  │  Redis      │  │  PostgreSQL/    │
│  WebSocket │  │  Publisher  │  │  TimescaleDB    │
│  Pool      │  │  (Circuit   │  │                 │
│            │  │   Breaker)  │  │  Stores:        │
│ - 3+ WS    │  │             │  │  - Subscriptions│
│   Conns    │  │ Publishes   │  │  - Instruments │
│ - 3000 tks │  │ real-time   │  │  - Accounts    │
│   each     │  │ tick data   │  │  - Orders      │
└────────────┘  └─────────────┘  └────────────────┘
```

### Service Initialization Flow

1. **Start** (`start_ticker.py`)
   - Token bootstrap for Kite authentication
   - Uvicorn server startup

2. **Lifespan** (`main.py: lifespan()`)
   - Redis connection initialization
   - Account store bootstrap (database)
   - Ticker loop startup
   - Trade sync service initialization
   - Strike rebalancer startup
   - Token refresher service startup
   - OrderExecutor worker start
   - WebSocket services initialization
   - Dashboard metrics setup

3. **Ticker Loop** (`generator.MultiAccountTickerLoop`)
   - Account orchestration (SessionOrchestrator)
   - Subscription reconciliation
   - Historical bootstrapping
   - Multi-account WebSocket streaming
   - Tick processing and publishing

---

## 2. CORE COMPONENTS & RESPONSIBILITIES

### 2.1 Entry Points and Initialization

| File | Purpose | Key Classes/Functions |
|------|---------|----------------------|
| `/start_ticker.py` | CLI entry point | `run_bootstrap()`, uvicorn.run() |
| `/app/main.py` | FastAPI app factory | `FastAPI()`, `lifespan()` context manager |
| `/app/generator.py` | Multi-account ticker streaming | `MultiAccountTickerLoop` |
| `/app/accounts.py` | Account credential management | `SessionOrchestrator`, `KiteAccount`, `AccountSession` |

### 2.2 Market Data Streaming & Processing

| File | Purpose | Responsibility |
|------|---------|-----------------|
| `generator.py::MultiAccountTickerLoop` | Main streaming orchestrator | Manages underlying + options streams, coordinates subscriptions |
| `kite/websocket_pool.py` | WebSocket connection pooling | Scales beyond 3000 instrument limit (Kite hardcap per connection) |
| `services/tick_processor.py` | Tick data transformation | Validates, enriches, routes ticks to channels |
| `services/tick_batcher.py` | Batched publishing | Combines 100+ ticks into single Redis publish (10x throughput) |
| `services/tick_validator.py` | Pydantic schema validation | Catches malformed tick data early |
| `publisher.py` | Redis publishing | Publishes option snapshots and underlying bars |
| `greeks_calculator.py` | Options Greeks calculation | Black-Scholes for delta, gamma, theta, vega, rho |

### 2.3 Subscription & Instrument Management

| File | Purpose | Responsibility |
|------|---------|-----------------|
| `subscription_store.py` | PostgreSQL subscription persistence | CRUD on instrument_subscriptions table |
| `instrument_registry.py` | Instrument metadata cache | Fetches/caches Kite instruments, validation |
| `strike_rebalancer.py` | Auto-rebalancing service | Dynamically adjusts option subscriptions by ATM ± OTM levels |
| `services/subscription_reconciler.py` | Load distribution | Builds account-to-instrument assignments |
| `services/historical_bootstrapper.py` | Historical data backfill | Loads candle data for Greeks calculation |

### 2.4 Order Execution Framework

| File | Purpose | Responsibility |
|------|---------|-----------------|
| `order_executor.py` | Reliable order execution | Task queue, retries, circuit breaker, memory cleanup |
| `websocket_orders.py` | WebSocket order streaming | Real-time order status updates to connected clients |
| `routes_orders.py` | Order REST endpoints | Place, modify, cancel orders |
| `batch_orders.py` | Bulk order operations | Batch place/cancel utilities |

### 2.5 Authentication & Security

| File | Purpose | Responsibility |
|------|---------|-----------------|
| `jwt_auth.py` | JWT token validation | Verifies tokens from user_service, caches JWKS |
| `auth.py` | API key authentication | X-API-Key header validation |
| `crypto.py` | Credential encryption | Fernet-based encryption for stored credentials |
| `middleware.py` | Request tracking | Request ID injection for tracing |

### 2.6 Database & Persistence

| File | Purpose | Responsibility |
|------|---------|-----------------|
| `account_store.py` | Trading account management | CRUD on encrypted account credentials |
| `subscription_store.py` | Subscription persistence | CRUD on instrument_subscriptions |
| `task_persistence.py` | Task durability | Saves/loads order tasks from database |
| `database_loader.py` | Database initialization | Schema migration, account loading |

### 2.7 Observability & Monitoring

| File | Purpose | Responsibility |
|------|---------|-----------------|
| `metrics.py` | Prometheus metrics registry | Defines all counter/gauge/histogram metrics |
| `metrics/kite_limits.py` | Broker-specific metrics | API rate limits, session status, order history |
| `metrics/service_health.py` | Service health metrics | CPU, memory, uptime, dependency health |
| `metrics/tick_metrics.py` | Tick processing metrics | Latency, throughput, Greeks calculation, validation |
| `backpressure_monitor.py` | Backpressure tracking | Queue depth, pending batches, circuit states |

### 2.8 Advanced Features

| File | Purpose | Responsibility |
|------|---------|-----------------|
| `trade_sync.py` | Order history sync | Background sync of trades from broker to database |
| `routes_sync.py` | Sync endpoints | Trigger manual/scheduled trade synchronization |
| `historical_greeks.py` | Historical Greeks enrichment | Calculates Greeks for past candles on-demand |
| `kite_failover.py` | Multi-account failover | Automatic retry with different account on API limits |
| `routes_advanced.py` | Advanced trading features | GTT, portfolios, mutual funds, advanced orders |
| `services/token_refresher.py` | Token auto-refresh | Daily token refresh service for broker credentials |

---

## 3. KEY DIRECTORIES & FILE STRUCTURE

```
/app
├── main.py                          # FastAPI app, lifespan, health/metrics endpoints
├── generator.py                     # Core MultiAccountTickerLoop (300+ lines)
├── config.py                        # Pydantic settings with 50+ configuration options
├── accounts.py                      # SessionOrchestrator, KiteAccount, credential resolution
│
├── /kite/                           # Kite Connect integration
│   ├── client.py                    # Wrapper around kiteconnect.KiteConnect
│   ├── websocket_pool.py            # Multi-connection pooling (3000 instr/conn limit)
│   ├── session.py                   # Individual account session management
│   ├── token_bootstrap.py           # Interactive token generation (TOTP + browser)
│   ├── run_kitesession.py           # Kite session runner
│   └── __init__.py
│
├── /services/                       # Modular services (Phase 4 refactoring)
│   ├── tick_processor.py            # Tick validation, routing, enrichment
│   ├── tick_batcher.py              # Batched Redis publishing (10x throughput)
│   ├── tick_validator.py            # Pydantic validation schemas
│   ├── subscription_reconciler.py   # Load balancing across accounts
│   ├── historical_bootstrapper.py   # Backfill historical data
│   ├── mock_generator.py            # Mock data for out-of-hours testing
│   ├── token_refresher.py           # Daily token refresh automation
│   └── __init__.py
│
├── /metrics/                        # Prometheus observability
│   ├── kite_limits.py               # Broker operation metrics
│   ├── service_health.py            # System health metrics
│   ├── tick_metrics.py              # Tick processing metrics
│   └── __init__.py
│
├── /utils/                          # Utility modules
│   ├── symbol_utils.py              # Symbol normalization
│   ├── task_monitor.py              # Global task exception handler
│   ├── circuit_breaker.py           # Fault tolerance pattern
│   ├── subscription_reloader.py     # Subscription reload scheduling
│   └── __init__.py
│
├── database.py / database_loader.py # Schema + initialization
├── subscription_store.py            # PostgreSQL subscriptions table
├── instrument_registry.py           # Kite instruments cache (PostgreSQL-backed)
├── account_store.py                 # Trading accounts encryption/storage
│
├── redis_client.py                  # Redis connection + circuit breaker
├── redis_publisher_v2.py            # Redis publishing (newer version)
├── publisher.py                     # Domain-specific publishers
│
├── order_executor.py                # Reliable order execution with retries
├── order_executor.py                # Circuit breaker, task queue, cleanup
├── websocket_orders.py              # WebSocket order updates
├── batch_orders.py                  # Bulk order operations
│
├── kite_failover.py                 # Multi-account failover on API limits
├── kite_rate_limiter.py             # API rate limiting (token bucket + sliding window)
├── strike_rebalancer.py             # Dynamic option strike rebalancing
├── trade_sync.py                    # Background trade synchronization
├── historical_greeks.py             # Greeks enrichment for past candles
│
├── jwt_auth.py                      # JWT token validation from user_service
├── auth.py                          # API key authentication
├── crypto.py                        # Fernet encryption for credentials
├── middleware.py                    # Request ID injection
│
├── api_models.py                    # Pydantic request/response models
├── schema.py                        # Domain models (Instrument, OptionSnapshot, etc.)
├── runtime_state.py                 # Ticker loop state tracking
├── greeks_calculator.py             # Black-Scholes Greeks calculation
├── backpressure_monitor.py          # Backpressure detection and metrics
│
├── routes_account.py                # Account info endpoints
├── routes_orders.py                 # Order CRUD endpoints
├── routes_portfolio.py              # Holdings/positions endpoints
├── routes_trading_accounts.py       # Multi-account management
├── routes_websocket.py              # WebSocket streaming endpoints
├── routes_sync.py                   # Trade sync endpoints
├── routes_gtt.py                    # Good-Till-Triggered orders
├── routes_mf.py                     # Mutual fund endpoints
├── routes_advanced.py               # Advanced features
│
├── dependencies.py                  # FastAPI dependency injection
├── user_service_client.py           # Integration with user_service
├── webhooks.py                      # Incoming webhook handlers
├── task_persistence.py              # Order task storage/recovery
│
└── __init__.py

/tests
├── /unit/                           # Unit tests (mocked dependencies)
│   ├── test_order_executor_simple.py
│   ├── test_task_monitor.py
│   ├── test_circuit_breaker.py
│   ├── test_auth.py
│   ├── test_tick_validator.py
│   ├── test_mock_state_eviction.py
│   └── ...
│
├── /integration/                    # Integration tests (real components)
│   ├── test_api_endpoints.py
│   ├── test_tick_processor.py
│   ├── test_tick_batcher.py
│   ├── test_refactored_components.py
│   └── test_websocket_basic.py
│
├── /load/                           # Load testing
│   ├── test_tick_throughput.py
│   └── conftest.py
│
└── conftest.py                      # Shared pytest fixtures

Dockerfile                           # Multi-stage Docker build (Python 3.11-slim)
requirements.txt                     # 26 dependencies
.env.example                         # Configuration template
README.md                            # Quick start guide
```

---

## 4. DATA FLOW & PROCESSING PIPELINE

### 4.1 Real-Time Tick Processing Flow

```
┌─────────────────────────────────────┐
│  Kite WebSocket (KiteTicker)       │
│  - Full/Quote/LTP mode             │
│  - Per-connection: 3000 instrument │
└──────────┬──────────────────────────┘
           │ Raw tick dict
           ▼
┌─────────────────────────────────────┐
│  TickValidator                      │
│  - Pydantic schema validation       │
│  - Range checks (price, volume)     │
│  - Early error detection            │
└──────────┬──────────────────────────┘
           │ Validated tick
           ▼
┌─────────────────────────────────────┐
│  TickProcessor.process_ticks()      │
│  - Route to underlying vs option    │
│  - Calculate Greeks (options only)  │
│  - Extract market depth (L1-L3)     │
│  - Normalize symbol                 │
└──────────┬──────────────────────────┘
           │ Processed snapshot
           ▼
┌─────────────────────────────────────┐
│  TickBatcher                        │
│  - Accumulate 100+ ticks            │
│  - 100ms time window OR 1000 size   │
│  - Flush to Redis                   │
└──────────┬──────────────────────────┘
           │ Batch of snapshots
           ▼
┌─────────────────────────────────────┐
│  Redis Publisher (Circuit Breaker)  │
│  - Resilient to Redis outages       │
│  - Gracefully drop on overload      │
│  - Don't block streaming            │
└──────────┬──────────────────────────┘
           │ Published to Redis
           ▼
┌─────────────────────────────────────┐
│  Redis Channel                      │
│  ticker:nifty:options               │
│  ticker:nifty:underlying            │
└─────────────────────────────────────┘
```

### 4.2 Subscription Management Flow

```
POST /subscriptions
     ↓
[Validate token against instrument registry]
     ↓
[Store in PostgreSQL subscriptions table]
     ↓
[Trigger background reload]
     ↓
SubscriptionReconciler.build_assignments()
  - Load all active subscriptions
  - Check account capacity (3000/connection)
  - Build load-balanced distribution
     ↓
MultiAccountTickerLoop._account_tasks
  - Create/recreate per-account stream task
  - Subscribe to assigned instruments
  - Start streaming
```

### 4.3 Order Execution Flow

```
POST /orders (place/modify/cancel)
     ↓
[Create OrderTask with UUID]
     ↓
[Enqueue in OrderExecutor.tasks dict]
     ↓
OrderExecutor.start_worker()
  ┌─────────────────────────────────┐
  │ Worker polling loop (every 1s)  │
  │ 1. Check status == PENDING      │
  │ 2. Borrow Kite client           │
  │ 3. Execute operation            │
  │ 4. Record success/failure       │
  │ 5. Exponential backoff on error │
  │ 6. After max_attempts → DEAD    │
  └─────────────────────────────────┘
     ↓
[Circuit Breaker: CLOSED/HALF_OPEN/OPEN]
  - Open if 5+ failures
  - Half-open after 60s
  - Close after 3 successful attempts
     ↓
[Metrics: order_requests_completed]
     ↓
[WebSocket broadcasts to connected clients]
```

### 4.4 Greeks Calculation Pipeline

```
Option Tick arrives
     ↓
[Extract: Strike, Expiry, LTP, IV (if available)]
     ↓
GreeksCalculator.black_scholes()
  - Underlying price from last tick_processor update
  - Interest rate: 10% (configurable)
  - Time to expiry: seconds until 15:30 IST
  - Dividend yield: 0% (configurable)
     ↓
[Compute: Delta, Gamma, Theta, Vega, Rho]
     ↓
[Publish in OptionSnapshot.greeks]
     ↓
[Store in Redis for visualization]
```

---

## 5. CONCURRENCY & PERFORMANCE PATTERNS

### 5.1 Async/Await Architecture

- **Framework:** FastAPI (async-first)
- **Event Loop:** asyncio.get_running_loop()
- **Multi-threading:** ThreadPoolExecutor for blocking Kite API calls (websocket-client)

**Key Async Components:**
```python
# Main ticker loop (async generator pattern)
async def _stream_account(account_id, instruments):
    async for ticks in kite_websocket.listen():
        await tick_processor.process_ticks(...)
        await tick_batcher.add_option(...)

# Parallel account streaming
self._account_tasks = {
    account_id: asyncio.create_task(self._stream_account(...))
    for account_id in available_accounts
}

# Concurrent Redis publishing
await redis_publisher.publish(channel, message)  # Non-blocking
```

### 5.2 Threading Models

**WebSocket Connection Pooling (Thread-safe):**
```python
# KiteWebSocketPool uses ThreadPoolExecutor
self._subscribe_executor = ThreadPoolExecutor(max_workers=5)

# Subscribe/Unsubscribe operations happen in thread pool
# Async callback marshaling via asyncio.to_thread()
```

### 5.3 Connection Pooling

**Database (PostgreSQL):**
```python
# Psycopg pool for subscription_store
AsyncConnectionPool(
    conninfo=db_url,
    min_size=1,      # Keep at least 1 connection warm
    max_size=5,      # Max 5 concurrent connections
    timeout=10       # 10s connection timeout
)
```

**Redis:**
```python
# Single connection (Redis pub/sub is inherently concurrent)
redis_client = redis.from_url(redis_url, decode_responses=True)
await redis_client.publish(channel, message)
```

**Kite API (Per-Account):**
```python
# SessionOrchestrator manages leases
async with orchestrator.borrow_account("primary") as session:
    await session.client.fetch_historical(...)
    # Enforces rate limits: max 2 concurrent per account
```

### 5.4 Caching Strategies

| Cache | TTL | Size Limit | Eviction | Use Case |
|-------|-----|-----------|----------|----------|
| `instrument_registry._cache` | 300s | 5000 items | LRU | Instrument metadata |
| `instrument_registry._cache_expiry` | Per-expiry | N/A | Manual | Expiry-specific caching |
| `_mock_generator._state` | Runtime | 5000 items | LRU | Mock market data |
| JWT JWKS | 3600s | 1 entry | Manual | User Service keys |
| Greeks calculation | Tick-time | N/A | N/A | Per-tick computation (no cache) |

### 5.5 Queue Management & Backpressure

**Tick Batcher (10x throughput improvement):**
```python
# Instead of 1 Redis publish per tick:
#   Single tick → redis.publish() → 1ms latency
#
# With batching:
#   100 ticks → 1 redis.publish() → 10x fewer publishes
#
# Implementation:
self._batch_window_ms = 100       # Flush every 100ms
self._batch_max_size = 1000       # OR when batch hits 1000 ticks
```

**Order Queue (Memory Management):**
```python
# OrderExecutor cleanup strategy
if len(self._tasks) > self._max_tasks:
    # Remove completed tasks older than 1 hour
    for task_id, task in list(self._tasks.items()):
        if task.status == "completed" and age_hours > 1:
            del self._tasks[task_id]
```

**Redis Circuit Breaker:**
```python
# If Redis unavailable for 10+ failures:
if not await circuit_breaker.can_execute():
    redis_circuit_open_drops.inc()  # Metric
    return  # Drop message gracefully, don't block
```

**Backpressure Monitoring:**
```python
class BackpressureMonitor:
    # Tracks queue depths
    redis_pending_bytes      # Pending Redis publishes
    websocket_pending_bytes  # Pending WebSocket frames
    tick_batch_size         # Current batch fill level
    
    # Alerts when exceeded
    if redis_pending_bytes > 1_000_000:  # 1MB threshold
        logger.warning("Backpressure: Redis queue at 1MB")
        # Potential actions: reduce batch size, slow tick processing
```

---

## 6. SECURITY & AUTHENTICATION

### 6.1 Authentication Mechanisms

**API Key Authentication (X-API-Key header):**
```python
# Enabled in production (enforced in config.py)
# Every non-health endpoint requires valid X-API-Key
if settings.api_key_enabled:
    # X-API-Key: <32-byte random string>
    # Hardcoded in environment for now (TODO: rotate regularly)
```

**JWT Token Validation (User Service):**
```python
# For WebSocket and sensitive REST endpoints
# Validates tokens from user_service

# Workflow:
1. Client sends Authorization: Bearer <jwt>
2. Extract kid from JWT header
3. Fetch JWKS from user_service (cached 1 hour)
4. Verify signature using kid
5. Check claims (exp, aud, scopes)
```

**Service-to-Service Authentication:**
```python
# ticker_service → user_service
USER_SERVICE_SERVICE_TOKEN = "..."  # Pre-shared token
# Used in trade_sync, account_store, routes_trading_accounts
```

### 6.2 Credential Management

**Encrypted Storage (Fernet):**
```python
# kite_accounts table stores encrypted credentials
class AccountStore:
    def __init__(self, encryption_key: str):
        self._cipher = Fernet(encryption_key)
    
    async def create_account(self, api_key, api_secret):
        encrypted = self._cipher.encrypt(api_secret.encode())
        # Store encrypted blob in database
```

**Token File Handling:**
```python
# Kite access tokens stored in:
# /app/kite/tokens/kite_token_<account_id>.json
# 
# File permissions: 600 (readable only by tickerservice user)
# Never logged or exposed in errors
```

**Environment Variable Resolution:**
```python
# accounts.py supports ${VAR_NAME} syntax
# Example: "api_key: ${KITE_API_KEY}"
# 
# Allows keeping secrets in .env, not YAML files
# Environment takes precedence over file-stored values
```

### 6.3 Input Validation & Sanitization

**Pydantic Schemas:**
```python
class SubscriptionRequest(BaseModel):
    instrument_token: int = Field(ge=1)           # > 0
    requested_mode: str = Field(default="FULL")   # Enum check
    account_id: Optional[str] = None              # If present, validate account exists

# Pre-request validation prevents malformed data reaching business logic
```

**PII Sanitization (Logs):**
```python
# Automatically redacts:
# - Email addresses: [EMAIL_REDACTED]
# - Phone numbers (10 digits): [PHONE_REDACTED]
# - Long hex strings (tokens/API keys): [TOKEN_REDACTED]

def sanitize_pii(record: dict) -> bool:
    message = record["message"]
    message = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\..+', '[EMAIL_REDACTED]', message)
    return True
```

### 6.4 Production Security Enforcement

```python
# config.py: model_post_init validation

if self.environment.lower() in ("production", "prod", "live"):
    # REQUIRE API key authentication
    if not self.api_key_enabled:
        raise ValueError("API_KEY_ENABLED must be True in production")
    
    # REQUIRE strong API key
    if not self.api_key or len(self.api_key) < 32:
        raise ValueError("API_KEY must be 32+ characters in production")
```

---

## 7. OBSERVABILITY

### 7.1 Logging Infrastructure

**Loguru Configuration (main.py):**
```python
# Console output (Docker logs)
logger.add(
    sink=lambda msg: print(msg, end=""),
    format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | {level} | {name}:{function}:{line} - {message}",
    filter=sanitize_pii,
    level="INFO"
)

# File output (persistent)
logger.add(
    sink=os.path.join(log_dir, "ticker_service.log"),
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level} | {name}:{function}:{line} - {message}",
    filter=sanitize_pii,
    rotation="100 MB",      # Auto-rotate at 100MB
    retention="7 days",     # Keep 7 days
    compression="zip",      # Compress old logs
    level="DEBUG"
)
```

**Log Rotation:**
- 100 MB per file → Auto-rotation
- 7-day retention → Automatic cleanup
- Compressed archives → Save disk space

### 7.2 Metrics (Prometheus)

**Available Metrics:**

| Metric | Type | Labels | Purpose |
|--------|------|--------|---------|
| `http_requests_total` | Counter | method, endpoint, status | API request volume |
| `http_request_duration_seconds` | Histogram | method, endpoint | API latency distribution |
| `order_requests_total` | Counter | operation, account_id | Order submission rate |
| `order_requests_completed` | Counter | operation, status, account_id | Order completion rate |
| `websocket_pool_connections` | Gauge | account_id | Active WS connections per account |
| `websocket_pool_subscribed_tokens` | Gauge | account_id | Subscribed instruments per account |
| `tick_processing_latency_seconds` | Histogram | tick_type | End-to-end tick latency |
| `greeks_calculation_latency_seconds` | Histogram | strike_offset | Greeks calc time |
| `redis_publish_failures` | Counter | N/A | Redis outage detection |
| `circuit_breaker_state` | Gauge | component | Fault tolerance status |
| `active_subscriptions_total` | Gauge | N/A | Current subscription count |
| `task_queue_depth` | Gauge | status | Order executor queue depth |

**Metrics Endpoint:**
```bash
curl http://localhost:8080/metrics

# Prometheus text format output
# Scrape interval: 15s (configure in Prometheus)
```

### 7.3 Health Checks

**`GET /health` Response:**
```json
{
  "status": "ok|degraded|critical",
  "environment": "development",
  "ticker": {
    "running": true,
    "active_subscriptions": 1250,
    "active_accounts": 2,
    "accounts": {
      "primary": {
        "status": "streaming",
        "subscriptions": 1000,
        "last_tick_at": 1699000000.123
      }
    }
  },
  "dependencies": {
    "redis": "ok|error: ...",
    "database": "ok|error: ...",
    "instrument_registry": {
      "status": "ok",
      "cached_instruments": 50000,
      "last_refresh": "2025-10-31T10:00:00Z"
    }
  }
}
```

### 7.4 Task Monitoring

**Global Exception Handler (main.py):**
```python
# TaskMonitor catches exceptions in background tasks
class TaskMonitor:
    def create_monitored_task(self, coro, task_name, on_error):
        # Wraps asyncio.create_task()
        # Catches unhandled exceptions
        # Logs with full context
        # Triggers on_error callback
```

---

## 8. ARCHITECTURE PATTERNS & DESIGN

### 8.1 Patterns Used

| Pattern | Implementation | Benefit |
|---------|----------------|---------|
| **Circuit Breaker** | `utils/circuit_breaker.py`, `redis_client.py` | Fail fast when dependency down |
| **Retry with Backoff** | `order_executor.py`, `kite_failover.py` | Transient error recovery |
| **Task Queue** | `order_executor.py` | Async order processing with durability |
| **Pub/Sub** | `redis_client.py`, `websocket_orders.py` | Real-time client updates |
| **Dependency Injection** | FastAPI `Depends()`, `dependencies.py` | Testable, modular code |
| **Repository Pattern** | `subscription_store.py`, `account_store.py` | Decoupled data access |
| **State Machine** | `OrderTask.status` enum | Clear execution flow |
| **Load Balancing** | `subscription_reconciler.py` | Even distribution across accounts |
| **Graceful Degradation** | `mock_generator.py`, Redis circuit breaker | Partial functionality when degraded |
| **Async Context Managers** | `lifespan()`, `borrow_with_failover()` | Resource cleanup guarantees |

### 8.2 Architectural Concerns & Bottlenecks

#### Critical Concerns

1. **Single Redis Connection Bottleneck**
   - Issue: All 1000s of ticks flow through single Redis connection
   - Impact: Redis network bandwidth becomes bottleneck at high volume
   - Mitigation: Tick batching (10x fewer publishes), pipeline mode
   - Status: Batcher implemented (Phase 4)

2. **Greeks Calculation CPU Cost**
   - Issue: Black-Scholes computation for every option tick
   - Impact: CPU-bound, 2-3ms per calculation × 1000 ticks/sec = bottleneck
   - Mitigation: Vectorized calculation, caching (not currently implemented)
   - Status: Being addressed

3. **WebSocket Connection Limit (3 per account)**
   - Issue: Kite hardcap prevents scaling single account beyond 9000 instruments
   - Impact: Multi-account setup required for large portfolios
   - Mitigation: WebSocket pool (implemented), load balancing (implemented)
   - Status: Architected solution in place

4. **Database Connection Pool**
   - Issue: 5 concurrent connections may be insufficient under load
   - Impact: Subscription store queries queue up
   - Mitigation: Monitor pool utilization, tune min_size/max_size
   - Status: Configuration-driven, needs monitoring

5. **OrderExecutor Task Memory**
   - Issue: Tasks in dict grow unbounded, each task ~200 bytes
   - Impact: 10,000 tasks = 2MB, old tasks must be cleaned
   - Mitigation: Auto-cleanup of completed tasks older than 1 hour
   - Status: Implemented with configurable threshold

#### Performance Bottlenecks

| Bottleneck | Metric | Threshold | Current Solution |
|------------|--------|-----------|-----------------|
| Redis writes | Publishes/sec | ~10K (single conn) | Tick batching (100ms) |
| Greeks calc | CPU ms/tick | ~2-3ms | Vectorization (TODO) |
| WS subscriptions | Instruments/account | 9000 (3 conns × 3000) | Pool + load balancing |
| DB connections | Concurrent queries | 5 | Psycopg pool |
| Memory (mock state) | LRU cache size | 5000 items | Auto-eviction |
| Task queue | Pending tasks | 10000 | Auto-cleanup |

#### Scalability Concerns

**Horizontal Scaling:**
- Multi-instance deployment: Share PostgreSQL/Redis, separate Kite accounts
- Current: Single-instance only, shared infrastructure
- Limitation: One ticker_service per Kite account (3 per person limit)

**Multi-Instrument Scaling:**
- Current: 9000 instruments per account (3 WS × 3000)
- Beyond: Requires additional Kite accounts
- Architectural: Fully supported via multi-account design

**Throughput Scaling:**
- Current: ~1000 ticks/sec sustainable
- Beyond: Tick batching 10x improvement (tested in Phase 4)
- Limitation: Redis/PostgreSQL as shared bottleneck

---

## 9. EXTERNAL DEPENDENCIES & INTEGRATIONS

### 9.1 Third-Party Services

| Service | Purpose | Integration Point | Fallback |
|---------|---------|------------------|----------|
| **Kite Connect (NSE broker)** | Market data + order execution | `kite/client.py`, `generator.py` | Mock data (ENABLE_MOCK_DATA) |
| **User Service** | JWT validation, account management | `jwt_auth.py`, `routes_trading_accounts.py` | None (optional) |
| **Redis** | Pub/sub messaging | `redis_client.py`, `publisher.py` | Circuit breaker drops messages |
| **PostgreSQL** | Instrument, subscription, account storage | `subscription_store.py`, `instrument_registry.py`, `account_store.py` | Required (no fallback) |

### 9.2 Internal Service Dependencies

```
ticker_service
├── Depends: PostgreSQL (instruments, subscriptions, accounts)
├── Depends: Redis (real-time tick publishing)
├── Depends: Kite Connect (market data, orders)
├── Depends (optional): user_service (trading accounts, JWT)
│
└── Used by:
    ├── Frontend (WebSocket tick streaming, REST API)
    ├── Backend (order execution, trade sync)
    ├── Monitoring (Prometheus/Grafana)
    └── Mobile (REST API endpoints)
```

### 9.3 Configuration Requirements

**Required Connections:**
```env
# Kite Connect API
KITE_API_KEY=<from https://developers.kite.trade/>
KITE_API_SECRET=<from Kite developer console>
KITE_ACCESS_TOKEN=<generated via token_bootstrap.py>

# PostgreSQL
INSTRUMENT_DB_HOST=postgres.example.com
INSTRUMENT_DB_PORT=5432
INSTRUMENT_DB_NAME=stocksblitz_unified
INSTRUMENT_DB_USER=stocksblitz
INSTRUMENT_DB_PASSWORD=<secure password>

# Redis
REDIS_URL=redis://<password>@redis.example.com:6379/0
```

**Optional Integrations:**
```env
# User Service (for trading accounts)
USER_SERVICE_BASE_URL=http://user_service:8001
USER_SERVICE_SERVICE_TOKEN=<inter-service token>
USE_USER_SERVICE_ACCOUNTS=true

# Kite account from database instead of YAML
LOAD_ACCOUNTS_FROM_DB=true
```

---

## 10. DEPLOYMENT & DOCKER CONFIGURATION

### 10.1 Docker Setup

**Dockerfile Strategy:**
```dockerfile
FROM python:3.11-slim

# Security: Non-root user
RUN useradd -m -u 1000 tickerservice
USER tickerservice

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8080}/health || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]  # Init system for signal handling
CMD ["python3", "start_ticker.py"]
```

**Runtime Environment:**
- Base image: `python:3.11-slim` (security updates, minimal)
- User: `tickerservice:tickerservice` (UID 1000)
- Workdir: `/app`
- Health check: Every 30s, 3 retries before marking unhealthy
- Logging: Unbuffered Python output (real-time Docker logs)

### 10.2 Container Orchestration

**Port Mapping:**
```yaml
# docker-compose.yml (example)
ticker_service:
  ports:
    - "8080:8080"  # FastAPI
  environment:
    ENVIRONMENT: production
    PORT: 8080
    REDIS_URL: redis://redis:6379/0
    INSTRUMENT_DB_HOST: postgres
```

**Volumes (Optional):**
```yaml
volumes:
  - ./logs:/app/logs              # Persistent logs
  - ./tokens:/app/tokens          # Persistent Kite tokens
  - ./data:/app/data              # Persistent state
```

### 10.3 Startup Sequence

```bash
# start_ticker.py workflow
1. Set KITE_TOKEN_DIR environment variable
2. Load .env from app/kite/.env
3. Run Kite token bootstrap (interactive if needed)
4. Start uvicorn server
5. FastAPI lifespan() triggers:
   - Redis connection
   - PostgreSQL initialization
   - Account store setup
   - Ticker loop start
   - Strike rebalancer start
   - Token refresher start
   - OrderExecutor worker start
   - WebSocket listener start
```

**Liveness Probe:**
```bash
curl -f http://localhost:8080/health || exit 1
```

**Readiness Probe:**
```bash
# Custom: Check if ticker is running + dependencies healthy
# Endpoint: GET /health
# Status codes: 200 (ready), 503 (degraded)
```

---

## 11. TESTING STRATEGY

### 11.1 Test Structure

```
/tests
├── conftest.py                     # Shared fixtures (asyncio, mocks)
│
├── /unit/                          # Mocked, fast (<100ms each)
│   ├── test_order_executor_simple.py          # Order execution
│   ├── test_circuit_breaker.py               # Fault tolerance
│   ├── test_task_monitor.py                  # Exception handling
│   ├── test_tick_validator.py                # Data validation
│   ├── test_auth.py                         # Authentication
│   └── ...
│
├── /integration/                   # Real components, slower (1-5s)
│   ├── test_api_endpoints.py                 # REST API
│   ├── test_tick_processor.py                # Tick processing
│   ├── test_tick_batcher.py                  # Batching
│   ├── test_websocket_basic.py               # WebSocket
│   └── test_refactored_components.py         # Phase 4 components
│
└── /load/                          # Performance testing
    └── test_tick_throughput.py               # 1000+ ticks/sec
```

### 11.2 Coverage

**Measured Coverage (from pytest-cov):**
- Lines: ~85%
- Branches: ~70%
- Exclusions: External API calls, resource cleanup in finally blocks

**Test Execution:**
```bash
# Unit tests only (fast)
pytest tests/unit -v

# Integration tests
pytest tests/integration -v

# Load tests (slow)
pytest tests/load -v

# All with coverage
pytest --cov=app --cov-report=html

# CI/CD: Run on every commit
```

---

## 12. RECENT IMPROVEMENTS (Phase 4 & 5)

### 12.1 Performance Enhancements

1. **Tick Batching (Phase 4)**
   - 100ms time windows or 1000-tick batches
   - 10x fewer Redis publishes
   - Measured improvement: 1000 ticks/sec → 10,000 ticks/sec capacity

2. **Tick Validation (Phase 4)**
   - Early error detection with Pydantic schemas
   - Prevents malformed data propagation
   - Metrics tracking for validation errors

3. **Task Monitoring (Phase 5)**
   - Global exception handler for background tasks
   - Prevents silent failures in ticker loop
   - Logs with full context for debugging

4. **Service Health Metrics (Phase 5)**
   - CPU, memory, uptime tracking
   - Dependency health status
   - Integrated with Grafana dashboards

### 12.2 Reliability Improvements

1. **Strike Rebalancer**
   - Auto-rebalance option subscriptions by ATM ± OTM
   - Adjusts to underlying price movements
   - Prevents stale strike subscriptions

2. **Token Refresher Service**
   - Daily automatic token refresh
   - Prevents authentication failures mid-day
   - Transparent credential management

3. **Trade Sync Service**
   - Background synchronization of fills/cancellations
   - Periodic reconciliation with broker
   - Configurable sync interval

4. **Historical Greeks Enrichment**
   - Calculates Greeks for past candles
   - Enables options analysis on historical data
   - Integrated with `/history` endpoint

---

## 13. POTENTIAL ARCHITECTURAL IMPROVEMENTS

### High Priority

1. **Redis Connection Pooling**
   - Current: Single connection for all publishes
   - Proposal: Connection pool with load balancing
   - Expected benefit: 2-5x throughput increase

2. **Greeks Calculation Vectorization**
   - Current: Per-tick Black-Scholes calculation
   - Proposal: NumPy/Pandas vectorized calculations
   - Expected benefit: 5-10x CPU reduction

3. **Subscription Caching Layer**
   - Current: Database query for every assignment rebuild
   - Proposal: In-memory cache with TTL
   - Expected benefit: 100ms faster rebalancing

4. **Order Task Persistence**
   - Current: In-memory dict (lost on restart)
   - Proposal: Database-backed task store
   - Expected benefit: Durability across crashes

### Medium Priority

1. **Multi-Instance Coordination**
   - Current: Single-instance only
   - Proposal: Distributed locking (Redis/etcd) for account assignments
   - Expected benefit: Horizontal scaling, HA

2. **Streaming Optimization**
   - Current: Per-tick processing
   - Proposal: Aggregate per underlying per 100ms
   - Expected benefit: Reduced CPU, cleaner data flow

3. **API Key Rotation**
   - Current: Static keys in environment
   - Proposal: Automated rotation via secrets manager
   - Expected benefit: Security, auditability

4. **Circuit Breaker Persistence**
   - Current: In-memory state (reset on restart)
   - Proposal: Redis-backed circuit state
   - Expected benefit: Coordinated failover

---

## 14. KEY FILES & QUICK REFERENCE

### Critical Files (Understand First)

1. **`app/main.py`** (827 lines)
   - FastAPI app setup, lifespan management
   - All critical services initialized here
   - Health/metrics endpoints

2. **`app/generator.py`** (350+ lines)
   - MultiAccountTickerLoop orchestration
   - Streaming core logic
   - Subscription reconciliation

3. **`app/accounts.py`** (300+ lines)
   - SessionOrchestrator (multi-account management)
   - Credential loading and resolution
   - Account lease system

4. **`app/kite/websocket_pool.py`** (200+ lines)
   - WebSocket pooling beyond 3000 limit
   - Connection health monitoring
   - Subscription distribution

5. **`app/order_executor.py`** (350+ lines)
   - Reliable order execution with retries
   - Task queue and circuit breaker
   - Completion guarantees

### Supporting Files

- `config.py` - 50+ configuration options with validation
- `redis_client.py` - Redis connection with circuit breaker
- `subscription_store.py` - PostgreSQL subscription CRUD
- `instrument_registry.py` - Instrument metadata cache
- `jwt_auth.py` - JWT validation from user_service
- `services/tick_processor.py` - Tick transformation and routing
- `services/tick_batcher.py` - Batched Redis publishing
- `metrics.py` - Prometheus metrics definitions

---

## SUMMARY

The ticker_service is a **sophisticated, production-grade streaming and order execution system** with:

- **Multi-account streaming** with load balancing across Kite API limits
- **High-throughput tick processing** (1000+ ticks/sec) with batching and validation
- **Reliable order execution** with task queues, retries, and circuit breakers
- **Comprehensive observability** via Prometheus, structured logging, and health checks
- **Security-first design** with JWT validation, encrypted credentials, PII redaction
- **Graceful degradation** when dependencies fail (Redis circuit breaker, mock data fallback)
- **Well-tested codebase** with unit, integration, and load tests (85%+ coverage)
- **Clear architectural patterns** (Circuit Breaker, Retry, Pub/Sub, Repository, State Machine)

**Key Strengths:**
- Modular service design (tick processor, batcher, validator, Greeks calculator)
- Async-first for high concurrency
- Fault tolerance throughout (failover, circuit breakers, task durability)
- Observable via metrics and structured logging

**Identified Bottlenecks & Mitigation:**
- Single Redis connection → Batching (implemented), pooling (recommended)
- Greeks CPU cost → Vectorization (recommended)
- WebSocket limits → Connection pool + load balancing (implemented)
- Task memory → Auto-cleanup (implemented)

---

