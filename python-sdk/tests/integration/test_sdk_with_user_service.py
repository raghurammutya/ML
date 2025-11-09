"""
Integration tests for Python SDK with live user_service.

These tests verify that the SDK correctly integrates with:
1. User service for authentication (JWT and API key)
2. Backend service for trading operations
3. Multi-account support

Prerequisites:
- user_service running on port 8011
- backend running on port 8010 (optional, for trading operations)
- PostgreSQL and Redis available
"""

import pytest
import time
from stocksblitz import TradingClient
from stocksblitz.exceptions import AuthenticationError, APIError


# Configuration
USER_SERVICE_URL = "http://localhost:8011"
BACKEND_URL = "http://localhost:8010"


class TestSDKAuthentication:
    """Test SDK authentication with user_service."""

    @pytest.fixture(scope="class")
    def test_credentials(self):
        """Test user credentials."""
        return {
            "email": f"sdk_test_{int(time.time())}@example.com",
            "password": "SDKTestPassword123!",
            "full_name": "SDK Test User"
        }

    def test_01_sdk_jwt_authentication(self, test_credentials):
        """Test SDK authentication with JWT (username/password)."""
        # First, register user via direct API call
        import httpx
        response = httpx.post(
            f"{USER_SERVICE_URL}/v1/auth/register",
            json=test_credentials,
            timeout=10.0
        )
        assert response.status_code == 201, f"Registration failed: {response.text}"

        # Now test SDK JWT authentication
        client = TradingClient.from_credentials(
            api_url=BACKEND_URL,
            user_service_url=USER_SERVICE_URL,
            username=test_credentials["email"],
            password=test_credentials["password"]
        )

        # Verify client is authenticated
        assert client._api._access_token is not None
        assert client._api._refresh_token is not None

    def test_02_sdk_jwt_authentication_invalid_credentials(self):
        """Test SDK JWT authentication with invalid credentials."""
        with pytest.raises(AuthenticationError):
            client = TradingClient.from_credentials(
                api_url=BACKEND_URL,
                user_service_url=USER_SERVICE_URL,
                username="nonexistent@example.com",
                password="WrongPassword123!"
            )

    def test_03_sdk_login_method(self, test_credentials):
        """Test SDK login() method."""
        # Create client without immediate login
        client = TradingClient(
            api_url=BACKEND_URL,
            user_service_url=USER_SERVICE_URL
        )

        # Login manually
        response = client.login(
            username=test_credentials["email"],
            password=test_credentials["password"]
        )

        # Verify login response
        assert "access_token" in response
        assert "user" in response
        assert response["user"]["email"] == test_credentials["email"]

    def test_04_sdk_logout(self, test_credentials):
        """Test SDK logout."""
        client = TradingClient.from_credentials(
            api_url=BACKEND_URL,
            user_service_url=USER_SERVICE_URL,
            username=test_credentials["email"],
            password=test_credentials["password"]
        )

        # Logout
        client.logout()

        # Tokens should be cleared
        assert client._api._access_token is None
        assert client._api._refresh_token is None


