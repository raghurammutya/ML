from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional

class Settings(BaseSettings):
    # Database
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "stocksblitz_unified"
    db_user: str = "stocksblitz"
    db_password: str = "stocksblitz123"
    db_pool_min: int = 10
    db_pool_max: int = 20
    db_pool_timeout: int = 60
    db_query_timeout: int = 30  # Individual query timeout
    database_url: Optional[str] = None
    timescale_database_url: Optional[str] = None
    postgres_url: Optional[str] = None
    
    # Redis
    redis_url: str = "redis://localhost:6379"
    redis_decode_responses: bool = True
    redis_socket_timeout: int = 30
    redis_socket_connect_timeout: int = 30
    fo_stream_enabled: bool = True
    fo_options_channel: str = "ticker:nifty:options"
    fo_underlying_channel: str = "ticker:nifty:underlying"
    fo_timeframes: list[str] = ["1min", "5min", "15min"]
    fo_persist_timeframes: list[str] = ["1min"]
    fo_flush_lag_seconds: int = 5
    fo_max_buffer_minutes: int = 60
    fo_strike_gap: int = 50
    fo_max_moneyness_level: int = 10
    fo_option_expiry_window: int = 3
    backfill_enabled: bool = True
    backfill_check_interval_seconds: int = 300
    backfill_gap_threshold_minutes: int = 3
    backfill_max_batch_minutes: int = 120
    monitor_default_symbol: str = "NIFTY50"
   
    # Ticker service
    ticker_service_url: str = "http://localhost:8080"
    ticker_service_timeout: int = 10
    ticker_service_mode: str = "FULL"
    ticker_service_account_id: Optional[str] = None
    monitor_stream_enabled: bool = True

    # Cache TTLs (seconds)
    cache_ttl_1m: int = 60
    cache_ttl_5m: int = 300
    cache_ttl_15m: int = 900
    cache_ttl_30m: int = 1800
    cache_ttl_1h: int = 3600
    cache_ttl_1d: int = 86400
    
    # Performance
    preload_days: int = 30
    preload_max_records: int = 50000
    refresh_interval: int = 300
    max_memory_cache_size: int = 100000  # Max records in memory
    
    # API Settings
    api_title: str = "TradingView ML Visualization API"
    api_version: str = "1.0.0"
    api_prefix: str = ""
    
    # Logging
    log_level: str = "info"
    log_format: str = "json"
    
    # CORS
    cors_origins: list[str] = ["*"]
    cors_credentials: bool = True
    cors_methods: list[str] = ["*"]
    cors_headers: list[str] = ["*"]
    
    class Config:
        env_file = ".env"
        env_file_encoding = 'utf-8'
        case_sensitive = False

@lru_cache()
def get_settings() -> Settings:
    return Settings()

# Resolution mappings for TradingView
RESOLUTION_MAP = {
    "1": "1 minute",
    "2": "2 minutes", 
    "3": "3 minutes",
    "5": "5 minutes",
    "10": "10 minutes",
    "15": "15 minutes",
    "30": "30 minutes",
    "60": "1 hour",
    "D": "1 day",
    "W": "1 week",
    "M": "1 month"
}

# Database table mappings - use base table for all timeframes and aggregate in code
TABLE_MAP = {
    "1": "minute_bars",       # 1-minute: use canonical base table
    "2": "minute_bars",       # 2-minute: aggregate from canonical table
    "3": "minute_bars",       # 3-minute: aggregate from canonical table
    "5": "minute_bars",       # 5-minute: aggregate from canonical table
    "10": "minute_bars",      # 10-minute: aggregate from canonical table
    "15": "minute_bars",      # 15-minute: aggregate from canonical table
    "30": "minute_bars",      # 30-minute: aggregate from canonical table
    "60": "minute_bars",      # 1-hour: aggregate from canonical table
    "D": "minute_bars",       # Daily: aggregate from canonical table
    "W": "minute_bars",       # Weekly: aggregate from canonical table
    "M": "minute_bars"        # Monthly: aggregate from canonical table
}
