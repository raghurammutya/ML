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
from app.models import User
from app.services.jwt_service import jwt_service
from app.services.auth_service import AuthService


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
