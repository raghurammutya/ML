# Backend Monitoring & Observability

Comprehensive monitoring setup for the TradingView Backend API service using Prometheus, Grafana, and Loki.

## 📊 Overview

The backend service is instrumented with **100+ Prometheus metrics** across:
- HTTP API performance (requests, latency, errors)
- Database operations (queries, pool health, latency)
- Cache performance (hit rates, Redis operations)
- WebSocket connections and messages
- Smart order validation and execution
- Strategy management and M2M calculations
- F&O analytics queries
- Authentication and security
- Background workers
- Business KPIs

## 🏗️ Architecture

```
┌─────────────┐      ┌──────────────┐      ┌───────────┐
│   Backend   │─────▶│  Prometheus  │─────▶│  Grafana  │
│   Service   │      │   (Metrics)  │      │(Dashboards│
│  :8081      │      │    :9090     │      │   :3000)  │
└─────────────┘      └──────────────┘      └───────────┘
       │                     │
       │                     ▼
       │              ┌──────────────┐
       │              │ Alertmanager │
       │              │    :9093     │
       │              └──────────────┘
       ▼
┌─────────────┐      ┌──────────────┐
│  Promtail   │─────▶│     Loki     │
│(Log Agent)  │      │  (Logs)      │
│             │      │   :3100      │
└─────────────┘      └──────────────┘
```

## 📈 Metrics Categories

### 1. HTTP API Metrics
- **http_requests_total**: Total requests by method, endpoint, status
- **http_request_duration_seconds**: Request latency histogram
- **http_request_size_bytes**: Request payload size
- **http_response_size_bytes**: Response payload size
- **http_active_requests**: Currently active requests

### 2. Database Metrics
- **database_queries_total**: Query count by type and status
- **database_query_duration_seconds**: Query execution time
- **database_pool_connections**: Pool state (active, idle, total)
- **database_pool_acquire_duration_seconds**: Time to get connection
- **database_pool_acquire_timeouts_total**: Pool exhaustion events
- **database_transaction_duration_seconds**: Transaction execution time
- **database_errors_total**: Errors by type

### 3. Cache Metrics (Redis + Memory)
- **cache_operations_total**: Operations by layer and status
- **cache_hit_rate**: Hit rate percentage by layer
- **cache_operation_duration_seconds**: Operation latency
- **cache_memory_usage_bytes**: Memory cache size
- **cache_entries_total**: Number of cached entries
- **redis_connection_errors_total**: Redis failures
- **redis_command_duration_seconds**: Redis operation latency

### 4. WebSocket Metrics
- **websocket_connections_active**: Active WS connections
- **websocket_messages_sent_total**: Messages sent to clients
- **websocket_messages_received_total**: Messages from clients
- **websocket_connection_duration_seconds**: Connection lifetime
- **websocket_errors_total**: WS errors by type
- **websocket_subscriptions_active**: Active subscriptions

### 5. Smart Order Metrics
- **smart_order_validations_total**: Validations by status
- **smart_order_validation_duration_seconds**: Validation latency
- **smart_order_rejection_reasons_total**: Rejections by reason
- **margin_calculations_total**: Margin calcs by status
- **margin_calculation_duration_seconds**: Margin calc latency
- **cost_breakdown_calculations_total**: Cost breakdowns
- **market_impact_assessments_total**: Impact assessments

### 6. Strategy Metrics
- **strategies_total**: Active strategies by account
- **strategy_operations_total**: CRUD operations
- **strategy_m2m_calculations_total**: M2M calculations
- **strategy_m2m_calculation_duration_seconds**: M2M latency
- **strategy_instruments_total**: Instruments in strategies
- **strategy_pnl_total**: Total P&L in rupees

### 7. F&O Analytics Metrics
- **fo_queries_total**: F&O query count
- **fo_query_duration_seconds**: F&O query latency
- **fo_instruments_cached**: Cached instruments
- **fo_greeks_calculations_total**: Greeks calculations

