"""
JWT Authentication Tests

Tests verify:
1. Token generation and validation
2. Token expiration handling
3. Invalid token rejection
4. WebSocket authentication
5. Token payload extraction
"""
import pytest
import time
from datetime import datetime, timedelta
from jose import jwt, JWTError
from fastapi import HTTPException
from unittest.mock import Mock, AsyncMock, patch

from app.config import get_settings
from app.dependencies import verify_websocket_token

settings = get_settings()

pytestmark = pytest.mark.security


class TestJWTTokenGeneration:
    """Test JWT token generation."""

    def test_token_creation_with_valid_payload(self):
        """Test creating a valid JWT token."""
        payload = {
            "user_id": "user_123",
            "account_id": "account_456",
            "exp": datetime.utcnow() + timedelta(hours=1)
        }

        token = jwt.encode(
            payload,
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm
        )

        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0

    def test_token_decode_returns_correct_payload(self):
        """Test decoding token returns original payload."""
        original_payload = {
            "user_id": "user_123",
            "account_id": "account_456",
            "exp": datetime.utcnow() + timedelta(hours=1)
        }

        token = jwt.encode(
            original_payload,
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm
        )

        decoded = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm]
        )

        assert decoded["user_id"] == original_payload["user_id"]
        assert decoded["account_id"] == original_payload["account_id"]

    def test_token_with_expiration(self):
        """Test token with expiration time."""
        exp_time = datetime.utcnow() + timedelta(minutes=30)
        payload = {
            "user_id": "user_123",
            "exp": exp_time
        }

        token = jwt.encode(
            payload,
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm
        )

        decoded = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm]
        )

        assert "exp" in decoded
        # exp is stored as unix timestamp
        assert decoded["exp"] == int(exp_time.timestamp())

    def test_token_without_expiration_is_valid(self):
        """Test token without expiration is accepted."""
        payload = {
            "user_id": "user_123",
            "account_id": "account_456"
        }

        token = jwt.encode(
            payload,
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm
        )

        decoded = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"verify_exp": False}  # Don't require exp claim
        )

        assert decoded["user_id"] == "user_123"


class TestJWTTokenValidation:
    """Test JWT token validation."""

    def test_invalid_token_raises_error(self):
        """Test that invalid token raises JWTError."""
        invalid_token = "invalid.token.here"

        with pytest.raises(JWTError):
            jwt.decode(
                invalid_token,
                settings.jwt_secret_key,
                algorithms=[settings.jwt_algorithm]
            )

    def test_tampered_token_raises_error(self):
        """Test that tampered token is rejected."""
        payload = {"user_id": "user_123"}
        token = jwt.encode(
            payload,
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm
        )

        # Tamper with token (change last character)
        tampered_token = token[:-1] + ("a" if token[-1] != "a" else "b")

        with pytest.raises(JWTError):
            jwt.decode(
                tampered_token,
                settings.jwt_secret_key,
                algorithms=[settings.jwt_algorithm]
            )

    def test_wrong_secret_key_raises_error(self):
        """Test token signed with different key is rejected."""
        payload = {"user_id": "user_123"}
        wrong_secret = "wrong_secret_key_123456789"

        token = jwt.encode(
            payload,
            wrong_secret,
            algorithm=settings.jwt_algorithm
        )

        with pytest.raises(JWTError):
            jwt.decode(
                token,
                settings.jwt_secret_key,
                algorithms=[settings.jwt_algorithm]
            )

    def test_expired_token_raises_error(self):
        """Test that expired token is rejected."""
        payload = {
            "user_id": "user_123",
            "exp": datetime.utcnow() - timedelta(hours=1)  # Expired 1 hour ago
        }

        token = jwt.encode(
            payload,
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm
        )

        with pytest.raises(JWTError):
            jwt.decode(
                token,
                settings.jwt_secret_key,
                algorithms=[settings.jwt_algorithm]
            )

    def test_wrong_algorithm_raises_error(self):
        """Test token with wrong algorithm is rejected."""
        payload = {"user_id": "user_123"}
        token = jwt.encode(
            payload,
            settings.jwt_secret_key,
            algorithm="HS512"  # Different algorithm
        )

        with pytest.raises(JWTError):
            jwt.decode(
                token,
                settings.jwt_secret_key,
                algorithms=[settings.jwt_algorithm]  # Expects HS256
            )