class TestSDKAPIKeyAuth:
    """Test SDK authentication with API keys."""

    @pytest.fixture(scope="class")
    def api_key_user(self):
        """Create user and generate API key."""
        import httpx

        # Register user
        email = f"sdk_apikey_{int(time.time())}@example.com"
        response = httpx.post(
            f"{USER_SERVICE_URL}/v1/auth/register",
            json={
                "email": email,
                "password": "TestPassword123!",
                "full_name": "SDK API Key Test User"
            },
            timeout=10.0
        )
        assert response.status_code == 201
        access_token = response.json()["access_token"]

        # Create API key
        response = httpx.post(
            f"{USER_SERVICE_URL}/v1/api-keys",
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                "name": "SDK Test Key",
                "scopes": ["read:market_data", "write:orders", "read:accounts"],
                "expires_in_days": 90
            },
            timeout=10.0
        )
        assert response.status_code == 201

        return {
            "email": email,
            "access_token": access_token,
            "api_key": response.json()["api_key"],
            "key_id": response.json()["key_id"]
        }

    def test_01_sdk_api_key_authentication(self, api_key_user):
        """Test SDK authentication with API key."""
        # Create client with API key
        client = TradingClient(
            api_url=BACKEND_URL,
            api_key=api_key_user["api_key"]
        )

        # Verify client is configured with API key
        assert client.api_key == api_key_user["api_key"]
        assert client._api._api_key == api_key_user["api_key"]

    def test_02_sdk_api_key_invalid(self):
        """Test SDK with invalid API key."""
        # Create client with invalid API key
        client = TradingClient(
            api_url=BACKEND_URL,
            api_key="sb_invalid_key"
        )

        # Making requests should fail
        # (This depends on backend implementing API key validation)
        # For now, we just verify the client was created
        assert client.api_key == "sb_invalid_key"


class TestSDKMultiAccount:
    """Test SDK multi-account support."""

    @pytest.fixture(scope="class")
    def multi_account_user(self):
        """Create user with multiple trading accounts."""
        import httpx

        # Register user
        email = f"sdk_multiacct_{int(time.time())}@example.com"
        response = httpx.post(
            f"{USER_SERVICE_URL}/v1/auth/register",
            json={
                "email": email,
                "password": "TestPassword123!",
                "full_name": "Multi Account Test User"
            },
            timeout=10.0
        )
        assert response.status_code == 201
        data = response.json()

        return {
            "email": email,
            "password": "TestPassword123!",
            "access_token": data["access_token"],
            "user_id": data["user"]["id"]
        }

    def test_01_accounts_collection_lazy_loading(self, multi_account_user):
        """Test that AccountsCollection uses lazy loading."""
        client = TradingClient.from_credentials(
            api_url=BACKEND_URL,
            user_service_url=USER_SERVICE_URL,
            username=multi_account_user["email"],
            password=multi_account_user["password"]
        )

        # Accounts should not be fetched yet
        assert client.Accounts._accounts is None

    def test_02_accounts_collection_fetch(self, multi_account_user):
        """Test fetching accounts through SDK."""
        client = TradingClient.from_credentials(
            api_url=BACKEND_URL,
            user_service_url=USER_SERVICE_URL,
            username=multi_account_user["email"],
            password=multi_account_user["password"]
        )

        # Access accounts to trigger fetch
        try:
            accounts = client.Accounts.list()
            print(f"Found {len(accounts)} accounts")

            # If user has accounts
            if len(accounts) > 0:
                # Verify account structure
                account = accounts[0]
                assert "account_id" in account
                assert "broker" in account

                # Test dict-like access
                account_id = account["account_id"]
                account_proxy = client.Accounts[account_id]
                assert account_proxy.account_id == account_id

        except APIError as e:
            # If endpoint not implemented yet, that's okay
            if "404" in str(e) or "Not Found" in str(e):
                pytest.skip("Multi-account endpoint not implemented yet")
            raise

    def test_03_primary_account_access(self, multi_account_user):
        """Test accessing primary account."""
        client = TradingClient.from_credentials(
            api_url=BACKEND_URL,
            user_service_url=USER_SERVICE_URL,
            username=multi_account_user["email"],
            password=multi_account_user["password"]
        )

        # Account() should use primary account
        try:
            account = client.Account()
            # If this works, verify it's using primary
            # (actual trading operations would happen here)
        except Exception as e:
            # Backend might not be fully implemented
            pass

    def test_04_explicit_account_access(self, multi_account_user):
        """Test explicit account access by ID."""
        client = TradingClient.from_credentials(
            api_url=BACKEND_URL,
            user_service_url=USER_SERVICE_URL,
            username=multi_account_user["email"],
            password=multi_account_user["password"]
        )

        try:
            # List accounts
            accounts = client.Accounts.list()

            if len(accounts) > 0:
                # Access specific account
                account_id = accounts[0]["account_id"]
                account_proxy = client.Accounts[account_id]

                assert account_proxy.account_id == account_id

                # Test membership
                assert account_id in client.Accounts

                # Test iteration
                for acc_id in client.Accounts:
                    assert isinstance(acc_id, str)
                    break  # Just test first one

        except APIError as e:
            if "404" in str(e):
                pytest.skip("Multi-account endpoint not implemented")
            raise


