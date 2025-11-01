"""
Integration tests for API endpoints
"""
import pytest


@pytest.mark.integration
def test_health_endpoint(client):
    """Test /health endpoint"""
    response = client.get("/health")

    assert response.status_code == 200
    data = response.json()

    assert "status" in data
    assert "ticker" in data
    assert "dependencies" in data


@pytest.mark.integration
def test_metrics_endpoint(client):
    """Test /metrics endpoint (Prometheus format)"""
    response = client.get("/metrics")

    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]


@pytest.mark.integration
def test_subscriptions_list(client):
    """Test GET /subscriptions"""
    response = client.get("/subscriptions")

    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.integration
def test_subscriptions_pagination(client):
    """Test subscriptions pagination"""
    # Test with limit and offset
    response = client.get("/subscriptions?limit=10&offset=0")

    assert response.status_code == 200
    data = response.json()
    assert len(data) <= 10


@pytest.mark.integration
def test_invalid_pagination_params(client):
    """Test invalid pagination parameters"""
    # Negative offset
    response = client.get("/subscriptions?offset=-1")
    assert response.status_code == 400

    # Invalid limit
    response = client.get("/subscriptions?limit=9999")
    assert response.status_code == 400


@pytest.mark.integration
@pytest.mark.skip(reason="Requires mock data configuration")
def test_mock_data_status(client):
    """Test GET /advanced/mock-data/status"""
    response = client.get("/advanced/mock-data/status")

    assert response.status_code == 200
    data = response.json()

    assert "mock_data_enabled" in data
    assert "market_hours" in data
    assert "mock_config" in data
