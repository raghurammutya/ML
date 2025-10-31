# app/database.py
from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta, date
from typing import Any, Dict, Iterable, List, Optional, Tuple, Set

import asyncpg

from .config import get_settings
from .utils import normalize_symbol, get_symbol_variants, normalize_timeframe

logger = logging.getLogger("app.database")

# IST timezone offset (UTC+5:30)
IST_OFFSET = timedelta(hours=5, minutes=30)
IST_TIMEZONE = timezone(IST_OFFSET)
# app/database.py

import random
import asyncpg

async def _executemany_with_deadlock_retry(conn, sql, records, *, retries: int = 5, base_sleep: float = 0.05):
    """
    Execute executemany with retry on deadlocks. Uses a small jittered backoff.
    """
    attempt = 0
    while True:
        try:
            # Important: deterministically order by primary key to reduce deadlock odds
            return await conn.executemany(sql, records)
        except asyncpg.exceptions.DeadlockDetectedError as e:
            attempt += 1
            if attempt >= retries:
                raise
            # jittered backoff
            await asyncio.sleep(base_sleep * attempt + random.uniform(0, base_sleep))
# -----------------------------
# Helpers / Normalization
# -----------------------------
async def _advisory_lock(conn, key: int):
    # pg_advisory_lock is session-level; use try_advisory_lock so we don't block forever
    return await conn.fetchval("SELECT pg_try_advisory_lock($1)", key)

async def _advisory_unlock(conn, key: int):
    await conn.execute("SELECT pg_advisory_unlock($1)", key)

def _bucket_label(raw: str | None) -> str:
    if not raw:
        return "Neutral"
    s = raw.lower()
    if any(k in s for k in ("bear", "sell", "short")):
        return "Bearish"
    if any(k in s for k in ("bull", "buy", "long")):
        return "Bullish"
    return "Neutral"
# Legacy function aliases for backward compatibility
# Use shared utils instead: from .utils import normalize_symbol, get_symbol_variants
def _normalize_symbol(symbol: str) -> str:
    """Deprecated: Use utils.normalize_symbol() instead."""
    return normalize_symbol(symbol)


def _symbol_variants(symbol: str) -> List[str]:
    """Deprecated: Use utils.get_symbol_variants() instead."""
    return get_symbol_variants(symbol)


# Legacy function alias for backward compatibility
# Use shared utils instead: from .utils import normalize_timeframe
def _normalize_timeframe(resolution: str) -> str:
    """Deprecated: Use utils.normalize_timeframe() instead."""
    return normalize_timeframe(resolution)


def _timeframe_to_resolution(resolution: str) -> int:
    """
    Convert normalized timeframe strings (e.g. '1min', '5min', '1hour') into
    integer minute representation used by the canonical minute_bars schema.
    """
    r = _normalize_timeframe(resolution)
    if r.endswith("min") and r[:-3].isdigit():
        return max(1, int(r[:-3]))
    if r.endswith("hour") and r[:-4].isdigit():
        return max(1, int(r[:-4]) * 60)
    if r in {"1day", "day"}:
        return 1440
    if r in {"1week", "week"}:
        return 7 * 1440
    if r in {"1month", "month"}:
        return 30 * 1440
    if r.isdigit():
        return max(1, int(r))
    return 1


def _resolution_interval_literal(resolution_minutes: int) -> str:
    """
    Build a safe interval literal string for time_bucket.
    Only a limited, known set of intervals is produced to avoid SQL injection.
    """
    if resolution_minutes <= 0:
        return "1 minute"
    if resolution_minutes % (30 * 24 * 60) == 0:
        months = resolution_minutes // (30 * 24 * 60)
        return f"{months} month" if months == 1 else f"{months} months"
    if resolution_minutes % (7 * 24 * 60) == 0:
        weeks = resolution_minutes // (7 * 24 * 60)
        return f"{weeks} week" if weeks == 1 else f"{weeks} weeks"
    if resolution_minutes % (24 * 60) == 0:
        days = resolution_minutes // (24 * 60)
        return f"{days} day" if days == 1 else f"{days} days"
    if resolution_minutes % 60 == 0:
        hours = resolution_minutes // 60
        return f"{hours} hour" if hours == 1 else f"{hours} hours"
    return f"{resolution_minutes} minutes"


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

