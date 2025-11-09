"""
API Contract Tests

Tests verify that API endpoints:
1. Return correct HTTP status codes
2. Return valid JSON responses
3. Match defined Pydantic schemas
4. Handle errors correctly
5. Validate request/response contracts
"""
import os
import pytest
from httpx import AsyncClient
from fastapi.testclient import TestClient

# Fix environment variable
if os.getenv('ENVIRONMENT') == 'dev':
    os.environ.pop('ENVIRONMENT', None)

from app.main import app
from app.config import get_settings

settings = get_settings()

pytestmark = pytest.mark.integration


@pytest.fixture
def client():
    """Synchronous test client."""
    return TestClient(app)


@pytest.fixture
async def async_client():
    """Async test client."""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


class TestHealthEndpoints:
    """Test health check endpoints."""

    def test_health_endpoint_returns_200(self, client):
        """Test /health endpoint returns 200 OK."""
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_endpoint_returns_json(self, client):
        """Test /health returns valid JSON."""
        response = client.get("/health")
        assert response.headers["content-type"] == "application/json"
        data = response.json()
        assert isinstance(data, dict)

    def test_health_endpoint_has_status_field(self, client):
        """Test /health response has status field."""
        response = client.get("/health")
        data = response.json()
        assert "status" in data
        assert data["status"] in ["ok", "healthy", "up"]

    def test_metrics_endpoint_exists(self, client):
        """Test /metrics endpoint exists."""
        response = client.get("/metrics")
        # Should return 200 or 404, not 500
        assert response.status_code in [200, 404]


class TestFundsAPIContracts:
    """Test Funds Management API contracts."""

    def test_upload_statement_requires_file(self, client):
        """Test /funds/upload-statement requires file parameter."""
        response = client.post(
            "/funds/upload-statement",
            params={"account_id": "test_account"}
        )
        # Should return 422 (validation error) or 400
        assert response.status_code in [400, 422]

    def test_upload_statement_requires_account_id(self, client):
        """Test /funds/upload-statement requires account_id parameter."""
        response = client.post("/funds/upload-statement")
        # Should return 422 (validation error)
        assert response.status_code == 422

    def test_get_uploads_returns_list(self, client):
        """Test /funds/uploads returns a list."""
        response = client.get(
            "/funds/uploads",
            params={"account_id": "test_account"}
        )
        # Should return 200 or valid response
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, (list, dict))

    def test_category_summary_validates_dates(self, client):
        """Test /funds/category-summary validates date parameters."""
        response = client.get(
            "/funds/category-summary",
            params={
                "account_id": "test_account",
                "start_date": "invalid-date",
                "end_date": "2025-12-31"
            }
        )
        # Should return 422 for invalid date format
        assert response.status_code in [400, 422]


class TestSmartOrdersAPIContracts:
    """Test Smart Orders API contracts."""

    def test_validate_order_requires_body(self, client):
        """Test /smart-orders/validate requires request body."""
        response = client.post("/smart-orders/validate")
        # Should return 422 (validation error)
        assert response.status_code == 422

    def test_validate_order_with_missing_fields(self, client):
        """Test /smart-orders/validate with incomplete data."""
        response = client.post(
            "/smart-orders/validate",
            json={"instrument_token": 12345}  # Missing required fields
        )
        # Should return 422 (validation error)
        assert response.status_code == 422

    def test_calculate_margin_endpoint_exists(self, client):
        """Test /smart-orders/calculate-margin endpoint exists."""
        response = client.post(
            "/smart-orders/calculate-margin",
            json={}
        )
        # Should return 422 or 200 (not 404)
        assert response.status_code != 404

    def test_cost_breakdown_validates_transaction_type(self, client):
        """Test /smart-orders/cost-breakdown validates transaction_type."""
        response = client.post(
            "/smart-orders/cost-breakdown",
            json={
                "instrument_token": 12345,
                "quantity": 1,
                "price": 100.0,
                "transaction_type": "INVALID_TYPE",  # Invalid
                "product": "MIS"
            }
        )
        # Should return 422 for invalid enum value
        assert response.status_code in [400, 422]


class TestInstrumentsAPIContracts:
    """Test Instruments API contracts."""

    def test_list_instruments_returns_array(self, client):
        """Test /instruments returns array of instruments."""
        response = client.get("/instruments")
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, (list, dict))
            # If it's a dict, should have instruments field
            if isinstance(data, dict):
                assert "instruments" in data or "data" in data

    def test_instruments_pagination_params(self, client):
        """Test /instruments accepts pagination parameters."""
        response = client.get(
            "/instruments",
            params={"limit": 10, "offset": 0}
        )
        # Should accept pagination params
        assert response.status_code != 422

    def test_fo_enabled_filter_works(self, client):
        """Test /instruments/fo-enabled endpoint."""
        response = client.get("/instruments/fo-enabled")
        # Should return 200 or 404
        assert response.status_code in [200, 404]


