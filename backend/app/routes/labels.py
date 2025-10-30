# app/routes/labels.py
from typing import Optional, List, Any
from fastapi import APIRouter, Request, HTTPException, Depends
from pydantic import BaseModel
import asyncpg
import logging
import json
import uuid
from datetime import datetime

from ..database import create_pool, _normalize_symbol, _normalize_timeframe
from ..realtime import RealTimeHub

router = APIRouter()
logger = logging.getLogger(__name__)

# Global labels hub - will be set by main.py
labels_hub: Optional[RealTimeHub] = None

def set_realtime_hub(hub: RealTimeHub):
    global labels_hub
    labels_hub = hub

# ---------- Pydantic Models ----------
class LabelMetadata(BaseModel):
    timeframe: str
    nearest_candle_timestamp_utc: str
    sample_offset_seconds: int
    price: Optional[float] = None
    pinnedCursorState: Optional[dict] = None

class LabelCreate(BaseModel):
    symbol: str
    label_type: str  # 'bullish', 'bearish', 'neutral', 'exit_bullish', 'exit_bearish'
    metadata: LabelMetadata
    tags: Optional[List[str]] = []

class LabelUpdate(BaseModel):
    metadata: Optional[LabelMetadata] = None
    label_type: Optional[str] = None
    tags: Optional[List[str]] = None

class LabelDelete(BaseModel):
    id: Optional[str] = None
    symbol: Optional[str] = None
    timeframe: Optional[str] = None
    timestamp: Optional[int] = None

class Label(BaseModel):
    id: str
    user_id: str
    symbol: str
    label_type: str
    metadata: dict
    tags: List[str]
    created_at: str
    updated_at: Optional[str] = None

class LabelResponse(BaseModel):
    id: Optional[str] = None
    success: bool
    message: str

class LabelsListResponse(BaseModel):
    labels: List[Label]

# ---------- Helper to get DB pool ----------
async def get_pool(request: Request) -> asyncpg.Pool:
    pool_key = "pg_pool"
    pool = getattr(request.app.state, pool_key, None)
    
    if pool is None:
        pool = await create_pool()
        setattr(request.app.state, pool_key, pool)
    
    return pool

# ---------- Helper to get current user (placeholder) ----------
def get_current_user():
    # For Sprint 1, return a default user
    # In production, this would extract from JWT token
    return "default-user"

# ---------- Helper to broadcast WebSocket messages ----------
async def broadcast_label_delta(message_type: str, payload: dict):
    if not labels_hub:
        logger.warning("Labels hub not initialized, skipping broadcast")
        return
    
    message = {
        "type": message_type,
        "seq": int(datetime.now().timestamp() * 1000),  # Simple sequence number
        "issuedAt": datetime.utcnow().isoformat() + "Z",
        "payload": payload
    }
    
    await labels_hub.broadcast(message)
    logger.info(f"Broadcasted {message_type} message")

# ---------- Routes ----------
@router.post("/api/labels", response_model=LabelResponse)
async def create_label(
    request: Request,
    label_data: LabelCreate
):
    """Create a new label with metadata-only storage"""
    logger.info(f"Received label create request: {label_data}")
    
    try:
        pool = await get_pool(request)
        current_user = get_current_user()
        
        # Validate metadata contains required fields
        required_fields = ["timeframe", "nearest_candle_timestamp_utc", "sample_offset_seconds"]
        for field in required_fields:
            if not hasattr(label_data.metadata, field):
                raise HTTPException(400, f"Missing required metadata field: {field}")
        
        # Normalize symbol and timeframe
        symbol_normalized = _normalize_symbol(label_data.symbol)
        
        # Normalize timeframe in metadata before storing
        metadata_dict = label_data.metadata.dict()
        metadata_dict['timeframe'] = _normalize_timeframe(metadata_dict['timeframe'])
        
        label_id = str(uuid.uuid4())
        
        async with pool.acquire() as conn:
            # Insert new label with metadata-only
            await conn.execute("""
                INSERT INTO ml_labels (id, user_id, symbol, label_type, metadata, tags)
                VALUES ($1, $2, $3, $4, $5, $6)
            """, 
                label_id, 
                current_user, 
                symbol_normalized, 
                label_data.label_type, 
                json.dumps(metadata_dict),
                label_data.tags or []
            )
        
        # Broadcast WebSocket delta
        await broadcast_label_delta("label.create", {
            "id": label_id,
            "user_id": current_user,
            "symbol": symbol_normalized,
            "label_type": label_data.label_type,
            "metadata": metadata_dict
        })
        
        logger.info(f"Created label {label_id} for {symbol_normalized}")
        return LabelResponse(id=label_id, success=True, message="Label created")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create label: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to create label: {str(e)}")

