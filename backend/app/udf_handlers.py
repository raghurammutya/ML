from fastapi import APIRouter, Query, HTTPException
from typing import Optional, Dict, Any, List
import logging
from datetime import datetime
from pydantic import BaseModel

from .models import (
    ConfigResponse, SymbolInfo, HistoryResponse,
    MarksResponse, TimescaleMarksResponse
)
from .database import DataManager
from .monitoring import timed_operation, track_request_metrics
import time

logger = logging.getLogger(__name__)

class UDFHandler:
    def __init__(self, data_manager: DataManager):
        self.data_manager = data_manager
        self.router = APIRouter()
        self._setup_routes()
    
    def _setup_routes(self):
        """Setup all UDF routes"""
        
        @self.router.get("/config", response_model=ConfigResponse)
        @timed_operation("config")
        async def get_config():
            """Get TradingView configuration"""
            return ConfigResponse()
        
        @self.router.get("/symbols")
        @timed_operation("symbol_info")
        async def get_symbol_info(symbol: str = Query(...)):
            """Get symbol information"""
            meta = await self.data_manager.lookup_instrument(symbol)
            if not meta:
                raise HTTPException(status_code=404, detail="Symbol not found")

            tick_size = meta.get("tick_size") or 0.0
            try:
                pricescale = max(1, int(round(1 / tick_size))) if tick_size and tick_size > 0 else 100
            except (ValueError, ZeroDivisionError):
                pricescale = 100
            instrument_type = (meta.get("instrument_type") or "").upper()
            type_map = {
                "EQ": "stock",
                "ETF": "stock",
                "FUT": "futures",
                "CE": "option",
                "PE": "option",
                "INDEX": "index",
            }
            tv_type = type_map.get(instrument_type, "stock")
            tradingsymbol = meta.get("tradingsymbol") or symbol.upper()
            display_name = meta.get("name") or tradingsymbol
            exchange = meta.get("exchange") or "NSE"

            return SymbolInfo(
                symbol=meta.get("canonical_symbol", tradingsymbol),
                name=display_name,
                description=display_name,
                type=tv_type,
                exchange=exchange,
                timezone="Asia/Kolkata",
                minmov=1,
                pricescale=pricescale,
                has_intraday=True,
                has_daily=True
            )
        
        @self.router.get("/search")
        @timed_operation("symbol_search")
        async def search_symbols(
            query: str = Query(...),
            type: Optional[str] = None,
            exchange: Optional[str] = None,
            limit: int = Query(30, ge=1, le=100)
        ):
            """Search for symbols"""
            matches = await self.data_manager.search_monitor_symbols(query, limit=min(limit, 50))
            results: List[Dict[str, Any]] = []
            for match in matches:
                canonical = match.get("canonical_symbol") or match.get("display_symbol") or query.upper()
                display = match.get("display_symbol") or canonical
                exchange = match.get("exchange") or "NSE"
                instrument_type = (match.get("instrument_type") or "").upper()
                type_map = {
                    "EQ": "stock",
                    "ETF": "stock",
                    "FUT": "futures",
                    "CE": "option",
                    "PE": "option",
                    "INDEX": "index",
                }
                results.append({
                    "symbol": canonical,
                    "full_name": f"{exchange}:{display.replace(' ', '')}",
                    "description": match.get("name") or display,
                    "exchange": exchange,
                    "type": type_map.get(instrument_type, "stock"),
                })
            return results
        
        @self.router.get("/history")
        # @timed_operation("history")  # Temporarily disable to check for interference
        async def get_history(
            symbol: str = Query(...),
            from_timestamp: int = Query(..., alias="from"),
            to_timestamp: int = Query(..., alias="to"),
            resolution: str = Query(...)
        ):
            """Get historical data"""
            start_time = time.time()
            
            try:
                # Validate inputs
                # Validate resolution
                valid_resolutions = ["1", "2", "3", "5", "10", "15", "30", "60", "1D", "D", "W", "M"]
                if resolution not in valid_resolutions:
                    return HistoryResponse(s="error", errmsg=f"Invalid resolution: {resolution}")
                
                # Get data
                logger.debug(f"UDF history request: symbol={symbol}, from={from_timestamp}, to={to_timestamp}, resolution={resolution}")

                result = await self.data_manager.get_history(
                    symbol, from_timestamp, to_timestamp, resolution
                )

                logger.debug(f"UDF history response: {len(result.get('t', []))} bars returned for {symbol}")

                # Debug: Log first few timestamps
                if result.get('t'):
                    logger.debug(f"First 3 timestamps for {symbol}: {result['t'][:3]}")
                
                # Track metrics
                duration = time.time() - start_time
                status = 200 if result.get("s") == "ok" else 404
                track_request_metrics("GET", "/history", status, duration)
                
                return result
                
            except Exception as e:
                logger.error(f"History error: {e}")
                return HistoryResponse(s="error", errmsg=str(e))
        
        @self.router.get("/marks")
        @timed_operation("marks")
        async def get_marks(
            symbol: str = Query(...),
            from_timestamp: int = Query(..., alias="from"),
            to_timestamp: int = Query(..., alias="to"),
            resolution: str = Query(...),
            include_neutral: bool = Query(False),
            min_confidence: int = Query(60, ge=0, le=100),   # NEW
            max_marks: int = Query(2000, ge=1, le=20000),    # NEW
            change_only: bool = Query(False),   # NEW
        ):
            try:
                result = await self.data_manager.get_marks(
                    symbol, from_timestamp, to_timestamp, resolution,
                    include_neutral, min_confidence, max_marks,change_only   
                )
                return result
            except Exception as e:
                logger.error(f"Marks error: {e}")
                return {"marks": []}

        @self.router.get("/timescale_marks")
        @timed_operation("timescale_marks")
        async def get_timescale_marks(
            symbol: str = Query(...),
            from_timestamp: int = Query(..., alias="from"),
            to_timestamp: int = Query(..., alias="to"),
            resolution: str = Query(...)
        ):
            """Get timescale marks with detailed tooltips"""
            try:
                get_timescale = getattr(self.data_manager, "get_timescale_marks", None)
                if get_timescale is None:
                    return {"marks": []}
                result = await get_timescale(
                    symbol, from_timestamp, to_timestamp, resolution
                )
                
                return result
                
            except Exception as e:
                logger.error(f"Timescale marks error: {e}")
                return {"marks": []}
        
        @self.router.get("/time")
        @timed_operation("server_time")
        async def get_server_time():
            """Get server time"""
            return str(int(datetime.now().timestamp()))
        
    def get_router(self) -> APIRouter:
        """Get the configured router"""
        return self.router

class LabelIn(BaseModel):
    symbol: str
    resolution: str
    time: int                  # epoch seconds
    label: str                 # "Bullish" | "Bearish" | "Neutral"
    confidence: float | None = None
