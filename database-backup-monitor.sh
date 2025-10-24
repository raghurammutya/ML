#!/bin/bash

# Database Backup Monitoring Script
# Monitors backup health and sends alerts when issues are detected

set -e

BACKUP_DIR="/opt/tradingview-db-backups"
ALERT_LOG="/var/log/tradingview-backup-alerts.log"
STATUS_FILE="/tmp/backup-monitor-status.json"
MAX_BACKUP_AGE_HOURS=2  # Alert if backup is older than 2 hours

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_alert() {
    echo -e "${RED}[$(date '+%Y-%m-%d %H:%M:%S')] BACKUP ALERT:${NC} $1" | tee -a "$ALERT_LOG"
}

log_info() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a "$ALERT_LOG"
}

warn() {
    echo -e "${YELLOW}[$(date '+%Y-%m-%d %H:%M:%S')] WARNING:${NC} $1" | tee -a "$ALERT_LOG"
}

# Check if backup directories exist
check_backup_directories() {
    local issues=0
    
    if [[ ! -d "$BACKUP_DIR" ]]; then
        log_alert "Backup directory missing: $BACKUP_DIR"
        ((issues++))
    fi
    
    if [[ ! -d "$BACKUP_DIR/current" ]]; then
        log_alert "Current backup directory missing: $BACKUP_DIR/current"
        ((issues++))
    fi
    
    if [[ ! -d "$BACKUP_DIR/metadata" ]]; then
        warn "Metadata directory missing: $BACKUP_DIR/metadata"
    fi
    
    return $issues
}

