#!/bin/bash

# TradingView ML Visualization Deployment Script
# Usage: ./deploy.sh [environment] [action]
# Examples:
#   ./deploy.sh dev start
#   ./deploy.sh staging deploy
#   ./deploy.sh prod restart

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
DOCKER_DIR="$PROJECT_ROOT/deployment/docker"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
ENVIRONMENT=${1:-dev}
ACTION=${2:-start}

# Logging function
log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Help function
show_help() {
    cat << EOF
TradingView ML Visualization Deployment Script

Usage: $0 [ENVIRONMENT] [ACTION]

ENVIRONMENTS:
    dev         Development environment (default)
    staging     Staging environment
    prod        Production environment

ACTIONS:
    start       Start services (default)
    stop        Stop services
    restart     Restart services
    deploy      Full deployment (build + start)
    logs        Show service logs
    status      Show service status
    clean       Clean up containers and volumes
    backup      Create database backup
    restore     Restore database from backup

Examples:
    $0 dev start                # Start development environment
    $0 staging deploy           # Deploy to staging
    $0 prod restart             # Restart production services
    $0 prod logs backend        # Show production backend logs

EOF
}

# Validate environment
validate_environment() {
    case $ENVIRONMENT in
        dev|staging|prod)
            log "Deploying to $ENVIRONMENT environment"
            ;;
        *)
            error "Invalid environment: $ENVIRONMENT"
            error "Valid environments: dev, staging, prod"
            exit 1
            ;;
    esac
}

# Load environment variables
load_env() {
    local env_file="$PROJECT_ROOT/.env.$ENVIRONMENT"
    
    if [[ -f "$env_file" ]]; then
        log "Loading environment variables from $env_file"
        set -a
        source "$env_file"
        set +a
    else
        warning "Environment file not found: $env_file"
        warning "Using default environment variables"
    fi
}

# Get Docker Compose file
get_compose_file() {
    case $ENVIRONMENT in
        dev)
            echo "$DOCKER_DIR/docker-compose.dev.yml"
            ;;
        staging)
            echo "$DOCKER_DIR/docker-compose.staging.yml"
            ;;
        prod)
            echo "$DOCKER_DIR/docker-compose.prod.yml"
            ;;
    esac
}

# Check prerequisites
check_prerequisites() {
    log "Checking prerequisites..."
    
    # Check Docker
    if ! command -v docker &> /dev/null; then
        error "Docker is not installed"
        exit 1
    fi
    
    # Check Docker Compose
    if ! command -v docker-compose &> /dev/null; then
        error "Docker Compose is not installed"
        exit 1
    fi
    
    # Check if Docker daemon is running
    if ! docker info &> /dev/null; then
        error "Docker daemon is not running"
        exit 1
    fi
    
    success "Prerequisites check passed"
}

# Build images
build_images() {
    local compose_file="$(get_compose_file)"
    log "Building images for $ENVIRONMENT environment..."
    
    cd "$PROJECT_ROOT"
    docker-compose -f "$compose_file" build
    
    success "Images built successfully"
}

# Start services
start_services() {
    local compose_file="$(get_compose_file)"
    log "Starting services for $ENVIRONMENT environment..."
    
    cd "$PROJECT_ROOT"
    docker-compose -f "$compose_file" up -d
    
    # Wait for services to be healthy
    log "Waiting for services to be healthy..."
    sleep 30
    
    # Check service health
    check_health
    
    success "Services started successfully"
}

# Stop services
stop_services() {
    local compose_file="$(get_compose_file)"
    log "Stopping services for $ENVIRONMENT environment..."
    
    cd "$PROJECT_ROOT"
    docker-compose -f "$compose_file" down
    
    success "Services stopped successfully"
}

# Restart services
restart_services() {
    log "Restarting services for $ENVIRONMENT environment..."
    stop_services
    start_services
}

