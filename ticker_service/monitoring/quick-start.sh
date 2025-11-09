#!/bin/bash
#
# Quick Start Script for Prometheus & Grafana
# No sudo required - uses Docker
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo ""
echo "=========================================="
echo "  Ticker Service Monitoring Quick Start"
echo "=========================================="
echo ""

# Check if Docker is available
if ! command -v docker &> /dev/null; then
    echo -e "${RED}Error: Docker is not installed${NC}"
    echo "Please install Docker first: https://docs.docker.com/get-docker/"
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo -e "${RED}Error: Docker Compose is not installed${NC}"
    echo "Please install Docker Compose first"
    exit 1
fi

# Check if Docker is running
if ! docker info &> /dev/null; then
    echo -e "${RED}Error: Docker is not running${NC}"
    echo "Please start Docker first"
    exit 1
fi

echo -e "${GREEN}✓${NC} Docker is available and running"
echo ""

# Navigate to monitoring directory
cd "$(dirname "$0")"

echo "Step 1: Starting Prometheus and Grafana containers..."
docker-compose -f docker-compose.monitoring.yml up -d

echo ""
echo -e "${GREEN}✓${NC} Containers started"
echo ""

# Wait for services to be ready
echo "Step 2: Waiting for services to be ready..."
sleep 5

# Check Prometheus
echo -n "Checking Prometheus... "
if curl -s --fail http://localhost:9090/-/healthy > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Ready${NC}"
else
    echo -e "${YELLOW}⚠ Not ready yet (may take a few more seconds)${NC}"
fi

# Check Grafana
echo -n "Checking Grafana... "
if curl -s --fail http://localhost:3000/api/health > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Ready${NC}"
else
    echo -e "${YELLOW}⚠ Not ready yet (may take a few more seconds)${NC}"
fi

echo ""
echo "=========================================="
echo -e "${GREEN}Monitoring Stack is Running!${NC}"
echo "=========================================="
echo ""
echo "Access URLs:"
echo -e "  ${BLUE}Prometheus:${NC} http://localhost:9090"
echo -e "  ${BLUE}Grafana:${NC}    http://localhost:3000"
echo ""
echo "Grafana Login:"
echo "  Username: admin"
echo "  Password: admin"
echo "  (You'll be prompted to change password on first login)"
echo ""
echo "Next Steps:"
echo "  1. Start ticker service on port 8000"
echo "  2. Open Grafana: http://localhost:3000"
echo "  3. Navigate to Dashboards → Ticker Service"
echo "  4. View 'Tick Processing - Performance & Health' dashboard"
echo ""
echo "Useful Commands:"
echo "  ${BLUE}View logs:${NC}        docker-compose -f docker-compose.monitoring.yml logs -f"
echo "  ${BLUE}Check status:${NC}     docker-compose -f docker-compose.monitoring.yml ps"
echo "  ${BLUE}Stop services:${NC}    docker-compose -f docker-compose.monitoring.yml down"
echo "  ${BLUE}Restart:${NC}          docker-compose -f docker-compose.monitoring.yml restart"
echo ""
echo "Dashboard import will happen automatically via provisioning."
echo "If not, manually import: grafana/tick-processing-dashboard.json"
echo ""