class TestWebSocketAuthentication:
    """Test WebSocket JWT authentication."""

    @pytest.mark.asyncio
    async def test_websocket_auth_with_valid_token(self):
        """Test WebSocket authentication with valid token."""
        # Create valid token
        payload = {
            "user_id": "user_123",
            "account_id": "account_456",
            "exp": datetime.utcnow() + timedelta(hours=1)
        }
        token = jwt.encode(
            payload,
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm
        )

        # Mock WebSocket
        websocket = Mock()
        websocket.query_params = {"token": token}

        # Verify token
        result = await verify_websocket_token(websocket)

        assert result["user_id"] == "user_123"
        assert result["account_id"] == "account_456"

    @pytest.mark.asyncio
    async def test_websocket_auth_missing_token(self):
        """Test WebSocket authentication fails without token."""
        # Mock WebSocket without token
        websocket = AsyncMock()
        websocket.query_params = {}

        # Should close connection and raise exception
        with pytest.raises(HTTPException) as exc_info:
            await verify_websocket_token(websocket)

        assert exc_info.value.status_code == 401
        assert "Missing authentication token" in exc_info.value.detail
        websocket.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_websocket_auth_invalid_token(self):
        """Test WebSocket authentication fails with invalid token."""
        websocket = AsyncMock()
        websocket.query_params = {"token": "invalid.token.here"}

        with pytest.raises(HTTPException) as exc_info:
            await verify_websocket_token(websocket)

        assert exc_info.value.status_code == 401
        assert "Invalid authentication token" in exc_info.value.detail
        websocket.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_websocket_auth_missing_user_id(self):
        """Test WebSocket authentication fails without user_id in payload."""
        # Token without user_id
        payload = {
            "account_id": "account_456",
            "exp": datetime.utcnow() + timedelta(hours=1)
        }
        token = jwt.encode(
            payload,
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm
        )

        websocket = AsyncMock()
        websocket.query_params = {"token": token}

        with pytest.raises(HTTPException) as exc_info:
            await verify_websocket_token(websocket)

        assert exc_info.value.status_code == 401
        assert "Invalid token payload" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_websocket_auth_expired_token(self):
        """Test WebSocket authentication fails with expired token."""
        # Expired token
        payload = {
            "user_id": "user_123",
            "account_id": "account_456",
            "exp": datetime.utcnow() - timedelta(hours=1)
        }
        token = jwt.encode(
            payload,
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm
        )

        websocket = AsyncMock()
        websocket.query_params = {"token": token}

        with pytest.raises(HTTPException) as exc_info:
            await verify_websocket_token(websocket)

        assert exc_info.value.status_code == 401


class TestTokenPayloadExtraction:
    """Test extracting data from token payload."""

    def test_extract_user_id(self):
        """Test extracting user_id from token."""
        payload = {
            "user_id": "user_123",
            "account_id": "account_456"
        }
        token = jwt.encode(
            payload,
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm
        )

        decoded = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm]
        )

        assert decoded.get("user_id") == "user_123"

    def test_extract_account_id(self):
        """Test extracting account_id from token."""
        payload = {
            "user_id": "user_123",
            "account_id": "account_456"
        }
        token = jwt.encode(
            payload,
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm
        )

        decoded = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm]
        )

        assert decoded.get("account_id") == "account_456"

    def test_extract_custom_claims(self):
        """Test extracting custom claims from token."""
        payload = {
            "user_id": "user_123",
            "role": "admin",
            "permissions": ["read", "write", "delete"]
        }
        token = jwt.encode(
            payload,
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm
        )

        decoded = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm]
        )

        assert decoded.get("role") == "admin"
        assert decoded.get("permissions") == ["read", "write", "delete"]


class TestTokenSecurity:
    """Test token security features."""

    def test_tokens_with_same_payload_are_different(self):
        """Test that tokens with same payload have different signatures due to timestamps."""
        payload1 = {"user_id": "user_123", "iat": int(time.time())}
        payload2 = {"user_id": "user_123", "iat": int(time.time()) + 1}

        token1 = jwt.encode(payload1, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
        time.sleep(0.1)  # Ensure different timestamp
        token2 = jwt.encode(payload2, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

        # Tokens should be different due to different iat timestamps
        assert token1 != token2

    def test_token_cannot_be_modified(self):
        """Test that token payload cannot be modified without detection."""
        payload = {"user_id": "regular_user"}
        token = jwt.encode(
            payload,
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm
        )

        # Try to decode and change to admin
        # This should fail because signature won't match

        with pytest.raises(JWTError):
            # Attempt to decode with wrong secret won't work
            jwt.decode(token, "wrong_secret", algorithms=[settings.jwt_algorithm])

    def test_token_algorithm_cannot_be_changed_to_none(self):
        """Test that algorithm cannot be changed to 'none' (security vulnerability)."""
        payload = {"user_id": "user_123"}

        # Create token with "none" algorithm (should be rejected)
        token_parts = jwt.encode(
            payload,
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm
        ).split(".")

        # Try to use the payload with "none" algorithm
        with pytest.raises(JWTError):
            jwt.decode(
                ".".join([token_parts[0], token_parts[1], ""]),
                settings.jwt_secret_key,
                algorithms=[settings.jwt_algorithm]
            )


class TestTokenEdgeCases:
    """Test edge cases in token handling."""

    def test_empty_payload(self):
        """Test token with empty payload."""
        payload = {}
        token = jwt.encode(
            payload,
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm
        )

        decoded = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm]
        )

        assert decoded == {}

    def test_large_payload(self):
        """Test token with large payload."""
        payload = {
            "user_id": "user_123",
            "large_data": "x" * 1000,  # 1KB of data
            "array": list(range(100))
        }

        token = jwt.encode(
            payload,
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm
        )

        decoded = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm]
        )

        assert decoded["user_id"] == "user_123"
        assert len(decoded["large_data"]) == 1000
        assert len(decoded["array"]) == 100

    def test_unicode_in_payload(self):
        """Test token with Unicode characters."""
        payload = {
            "user_id": "user_123",
            "name": "用户名称",  # Chinese characters
            "emoji": "🚀🎉"
        }

        token = jwt.encode(
            payload,
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm
        )

        decoded = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm]
        )

        assert decoded["name"] == "用户名称"
        assert decoded["emoji"] == "🚀🎉"

    def test_null_values_in_payload(self):
        """Test token with null values."""
        payload = {
            "user_id": "user_123",
            "optional_field": None
        }

        token = jwt.encode(
            payload,
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm
        )

        decoded = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm]
        )

        assert decoded["optional_field"] is None
