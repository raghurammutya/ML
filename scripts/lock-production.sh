#!/bin/bash

# Production Environment Lock Script
# This script secures the production environment against unauthorized changes

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
LOCK_FILE="/tmp/tradingview-production.lock"
PROTECTION_LOG="/var/log/tradingview-protection.log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a "$PROTECTION_LOG"
}

warn() {
    echo -e "${YELLOW}[$(date '+%Y-%m-%d %H:%M:%S')] WARNING:${NC} $1" | tee -a "$PROTECTION_LOG"
}

error() {
    echo -e "${RED}[$(date '+%Y-%m-%d %H:%M:%S')] ERROR:${NC} $1" | tee -a "$PROTECTION_LOG"
}

info() {
    echo -e "${BLUE}[$(date '+%Y-%m-%d %H:%M:%S')] INFO:${NC} $1" | tee -a "$PROTECTION_LOG"
}

# Check if running as root or with sudo
check_permissions() {
    if [[ $EUID -ne 0 ]]; then
        error "This script must be run as root or with sudo privileges"
        exit 1
    fi
}

# Create protection lock
create_lock() {
    if [[ -f "$LOCK_FILE" ]]; then
        warn "Production environment is already locked"
        return 0
    fi
    
    echo "PRODUCTION_LOCKED=true" > "$LOCK_FILE"
    echo "LOCKED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$LOCK_FILE"
    echo "LOCKED_BY=$(whoami)" >> "$LOCK_FILE"
    echo "PROJECT_PATH=$PROJECT_ROOT" >> "$LOCK_FILE"
    
    chmod 444 "$LOCK_FILE"
    log "Production lock file created: $LOCK_FILE"
}

# Set critical files to read-only
protect_critical_files() {
    log "Setting critical files to read-only..."
    
    # Critical configuration files
    local critical_files=(
        ".env.prod"
        "docker-compose.unified.yml" 
        "deployment/nginx.conf.template"
        "deployment/Dockerfile.frontend.unified"
        "backend/Dockerfile"
        "backend/requirements.txt"
        "backend/app/config.py"
        "backend/app/database.py"
        "backend/app/main.py"
        "frontend/package.json"
        "frontend/package-lock.json"
        "frontend/src/App.tsx"
        "frontend/src/components/CustomChartWithMLLabels.tsx"
    )
    
    for file in "${critical_files[@]}"; do
        local filepath="$PROJECT_ROOT/$file"
        if [[ -f "$filepath" ]]; then
            # Backup original permissions
            stat -c "%a" "$filepath" > "${filepath}.original_perms"
            # Set to read-only
            chmod 444 "$filepath"
            log "Protected: $file (read-only)"
        else
            warn "File not found: $file"
        fi
    done
}

# Protect directories
protect_directories() {
    log "Protecting critical directories..."
    
    local critical_dirs=(
        "backend/app"
        "frontend/src"
        "deployment"
        "scripts"
    )
    
    for dir in "${critical_dirs[@]}"; do
        local dirpath="$PROJECT_ROOT/$dir"
        if [[ -d "$dirpath" ]]; then
            # Backup original permissions
            stat -c "%a" "$dirpath" > "${dirpath}.original_perms"
            # Set to read and execute only (no write)
            chmod 555 "$dirpath"
            log "Protected directory: $dir (read/execute only)"
        else
            warn "Directory not found: $dir"
        fi
    done
}

# Create file integrity checksums
create_integrity_checksums() {
    log "Creating file integrity checksums..."
    
    local checksum_file="$PROJECT_ROOT/.production_checksums"
    
    # Generate checksums for all critical files
    find "$PROJECT_ROOT" -type f \( \
        -name "*.py" -o \
        -name "*.tsx" -o \
        -name "*.ts" -o \
        -name "*.js" -o \
        -name "*.json" -o \
        -name "*.yml" -o \
        -name "*.yaml" -o \
        -name "*.conf" -o \
        -name "Dockerfile*" -o \
        -name "*.sh" \
    \) -not -path "*/node_modules/*" -not -path "*/__pycache__/*" \
    | xargs sha256sum > "$checksum_file"
    
    chmod 444 "$checksum_file"
    log "Integrity checksums created: $checksum_file"
}

# Create deployment validation script
create_deployment_validator() {
    log "Creating deployment validation script..."
    
    cat > "$PROJECT_ROOT/scripts/validate-deployment.sh" << 'EOF'
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
EOF
    
    chmod +x "$PROJECT_ROOT/scripts/validate-deployment.sh"
    log "Deployment validator created: scripts/validate-deployment.sh"
}

# Create backup mechanism
create_backup_system() {
    log "Creating backup system..."
    
    local backup_dir="/opt/tradingview-backups"
    local timestamp=$(date +%Y%m%d_%H%M%S)
    local backup_path="$backup_dir/production_$timestamp"
    
    mkdir -p "$backup_dir"
    
    # Create full backup
    cp -r "$PROJECT_ROOT" "$backup_path"
    
    # Create backup metadata
    cat > "$backup_path/backup_info.txt" << EOF
Backup created: $(date -u +%Y-%m-%dT%H:%M:%SZ)
Source path: $PROJECT_ROOT
Backup type: Production lock backup
Git commit: $(cd "$PROJECT_ROOT" && git rev-parse HEAD 2>/dev/null || echo "N/A")
Environment: production
EOF
    
    # Keep only last 10 backups
    ls -t "$backup_dir" | tail -n +11 | xargs -r -I {} rm -rf "$backup_dir/{}"
    
    log "Backup created: $backup_path"
}

