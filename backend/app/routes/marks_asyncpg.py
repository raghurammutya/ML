# app/routes/marks_asyncpg.py
from typing import List, Optional
from fastapi import APIRouter, Query, HTTPException, Request
from pydantic import BaseModel, field_validator
import asyncpg
import os

router = APIRouter()

# ---------- Pydantic ----------
class MarksQuery(BaseModel):
    symbol: str
    resolution: str
    from_ts: int
    to_ts: int

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, v: str) -> str:
        s = v.strip().upper()
        aliases = {
            "NIFTY": "NIFTY",
            "NIFTY50": "NIFTY",
            "NSE:NIFTY50": "NIFTY",
            "NSE:NIFTY": "NIFTY",
            "^NSEI": "NIFTY",
        }
        return aliases.get(s, s)

    @field_validator("resolution")
    @classmethod
    def normalize_resolution(cls, v: str) -> str:
        r = v.strip().lower()
        # canonicalize to DB style "Xmin"
        if r.isdigit():
            return f"{int(r)}min"
        if r.endswith("m") and r[:-1].isdigit():
            return f"{int(r[:-1])}min"
        # e.g. raw seconds like "120" for 2min, "180" for 3min, "300" for 5min
        if r.isdigit() and int(r) in (60,120,180,300,600,900,1800,3600):
            return f"{int(r)//60}min"
        # Handle hourly and daily
        if r == "60" or r == "1h" or r == "60min":
            return "1hour"
        if r == "1d" or r == "1440" or r == "1440min":
            return "1day"
        # if already like "15min" keep it
        return r

    def as_seconds_window(self) -> tuple[int, int]:
        f, t = self.from_ts, self.to_ts
        # accept seconds or milliseconds
        if f >= 10**12 or t >= 10**12:
            return f // 1000, t // 1000
        return f, t


class MarkPoint(BaseModel):
    id: str
    time: int          # epoch seconds for TradingView
    color: Optional[str] = None
    text: Optional[str] = None


class MarksResponse(BaseModel):
    marks: List[MarkPoint] = []


# ---------- Connection helper (asyncpg pool in app.state) ----------
POOL_KEY = "pg_pool"

async def get_pool(request: Request) -> asyncpg.Pool:
    pool: asyncpg.Pool = getattr(request.app.state, POOL_KEY, None)
    if pool is None:
        dsn = (
            os.getenv("DATABASE_URL")
            or os.getenv("TIMESCALE_DATABASE_URL")
            or os.getenv("POSTGRES_URL")
        )
        if not dsn:
            raise RuntimeError("DATABASE_URL/TIMESCALE_DATABASE_URL/POSTGRES_URL not set")
        request.app.state.__dict__[POOL_KEY] = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=5)
        pool = request.app.state.__dict__[POOL_KEY]
    return pool