@router.patch("/api/labels/{label_id}", response_model=LabelResponse)
async def update_label(
    request: Request,
    label_id: str,
    updates: LabelUpdate
):
    """Update an existing label"""
    try:
        pool = await get_pool(request)
        current_user = get_current_user()
        
        async with pool.acquire() as conn:
            # Check if label exists and belongs to user
            existing = await conn.fetchrow("""
                SELECT metadata FROM ml_labels 
                WHERE id = $1 AND user_id = $2
            """, label_id, current_user)
            
            if not existing:
                raise HTTPException(404, "Label not found")
            
            # Merge metadata if provided
            current_metadata = json.loads(existing['metadata'])
            if updates.metadata:
                current_metadata.update(updates.metadata.dict(exclude_unset=True))
            
            # Prepare update query
            update_fields = []
            params = []
            param_count = 1
            
            if updates.label_type:
                update_fields.append(f"label_type = ${param_count}")
                params.append(updates.label_type)
                param_count += 1
            
            if updates.metadata:
                update_fields.append(f"metadata = ${param_count}")
                params.append(json.dumps(current_metadata))
                param_count += 1
            
            if updates.tags is not None:
                update_fields.append(f"tags = ${param_count}")
                params.append(updates.tags)
                param_count += 1
            
            update_fields.append(f"updated_at = NOW()")
            params.extend([label_id, current_user])
            
            if update_fields:
                query = f"""
                    UPDATE ml_labels 
                    SET {', '.join(update_fields)}
                    WHERE id = ${param_count} AND user_id = ${param_count + 1}
                """
                await conn.execute(query, *params)
        
        # Broadcast WebSocket delta
        patch_data = {}
        if updates.label_type:
            patch_data["label_type"] = updates.label_type
        if updates.metadata:
            patch_data["metadata"] = updates.metadata.dict(exclude_unset=True)
        if updates.tags is not None:
            patch_data["tags"] = updates.tags
            
        await broadcast_label_delta("label.update", {
            "id": label_id,
            "patch": patch_data
        })
        
        logger.info(f"Updated label {label_id}")
        return LabelResponse(id=label_id, success=True, message="Label updated")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update label: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to update label: {str(e)}")

@router.delete("/api/labels", response_model=LabelResponse)
async def delete_label(
    request: Request,
    label_data: LabelDelete
):
    """Delete a label by ID or by symbol/timeframe/timestamp"""
    try:
        pool = await get_pool(request)
        current_user = get_current_user()
        
        async with pool.acquire() as conn:
            if label_data.id:
                # Delete by ID
                result = await conn.execute("""
                    DELETE FROM ml_labels
                    WHERE id = $1 AND user_id = $2
                """, label_data.id, current_user)
                label_id = label_data.id
            else:
                # Delete by symbol/timeframe/timestamp (legacy support)
                if not all([label_data.symbol, label_data.timeframe, label_data.timestamp]):
                    raise HTTPException(400, "Either id or symbol+timeframe+timestamp required")
                
                symbol_normalized = _normalize_symbol(label_data.symbol)
                timeframe = _normalize_timeframe(label_data.timeframe)
                timestamp_utc = datetime.fromtimestamp(label_data.timestamp).isoformat() + "Z"
                
                # Find label by metadata
                label_row = await conn.fetchrow("""
                    SELECT id FROM ml_labels
                    WHERE user_id = $1 AND symbol = $2 
                    AND metadata->>'timeframe' = $3
                    AND metadata->>'nearest_candle_timestamp_utc' = $4
                """, current_user, symbol_normalized, timeframe, timestamp_utc)
                
                if not label_row:
                    return LabelResponse(success=False, message="No label found to delete")
                
                label_id = label_row['id']
                result = await conn.execute("""
                    DELETE FROM ml_labels WHERE id = $1
                """, label_id)
            
            rows_deleted = int(result.split()[-1])
            
        if rows_deleted > 0:
            # Broadcast WebSocket delta
            await broadcast_label_delta("label.delete", {
                "id": label_id
            })
            
            logger.info(f"Deleted label {label_id}")
            return LabelResponse(success=True, message="Label deleted")
        else:
            return LabelResponse(success=False, message="No label found to delete")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete label: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to delete label: {str(e)}")

@router.get("/api/labels", response_model=LabelsListResponse)
async def get_labels(
    request: Request,
    symbol: str,
    timeframe: str,
    from_timestamp: Optional[int] = None,
    to_timestamp: Optional[int] = None
):
    """Get labels for a symbol and timeframe, optionally filtered by time range"""
    try:
        pool = await get_pool(request)
        current_user = get_current_user()
        symbol_normalized = _normalize_symbol(symbol)
        timeframe_normalized = _normalize_timeframe(timeframe)
        
        # Build query with optional time filtering
        base_query = """
            SELECT id, user_id, symbol, label_type, metadata, tags, 
                   created_at, updated_at
            FROM ml_labels
            WHERE user_id = $1 AND symbol = $2 AND metadata->>'timeframe' = $3
        """
        params = [current_user, symbol_normalized, timeframe_normalized]
        
        if from_timestamp and to_timestamp:
            from_utc = datetime.fromtimestamp(from_timestamp).isoformat() + "Z"
            to_utc = datetime.fromtimestamp(to_timestamp).isoformat() + "Z"
            base_query += " AND metadata->>'nearest_candle_timestamp_utc' BETWEEN $4 AND $5"
            params.extend([from_utc, to_utc])
        
        base_query += " ORDER BY metadata->>'nearest_candle_timestamp_utc' ASC"
        
        async with pool.acquire() as conn:
            rows = await conn.fetch(base_query, *params)
            
        labels = []
        for row in rows:
            labels.append(Label(
                id=str(row['id']),
                user_id=row['user_id'],
                symbol=row['symbol'],
                label_type=row['label_type'],
                metadata=json.loads(row['metadata']),
                tags=row['tags'],
                created_at=row['created_at'].isoformat(),
                updated_at=row['updated_at'].isoformat() if row['updated_at'] else None
            ))
        
        logger.info(f"Retrieved {len(labels)} labels for {symbol_normalized}/{timeframe_normalized}")
        return LabelsListResponse(labels=labels)
        
    except Exception as e:
        logger.error(f"Failed to get labels: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get labels: {str(e)}")

def get_labels_hub():
    """Dependency to get the labels hub"""
    return labels_hub