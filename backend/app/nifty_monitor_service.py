from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Dict, Iterable, List, Optional, Set, Tuple

import redis.asyncio as redis

from .config import Settings
from .realtime import RealTimeHub
from .ticker_client import TickerServiceClient, TickerServiceError

logger = logging.getLogger(__name__)


class NiftySubscriptionManager:
    """
    Tracks active Nifty monitor sessions and maintains reference-counted
    subscriptions with the ticker microservice.
    """

    def __init__(
        self,
        ticker_client: TickerServiceClient,
        settings: Settings,
    ) -> None:
        self._client = ticker_client
        self._settings = settings
        self._lock = asyncio.Lock()
        self._sessions: Dict[str, Set[int]] = {}
        self._ref_counts: Dict[int, int] = {}

    async def create_session(
        self,
        tokens: Iterable[int],
        requested_mode: Optional[str] = None,
        account_id: Optional[str] = None,
    ) -> Tuple[str, List[int]]:
        token_set: Set[int] = {int(t) for t in tokens if t is not None}
        if not token_set:
            raise ValueError("No instrument tokens provided")

        mode = (requested_mode or self._settings.ticker_service_mode).upper()
        acct = account_id or self._settings.ticker_service_account_id

        async with self._lock:
            session_id = uuid.uuid4().hex
            newly_subscribed: List[int] = []
            try:
                for token in token_set:
                    ref = self._ref_counts.get(token, 0)
                    if ref == 0:
                        await self._client.subscribe(token, requested_mode=mode, account_id=acct)
                        newly_subscribed.append(token)
                    self._ref_counts[token] = ref + 1
                self._sessions[session_id] = set(token_set)
            except Exception as exc:
                logger.exception("Failed to create monitor session")
                await self._rollback(newly_subscribed)
                raise

        return session_id, sorted(token_set)

    async def release_session(self, session_id: str) -> List[int]:
        async with self._lock:
            tokens = self._sessions.pop(session_id, None)
            if not tokens:
                return []
            unsubscribed: List[int] = []
            for token in tokens:
                ref = self._ref_counts.get(token, 0)
                if ref <= 1:
                    self._ref_counts.pop(token, None)
                    try:
                        await self._client.unsubscribe(token)
                        unsubscribed.append(token)
                    except TickerServiceError as exc:
                        # Log and continue; maybe already unsubscribed server-side.
                        logger.warning("Ticker unsubscribe warning for %s: %s", token, exc)
                else:
                    self._ref_counts[token] = ref - 1
        return unsubscribed

    async def active_tokens(self) -> List[int]:
        async with self._lock:
            return sorted(self._ref_counts.keys())

    async def active_sessions(self) -> int:
        async with self._lock:
            return len(self._sessions)

    async def _rollback(self, tokens: List[int]) -> None:
        for token in tokens:
            try:
                await self._client.unsubscribe(token)
            except Exception:
                logger.warning("Rollback unsubscribe failed for token %s", token)


class NiftyMonitorStream:
    """
    Subscribes to Redis ticker channels and keeps track of the latest ticks
    for the Nifty monitor, while optionally broadcasting to a realtime hub.
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        settings: Settings,
        hub: Optional[RealTimeHub] = None,
    ) -> None:
        self._redis = redis_client
        self._settings = settings
        self._hub = hub
        self._lock = asyncio.Lock()
        self._latest_underlying: Optional[dict] = None
        self._latest_options: Dict[int, dict] = {}
        self._task: Optional[asyncio.Task] = None
        self._running = asyncio.Event()

    async def run(self) -> None:
        print("[NiftyMonitorStream] run() called - starting...", flush=True)
        logger.info("NiftyMonitorStream.run() called - starting...")
        try:
            pubsub = self._redis.pubsub()
            print("[NiftyMonitorStream] pubsub object created", flush=True)
            logger.info("NiftyMonitorStream: pubsub object created")
            channels = [
                self._settings.fo_underlying_channel,
                self._settings.fo_options_channel,
            ]
            print(f"[NiftyMonitorStream] subscribing to channels: {channels}", flush=True)
            logger.info(f"NiftyMonitorStream: subscribing to channels: {channels}")
            await pubsub.subscribe(*channels)
            print("[NiftyMonitorStream] subscribe call completed", flush=True)
            logger.info("NiftyMonitorStream: subscribe call completed")
            self._running.set()
            print(f"[NiftyMonitorStream] subscribed to {channels}, now listening for messages", flush=True)
            logger.info("Nifty monitor stream subscribed to %s", channels)
        except Exception as e:
            logger.error(f"NiftyMonitorStream: Failed to subscribe: {e}", exc_info=True)
            raise
        try:
            while True:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if not message:
                    await asyncio.sleep(0.05)
                    continue
                channel = message.get("channel")
                data = message.get("data")
                if isinstance(channel, bytes):
                    channel = channel.decode()
                if isinstance(data, bytes):
                    data = data.decode()
                if not channel or not data:
                    continue
                try:
                    payload = json.loads(data)
                except json.JSONDecodeError:
                    logger.debug("Skipping non-JSON payload on %s: %s", channel, data)
                    continue
                await self._handle_message(channel, payload)
        except asyncio.CancelledError:
            logger.info("Nifty monitor stream cancelled")
            raise
        finally:
            await pubsub.unsubscribe(*channels)
            await pubsub.close()
            self._running.clear()
            logger.info("Nifty monitor stream stopped")

    async def _handle_message(self, channel: str, payload: dict) -> None:
        async with self._lock:
            if channel == self._settings.fo_underlying_channel:
                self._latest_underlying = payload
            elif channel == self._settings.fo_options_channel:
                token = payload.get("token") or payload.get("instrument_token")
                if token is None:
                    return
                try:
                    token_int = int(token)
                except (TypeError, ValueError):
                    return
                self._latest_options[token_int] = payload

            snapshot = {
                "channel": channel,
                "payload": payload,
            }

        if self._hub:
            await self._hub.broadcast(snapshot)

    async def snapshot(self) -> dict:
        async with self._lock:
            underlying = self._latest_underlying.copy() if self._latest_underlying else None
            options = {token: data.copy() for token, data in self._latest_options.items()}
        return {
            "underlying": underlying,
            "options": options,
        }

    async def latest_underlying(self) -> Optional[dict]:
        async with self._lock:
            return self._latest_underlying.copy() if self._latest_underlying else None

    async def latest_options(self) -> Dict[int, dict]:
        async with self._lock:
            return {token: data.copy() for token, data in self._latest_options.items()}
