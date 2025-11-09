"""
Shared pytest fixtures for all tests.
"""

import os
import pytest
from fastapi.testclient import TestClient


# Set test environment variables before importing app
@pytest.fixture(scope="session", autouse=True)
def setup_test_env():
    """Setup test environment variables."""
    os.environ["ENVIRONMENT"] = "development"
    os.environ["DATABASE_URL"] = "postgresql://test:test@localhost:5432/test"
    os.environ["REDIS_URL"] = "redis://localhost:6379/0"


@pytest.fixture
def client():
    """FastAPI test client fixture."""
    from app.main import app
    return TestClient(app)
