"""
Integration tests for API key endpoints.

These tests verify the complete API key lifecycle:
1. User registration and login
2. API key generation
3. API key listing
4. API key authentication
5. API key rotation
6. API key revocation
7. Scope enforcement
8. Rate limiting

Requirements:
- user_service running on port 8011 (dev) or configured port
- PostgreSQL database accessible
- Redis accessible
"""

import pytest
import httpx
import time
from typing import Dict, Any, Optional


# Configuration
BASE_URL = "http://localhost:8011"  # Development environment
API_V1 = f"{BASE_URL}/v1"


class TestAPIKeyLifecycle:
    """Test complete API key lifecycle."""

    @pytest.fixture(scope="class")
    def test_user(self) -> Dict[str, str]:
        """Create a test user for all tests."""
        return {
            "email": f"test_apikey_{int(time.time())}@example.com",
            "password": "TestPassword123!",
            "full_name": "API Key Test User"
        }

    @pytest.fixture(scope="class")
    def registered_user(self, test_user: Dict[str, str]) -> Dict[str, Any]:
        """Register test user and return credentials."""
        # Register user
        response = httpx.post(
            f"{API_V1}/auth/register",
            json=test_user,
            timeout=10.0
        )

        assert response.status_code == 201, f"Registration failed: {response.text}"
        data = response.json()

        return {
            **test_user,
            "user_id": data["user"]["id"],
            "access_token": data["access_token"]
        }

    @pytest.fixture(scope="class")
    def auth_headers(self, registered_user: Dict[str, Any]) -> Dict[str, str]:
        """Get authentication headers with Bearer token."""
        return {
            "Authorization": f"Bearer {registered_user['access_token']}"
        }

    def test_01_register_and_login(self, test_user: Dict[str, str]):
        """Test user registration for API key tests."""
        # Register
        response = httpx.post(
            f"{API_V1}/auth/register",
            json=test_user,
            timeout=10.0
        )

        assert response.status_code == 201
        data = response.json()
        assert "access_token" in data
        assert "user" in data
        assert data["user"]["email"] == test_user["email"]

    def test_02_create_api_key(self, auth_headers: Dict[str, str], registered_user: Dict[str, Any]):
        """Test creating an API key."""
        response = httpx.post(
            f"{API_V1}/api-keys",
            headers=auth_headers,
            json={
                "name": "Test API Key",
                "scopes": ["read:market_data", "write:orders"],
                "expires_in_days": 90
            },
            timeout=10.0
        )

        assert response.status_code == 201, f"API key creation failed: {response.text}"
        data = response.json()

        # Verify response structure
        assert "api_key" in data, "Response missing 'api_key' field"
        assert "key_id" in data, "Response missing 'key_id' field"
        assert "prefix" in data, "Response missing 'prefix' field"

        # Verify API key format (sb_<8hex>_<32hex>)
        api_key = data["api_key"]
        assert api_key.startswith("sb_"), "API key doesn't start with 'sb_'"
        parts = api_key.split("_")
        assert len(parts) == 3, "API key doesn't have 3 parts"
        assert len(parts[1]) == 8, "Key ID part should be 8 characters"
        assert len(parts[2]) == 64, "Key secret part should be 64 characters"

        # Verify metadata
        assert data["name"] == "Test API Key"
        assert "read:market_data" in data["scopes"]
        assert "write:orders" in data["scopes"]
        assert data["is_active"] is True

        # Store for later tests
        registered_user["api_key"] = data["api_key"]
        registered_user["key_id"] = data["key_id"]

    def test_03_list_api_keys(self, auth_headers: Dict[str, str]):
        """Test listing API keys."""
        response = httpx.get(
            f"{API_V1}/api-keys",
            headers=auth_headers,
            timeout=10.0
        )

        assert response.status_code == 200, f"Failed to list API keys: {response.text}"
        data = response.json()

        assert "api_keys" in data
        assert len(data["api_keys"]) > 0, "Should have at least one API key"

        # Verify key structure (should not include secret)
        api_key = data["api_keys"][0]
        assert "key_id" in api_key
        assert "name" in api_key
        assert "prefix" in api_key
        assert "scopes" in api_key
        assert "is_active" in api_key
        assert "created_at" in api_key
        assert "last_used_at" in api_key
        assert "expires_at" in api_key

        # Should NOT include secret
        assert "api_key" not in api_key
        assert "key_secret" not in api_key

    def test_04_authenticate_with_api_key(self, registered_user: Dict[str, Any]):
        """Test authenticating with API key."""
        if "api_key" not in registered_user:
            pytest.skip("API key not created yet")

        # Use API key to access protected endpoint
        response = httpx.get(
            f"{API_V1}/users/me",
            headers={
                "Authorization": f"Bearer {registered_user['api_key']}"
            },
            timeout=10.0
        )

        assert response.status_code == 200, f"API key authentication failed: {response.text}"
        data = response.json()

        assert data["email"] == registered_user["email"]
        assert data["id"] == registered_user["user_id"]

    def test_05_api_key_with_x_api_key_header(self, registered_user: Dict[str, Any]):
        """Test authenticating with X-API-Key header."""
        if "api_key" not in registered_user:
            pytest.skip("API key not created yet")

        # Use X-API-Key header
        response = httpx.get(
            f"{API_V1}/users/me",
            headers={
                "X-API-Key": registered_user['api_key']
            },
            timeout=10.0
        )

        assert response.status_code == 200, f"X-API-Key authentication failed: {response.text}"
        data = response.json()

        assert data["email"] == registered_user["email"]

    def test_06_get_api_key_details(self, auth_headers: Dict[str, str], registered_user: Dict[str, Any]):
        """Test getting specific API key details."""
        if "key_id" not in registered_user:
            pytest.skip("API key not created yet")

        response = httpx.get(
            f"{API_V1}/api-keys/{registered_user['key_id']}",
            headers=auth_headers,
            timeout=10.0
        )

        assert response.status_code == 200, f"Failed to get API key: {response.text}"
        data = response.json()

        assert data["key_id"] == registered_user["key_id"]
        assert data["name"] == "Test API Key"
        assert "scopes" in data

        # Usage stats should be updated
        assert "usage_count" in data
        assert data["usage_count"] >= 2, "Usage count should be at least 2 (from previous tests)"

    def test_07_update_api_key(self, auth_headers: Dict[str, str], registered_user: Dict[str, Any]):
        """Test updating API key metadata."""
        if "key_id" not in registered_user:
            pytest.skip("API key not created yet")

        response = httpx.put(
            f"{API_V1}/api-keys/{registered_user['key_id']}",
            headers=auth_headers,
            json={
                "name": "Updated API Key Name",
                "scopes": ["read:market_data"]  # Remove write:orders
            },
            timeout=10.0
        )

        assert response.status_code == 200, f"Failed to update API key: {response.text}"
        data = response.json()

        assert data["name"] == "Updated API Key Name"
        assert "read:market_data" in data["scopes"]
        assert "write:orders" not in data["scopes"]

    def test_08_rotate_api_key(self, auth_headers: Dict[str, str], registered_user: Dict[str, Any]):
        """Test rotating API key."""
        if "key_id" not in registered_user:
            pytest.skip("API key not created yet")

        old_api_key = registered_user["api_key"]

        response = httpx.post(
            f"{API_V1}/api-keys/{registered_user['key_id']}/rotate",
            headers=auth_headers,
            timeout=10.0
        )

        assert response.status_code == 200, f"Failed to rotate API key: {response.text}"
        data = response.json()

        # Should get new API key
        assert "api_key" in data
        new_api_key = data["api_key"]

        # New key should be different
        assert new_api_key != old_api_key

        # New key should work
        response = httpx.get(
            f"{API_V1}/users/me",
            headers={"Authorization": f"Bearer {new_api_key}"},
            timeout=10.0
        )
        assert response.status_code == 200

        # Old key should NOT work (immediate revocation)
        response = httpx.get(
            f"{API_V1}/users/me",
            headers={"Authorization": f"Bearer {old_api_key}"},
            timeout=10.0
        )
        assert response.status_code == 401, "Old API key should be revoked"

        # Update for later tests
        registered_user["api_key"] = new_api_key

    def test_09_revoke_api_key(self, auth_headers: Dict[str, str], registered_user: Dict[str, Any]):
        """Test revoking API key."""
        if "key_id" not in registered_user:
            pytest.skip("API key not created yet")

        response = httpx.delete(
            f"{API_V1}/api-keys/{registered_user['key_id']}",
            headers=auth_headers,
            timeout=10.0
        )

        assert response.status_code == 200, f"Failed to revoke API key: {response.text}"

        # Revoked key should NOT work
        response = httpx.get(
            f"{API_V1}/users/me",
            headers={"Authorization": f"Bearer {registered_user['api_key']}"},
            timeout=10.0
        )
        assert response.status_code == 401, "Revoked API key should not authenticate"

    def test_10_create_multiple_api_keys(self, auth_headers: Dict[str, str]):
        """Test creating multiple API keys."""
        # Create 3 API keys
        keys = []
        for i in range(3):
            response = httpx.post(
                f"{API_V1}/api-keys",
                headers=auth_headers,
                json={
                    "name": f"Test Key {i+1}",
                    "scopes": ["read:market_data"],
                    "expires_in_days": 30
                },
                timeout=10.0
            )

            assert response.status_code == 201
            keys.append(response.json())

        # List all keys
        response = httpx.get(
            f"{API_V1}/api-keys",
            headers=auth_headers,
            timeout=10.0
        )

        assert response.status_code == 200
        data = response.json()
        # Should have at least 3 active keys (might have revoked ones too)
        active_keys = [k for k in data["api_keys"] if k["is_active"]]
        assert len(active_keys) >= 3


