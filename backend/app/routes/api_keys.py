"""
API Key Management Routes

Endpoints for creating, listing, and revoking API keys.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime, timedelta
import logging

from ..auth import APIKeyManager, get_api_key_manager, APIKey, require_api_key

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api-keys", tags=["api-keys"])


# ============================================================================
# Request/Response Models
# ============================================================================

class CreateAPIKeyRequest(BaseModel):
    """Request model for creating API key."""
    name: str = Field(..., min_length=1, max_length=255, description="Friendly name for the key")
    description: Optional[str] = Field(None, description="Optional description")
    strategy_id: Optional[str] = Field(None, description="Link to strategy (optional)")

    # Permissions
    can_read: bool = Field(True, description="Can read market data and account info")
    can_trade: bool = Field(False, description="Can place orders")
    can_cancel: bool = Field(False, description="Can cancel orders")
    can_modify: bool = Field(False, description="Can modify orders")

    # Rate limits
    rate_limit_orders_per_sec: int = Field(10, ge=1, le=100, description="Max orders per second")
    rate_limit_requests_per_min: int = Field(200, ge=10, le=1000, description="Max requests per minute")

    # Security
    ip_whitelist: Optional[List[str]] = Field(None, description="Allowed IP addresses (empty = allow all)")
    allowed_accounts: Optional[List[str]] = Field(None, description="Allowed trading accounts (empty = allow all)")

    # Expiration
    expires_in_days: Optional[int] = Field(None, ge=1, le=365, description="Expire after N days (null = never)")


class APIKeyResponse(BaseModel):
    """Response model for API key (without the actual key)."""
    key_id: str
    key_prefix: str
    user_id: str
    name: str
    description: Optional[str]
    permissions: Dict[str, bool]
    rate_limit_orders_per_sec: int
    rate_limit_requests_per_min: int
    ip_whitelist: List[str]
    allowed_accounts: List[str]
    created_at: datetime
    expires_at: Optional[datetime]
    last_used_at: Optional[datetime]
    is_active: bool
    revoked_at: Optional[datetime]
    revoke_reason: Optional[str]


class CreateAPIKeyResponse(BaseModel):
    """Response when creating API key (includes the actual key ONCE)."""
    api_key: str = Field(..., description="API key - SAVE THIS! It won't be shown again.")
    key_id: str
    key_prefix: str
    user_id: str
    name: str
    permissions: Dict[str, bool]
    expires_at: Optional[str]


class RevokeAPIKeyRequest(BaseModel):
    """Request to revoke API key."""
    reason: Optional[str] = Field(None, description="Reason for revocation")


# ============================================================================
# Endpoints
# ============================================================================

@router.post("", response_model=CreateAPIKeyResponse)
async def create_api_key(
    request: CreateAPIKeyRequest,
    req: Request,
    manager: APIKeyManager = Depends(get_api_key_manager)
) -> CreateAPIKeyResponse:
    """
    Create a new API key.

    **IMPORTANT**: The API key is only shown once. Save it securely!

    Args:
        request: API key configuration

    Returns:
        API key details (including the actual key)
    """
    try:
        # Build permissions dict
        permissions = {
            "can_read": request.can_read,
            "can_trade": request.can_trade,
            "can_cancel": request.can_cancel,
            "can_modify": request.can_modify
        }

        # Calculate expiration
        expires_at = None
        if request.expires_in_days:
            expires_at = datetime.now() + timedelta(days=request.expires_in_days)

        # Get user_id from request (in production, get from authenticated user)
        # For now, use a default user_id
        user_id = "default-user"  # TODO: Replace with actual authenticated user

        # Create API key
        result = await manager.create_api_key(
            user_id=user_id,
            name=request.name,
            description=request.description,
            permissions=permissions,
            strategy_id=request.strategy_id,
            rate_limit_orders_per_sec=request.rate_limit_orders_per_sec,
            rate_limit_requests_per_min=request.rate_limit_requests_per_min,
            ip_whitelist=request.ip_whitelist,
            allowed_accounts=request.allowed_accounts,
            expires_at=expires_at,
            created_by=user_id  # TODO: Get from authenticated user
        )

        logger.info(f"Created API key {result['key_prefix']} for user {user_id}")

        return CreateAPIKeyResponse(**result)
    except Exception as e:
        logger.error(f"Error creating API key: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("", response_model=List[APIKeyResponse])
async def list_api_keys(
    manager: APIKeyManager = Depends(get_api_key_manager)
) -> List[APIKeyResponse]:
    """
    List all API keys for the current user.

    Returns:
        List of API keys (without the actual key values)
    """
    try:
        # Get user_id (in production, from authenticated user)
        user_id = "default-user"  # TODO: Replace with actual authenticated user

        keys = await manager.list_api_keys(user_id)

        return [APIKeyResponse(**key) for key in keys]
    except Exception as e:
        logger.error(f"Error listing API keys: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{key_id}", response_model=APIKeyResponse)
async def get_api_key(
    key_id: str,
    manager: APIKeyManager = Depends(get_api_key_manager)
) -> APIKeyResponse:
    """
    Get details of a specific API key.

    Args:
        key_id: API key ID

    Returns:
        API key details (without the actual key)
    """
    try:
        # Get user_id (in production, from authenticated user)
        user_id = "default-user"  # TODO: Replace with actual authenticated user

        keys = await manager.list_api_keys(user_id)
        key = next((k for k in keys if k["key_id"] == key_id), None)

        if not key:
            raise HTTPException(status_code=404, detail=f"API key {key_id} not found")

        return APIKeyResponse(**key)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting API key: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{key_id}")
async def revoke_api_key(
    key_id: str,
    request: RevokeAPIKeyRequest,
    manager: APIKeyManager = Depends(get_api_key_manager)
) -> Dict[str, str]:
    """
    Revoke (deactivate) an API key.

    Args:
        key_id: API key ID to revoke
        request: Revocation reason

    Returns:
        Success message
    """
    try:
        # Get user_id (in production, from authenticated user)
        user_id = "default-user"  # TODO: Replace with actual authenticated user

        await manager.revoke_api_key(
            key_id=key_id,
            revoked_by=user_id,
            reason=request.reason
        )

        logger.info(f"Revoked API key {key_id}")

        return {
            "status": "success",
            "message": f"API key {key_id} revoked",
            "key_id": key_id
        }
    except Exception as e:
        logger.error(f"Error revoking API key: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/validate")
async def validate_api_key(
    req: Request,
    api_key: APIKey = Depends(require_api_key)
) -> Dict[str, Any]:
    """
    Validate current API key.

    Requires: Valid API key in Authorization header

    Returns:
        API key details if valid
    """
    return {
        "status": "valid",
        "key_id": str(api_key.key_id),
        "user_id": api_key.user_id,
        "name": api_key.name,
        "permissions": api_key.permissions,
        "rate_limits": {
            "orders_per_sec": api_key.rate_limit_orders_per_sec,
            "requests_per_min": api_key.rate_limit_requests_per_min
        }
    }
