# Implementation Prompt: Architecture Fixes (Week 4)

**Priority**: P1 (HIGH)
**Estimated Duration**: 5-7 days (1 engineer)
**Prerequisites**: Security remediation complete
**Blocking**: Scalability and deployment reliability

---

## Objective

Fix **3 critical architectural issues** identified in Phase 1 Architecture Review to enable production scalability and reliable deployments.

**Critical Issues**:
1. Missing migration framework (Alembic) - deployment risk
2. Connection pool too small (20 vs 100 needed) - service outage at 20% load
3. Global state anti-pattern (15+ globals) - fragile initialization

**Success Criteria**: System scales to 100 concurrent users, zero-downtime deployments possible, global state eliminated.

---

## Context

**Working Directory**: `/mnt/stocksblitz-data/Quantagro/tradingview-viz/backend`
**Reference**: `/docs/assessment_1/phase1_architecture_reassessment.md`
**Current Architecture Grade**: B+ (82/100)
**Target Architecture Grade**: A (90/100)

---

## Task 1: Implement Alembic Migration Framework - Days 1-2

### Background

**Current State**: Raw SQL files in `migrations/`, no version tracking, no rollback support
**Risk**: Cannot safely deploy schema changes, no rollback plan
**Impact**: Production deployment blocked

### Implementation Steps

**Step 1.1: Install Alembic**
```bash
cd /mnt/stocksblitz-data/Quantagro/tradingview-viz/backend
pip install alembic==1.12.0 asyncpg==0.28.0
echo "alembic==1.12.0" >> requirements.txt
```

**Step 1.2: Initialize Alembic**
```bash
alembic init alembic

# Output:
# Created alembic/ directory
# Created alembic.ini configuration
```

**Step 1.3: Configure alembic.ini**
```ini
# alembic.ini - UPDATE
[alembic]
script_location = alembic
sqlalchemy.url = postgresql://stocksblitz:%(DB_PASSWORD)s@localhost:5432/stocksblitz_unified

# Use async driver
[alembic:async]
# For asyncpg support
```

**Step 1.4: Configure alembic/env.py for async**
```python
# alembic/env.py - UPDATE FOR ASYNC
from logging.config import fileConfig
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context
import asyncio
import os

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Alembic Config object
config = context.config

# Update sqlalchemy.url with environment variable
config.set_main_option(
    "sqlalchemy.url",
    f"postgresql+asyncpg://stocksblitz:{os.getenv('DB_PASSWORD')}@localhost:5432/stocksblitz_unified"
)

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Target metadata (for autogenerate support)
target_metadata = None


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (SQL output only)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations in 'online' mode (execute against database)."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def do_run_migrations(connection: Connection) -> None:
    """Execute migrations within connection context."""
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
```

**Step 1.5: Create initial migration (from existing schema)**
```bash
# Generate initial migration from current database
alembic revision --autogenerate -m "initial_schema"

# Edit generated file: alembic/versions/XXXX_initial_schema.py
# Verify it captures all existing tables
```

**Step 1.6: Mark current database as migrated**
```bash
# Stamp database with current version (don't run migrations)
alembic stamp head
```

**Step 1.7: Create example migration**
```bash
# Create new migration
alembic revision -m "add_strategy_notes_column"
```

```python
# alembic/versions/XXXX_add_strategy_notes_column.py
"""add_strategy_notes_column

Revision ID: abc123
Revises: def456
Create Date: 2025-11-09 10:00:00
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = 'abc123'
down_revision = 'def456'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add notes column to strategies table."""
    op.add_column('strategies', sa.Column('notes', sa.Text(), nullable=True))


def downgrade() -> None:
    """Remove notes column from strategies table."""
    op.drop_column('strategies', 'notes')
```

**Step 1.8: Run migration**
```bash
# Apply migration
alembic upgrade head

# Verify migration
alembic current

# Test rollback
alembic downgrade -1  # Rollback 1 version
alembic upgrade head  # Re-apply
```

