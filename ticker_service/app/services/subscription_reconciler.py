"""
Subscription reconciliation service.

Syncs runtime subscription state with database, handles reload requests.
Extracted from generator.py to improve modularity.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

from loguru import logger

from ..subscription_store import subscription_store, SubscriptionRecord
from ..instrument_registry import instrument_registry
from ..schema import Instrument
from ..utils.subscription_reloader import SubscriptionReloader


@dataclass
class SubscriptionPlanItem:
    """Item in subscription plan with record and resolved instrument"""
    record: SubscriptionRecord
    instrument: Instrument


class SubscriptionReconciler:
    """
    Manages subscription reconciliation and reloads.

    Responsibilities:
    - Load subscription plan from database
    - Build instrument assignments for accounts
    - Handle subscription reload requests
    - Coordinate with SubscriptionReloader for rate limiting
    """

    def __init__(self, market_tz):
        """
        Initialize subscription reconciler.

        Args:
            market_tz: Market timezone for expiry comparisons
        """
        self._market_tz = market_tz
        self._subscription_reloader: Optional[SubscriptionReloader] = None
        self._reload_callback: Optional[callable] = None

    def initialize_reloader(self, reload_callback: callable) -> None:
        """
        Initialize the subscription reloader with callback.

        Args:
            reload_callback: Async function to call when reload needed
        """
        self._reload_callback = reload_callback
        self._subscription_reloader = SubscriptionReloader(
            reload_fn=reload_callback,
            debounce_seconds=1.0,
            max_reload_frequency_seconds=5.0,
        )

    async def start_reloader(self) -> None:
        """Start the subscription reloader background task"""
        if self._subscription_reloader:
            await self._subscription_reloader.start()

    async def stop_reloader(self) -> None:
        """Stop the subscription reloader background task"""
        if self._subscription_reloader:
            await self._subscription_reloader.stop()

    async def load_subscription_plan(self) -> List[SubscriptionPlanItem]:
        """
        Load active subscription plan from database.

        Filters out:
        - Stale instruments (not in registry or inactive)
        - Expired contracts (past expiry date)

        Returns:
            List of SubscriptionPlanItem with resolved instruments
        """
        await instrument_registry.initialise()

        active_records = await subscription_store.list_active()
        if not active_records:
            return []

        plan: List[SubscriptionPlanItem] = []
        stale: List[int] = []
        expired: List[int] = []

        # Get current date in market timezone for expiry comparison
        today_market = datetime.now(self._market_tz).date()

        for record in active_records:
            metadata = await instrument_registry.fetch_metadata(record.instrument_token)
            if not metadata or not metadata.is_active:
                stale.append(record.instrument_token)
                continue

            # Check if instrument has expired (for options with expiry dates)
            instrument = metadata.to_instrument()
            if instrument.expiry and instrument.expiry < today_market:
                expired.append(record.instrument_token)
                logger.info(
                    "Marking expired contract for deactivation: %s (expiry=%s, today=%s)",
                    instrument.tradingsymbol,
                    instrument.expiry,
                    today_market
                )
                continue

            plan.append(
                SubscriptionPlanItem(
                    record=record,
                    instrument=instrument,
                )
            )

        # Deactivate stale and expired subscriptions
        for token in stale:
            try:
                await subscription_store.deactivate(token)
                logger.info("Deactivated subscription %s – instrument missing or inactive.", token)
            except Exception as exc:
                logger.exception("Failed to deactivate stale subscription %s: %s", token, exc)

        for token in expired:
            try:
                await subscription_store.deactivate(token)
                logger.info("Deactivated subscription %s – contract expired.", token)
            except Exception as exc:
                logger.exception("Failed to deactivate expired subscription %s: %s", token, exc)

        if expired:
            logger.info("Deactivated %d expired contract subscriptions", len(expired))

        return plan

    async def build_assignments(
        self,
        plan_items: List[SubscriptionPlanItem],
        available_accounts: List[str],
    ) -> Dict[str, List[Instrument]]:
        """
        Build instrument assignments for accounts using round-robin.

        Args:
            plan_items: List of SubscriptionPlanItem
            available_accounts: List of account IDs

        Returns:
            Dict mapping account_id -> list of instruments
        """
        if not available_accounts:
            return {}

        assignments: Dict[str, List[Instrument]] = {account_id: [] for account_id in available_accounts}
        rr_index = 0
        account_count = len(available_accounts)

        for item in plan_items:
            target_account = item.record.account_id if item.record.account_id in assignments else None
            if target_account is None:
                target_account = available_accounts[rr_index % account_count]
                rr_index += 1

            assignments[target_account].append(item.instrument)
            try:
                await subscription_store.update_account(item.record.instrument_token, target_account)
            except Exception as exc:
                logger.exception(
                    "Failed to persist account assignment for token %s -> %s: %s",
                    item.record.instrument_token,
                    target_account,
                    exc,
                )

        return {account: instruments for account, instruments in assignments.items() if instruments}

    def trigger_reload(self) -> None:
        """Trigger a subscription reload (non-blocking)"""
        if self._subscription_reloader:
            self._subscription_reloader.trigger_reload()
        else:
            logger.warning("Subscription reloader not initialized, ignoring reload trigger")

    async def reload_subscriptions_blocking(self) -> None:
        """Blocking reload of subscriptions (for API endpoint)"""
        if self._reload_callback:
            await self._reload_callback()
        else:
            logger.warning("Reload callback not set, cannot perform reload")
