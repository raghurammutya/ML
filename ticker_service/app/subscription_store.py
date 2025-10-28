from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional, Sequence, Tuple

from loguru import logger
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from .config import get_settings


@dataclass(slots=True)
class SubscriptionRecord:
    instrument_token: int
    tradingsymbol: str
    segment: str
    status: str
    requested_mode: str
    account_id: Optional[str]
    created_at: datetime
    updated_at: datetime


class SubscriptionStore:
    def __init__(self) -> None:
        self._settings = get_settings()
        self._pool: AsyncConnectionPool | None = None
        self._lock = asyncio.Lock()
        self._initialised = False

    async def initialise(self) -> None:
        if self._initialised:
            return
        async with self._lock:
            if self._initialised:
                return
            self._pool = AsyncConnectionPool(
                conninfo=self._build_conninfo(),
                min_size=1,
                max_size=5,
                timeout=10,
            )
            await self._pool.open()
            await self._ensure_schema()
            self._initialised = True
            logger.debug("Subscription store initialised.")

    async def close(self) -> None:
        async with self._lock:
            if self._pool:
                await self._pool.close()
                self._pool = None
            self._initialised = False

    async def upsert(
        self,
        *,
        instrument_token: int,
        tradingsymbol: str,
        segment: str,
        requested_mode: str = "FULL",
        account_id: Optional[str] = None,
        status: str = "active",
    ) -> None:
        await self.initialise()
        if not self._pool:
            raise RuntimeError("Subscription store pool unavailable")
        now = datetime.now(timezone.utc)
        async with self._pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO instrument_subscriptions (
                        instrument_token,
                        tradingsymbol,
                        segment,
                        status,
                        requested_mode,
                        account_id,
                        created_at,
                        updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (instrument_token) DO UPDATE SET
                        tradingsymbol = EXCLUDED.tradingsymbol,
                        segment = EXCLUDED.segment,
                        status = EXCLUDED.status,
                        requested_mode = EXCLUDED.requested_mode,
                        account_id = EXCLUDED.account_id,
                        updated_at = EXCLUDED.updated_at
                    """,
                    (
                        instrument_token,
                        tradingsymbol,
                        segment,
                        status,
                        requested_mode,
                        account_id,
                        now,
                        now,
                    ),
                )
                await conn.commit()
        logger.debug(
            "Subscription upserted | token=%s status=%s account=%s",
            instrument_token,
            status,
            account_id,
        )

    async def update_account(self, instrument_token: int, account_id: Optional[str]) -> None:
        await self.initialise()
        if not self._pool:
            raise RuntimeError("Subscription store pool unavailable")
        now = datetime.now(timezone.utc)
        async with self._pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    UPDATE instrument_subscriptions
                    SET account_id=%s, updated_at=%s
                    WHERE instrument_token=%s
                    """,
                    (account_id, now, instrument_token),
                )
                await conn.commit()
        logger.debug("Subscription account updated | token=%s account=%s", instrument_token, account_id)

    async def deactivate(self, instrument_token: int) -> bool:
        await self.initialise()
        if not self._pool:
            raise RuntimeError("Subscription store pool unavailable")
        now = datetime.now(timezone.utc)
        async with self._pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    UPDATE instrument_subscriptions
                    SET status='inactive', updated_at=%s
                    WHERE instrument_token=%s
                    """,
                    (now, instrument_token),
                )
                changed = cur.rowcount
                await conn.commit()
        if changed:
            logger.debug("Subscription deactivated | token=%s", instrument_token)
        return bool(changed)

    async def list_active(self) -> List[SubscriptionRecord]:
        return await self._fetch("status=%s", ("active",))

    async def list_all(self) -> List[SubscriptionRecord]:
        return await self._fetch()

    async def get(self, instrument_token: int) -> Optional[SubscriptionRecord]:
        records = await self._fetch("instrument_token=%s", (instrument_token,))
        return records[0] if records else None

    async def _fetch(self, where: Optional[str] = None, params: Sequence[object] = ()) -> List[SubscriptionRecord]:
        await self.initialise()
        if not self._pool:
            raise RuntimeError("Subscription store pool unavailable")
        query = """
            SELECT instrument_token,
                   tradingsymbol,
                   segment,
                   status,
                   requested_mode,
                   account_id,
                   created_at,
                   updated_at
            FROM instrument_subscriptions
        """
        if where:
            query += f" WHERE {where}"
        async with self._pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                if params:
                    await cur.execute(query, tuple(params))
                else:
                    await cur.execute(query)
                rows = await cur.fetchall()
        records: List[SubscriptionRecord] = []
        for row in rows:
            records.append(
                SubscriptionRecord(
                    instrument_token=int(row["instrument_token"]),
                    tradingsymbol=row["tradingsymbol"],
                    segment=row["segment"],
                    status=row["status"],
                    requested_mode=row["requested_mode"],
                    account_id=row["account_id"],
                    created_at=self._ensure_tz(row["created_at"]),
                    updated_at=self._ensure_tz(row["updated_at"]),
                )
            )
        return records

    async def _ensure_schema(self) -> None:
        if not self._pool:
            raise RuntimeError("Subscription store pool unavailable")
        async with self._pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS instrument_subscriptions (
                        instrument_token BIGINT PRIMARY KEY,
                        tradingsymbol TEXT NOT NULL,
                        segment TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'active',
                        requested_mode TEXT NOT NULL DEFAULT 'FULL',
                        account_id TEXT,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                await cur.execute(
                    "CREATE INDEX IF NOT EXISTS instrument_subscriptions_status_idx ON instrument_subscriptions(status)"
                )
                await cur.execute(
                    "CREATE INDEX IF NOT EXISTS instrument_subscriptions_account_idx ON instrument_subscriptions(account_id)"
                )
                await conn.commit()

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
    def _ensure_tz(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value


subscription_store = SubscriptionStore()
