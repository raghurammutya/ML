#!/bin/bash

# Fix Development Environment Configuration
# Ensures dev environment matches production setup but with separate services

set -e

echo "=== Fixing Development Environment ==="
echo "Date: $(date)"
echo ""

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Load development environment variables
if [[ -f "$PROJECT_ROOT/.env.dev" ]]; then
    export $(cat "$PROJECT_ROOT/.env.dev" | grep -v '^#' | xargs)
    echo "✅ Loaded development environment variables"
else
    echo "❌ .env.dev file not found!"
    exit 1
fi

echo ""
echo "🔧 Current Development Configuration:"
echo "Backend Port: $BACKEND_PORT"
echo "Frontend Port: $FRONTEND_PORT" 
echo "Database: $DB_NAME"
echo "Redis Service: $REDIS_SERVICE_NAME"
echo ""

# Stop current development services
echo "🛑 Stopping current development services..."
docker-compose -f docker-compose.unified.yml --env-file .env.dev down || true

echo ""
echo "🗄️ Checking Development Database..."

# Check if development database has data
dev_db_container="tv-postgres-dev"
if docker ps --filter "name=$dev_db_container" --filter "status=running" | grep -q "$dev_db_container"; then
    echo "✅ Development database container is running"
    
    # Check tables
    tables_exist=$(docker exec "$dev_db_container" psql -U stocksblitz -d stocksblitz_unified -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_name IN ('ml_labeled_data', 'nifty50_ohlc', 'nifty_fo_ohlc');" 2>/dev/null | tr -d ' ' || echo "0")
    
    if [[ "$tables_exist" == "3" ]]; then
        echo "✅ All critical tables exist in development database"
        
        # Check data counts
        for table in ml_labeled_data nifty50_ohlc nifty_fo_ohlc; do
            count=$(docker exec "$dev_db_container" psql -U stocksblitz -d stocksblitz_unified -t -c "SELECT COUNT(*) FROM $table;" 2>/dev/null | tr -d ' ' || echo "0")
            echo "   $table: $count rows"
        done
    else
        echo "⚠️ Some tables missing in development database"
        echo "   Found $tables_exist out of 3 expected tables"
    fi
else
    echo "❌ Development database container not running"
fi

echo ""
echo "🚀 Starting Development Services with Correct Configuration..."

# Start development services with proper environment
docker-compose -f docker-compose.unified.yml --env-file .env.dev up -d

# Wait for services to start
echo "⏳ Waiting for services to start..."
sleep 15

echo ""
echo "🔍 Verifying Development Services..."

# Check each service
services=("$BACKEND_SERVICE_NAME" "$FRONTEND_SERVICE_NAME" "$REDIS_SERVICE_NAME")
for service in "${services[@]}"; do
    if docker ps --filter "name=$service" --filter "status=running" | grep -q "$service"; then
        echo "✅ $service: Running"
    else
        echo "❌ $service: Not running"
    fi
done

echo ""
echo "🧪 Testing Development Environment..."

# Test backend health
echo "Testing backend health..."
max_attempts=10
attempt=1

while [[ $attempt -le $max_attempts ]]; do
    if curl -s "http://localhost:$BACKEND_PORT/health" | grep -q "healthy\|ok"; then
        echo "✅ Backend health check passed"
        break
    elif [[ $attempt -eq $max_attempts ]]; then
        echo "❌ Backend health check failed after $max_attempts attempts"
        echo "Backend logs:"
        docker logs "$BACKEND_SERVICE_NAME" --tail 10
    else
        echo "⏳ Backend health check attempt $attempt/$max_attempts..."
        sleep 3
    fi
    ((attempt++))
done

# Test frontend
if curl -s "http://localhost:$FRONTEND_PORT" > /dev/null; then
    echo "✅ Frontend responding"
else
    echo "❌ Frontend not responding"
fi

# Test API endpoints
echo ""
echo "🔍 Testing API Endpoints..."

# Test chart data
if curl -s "http://localhost:$BACKEND_PORT/history?symbol=NIFTY50&resolution=5&from=1640995200&to=1672531200" | jq -e '.s == "ok"' > /dev/null 2>&1; then
    echo "✅ Chart data endpoint working"
else
    echo "❌ Chart data endpoint failed"
fi

# Test labels
if curl -s "http://localhost:$BACKEND_PORT/marks?symbol=NIFTY50&resolution=5&from=1640995200&to=1672531200" | jq -e '.marks' > /dev/null 2>&1; then
    echo "✅ Labels endpoint working"
else
    echo "❌ Labels endpoint failed"
fi

echo ""
echo "🎯 Development Environment Status:"
echo "================================="
echo "Frontend: http://localhost:$FRONTEND_PORT"
echo "Backend:  http://localhost:$BACKEND_PORT"
echo "Database: localhost:5433 (PostgreSQL)"
echo "Redis:    localhost:6380"
echo ""
echo "Compare with Production:"
echo "Frontend: http://localhost:3080"
echo "Backend:  http://localhost:8888"
echo ""

if curl -s "http://localhost:$BACKEND_PORT/health" | grep -q "healthy\|ok" && curl -s "http://localhost:$FRONTEND_PORT" > /dev/null; then
    echo "🎉 Development environment is ready for testing!"
    echo ""
    echo "You can now test your changes in development before deploying to production."
    echo ""
    echo "To test the frontend with charts:"
    echo "1. Open http://localhost:$FRONTEND_PORT in your browser"
    echo "2. Verify charts load with IST timezone"
    echo "3. Test crosshair OHLCV display functionality"
    echo "4. Verify all timeframes work correctly"
else
    echo "⚠️ Development environment has issues - check logs above"
    exit 1
fi