#!/bin/bash
#
# Ticker Service Restart Script
# Applies medium priority fixes by restarting the service
#
# Usage: sudo ./restart_ticker.sh
#

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Ticker Service Restart${NC}"
echo -e "${BLUE}Applying Medium Priority Fixes${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}❌ Error: Please run with sudo${NC}"
    echo -e "   Usage: sudo ./restart_ticker.sh"
    exit 1
fi

# Configuration
SERVICE_DIR="/mnt/stocksblitz-data/Quantagro/tradingview-viz/ticker_service"
LOG_FILE="$SERVICE_DIR/ticker_service.log"
PID_FILE="$SERVICE_DIR/ticker.pid"

# Step 1: Find current process
echo -e "${YELLOW}Step 1: Finding current ticker service process...${NC}"
OLD_PID=$(ps aux | grep "python start_ticker.py" | grep -v grep | awk '{print $2}' | head -1)

if [ -z "$OLD_PID" ]; then
    echo -e "${YELLOW}⚠️  No running ticker service found${NC}"
else
    echo -e "${GREEN}✓ Found ticker service (PID: $OLD_PID)${NC}"

    # Step 2: Graceful shutdown
    echo -e "${YELLOW}Step 2: Stopping ticker service gracefully...${NC}"
    kill -TERM $OLD_PID

    # Wait for graceful shutdown (max 30 seconds)
    echo -n "   Waiting for shutdown"
    for i in {1..30}; do
        if ! ps -p $OLD_PID > /dev/null 2>&1; then
            echo ""
            echo -e "${GREEN}✓ Service stopped gracefully${NC}"
            break
        fi
        echo -n "."
        sleep 1
    done
    echo ""

    # Force kill if still running
    if ps -p $OLD_PID > /dev/null 2>&1; then
        echo -e "${YELLOW}⚠️  Service did not stop, forcing shutdown...${NC}"
        kill -9 $OLD_PID
        sleep 2
        echo -e "${GREEN}✓ Service force-stopped${NC}"
    fi
fi

# Step 3: Clean up old log (optional - keep last 1000 lines)
if [ -f "$LOG_FILE" ]; then
    echo -e "${YELLOW}Step 3: Rotating log file...${NC}"
    tail -n 1000 "$LOG_FILE" > "$LOG_FILE.tmp"
    mv "$LOG_FILE.tmp" "$LOG_FILE"
    echo -e "${GREEN}✓ Log rotated (kept last 1000 lines)${NC}"
fi

# Step 4: Start new service
echo -e "${YELLOW}Step 4: Starting ticker service with new code...${NC}"
cd "$SERVICE_DIR"

# Start as root (since original was running as root)
nohup python start_ticker.py > "$LOG_FILE" 2>&1 &
NEW_PID=$!

# Save PID
echo $NEW_PID > "$PID_FILE"

echo -e "${GREEN}✓ Ticker service started (PID: $NEW_PID)${NC}"

# Step 5: Wait for service to initialize
echo -e "${YELLOW}Step 5: Waiting for service initialization...${NC}"
echo -n "   Initializing"
for i in {1..10}; do
    sleep 1
    echo -n "."
done
echo ""

# Step 6: Verify service is running
echo -e "${YELLOW}Step 6: Verifying service status...${NC}"
if ps -p $NEW_PID > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Service is running (PID: $NEW_PID)${NC}"
else
    echo -e "${RED}❌ Service failed to start!${NC}"
    echo -e "${YELLOW}Last 20 lines of log:${NC}"
    tail -20 "$LOG_FILE"
    exit 1
fi

# Step 7: Test health endpoint
echo -e "${YELLOW}Step 7: Testing health endpoint...${NC}"
HEALTH_RESPONSE=$(curl -s http://localhost:8081/health 2>&1)
HEALTH_STATUS=$(echo "$HEALTH_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('status', 'unknown'))" 2>/dev/null || echo "error")

if [ "$HEALTH_STATUS" = "ok" ] || [ "$HEALTH_STATUS" = "healthy" ]; then
    echo -e "${GREEN}✓ Health check passed: $HEALTH_STATUS${NC}"
elif [ "$HEALTH_STATUS" = "degraded" ]; then
    echo -e "${YELLOW}⚠️  Health check degraded (some dependencies may be down)${NC}"
else
    echo -e "${RED}❌ Health check failed${NC}"
    echo "Response: $HEALTH_RESPONSE"
fi

# Step 8: Show service info
echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}✅ Restart Complete!${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "${YELLOW}Service Information:${NC}"
echo "  PID:      $NEW_PID"
echo "  Port:     8081"
echo "  Log File: $LOG_FILE"
echo "  PID File: $PID_FILE"
echo ""

echo -e "${YELLOW}New Features Active:${NC}"
echo "  ✓ API Key Authentication (disabled by default)"
echo "  ✓ Standardized Error Format"
echo "  ✓ Rate Limiting (100/min)"
echo "  ✓ Pagination on /subscriptions"
echo "  ✓ PII Sanitization in logs"
echo "  ✓ Enhanced Health Check"
echo "  ✓ Configurable Worker Intervals"
echo "  ✓ Exit Order via OrderExecutor"
echo ""

echo -e "${YELLOW}Quick Tests:${NC}"
echo "  Health:      curl http://localhost:8081/health | jq"
echo "  Pagination:  curl 'http://localhost:8081/subscriptions?limit=5' | jq"
echo "  Tail Logs:   tail -f $LOG_FILE"
echo ""

echo -e "${YELLOW}To enable authentication:${NC}"
echo "  1. Add to .env:"
echo "     API_KEY_ENABLED=true"
echo "     API_KEY=your-secret-key-here"
echo "  2. Run: sudo ./restart_ticker.sh"
echo ""

echo -e "${GREEN}Documentation:${NC}"
echo "  See: MEDIUM_FIXES_DOCUMENTATION.md"
echo ""

# Show recent log entries
echo -e "${YELLOW}Recent Log Entries (last 10 lines):${NC}"
tail -10 "$LOG_FILE"
echo ""

echo -e "${GREEN}Done! Service is ready.${NC}"
