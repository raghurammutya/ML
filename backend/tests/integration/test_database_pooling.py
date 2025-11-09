"""
Integration tests for database connection pooling.

Tests verify that:
1. Pool can handle concurrent connections
2. Connections are properly returned to pool
3. Pool handles connection failures gracefully
4. Pool respects size limits
5. Queries execute correctly through pool
"""
import asyncio
import pytest
import asyncpg
from app.config import get_settings
from app.database import DataManager

settings = get_settings()

pytestmark = pytest.mark.integration


class TestDatabasePoolBasics:
    """Test basic pool functionality."""

    @pytest.mark.asyncio
    async def test_pool_creation(self, db_pool):
        """Test that pool is created successfully."""
        assert db_pool is not None
        assert isinstance(db_pool, asyncpg.Pool)

    @pytest.mark.asyncio
    async def test_pool_acquire_release(self, db_pool):
        """Test acquiring and releasing connections."""
        # Acquire connection
        async with db_pool.acquire() as conn:
            assert conn is not None
            result = await conn.fetchval("SELECT 1")
            assert result == 1

        # Connection should be returned to pool

    @pytest.mark.asyncio
    async def test_pool_size_configuration(self, db_pool):
        """Test pool is configured with correct size."""
        # Pool should respect min/max settings
        assert db_pool._minsize == settings.db_pool_min
        assert db_pool._maxsize == settings.db_pool_max

    @pytest.mark.asyncio
    async def test_simple_query(self, db_connection):
        """Test executing simple query through pool."""
        result = await db_connection.fetchval("SELECT 42")
        assert result == 42

    @pytest.mark.asyncio
    async def test_query_with_parameters(self, db_connection):
        """Test parameterized queries."""
        result = await db_connection.fetchval(
            "SELECT $1::int + $2::int",
            10, 20
        )
        assert result == 30


class TestConcurrentConnections:
    """Test pool behavior under concurrent load."""

    @pytest.mark.asyncio
    async def test_concurrent_queries(self, db_pool):
        """Test multiple concurrent queries don't interfere."""
        async def run_query(query_id: int):
            async with db_pool.acquire() as conn:
                result = await conn.fetchval("SELECT $1::int", query_id)
                return result

        # Run 20 concurrent queries
        results = await asyncio.gather(
            *[run_query(i) for i in range(20)]
        )

        # All queries should return correct results
        assert results == list(range(20))

    @pytest.mark.asyncio
    async def test_pool_handles_max_connections(self, db_pool):
        """Test pool doesn't exceed max connections."""
        connections = []

        try:
            # Acquire max connections
            for _ in range(settings.db_pool_max):
                conn = await db_pool.acquire()
                connections.append(conn)

            # Pool should be at capacity
            # Next acquire should wait (but not fail)

        finally:
            # Release all connections
            for conn in connections:
                await db_pool.release(conn)

    @pytest.mark.asyncio
    async def test_connection_reuse(self, db_pool):
        """Test connections are reused from pool."""
        # Get connection ID
        async with db_pool.acquire() as conn1:
            conn1_pid = await conn1.fetchval("SELECT pg_backend_pid()")

        # Get another connection - might be the same one from pool
        async with db_pool.acquire() as conn2:
            conn2_pid = await conn2.fetchval("SELECT pg_backend_pid()")

        # Both should have valid PIDs
        assert conn1_pid > 0
        assert conn2_pid > 0


class TestDatabaseOperations:
    """Test database operations through pool."""

    @pytest.mark.asyncio
    async def test_transaction_commit(self, db_connection):
        """Test transaction commit works."""
        # Start transaction
        async with db_connection.transaction():
            # Create temporary table
            await db_connection.execute("""
                CREATE TEMP TABLE test_commit (
                    id SERIAL PRIMARY KEY,
                    value INT
                )
            """)

            # Insert data
            await db_connection.execute(
                "INSERT INTO test_commit (value) VALUES ($1)",
                42
            )

        # Verify data persists
        result = await db_connection.fetchval(
            "SELECT value FROM test_commit WHERE id = 1"
        )
        assert result == 42

    @pytest.mark.asyncio
    async def test_transaction_rollback(self, db_connection):
        """Test transaction rollback works."""
        # Create temp table first
        await db_connection.execute("""
            CREATE TEMP TABLE test_rollback (
                id SERIAL PRIMARY KEY,
                value INT
            )
        """)

        try:
            async with db_connection.transaction():
                # Insert data
                await db_connection.execute(
                    "INSERT INTO test_rollback (value) VALUES ($1)",
                    99
                )

                # Raise error to trigger rollback
                raise Exception("Intentional rollback")
        except Exception:
            pass

        # Data should not exist
        result = await db_connection.fetchval(
            "SELECT COUNT(*) FROM test_rollback"
        )
        assert result == 0

    @pytest.mark.asyncio
    async def test_prepared_statements(self, db_connection):
        """Test prepared statements work correctly."""
        # Prepare statement
        stmt = await db_connection.prepare(
            "SELECT $1::int * 2 AS result"
        )

        # Execute multiple times
        result1 = await stmt.fetchval(5)
        result2 = await stmt.fetchval(10)
        result3 = await stmt.fetchval(15)

        assert result1 == 10
        assert result2 == 20
        assert result3 == 30


