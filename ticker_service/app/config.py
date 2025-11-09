from functools import lru_cache
from datetime import time as dtime
from typing import List

import pytz
from pydantic import Field, field_validator, ValidationError
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = Field(default="ticker-service")
    environment: str = Field(default="dev")
    redis_url: str = Field(default="redis://localhost:6379/0")
    kite_api_key: str = Field(default="", env="KITE_API_KEY")
    kite_api_secret: str = Field(default="", env="KITE_API_SECRET")
    kite_access_token: str = Field(default="", env="KITE_ACCESS_TOKEN")
    nifty_symbol: str = Field(default="NSE:NIFTY")
    nifty_quote_symbol: str = Field(default="NSE:NIFTY 50")
    fo_underlying: str = Field(default="NIFTY")
    fo_underlyings: List[str] = Field(
        default_factory=lambda: ["NIFTY", "BANKNIFTY", "FINNIFTY"],
        description="List of underlyings to track for options (used by strike rebalancer and multi-instrument support)",
    )
    option_expiry_window: int = Field(default=3, description="Number of upcoming expiries to track")
    otm_levels: int = Field(default=10)
    historical_days: int = Field(default=10)
    historical_bootstrap_batch: int = Field(default=6)
    option_strike_step: int = Field(default=50, description="Strike spacing used to derive ATM ladder")
    stream_interval_seconds: float = Field(default=1.0)
    publish_channel_prefix: str = Field(default="ticker:nifty")
    ticker_mode: str = Field(default="full", description="Ticker mode to request from KiteTicker (full|quote|ltp)")
    max_instruments_per_ws_connection: int = Field(
        default=3000,
        description="Maximum instruments per WebSocket connection (KiteConnect limit: 3,000). Pool will create additional connections when limit reached.",
    )
    max_ws_connections_per_account: int = Field(
        default=3,
        description="Maximum WebSocket connections per API key (KiteConnect hard limit: 3)",
    )
    enabled_panels: List[str] = Field(
        default_factory=lambda: [
            "pcr",
            "max_pain",
            "iv_atm",
            "iv_otm",
            "delta",
            "gamma",
            "theta",
            "vega",
        ]
    )
    instrument_db_host: str = Field(default="localhost", env="INSTRUMENT_DB_HOST")
    instrument_db_port: int = Field(default=5432, env="INSTRUMENT_DB_PORT")
    instrument_db_name: str = Field(default="stocksblitz_unified", env="INSTRUMENT_DB_NAME")
    instrument_db_user: str = Field(default="stocksblitz", env="INSTRUMENT_DB_USER")
    instrument_db_password: str = Field(default="", env="INSTRUMENT_DB_PASSWORD")  # MUST be set via environment
    instrument_refresh_hours: int = Field(default=1, description="Refresh cadence for instrument metadata (hours)")
    instrument_refresh_check_seconds: int = Field(
        default=1_800, description="Background poll interval for registry refresh checks (seconds)"
    )
    instrument_segments: List[str] = Field(default_factory=lambda: ["NFO", "NSE", "BSE", "MCX", "CDS"])
    instrument_cache_ttl_seconds: int = Field(
        default=300,
        description="Lifetime for instrument lookup cache (seconds)",
    )
    market_open_time: dtime = Field(
        default=dtime(9, 15),
        description="Local market open time (24h clock).",
    )
    market_close_time: dtime = Field(
        default=dtime(15, 30),
        description="Local market close time (24h clock).",
    )
    market_timezone: str = Field(
        default="Asia/Kolkata",
        description="IANA timezone used to evaluate market hours.",
    )
    mock_history_minutes: int = Field(
        default=10,
        description="Number of minutes of historical data to seed mock generation.",
    )
    mock_price_variation_bps: float = Field(
        default=12.5,
        description="Maximum mock price variation per tick in basis points.",
    )
    mock_volume_variation: float = Field(
        default=0.15,
        description="Maximum proportional variation applied to mock volumes/OI.",
    )
    enable_mock_data: bool = Field(
        default=True,
        description="Enable mock data generation outside market hours. Set to False to disable all mock data.",
    )
    mock_state_max_size: int = Field(
        default=5000,
        description="Maximum number of instruments in mock state cache (LRU eviction prevents memory leak).",
    )

    # Tick batching configuration (Phase 4)
    tick_batch_enabled: bool = Field(
        default=True,
        description="Enable tick batching for improved throughput (10x faster). Set to False for testing.",
    )
    tick_batch_window_ms: int = Field(
        default=100,
        description="Tick batch window in milliseconds before flushing to Redis.",
    )
    tick_batch_max_size: int = Field(
        default=1000,
        description="Maximum batch size before forced flush to Redis.",
    )

    # Tick validation configuration (Phase 4)
    tick_validation_enabled: bool = Field(
        default=True,
        description="Enable tick validation with Pydantic schemas to catch malformed data early.",
    )
    tick_validation_strict: bool = Field(
        default=False,
        description="Strict validation mode - raise exceptions on validation errors instead of logging.",
    )

    # Option Greeks calculation configuration
    option_greeks_interest_rate: float = Field(
        default=0.10,
        description="Risk-free interest rate for Greeks calculation (as decimal, e.g., 0.10 for 10%)",
    )
    option_greeks_dividend_yield: float = Field(
        default=0.0,
        description="Dividend yield for Greeks calculation (as decimal, e.g., 0.02 for 2%)",
    )
    option_expiry_time_hour: int = Field(
        default=15,
        description="Hour of option expiry time in 24h format (IST timezone)",
    )
    option_expiry_time_minute: int = Field(
        default=30,
        description="Minute of option expiry time (IST timezone)",
    )

    # OrderExecutor configuration
    order_executor_worker_poll_interval: float = Field(
        default=1.0,
        description="Interval in seconds for OrderExecutor worker to poll for pending tasks",
    )
    order_executor_worker_error_backoff: float = Field(
        default=5.0,
        description="Backoff delay in seconds after OrderExecutor worker encounters an error",
    )
    order_executor_max_tasks: int = Field(
        default=10000,
        description="Maximum number of tasks to keep in memory before cleanup",
    )

    # API Authentication configuration
    api_key_enabled: bool = Field(
        default=True,  # PRODUCTION DEFAULT: Always require authentication
        env="API_KEY_ENABLED",
        description="Enable API key authentication. Set to True to require X-API-Key header.",
    )
    api_key: str = Field(
        default="",
        env="API_KEY",
        description="API key for authenticating requests. Required when api_key_enabled=True.",
    )
    user_service_base_url: str = Field(
        default="",
        env="USER_SERVICE_BASE_URL",
        description="Base URL of the user service for centralized trading-account credentials.",
    )
    user_service_service_token: str = Field(
        default="",
        env="USER_SERVICE_SERVICE_TOKEN",
        description="Service-to-service token for authenticating with the user service.",
    )
    use_user_service_accounts: bool = Field(
        default=False,
        env="USE_USER_SERVICE_ACCOUNTS",
        description="Set to true to load Kite accounts from the user service instead of local YAML.",
    )

    # Validators
    @field_validator("option_expiry_window", "otm_levels", "historical_days", "option_strike_step")
    @classmethod
    def validate_positive_integers(cls, v: int, info) -> int:
        """Ensure positive integer values"""
        if v <= 0:
            raise ValueError(f"{info.field_name} must be positive, got {v}")
        return v

    @field_validator("instrument_db_port")
    @classmethod
    def validate_port(cls, v: int) -> int:
        """Ensure port is in valid range"""
        if not (1 <= v <= 65535):
            raise ValueError(f"instrument_db_port must be between 1 and 65535, got {v}")
        return v

    @field_validator("ticker_mode")
    @classmethod
    def validate_ticker_mode(cls, v: str) -> str:
        """Ensure ticker mode is valid"""
        mode = v.lower()
        if mode not in {"full", "quote", "ltp"}:
            raise ValueError(f"ticker_mode must be one of 'full', 'quote', 'ltp', got '{v}'")
        return mode

    @field_validator("market_timezone")
    @classmethod
    def validate_timezone(cls, v: str) -> str:
        """Ensure timezone is valid IANA timezone"""
        try:
            pytz.timezone(v)
        except pytz.UnknownTimeZoneError:
            raise ValueError(f"market_timezone '{v}' is not a valid IANA timezone")
        return v

    @field_validator("mock_volume_variation")
    @classmethod
    def validate_proportion(cls, v: float) -> float:
        """Ensure proportion is between 0 and 1"""
        if not (0 <= v <= 1):
            raise ValueError(f"mock_volume_variation must be between 0 and 1, got {v}")
        return v

    @field_validator("mock_price_variation_bps")
    @classmethod
    def validate_bps(cls, v: float) -> float:
        """Ensure basis points are non-negative"""
        if v < 0:
            raise ValueError(f"mock_price_variation_bps must be non-negative, got {v}")
        return v

    @field_validator("option_greeks_interest_rate", "option_greeks_dividend_yield")
    @classmethod
    def validate_rates(cls, v: float, info) -> float:
        """Ensure rates are valid (0 to 1)"""
        if not (0 <= v <= 1):
            raise ValueError(f"{info.field_name} must be between 0 and 1 (as decimal), got {v}")
        return v

    @field_validator("option_expiry_time_hour")
    @classmethod
    def validate_hour(cls, v: int) -> int:
        """Ensure hour is valid (0-23)"""
        if not (0 <= v <= 23):
            raise ValueError(f"option_expiry_time_hour must be between 0 and 23, got {v}")
        return v

    @field_validator("option_expiry_time_minute")
    @classmethod
    def validate_minute(cls, v: int) -> int:
        """Ensure minute is valid (0-59)"""
        if not (0 <= v <= 59):
            raise ValueError(f"option_expiry_time_minute must be between 0 and 59, got {v}")
        return v

    @field_validator("stream_interval_seconds", "order_executor_worker_poll_interval", "order_executor_worker_error_backoff")
    @classmethod
    def validate_positive_floats(cls, v: float, info) -> float:
        """Ensure positive float values"""
        if v <= 0:
            raise ValueError(f"{info.field_name} must be positive, got {v}")
        return v

    @field_validator("order_executor_max_tasks")
    @classmethod
    def validate_max_tasks(cls, v: int) -> int:
        """Ensure max tasks is positive"""
        if v <= 0:
            raise ValueError(f"order_executor_max_tasks must be positive, got {v}")
        return v

    @field_validator("instrument_db_host", "instrument_db_name", "instrument_db_user")
    @classmethod
    def validate_non_empty_strings(cls, v: str, info) -> str:
        """Ensure critical database fields are not empty"""
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} cannot be empty")
        return v.strip()

    @field_validator("redis_url")
    @classmethod
    def validate_redis_url(cls, v: str) -> str:
        """Ensure Redis URL starts with redis://"""
        if not v.startswith("redis://"):
            raise ValueError(f"redis_url must start with 'redis://', got '{v}'")
        return v

    @field_validator("max_instruments_per_ws_connection")
    @classmethod
    def validate_max_instruments(cls, v: int) -> int:
        """Ensure max instruments is reasonable (1-3000)"""
        if not (1 <= v <= 3000):
            raise ValueError(f"max_instruments_per_ws_connection must be between 1 and 3000, got {v}")
        return v

    @field_validator("max_ws_connections_per_account")
    @classmethod
    def validate_max_connections(cls, v: int) -> int:
        """Ensure max connections is reasonable (1-3)"""
        if not (1 <= v <= 3):
            raise ValueError(f"max_ws_connections_per_account must be between 1 and 3 (KiteConnect limit), got {v}")
        return v

    def model_post_init(self, __context) -> None:
        """Post-initialization validation for dependent fields"""
        # Validate API key is set when authentication is enabled
        if self.api_key_enabled and not self.api_key.strip():
            raise ValueError("api_key must be set when api_key_enabled=True")

        # PRODUCTION SECURITY: Force authentication in production environments
        if self.environment.lower() in ("production", "prod", "live") and not self.api_key_enabled:
            raise ValueError(
                "API key authentication MUST be enabled in production environments. "
                "Set API_KEY_ENABLED=true and provide a strong API_KEY."
            )

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }


@lru_cache()
def get_settings() -> Settings:
    return Settings()
