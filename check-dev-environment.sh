#!/bin/bash

# Development Environment Status Check
# Verifies that dev environment is running and behaves like production

set -e

echo "=== Development Environment Status Check ==="
echo "Date: $(date)"
echo ""

# Check development services
echo "🔍 Checking Development Services:"
echo "--------------------------------"

# Backend Dev
if curl -s http://localhost:8001/health > /dev/null; then
    echo "✅ Backend Dev (port 8001): Running"
    backend_health=$(curl -s http://localhost:8001/health | jq -r '.status' 2>/dev/null || echo "unknown")
    echo "   Health Status: $backend_health"
else
    echo "❌ Backend Dev (port 8001): Not responding"
fi

# Frontend Dev  
if curl -s http://localhost:3001 > /dev/null; then
    echo "✅ Frontend Dev (port 3001): Running"
else
    echo "❌ Frontend Dev (port 3001): Not responding"
fi

# Redis Dev
if docker exec tv-redis-dev redis-cli ping > /dev/null 2>&1; then
    echo "✅ Redis Dev (port 6380): Running"
else
    echo "❌ Redis Dev: Not responding"
fi

# Postgres Dev
if docker exec tv-postgres-dev pg_isready -U stocksblitz > /dev/null 2>&1; then
    echo "✅ Postgres Dev (port 5433): Running"
else
    echo "❌ Postgres Dev: Not responding"
fi

echo ""
echo "🔍 Checking Development Database:"
echo "--------------------------------"

# Check critical tables exist in dev database
tables=("ml_labeled_data" "nifty50_ohlc" "nifty_fo_ohlc")
for table in "${tables[@]}"; do
    count=$(docker exec tv-postgres-dev psql -U stocksblitz -d stocksblitz_unified -t -c "SELECT COUNT(*) FROM $table;" 2>/dev/null | tr -d ' ' || echo "0")
    if [[ "$count" =~ ^[0-9]+$ ]] && [[ $count -gt 0 ]]; then
        echo "✅ $table: $count rows"
    else
        echo "❌ $table: No data or table missing"
    fi
done

echo ""
echo "🔍 Testing Development API Endpoints:"
echo "------------------------------------"

# Test chart data endpoint
if curl -s "http://localhost:8001/history?symbol=NIFTY50&resolution=5&from=1640995200&to=1672531200" | jq -e '.s == "ok"' > /dev/null 2>&1; then
    echo "✅ Chart data endpoint: Working"
else
    echo "❌ Chart data endpoint: Failed"
fi

# Test labels endpoint
if curl -s "http://localhost:8001/marks?symbol=NIFTY50&resolution=5&from=1640995200&to=1672531200" | jq -e '.marks' > /dev/null 2>&1; then
    echo "✅ Labels endpoint: Working"
else
    echo "❌ Labels endpoint: Failed"
fi

echo ""
echo "🔍 Environment Configuration Check:"
echo "----------------------------------"

# Check if using correct dev database
dev_db_host=$(docker exec tv-backend-dev printenv DB_HOST 2>/dev/null || echo "not set")
dev_db_port=$(docker exec tv-backend-dev printenv DB_PORT 2>/dev/null || echo "not set")
echo "Dev Backend DB Host: $dev_db_host"
echo "Dev Backend DB Port: $dev_db_port"

# Check environment
dev_env=$(docker exec tv-backend-dev printenv ENVIRONMENT 2>/dev/null || echo "not set")
echo "Environment: $dev_env"

echo ""
echo "🔍 Port Mapping Summary:"
echo "----------------------"
echo "Development:"
echo "  Frontend: http://localhost:3001"
echo "  Backend:  http://localhost:8001" 
echo "  Database: localhost:5433"
echo "  Redis:    localhost:6380"
echo ""
echo "Production:"
echo "  Frontend: http://localhost:3080"
echo "  Backend:  http://localhost:8888"
echo "  Database: localhost:5432 (external)"
echo "  Redis:    localhost:6382"

echo ""
echo "=== Development Environment Check Complete ==="