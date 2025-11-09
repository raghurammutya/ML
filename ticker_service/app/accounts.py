from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass, field
from contextlib import AbstractAsyncContextManager
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from loguru import logger
import yaml

from .config import get_settings
from .user_service_client import fetch_remote_trading_accounts
from .database_loader import load_accounts_from_database, check_database_connection
from .kite.client import KiteClient

KITE_SCRIPTS_ROOT = Path(__file__).resolve().parents[2] / "Kite_FOdata_scripts"
DEFAULT_ACCOUNTS_FILE = KITE_SCRIPTS_ROOT / "kite_accounts.yaml"


def _resolve_env_value(value: str) -> str:
    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
        env_name = value[2:-1]
        return os.getenv(env_name, "")
    return value


def _load_access_token(account_id: str, token_dir: Path) -> str:
    token_file = token_dir / f"kite_token_{account_id}.json"
    if not token_file.exists():
        return ""
    try:
        with open(token_file, "r", encoding="utf-8") as fp:
            payload = json.load(fp)
    except json.JSONDecodeError:
        return ""
    return payload.get("access_token") or payload.get("enctoken", "")


@dataclass
class KiteAccount:
    account_id: str
    api_key: str
    api_secret: str | None = None
    access_token: str | None = None
    username: str | None = None
    password: str | None = None
    totp_key: str | None = None
    token_dir: Path | None = None

    @classmethod
    def from_raw(cls, account_id: str, raw: Dict[str, Any], base_dir: Path) -> KiteAccount:
        resolved: Dict[str, Any] = {}
        for key, value in raw.items():
            if key == "token_dir":
                token_dir = Path(value)
                if not token_dir.is_absolute():
                    token_dir = (base_dir / token_dir).resolve()
                resolved[key] = token_dir
                continue
            resolved[key] = _resolve_env_value(value)

        token_dir = resolved.get("token_dir") or base_dir / "tokens"
        access_token = resolved.get("access_token")
        env_prefix = f"KITE_{account_id}_"
        api_key = resolved.get("api_key") or os.getenv(f"{env_prefix}API_KEY") or os.getenv("KITE_API_KEY", "")
        api_secret = resolved.get("api_secret") or os.getenv(f"{env_prefix}API_SECRET") or os.getenv("KITE_API_SECRET")
        username = resolved.get("username") or os.getenv(f"{env_prefix}USERNAME")
        password = resolved.get("password") or os.getenv(f"{env_prefix}PASSWORD")
        totp_key = resolved.get("totp_key") or os.getenv(f"{env_prefix}TOTP_KEY")
        if not access_token:
            token_dir_path = Path(token_dir)
            access_token = _load_access_token(account_id, token_dir_path)
        if not api_key:
            raise RuntimeError(
                f"Missing API key for account '{account_id}'. "
                f"Set KITE_{account_id}_API_KEY or store it in the YAML/env."
            )

        return cls(
            account_id=account_id,
            api_key=api_key,
            api_secret=api_secret,
            access_token=access_token or None,
            username=username,
            password=password,
            totp_key=totp_key,
            token_dir=Path(token_dir),
        )


def _load_accounts_from_yaml(accounts_file: Path) -> Dict[str, KiteAccount]:
    if not accounts_file.exists():
        raise FileNotFoundError(f"Kite accounts file not found: {accounts_file}")

    logger.debug("Loading accounts from YAML: %s", accounts_file)
    with open(accounts_file, "r", encoding="utf-8") as fp:
        data = yaml.safe_load(fp) or {}

    raw_accounts: Dict[str, Dict[str, Any]] = data.get("accounts", {})
    if not raw_accounts:
        raise ValueError(f"No accounts configured in {accounts_file}")

    base_dir = accounts_file.parent
    accounts: Dict[str, KiteAccount] = {}
    for account_id, raw in raw_accounts.items():
        logger.debug("Processing account %s from YAML", account_id)
        try:
            accounts[account_id] = KiteAccount.from_raw(account_id, raw, base_dir)
        except RuntimeError as exc:
            logger.warning("Skipping account %s from YAML: %s", account_id, exc)
    return accounts


def _load_accounts_from_database() -> Dict[str, KiteAccount]:
    """
    Load accounts from ticker_service database (kite_accounts table).

    This is the primary method for production deployments.
    Credentials are stored encrypted in the database and decrypted on load.

    Returns:
        Dict mapping account_id to KiteAccount objects
    """
    logger.info("Loading Kite accounts from database")
    db_accounts = load_accounts_from_database()

    if not db_accounts:
        raise FileNotFoundError("No accounts found in database or database connection failed")

    accounts: Dict[str, KiteAccount] = {}
    for account_id, creds in db_accounts.items():
        token_dir = Path(creds.get('token_dir', './tokens'))
        if not token_dir.is_absolute():
            token_dir = (Path(__file__).parent / token_dir).resolve()

        accounts[account_id] = KiteAccount(
            account_id=account_id,
            api_key=creds['api_key'],
            api_secret=creds.get('api_secret'),
            access_token=creds.get('access_token'),
            username=creds.get('username'),
            password=creds.get('password'),
            totp_key=creds.get('totp_key'),
            token_dir=token_dir,
        )

        logger.debug(
            "Loaded account %s from database: username=%s, tier=%s",
            account_id,
            creds.get('username'),
            creds.get('subscription_tier')
        )

    logger.info("Loaded %d account(s) from database", len(accounts))
    return accounts


