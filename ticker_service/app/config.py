from functools import lru_cache
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    app_name: str = Field(default="ticker-service")
    environment: str = Field(default="dev")
    redis_url: str = Field(default="redis://localhost:6379/0")
    kite_api_key: str = Field(default="", env="KITE_API_KEY")
    kite_api_secret: str = Field(default="", env="KITE_API_SECRET")
    kite_access_token: str = Field(default="", env="KITE_ACCESS_TOKEN")
    historical_days: int = Field(default=10)

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }


@lru_cache()
def get_settings() -> Settings:
    return Settings()
