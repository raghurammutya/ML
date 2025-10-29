"""Shared configuration for Kite FO data scripts."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env placed in Kite_FOdata_scripts so overrides can be applied per env
load_dotenv(Path(__file__).parent / ".env")

def _env(name: str, default: str | None = None) -> str:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value

DB_CONFIG = {
    "host": _env("DEV_DB_HOST", _env("DB_HOST", "127.0.0.1")),
    "port": int(_env("DEV_DB_PORT", _env("DB_PORT", "5433"))),
    "database": _env("DEV_DB_NAME", _env("DB_NAME", "stocksblitz_unified_dev")),
    "user": _env("DEV_DB_USER", _env("DB_USER", "stocksblitz")),
    "password": _env("DEV_DB_PASSWORD", _env("DB_PASSWORD", "dev_password")),
}

__all__ = ["DB_CONFIG"]
