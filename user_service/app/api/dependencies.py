"""
API dependencies for authentication and authorization
"""

from typing import Optional
from fastapi import Depends, HTTPException, status, Request, Cookie
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.redis_client import get_redis, RedisClient
from app.models import User, ApiKey, RateLimitTier
from app.services.jwt_service import jwt_service
from app.services.auth_service import AuthService
from app.services.api_key_service import ApiKeyService


# Security scheme
security = HTTPBearer()


def get_auth_service(
    db: Session = Depends(get_db),
    redis: RedisClient = Depends(get_redis)
) -> AuthService:
    """
    Get authentication service instance

    Args:
        db: Database session
        redis: Redis client

    Returns:
        AuthService instance
    """
    return AuthService(db, redis)


async def get_current_user_token(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> str:
    """
    Extract and validate bearer token from Authorization header

    Args:
        credentials: HTTP authorization credentials

    Returns:
        Access token string

    Raises:
        HTTPException: If token is missing or invalid format
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return credentials.credentials


async def get_current_user(
    token: str = Depends(get_current_user_token),
    db: Session = Depends(get_db)
) -> User:
    """
    Get current authenticated user from access token

    Args:
        token: Access token
        db: Database session

    Returns:
        Current user object

    Raises:
        HTTPException: If token is invalid or user not found
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        # Validate token
        payload = jwt_service.validate_token(token, token_type="access")

        # Extract user ID
        user_id_str = payload.get("sub", "").split(":", 1)[-1]
        if not user_id_str:
            raise credentials_exception

        user_id = int(user_id_str)

    except (JWTError, ValueError, IndexError):
        raise credentials_exception

    # Get user from database
    user = db.query(User).filter(User.user_id == user_id).first()
    if user is None:
        raise credentials_exception

    # Check if user is active
    if user.status == "deactivated":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account has been deactivated"
        )

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    Get current active user (must be in active status)

    Args:
        current_user: Current user from token

    Returns:
        Current active user

    Raises:
        HTTPException: If user is not active
    """
    if current_user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Account status is {current_user.status}. Active status required."
        )

    return current_user


async def get_current_session_id(
    token: str = Depends(get_current_user_token)
) -> str:
    """
    Extract session ID from access token

    Args:
        token: Access token

    Returns:
        Session ID

    Raises:
        HTTPException: If token is invalid or session ID missing
    """
    try:
        payload = jwt_service.validate_token(token, token_type="access")
        session_id = payload.get("sid")

        if not session_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session ID missing from token"
            )

        return session_id

    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )


async def require_role(required_role: str):
    """
    Dependency factory to require specific role

    Args:
        required_role: Role name required (e.g., 'admin', 'compliance')

    Returns:
        Dependency function that checks role
    """
    async def role_checker(current_user: User = Depends(get_current_active_user)) -> User:
        user_roles = [ur.role.name for ur in current_user.roles]

        if required_role not in user_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{required_role}' required"
            )

        return current_user

    return role_checker


async def get_admin_user(
    current_user: User = Depends(get_current_active_user)
) -> User:
    """
    Require admin role

    Args:
        current_user: Current active user

    Returns:
        Admin user

    Raises:
        HTTPException: If user is not admin
    """
    checker = await require_role("admin")
    return await checker(current_user)


async def get_service_token(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> dict:
    """
    Validate service-to-service token

    Args:
        credentials: HTTP authorization credentials

    Returns:
        Token payload with service info

    Raises:
        HTTPException: If token is invalid or not a service token
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing service credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        # Validate token
        payload = jwt_service.validate_token(credentials.credentials, token_type="access")

        # Check if it's a service token
        subject = payload.get("sub", "")
        if not subject.startswith("service:"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Service token required"
            )

        return payload

    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid service token: {str(e)}"
        )


async def get_refresh_token_from_cookie(
    refresh_token: Optional[str] = Cookie(None, alias="__Secure-refresh_token")
) -> str:
    """
    Extract refresh token from secure HTTP-only cookie

    Args:
        refresh_token: Refresh token from cookie

    Returns:
        Refresh token string

    Raises:
        HTTPException: If refresh token cookie is missing
    """
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token cookie missing"
        )

    return refresh_token


async def get_client_ip(request: Request) -> str:
    """
    Get client IP address from request

    Args:
        request: FastAPI request object

    Returns:
        Client IP address
    """
    # Check for X-Forwarded-For header (if behind proxy)
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # Take the first IP in the chain
        return forwarded_for.split(",")[0].strip()

    # Check X-Real-IP header
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip

    # Fall back to direct client host
    return request.client.host if request.client else "unknown"


async def get_user_agent(request: Request) -> str:
    """
    Get user agent from request

    Args:
        request: FastAPI request object

    Returns:
        User agent string
    """
    return request.headers.get("User-Agent", "unknown")


