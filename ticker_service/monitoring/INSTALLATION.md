# Prometheus & Grafana Installation Guide

Complete guide to install and configure Prometheus and Grafana for ticker service monitoring.

## Option 1: Docker Installation (Recommended - No sudo required)

This is the easiest method and doesn't require sudo access for the application setup.

### Prerequisites

- Docker installed and running
- Docker Compose installed

### Step 1: Create Docker Compose File

We'll create a `docker-compose.yml` in the monitoring directory:

```bash
cd /mnt/stocksblitz-data/Quantagro/tradingview-viz/ticker_service/monitoring
```

Create `docker-compose.monitoring.yml`:

```yaml
version: '3.8'

services:
  prometheus:
    image: prom/prometheus:latest
    container_name: ticker-prometheus
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - ./alerts:/etc/prometheus/rules
      - prometheus-data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--web.console.libraries=/usr/share/prometheus/console_libraries'
      - '--web.console.templates=/usr/share/prometheus/consoles'
      - '--web.enable-lifecycle'
    restart: unless-stopped
    networks:
      - monitoring

  grafana:
    image: grafana/grafana:latest
    container_name: ticker-grafana
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_USER=admin
      - GF_SECURITY_ADMIN_PASSWORD=admin
      - GF_INSTALL_PLUGINS=
    volumes:
      - grafana-data:/var/lib/grafana
      - ./grafana/provisioning:/etc/grafana/provisioning
    restart: unless-stopped
    networks:
      - monitoring
    depends_on:
      - prometheus

volumes:
  prometheus-data:
  grafana-data:

networks:
  monitoring:
    driver: bridge
```

### Step 2: Create Prometheus Configuration

Create `prometheus.yml`:

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

# Load alerting rules
rule_files:
  - /etc/prometheus/rules/tick-processing-alerts.yml

# Scrape configurations
scrape_configs:
  # Ticker service metrics
  - job_name: 'ticker-service'
    static_configs:
      - targets: ['host.docker.internal:8000']  # Ticker service /metrics endpoint
        labels:
          service: 'ticker-service'
          env: 'development'

  # Prometheus self-monitoring
  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']
```

### Step 3: Create Grafana Provisioning

Create directory structure:

```bash
mkdir -p grafana/provisioning/datasources
mkdir -p grafana/provisioning/dashboards
```

Create `grafana/provisioning/datasources/prometheus.yml`:

```yaml
apiVersion: 1

datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
    editable: false
```

Create `grafana/provisioning/dashboards/dashboards.yml`:

```yaml
apiVersion: 1

providers:
  - name: 'Ticker Service'
    orgId: 1
    folder: ''
    type: file
    disableDeletion: false
    updateIntervalSeconds: 10
    allowUiUpdates: true
    options:
      path: /etc/grafana/provisioning/dashboards
```

### Step 4: Start Services

```bash
# Start Prometheus and Grafana
docker-compose -f docker-compose.monitoring.yml up -d

# Check logs
docker-compose -f docker-compose.monitoring.yml logs -f
```

### Step 5: Verify Installation

```bash
# Check Prometheus
curl http://localhost:9090/-/healthy

# Check Grafana
curl http://localhost:3000/api/health
```

Access URLs:
- **Prometheus:** http://localhost:9090
- **Grafana:** http://localhost:3000 (admin/admin)

### Step 6: Import Dashboard

1. Open Grafana: http://localhost:3000
2. Login: admin/admin (change password on first login)
3. Go to Dashboards → Import
4. Upload `grafana/tick-processing-dashboard.json`
5. Select Prometheus data source
6. Click Import

---

## Option 2: Native Installation (Requires sudo)

### Ubuntu/Debian

**Install Prometheus:**

```bash
# Download Prometheus
cd /tmp
wget https://github.com/prometheus/prometheus/releases/download/v2.45.0/prometheus-2.45.0.linux-amd64.tar.gz
tar xvfz prometheus-2.45.0.linux-amd64.tar.gz
sudo mv prometheus-2.45.0.linux-amd64 /opt/prometheus

# Create user
sudo useradd --no-create-home --shell /bin/false prometheus

# Create directories
sudo mkdir -p /etc/prometheus
sudo mkdir -p /var/lib/prometheus

# Copy files
sudo cp /opt/prometheus/prometheus /usr/local/bin/
sudo cp /opt/prometheus/promtool /usr/local/bin/
sudo cp -r /opt/prometheus/consoles /etc/prometheus
sudo cp -r /opt/prometheus/console_libraries /etc/prometheus

# Copy your config
sudo cp monitoring/prometheus.yml /etc/prometheus/
sudo cp -r monitoring/alerts /etc/prometheus/rules

# Set ownership
sudo chown -R prometheus:prometheus /etc/prometheus
sudo chown -R prometheus:prometheus /var/lib/prometheus
sudo chown prometheus:prometheus /usr/local/bin/prometheus
sudo chown prometheus:prometheus /usr/local/bin/promtool

# Create systemd service
sudo tee /etc/systemd/system/prometheus.service > /dev/null <<EOF
[Unit]
Description=Prometheus
Wants=network-online.target
After=network-online.target

[Service]
User=prometheus
Group=prometheus
Type=simple
ExecStart=/usr/local/bin/prometheus \
    --config.file /etc/prometheus/prometheus.yml \
    --storage.tsdb.path /var/lib/prometheus/ \
    --web.console.templates=/etc/prometheus/consoles \
    --web.console.libraries=/etc/prometheus/console_libraries \
    --web.enable-lifecycle

