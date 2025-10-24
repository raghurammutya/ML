#!/bin/bash

# Deployment Validation Script
# Validates production environment integrity before allowing deployments

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCK_FILE="/tmp/tradingview-production.lock"
CHECKSUM_FILE="$PROJECT_ROOT/.production_checksums"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

validate_lock() {
    if [[ ! -f "$LOCK_FILE" ]]; then
        echo -e "${RED}ERROR:${NC} Production environment is not properly locked"
        return 1
    fi
    
    source "$LOCK_FILE"
    if [[ "$PRODUCTION_LOCKED" != "true" ]]; then
        echo -e "${RED}ERROR:${NC} Production lock is invalid"
        return 1
    fi
    
    echo -e "${GREEN}✓${NC} Production lock validated"
}

validate_integrity() {
    if [[ ! -f "$CHECKSUM_FILE" ]]; then
        echo -e "${RED}ERROR:${NC} Integrity checksums not found"
        return 1
    fi
    
    echo "Validating file integrity..."
    if sha256sum -c "$CHECKSUM_FILE" --quiet; then
        echo -e "${GREEN}✓${NC} All files integrity validated"
    else
        echo -e "${RED}ERROR:${NC} File integrity check failed"
        return 1
    fi
}

validate_environment() {
    echo "Validating environment variables..."
    
    local required_vars=(
        "ENVIRONMENT"
        "DATABASE_URL"
        "REDIS_URL"
        "BACKEND_SERVICE_NAME"
        "FRONTEND_SERVICE_NAME"
    )
    
    for var in "${required_vars[@]}"; do
        if [[ -z "${!var}" ]]; then
            echo -e "${RED}ERROR:${NC} Required environment variable $var is not set"
            return 1
        fi
    done
    
    if [[ "$ENVIRONMENT" != "production" ]]; then
        echo -e "${RED}ERROR:${NC} ENVIRONMENT must be set to 'production'"
        return 1
    fi
    
    echo -e "${GREEN}✓${NC} Environment variables validated"
}

validate_docker_services() {
    echo "Validating Docker services..."
    
    local required_services=(
        "tv-backend-prod"
        "tv-frontend-prod" 
        "tv-redis-prod"
    )
    
    for service in "${required_services[@]}"; do
        if ! docker ps --filter "name=$service" --filter "status=running" | grep -q "$service"; then
            echo -e "${YELLOW}WARNING:${NC} Service $service is not running"
        else
            echo -e "${GREEN}✓${NC} Service $service is running"
        fi
    done
}

main() {
    echo "=== Production Deployment Validation ==="
    
    validate_lock || exit 1
    validate_integrity || exit 1
    validate_environment || exit 1
    validate_docker_services
    
    echo -e "${GREEN}✓ Production environment validation completed successfully${NC}"
}

main "$@"