### 8. Ticker Service Client Metrics
- **ticker_service_requests_total**: Requests by operation
- **ticker_service_request_duration_seconds**: Request latency
- **ticker_service_circuit_breaker_state**: CB state (0/1/2)
- **ticker_service_circuit_breaker_failures_total**: CB failures
- **ticker_service_errors_total**: Errors by type

### 9. Authentication Metrics
- **auth_attempts_total**: Auth attempts
- **jwt_validations_total**: JWT validations
- **jwt_validation_duration_seconds**: JWT validation latency
- **active_sessions**: Current active sessions
- **api_key_validations_total**: API key validations

### 10. Business Metrics
- **active_users**: Active users by time window (5m, 15m, 1h)
- **daily_active_users**: DAU count
- **total_orders_placed_today**: Orders today
- **total_strategies_created_today**: Strategies created today

## 📊 Grafana Dashboards

### Dashboard 1: API Performance & Health
**File**: `dashboards/dashboard-1-api-performance.json`

**Panels**:
- Request rate (req/s) with 2xx/4xx/5xx breakdown
- Active requests gauge
- Error rate percentage
- Active WebSocket connections
- Active users (15m window)
- Request duration P95/P99
- Database pool status
- Circuit breaker state
- Latency by endpoint (P95)
- Request duration heatmap
- Requests by endpoint (Top 10)
- HTTP status code distribution
- Requests by method
- WebSocket metrics (connections, messages, duration, errors)
- Authentication metrics
- Rate limit violations

**Refresh**: 5s | **Time Range**: Last 15 minutes

### Dashboard 2: Database & Cache Operations
**File**: `dashboards/dashboard-2-database-cache.json`

**Panels**:
- Query rate (queries/s)
- Query duration P95/P99
- Pool active/idle connections
- Pool acquire timeouts
- Database errors/sec
- Transaction duration P95
- Queries by type
- Query duration by type (P95)
- Database errors by type
- Transaction duration heatmap
- Cache hit rate % (L1/L2)
- Cache operations/sec
- Cache entries by layer
- Cache operation duration (P95)
- Redis command duration
- Redis connection errors
- Memory cache usage
- Connection pool health

**Refresh**: 10s | **Time Range**: Last 15 minutes

### Dashboard 3: Business & Trading Metrics
**File**: `dashboards/dashboard-3-business-trading.json`

**Panels**:
- Order validations/sec
- Validation success rate %
- Validation duration P95
- Orders placed today
- Rejection rate
- Rejection reasons (pie chart)
- Market impact assessments
- Margin calculations/sec
- Margin calculation duration by method
- Cost breakdowns by transaction type
- Ticker service success rate
- Circuit breaker failures
- Active strategies by account
- Strategy operations
- M2M calculations/sec
- M2M calculation duration
- Total strategy instruments
- Strategies created today
- Total P&L (₹)
- F&O query rate
- F&O query duration by type
- F&O instruments cached
- Greeks calculations/sec
- Active users by time window
- Daily active users
- Worker task rate
- Worker queue depth

**Refresh**: 10s | **Time Range**: Last 1 hour

## 🚨 Alerting Rules

### Critical Alerts (P0 - Immediate Action)
**File**: `alerts/backend-alerts.yml`

1. **BackendServiceDown**: Service unreachable for 1 minute
2. **HighAPIErrorRate**: >5% error rate for 2 minutes
3. **DatabasePoolExhausted**: ≥19/20 connections for 2 minutes
4. **DatabaseAcquireTimeouts**: Pool timeouts >1/sec for 2 minutes
5. **CriticalAPILatency**: P99 >5s for 2 minutes
6. **RedisConnectionFailure**: Connection errors >1/sec for 2 minutes
7. **CircuitBreakerOpen**: Ticker service CB open for 2 minutes

