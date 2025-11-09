"""
Shared fixtures for integration tests.
"""
import asyncio
import os
import pytest
import asyncpg

# Unset ENVIRONMENT if it's set to invalid value
if os.getenv('ENVIRONMENT') == 'dev':
    os.environ.pop('ENVIRONMENT', None)

from app.config import get_settings

settings = get_settings()


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def db_pool():
    """Create database pool for integration tests."""
    pool = await asyncpg.create_pool(
        host=settings.db_host,
        port=settings.db_port,
        database=settings.db_name,
        user=settings.db_user,
        password=settings.db_password,
        min_size=settings.db_pool_min,
        max_size=settings.db_pool_max,
        command_timeout=settings.db_query_timeout,
    )
    yield pool
    await pool.close()


@pytest.fixture
async def db_connection(db_pool):
    """Get a connection from the pool."""
    async with db_pool.acquire() as connection:
        yield connection
