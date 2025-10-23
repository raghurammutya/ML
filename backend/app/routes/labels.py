# app/routes/labels.py
from typing import Optional
from fastapi import APIRouter, Request, HTTPException, Depends
from pydantic import BaseModel
import asyncpg
import logging
from datetime import datetime

router = APIRouter()
logger = logging.getLogger(__name__)

# ---------- Pydantic Models ----------
class LabelCreate(BaseModel):
    symbol: str
    timeframe: str  # '1', '5', '15', '30'
    timestamp: int  # unix seconds
    label: str  # 'Bullish', 'Bearish', 'Neutral'
    price: Optional[float] = None
    ohlc: Optional[dict] = None  # optional OHLC data

class LabelDelete(BaseModel):
    symbol: str
    timeframe: str
    timestamp: int

class LabelResponse(BaseModel):
    success: bool
    message: str

# ---------- Helper to get DB pool ----------
async def get_pool(request: Request) -> asyncpg.Pool:
    # Try to get from app.state first (like marks_asyncpg.py does)
    from app.database import create_pool
    pool_key = "pg_pool"
    pool = getattr(request.app.state, pool_key, None)
    
    if pool is None:
        # Create a new pool if needed
        pool = await create_pool()
        setattr(request.app.state, pool_key, pool)
    
    return pool

# ---------- Routes ----------
@router.post("/api/labels", response_model=LabelResponse)
async def create_label(
    request: Request,
    label_data: LabelCreate
):
    """Create or update a label for a specific candle"""
    logger.info(f"Received label create request: {label_data}")
    try:
        pool = await get_pool(request)
        
        # Normalize symbol to match marks endpoint logic
        symbol_normalized = label_data.symbol.strip().upper()
        symbol_aliases = {
            "NIFTY": "NIFTY",
            "NIFTY50": "NIFTY", 
            "NSE:NIFTY50": "NIFTY",
            "NSE:NIFTY": "NIFTY",
            "^NSEI": "NIFTY",
        }
        symbol_normalized = symbol_aliases.get(symbol_normalized, symbol_normalized)
        
        # Normalize timeframe to match DB format ('5' -> '5min')
        timeframe = f"{label_data.timeframe}min" if label_data.timeframe.isdigit() else label_data.timeframe
        
        # Convert unix timestamp to PostgreSQL timestamp
        timestamp = datetime.fromtimestamp(label_data.timestamp)
        
        async with pool.acquire() as conn:
            # First check if a label already exists
            existing = await conn.fetchrow("""
                SELECT id FROM ml_labeled_data
                WHERE symbol = $1 AND timeframe = $2 AND time = $3
            """, symbol_normalized, timeframe, timestamp)
            
            if existing:
                # Update existing label
                await conn.execute("""
                    UPDATE ml_labeled_data
                    SET label = $4, label_confidence = 1.0, updated_at = NOW()
                    WHERE symbol = $1 AND timeframe = $2 AND time = $3
                """, symbol_normalized, timeframe, timestamp, label_data.label)
                message = f"Updated label to {label_data.label}"
            else:
                # Insert new label
                await conn.execute("""
                    INSERT INTO ml_labeled_data (symbol, timeframe, time, label, label_confidence, created_at)
                    VALUES ($1, $2, $3, $4, 1.0, NOW())
                """, symbol_normalized, timeframe, timestamp, label_data.label)
                message = f"Created new {label_data.label} label"
        
        logger.info(f"Label operation: {message} for {label_data.symbol} at {timestamp}")
        return LabelResponse(success=True, message=message)
        
    except Exception as e:
        logger.error(f"Failed to create/update label: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to save label: {str(e)}")

@router.delete("/api/labels", response_model=LabelResponse)
async def delete_label(
    request: Request,
    label_data: LabelDelete
):
    """Delete a label for a specific candle"""
    try:
        pool = await get_pool(request)
        
        # Normalize symbol to match marks endpoint logic
        symbol_normalized = label_data.symbol.strip().upper()
        symbol_aliases = {
            "NIFTY": "NIFTY",
            "NIFTY50": "NIFTY", 
            "NSE:NIFTY50": "NIFTY",
            "NSE:NIFTY": "NIFTY",
            "^NSEI": "NIFTY",
        }
        symbol_normalized = symbol_aliases.get(symbol_normalized, symbol_normalized)
        
        # Normalize timeframe
        timeframe = f"{label_data.timeframe}min" if label_data.timeframe.isdigit() else label_data.timeframe
        
        # Convert unix timestamp to PostgreSQL timestamp
        timestamp = datetime.fromtimestamp(label_data.timestamp)
        
        async with pool.acquire() as conn:
            result = await conn.execute("""
                DELETE FROM ml_labeled_data
                WHERE symbol = $1 AND timeframe = $2 AND time = $3
            """, symbol_normalized, timeframe, timestamp)
            
            rows_deleted = int(result.split()[-1])
            
        if rows_deleted > 0:
            message = f"Deleted label for {label_data.symbol} at {timestamp}"
            logger.info(message)
            return LabelResponse(success=True, message=message)
        else:
            return LabelResponse(success=False, message="No label found to delete")
            
    except Exception as e:
        logger.error(f"Failed to delete label: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to delete label: {str(e)}")