async def get_current_user_from_api_key(
    request: Request,
    db: Session = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
    client_ip: str = Depends(get_client_ip)
) -> User:
    """
    Authenticate user via API key.

    Supports two header formats:
    - X-API-Key: sb_30d4d5ea_bbb52c64...
    - Authorization: Bearer sb_30d4d5ea_bbb52c64...

    Args:
        request: FastAPI request object
        db: Database session
        redis: Redis client
        client_ip: Client IP address

    Returns:
        Authenticated user

    Raises:
        HTTPException: If API key is invalid or missing
    """
    # Extract API key from headers
    x_api_key = request.headers.get("X-API-Key")
    authorization = request.headers.get("Authorization", "")

    api_key_string = None

    if x_api_key:
        api_key_string = x_api_key
    elif authorization.startswith("Bearer sb_"):
        api_key_string = authorization.replace("Bearer ", "")

    if not api_key_string:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required. Provide via X-API-Key header or Authorization: Bearer header"
        )

    # Parse key (format: sb_{prefix}_{secret})
    if not api_key_string.startswith("sb_"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key format"
        )

    parts = api_key_string.split("_")
    if len(parts) != 3:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key format. Expected: sb_{prefix}_{secret}"
        )

    key_prefix = f"sb_{parts[1]}"
    secret = parts[2]

    # Verify API key
    api_key_service = ApiKeyService(db, redis)
    api_key = api_key_service.verify_api_key(key_prefix, secret, client_ip)

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired API key"
        )

    # Check rate limit based on tier
    rate_limits = {
        RateLimitTier.FREE: (100, 3600),       # 100/hour
        RateLimitTier.STANDARD: (1000, 3600),  # 1000/hour
        RateLimitTier.PREMIUM: (10000, 3600),  # 10000/hour
        RateLimitTier.UNLIMITED: None
    }

    if api_key.rate_limit_tier != RateLimitTier.UNLIMITED:
        limit, window = rate_limits[api_key.rate_limit_tier]
        rate_limit_key = f"ratelimit:apikey:{api_key.api_key_id}"
        allowed, remaining = redis.check_rate_limit(rate_limit_key, limit, window)

        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded for API key. Tier: {api_key.rate_limit_tier.value}",
                headers={"Retry-After": str(window)}
            )

    # Return user
    return api_key.user


async def get_current_user_flexible(
    request: Request,
    db: Session = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
    client_ip: str = Depends(get_client_ip)
) -> User:
    """
    Authenticate user via JWT OR API key.

    Priority:
    1. Try JWT (Authorization: Bearer eyJ...)
    2. Try API key (X-API-Key or Authorization: Bearer sb_...)

    Args:
        request: FastAPI request object
        db: Database session
        redis: Redis client
        client_ip: Client IP address

    Returns:
        Authenticated user

    Raises:
        HTTPException: If authentication fails
    """
    authorization = request.headers.get("Authorization", "")
    x_api_key = request.headers.get("X-API-Key")

    # Try JWT first (if not an API key)
    if authorization and not authorization.startswith("Bearer sb_"):
        try:
            token = authorization.replace("Bearer ", "")
            return await get_current_user(token=token, db=db)
        except HTTPException:
            pass

    # Try API key
    return await get_current_user_from_api_key(
        request=request,
        db=db,
        redis=redis,
        client_ip=client_ip
    )


def require_scope(required_scope: str):
    """
    Dependency factory to require specific API key scope.

    Usage:
        @router.post("/orders")
        async def place_order(
            current_user: User = Depends(require_scope("trade"))
        ):
            ...

    Args:
        required_scope: Scope name required (e.g., 'trade', 'read')

    Returns:
        Dependency function that checks scope
    """
    async def dependency(
        request: Request,
        db: Session = Depends(get_db),
        redis: RedisClient = Depends(get_redis),
        client_ip: str = Depends(get_client_ip)
    ) -> User:
        # Check if API key was used
        x_api_key = request.headers.get("X-API-Key")
        authorization = request.headers.get("Authorization", "")

        is_api_key = x_api_key or authorization.startswith("Bearer sb_")

        if not is_api_key:
            # Not API key auth, just authenticate normally (JWT doesn't have scopes)
            return await get_current_user_flexible(
                request=request,
                db=db,
                redis=redis,
                client_ip=client_ip
            )

        # API key authentication - check scope
        user = await get_current_user_from_api_key(
            request=request,
            db=db,
            redis=redis,
            client_ip=client_ip
        )

        # Get API key to check scopes
        if authorization.startswith("Bearer sb_"):
            api_key_string = authorization.replace("Bearer ", "")
        else:
            api_key_string = x_api_key

        parts = api_key_string.split("_")
        key_prefix = f"sb_{parts[1]}"
        secret = parts[2]

        api_key_service = ApiKeyService(db, redis)
        api_key = api_key_service.verify_api_key(key_prefix, secret, client_ip)

        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key"
            )

        # Check if scope is present
        if required_scope not in api_key.scopes and "*" not in api_key.scopes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"API key missing required scope: {required_scope}"
            )

        return user

    return dependency
