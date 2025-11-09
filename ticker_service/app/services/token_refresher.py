"""
Automatic Kite token refresh service.

Ensures trading accounts have valid access tokens by:
1. Monitoring token expiry times
2. Automatically refreshing tokens before they expire
3. Scheduling daily token refresh at a configurable time
"""

from __future__ import annotations

import asyncio
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Optional, Dict, Any
from zoneinfo import ZoneInfo

from loguru import logger


class TokenRefresher:
    """
    Monitors and refreshes Kite access tokens to ensure uninterrupted service.

    Features:
    - Daily automatic refresh at configured time (default: 7:00 AM IST)
    - Pre-emptive refresh when tokens near expiry (default: 1 hour before)
    - Graceful error handling with retries
    """

    def __init__(
        self,
        token_dir: Path | str = "./tokens",
        refresh_time_hour: int = 7,
        refresh_time_minute: int = 0,
        timezone_str: str = "Asia/Kolkata",
        preemptive_refresh_minutes: int = 60,
    ):
        """
        Initialize token refresher.

        Args:
            token_dir: Directory containing token files
            refresh_time_hour: Hour of day to refresh (24-hour format)
            refresh_time_minute: Minute of hour to refresh
            timezone_str: Timezone for scheduling (default: Asia/Kolkata)
            preemptive_refresh_minutes: Refresh this many minutes before expiry
        """
        self._token_dir = Path(token_dir) if isinstance(token_dir, str) else token_dir
        self._refresh_hour = refresh_time_hour
        self._refresh_minute = refresh_time_minute
        self._preemptive_minutes = preemptive_refresh_minutes

        try:
            self._timezone = ZoneInfo(timezone_str)
        except Exception:
            logger.warning(f"Invalid timezone {timezone_str}, falling back to UTC")
            self._timezone = timezone.utc

        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._accounts: Dict[str, Any] = {}

    async def start(self, accounts: Dict[str, Any]) -> None:
        """
        Start the token refresher service.

        Args:
            accounts: Dictionary of account configurations with credentials
        """
        if self._running:
            logger.warning("TokenRefresher already running")
            return

        self._accounts = accounts
        self._running = True
        self._task = asyncio.create_task(self._refresh_loop())

        logger.info(
            f"TokenRefresher started | daily_refresh={self._refresh_hour:02d}:{self._refresh_minute:02d} "
            f"{self._timezone} | preemptive={self._preemptive_minutes}min"
        )

    async def stop(self) -> None:
        """Stop the token refresher service."""
        if not self._running:
            return

        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        logger.info("TokenRefresher stopped")

    async def _refresh_loop(self) -> None:
        """Main loop that schedules and executes token refreshes."""
        # Wait a bit for service to fully start up
        await asyncio.sleep(30)

        while self._running:
            try:
                # Calculate time until next scheduled refresh
                now = datetime.now(self._timezone)
                target_time = time(hour=self._refresh_hour, minute=self._refresh_minute)
                next_refresh = datetime.combine(now.date(), target_time, tzinfo=self._timezone)

                # If we've passed today's refresh time, schedule for tomorrow
                if next_refresh <= now:
                    next_refresh = datetime.combine(
                        now.date() + timedelta(days=1),
                        target_time,
                        tzinfo=self._timezone
                    )

                seconds_until = (next_refresh - now).total_seconds()
                logger.info(
                    f"Next token refresh scheduled for {next_refresh.isoformat()} "
                    f"(in {seconds_until / 3600:.1f} hours)"
                )

                # Sleep until scheduled time (check every hour for early refresh needs)
                check_interval = min(3600, seconds_until)
                await asyncio.sleep(check_interval)

                # If we've reached the scheduled time, refresh all tokens
                if datetime.now(self._timezone) >= next_refresh:
                    await self._refresh_all_tokens()

                # Also check if any tokens need preemptive refresh
                await self._check_preemptive_refresh()

            except Exception as exc:
                logger.error(f"Token refresh loop error: {exc}", exc_info=True)
                await asyncio.sleep(300)  # Wait 5 minutes before retrying

    async def _refresh_all_tokens(self) -> None:
        """Refresh tokens for all configured accounts."""
        logger.info("Starting scheduled token refresh for all accounts")

        for account_id, account_config in self._accounts.items():
            try:
                await self._refresh_account_token(account_id, account_config)
            except Exception as exc:
                logger.error(f"Failed to refresh token for {account_id}: {exc}", exc_info=True)

        logger.info("Completed scheduled token refresh")

    async def _refresh_account_token(
        self,
        account_id: str,
        account_config: Dict[str, Any]
    ) -> None:
        """
        Refresh token for a single account using KiteSession auto-login.

        Args:
            account_id: Account identifier
            account_config: Account credentials and configuration
        """
        logger.info(f"Refreshing token for account: {account_id}")

        # Import KiteSession here to avoid circular dependencies
        try:
            from ..kite.session import KiteSession
        except ImportError:
            logger.error("KiteSession not available for token refresh")
            return

        try:
            # Extract credentials from account config
            credentials = {
                "api_key": account_config.get("api_key"),
                "api_secret": account_config.get("api_secret"),
                "username": account_config.get("username"),
                "password": account_config.get("password"),
                "totp_key": account_config.get("totp_key"),
            }

            # Validate required credentials
            missing = [k for k, v in credentials.items() if not v]
            if missing:
                logger.warning(
                    f"Cannot refresh token for {account_id}: missing {', '.join(missing)}"
                )
                return

            # Perform auto-login to refresh token
            # KiteSession will automatically save the new token
            session = KiteSession(
                credentials=credentials,
                account_id=account_id,
                token_dir=self._token_dir
            )

            # Validate the new token
            profile = session.kite.profile()
            logger.info(
                f"✓ Token refreshed successfully for {account_id} "
                f"(user_id={profile.get('user_id')})"
            )

        except Exception as exc:
            logger.error(
                f"Failed to refresh token for {account_id}: {exc}",
                exc_info=True
            )
            # Don't re-raise - continue with other accounts

    async def _check_preemptive_refresh(self) -> None:
        """Check if any tokens need preemptive refresh based on expiry time."""
        import json

        if not self._token_dir.exists():
            return

        for token_file in self._token_dir.glob("kite_token_*.json"):
            try:
                data = json.loads(token_file.read_text())
                expires_at_str = data.get("expires_at")

                if not expires_at_str:
                    continue

                expires_at = datetime.fromisoformat(expires_at_str)
                now = datetime.now()

                # Check if token expires within preemptive window
                time_until_expiry = (expires_at - now).total_seconds() / 60  # minutes

                if 0 < time_until_expiry < self._preemptive_minutes:
                    # Extract account ID from filename: kite_token_primary.json -> primary
                    account_id = token_file.stem.replace("kite_token_", "")

                    logger.warning(
                        f"Token for {account_id} expires in {time_until_expiry:.0f} minutes, "
                        f"triggering preemptive refresh"
                    )

                    account_config = self._accounts.get(account_id)
                    if account_config:
                        await self._refresh_account_token(account_id, account_config)

            except Exception as exc:
                logger.error(f"Error checking token {token_file.name}: {exc}")

    def get_status(self) -> Dict[str, Any]:
        """Get current status of token refresher."""
        import json

        token_status = []

        if self._token_dir.exists():
            for token_file in self._token_dir.glob("kite_token_*.json"):
                try:
                    data = json.loads(token_file.read_text())
                    account_id = token_file.stem.replace("kite_token_", "")
                    expires_at_str = data.get("expires_at")

                    if expires_at_str:
                        expires_at = datetime.fromisoformat(expires_at_str)
                        now = datetime.now()
                        minutes_until_expiry = (expires_at - now).total_seconds() / 60

                        token_status.append({
                            "account_id": account_id,
                            "expires_at": expires_at_str,
                            "minutes_until_expiry": int(minutes_until_expiry),
                            "is_valid": minutes_until_expiry > 0,
                        })
                except Exception as exc:
                    logger.debug(f"Error reading token status for {token_file.name}: {exc}")

        # Calculate next scheduled refresh
        now = datetime.now(self._timezone)
        target_time = time(hour=self._refresh_hour, minute=self._refresh_minute)
        next_refresh = datetime.combine(now.date(), target_time, tzinfo=self._timezone)
        if next_refresh <= now:
            next_refresh = datetime.combine(
                now.date() + timedelta(days=1),
                target_time,
                tzinfo=self._timezone
            )

        return {
            "running": self._running,
            "next_scheduled_refresh": next_refresh.isoformat(),
            "timezone": str(self._timezone),
            "preemptive_refresh_minutes": self._preemptive_minutes,
            "managed_accounts": len(self._accounts),
            "tokens": token_status,
        }


# Global instance
token_refresher = TokenRefresher()
