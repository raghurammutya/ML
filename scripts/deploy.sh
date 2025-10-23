#!/bin/bash

# TradingView ML Visualization Deployment Script
# Usage: ./deploy.sh [environment] [action]

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$(dirname "$SCRIPT_DIR")" && pwd)"
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
    dev         Development environment (ports 3001, 8001)
    staging     Staging environment (ports 3002, 8002)
    prod        Production environment (ports 8081, 8080)

ACTIONS:
    start       Start services (default)
    stop        Stop services
    restart     Restart services
    status      Show service status
    logs        Show service logs
    clean       Clean up containers and volumes

External URLs:
    Current:    http://5.223.52.98:3000 (existing system)
    Dev:        http://5.223.52.98:3001
    Staging:    http://5.223.52.98:3002
    Production: http://5.223.52.98:8081

EOF
}

# Validate environment
validate_environment() {
    case $ENVIRONMENT in
        dev|staging|prod)
            log "Working with $ENVIRONMENT environment"
            ;;
        *)
            error "Invalid environment: $ENVIRONMENT"
            error "Valid environments: dev, staging, prod"
            exit 1
            ;;
    esac
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
    
    if ! command -v docker &> /dev/null; then
        error "Docker is not installed"
        exit 1
    fi
    
    if ! command -v docker-compose &> /dev/null; then
        error "Docker Compose is not installed"
        exit 1
    fi
    
    if ! docker info &> /dev/null; then
        error "Docker daemon is not running"
        exit 1
    fi
    
    success "Prerequisites check passed"
}

# Start services
start_services() {
    local compose_file="$(get_compose_file)"
    log "Starting services for $ENVIRONMENT environment..."
    
    cd "$PROJECT_ROOT"
    docker-compose -f "$compose_file" up -d --build
    
    log "Waiting for services to start..."
    sleep 30
    
    # Show URLs
    case $ENVIRONMENT in
        dev)
            success "Development environment started!"
            success "Frontend: http://5.223.52.98:3001"
            success "Backend:  http://5.223.52.98:8001"
            ;;
        staging)
            success "Staging environment started!"
            success "Frontend: http://5.223.52.98:3002"
            success "Backend:  http://5.223.52.98:8002"
            ;;
        prod)
            success "Production environment started!"
            success "Frontend: http://5.223.52.98:8081"
            success "Backend:  http://5.223.52.98:8080"
            ;;
    esac
}

# Stop services
stop_services() {
    local compose_file="$(get_compose_file)"
    log "Stopping services for $ENVIRONMENT environment..."
    
    cd "$PROJECT_ROOT"
    docker-compose -f "$compose_file" down
    
    success "Services stopped successfully"
}

# Show status
show_status() {
    local compose_file="$(get_compose_file)"
    log "Service status for $ENVIRONMENT environment:"
    
    cd "$PROJECT_ROOT"
    docker-compose -f "$compose_file" ps
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

# Clean up
cleanup() {
    local compose_file="$(get_compose_file)"
    log "Cleaning up containers and volumes for $ENVIRONMENT environment..."
    
    cd "$PROJECT_ROOT"
    docker-compose -f "$compose_file" down -v --remove-orphans
    
    success "Cleanup completed"
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
    check_prerequisites
    
    case $ACTION in
        start)
            start_services
            ;;
        stop)
            stop_services
            ;;
        restart)
            stop_services
            start_services
            ;;
        status)
            show_status
            ;;
        logs)
            show_logs "$@"
            ;;
        clean)
            cleanup
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