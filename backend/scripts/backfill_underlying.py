#!/usr/bin/env python3
"""
Backfill 1-minute bars from ticker-service into canonical storage.
Usage:
  poetry run python backend/scripts/backfill_underlying.py \
      --from 2024-10-23T09:15:00+05:30 \
      --to   2024-10-28T15:30:00+05:30
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone, timedelta, tzinfo
from typing import Optional

import httpx
from asyncpg import create_pool

from app.config import get_settings
from app.database import DataManager

settings = get_settings()

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None

IST_TZ: tzinfo = ZoneInfo("Asia/Kolkata") if ZoneInfo else timezone(timedelta(hours=5, minutes=30))


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"Invalid ISO timestamp: {value}") from exc


async def fetch_history(client: httpx.AsyncClient, instrument_token: int, start_iso: str, end_iso: str):
    params = {
        "instrument_token": instrument_token,
        "interval": "minute",
        "from_ts": start_iso,
        "to_ts": end_iso,
        "oi": "false",
    }
    resp = await client.get(f"{settings.ticker_service_url.rstrip('/')}/history", params=params, timeout=30)
    resp.raise_for_status()
    payload = resp.json()
    candles = payload.get("candles", [])
    if isinstance(candles, dict):
        candles = candles.get("data", [])
    return candles

def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _ensure_naive_ist(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(IST_TZ).replace(tzinfo=None)

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--from", dest="from_iso", required=False,
                        help="ISO8601 start (default: last bar + 1 minute)")
    parser.add_argument("--to", dest="to_iso", required=False,
                        help="ISO8601 end (default: now)")
    args = parser.parse_args()

    start_override = _parse_iso(args.from_iso)
    end_override = _parse_iso(args.to_iso)

    pool = await create_pool(
        user=settings.db_user,
        password=settings.db_password,
        host=settings.db_host,
        port=settings.db_port,
        database=settings.db_name,
        min_size=1,
        max_size=5,
    )
    dm = DataManager(pool)

    target_symbol = settings.monitor_default_symbol

    async with pool.acquire() as conn:
        last_row = await conn.fetchrow(
            """
            SELECT time
            FROM minute_bars
            WHERE symbol = $1 AND resolution = 1
            ORDER BY time DESC
            LIMIT 1
            """,
            target_symbol,
        )

    metadata = await dm.get_nifty_monitor_metadata(target_symbol, expiry_limit=1)
    underlying_info = metadata.get("underlying") if metadata else None
    if not underlying_info or not underlying_info.get("instrument_token"):
        raise RuntimeError("Unable to resolve instrument_token from metadata")
    instrument_token = int(underlying_info["instrument_token"])

    if last_row:
        default_start = last_row["time"] + timedelta(minutes=1)
    else:
        default_start = datetime(2024, 10, 23, 9, 15)  # whatever start point you prefer

    start_dt = start_override or default_start
    end_dt = end_override or datetime.now(timezone.utc)

    start_iso = _iso(start_dt)
    end_iso = _iso(end_dt)

    async with httpx.AsyncClient() as client:
        candles = await fetch_history(client, instrument_token, start_iso, end_iso)

    rows = []
    if not candles:
        print(f"No candles returned between {start_iso} and {end_iso}")
    for candle in candles:
        ts: Optional[str] = None
        o = h = l = c = v = None

        if isinstance(candle, (list, tuple)):
            if len(candle) < 6:
                print(f"Skipping malformed candle: {candle}")
                continue
            ts, o, h, l, c, v = candle[:6]
        elif isinstance(candle, dict):
            ts = candle.get("date") or candle.get("time")
            o = candle.get("open")
            h = candle.get("high")
            l = candle.get("low")
            c = candle.get("close")
            v = candle.get("volume", 0)
        else:
            print(f"Skipping malformed candle: {candle}")
            continue

        try:
            ts_dt = datetime.fromisoformat(ts)
        except Exception:
            print(f"Skipping candle with invalid timestamp: {candle}")
            continue

        if ts_dt.tzinfo is not None:
            ts_dt = ts_dt.astimezone(timezone.utc).replace(tzinfo=None)

        try:
            rows.append(
                {
                    "symbol": target_symbol,
                    "timeframe": "1min",
                    "time": _ensure_naive_ist(ts_dt),
                    "open": float(o),
                    "high": float(h),
                    "low": float(l),
                    "close": float(c),
                    "volume": int(v or 0),
                }
            )
        except Exception:
            print(f"Skipping candle with invalid numeric fields: {candle}")
            continue

    await dm.upsert_underlying_bars(rows)
    await pool.close()
    print(f"Inserted/updated {len(rows)} bars between {start_iso} and {end_iso}")

if __name__ == "__main__":
    asyncio.run(main())