**Step 1.9: Document migration workflow**
```markdown
# docs/MIGRATIONS.md - NEW FILE

## Database Migrations with Alembic

### Creating a New Migration

```bash
# Auto-generate migration from model changes
alembic revision --autogenerate -m "description_of_change"

# Manual migration (more control)
alembic revision -m "description_of_change"
```

### Applying Migrations

```bash
# Apply all pending migrations
alembic upgrade head

# Apply specific version
alembic upgrade abc123

# Apply next N migrations
alembic upgrade +2
```

### Rolling Back Migrations

```bash
# Rollback 1 version
alembic downgrade -1

# Rollback to specific version
alembic downgrade abc123

# Rollback all
alembic downgrade base
```

### Production Deployment

1. Backup database before migration
2. Run migrations in maintenance window
3. Test rollback procedure
4. Have rollback plan ready
```

**Validation**:
- [ ] Alembic installed and configured
- [ ] Initial migration created and stamped
- [ ] Test migration applied successfully
- [ ] Rollback tested successfully
- [ ] Documentation created (MIGRATIONS.md)

**Effort**: 2 days

---

## Task 2: Increase Connection Pool Size - Day 3

### Background

**Current State**: Connection pool max_size = 20
**Problem**: Service outage when 20+ concurrent users
**Calculation**:
- 100 concurrent users × 2 connections avg = 200 connections needed
- Current pool: 20 connections = 10% capacity
- **Result**: Service crashes at 20% load

### Implementation Steps

**Step 2.1: Update app/database.py**
```python
# app/database.py - UPDATE CONNECTION POOL
from app.config import settings

async def init_db_pool():
    """Initialize database connection pool with production-grade settings."""
    global pool

    pool = await asyncpg.create_pool(
        dsn=settings.database_url,
        min_size=10,           # ✅ Minimum idle connections
        max_size=100,          # ✅ INCREASED from 20 to 100
        max_queries=50000,     # Max queries per connection before reset
        max_inactive_connection_lifetime=300,  # 5 minutes idle timeout
        command_timeout=60,    # 60 seconds query timeout
        server_settings={
            'application_name': 'backend_api'
        }
    )

    logger.info(f"Database connection pool initialized: min={pool.get_min_size()}, max={pool.get_max_size()}")

    return pool
```

**Step 2.2: Configure PostgreSQL max_connections**
```bash
# Check current PostgreSQL max_connections
PGPASSWORD=stocksblitz123 psql -U stocksblitz -d stocksblitz_unified -h localhost -c "SHOW max_connections;"

# Should be >= 200 (100 from backend + 100 buffer for other services)
# If not, update postgresql.conf:
# max_connections = 200

# Restart PostgreSQL
sudo systemctl restart postgresql
```

**Step 2.3: Add connection pool monitoring**
```python
# app/routes/health.py - UPDATE
from app.database import get_pool

@router.get("/health/pool")
async def health_check_pool():
    """
    Health check endpoint for database connection pool.

    Returns:
        Pool statistics (size, idle, in-use)
    """
    pool = await get_pool()

    return {
        "status": "healthy",
        "pool": {
            "size": pool.get_size(),
            "min_size": pool.get_min_size(),
            "max_size": pool.get_max_size(),
            "idle_connections": pool.get_idle_size(),
            "in_use_connections": pool.get_size() - pool.get_idle_size(),
            "utilization_percent": round((pool.get_size() / pool.get_max_size()) * 100, 2)
        }
    }
```

**Step 2.4: Load test connection pool**
```python
# tests/load/test_connection_pool.py - NEW FILE
import pytest
import asyncio
from app.database import get_pool

@pytest.mark.asyncio
async def test_pool_handles_100_concurrent_connections():
    """Test connection pool handles 100 concurrent requests."""
    pool = await get_pool()

    async def query():
        async with pool.acquire() as conn:
            return await conn.fetchval("SELECT 1")

    # 100 concurrent queries
    results = await asyncio.gather(*[query() for _ in range(100)])

    assert all(r == 1 for r in results)
    assert len(results) == 100

    # Check pool didn't overflow
    assert pool.get_size() <= pool.get_max_size()
```

