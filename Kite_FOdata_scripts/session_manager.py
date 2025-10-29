"""
Session orchestration for multiple Kite accounts.

This module focuses on:
1. Maintaining KiteService instances per configured account.
2. Providing a `borrow()` context manager that tracks usage / lock ownership.
3. Offering helper methods to distribute work units (expiries, strikes, etc.)
   across the available accounts in a round-robin fashion.

Future enhancements (documented in README):
  • integrate live subscription counts to respect Kite's instrument caps
  • persist usage metrics so restarts keep the rotation balanced
  • expose async callbacks for automatic resubscribe/retry on failures
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from dataclasses import dataclass, field
from typing import Iterator, Iterable, List, Dict, Optional, Any

from kite_accounts import KiteAccountManager, get_kite_service
from services.kite_service import KiteService


@dataclass
class AccountSession:
    account_id: str
    service: KiteService
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    last_used: float = field(default=0.0)
    tasks_inflight: int = field(default=0)
    failures: int = field(default=0)

    async def acquire(self):
        await self.lock.acquire()
        self.tasks_inflight += 1
        self.last_used = time.time()
        return self

    def release(self):
        if self.tasks_inflight > 0:
            self.tasks_inflight -= 1
        if self.lock.locked():
            self.lock.release()


class AccountLease(contextlib.AbstractAsyncContextManager):
    def __init__(self, session: AccountSession):
        self._session = session

    async def __aenter__(self) -> KiteService:
        await self._session.acquire()
        return self._session.service

    async def __aexit__(self, exc_type, exc, tb):
        if exc:
            self._session.failures += 1
        self._session.release()


class SessionOrchestrator:
    """
    Provides the orchestration layer for multi-account usage.
    """

    def __init__(self, account_manager: Optional[KiteAccountManager] = None):
        self.account_manager = account_manager or KiteAccountManager()
        self._sessions: Dict[str, AccountSession] = {}
        for account_id in self.account_manager.list_accounts():
            service = self.account_manager.get(account_id)
            self._sessions[account_id] = AccountSession(account_id=account_id, service=service)
        self._rotation = list(self._sessions.values())
        if not self._rotation:
            raise RuntimeError("No Kite accounts available in SessionOrchestrator.")
        self._rr_index = 0

    def borrow(self, preferred_account: Optional[str] = None) -> AccountLease:
        """
        Returns an async context manager (AccountLease) that yields a KiteService.
        """
        if preferred_account:
            session = self._sessions.get(preferred_account)
            if not session:
                raise KeyError(f"Account '{preferred_account}' not registered.")
            return AccountLease(session)
        session = self._next_available_session()
        return AccountLease(session)

    def _next_available_session(self) -> AccountSession:
        start = self._rr_index
        while True:
            session = self._rotation[self._rr_index]
            self._rr_index = (self._rr_index + 1) % len(self._rotation)
            # if lock is free, use it, otherwise keep scanning
            if not session.lock.locked():
                return session
            if self._rr_index == start:
                # All busy, pick the currently selected session anyway
                return session

    def distribute(self, work_items: Iterable[Any]) -> Dict[str, List[Any]]:
        """
        Assign work items to accounts in round-robin fashion.

        Example:
            orchestrator.distribute(["2025-11-07","2025-11-14"])
            -> {"primary":["2025-11-07"], "secondary":["2025-11-14"]}
        """
        result: Dict[str, List[Any]] = {session.account_id: [] for session in self._rotation}
        rr = 0
        rotation_len = len(self._rotation)
        for work in work_items:
            account_id = self._rotation[rr].account_id
            result[account_id].append(work)
            rr = (rr + 1) % rotation_len
        # drop empty assignments to keep downstream logic light
        return {k: v for k, v in result.items() if v}

    def idle_accounts(self) -> List[str]:
        return [session.account_id for session in self._rotation if not session.lock.locked()]
