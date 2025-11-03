"""
Authentication endpoints
"""

from typing import Union
from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.redis_client import get_redis, RedisClient
from app.core.config import settings
from app.api.dependencies import (
    get_auth_service,
    get_current_user,
    get_current_session_id,
    get_refresh_token_from_cookie,
    get_client_ip,
    get_user_agent
)
from app.models import User
from app.services.auth_service import AuthService
from app.services.password_reset_service import PasswordResetService
from app.schemas.auth import (
    RegisterRequest,
    RegisterResponse,
    LoginRequest,
    LoginResponse,
    MfaRequiredResponse,
    MfaVerifyRequest,
    LogoutRequest,
    LogoutResponse,
    TokenRefreshResponse,
    SessionsResponse,
    SessionInfo
)
from app.schemas.password_reset import (
    PasswordResetRequestRequest,
    PasswordResetRequestResponse,
    PasswordResetRequest,
    PasswordResetResponse
)
from app.schemas.oauth import (
    OAuthInitiateRequest,
    OAuthInitiateResponse,
    OAuthCallbackRequest,
    OAuthCallbackResponse
)
from app.utils.security import generate_device_fingerprint
from app.services.jwt_service import jwt_service
from app.services.oauth_service import OAuthService


router = APIRouter()


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(
    request_data: RegisterRequest,
    auth_service: AuthService = Depends(get_auth_service),
    ip: str = Depends(get_client_ip)
):
    """
    Register a new user account

    **Request Body:**
    - email: Valid email address
    - password: Minimum 12 characters with complexity requirements
    - name: User's full name
    - phone: Optional phone number
    - timezone: User timezone (default: UTC)
    - locale: User locale (default: en-US)

    **Returns:**
    - user_id: Created user ID
    - email: User email
    - status: Account status (pending_verification)
    - verification_email_sent: Whether verification email was sent
    - created_at: Account creation timestamp

    **Errors:**
    - 400: Validation failed (weak password, invalid email)
    - 409: Email already registered
    - 429: Rate limit exceeded (5 registrations per hour per IP)
    """
    try:
        # Check rate limit
        rate_limit_key = f"ratelimit:register:{ip}"
        allowed, remaining = auth_service.redis.check_rate_limit(
            rate_limit_key,
            settings.RATELIMIT_REGISTER_ATTEMPTS,
            settings.RATELIMIT_REGISTER_WINDOW_HOURS * 3600
        )

        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded. Please try again later.",
                headers={"Retry-After": str(settings.RATELIMIT_REGISTER_WINDOW_HOURS * 3600)}
            )

        # Register user
        user, validation = auth_service.register_user(
            email=request_data.email,
            password=request_data.password,
            name=request_data.name,
            phone=request_data.phone,
            timezone=request_data.timezone,
            locale=request_data.locale
        )

        return RegisterResponse(
            user_id=user.user_id,
            email=user.email,
            status=user.status.value,
            verification_email_sent=False,  # TODO: Implement email sending
            created_at=user.created_at.isoformat()
        )

    except ValueError as e:
        # Check if it's a duplicate email error
        if "already registered" in str(e):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(e)
            )
        # Otherwise it's a validation error
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/login", response_model=Union[LoginResponse, MfaRequiredResponse])
async def login(
    response: Response,
    request_data: LoginRequest,
    request: Request,
    auth_service: AuthService = Depends(get_auth_service),
    ip: str = Depends(get_client_ip),
    user_agent: str = Depends(get_user_agent)
):
    """
    Authenticate user with email and password

    **Request Body:**
    - email: User email
    - password: User password
    - persist_session: Whether to create long-lived session (default: false)
    - device_fingerprint: Optional device fingerprint

    **Returns:**
    - If MFA not required:
      - access_token: JWT access token (15 min)
      - refresh_token: Refresh token (only if persist_session=true)
      - token_type: "Bearer"
      - expires_in: Token expiration in seconds
      - user: User information

    - If MFA required:
      - status: "mfa_required"
      - session_token: Temporary token for MFA verification
      - methods: Available MFA methods (["totp"])
      - message: Instructions

    **Errors:**
    - 401: Invalid credentials
    - 423: Account locked (too many failed attempts)
    - 429: Rate limit exceeded (5 attempts per 15 minutes)
    """
    try:
        # Generate device fingerprint if not provided
        device_fingerprint = request_data.device_fingerprint
        if not device_fingerprint:
            device_fingerprint = generate_device_fingerprint(user_agent, ip)

        # Attempt login
        result = auth_service.login(
            email=request_data.email,
            password=request_data.password,
            device_fingerprint=device_fingerprint,
            ip=ip,
            persist_session=request_data.persist_session
        )

        if result is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password"
            )

        # Check if MFA is required
        if result.get("status") == "mfa_required":
            return MfaRequiredResponse(**result)

        # Set refresh token cookie if present
        if result.get("refresh_token"):
            response.set_cookie(
                key=settings.SESSION_COOKIE_NAME,
                value=result["refresh_token"],
                httponly=settings.SESSION_COOKIE_HTTPONLY,
                secure=settings.SESSION_COOKIE_SECURE,
                samesite=settings.SESSION_COOKIE_SAMESITE,
                max_age=settings.JWT_REFRESH_TOKEN_TTL_DAYS * 86400
            )

        return LoginResponse(
            access_token=result["access_token"],
            token_type=result["token_type"],
            expires_in=result["expires_in"],
            user=result["user"],
            refresh_token=None  # Don't send in body, only cookie
        )

    except ValueError as e:
        error_msg = str(e)

        # Rate limit error
        if "Rate limit exceeded" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=error_msg,
                headers={"Retry-After": str(settings.RATELIMIT_LOGIN_WINDOW_MINUTES * 60)}
            )

        # Account status errors
        if "deactivated" in error_msg or "suspended" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=error_msg
            )

        # Generic error
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg
        )


