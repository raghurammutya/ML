"""
API client for StocksBlitz backend.
"""

import httpx
from typing import Dict, Any, Optional, List
from .exceptions import APIError, TimeoutError as SDKTimeoutError
from .cache import SimpleCache, cache_key


class APIClient:
    """HTTP client for StocksBlitz API."""

    def __init__(self, base_url: str, api_key: str, cache: Optional[SimpleCache] = None):
        """
        Initialize API client.

        Args:
            base_url: Base URL of the API (e.g., "http://localhost:8009")
            api_key: API key for authentication
            cache: Cache instance (optional)
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.cache = cache or SimpleCache(default_ttl=60)

        self.client = httpx.Client(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30.0
        )

    def __del__(self):
        """Cleanup client on destruction."""
        try:
            self.client.close()
        except:
            pass

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
        """
        # Check cache first
        if cache_ttl is not None:
            key = cache_key("GET", path, str(params))
            cached = self.cache.get(key)
            if cached is not None:
                return cached

        try:
            response = self.client.get(path, params=params)
            response.raise_for_status()
            data = response.json()

            # Cache successful response
            if cache_ttl is not None:
                self.cache.set(key, data, ttl=cache_ttl)

            return data

        except httpx.HTTPStatusError as e:
            raise APIError(
                f"HTTP {e.response.status_code}: {e.response.text}",
                status_code=e.response.status_code,
                response=e.response.json() if e.response.text else None
            )
        except httpx.TimeoutException:
            raise SDKTimeoutError(f"Request timeout for GET {path}")
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
        """
        try:
            response = self.client.post(path, json=json, params=params)
            response.raise_for_status()
            return response.json()

        except httpx.HTTPStatusError as e:
            raise APIError(
                f"HTTP {e.response.status_code}: {e.response.text}",
                status_code=e.response.status_code,
                response=e.response.json() if e.response.text else None
            )
        except httpx.TimeoutException:
            raise SDKTimeoutError(f"Request timeout for POST {path}")
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
        """
        try:
            response = self.client.delete(path, params=params)
            response.raise_for_status()
            return response.json()

        except httpx.HTTPStatusError as e:
            raise APIError(
                f"HTTP {e.response.status_code}: {e.response.text}",
                status_code=e.response.status_code,
                response=e.response.json() if e.response.text else None
            )
        except httpx.TimeoutException:
            raise SDKTimeoutError(f"Request timeout for DELETE {path}")
        except Exception as e:
            raise APIError(f"Request failed: {str(e)}")
