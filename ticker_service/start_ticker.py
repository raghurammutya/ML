#!/usr/bin/env python3
from __future__ import annotations
import os
os.environ.setdefault(
    "KITE_TOKEN_DIR",
    "/home/stocksadmin/Quantagro/tradingview-viz/ticker_service/app/kite/tokens"
)



import logging
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
env_loaded = load_dotenv(BASE_DIR / "app" / "kite" / ".env", override=False)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("ticker_startup")

logger.debug("Base directory set to %s", BASE_DIR)
logger.debug(".env load attempted -> success=%s", env_loaded)
logger.debug("Effective PORT env: %s", os.getenv("PORT"))
logger.debug("Configured Kite accounts: %s", os.getenv("KITE_ACCOUNTS"))

from app.kite.token_bootstrap import run_bootstrap

logger.info("Running Kite token bootstrap...")
run_bootstrap()
logger.info("Token bootstrap complete.")

import uvicorn

port = int(os.getenv("PORT", "8080"))
logging.info("Starting ticker_service on port %s", port)
uvicorn.run("app.main:app", host="0.0.0.0", port=port)
