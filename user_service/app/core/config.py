"""
Configuration management for user_service
Uses pydantic-settings for environment variable loading and validation
"""

from typing import List, Optional
from pydantic import Field, PostgresDsn, RedisDsn, validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    # Application
    APP_NAME: str = "user_service"
    VERSION: str = "1.0.0"
    ENVIRONMENT: str = Field(default="development", env="ENVIRONMENT")
    DEBUG: bool = Field(default=False, env="DEBUG")

    # API
    API_V1_PREFIX: str = "/v1"

    # Database
    DATABASE_URL: PostgresDsn = Field(..., env="DATABASE_URL")
    DATABASE_POOL_SIZE: int = Field(default=20, env="DATABASE_POOL_SIZE")
    DATABASE_MAX_OVERFLOW: int = Field(default=10, env="DATABASE_MAX_OVERFLOW")
    DATABASE_POOL_TIMEOUT: int = Field(default=30, env="DATABASE_POOL_TIMEOUT")

    # Redis
    REDIS_URL: RedisDsn = Field(..., env="REDIS_URL")
    REDIS_POOL_SIZE: int = Field(default=50, env="REDIS_POOL_SIZE")
    REDIS_SESSION_TTL_DAYS: int = Field(default=90, env="REDIS_SESSION_TTL_DAYS")
    REDIS_SESSION_INACTIVITY_DAYS: int = Field(default=14, env="REDIS_SESSION_INACTIVITY_DAYS")

    # JWT
    JWT_SIGNING_KEY_ID: str = Field(..., env="JWT_SIGNING_KEY_ID")
    JWT_ACCESS_TOKEN_TTL_MINUTES: int = Field(default=15, env="JWT_ACCESS_TOKEN_TTL_MINUTES")
    JWT_REFRESH_TOKEN_TTL_DAYS: int = Field(default=90, env="JWT_REFRESH_TOKEN_TTL_DAYS")
    JWT_ALGORITHM: str = Field(default="RS256", env="JWT_ALGORITHM")
    JWT_ISSUER: str = Field(..., env="JWT_ISSUER")
    JWT_AUDIENCE: str = Field(..., env="JWT_AUDIENCE")

    # KMS/Encryption
    KMS_PROVIDER: str = Field(default="local", env="KMS_PROVIDER")  # 'aws', 'vault', 'local'
    KMS_MASTER_KEY_ID: Optional[str] = Field(default=None, env="KMS_MASTER_KEY_ID")
    KMS_REGION: Optional[str] = Field(default=None, env="KMS_REGION")
    VAULT_URL: Optional[str] = Field(default=None, env="VAULT_URL")
    VAULT_TOKEN: Optional[str] = Field(default=None, env="VAULT_TOKEN")
    LOCAL_KMS_KEY_PATH: str = Field(default="/app/keys/master.key", env="LOCAL_KMS_KEY_PATH")

    # OAuth Providers
    GOOGLE_OAUTH_CLIENT_ID: Optional[str] = Field(default=None, env="GOOGLE_OAUTH_CLIENT_ID")
    GOOGLE_OAUTH_CLIENT_SECRET: Optional[str] = Field(default=None, env="GOOGLE_OAUTH_CLIENT_SECRET")
    GOOGLE_OAUTH_REDIRECT_URI: Optional[str] = Field(default=None, env="GOOGLE_OAUTH_REDIRECT_URI")

    # Email
    SMTP_HOST: str = Field(default="localhost", env="SMTP_HOST")
    SMTP_PORT: int = Field(default=587, env="SMTP_PORT")
    SMTP_USERNAME: Optional[str] = Field(default=None, env="SMTP_USERNAME")
    SMTP_PASSWORD: Optional[str] = Field(default=None, env="SMTP_PASSWORD")
    SMTP_FROM: str = Field(default="noreply@example.com", env="SMTP_FROM")
    SMTP_TLS: bool = Field(default=True, env="SMTP_TLS")

    # Rate Limiting
    RATELIMIT_LOGIN_ATTEMPTS: int = Field(default=5, env="RATELIMIT_LOGIN_ATTEMPTS")
    RATELIMIT_LOGIN_WINDOW_MINUTES: int = Field(default=15, env="RATELIMIT_LOGIN_WINDOW_MINUTES")
    RATELIMIT_REGISTER_ATTEMPTS: int = Field(default=5, env="RATELIMIT_REGISTER_ATTEMPTS")
    RATELIMIT_REGISTER_WINDOW_HOURS: int = Field(default=1, env="RATELIMIT_REGISTER_WINDOW_HOURS")
    RATELIMIT_REFRESH_ATTEMPTS: int = Field(default=10, env="RATELIMIT_REFRESH_ATTEMPTS")
    RATELIMIT_REFRESH_WINDOW_MINUTES: int = Field(default=1, env="RATELIMIT_REFRESH_WINDOW_MINUTES")

    # Security
    PASSWORD_MIN_LENGTH: int = Field(default=12, env="PASSWORD_MIN_LENGTH")
    PASSWORD_BCRYPT_COST: int = Field(default=12, env="PASSWORD_BCRYPT_COST")
    PASSWORD_RESET_TOKEN_TTL_MINUTES: int = Field(default=30, env="PASSWORD_RESET_TOKEN_TTL_MINUTES")
    MFA_TOTP_WINDOW_SECONDS: int = Field(default=30, env="MFA_TOTP_WINDOW_SECONDS")
    SESSION_COOKIE_NAME: str = Field(default="__Secure-refresh_token", env="SESSION_COOKIE_NAME")
    SESSION_COOKIE_SECURE: bool = Field(default=True, env="SESSION_COOKIE_SECURE")
    SESSION_COOKIE_HTTPONLY: bool = Field(default=True, env="SESSION_COOKIE_HTTPONLY")
    SESSION_COOKIE_SAMESITE: str = Field(default="strict", env="SESSION_COOKIE_SAMESITE")

    # CORS
    CORS_ALLOWED_ORIGINS: List[str] = Field(
        default=["http://localhost:3000"],
        env="CORS_ALLOWED_ORIGINS"
    )
    CORS_ALLOW_CREDENTIALS: bool = Field(default=True, env="CORS_ALLOW_CREDENTIALS")

    # Logging & Observability
    LOG_LEVEL: str = Field(default="INFO", env="LOG_LEVEL")
    LOG_FORMAT: str = Field(default="json", env="LOG_FORMAT")  # 'json' or 'text'
    SENTRY_DSN: Optional[str] = Field(default=None, env="SENTRY_DSN")
    PROMETHEUS_PORT: int = Field(default=9090, env="PROMETHEUS_PORT")

    # Feature Flags
    FEATURE_GOOGLE_OAUTH: bool = Field(default=False, env="FEATURE_GOOGLE_OAUTH")
    FEATURE_MFA_TOTP: bool = Field(default=True, env="FEATURE_MFA_TOTP")
    FEATURE_SHARED_ACCOUNTS: bool = Field(default=True, env="FEATURE_SHARED_ACCOUNTS")

    # External APIs
    KITE_API_BASE_URL: str = Field(default="https://api.kite.trade", env="KITE_API_BASE_URL")
    KITE_API_TIMEOUT_SECONDS: int = Field(default=10, env="KITE_API_TIMEOUT_SECONDS")
    KITE_API_MAX_RETRIES: int = Field(default=3, env="KITE_API_MAX_RETRIES")

    # Service Discovery
    TICKER_SERVICE_URL: str = Field(default="http://ticker_service:8002", env="TICKER_SERVICE_URL")
    ALERT_SERVICE_URL: str = Field(default="http://alert_service:8003", env="ALERT_SERVICE_URL")
    BACKEND_SERVICE_URL: str = Field(default="http://backend:8000", env="BACKEND_SERVICE_URL")

    @validator("CORS_ALLOWED_ORIGINS", pre=True)
    def parse_cors_origins(cls, v):
        """Parse comma-separated string to list"""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v

    @validator("SESSION_COOKIE_SAMESITE")
    def validate_samesite(cls, v):
        """Validate SameSite cookie attribute"""
        allowed = ["strict", "lax", "none"]
        if v.lower() not in allowed:
            raise ValueError(f"SESSION_COOKIE_SAMESITE must be one of {allowed}")
        return v.lower()

    @validator("LOG_LEVEL")
    def validate_log_level(cls, v):
        """Validate log level"""
        allowed = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in allowed:
            raise ValueError(f"LOG_LEVEL must be one of {allowed}")
        return v.upper()

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


# Global settings instance
settings = Settings()
