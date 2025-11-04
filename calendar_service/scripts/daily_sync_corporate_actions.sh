#!/bin/bash
#
# Daily Corporate Actions Sync Script
# Runs before market open (8:30 AM IST) to fetch latest corporate actions from NSE
#
# This script performs UPSERT operations:
# - Keeps old/historical records intact
# - Updates existing records if data changed
# - Adds new corporate actions
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="/var/log/corporate-actions"
LOG_FILE="$LOG_DIR/sync_$(date +%Y%m%d).log"

# Create log directory if it doesn't exist
mkdir -p "$LOG_DIR"

# Log function
log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "=========================================="
log "Starting daily corporate actions sync"
log "=========================================="

# Check if running inside Docker container
if [ -f /.dockerenv ]; then
    # Running inside container
    log "Running inside Docker container"
    cd /app
    python3 scripts/fetch_real_corporate_actions.py >> "$LOG_FILE" 2>&1
else
    # Running on host - execute via docker
    log "Running on host - executing via Docker"

    # Find the backend container
    CONTAINER_NAME="tv-backend"

    if ! docker ps | grep -q "$CONTAINER_NAME"; then
        log "ERROR: Backend container '$CONTAINER_NAME' is not running"
        exit 1
    fi

    log "Executing sync in container: $CONTAINER_NAME"
    docker exec "$CONTAINER_NAME" python3 /app/scripts/fetch_real_corporate_actions.py >> "$LOG_FILE" 2>&1
fi

EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    log "✓ Corporate actions sync completed successfully"

    # Cleanup old log files (keep last 30 days)
    find "$LOG_DIR" -name "sync_*.log" -type f -mtime +30 -delete 2>/dev/null || true
else
    log "✗ Corporate actions sync failed with exit code: $EXIT_CODE"
    exit $EXIT_CODE
fi

log "=========================================="
log "Sync completed at $(date +'%Y-%m-%d %H:%M:%S')"
log "=========================================="
