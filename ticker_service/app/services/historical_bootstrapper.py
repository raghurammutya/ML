"""
Historical data bootstrapping service.

Backfills missing historical data for option instruments.
Extracted from generator.py to improve modularity.
"""
from __future__ import annotations

import time
from typing import Dict, List

from loguru import logger

from ..schema import Instrument
from ..kite.client import KiteClient
from ..config import get_settings

settings = get_settings()


class HistoricalBootstrapper:
    """
    Manages historical data backfill for option instruments.

    Responsibilities:
    - Track which accounts have been bootstrapped
    - Batch historical data requests
    - Coordinate with KiteClient for API calls
    """

    def __init__(self):
        """Initialize bootstrapper"""
        self._bootstrap_done: Dict[str, bool] = {}

    def is_bootstrap_done(self, account_id: str) -> bool:
        """Check if account has been bootstrapped"""
        return self._bootstrap_done.get(account_id, False)

    def mark_bootstrap_done(self, account_id: str) -> None:
        """Mark account as bootstrapped"""
        self._bootstrap_done[account_id] = True

    def reset_bootstrap_state(self) -> None:
        """Reset all bootstrap state"""
        self._bootstrap_done.clear()

    async def backfill_missing_history(
        self,
        account_id: str,
        instruments: List[Instrument],
        client: KiteClient,
    ) -> None:
        """
        Backfill missing historical data for instruments.

        Args:
            account_id: Account ID for logging
            instruments: List of instruments to backfill
            client: KiteClient for API calls
        """
        if self.is_bootstrap_done(account_id):
            logger.debug(f"Historical bootstrap already done for {account_id}, skipping")
            return

        if settings.historical_days <= 0:
            logger.debug("Historical bootstrap disabled (historical_days <= 0)")
            return

        now = int(time.time())
        from_ts = now - settings.historical_days * 86400
        sample = instruments[:settings.historical_bootstrap_batch]

        logger.info(
            f"Starting historical bootstrap for {account_id} "
            f"(sampling {len(sample)}/{len(instruments)} instruments, {settings.historical_days} days)"
        )

        for instrument in sample:
            try:
                await client.fetch_historical(
                    instrument_token=instrument.instrument_token,
                    from_ts=from_ts,
                    to_ts=now,
                    interval="minute",
                )
            except Exception as exc:
                logger.error(
                    "Historical fetch failed [%s token=%s]: %s",
                    client.account_id,
                    instrument.instrument_token,
                    exc
                )

        self.mark_bootstrap_done(account_id)
        logger.info(
            "Historical bootstrap complete | account=%s instruments=%d days=%d",
            client.account_id,
            len(sample),
            settings.historical_days,
        )

        if not sample:
            logger.debug("Historical bootstrap skipped (no instruments sampled)")
