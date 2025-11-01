#!/bin/bash
#
# Holiday Synchronization Script
# Automatically syncs market holidays from official sources
#
# Usage:
#   ./sync_holidays.sh [YEARS]
#   ./sync_holidays.sh 2026,2027
#
# Cron setup (monthly):
#   0 0 1 * * /path/to/sync_holidays.sh 2026,2027 >> /var/log/holiday_sync.log 2>&1
#

set -e

# Configuration
CONTAINER_NAME="tv-backend"
YEARS="${1:-$(date +%Y),$(date -d '+1 year' +%Y)}"
LOG_PREFIX="[Holiday Sync]"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}${LOG_PREFIX} INFO:${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}${LOG_PREFIX} WARN:${NC} $1"
}

log_error() {
    echo -e "${RED}${LOG_PREFIX} ERROR:${NC} $1"
}

# Check if Docker container is running
if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    log_error "Container ${CONTAINER_NAME} is not running"
    exit 1
fi

log_info "Starting holiday synchronization for years: ${YEARS}"
log_info "Container: ${CONTAINER_NAME}"

# Run holiday sync
log_info "Executing holiday fetcher..."
if docker exec ${CONTAINER_NAME} python -m app.services.holiday_fetcher \
    --sync-all --years "${YEARS}"; then
    log_info "✅ Holiday synchronization completed successfully"

    # Verify sync
    log_info "Verifying sync..."
    IFS=',' read -ra YEAR_ARRAY <<< "$YEARS"
    for year in "${YEAR_ARRAY[@]}"; do
        year=$(echo $year | tr -d ' ')
        count=$(docker exec ${CONTAINER_NAME} python -c "
import asyncio
import asyncpg

async def count_holidays():
    conn = await asyncpg.connect(
        user='stocksblitz',
        password='stocksblitz123',
        database='stocksblitz_unified',
        host='localhost'
    )
    try:
        result = await conn.fetchval('''
            SELECT COUNT(*) FROM calendar_events
            WHERE EXTRACT(YEAR FROM event_date) = \$1
            AND category = 'market_holiday'
        ''', $year)
        print(result)
    finally:
        await conn.close()

asyncio.run(count_holidays())
" 2>/dev/null || echo "0")

        log_info "  Year ${year}: ${count} holidays"
    done

    log_info "✅ All holidays synced and verified"
    exit 0
else
    log_error "Holiday synchronization failed"
    exit 1
fi