# Create monitoring script
create_monitoring_script() {
    log "Creating monitoring script..."
    
    cat > "$PROJECT_ROOT/scripts/monitor-production.sh" << 'EOF'
#!/bin/bash

# Production Monitoring Script
# Continuously monitors production environment for unauthorized changes

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCK_FILE="/tmp/tradingview-production.lock"
CHECKSUM_FILE="$PROJECT_ROOT/.production_checksums"
ALERT_LOG="/var/log/tradingview-security-alerts.log"

alert() {
    local message="$1"
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] SECURITY ALERT: $message" | tee -a "$ALERT_LOG"
    # You can add email/Slack notifications here
}

check_lock_integrity() {
    if [[ ! -f "$LOCK_FILE" ]]; then
        alert "Production lock file is missing!"
        return 1
    fi
    
    if [[ ! -r "$LOCK_FILE" ]]; then
        alert "Production lock file permissions have been altered!"
        return 1
    fi
}

check_file_integrity() {
    if [[ ! -f "$CHECKSUM_FILE" ]]; then
        alert "Integrity checksum file is missing!"
        return 1
    fi
    
    if ! sha256sum -c "$CHECKSUM_FILE" --quiet 2>/dev/null; then
        alert "File integrity check failed - unauthorized changes detected!"
        
        # Show which files changed
        sha256sum -c "$CHECKSUM_FILE" 2>&1 | grep FAILED | tee -a "$ALERT_LOG"
        return 1
    fi
}

monitor_loop() {
    while true; do
        check_lock_integrity
        check_file_integrity
        sleep 300  # Check every 5 minutes
    done
}

if [[ "${1:-}" == "--daemon" ]]; then
    echo "Starting production monitoring daemon..."
    monitor_loop
else
    echo "Running one-time production integrity check..."
    check_lock_integrity && check_file_integrity
    echo "Production integrity check completed"
fi
EOF
    
    chmod +x "$PROJECT_ROOT/scripts/monitor-production.sh"
    log "Monitoring script created: scripts/monitor-production.sh"
}

# Create unlock script (for authorized maintenance)
create_unlock_script() {
    log "Creating authorized unlock script..."
    
    cat > "$PROJECT_ROOT/scripts/unlock-production.sh" << 'EOF'
#!/bin/bash

# Production Unlock Script (For Authorized Maintenance Only)
# This script temporarily unlocks production for authorized changes

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCK_FILE="/tmp/tradingview-production.lock"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

if [[ $EUID -ne 0 ]]; then
    echo -e "${RED}ERROR:${NC} This script must be run as root or with sudo"
    exit 1
fi

echo -e "${YELLOW}WARNING:${NC} This will unlock production environment for maintenance"
echo "This should only be done for authorized deployments or emergency fixes"
echo ""
read -p "Enter maintenance reason: " reason
read -p "Enter your name/ID: " maintainer
read -p "Are you sure you want to unlock production? (yes/no): " confirm

if [[ "$confirm" != "yes" ]]; then
    echo "Unlock cancelled"
    exit 0
fi

# Log the unlock
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] PRODUCTION UNLOCKED by $maintainer: $reason" >> /var/log/tradingview-maintenance.log

# Remove lock
rm -f "$LOCK_FILE"

# Restore file permissions
find "$PROJECT_ROOT" -name "*.original_perms" | while read perm_file; do
    original_file="${perm_file%.original_perms}"
    if [[ -f "$original_file" && -f "$perm_file" ]]; then
        chmod "$(cat "$perm_file")" "$original_file"
        rm "$perm_file"
    fi
done

echo -e "${GREEN}Production environment unlocked${NC}"
echo -e "${YELLOW}Remember to re-lock after maintenance with: sudo ./scripts/lock-production.sh${NC}"
EOF
    
    chmod 700 "$PROJECT_ROOT/scripts/unlock-production.sh"  # Only root can execute
    log "Unlock script created: scripts/unlock-production.sh (root only)"
}

# Main function
main() {
    log "=== Starting Production Environment Lock ==="
    
    check_permissions
    
    # Create backup before locking
    create_backup_system
    
    # Lock the environment
    create_lock
    protect_critical_files
    protect_directories
    create_integrity_checksums
    
    # Create management scripts
    create_deployment_validator
    create_monitoring_script
    create_unlock_script
    
    log "=== Production Environment Successfully Locked ==="
    echo ""
    info "Production environment is now protected against unauthorized changes"
    info "Use the following scripts for management:"
    echo "  - Validate deployment: ./scripts/validate-deployment.sh"
    echo "  - Monitor integrity:   ./scripts/monitor-production.sh"
    echo "  - Unlock (emergency):  sudo ./scripts/unlock-production.sh"
    echo ""
    warn "Keep backups safe and only unlock for authorized maintenance"
}

# Run main function
main "$@"