# Check backup freshness
check_backup_freshness() {
    local issues=0
    local current_time=$(date +%s)
    local max_age_seconds=$((MAX_BACKUP_AGE_HOURS * 3600))
    
    # Check current backups
    if [[ -d "$BACKUP_DIR/current" ]]; then
        local latest_backup=""
        local latest_time=0
        
        # Find the most recent backup
        for file in "$BACKUP_DIR/current"/*.sql; do
            if [[ -f "$file" ]]; then
                local file_time=$(stat -c %Y "$file" 2>/dev/null || echo 0)
                if [[ $file_time -gt $latest_time ]]; then
                    latest_time=$file_time
                    latest_backup="$file"
                fi
            fi
        done
        
        if [[ -n "$latest_backup" ]]; then
            local age_seconds=$((current_time - latest_time))
            local age_hours=$((age_seconds / 3600))
            
            if [[ $age_seconds -gt $max_age_seconds ]]; then
                log_alert "Latest backup is $age_hours hours old (threshold: $MAX_BACKUP_AGE_HOURS hours)"
                log_alert "Latest backup: $latest_backup"
                ((issues++))
            else
                log_info "Latest backup is $age_hours hours old (within threshold)"
            fi
        else
            log_alert "No backup files found in current directory"
            ((issues++))
        fi
    else
        log_alert "Current backup directory does not exist"
        ((issues++))
    fi
    
    return $issues
}

# Check backup completeness
check_backup_completeness() {
    local issues=0
    local expected_tables=("ml_labeled_data" "nifty50_ohlc" "nifty_fo_ohlc")
    
    if [[ -d "$BACKUP_DIR/current" ]]; then
        # Get the latest timestamp
        local latest_timestamp=""
        for file in "$BACKUP_DIR/current"/*.meta; do
            if [[ -f "$file" ]]; then
                local timestamp=$(basename "$file" .meta | cut -d'_' -f3-)
                if [[ "$timestamp" > "$latest_timestamp" ]]; then
                    latest_timestamp="$timestamp"
                fi
            fi
        done
        
        if [[ -n "$latest_timestamp" ]]; then
            log_info "Checking completeness for backup: $latest_timestamp"
            
            for table in "${expected_tables[@]}"; do
                local sql_file="$BACKUP_DIR/current/${table}_${latest_timestamp}.sql"
                local meta_file="$BACKUP_DIR/current/${table}_${latest_timestamp}.meta"
                
                if [[ -f "$sql_file" && -f "$meta_file" ]]; then
                    # Check if SQL file has content
                    if [[ -s "$sql_file" ]]; then
                        log_info "✓ $table backup complete"
                    else
                        log_alert "✗ $table backup file is empty"
                        ((issues++))
                    fi
                else
                    log_alert "✗ $table backup missing (SQL: $(test -f "$sql_file" && echo "✓" || echo "✗"), Meta: $(test -f "$meta_file" && echo "✓" || echo "✗"))"
                    ((issues++))
                fi
            done
        else
            warn "No backup timestamp found for completeness check"
        fi
    fi
    
    return $issues
}

# Check disk space
check_disk_space() {
    local issues=0
    local usage=$(df "$BACKUP_DIR" | tail -1 | awk '{print $5}' | sed 's/%//')
    
    if [[ $usage -gt 90 ]]; then
        log_alert "Backup disk usage critical: ${usage}%"
        ((issues++))
    elif [[ $usage -gt 80 ]]; then
        warn "Backup disk usage high: ${usage}%"
    else
        log_info "Backup disk usage normal: ${usage}%"
    fi
    
    return $issues
}

# Check backup process health
check_backup_process() {
    local issues=0
    
    # Check if backup cron job exists
    if crontab -l 2>/dev/null | grep -q "database-backup.sh"; then
        log_info "✓ Backup cron job is configured"
    else
        warn "Backup cron job not found in crontab"
    fi
    
    # Check backup log for recent errors
    if [[ -f "/var/log/tradingview-db-backup.log" ]]; then
        local recent_errors=$(tail -50 /var/log/tradingview-db-backup.log | grep -i error | wc -l)
        if [[ $recent_errors -gt 0 ]]; then
            log_alert "Found $recent_errors recent errors in backup log"
            ((issues++))
        else
            log_info "✓ No recent errors in backup log"
        fi
    else
        warn "Backup log file not found"
    fi
    
    return $issues
}

# Generate backup status report
generate_status_report() {
    local total_issues="$1"
    local status="healthy"
    
    if [[ $total_issues -gt 0 ]]; then
        status="issues_detected"
    fi
    
    # Count backups
    local current_backups=0
    local previous_backups=0
    
    if [[ -d "$BACKUP_DIR/current" ]]; then
        current_backups=$(ls -1 "$BACKUP_DIR/current"/*.sql 2>/dev/null | wc -l)
    fi
    
    if [[ -d "$BACKUP_DIR/previous" ]]; then
        previous_backups=$(ls -1 "$BACKUP_DIR/previous"/*.sql 2>/dev/null | wc -l)
    fi
    
    # Get latest backup info
    local latest_backup_time=""
    local latest_backup_size=0
    
    if [[ -d "$BACKUP_DIR/current" ]]; then
        for file in "$BACKUP_DIR/current"/*.sql; do
            if [[ -f "$file" ]]; then
                local file_time=$(stat -c %Y "$file" 2>/dev/null || echo 0)
                local file_size=$(stat -c %s "$file" 2>/dev/null || echo 0)
                latest_backup_time=$(date -d "@$file_time" -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo "unknown")
                latest_backup_size=$((latest_backup_size + file_size))
                break
            fi
        done
    fi
    
    # Create JSON status
    cat > "$STATUS_FILE" << EOF
{
    "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "status": "$status",
    "issues_count": $total_issues,
    "backup_counts": {
        "current": $current_backups,
        "previous": $previous_backups
    },
    "latest_backup": {
        "time": "$latest_backup_time",
        "size_bytes": $latest_backup_size,
        "size_mb": $((latest_backup_size / 1024 / 1024))
    },
    "disk_usage": "$(df "$BACKUP_DIR" | tail -1 | awk '{print $5}' || echo "unknown")",
    "next_check": "$(date -d '+1 hour' -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF
    
    log_info "Status report generated: $STATUS_FILE"
}

# Send notifications (placeholder for integration with external systems)
send_notifications() {
    local total_issues="$1"
    
    if [[ $total_issues -gt 0 ]]; then
        # Create notification payload for external systems
        cat > "/tmp/backup-alert-notification.json" << EOF
{
    "alert_type": "database_backup_issues",
    "severity": "$(if [[ $total_issues -gt 2 ]]; then echo "high"; else echo "medium"; fi)",
    "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "issues_count": $total_issues,
    "message": "Database backup monitoring detected $total_issues issues",
    "details": "Check $ALERT_LOG for detailed information"
}
EOF
        
        log_alert "Notification payload created: /tmp/backup-alert-notification.json"
        
        # Future: Add email/Slack/webhook notifications here
        # Example: curl -X POST -H "Content-Type: application/json" -d @/tmp/backup-alert-notification.json "$WEBHOOK_URL"
    fi
}

# Main monitoring function
main() {
    log_info "=== Database Backup Monitoring Started ==="
    
    local total_issues=0
    
    # Run all checks
    check_backup_directories || ((total_issues += $?))
    check_backup_freshness || ((total_issues += $?))
    check_backup_completeness || ((total_issues += $?))
    check_disk_space || ((total_issues += $?))
    check_backup_process || ((total_issues += $?))
    
    # Generate status and notifications
    generate_status_report "$total_issues"
    send_notifications "$total_issues"
    
    if [[ $total_issues -eq 0 ]]; then
        log_info "=== Backup Monitoring: All checks passed ✓ ==="
    else
        log_alert "=== Backup Monitoring: $total_issues issues detected ✗ ==="
    fi
    
    log_info "=== Database Backup Monitoring Completed ==="
    
    return $total_issues
}

# Handle script arguments
case "${1:-}" in
    --status)
        if [[ -f "$STATUS_FILE" ]]; then
            cat "$STATUS_FILE"
        else
            echo '{"status": "no_data", "message": "No monitoring data available"}'
        fi
        ;;
    --alerts)
        if [[ -f "$ALERT_LOG" ]]; then
            tail -20 "$ALERT_LOG"
        else
            echo "No alerts logged yet"
        fi
        ;;
    --force-check)
        main
        ;;
    *)
        main
        ;;
esac