[Install]
WantedBy=multi-user.target
EOF

# Start service
sudo systemctl daemon-reload
sudo systemctl start prometheus
sudo systemctl enable prometheus
sudo systemctl status prometheus
```

**Install Grafana:**

```bash
# Add Grafana repository
sudo apt-get install -y software-properties-common
sudo add-apt-repository "deb https://packages.grafana.com/oss/deb stable main"
wget -q -O - https://packages.grafana.com/gpg.key | sudo apt-key add -

# Install
sudo apt-get update
sudo apt-get install grafana

# Start service
sudo systemctl daemon-reload
sudo systemctl start grafana-server
sudo systemctl enable grafana-server
sudo systemctl status grafana-server
```

---

## Testing the Setup

### 1. Verify Prometheus is Scraping

```bash
# Check if ticker service is being scraped
curl http://localhost:9090/api/v1/targets

# Query a metric
curl 'http://localhost:9090/api/v1/query?query=tick_processing_latency_seconds_count'
```

### 2. Start Ticker Service with Metrics

Ensure the ticker service is exposing metrics on port 8000:

```bash
cd /mnt/stocksblitz-data/Quantagro/tradingview-viz/ticker_service

# Start the service
.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Check metrics endpoint:

```bash
curl http://localhost:8000/metrics | grep tick_processing
```

### 3. Verify Alerts Loaded

```bash
# Check alert rules loaded in Prometheus
curl http://localhost:9090/api/v1/rules | jq '.data.groups[] | select(.name=="tick_processing")'
```

### 4. Access Grafana Dashboard

1. Open http://localhost:3000
2. Login (admin/admin)
3. Navigate to Dashboards
4. Open "Tick Processing - Performance & Health"
5. Verify all panels showing data

---

## Troubleshooting

### Prometheus Not Scraping Ticker Service

**Problem:** Targets show as "DOWN" in Prometheus

**Solution:**

1. Check ticker service is running:
   ```bash
   curl http://localhost:8000/metrics
   ```

2. If using Docker, update `prometheus.yml`:
   ```yaml
   - targets: ['host.docker.internal:8000']  # For Docker Desktop
   # OR
   - targets: ['172.17.0.1:8000']  # For Linux Docker
   ```

3. Reload Prometheus:
   ```bash
   curl -X POST http://localhost:9090/-/reload
   ```

### Grafana Dashboard Not Showing Data

**Problem:** All panels empty

**Solutions:**

1. Check Prometheus data source configured:
   - Settings → Data Sources → Prometheus
   - URL should be `http://prometheus:9090` (Docker) or `http://localhost:9090` (native)

2. Verify metrics exist:
   ```bash
   curl 'http://localhost:9090/api/v1/query?query=up{job="ticker-service"}'
   ```

3. Check time range in Grafana (top right) - set to "Last 1 hour"

### Alerts Not Firing

**Problem:** No alerts appearing in Prometheus

**Solutions:**

1. Check alert rules loaded:
   ```bash
   curl http://localhost:9090/api/v1/rules
   ```

2. Verify alert file syntax:
   ```bash
   promtool check rules monitoring/alerts/tick-processing-alerts.yml
   ```

3. Check Prometheus logs:
   ```bash
   # Docker
   docker logs ticker-prometheus

   # Native
   sudo journalctl -u prometheus -f
   ```

---

## Quick Start Commands

### Docker (Recommended)

```bash
# Start monitoring stack
cd /mnt/stocksblitz-data/Quantagro/tradingview-viz/ticker_service/monitoring
docker-compose -f docker-compose.monitoring.yml up -d

# Check status
docker-compose -f docker-compose.monitoring.yml ps

# View logs
docker-compose -f docker-compose.monitoring.yml logs -f

# Stop
docker-compose -f docker-compose.monitoring.yml down

# Stop and remove volumes (clean slate)
docker-compose -f docker-compose.monitoring.yml down -v
```

### Native Installation

```bash
# Start services
sudo systemctl start prometheus
sudo systemctl start grafana-server

# Check status
sudo systemctl status prometheus
sudo systemctl status grafana-server

# View logs
sudo journalctl -u prometheus -f
sudo journalctl -u grafana-server -f

# Stop services
sudo systemctl stop prometheus
sudo systemctl stop grafana-server
```

---

## Next Steps

After installation:

1. ✅ Access Grafana at http://localhost:3000
2. ✅ Import tick-processing-dashboard.json
3. ✅ Configure notification channels (Slack, PagerDuty, Email)
4. ✅ Run load tests to generate metrics
5. ✅ Verify alerts fire correctly
6. ✅ Share dashboard with team

---

## Production Deployment

For production, consider:

1. **Persistence:** Ensure Prometheus and Grafana data is backed up
2. **Authentication:** Change default Grafana password
3. **HTTPS:** Use reverse proxy (nginx) for SSL
4. **High Availability:** Run multiple Prometheus instances
5. **Retention:** Configure Prometheus retention policy (default 15 days)
6. **Resource Limits:** Set memory/CPU limits in Docker or systemd

---

## Support

For issues:
1. Check troubleshooting section above
2. Review logs (Docker or systemd)
3. Verify network connectivity
4. Check port availability (9090, 3000)
