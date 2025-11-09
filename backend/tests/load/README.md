# Load Testing Suite

Performance and load testing for TradingView Backend API using Locust.

## Prerequisites

```bash
pip install locust==2.20.0
```

## Quick Start

### 1. Interactive Web UI (Recommended)

```bash
# Start Locust web interface
locust -f tests/load/locustfile.py --host=http://localhost:8000

# Open browser to http://localhost:8089
# Configure:
#   - Number of users: 100
#   - Spawn rate: 10 users/second
#   - Host: http://localhost:8000
```

### 2. Headless Mode (CI/CD)

```bash
# Run 100 users for 5 minutes
locust -f tests/load/locustfile.py \
  --host=http://localhost:8000 \
  --users 100 \
  --spawn-rate 10 \
  --run-time 5m \
  --headless \
  --html reports/load_test_report.html \
  --csv reports/load_test_data
```

### 3. Specific User Class

```bash
# Test only API operations
locust -f tests/load/locustfile.py \
  --host=http://localhost:8000 \
  APIUser \
  --users 50 \
  --spawn-rate 5 \
  --run-time 2m \
  --headless
```

## User Classes

### ReadOnlyUser
**Purpose:** Simulates users browsing instruments and checking system health.

**Operations:**
- Health checks (high frequency)
- List instruments with pagination
- Search instruments
- Get F&O enabled instruments
- Get instrument by token

**Wait time:** 1-3 seconds between requests

**Usage:**
```bash
locust -f tests/load/locustfile.py ReadOnlyUser --users 200 --spawn-rate 20
```

### APIUser
**Purpose:** Simulates users performing CRUD operations.

**Operations:**
- Get statement uploads
- Get category summary
- List strategies
- Validate orders
- Calculate cost breakdown

**Wait time:** 2-5 seconds between requests

**Usage:**
```bash
locust -f tests/load/locustfile.py APIUser --users 50 --spawn-rate 5
```

### UDFUser
**Purpose:** Simulates TradingView chart data requests.

**Operations:**
- Get UDF configuration
- Search symbols
- Get historical OHLCV data

**Wait time:** 1-2 seconds between requests

**Usage:**
```bash
locust -f tests/load/locustfile.py UDFUser --users 100 --spawn-rate 10
```

### FOAnalysisUser
**Purpose:** Simulates F&O analysis queries.

**Operations:**
- Get moneyness series (IV, delta, gamma, OI)
- Get option chain snapshots
- Get strike-level analytics

**Wait time:** 2-4 seconds between requests

**Usage:**
```bash
locust -f tests/load/locustfile.py FOAnalysisUser --users 30 --spawn-rate 5
```

### MixedWorkloadUser (Recommended for realistic testing)
**Purpose:** Realistic mix of operations weighted by typical usage patterns.

**Operation weights:**
- Health checks: 20x (very frequent)
- Instrument queries: 10x (frequent)
- UDF requests: 8x (frequent for chart users)
- F&O analysis: 5x (moderate)
- Funds queries: 3x (moderate)
- Order validation: 2x (less frequent)
- Strategy queries: 1x (occasional)

**Wait time:** 1-5 seconds between requests

**Usage:**
```bash
locust -f tests/load/locustfile.py MixedWorkloadUser --users 100 --spawn-rate 10
```

## Testing Scenarios

### 1. Baseline Performance Test
**Goal:** Establish baseline metrics with normal load

```bash
locust -f tests/load/locustfile.py \
  --host=http://localhost:8000 \
  MixedWorkloadUser \
  --users 50 \
  --spawn-rate 5 \
  --run-time 5m \
  --headless \
  --html reports/baseline_test.html
```

**Success criteria:**
- 95th percentile response time < 500ms
- Error rate < 1%
- RPS > 100

### 2. Spike Test
**Goal:** Test system behavior under sudden traffic spike

```bash
locust -f tests/load/locustfile.py \
  --host=http://localhost:8000 \
  MixedWorkloadUser \
  --users 500 \
  --spawn-rate 100 \
  --run-time 2m \
  --headless \
  --html reports/spike_test.html
```

**Success criteria:**
- System remains responsive
- No crashes or 5xx errors
- Graceful degradation

### 3. Sustained Load Test
**Goal:** Test system stability under sustained load

```bash
locust -f tests/load/locustfile.py \
  --host=http://localhost:8000 \
  MixedWorkloadUser \
  --users 200 \
  --spawn-rate 10 \
  --run-time 30m \
  --headless \
  --html reports/sustained_test.html
```

**Success criteria:**
- No memory leaks
- Consistent response times
- No connection pool exhaustion

### 4. Database-Heavy Test
**Goal:** Test database connection pooling under load

```bash
locust -f tests/load/locustfile.py \
  --host=http://localhost:8000 \
  APIUser \
  --users 100 \
  --spawn-rate 20 \
  --run-time 10m \
  --headless \
  --html reports/db_heavy_test.html
```

**Success criteria:**
- No connection pool timeouts
- Database query performance remains stable
- Connection pool size is adequate

### 5. Read-Heavy Test
**Goal:** Test caching and read performance

```bash
locust -f tests/load/locustfile.py \
  --host=http://localhost:8000 \
  ReadOnlyUser \
  --users 500 \
  --spawn-rate 50 \
  --run-time 10m \
  --headless \
  --html reports/read_heavy_test.html
```

**Success criteria:**
- Response times < 200ms for cached data
- RPS > 500
- Redis hit rate > 80%

## Performance Targets

