from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone, date, timedelta, tzinfo
from typing import Dict, List, Optional, Set, Tuple

import redis.asyncio as redis

from .config import Settings
from .database import DataManager, _normalize_timeframe
from .realtime import RealTimeHub
from .services.market_depth_analyzer import MarketDepthAnalyzer

logger = logging.getLogger(__name__)

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None

IST_TZ: tzinfo = ZoneInfo("Asia/Kolkata") if ZoneInfo else timezone(timedelta(hours=5, minutes=30))


def _timeframe_to_seconds(timeframe: str) -> int:
    tf = _normalize_timeframe(timeframe)
    if tf.endswith("min"):
        return max(60, int(tf[:-3]) * 60)
    if tf.endswith("hour"):
        return int(tf[:-4]) * 3600
    if tf.endswith("day"):
        return 86400
    if tf.endswith("week"):
        return 7 * 86400
    if tf.endswith("month"):
        return 30 * 86400
    if tf.isdigit():
        minutes = int(tf)
        return max(60, minutes * 60)
    raise ValueError(f"Unsupported timeframe: {timeframe}")


def _epoch_to_datetime(ts: int) -> datetime:
    return datetime.fromtimestamp(ts, tz=timezone.utc)


def _parse_expiry(raw: str) -> Optional[date]:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw).date()
    except ValueError:
        try:
            # Allow dd-MMM-YYYY style
            return datetime.strptime(raw, "%d-%b-%Y").date()
        except ValueError:
            logger.debug("Unable to parse expiry %s", raw)
            return None


@dataclass
class OptionStats:
    iv_sum: float = 0.0
    delta_sum: float = 0.0
    gamma_sum: float = 0.0
    theta_sum: float = 0.0
    vega_sum: float = 0.0
    volume_sum: float = 0.0
    oi_sum: float = 0.0
    count: int = 0

    def add(self, payload: Dict[str, float]) -> None:
        self.iv_sum += payload.get("iv", 0.0)
        self.delta_sum += payload.get("delta", 0.0)
        self.gamma_sum += payload.get("gamma", 0.0)
        self.theta_sum += payload.get("theta", 0.0)
        self.vega_sum += payload.get("vega", 0.0)
        self.volume_sum += payload.get("volume", 0.0)
        self.oi_sum += payload.get("oi", 0.0)
        self.count += 1

    def avg(self, field: str) -> Optional[float]:
        if self.count == 0:
            return None
        total = getattr(self, f"{field}_sum", None)
        if total is None:
            return None
        return total / self.count


@dataclass
class StrikeBucket:
    strikes: Dict[float, Dict[str, OptionStats]] = field(default_factory=lambda: defaultdict(lambda: {"CE": OptionStats(), "PE": OptionStats()}))
    underlying_close: Optional[float] = None
    # Store latest liquidity metrics per strike (updated on each tick with depth data)
    liquidity: Dict[float, Dict[str, object]] = field(default_factory=dict)


@dataclass
class UnderlyingBar:
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


