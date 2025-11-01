"""
Pytest configuration and shared fixtures
"""
import asyncio
import os
from typing import AsyncGenerator, Generator
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient

# Set test environment before importing app
os.environ["ENVIRONMENT"] = "test"
os.environ["API_KEY_ENABLED"] = "false"  # Disable auth for most tests
os.environ["ENABLE_MOCK_DATA"] = "true"
os.environ["REDIS_URL"] = "redis://localhost:6379/15"  # Use test database


@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def test_api_key() -> str:
    """Test API key for authenticated endpoints"""
    return "test-api-key-12345"


@pytest.fixture
def mock_settings():
    """Mock settings for testing"""
    from app.config import Settings

    return Settings(
        environment="test",
        redis_url="redis://localhost:6379/15",
        api_key_enabled=False,
        enable_mock_data=True,
        instrument_db_host="localhost",
        instrument_db_port=5432,
        instrument_db_name="stocksblitz_test",
        instrument_db_user="test",
        instrument_db_password="test"
    )


@pytest.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client for testing"""
    from app.main import app

    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client


@pytest.fixture
def client() -> TestClient:
    """Synchronous test client"""
    from app.main import app

    return TestClient(app)


@pytest.fixture
def mock_kite_client():
    """Mock KiteConnect client"""
    mock = MagicMock()
    mock.quote.return_value = {
        "NSE:NIFTY 50": {
            "last_price": 19500.0,
            "volume": 1000000,
            "oi": 5000
        }
    }
    mock.historical_data.return_value = [
        {
            "date": "2025-01-01",
            "open": 19500,
            "high": 19600,
            "low": 19400,
            "close": 19550,
            "volume": 100000
        }
    ]
    return mock


@pytest.fixture
async def mock_redis():
    """Mock Redis client for testing"""
    from unittest.mock import AsyncMock

    mock = AsyncMock()
    mock.publish.return_value = 1
    mock.ping.return_value = True
    return mock


@pytest.fixture
def sample_order_task():
    """Sample order task for testing"""
    from app.order_executor import OrderTask, TaskStatus

    return OrderTask(
        task_id="test-task-123",
        idempotency_key="test-idempotency-key",
        operation="place_order",
        params={
            "exchange": "NFO",
            "tradingsymbol": "NIFTY25NOVFUT",
            "transaction_type": "BUY",
            "quantity": 50,
            "product": "NRML",
            "order_type": "MARKET"
        },
        status=TaskStatus.PENDING,
        account_id="primary"
    )


@pytest.fixture
def sample_batch_orders():
    """Sample batch orders for testing"""
    from app.batch_orders import BatchOrderRequest

    return [
        BatchOrderRequest(
            exchange="NFO",
            tradingsymbol="NIFTY25NOVFUT",
            transaction_type="BUY",
            quantity=50,
            product="NRML",
            order_type="MARKET"
        ),
        BatchOrderRequest(
            exchange="NFO",
            tradingsymbol="BANKNIFTY25NOVFUT",
            transaction_type="BUY",
            quantity=25,
            product="NRML",
            order_type="MARKET"
        )
    ]
