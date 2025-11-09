# Backend Monitoring - Quick Start Guide

Get the complete monitoring stack running in 5 minutes.

## Prerequisites

- Docker and Docker Compose installed
- Backend service running on port 8081
- PostgreSQL running (for postgres_exporter)
- Redis running (for redis_exporter)

## Step 1: Start Monitoring Stack (2 minutes)

```bash
cd /path/to/backend/monitoring

# Start all monitoring services
docker-compose -f docker-compose.monitoring.yml up -d

# Verify all services are running
docker-compose -f docker-compose.monitoring.yml ps
```

**Expected Output**:
```
NAME                        STATUS          PORTS
backend-grafana             Up              0.0.0.0:3000->3000/tcp
backend-prometheus          Up              0.0.0.0:9090->9090/tcp
backend-loki                Up              0.0.0.0:3100->3100/tcp
backend-promtail            Up
backend-postgres-exporter   Up              0.0.0.0:9187->9187/tcp
backend-redis-exporter      Up              0.0.0.0:9121->9121/tcp
backend-node-exporter       Up              0.0.0.0:9100->9100/tcp
```

## Step 2: Verify Metrics Collection (1 minute)

```bash
# Check backend is exposing metrics
curl http://localhost:8081/metrics | head -20

# Check Prometheus is scraping
curl http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | {job: .labels.job, health: .health}'
```

**Expected**: All targets should show `health: "up"`

## Step 3: Access Grafana Dashboards (1 minute)

1. Open browser: **http://localhost:3000**
2. Login credentials:
   - Username: `admin`
   - Password: `admin`
3. Go to **Dashboards** → **Browse** → **Backend** folder
4. Open any dashboard:
   - **Dashboard 1: API Performance & Health**
   - **Dashboard 2: Database & Cache Operations**
   - **Dashboard 3: Business & Trading Metrics**

## Step 4: Test Metrics (1 minute)

Generate some traffic to see metrics in action:

```bash
# Generate API requests
for i in {1..100}; do
  curl http://localhost:8081/health
  sleep 0.1
done

# Check metrics in Grafana
# Navigate to Dashboard 1 and see:
# - Request rate increasing
# - Latency charts updating
# - Active requests changing
```

## Step 5: View Logs (30 seconds)

1. In Grafana, click **Explore** (compass icon)
2. Select **Loki** datasource
3. Enter query: `{compose_service="backend"}`
4. Click **Run query**
5. Try filtering: `{compose_service="backend"} |= "ERROR"`

## Quick Health Check

Run this command to verify everything is working:

```bash
# Check all endpoints
echo "Backend Metrics: $(curl -s http://localhost:8081/metrics | grep -c 'http_requests_total')"
echo "Prometheus Health: $(curl -s http://localhost:9090/-/healthy)"
echo "Grafana Health: $(curl -s http://localhost:3000/api/health | jq -r '.database')"
echo "Loki Health: $(curl -s http://localhost:3100/ready)"
```

**Expected Output**:
```
Backend Metrics: 1
Prometheus Health: Prometheus is Healthy.
Grafana Health: ok
Loki Health: ready
```

## Common Issues

### Issue: Backend metrics endpoint returns 404

**Solution**: Ensure backend service has the MetricsMiddleware configured in `app/main.py`

```python
# app/main.py
from app.metrics_middleware import MetricsMiddleware
app.add_middleware(MetricsMiddleware)
```

### Issue: Prometheus shows targets as "down"

**Solution**: Check network connectivity

```bash
# From Prometheus container
docker exec backend-prometheus wget -O- http://host.docker.internal:8081/metrics
```

If fails, update `prometheus.yml` to use correct backend URL.

### Issue: No logs in Loki

**Solution**: Check Promtail is running and has access to Docker socket

```bash
docker logs backend-promtail

# Should see: "Clients configured:"
```

### Issue: Grafana dashboards not loading

**Solution**: Import dashboards manually

1. Go to **Dashboards** → **Import**
2. Upload JSON file from `monitoring/grafana/dashboards/`
3. Select **Prometheus** as datasource

## Next Steps

- ✅ **Configure Alerts**: See `alerts/backend-alerts.yml`
- ✅ **Customize Dashboards**: Edit JSON files in `grafana/dashboards/`
- ✅ **Add Custom Metrics**: See `app/metrics.py`
- ✅ **Set Up Alertmanager**: Configure notifications (Slack, PagerDuty, email)

## Useful URLs

| Service | URL | Purpose |
|---------|-----|---------|
| Grafana | http://localhost:3000 | Dashboards and visualizations |
| Prometheus | http://localhost:9090 | Metrics database and PromQL queries |
| Loki | http://localhost:3100 | Log aggregation |
| Backend Metrics | http://localhost:8081/metrics | Raw Prometheus metrics |
| Prometheus Targets | http://localhost:9090/targets | Scrape target status |
| Prometheus Alerts | http://localhost:9090/alerts | Active alerts |

## Stopping the Stack

```bash
# Stop all services
docker-compose -f docker-compose.monitoring.yml down

# Stop and remove volumes (deletes all metrics data)
docker-compose -f docker-compose.monitoring.yml down -v
```

---

**Need Help?** See the full documentation in `README.md` or check the troubleshooting section.
