#!/bin/bash

echo "======================================================"
echo "Starting Backend - Development Environment"
echo "======================================================"
echo ""

# Ensure we're using dev config
cp .env.dev .env

echo "Configuration:"
grep -E "ENVIRONMENT|REDIS_URL|DB_PORT|TICKER_SERVICE_URL|BACKEND_PORT" .env
echo ""

# Check connections
echo "Testing connections..."
echo -n "Redis (8002): "
redis-cli -p 8002 ping 2>/dev/null && echo "✅" || echo "❌"

echo -n "PostgreSQL (8003): "
PGPASSWORD=stocksblitz123 psql -h localhost -p 8003 -U stocksblitz -d stocksblitz_dev -c "SELECT 1;" -t 2>/dev/null && echo "✅" || echo "❌"

echo -n "Ticker Service (8080): "
curl -sf http://localhost:8080/health >/dev/null 2>&1 && echo "✅" || echo "❌"

echo ""
echo "Starting backend on port 8010..."
echo "Logs will be written to: backend_dev.log"
echo ""

# Start backend
nohup uvicorn app.main:app --host 0.0.0.0 --port 8010 --reload > backend_dev.log 2>&1 &
BACKEND_PID=$!

sleep 3

# Check if it started
if ps -p $BACKEND_PID > /dev/null; then
    echo "✅ Backend started successfully (PID: $BACKEND_PID)"
    echo ""
    echo "Access backend at: http://localhost:8010"
    echo "Health check: http://localhost:8010/health"
    echo "View logs: tail -f backend_dev.log"
    echo ""
else
    echo "❌ Backend failed to start. Check backend_dev.log for errors"
    tail -20 backend_dev.log
    exit 1
fi
