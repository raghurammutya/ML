from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Optional

import yaml

from services.kite_service import KiteService

DEFAULT_ACCOUNTS_FILE = Path(__file__).parent / "kite_accounts.yaml"
DEFAULT_ACCOUNT_ENV = "KITE_ACCOUNT"


class KiteAccountManager:
    def __init__(self, accounts_file: Optional[Path] = None):
        self.accounts_file = Path(accounts_file or os.getenv("KITE_ACCOUNTS_FILE", DEFAULT_ACCOUNTS_FILE))
        if not self.accounts_file.exists():
            raise FileNotFoundError(f"Kite accounts file not found: {self.accounts_file}")
        with open(self.accounts_file, "r") as fp:
            data = yaml.safe_load(fp) or {}
        self._accounts: Dict[str, Dict[str, str]] = data.get("accounts", {})
        if not self._accounts:
            raise ValueError("No accounts configured in kite_accounts.yaml")
        self._services: Dict[str, KiteService] = {}

    def list_accounts(self):
        return list(self._accounts.keys())

    def get(self, account_id: Optional[str] = None) -> KiteService:
        account_id = account_id or os.getenv(DEFAULT_ACCOUNT_ENV) or next(iter(self._accounts.keys()))
        if account_id not in self._accounts:
            raise KeyError(f"Account '{account_id}' not found in configuration. Available: {self.list_accounts()}")
        if account_id not in self._services:
            creds = self._resolve_credentials(self._accounts[account_id])
            token_dir = Path(creds.pop("token_dir", "./tokens"))
            self._services[account_id] = KiteService(credentials=creds, account_id=account_id, token_dir=token_dir)
        return self._services[account_id]

    def _resolve_credentials(self, raw: Dict[str, str]) -> Dict[str, str]:
        resolved = {}
        for key, value in raw.items():
            if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
                env_name = value[2:-1]
                resolved[key] = os.getenv(env_name, "")
            else:
                resolved[key] = value
        return resolved


_manager: Optional[KiteAccountManager] = None


def get_kite_service(account_id: Optional[str] = None) -> KiteService:
    global _manager
    if _manager is None:
        _manager = KiteAccountManager()
    return _manager.get(account_id)
