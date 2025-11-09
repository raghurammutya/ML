# Loki Log Aggregation - Usage Guide

## Quick Start

### Access Grafana
- URL: http://localhost:3000
- Username: `admin`
- Password: `admin`

### View Logs in Grafana Explore

1. Click the **Explore** icon (compass) in the left sidebar
2. Select **Loki** from the datasource dropdown at the top
3. Use the **Label filters** button or write a LogQL query manually
4. Click **Run query** button

## Available Services

Your Loki instance is collecting logs from these services:

- `ticker-service` - Main ticker service
- `backend` - Trading backend service
- `frontend` - Web frontend
- `user-service` - User authentication service
- `redis` - Redis cache
- `prometheus` - Metrics collection
- `grafana` - Dashboard service
- `loki` - Log aggregation service
- `promtail` - Log collector
- `stocksblitz-postgres` - PostgreSQL database
- `pgadmin` - Database admin tool

## LogQL Query Examples

### Basic Queries

**View all logs from ticker service:**
```logql
{compose_service="ticker-service"}
```

**View all logs from backend:**
```logql
{compose_service="backend"}
```

**View all logs from a specific container:**
```logql
{container="tv-ticker"}
```

### Filtering Logs

**Filter for errors:**
```logql
{compose_service="ticker-service"} |= "ERROR"
```

**Filter for warnings or errors:**
```logql
{compose_service="ticker-service"} |~ "ERROR|WARN"
```

**Exclude health check logs:**
```logql
{compose_service="ticker-service"} != "GET /health"
```

**Filter by multiple services:**
```logql
{compose_service=~"ticker-service|backend|user-service"}
```

### JSON Log Parsing

**Parse JSON logs and extract fields:**
```logql
{compose_service="backend"} | json
```

**Filter JSON logs by field:**
```logql
{compose_service="backend"} | json | level="ERROR"
```

**Extract specific JSON fields:**
```logql
{compose_service="backend"} | json message, level, logger
```

### Advanced Queries

**Count error logs per minute:**
```logql
sum(count_over_time({compose_service="ticker-service"} |= "ERROR" [1m]))
```

**Rate of logs per second:**
```logql
rate({compose_service="ticker-service"}[5m])
```

**Search for subscription timeout errors:**
```logql
{compose_service="ticker-service"} |~ "subscription.*timeout"
```

**View logs from last 5 minutes:**
```logql
{compose_service="ticker-service"}[5m]
```

**Filter by log level (if extracted):**
```logql
{compose_service="ticker-service"} | json | level=~"ERROR|CRITICAL"
```

### Useful Patterns

**Database connection errors:**
```logql
{compose_service=~"backend|ticker-service|user-service"} |~ "connection.*error|database.*error"
```

**Redis errors:**
```logql
{compose_service="redis"} |= "ERROR"
```

**All errors across all services:**
```logql
{compose_service=~".+"} |= "ERROR"
```

**HTTP 500 errors:**
```logql
{compose_service=~"backend|ticker-service|user-service"} |~ "500|Internal Server Error"
```

## Using Grafana UI (No Code)

### Method 1: Label Browser
1. Go to Explore
2. Select **Loki** datasource
3. Click **Label browser** button
4. Select labels from the UI:
   - Click `compose_service`
   - Select a service (e.g., `ticker-service`)
   - Click **Show logs**

### Method 2: Query Builder
1. Go to Explore
2. Select **Loki** datasource
3. Click **+ Label filters** button
4. Select:
   - Label: `compose_service`
   - Operator: `=`
   - Value: `ticker-service`
5. Click **Run query**

### Adding Filters
After getting basic logs, you can add filters:
1. Click **+ Line filter** or **+ Parsers**
2. Add text filters like `|= "ERROR"` or `|~ "pattern"`
3. Click **Run query**

## Time Range Selection

Use the time picker in the top right:
- Last 5 minutes
- Last 15 minutes
- Last 1 hour
- Last 6 hours
- Last 24 hours
- Custom range

## Tips

1. **Start Simple**: Begin with `{compose_service="ticker-service"}` and add filters
2. **Use Live Streaming**: Toggle the "Live" button to see real-time logs
3. **Context**: Click on any log line to see surrounding context
4. **Log Volume**: Enable "Show logs volume" to see log rate histogram
5. **Save Queries**: Star useful queries for quick access later

## Troubleshooting

### No logs showing?

1. **Check time range** - Make sure it's recent (last 15 minutes)
2. **Verify query** - Start with simple query like `{compose_service="ticker-service"}`
3. **Check if services are running**:
   ```bash
   docker ps | grep -E "tv-ticker|tv-backend|tv-user-service"
   ```
4. **Check Loki is collecting**:
   ```bash
   curl -s "http://localhost:3100/loki/api/v1/label/container/values"
   ```

### Slow queries?

- Reduce time range
- Add more specific label filters
- Avoid regex on large time ranges

## Command Line Access

### Query Loki directly:
```bash
# Get available labels
curl -s "http://localhost:3100/loki/api/v1/labels" | python3 -m json.tool

# Get available services
curl -s "http://localhost:3100/loki/api/v1/label/compose_service/values" | python3 -m json.tool

# Query logs
curl -s -G "http://localhost:3100/loki/api/v1/query_range" \
  --data-urlencode 'query={compose_service="ticker-service"}' \
  --data-urlencode 'limit=10'
```

### Check service status:
```bash
cd /mnt/stocksblitz-data/Quantagro/tradingview-viz/ticker_service/monitoring

# Check Loki logs
docker logs ticker-loki --tail 50

# Check Promtail logs
docker logs ticker-promtail --tail 50

# Restart services
docker-compose -f docker-compose.monitoring.yml restart loki promtail
```

## Log Retention

- **Retention Period**: 31 days
- **Storage**: `/var/lib/docker/volumes/monitoring_loki-data`
- Logs older than 31 days are automatically deleted

## Resource Usage

- **Loki**: ~200-400MB RAM
- **Promtail**: ~50-100MB RAM
- Total: Much lighter than Kibana (2-4GB)

## Support

For issues:
1. Check container logs: `docker logs ticker-loki` and `docker logs ticker-promtail`
2. Verify network connectivity: `docker exec ticker-grafana wget -qO- http://loki:3100/ready`
3. Check Promtail is discovering containers: `docker logs ticker-promtail | grep "added Docker target"`
