#!/bin/bash
set -e

# Environment switching script
# Usage: ./switch-env.sh [dev|prod]

ENVIRONMENT=${1:-dev}

echo "🔄 Switching to $ENVIRONMENT environment"

# Stop all running containers
echo "🛑 Stopping all TradingView containers..."
docker ps --format "table {{.Names}}" | grep -E "tv-|tradingview" | xargs -r docker stop
docker ps -a --format "table {{.Names}}" | grep -E "tv-|tradingview" | xargs -r docker rm

# Clean up networks
echo "🧹 Cleaning up networks..."
docker network ls --format "table {{.Name}}" | grep -E "tradingview" | xargs -r docker network rm 2>/dev/null || true

# Deploy new environment
echo "🚀 Deploying $ENVIRONMENT environment..."
./scripts/deploy.sh "$ENVIRONMENT" --build

echo "✅ Successfully switched to $ENVIRONMENT environment"