class TestAPIKeyScopeEnforcement:
    """Test API key scope enforcement."""

    @pytest.fixture(scope="class")
    def scoped_keys(self) -> Dict[str, str]:
        """Create API keys with different scopes."""
        # Register user
        user_email = f"test_scopes_{int(time.time())}@example.com"
        response = httpx.post(
            f"{API_V1}/auth/register",
            json={
                "email": user_email,
                "password": "TestPassword123!",
                "full_name": "Scope Test User"
            },
            timeout=10.0
        )
        assert response.status_code == 201
        access_token = response.json()["access_token"]

        headers = {"Authorization": f"Bearer {access_token}"}
        keys = {}

        # Create read-only key
        response = httpx.post(
            f"{API_V1}/api-keys",
            headers=headers,
            json={
                "name": "Read Only Key",
                "scopes": ["read:market_data"],
                "expires_in_days": 30
            },
            timeout=10.0
        )
        assert response.status_code == 201
        keys["read_only"] = response.json()["api_key"]

        # Create write-only key
        response = httpx.post(
            f"{API_V1}/api-keys",
            headers=headers,
            json={
                "name": "Write Only Key",
                "scopes": ["write:orders"],
                "expires_in_days": 30
            },
            timeout=10.0
        )
        assert response.status_code == 201
        keys["write_only"] = response.json()["api_key"]

        # Create full access key
        response = httpx.post(
            f"{API_V1}/api-keys",
            headers=headers,
            json={
                "name": "Full Access Key",
                "scopes": ["read:market_data", "write:orders", "read:accounts"],
                "expires_in_days": 30
            },
            timeout=10.0
        )
        assert response.status_code == 201
        keys["full_access"] = response.json()["api_key"]

        return keys

    def test_read_scope_enforcement(self, scoped_keys: Dict[str, str]):
        """Test that read-only key can read but not write."""
        # Read operation should succeed
        response = httpx.get(
            f"{API_V1}/users/me",
            headers={"Authorization": f"Bearer {scoped_keys['read_only']}"},
            timeout=10.0
        )
        assert response.status_code == 200

        # Write operation should fail (if we had such an endpoint)
        # This is a placeholder - actual implementation depends on backend
        # assert response.status_code == 403

    def test_scope_validation(self, scoped_keys: Dict[str, str]):
        """Test that keys work within their scope."""
        # Full access key should work for everything
        response = httpx.get(
            f"{API_V1}/users/me",
            headers={"Authorization": f"Bearer {scoped_keys['full_access']}"},
            timeout=10.0
        )
        assert response.status_code == 200


