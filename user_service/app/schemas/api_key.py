"""
API Key schemas
"""

from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field, validator

from app.models import RateLimitTier


class ApiKeyCreateRequest(BaseModel):
    """API key creation request"""
    name: str = Field(..., min_length=1, max_length=255, description="User-friendly name")
    scopes: List[str] = Field(..., min_items=1, description="List of scopes")
    description: Optional[str] = Field(None, description="Optional description")
    ip_whitelist: Optional[List[str]] = Field(None, description="Optional IP whitelist")
    rate_limit_tier: Optional[RateLimitTier] = Field(RateLimitTier.STANDARD, description="Rate limit tier")
    expires_in_days: Optional[int] = Field(None, ge=1, le=3650, description="Expiration in days (max 10 years)")

    @validator('scopes')
    def validate_scopes(cls, v):
        valid_scopes = ['read', 'trade', 'admin', 'account:manage', 'strategy:execute', '*']
        for scope in v:
            if scope not in valid_scopes:
                raise ValueError(f"Invalid scope: {scope}. Valid scopes: {', '.join(valid_scopes)}")
        return v

    class Config:
        use_enum_values = True


class ApiKeyCreateResponse(BaseModel):
    """API key creation response"""
    api_key_id: int
    api_key: str = Field(..., description="Full API key (save this, won't be shown again!)")
    key_prefix: str
    name: str
    description: Optional[str]
    scopes: List[str]
    ip_whitelist: Optional[List[str]]
    rate_limit_tier: str
    expires_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


class ApiKeyResponse(BaseModel):
    """API key response (without secret)"""
    api_key_id: int
    key_prefix: str
    name: str
    description: Optional[str]
    scopes: List[str]
    ip_whitelist: Optional[List[str]]
    rate_limit_tier: str
    last_used_at: Optional[datetime]
    last_used_ip: Optional[str]
    usage_count: int
    expires_at: Optional[datetime]
    created_at: datetime
    revoked_at: Optional[datetime]
    revoked_reason: Optional[str]

    class Config:
        from_attributes = True


class ApiKeyListResponse(BaseModel):
    """API key list response"""
    api_keys: List[ApiKeyResponse]


class ApiKeyUpdateRequest(BaseModel):
    """API key update request"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    scopes: Optional[List[str]] = None
    ip_whitelist: Optional[List[str]] = None
    rate_limit_tier: Optional[RateLimitTier] = None

    @validator('scopes')
    def validate_scopes(cls, v):
        if v is None:
            return v
        valid_scopes = ['read', 'trade', 'admin', 'account:manage', 'strategy:execute', '*']
        for scope in v:
            if scope not in valid_scopes:
                raise ValueError(f"Invalid scope: {scope}")
        return v

    class Config:
        use_enum_values = True


class ApiKeyRotateResponse(BaseModel):
    """API key rotation response"""
    new_api_key_id: int
    api_key: str = Field(..., description="New full API key (save this!)")
    key_prefix: str
    name: str
    scopes: List[str]
    old_api_key_id: int

    class Config:
        from_attributes = True