class FOAggregator:
    def __init__(self, data_manager: DataManager, settings: Settings, hub: Optional[RealTimeHub] = None):
        self._dm = data_manager
        self._settings = settings
        self._hub = hub
        persisted = getattr(settings, "fo_persist_timeframes", None) or ["1min"]
        self._persist_timeframes: Set[str] = {
            _normalize_timeframe(tf) for tf in persisted
        }
        configured = settings.fo_timeframes or list(self._persist_timeframes)
        all_tfs: List[str] = []
        self._tf_seconds: Dict[str, int] = {}
        for tf in set(list(configured) + list(self._persist_timeframes)):
            normalized = _normalize_timeframe(tf)
            try:
                self._tf_seconds[normalized] = _timeframe_to_seconds(normalized)
                all_tfs.append(normalized)
            except ValueError:
                logger.warning("Skipping unsupported timeframe %s", tf)
        self._timeframes = sorted(set(all_tfs), key=lambda x: self._tf_seconds.get(x, 0))
        self._buffers: Dict[str, Dict[Tuple[str, date, int], StrikeBucket]] = {tf: {} for tf in self._timeframes}
        self._underlying_buffers: Dict[str, Dict[Tuple[str, int], UnderlyingBar]] = {tf: {} for tf in self._timeframes}

        # Initialize market depth analyzer for liquidity metrics
        # Use include_advanced=False for real-time performance
        self._depth_analyzer = MarketDepthAnalyzer(include_advanced=False)
        self._last_underlying: Dict[str, float] = {}
        self._lock = asyncio.Lock()
        # NEW: limit concurrent DB writes (tune the value as needed)
        self._persist_sem = asyncio.Semaphore(2)


    def _bucket_start(self, ts: int, seconds: int) -> int:
        return ts - (ts % seconds)

    async def handle_underlying(self, payload: Dict[str, object]) -> None:
        # Skip mock data - don't store it in the database
        if payload.get("is_mock"):
            return

        symbol = str(payload.get("symbol") or self._settings.fo_underlying)
        close = payload.get("close") or payload.get("price") or payload.get("last_price")
        if close is None:
            return
        try:
            close_val = float(close)
        except (TypeError, ValueError):
            logger.debug("Invalid close price in payload: %s", payload)
            return
        ts = int(payload.get("ts") or payload.get("timestamp") or datetime.now(timezone.utc).timestamp())
        volume_raw = payload.get("volume") or payload.get("vol") or 0.0
        try:
            volume_val = float(volume_raw)
        except (TypeError, ValueError):
            volume_val = 0.0

        # Use lock to protect data collection and conversion
        # This prevents race conditions between collection and persistence
        async with self._lock:
            self._last_underlying[symbol] = close_val
            self._update_underlying_buffers(symbol, close_val, volume_val, ts)
            underlying_flush = self._collect_underlying_flush(ts)
            flush_payloads = self._collect_flush_payloads(ts)

            # Convert data while holding lock to ensure consistency
            underlying_converted = self._convert_underlying_items(underlying_flush)

        # Persist after releasing lock
        # Note: flush_payloads data is already removed from buffers (via pop()),
        # so it's safe to persist after lock release
        await self._persist_underlying_bars(underlying_converted)
        await self._persist_batches(flush_payloads)

    async def handle_option(self, payload: Dict[str, object]) -> None:
        # Skip mock data - don't store it in the database
        if payload.get("is_mock"):
            return

        expiry = _parse_expiry(str(payload.get("expiry", "")))
        if not expiry:
            return
        symbol = str(payload.get("symbol") or self._settings.fo_underlying)
        option_type = str(payload.get("type") or "").upper()
        if option_type not in {"CE", "PE"}:
            return
        try:
            strike = float(payload.get("strike"))
        except (TypeError, ValueError):
            return
        ts = int(payload.get("ts") or payload.get("timestamp") or datetime.now(timezone.utc).timestamp())

        metrics = {
            "iv": float(payload.get("iv") or 0.0),
            "delta": float(payload.get("delta") or 0.0),
            "gamma": float(payload.get("gamma") or 0.0),
            "theta": float(payload.get("theta") or 0.0),
            "vega": float(payload.get("vega") or 0.0),
            "volume": float(payload.get("volume") or 0.0),
            "oi": float(payload.get("oi") or payload.get("open_interest") or 0.0),
        }

        # Extract and analyze market depth if available
        depth_data = payload.get("depth")
        if depth_data and isinstance(depth_data, dict):
            try:
                last_price = float(payload.get("price") or payload.get("last_price") or 0.0)
                if last_price > 0:
                    # Analyze market depth to compute liquidity metrics
                    analysis = self._depth_analyzer.analyze(
                        depth_data=depth_data,
                        last_price=last_price,
                        instrument_token=payload.get("token")
                    )

                    # Extract essential liquidity metrics
                    # These will be stored via database.py:_aggregate_liquidity_metrics()
                    metrics["liquidity"] = {
                        "score": analysis.liquidity.liquidity_score,
                        "tier": analysis.liquidity.liquidity_tier,
                        "spread_pct": analysis.spread.bid_ask_spread_pct,
                        "spread_abs": analysis.spread.bid_ask_spread_abs,
                        "depth_imbalance_pct": analysis.imbalance.depth_imbalance_pct,
                        "book_pressure": analysis.imbalance.book_pressure,
                        "total_bid_quantity": analysis.depth.total_bid_quantity,
                        "total_ask_quantity": analysis.depth.total_ask_quantity,
                        "depth_at_best_bid": analysis.depth.depth_at_best_bid,
                        "depth_at_best_ask": analysis.depth.depth_at_best_ask,
                    }
            except Exception as e:
                logger.debug(f"Failed to analyze market depth for {symbol} {strike}{option_type}: {e}")

        async with self._lock:
            for tf, seconds in self._tf_seconds.items():
                bucket_start = self._bucket_start(ts, seconds)
                key = (symbol, expiry, bucket_start)
                bucket = self._buffers[tf].setdefault(key, StrikeBucket())
                bucket.strikes[strike][option_type].add(metrics)
                if not bucket.underlying_close:
                    bucket.underlying_close = self._last_underlying.get(symbol)

                # Store liquidity metrics if available (last-write-wins for the bucket period)
                if "liquidity" in metrics:
                    bucket.liquidity[strike] = metrics["liquidity"]
            underlying_flush = self._collect_underlying_flush(ts)
            flush_payloads = self._collect_flush_payloads(ts)

        await self._persist_underlying_bars(self._convert_underlying_items(underlying_flush))
        await self._persist_batches(flush_payloads)

    def _collect_flush_payloads(self, reference_ts: int) -> List[Tuple[str, Tuple[str, date, int], StrikeBucket]]:
        flush_items: List[Tuple[str, Tuple[str, date, int], StrikeBucket]] = []
        lag = max(1, self._settings.fo_flush_lag_seconds)
        for tf, seconds in self._tf_seconds.items():
            buffer = self._buffers[tf]
            keys_to_flush = [
                key for key in buffer.keys()
                if reference_ts - key[2] >= seconds + lag
            ]
            for key in keys_to_flush:
                bucket = buffer.pop(key)
                flush_items.append((tf, key, bucket))
        return flush_items

    async def flush_all(self) -> None:
        async with self._lock:
            items: List[Tuple[str, Tuple[str, date, int], StrikeBucket]] = []
            underlying_items: List[Tuple[str, Tuple[str, int], UnderlyingBar]] = []
            for tf, buffer in self._buffers.items():
                for key, bucket in buffer.items():
                    items.append((tf, key, bucket))
                buffer.clear()
            for tf, buffer in self._underlying_buffers.items():
                for key, bar in buffer.items():
                    underlying_items.append((tf, key, bar))
                buffer.clear()
        await self._persist_underlying_bars(self._convert_underlying_items(underlying_items))
        await self._persist_batches(items)

    async def _persist_batches(self, items: List[Tuple[str, Tuple[str, date, int], StrikeBucket]]) -> None:
        async with self._persist_sem:   # NEW
            for tf, key, bucket in items:
                persist = tf in self._persist_timeframes
                await self._persist_bucket(tf, key, bucket, persist)

    async def _persist_bucket(self, timeframe: str, key: Tuple[str, date, int], bucket: StrikeBucket, persist: bool) -> None:
        symbol, expiry, bucket_ts = key
        if not bucket.strikes:
            return

        bucket_dt = _epoch_to_datetime(bucket_ts)
        underlying = bucket.underlying_close or self._last_underlying.get(symbol)
        strike_rows = []
        total_call_volume = 0.0
        total_put_volume = 0.0
        total_call_oi = 0.0
        total_put_oi = 0.0

        for strike_value, option_map in bucket.strikes.items():
            call_stats = option_map["CE"]
            put_stats = option_map["PE"]
            total_call_volume += call_stats.volume_sum
            total_put_volume += put_stats.volume_sum
            total_call_oi += call_stats.oi_sum
            total_put_oi += put_stats.oi_sum

            # Include liquidity metrics if available for this strike
            row = {
                "bucket_time": bucket_dt,
                "timeframe": timeframe,
                "symbol": symbol,
                "expiry": expiry,
                "strike": strike_value,
                "underlying_close": underlying,
                "call": self._serialize_stats(call_stats),
                "put": self._serialize_stats(put_stats),
            }

            # Add liquidity metrics if available
            if strike_value in bucket.liquidity:
                row["liquidity"] = bucket.liquidity[strike_value]

            strike_rows.append(row)

        max_pain = self._compute_max_pain(bucket.strikes)
        expiry_metrics = {
            "bucket_time": bucket_dt,
            "timeframe": timeframe,
            "symbol": symbol,
            "expiry": expiry,
            "underlying_close": underlying,
            "total_call_volume": total_call_volume,
            "total_put_volume": total_put_volume,
            "total_call_oi": total_call_oi,
            "total_put_oi": total_put_oi,
            "pcr": self._safe_ratio(total_put_volume, total_call_volume),
            "max_pain_strike": max_pain,
        }

        if persist:
            await self._dm.upsert_fo_strike_rows(strike_rows)
            await self._dm.upsert_fo_expiry_metrics([expiry_metrics])

        if self._hub:
            payload = self._build_stream_payload(timeframe, symbol, expiry, bucket_dt, strike_rows, expiry_metrics)
            await self._hub.broadcast(payload)

    def _safe_ratio(self, numerator: float, denominator: float) -> Optional[float]:
        if denominator <= 0:
            return None
        return numerator / denominator

    def _compute_max_pain(self, strikes: Dict[float, Dict[str, OptionStats]]) -> Optional[float]:
        if not strikes:
            return None
        candidates = sorted(strikes.keys())
        min_loss = math.inf
        best_strike = None
        for candidate in candidates:
            loss = 0.0
            for strike, option_map in strikes.items():
                call_vol = option_map["CE"].volume_sum
                put_vol = option_map["PE"].volume_sum
                loss += max(0.0, strike - candidate) * call_vol
                loss += max(0.0, candidate - strike) * put_vol
            if loss < min_loss:
                min_loss = loss
                best_strike = candidate
        return best_strike

    def _serialize_stats(self, stats: OptionStats) -> Dict[str, Optional[float]]:
        return {
            "iv": stats.avg("iv"),
            "delta": stats.avg("delta"),
            "gamma": stats.avg("gamma"),
            "theta": stats.avg("theta"),
            "vega": stats.avg("vega"),
            "volume": stats.volume_sum,
            "oi": stats.oi_sum,
            "count": stats.count,
        }

    def _build_stream_payload(
        self,
        timeframe: str,
        symbol: str,
        expiry: date,
        bucket_dt: datetime,
        strike_rows: List[Dict[str, object]],
        expiry_metrics: Dict[str, object],
    ) -> Dict[str, object]:
        bucket_epoch = int(bucket_dt.timestamp())
        strikes_payload = []
        for row in strike_rows:
            strikes_payload.append({
                "strike": row["strike"],
                "call": row["call"],
                "put": row["put"],
                "underlying": row.get("underlying_close"),
            })
        metrics_payload = dict(expiry_metrics)
        metrics_payload["bucket_time"] = bucket_epoch
        metrics_payload["total_call_oi"] = expiry_metrics.get("total_call_oi")
        metrics_payload["total_put_oi"] = expiry_metrics.get("total_put_oi")
        if isinstance(metrics_payload.get("expiry"), (datetime, date)):
            metrics_payload["expiry"] = metrics_payload["expiry"].isoformat()
        return {
            "type": "fo_bucket",
            "timeframe": timeframe,
            "symbol": symbol,
            "expiry": expiry.isoformat(),
            "bucket_time": bucket_epoch,
            "strikes": strikes_payload,
            "metrics": metrics_payload,
        }

    def _update_underlying_buffers(self, symbol: str, price: float, volume: float, ts: int) -> None:
        for tf, seconds in self._tf_seconds.items():
            bucket_start = self._bucket_start(ts, seconds)
            key = (symbol, bucket_start)
            buffer = self._underlying_buffers[tf]
            bar = buffer.get(key)
            if not bar:
                bar = UnderlyingBar(open=price, high=price, low=price, close=price, volume=volume)
                buffer[key] = bar
            else:
                bar.close = price
                if price > bar.high:
                    bar.high = price
                if price < bar.low:
                    bar.low = price
                bar.volume += volume

    def _collect_underlying_flush(self, reference_ts: int) -> List[Tuple[str, Tuple[str, int], UnderlyingBar]]:
        flush_items: List[Tuple[str, Tuple[str, int], UnderlyingBar]] = []
        lag = max(1, self._settings.fo_flush_lag_seconds)
        for tf, seconds in self._tf_seconds.items():
            buffer = self._underlying_buffers[tf]
            keys_to_flush = [
                key for key in list(buffer.keys())
                if reference_ts - key[1] >= seconds + lag
            ]
            for key in keys_to_flush:
                bar = buffer.pop(key)
                flush_items.append((tf, key, bar))
        return flush_items

    async def _persist_underlying_bars(self, items: List[Dict[str, object]]) -> None:
        if not items:
            return
        async with self._persist_sem:   # NEW
            try:
                await self._dm.upsert_underlying_bars(items)
            except Exception as exc:
                logger.error("Failed to upsert underlying bars: %s", exc, exc_info=True)

    def _convert_underlying_items(
        self,
        items: List[Tuple[str, Tuple[str, int], UnderlyingBar]],
    ) -> List[Dict[str, object]]:
        rows: List[Dict[str, object]] = []
        for timeframe, key, bar in items:
            symbol, bucket_start = key
            bucket_dt = datetime.fromtimestamp(bucket_start, tz=timezone.utc).replace(tzinfo=None)
            rows.append(
                {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "time": bucket_dt,
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "volume": int(bar.volume),
                    "metadata": {"source": "fo_stream", "timeframe": timeframe},
                }
            )
        return rows


