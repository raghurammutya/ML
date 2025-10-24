#!/bin/bash
set -e

# Unified deployment script for TradingView ML Visualization System
# Usage: ./deploy.sh [dev|prod] [--build] [--logs]

ENVIRONMENT=${1:-dev}
BUILD_FLAG=${2}
LOGS_FLAG=${3}

echo "🚀 Deploying TradingView ML Visualization System"
echo "📌 Environment: $ENVIRONMENT"
echo "⏰ $(date)"

# Validate environment
if [[ "$ENVIRONMENT" != "dev" && "$ENVIRONMENT" != "prod" ]]; then
    echo "❌ Error: Environment must be 'dev' or 'prod'"
    echo "Usage: $0 [dev|prod] [--build] [--logs]"
    exit 1
fi

# Set environment file
ENV_FILE=".env.$ENVIRONMENT"
if [[ ! -f "$ENV_FILE" ]]; then
    echo "❌ Error: Environment file $ENV_FILE not found"
    exit 1
fi

echo "📄 Using environment file: $ENV_FILE"

# Export environment variables
set -a
source "$ENV_FILE"
set +a

# Generate unique network name
export COMPOSE_PROJECT_NAME="tradingview-$ENVIRONMENT"

echo "🔧 Configuration:"
echo "   - Environment: $ENVIRONMENT"
echo "   - Backend Port: $BACKEND_PORT"
echo "   - Frontend Port: $FRONTEND_PORT"
echo "   - Database: $DB_HOST:$DB_PORT/$DB_NAME"
echo "   - Redis: $REDIS_HOST:$REDIS_PORT"
echo "   - Backend Service: $BACKEND_SERVICE_NAME"
echo "   - Frontend Service: $FRONTEND_SERVICE_NAME"

# Stop existing containers
echo "🛑 Stopping existing containers..."
docker-compose -f docker-compose.unified.yml --env-file "$ENV_FILE" down --remove-orphans

# Build if requested
if [[ "$BUILD_FLAG" == "--build" ]]; then
    echo "🏗️  Building containers..."
    docker-compose -f docker-compose.unified.yml --env-file "$ENV_FILE" build --no-cache
fi

# Start services
echo "🚀 Starting services..."
docker-compose -f docker-compose.unified.yml --env-file "$ENV_FILE" up -d

# Wait for services to be healthy
echo "⏳ Waiting for services to be healthy..."
sleep 10

# Health checks
echo "🔍 Performing health checks..."

# Check backend
BACKEND_URL="http://localhost:$BACKEND_PORT"
echo "   Checking backend: $BACKEND_URL/health"
for i in {1..30}; do
    if curl -s "$BACKEND_URL/health" > /dev/null 2>&1; then
        echo "   ✅ Backend is healthy"
        break
    fi
    if [[ $i -eq 30 ]]; then
        echo "   ❌ Backend health check failed"
        exit 1
    fi
    sleep 2
done

# Check frontend
FRONTEND_URL="http://localhost:$FRONTEND_PORT"
echo "   Checking frontend: $FRONTEND_URL/health"
for i in {1..30}; do
    if curl -s "$FRONTEND_URL/health" > /dev/null 2>&1; then
        echo "   ✅ Frontend is healthy"
        break
    fi
    if [[ $i -eq 30 ]]; then
        echo "   ❌ Frontend health check failed"
        exit 1
    fi
    sleep 2
done

# Test API connectivity
echo "   Checking API connectivity: $FRONTEND_URL/tradingview-api/health"
if curl -s "$FRONTEND_URL/tradingview-api/health" | grep -q "healthy"; then
    echo "   ✅ API proxy is working"
else
    echo "   ⚠️  API proxy may have issues"
fi

echo ""
echo "🎉 Deployment completed successfully!"
echo ""
echo "📊 Access URLs:"
echo "   Frontend: http://localhost:$FRONTEND_PORT"
if [[ "$ENVIRONMENT" == "prod" ]]; then
    echo "   Frontend: http://5.223.52.98:$FRONTEND_PORT"
fi
echo "   Backend:  $BACKEND_URL"
echo "   API:      $FRONTEND_URL/tradingview-api/"
echo ""
echo "🔧 Management Commands:"
echo "   View logs:    docker-compose -f docker-compose.unified.yml --env-file $ENV_FILE logs -f"
echo "   Stop:         docker-compose -f docker-compose.unified.yml --env-file $ENV_FILE down"
echo "   Restart:      $0 $ENVIRONMENT"
echo "   Rebuild:      $0 $ENVIRONMENT --build"

# Show logs if requested
if [[ "$LOGS_FLAG" == "--logs" ]]; then
    echo ""
    echo "📋 Showing logs (Ctrl+C to exit)..."
    docker-compose -f docker-compose.unified.yml --env-file "$ENV_FILE" logs -f
fi