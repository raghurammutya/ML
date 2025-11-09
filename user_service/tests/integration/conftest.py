"""
Pytest configuration for integration tests.

Provides shared fixtures and configuration for all integration tests.
"""

import pytest
import httpx
import os
from typing import Generator


def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "integration: mark test as integration test requiring live services"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow running"
    )


@pytest.fixture(scope="session")
def base_url() -> str:
    """Get base URL from environment or use default."""
    return os.getenv("USER_SERVICE_URL", "http://localhost:8011")


@pytest.fixture(scope="session")
def api_v1_url(base_url: str) -> str:
    """Get API v1 base URL."""
    return f"{base_url}/v1"


@pytest.fixture(scope="session")
def http_client() -> Generator[httpx.Client, None, None]:
    """
    Create a persistent HTTP client for all tests.

    Using a session-scoped client with connection pooling
    improves test performance.
    """
    client = httpx.Client(timeout=10.0)
    yield client
    client.close()


@pytest.fixture(scope="session")
def check_service_available(base_url: str) -> bool:
    """
    Check if user_service is available before running tests.

    Fails early if service is not reachable.
    """
    try:
        response = httpx.get(f"{base_url}/health", timeout=5.0)
        if response.status_code != 200:
            pytest.fail(
                f"user_service health check failed with status {response.status_code}. "
                f"Is the service running on {base_url}?"
            )
        return True
    except httpx.ConnectError:
        pytest.fail(
            f"Cannot connect to user_service at {base_url}. "
            f"Please start the service before running integration tests."
        )
    except Exception as e:
        pytest.fail(f"Health check failed: {str(e)}")


@pytest.fixture(autouse=True)
def ensure_service_running(check_service_available):
    """
    Auto-use fixture that ensures service is running for every test.

    This will be called before each test automatically.
    """
    pass