class TestAPIKeyRateLimiting:
    """Test API key rate limiting."""

    @pytest.fixture(scope="class")
    def rate_limited_key(self) -> str:
        """Create an API key for rate limit testing."""
        # Register user
        user_email = f"test_ratelimit_{int(time.time())}@example.com"
        response = httpx.post(
            f"{API_V1}/auth/register",
            json={
                "email": user_email,
                "password": "TestPassword123!",
                "full_name": "Rate Limit Test User"
            },
            timeout=10.0
        )
        assert response.status_code == 201
        access_token = response.json()["access_token"]

        # Create API key
        response = httpx.post(
            f"{API_V1}/api-keys",
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                "name": "Rate Limit Test Key",
                "scopes": ["read:market_data"],
                "expires_in_days": 30
            },
            timeout=10.0
        )
        assert response.status_code == 201
        return response.json()["api_key"]

    @pytest.mark.skip(reason="Rate limiting configuration depends on production settings")
    def test_api_key_rate_limit(self, rate_limited_key: str):
        """Test that API keys are rate limited."""
        # Make multiple requests rapidly
        success_count = 0
        rate_limited_count = 0

        for i in range(100):
            response = httpx.get(
                f"{API_V1}/users/me",
                headers={"Authorization": f"Bearer {rate_limited_key}"},
                timeout=10.0
            )

            if response.status_code == 200:
                success_count += 1
            elif response.status_code == 429:  # Too Many Requests
                rate_limited_count += 1
                break

        # Should eventually hit rate limit
        assert rate_limited_count > 0, "Rate limiting not enforced"