**Validation**:
- [ ] Connection pool max_size increased to 100
- [ ] PostgreSQL max_connections >= 200
- [ ] Pool monitoring endpoint functional
- [ ] Load test passes (100 concurrent connections)

**Effort**: 1 day

---

## Task 3: Eliminate Global State Anti-Pattern - Days 4-7

### Background

**Current State**: 15+ global variables in `app/main.py`, `app/database.py`
**Problem**:
- Fragile initialization order
- Difficult to test (global state interferes with tests)
- Race conditions on startup

**Global Variables Found**:
```python
# app/database.py
pool = None  # ❌ Global

# app/main.py
redis_client = None  # ❌ Global
ticker_service_client = None  # ❌ Global
user_service_client = None  # ❌ Global
```

### Implementation Steps

**Step 3.1: Create dependency injection pattern**
```python
# app/dependencies.py - UPDATE
from fastapi import Depends
from typing import Annotated
import asyncpg
import redis.asyncio as redis
from app.config import settings
import httpx

# Database pool (initialized on startup)
_db_pool: asyncpg.Pool = None

async def get_db_pool() -> asyncpg.Pool:
    """
    Dependency for database connection pool.

    Returns:
        Database connection pool
    """
    global _db_pool
    if _db_pool is None:
        raise RuntimeError("Database pool not initialized. Call init_db_pool() on startup.")
    return _db_pool


async def init_db_pool():
    """Initialize database connection pool (called on startup)."""
    global _db_pool
    _db_pool = await asyncpg.create_pool(
        dsn=settings.database_url,
        min_size=10,
        max_size=100,
        command_timeout=60
    )
    return _db_pool


async def close_db_pool():
    """Close database connection pool (called on shutdown)."""
    global _db_pool
    if _db_pool:
        await _db_pool.close()
        _db_pool = None


# Redis client
_redis_client: redis.Redis = None

async def get_redis() -> redis.Redis:
    """
    Dependency for Redis client.

    Returns:
        Redis client
    """
    global _redis_client
    if _redis_client is None:
        raise RuntimeError("Redis not initialized. Call init_redis() on startup.")
    return _redis_client


async def init_redis():
    """Initialize Redis client (called on startup)."""
    global _redis_client
    _redis_client = redis.from_url(settings.redis_url, decode_responses=True)
    await _redis_client.ping()  # Test connection
    return _redis_client


async def close_redis():
    """Close Redis client (called on shutdown)."""
    global _redis_client
    if _redis_client:
        await _redis_client.close()
        _redis_client = None


# HTTP clients for external services
_http_client: httpx.AsyncClient = None

async def get_http_client() -> httpx.AsyncClient:
    """
    Dependency for HTTP client.

    Returns:
        Reusable HTTP client (connection pooling)
    """
    global _http_client
    if _http_client is None:
        raise RuntimeError("HTTP client not initialized. Call init_http_client() on startup.")
    return _http_client


async def init_http_client():
    """Initialize HTTP client (called on startup)."""
    global _http_client
    _http_client = httpx.AsyncClient(timeout=30.0)
    return _http_client


async def close_http_client():
    """Close HTTP client (called on shutdown)."""
    global _http_client
    if _http_client:
        await _http_client.aclose()
        _http_client = None


# Type aliases for dependency injection
DbPool = Annotated[asyncpg.Pool, Depends(get_db_pool)]
RedisClient = Annotated[redis.Redis, Depends(get_redis)]
HttpClient = Annotated[httpx.AsyncClient, Depends(get_http_client)]
```

