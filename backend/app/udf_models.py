from pydantic import BaseModel, Field
from typing import List, Optional, Union, Literal
from datetime import datetime
from enum import Enum

class SymbolInfo(BaseModel):
    symbol: str
    name: str
    description: str
    type: str = "stock"
    exchange: str = "NSE"
    timezone: str = "Asia/Kolkata"
    minmov: int = 1
    pricescale: int = 100
    has_intraday: bool = True
    has_daily: bool = True
    has_weekly: bool = True
    has_monthly: bool = True

class ConfigResponse(BaseModel):
    supports_search: bool = True
    supports_group_request: bool = False
    supports_marks: bool = True
    supports_timescale_marks: bool = True
    supports_time: bool = True
    exchanges: List[dict] = Field(default_factory=lambda: [
        {"value": "NSE", "name": "NSE", "desc": "National Stock Exchange"}
    ])
    supported_resolutions: List[str] = [
        "1", "2", "3", "5", "10", "15", "30", "60", "D", "W", "M"
    ]

class HistoryResponse(BaseModel):
    s: Literal["ok", "no_data", "error"]
    t: Optional[List[int]] = None  # Unix timestamps
    o: Optional[List[float]] = None  # Open prices
    h: Optional[List[float]] = None  # High prices
    l: Optional[List[float]] = None  # Low prices
    c: Optional[List[float]] = None  # Close prices
    v: Optional[List[float]] = None  # Volumes
    errmsg: Optional[str] = None

class MarkInfo(BaseModel):
    id: str
    time: int
    color: str
    text: str
    label: str
    labelFontColor: str = "white"
    minSize: int = 5

class MarksResponse(BaseModel):
    marks: List[MarkInfo]

class TimescaleMarkInfo(BaseModel):
    id: str
    time: int
    color: str
    tooltip: List[str]
    label: str

class TimescaleMarksResponse(BaseModel):
    marks: List[TimescaleMarkInfo]

class MLLabel(BaseModel):
    time: int
    label: str
    confidence: float
    color: str

class LabelType(str, Enum):
    VERY_BEARISH = "Very Bearish"
    BEARISH = "Bearish"
    SOMEWHAT_BEARISH = "Somewhat Bearish"
    NEUTRAL = "Neutral"
    SOMEWHAT_BULLISH = "Somewhat Bullish"
    BULLISH = "Bullish"
    VERY_BULLISH = "Very Bullish"

# Color mapping for labels
LABEL_COLORS = {
    "Very Bearish": "#8B0000",      # Dark Red
    "Bearish": "#FF0000",           # Red
    "Somewhat Bearish": "#FF6347",  # Tomato
    "Neutral": "#808080",           # Gray
    "Somewhat Bullish": "#90EE90",  # Light Green
    "Bullish": "#00FF00",           # Green
    "Very Bullish": "#006400"       # Dark Green
}

class CacheStats(BaseModel):
    l1_hits: int = 0
    l2_hits: int = 0
    l3_hits: int = 0
    total_misses: int = 0
    hit_rate: float = 0.0
    memory_cache_size: int = 0
    redis_keys: int = 0

class HealthResponse(BaseModel):
    status: str
    database: str
    redis: str
    cache_stats: CacheStats
    uptime: float
    version: str