def _load_accounts_from_env() -> Dict[str, KiteAccount]:
    settings = get_settings()
    accounts_csv = os.getenv("KITE_ACCOUNTS", "default")
    account_ids = [item.strip() for item in accounts_csv.split(",") if item.strip()]
    if not account_ids:
        account_ids = ["default"]

    logger.debug("Falling back to environment based accounts: %s", account_ids)
    accounts: Dict[str, KiteAccount] = {}
    for account_id in account_ids:
        prefix = f"KITE_{account_id}_"
        api_key = os.getenv(f"{prefix}API_KEY") or settings.kite_api_key
        api_secret = os.getenv(f"{prefix}API_SECRET") or settings.kite_api_secret or None
        access_token = os.getenv(f"{prefix}ACCESS_TOKEN") or settings.kite_access_token or None
        username = os.getenv(f"{prefix}USERNAME") or None
        password = os.getenv(f"{prefix}PASSWORD") or None
        totp_key = os.getenv(f"{prefix}TOTP_KEY") or None

        token_dir_env = os.getenv(f"{prefix}TOKEN_DIR") or os.getenv("KITE_TOKEN_DIR")
        token_dir: Path | None = None
        if token_dir_env:
            raw_path = Path(token_dir_env)
            token_dir = raw_path if raw_path.is_absolute() else (Path(__file__).parent / token_dir_env).resolve()
            logger.debug("Account %s using token dir %s", account_id, token_dir)

        if not api_key:
            raise FileNotFoundError(
                f"Missing API key for account '{account_id}'. Set {prefix}API_KEY or KITE_API_KEY."
            )

        logger.debug(
            "Configured env account %s | has_access_token=%s",
            account_id,
            bool(access_token),
        )
        accounts[account_id] = KiteAccount(
            account_id=account_id,
            api_key=api_key,
            api_secret=api_secret,
            access_token=access_token,
            username=username,
            password=password,
            totp_key=totp_key,
            token_dir=token_dir,
        )

    if not accounts:
        raise FileNotFoundError(
            "Kite accounts file missing and no environment based accounts configured. "
            "Set KITE_ACCOUNTS and per-account credentials."
        )
    logger.info("Loaded %d account(s) from environment", len(accounts))
    return accounts


@dataclass
class AccountSession:
    account_id: str
    client: KiteClient
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    last_used: float = field(default=0.0)
    tasks_inflight: int = field(default=0)
    failures: int = field(default=0)

    async def acquire(self) -> KiteClient:
        await self.lock.acquire()
        self.tasks_inflight += 1
        self.last_used = time.time()
        return self.client

    def release(self) -> None:
        if self.tasks_inflight > 0:
            self.tasks_inflight -= 1
        if self.lock.locked():
            self.lock.release()


class AccountLease(AbstractAsyncContextManager):
    def __init__(self, session: AccountSession):
        self._session = session
        self._client: KiteClient | None = None

    async def __aenter__(self) -> KiteClient:
        self._client = await self._session.acquire()
        return self._client

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if exc:
            self._session.failures += 1
        self._session.release()


