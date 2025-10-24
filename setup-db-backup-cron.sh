#!/bin/bash

# Setup Database Backup Cron Job
# Creates hourly backup schedule for critical database tables

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_SCRIPT="$PROJECT_ROOT/database-backup.sh"

if [[ $EUID -ne 0 ]]; then
    echo "This script must be run as root or with sudo"
    exit 1
fi

# Ensure backup script exists and is executable
if [[ ! -x "$BACKUP_SCRIPT" ]]; then
    echo "ERROR: Database backup script not found or not executable: $BACKUP_SCRIPT"
    exit 1
fi

# Create log directory
mkdir -p /var/log
touch /var/log/tradingview-db-backup.log
chown stocksadmin:stocksadmin /var/log/tradingview-db-backup.log

# Test backup script
echo "Testing database backup script..."
if sudo -u stocksadmin "$BACKUP_SCRIPT" --test; then
    echo "✓ Database backup script test passed"
else
    echo "✗ Database backup script test failed"
    exit 1
fi

# Create cron job
CRON_JOB="0 * * * * /bin/bash $BACKUP_SCRIPT >> /var/log/tradingview-db-backup.log 2>&1"

# Add to stocksadmin user's crontab
(sudo -u stocksadmin crontab -l 2>/dev/null | grep -v "$BACKUP_SCRIPT"; echo "$CRON_JOB") | sudo -u stocksadmin crontab -

echo "✓ Hourly database backup cron job created"
echo "Backup schedule: Every hour at minute 0"
echo "Log file: /var/log/tradingview-db-backup.log"
echo ""
echo "To view current cron jobs: sudo -u stocksadmin crontab -l"
echo "To check backup status: $BACKUP_SCRIPT --status"
echo "To test backup: $BACKUP_SCRIPT --test"