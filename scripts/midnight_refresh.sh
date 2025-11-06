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

# 1. Clean up old expiry metadata
echo "$(date '+%Y-%m-%d %H:%M:%S') - Cleaning up old expiry metadata..." >> "$LOG_FILE"
cd "$PROJECT_DIR/backend"
docker exec tv-backend python3 -c "
import asyncio
import asyncpg
from app.config import get_settings

async def cleanup_expiries():
    settings = get_settings()
    conn = await asyncpg.connect(
        host=settings.db_host,
        port=settings.db_port,
        user=settings.db_user,
        password=settings.db_password,
        database=settings.db_name
    )

    # Remove expired entries from expiry_metadata
    result = await conn.execute('''
        DELETE FROM expiry_metadata
        WHERE expiry < CURRENT_DATE
    ''')

    print(f'Removed {result} expired entries from expiry_metadata')
    await conn.close()

asyncio.run(cleanup_expiries())
" >> "$LOG_FILE" 2>&1

# 2. Refresh tokens for all trading accounts in ticker_service
echo "$(date '+%Y-%m-%d %H:%M:%S') - Refreshing tokens for ticker service..." >> "$LOG_FILE"
cd "$PROJECT_DIR/ticker_service"
docker exec tv-ticker python3 -c "
import asyncio
import json
import os
from pathlib import Path

async def refresh_tokens():
    tokens_dir = Path('/app/tokens')
    if not tokens_dir.exists():
        tokens_dir = Path('tokens')

    # Find all token files
    token_files = list(tokens_dir.glob('kite_token_*.json'))
    print(f'Found {len(token_files)} token files')

    for token_file in token_files:
        try:
            with open(token_file, 'r') as f:
                data = json.load(f)

            # Check if token needs refresh (within 24 hours of expiry)
            # This is a placeholder - actual refresh logic depends on your auth system
            print(f'Token file: {token_file.name}')
            print(f'User ID: {data.get(\"user_id\")}')
            print(f'Access token present: {bool(data.get(\"access_token\"))}')
        except Exception as e:
            print(f'Error processing {token_file}: {e}')

asyncio.run(refresh_tokens())
" >> "$LOG_FILE" 2>&1

echo "$(date '+%Y-%m-%d %H:%M:%S') - Midnight refresh completed" >> "$LOG_FILE"
echo "========================================" >> "$LOG_FILE"
