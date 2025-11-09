"""
Unit tests for AccountsCollection and AccountProxy.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from stocksblitz.accounts_collection import AccountsCollection, AccountProxy
from stocksblitz.exceptions import AuthenticationError, APIError


class TestAccountProxy:
    """Test AccountProxy delegation to Account."""

    def test_account_proxy_creation(self):
        """Test creating an AccountProxy."""
        api_client = Mock()
        proxy = AccountProxy("XJ4540", api_client)

        assert proxy.account_id == "XJ4540"
        assert proxy._api == api_client
        assert proxy._account is not None

    def test_account_proxy_delegates_positions(self):
        """Test that positions property delegates to Account."""
        api_client = Mock()
        api_client.get.return_value = {"data": []}
        api_client.cache = Mock()
        api_client.cache.get.return_value = None

        proxy = AccountProxy("XJ4540", api_client)
        positions = proxy.positions

        # Verify API was called with correct account_id
        api_client.get.assert_called_once()
        call_args = api_client.get.call_args
        assert "/accounts/XJ4540/positions" in call_args[0][0]

    def test_account_proxy_delegates_buy(self):
        """Test that buy() delegates to Account."""
        api_client = Mock()
        api_client.post.return_value = {"order_id": "ORD123"}

        proxy = AccountProxy("XJ4540", api_client)
        order = proxy.buy("NIFTY50", 50)

        # Verify API was called
        api_client.post.assert_called_once()
        call_args = api_client.post.call_args
        assert "/accounts/XJ4540/orders" in call_args[0][0]
        assert call_args[1]["json"]["tradingsymbol"] == "NIFTY50"
        assert call_args[1]["json"]["quantity"] == 50

    def test_account_proxy_repr(self):
        """Test AccountProxy string representation."""
        api_client = Mock()
        proxy = AccountProxy("XJ4540", api_client)

        assert repr(proxy) == "<AccountProxy XJ4540>"


class TestAccountsCollection:
    """Test AccountsCollection."""

    @pytest.fixture
    def mock_api_client(self):
        """Create mock API client."""
        api = Mock()
        api._access_token = "test_token"
        api._api_key = None
        api.user_service_url = "http://localhost:8011"
        api._get_auth_header = Mock(return_value={"Authorization": "Bearer test_token"})
        return api

    @pytest.fixture
    def sample_accounts_response(self):
        """Sample accounts API response."""
        return {
            "accounts": [
                {
                    "account_id": "XJ4540",
                    "broker": "zerodha",
                    "role": "owner",
                    "is_primary": True
                },
                {
                    "account_id": "AB1234",
                    "broker": "zerodha",
                    "role": "member",
                    "is_primary": False
                }
            ]
        }

    def test_collection_lazy_loading(self, mock_api_client):
        """Test that accounts are not fetched until accessed."""
        collection = AccountsCollection(mock_api_client)

        # Should not have fetched yet
        assert collection._accounts is None

    @patch("httpx.get")
    def test_collection_fetch_accounts_jwt(self, mock_httpx_get, mock_api_client, sample_accounts_response):
        """Test fetching accounts with JWT authentication."""
        # Mock httpx response
        mock_response = Mock()
        mock_response.json.return_value = sample_accounts_response
        mock_response.raise_for_status = Mock()
        mock_httpx_get.return_value = mock_response

        collection = AccountsCollection(mock_api_client)
        collection._fetch_accounts()

        # Verify httpx.get was called
        mock_httpx_get.assert_called_once()
        call_args = mock_httpx_get.call_args
        assert "/v1/users/me/accounts" in call_args[0][0]

        # Verify accounts were stored
        assert len(collection._accounts) == 2
        assert "XJ4540" in collection._accounts
        assert "AB1234" in collection._accounts

        # Verify primary account was identified
        assert collection._primary_account_id == "XJ4540"

    @patch("httpx.get")
    def test_collection_getitem(self, mock_httpx_get, mock_api_client, sample_accounts_response):
        """Test accessing account by ID using []."""
        # Mock httpx response
        mock_response = Mock()
        mock_response.json.return_value = sample_accounts_response
        mock_response.raise_for_status = Mock()
        mock_httpx_get.return_value = mock_response

        collection = AccountsCollection(mock_api_client)
        account_proxy = collection["XJ4540"]

        # Verify AccountProxy was returned
        assert isinstance(account_proxy, AccountProxy)
        assert account_proxy.account_id == "XJ4540"

    @patch("httpx.get")
    def test_collection_getitem_invalid_account(self, mock_httpx_get, mock_api_client, sample_accounts_response):
        """Test accessing invalid account raises KeyError."""
        # Mock httpx response
        mock_response = Mock()
        mock_response.json.return_value = sample_accounts_response
        mock_response.raise_for_status = Mock()
        mock_httpx_get.return_value = mock_response

        collection = AccountsCollection(mock_api_client)

        with pytest.raises(KeyError) as exc_info:
            collection["INVALID"]

        assert "INVALID" in str(exc_info.value)
        assert "not found or not accessible" in str(exc_info.value)

    @patch("httpx.get")
    def test_collection_contains(self, mock_httpx_get, mock_api_client, sample_accounts_response):
        """Test 'in' operator."""
        # Mock httpx response
        mock_response = Mock()
        mock_response.json.return_value = sample_accounts_response
        mock_response.raise_for_status = Mock()
        mock_httpx_get.return_value = mock_response

        collection = AccountsCollection(mock_api_client)

        assert "XJ4540" in collection
        assert "AB1234" in collection
        assert "INVALID" not in collection

    @patch("httpx.get")
    def test_collection_iteration(self, mock_httpx_get, mock_api_client, sample_accounts_response):
        """Test iterating over account IDs."""
        # Mock httpx response
        mock_response = Mock()
        mock_response.json.return_value = sample_accounts_response
        mock_response.raise_for_status = Mock()
        mock_httpx_get.return_value = mock_response

        collection = AccountsCollection(mock_api_client)
        account_ids = list(collection)

        assert len(account_ids) == 2
        assert "XJ4540" in account_ids
        assert "AB1234" in account_ids

    @patch("httpx.get")
    def test_collection_len(self, mock_httpx_get, mock_api_client, sample_accounts_response):
        """Test len() on collection."""
        # Mock httpx response
        mock_response = Mock()
        mock_response.json.return_value = sample_accounts_response
        mock_response.raise_for_status = Mock()
        mock_httpx_get.return_value = mock_response

        collection = AccountsCollection(mock_api_client)

        assert len(collection) == 2

    @patch("httpx.get")
    def test_collection_list(self, mock_httpx_get, mock_api_client, sample_accounts_response):
        """Test list() method returns account details."""
        # Mock httpx response
        mock_response = Mock()
        mock_response.json.return_value = sample_accounts_response
        mock_response.raise_for_status = Mock()
        mock_httpx_get.return_value = mock_response

        collection = AccountsCollection(mock_api_client)
        accounts = collection.list()

        assert len(accounts) == 2
        assert accounts[0]["account_id"] == "XJ4540"
        assert accounts[0]["broker"] == "zerodha"
        assert accounts[1]["account_id"] == "AB1234"

    @patch("httpx.get")
    def test_collection_primary(self, mock_httpx_get, mock_api_client, sample_accounts_response):
        """Test primary() method."""
        # Mock httpx response
        mock_response = Mock()
        mock_response.json.return_value = sample_accounts_response
        mock_response.raise_for_status = Mock()
        mock_httpx_get.return_value = mock_response

        collection = AccountsCollection(mock_api_client)
        primary = collection.primary()

        assert isinstance(primary, AccountProxy)
        assert primary.account_id == "XJ4540"

    @patch("httpx.get")
    def test_collection_primary_id(self, mock_httpx_get, mock_api_client, sample_accounts_response):
        """Test primary_id property."""
        # Mock httpx response
        mock_response = Mock()
        mock_response.json.return_value = sample_accounts_response
        mock_response.raise_for_status = Mock()
        mock_httpx_get.return_value = mock_response

        collection = AccountsCollection(mock_api_client)

        assert collection.primary_id == "XJ4540"

    @patch("httpx.get")
    def test_collection_primary_fallback(self, mock_httpx_get, mock_api_client):
        """Test primary account fallback when no is_primary flag."""
        # Response without is_primary
        response = {
            "accounts": [
                {
                    "account_id": "XJ4540",
                    "broker": "zerodha",
                    "role": "member"
                },
                {
                    "account_id": "AB1234",
                    "broker": "zerodha",
                    "role": "member"
                }
            ]
        }

        mock_response = Mock()
        mock_response.json.return_value = response
        mock_response.raise_for_status = Mock()
        mock_httpx_get.return_value = mock_response

        collection = AccountsCollection(mock_api_client)

        # Should use first account as primary
        assert collection.primary_id == "XJ4540"

    def test_collection_unauthenticated(self):
        """Test fetching without authentication raises error."""
        api = Mock()
        api._access_token = None
        api._api_key = None

        collection = AccountsCollection(api)

        with pytest.raises(AuthenticationError) as exc_info:
            collection._fetch_accounts()

        assert "Must be authenticated" in str(exc_info.value)

    @patch("httpx.get")
    def test_collection_clear_cache(self, mock_httpx_get, mock_api_client, sample_accounts_response):
        """Test clear_cache() method."""
        # Mock httpx response
        mock_response = Mock()
        mock_response.json.return_value = sample_accounts_response
        mock_response.raise_for_status = Mock()
        mock_httpx_get.return_value = mock_response

        collection = AccountsCollection(mock_api_client)

        # Fetch accounts
        _ = collection["XJ4540"]
        assert collection._accounts is not None

        # Clear cache
        collection.clear_cache()
        assert collection._accounts is None
        assert len(collection._proxies) == 0

    @patch("httpx.get")
    def test_collection_proxy_caching(self, mock_httpx_get, mock_api_client, sample_accounts_response):
        """Test that AccountProxy instances are cached."""
        # Mock httpx response
        mock_response = Mock()
        mock_response.json.return_value = sample_accounts_response
        mock_response.raise_for_status = Mock()
        mock_httpx_get.return_value = mock_response

        collection = AccountsCollection(mock_api_client)

        # Access same account twice
        proxy1 = collection["XJ4540"]
        proxy2 = collection["XJ4540"]

        # Should be same instance
        assert proxy1 is proxy2

    def test_collection_repr_not_loaded(self):
        """Test repr when accounts not loaded."""
        api = Mock()
        collection = AccountsCollection(api)

        assert repr(collection) == "<AccountsCollection (not loaded)>"

    @patch("httpx.get")
    def test_collection_repr_loaded(self, mock_httpx_get, mock_api_client, sample_accounts_response):
        """Test repr when accounts loaded."""
        # Mock httpx response
        mock_response = Mock()
        mock_response.json.return_value = sample_accounts_response
        mock_response.raise_for_status = Mock()
        mock_httpx_get.return_value = mock_response

        collection = AccountsCollection(mock_api_client)
        _ = len(collection)  # Trigger fetch

        assert repr(collection) == "<AccountsCollection 2 accounts>"

    def test_fetch_accounts_api_key_mode(self, sample_accounts_response):
        """Test fetching accounts in API key mode (no user_service_url)."""
        api = Mock()
        api._access_token = None
        api._api_key = "test_api_key"
        api.user_service_url = None
        api.get.return_value = sample_accounts_response

        collection = AccountsCollection(api)
        collection._fetch_accounts()

        # Should call backend /v1/accounts
        api.get.assert_called_once_with("/v1/accounts", cache_ttl=60)

        # Verify accounts were stored
        assert len(collection._accounts) == 2
        assert collection._primary_account_id == "XJ4540"
