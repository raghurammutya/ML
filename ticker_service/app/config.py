from functools import lru_cache
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
    instrument_refresh_hours: int = Field(default=12, description="Refresh cadence for instrument metadata (hours)")
    instrument_refresh_check_seconds: int = Field(
        default=1_800, description="Background poll interval for registry refresh checks (seconds)"
    )
    instrument_segments: List[str] = Field(default_factory=lambda: ["NFO", "NSE"])
    instrument_cache_ttl_seconds: int = Field(
        default=300,
        description="Lifetime for instrument lookup cache (seconds)",
    )

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }


@lru_cache()
def get_settings() -> Settings:
    return Settings()
