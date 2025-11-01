from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone, tzinfo
from typing import Dict, List, Optional
try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None

from .config import get_settings
from .database import DataManager
from .ticker_client import TickerServiceClient

logger = logging.getLogger(__name__)
settings = get_settings()


IST_TZ: tzinfo = ZoneInfo("Asia/Kolkata") if ZoneInfo else timezone(timedelta(hours=5, minutes=30))


def _utc_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _ensure_naive_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def _ensure_naive_ist(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(IST_TZ).replace(tzinfo=None)


class BackfillManager:
    def __init__(
        self,
        data_manager: DataManager,
        ticker_client: TickerServiceClient,
    ) -> None:
        self._dm = data_manager
        self._client = ticker_client
        self._enabled = settings.backfill_enabled
        self._interval = settings.backfill_check_interval_seconds
        self._gap_threshold = timedelta(minutes=settings.backfill_gap_threshold_minutes)
        self._max_batch = timedelta(minutes=settings.backfill_max_batch_minutes)
        self._option_expiry_limit = settings.fo_option_expiry_window
        self._running = False
        self._recent_failures: Dict[int, datetime] = {}
        self._failure_cooldown = timedelta(minutes=30)  # configurable


    async def run(self) -> None:
        if not self._enabled:
            logger.info("BackfillManager disabled via configuration")
            return
        self._running = True
        logger.info("BackfillManager started | interval=%ss", self._interval)
        while self._running:
            start_time = datetime.utcnow()
            try:
                await self._tick()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("Backfill tick failed: %s", exc, exc_info=True)
            elapsed = (datetime.utcnow() - start_time).total_seconds()
            sleep_for = max(1.0, self._interval - elapsed)
            await asyncio.sleep(sleep_for)

    async def shutdown(self) -> None:
        self._running = False

    async def _tick(self) -> None:
        now = datetime.utcnow()
        metadata = await self._dm.get_nifty_monitor_metadata(
            settings.monitor_default_symbol,
            expiry_limit=self._option_expiry_limit,
        )
        if not metadata:
            logger.warning("Backfill tick skipped: no metadata available")
            return

        underlying_info = metadata.get("underlying")
        futures_info = metadata.get("futures", [])
        options_info = metadata.get("options", [])

        await self._backfill_underlying(underlying_info, now)
        underlying_symbol = (
            (underlying_info or {}).get("tradingsymbol")
            or (underlying_info or {}).get("name")
            or settings.monitor_default_symbol
        )
        await self._backfill_futures(underlying_symbol, futures_info, now)
        await self._backfill_options(underlying_symbol, options_info, now)

    async def _backfill_underlying(self, info: Optional[dict], now: datetime) -> None:
        if not info or not info.get("instrument_token"):
            logger.debug("Backfill underlying skipped: missing metadata")
            return
        symbol = info.get("tradingsymbol") or info.get("name") or settings.monitor_default_symbol
        instrument_token = info["instrument_token"]
        start = await self._dm.latest_ml_bar_time(symbol, "1min")
        await self._do_backfill_ohlc(symbol, instrument_token, start, now)

    async def _backfill_futures(self, underlying_symbol: str, futures: List[dict], now: datetime) -> None:
        if not futures:
            return
        for fut in futures:
            token = fut.get("instrument_token")
            contract = fut.get("tradingsymbol")
            if not token or not contract:
                continue
            expiry_raw = fut.get("expiry")
            expiry_date: Optional[date] = None
            if expiry_raw:
                try:
                    expiry_date = datetime.fromisoformat(str(expiry_raw)).date()
                except ValueError:
                    expiry_date = None

            last_time = await self._dm.latest_futures_bar_time(underlying_symbol, contract, "1min")
            window = self._compute_window(last_time, now)
            if not window:
                continue
            start, end = window
            candles = await self._fetch_history(token, start, end, include_greeks=True)
            rows = self._candles_to_future_rows(underlying_symbol, contract, expiry_date, candles)
            if not rows:
                continue
            await self._dm.upsert_futures_bars(rows)
            logger.info(
                "Backfilled futures | contract=%s count=%d range=%s->%s",
                contract,
                len(rows),
                start,
                end,
            )

    async def _backfill_options(self, symbol: str, options: List[dict], now: datetime) -> None:
        if not options:
            return
        latest_option_time = await self._dm.latest_option_bucket_time(symbol, "1min")
        window = self._compute_window(latest_option_time, now)
        if not window:
            return
        start, end = window
        for expiry_info in options:
            await self._backfill_option_expiry(symbol, expiry_info, start, end)

    async def _do_backfill_ohlc(
        self,
        symbol: str,
        instrument_token: int,
        last_time: Optional[datetime],
        now: datetime,
    ) -> None:
        window = self._compute_window(last_time, now)
        if not window:
            return
        start, end = window
        candles = await self._fetch_history(instrument_token, start, end, include_greeks=False)
        rows = self._candles_to_rows(symbol, candles)
        if not rows:
            return
        await self._dm.upsert_underlying_bars(rows)
        logger.info(
            "Backfilled OHLC | symbol=%s count=%d range=%s->%s",
            symbol,
            len(rows),
            start,
            end,
        )

    async def _backfill_option_expiry(self, symbol: str, expiry_info: dict, start: datetime, end: datetime) -> None:
        expiry = expiry_info.get("expiry")
        strikes = expiry_info.get("strikes") or []
        if not expiry or not strikes:
            return
        strike_rows: List[dict] = []
        metrics_map: Dict[datetime, Dict[str, object]] = {}

        for strike_info in strikes:
            strike_value = strike_info.get("strike")
            call = strike_info.get("call")
            put = strike_info.get("put")
            if not strike_value or (not call and not put):
                continue
            call_rows = await self._option_history(call, start, end)
            put_rows = await self._option_history(put, start, end)
            combined_times = set(call_rows.keys()) | set(put_rows.keys())
            for ts in sorted(combined_times):
                call_data = call_rows.get(ts)
                put_data = put_rows.get(ts)
                if not (call_data or put_data):
                    continue
                bucket_time = _ensure_naive_utc(ts).replace(tzinfo=timezone.utc)
                strike_rows.append(
                    {
                        "bucket_time": bucket_time,
                        "timeframe": "1min",
                        "symbol": symbol,
                        "expiry": expiry,
                        "strike": float(strike_value),
                        "underlying_close": call_data.get("underlying") if call_data else put_data.get("underlying"),
                        "call": call_data.get("stats") if call_data else {"iv": None, "delta": None, "gamma": None, "theta": None, "vega": None, "volume": 0.0, "oi": 0.0, "count": 0},
                        "put": put_data.get("stats") if put_data else {"iv": None, "delta": None, "gamma": None, "theta": None, "vega": None, "volume": 0.0, "oi": 0.0, "count": 0},
                    }
                )
                metric = metrics_map.setdefault(
                    bucket_time,
                    {
                        "bucket_time": bucket_time,
                        "timeframe": "1min",
                        "symbol": symbol,
                        "expiry": expiry,
                        "underlying_close": None,
                        "total_call_volume": 0.0,
                        "total_put_volume": 0.0,
                        "total_call_oi": 0.0,
                        "total_put_oi": 0.0,
                    },
                )
                if call_data:
                    metric["total_call_volume"] = metric.get("total_call_volume", 0.0) + call_data.get("volume", 0.0)
                    metric["total_call_oi"] = metric.get("total_call_oi", 0.0) + (call_data.get("stats", {}).get("oi") or 0.0)
                    metric["underlying_close"] = metric["underlying_close"] or call_data.get("underlying")
                if put_data:
                    metric["total_put_volume"] = metric.get("total_put_volume", 0.0) + put_data.get("volume", 0.0)
                    metric["total_put_oi"] = metric.get("total_put_oi", 0.0) + (put_data.get("stats", {}).get("oi") or 0.0)
                    metric["underlying_close"] = metric["underlying_close"] or put_data.get("underlying")

        if not strike_rows:
            return

        await self._dm.upsert_fo_strike_rows(strike_rows)

        metrics_payload: List[dict] = []
        for metric in metrics_map.values():
            call_vol = metric.get("total_call_volume") or 0.0
            put_vol = metric.get("total_put_volume") or 0.0
            metric["pcr"] = (put_vol / call_vol) if call_vol > 0 else None
            metric["max_pain_strike"] = None
            metrics_payload.append(metric)

        if metrics_payload:
            await self._dm.upsert_fo_expiry_metrics(metrics_payload)

        logger.info(
            "Backfilled option expiry | expiry=%s strikes=%d buckets=%d",
            expiry,
            len(strikes),
            len(metrics_payload),
        )

    async def _option_history(self, leg: Optional[dict], start: datetime, end: datetime) -> Dict[datetime, dict]:
        if not leg or not leg.get("instrument_token"):
            return {}

        token = leg["instrument_token"]
        if not self._dm.is_token_supported(token):
            logger.debug("Skipping unsupported option token %s", token)
            return {}

        candles = await self._fetch_history(token, start, end, include_greeks=True)
        mapped: Dict[datetime, dict] = {}
        for candle in candles:
            ts, stats = self._parse_option_candle(candle)
            if not ts:
                continue
            mapped[ts] = stats
        return mapped

    async def _fetch_history(
        self,
        instrument_token: int,
        start: datetime,
        end: datetime,
        include_greeks: bool = False,
    ) -> List[dict]:
        now = datetime.utcnow()

        # Skip if token is marked unsupported
        if not self._dm.is_token_supported(instrument_token):
            logger.debug("Skipping unsupported token %s", instrument_token)
            return []

        # Skip if token failed recently
        last_fail = self._recent_failures.get(instrument_token)
        if last_fail and (now - last_fail) < self._failure_cooldown:
            logger.debug("Skipping token %s due to recent failure at %s", instrument_token, last_fail.isoformat())
            return []

        params: Dict[str, object] = {
            "instrument_token": instrument_token,
            "interval": "minute",
            "from_ts": _utc_iso(start),
            "to_ts": _utc_iso(end),
        }
        if include_greeks:
            params["oi"] = "true"

        try:
            payload = await self._client.history(**params)
        except Exception as exc:
            logger.error("History fetch failed | token=%s error=%s", instrument_token, exc)
            self._recent_failures[instrument_token] = now
            self._dm.mark_token_no_history(instrument_token, str(exc))
            return []

        candles = payload.get("candles") if isinstance(payload, dict) else None
        if isinstance(candles, dict):
            candles = candles.get("data")

        if not candles:
            logger.warning("No candles returned for token %s", instrument_token)
            self._recent_failures[instrument_token] = now
            self._dm.mark_token_no_history(instrument_token, "no candles returned")
            return []

        return candles

    
    def _candles_to_rows(self, symbol: str, candles: List[object]) -> List[dict]:
        rows: List[dict] = []
        for candle in candles:
            ts, o, h, l, c, v = self._parse_ohlc_candle(candle)
            if not ts:
                continue
            rows.append(
                {
                    "symbol": symbol,
                    "timeframe": "1min",
                    "time": _ensure_naive_ist(ts),
                    "open": o,
                    "high": h,
                    "low": l,
                    "close": c,
                    "volume": v,
                    "metadata": {"source": "backfill", "timeframe": "1min"},
                }
            )
        return rows

    def _candles_to_future_rows(self, underlying: str, contract: str, expiry: Optional[date], candles: List[object]) -> List[dict]:
        rows: List[dict] = []
        for candle in candles:
            ts, o, h, l, c, v = self._parse_ohlc_candle(candle)
            if not ts:
                continue
            rows.append(
                {
                    "symbol": underlying,
                    "contract": contract,
                    "expiry": expiry,
                    "timeframe": "1min",
                    "time": _ensure_naive_ist(ts),
                    "open": o,
                    "high": h,
                    "low": l,
                    "close": c,
                    "volume": v,
                    "open_interest": self._extract_field(candle, "oi"),
                    "metadata": {
                        "source": "backfill",
                        "timeframe": "1min",
                        "contract": contract,
                    },
                }
            )
        return rows

    def _parse_ohlc_candle(self, candle: object):
        ts = o = h = l = c = v = None
        if isinstance(candle, (list, tuple)):
            if len(candle) >= 6:
                ts, o, h, l, c, v = candle[:6]
        elif isinstance(candle, dict):
            ts = candle.get("date") or candle.get("time")
            o = candle.get("open")
            h = candle.get("high")
            l = candle.get("low")
            c = candle.get("close")
            v = candle.get("volume")
        if not ts:
            return None, None, None, None, None, None
        try:
            ts_dt = datetime.fromisoformat(ts)
        except Exception:
            return None, None, None, None, None, None
        return ts_dt, float(o or 0), float(h or 0), float(l or 0), float(c or 0), int(v or 0)

    def _parse_option_candle(self, candle: object):
        ts_dt, o, h, l, c, v = self._parse_ohlc_candle(candle)
        if not ts_dt:
            return None, {}
        stats = {
            "stats": {
                "iv": self._extract_field(candle, "iv"),
                "delta": self._extract_field(candle, "delta"),
                "gamma": self._extract_field(candle, "gamma"),
                "theta": self._extract_field(candle, "theta"),
                "vega": self._extract_field(candle, "vega"),
                "volume": float(v or 0),
                "oi": self._extract_field(candle, "oi"),
                "count": 1,
            },
            "volume": float(v or 0),
            "underlying": self._extract_field(candle, "underlying"),
        }
        return ts_dt, stats

    def _extract_field(self, candle: object, key: str) -> Optional[float]:
        if isinstance(candle, dict):
            value = candle.get(key)
            try:
                return float(value) if value is not None else None
            except (TypeError, ValueError):
                return None
        if isinstance(candle, (list, tuple)):
            # best effort: option history sometimes returns extended list
            named = {
                6: "oi",
                7: "iv",
                8: "delta",
                9: "gamma",
                10: "theta",
                11: "vega",
            }
            index = None
            for idx, name in named.items():
                if name == key and idx < len(candle):
                    index = idx
                    break
            if index is not None:
                try:
                    return float(candle[index])
                except (TypeError, ValueError):
                    return None
        return None

    def _compute_window(self, last_time: Optional[datetime], now: datetime) -> Optional[tuple[datetime, datetime]]:
        now = _ensure_naive_utc(now)
        if last_time is None:
            start = now - self._max_batch
        else:
            start = _ensure_naive_utc(last_time) + timedelta(minutes=1)

        if start > now:
            return None

        if (now - start) < self._gap_threshold:
            return None

        end = min(now, start + self._max_batch)
        return start, end

    async def backfill_instrument_immediate(self, instrument_token: int) -> None:
        """
        Trigger immediate backfill for a newly subscribed instrument.
        Fetches last 2 hours of historical data.

        Called by subscription event listener when new instrument is subscribed.
        """
        try:
            logger.info(f"Starting immediate backfill for instrument token {instrument_token}")

            # Get instrument details from database
            instrument = await self._get_instrument_details(instrument_token)
            if not instrument:
                logger.warning(f"Instrument {instrument_token} not found in database, skipping immediate backfill")
                return

            # Determine time window (last 2 hours)
            now = datetime.utcnow()
            start = now - timedelta(hours=2)

            # Determine instrument type and backfill accordingly
            segment = instrument.get("segment", "")
            tradingsymbol = instrument.get("tradingsymbol", "")

            if segment == "INDICES":
                # Underlying index
                await self._immediate_backfill_underlying(tradingsymbol, instrument_token, start, now)

            elif segment in ["NFO-FUT", "BFO-FUT", "MCX-FUT"]:
                # Futures contract
                await self._immediate_backfill_future(instrument, start, now)

            elif segment in ["NFO-OPT", "BFO-OPT"]:
                # Options contract - trigger full expiry backfill
                await self._immediate_backfill_option(instrument, start, now)

            else:
                logger.warning(f"Unknown segment {segment} for token {instrument_token}, attempting generic OHLC backfill")
                await self._immediate_backfill_generic(tradingsymbol, instrument_token, start, now)

            logger.info(f"Immediate backfill completed for instrument {instrument_token} ({tradingsymbol})")

        except Exception as e:
            logger.error(f"Immediate backfill failed for token {instrument_token}: {e}", exc_info=True)

    async def _get_instrument_details(self, instrument_token: int) -> Optional[dict]:
        """Query database for instrument details"""
        try:
            query = """
                SELECT instrument_token, tradingsymbol, name, expiry, strike, instrument_type, segment, exchange
                FROM instruments
                WHERE instrument_token = $1
                LIMIT 1
            """
            async with self._dm.pool.acquire() as conn:
                row = await conn.fetchrow(query, instrument_token)
                if row:
                    return dict(row)
            return None
        except Exception as e:
            logger.error(f"Failed to fetch instrument details for token {instrument_token}: {e}")
            return None

    async def _immediate_backfill_underlying(
        self,
        symbol: str,
        instrument_token: int,
        start: datetime,
        end: datetime
    ) -> None:
        """Backfill underlying index data"""
        try:
            candles = await self._fetch_history(instrument_token, start, end, include_greeks=False)
            if not candles:
                logger.warning(f"No candles returned for underlying {symbol}")
                return

            rows = self._candles_to_rows(symbol, candles)
            if rows:
                await self._dm.upsert_underlying_bars(rows)
                logger.info(f"Immediate backfill: underlying {symbol} - {len(rows)} bars")
        except Exception as e:
            logger.error(f"Failed to backfill underlying {symbol}: {e}", exc_info=True)

    async def _immediate_backfill_future(
        self,
        instrument: dict,
        start: datetime,
        end: datetime
    ) -> None:
        """Backfill futures contract data"""
        try:
            instrument_token = instrument.get("instrument_token")
            tradingsymbol = instrument.get("tradingsymbol")

            # Extract underlying symbol from tradingsymbol (e.g., NIFTY25NOVFUT -> NIFTY50)
            # This is a simplification - adjust based on your naming conventions
            underlying_symbol = settings.monitor_default_symbol

            expiry_raw = instrument.get("expiry")
            expiry_date: Optional[date] = None
            if expiry_raw:
                try:
                    if isinstance(expiry_raw, str):
                        expiry_date = datetime.fromisoformat(expiry_raw).date()
                    elif isinstance(expiry_raw, date):
                        expiry_date = expiry_raw
                    elif isinstance(expiry_raw, datetime):
                        expiry_date = expiry_raw.date()
                except (ValueError, AttributeError):
                    logger.warning(f"Could not parse expiry date: {expiry_raw}")

            candles = await self._fetch_history(instrument_token, start, end, include_greeks=True)
            if not candles:
                logger.warning(f"No candles returned for future {tradingsymbol}")
                return

            rows = self._candles_to_future_rows(underlying_symbol, tradingsymbol, expiry_date, candles)
            if rows:
                await self._dm.upsert_futures_bars(rows)
                logger.info(f"Immediate backfill: future {tradingsymbol} - {len(rows)} bars")
        except Exception as e:
            logger.error(f"Failed to backfill future {instrument.get('tradingsymbol')}: {e}", exc_info=True)

    async def _immediate_backfill_option(
        self,
        instrument: dict,
        start: datetime,
        end: datetime
    ) -> None:
        """
        Backfill option contract data.

        Note: Options are typically backfilled as part of an expiry group.
        For immediate backfill, we'll fetch just this option's data and store it.
        The full expiry metrics will be updated in the next scheduled backfill cycle.
        """
        try:
            instrument_token = instrument.get("instrument_token")
            tradingsymbol = instrument.get("tradingsymbol")

            # For now, log that we received the option subscription
            # The full option chain backfill will happen in the next scheduled cycle
            # This is because options require coordinated backfill across strikes for metrics

            logger.info(
                f"Option subscription detected: {tradingsymbol} (token: {instrument_token}). "
                f"Full option chain backfill will occur in next scheduled cycle."
            )

            # Optionally: fetch basic OHLC for this option to provide some immediate data
            candles = await self._fetch_history(instrument_token, start, end, include_greeks=True)
            if candles:
                logger.info(f"Fetched {len(candles)} candles for option {tradingsymbol}")
                # Note: Not storing individual option candles as they're typically stored
                # as part of strike distribution tables. This just validates data availability.

        except Exception as e:
            logger.error(f"Failed to process option {instrument.get('tradingsymbol')}: {e}", exc_info=True)

    async def _immediate_backfill_generic(
        self,
        symbol: str,
        instrument_token: int,
        start: datetime,
        end: datetime
    ) -> None:
        """Generic OHLC backfill for unknown instrument types"""
        try:
            candles = await self._fetch_history(instrument_token, start, end, include_greeks=False)
            if not candles:
                logger.warning(f"No candles returned for instrument {symbol}")
                return

            rows = self._candles_to_rows(symbol, candles)
            if rows:
                await self._dm.upsert_underlying_bars(rows)
                logger.info(f"Immediate backfill (generic): {symbol} - {len(rows)} bars")
        except Exception as e:
            logger.error(f"Failed to backfill instrument {symbol}: {e}", exc_info=True)
