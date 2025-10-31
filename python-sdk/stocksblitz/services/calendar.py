"""
Calendar Service - Reminders and scheduled events.

Provides functionality to set one-time or recurring reminders and get alerted.
"""

import uuid
import threading
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime, timedelta

from ..enums import ReminderFrequency
from ..types import Reminder
from ..exceptions import APIError


class CalendarService:
    """
    Calendar and reminder service.

    Features:
    - One-time reminders
    - Recurring reminders (daily, weekly, monthly)
    - Custom schedules
    - Callbacks when reminders trigger

    Examples:
        # Get calendar service
        calendar = client.calendar

        # One-time reminder
        reminder_id = calendar.set_reminder(
            title="Check NIFTY position",
            scheduled_at=datetime(2025, 10, 31, 15, 0),
            callback=lambda r: print(f"Reminder: {r.title}")
        )

        # Recurring reminder (daily at 9:15 AM)
        calendar.set_recurring_reminder(
            title="Market open",
            frequency=ReminderFrequency.DAILY,
            scheduled_at=datetime.now().replace(hour=9, minute=15),
            callback=lambda r: print("Market is open!")
        )

        # Custom recurring (every 5 minutes)
        calendar.set_recurring_reminder(
            title="Check RSI",
            frequency=ReminderFrequency.CUSTOM,
            scheduled_at=datetime.now(),
            metadata={"interval_minutes": 5}
        )
    """

    def __init__(self, api_client: 'APIClient'):
        """Initialize calendar service."""
        self._api = api_client
        self._reminders: Dict[str, Reminder] = {}
        self._lock = threading.Lock()
        self._monitoring = False
        self._monitor_thread: Optional[threading.Thread] = None

    def set_reminder(
        self,
        title: str,
        scheduled_at: datetime,
        description: str = "",
        callback: Optional[Callable[[Reminder], None]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Set a one-time reminder.

        Args:
            title: Reminder title
            scheduled_at: When to trigger
            description: Detailed description
            callback: Callback function
            metadata: Additional data

        Returns:
            Reminder ID

        Example:
            reminder_id = calendar.set_reminder(
                title="Close positions",
                scheduled_at=datetime(2025, 10, 31, 15, 30),
                description="Close all positions before market close",
                callback=lambda r: close_all_positions()
            )
        """
        reminder_id = str(uuid.uuid4())
        reminder = Reminder(
            reminder_id=reminder_id,
            title=title,
            description=description,
            frequency=ReminderFrequency.ONCE,
            scheduled_at=scheduled_at,
            next_trigger=scheduled_at,
            callback=callback,
            metadata=metadata or {}
        )

        with self._lock:
            self._reminders[reminder_id] = reminder

        # TODO: Send to API
        # self._api.post("/calendar/reminders", json=reminder.to_dict())

        return reminder_id

    def set_recurring_reminder(
        self,
        title: str,
        frequency: ReminderFrequency,
        scheduled_at: datetime,
        description: str = "",
        callback: Optional[Callable[[Reminder], None]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Set a recurring reminder.

        Args:
            title: Reminder title
            frequency: How often to repeat
            scheduled_at: First occurrence time
            description: Detailed description
            callback: Callback function
            metadata: Additional data (e.g., interval_minutes for CUSTOM)

        Returns:
            Reminder ID

        Example:
            # Daily at 9:15 AM
            calendar.set_recurring_reminder(
                title="Market open",
                frequency=ReminderFrequency.DAILY,
                scheduled_at=datetime.now().replace(hour=9, minute=15),
                callback=lambda r: print("Market is open!")
            )

            # Every 5 minutes
            calendar.set_recurring_reminder(
                title="Check indicators",
                frequency=ReminderFrequency.CUSTOM,
                scheduled_at=datetime.now(),
                metadata={"interval_minutes": 5}
            )
        """
        reminder_id = str(uuid.uuid4())
        reminder = Reminder(
            reminder_id=reminder_id,
            title=title,
            description=description,
            frequency=frequency,
            scheduled_at=scheduled_at,
            next_trigger=scheduled_at,
            callback=callback,
            metadata=metadata or {}
        )

        with self._lock:
            self._reminders[reminder_id] = reminder

        # TODO: Send to API
        # self._api.post("/calendar/reminders", json=reminder.to_dict())

        return reminder_id

    def cancel_reminder(self, reminder_id: str) -> bool:
        """
        Cancel a reminder.

        Args:
            reminder_id: Reminder ID

        Returns:
            True if cancelled, False if not found

        Example:
            success = calendar.cancel_reminder(reminder_id)
        """
        with self._lock:
            if reminder_id in self._reminders:
                del self._reminders[reminder_id]
                return True
        return False

        # TODO: Delete from API
        # self._api.delete(f"/calendar/reminders/{reminder_id}")

    def enable_reminder(self, reminder_id: str) -> bool:
        """Enable a reminder."""
        reminder = self.get_reminder(reminder_id)
        if reminder:
            reminder.enabled = True
            return True
        return False

    def disable_reminder(self, reminder_id: str) -> bool:
        """Disable a reminder (without deleting)."""
        reminder = self.get_reminder(reminder_id)
        if reminder:
            reminder.enabled = False
            return True
        return False

    def get_reminder(self, reminder_id: str) -> Optional[Reminder]:
        """Get reminder by ID."""
        return self._reminders.get(reminder_id)

    def get_reminders(
        self,
        frequency: Optional[ReminderFrequency] = None,
        enabled_only: bool = True
    ) -> List[Reminder]:
        """
        Get reminders with filters.

        Args:
            frequency: Filter by frequency
            enabled_only: Only enabled reminders

        Returns:
            List of reminders

        Example:
            # Get all daily reminders
            daily = calendar.get_reminders(
                frequency=ReminderFrequency.DAILY
            )
        """
        with self._lock:
            results = list(self._reminders.values())

        if frequency:
            results = [r for r in results if r.frequency == frequency]
        if enabled_only:
            results = [r for r in results if r.enabled]

        return results

    def get_upcoming(
        self,
        hours: int = 24,
        enabled_only: bool = True
    ) -> List[Reminder]:
        """
        Get upcoming reminders.

        Args:
            hours: Look ahead hours
            enabled_only: Only enabled reminders

        Returns:
            List of upcoming reminders

        Example:
            # Get reminders in next 4 hours
            upcoming = calendar.get_upcoming(hours=4)
        """
        cutoff = datetime.now() + timedelta(hours=hours)
        reminders = self.get_reminders(enabled_only=enabled_only)

        return [
            r for r in reminders
            if r.next_trigger and r.next_trigger <= cutoff
        ]

    def trigger_reminder(self, reminder_id: str) -> bool:
        """
        Manually trigger a reminder.

        Args:
            reminder_id: Reminder ID

        Returns:
            True if triggered, False if not found

        Example:
            calendar.trigger_reminder(reminder_id)
        """
        reminder = self.get_reminder(reminder_id)
        if not reminder:
            return False

        reminder.trigger()

        # Calculate next trigger for recurring reminders
        if reminder.frequency != ReminderFrequency.ONCE:
            reminder.next_trigger = self._calculate_next_trigger(reminder)

        return True

    def _calculate_next_trigger(self, reminder: Reminder) -> datetime:
        """Calculate next trigger time for recurring reminder."""
        if reminder.frequency == ReminderFrequency.DAILY:
            return reminder.last_triggered + timedelta(days=1)
        elif reminder.frequency == ReminderFrequency.WEEKLY:
            return reminder.last_triggered + timedelta(weeks=1)
        elif reminder.frequency == ReminderFrequency.MONTHLY:
            return reminder.last_triggered + timedelta(days=30)
        elif reminder.frequency == ReminderFrequency.CUSTOM:
            interval = reminder.metadata.get("interval_minutes", 60)
            return reminder.last_triggered + timedelta(minutes=interval)
        else:
            return None

    def start_monitoring(self) -> None:
        """
        Start background monitoring for reminders.

        Example:
            calendar.start_monitoring()
        """
        if self._monitoring:
            return

        self._monitoring = True
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop,
            daemon=True
        )
        self._monitor_thread.start()

    def stop_monitoring(self) -> None:
        """Stop background monitoring."""
        self._monitoring = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)
            self._monitor_thread = None

    def _monitor_loop(self) -> None:
        """Background monitoring loop."""
        import time

        while self._monitoring:
            try:
                now = datetime.now()
                reminders = self.get_reminders(enabled_only=True)

                for reminder in reminders:
                    if reminder.next_trigger and reminder.next_trigger <= now:
                        self.trigger_reminder(reminder.reminder_id)

                time.sleep(10)  # Check every 10 seconds
            except Exception as e:
                print(f"Error in calendar monitor: {e}")

    def clear_history(self, days: int = 7) -> int:
        """
        Clear old one-time reminders.

        Args:
            days: Clear reminders older than this many days

        Returns:
            Number of reminders cleared

        Example:
            # Clear reminders older than 7 days
            count = calendar.clear_history(days=7)
        """
        cutoff = datetime.now() - timedelta(days=days)
        count = 0

        with self._lock:
            to_remove = [
                rid for rid, r in self._reminders.items()
                if (r.frequency == ReminderFrequency.ONCE and
                    r.last_triggered and
                    r.last_triggered < cutoff)
            ]
            for rid in to_remove:
                del self._reminders[rid]
                count += 1

        return count
