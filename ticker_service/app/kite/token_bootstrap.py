# app/kite/token_bootstrap.py
from __future__ import annotations
import os, logging
from pathlib import Path
from typing import Dict, List
import json
from kiteconnect import KiteConnect

log = logging.getLogger("token_bootstrap")
log.setLevel(logging.INFO)

# --- Lazy-load .env next to this file into os.environ (without clobbering existing vars) ---
ENV_PATH = Path(__file__).with_name(".env")
if ENV_PATH.exists():
    try:
        from dotenv import dotenv_values
    except Exception as exc:  # pragma: no cover - import failure handled at runtime
        raise RuntimeError("python-dotenv is required: pip install python-dotenv") from exc
    file_vars = dotenv_values(str(ENV_PATH))
    for key, value in file_vars.items():
        if value is None:
            continue
        if os.getenv(key):
            log.debug("Env var %s already set, leaving existing value", key)
            continue
        os.environ[key] = value
        log.debug("Loaded %s from %s", key, ENV_PATH)
else:
    raise RuntimeError(f".env not found at {ENV_PATH}")

# Use relative import since we run with: python -m app.kite.token_bootstrap
from .session import KiteSession  # path-anchored token dir lives in session.py
def _mask(secret: str, retain: int = 2) -> str:
    if not secret:
        return ""
    if len(secret) <= retain * 2:
        return "*" * len(secret)
    return f"{secret[:retain]}{'*' * (len(secret) - retain * 2)}{secret[-retain:]}"

def _env_for_account(account: str) -> Dict[str, str]:
    ak  = os.getenv(f"KITE_{account}_API_KEY")  or os.getenv("KITE_API_KEY")
    as_ = os.getenv(f"KITE_{account}_API_SECRET") or os.getenv("KITE_API_SECRET")
    un  = os.getenv(f"KITE_{account}_USERNAME")
    pw  = os.getenv(f"KITE_{account}_PASSWORD")
    tk  = os.getenv(f"KITE_{account}_TOTP_KEY")

    missing = [k for k, v in {
        "api_key": ak, "api_secret": as_, "username": un, "password": pw, "totp_key": tk
    }.items() if not v]
    if missing:
        raise RuntimeError(
            f"Missing env for account '{account}': {', '.join(missing)}. "
            f"Set KITE_{account}_USERNAME/PASSWORD/TOTP_KEY and API key/secret "
            f"(shared KITE_API_KEY/KITE_API_SECRET or per-account overrides)."
        )
    return {"api_key": ak, "api_secret": as_, "username": un, "password": pw, "totp_key": tk}

def _token_path_for(account: str) -> Path:
    # same anchored tokens dir as session.py uses ("./tokens" relative to this module)
    return Path(__file__).with_name("tokens") / f"kite_token_{account}.json"

def _have_valid_cached_token(account: str, api_key: str) -> bool:
    """Return True if token file exists AND profile() succeeds with it."""
    p = _token_path_for(account)
    if not p.exists():
        log.debug("Token file missing for %s at %s", account, p)
        return False
    try:
        data = json.loads(p.read_text())
        access_token = data.get("access_token")
        if not access_token:
            log.debug("Token file %s missing access_token field", p)
            return False
        k = KiteConnect(api_key=api_key)
        k.set_access_token(access_token)
        # cheap authenticated call; raises if token is invalid/expired/revoked
        _ = k.profile()
        return True
    except Exception:
        log.exception("Cached token validation failed for %s (path=%s)", account, p)
        return False

def ensure_tokens_for_all(accounts: List[str]) -> None:
    raw = [a.strip() for a in accounts if a.strip()]
    if not raw:
        raise RuntimeError("No accounts specified (KITE_ACCOUNTS).")

    for acct in raw:
        log.info("Ensuring token for account=%s", acct)

        # Prefer per-account API key/secret; else shared
        ak  = os.getenv(f"KITE_{acct}_API_KEY")  or os.getenv("KITE_API_KEY")
        as_ = os.getenv(f"KITE_{acct}_API_SECRET") or os.getenv("KITE_API_SECRET")
        if not ak or not as_:
            raise RuntimeError(f"Missing API key/secret for '{acct}' (set shared KITE_API_KEY/SECRET or KITE_{acct}_API_KEY/SECRET)")

        # 1) Fast path: if cached token is valid, accept it (no creds needed)
        if _have_valid_cached_token(acct, ak):
            log.info("OK (cached): account=%s", acct)
            continue

        # 2) Slow path: require per-account creds, do auto-login via KiteSession
        creds = {
            "api_key":    ak,
            "api_secret": as_,
            "username":   os.getenv(f"KITE_{acct}_USERNAME"),
            "password":   os.getenv(f"KITE_{acct}_PASSWORD"),
            "totp_key":   os.getenv(f"KITE_{acct}_TOTP_KEY"),
        }
        missing = [k for k,v in creds.items() if not v and k in ("username","password","totp_key")]
        if missing:
            raise RuntimeError(
                f"Missing env for account '{acct}': {', '.join(missing)}. "
                f"Set KITE_{acct}_USERNAME/PASSWORD/TOTP_KEY (and API key/secret)."
            )

        log.debug("No valid cached token for %s, performing auto login", acct)
        ks = KiteSession(credentials=creds, account_id=acct)
        prof = ks.kite.profile()
        log.info("OK (fresh): account=%s user_id=%s", acct, prof.get("user_id"))

def run_bootstrap() -> None:
    accounts_csv = os.getenv("KITE_ACCOUNTS", "primary")
    accounts = [a.strip() for a in accounts_csv.split(",")]
    log.info("Ensuring Kite tokens for accounts=%s", ", ".join(accounts))
    for env_key in ("KITE_primary_USERNAME", "KITE_primary_PASSWORD", "KITE_primary_TOTP_KEY"):
        value = os.getenv(env_key)
        if value:
            log.debug("%s loaded (%s)", env_key, _mask(value))
        else:
            log.debug("%s not set", env_key)
    ensure_tokens_for_all(accounts)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    run_bootstrap()
