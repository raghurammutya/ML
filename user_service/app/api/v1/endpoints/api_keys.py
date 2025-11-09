"""
API Key management endpoints
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.redis_client import get_redis, RedisClient
from app.api.dependencies import get_current_user
from app.models import User, RateLimitTier
from app.services.api_key_service import ApiKeyService
from app.schemas.api_key import (
    ApiKeyCreateRequest,
    ApiKeyCreateResponse,
    ApiKeyResponse,
    ApiKeyListResponse,
    ApiKeyUpdateRequest,
    ApiKeyRotateResponse
)


router = APIRouter()


def get_api_key_service(
    db: Session = Depends(get_db),
    redis: RedisClient = Depends(get_redis)
) -> ApiKeyService:
    """Get API key service dependency"""
    return ApiKeyService(db, redis)


@router.post("", response_model=ApiKeyCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    request_data: ApiKeyCreateRequest,
    current_user: User = Depends(get_current_user),
    api_key_service: ApiKeyService = Depends(get_api_key_service)
):
    """
    Create a new API key.

    **WARNING:** The full API key is returned ONLY ONCE and cannot be retrieved later.
    Store it securely.

    **Request Body:**
    - name: User-friendly name (e.g., "Production Bot")
    - scopes: List of scopes (e.g., ["read", "trade"])
    - description: Optional description
    - ip_whitelist: Optional list of allowed IPs
    - rate_limit_tier: Rate limit tier (free, standard, premium, unlimited)
    - expires_in_days: Optional expiration in days

    **Returns:**
    - api_key_id: Created API key ID
    - api_key: Full API key string (save this!)
    - key_prefix: Key prefix for identification
    - name, scopes, expires_at, etc.

    **Scopes:**
    - read: Read-only access
    - trade: Place and cancel orders
    - admin: Full access
    - account:manage: Manage trading accounts
    - strategy:execute: Execute strategies
    - *: All permissions

    **Rate Limit Tiers:**
    - free: 100 requests/hour
    - standard: 1,000 requests/hour
    - premium: 10,000 requests/hour
    - unlimited: No limit
    """
    try:
        api_key, full_key = api_key_service.generate_api_key(
            user_id=current_user.user_id,
            name=request_data.name,
            scopes=request_data.scopes,
            description=request_data.description,
            ip_whitelist=request_data.ip_whitelist,
            rate_limit_tier=request_data.rate_limit_tier or RateLimitTier.STANDARD,
            expires_in_days=request_data.expires_in_days
        )

        return ApiKeyCreateResponse(
            api_key_id=api_key.api_key_id,
            api_key=full_key,
            key_prefix=api_key.key_prefix,
            name=api_key.name,
            description=api_key.description,
            scopes=api_key.scopes,
            ip_whitelist=api_key.ip_whitelist,
            rate_limit_tier=api_key.rate_limit_tier.value,
            expires_at=api_key.expires_at,
            created_at=api_key.created_at
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create API key: {str(e)}"
        )


@router.get("", response_model=ApiKeyListResponse)
async def list_api_keys(
    include_revoked: bool = False,
    current_user: User = Depends(get_current_user),
    api_key_service: ApiKeyService = Depends(get_api_key_service)
):
    """
    List all API keys for the current user.

    **Query Parameters:**
    - include_revoked: Include revoked keys (default: false)

    **Returns:**
    - List of API keys (without secrets)
    """
    api_keys = api_key_service.list_user_api_keys(
        current_user.user_id,
        include_revoked=include_revoked
    )

    return ApiKeyListResponse(
        api_keys=[
            ApiKeyResponse(
                api_key_id=key.api_key_id,
                key_prefix=key.key_prefix,
                name=key.name,
                description=key.description,
                scopes=key.scopes,
                ip_whitelist=key.ip_whitelist,
                rate_limit_tier=key.rate_limit_tier.value,
                last_used_at=key.last_used_at,
                last_used_ip=key.last_used_ip,
                usage_count=key.usage_count,
                expires_at=key.expires_at,
                created_at=key.created_at,
                revoked_at=key.revoked_at,
                revoked_reason=key.revoked_reason
            )
            for key in api_keys
        ]
    )


@router.get("/{api_key_id}", response_model=ApiKeyResponse)
async def get_api_key(
    api_key_id: int,
    current_user: User = Depends(get_current_user),
    api_key_service: ApiKeyService = Depends(get_api_key_service)
):
    """
    Get a specific API key.

    **Path Parameters:**
    - api_key_id: API key ID

    **Returns:**
    - API key details (without secret)
    """
    api_key = api_key_service.get_api_key(api_key_id, current_user.user_id)

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )

    return ApiKeyResponse(
        api_key_id=api_key.api_key_id,
        key_prefix=api_key.key_prefix,
        name=api_key.name,
        description=api_key.description,
        scopes=api_key.scopes,
        ip_whitelist=api_key.ip_whitelist,
        rate_limit_tier=api_key.rate_limit_tier.value,
        last_used_at=api_key.last_used_at,
        last_used_ip=api_key.last_used_ip,
        usage_count=api_key.usage_count,
        expires_at=api_key.expires_at,
        created_at=api_key.created_at,
        revoked_at=api_key.revoked_at,
        revoked_reason=api_key.revoked_reason
    )


@router.delete("/{api_key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(
    api_key_id: int,
    reason: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    api_key_service: ApiKeyService = Depends(get_api_key_service)
):
    """
    Revoke an API key.

    **Path Parameters:**
    - api_key_id: API key ID to revoke

    **Query Parameters:**
    - reason: Optional reason for revocation

    **Returns:**
    - 204 No Content on success
    - 404 if API key not found
    """
    success = api_key_service.revoke_api_key(
        api_key_id=api_key_id,
        revoked_by_user_id=current_user.user_id,
        reason=reason
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found or already revoked"
        )


@router.put("/{api_key_id}", response_model=ApiKeyResponse)
async def update_api_key(
    api_key_id: int,
    request_data: ApiKeyUpdateRequest,
    current_user: User = Depends(get_current_user),
    api_key_service: ApiKeyService = Depends(get_api_key_service)
):
    """
    Update an API key.

    **Path Parameters:**
    - api_key_id: API key ID to update

    **Request Body:**
    - name: New name (optional)
    - description: New description (optional)
    - scopes: New scopes (optional)
    - ip_whitelist: New IP whitelist (optional)
    - rate_limit_tier: New rate limit tier (optional)

    **Returns:**
    - Updated API key
    """
    api_key = api_key_service.update_api_key(
        api_key_id=api_key_id,
        user_id=current_user.user_id,
        name=request_data.name,
        description=request_data.description,
        scopes=request_data.scopes,
        ip_whitelist=request_data.ip_whitelist,
        rate_limit_tier=request_data.rate_limit_tier
    )

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found or revoked"
        )

    return ApiKeyResponse(
        api_key_id=api_key.api_key_id,
        key_prefix=api_key.key_prefix,
        name=api_key.name,
        description=api_key.description,
        scopes=api_key.scopes,
        ip_whitelist=api_key.ip_whitelist,
        rate_limit_tier=api_key.rate_limit_tier.value,
        last_used_at=api_key.last_used_at,
        last_used_ip=api_key.last_used_ip,
        usage_count=api_key.usage_count,
        expires_at=api_key.expires_at,
        created_at=api_key.created_at,
        revoked_at=api_key.revoked_at,
        revoked_reason=api_key.revoked_reason
    )


@router.post("/{api_key_id}/rotate", response_model=ApiKeyRotateResponse)
async def rotate_api_key(
    api_key_id: int,
    current_user: User = Depends(get_current_user),
    api_key_service: ApiKeyService = Depends(get_api_key_service)
):
    """
    Rotate an API key (revoke old, create new with same settings).

    **WARNING:** The new API key is returned ONLY ONCE. Store it securely.
    The old key is immediately revoked.

    **Path Parameters:**
    - api_key_id: API key ID to rotate

    **Returns:**
    - new_api_key_id: New API key ID
    - api_key: New full API key string
    - old_api_key_id: Old API key ID (now revoked)
    """
    new_key, full_key = api_key_service.rotate_api_key(
        api_key_id=api_key_id,
        user_id=current_user.user_id
    )

    if not new_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found or already revoked"
        )

    return ApiKeyRotateResponse(
        new_api_key_id=new_key.api_key_id,
        api_key=full_key,
        key_prefix=new_key.key_prefix,
        name=new_key.name,
        scopes=new_key.scopes,
        old_api_key_id=api_key_id
    )