**Step 3.2: Update app/main.py startup/shutdown**
```python
# app/main.py - UPDATE
from app.dependencies import (
    init_db_pool, close_db_pool,
    init_redis, close_redis,
    init_http_client, close_http_client
)

@app.on_event("startup")
async def startup():
    """Initialize all services on application startup."""
    logger.info("Starting backend application...")

    # Initialize in dependency order
    await init_db_pool()
    await init_redis()
    await init_http_client()

    # Start background workers
    asyncio.create_task(calculate_strategy_m2m_worker())

    logger.info("Backend application started successfully")


@app.on_event("shutdown")
async def shutdown():
    """Clean up resources on application shutdown."""
    logger.info("Shutting down backend application...")

    await close_http_client()
    await close_redis()
    await close_db_pool()

    logger.info("Backend application shut down successfully")
```

**Step 3.3: Update routes to use dependency injection**
```python
# app/routes/strategies.py - UPDATE
from app.dependencies import DbPool, RedisClient, HttpClient

@router.get("")
async def get_strategies(
    user_id: int,
    pool: DbPool,  # ✅ Injected dependency
    redis: RedisClient  # ✅ Injected dependency
):
    """Get all strategies for a user."""
    # Use pool instead of global variable
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM strategies WHERE user_id = $1", user_id)
        return {"strategies": [dict(row) for row in rows]}


@router.post("/{strategy_id}/orders")
async def place_order(
    strategy_id: int,
    order: OrderRequest,
    http_client: HttpClient  # ✅ Injected dependency
):
    """Place order via ticker service."""
    # Use http_client instead of global variable
    response = await http_client.post(
        f"{settings.ticker_service_url}/orders",
        json=order.dict()
    )
    return response.json()
```

**Step 3.4: Update tests to use dependency injection**
```python
# tests/conftest.py - UPDATE
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.dependencies import get_db_pool, init_db_pool, close_db_pool

@pytest.fixture(scope="session", autouse=True)
async def setup_database():
    """Initialize database pool for tests."""
    await init_db_pool()
    yield
    await close_db_pool()


@pytest.fixture
def client():
    """FastAPI test client."""
    return TestClient(app)


# Override dependencies for testing
@pytest.fixture
def override_db_pool(test_db_pool):
    """Override database pool with test pool."""
    app.dependency_overrides[get_db_pool] = lambda: test_db_pool
    yield
    app.dependency_overrides.clear()
```

**Validation**:
- [ ] All global variables eliminated
- [ ] Dependency injection pattern implemented
- [ ] Startup/shutdown lifecycle managed
- [ ] Routes use dependency injection
- [ ] Tests use dependency overrides

**Effort**: 4 days (includes refactoring all routes)

---

## Final Checklist

### Architecture Fixes
- [ ] **Task 1**: Alembic migration framework implemented
- [ ] **Task 2**: Connection pool increased to 100
- [ ] **Task 3**: Global state eliminated (dependency injection)

### Zero Regression Validation
- [ ] All existing API endpoints functional
- [ ] All existing tests pass
- [ ] No breaking changes

### Testing
- [ ] Migration rollback tested
- [ ] Connection pool load tested (100 concurrent)
- [ ] Dependency injection tested

### Documentation
- [ ] MIGRATIONS.md created
- [ ] Dependency injection documented
- [ ] Deployment guide updated

---

## Success Metrics

**Before (Phase 1 Architecture Review)**:
- Architecture Grade: B+ (82/100)
- Migration framework: Missing
- Connection pool: 20 (crashes at 20% load)
- Global state: 15+ variables

**After (Target)**:
- Architecture Grade: A (90/100)
- Migration framework: Alembic (zero-downtime deployments)
- Connection pool: 100 (scales to 100 concurrent users)
- Global state: 0 (dependency injection)

---

## Next Steps

1. **Week 5+**: Implement code quality improvements (Prompt 05)
2. **Ongoing**: Monitor connection pool utilization
3. **Ongoing**: Create migrations for all schema changes

---

**Estimated Effort**: 5-7 days (1 engineer)
**Priority**: P1 - HIGH
**Impact**: CRITICAL - Enables production scalability

---

**Last Updated**: 2025-11-09
**Owner**: Backend Team
**Next Review**: After implementation complete
