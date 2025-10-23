# app/database.py
from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

import asyncpg

logger = logging.getLogger("app.database")

# IST timezone offset (UTC+5:30)
IST_OFFSET = timedelta(hours=5, minutes=30)
IST_TIMEZONE = timezone(IST_OFFSET)

# -----------------------------
# Helpers / Normalization
# -----------------------------
def _bucket_label(raw: str | None) -> str:
    if not raw:
        return "Neutral"
    s = raw.lower()
    if any(k in s for k in ("bear", "sell", "short")):
        return "Bearish"
    if any(k in s for k in ("bull", "buy", "long")):
        return "Bullish"
    return "Neutral"
def _normalize_symbol(symbol: str) -> str:
    s = (symbol or "").strip().upper()
    aliases = {
        "NIFTY50": "NIFTY",
        "NSE:NIFTY50": "NIFTY",
        "NSE:NIFTY": "NIFTY",
        "^NSEI": "NIFTY",
    }
    return aliases.get(s, s)


def _normalize_timeframe(resolution: str) -> str:
    """
    Convert UI resolution into DB timeframe strings.
    Common DB formats: '1min', '2min', '5min', '15min', '30min', '1hour', '1day'.
    """
    r = str(resolution).strip().lower()
    
    # Handle special cases first
    if r in {"60", "1h", "60min", "1hour"}:
        return "1hour"
    if r in {"1d", "d", "day", "1day"}:
        return "1day"
    
    # Handle minute intervals
    if r.isdigit():
        minutes = int(r)
        if minutes <= 30:
            return f"{minutes}min"  # '1' -> '1min', '15' -> '15min'
        elif minutes == 60:
            return "1hour"
        else:
            return f"{minutes}min"  # fallback
    
    if r.endswith("m") and r[:-1].isdigit():
        return f"{int(r[:-1])}min"  # '15m' -> '15min'
    
    # Seconds like "120", "300", "900", …
    if r.isdigit() and int(r) in (60, 120, 180, 300, 600, 900, 1800, 3600):
        seconds = int(r)
        if seconds == 3600:
            return "1hour"
        else:
            return f"{seconds//60}min"
    
    # Already like 'Xmin'
    if r.endswith("min") and r[:-3].isdigit():
        return r
    
    return r


def _as_epoch_seconds(from_ts: int, to_ts: int) -> Tuple[int, int]:
    """
    Accept seconds or milliseconds from the client. Convert to epoch seconds.
    """
    if from_ts >= 10**12 or to_ts >= 10**12:  # looks like milliseconds
        return from_ts // 1000, to_ts // 1000
    return from_ts, to_ts


# Simple color map (tune to your labels)
LABEL_COLORS: Dict[str, str] = {
    "Bullish": "#00E676",   # bright green
    "Bearish": "#FF1744",   # bright red
    "Neutral": "#9CA3AF",   # neutral grey
    # Optional extras (kept, but won’t be used unless you emit those labels):
    "Reversal": "#EAB308",
    "Breakout": "#3B82F6",
}


# -----------------------------
# Pool bootstrap (optional helper)
# -----------------------------
async def create_pool(
    dsn: Optional[str] = None,
    min_size: int = 10,
    max_size: int = 20,
) -> asyncpg.Pool:
    dsn = (
        dsn
        or os.getenv("DATABASE_URL")
        or os.getenv("TIMESCALE_DATABASE_URL")
        or os.getenv("POSTGRES_URL")
    )
    if not dsn:
        raise RuntimeError("No database DSN found in env (DATABASE_URL / TIMESCALE_DATABASE_URL / POSTGRES_URL)")
    pool = await asyncpg.create_pool(dsn=dsn, min_size=min_size, max_size=max_size)
    logger.info("Database pool created: min=%s, max=%s", min_size, max_size)
    return pool


