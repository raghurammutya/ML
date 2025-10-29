from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Sequence, TYPE_CHECKING

from loguru import logger
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from .config import get_settings
from .schema import Instrument
try:  # pragma: no cover - stdlib availability
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None
IST = ZoneInfo("Asia/Kolkata") if ZoneInfo else None

if TYPE_CHECKING:  # pragma: no cover - typing aid only
    from .kite.client import KiteClient


@dataclass(slots=True)
class InstrumentMetadata:
    instrument_token: int
    tradingsymbol: str
    name: str
    segment: str
    instrument_type: str
    strike: Optional[float]
    expiry: Optional[str]
    tick_size: Optional[float]
    lot_size: Optional[int]
    exchange: str
    is_active: bool
    last_refreshed_at: datetime

    def to_instrument(self) -> Instrument:
        return Instrument(
            symbol=self.name or self.tradingsymbol,
            instrument_token=self.instrument_token,
            tradingsymbol=self.tradingsymbol,
            segment=self.segment,
            exchange=self.exchange,
            strike=self.strike,
            expiry=self.expiry,
            instrument_type=self.instrument_type or "EQ",
            lot_size=self.lot_size,
            tick_size=self.tick_size,
        )


class InstrumentRegistry:
    """
    Maintains a TimescaleDB/PostgreSQL-backed registry of tradable instruments sourced from Kite.
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._conninfo = self._build_conninfo()
        self._pool: AsyncConnectionPool | None = None
        self._cache: Dict[int, InstrumentMetadata] = {}
        self._lock = asyncio.Lock()
        self._initialised = False
        self._last_refresh: datetime | None = None
        self._cache_expiry: Dict[int, datetime] = {}

    # ------------------------------------------------------------------ lifecycle helpers
    async def initialise(self) -> None:
        if self._initialised:
            return
        async with self._lock:
            if self._initialised:
                return
            self._pool = AsyncConnectionPool(
                conninfo=self._conninfo,
                min_size=1,
                max_size=5,
                timeout=10,
            )
            await self._pool.open()
            await self._ensure_schema()
            await self._reload_cache()
            self._initialised = True
            logger.debug("Instrument registry initialised using %s", self._conninfo)

    async def close(self) -> None:
        async with self._lock:
            if self._pool:
                await self._pool.close()
                self._pool = None
            self._cache = {}
            self._initialised = False
            self._last_refresh = None

    async def ensure_cache_loaded(self) -> None:
        if not self._cache:
            await self._reload_cache()

    def is_stale(self) -> bool:
        if not self._last_refresh:
            return True
        now_utc = datetime.now(timezone.utc)
        hours = self._settings.instrument_refresh_hours
        if hours and hours > 0:
            if now_utc - self._last_refresh >= timedelta(hours=hours):
                return True
        if IST:
            last_local = self._last_refresh.astimezone(IST)
            now_local = now_utc.astimezone(IST)
            if last_local.date() < now_local.date():
                return True
        return False

    def last_refresh_at(self) -> Optional[datetime]:
        return self._last_refresh

    # ------------------------------------------------------------------ refresh pipeline
    async def refresh_with_client(self, client: "KiteClient") -> None:
        await self.initialise()
        await client.ensure_session()

        segments = self._settings.instrument_segments
        logger.info("Refreshing instrument registry | segments=%s", ",".join(segments))

        async def _download(segment: str) -> List[Dict[str, object]]:
            try:
                instruments = await client.fetch_instruments(segment)
                logger.debug("Fetched %d instruments for segment=%s", len(instruments), segment)
                return instruments
            except Exception as exc:
                logger.exception("Failed to fetch instruments for segment=%s: %s", segment, exc)
                return []

        downloads = await asyncio.gather(*[_download(segment) for segment in segments])
        payload = dict(zip(segments, downloads))

        async with self._lock:
            await self._apply_refresh(payload)
            await self._reload_cache()

        logger.info("Instrument registry refresh complete | records=%d", len(self._cache))

    async def _apply_refresh(self, payload: Dict[str, Sequence[Dict[str, object]]]) -> None:
        if not self._pool:
            raise RuntimeError("Instrument registry pool not initialised")
        timestamp = datetime.now(timezone.utc)
        segments = list(payload.keys())

        async with self._pool.connection() as conn:
            async with conn.cursor() as cur:
                if segments:
                    await cur.execute(
                        "UPDATE instrument_registry "
                        "SET is_active = FALSE, last_refreshed_at = %s "
                        "WHERE segment = ANY(%s)",
                        (timestamp, segments),
                    )

                insert_sql = (
                    "INSERT INTO instrument_registry ("
                    "instrument_token, tradingsymbol, name, segment, instrument_type, strike, "
                    "expiry, tick_size, lot_size, exchange, is_active, last_refreshed_at"
                    ") VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT (instrument_token) DO UPDATE SET "
                    "tradingsymbol = EXCLUDED.tradingsymbol, "
                    "name = EXCLUDED.name, "
                    "segment = EXCLUDED.segment, "
                    "instrument_type = EXCLUDED.instrument_type, "
                    "strike = EXCLUDED.strike, "
                    "expiry = EXCLUDED.expiry, "
                    "tick_size = EXCLUDED.tick_size, "
                    "lot_size = EXCLUDED.lot_size, "
                    "exchange = EXCLUDED.exchange, "
                    "is_active = EXCLUDED.is_active, "
                    "last_refreshed_at = EXCLUDED.last_refreshed_at"
                )

                rows: List[tuple] = []
                for segment, instruments in payload.items():
                    for raw in instruments:
                        record = self._normalise_record(raw, segment, timestamp)
                        rows.append(
                            (
                                record.instrument_token,
                                record.tradingsymbol,
                                record.name,
                                record.segment,
                                record.instrument_type,
                                record.strike,
                                record.expiry,
                                record.tick_size,
                                record.lot_size,
                                record.exchange,
                                True,
                                record.last_refreshed_at,
                            )
                        )

                if rows:
                    await cur.executemany(insert_sql, rows)
                await conn.commit()

        self._last_refresh = timestamp

    # ------------------------------------------------------------------ queries
    async def option_chain(
        self,
        underlying: str,
        expiry_window: int,
        otm_levels: int,
        strike_step: int,
        spot_price: Optional[float],
    ) -> List[Instrument]:
        await self.initialise()
        await self.ensure_cache_loaded()
        records = [
            meta
            for meta in self._cache.values()
            if meta.is_active
            and meta.name
            and meta.name.upper() == underlying.upper()
            and meta.instrument_type in ("CE", "PE")
        ]
        if not records:
            return []

        expiries = sorted({meta.expiry for meta in records if meta.expiry})
        if expiry_window > 0:
            expiries = expiries[:expiry_window]
        records = [meta for meta in records if meta.expiry in expiries]

        strikes = sorted({meta.strike for meta in records if meta.strike is not None})
        if not strikes:
            return [meta.to_instrument() for meta in records]

        if spot_price and strike_step > 0:
            atm_strike = round(spot_price / strike_step) * strike_step
        else:
            midpoint = len(strikes) // 2
            atm_strike = strikes[midpoint] if strikes else 0.0

        if strike_step <= 0:
            strike_targets = {round(float(strike), 2) for strike in strikes}
        else:
            strike_targets = {
                round(atm_strike + strike_step * offset, 2)
                for offset in range(-otm_levels, otm_levels + 1)
            }

        def _strike_key(meta: InstrumentMetadata) -> Optional[float]:
            if meta.strike is None:
                return None
            return round(float(meta.strike), 2)

        filtered = [
            meta
            for meta in records
            if not strike_targets or (_strike_key(meta) in strike_targets)
        ]
        filtered.sort(key=lambda meta: (meta.expiry or "", meta.strike or 0.0, meta.instrument_type))
        return [meta.to_instrument() for meta in filtered]

    def get_metadata(self, instrument_token: int) -> Optional[InstrumentMetadata]:
        metadata = self._cache.get(instrument_token)
        if not metadata:
            return None
        ttl = timedelta(seconds=self._settings.instrument_cache_ttl_seconds)
        expires_at = self._cache_expiry.get(instrument_token)
        if expires_at and datetime.now(timezone.utc) > expires_at:
            self._cache.pop(instrument_token, None)
            self._cache_expiry.pop(instrument_token, None)
            return None
        return metadata

    async def fetch_metadata(self, instrument_token: int) -> Optional[InstrumentMetadata]:
        metadata = self.get_metadata(instrument_token)
        if metadata:
            return metadata
        await self.initialise()
        if not self._pool:
            raise RuntimeError("Instrument registry pool not initialised")
        async with self._pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    SELECT instrument_token,
                           tradingsymbol,
                           name,
                           segment,
                           instrument_type,
                           strike,
                           expiry,
                           tick_size,
                           lot_size,
                           exchange,
                           is_active,
                           last_refreshed_at
                    FROM instrument_registry
                    WHERE instrument_token=%s
                    """,
                    (instrument_token,),
                )
                row = await cur.fetchone()
        if not row:
            return None

        last_refreshed = row["last_refreshed_at"]
        if isinstance(last_refreshed, str):
            last_refreshed_dt = datetime.fromisoformat(last_refreshed)
        else:
            last_refreshed_dt = last_refreshed
        if last_refreshed_dt and last_refreshed_dt.tzinfo is None:
            last_refreshed_dt = last_refreshed_dt.replace(tzinfo=timezone.utc)

        metadata = InstrumentMetadata(
            instrument_token=int(row["instrument_token"]),
            tradingsymbol=row["tradingsymbol"] or "",
            name=row["name"] or "",
            segment=row["segment"] or "",
            instrument_type=row["instrument_type"] or "",
            strike=float(row["strike"]) if row["strike"] is not None else None,
            expiry=row["expiry"],
            tick_size=float(row["tick_size"]) if row["tick_size"] is not None else None,
            lot_size=int(row["lot_size"]) if row["lot_size"] is not None else None,
            exchange=row["exchange"] or "",
            is_active=bool(row["is_active"]),
            last_refreshed_at=last_refreshed_dt,
        )
        ttl = timedelta(seconds=self._settings.instrument_cache_ttl_seconds)
        self._cache[instrument_token] = metadata
        self._cache_expiry[instrument_token] = datetime.now(timezone.utc) + ttl
        return metadata
    def cache_metadata(self, metadata: InstrumentMetadata) -> None:
        ttl = timedelta(seconds=self._settings.instrument_cache_ttl_seconds)
        self._cache[metadata.instrument_token] = metadata
        self._cache_by_token[metadata.instrument_token] = metadata
        self._cache_expiry[metadata.instrument_token] = datetime.now(timezone.utc) + ttl

    # ------------------------------------------------------------------ internals
    async def _ensure_schema(self) -> None:
        if not self._pool:
            raise RuntimeError("Instrument registry pool not initialised")
        async with self._pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS instrument_registry (
                        instrument_token BIGINT PRIMARY KEY,
                        tradingsymbol TEXT NOT NULL,
                        name TEXT,
                        segment TEXT,
                        instrument_type TEXT,
                        strike DOUBLE PRECISION,
                        expiry TEXT,
                        tick_size DOUBLE PRECISION,
                        lot_size INTEGER,
                        exchange TEXT,
                        is_active BOOLEAN NOT NULL DEFAULT TRUE,
                        last_refreshed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                await cur.execute(
                    "CREATE INDEX IF NOT EXISTS instrument_registry_name_idx ON instrument_registry(name)"
                )
                await cur.execute(
                    "CREATE INDEX IF NOT EXISTS instrument_registry_segment_idx ON instrument_registry(segment)"
                )
                await conn.commit()

    async def _reload_cache(self) -> None:
        if not self._pool:
            raise RuntimeError("Instrument registry pool not initialised")
        async with self._pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    SELECT instrument_token,
                           tradingsymbol,
                           name,
                           segment,
                           instrument_type,
                           strike,
                           expiry,
                           tick_size,
                           lot_size,
                           exchange,
                           is_active,
                           last_refreshed_at
                    FROM instrument_registry
                    """
                )
                rows = await cur.fetchall()

        cache: Dict[int, InstrumentMetadata] = {}
        latest: Optional[datetime] = self._last_refresh

        for row in rows:
            last_refreshed = row["last_refreshed_at"]
            if isinstance(last_refreshed, str):
                last_refreshed_dt = datetime.fromisoformat(last_refreshed)
            else:
                last_refreshed_dt = last_refreshed
            if last_refreshed_dt and last_refreshed_dt.tzinfo is None:
                last_refreshed_dt = last_refreshed_dt.replace(tzinfo=timezone.utc)

            strike = row["strike"]
            tick_size = row["tick_size"]
            lot_size = row["lot_size"]

            metadata = InstrumentMetadata(
                instrument_token=int(row["instrument_token"]),
                tradingsymbol=row["tradingsymbol"] or "",
                name=row["name"] or "",
                segment=row["segment"] or "",
                instrument_type=row["instrument_type"] or "",
                strike=float(strike) if strike is not None else None,
                expiry=row["expiry"],
                tick_size=float(tick_size) if tick_size is not None else None,
                lot_size=int(lot_size) if lot_size is not None else None,
                exchange=row["exchange"] or "",
                is_active=bool(row["is_active"]),
                last_refreshed_at=last_refreshed_dt,
            )
            cache[metadata.instrument_token] = metadata
            if last_refreshed_dt and (latest is None or last_refreshed_dt > latest):
                latest = last_refreshed_dt

        ttl = timedelta(seconds=self._settings.instrument_cache_ttl_seconds)
        expiry = datetime.now(timezone.utc)
        self._cache = cache
        self._cache_expiry = {token: expiry + ttl for token in cache.keys()}
        self._last_refresh = latest
        logger.debug("Instrument registry cache loaded | records=%d", len(cache))

    def _build_conninfo(self) -> str:
        parts = [
            f"host={self._settings.instrument_db_host}",
            f"port={self._settings.instrument_db_port}",
            f"dbname={self._settings.instrument_db_name}",
            f"user={self._settings.instrument_db_user}",
        ]
        if self._settings.instrument_db_password:
            parts.append(f"password={self._settings.instrument_db_password}")
        return " ".join(parts)

    @staticmethod
    def _normalise_record(
        raw: Dict[str, object],
        segment: str,
        refreshed_at: datetime,
    ) -> InstrumentMetadata:
        expiry = raw.get("expiry")
        if hasattr(expiry, "isoformat"):
            expiry_str = expiry.isoformat()
        elif expiry:
            expiry_str = str(expiry)
        else:
            expiry_str = None

        strike_raw = raw.get("strike")
        try:
            strike_value = float(strike_raw) if strike_raw is not None else None
        except (TypeError, ValueError):
            strike_value = None

        tick_raw = raw.get("tick_size")
        try:
            tick_size = float(tick_raw) if tick_raw is not None else None
        except (TypeError, ValueError):
            tick_size = None

        lot_raw = raw.get("lot_size")
        try:
            lot_size = int(lot_raw) if lot_raw is not None else None
        except (TypeError, ValueError):
            lot_size = None

        return InstrumentMetadata(
            instrument_token=int(raw["instrument_token"]),
            tradingsymbol=str(raw.get("tradingsymbol") or ""),
            name=str(raw.get("name") or ""),
            segment=str(raw.get("segment") or segment),
            instrument_type=str(raw.get("instrument_type") or ""),
            strike=strike_value,
            expiry=expiry_str,
            tick_size=tick_size,
            lot_size=lot_size,
            exchange=str(raw.get("exchange") or ""),
            is_active=True,
            last_refreshed_at=refreshed_at,
        )


instrument_registry = InstrumentRegistry()
