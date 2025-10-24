#!/bin/bash

# Setup Production Monitoring Service
# Creates a systemd service to continuously monitor production integrity

set -e

if [[ $EUID -ne 0 ]]; then
    echo "This script must be run as root or with sudo"
    exit 1
fi

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Create systemd service file
cat > /etc/systemd/system/tradingview-monitor.service << EOF
[Unit]
Description=TradingView Production Environment Monitor
After=network.target
Wants=network.target

[Service]
Type=simple
ExecStart=$PROJECT_ROOT/scripts/monitor-production.sh --daemon
Restart=always
RestartSec=30
User=stocksadmin
Group=stocksadmin
Environment=PROJECT_ROOT=$PROJECT_ROOT

# Security settings
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/log /tmp
CapabilityBoundingSet=

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=tradingview-monitor

[Install]
WantedBy=multi-user.target
EOF

# Create log rotation config
cat > /etc/logrotate.d/tradingview-monitor << EOF
/var/log/tradingview-*.log {
    weekly
    rotate 4
    compress
    delaycompress
    missingok
    notifempty
    create 0644 stocksadmin stocksadmin
}
EOF

# Enable and start the service
systemctl daemon-reload
systemctl enable tradingview-monitor.service

echo "✓ Monitoring service created and enabled"
echo "To start monitoring: sudo systemctl start tradingview-monitor"
echo "To check status: sudo systemctl status tradingview-monitor"
echo "To view logs: sudo journalctl -u tradingview-monitor -f"