class SessionOrchestrator:
    """
    Light-weight orchestration layer that mirrors the behaviour of the standalone
    Kite_FOdata_scripts session manager so the ticker service can reuse the same
    multi-account rotation logic.
    """

    def __init__(self, accounts_file: Optional[Path] = None):
        settings = get_settings()
        self._accounts: Dict[str, KiteAccount] = {}
        accounts_loaded = False

        # Priority 1: User service API (if enabled)
        if settings.use_user_service_accounts:
            remote_accounts = fetch_remote_trading_accounts()
            if remote_accounts:
                try:
                    self._accounts = self._build_accounts_from_remote(remote_accounts)
                    accounts_loaded = True
                    logger.info("Loaded %d Kite account(s) from user service", len(self._accounts))
                except Exception as exc:
                    logger.exception("Failed to build accounts from user service response: %s", exc)

        # Priority 2: Database (ticker_service owns credentials)
        if not accounts_loaded and check_database_connection():
            try:
                self._accounts = _load_accounts_from_database()
                accounts_loaded = True
                logger.info("Loaded %d Kite account(s) from database", len(self._accounts))
            except Exception as exc:
                logger.warning("Failed to load accounts from database: %s", exc)

        # Priority 3: YAML file (legacy/development)
        if not accounts_loaded:
            accounts_file = Path(accounts_file or os.getenv("KITE_ACCOUNTS_FILE", DEFAULT_ACCOUNTS_FILE))
            logger.debug("SessionOrchestrator initialising with accounts_file=%s", accounts_file)
            try:
                self._accounts = _load_accounts_from_yaml(accounts_file)
                logger.info("Loaded Kite accounts from YAML (%d found)", len(self._accounts))
            except FileNotFoundError:
                logger.warning("Accounts file %s not found; falling back to environment", accounts_file)
                # Priority 4: Environment variables (last resort)
                self._accounts = _load_accounts_from_env()

        self._sessions: Dict[str, AccountSession] = {}
        for account_id, account in self._accounts.items():
            client = KiteClient.from_account(account)
            self._sessions[account_id] = AccountSession(account_id=account_id, client=client)
            logger.debug("Session created for account %s", account_id)

        # Allow running without accounts when mock mode is enabled
        if not self._sessions and not settings.enable_mock_data:
            raise RuntimeError("No Kite accounts available for ticker service.")
        elif not self._sessions:
            logger.warning("Running ticker service without Kite accounts (mock mode enabled)")

        self._rotation = list(self._sessions.values())
        self._rr_index = 0
        logger.info("SessionOrchestrator ready with accounts: %s", ", ".join(self.list_accounts()))

    def get_default_session(self) -> KiteClient:
        """
        Returns the KiteClient for the default account.
        Falls back to the first available account if 'default' is not explicitly configured.
        Returns None if no accounts are configured (mock mode).
        """
        if "default" in self._sessions:
            return self._sessions["default"].client
        return self._rotation[0].client if self._rotation else None

    @staticmethod
    def _build_accounts_from_remote(records: List[Dict[str, Any]]) -> Dict[str, KiteAccount]:
        """
        Build KiteAccount objects from remote trading account records.

        Filters accounts to only include those with market data access (Connect/Startup tier).
        Personal API accounts (free tier) are excluded as they cannot subscribe to market data.
        """
        # Filter to accounts with market data access only
        market_data_accounts = [
            rec for rec in records
            if rec.get("market_data_available", False)
        ]

        no_market_data_accounts = [
            rec for rec in records
            if not rec.get("market_data_available", False)
        ]

        # Log filtering results
        if no_market_data_accounts:
            excluded_ids = [rec.get("broker_user_id", rec.get("trading_account_id")) for rec in no_market_data_accounts]
            excluded_tiers = [rec.get("subscription_tier", "unknown") for rec in no_market_data_accounts]
            logger.warning(
                "Excluding %d account(s) without market data access: %s (tiers: %s)",
                len(no_market_data_accounts),
                excluded_ids,
                excluded_tiers
            )
            logger.info(
                "These accounts have Personal API tier (free) which does not support WebSocket market data. "
                "They can still be used for trading via other APIs."
            )

        logger.info(
            "Loading %d account(s) with market data access for WebSocket subscriptions",
            len(market_data_accounts)
        )

        # Log tier information for loaded accounts
        for rec in market_data_accounts:
            tier = rec.get("subscription_tier", "unknown")
            broker_id = rec.get("broker_user_id", rec.get("trading_account_id"))
            logger.info(
                "Account %s: tier=%s, market_data=True",
                broker_id,
                tier
            )

        # Build KiteAccount objects from filtered list
        accounts: Dict[str, KiteAccount] = {}
        for record in market_data_accounts:
            account_id = str(record["trading_account_id"])
            accounts[account_id] = KiteAccount(
                account_id=account_id,
                api_key=record["api_key"],
                api_secret=record.get("api_secret"),
                access_token=record.get("access_token"),
                username=record.get("broker_user_id"),
                password=record.get("password"),
                totp_key=record.get("totp_seed"),
                token_dir=None,
            )
        return accounts
    def list_accounts(self) -> List[str]:
        return list(self._sessions.keys())

    def get_account_config(self, account_id: str) -> KiteAccount | None:
        return self._accounts.get(account_id)

    def primary_account_id(self) -> Optional[str]:
        return self._rotation[0].account_id if self._rotation else None

    def get_client_for_api_call(self, preferred_account: Optional[str] = None) -> KiteClient:
        """
        Get a KiteClient for API calls WITHOUT acquiring exclusive lock.

        This bypasses the locking mechanism since API calls (historical data, quotes, etc.)
        don't need exclusive access - they're thread-safe operations that just make HTTP requests.
        Only WebSocket operations need exclusive locks.

        Args:
            preferred_account: Optional account ID to use

        Returns:
            KiteClient instance
        """
        if preferred_account:
            session = self._sessions.get(preferred_account)
            if not session:
                raise KeyError(f"Account '{preferred_account}' not registered.")
            logger.debug("Getting client for API call from account %s", preferred_account)
            return session.client

        # Round-robin selection for API calls
        session = self._rotation[self._rr_index % len(self._rotation)]
        self._rr_index = (self._rr_index + 1) % len(self._rotation)
        logger.debug("Getting client for API call from account %s via round-robin", session.account_id)
        return session.client

    def borrow(self, preferred_account: Optional[str] = None) -> AccountLease:
        if preferred_account:
            session = self._sessions.get(preferred_account)
            if not session:
                raise KeyError(f"Account '{preferred_account}' not registered.")
            logger.debug("Borrowing preferred account %s", preferred_account)
            return AccountLease(session)
        session = self._next_available_session()
        logger.debug("Borrowing account %s via round-robin", session.account_id)
        return AccountLease(session)

    def _next_available_session(self) -> AccountSession:
        start = self._rr_index
        while True:
            session = self._rotation[self._rr_index]
            self._rr_index = (self._rr_index + 1) % len(self._rotation)
            if not session.lock.locked():
                return session
            if self._rr_index == start:
                return session

    def distribute(self, work_items: Iterable[Any]) -> Dict[str, List[Any]]:
        result: Dict[str, List[Any]] = {session.account_id: [] for session in self._rotation}
        rotation_len = len(self._rotation)
        if rotation_len == 0:
            return {}
        rr = 0
        for item in work_items:
            account_id = self._rotation[rr].account_id
            result[account_id].append(item)
            rr = (rr + 1) % rotation_len
        logger.debug(
            "Distributed %d work items across accounts: %s",
            sum(len(items) for items in result.values()),
            {k: len(v) for k, v in result.items()},
        )
        return {key: value for key, value in result.items() if value}

    def stats(self) -> List[Dict[str, Any]]:
        return [
            {
                "account_id": session.account_id,
                "last_used": session.last_used,
                "tasks_inflight": session.tasks_inflight,
                "failures": session.failures,
            }
            for session in self._rotation
        ]

    async def reload_accounts(self, accounts_from_db: List[Dict[str, Any]]) -> None:
        """
        Reload trading accounts from database dynamically.

        This allows adding/removing accounts without service restart.

        Args:
            accounts_from_db: List of account dicts from database with decrypted credentials
        """
        from pathlib import Path

        logger.info(f"Reloading accounts from database ({len(accounts_from_db)} accounts)")

        # Convert database accounts to KiteAccount objects
        new_accounts: Dict[str, KiteAccount] = {}
        for db_account in accounts_from_db:
            if not db_account.get("is_active", True):
                logger.debug(f"Skipping inactive account: {db_account['account_id']}")
                continue

            # Convert to KiteAccount
            account_id = db_account["account_id"]
            token_dir = db_account.get("token_dir")
            if token_dir:
                token_dir = Path(token_dir)
            else:
                # Default token directory
                token_dir = Path(__file__).parent.parent / "tokens"

            new_accounts[account_id] = KiteAccount(
                account_id=account_id,
                api_key=db_account["api_key"],
                api_secret=db_account.get("api_secret"),
                access_token=db_account.get("access_token"),
                username=db_account.get("username"),
                password=db_account.get("password"),
                totp_key=db_account.get("totp_key"),
                token_dir=token_dir
            )
            logger.debug(f"Loaded account {account_id} from database")

        if not new_accounts:
            raise RuntimeError("No active accounts loaded from database")

        # Close old sessions (release connections, cleanup)
        old_account_ids = set(self._accounts.keys())
        new_account_ids = set(new_accounts.keys())

        removed_accounts = old_account_ids - new_account_ids
        added_accounts = new_account_ids - old_account_ids

        logger.info(f"Accounts removed: {removed_accounts or 'none'}")
        logger.info(f"Accounts added: {added_accounts or 'none'}")

        # Update internal state
        self._accounts = new_accounts
        self._sessions.clear()

        # Create new sessions
        for account_id, account in self._accounts.items():
            client = KiteClient.from_account(account)
            self._sessions[account_id] = AccountSession(account_id=account_id, client=client)
            logger.debug(f"Created new session for account {account_id}")

        # Update rotation list
        self._rotation = list(self._sessions.values())
        self._rr_index = 0

        logger.info(f"Account reload complete. Active accounts: {', '.join(self.list_accounts())}")


# Global orchestrator singleton
_orchestrator_instance: SessionOrchestrator | None = None


def get_orchestrator() -> SessionOrchestrator:
    """
    Get the global SessionOrchestrator singleton instance.
    Creates one if it doesn't exist yet.
    """
    global _orchestrator_instance
    if _orchestrator_instance is None:
        _orchestrator_instance = SessionOrchestrator()
    return _orchestrator_instance
