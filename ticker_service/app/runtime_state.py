"""
Runtime State Management

Manages mutable runtime state separately from immutable configuration.
Thread-safe state management for settings that can change during runtime.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from loguru import logger

from .config import get_settings


@dataclass
class RuntimeState:
    """Thread-safe runtime state for the ticker service"""

    # Mock data control
    mock_data_enabled: bool = field(default_factory=lambda: get_settings().enable_mock_data)
    mock_data_last_toggled: Optional[datetime] = None
    mock_data_toggled_by: Optional[str] = None

    # Add other runtime state as needed
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    async def set_mock_data_enabled(self, enabled: bool, changed_by: str = "api") -> None:
        """
        Enable or disable mock data generation.

        Args:
            enabled: True to enable mock data, False to disable
            changed_by: Who/what changed this setting (for audit trail)
        """
        async with self._lock:
            old_value = self.mock_data_enabled
            self.mock_data_enabled = enabled
            self.mock_data_last_toggled = datetime.now(timezone.utc)
            self.mock_data_toggled_by = changed_by

            if old_value != enabled:
                logger.warning(
                    f"Mock data {'enabled' if enabled else 'disabled'} by {changed_by} "
                    f"at {self.mock_data_last_toggled.isoformat()}"
                )

    async def get_mock_data_enabled(self) -> bool:
        """Thread-safe getter for mock data setting"""
        async with self._lock:
            return self.mock_data_enabled

    def get_mock_data_enabled_sync(self) -> bool:
        """Synchronous getter for mock data setting (use sparingly)"""
        return self.mock_data_enabled

    async def get_state_summary(self) -> dict:
        """Get a summary of the current runtime state"""
        async with self._lock:
            return {
                "mock_data_enabled": self.mock_data_enabled,
                "mock_data_last_toggled": (
                    self.mock_data_last_toggled.isoformat()
                    if self.mock_data_last_toggled
                    else None
                ),
                "mock_data_toggled_by": self.mock_data_toggled_by,
            }


# Global singleton
_runtime_state: Optional[RuntimeState] = None


def get_runtime_state() -> RuntimeState:
    """Get the global runtime state singleton"""
    global _runtime_state
    if _runtime_state is None:
        _runtime_state = RuntimeState()
    return _runtime_state
