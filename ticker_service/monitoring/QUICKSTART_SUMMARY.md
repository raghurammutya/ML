# Monitoring Stack - Quick Start Summary

## ✅ Status: RUNNING

Prometheus and Grafana are now running and ready to use!

---

## Access Information

| Service | URL | Credentials |
|---------|-----|-------------|
| **Grafana** | http://localhost:3000 | admin / admin |
| **Prometheus** | http://localhost:9090 | No auth |

---

## What's Running

```
✓ Prometheus (ticker-prometheus)
  - Port: 9090
  - Status: Healthy
  - Scraping: ticker-service on port 8000

✓ Grafana (ticker-grafana)
  - Port: 3000
  - Status: Healthy
  - Version: 12.2.1
  - Datasource: Prometheus (auto-configured)
```

---

## Next Steps

### 1. Start Ticker Service with Metrics

The ticker service needs to be running on port 8000 for Prometheus to scrape metrics.

```bash
cd /mnt/stocksblitz-data/Quantagro/tradingview-viz/ticker_service

# Start the service (if not already running)
.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 2. Verify Metrics Endpoint

```bash
# Check metrics are being exposed
curl http://localhost:8000/metrics | grep tick_processing

# You should see output like:
# tick_processing_latency_seconds_bucket{...}
# ticks_processed_total{...}
# etc.
```

### 3. Check Prometheus is Scraping

Open http://localhost:9090/targets

You should see:
- **ticker-service** - should be UP (green)
- **prometheus** - should be UP (green)

If ticker-service shows as DOWN, make sure the service is running on port 8000.

### 4. Access Grafana Dashboard

1. **Open Grafana:** http://localhost:3000
2. **Login:** admin / admin (change password on first login)
3. **Navigate to Dashboards:**
   - Click the hamburger menu (☰) on the left
   - Click "Dashboards"
   - Look for "Ticker Service" folder
   - Click "Tick Processing - Performance & Health"

**Note:** The dashboard should auto-import via provisioning. If not visible:
- Go to Dashboards → Import
- Upload `grafana/tick-processing-dashboard.json`
- Select "Prometheus" data source
- Click Import

### 5. Generate Some Load (Optional)

Run load tests to see metrics in action:

```bash
cd /mnt/stocksblitz-data/Quantagro/tradingview-viz/ticker_service

# Run fast load tests
./tests/load/run_load_tests.sh

# Watch the dashboard update in real-time!
```

---

## Useful Commands

### Check Container Status

```bash
cd /mnt/stocksblitz-data/Quantagro/tradingview-viz/ticker_service/monitoring
docker-compose -f docker-compose.monitoring.yml ps
```

### View Logs

```bash
# All logs
docker-compose -f docker-compose.monitoring.yml logs -f

# Just Prometheus
docker logs ticker-prometheus -f

# Just Grafana
docker logs ticker-grafana -f
```

### Stop Services

```bash
docker-compose -f docker-compose.monitoring.yml down

# To also remove data volumes (clean slate):
docker-compose -f docker-compose.monitoring.yml down -v
```

### Restart Services

```bash
docker-compose -f docker-compose.monitoring.yml restart
```

### Update Configuration

If you modify `prometheus.yml` or alert rules:

```bash
# Reload Prometheus without restart
curl -X POST http://localhost:9090/-/reload