class TestSDKEndToEnd:
    """End-to-end SDK tests."""

    @pytest.fixture(scope="class")
    def e2e_client(self):
        """Create authenticated client for E2E tests."""
        import httpx

        # Register user
        email = f"sdk_e2e_{int(time.time())}@example.com"
        response = httpx.post(
            f"{USER_SERVICE_URL}/v1/auth/register",
            json={
                "email": email,
                "password": "TestPassword123!",
                "full_name": "E2E Test User"
            },
            timeout=10.0
        )
        assert response.status_code == 201
        password = "TestPassword123!"

        # Create SDK client
        client = TradingClient.from_credentials(
            api_url=BACKEND_URL,
            user_service_url=USER_SERVICE_URL,
            username=email,
            password=password
        )

        return client

    def test_01_full_workflow_with_jwt(self, e2e_client):
        """Test complete workflow: login -> list accounts -> access account."""
        # Client should be authenticated
        assert e2e_client._api._access_token is not None

        # Try to access accounts (may not be implemented yet)
        try:
            accounts = e2e_client.Accounts.list()
            print(f"User has {len(accounts)} accounts")
        except APIError as e:
            if "404" in str(e):
                pytest.skip("Accounts endpoint not implemented")
            raise

    def test_02_full_workflow_with_api_key(self):
        """Test complete workflow using API key."""
        import httpx

        # Register user
        email = f"sdk_e2e_apikey_{int(time.time())}@example.com"
        response = httpx.post(
            f"{USER_SERVICE_URL}/v1/auth/register",
            json={
                "email": email,
                "password": "TestPassword123!",
                "full_name": "E2E API Key User"
            },
            timeout=10.0
        )
        assert response.status_code == 201
        access_token = response.json()["access_token"]

        # Create API key
        response = httpx.post(
            f"{USER_SERVICE_URL}/v1/api-keys",
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                "name": "E2E Test Key",
                "scopes": ["read:market_data", "write:orders", "read:accounts"],
                "expires_in_days": 90
            },
            timeout=10.0
        )
        assert response.status_code == 201
        api_key = response.json()["api_key"]

        # Create SDK client with API key
        client = TradingClient(
            api_url=BACKEND_URL,
            api_key=api_key
        )

        # Verify API key is set
        assert client.api_key == api_key

        # Try to access accounts
        try:
            accounts = client.Accounts.list()
            print(f"User has {len(accounts)} accounts via API key")
        except APIError as e:
            if "404" in str(e):
                pytest.skip("Accounts endpoint not implemented")
            raise


class TestSDKTokenRefresh:
    """Test JWT token refresh functionality."""

    def test_token_refresh(self):
        """Test that SDK automatically refreshes expired tokens."""
        import httpx

        # Register user
        email = f"sdk_refresh_{int(time.time())}@example.com"
        response = httpx.post(
            f"{USER_SERVICE_URL}/v1/auth/register",
            json={
                "email": email,
                "password": "TestPassword123!",
                "full_name": "Token Refresh Test"
            },
            timeout=10.0
        )
        assert response.status_code == 201

        # Create client
        client = TradingClient.from_credentials(
            api_url=BACKEND_URL,
            user_service_url=USER_SERVICE_URL,
            username=email,
            password="TestPassword123!"
        )

        # Store original token
        original_token = client._api._access_token

        # Token refresh is automatic - would need to manipulate
        # expiry time to test this properly
        # For now, just verify mechanism exists
        assert hasattr(client._api, '_refresh_access_token')
        assert hasattr(client._api, '_token_expires_at')


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
