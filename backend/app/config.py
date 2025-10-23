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
    
    # Redis
    redis_url: str = "redis://localhost:6379"
    redis_decode_responses: bool = True
    redis_socket_timeout: int = 5
    redis_socket_connect_timeout: int = 5
    
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
    "1": "nifty50_ohlc",      # 1-minute: use base table
    "2": "nifty50_ohlc",      # 2-minute: aggregate from base table  
    "3": "nifty50_ohlc",      # 3-minute: aggregate from base table
    "5": "nifty50_ohlc",      # 5-minute: aggregate from base table
    "10": "nifty50_ohlc",     # 10-minute: aggregate from base table
    "15": "nifty50_ohlc",     # 15-minute: aggregate from base table
    "30": "nifty50_ohlc",     # 30-minute: aggregate from base table
    "60": "nifty50_ohlc",     # 1-hour: aggregate from base table
    "D": "nifty50_ohlc",      # Daily: aggregate from base table
    "W": "nifty50_ohlc",      # Weekly: aggregate from base table
    "M": "nifty50_ohlc"       # Monthly: aggregate from base table
}