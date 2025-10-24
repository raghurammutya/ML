#!/bin/bash

# Critical Database Tables Backup Script
# Backs up ml_labeled_data, nifty50_ohlc, nifty_fo_ohlc tables every hour
# Maintains rotation: keeps current + 1 previous backup

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"

# Load environment variables
if [[ -f "$PROJECT_ROOT/.env.prod" ]]; then
    export $(cat "$PROJECT_ROOT/.env.prod" | grep -v '^#' | xargs)
fi

# Configuration
BACKUP_DIR="/opt/tradingview-db-backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
HOUR_MARKER=$(date +%H)
BACKUP_LOG="/var/log/tradingview-db-backup.log"

# Critical tables to backup
CRITICAL_TABLES=(
    "ml_labeled_data"
    "nifty50_ohlc"
    "nifty_fo_ohlc"
)

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a "$BACKUP_LOG"
}

warn() {
    echo -e "${YELLOW}[$(date '+%Y-%m-%d %H:%M:%S')] WARNING:${NC} $1" | tee -a "$BACKUP_LOG"
}

error() {
    echo -e "${RED}[$(date '+%Y-%m-%d %H:%M:%S')] ERROR:${NC} $1" | tee -a "$BACKUP_LOG"
}

info() {
    echo -e "${BLUE}[$(date '+%Y-%m-%d %H:%M:%S')] INFO:${NC} $1" | tee -a "$BACKUP_LOG"
}

# Parse database URL
parse_db_config() {
    if [[ -z "$DATABASE_URL" ]]; then
        error "DATABASE_URL not found in environment"
        exit 1
    fi
    
    # Parse postgres://user:password@host:port/database
    if [[ $DATABASE_URL =~ postgresql://([^:]+):([^@]+)@([^:]+):([^/]+)/(.+) ]]; then
        DB_USER="${BASH_REMATCH[1]}"
        DB_PASSWORD="${BASH_REMATCH[2]}"
        DB_HOST="${BASH_REMATCH[3]}"
        DB_PORT="${BASH_REMATCH[4]}"
        DB_NAME="${BASH_REMATCH[5]}"
    else
        error "Invalid DATABASE_URL format"
        exit 1
    fi
    
    log "Database config parsed: $DB_USER@$DB_HOST:$DB_PORT/$DB_NAME"
}

# Create backup directory structure
setup_backup_directory() {
    mkdir -p "$BACKUP_DIR"
    mkdir -p "$BACKUP_DIR/current"
    mkdir -p "$BACKUP_DIR/previous"
    mkdir -p "$BACKUP_DIR/metadata"
    
    # Set appropriate permissions
    chmod 750 "$BACKUP_DIR"
    
    log "Backup directory structure created: $BACKUP_DIR"
}

# Test database connection
test_database_connection() {
    log "Testing database connection..."
    
    export PGPASSWORD="$DB_PASSWORD"
    
    if psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c "SELECT version();" > /dev/null 2>&1; then
        log "✓ Database connection successful"
    else
        error "Database connection failed"
        exit 1
    fi
}

# Get table statistics
get_table_stats() {
    local table="$1"
    export PGPASSWORD="$DB_PASSWORD"
    
    local stats=$(psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -t -c "
        SELECT 
            COALESCE(n_live_tup, 0) as live_rows,
            COALESCE(pg_total_relation_size('$table'), 0) as size_bytes
        FROM pg_stat_user_tables 
        WHERE tablename = '$table';
    " 2>/dev/null | tr -d ' ')
    
    if [[ -n "$stats" ]]; then
        echo "$stats"
    else
        echo "0,0"
    fi
}

# Backup single table
backup_table() {
    local table="$1"
    local backup_path="$2"
    
    log "Backing up table: $table"
    
    export PGPASSWORD="$DB_PASSWORD"
    
    # Get table stats before backup
    local stats=$(get_table_stats "$table")
    local row_count=$(echo "$stats" | cut -d',' -f1)
    
    # Create table backup
    local table_backup_file="$backup_path/${table}_${TIMESTAMP}.sql"
    
    if pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
        --table="$table" \
        --data-only \
        --column-inserts \
        --no-owner \
        --no-privileges \
        --compress=9 \
        -f "$table_backup_file" 2>/dev/null; then
        
        # Create metadata file
        cat > "$backup_path/${table}_${TIMESTAMP}.meta" << EOF
table_name=$table
backup_timestamp=$TIMESTAMP
backup_date=$(date -u +%Y-%m-%dT%H:%M:%SZ)
row_count=$row_count
backup_size=$(stat -c%s "$table_backup_file" 2>/dev/null || echo "0")
backup_type=hourly
database=$DB_NAME
host=$DB_HOST
EOF
        
        log "✓ Table $table backed up successfully ($row_count rows)"
        echo "$table_backup_file"
    else
        error "Failed to backup table: $table"
        return 1
    fi
}

# Rotate backups (keep current + 1 previous)
rotate_backups() {
    log "Rotating backups..."
    
    # Move current to previous
    if [[ -d "$BACKUP_DIR/current" ]] && [[ "$(ls -A $BACKUP_DIR/current)" ]]; then
        rm -rf "$BACKUP_DIR/previous"/*
        mv "$BACKUP_DIR/current"/* "$BACKUP_DIR/previous/"
        log "Moved current backups to previous"
    fi
    
    # Clean current directory for new backups
    rm -rf "$BACKUP_DIR/current"/*
    
    log "Backup rotation completed"
}

# Main backup function
main() {
    local start_time=$(date +%s)
    
    log "=== Starting Critical Database Backup ==="
    log "Timestamp: $TIMESTAMP"
    log "Tables: ${CRITICAL_TABLES[*]}"
    
    # Setup
    parse_db_config
    setup_backup_directory
    test_database_connection
    
    # Rotate previous backups
    rotate_backups
    
    # Perform backups
    local backup_path="$BACKUP_DIR/current"
    local success_count=0
    
    for table in "${CRITICAL_TABLES[@]}"; do
        if backup_table "$table" "$backup_path"; then
            ((success_count++))
        fi
    done
    
    # Create summary
    cat > "$backup_path/backup_summary_${TIMESTAMP}.txt" << EOF
=== TradingView Database Backup Summary ===
Backup Date: $(date -u +%Y-%m-%dT%H:%M:%SZ)
Backup Type: Hourly Critical Tables
Database: $DB_NAME
Success Count: $success_count/${#CRITICAL_TABLES[@]}
EOF
    
    if [[ $success_count -eq ${#CRITICAL_TABLES[@]} ]]; then
        log "=== Backup Completed Successfully ==="
        log "All $success_count critical tables backed up"
        log "Backup location: $backup_path"
    else
        error "=== Backup Completed with Errors ==="
        error "Only $success_count/${#CRITICAL_TABLES[@]} tables backed up successfully"
        exit 1
    fi
}

# Handle script arguments
case "${1:-}" in
    --test)
        log "Testing database connection and configuration..."
        parse_db_config
        test_database_connection
        log "Test completed successfully"
        ;;
    --status)
        echo "=== Backup Status ==="
        ls -la "$BACKUP_DIR/current/" 2>/dev/null || echo "No current backups"
        echo ""
        ls -la "$BACKUP_DIR/previous/" 2>/dev/null || echo "No previous backups"
        ;;
    *)
        main "$@"
        ;;
esac