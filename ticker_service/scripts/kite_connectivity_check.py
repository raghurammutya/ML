#!/usr/bin/env python3
"""Simple connectivity check using local ticker_service helpers."""

from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv

from app.kite.session import KiteSession

BASE_DIR = Path(__file__).resolve().parents[1]
ENV_PATH = BASE_DIR / "Kite_FOdata_scripts" / ".env"
if ENV_PATH.exists():
    load_dotenv(ENV_PATH)


def main() -> None:
    credentials = {
        "api_key": os.getenv("KITE_API_KEY"),
        "api_secret": os.getenv("KITE_API_SECRET"),
        "username": os.getenv("KITE_USERNAME"),
        "password": os.getenv("KITE_PASSWORD"),
        "totp_key": os.getenv("KITE_TOTP_KEY"),
    }
    session = KiteSession(
        credentials=credentials,
        account_id=os.getenv("KITE_ACCOUNT", "default"),
        token_dir=BASE_DIR / "Kite_FOdata_scripts" / "tokens",
    )
    margins = session.ping()
    print(json.dumps(margins, indent=2))


if __name__ == "__main__":
    main()
