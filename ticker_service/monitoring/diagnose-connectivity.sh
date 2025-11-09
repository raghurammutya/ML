#!/bin/bash
#
# Connectivity Diagnostic Script
# Helps troubleshoot external access issues
#

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo ""
echo "=========================================="
echo "  Connectivity Diagnostics"
echo "=========================================="
echo ""

# Get server IP
SERVER_IP=$(hostname -I | awk '{print $1}')
echo -e "${BLUE}Server IP:${NC} $SERVER_IP"
echo ""

# Check Docker containers
echo "1. Docker Containers:"
docker ps --filter "name=ticker-" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null
echo ""

# Check port bindings
echo "2. Port Bindings:"
netstat -tlnp 2>/dev/null | grep -E "(3000|9090)" || ss -tlnp 2>/dev/null | grep -E "(3000|9090)"
echo ""

# Test local connectivity
echo "3. Local Connectivity Tests:"
echo -n "   Grafana (localhost:3000): "
if curl -s --max-time 2 http://localhost:3000/api/health > /dev/null 2>&1; then
    echo -e "${GREEN}✓ OK${NC}"
else
    echo -e "${RED}✗ FAILED${NC}"
fi

echo -n "   Prometheus (localhost:9090): "
if curl -s --max-time 2 http://localhost:9090/-/healthy > /dev/null 2>&1; then
    echo -e "${GREEN}✓ OK${NC}"
else
    echo -e "${RED}✗ FAILED${NC}"
fi
echo ""

# Test external connectivity (via server IP)
echo "4. External Connectivity Tests (via $SERVER_IP):"
echo -n "   Grafana ($SERVER_IP:3000): "
if curl -s --max-time 2 http://$SERVER_IP:3000/api/health > /dev/null 2>&1; then
    echo -e "${GREEN}✓ OK${NC}"
else
    echo -e "${RED}✗ FAILED${NC}"
fi

echo -n "   Prometheus ($SERVER_IP:9090): "
if curl -s --max-time 2 http://$SERVER_IP:9090/-/healthy > /dev/null 2>&1; then
    echo -e "${GREEN}✓ OK${NC}"
else
    echo -e "${RED}✗ FAILED${NC}"
fi
echo ""

# Check firewall (requires sudo)
echo "5. Firewall Status:"
if command -v ufw &> /dev/null; then
    echo "   UFW detected:"
    sudo ufw status 2>/dev/null | head -10 || echo "   (Requires sudo to check)"
elif command -v firewall-cmd &> /dev/null; then
    echo "   firewalld detected:"
    sudo firewall-cmd --list-all 2>/dev/null || echo "   (Requires sudo to check)"
else
    echo "   iptables:"
    sudo iptables -L -n | grep -E "(3000|9090|ACCEPT)" 2>/dev/null || echo "   (Requires sudo to check)"
fi
echo ""

# Summary
echo "=========================================="
echo "Summary:"
echo "=========================================="
echo ""
echo "Access URLs from your Windows laptop:"
echo -e "  ${BLUE}Grafana:${NC}    http://$SERVER_IP:3000"
echo -e "  ${BLUE}Prometheus:${NC} http://$SERVER_IP:9090"
echo ""
echo "Next Steps:"
echo "  1. If local tests pass but external fail → Check firewall"
echo "  2. If using cloud (AWS/Azure/GCP) → Check security groups"
echo "  3. Run firewall commands from EXTERNAL_ACCESS_GUIDE.md"
echo ""

# Provide specific commands
echo "Quick Firewall Fix (requires sudo):"
echo -e "  ${BLUE}UFW:${NC}"
echo "    sudo ufw allow 3000/tcp"
echo "    sudo ufw allow 9090/tcp"
echo ""
echo -e "  ${BLUE}firewalld:${NC}"
echo "    sudo firewall-cmd --permanent --add-port=3000/tcp"
echo "    sudo firewall-cmd --permanent --add-port=9090/tcp"
echo "    sudo firewall-cmd --reload"
echo ""
