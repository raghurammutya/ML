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
