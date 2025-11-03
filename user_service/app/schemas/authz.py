"""
Pydantic schemas for authorization endpoints
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


# Request schemas

class AuthzCheckRequest(BaseModel):
    """
    Authorization check request (Policy Decision Point)

    This is the primary request schema for checking if a subject
    is authorized to perform an action on a resource.
    """
    subject: str = Field(
        ...,
        description="Subject identifier (e.g., 'user:123', 'service:ticker_service')",
        example="user:123"
    )
    action: str = Field(
        ...,
        description="Action to perform (e.g., 'trade:place_order', 'account:view')",
        example="trade:place_order"
    )
    resource: str = Field(
        ...,
        description="Resource identifier (e.g., 'trading_account:456', 'user:123')",
        example="trading_account:456"
    )
    context: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Additional context for policy evaluation (e.g., time, location, risk_score)"
    )


class BulkAuthzCheckRequest(BaseModel):
    """
    Bulk authorization check request

    Allows checking multiple permissions in a single request
    for better performance.
    """
    checks: List[AuthzCheckRequest] = Field(
        ...,
        min_items=1,
        max_items=100,
        description="List of authorization checks to perform (max 100)"
    )


# Response schemas

class AuthzCheckResponse(BaseModel):
    """
    Authorization check response

    Returns the decision (allow/deny) along with metadata
    about which policy was applied.
    """
    allowed: bool = Field(
        ...,
        description="Whether the action is allowed"
    )
    decision: str = Field(
        ...,
        description="Decision type: 'allow', 'deny', or 'default_deny'",
        example="allow"
    )
    matched_policy: Optional[str] = Field(
        None,
        description="Name of the policy that matched (if any)"
    )
    reason: Optional[str] = Field(
        None,
        description="Human-readable reason for the decision"
    )
    cached: bool = Field(
        default=False,
        description="Whether this result was served from cache"
    )


class BulkAuthzCheckResponse(BaseModel):
    """Bulk authorization check response"""
    results: List[AuthzCheckResponse] = Field(
        ...,
        description="List of authorization decisions in same order as requests"
    )
    summary: Dict[str, int] = Field(
        ...,
        description="Summary statistics (allowed, denied, cached)",
        example={"allowed": 5, "denied": 2, "cached": 3}
    )


class PolicyInfo(BaseModel):
    """Policy information for listing"""
    policy_id: int
    name: str
    description: Optional[str] = None
    effect: str  # ALLOW or DENY
    subjects: List[str]
    actions: List[str]
    resources: List[str]
    conditions: Optional[Dict[str, Any]] = None
    priority: int
    enabled: bool
    created_at: str
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True


class PoliciesResponse(BaseModel):
    """Response for listing policies"""
    policies: List[PolicyInfo]
    total: int
    page: int = 1
    page_size: int = 50


class PolicyEvaluationDebug(BaseModel):
    """
    Debug information for policy evaluation

    Used for troubleshooting authorization decisions.
    Only returned when debug mode is enabled.
    """
    evaluated_policies: List[Dict[str, Any]] = Field(
        ...,
        description="List of policies that were evaluated"
    )
    matched_policies: List[str] = Field(
        ...,
        description="Names of policies that matched the request"
    )
    final_decision: str = Field(
        ...,
        description="Final decision after applying priority rules"
    )
    evaluation_time_ms: float = Field(
        ...,
        description="Time taken to evaluate policies in milliseconds"
    )
    cache_hit: bool = Field(
        ...,
        description="Whether the result was found in cache"
    )


class AuthzCheckDebugResponse(AuthzCheckResponse):
    """Authorization check response with debug information"""
    debug: Optional[PolicyEvaluationDebug] = Field(
        None,
        description="Debug information (only included if debug=true in request)"
    )


# Permission checking schemas (for trading accounts)

class PermissionCheckRequest(BaseModel):
    """
    Check if user has permission on a specific trading account

    Simplified schema for common use case of checking
    trading account permissions.
    """
    user_id: int = Field(..., description="User ID to check")
    trading_account_id: int = Field(..., description="Trading account ID")
    permission: str = Field(
        ...,
        description="Permission to check (e.g., 'view', 'trade', 'manage')",
        example="trade"
    )


class PermissionCheckResponse(BaseModel):
    """Permission check response"""
    has_permission: bool = Field(
        ...,
        description="Whether user has the requested permission"
    )
    permission_source: Optional[str] = Field(
        None,
        description="Source of permission: 'owner', 'membership', or 'policy'",
        example="owner"
    )
    membership_role: Optional[str] = Field(
        None,
        description="Role if permission is from membership"
    )


# Cache invalidation schemas

class CacheInvalidationRequest(BaseModel):
    """
    Request to invalidate authorization cache

    Used when permissions change and cache needs to be cleared.
    """
    subject: Optional[str] = Field(
        None,
        description="Invalidate cache for specific subject (e.g., 'user:123')"
    )
    resource: Optional[str] = Field(
        None,
        description="Invalidate cache for specific resource"
    )
    action: Optional[str] = Field(
        None,
        description="Invalidate cache for specific action"
    )
    invalidate_all: bool = Field(
        default=False,
        description="Invalidate entire authorization cache"
    )


class CacheInvalidationResponse(BaseModel):
    """Cache invalidation response"""
    invalidated_keys: int = Field(
        ...,
        description="Number of cache keys invalidated"
    )
    message: str = Field(
        default="Cache invalidated successfully"
    )
