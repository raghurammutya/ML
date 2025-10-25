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
    nifty_symbol: str = Field(default="NIFTY50")
    fo_underlying: str = Field(default="NIFTY50")
    option_expiry_window: int = Field(default=3, description="Number of upcoming expiries to track")
    otm_levels: int = Field(default=10)
    historical_days: int = Field(default=10)
    publish_channel_prefix: str = Field(default="ticker:nifty")
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

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }


@lru_cache()
def get_settings() -> Settings:
    return Settings()
