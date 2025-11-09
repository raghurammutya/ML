#!/bin/bash
#
# Monitoring Deployment Script
# Deploys Grafana dashboard and Prometheus alerts
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=========================================="
echo "Deploying Monitoring Stack"
echo "=========================================="
echo ""

# Configuration
GRAFANA_URL="${GRAFANA_URL:-http://localhost:3000}"
GRAFANA_API_KEY="${GRAFANA_API_KEY:-}"
PROMETHEUS_CONFIG_DIR="${PROMETHEUS_CONFIG_DIR:-/etc/prometheus}"

# Check if Grafana URL is reachable
echo "Checking Grafana connection..."
if curl -s --fail "$GRAFANA_URL/api/health" > /dev/null 2>&1; then
    echo -e "${GREEN}✓${NC} Grafana is reachable at $GRAFANA_URL"
else
    echo -e "${YELLOW}⚠${NC} Warning: Grafana is not reachable at $GRAFANA_URL"
    echo "  Set GRAFANA_URL environment variable if using a different URL"
fi

echo ""

# Deploy Grafana Dashboard
echo "Deploying Grafana dashboard..."
if [ -n "$GRAFANA_API_KEY" ]; then
    RESPONSE=$(curl -s -X POST \
        -H "Authorization: Bearer $GRAFANA_API_KEY" \
        -H "Content-Type: application/json" \
        -d @grafana/tick-processing-dashboard.json \
        "$GRAFANA_URL/api/dashboards/db" 2>&1)

    if echo "$RESPONSE" | grep -q "success"; then
        echo -e "${GREEN}✓${NC} Grafana dashboard deployed successfully"
        DASHBOARD_URL=$(echo "$RESPONSE" | grep -o '"url":"[^"]*"' | cut -d'"' -f4)
        echo "  Dashboard URL: $GRAFANA_URL$DASHBOARD_URL"
    else
        echo -e "${RED}✗${NC} Failed to deploy Grafana dashboard"
        echo "  Response: $RESPONSE"
    fi
else
    echo -e "${YELLOW}⚠${NC} Skipping Grafana deployment (GRAFANA_API_KEY not set)"
    echo "  Manual import: Import grafana/tick-processing-dashboard.json via Grafana UI"
fi

echo ""

# Deploy Prometheus Alerts
echo "Deploying Prometheus alerts..."
if [ -d "$PROMETHEUS_CONFIG_DIR" ] && [ -w "$PROMETHEUS_CONFIG_DIR" ]; then
    cp alerts/tick-processing-alerts.yml "$PROMETHEUS_CONFIG_DIR/rules/tick-processing-alerts.yml"
    echo -e "${GREEN}✓${NC} Prometheus alerts deployed to $PROMETHEUS_CONFIG_DIR/rules/"
    echo "  Reload Prometheus to apply: curl -X POST http://localhost:9090/-/reload"
else
    echo -e "${YELLOW}⚠${NC} Cannot write to $PROMETHEUS_CONFIG_DIR"
    echo "  Manual deployment required:"
    echo "    1. Copy alerts/tick-processing-alerts.yml to Prometheus rules directory"
    echo "    2. Reload Prometheus configuration"
fi

echo ""

# Verify deployment
echo "Verifying deployment..."
echo ""
echo "Grafana Dashboard:"
echo "  - URL: $GRAFANA_URL/dashboards"
echo "  - Search for: 'Tick Processing - Performance & Health'"
echo ""
echo "Prometheus Alerts:"
echo "  - URL: http://localhost:9090/alerts"
echo "  - Group: tick_processing"
echo "  - Rules: 15+ alerting rules"
echo ""

echo "=========================================="
echo -e "${GREEN}Deployment Complete${NC}"
echo "=========================================="
echo ""
echo "Next steps:"
echo "  1. Verify dashboard appears in Grafana"
echo "  2. Check Prometheus alerts are loaded"
echo "  3. Configure alert notification channels"
echo "  4. Test alert firing with load tests"
echo ""