# Show logs
show_logs() {
    local compose_file="$(get_compose_file)"
    local service=${3:-}
    
    cd "$PROJECT_ROOT"
    
    if [[ -n "$service" ]]; then
        log "Showing logs for service: $service"
        docker-compose -f "$compose_file" logs -f "$service"
    else
        log "Showing logs for all services"
        docker-compose -f "$compose_file" logs -f
    fi
}

# Show status
show_status() {
    local compose_file="$(get_compose_file)"
    log "Service status for $ENVIRONMENT environment:"
    
    cd "$PROJECT_ROOT"
    docker-compose -f "$compose_file" ps
}

# Check health
check_health() {
    log "Checking service health..."
    
    # Define health check URLs based on environment
    case $ENVIRONMENT in
        dev)
            BACKEND_URL="http://localhost:8001"
            FRONTEND_URL="http://localhost:3001"
            ;;
        staging)
            BACKEND_URL="http://localhost:8002"
            FRONTEND_URL="http://localhost:3002"
            ;;
        prod)
            BACKEND_URL="http://localhost:8000"
            FRONTEND_URL="http://localhost:80"
            ;;
    esac
    
    # Check backend health
    if curl -f -s "$BACKEND_URL/health" > /dev/null; then
        success "Backend is healthy"
    else
        warning "Backend health check failed"
    fi
    
    # Check frontend health
    if curl -f -s "$FRONTEND_URL/health" > /dev/null; then
        success "Frontend is healthy"
    else
        warning "Frontend health check failed"
    fi
}

# Clean up
cleanup() {
    local compose_file="$(get_compose_file)"
    log "Cleaning up containers and volumes for $ENVIRONMENT environment..."
    
    cd "$PROJECT_ROOT"
    docker-compose -f "$compose_file" down -v --remove-orphans
    
    # Remove unused images
    docker image prune -f
    
    success "Cleanup completed"
}

# Create backup
create_backup() {
    log "Creating database backup for $ENVIRONMENT environment..."
    
    local backup_dir="$PROJECT_ROOT/backups"
    local timestamp=$(date +"%Y%m%d_%H%M%S")
    local backup_file="$backup_dir/backup_${ENVIRONMENT}_${timestamp}.sql"
    
    mkdir -p "$backup_dir"
    
    # Get database connection details based on environment
    case $ENVIRONMENT in
        dev)
            DB_HOST="localhost"
            DB_PORT="5433"
            ;;
        staging)
            DB_HOST="localhost"
            DB_PORT="5434"
            ;;
        prod)
            DB_HOST="localhost"
            DB_PORT="5432"
            ;;
    esac
    
    # Create backup using pg_dump
    if docker exec tv-postgres-${ENVIRONMENT} pg_dump -U stocksblitz -h localhost stocksblitz_unified > "$backup_file"; then
        success "Backup created: $backup_file"
    else
        error "Backup failed"
        exit 1
    fi
}

# Deploy (full deployment)
deploy() {
    log "Starting full deployment for $ENVIRONMENT environment..."
    
    # Create backup for production
    if [[ "$ENVIRONMENT" == "prod" ]]; then
        create_backup
    fi
    
    # Build and start services
    build_images
    start_services
    
    # Run health checks
    sleep 30
    check_health
    
    success "Deployment completed successfully"
}

# Main execution
main() {
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        "")
            show_help
            exit 1
            ;;
    esac
    
    validate_environment
    load_env
    check_prerequisites
    
    case $ACTION in
        start)
            start_services
            ;;
        stop)
            stop_services
            ;;
        restart)
            restart_services
            ;;
        deploy)
            deploy
            ;;
        logs)
            show_logs "$@"
            ;;
        status)
            show_status
            ;;
        clean)
            cleanup
            ;;
        backup)
            create_backup
            ;;
        health)
            check_health
            ;;
        *)
            error "Invalid action: $ACTION"
            show_help
            exit 1
            ;;
    esac
}

# Run main function with all arguments
main "$@"