### Warning Alerts (P1 - Action Required Soon)
1. **HighAPILatency**: P95 >1s for 5 minutes
2. **ElevatedDatabaseLatency**: P95 >500ms for 5 minutes
3. **HighDatabasePoolUtilization**: >75% for 5 minutes
4. **LowCacheHitRate**: Redis hit rate <70% for 10 minutes
5. **HighOrderRejectionRate**: >20% for 5 minutes
6. **StrategyM2MCalculationErrors**: >1/sec for 5 minutes
7. **TickerServiceHighLatency**: P95 >2s for 5 minutes
8. **HighAuthenticationFailureRate**: >10% for 5 minutes
9. **WebSocketConnectionsHigh**: >100 connections for 5 minutes
10. **BackgroundWorkerQueueBacklog**: >100 tasks for 5 minutes
11. **HighRateLimitViolations**: >5/sec per endpoint for 5 minutes

### Info Alerts (P2 - Informational)
1. **NoActiveUsers**: No activity for 15 minutes
2. **FOQueryLatencyIncreasing**: P95 >5s for 10 minutes
3. **StatementParsingErrors**: >0.1/sec for 10 minutes
4. **CacheMissRateHigh**: >40% for 10 minutes

### SLA Alerts
1. **API_SLA_Breach_Latency**: 1-hour P95 >500ms
2. **API_SLA_Breach_Availability**: 1-hour availability <99.9%

## 🚀 Quick Start

### 1. Start Monitoring Stack

```bash
cd /path/to/backend/monitoring
docker-compose -f docker-compose.monitoring.yml up -d
```

