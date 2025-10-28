from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from loguru import logger
from pydantic import BaseModel, Field

from .config import get_settings
from .generator import ticker_loop
from .instrument_registry import instrument_registry
from .redis_client import redis_publisher
from .subscription_store import SubscriptionRecord, subscription_store

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting %s", settings.app_name)
    await redis_publisher.connect()
    await ticker_loop.start()
    try:
        yield
    finally:
        await ticker_loop.stop()
        await redis_publisher.close()
        await instrument_registry.close()
        logger.info("Shutdown complete")


app = FastAPI(title="Ticker Service", lifespan=lifespan)


class SubscriptionRequest(BaseModel):
    instrument_token: int = Field(ge=1)
    requested_mode: str = Field(default="FULL")
    account_id: Optional[str] = None


class SubscriptionResponse(BaseModel):
    instrument_token: int
    tradingsymbol: str
    segment: str
    status: str
    requested_mode: str
    account_id: Optional[str]
    created_at: datetime
    updated_at: datetime


def _record_to_response(record: SubscriptionRecord) -> SubscriptionResponse:
    return SubscriptionResponse(
        instrument_token=record.instrument_token,
        tradingsymbol=record.tradingsymbol,
        segment=record.segment,
        status=record.status,
        requested_mode=record.requested_mode,
        account_id=record.account_id,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _to_timestamp(dt: datetime) -> int:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return int(dt.timestamp())


@app.get("/health")
async def health() -> dict[str, object]:
    return {
        "status": "ok",
        "environment": settings.environment,
        "ticker": ticker_loop.runtime_state(),
    }


@app.post("/admin/instrument-refresh")
async def instrument_refresh(force: bool = False) -> dict[str, object]:
    try:
        result = await ticker_loop.refresh_instruments(force=force)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {
        "force": force,
        **result,
    }


@app.get("/subscriptions", response_model=List[SubscriptionResponse])
async def list_subscriptions(status: Optional[str] = None) -> List[SubscriptionResponse]:
    status_normalised = status.lower() if status else None
    if status_normalised not in (None, "active", "inactive"):
        raise HTTPException(status_code=400, detail="status must be 'active', 'inactive', or omitted")
    if status_normalised == "active":
        records = await subscription_store.list_active()
    else:
        records = await subscription_store.list_all()
        if status_normalised == "inactive":
            records = [record for record in records if record.status == "inactive"]
    return [_record_to_response(record) for record in records]


@app.post("/subscriptions", response_model=SubscriptionResponse, status_code=201)
async def create_subscription(payload: SubscriptionRequest) -> SubscriptionResponse:
    requested_mode = (payload.requested_mode or "FULL").upper()
    if requested_mode not in {"FULL", "QUOTE", "LTP"}:
        raise HTTPException(status_code=400, detail="requested_mode must be one of FULL, QUOTE, LTP")

    metadata = await instrument_registry.fetch_metadata(payload.instrument_token)
    if not metadata or not metadata.is_active:
        raise HTTPException(status_code=404, detail="Instrument token not found or inactive in registry")

    tradingsymbol = metadata.tradingsymbol or metadata.name
    if not tradingsymbol:
        raise HTTPException(status_code=400, detail="Instrument metadata missing tradingsymbol/name")

    account_id = payload.account_id
    if account_id:
        accounts = ticker_loop.list_accounts()
        if account_id not in accounts:
            raise HTTPException(status_code=400, detail=f"Account '{account_id}' is not configured")

    await subscription_store.upsert(
        instrument_token=payload.instrument_token,
        tradingsymbol=tradingsymbol,
        segment=metadata.segment or "",
        requested_mode=requested_mode,
        account_id=account_id,
        status="active",
    )
    record = await subscription_store.get(payload.instrument_token)
    if not record:
        raise HTTPException(status_code=500, detail="Failed to persist subscription")

    try:
        await ticker_loop.reload_subscriptions()
    except Exception as exc:
        logger.exception("Subscription reload failed after create: %s", exc)
        raise HTTPException(status_code=502, detail=f"Failed to activate subscription: {exc}") from exc
    return _record_to_response(record)


@app.get("/history")
async def history(
    instrument_token: int,
    from_ts: datetime,
    to_ts: datetime,
    interval: str = "minute",
    account_id: Optional[str] = None,
    continuous: bool = False,
    oi: bool = False,
) -> dict[str, object]:
    if to_ts <= from_ts:
        raise HTTPException(status_code=400, detail="'to_ts' must be greater than 'from_ts'")

    metadata = await instrument_registry.fetch_metadata(instrument_token)
    if not metadata:
        raise HTTPException(status_code=404, detail="Instrument token not found in registry")

    from_epoch = _to_timestamp(from_ts)
    to_epoch = _to_timestamp(to_ts)

    try:
        candles = await ticker_loop.fetch_history(
            instrument_token=instrument_token,
            from_ts=from_epoch,
            to_ts=to_epoch,
            interval=interval,
            account_id=account_id,
            continuous=continuous,
            oi=oi,
        )
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Historical fetch failed: {exc}") from exc

    for candle in candles:
        ts = candle.get("date")
        if isinstance(ts, datetime):
            candle["date"] = ts.isoformat()

    return {
        "instrument_token": instrument_token,
        "tradingsymbol": metadata.tradingsymbol or metadata.name,
        "segment": metadata.segment,
        "interval": interval,
        "from_ts": from_ts,
        "to_ts": to_ts,
        "candles": candles,
    }


@app.delete("/subscriptions/{instrument_token}", response_model=SubscriptionResponse)
async def delete_subscription(instrument_token: int) -> SubscriptionResponse:
    record = await subscription_store.get(instrument_token)
    if not record:
        raise HTTPException(status_code=404, detail="Subscription not found")
    changed = await subscription_store.deactivate(instrument_token)
    if not changed:
        raise HTTPException(status_code=404, detail="Subscription not found or already inactive")
    record = await subscription_store.get(instrument_token)
    if not record:
        raise HTTPException(status_code=500, detail="Failed to fetch updated subscription")
    try:
        await ticker_loop.reload_subscriptions()
    except Exception as exc:
        logger.exception("Subscription reload failed after delete: %s", exc)
        raise HTTPException(status_code=502, detail=f"Failed to apply subscription removal: {exc}") from exc
    return _record_to_response(record)
