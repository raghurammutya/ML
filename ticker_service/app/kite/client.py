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
from ..kite_rate_limiter import get_rate_limiter, KiteEndpoint
from .websocket_pool import KiteWebSocketPool

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
        self._ws_pool: KiteWebSocketPool | None = None
        self._pool_started = False
        self._loop: asyncio.AbstractEventLoop | None = None
        self._tick_handler: TickHandler | None = None
        self._error_handler: ErrorHandler | None = None

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

        # Rate limiting: 3 requests/second for historical data
        rate_limiter = get_rate_limiter()
        await rate_limiter.acquire(KiteEndpoint.HISTORICAL, wait=True, timeout=30.0)

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

        # Rate limiting: 1 request/second for quote endpoint
        rate_limiter = get_rate_limiter()
        await rate_limiter.acquire(KiteEndpoint.QUOTE, wait=True, timeout=30.0)

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

        # Initialize pool if needed
        self._ensure_pool()

        # Subscribe via pool (automatically handles multi-connection scaling)
        logger.info(
            "Account %s subscribing to %d tokens via WebSocket pool",
            self.account_id,
            len(instrument_tokens),
        )
        self._ws_pool.subscribe_tokens(instrument_tokens)

    async def unsubscribe_tokens(self, tokens: Iterable[int]) -> None:
        instrument_tokens = [int(token) for token in tokens]
        if not instrument_tokens:
            return

        if not self._ws_pool:
            logger.warning("Account %s: no WebSocket pool to unsubscribe from", self.account_id)
            return

        logger.info(
            "Account %s unsubscribing from %d tokens via WebSocket pool",
            self.account_id,
            len(instrument_tokens),
        )
        self._ws_pool.unsubscribe_tokens(instrument_tokens)

    async def stop_stream(self) -> None:
        if self._ws_pool:
            try:
                self._ws_pool.stop_all()
            except Exception:  # pragma: no cover - depends on network state
                logger.exception("Failed to stop WebSocket pool for %s", self.account_id)

        self._ws_pool = None
        self._pool_started = False
        self._loop = None
        logger.info("WebSocket pool stopped for account %s", self.account_id)

    # ------------------------------------------------------------------ Order Management APIs
    async def place_order(
        self,
        exchange: str,
        tradingsymbol: str,
        transaction_type: str,
        quantity: int,
        product: str,
        order_type: str,
        variety: str = "regular",
        price: Optional[float] = None,
        trigger_price: Optional[float] = None,
        validity: str = "DAY",
        disclosed_quantity: Optional[int] = None,
        squareoff: Optional[float] = None,
        stoploss: Optional[float] = None,
        trailing_stoploss: Optional[float] = None,
        tag: Optional[str] = None,
    ) -> str:
        """
        Place an order.

        Returns: order_id
        """
        await self.ensure_session()

        # Rate limiting: 10 req/sec, 200 req/min, 3000 req/day for orders
        rate_limiter = get_rate_limiter()
        await rate_limiter.acquire(KiteEndpoint.ORDER_PLACE, wait=True, timeout=30.0)

        def _place() -> str:
            params = {
                "variety": variety,
                "exchange": exchange,
                "tradingsymbol": tradingsymbol,
                "transaction_type": transaction_type,
                "quantity": quantity,
                "product": product,
                "order_type": order_type,
                "validity": validity,
            }
            if price is not None:
                params["price"] = price
            if trigger_price is not None:
                params["trigger_price"] = trigger_price
            if disclosed_quantity is not None:
                params["disclosed_quantity"] = disclosed_quantity
            if squareoff is not None:
                params["squareoff"] = squareoff
            if stoploss is not None:
                params["stoploss"] = stoploss
            if trailing_stoploss is not None:
                params["trailing_stoploss"] = trailing_stoploss
            if tag is not None:
                params["tag"] = tag

            return self._kite.place_order(**params)

        return await asyncio.to_thread(_place)

    async def modify_order(
        self,
        variety: str,
        order_id: str,
        quantity: Optional[int] = None,
        price: Optional[float] = None,
        order_type: Optional[str] = None,
        trigger_price: Optional[float] = None,
        validity: Optional[str] = None,
        disclosed_quantity: Optional[int] = None,
        parent_order_id: Optional[str] = None,
    ) -> str:
        """
        Modify a pending order.

        Returns: order_id
        """
        await self.ensure_session()

        # Rate limiting: 10 req/sec for order modifications
        rate_limiter = get_rate_limiter()
        await rate_limiter.acquire(KiteEndpoint.ORDER_MODIFY, wait=True, timeout=30.0)

        def _modify() -> str:
            params = {
                "variety": variety,
                "order_id": order_id,
            }
            if quantity is not None:
                params["quantity"] = quantity
            if price is not None:
                params["price"] = price
            if order_type is not None:
                params["order_type"] = order_type
            if trigger_price is not None:
                params["trigger_price"] = trigger_price
            if validity is not None:
                params["validity"] = validity
            if disclosed_quantity is not None:
                params["disclosed_quantity"] = disclosed_quantity
            if parent_order_id is not None:
                params["parent_order_id"] = parent_order_id

            return self._kite.modify_order(**params)

        return await asyncio.to_thread(_modify)

    async def cancel_order(self, variety: str, order_id: str, parent_order_id: Optional[str] = None) -> str:
        """
        Cancel a pending order.

        Returns: order_id
        """
        await self.ensure_session()

        # Rate limiting: 10 req/sec for order cancellations
        rate_limiter = get_rate_limiter()
        await rate_limiter.acquire(KiteEndpoint.ORDER_CANCEL, wait=True, timeout=30.0)

        def _cancel() -> str:
            params = {
                "variety": variety,
                "order_id": order_id,
            }
            if parent_order_id is not None:
                params["parent_order_id"] = parent_order_id

            return self._kite.cancel_order(**params)

        return await asyncio.to_thread(_cancel)

    async def exit_order(self, variety: str, order_id: str, parent_order_id: Optional[str] = None) -> str:
        """
        Exit a cover order or bracket order.

        Returns: order_id
        """
        await self.ensure_session()

        def _exit() -> str:
            params = {
                "variety": variety,
                "order_id": order_id,
            }
            if parent_order_id is not None:
                params["parent_order_id"] = parent_order_id

            return self._kite.exit_order(**params)

        return await asyncio.to_thread(_exit)

    async def orders(self) -> List[Dict[str, Any]]:
        """
        Get list of all orders for the day.
        """
        await self.ensure_session()

        def _orders() -> List[Dict[str, Any]]:
            return self._kite.orders()

        return await asyncio.to_thread(_orders)

    async def order_history(self, order_id: str) -> List[Dict[str, Any]]:
        """
        Get history/trail of a specific order.
        """
        await self.ensure_session()

        def _history() -> List[Dict[str, Any]]:
            return self._kite.order_history(order_id)

        return await asyncio.to_thread(_history)

    async def order_trades(self, order_id: str) -> List[Dict[str, Any]]:
        """
        Get list of trades executed for an order.
        """
        await self.ensure_session()

        def _trades() -> List[Dict[str, Any]]:
            return self._kite.order_trades(order_id)

        return await asyncio.to_thread(_trades)

    async def trades(self) -> List[Dict[str, Any]]:
        """
        Get all trades for the day.
        """
        await self.ensure_session()

        def _trades() -> List[Dict[str, Any]]:
            return self._kite.trades()

        return await asyncio.to_thread(_trades)

    async def order_margins(self, orders: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Calculate margins for a list of orders (basket).
        """
        await self.ensure_session()

        def _margins() -> List[Dict[str, Any]]:
            return self._kite.order_margins(orders)

        return await asyncio.to_thread(_margins)

    async def basket_order_margins(self, orders: List[Dict[str, Any]], consider_positions: bool = True) -> Dict[str, Any]:
        """
        Calculate total margins required for a basket of orders.
        """
        await self.ensure_session()

        def _basket_margins() -> Dict[str, Any]:
            return self._kite.basket_order_margins(orders, consider_positions=consider_positions)

        return await asyncio.to_thread(_basket_margins)

    # ------------------------------------------------------------------ Portfolio APIs
    async def holdings(self) -> List[Dict[str, Any]]:
        """
        Get list of long-term equity holdings.
        """
        await self.ensure_session()

        def _holdings() -> List[Dict[str, Any]]:
            return self._kite.holdings()

        return await asyncio.to_thread(_holdings)

    async def positions(self) -> Dict[str, Any]:
        """
        Get net and day positions.
        """
        await self.ensure_session()

        def _positions() -> Dict[str, Any]:
            return self._kite.positions()

        return await asyncio.to_thread(_positions)

    async def convert_position(
        self,
        exchange: str,
        tradingsymbol: str,
        transaction_type: str,
        position_type: str,
        quantity: int,
        old_product: str,
        new_product: str,
    ) -> bool:
        """
        Convert position between product types.
        """
        await self.ensure_session()

        def _convert() -> bool:
            return self._kite.convert_position(
                exchange=exchange,
                tradingsymbol=tradingsymbol,
                transaction_type=transaction_type,
                position_type=position_type,
                quantity=quantity,
                old_product=old_product,
                new_product=new_product,
            )

        return await asyncio.to_thread(_convert)

    # ------------------------------------------------------------------ User & Account APIs
    async def profile(self) -> Dict[str, Any]:
        """
        Get user profile details.
        """
        await self.ensure_session()

        def _profile() -> Dict[str, Any]:
            return self._kite.profile()

        return await asyncio.to_thread(_profile)

    async def margins(self, segment: Optional[str] = None) -> Dict[str, Any]:
        """
        Get account margins and cash balances.

        Args:
            segment: Optional segment filter ("equity" or "commodity")
        """
        await self.ensure_session()

        def _margins() -> Dict[str, Any]:
            if segment:
                return self._kite.margins(segment)
            return self._kite.margins()

        return await asyncio.to_thread(_margins)

    # ------------------------------------------------------------------ GTT APIs
    async def place_gtt(
        self,
        trigger_type: str,
        tradingsymbol: str,
        exchange: str,
        trigger_values: List[float],
        last_price: float,
        orders: List[Dict[str, Any]],
    ) -> int:
        """
        Place a GTT (Good Till Triggered) order.

        Returns: gtt_id
        """
        await self.ensure_session()

        def _place_gtt() -> int:
            return self._kite.place_gtt(
                trigger_type=trigger_type,
                tradingsymbol=tradingsymbol,
                exchange=exchange,
                trigger_values=trigger_values,
                last_price=last_price,
                orders=orders,
            )

        return await asyncio.to_thread(_place_gtt)

    async def get_gtt(self, gtt_id: int) -> Dict[str, Any]:
        """
        Get details of a specific GTT.
        """
        await self.ensure_session()

        def _get_gtt() -> Dict[str, Any]:
            return self._kite.get_gtt(gtt_id)

        return await asyncio.to_thread(_get_gtt)

    async def get_gtts(self) -> List[Dict[str, Any]]:
        """
        Get list of all active GTTs.
        """
        await self.ensure_session()

        def _get_gtts() -> List[Dict[str, Any]]:
            return self._kite.get_gtts()

        return await asyncio.to_thread(_get_gtts)

    async def modify_gtt(
        self,
        gtt_id: int,
        trigger_type: str,
        tradingsymbol: str,
        exchange: str,
        trigger_values: List[float],
        last_price: float,
        orders: List[Dict[str, Any]],
    ) -> int:
        """
        Modify a GTT order.

        Returns: gtt_id
        """
        await self.ensure_session()

        def _modify_gtt() -> int:
            return self._kite.modify_gtt(
                gtt_id=gtt_id,
                trigger_type=trigger_type,
                tradingsymbol=tradingsymbol,
                exchange=exchange,
                trigger_values=trigger_values,
                last_price=last_price,
                orders=orders,
            )

        return await asyncio.to_thread(_modify_gtt)

    async def delete_gtt(self, gtt_id: int) -> int:
        """
        Cancel a GTT order.

        Returns: gtt_id
        """
        await self.ensure_session()

        def _delete_gtt() -> int:
            return self._kite.delete_gtt(gtt_id)

        return await asyncio.to_thread(_delete_gtt)

    async def gtt_trigger_range(self, transaction_type: str, exchange: str, tradingsymbol: str) -> Dict[str, Any]:
        """
        Get trigger range for GTT orders.
        """
        await self.ensure_session()

        def _trigger_range() -> Dict[str, Any]:
            return self._kite.gtt_trigger_range(
                transaction_type=transaction_type,
                exchange=exchange,
                tradingsymbol=tradingsymbol,
            )

        return await asyncio.to_thread(_trigger_range)

    # ------------------------------------------------------------------ Mutual Funds APIs
    async def place_mf_order(
        self,
        tradingsymbol: str,
        transaction_type: str,
        amount: Optional[float] = None,
        quantity: Optional[float] = None,
        tag: Optional[str] = None,
    ) -> str:
        """
        Place a mutual fund order.

        Returns: order_id
        """
        await self.ensure_session()

        def _place_mf() -> str:
            params = {
                "tradingsymbol": tradingsymbol,
                "transaction_type": transaction_type,
            }
            if amount is not None:
                params["amount"] = amount
            if quantity is not None:
                params["quantity"] = quantity
            if tag is not None:
                params["tag"] = tag

            return self._kite.place_mf_order(**params)

        return await asyncio.to_thread(_place_mf)

    async def cancel_mf_order(self, order_id: str) -> str:
        """
        Cancel a pending mutual fund order.

        Returns: order_id
        """
        await self.ensure_session()

        def _cancel_mf() -> str:
            return self._kite.cancel_mf_order(order_id)

        return await asyncio.to_thread(_cancel_mf)

    async def mf_orders(self, order_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get all mutual fund orders or details of a specific order.
        """
        await self.ensure_session()

        def _mf_orders() -> List[Dict[str, Any]]:
            if order_id:
                return self._kite.mf_orders(order_id)
            return self._kite.mf_orders()

        return await asyncio.to_thread(_mf_orders)

    async def place_mf_sip(
        self,
        tradingsymbol: str,
        amount: float,
        frequency: str,
        initial_amount: Optional[float] = None,
        installments: Optional[int] = None,
        installment_day: Optional[int] = None,
        tag: Optional[str] = None,
    ) -> str:
        """
        Place a mutual fund SIP.

        Returns: sip_id
        """
        await self.ensure_session()

        def _place_sip() -> str:
            params = {
                "tradingsymbol": tradingsymbol,
                "amount": amount,
                "frequency": frequency,
            }
            if initial_amount is not None:
                params["initial_amount"] = initial_amount
            if installments is not None:
                params["installments"] = installments
            if installment_day is not None:
                params["installment_day"] = installment_day
            if tag is not None:
                params["tag"] = tag

            return self._kite.place_mf_sip(**params)

        return await asyncio.to_thread(_place_sip)

    async def modify_mf_sip(
        self,
        sip_id: str,
        amount: Optional[float] = None,
        frequency: Optional[str] = None,
        installments: Optional[int] = None,
        installment_day: Optional[int] = None,
        status: Optional[str] = None,
    ) -> str:
        """
        Modify an active mutual fund SIP.

        Returns: sip_id
        """
        await self.ensure_session()

        def _modify_sip() -> str:
            params = {"sip_id": sip_id}
            if amount is not None:
                params["amount"] = amount
            if frequency is not None:
                params["frequency"] = frequency
            if installments is not None:
                params["installments"] = installments
            if installment_day is not None:
                params["installment_day"] = installment_day
            if status is not None:
                params["status"] = status

            return self._kite.modify_mf_sip(**params)

        return await asyncio.to_thread(_modify_sip)

    async def cancel_mf_sip(self, sip_id: str) -> str:
        """
        Cancel an active mutual fund SIP.

        Returns: sip_id
        """
        await self.ensure_session()

        def _cancel_sip() -> str:
            return self._kite.cancel_mf_sip(sip_id)

        return await asyncio.to_thread(_cancel_sip)

    async def mf_sips(self, sip_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get all mutual fund SIPs or details of a specific SIP.
        """
        await self.ensure_session()

        def _mf_sips() -> List[Dict[str, Any]]:
            if sip_id:
                return self._kite.mf_sips(sip_id)
            return self._kite.mf_sips()

        return await asyncio.to_thread(_mf_sips)

    async def mf_holdings(self) -> List[Dict[str, Any]]:
        """
        Get mutual fund holdings.
        """
        await self.ensure_session()

        def _mf_holdings() -> List[Dict[str, Any]]:
            return self._kite.mf_holdings()

        return await asyncio.to_thread(_mf_holdings)

    async def mf_instruments(self) -> List[Dict[str, Any]]:
        """
        Get list of all mutual fund instruments.
        """
        await self.ensure_session()

        def _mf_instruments() -> List[Dict[str, Any]]:
            return self._kite.mf_instruments()

        return await asyncio.to_thread(_mf_instruments)

    # ------------------------------------------------------------------ Session Management APIs
    async def invalidate_access_token(self) -> bool:
        """
        Invalidate the current access token.
        """
        await self.ensure_session()

        def _invalidate() -> bool:
            return self._kite.invalidate_access_token()

        return await asyncio.to_thread(_invalidate)

    async def invalidate_refresh_token(self, refresh_token: str) -> bool:
        """
        Invalidate the refresh token.
        """
        await self.ensure_session()

        def _invalidate_refresh() -> bool:
            return self._kite.invalidate_refresh_token(refresh_token)

        return await asyncio.to_thread(_invalidate_refresh)

    async def renew_access_token(self, refresh_token: str, api_secret: str) -> Dict[str, Any]:
        """
        Renew access token using refresh token.

        Returns: dict with access_token
        """
        def _renew() -> Dict[str, Any]:
            return self._kite.renew_access_token(refresh_token, api_secret)

        return await asyncio.to_thread(_renew)

    def set_session_expiry_hook(self, callback: Callable[[], None]) -> None:
        """
        Set callback for session expiry.
        """
        self._kite.set_session_expiry_hook(callback)

    # ------------------------------------------------------------------ internals
    def _ensure_pool(self) -> None:
        """Initialize WebSocket pool if not already started"""
        if self._pool_started and self._ws_pool:
            return

        if not self.access_token:
            raise RuntimeError(
                f"Account {self.account_id} has no access token. Call ensure_session() first."
            )

        if not self._loop:
            raise RuntimeError(
                f"Account {self.account_id} has no event loop. Call from async context."
            )

        # Get configuration
        ticker_mode = getattr(self._settings, "ticker_mode", "LTP").upper()
        max_instruments_per_connection = getattr(
            self._settings,
            "max_instruments_per_ws_connection",
            1000,
        )

        # Create pool
        self._ws_pool = KiteWebSocketPool(
            account_id=self.account_id,
            api_key=self.api_key,
            access_token=self.access_token,
            ws_root=WS_ROOT,
            ticker_mode=ticker_mode,
            max_instruments_per_connection=max_instruments_per_connection,
            tick_handler=self._tick_handler,
            error_handler=self._error_handler,
        )

        # Start pool
        self._ws_pool.start(self._loop)
        self._pool_started = True

        logger.info(
            "WebSocket pool initialized for account %s (mode=%s, max_per_connection=%d)",
            self.account_id,
            ticker_mode,
            max_instruments_per_connection,
        )

    def get_pool_stats(self) -> Optional[Dict[str, Any]]:
        """Get statistics about the WebSocket connection pool"""
        if not self._ws_pool:
            return None
        return self._ws_pool.get_stats()