class FOStreamConsumer:
    def __init__(
        self,
        redis_client: redis.Redis,
        data_manager: DataManager,
        settings: Settings,
        hub: Optional[RealTimeHub] = None,
    ):
        self._redis = redis_client
        self._settings = settings
        self._aggregator = FOAggregator(data_manager, settings, hub)
        self._options_channel = settings.fo_options_channel
        self._underlying_channel = settings.fo_underlying_channel
        self._running = True

    async def run(self) -> None:
        logger.info(f"FOStreamConsumer starting - channels: {self._options_channel}, {self._underlying_channel}")
        while self._running:
            pubsub = None
            try:
                pubsub = self._redis.pubsub(ignore_subscribe_messages=True)
                await pubsub.subscribe(self._options_channel, self._underlying_channel)
                logger.info(f"FOStreamConsumer subscribed to channels")
                while self._running:
                    try:
                        message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=5.0)
                    except asyncio.TimeoutError:
                        continue
                    if not message:
                        await asyncio.sleep(0.1)
                        continue
                    if message["type"] != "message":
                        continue
                    # Handle bytes channel names from decode_responses=False
                    channel = message["channel"]
                    if isinstance(channel, bytes):
                        channel = channel.decode('utf-8')
                    # Handle bytes data from decode_responses=False
                    data_raw = message["data"]
                    if isinstance(data_raw, bytes):
                        data = json.loads(data_raw.decode('utf-8'))
                    else:
                        data = json.loads(data_raw)

                    if channel == self._options_channel:
                        await self._aggregator.handle_option(data)
                    elif channel == self._underlying_channel:
                        await self._aggregator.handle_underlying(data)
                    else:
                        logger.warning(f"Unknown channel: {channel}")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("FO stream consumer error: %s", exc, exc_info=True)
                await asyncio.sleep(5)
            finally:
                if pubsub:
                    with contextlib.suppress(Exception):
                        await pubsub.close()

    async def shutdown(self) -> None:
        self._running = False
        await self._aggregator.flush_all()
