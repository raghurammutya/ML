#!/bin/bash
# Morning Refresh Script - Runs at 9:12 AM IST
# Refreshes instrument_registry and re-validates expiries table

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_FILE="$PROJECT_DIR/logs/morning_refresh.log"

# Ensure log directory exists
mkdir -p "$(dirname "$LOG_FILE")"

echo "========================================" >> "$LOG_FILE"
echo "$(date '+%Y-%m-%d %H:%M:%S') - Starting morning refresh" >> "$LOG_FILE"

# 1. Refresh instrument_registry from Zerodha/NSE
echo "$(date '+%Y-%m-%d %H:%M:%S') - Refreshing instrument registry..." >> "$LOG_FILE"
cd "$PROJECT_DIR/backend"
docker exec tv-backend python3 -c "
import asyncio
import aiohttp
import asyncpg
import csv
from io import StringIO
from datetime import datetime
from app.config import get_settings

async def refresh_instruments():
    settings = get_settings()

    # Download instruments CSV from Zerodha
    url = 'https://api.kite.trade/instruments'
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status != 200:
                print(f'Failed to download instruments: {response.status}')
                return

            content = await response.text()

    # Parse CSV
    reader = csv.DictReader(StringIO(content))
    instruments = list(reader)
    print(f'Downloaded {len(instruments)} instruments')

    # Connect to database
    conn = await asyncpg.connect(
        host=settings.db_host,
        port=settings.db_port,
        user=settings.db_user,
        password=settings.db_password,
        database=settings.db_name
    )

    # Filter F&O instruments and update registry
    fo_count = 0
    for inst in instruments:
        if inst.get('segment') in ['NFO-FUT', 'NFO-OPT']:
            # Upsert into instrument_registry
            await conn.execute('''
                INSERT INTO instrument_registry (
                    instrument_token, tradingsymbol, name, segment,
                    instrument_type, strike, expiry, tick_size,
                    lot_size, exchange, last_refreshed_at
                )
                VALUES (\$1, \$2, \$3, \$4, \$5, \$6, \$7, \$8, \$9, \$10, NOW())
                ON CONFLICT (instrument_token) DO UPDATE SET
                    tradingsymbol = EXCLUDED.tradingsymbol,
                    name = EXCLUDED.name,
                    segment = EXCLUDED.segment,
                    instrument_type = EXCLUDED.instrument_type,
                    strike = EXCLUDED.strike,
                    expiry = EXCLUDED.expiry,
                    tick_size = EXCLUDED.tick_size,
                    lot_size = EXCLUDED.lot_size,
                    exchange = EXCLUDED.exchange,
                    last_refreshed_at = NOW()
            ''',
                int(inst['instrument_token']),
                inst['tradingsymbol'],
                inst['name'],
                inst['segment'],
                inst.get('instrument_type'),
                float(inst['strike']) if inst.get('strike') else None,
                inst.get('expiry'),
                float(inst['tick_size']) if inst.get('tick_size') else None,
                int(inst['lot_size']) if inst.get('lot_size') else None,
                inst['exchange']
            )
            fo_count += 1

    print(f'Updated {fo_count} F&O instruments in registry')
    await conn.close()

asyncio.run(refresh_instruments())
" >> "$LOG_FILE" 2>&1

# 2. Verify instrument counts
echo "$(date '+%Y-%m-%d %H:%M:%S') - Verifying instrument counts..." >> "$LOG_FILE"
cd "$PROJECT_DIR/backend"
docker exec tv-backend python3 -c "
import asyncio
import asyncpg
from app.config import get_settings

async def verify_instruments():
    settings = get_settings()
    conn = await asyncpg.connect(
        host=settings.db_host,
        port=settings.db_port,
        user=settings.db_user,
        password=settings.db_password,
        database=settings.db_name
    )

    # Count instruments by segment
    counts = await conn.fetch('''
        SELECT segment, COUNT(*) as count
        FROM instrument_registry
        GROUP BY segment
        ORDER BY count DESC
    ''')

    print('Instrument counts by segment:')
    for row in counts:
        print(f'  {row[\"segment\"]}: {row[\"count\"]}')

    # Verify upcoming expiries for NIFTY
    nifty_expiries = await conn.fetch('''
        SELECT DISTINCT expiry
        FROM instrument_registry
        WHERE symbol = 'NIFTY'
        AND expiry >= CURRENT_DATE
        ORDER BY expiry
        LIMIT 5
    ''')
    print(f'\\nNIFTY upcoming expiries: {[str(r[\"expiry\"]) for r in nifty_expiries]}')

    await conn.close()

asyncio.run(verify_instruments())
" >> "$LOG_FILE" 2>&1

echo "$(date '+%Y-%m-%d %H:%M:%S') - Morning refresh completed" >> "$LOG_FILE"
echo "========================================" >> "$LOG_FILE"
