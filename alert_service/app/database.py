"""
Database Connection Management
Provides asyncpg connection pool for PostgreSQL/TimescaleDB
"""

import asyncpg
import logging
from typing import Optional
from contextlib import asynccontextmanager

from .config import get_settings

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages database connection pool."""

    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None
        self.settings = get_settings()

    async def connect(self):
        """Create database connection pool."""
        if self.pool is not None:
            logger.warning("Database pool already exists")
            return

        try:
            self.pool = await asyncpg.create_pool(
                host=self.settings.db_host,
                port=self.settings.db_port,
                database=self.settings.db_name,
                user=self.settings.db_user,
                password=self.settings.db_password,
                min_size=self.settings.db_pool_min_size,
                max_size=self.settings.db_pool_max_size,
                command_timeout=60,
            )
            logger.info(
                f"Database pool created: {self.settings.db_host}:{self.settings.db_port}/{self.settings.db_name}"
            )

            # Test connection
            async with self.pool.acquire() as conn:
                version = await conn.fetchval("SELECT version()")
                logger.info(f"Database connected: {version}")

        except Exception as e:
            logger.error(f"Failed to create database pool: {e}")
            raise

    async def disconnect(self):
        """Close database connection pool."""
        if self.pool is None:
            return

        try:
            await self.pool.close()
            logger.info("Database pool closed")
            self.pool = None
        except Exception as e:
            logger.error(f"Error closing database pool: {e}")
            raise

    @asynccontextmanager
    async def acquire(self):
        """Acquire connection from pool."""
        if self.pool is None:
            raise RuntimeError("Database pool not initialized")

        async with self.pool.acquire() as connection:
            yield connection


# Global database manager instance
_db_manager: Optional[DatabaseManager] = None


async def get_database_manager() -> DatabaseManager:
    """Get or create global database manager instance."""
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
        await _db_manager.connect()
    return _db_manager


async def close_database_manager():
    """Close global database manager."""
    global _db_manager
    if _db_manager is not None:
        await _db_manager.disconnect()
        _db_manager = None
