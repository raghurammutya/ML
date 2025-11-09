#!/bin/bash
# Midnight Refresh Script - Runs at 12:01 AM IST
# Refreshes expiries table and token for all trading accounts

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_FILE="$PROJECT_DIR/logs/midnight_refresh.log"

# Ensure log directory exists
mkdir -p "$(dirname "$LOG_FILE")"

echo "========================================" >> "$LOG_FILE"
echo "$(date '+%Y-%m-%d %H:%M:%S') - Starting midnight refresh" >> "$LOG_FILE"

# 1. Clean up old expiry metadata and refresh for today
echo "$(date '+%Y-%m-%d %H:%M:%S') - Cleaning up old expiry metadata and refreshing for today..." >> "$LOG_FILE"

# Run database functions directly using psql
PGPASSWORD=stocksblitz123 psql -h localhost -U stocksblitz -d stocksblitz_unified -c "
    -- Refresh expiry metadata for today
    SELECT refresh_expiry_metadata() as refreshed_rows;

    -- Clean up old expiry metadata (keep last 90 days)
    SELECT cleanup_old_expiry_metadata(90) as cleaned_rows;
" >> "$LOG_FILE" 2>&1

if [ $? -eq 0 ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') - Successfully refreshed and cleaned up expiry metadata" >> "$LOG_FILE"
else
    echo "$(date '+%Y-%m-%d %H:%M:%S') - ERROR: Failed to refresh/cleanup expiry metadata" >> "$LOG_FILE"
fi

# 2. Refresh tokens for all trading accounts in ticker_service
echo "$(date '+%Y-%m-%d %H:%M:%S') - Refreshing tokens for ticker service..." >> "$LOG_FILE"
cd "$PROJECT_DIR/ticker_service"

# Run token bootstrap inside the container
docker exec tv-ticker python3 -m app.kite.token_bootstrap >> "$LOG_FILE" 2>&1

if [ $? -eq 0 ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') - Successfully refreshed Kite tokens" >> "$LOG_FILE"
else
    echo "$(date '+%Y-%m-%d %H:%M:%S') - ERROR: Failed to refresh Kite tokens" >> "$LOG_FILE"
fi

echo "$(date '+%Y-%m-%d %H:%M:%S') - Midnight refresh completed" >> "$LOG_FILE"
echo "========================================" >> "$LOG_FILE"