@router.post("/mfa/verify", response_model=LoginResponse)
async def verify_mfa(
    response: Response,
    request_data: MfaVerifyRequest,
    request: Request,
    auth_service: AuthService = Depends(get_auth_service),
    ip: str = Depends(get_client_ip),
    user_agent: str = Depends(get_user_agent)
):
    """
    Verify MFA code and complete login

    **Request Body:**
    - session_token: Temporary session token from login
    - code: 6-digit TOTP code

    **Returns:**
    - access_token: JWT access token
    - token_type: "Bearer"
    - expires_in: Token expiration in seconds
    - user: User information

    **Errors:**
    - 400: Invalid or expired session token
    - 401: Invalid MFA code
    - 429: Too many attempts (3 per session token)
    """
    try:
        # Generate device fingerprint
        device_fingerprint = generate_device_fingerprint(user_agent, ip)

        # Verify MFA
        result = auth_service.verify_mfa_and_login(
            session_token=request_data.session_token,
            totp_code=request_data.code,
            device_fingerprint=device_fingerprint,
            ip=ip,
            persist_session=True  # Assume persist if MFA is enabled
        )

        # Set refresh token cookie
        if result.get("refresh_token"):
            response.set_cookie(
                key=settings.SESSION_COOKIE_NAME,
                value=result["refresh_token"],
                httponly=settings.SESSION_COOKIE_HTTPONLY,
                secure=settings.SESSION_COOKIE_SECURE,
                samesite=settings.SESSION_COOKIE_SAMESITE,
                max_age=settings.JWT_REFRESH_TOKEN_TTL_DAYS * 86400
            )

        return LoginResponse(
            access_token=result["access_token"],
            token_type=result["token_type"],
            expires_in=result["expires_in"],
            user=result["user"],
            refresh_token=None
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/refresh", response_model=TokenRefreshResponse)
async def refresh_token(
    response: Response,
    refresh_token: str = Depends(get_refresh_token_from_cookie),
    auth_service: AuthService = Depends(get_auth_service)
):
    """
    Refresh access token using refresh token

    **Cookie:**
    - __Secure-refresh_token: Refresh token (HTTP-only cookie)

    **Returns:**
    - access_token: New JWT access token
    - refresh_token: New rotated refresh token (in cookie)
    - token_type: "Bearer"
    - expires_in: Token expiration in seconds

    **Errors:**
    - 401: Invalid or expired refresh token
    - 401: Refresh token reuse detected (security violation)
    - 429: Too many refresh requests (10 per minute)
    """
    try:
        # Refresh token and get new tokens
        result = auth_service.refresh_access_token(refresh_token)

        # Set new refresh token cookie
        response.set_cookie(
            key=settings.SESSION_COOKIE_NAME,
            value=result["refresh_token"],
            httponly=settings.SESSION_COOKIE_HTTPONLY,
            secure=settings.SESSION_COOKIE_SECURE,
            samesite=settings.SESSION_COOKIE_SAMESITE,
            max_age=settings.JWT_REFRESH_TOKEN_TTL_DAYS * 86400
        )

        return TokenRefreshResponse(
            access_token=result["access_token"],
            refresh_token="[set in cookie]",  # Don't send in body
            token_type=result["token_type"],
            expires_in=result["expires_in"]
        )

    except ValueError as e:
        error_msg = str(e)

        # Reuse detection is a security violation
        if "reuse detected" in error_msg:
            # Clear the cookie
            response.delete_cookie(settings.SESSION_COOKIE_NAME)

            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=error_msg
            )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error_msg
        )