**Services Started**:
- Prometheus (http://localhost:9090)
- Grafana (http://localhost:3000)
- Loki (http://localhost:3100)
- Promtail (log collection)
- Postgres Exporter (http://localhost:9187)
- Redis Exporter (http://localhost:9121)
- Node Exporter (http://localhost:9100)

### 2. Access Grafana

1. Open http://localhost:3000
2. Login: admin / admin
3. Dashboards → Browse → Backend folder
4. Select a dashboard

### 3. Verify Metrics Collection

```bash
# Check Prometheus targets
curl http://localhost:9090/api/v1/targets

# Check metrics endpoint
curl http://localhost:8081/metrics

# Query specific metric
curl 'http://localhost:9090/api/v1/query?query=http_requests_total'
```

### 4. View Logs in Loki

1. In Grafana, go to Explore
2. Select "Loki" datasource
3. Query: `{compose_service="backend"}`
4. Filter by level: `{compose_service="backend"} |= "ERROR"`

## 📝 Logging with Loki

### Log Queries (LogQL)

```logql
# All backend logs
{compose_service="backend"}

# Errors only
{compose_service="backend"} |= "ERROR"

# Errors or warnings
{compose_service="backend"} |~ "ERROR|WARN"

# Error rate (last 5m)
sum(rate({compose_service="backend"} |= "ERROR" [5m]))

# Parse JSON logs
{compose_service="backend"} | json | level="ERROR"

# Count errors by endpoint
sum(count_over_time({compose_service="backend"} |= "ERROR" [1m])) by (endpoint)
```

### Log Retention
- **Retention Period**: 30 days
- **Ingestion Rate Limit**: 10 MB/s
- **Max Query Lookback**: 30 days

## 🔧 Configuration

### Environment Variables

```bash
# Prometheus
PROMETHEUS_RETENTION=30d
PROMETHEUS_SCRAPE_INTERVAL=15s

# Grafana
GF_SECURITY_ADMIN_PASSWORD=<your-strong-password>
GF_SERVER_ROOT_URL=http://localhost:3000

# Database Exporter
DATA_SOURCE_NAME=postgresql://user:pass@host:5432/db?sslmode=disable
```

### Prometheus Scrape Targets

Edit `prometheus.yml` to add/modify targets:

```yaml
scrape_configs:
  - job_name: 'backend'
    static_configs:
      - targets: ['backend:8081']
    scrape_interval: 5s
```

## 📊 Using Metrics in Code

### Track HTTP Requests (Automatic)
The `MetricsMiddleware` automatically tracks all HTTP requests.

### Track Database Queries

```python
from app.metrics_middleware import track_database_query
import time

start = time.time()
try:
    result = await conn.fetch("SELECT * FROM ...")
    track_database_query("select", time.time() - start, success=True)
except Exception:
    track_database_query("select", time.time() - start, success=False)
    raise
```

### Track Cache Operations

```python
from app.metrics_middleware import track_cache_operation

start = time.time()
value = await cache.get(key)
hit = value is not None
track_cache_operation("get", "l2_redis", time.time() - start, hit=hit)
```

### Track Smart Order Validation

```python
from app.metrics_middleware import track_smart_order_validation

start = time.time()
passed, reason = validate_order(order)
track_smart_order_validation(passed, time.time() - start, reason)
```

### Track WebSocket Connections

```python
from app.metrics_middleware import track_websocket_connection, track_websocket_message

# On connect
track_websocket_connection("/ws/fo/stream", connected=True)

# On message
track_websocket_message("/ws/fo/stream", "tick", sent=True)

# On disconnect
track_websocket_connection("/ws/fo/stream", connected=False)
```

## 🎯 SLO/SLA Targets

### API Performance
- **P95 Latency**: <500ms
- **P99 Latency**: <1s
- **Availability**: >99.9%
- **Error Rate**: <1%

### Database
- **Query P95**: <100ms
- **Pool Utilization**: <80%
- **Connection Timeout Rate**: <0.1%

### Cache
- **Redis Hit Rate**: >80%
- **Memory Hit Rate**: >90%
- **Operation P95**: <10ms

### WebSocket
- **Connection Establishment**: <1s
- **Message Latency**: <100ms
- **Error Rate**: <0.1%

## 🔍 Troubleshooting

### High Latency

1. Check database query performance:
   ```
   histogram_quantile(0.95, sum(rate(database_query_duration_seconds_bucket[5m])) by (le, query_type))
   ```

2. Check slow endpoints:
   ```
   topk(5, histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])) by (le, endpoint)))
   ```

3. Check cache hit rate:
   ```
   cache_hit_rate{cache_layer="l2_redis"}
   ```

### High Error Rate

1. Check errors by endpoint:
   ```
   sum(rate(http_requests_total{status=~"5.."}[5m])) by (endpoint)
   ```

2. Check database errors:
   ```
   sum(rate(database_errors_total[5m])) by (error_type)
   ```

3. Check application errors:
   ```
   sum(rate(application_errors_total[5m])) by (error_type)
   ```

### Database Pool Exhaustion

1. Check pool utilization:
   ```
   100 * database_pool_connections{state="active"} / database_pool_connections{state="total"}
   ```

2. Check acquire timeouts:
   ```
   rate(database_pool_acquire_timeouts_total[5m])
   ```

3. Check connection duration:
   ```
   histogram_quantile(0.95, rate(database_pool_acquire_duration_seconds_bucket[5m]))
   ```

## 📚 Additional Resources

- [Prometheus Documentation](https://prometheus.io/docs/)
- [Grafana Documentation](https://grafana.com/docs/)
- [Loki Documentation](https://grafana.com/docs/loki/latest/)
- [PromQL Cheat Sheet](https://promlabs.com/promql-cheat-sheet/)
- [LogQL Cheat Sheet](https://grafana.com/docs/loki/latest/logql/)

## 🤝 Contributing

To add new metrics:

1. Define metric in `app/metrics.py`
2. Add tracking function in `app/metrics_middleware.py`
3. Use metric in your code
4. Add to relevant Grafana dashboard
5. Add alerting rule if needed
6. Update this README

---

**Last Updated**: 2025-11-09
**Version**: 1.0.0
**Maintainer**: Backend Team