# Or restart the container
docker-compose -f docker-compose.monitoring.yml restart prometheus
```

---

## Verifying Everything Works

### 1. Check Prometheus Targets

```bash
curl -s http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | {job: .labels.job, health: .health}'
```

Expected output:
```json
{
  "job": "ticker-service",
  "health": "up"
}
{
  "job": "prometheus",
  "health": "up"
}
```

### 2. Query a Metric

```bash
curl -s 'http://localhost:9090/api/v1/query?query=up{job="ticker-service"}' | jq '.data.result[0].value'
```

Expected: `[timestamp, "1"]` (meaning UP)

### 3. Check Alert Rules Loaded

```bash
curl -s http://localhost:9090/api/v1/rules | jq '.data.groups[] | select(.name=="tick_processing") | .rules | length'
```

Expected: `15` (number of alert rules)

### 4. Verify Grafana Datasource

```bash
curl -s -u admin:admin http://localhost:3000/api/datasources | jq '.[0] | {name: .name, type: .type, url: .url}'
```

Expected output:
```json
{
  "name": "Prometheus",
  "type": "prometheus",
  "url": "http://prometheus:9090"
}
```

---

## Troubleshooting

### Ticker Service Shows as DOWN in Prometheus

**Problem:** Target shows as red/DOWN in Prometheus targets page

**Solutions:**

1. **Check ticker service is running:**
   ```bash
   curl http://localhost:8000/metrics
   ```

2. **If on Linux Docker, update prometheus.yml:**

   Change:
   ```yaml
   - targets: ['host.docker.internal:8000']
   ```

   To:
   ```yaml
   - targets: ['172.17.0.1:8000']  # Linux Docker bridge IP
   ```

   Then reload:
   ```bash
   curl -X POST http://localhost:9090/-/reload
   ```

3. **Check firewall/network:**
   ```bash
   # Test from inside Prometheus container
   docker exec ticker-prometheus wget -qO- http://host.docker.internal:8000/metrics
   ```

### Grafana Dashboard Shows No Data

**Problem:** All panels are empty

**Solutions:**

1. **Check time range:** Top-right corner, set to "Last 1 hour"

2. **Verify Prometheus datasource:**
   - Grafana → Settings → Data Sources → Prometheus
   - Click "Test" button - should show green "Data source is working"

3. **Check metrics exist:**
   ```bash
   curl -s 'http://localhost:9090/api/v1/query?query=ticks_processed_total' | jq '.data.result | length'
   ```
   Should return > 0

4. **Ensure ticker service is running and processing ticks**

### Alerts Not Visible in Prometheus

**Problem:** No alerts showing at http://localhost:9090/alerts

**Solutions:**

1. **Check rules loaded:**
   ```bash
   curl http://localhost:9090/api/v1/rules | jq '.data.groups[] | .name'
   ```

2. **Validate rules file:**
   ```bash
   docker exec ticker-prometheus promtool check rules /etc/prometheus/rules/tick-processing-alerts.yml
   ```

3. **Check Prometheus logs:**
   ```bash
   docker logs ticker-prometheus | grep -i error
   ```

---

## What Gets Monitored

The dashboard tracks 20+ metrics across 5 categories:

### 1. Overview
- Tick throughput (ticks/sec)
- Active trading accounts
- Error rate
- System health
- Underlying price (NIFTY)

### 2. Latency
- Tick processing latency (P50, P95, P99)
- Batch flush latency
- Greeks calculation latency

### 3. Batching
- Batch size distribution
- Batches flushed per second
- Batch fill rate
- Pending batch size

### 4. Errors
- Validation errors by type
- Processing errors by type
- Error distribution pie chart
- Total errors (last hour)

### 5. Business Metrics
- Underlying ticks processed
- Option ticks processed
- Greeks calculations/sec
- Market depth updates

---

## Performance Expectations

Based on load tests, you should see:

- **Throughput:** 50,000+ ticks/sec (under load)
- **P99 Latency:** < 1ms (without Redis overhead)
- **Error Rate:** < 0.1%
- **Batch Size:** ~100-1000 ticks per batch
- **Greeks Overhead:** ~0.02ms per tick

---

## Production Checklist

Before deploying to production:

- [ ] Change Grafana admin password
- [ ] Configure Grafana notification channels (Slack/Email/PagerDuty)
- [ ] Set up Prometheus persistence (done via Docker volumes)
- [ ] Configure Prometheus retention policy if needed
- [ ] Test alert firing (run load tests)
- [ ] Add SSL/TLS via reverse proxy
- [ ] Set up backup for Grafana dashboards
- [ ] Document runbooks for alerts
- [ ] Train team on dashboard usage

---

## Support

For help:
1. Check troubleshooting section above
2. Review container logs
3. Check monitoring/INSTALLATION.md for detailed docs
4. Verify network connectivity between containers

---

**Monitoring Stack Version:**
- Prometheus: latest (pulled 2025-11-08)
- Grafana: 12.2.1
- Docker Compose: 3.8

**Status:** ✅ RUNNING AND READY