# ---------- Route ----------
@router.get("/marks")
async def get_marks(
    request: Request,
    symbol: str = Query(...),
    resolution: str = Query(...),
    from_: int = Query(..., alias="from"),
    to_: int = Query(..., alias="to"),
    include_neutral: bool = Query(False, description="Include Neutral labels if true"),
    raw: bool = Query(False, description="Return raw data instead of formatted markers"),
):
    # Validate + normalize inputs
    try:
        payload = MarksQuery(symbol=symbol, resolution=resolution, from_ts=from_, to_ts=to_)
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))

    from_s, to_s = payload.as_seconds_window()
    timeframe = payload.resolution  # "5min" | "15min" etc.

    # Only show user-created labels (confidence = 1.0, displayed as 100%)
    label_pred = "AND label_confidence = 1.0"
    if not include_neutral:
        label_pred += " AND label <> 'Neutral'"

    # Convert IST timestamps to UTC epochs for TradingView
    # Database stores naive timestamps representing IST (UTC+5:30)
    # We need to subtract 19800 seconds (5.5 hours) from the epoch
    sql = f"""
        SELECT
          symbol,
          timeframe,
          (EXTRACT(EPOCH FROM "time")::bigint - 19800) AS time_s,
          label,
          label_confidence,
          "time" as db_time
        FROM ml_labeled_data
        WHERE symbol = $1
          AND timeframe = $2
          AND "time" BETWEEN (to_timestamp($3) + interval '5 hours 30 minutes') 
                         AND (to_timestamp($4) + interval '5 hours 30 minutes')
          {label_pred}
        ORDER BY time_s DESC
        LIMIT 2000
    """

    pool = await get_pool(request)
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, payload.symbol, timeframe, from_s, to_s)
    
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"Marks query: symbol={payload.symbol}, timeframe={timeframe}, from={from_s}, to={to_s}, found {len(rows)} rows, raw={raw}")
    logger.info(f"Debug: SQL query with label_pred='{label_pred}' - filtering for user labels only")

    # Return raw data if requested (for frontend processing)
    if raw:
        raw_data = []
        for r in rows:
            raw_data.append({
                "ts": int(r["time_s"]),
                "time": int(r["time_s"]),
                "label": r["label"],
                "label_confidence": float(r["label_confidence"]) if r["label_confidence"] is not None else None,
            })
        return raw_data

    # Return formatted markers (for TradingView)
    marks: List[MarkPoint] = []
    for i, r in enumerate(rows):
        txt = f"{r['label']}" if r["label"] is not None else "Label"
        if r["label_confidence"] is not None:
            try:
                txt += f" | p={float(r['label_confidence']):.2f}"
            except Exception:
                pass
        label_text = r['label']
        if label_text == "Bullish":
            color = "#00E676"  # bright green
        elif label_text == "Bearish":
            color = "#FF1744"  # bright red
        elif label_text == "Exit Bullish":
            color = "#FFA726"  # orange
        elif label_text == "Exit Bearish":
            color = "#42A5F5"  # blue
        else:
            color = "#9CA3AF"  # grey
        marks.append(MarkPoint(
            id=f"ml-{r['time_s']}-{i}",
            time=int(r["time_s"]),
            text=txt,
            color=color
        ))

    return MarksResponse(marks=marks)


@router.get("/marks/raw")
async def get_marks_raw(
    request: Request,
    symbol: str = Query(...),
    resolution: str = Query(...),
    from_: int = Query(..., alias="from"),
    to_: int = Query(..., alias="to"),
    include_neutral: bool = Query(False, description="Include Neutral labels if true"),
):
    """Get raw marks data for frontend processing"""
    # Validate + normalize inputs
    try:
        payload = MarksQuery(symbol=symbol, resolution=resolution, from_ts=from_, to_ts=to_)
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))

    from_s, to_s = payload.as_seconds_window()
    timeframe = payload.resolution  # "5min" | "15min" etc.

    # Only show user-created labels (confidence = 1.0, displayed as 100%)
    label_pred = "AND label_confidence = 1.0"
    if not include_neutral:
        label_pred += " AND label <> 'Neutral'"

    # Convert IST timestamps to UTC epochs for TradingView
    # Database stores naive timestamps representing IST (UTC+5:30)
    # We need to subtract 19800 seconds (5.5 hours) from the epoch
    sql = f"""
        SELECT
          symbol,
          timeframe,
          (EXTRACT(EPOCH FROM "time")::bigint - 19800) AS time_s,
          label,
          label_confidence,
          "time" as db_time
        FROM ml_labeled_data
        WHERE symbol = $1
          AND timeframe = $2
          AND "time" BETWEEN (to_timestamp($3) + interval '5 hours 30 minutes') 
                         AND (to_timestamp($4) + interval '5 hours 30 minutes')
          {label_pred}
        ORDER BY time_s DESC
        LIMIT 2000
    """

    pool = await get_pool(request)
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, payload.symbol, timeframe, from_s, to_s)
    
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"Raw marks query: symbol={payload.symbol}, timeframe={timeframe}, from={from_s}, to={to_s}, found {len(rows)} rows")

    # Return raw data for frontend processing
    raw_data = []
    for r in rows:
        raw_data.append({
            "ts": int(r["time_s"]),
            "time": int(r["time_s"]),
            "label": r["label"],
            "label_confidence": float(r["label_confidence"]) if r["label_confidence"] is not None else None,
        })
    
    return raw_data
