"""
Indicator validation and registry management for StocksBlitz SDK.

This module fetches indicator definitions from the API and validates
indicator parameters before making subscription requests.

Features:
- In-memory caching (instant validation after first fetch)
- Persistent disk cache (instant initialization on subsequent runs)
- Auto-refresh (once per day by default)
- Fallback to API if cache is stale
"""

import os
import json
import time
from typing import Dict, List, Optional, Any
from pathlib import Path
from .exceptions import APIError


class IndicatorValidationError(Exception):
    """Raised when indicator validation fails."""
    pass


class IndicatorRegistry:
    """
    Client-side indicator registry that fetches definitions from API
    and validates indicator parameters.

    Caching strategy:
    1. In-memory cache: First validation in session
    2. Disk cache: Subsequent SDK runs (instant load)
    3. Auto-refresh: Once per day (configurable)
    """

    DEFAULT_CACHE_DIR = Path.home() / ".stocksblitz"
    DEFAULT_CACHE_FILE = "indicator_registry.json"
    DEFAULT_CACHE_TTL = 86400  # 24 hours

    def __init__(
        self,
        api_client,
        enable_disk_cache: bool = True,
        cache_dir: Optional[Path] = None,
        cache_ttl: int = DEFAULT_CACHE_TTL
    ):
        """
        Initialize indicator registry.

        Args:
            api_client: APIClient instance
            enable_disk_cache: Enable persistent disk cache (default: True)
            cache_dir: Custom cache directory (default: ~/.stocksblitz)
            cache_ttl: Cache TTL in seconds (default: 86400 = 24 hours)
        """
        self.api_client = api_client
        self._indicators: Optional[Dict[str, Dict]] = None
        self._categories: Optional[List[str]] = None

        # Disk cache settings
        self.enable_disk_cache = enable_disk_cache
        self.cache_dir = cache_dir or self.DEFAULT_CACHE_DIR
        self.cache_file = self.cache_dir / self.DEFAULT_CACHE_FILE
        self.cache_ttl = cache_ttl

        # Try to load from disk cache on initialization
        if self.enable_disk_cache:
            self._load_from_disk_cache()

    def _load_from_disk_cache(self) -> bool:
        """
        Load indicator registry from disk cache.

        Returns:
            True if cache was loaded successfully, False otherwise
        """
        try:
            if not self.cache_file.exists():
                return False

            with open(self.cache_file, 'r') as f:
                cache_data = json.load(f)

            # Check cache age
            cached_at = cache_data.get("cached_at", 0)
            age = time.time() - cached_at

            if age > self.cache_ttl:
                # Cache is stale
                return False

            # Load cached data
            self._indicators = cache_data.get("indicators", {})
            self._categories = cache_data.get("categories", [])

            return True

        except Exception:
            # Ignore errors, will fetch from API
            return False

    def _save_to_disk_cache(self):
        """Save indicator registry to disk cache."""
        if not self.enable_disk_cache:
            return

        try:
            # Create cache directory if it doesn't exist
            self.cache_dir.mkdir(parents=True, exist_ok=True)

            cache_data = {
                "cached_at": time.time(),
                "indicators": self._indicators,
                "categories": self._categories,
                "version": "1.0"
            }

            # Write to temp file first, then rename (atomic operation)
            temp_file = self.cache_file.with_suffix('.tmp')
            with open(temp_file, 'w') as f:
                json.dump(cache_data, f, indent=2)

            temp_file.replace(self.cache_file)

        except Exception:
            # Silently ignore cache write errors
            pass

    def fetch_indicators(self, force_refresh: bool = False) -> Dict[str, Dict]:
        """
        Fetch indicator definitions from API.

        Args:
            force_refresh: If True, bypass all caches and fetch fresh data from API

        Returns:
            Dictionary mapping indicator names to definitions

        Raises:
            APIError: If API request fails

        Force Refresh Methods:
        ----------------------
        1. Programmatic:
           >>> client.indicators.fetch_indicators(force_refresh=True)

        2. Environment variable:
           >>> export STOCKSBLITZ_FORCE_REFRESH=1
           >>> python my_script.py

        3. Delete cache file:
           >>> rm ~/.stocksblitz/indicator_registry.json

        4. Clear cache method:
           >>> client.indicators.clear_cache()

        5. Disable disk cache:
           >>> client = TradingClient(..., enable_disk_cache=False)
        """
        # Check environment variable for force refresh
        if os.environ.get('STOCKSBLITZ_FORCE_REFRESH') == '1':
            force_refresh = True

        # Return in-memory cache if available (unless force refresh)
        if self._indicators is not None and not force_refresh:
            return self._indicators

        try:
            # Fetch from API
            response = self.api_client.get("/indicators/list")

            if response.get("status") != "success":
                raise APIError(f"Failed to fetch indicators: {response.get('detail', 'Unknown error')}")

            # Build lookup dict
            self._indicators = {
                ind["name"]: ind
                for ind in response.get("indicators", [])
            }

            self._categories = response.get("categories", [])

            # Save to disk cache
            self._save_to_disk_cache()

            return self._indicators

        except Exception as e:
            raise APIError(f"Failed to fetch indicator registry: {str(e)}")

    def clear_cache(self):
        """
        Clear both in-memory and disk cache.

        Use this when you want to force a fresh fetch from API.

        Example:
            >>> client.indicators.clear_cache()
            >>> client.indicators.fetch_indicators()  # Will fetch from API
        """
        # Clear in-memory cache
        self._indicators = None
        self._categories = None

        # Delete disk cache file
        if self.enable_disk_cache and self.cache_file.exists():
            try:
                self.cache_file.unlink()
            except Exception:
                pass

    def get_indicator(self, name: str) -> Optional[Dict]:
        """
        Get indicator definition by name.

        Args:
            name: Indicator name (e.g., "RSI", "MACD")

        Returns:
            Indicator definition dict or None if not found
        """
        if self._indicators is None:
            self.fetch_indicators()

        return self._indicators.get(name.upper())

    def list_indicators(
        self,
        category: Optional[str] = None,
        include_custom: bool = True
    ) -> List[Dict]:
        """
        List available indicators.

        Args:
            category: Filter by category (momentum, trend, volatility, volume, other)
            include_custom: Include custom user-defined indicators

        Returns:
            List of indicator definitions
        """
        if self._indicators is None:
            self.fetch_indicators()

        indicators = list(self._indicators.values())

        if category:
            indicators = [ind for ind in indicators if ind.get("category") == category.lower()]

        if not include_custom:
            indicators = [ind for ind in indicators if not ind.get("is_custom", False)]

        return indicators

    def get_categories(self) -> List[str]:
        """
        Get list of indicator categories.

        Returns:
            List of category names
        """
        if self._categories is None:
            self.fetch_indicators()

        return self._categories or []

    def search_indicators(self, query: str) -> List[Dict]:
        """
        Search indicators by name or description.

        Args:
            query: Search query

        Returns:
            List of matching indicator definitions
        """
        if self._indicators is None:
            self.fetch_indicators()

        query_lower = query.lower()
        results = []

        for indicator in self._indicators.values():
            if (query_lower in indicator.get("name", "").lower() or
                query_lower in indicator.get("display_name", "").lower() or
                query_lower in indicator.get("description", "").lower()):
                results.append(indicator)

        return results

    def validate_indicator(
        self,
        name: str,
        params: Dict[str, Any],
        raise_on_error: bool = True
    ) -> tuple[bool, Optional[str]]:
        """
        Validate indicator name and parameters against registry.

        Args:
            name: Indicator name (e.g., "RSI", "MACD")
            params: Parameter dict (e.g., {"length": 14, "scalar": 100})
            raise_on_error: If True, raise IndicatorValidationError on validation failure

        Returns:
            Tuple of (is_valid, error_message)

        Raises:
            IndicatorValidationError: If validation fails and raise_on_error=True
        """
        # Get indicator definition
        indicator = self.get_indicator(name)

        if not indicator:
            error = f"Unknown indicator: '{name}'. Use list_indicators() to see available indicators."
            if raise_on_error:
                raise IndicatorValidationError(error)
            return False, error

        # Validate parameters
        param_defs = {p["name"]: p for p in indicator.get("parameters", [])}

        # Check for required parameters
        for param_name, param_def in param_defs.items():
            if param_def.get("required", True) and param_name not in params:
                error = (
                    f"Missing required parameter '{param_name}' for indicator '{name}'. "
                    f"Expected: {param_def.get('description', 'No description')}"
                )
                if raise_on_error:
                    raise IndicatorValidationError(error)
                return False, error

        # Validate each provided parameter
        for param_name, param_value in params.items():
            if param_name not in param_defs:
                error = (
                    f"Unknown parameter '{param_name}' for indicator '{name}'. "
                    f"Valid parameters: {', '.join(param_defs.keys())}"
                )
                if raise_on_error:
                    raise IndicatorValidationError(error)
                return False, error

            param_def = param_defs[param_name]

            # Validate type
            param_type = param_def.get("type")
            if param_type == "integer":
                if not isinstance(param_value, int):
                    error = (
                        f"Parameter '{param_name}' must be an integer, got {type(param_value).__name__}"
                    )
                    if raise_on_error:
                        raise IndicatorValidationError(error)
                    return False, error

            elif param_type == "float":
                if not isinstance(param_value, (int, float)):
                    error = (
                        f"Parameter '{param_name}' must be a number, got {type(param_value).__name__}"
                    )
                    if raise_on_error:
                        raise IndicatorValidationError(error)
                    return False, error

            elif param_type == "boolean":
                if not isinstance(param_value, bool):
                    error = (
                        f"Parameter '{param_name}' must be a boolean, got {type(param_value).__name__}"
                    )
                    if raise_on_error:
                        raise IndicatorValidationError(error)
                    return False, error

            elif param_type == "string":
                if not isinstance(param_value, str):
                    error = (
                        f"Parameter '{param_name}' must be a string, got {type(param_value).__name__}"
                    )
                    if raise_on_error:
                        raise IndicatorValidationError(error)
                    return False, error

            # Validate range (for numeric types)
            if param_type in ["integer", "float"]:
                min_val = param_def.get("min")
                max_val = param_def.get("max")

                if min_val is not None and param_value < min_val:
                    error = (
                        f"Parameter '{param_name}' value {param_value} is below minimum {min_val}"
                    )
                    if raise_on_error:
                        raise IndicatorValidationError(error)
                    return False, error

                if max_val is not None and param_value > max_val:
                    error = (
                        f"Parameter '{param_name}' value {param_value} exceeds maximum {max_val}"
                    )
                    if raise_on_error:
                        raise IndicatorValidationError(error)
                    return False, error

        return True, None

    def get_parameter_info(self, name: str) -> List[Dict]:
        """
        Get parameter information for an indicator.

        Args:
            name: Indicator name

        Returns:
            List of parameter definitions

        Raises:
            IndicatorValidationError: If indicator not found
        """
        indicator = self.get_indicator(name)

        if not indicator:
            raise IndicatorValidationError(
                f"Unknown indicator: '{name}'. Use list_indicators() to see available indicators."
            )

        return indicator.get("parameters", [])

    def get_default_params(self, name: str) -> Dict[str, Any]:
        """
        Get default parameters for an indicator.

        Args:
            name: Indicator name

        Returns:
            Dict of parameter names to default values

        Raises:
            IndicatorValidationError: If indicator not found
        """
        param_info = self.get_parameter_info(name)

        defaults = {}
        for param in param_info:
            # Only include required parameters in defaults
            if param.get("required", True):
                defaults[param["name"]] = param["default"]

        return defaults

    def print_indicator_info(self, name: str):
        """
        Print detailed information about an indicator.

        Args:
            name: Indicator name

        Raises:
            IndicatorValidationError: If indicator not found
        """
        indicator = self.get_indicator(name)

        if not indicator:
            raise IndicatorValidationError(
                f"Unknown indicator: '{name}'. Use list_indicators() to see available indicators."
            )

        print(f"\n{indicator['display_name']}")
        print("=" * 80)
        print(f"Name: {indicator['name']}")
        print(f"Category: {indicator['category']}")
        print(f"Description: {indicator['description']}")

        if indicator.get("is_custom"):
            print(f"Type: Custom (by {indicator.get('author', 'Unknown')})")

        print(f"\nParameters:")
        if indicator.get("parameters"):
            for param in indicator["parameters"]:
                required = "✓" if param.get("required", True) else " "
                param_type = param["type"]
                default = param["default"]

                print(f"  [{required}] {param['name']:<12} ({param_type:<8}): {param['description']}")

                if param_type in ["integer", "float"]:
                    print(f"      {'':12}  Default: {default}, Range: [{param.get('min')}, {param.get('max')}]")
                else:
                    print(f"      {'':12}  Default: {default}")
        else:
            print("  No parameters")

        print(f"\nOutputs: {', '.join(indicator['outputs'])}")
        print()