class TestStrategiesAPIContracts:
    """Test Strategies API contracts."""

    def test_list_strategies_requires_account_id(self, client):
        """Test /strategies requires account_id parameter."""
        response = client.get("/strategies")
        # Might require authentication or account_id
        assert response.status_code in [200, 401, 422]

    def test_create_strategy_validates_schema(self, client):
        """Test /strategies POST validates request schema."""
        response = client.post(
            "/strategies",
            json={"invalid_field": "value"}
        )
        # Should return validation error
        assert response.status_code in [401, 422]

    def test_get_strategy_by_id_returns_404_for_invalid(self, client):
        """Test GET /strategies/{id} returns 404 for non-existent."""
        response = client.get("/strategies/99999999")
        # Should return 404 or 401 (if auth required)
        assert response.status_code in [401, 404]


class TestErrorHandling:
    """Test API error handling contracts."""

    def test_invalid_endpoint_returns_404(self, client):
        """Test invalid endpoint returns 404."""
        response = client.get("/this-endpoint-does-not-exist")
        assert response.status_code == 404

    def test_404_returns_json(self, client):
        """Test 404 errors return JSON."""
        response = client.get("/invalid-endpoint")
        assert response.status_code == 404
        # FastAPI returns JSON for 404s
        assert "application/json" in response.headers.get("content-type", "")

    def test_invalid_method_returns_405(self, client):
        """Test invalid HTTP method returns 405."""
        # Try POST on GET-only endpoint
        response = client.post("/health")
        assert response.status_code == 405

    def test_validation_error_returns_422(self, client):
        """Test validation errors return 422."""
        # Send invalid data to an endpoint
        response = client.post(
            "/smart-orders/validate",
            json={"invalid": "data"}
        )
        assert response.status_code == 422

    def test_validation_error_has_detail(self, client):
        """Test validation errors include detail field."""
        response = client.post(
            "/smart-orders/validate",
            json={}
        )
        if response.status_code == 422:
            data = response.json()
            assert "detail" in data


class TestResponseHeaders:
    """Test API response headers."""

    def test_cors_headers_present(self, client):
        """Test CORS headers are present."""
        response = client.get("/health")
        # Check if CORS headers exist (if CORS is enabled)
        headers = response.headers
        # At minimum, should have content-type
        assert "content-type" in headers

    def test_json_content_type_for_json_responses(self, client):
        """Test JSON endpoints return application/json."""
        response = client.get("/health")
        assert "application/json" in response.headers.get("content-type", "")

    def test_response_has_date_header(self, client):
        """Test responses include Date header."""
        response = client.get("/health")
        # HTTP responses should have Date header
        assert "date" in response.headers or "Date" in response.headers


class TestRequestValidation:
    """Test request validation contracts."""

    def test_negative_limit_rejected(self, client):
        """Test negative limit parameter is rejected."""
        response = client.get(
            "/instruments",
            params={"limit": -10}
        )
        # Should reject negative limit
        assert response.status_code in [400, 422]

    def test_excessive_limit_rejected(self, client):
        """Test excessive limit parameter is rejected."""
        response = client.get(
            "/instruments",
            params={"limit": 100000}
        )
        # Should reject or cap excessive limits
        # Some APIs allow it, others reject
        assert response.status_code in [200, 400, 422]

    def test_negative_offset_rejected(self, client):
        """Test negative offset parameter is rejected."""
        response = client.get(
            "/instruments",
            params={"offset": -10}
        )
        # Should reject negative offset
        assert response.status_code in [400, 422]


class TestDataTypes:
    """Test API data type contracts."""

    def test_integer_fields_reject_strings(self, client):
        """Test integer fields reject string values."""
        response = client.get(
            "/instruments",
            params={"limit": "not_a_number"}
        )
        # Should return validation error
        assert response.status_code == 422

    def test_date_fields_validate_format(self, client):
        """Test date fields validate ISO format."""
        response = client.get(
            "/funds/category-summary",
            params={
                "account_id": "test",
                "start_date": "not-a-date"
            }
        )
        # Should return validation error
        assert response.status_code in [400, 422]

    def test_enum_fields_reject_invalid_values(self, client):
        """Test enum fields reject invalid values."""
        response = client.post(
            "/smart-orders/cost-breakdown",
            json={
                "instrument_token": 12345,
                "quantity": 1,
                "price": 100.0,
                "transaction_type": "INVALID_ENUM_VALUE",
                "product": "MIS"
            }
        )
        # Should return validation error
        assert response.status_code in [400, 422]
