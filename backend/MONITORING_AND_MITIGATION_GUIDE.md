### Comprehensive Monitoring and Mitigation Guide

**Version:** 1.0
**Date:** 2025-10-31
**Purpose:** Detect and mitigate backpressure, memory leaks, architectural issues, and implement rate limiting

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Backpressure Detection & Mitigation](#backpressure-detection--mitigation)
3. [Memory Leak Detection & Mitigation](#memory-leak-detection--mitigation)
4. [Architectural Health Monitoring](#architectural-health-monitoring)
5. [Rate Limiting Strategy](#rate-limiting-strategy)
6. [Setup and Configuration](#setup-and-configuration)
7. [Alert Response Playbook](#alert-response-playbook)
8. [Grafana Dashboards](#grafana-dashboards)

---

## Architecture Overview

### Monitoring Stack

```
┌──────────────────────────────────────────────────────────────┐
│                    FastAPI Application                        │
│  ┌────────────────┐  ┌──────────────┐  ┌─────────────────┐  │
│  │ Rate Limiting  │  │  Advanced    │  │  Prometheus     │  │
│  │  Middleware    │  │  Monitoring  │  │  Metrics        │  │
│  └────────────────┘  └──────────────┘  └─────────────────┘  │
└──────────────────────────────────────────────────────────────┘
                              │
                ┌─────────────┴────────────┐
                │                          │
         ┌──────▼──────┐          ┌───────▼────────┐
         │  Prometheus │          │     Redis      │
         │   Server    │          │ (Rate Limits)  │
         └──────┬──────┘          └────────────────┘
                │
         ┌──────▼──────┐
         │   Grafana   │
         │  Dashboards │
         └──────┬──────┘
                │
         ┌──────▼──────┐
         │  Alertmanager│
         │ (PagerDuty/  │
         │   Slack)     │
         └─────────────┘
```

### Key Components

1. **monitoring_advanced.py**: Comprehensive monitoring module
   - Backpressure detector
   - Memory leak detector
   - Architectural health monitor

2. **rate_limiting.py**: Multi-tier rate limiting
   - IP-based (current)
   - User-based (future)
   - Redis-backed distributed limiting

3. **Prometheus**: Metrics collection and alerting
4. **Grafana**: Visualization and dashboards
5. **Alertmanager**: Alert routing and notification

---

## Backpressure Detection & Mitigation

### What is Backpressure?

Backpressure occurs when the system receives requests faster than it can process them, leading to:
- Queue buildup (DB connections, async tasks)
- Event loop lag
- Increased latency
- Memory exhaustion

### Detection Metrics

| Metric | Threshold | Severity | Action |
|--------|-----------|----------|--------|
| `backpressure_event_loop_lag_seconds` | > 0.1s | Warning | Investigate slow async operations |
| `backpressure_event_loop_lag_seconds` | > 0.5s | Critical | Immediate action - shed load |
| `backpressure_db_queue_size` | > 10 | Warning | Increase DB pool size |
| `backpressure_async_tasks_pending` | > 500 | Warning | Check for task leaks |

### Mitigation Strategies

#### 1. Load Shedding

```python
# In middleware or endpoint
if backpressure_detected():
    return Response(
        status_code=503,
        content={"error": "Service temporarily unavailable"},
        headers={"Retry-After": "30"}
    )
```

#### 2. Database Pool Tuning

```python
# app/database.py
pool = await asyncpg.create_pool(
    min_size=10,
    max_size=50,  # Increase from 20
    max_inactive_connection_lifetime=300,
    command_timeout=30,
)
```

#### 3. Async Task Management

```python
# Limit concurrent tasks
semaphore = asyncio.Semaphore(100)

async def process_with_limit():
    async with semaphore:
        await process_task()
```

#### 4. Circuit Breaker Pattern

```python
from app.monitoring_advanced import CircuitBreaker

db_breaker = CircuitBreaker(failure_threshold=5, timeout=60)

def query_database():
    return db_breaker.call(lambda: execute_query())
```

### Example Alert Response

**Alert**: `HighEventLoopLag`

**Response Steps**:
1. Check Grafana dashboard for correlating metrics
2. Review slow query logs
3. Check for blocking I/O operations
4. Consider enabling load shedding
5. Scale horizontally if needed

---

## Memory Leak Detection & Mitigation

### What are Memory Leaks?

Memory leaks occur when allocated memory is not released, causing:
- Gradual memory growth
- OOM (Out of Memory) kills
- Performance degradation
- Service instability

### Detection Metrics

| Metric | Threshold | Action |
|--------|-----------|--------|
| `memory_rss_bytes` | > 4GB | Investigate growth |
| `memory_growth_rate_bytes_per_second` | > 1MB/s for 10min | Memory leak suspected |
| `memory_gc_collections_total` | High rate | GC pressure - optimize |

### Common Leak Sources

#### 1. Unclosed Connections

```python
# BAD: Connection leak
async def query_data():
    conn = await pool.acquire()
    result = await conn.fetch("SELECT ...")
    # MISSING: await pool.release(conn)
    return result

# GOOD: Proper cleanup
async def query_data():
    async with pool.acquire() as conn:
        result = await conn.fetch("SELECT ...")
    return result
```

#### 2. Growing Caches

```python
# BAD: Unbounded cache
cache = {}  # Grows forever

# GOOD: LRU cache with size limit
from functools import lru_cache

@lru_cache(maxsize=1000)
def expensive_function(param):
    ...
```

#### 3. Event Listeners

```python
# BAD: Accumulating listeners
async def setup():
    websocket.on("message", handler)
    # Never removed

# GOOD: Cleanup on disconnect
async def setup():
    websocket.on("message", handler)
    try:
        await websocket.wait_closed()
    finally:
        websocket.remove_listener("message", handler)
```

### Mitigation Strategies

#### 1. Enable Memory Profiling

```python
# In production with low overhead
from app.monitoring_advanced import MemoryLeakDetector

detector = MemoryLeakDetector(
    snapshot_interval=60,
    enable_tracemalloc=False  # Use in dev only
)
await detector.monitor_loop()
```

#### 2. Force Garbage Collection

```python
import gc

# Periodic GC (use sparingly)
gc.collect()
```

#### 3. Memory Limits

```python
# Docker container limits
services:
  backend:
    deploy:
      resources:
        limits:
          memory: 4G
        reservations:
          memory: 2G
```

#### 4. Automatic Restarts

```python
# In production, restart service when memory > threshold
if memory_usage > THRESHOLD:
    logger.critical("Memory limit reached - graceful restart")
    await graceful_shutdown()
    sys.exit(1)  # Let orchestrator restart
```

### Debugging Memory Leaks

```python
# Development: Enable detailed tracking
import tracemalloc

tracemalloc.start()

# Take snapshots
snapshot1 = tracemalloc.take_snapshot()
# ... run operations ...
snapshot2 = tracemalloc.take_snapshot()

# Compare
top_stats = snapshot2.compare_to(snapshot1, 'lineno')
for stat in top_stats[:10]:
    print(stat)
```

---

## Architectural Health Monitoring

### Circuit Breaker States

| State | Description | Action |
|-------|-------------|--------|
| **Closed** | Normal operation | None |
| **Open** | Service failing | Reject requests, return cached data |
| **Half-Open** | Testing recovery | Allow limited traffic |

### Dependency Health Checks

```python
from app.monitoring_advanced import ArchitecturalHealthMonitor

monitor = ArchitecturalHealthMonitor()

# Register circuit breakers
monitor.register_circuit_breaker("database", failure_threshold=5, timeout=60)
monitor.register_circuit_breaker("redis", failure_threshold=3, timeout=30)

# Health checks
async def check_database():
    await db_pool.fetchval("SELECT 1")

async def check_redis():
    await redis_client.ping()

await monitor.check_dependency("database", check_database)
await monitor.check_dependency("redis", check_redis)
```

### Slow Query Monitoring

```python
# Record slow queries
async def execute_with_monitoring(query, query_type):
    start = time.time()
    try:
        result = await conn.fetch(query)
        duration = time.time() - start
        monitor.record_slow_query(query_type, duration, query)
        return result
    except asyncio.TimeoutError:
        query_timeout_count.labels(query_type=query_type).inc()
        raise
```

---

## Rate Limiting Strategy

### Current Implementation: IP-Based

Since user service is not yet built, we use **IP-based rate limiting**:

```python
from app.rate_limiting import RateLimitMiddleware, IPBasedIdentifier

# In app/main.py
app.add_middleware(
    RateLimitMiddleware,
    redis_client=redis_client,
    identifier_strategy=IPBasedIdentifier(),
)
```

### Rate Limit Tiers

| Tier | Req/Second | Req/Minute | Req/Hour | Use Case |
|------|------------|------------|----------|----------|
| **FREE** | 5 | 100 | 1,000 | Public users |
| **PREMIUM** | 20 | 500 | 10,000 | Paid users |
| **ENTERPRISE** | 100 | 3,000 | 50,000 | Enterprise |
| **INTERNAL** | 1,000 | 30,000 | 500,000 | Internal services |

### Endpoint-Specific Limits

```python
# Heavy endpoints have stricter limits
TIER_CONFIGS = {
    RateLimitTier.FREE: RateLimitConfig(
        requests_per_second=5,
        requests_per_minute=100,
        endpoint_limits={
            "/fo/moneyness-series": {
                "second": 2,
                "minute": 30,
                "hour": 300
            },
        }
    )
}
```

### Future: User-Based Rate Limiting

When user service is ready:

```python
from app.rate_limiting import UserBasedIdentifier, TierResolver

# Extract user_id from JWT
tier_resolver = TierResolver(user_service_available=True)

app.add_middleware(
    RateLimitMiddleware,
    redis_client=redis_client,
    identifier_strategy=UserBasedIdentifier(),
    tier_resolver=tier_resolver,
)
```

### Rate Limit Headers

Clients receive these headers:

```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1698765432
Retry-After: 30  (if rate limited)
```

### DDoS Protection

```yaml
# Prometheus alert
- alert: PossibleDDoSAttack
  expr: rate(rate_limit_blocks_total[1m]) > 100
  for: 2m
  annotations:
    summary: "{{ $value }} requests/sec blocked - possible DDoS"
```

**Response**:
1. Enable stricter rate limits
2. Block abusive IPs at firewall/CDN level
3. Enable CAPTCHA for suspicious traffic
4. Scale infrastructure if legitimate traffic spike

---

## Setup and Configuration

### 1. Install Dependencies

```bash
# Already in requirements.txt
pip install prometheus-client psutil
```

### 2. Update main.py

```python
# app/main.py
from app.monitoring_advanced import monitoring_orchestrator
from app.rate_limiting import create_rate_limit_middleware

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start monitoring
    await monitoring_orchestrator.start(
        db_pool=data_manager.pool,
        redis_client=redis_client
    )

    # Add rate limiting
    rate_limit_mw = create_rate_limit_middleware(
        redis_client=redis_client,
        use_user_based=False  # Set to True when user service ready
    )
    app.add_middleware(rate_limit_mw)

    yield

    # Cleanup
    await monitoring_orchestrator.stop()
```

### 3. Start Prometheus and Grafana

```bash
cd monitoring
docker-compose up -d
```

### 4. Access Dashboards

- **Grafana**: http://localhost:3000 (admin/admin)
- **Prometheus**: http://localhost:9090

### 5. Import Grafana Dashboards

1. Login to Grafana
2. Go to Dashboards → Import
3. Upload `grafana_dashboard.json`

---

## Alert Response Playbook

### High Event Loop Lag

**Severity**: Warning/Critical
**Threshold**: > 100ms (warning), > 500ms (critical)

**Investigation**:
```bash
# Check async task count
curl http://localhost:8081/metrics | grep backpressure_async_tasks

# Check for blocking operations in logs
docker logs tv-backend --tail=1000 | grep -i "blocking\|slow"
```

**Mitigation**:
1. Identify slow async operations (DB queries, external APIs)
2. Add timeouts to prevent hanging tasks
3. Increase worker processes/threads
4. Enable load shedding

---

### Memory Leak Detected

**Severity**: Critical
**Threshold**: > 1MB/s growth for 10+ minutes

**Investigation**:
```bash
# Check memory usage
curl http://localhost:8081/metrics | grep memory_rss_bytes

# Check for connection leaks
# In PostgreSQL
SELECT count(*) FROM pg_stat_activity WHERE datname='stocksblitz_unified';

# Check Redis connections
redis-cli CLIENT LIST | wc -l
```

**Mitigation**:
1. Review recent code changes
2. Check for unclosed connections
3. Review cache implementations
4. Consider graceful restart
5. Enable memory profiling in dev

---

### Database Pool Exhausted

**Severity**: Warning
**Threshold**: > 10 waiting connections

**Investigation**:
```bash
# Check DB pool stats
curl http://localhost:8081/health | jq '.db_pool'

# Check slow queries
SELECT query, mean_exec_time, calls
FROM pg_stat_statements
ORDER BY mean_exec_time DESC
LIMIT 10;
```

**Mitigation**:
1. Increase pool size (if resources available)
2. Optimize slow queries
3. Add indexes
4. Implement connection pooling best practices
5. Consider read replicas

---

### High Rate Limit Block Rate

**Severity**: Warning
**Threshold**: > 10 blocks/sec for 5 minutes

**Investigation**:
```bash
# Check which endpoints are blocked
curl http://localhost:8081/metrics | grep rate_limit_blocks_total

# Check blocked IPs in Redis
redis-cli KEYS "rate_limit:*"
```

**Mitigation**:
1. Verify legitimate traffic vs abuse
2. Whitelist legitimate high-volume clients
3. Adjust rate limits for specific endpoints
4. Contact affected users
5. Enable CAPTCHA if bot traffic

---

## Grafana Dashboards

### Main Dashboard Panels

1. **System Overview**
   - Memory usage (RSS, VMS)
   - CPU usage
   - Event loop lag
   - Request rate

2. **Backpressure**
   - DB queue size
   - Redis connection pool
   - Async task count
   - Event loop lag timeline

3. **API Performance**
   - Request latency (P50, P95, P99)
   - Error rate
   - Throughput
   - Slow queries

4. **Rate Limiting**
   - Requests by tier
   - Block rate
   - Remaining quota
   - Top blocked endpoints

5. **Memory**
   - RSS/VMS over time
   - Growth rate
   - GC collections
   - Top objects (if tracemalloc enabled)

6. **Dependencies**
   - Database health
   - Redis health
   - Circuit breaker states
   - External service latency

---

## Best Practices

### 1. Always Use Context Managers

```python
# Database connections
async with pool.acquire() as conn:
    result = await conn.fetch(query)

# Redis connections
async with redis_client.pipeline() as pipe:
    await pipe.set("key", "value")
    await pipe.execute()
```

### 2. Set Timeouts

```python
# Query timeout
conn = await pool.fetchval(query, timeout=30)

# HTTP timeout
async with httpx.AsyncClient(timeout=10.0) as client:
    response = await client.get(url)
```

### 3. Monitor Resource Usage

```python
# Add resource tracking to long-running operations
with track_resource_usage("expensive_operation"):
    result = await expensive_operation()
```

### 4. Implement Graceful Degradation

```python
# Fallback to cached data if primary source fails
try:
    data = await fetch_from_primary()
except Exception:
    data = await fetch_from_cache()
```

### 5. Regular Health Checks

```bash
# Automated health monitoring
*/5 * * * * curl -f http://localhost:8081/health || alert-on-call
```

---

## Troubleshooting

### Metrics Not Appearing in Prometheus

1. Check `/metrics` endpoint is accessible
2. Verify Prometheus scrape config
3. Check firewall/network connectivity
4. Review Prometheus logs

### High Memory Usage

1. Enable memory profiling
2. Review object counts
3. Check for circular references
4. Monitor GC behavior

### Rate Limiting Not Working

1. Verify Redis connectivity
2. Check Redis key expiry
3. Review identifier strategy
4. Test with curl/postman

---

## References

- Prometheus documentation: https://prometheus.io/docs
- Grafana dashboards: https://grafana.com/docs
- FastAPI best practices: https://fastapi.tiangolo.com/
- Python asyncio: https://docs.python.org/3/library/asyncio.html
- Rate limiting patterns: https://www.cloudflare.com/learning/bots/what-is-rate-limiting/

---

**Last Updated**: 2025-10-31
**Version**: 1.0
**Maintainer**: Backend Team
