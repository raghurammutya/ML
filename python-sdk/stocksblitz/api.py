"""
API client for StocksBlitz backend.
"""

import httpx
import time
from typing import Dict, Any, Optional, List
from .exceptions import APIError, TimeoutError as SDKTimeoutError, AuthenticationError
from .cache import SimpleCache, cache_key


class APIClient:
    """HTTP client for StocksBlitz API with dual authentication support."""

    def __init__(
        self,
        base_url: str,
        api_key: Optional[str] = None,
        user_service_url: Optional[str] = None,
        cache: Optional[SimpleCache] = None
    ):
        """
        Initialize API client.

        Args:
            base_url: Base URL of the API (e.g., "http://localhost:8081")
            api_key: API key for server-to-server authentication (optional)
            user_service_url: User service URL for JWT authentication (optional)
            cache: Cache instance (optional)

        Note:
            Either api_key OR user_service_url should be provided.
            If user_service_url is provided, use login() method before making requests.
        """
        self.base_url = base_url.rstrip("/")
        self.cache = cache or SimpleCache(default_ttl=60)
        self.user_service_url = user_service_url.rstrip("/") if user_service_url else None

        # Authentication state
        self._api_key = api_key
        self._access_token: Optional[str] = None
        self._refresh_token: Optional[str] = None
        self._token_expires_at: Optional[float] = None

        # Initialize httpx client without auth header (added per-request)
        self.client = httpx.Client(
            base_url=self.base_url,
            timeout=30.0
        )

    def __del__(self):
        """Cleanup client on destruction."""
        try:
            self.client.close()
        except:
            pass

    def _get_auth_header(self) -> Dict[str, str]:
        """
        Get appropriate Authorization header based on auth type.

        Returns:
            Authorization header dict

        Raises:
            AuthenticationError: If no valid authentication available
        """
        # JWT token auth (check if refresh needed)
        if self._access_token:
            # Refresh token if expiring within 60 seconds
            if self._token_expires_at and time.time() >= self._token_expires_at - 60:
                try:
                    self._refresh_access_token()
                except Exception as e:
                    raise AuthenticationError(f"Token refresh failed: {str(e)}")

            return {"Authorization": f"Bearer {self._access_token}"}

        # API key auth
        elif self._api_key:
            return {"Authorization": f"Bearer {self._api_key}"}

        # No authentication configured
        else:
            raise AuthenticationError(
                "No authentication configured. Provide api_key or call login() first."
            )

    def login(self, username: str, password: str, persist_session: bool = True) -> Dict[str, Any]:
        """
        Login with username/password to obtain JWT tokens.

        Args:
            username: User email/username
            password: User password
            persist_session: If True, obtain refresh token for long-lived session

        Returns:
            Login response with user info and tokens

        Raises:
            AuthenticationError: If login fails
            APIError: If request fails
        """
        if not self.user_service_url:
            raise AuthenticationError(
                "user_service_url required for JWT authentication. "
                "Provide it in APIClient constructor."
            )

        try:
            response = httpx.post(
                f"{self.user_service_url}/v1/auth/login",
                json={
                    "email": username,
                    "password": password,
                    "persist_session": persist_session
                },
                timeout=10.0
            )
            response.raise_for_status()
            data = response.json()

            # Store tokens
            self._access_token = data["access_token"]
            self._refresh_token = data.get("refresh_token")
            self._token_expires_at = time.time() + data["expires_in"]

            return data

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise AuthenticationError("Invalid username or password")
            raise AuthenticationError(f"Login failed: {e.response.text}")
        except httpx.TimeoutException:
            raise SDKTimeoutError("Login request timeout")
        except Exception as e:
            raise AuthenticationError(f"Login failed: {str(e)}")

    def _refresh_access_token(self):
        """
        Refresh JWT access token using refresh token.

        Raises:
            AuthenticationError: If refresh fails
        """
        if not self._refresh_token:
            raise AuthenticationError(
                "No refresh token available. Re-login required."
            )

        if not self.user_service_url:
            raise AuthenticationError("user_service_url not configured")

        try:
            response = httpx.post(
                f"{self.user_service_url}/v1/auth/refresh",
                cookies={"refresh_token": self._refresh_token},
                timeout=10.0
            )
            response.raise_for_status()
            data = response.json()

            # Update access token
            self._access_token = data["access_token"]
            self._token_expires_at = time.time() + data["expires_in"]

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise AuthenticationError(
                    "Refresh token expired or invalid. Re-login required."
                )
            raise AuthenticationError(f"Token refresh failed: {e.response.text}")
        except Exception as e:
            raise AuthenticationError(f"Token refresh failed: {str(e)}")

    def logout(self):
        """
        Logout and clear authentication tokens.

        For JWT auth, this also calls user_service logout endpoint.
        """
        if self._access_token and self.user_service_url:
            try:
                # Logout from user service
                httpx.post(
                    f"{self.user_service_url}/v1/auth/logout",
                    headers={"Authorization": f"Bearer {self._access_token}"},
                    timeout=5.0
                )
            except:
                pass  # Best effort

        # Clear tokens
        self._access_token = None
        self._refresh_token = None
        self._token_expires_at = None

    def get(self, path: str, params: Optional[Dict] = None,
            cache_ttl: Optional[int] = None) -> Dict[str, Any]:
        """
        GET request with optional caching.

        Args:
            path: API path (e.g., "/instruments/current")
            params: Query parameters
            cache_ttl: Cache TTL in seconds (None to disable caching)

        Returns:
            Response JSON

        Raises:
            APIError: If request fails
            AuthenticationError: If authentication fails
        """
        # Check cache first
        if cache_ttl is not None:
            key = cache_key("GET", path, str(params))
            cached = self.cache.get(key)
            if cached is not None:
                return cached

        try:
            # Get auth header
            headers = self._get_auth_header()

            response = self.client.get(path, params=params, headers=headers)
            response.raise_for_status()
            data = response.json()

            # Cache successful response
            if cache_ttl is not None:
                self.cache.set(key, data, ttl=cache_ttl)

            return data

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise AuthenticationError(f"Authentication failed: {e.response.text}")
            raise APIError(
                f"HTTP {e.response.status_code}: {e.response.text}",
                status_code=e.response.status_code,
                response=e.response.json() if e.response.text else None
            )
        except httpx.TimeoutException:
            raise SDKTimeoutError(f"Request timeout for GET {path}")
        except AuthenticationError:
            raise  # Re-raise auth errors
        except Exception as e:
            raise APIError(f"Request failed: {str(e)}")

    def post(self, path: str, json: Optional[Dict] = None,
             params: Optional[Dict] = None) -> Dict[str, Any]:
        """
        POST request.

        Args:
            path: API path
            json: JSON body
            params: Query parameters

        Returns:
            Response JSON

        Raises:
            APIError: If request fails
            AuthenticationError: If authentication fails
        """
        try:
            # Get auth header
            headers = self._get_auth_header()

            response = self.client.post(path, json=json, params=params, headers=headers)
            response.raise_for_status()
            return response.json()

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise AuthenticationError(f"Authentication failed: {e.response.text}")
            raise APIError(
                f"HTTP {e.response.status_code}: {e.response.text}",
                status_code=e.response.status_code,
                response=e.response.json() if e.response.text else None
            )
        except httpx.TimeoutException:
            raise SDKTimeoutError(f"Request timeout for POST {path}")
        except AuthenticationError:
            raise  # Re-raise auth errors
        except Exception as e:
            raise APIError(f"Request failed: {str(e)}")

    def delete(self, path: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        """
        DELETE request.

        Args:
            path: API path
            params: Query parameters

        Returns:
            Response JSON

        Raises:
            APIError: If request fails
            AuthenticationError: If authentication fails
        """
        try:
            # Get auth header
            headers = self._get_auth_header()

            response = self.client.delete(path, params=params, headers=headers)
            response.raise_for_status()
            return response.json()

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise AuthenticationError(f"Authentication failed: {e.response.text}")
            raise APIError(
                f"HTTP {e.response.status_code}: {e.response.text}",
                status_code=e.response.status_code,
                response=e.response.json() if e.response.text else None
            )
        except httpx.TimeoutException:
            raise SDKTimeoutError(f"Request timeout for DELETE {path}")
        except AuthenticationError:
            raise  # Re-raise auth errors
        except Exception as e:
            raise APIError(f"Request failed: {str(e)}")
