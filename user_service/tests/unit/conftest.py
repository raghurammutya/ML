"""
Pytest configuration for unit tests.
"""

import pytest
import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from app.core.database import Base
from app.models.user import User, UserStatus


# Use PostgreSQL test database to match production
# Use the same database as dev but with a test schema
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://stocksblitz:stocksblitz123@localhost:8003/stocksblitz_unified_dev"
)


@pytest.fixture(scope="session")
def db_engine():
    """Create database engine once per test session."""
    engine = create_engine(TEST_DATABASE_URL, echo=False)

    # Ensure schema exists
    with engine.connect() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS user_service"))
        conn.commit()

    # Create all tables if they don't exist (they should exist from migrations)
    Base.metadata.create_all(engine, checkfirst=True)

    yield engine

    # Don't drop tables - they're shared with the dev database
    engine.dispose()


@pytest.fixture(scope="function")
def db_session(db_engine):
    """
    Create a fresh database session for each test.

    Each test runs in a transaction that is rolled back after completion,
    ensuring test isolation without recreating tables.
    """
    # Create a connection and begin a transaction
    connection = db_engine.connect()
    transaction = connection.begin()

    # Create session bound to this transaction
    session = Session(bind=connection)

    yield session

    # Rollback transaction to undo all changes
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def test_users(db_session: Session):
    """Create test users for organization tests."""
    users = []

    for i in range(5):
        user = User(
            email=f"user{i}@example.com",
            email_verified=True,
            password_hash="test_hash",
            name=f"Test User {i}",
            status=UserStatus.ACTIVE,
            timezone="UTC",
            locale="en-US"
        )
        db_session.add(user)
        users.append(user)

    db_session.commit()

    # Refresh to get IDs
    for user in users:
        db_session.refresh(user)

    return users