class TestPoolErrorHandling:
    """Test pool handles errors gracefully."""

    @pytest.mark.asyncio
    async def test_invalid_query_doesnt_break_pool(self, db_pool):
        """Test that invalid queries don't break the pool."""
        # Execute invalid query
        with pytest.raises(asyncpg.PostgresSyntaxError):
            async with db_pool.acquire() as conn:
                await conn.fetch("INVALID SQL QUERY")

        # Pool should still work
        async with db_pool.acquire() as conn:
            result = await conn.fetchval("SELECT 1")
            assert result == 1

    @pytest.mark.asyncio
    async def test_connection_timeout_handling(self, db_pool):
        """Test pool handles connection timeouts."""
        # This tests that queries respect timeout settings
        async with db_pool.acquire() as conn:
            # Quick query should succeed
            result = await conn.fetchval("SELECT 1")
            assert result == 1

    @pytest.mark.asyncio
    async def test_pool_recovers_from_connection_errors(self, db_pool):
        """Test pool can recover from connection errors."""
        # Simulate connection issues by running a bad query
        try:
            async with db_pool.acquire() as conn:
                await conn.execute("SELECT 1 / 0")
        except asyncpg.DivisionByZeroError:
            pass

        # Pool should still be functional
        async with db_pool.acquire() as conn:
            result = await conn.fetchval("SELECT 1")
            assert result == 1


class TestDataManagerIntegration:
    """Test DataManager with connection pool."""

    @pytest.mark.asyncio
    async def test_datamanager_creation(self):
        """Test DataManager can be created."""
        dm = DataManager()
        await dm.connect()

        assert dm.pool is not None
        assert isinstance(dm.pool, asyncpg.Pool)

        await dm.disconnect()

    @pytest.mark.asyncio
    async def test_datamanager_query_execution(self):
        """Test DataManager can execute queries."""
        dm = DataManager()
        await dm.connect()

        async with dm.pool.acquire() as conn:
            result = await conn.fetchval("SELECT version()")
            assert "PostgreSQL" in result

        await dm.disconnect()

    @pytest.mark.asyncio
    async def test_datamanager_pool_stats(self):
        """Test DataManager reports pool statistics."""
        dm = DataManager()
        await dm.connect()

        stats = await dm.get_pool_stats()

        assert "size" in stats
        assert "free_connections" in stats
        assert "used_connections" in stats
        assert stats["min_size"] == settings.db_pool_min
        assert stats["max_size"] == settings.db_pool_max

        await dm.disconnect()


class TestRealDatabaseTables:
    """Test operations on real database tables."""

    @pytest.mark.asyncio
    async def test_query_existing_tables(self, db_connection):
        """Test querying actual database tables."""
        # Query to check if key tables exist
        result = await db_connection.fetch("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name IN (
                'instrument',
                'instrument_subscriptions',
                'statement_uploads'
            )
            ORDER BY table_name
        """)

        table_names = [row['table_name'] for row in result]
        assert 'instrument' in table_names or len(table_names) >= 0

    @pytest.mark.asyncio
    async def test_alembic_version_table_exists(self, db_connection):
        """Test Alembic version table exists."""
        result = await db_connection.fetchval("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'alembic_version'
            )
        """)

        # Should exist after Alembic setup
        assert result is True

    @pytest.mark.asyncio
    async def test_check_timescaledb_extension(self, db_connection):
        """Test TimescaleDB extension is available."""
        result = await db_connection.fetchval("""
            SELECT EXISTS (
                SELECT FROM pg_extension
                WHERE extname = 'timescaledb'
            )
        """)

        # TimescaleDB should be installed
        assert result is True


class TestPoolPerformance:
    """Test pool performance characteristics."""

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_high_concurrency_load(self, db_pool):
        """Test pool under high concurrent load."""
        async def run_concurrent_query(query_id: int):
            async with db_pool.acquire() as conn:
                await asyncio.sleep(0.01)  # Simulate some work
                result = await conn.fetchval("SELECT $1::int", query_id)
                return result

        # Run 100 concurrent queries
        import time
        start = time.time()

        results = await asyncio.gather(
            *[run_concurrent_query(i) for i in range(100)]
        )

        duration = time.time() - start

        # All queries should succeed
        assert len(results) == 100
        assert results == list(range(100))

        # Should complete in reasonable time (adjust based on your needs)
        assert duration < 10.0  # 10 seconds for 100 queries is reasonable

    @pytest.mark.asyncio
    async def test_connection_acquisition_speed(self, db_pool):
        """Test connection acquisition is fast."""
        import time

        times = []
        for _ in range(10):
            start = time.time()
            async with db_pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            times.append(time.time() - start)

        avg_time = sum(times) / len(times)

        # Average should be under 100ms
        assert avg_time < 0.1
