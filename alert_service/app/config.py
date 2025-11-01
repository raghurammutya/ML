"""
Alert Service Configuration
Uses Pydantic Settings for environment variable management
"""

from functools import lru_cache
from typing import List, Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Alert service configuration settings."""

    # Service
    app_name: str = Field(default="alert-service")
    environment: str = Field(default="development")
    port: int = Field(default=8082)

    # Database (shared with backend)
    db_host: str = Field(default="localhost")
    db_port: int = Field(default=5432)
    db_name: str = Field(default="stocksblitz_unified")
    db_user: str = Field(default="stocksblitz")
    db_password: str = Field(default="stocksblitz123")
    db_pool_min_size: int = Field(default=5)
    db_pool_max_size: int = Field(default=20)

    # Redis
    redis_url: str = Field(default="redis://localhost:6379/1")
    redis_cache_ttl: int = Field(default=300)

    # External services
    backend_url: str = Field(default="http://localhost:8000")
    ticker_service_url: str = Field(default="http://localhost:8080")

    # Telegram Bot
    telegram_enabled: bool = Field(default=True)
    telegram_bot_token: str = Field(default="")
    telegram_webhook_secret: str = Field(default="")

    # Evaluation settings
    evaluation_worker_enabled: bool = Field(default=True)
    evaluation_batch_size: int = Field(default=100)
    evaluation_concurrency: int = Field(default=10)
    min_evaluation_interval: int = Field(default=10, description="Minimum seconds between evaluations")

    # Notification settings
    notification_rate_limit_per_user_per_hour: int = Field(default=50)
    notification_retry_attempts: int = Field(default=3)
    notification_retry_backoff: float = Field(default=2.0)
    global_telegram_rate_limit: int = Field(default=30, description="Messages per second")

    # Security
    api_key_enabled: bool = Field(default=True)

    # Monitoring
    metrics_enabled: bool = Field(default=True)
    metrics_port: int = Field(default=9092)
    log_level: str = Field(default="INFO")

    # Validators
    @field_validator("db_port", "port", "metrics_port")
    @classmethod
    def validate_port(cls, v: int) -> int:
        """Ensure port is in valid range."""
        if not (1 <= v <= 65535):
            raise ValueError(f"Port must be between 1 and 65535, got {v}")
        return v

    @field_validator("redis_url")
    @classmethod
    def validate_redis_url(cls, v: str) -> str:
        """Ensure Redis URL starts with redis://"""
        if not v.startswith("redis://"):
            raise ValueError(f"redis_url must start with 'redis://', got '{v}'")
        return v

    @field_validator("min_evaluation_interval")
    @classmethod
    def validate_min_interval(cls, v: int) -> int:
        """Ensure minimum evaluation interval is reasonable."""
        if v < 10:
            raise ValueError(f"min_evaluation_interval must be >= 10 seconds, got {v}")
        return v

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Ensure log level is valid."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in valid_levels:
            raise ValueError(f"log_level must be one of {valid_levels}, got '{v}'")
        return v.upper()

    def model_post_init(self, __context) -> None:
        """Post-initialization validation for dependent fields."""
        # Validate Telegram token is set when Telegram is enabled
        if self.telegram_enabled and not self.telegram_bot_token.strip():
            raise ValueError("telegram_bot_token must be set when telegram_enabled=True")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }

    @property
    def database_url(self) -> str:
        """Construct database URL."""
        return f"postgresql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"

    @property
    def async_database_url(self) -> str:
        """Construct async database URL for asyncpg."""
        return f"postgresql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