# -----------------------------
# DataManager
# -----------------------------
@dataclass
class DataManager:
    pool: asyncpg.Pool

    # ---------- HISTORY ----------
    async def get_history(
        self,
        symbol: str,
        from_timestamp: int,
        to_timestamp: int,
        resolution: str,
        limit: int = 20000,
    ) -> Dict[str, Any]:
        """
        Returns OHLC candles for the requested window.
        Uses ml_labeled_data for convenience since your sample row contains OHLC.
        """
        symbol_db = _normalize_symbol(symbol)
        timeframe = _normalize_timeframe(resolution)
        from_s, to_s = _as_epoch_seconds(from_timestamp, to_timestamp)

        query = """
            SELECT
              "time" AS ts,
              open, high, low, close,
              volume
            FROM ml_labeled_data
            WHERE symbol = $1
              AND timeframe = $2
              AND "time" BETWEEN to_timestamp($3) AND to_timestamp($4)
            ORDER BY "time"
            LIMIT $5
        """
        async with self.pool.acquire() as conn:
            try:
                rows = await conn.fetch(query, symbol_db, timeframe, from_s, to_s, limit)
            except Exception as e:
                logger.error("History fetch error: %s", e)
                return {"s": "error", "errmsg": "history query failed", "t": [], "o": [], "h": [], "l": [], "c": [], "v": []}

        t, o, h, l, c, v = [], [], [], [], [], []
        for r in rows:
            # Skip rows with NULL OHLC values
            if any(r[field] is None for field in ["open", "high", "low", "close"]):
                continue
                
            # Database stores naive timestamps that represent IST time
            # We need to treat them as IST and convert to UTC for TradingView
            naive_dt = r["ts"]
            if isinstance(naive_dt, datetime):
                # Treat the naive datetime as IST
                ist_dt = naive_dt.replace(tzinfo=IST_TIMEZONE)
                # Convert to UTC timestamp
                ts = int(ist_dt.timestamp())
                logger.info(f"TIMEZONE FIX: {naive_dt} (naive) -> {ist_dt} (IST) -> {ts} (UTC epoch)")
            else:
                # Fallback to original method if timestamp format is unexpected
                ts = int(naive_dt.timestamp())
                logger.warning(f"TIMEZONE FALLBACK: {naive_dt} -> {ts}")
            t.append(ts)
            o.append(float(r["open"]))
            h.append(float(r["high"]))
            l.append(float(r["low"]))
            c.append(float(r["close"]))
            v.append(int(r["volume"]) if r["volume"] is not None else 0)

        return {"s": "ok", "t": t, "o": o, "h": h, "l": l, "c": c, "v": v}
    async def set_bar_label(
        self,
        symbol: str,
        resolution: str,
        ts_seconds: int,            # bar time (epoch seconds, UTC)
        label: str,                 # "Bullish" | "Bearish" | "Neutral"
        confidence: Optional[float] = None,
        note: Optional[str] = None, # ignored if not in schema
    ) -> bool:
        symbol_db = _normalize_symbol(symbol)
        timeframe = _normalize_timeframe(resolution)
        t = int(ts_seconds)

        update_sql = """
            UPDATE ml_labeled_data
            SET label = $1,
                label_confidence = $2,
                updated_at = NOW()
            WHERE symbol = $3
            AND timeframe = $4
            AND time = to_timestamp($5)
        """
        insert_sql = """
            INSERT INTO ml_labeled_data (symbol, timeframe, time, label, label_confidence, labeling_version, labeling_rules_used, created_at, updated_at)
            VALUES ($1, $2, to_timestamp($3), $4, $5, 'user', '{user}', NOW(), NOW())
        """

        async with self.pool.acquire() as conn:
            tr = conn.transaction()
            await tr.start()
            try:
                res = await conn.execute(update_sql, label, confidence, symbol_db, timeframe, t)
                # res format like 'UPDATE 0' or 'UPDATE 1'
                if res.split()[-1] == '0':
                    # no row — insert minimal record
                    await conn.execute(insert_sql, symbol_db, timeframe, t, label, confidence)
                await tr.commit()
                return True
            except Exception as e:
                await tr.rollback()
                logger.error("set_bar_label failed: %s", e)
                return False


    async def delete_bar_label(
        self,
        symbol: str,
        resolution: str,
        ts_seconds: int
    ) -> bool:
        symbol_db = _normalize_symbol(symbol)
        timeframe = _normalize_timeframe(resolution)
        t = int(ts_seconds)

        sql = """
            UPDATE ml_labeled_data
            SET label = NULL,
                label_confidence = NULL,
                updated_at = NOW()
            WHERE symbol = $1
            AND timeframe = $2
            AND time = to_timestamp($3)
        """
        async with self.pool.acquire() as conn:
            try:
                await conn.execute(sql, symbol_db, timeframe, t)
                return True
            except Exception as e:
                logger.error("delete_bar_label failed: %s", e)
                return False

    # ---------- MARKS (fixed) ----------
    async def get_marks(
        self,
        symbol: str,
        from_timestamp: int,
        to_timestamp: int,
        resolution: str,
        include_neutral: bool = True,     # default now shows all labels incl. Neutral
        min_confidence: int = 0,          # we don’t filter by confidence by default
        limit: int = 20000,
        change_only: bool = False,        # accepted but ignored
    ) -> Dict[str, Any]:
        def _to_pct(v: Optional[float]) -> float:
            if v is None: return 0.0
            f = float(v)
            return f * 100.0 if f <= 1.0 else f

        symbol_db = _normalize_symbol(symbol)
        timeframe = _normalize_timeframe(resolution)
        from_s, to_s = _as_epoch_seconds(from_timestamp, to_timestamp)

        neutral_clause = "" if include_neutral else "AND label IS NOT NULL AND label <> 'Neutral'"

        # Convert IST timestamps to UTC epochs for TradingView
        # Database stores naive timestamps representing IST (UTC+5:30)
        sql = f"""
            SELECT
            (EXTRACT(EPOCH FROM time)::bigint - 19800) AS time_s,
            label,
            label_confidence
            FROM ml_labeled_data
            WHERE symbol=$1
            AND timeframe=$2
            AND time BETWEEN (to_timestamp($3) + interval '5 hours 30 minutes') 
                         AND (to_timestamp($4) + interval '5 hours 30 minutes')
            AND label IS NOT NULL
            {neutral_clause}
            ORDER BY time ASC
            LIMIT $5
        """

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, symbol_db, timeframe, from_s, to_s, int(limit))

        marks = []
        for i, r in enumerate(rows):
            ts = int(r["time_s"])
            lbl = r["label"] or "Neutral"
            conf = _to_pct(r["label_confidence"])
            color = LABEL_COLORS.get(lbl, LABEL_COLORS["Neutral"])
            marks.append({
                "id": f"ml-{ts}-{i}",
                "time": ts,
                "color": color,
                "text": f"{lbl}" + (f" | p={conf:.2f}" if r["label_confidence"] is not None else ""),
                "label": lbl[:1],
                "labelFontColor": "#FFFFFF",
                "minSize": 7,
            })
        return {"marks": marks}


    
    async def initialize(self) -> None:
        """
        Called by main.py during startup. If an asyncpg pool is available,
        ping it; otherwise skip gracefully (some deployments wire the pool later).
        """
        pool = getattr(self, "pool", None)
        if not (pool and hasattr(pool, "acquire")):
            logger.warning("DataManager.initialize: no asyncpg pool available yet; skipping DB ping")
            return
        try:
            async with pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            logger.info("DataManager initialized")
        except Exception as e:
            logger.error("DataManager initialization failed: %s", e)
            raise

    async def close(self) -> None:
        """
        Called by main.py on shutdown. Close the pool *only* if it's an asyncpg pool
        we own and it's closable; otherwise, no-op.
        """
        pool = getattr(self, "pool", None)
        if not (pool and hasattr(pool, "close")):
            logger.info("DataManager close: no closable pool; skipping")
            return
        try:
            # If your app owns the pool here, you may close it:
            # await pool.close()
            logger.info("DataManager closed")
        except Exception as e:
            logger.error("DataManager close failed: %s", e)
            # don't re-raise on shutdown

    def acquire(self):
        """
        Proxy to the asyncpg pool's acquire() so callers can use:
            async with data_manager.acquire() as conn:
                ...
        """
        pool = getattr(self, "pool", None)
        if not (pool and hasattr(pool, "acquire")):
            raise AttributeError("DataManager has no usable asyncpg pool")
        return pool.acquire()

    async def get_pool_stats(self) -> dict:
        """
        Async to match main.py's `await data_manager.get_pool_stats()`.
        Returns lightweight pool stats if an asyncpg pool is present.
        """
        pool = getattr(self, "pool", None)
        if not pool:
            return {"available": False}

        stats = {"available": True}
        for name, key in [
            ("get_size", "size"),
            ("get_min_size", "min"),
            ("get_max_size", "max"),
            ("get_idle_size", "idle"),   # some versions expose this
            ("get_idle_count", "idle"),  # fallback name in older/newer versions
        ]:
            meth = getattr(pool, name, None)
            if callable(meth):
                try:
                    stats[key] = int(meth())
                except Exception:
                    pass
        return stats

# -----------------------------
# Background refresh task expected by main.py
# -----------------------------
async def data_refresh_task(data_manager, interval_seconds: int = 300) -> None:
    """
    main.py passes the DataManager, not the pool.
    If an asyncpg pool is available, ping it; otherwise skip gracefully.
    Optionally bootstrap the pool from env if none exists yet.
    """
    while True:
        try:
            pool = getattr(data_manager, "pool", None)

            if not (pool and hasattr(pool, "acquire")):
                # Try to lazily create a pool (only if env DSN is set)
                try:
                    data_manager.pool = await create_pool()
                    pool = data_manager.pool
                    logger.info("data_refresh_task: created asyncpg pool")
                except Exception:
                    # No DSN or creation failed; skip this cycle quietly
                    logger.info("data_refresh_task: no pool yet; skipping this cycle")
                    await asyncio.sleep(interval_seconds)
                    continue

            async with pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            logger.info("Data refresh completed")

        except Exception as e:
            logger.error("Data refresh error: %s", e)

        await asyncio.sleep(interval_seconds)

