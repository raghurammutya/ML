#!/bin/bash

# Secure Deployment Script
# Ensures only authorized deployments can occur in production

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
LOCK_FILE="/tmp/tradingview-production.lock"
DEPLOY_LOG="/var/log/tradingview-deployments.log"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_deploy() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a "$DEPLOY_LOG"
}

error_deploy() {
    echo -e "${RED}[$(date '+%Y-%m-%d %H:%M:%S')] ERROR:${NC} $1" | tee -a "$DEPLOY_LOG"
}

warn_deploy() {
    echo -e "${YELLOW}[$(date '+%Y-%m-%d %H:%M:%S')] WARNING:${NC} $1" | tee -a "$DEPLOY_LOG"
}

# Check if production is locked
check_production_lock() {
    if [[ -f "$LOCK_FILE" ]]; then
        source "$LOCK_FILE"
        if [[ "$PRODUCTION_LOCKED" == "true" ]]; then
            error_deploy "Production environment is locked!"
            error_deploy "Locked at: $LOCKED_AT by $LOCKED_BY"
            error_deploy "To deploy, first unlock with: sudo ./scripts/unlock-production.sh"
            exit 1
        fi
    fi
}

# Validate deployment prerequisites
validate_deployment() {
    log_deploy "Validating deployment prerequisites..."
    
    # Check environment
    if [[ "${ENVIRONMENT:-}" == "production" ]] && [[ -f "$LOCK_FILE" ]]; then
        error_deploy "Cannot deploy to locked production environment"
        exit 1
    fi
    
    # Check git status
    if ! git diff-index --quiet HEAD -- 2>/dev/null; then
        warn_deploy "Working directory has uncommitted changes"
        read -p "Continue anyway? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
    
    # Check for critical files
    local critical_files=(
        "docker-compose.unified.yml"
        "frontend/src/App.tsx" 
        "frontend/src/components/CustomChartWithMLLabels.tsx"
        "backend/app/main.py"
    )
    
    for file in "${critical_files[@]}"; do
        if [[ ! -f "$PROJECT_ROOT/$file" ]]; then
            error_deploy "Critical file missing: $file"
            exit 1
        fi
    done
    
    log_deploy "Deployment validation passed"
}

# Safe deployment with rollback capability
safe_deploy() {
    local environment="${1:-development}"
    
    log_deploy "Starting safe deployment to $environment environment"
    
    # Create pre-deployment backup
    local backup_dir="/opt/tradingview-backups"
    local timestamp=$(date +%Y%m%d_%H%M%S)
    local backup_path="$backup_dir/pre_deploy_$timestamp"
    
    mkdir -p "$backup_dir"
    cp -r "$PROJECT_ROOT" "$backup_path"
    log_deploy "Pre-deployment backup created: $backup_path"
    
    # Set environment variables
    if [[ "$environment" == "production" ]]; then
        export $(cat "$PROJECT_ROOT/.env.prod" | grep -v '^#' | xargs)
    else
        export $(cat "$PROJECT_ROOT/.env.dev" | grep -v '^#' | xargs)
    fi
    
    # Deploy
    log_deploy "Deploying to $environment..."
    
    cd "$PROJECT_ROOT"
    
    # Build and deploy
    if docker-compose -f docker-compose.unified.yml down; then
        log_deploy "Services stopped successfully"
    else
        warn_deploy "Some services may not have been running"
    fi
    
    if docker-compose -f docker-compose.unified.yml build; then
        log_deploy "Build completed successfully"
    else
        error_deploy "Build failed - restoring from backup"
        restore_backup "$backup_path"
        exit 1
    fi
    
    if docker-compose -f docker-compose.unified.yml up -d; then
        log_deploy "Services started successfully"
    else
        error_deploy "Service startup failed - restoring from backup"
        restore_backup "$backup_path"
        exit 1
    fi
    
    # Verify deployment
    sleep 10
    if verify_deployment "$environment"; then
        log_deploy "Deployment verified successfully"
        log_deploy "Deployment to $environment completed successfully"
    else
        error_deploy "Deployment verification failed - restoring from backup"
        restore_backup "$backup_path"
        exit 1
    fi
}

# Verify deployment health
verify_deployment() {
    local environment="$1"
    local max_attempts=6
    local attempt=1
    
    log_deploy "Verifying deployment health..."
    
    while [[ $attempt -le $max_attempts ]]; do
        log_deploy "Health check attempt $attempt/$max_attempts"
        
        # Check if containers are running
        local running_containers=$(docker-compose -f docker-compose.unified.yml ps --services --filter "status=running" | wc -l)
        local total_containers=$(docker-compose -f docker-compose.unified.yml ps --services | wc -l)
        
        if [[ $running_containers -eq $total_containers ]] && [[ $running_containers -gt 0 ]]; then
            # Check API health
            local api_port="${BACKEND_PORT:-8888}"
            if curl -s -f "http://localhost:$api_port/health" > /dev/null; then
                log_deploy "✓ API health check passed"
                
                # Check frontend
                local frontend_port="${FRONTEND_PORT:-3080}" 
                if curl -s -f "http://localhost:$frontend_port" > /dev/null; then
                    log_deploy "✓ Frontend health check passed"
                    return 0
                else
                    warn_deploy "Frontend health check failed"
                fi
            else
                warn_deploy "API health check failed"
            fi
        else
            warn_deploy "Not all containers are running ($running_containers/$total_containers)"
        fi
        
        sleep 10
        ((attempt++))
    done
    
    error_deploy "Deployment verification failed after $max_attempts attempts"
    return 1
}

# Restore from backup
restore_backup() {
    local backup_path="$1"
    
    error_deploy "Restoring from backup: $backup_path"
    
    # Stop current services
    docker-compose -f docker-compose.unified.yml down || true
    
    # Restore files
    rsync -av --delete "$backup_path/" "$PROJECT_ROOT/"
    
    # Restart services
    docker-compose -f docker-compose.unified.yml up -d
    
    log_deploy "Restoration completed"
}

# Main deployment function
main() {
    local environment="${1:-development}"
    local force="${2:-false}"
    
    echo "=== Secure TradingView Deployment ==="
    echo "Environment: $environment"
    echo "Force: $force"
    echo ""
    
    # Production safety checks
    if [[ "$environment" == "production" ]]; then
        if [[ "$force" != "--force" ]]; then
            check_production_lock
        fi
        
        echo -e "${RED}WARNING: Deploying to PRODUCTION environment${NC}"
        read -p "Are you absolutely sure? (type 'DEPLOY' to confirm): " confirm
        if [[ "$confirm" != "DEPLOY" ]]; then
            echo "Deployment cancelled"
            exit 0
        fi
    fi
    
    validate_deployment
    safe_deploy "$environment"
    
    echo ""
    log_deploy "=== Deployment completed successfully ==="
    
    if [[ "$environment" == "production" ]]; then
        echo -e "${YELLOW}Remember to re-lock production with: sudo ./scripts/lock-production.sh${NC}"
    fi
}

# Show usage if no arguments
if [[ $# -eq 0 ]]; then
    echo "Usage: $0 <environment> [--force]"
    echo ""
    echo "Environments:"
    echo "  development  - Deploy to development environment"
    echo "  production   - Deploy to production environment (requires unlock)"
    echo ""
    echo "Options:"
    echo "  --force      - Force deployment even if production is locked (DANGEROUS)"
    echo ""
    echo "Examples:"
    echo "  $0 development"
    echo "  $0 production"
    echo ""
    exit 1
fi

main "$@"