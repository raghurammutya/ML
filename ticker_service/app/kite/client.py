from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, Iterable, List, Optional, Set, TYPE_CHECKING

import asyncio
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

from ..config import get_settings
from ..schema import Instrument

if TYPE_CHECKING:  # pragma: no cover - typing aid only
    from ..accounts import KiteAccount

try:
    from kiteconnect import KiteConnect, KiteTicker
except ImportError as exc:  # pragma: no cover - surfaced at runtime if package missing
    KiteConnect = None
    KiteTicker = None
    _kite_import_error = exc
else:
    _kite_import_error = None


TickHandler = Callable[[str, List[Dict[str, Any]]], Awaitable[None]]
ErrorHandler = Callable[[str, Exception], Awaitable[None]]


def _resolve_token_dir() -> Path:
    """Resolve the token directory consistently with session.py."""
    base = Path(__file__).parent
    env_dir = os.getenv("KITE_TOKEN_DIR")
    if env_dir:
        candidate = Path(env_dir)
        return candidate if candidate.is_absolute() else base / candidate
    return base / "tokens"


WS_ROOT = os.getenv("KITE_WS_ROOT", "wss://ws.kite.trade")


class KiteClient:
    """
    Async-friendly wrapper around KiteConnect/KiteTicker that takes care of session
    management, instrument discovery, and websocket lifecycle for a single account.
    """

    def __init__(self, account_id: str, api_key: str, access_token: str | None = None) -> None:
        if _kite_import_error:
            raise RuntimeError(
                "kiteconnect is not installed. Install it via `pip install kiteconnect`."
            ) from _kite_import_error
        self.account_id = account_id
        self.api_key = api_key
        self.access_token = access_token or ""

        self._kite = KiteConnect(api_key=api_key)
        if self.access_token:
            self._kite.set_access_token(self.access_token)
        logger.debug(
            "Access token set for account=%s | headers=%s",
            self.account_id,
            self.access_token
        )

        self._settings = get_settings()
        self._ticker: KiteTicker | None = None
        self._ticker_connected = False
        self._ticker_running = False
        self._ticker_mode: str | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._tick_handler: TickHandler | None = None
        self._error_handler: ErrorHandler | None = None
        self._subscription_lock = threading.Lock()
        self._target_tokens: Set[int] = set()
        self._subscribed_tokens: Set[int] = set()

    @classmethod
    def from_account(cls, account: "KiteAccount") -> "KiteClient":
        logger.debug(
            "Creating KiteClient for account=%s | token=%s",
            account.account_id,
            (account.access_token or "")[:6] + "..." if account.access_token else "MISSING"
        )

        return cls(
            account_id=account.account_id,
            api_key=account.api_key,
            access_token=account.access_token,
        )

    async def ensure_session(self) -> None:
        logger.debug("Ensuring session for account %s (has_token=%s)", self.account_id, bool(self.access_token))
        if self.access_token:
            return

        token_dir = _resolve_token_dir()
        candidates = [
            token_dir / f"kite_token_{self.account_id}.json",
            token_dir / f"kite_token_{self.account_id.lower()}.json",
            Path.cwd() / "Kite_FOdata_scripts" / "tokens" / f"kite_token_{self.account_id}.json",
        ]

        for candidate in candidates:
            if not candidate.exists():
                continue
            try:
                payload = json.loads(candidate.read_text())
            except Exception:
                logger.exception("Failed to read token file %s", candidate)
                continue
            token = payload.get("access_token")
            if not token:
                continue
            self.access_token = token
            self._kite.set_access_token(token)
            logger.debug("Loaded access token for account %s from %s", self.account_id, candidate)
            return

        raise RuntimeError(
            f"Account {self.account_id} missing access token. "
            f"Tried: {', '.join(str(p) for p in candidates)}. "
            "Set KITE_TOKEN_DIR or run the token bootstrap."
        )

    async def fetch_historical(
        self,
        instrument_token: int,
        from_ts: int,
        to_ts: int,
        interval: str,
        *,
        continuous: bool = False,
        oi: bool = False,
    ) -> List[Dict[str, Any]]:
        await self.ensure_session()

        from_dt = datetime.fromtimestamp(from_ts, tz=timezone.utc)
        to_dt = datetime.fromtimestamp(to_ts, tz=timezone.utc)
        logger.debug(
            "Fetching historical data | account=%s token=%s interval=%s from=%s to=%s",
            self.account_id,
            instrument_token,
            interval,
            from_dt,
            to_dt,
        )

        def _fetch() -> List[Dict[str, Any]]:
            return self._kite.historical_data(
                instrument_token,
                from_dt,
                to_dt,
                interval,
                continuous=continuous,
                oi=oi,
            )

        return await asyncio.to_thread(_fetch)

    def fetch_instruments(self, segment: str) -> List[Dict[str, Any]]:
        def _download():
            # Temporarily override the token header for this call
            self._kite.set_access_token(f"token {self.api_key}:{self.access_token}")
            try:
                return self._kite.instruments(segment)
            finally:
                # Restore raw token for other API calls
                self._kite.set_access_token(self.access_token)

        return asyncio.to_thread(_download)


    async def get_last_price(self, tradingsymbol: str) -> float:
        await self.ensure_session()

        def _quote() -> float:
            quote = self._kite.quote([tradingsymbol])
            return float(quote[tradingsymbol]["last_price"])

        return await asyncio.to_thread(_quote)

    async def get_quote(self, tradingsymbols: Iterable[str]) -> Dict[str, Any]:
        symbols = [str(symbol) for symbol in tradingsymbols if symbol]
        if not symbols:
            return {}

        await self.ensure_session()

        def _quote() -> Dict[str, Any]:
            return self._kite.quote(symbols)

        return await asyncio.to_thread(_quote)

    async def load_option_chain(
        self,
        underlying: str,
        expiry_window: int,
        otm_levels: int,
    ) -> List[Instrument]:
        await self.ensure_session()

        def _fetch_instruments() -> List[Dict[str, Any]]:
            return self._kite.instruments("NFO")

        instruments = await asyncio.to_thread(_fetch_instruments)
        logger.debug("Fetched %d NFO instruments for account %s", len(instruments), self.account_id)
        filtered = [inst for inst in instruments if inst.get("name", "").upper() == underlying.upper()]
        if not filtered:
            logger.warning("Account %s: no instruments found for %s", self.account_id, underlying)
            return []

        quote_symbol = self._settings.nifty_quote_symbol

        async def _fetch_spot() -> float:
            def _quote() -> float:
                quote = self._kite.quote([quote_symbol])
                return float(quote[quote_symbol]["last_price"])

            return await asyncio.to_thread(_quote)

        try:
            spot_price = await _fetch_spot()
        except Exception as exc:  # pragma: no cover - depends on external API
            logger.error(
                "Account %s: failed to fetch spot price (%s). Falling back to synthetic strikes.",
                self.account_id,
                exc,
            )
            spot_price = 0.0

        strike_step = 50
        atm_strike = round(spot_price / strike_step) * strike_step if spot_price else 0
        strike_range = (
            {atm_strike + strike_step * i for i in range(-otm_levels, otm_levels + 1)}
            if atm_strike
            else set()
        )

        expiries = sorted({inst["expiry"] for inst in filtered if inst.get("expiry")})
        expiries = expiries[:expiry_window] if expiry_window else expiries
        expiry_whitelist = set(expiries)

        option_chain: List[Instrument] = []
        for inst in filtered:
            instrument_type = inst.get("instrument_type")
            expiry = inst.get("expiry")
            strike = float(inst.get("strike") or 0)
            if instrument_type not in ("CE", "PE"):
                continue
            if expiry_whitelist and expiry not in expiry_whitelist:
                continue
            if strike_range and strike not in strike_range:
                continue
            option_chain.append(
                Instrument(
                    symbol=underlying,
                    instrument_token=int(inst["instrument_token"]),
                    strike=strike,
                    expiry=expiry.isoformat() if hasattr(expiry, "isoformat") else str(expiry),
                    instrument_type=instrument_type,
                )
        )

        option_chain.sort(key=lambda inst: (inst.expiry or "", inst.strike or 0.0, inst.instrument_type))
        logger.debug(
            "Account %s discovered %d instruments for %s (expiry_window=%d, otm=%d)",
            self.account_id,
            len(option_chain),
            underlying,
            expiry_window,
            otm_levels,
        )
        return option_chain

    async def subscribe_tokens(
        self,
        tokens: Iterable[int],
        on_ticks: TickHandler,
        on_error: Optional[ErrorHandler] = None,
    ) -> None:
        instrument_tokens = [int(token) for token in tokens]
        if not instrument_tokens:
            return

        await self.ensure_session()

        self._loop = asyncio.get_running_loop()
        self._tick_handler = on_ticks
        self._error_handler = on_error

        with self._subscription_lock:
            self._target_tokens.update(instrument_tokens)

        logger.debug("Account %s scheduling subscribe for %d tokens", self.account_id, len(instrument_tokens))
        self._ensure_ticker()
        self._sync_subscriptions()

    async def unsubscribe_tokens(self, tokens: Iterable[int]) -> None:
        instrument_tokens = [int(token) for token in tokens]
        if not instrument_tokens:
            return

        with self._subscription_lock:
            for token in instrument_tokens:
                self._target_tokens.discard(token)
        logger.debug("Account %s scheduling unsubscribe for %d tokens", self.account_id, len(instrument_tokens))

        self._sync_subscriptions()

    async def stop_stream(self) -> None:
        with self._subscription_lock:
            self._target_tokens.clear()

        self._sync_subscriptions()

        if self._ticker:
            try:
                self._ticker.close()
            except Exception:  # pragma: no cover - depends on network state
                logger.exception("Failed to close ticker for %s", self.account_id)

        self._ticker = None
        self._ticker_running = False
        self._ticker_connected = False
        self._subscribed_tokens.clear()
        self._loop = None
        logger.info("Kite ticker stopped for account %s", self.account_id)

    # ------------------------------------------------------------------ internals
    def _ensure_ticker(self) -> None:
        if self._ticker_running:
            return

        if not self.access_token:
            raise RuntimeError(
                f"Account {self.account_id} has no access token. Call ensure_session() first."
            )

        self._ticker = KiteTicker(
            api_key=self.api_key,
            access_token=self.access_token,
            root=WS_ROOT,
            reconnect=True,
            reconnect_max_tries=50,
            reconnect_max_delay=60,
        )
        logger.debug("KiteTicker constructed for account %s (root=%s)", self.account_id, WS_ROOT)

        def _on_connect(ws, response=None):  # pragma: no cover - runs in WS thread
            self._ticker_connected = True
            mode = getattr(self._settings, "ticker_mode", "LTP").upper()
            self._ticker_mode = mode
            logger.info("Kite ticker connected for %s in %s mode", self.account_id, mode)
            self._sync_subscriptions()

        def _on_close(ws, code, reason):  # pragma: no cover - runs in WS thread
            self._ticker_connected = False
            logger.warning(
                "Kite ticker closed for %s (code=%s reason=%s)",
                self.account_id,
                code,
                reason,
            )

        def _on_error(ws, code, reason):  # pragma: no cover - runs in WS thread
            logger.error(
                "Kite ticker error for %s (code=%s reason=%s)",
                self.account_id,
                code,
                reason,
            )
            if self._error_handler and self._loop:
                asyncio.run_coroutine_threadsafe(
                    self._error_handler(self.account_id, RuntimeError(f"WS error {code}: {reason}")),
                    self._loop,
                )

        def _on_ticks(ws, ticks):  # pragma: no cover - runs in WS thread
            if self._tick_handler and self._loop:
                asyncio.run_coroutine_threadsafe(
                    self._tick_handler(self.account_id, ticks),
                    self._loop,
                )

        self._ticker.on_connect = _on_connect
        self._ticker.on_close = _on_close
        self._ticker.on_error = _on_error
        self._ticker.on_ticks = _on_ticks

        self._ticker_running = True
        self._ticker.connect(threaded=True, reconnect=True, disable_ssl_verification=False)

    def _sync_subscriptions(self) -> None:
        if not self._ticker or not self._ticker_running:
            return

        if not self._ticker_connected or getattr(self._ticker, "ws", None) is None:
            logger.debug("WS not connected yet; deferring subscribe sync for %s", self.account_id)
            return

        with self._subscription_lock:
            target = set(self._target_tokens)
            to_add = list(target - self._subscribed_tokens)
            to_remove = list(self._subscribed_tokens - target)

        if to_add:
            try:
                self._ticker.subscribe(to_add)
                self._subscribed_tokens.update(to_add)
                logger.debug("Subscribed %s -> %s", self.account_id, to_add)
            except Exception:  # pragma: no cover
                logger.exception("Subscribe failed for %s", self.account_id)

        if to_remove:
            try:
                self._ticker.unsubscribe(to_remove)
                for token in to_remove:
                    self._subscribed_tokens.discard(token)
                logger.debug("Unsubscribed %s -> %s", self.account_id, to_remove)
            except Exception:  # pragma: no cover
                logger.exception("Unsubscribe failed for %s", self.account_id)

        if not self._subscribed_tokens:
            return

        mode = (self._ticker_mode or "LTP").upper()
        tokens = list(self._subscribed_tokens)
        try:
            if mode == "FULL":
                self._ticker.set_mode(self._ticker.MODE_FULL, tokens)
            elif mode == "QUOTE":
                self._ticker.set_mode(self._ticker.MODE_QUOTE, tokens)
            else:
                self._ticker.set_mode(self._ticker.MODE_LTP, tokens)
        except Exception:  # pragma: no cover
            logger.exception("set_mode(%s) failed for %s", mode, self.account_id)