@router.post("/logout", response_model=LogoutResponse)
async def logout(
    response: Response,
    request_data: LogoutRequest,
    current_user: User = Depends(get_current_user),
    session_id: str = Depends(get_current_session_id),
    auth_service: AuthService = Depends(get_auth_service)
):
    """
    Logout user and invalidate session

    **Request Body:**
    - all_devices: Whether to logout from all devices (default: false)

    **Returns:**
    - message: Success message
    - sessions_revoked: Number of sessions invalidated

    **Errors:**
    - 401: Invalid or missing token
    """
    # Logout
    sessions_revoked = auth_service.logout(
        session_id=session_id,
        user_id=current_user.user_id,
        all_devices=request_data.all_devices
    )

    # Clear refresh token cookie
    response.delete_cookie(settings.SESSION_COOKIE_NAME)

    return LogoutResponse(
        message="Logged out successfully",
        sessions_revoked=sessions_revoked
    )


@router.get("/sessions", response_model=SessionsResponse)
async def get_sessions(
    current_user: User = Depends(get_current_user),
    session_id: str = Depends(get_current_session_id),
    redis: RedisClient = Depends(get_redis)
):
    """
    Get all active sessions for current user

    **Returns:**
    - sessions: List of active sessions
    - total: Total session count

    **Errors:**
    - 401: Invalid or missing token
    """
    # Get current session
    current_session = redis.get_session(session_id)

    if not current_session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session not found"
        )

    # TODO: Implement pattern matching to find all user sessions
    # For now, return only current session
    sessions = [
        SessionInfo(
            session_id=session_id,
            device_fingerprint=current_session.get("device_fingerprint", ""),
            ip=current_session.get("ip", ""),
            country=None,  # TODO: Implement country detection
            created_at=current_session.get("created_at", ""),
            last_active_at=current_session.get("last_active_at", ""),
            current=True
        )
    ]

    return SessionsResponse(
        sessions=sessions,
        total=len(sessions)
    )


@router.post("/password/reset-request", response_model=PasswordResetRequestResponse)
async def request_password_reset(
    request_data: PasswordResetRequestRequest,
    client_ip: str = Depends(get_client_ip),
    db: Session = Depends(get_db),
    redis: RedisClient = Depends(get_redis)
):
    """
    Request password reset

    Sends password reset email with secure token.
    Always returns success (security - don't reveal if email exists).

    **Request Body:**
    - email: Email address of account

    **Example:**
    ```json
    {
      "email": "user@example.com"
    }
    ```

    **Returns:**
    - message: Success message (always same message for security)
    - expires_in_minutes: Token expiry time (30 minutes)

    **Security:**
    - Always returns same response (don't reveal if email exists)
    - Token expires in 30 minutes
    - Token can only be used once
    - Rate limited per IP (TODO)

    **Process:**
    1. Request password reset with email
    2. Check email inbox for reset link
    3. Click link or copy token
    4. Call `/password/reset` with token and new password

    **Note:** In production, this sends an email. In development, token is logged.
    """
    password_reset_service = PasswordResetService(db, redis)

    # Generate reset token (returns None if email doesn't exist, but we don't tell user)
    reset_token = password_reset_service.request_password_reset(
        email=request_data.email,
        ip=client_ip
    )

    # TODO: In development, log the token for testing
    if reset_token and settings.ENVIRONMENT == "development":
        print(f"\n[DEV] Password reset token for {request_data.email}: {reset_token}\n")

    # Always return same message (security best practice)
    return PasswordResetRequestResponse(
        email=request_data.email,
        expires_in_minutes=settings.PASSWORD_RESET_TOKEN_TTL_MINUTES
    )