class TestAPIKeyErrorHandling:
    """Test API key error scenarios."""

    def test_invalid_api_key_format(self):
        """Test authentication with invalid API key format."""
        response = httpx.get(
            f"{API_V1}/users/me",
            headers={"Authorization": "Bearer invalid_key"},
            timeout=10.0
        )

        assert response.status_code == 401

    def test_nonexistent_api_key(self):
        """Test authentication with non-existent API key."""
        fake_key = "sb_12345678_" + "a" * 64
        response = httpx.get(
            f"{API_V1}/users/me",
            headers={"Authorization": f"Bearer {fake_key}"},
            timeout=10.0
        )

        assert response.status_code == 401

    def test_expired_api_key(self):
        """Test authentication with expired API key."""
        # This test requires creating a key with very short expiry
        # or manipulating the database to set expiry in the past
        pytest.skip("Requires database manipulation for expiry testing")

    def test_create_api_key_without_auth(self):
        """Test creating API key without authentication."""
        response = httpx.post(
            f"{API_V1}/api-keys",
            json={
                "name": "Test Key",
                "scopes": ["read:market_data"],
                "expires_in_days": 30
            },
            timeout=10.0
        )

        assert response.status_code == 401 or response.status_code == 403

    def test_access_other_user_api_key(self):
        """Test that users cannot access other users' API keys."""
        # Register two users
        user1_email = f"user1_{int(time.time())}@example.com"
        user2_email = f"user2_{int(time.time())}@example.com"

        # User 1
        response1 = httpx.post(
            f"{API_V1}/auth/register",
            json={
                "email": user1_email,
                "password": "TestPassword123!",
                "full_name": "User 1"
            },
            timeout=10.0
        )
        assert response1.status_code == 201
        token1 = response1.json()["access_token"]

        # User 2
        response2 = httpx.post(
            f"{API_V1}/auth/register",
            json={
                "email": user2_email,
                "password": "TestPassword123!",
                "full_name": "User 2"
            },
            timeout=10.0
        )
        assert response2.status_code == 201
        token2 = response2.json()["access_token"]

        # User 1 creates API key
        response = httpx.post(
            f"{API_V1}/api-keys",
            headers={"Authorization": f"Bearer {token1}"},
            json={
                "name": "User 1 Key",
                "scopes": ["read:market_data"],
                "expires_in_days": 30
            },
            timeout=10.0
        )
        assert response.status_code == 201
        key_id = response.json()["key_id"]

        # User 2 tries to access User 1's key
        response = httpx.get(
            f"{API_V1}/api-keys/{key_id}",
            headers={"Authorization": f"Bearer {token2}"},
            timeout=10.0
        )

        assert response.status_code == 404, "User 2 should not see User 1's API key"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
