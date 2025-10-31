# Monitoring & Rate Limiting Setup Guide

**Quick setup guide for comprehensive monitoring, backpressure detection, and rate limiting**

---

## 🚀 Quick Start (5 minutes)

### Step 1: Start Monitoring Stack

```bash
cd /mnt/stocksblitz-data/Quantagro/tradingview-viz/backend/monitoring
docker-compose -f docker-compose.monitoring.yml up -d
```

This starts:
- ✅ **Prometheus** (http://localhost:9090) - Metrics collection
- ✅ **Grafana** (http://localhost:3000) - Dashboards (admin/admin)
- ✅ **Alertmanager** (http://localhost:9093) - Alert routing
- ✅ **Node Exporter** - System metrics
- ✅ **cAdvisor** - Container metrics

### Step 2: Integrate with Backend

Update `app/main.py`:

```python
from app.monitoring_advanced import monitoring_orchestrator
from app.rate_limiting import create_rate_limit_middleware

@asynccontextmanager
async def lifespan(app: FastAPI):
    global data_manager, cache_manager, redis_client

    # ... existing startup code ...

    # ✨ NEW: Start advanced monitoring
    await monitoring_orchestrator.start(
        db_pool=data_manager.pool,
        redis_client=redis_client
    )

    # ✨ NEW: Add rate limiting
    logger.info("Configuring rate limiting middleware")

    yield

    # Cleanup
    await monitoring_orchestrator.stop()
    # ... existing cleanup code ...

# ✨ NEW: Add rate limiting middleware AFTER app creation
app = FastAPI(lifespan=lifespan)

# Add rate limiting (IP-based for now)
from app.rate_limiting import RateLimitMiddleware, IPBasedIdentifier
app.add_middleware(
    RateLimitMiddleware,
    redis_client=redis_client,
    identifier_strategy=IPBasedIdentifier(),
    exempt_endpoints=["/health", "/metrics", "/docs", "/openapi.json"]
)
```

### Step 3: Verify Setup

```bash
# Check metrics endpoint
curl http://localhost:8081/metrics

# Should see metrics like:
# backpressure_event_loop_lag_seconds
# memory_rss_bytes
# rate_limit_hits_total
```

### Step 4: Access Dashboards

1. **Grafana**: http://localhost:3000
   - Username: `admin`
   - Password: `admin`

2. **Prometheus**: http://localhost:9090
   - Query examples:
     - `rate(tradingview_requests_total[5m])`
     - `memory_rss_bytes / 1024 / 1024 / 1024`
     - `backpressure_event_loop_lag_seconds`

---

## 📊 What You Get

### 1. Backpressure Detection

**Metrics:**
- Event loop lag monitoring (every 5 seconds)
- Database connection pool queue size
- Redis connection pool monitoring
- Async task count tracking

**Alerts:**
- ⚠️ Warning: Event loop lag > 100ms for 2 minutes
- 🚨 Critical: Event loop lag > 500ms for 1 minute
- ⚠️ Warning: DB pool queue > 10 for 2 minutes

**Access:**
```python
# Get current backpressure status
from app.monitoring_advanced import monitoring_orchestrator

health = monitoring_orchestrator.get_health_summary()
print(health["backpressure"])
# {
#   "has_backpressure": False,
#   "severity": "normal",
#   "event_loop_lag_ms": 2.5
# }
```

---

### 2. Memory Leak Detection

**Metrics:**
- RSS (Resident Set Size) tracking
- Memory growth rate calculation
- Garbage collection statistics
- Top memory consumers (optional with tracemalloc)

**Alerts:**
- ⚠️ Warning: Memory > 4GB for 5 minutes
- 🚨 Critical: Memory growth > 1MB/sec for 10 minutes
- ⚠️ Warning: High GC rate (> 10 collections/sec)

**Access:**
```python
health = monitoring_orchestrator.get_health_summary()
print(health["memory"])
# {
#   "rss_mb": 512.3,
#   "percent": 25.5,
#   "growth_rate_mb_per_sec": 0.02
# }
```

---

### 3. Rate Limiting

**Current Implementation: IP-Based**

| Tier | Req/Second | Req/Minute | Req/Hour |
|------|------------|------------|----------|
| FREE (default) | 5 | 100 | 1,000 |
| PREMIUM | 20 | 500 | 10,000 |
| ENTERPRISE | 100 | 3,000 | 50,000 |

**Endpoint-Specific Limits:**
- `/fo/moneyness-series`: 2/sec, 30/min, 300/hour (FREE tier)
- `/fo/strike-distribution`: 2/sec, 30/min, 300/hour (FREE tier)

**Client Response:**
```
HTTP/1.1 200 OK
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1698765432
```

**When Rate Limited:**
```json
HTTP/1.1 429 Too Many Requests
Retry-After: 30

{
  "error": "Rate limit exceeded",
  "retry_after": 30,
  "limit": 100,
  "period": "minute"
}
```

**Metrics:**
- `rate_limit_hits_total{identifier_type="ip",tier="free",endpoint="/fo/strike-distribution"}`
- `rate_limit_blocks_total` - Tracks blocked requests
- `rate_limit_remaining_requests` - Histogram of remaining quota

---

### 4. Architectural Health

**Features:**
- Circuit breaker pattern for external services
- Dependency health checks (DB, Redis)
- Slow query detection and logging
- Query timeout tracking

**Usage:**
```python
from app.monitoring_advanced import monitoring_orchestrator

arch_monitor = monitoring_orchestrator.arch_health_monitor

# Register circuit breaker
arch_monitor.register_circuit_breaker(
    "external_api",
    failure_threshold=5,
    timeout=60
)

# Check dependency
async def check_db():
    await db_pool.fetchval("SELECT 1")

await arch_monitor.check_dependency("database", check_db)
```

---

## 🔧 Configuration

### Adjust Rate Limits

Edit `app/rate_limiting.py`:

```python
TIER_CONFIGS = {
    RateLimitTier.FREE: RateLimitConfig(
        requests_per_second=10,  # Increase from 5
        requests_per_minute=200, # Increase from 100
        requests_per_hour=2000,  # Increase from 1000
        burst_size=20,
        endpoint_limits={
            "/fo/moneyness-series": {"second": 5, "minute": 60},
        }
    ),
}
```

### Configure Alerting

Edit `monitoring/alertmanager.yml`:

```yaml
receivers:
  - name: 'slack'
    slack_configs:
      - channel: '#your-channel'
        api_url: 'https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK'
```

### Enable Memory Profiling (Dev Only)

```python
from app.monitoring_advanced import MemoryLeakDetector

detector = MemoryLeakDetector(
    snapshot_interval=60,
    enable_tracemalloc=True  # Enable for detailed tracking
)
```

---

## 📈 Key Queries

### Prometheus Queries

**Request Rate:**
```promql
rate(tradingview_requests_total[5m])
```

**P95 Latency:**
```promql
histogram_quantile(0.95, rate(tradingview_request_duration_seconds_bucket[5m]))
```

**Memory Growth:**
```promql
rate(memory_rss_bytes[10m])
```

**Rate Limit Blocks:**
```promql
rate(rate_limit_blocks_total[5m])
```

**Event Loop Lag:**
```promql
backpressure_event_loop_lag_seconds > 0.1
```

---

## 🚨 Alert Response

### When You Get an Alert

1. **Check Grafana Dashboard**: http://localhost:3000
   - System Overview panel
   - Look for correlated metrics

2. **Check Application Logs**:
   ```bash
   docker logs tv-backend --tail=1000 --follow
   ```

3. **Check Metrics Directly**:
   ```bash
   curl http://localhost:8081/metrics | grep <metric_name>
   ```

4. **Review Health Summary**:
   ```bash
   curl http://localhost:8081/health | jq
   ```

### Common Issues

| Alert | Likely Cause | Quick Fix |
|-------|--------------|-----------|
| High Event Loop Lag | Blocking I/O | Add `await` to sync operations |
| Memory Leak | Unclosed connections | Check `async with` usage |
| DB Pool Exhausted | Slow queries | Optimize queries, add indexes |
| High Rate Limit Blocks | Bot traffic | Review blocked IPs, adjust limits |

---

## 🔄 Migrating to User-Based Rate Limiting

When your user service is ready:

### Step 1: Update Rate Limiting Config

```python
# In app/main.py
from app.rate_limiting import UserBasedIdentifier, TierResolver

app.add_middleware(
    RateLimitMiddleware,
    redis_client=redis_client,
    identifier_strategy=UserBasedIdentifier(),  # Changed from IPBasedIdentifier
    tier_resolver=TierResolver(user_service_available=True),
)
```

### Step 2: Implement User ID Extraction

Edit `app/rate_limiting.py`:

```python
class UserBasedIdentifier(IdentifierStrategy):
    async def get_identifier(self, request: Request) -> str:
        # Extract JWT from Authorization header
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return await IPBasedIdentifier().get_identifier(request)

        token = auth_header.replace("Bearer ", "")

        # Decode JWT and extract user_id
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
            user_id = payload.get("user_id")
            return f"user:{user_id}"
        except:
            # Fallback to IP-based
            return await IPBasedIdentifier().get_identifier(request)
```

### Step 3: Implement Tier Resolution

```python
class TierResolver:
    async def get_tier(self, request: Request) -> RateLimitTier:
        # Extract user_id
        user_id = await extract_user_id(request)

        # Fetch from user service or database
        user = await user_service.get_user(user_id)

        # Map subscription to tier
        tier_map = {
            "free": RateLimitTier.FREE,
            "premium": RateLimitTier.PREMIUM,
            "enterprise": RateLimitTier.ENTERPRISE,
        }
        return tier_map.get(user.subscription, RateLimitTier.FREE)
```

---

## 📚 Additional Resources

- **Comprehensive Guide**: `MONITORING_AND_MITIGATION_GUIDE.md`
- **Monitoring Module**: `app/monitoring_advanced.py`
- **Rate Limiting Module**: `app/rate_limiting.py`
- **Alert Rules**: `monitoring/prometheus_alerts.yml`

---

## ✅ Checklist

- [ ] Start monitoring stack (`docker-compose up`)
- [ ] Integrate monitoring in `main.py`
- [ ] Add rate limiting middleware
- [ ] Verify `/metrics` endpoint
- [ ] Access Grafana dashboard
- [ ] Configure Slack/PagerDuty alerts
- [ ] Test rate limiting with curl
- [ ] Review alert thresholds
- [ ] Document custom alerts
- [ ] Train team on alert response

---

**Last Updated**: 2025-10-31
**Version**: 1.0
**Status**: ✅ Ready for Production
