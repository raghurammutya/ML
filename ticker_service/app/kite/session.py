from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, time
from pathlib import Path
from typing import Dict, Optional
from urllib.parse import urlparse, parse_qs

import requests
from kiteconnect import KiteConnect

try:
    import pyotp
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("pyotp is required for Kite session automation") from exc

# SEC-CRITICAL-003 FIX: Import secure token storage
from .secure_token_storage import get_secure_storage

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class KiteSession:
    def __init__(
        self,
        credentials: Optional[Dict[str, str]] = None,
        account_id: str = "default",
        token_dir: Path | str = "./tokens",
    ) -> None:
        creds = credentials or {}
        self.api_key = creds.get("api_key") or os.getenv("KITE_API_KEY")
        self.api_secret = creds.get("api_secret") or os.getenv("KITE_API_SECRET")
        self.username = creds.get("username") or os.getenv("KITE_USERNAME")
        self.password = creds.get("password") or os.getenv("KITE_PASSWORD")
        self.totp_key = creds.get("totp_key") or os.getenv("KITE_TOTP_KEY")
        self.account_id = account_id or creds.get("account_id") or os.getenv("KITE_ACCOUNT", "default")
        if not self.api_key or not self.api_secret:
            raise ValueError("KITE_API_KEY and KITE_API_SECRET are required")

        self.kite = KiteConnect(api_key=self.api_key)
        base = Path(__file__).parent  # app/kite
        self._token_dir = (Path(token_dir) if Path(token_dir).is_absolute()
                   else base / token_dir)
        self._token_dir.mkdir(parents=True, exist_ok=True)
        self.token_path = self._token_dir / f"kite_token_{self.account_id}.json"

        # Try cached token; fall back to login on failure.
        if not self._load_existing_token():
            logger.info("No valid cached token; performing auto-login.")
            self.auto_login()

    # ------------------------------------------------------------------
    def _load_existing_token(self) -> bool:
        """
        Load existing token from secure encrypted storage.

        SEC-CRITICAL-003 FIX: Uses encrypted token storage instead of plaintext.
        Automatically migrates from old plaintext format if found.
        """
        try:
            # SEC-CRITICAL-003 FIX: Load from encrypted storage
            storage = get_secure_storage()
            payload = storage.load_token(self.token_path)

            if not payload:
                return False

            expires_at = datetime.fromisoformat(payload["expires_at"])
            if expires_at <= datetime.now():
                logger.info("Cached token expired at %s", expires_at.isoformat())
                return False

            access_token = payload["access_token"]
            self.kite.set_access_token(access_token)

            # Validate token by making a trivial authenticated call
            try:
                self.kite.profile()  # throws if invalid/expired/revoked
            except Exception as e:
                logger.warning("Cached token failed validation: %s", e)
                return False

            logger.info("Loaded cached token for %s (encrypted)", self.account_id)
            return True
        except Exception as exc:
            logger.warning("Failed to load cached token (%s)", exc)
            return False

    def _save_access_token(self, access_token: str) -> None:
        """
        Save access token to secure encrypted storage.

        SEC-CRITICAL-003 FIX: Uses encrypted token storage with proper file permissions (600).
        """
        # Many brokers rotate access tokens at start of trading day; keep your heuristic
        expiry = datetime.combine(datetime.now().date() + timedelta(days=1), time(hour=7, minute=30))
        payload = {
            "access_token": access_token,
            "expires_at": expiry.isoformat(),
            "created_at": datetime.now().isoformat(),
        }

        # SEC-CRITICAL-003 FIX: Save to encrypted storage with 600 permissions
        storage = get_secure_storage()
        storage.save_token(self.token_path, payload)
        logger.info("Saved new access token (encrypted); expires at %s", payload["expires_at"])

    # ------------------------------------------------------------------
    def auto_login(self) -> None:
        if not all([self.username, self.password, self.totp_key]):
            raise RuntimeError("Username/password/TOTP required for automated login")

        session = requests.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0 (KiteSession/auto-login)"})

        # Step 1: primary login
        login_resp = session.post(
            "https://kite.zerodha.com/api/login",
            data={"user_id": self.username, "password": self.password},
            timeout=20,
        )
        login_resp.raise_for_status()
        login_data = login_resp.json()
        if login_data.get("status") != "success":
            raise RuntimeError(f"Login failed: {login_data}")

        request_id = login_data["data"]["request_id"]

        # Step 2: 2FA (TOTP)
        totp_code = pyotp.TOTP(self.totp_key).now()
        twofa_resp = session.post(
            "https://kite.zerodha.com/api/twofa",
            data={
                "user_id": self.username,
                "request_id": request_id,
                "twofa_value": totp_code,
                "twofa_type": "totp",
            },
            timeout=20,
        )
        twofa_resp.raise_for_status()
        if twofa_resp.json().get("status") != "success":
            raise RuntimeError(f"TOTP verification failed: {twofa_resp.text}")

        # Step 3: visit the KiteConnect login URL while authenticated
        # This should redirect to a URL containing ?request_token=...&status=success
        resp = session.get(self.kite.login_url(), allow_redirects=True, timeout=20)

        request_token = self._extract_request_token(resp)
        if not request_token:
            raise RuntimeError("Unable to extract request_token from redirect chain")

        # Step 4: exchange request_token for access_token
        data = self.kite.generate_session(request_token=request_token, api_secret=self.api_secret)
        access_token = data["access_token"]
        self.kite.set_access_token(access_token)
        self._save_access_token(access_token)

    # ------------------------------------------------------------------
    @staticmethod
    def _extract_request_token(response: requests.Response) -> Optional[str]:
        """
        Extract request_token from either the final URL or any redirect in response.history.
        """
        candidates = [*(response.history or []), response]
        for r in candidates:
            try:
                url = r.url
                qs = parse_qs(urlparse(url).query)
                token = qs.get("request_token", [None])[0]
                status = qs.get("status", [None])[0]
                if token and (status in (None, "success")):
                    return token
            except Exception:
                continue
        return None