FO_STRIKE_TABLES: Dict[str, str] = {
    # 1min: Base table with all columns including call_oi_sum and put_oi_sum
    "1min": "fo_option_strike_bars",

    # 5min/15min: Enriched views that wrap TimescaleDB continuous aggregates
    # Background: Continuous aggregates were created before OI columns were added to base table.
    # TimescaleDB doesn't automatically include columns added after aggregate creation.
    # Solution: Enriched views LEFT JOIN with 1min base table to fetch OI columns.
    # See migration: 013_create_fo_enriched_views.sql
    # Performance: Slight overhead from JOIN, but ensures data completeness.
    "5min": "fo_option_strike_bars_5min_enriched",   # Wraps fo_option_strike_bars_5min
    "15min": "fo_option_strike_bars_15min_enriched",  # Wraps fo_option_strike_bars_15min
}

FO_EXPIRY_TABLES: Dict[str, str] = {
    "1min": "fo_expiry_metrics",
    "5min": "fo_expiry_metrics_5min",
    "15min": "fo_expiry_metrics_15min",
}


def _fo_strike_table(timeframe: str) -> str:
    tf = _normalize_timeframe(timeframe)
    return FO_STRIKE_TABLES.get(tf, FO_STRIKE_TABLES["1min"])


def _fo_expiry_table(timeframe: str) -> str:
    tf = _normalize_timeframe(timeframe)
    return FO_EXPIRY_TABLES.get(tf, FO_EXPIRY_TABLES["1min"])


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
        settings = get_settings()
        dsn = (
            f"postgresql://{settings.db_user}:{settings.db_password}"
            f"@{settings.db_host}:{settings.db_port}/{settings.db_name}"
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
    _unsupported_tokens: Dict[int, str] = field(default_factory=dict, init=False)

    def mark_token_no_history(self, instrument_token: int, reason: str, symbol: Optional[str] = None) -> None:
        """Record that a token has no available historical data."""
        if instrument_token in self._unsupported_tokens:
            return
        detail = reason or "no historical data"
        if symbol:
            detail = f"{symbol}: {detail}"
        self._unsupported_tokens[instrument_token] = detail
        logger.warning("Skipping token %s (%s)", instrument_token, detail)

    def is_token_supported(self, instrument_token: int) -> bool:
        return instrument_token not in self._unsupported_tokens

    def filter_supported_tokens(self, tokens: Iterable[int]) -> Tuple[List[int], List[Tuple[int, str]]]:
        supported: List[int] = []
        dropped: List[Tuple[int, str]] = []
        for token in tokens:
            if token is None:
                continue
            try:
                token_int = int(token)
            except (TypeError, ValueError):
                continue
            if self.is_token_supported(token_int):
                supported.append(token_int)
            else:
                dropped.append((token_int, self._unsupported_tokens[token_int]))
        return supported, dropped

    async def lookup_instrument(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Resolve a user-supplied symbol (with optional exchange prefixes or spacing)
        into the latest instrument_registry entry. Returns None if no active
        instrument matches.
        """
        if not symbol:
            return None
        symbol_norm = _normalize_symbol(symbol)
        raw_upper = (symbol or "").strip().upper()
        variants = {
            symbol_norm,
            raw_upper,
            raw_upper.replace(" ", ""),
        }
        if ":" in raw_upper:
            variants.add(raw_upper.split(":")[-1])
        for prefix in ("NSE:", "BSE:", "IDX:", "MCX:", "CDS:"):
            if raw_upper.startswith(prefix):
                variants.add(raw_upper[len(prefix):])
        candidates = list({v for v in variants if v})
        if not candidates:
            return None

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT instrument_token,
                       tradingsymbol,
                       name,
                       segment,
                       instrument_type,
                       exchange,
                       lot_size,
                       tick_size,
                       last_refreshed_at
                  FROM instrument_registry
                 WHERE is_active = TRUE
                   AND (
                        upper(tradingsymbol) = ANY($1)
                     OR replace(upper(tradingsymbol), ' ', '') = ANY($1)
                     OR upper(name) = ANY($1)
                     OR replace(upper(name), ' ', '') = ANY($1)
                   )
              ORDER BY last_refreshed_at DESC
                 LIMIT 1
                """,
                candidates,
            )

        if not row:
            return None

        tick_size = float(row["tick_size"]) if row["tick_size"] is not None else None
        lot_size = int(row["lot_size"]) if row["lot_size"] is not None else None

        return {
            "canonical_symbol": symbol_norm,
            "tradingsymbol": row["tradingsymbol"],
            "name": row["name"],
            "segment": row["segment"],
            "instrument_type": row["instrument_type"],
            "exchange": row["exchange"],
            "instrument_token": int(row["instrument_token"]) if row["instrument_token"] is not None else None,
            "lot_size": lot_size,
            "tick_size": tick_size,
        }

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
        Returns OHLC candles for the requested window using the canonical minute_bars table.
        """
        symbol_db = _normalize_symbol(symbol)
        timeframe = _normalize_timeframe(resolution)
        from_s, to_s = _as_epoch_seconds(from_timestamp, to_timestamp)
        resolution_minutes = _timeframe_to_resolution(timeframe)
        limit = int(limit)

        async with self.pool.acquire() as conn:
            try:
                if resolution_minutes == 1:
                    sql = """
                        SELECT
                          EXTRACT(EPOCH FROM (time AT TIME ZONE 'Asia/Kolkata'))::bigint AS ts,
                          open, high, low, close, volume
                        FROM minute_bars
                        WHERE symbol = $1
                          AND resolution = $2
                          AND time BETWEEN (to_timestamp($3) + interval '5 hours 30 minutes')
                                       AND (to_timestamp($4) + interval '5 hours 30 minutes')
                        ORDER BY time
                        LIMIT $5
                    """
                    rows = await conn.fetch(sql, symbol_db, resolution_minutes, from_s, to_s, limit)
                else:
                    interval_literal = _resolution_interval_literal(resolution_minutes)
                    sql = f"""
                        WITH base AS (
                            SELECT
                                time,
                                time AT TIME ZONE 'Asia/Kolkata' AS time_utc,
                                open,
                                high,
                                low,
                                close,
                                volume
                            FROM minute_bars
                            WHERE symbol = $1
                              AND resolution = 1
                              AND time BETWEEN (to_timestamp($2) + interval '5 hours 30 minutes')
                                           AND (to_timestamp($3) + interval '5 hours 30 minutes')
                        ),
                        buckets AS (
                            SELECT
                                time_bucket('{interval_literal}', time_utc) AS bucket,
                                first(open, time_utc) AS open,
                                max(high) AS high,
                                min(low) AS low,
                                last(close, time_utc) AS close,
                                sum(volume) AS volume
                            FROM base
                            GROUP BY bucket
                        )
                        SELECT
                            EXTRACT(EPOCH FROM bucket)::bigint AS ts,
                            open, high, low, close, volume
                        FROM buckets
                        ORDER BY bucket
                        LIMIT $4
                    """
                    rows = await conn.fetch(sql, symbol_db, from_s, to_s, limit)
            except Exception as exc:
                logger.error("History fetch error | symbol=%s resolution=%s error=%s", symbol_db, timeframe, exc)
                return {"s": "error", "errmsg": "history query failed", "t": [], "o": [], "h": [], "l": [], "c": [], "v": []}

        t, o, h, l, c, v = [], [], [], [], [], []
        for row in rows:
            if any(row[field] is None for field in ("open", "high", "low", "close")):
                continue
            ts = int(row["ts"])
            t.append(ts)
            o.append(float(row["open"]))
            h.append(float(row["high"]))
            l.append(float(row["low"]))
            c.append(float(row["close"]))
            v.append(int(row["volume"]) if row["volume"] is not None else 0)

        if not t:
            logger.info("No history rows for symbol=%s timeframe=%s window=%s-%s", symbol_db, timeframe, from_s, to_s)
            return {"s": "no_data"}

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

        neutral_clause = "" if include_neutral else "AND label_type <> 'Neutral'"

        # Convert IST timestamps to UTC epochs for TradingView
        # Database stores timestamps in metadata->nearest_candle_timestamp_utc (UTC)
        # We subtract 19800 seconds (5.5 hours) for IST adjustment
        # Only show user-created labels (confidence = 1.0, displayed as 100%)
        sql = f"""
            SELECT
            (EXTRACT(EPOCH FROM (metadata->>'nearest_candle_timestamp_utc')::timestamptz)::bigint - 19800) AS time_s,
            label_type as label,
            COALESCE((metadata->>'confidence')::numeric, 1.0) as label_confidence
            FROM ml_labels
            WHERE symbol=$1
            AND metadata->>'timeframe'=$2
            AND (metadata->>'nearest_candle_timestamp_utc')::timestamptz BETWEEN (to_timestamp($3) + interval '5 hours 30 minutes')
                         AND (to_timestamp($4) + interval '5 hours 30 minutes')
            AND label_type IS NOT NULL
            AND COALESCE((metadata->>'confidence')::numeric, 1.0) = 1.0
            {neutral_clause}
            ORDER BY time_s ASC
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

    # ---------- FO DATA ----------

    async def upsert_underlying_bars(self, rows: List[Dict[str, Any]]) -> None:
        if not rows:
            return

        # Write to minute_bars table (underlying OHLC data)
        minute_sql = """
            INSERT INTO minute_bars (
                time,
                symbol,
                resolution,
                open,
                high,
                low,
                close,
                volume,
                metadata
            ) VALUES (
                $1,$2,$3,$4,$5,$6,$7,$8,$9
            )
            ON CONFLICT (symbol, resolution, time)
            DO UPDATE SET
                open   = EXCLUDED.open,
                high   = EXCLUDED.high,
                low    = EXCLUDED.low,
                close  = EXCLUDED.close,
                volume = EXCLUDED.volume,
                metadata = EXCLUDED.metadata
        """

        minute_records: List[tuple] = []
        for row in rows:
            symbol_norm = _normalize_symbol(row["symbol"])
            time_value = row["time"]
            resolution = _timeframe_to_resolution(row.get("timeframe", "1min"))
            metadata_json = row.get("metadata", {})
            if not isinstance(metadata_json, str):
                metadata_json = json.dumps(metadata_json)

            minute_records.append(
                (
                    time_value,
                    symbol_norm,
                    resolution,
                    row["open"],
                    row["high"],
                    row["low"],
                    row["close"],
                    row.get("volume", 0),
                    metadata_json,
                )
            )

        # Sort to ensure deterministic lock order
        minute_records.sort(key=lambda r: (r[0], r[1], r[2]))  # (time, symbol, resolution)

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await _executemany_with_deadlock_retry(conn, minute_sql, minute_records)
    
    async def upsert_futures_bars(self, rows: List[Dict[str, Any]]) -> None:
        if not rows:
            return
        sql = """
            INSERT INTO futures_bars (
                time,
                symbol,
                contract,
                expiry,
                resolution,
                open,
                high,
                low,
                close,
                volume,
                open_interest,
                metadata
            ) VALUES (
                $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12
            )
            ON CONFLICT (time, symbol, contract, resolution)
            DO UPDATE SET
                open = EXCLUDED.open,
                high = EXCLUDED.high,
                low = EXCLUDED.low,
                close = EXCLUDED.close,
                volume = EXCLUDED.volume,
                open_interest = EXCLUDED.open_interest,
                metadata = EXCLUDED.metadata,
                updated_at = NOW()
        """
        records = []
        for row in rows:
            metadata = row.get("metadata") or {}
            metadata_json = metadata if isinstance(metadata, str) else json.dumps(metadata)
            records.append(
                (
                    row["time"],
                    _normalize_symbol(row["symbol"]),
                    row["contract"],
                    row.get("expiry"),
                    _timeframe_to_resolution(row.get("timeframe", "1min")),
                    row["open"],
                    row["high"],
                    row["low"],
                    row["close"],
                    row.get("volume", 0),
                    row.get("open_interest"),
                    metadata_json,
                )
            )

        # Sort by conflict keys: (time, symbol, contract, resolution)
        records.sort(key=lambda r: (r[0], r[1], r[2], r[4]))

        async with self.pool.acquire() as conn:
            await _executemany_with_deadlock_retry(conn, sql, records)

    async def list_fo_expiries(self, symbol: str) -> List[date]:
            symbol_variants = _symbol_variants(symbol)
            query = """
                SELECT DISTINCT expiry
                FROM fo_option_strike_bars
                WHERE symbol = ANY($1::text[])
                ORDER BY expiry ASC
            """
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, symbol_variants)
            return [row["expiry"] for row in rows]

    async def upsert_fo_strike_rows(self, rows: List[Dict[str, Any]]) -> None:
        if not rows:
            return
        sql = """
            INSERT INTO fo_option_strike_bars (
                bucket_time,
                timeframe,
                symbol,
                expiry,
                strike,
                underlying_close,
                call_iv_avg,
                put_iv_avg,
                call_delta_avg,
                put_delta_avg,
                call_gamma_avg,
                put_gamma_avg,
                call_theta_avg,
                put_theta_avg,
                call_vega_avg,
                put_vega_avg,
                call_volume,
                put_volume,
                call_count,
                put_count,
                call_oi_sum,
                put_oi_sum
            ) VALUES (
                $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22
            )
            ON CONFLICT (symbol, expiry, timeframe, bucket_time, strike)
            DO UPDATE SET
                underlying_close = EXCLUDED.underlying_close,
                call_iv_avg = EXCLUDED.call_iv_avg,
                put_iv_avg = EXCLUDED.put_iv_avg,
                call_delta_avg = EXCLUDED.call_delta_avg,
                put_delta_avg = EXCLUDED.put_delta_avg,
                call_gamma_avg = EXCLUDED.call_gamma_avg,
                put_gamma_avg = EXCLUDED.put_gamma_avg,
                call_theta_avg = EXCLUDED.call_theta_avg,
                put_theta_avg = EXCLUDED.put_theta_avg,
                call_vega_avg = EXCLUDED.call_vega_avg,
                put_vega_avg = EXCLUDED.put_vega_avg,
                call_volume = EXCLUDED.call_volume,
                put_volume = EXCLUDED.put_volume,
                call_count = EXCLUDED.call_count,
                put_count = EXCLUDED.put_count,
                call_oi_sum = EXCLUDED.call_oi_sum,
                put_oi_sum = EXCLUDED.put_oi_sum,
                updated_at = NOW()
        """
        records = []
        for row in rows:
            call = row["call"]
            put = row["put"]
            call_oi = call.get("oi") if isinstance(call, dict) else None
            put_oi = put.get("oi") if isinstance(put, dict) else None
            records.append((
                row["bucket_time"],
                _normalize_timeframe(row["timeframe"]),
                _normalize_symbol(row["symbol"]),
                row["expiry"],
                float(row["strike"]),
                row.get("underlying_close"),
                call.get("iv"),
                put.get("iv"),
                call.get("delta"),
                put.get("delta"),
                call.get("gamma"),
                put.get("gamma"),
                call.get("theta"),
                put.get("theta"),
                call.get("vega"),
                put.get("vega"),
                call.get("volume"),
                put.get("volume"),
                call.get("count"),
                put.get("count"),
                float(call_oi) if call_oi is not None else None,
                float(put_oi) if put_oi is not None else None,
            ))

        # Sort by conflict keys: (symbol, expiry, timeframe, bucket_time, strike)
        records.sort(key=lambda r: (r[2], r[3], r[1], r[0], r[4]))

        async with self.pool.acquire() as conn:
            await _executemany_with_deadlock_retry(conn, sql, records)
    
    async def fetch_latest_fo_strike_rows(
        self,
        symbol: str,
        timeframe: str,
        expiries: Optional[List[date]],
    ):
        tf = _normalize_timeframe(timeframe)
        symbol_variants = _symbol_variants(symbol)
        table_name = _fo_strike_table(tf)

        # Build query parameters
        params: List[Any] = [symbol_variants]
        if expiries:
            params.append(expiries)

        # Query latest data from the appropriate table/view
        query = f"""
            WITH latest AS (
                SELECT expiry, MAX(bucket_time) AS bucket_time
                FROM {table_name}
                WHERE symbol = ANY($1::text[])
                GROUP BY expiry
            )
            SELECT s.*
            FROM {table_name} s
            JOIN latest l
              ON s.expiry = l.expiry
             AND s.bucket_time = l.bucket_time
            WHERE s.symbol = ANY($1::text[])
              {"AND s.expiry = ANY($2)" if expiries else ""}
            ORDER BY s.expiry ASC, s.strike ASC
        """
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, *params)

    async def upsert_fo_expiry_metrics(self, rows: List[Dict[str, Any]]) -> None:
        if not rows:
            return
        sql = """
            INSERT INTO fo_expiry_metrics (
                bucket_time,
                timeframe,
                symbol,
                expiry,
                underlying_close,
                total_call_volume,
                total_put_volume,
                total_call_oi,
                total_put_oi,
                pcr,
                max_pain_strike
            ) VALUES (
                $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11
            )
            ON CONFLICT (symbol, expiry, timeframe, bucket_time)
            DO UPDATE SET
                underlying_close = EXCLUDED.underlying_close,
                total_call_volume = EXCLUDED.total_call_volume,
                total_put_volume = EXCLUDED.total_put_volume,
                total_call_oi = EXCLUDED.total_call_oi,
                total_put_oi = EXCLUDED.total_put_oi,
                pcr = EXCLUDED.pcr,
                max_pain_strike = EXCLUDED.max_pain_strike,
                updated_at = NOW()
        """
        records = [
            (
                row["bucket_time"],
                _normalize_timeframe(row["timeframe"]),
                _normalize_symbol(row["symbol"]),
                row["expiry"],
                row.get("underlying_close"),
                row.get("total_call_volume"),
                row.get("total_put_volume"),
                row.get("total_call_oi"),
                row.get("total_put_oi"),
                row.get("pcr"),
                row.get("max_pain_strike"),
            )
            for row in rows
        ]

        # Sort by conflict keys: (symbol, expiry, timeframe, bucket_time)
        records.sort(key=lambda r: (r[2], r[3], r[1], r[0]))

        async with self.pool.acquire() as conn:
            await _executemany_with_deadlock_retry(conn, sql, records)
    
    async def search_monitor_symbols(
        self,
        query: str,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        cleaned = (query or "").strip()
        if not cleaned:
            return []
        like_pattern = f"%{cleaned}%"
        prefix_pattern = f"{cleaned}%"
        limit = max(1, min(int(limit), 50))
        sql = """
            SELECT
                tradingsymbol,
                name,
                segment,
                instrument_type,
                exchange,
                instrument_token,
                last_refreshed_at
            FROM instrument_registry
            WHERE is_active = TRUE
              AND (
                    tradingsymbol ILIKE $1
                 OR replace(tradingsymbol, ' ', '') ILIKE replace($1, ' ', '')
                 OR name ILIKE $1
                 OR replace(name, ' ', '') ILIKE replace($1, ' ', '')
              )
            ORDER BY
                CASE
                    WHEN tradingsymbol ILIKE $2 THEN 0
                    WHEN name ILIKE $2 THEN 1
                    ELSE 2
                END,
                last_refreshed_at DESC
            LIMIT $3
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, like_pattern, prefix_pattern, limit)

        results: List[Dict[str, Any]] = []
        seen: Set[str] = set()
        for row in rows:
            display_symbol = row["tradingsymbol"] or row["name"] or ""
            if not display_symbol:
                continue
            compact = display_symbol.replace(" ", "")
            canonical = _normalize_symbol(compact)
            if not canonical:
                canonical = compact.upper()
            if canonical in seen:
                continue
            seen.add(canonical)
            results.append(
                {
                    "canonical_symbol": canonical,
                    "display_symbol": display_symbol,
                    "name": row["name"],
                    "segment": row["segment"],
                    "instrument_type": row["instrument_type"],
                    "exchange": row["exchange"],
                    "instrument_token": int(row["instrument_token"]) if row["instrument_token"] is not None else None,
                }
            )
        return results

    async def get_nifty_monitor_metadata(
        self,
        symbol: str,
        expiry_limit: Optional[int] = None,
        otm_levels: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Build the instrument metadata payload required by the monitor dashboard.
        Returns underlying instrument, near-dated futures, and option ladders
        (ATM +/- requested moneyness levels) across upcoming expiries.
        """
        settings = get_settings()
        if not self.pool:
            raise RuntimeError("DataManager pool not initialised")

        symbol_norm = _normalize_symbol(symbol)
        symbol_upper = symbol_norm.upper()
        symbol_variants = set(_symbol_variants(symbol))
        symbol_variants.add(symbol_upper)
        symbol_variants.add(symbol_upper.replace("NSE:", ""))
        symbol_variants.add(symbol_upper.replace("BSE:", ""))
        symbol_variants.add(symbol_upper.replace("IDX:", ""))
        symbol_variants.add(symbol_upper.replace(" ", ""))
        symbol_array = list({variant for variant in symbol_variants if variant})

        max_expiries = expiry_limit or settings.fo_option_expiry_window
        if max_expiries <= 0:
            max_expiries = settings.fo_option_expiry_window

        ladder_levels = otm_levels or settings.fo_max_moneyness_level
        if ladder_levels <= 0:
            ladder_levels = settings.fo_max_moneyness_level

        strike_gap = settings.fo_strike_gap or 50
        strike_span = float(strike_gap) * float(ladder_levels)

        async with self.pool.acquire() as conn:
            underlying_row = await conn.fetchrow(
                """
                SELECT instrument_token,
                       tradingsymbol,
                       name,
                       segment,
                       instrument_type,
                       exchange,
                       lot_size,
                       tick_size
                  FROM instrument_registry
                 WHERE is_active = TRUE
                   AND (
                        upper(tradingsymbol) = ANY($1)
                     OR replace(upper(tradingsymbol), ' ', '') = ANY($1)
                     OR upper(name) = ANY($1)
                     OR replace(upper(name), ' ', '') = ANY($1)
                   )
              ORDER BY last_refreshed_at DESC
                 LIMIT 1
                """,
                symbol_array,
            )

            price_row = await conn.fetchrow(
                """
                SELECT time, close
                  FROM minute_bars
                 WHERE symbol = $1
                   AND resolution = 1
              ORDER BY time DESC
                 LIMIT 1
                """,
                symbol_norm,
            )

            futures_rows = await conn.fetch(
                """
                SELECT instrument_token,
                       tradingsymbol,
                       expiry,
                       lot_size,
                       tick_size,
                       exchange,
                       segment
                  FROM instrument_registry
                 WHERE is_active = TRUE
                   AND segment = 'NFO-FUT'
                   AND (
                        upper(name) = ANY($1)
                     OR replace(upper(name), ' ', '') = ANY($1)
                   )
                   AND expiry IS NOT NULL
              ORDER BY expiry::date ASC
                 LIMIT $2
                """,
                symbol_array,
                int(max_expiries),
            )

            expiry_rows = await conn.fetch(
                """
                SELECT DISTINCT expiry,
                                expiry::date AS expiry_date
                  FROM instrument_registry
                 WHERE is_active = TRUE
                   AND segment = 'NFO-OPT'
                   AND (
                        upper(name) = ANY($1)
                     OR replace(upper(name), ' ', '') = ANY($1)
                   )
                   AND expiry IS NOT NULL
              ORDER BY expiry_date ASC
                 LIMIT $2
                """,
                symbol_array,
                int(max_expiries),
            )

            last_price: Optional[float] = None
            last_price_ts: Optional[str] = None
            if price_row:
                close_value = price_row["close"]
                if close_value is not None:
                    last_price = float(close_value)
                ts_value = price_row["time"]
                if isinstance(ts_value, datetime):
                    ist_dt = ts_value.replace(tzinfo=IST_TIMEZONE)
                    last_price_ts = ist_dt.isoformat()
                elif ts_value is not None:
                    last_price_ts = str(ts_value)

            estimated_atm: Optional[float] = None
            if last_price is not None and strike_gap > 0:
                estimated_atm = round(last_price / float(strike_gap)) * float(strike_gap)

            futures_payload: List[Dict[str, Any]] = []
            for row in futures_rows:
                expiry_raw = row["expiry"]
                futures_payload.append(
                    {
                        "instrument_token": int(row["instrument_token"]),
                        "tradingsymbol": row["tradingsymbol"],
                        "expiry": str(expiry_raw) if expiry_raw is not None else None,
                        "lot_size": int(row["lot_size"]) if row["lot_size"] is not None else None,
                        "tick_size": float(row["tick_size"]) if row["tick_size"] is not None else None,
                        "exchange": row["exchange"],
                        "segment": row["segment"],
                    }
                )

            option_expiries = [row["expiry"] for row in expiry_rows if row["expiry"]]

            option_payload: List[Dict[str, Any]] = []
            option_query = """
                SELECT instrument_token,
                       tradingsymbol,
                       instrument_type,
                       strike,
                       expiry,
                       lot_size,
                       tick_size,
                       exchange,
                       segment
                  FROM instrument_registry
                 WHERE is_active = TRUE
                   AND segment = 'NFO-OPT'
                   AND expiry = $1
                   AND (
                        upper(name) = ANY($4)
                     OR replace(upper(name), ' ', '') = ANY($4)
                   )
                   AND strike BETWEEN $2 AND $3
              ORDER BY strike ASC, instrument_type ASC
            """

            for expiry in option_expiries:
                lower_bound = (
                    estimated_atm - strike_span if estimated_atm is not None else -1_000_000_000.0
                )
                upper_bound = (
                    estimated_atm + strike_span if estimated_atm is not None else 1_000_000_000.0
                )
                rows = await conn.fetch(
                    option_query,
                    expiry,
                    lower_bound,
                    upper_bound,
                    symbol_array,
                )
                strikes: Dict[float, Dict[str, Any]] = {}
                for row in rows:
                    strike_value_raw = row["strike"]
                    if strike_value_raw is None:
                        continue
                    strike_value = float(strike_value_raw)
                    bucket = strikes.setdefault(
                        strike_value,
                        {"strike": strike_value, "call": None, "put": None},
                    )
                    payload = {
                        "instrument_token": int(row["instrument_token"]),
                        "tradingsymbol": row["tradingsymbol"],
                        "lot_size": int(row["lot_size"]) if row["lot_size"] is not None else None,
                        "tick_size": float(row["tick_size"]) if row["tick_size"] is not None else None,
                        "exchange": row["exchange"],
                        "segment": row["segment"],
                    }
                    side = row["instrument_type"]
                    if side == "CE":
                        bucket["call"] = payload
                    elif side == "PE":
                        bucket["put"] = payload

                if not strikes:
                    continue

                ordered = sorted(strikes.values(), key=lambda item: item["strike"])
                atm_from_chain: Optional[float] = None
                if last_price is not None:
                    atm_from_chain = min(
                        (entry["strike"] for entry in ordered),
                        key=lambda strike_val: abs(strike_val - last_price),
                    )

                option_payload.append(
                    {
                        "expiry": str(expiry),
                        "atm_strike": atm_from_chain if atm_from_chain is not None else estimated_atm,
                        "strikes": ordered,
                    }
                )

        underlying_payload: Optional[Dict[str, Any]] = None
        if underlying_row:
            underlying_payload = {
                "instrument_token": int(underlying_row["instrument_token"]),
                "tradingsymbol": underlying_row["tradingsymbol"],
                "name": underlying_row["name"],
                "segment": underlying_row["segment"],
                "instrument_type": underlying_row["instrument_type"],
                "exchange": underlying_row["exchange"],
                "lot_size": int(underlying_row["lot_size"]) if underlying_row["lot_size"] is not None else None,
                "tick_size": float(underlying_row["tick_size"]) if underlying_row["tick_size"] is not None else None,
                "last_price": last_price,
                "last_price_ts": last_price_ts,
                "symbol": symbol_norm,
            }

        return {
            "symbol": symbol_norm,
            "underlying": underlying_payload,
            "futures": futures_payload,
            "options": option_payload,
            "meta": {
                "otm_levels": ladder_levels,
                "expiry_limit": max_expiries,
                "strike_gap": strike_gap,
                "redis_channels": {
                    "options": settings.fo_options_channel,
                    "underlying": settings.fo_underlying_channel,
                },
            },
        }

    
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

    async def get_next_expiries(self, symbol: str, limit: int = 2) -> List[date]:
        """
        Get next N expiries for a symbol from fo_option_strike_bars.
        Used as default when expiries not specified.
        """
        if not self.pool:
            return []

        symbol_norm = _normalize_symbol(symbol)
        query = """
            SELECT DISTINCT expiry
            FROM fo_option_strike_bars
            WHERE symbol = $1
              AND expiry >= CURRENT_DATE
            ORDER BY expiry
            LIMIT $2
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, symbol_norm, limit)
        return [row['expiry'] for row in rows]

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

    async def latest_ml_bar_time(self, symbol: str, timeframe: str) -> Optional[datetime]:
        sql = """
            SELECT time
            FROM minute_bars
            WHERE symbol = $1 AND resolution = $2
            ORDER BY time DESC
            LIMIT 1
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                sql,
                _normalize_symbol(symbol),
                _timeframe_to_resolution(timeframe),
            )
        return row["time"] if row else None

    async def latest_option_bucket_time(self, symbol: str, timeframe: str) -> Optional[datetime]:
        sql = """
            SELECT bucket_time
            FROM fo_option_strike_bars
            WHERE symbol = $1 AND timeframe = $2
            ORDER BY bucket_time DESC
            LIMIT 1
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(sql, _normalize_symbol(symbol), _normalize_timeframe(timeframe))
        return row["bucket_time"] if row else None

    async def latest_futures_bar_time(self, symbol: str, contract: str, timeframe: str) -> Optional[datetime]:
        sql = """
            SELECT time
            FROM futures_bars
            WHERE symbol = $1 AND contract = $2 AND resolution = $3
            ORDER BY time DESC
            LIMIT 1
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                sql,
                _normalize_symbol(symbol),
                contract,
                _timeframe_to_resolution(timeframe),
            )
        return row["time"] if row else None

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
