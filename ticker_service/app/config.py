from functools import lru_cache
from datetime import time as dtime
from typing import List

from pydantic import Field
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
    option_expiry_window: int = Field(default=3, description="Number of upcoming expiries to track")
    otm_levels: int = Field(default=10)
    historical_days: int = Field(default=10)
    historical_bootstrap_batch: int = Field(default=6)
    option_strike_step: int = Field(default=50, description="Strike spacing used to derive ATM ladder")
    stream_interval_seconds: float = Field(default=1.0)
    publish_channel_prefix: str = Field(default="ticker:nifty")
    ticker_mode: str = Field(default="full", description="Ticker mode to request from KiteTicker (full|quote|ltp)")
    max_instruments_per_ws_connection: int = Field(
        default=1000,
        description="Maximum instruments per WebSocket connection. Pool will create additional connections when limit reached.",
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
    instrument_db_password: str = Field(default="stocksblitz123", env="INSTRUMENT_DB_PASSWORD")
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
        default=False,
        env="API_KEY_ENABLED",
        description="Enable API key authentication. Set to True to require X-API-Key header.",
    )
    api_key: str = Field(
        default="",
        env="API_KEY",
        description="API key for authenticating requests. Required when api_key_enabled=True.",
    )

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }


@lru_cache()
def get_settings() -> Settings:
    return Settings()
