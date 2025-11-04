#!/bin/bash
#
# Setup Daily Corporate Actions Sync
#
# This script sets up automated daily sync using systemd timer
# Runs at 8:30 AM IST every day (before market open at 9:15 AM)
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYNC_SCRIPT="$SCRIPT_DIR/daily_sync_corporate_actions.sh"

echo "=========================================="
echo "Corporate Actions Daily Sync Setup"
echo "=========================================="
echo ""

# Make sync script executable
chmod +x "$SYNC_SCRIPT"
echo "✓ Made sync script executable"

# Check if we should use systemd or cron
if command -v systemctl &> /dev/null; then
    echo ""
    echo "Setting up systemd timer..."
    echo ""

    # Create systemd service
    SERVICE_FILE="/etc/systemd/system/corporate-actions-sync.service"
    sudo tee "$SERVICE_FILE" > /dev/null <<EOF
[Unit]
Description=Daily Corporate Actions Sync from NSE/BSE
After=network.target docker.service
Requires=docker.service

[Service]
Type=oneshot
User=$USER
WorkingDirectory=$SCRIPT_DIR
ExecStart=$SYNC_SCRIPT
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
    echo "✓ Created systemd service: $SERVICE_FILE"

    # Create systemd timer (8:30 AM IST = 3:00 AM UTC, adjust based on your timezone)
    TIMER_FILE="/etc/systemd/system/corporate-actions-sync.timer"
    sudo tee "$TIMER_FILE" > /dev/null <<EOF
[Unit]
Description=Daily Corporate Actions Sync Timer
Requires=corporate-actions-sync.service

[Timer]
# Run at 8:30 AM IST (03:00 UTC - adjust based on timezone)
OnCalendar=*-*-* 08:30:00
# Run at 8:35 AM if missed (e.g., system was off)
Persistent=true

[Install]
WantedBy=timers.target
EOF
    echo "✓ Created systemd timer: $TIMER_FILE"

    # Reload systemd and enable timer
    sudo systemctl daemon-reload
    sudo systemctl enable corporate-actions-sync.timer
    sudo systemctl start corporate-actions-sync.timer

    echo ""
    echo "✓ Systemd timer enabled and started"
    echo ""
    echo "Status:"
    sudo systemctl status corporate-actions-sync.timer --no-pager
    echo ""
    echo "Next scheduled runs:"
    sudo systemctl list-timers corporate-actions-sync.timer --no-pager

else
    echo ""
    echo "Systemd not available, setting up cron job..."
    echo ""

    # Add to crontab (8:30 AM every day)
    CRON_CMD="30 8 * * * $SYNC_SCRIPT"

    # Check if already in crontab
    if crontab -l 2>/dev/null | grep -q "$SYNC_SCRIPT"; then
        echo "✓ Cron job already exists"
    else
        # Add to crontab
        (crontab -l 2>/dev/null; echo "$CRON_CMD") | crontab -
        echo "✓ Added cron job: $CRON_CMD"
    fi

    echo ""
    echo "Current crontab:"
    crontab -l | grep "$SYNC_SCRIPT" || echo "(no matching cron jobs)"
fi

echo ""
echo "=========================================="
echo "Setup Complete!"
echo "=========================================="
echo ""
echo "Daily sync will run at 8:30 AM IST (before market open)"
echo ""
echo "Manual sync:"
echo "  $SYNC_SCRIPT"
echo ""
echo "View logs:"
echo "  tail -f /var/log/corporate-actions/sync_\$(date +%Y%m%d).log"
echo ""
echo "Test sync now:"
echo "  $SYNC_SCRIPT"
echo ""