### Response Time Targets
- **Health endpoint:** < 50ms (p95)
- **Instrument queries:** < 200ms (p95)
- **UDF history:** < 500ms (p95)
- **F&O analysis:** < 1000ms (p95)
- **Order validation:** < 300ms (p95)

### Throughput Targets
- **Minimum RPS:** 100 requests/second
- **Target RPS:** 500 requests/second
- **Peak RPS:** 1000 requests/second

### Concurrency Targets
- **Normal load:** 100 concurrent users
- **Peak load:** 500 concurrent users
- **Max capacity:** 1000 concurrent users

### Error Rate Targets
- **Normal conditions:** < 0.1%
- **Peak load:** < 1%
- **Spike conditions:** < 5%

## Monitoring During Load Tests

### 1. Backend Metrics
```bash
# Monitor backend logs
docker-compose logs -f backend | grep -E "(ERROR|WARNING|latency)"

# Check Prometheus metrics
curl http://localhost:8000/metrics
```

### 2. Database Metrics
```bash
# Connection pool stats
psql -U stocksblitz -d stocksblitz_unified -c "
  SELECT count(*) as total_connections,
         sum(CASE WHEN state = 'active' THEN 1 ELSE 0 END) as active,
         sum(CASE WHEN state = 'idle' THEN 1 ELSE 0 END) as idle
  FROM pg_stat_activity
  WHERE datname = 'stocksblitz_unified';
"

# Slow queries
psql -U stocksblitz -d stocksblitz_unified -c "
  SELECT query, calls, mean_exec_time, max_exec_time
  FROM pg_stat_statements
  ORDER BY mean_exec_time DESC
  LIMIT 10;
"
```

### 3. Redis Metrics
```bash
# Redis stats
redis-cli INFO stats | grep -E "(total_commands_processed|instantaneous_ops_per_sec|keyspace_hits|keyspace_misses)"
```

### 4. System Resources
```bash
# CPU and memory
docker stats backend ticker-service postgres redis

# Network
docker exec backend ss -s
```

## Analyzing Results

### Locust Web UI Metrics
- **Requests/second:** Current throughput
- **Response time (ms):** 50th, 95th, 99th percentiles
- **Failures:** Error count and rate
- **Charts:** Response time and RPS over time

### HTML Report Metrics
After test completes, open `reports/load_test_report.html`:
- Request statistics per endpoint
- Response time distribution
- Failure breakdown
- Charts and graphs

### CSV Data Analysis
```bash
# Load CSV data into pandas for analysis
python3 << EOF
import pandas as pd

stats = pd.read_csv('reports/load_test_data_stats.csv')
print("Top 10 slowest endpoints:")
print(stats.nlargest(10, 'Average Response Time'))

print("\nEndpoints with failures:")
print(stats[stats['Failure Count'] > 0])
EOF
```

## Production Load Testing

### Pre-Production Checklist
- [ ] Test against staging environment first
- [ ] Notify team before production load test
- [ ] Set up monitoring and alerting
- [ ] Have rollback plan ready
- [ ] Start with low load and gradually increase

### Production Load Test Example
```bash
# Gradual ramp-up test
locust -f tests/load/locustfile.py \
  --host=https://api.production.example.com \
  MixedWorkloadUser \
  --users 1000 \
  --spawn-rate 10 \
  --run-time 30m \
  --headless \
  --html reports/production_load_test.html
```

### Safety Measures
- Start with 10% of target load
- Monitor error rates continuously
- Use circuit breakers
- Set up auto-scaling triggers
- Have DBA on standby

## Continuous Load Testing (CI/CD)

### GitHub Actions Example
```yaml
name: Load Test

on:
  schedule:
    - cron: '0 2 * * *'  # Daily at 2 AM
  workflow_dispatch:

jobs:
  load-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Install dependencies
        run: pip install locust==2.20.0
      - name: Run load test
        run: |
          locust -f tests/load/locustfile.py \
            --host=https://staging.example.com \
            MixedWorkloadUser \
            --users 100 \
            --spawn-rate 10 \
            --run-time 5m \
            --headless \
            --html load_test_report.html
      - name: Upload report
        uses: actions/upload-artifact@v3
        with:
          name: load-test-report
          path: load_test_report.html
```

## Troubleshooting

### High Response Times
1. Check database query performance
2. Review connection pool configuration
3. Check Redis cache hit rate
4. Profile slow endpoints with `cProfile`

### Connection Errors
1. Increase database connection pool size
2. Check file descriptor limits (`ulimit -n`)
3. Review nginx/load balancer timeouts
4. Check network bandwidth

### Memory Leaks
1. Monitor memory usage during test
2. Check for unclosed database connections
3. Review object lifecycle in long-running requests
4. Use `memory_profiler` for analysis

### CPU Bottlenecks
1. Profile code with `py-spy`
2. Check for CPU-intensive operations in request path
3. Consider async/await optimization
4. Review JSON serialization overhead

## Best Practices

1. **Always test against staging first**
2. **Start with low load and ramp up gradually**
3. **Monitor all system metrics during tests**
4. **Run tests during off-peak hours**
5. **Use realistic data and access patterns**
6. **Clean up test data after completion**
7. **Document baseline metrics for comparison**
8. **Run tests regularly to catch regressions**

## References

- [Locust Documentation](https://docs.locust.io/)
- [Load Testing Best Practices](https://locust.io/load-testing-best-practices)
- [FastAPI Performance Tips](https://fastapi.tiangolo.com/deployment/concepts/)
