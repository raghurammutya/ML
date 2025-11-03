"""
Authorization endpoints - Policy Decision Point (PDP)
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.redis_client import get_redis, RedisClient
from app.api.dependencies import get_current_user, get_service_token
from app.models import User
from app.services.authz_service import AuthzService
from app.schemas.authz import (
    AuthzCheckRequest,
    AuthzCheckResponse,
    BulkAuthzCheckRequest,
    BulkAuthzCheckResponse,
    PoliciesResponse,
    PolicyInfo,
    PermissionCheckRequest,
    PermissionCheckResponse,
    CacheInvalidationRequest,
    CacheInvalidationResponse
)


router = APIRouter()


def get_authz_service(
    db: Session = Depends(get_db),
    redis: RedisClient = Depends(get_redis)
) -> AuthzService:
    """
    Get authorization service instance

    Args:
        db: Database session
        redis: Redis client

    Returns:
        AuthzService instance
    """
    return AuthzService(db, redis)


@router.post("/check", response_model=AuthzCheckResponse)
async def check_authorization(
    request_data: AuthzCheckRequest,
    authz_service: AuthzService = Depends(get_authz_service),
    use_cache: bool = Query(default=True, description="Use Redis cache for faster responses")
):
    """
    Check if subject is authorized to perform action on resource

    This is the **Policy Decision Point (PDP)** - the central authorization endpoint
    that all services should call to check permissions.

    **Request Body:**
    - subject: Subject identifier (e.g., "user:123", "service:ticker_service")
    - action: Action to perform (e.g., "trade:place_order", "account:view")
    - resource: Resource identifier (e.g., "trading_account:456", "user:123")
    - context: Optional context for condition evaluation (e.g., {"time": "2025-11-03T10:00:00Z"})

    **Returns:**
    - allowed: Whether the action is permitted
    - decision: "allow", "deny", or "default_deny"
    - matched_policy: Name of the policy that matched
    - reason: Human-readable reason for decision
    - cached: Whether result was served from cache

    **Examples:**

    Check if user can place order:
    ```json
    {
      "subject": "user:123",
      "action": "trade:place_order",
      "resource": "trading_account:456"
    }
    ```

    Check with context:
    ```json
    {
      "subject": "user:123",
      "action": "trade:place_order",
      "resource": "trading_account:456",
      "context": {
        "market_hours": true,
        "risk_score": "low"
      }
    }
    ```

    **Performance:**
    - Cache TTL: 60 seconds
    - Average response time (cached): < 5ms
    - Average response time (uncached): < 20ms

    **Authentication:**
    - This endpoint accepts both user tokens and service tokens
    - Use service token for service-to-service authorization checks
    """
    try:
        # Perform authorization check
        allowed, decision_type, matched_policy = authz_service.check_permission(
            subject=request_data.subject,
            action=request_data.action,
            resource=request_data.resource,
            context=request_data.context,
            use_cache=use_cache
        )

        # Build reason
        if decision_type == "allow" and matched_policy:
            reason = f"Action allowed by policy: {matched_policy}"
        elif decision_type == "deny" and matched_policy:
            reason = f"Action denied by policy: {matched_policy}"
        else:
            reason = "Action denied (no matching policy)"

        return AuthzCheckResponse(
            allowed=allowed,
            decision=decision_type,
            matched_policy=matched_policy,
            reason=reason,
            cached=False  # TODO: Track if result came from cache
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Authorization check failed: {str(e)}"
        )


@router.post("/check/bulk", response_model=BulkAuthzCheckResponse)
async def check_bulk_authorization(
    request_data: BulkAuthzCheckRequest,
    authz_service: AuthzService = Depends(get_authz_service),
    use_cache: bool = Query(default=True, description="Use Redis cache")
):
    """
    Check multiple authorization requests in a single call

    **Performance optimization** for checking multiple permissions at once.
    Useful when rendering UI elements that depend on multiple permissions.

    **Request Body:**
    - checks: List of authorization checks (max 100)

    **Returns:**
    - results: List of authorization decisions in same order as requests
    - summary: Statistics (allowed, denied, cached)

    **Example:**
    ```json
    {
      "checks": [
        {
          "subject": "user:123",
          "action": "trade:place_order",
          "resource": "trading_account:456"
        },
        {
          "subject": "user:123",
          "action": "account:view",
          "resource": "trading_account:789"
        }
      ]
    }
    ```

    **Limits:**
    - Maximum 100 checks per request
    - Recommended: Keep under 20 for best performance
    """
    results = []
    allowed_count = 0
    denied_count = 0
    cached_count = 0

    for check in request_data.checks:
        try:
            allowed, decision_type, matched_policy = authz_service.check_permission(
                subject=check.subject,
                action=check.action,
                resource=check.resource,
                context=check.context,
                use_cache=use_cache
            )

            if allowed:
                allowed_count += 1
                reason = f"Action allowed by policy: {matched_policy}"
            else:
                denied_count += 1
                reason = f"Action denied" + (f" by policy: {matched_policy}" if matched_policy else " (no matching policy)")

            results.append(AuthzCheckResponse(
                allowed=allowed,
                decision=decision_type,
                matched_policy=matched_policy,
                reason=reason,
                cached=False
            ))

        except Exception as e:
            # On error, deny the specific check
            denied_count += 1
            results.append(AuthzCheckResponse(
                allowed=False,
                decision="error",
                matched_policy=None,
                reason=f"Error evaluating policy: {str(e)}",
                cached=False
            ))

    return BulkAuthzCheckResponse(
        results=results,
        summary={
            "allowed": allowed_count,
            "denied": denied_count,
            "cached": cached_count
        }
    )


@router.get("/policies", response_model=PoliciesResponse)
async def list_policies(
    authz_service: AuthzService = Depends(get_authz_service),
    current_user: User = Depends(get_current_user),
    enabled_only: bool = Query(default=True, description="Only return enabled policies"),
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=50, ge=1, le=100, description="Items per page")
):
    """
    List authorization policies

    **Returns:**
    - policies: List of policies with details
    - total: Total number of policies
    - page: Current page number
    - page_size: Items per page

    **Filters:**
    - enabled_only: Only return enabled policies (default: true)

    **Pagination:**
    - page: Page number (1-indexed)
    - page_size: Items per page (max 100)

    **Authentication:**
    - Requires authenticated user
    - Use for debugging and auditing authorization rules

    **Example Response:**
    ```json
    {
      "policies": [
        {
          "policy_id": 1,
          "name": "Trading Account Owner Can Trade",
          "effect": "ALLOW",
          "subjects": ["user:*"],
          "actions": ["trade:place_order", "trade:cancel_order"],
          "resources": ["trading_account:*"],
          "priority": 100,
          "enabled": true
        }
      ],
      "total": 5,
      "page": 1,
      "page_size": 50
    }
    ```
    """
    try:
        policies, total = authz_service.list_policies(
            enabled_only=enabled_only,
            page=page,
            page_size=page_size
        )

        policy_infos = [
            PolicyInfo(
                policy_id=p.policy_id,
                name=p.name,
                description=p.description,
                effect=p.effect.value,
                subjects=p.subjects,
                actions=p.actions,
                resources=p.resources,
                conditions=p.conditions,
                priority=p.priority,
                enabled=p.enabled,
                created_at=p.created_at.isoformat(),
                updated_at=p.updated_at.isoformat() if p.updated_at else None
            )
            for p in policies
        ]

        return PoliciesResponse(
            policies=policy_infos,
            total=total,
            page=page,
            page_size=page_size
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list policies: {str(e)}"
        )


@router.post("/permissions/check", response_model=PermissionCheckResponse)
async def check_trading_account_permission(
    request_data: PermissionCheckRequest,
    authz_service: AuthzService = Depends(get_authz_service)
):
    """
    Check if user has permission on a trading account

    **Simplified endpoint** for common use case of checking trading account permissions.
    Checks both ownership and membership.

    **Request Body:**
    - user_id: User ID to check
    - trading_account_id: Trading account ID
    - permission: Permission level ("view", "trade", "manage")

    **Returns:**
    - has_permission: Whether user has the requested permission
    - permission_source: "owner", "membership", or null
    - membership_role: Role if source is membership

    **Example:**
    ```json
    {
      "user_id": 123,
      "trading_account_id": 456,
      "permission": "trade"
    }
    ```

    **Permission Levels:**
    - **view**: Can view account details and positions
    - **trade**: Can place and cancel orders
    - **manage**: Can modify account settings and memberships (owner only)
    """
    try:
        has_permission, source, role = authz_service.check_trading_account_permission(
            user_id=request_data.user_id,
            trading_account_id=request_data.trading_account_id,
            permission=request_data.permission
        )

        return PermissionCheckResponse(
            has_permission=has_permission,
            permission_source=source,
            membership_role=role
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Permission check failed: {str(e)}"
        )


@router.post("/cache/invalidate", response_model=CacheInvalidationResponse)
async def invalidate_cache(
    request_data: CacheInvalidationRequest,
    authz_service: AuthzService = Depends(get_authz_service),
    _service_token: dict = Depends(get_service_token)
):
    """
    Invalidate authorization cache

    **Use this endpoint** when permissions change and cache needs to be cleared.

    **Request Body:**
    - subject: Invalidate cache for specific subject (optional)
    - resource: Invalidate cache for specific resource (optional)
    - action: Invalidate cache for specific action (optional)
    - invalidate_all: Invalidate entire authorization cache (default: false)

    **Returns:**
    - invalidated_keys: Number of cache keys invalidated
    - message: Success message

    **Examples:**

    Invalidate all cache entries for a user:
    ```json
    {
      "subject": "user:123"
    }
    ```

    Invalidate cache for a specific resource:
    ```json
    {
      "resource": "trading_account:456"
    }
    ```

    Invalidate entire cache:
    ```json
    {
      "invalidate_all": true
    }
    ```

    **Authentication:**
    - Requires service token (not user token)
    - Only internal services should call this endpoint

    **When to Invalidate:**
    - After granting/revoking trading account membership
    - After changing user roles
    - After updating policy definitions
    - After disabling/enabling policies
    """
    try:
        if request_data.invalidate_all:
            count = authz_service.invalidate_cache()
            message = "Entire authorization cache invalidated"
        else:
            count = authz_service.invalidate_cache(
                subject=request_data.subject,
                action=request_data.action,
                resource=request_data.resource
            )
            message = "Authorization cache invalidated successfully"

        return CacheInvalidationResponse(
            invalidated_keys=count,
            message=message
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Cache invalidation failed: {str(e)}"
        )