@router.post("/password/reset", response_model=PasswordResetResponse)
async def reset_password(
    request_data: PasswordResetRequest,
    db: Session = Depends(get_db),
    redis: RedisClient = Depends(get_redis)
):
    """
    Complete password reset

    Uses token from email to reset password.

    **Request Body:**
    - token: Reset token from email (32+ characters)
    - new_password: New password (min 8 characters)

    **Example:**
    ```json
    {
      "token": "abc123...",
      "new_password": "NewSecurePassword123!"
    }
    ```

    **Returns:**
    - user_id: User ID
    - message: Success message

    **Password Requirements:**
    - Minimum 8 characters
    - Must contain uppercase and lowercase
    - Must contain numbers
    - Must contain special characters
    - Cannot contain email or name

    **Security:**
    - Token can only be used once
    - Token expires after 30 minutes
    - Password strength validation
    - Old sessions remain valid (user stays logged in)

    **Errors:**
    - 400: Invalid/expired token or weak password
    """
    password_reset_service = PasswordResetService(db, redis)

    try:
        user = password_reset_service.reset_password(
            token=request_data.token,
            new_password=request_data.new_password
        )

        return PasswordResetResponse(
            user_id=user.user_id
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/oauth/google", response_model=OAuthInitiateResponse)
async def initiate_google_oauth(
    request_data: OAuthInitiateRequest,
    db: Session = Depends(get_db),
    redis: RedisClient = Depends(get_redis)
):
    """
    Initiate Google OAuth flow

    Returns authorization URL for user to visit Google's consent screen.

    **Request Body:**
    - provider: OAuth provider (default: "google")
    - redirect_uri: Optional custom redirect URI (must be pre-registered)

    **Returns:**
    - authorization_url: URL to redirect user to for OAuth consent
    - state: CSRF protection state token (verify on callback)
    - provider: OAuth provider name

    **Example:**
    ```json
    {
      "provider": "google"
    }
    ```

    **Flow:**
    1. Call this endpoint to get authorization URL
    2. Redirect user to authorization_url
    3. User authorizes app on Google
    4. Google redirects to callback URL with code and state
    5. Call `/oauth/google/callback` with code and state

    **Errors:**
    - 400: OAuth provider not supported or not configured
    - 503: Google OAuth is disabled

    **Security:**
    - State token is stored in Redis with 10-minute expiry
    - State must match on callback (CSRF protection)
    """
    oauth_service = OAuthService(db, redis)

    try:
        result = oauth_service.initiate_oauth_flow(
            provider=request_data.provider,
            redirect_uri=request_data.redirect_uri
        )

        return OAuthInitiateResponse(**result)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/oauth/google/callback", response_model=OAuthCallbackResponse)
async def handle_google_oauth_callback(
    response: Response,
    request_data: OAuthCallbackRequest,
    request: Request,
    db: Session = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
    ip: str = Depends(get_client_ip),
    user_agent: str = Depends(get_user_agent)
):
    """
    Handle Google OAuth callback

    Completes OAuth flow by exchanging code for tokens and creating/logging in user.

    **Request Body:**
    - code: Authorization code from Google (from redirect URL)
    - state: CSRF protection state token (from initiate endpoint)
    - persist_session: Whether to create long-lived session (default: true)

    **Returns:**
    - access_token: JWT access token (15 min)
    - refresh_token: Refresh token (set in HTTP-only cookie)
    - token_type: "Bearer"
    - expires_in: Token expiration in seconds
    - user: User information
    - is_new_user: Whether this is a newly created account

    **Example:**
    ```json
    {
      "code": "4/0AY0e-g7...",
      "state": "abc123...",
      "persist_session": true
    }
    ```

    **Flow:**
    1. Validate state token (CSRF protection)
    2. Exchange code for Google access token
    3. Fetch user info from Google
    4. Create new user or update existing user
    5. Generate JWT tokens
    6. Set refresh token in HTTP-only cookie

    **User Creation:**
    - If email exists: Updates OAuth provider info
    - If new user: Creates account with email verified (if Google verified)
    - Status: ACTIVE if email verified, PENDING_VERIFICATION otherwise

    **Errors:**
    - 400: Invalid state token, code exchange failed, or user creation failed
    - 401: OAuth authorization failed

    **Security:**
    - State token validation (CSRF protection)
    - Single-use state tokens
    - Refresh token in HTTP-only cookie
    - Email verification from Google
    """
    oauth_service = OAuthService(db, redis)

    try:
        # Generate device fingerprint
        device_fingerprint = generate_device_fingerprint(user_agent, ip)

        # Handle OAuth callback
        result = oauth_service.handle_oauth_callback(
            code=request_data.code,
            state=request_data.state,
            device_fingerprint=device_fingerprint,
            ip=ip,
            persist_session=request_data.persist_session
        )

        # Set refresh token cookie if present
        if result.get("refresh_token"):
            response.set_cookie(
                key=settings.SESSION_COOKIE_NAME,
                value=result["refresh_token"],
                httponly=settings.SESSION_COOKIE_HTTPONLY,
                secure=settings.SESSION_COOKIE_SECURE,
                samesite=settings.SESSION_COOKIE_SAMESITE,
                max_age=settings.JWT_REFRESH_TOKEN_TTL_DAYS * 86400
            )

        return OAuthCallbackResponse(
            access_token=result["access_token"],
            token_type=result["token_type"],
            expires_in=result["expires_in"],
            user=result["user"],
            is_new_user=result["is_new_user"],
            refresh_token=None  # Don't send in body, only cookie
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/.well-known/jwks.json")
async def get_jwks():
    """
    Get JSON Web Key Set (JWKS) for JWT validation

    This endpoint provides the public keys used to verify JWT signatures.
    Clients and services should use this endpoint to fetch public keys
    for token validation.

    **Returns:**
    - keys: List of public keys in JWK format

    **Usage:**
    This is a public endpoint (no authentication required) used by:
    - Other services for verifying access tokens
    - API gateways for token validation
    - Client applications for token verification
    """
    return jwt_service.get_jwks()
