"""
AccountsCollection and AccountProxy for multi-account support.

Provides hybrid interface:
- Simple: client.Account().buy(...)  # Uses primary account
- Explicit: client.Accounts["XJ4540"].buy(...)  # Specific account
"""

from typing import TYPE_CHECKING, Dict, Optional, List
from .account import Account
from .exceptions import AuthenticationError, APIError

if TYPE_CHECKING:
    from .api import APIClient


class AccountProxy:
    """
    Proxy for accessing a specific trading account.

    Provides the same interface as Account but bound to a specific account_id.

    Example:
        >>> # Access specific account
        >>> account = client.Accounts["XJ4540"]
        >>> account.buy("NIFTY50", quantity=50)
        >>> positions = account.positions
    """

    def __init__(self, account_id: str, api_client: 'APIClient'):
        """
        Initialize account proxy.

        Args:
            account_id: Trading account ID (e.g., "XJ4540")
            api_client: API client instance
        """
        self.account_id = account_id
        self._api = api_client
        # Create underlying Account instance
        self._account = Account(account_id, api_client)

    # Delegate all Account methods to underlying Account instance

    @property
    def positions(self):
        """Get all positions for this account."""
        return self._account.positions

    @property
    def holdings(self):
        """Get all holdings for this account."""
        return self._account.holdings

    @property
    def orders(self):
        """Get all orders for this account."""
        return self._account.orders

    @property
    def funds(self):
        """Get available funds for this account."""
        return self._account.funds

    def position(self, instrument):
        """Get position for specific instrument."""
        return self._account.position(instrument)

    def buy(self, instrument, quantity: int, **kwargs):
        """Place buy order."""
        return self._account.buy(instrument, quantity, **kwargs)

    def sell(self, instrument, quantity: int, **kwargs):
        """Place sell order."""
        return self._account.sell(instrument, quantity, **kwargs)

    def __repr__(self) -> str:
        return f"<AccountProxy {self.account_id}>"


class AccountsCollection:
    """
    Collection of trading accounts accessible to the user.

    Provides dict-like access to accounts by account_id.
    Auto-populates on first access by fetching from user_service.

    Example:
        >>> # Access specific account
        >>> client.Accounts["XJ4540"].positions
        >>> client.Accounts["XJ4540"].buy("NIFTY50", 50)
        >>>
        >>> # List all accounts
        >>> for account_id in client.Accounts:
        ...     print(account_id)
        >>>
        >>> # Get account details
        >>> accounts_list = client.Accounts.list()
    """

    def __init__(self, api_client: 'APIClient'):
        """
        Initialize accounts collection.

        Args:
            api_client: API client instance
        """
        self._api = api_client
        self._accounts: Optional[Dict[str, Dict]] = None  # Lazy loaded
        self._proxies: Dict[str, AccountProxy] = {}  # Cache of AccountProxy instances
        self._primary_account_id: Optional[str] = None

    def _fetch_accounts(self):
        """
        Fetch accessible accounts from user_service.

        Raises:
            AuthenticationError: If not authenticated
            APIError: If request fails
        """
        if self._accounts is not None:
            return  # Already fetched

        # Check if authenticated
        if not self._api._access_token and not self._api._api_key:
            raise AuthenticationError(
                "Must be authenticated to access accounts. "
                "Call login() first or provide api_key."
            )

        try:
            # Fetch from user_service /v1/users/me/accounts
            if self._api.user_service_url:
                # JWT authentication - use user_service
                import httpx
                headers = self._api._get_auth_header()
                response = httpx.get(
                    f"{self._api.user_service_url}/v1/users/me/accounts",
                    headers=headers,
                    timeout=10.0
                )
                response.raise_for_status()
                data = response.json()
            else:
                # API key authentication - use backend
                # Backend should have /v1/accounts endpoint that returns user's accounts
                data = self._api.get("/v1/accounts", cache_ttl=60)

            # Store accounts indexed by account_id
            accounts_list = data.get("accounts", [])
            self._accounts = {acc["account_id"]: acc for acc in accounts_list}

            # Identify primary account
            for acc in accounts_list:
                if acc.get("is_primary") or acc.get("role") == "owner":
                    self._primary_account_id = acc["account_id"]
                    break

            # If no primary found, use first account
            if not self._primary_account_id and self._accounts:
                self._primary_account_id = list(self._accounts.keys())[0]

        except Exception as e:
            raise APIError(f"Failed to fetch accounts: {str(e)}")

    def __getitem__(self, account_id: str) -> AccountProxy:
        """
        Get account proxy by account_id.

        Args:
            account_id: Trading account ID (e.g., "XJ4540")

        Returns:
            AccountProxy for the specified account

        Raises:
            KeyError: If account not found
            AuthenticationError: If not authenticated

        Example:
            >>> account = client.Accounts["XJ4540"]
            >>> account.buy("NIFTY50", 50)
        """
        # Lazy load accounts
        self._fetch_accounts()

        # Verify account exists and user has access
        if account_id not in self._accounts:
            available = ", ".join(self._accounts.keys())
            raise KeyError(
                f"Account '{account_id}' not found or not accessible. "
                f"Available accounts: {available}"
            )

        # Return cached proxy or create new one
        if account_id not in self._proxies:
            self._proxies[account_id] = AccountProxy(account_id, self._api)

        return self._proxies[account_id]

    def __contains__(self, account_id: str) -> bool:
        """
        Check if account_id is accessible.

        Args:
            account_id: Trading account ID

        Returns:
            True if account is accessible
        """
        self._fetch_accounts()
        return account_id in self._accounts

    def __iter__(self):
        """
        Iterate over account IDs.

        Returns:
            Iterator of account IDs

        Example:
            >>> for account_id in client.Accounts:
            ...     print(account_id)
        """
        self._fetch_accounts()
        return iter(self._accounts.keys())

    def __len__(self) -> int:
        """
        Get number of accessible accounts.

        Returns:
            Number of accounts
        """
        self._fetch_accounts()
        return len(self._accounts)

    def list(self) -> List[Dict]:
        """
        Get list of all accessible accounts with details.

        Returns:
            List of account dicts with metadata

        Example:
            >>> accounts = client.Accounts.list()
            >>> for acc in accounts:
            ...     print(f"{acc['account_id']}: {acc['broker']} ({acc['role']})")
        """
        self._fetch_accounts()
        return list(self._accounts.values())

    def primary(self) -> AccountProxy:
        """
        Get primary account proxy.

        Returns:
            AccountProxy for primary account

        Example:
            >>> account = client.Accounts.primary()
            >>> account.buy("NIFTY50", 50)
        """
        self._fetch_accounts()
        if not self._primary_account_id:
            raise APIError("No primary account found")

        return self[self._primary_account_id]

    @property
    def primary_id(self) -> Optional[str]:
        """
        Get primary account ID.

        Returns:
            Primary account ID or None
        """
        self._fetch_accounts()
        return self._primary_account_id

    def clear_cache(self):
        """Clear cached accounts data (forces re-fetch on next access)."""
        self._accounts = None
        self._proxies.clear()
        self._primary_account_id = None

    def __repr__(self) -> str:
        if self._accounts is None:
            return "<AccountsCollection (not loaded)>"
        return f"<AccountsCollection {len(self._accounts)} accounts>"
